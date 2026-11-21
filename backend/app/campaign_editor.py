import asyncio
from typing import Annotated, Literal

import httpx
from pydantic import BaseModel, Field, PositiveInt, TypeAdapter, model_validator
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.keitaro import CatalogOption, load_catalog
from app.models import StreamOfferPreference


class CampaignEditorError(Exception):
    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class FlowOffer(BaseModel):
    offer_id: PositiveInt
    share: Annotated[int, Field(ge=0, le=100)]
    state: Literal["active", "disabled"]


class CampaignFlow(BaseModel):
    id: PositiveInt
    campaign_id: PositiveInt
    name: str
    state: str
    flow_schema: str = Field(validation_alias="schema")
    offers: list[FlowOffer] = Field(default_factory=list)


class EditorOffer(BaseModel):
    offer_id: PositiveInt
    share: int
    state: Literal["active", "disabled", "removed"]
    pinned: bool = False


class EditorFlow(BaseModel):
    id: PositiveInt
    name: str
    state: str
    offers: list[EditorOffer]
    clicks_today: int | None = None


class CampaignEditorData(BaseModel):
    campaign: CatalogOption
    admin_url: str
    flows: list[EditorFlow]
    offers: list[CatalogOption]


class UpdateFlowOffers(BaseModel):
    expected_offers: list[FlowOffer]
    expected_pinned_offer_ids: list[PositiveInt] = Field(default_factory=list)
    offers: list[FlowOffer]
    pinned_offer_ids: list[PositiveInt] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_offer_shares(self) -> "UpdateFlowOffers":
        active = {offer.offer_id: offer.share for offer in self.offers if offer.state == "active"}
        if len({offer.offer_id for offer in self.offers}) != len(self.offers):
            raise ValueError("Оффер может быть добавлен в поток только один раз.")
        if not set(self.pinned_offer_ids) <= active.keys():
            raise ValueError("Можно закреплять доли только активных офферов.")
        if self.offers != self.expected_offers and active and sum(active.values()) != 100:
            raise ValueError("Сумма долей активных офферов должна составлять 100%.")
        return self


campaign_flows = TypeAdapter(list[CampaignFlow])


class ClickReportRow(BaseModel):
    stream_id: PositiveInt
    clicks: Annotated[int, Field(ge=0)]


class ClickReport(BaseModel):
    rows: list[ClickReportRow]


async def load_campaign_editor(
    client: httpx.AsyncClient, session: AsyncSession, campaign_id: int
) -> CampaignEditorData:
    campaign, streams, offers, clicks = await asyncio.gather(
        client.get(f"campaigns/{campaign_id}"),
        client.get(f"campaigns/{campaign_id}/streams"),
        load_catalog(client, "offers"),
        load_clicks_today(client, campaign_id),
    )
    campaign.raise_for_status()
    streams.raise_for_status()
    flows = [
        flow
        for flow in campaign_flows.validate_json(streams.content)
        if flow.state != "deleted" and flow.flow_schema == "landings"
    ]
    await remember_offers(session, [
        (flow.id, offer.offer_id) for flow in flows for offer in flow.offers
    ])
    prefs = await get_offer_preferences(session, [flow.id for flow in flows])
    await session.commit()

    return CampaignEditorData(
        campaign=CatalogOption.model_validate_json(campaign.content),
        admin_url=str(client.base_url.copy_with(path="/admin/", fragment=f"/campaigns/{campaign_id}")),
        flows=[
            build_editor_flow(
                flow,
                prefs.get(flow.id, {}),
                clicks.get(flow.id, 0) if clicks is not None else None,
            )
            for flow in flows
        ],
        offers=offers,
    )


async def update_flow_offers(
    client: httpx.AsyncClient,
    session: AsyncSession,
    campaign_id: int,
    flow_id: int,
    data: UpdateFlowOffers,
) -> EditorFlow:
    await session.execute(select(func.pg_advisory_xact_lock(flow_id)))
    response = await client.get(f"streams/{flow_id}")
    response.raise_for_status()
    flow = CampaignFlow.model_validate_json(response.content)
    if (
        flow.id != flow_id
        or flow.campaign_id != campaign_id
        or flow.state == "deleted"
        or flow.flow_schema != "landings"
    ):
        raise CampaignEditorError("Поток офферов не найден в указанной кампании.", 404)

    current = {offer.offer_id: offer for offer in flow.offers}
    desired = {offer.offer_id: offer for offer in data.offers}
    expected = {offer.offer_id: offer for offer in data.expected_offers}
    await remember_offers(session, [(flow.id, offer_id) for offer_id in current.keys() | desired.keys()])
    prefs = (await get_offer_preferences(session, [flow.id])).get(flow.id, {})
    current_pins = {pref.offer_id for pref in prefs.values() if pref.pinned}
    desired_pins = set(data.pinned_offer_ids)
    if current_pins not in (set(data.expected_pinned_offer_ids), desired_pins):
        raise CampaignEditorError("Закреплённые доли изменились. Обновите кампанию.", 409)

    if current != desired:
        if current != expected:
            raise CampaignEditorError("Офферы изменились в Keitaro. Обновите кампанию.", 409)
        response = await client.put(
            f"streams/{flow_id}",
            json={"offers": [offer.model_dump() for offer in data.offers]},
        )
        response.raise_for_status()
        flow = CampaignFlow.model_validate_json(response.content)
        if flow.id != flow_id or {offer.offer_id: offer for offer in flow.offers} != desired:
            raise CampaignEditorError("Keitaro вернул другие доли. Обновите кампанию.", 502)

    for option in prefs.values():
        option.pinned = option.offer_id in desired_pins
    await session.commit()
    return build_editor_flow(flow, prefs)


async def remember_offers(session: AsyncSession, keys: list[tuple[int, int]]) -> None:
    if keys:
        statement = insert(StreamOfferPreference).values([
            {"stream_id": stream_id, "offer_id": offer_id}
            for stream_id, offer_id in sorted(set(keys))
        ])
        await session.execute(statement.on_conflict_do_nothing())


async def get_offer_preferences(
    session: AsyncSession, stream_ids: list[int]
) -> dict[int, dict[int, StreamOfferPreference]]:
    if not stream_ids:
        return {}
    prefs = await session.scalars(
        select(StreamOfferPreference).where(StreamOfferPreference.stream_id.in_(stream_ids))
    )
    result: dict[int, dict[int, StreamOfferPreference]] = {}
    for pref in prefs:
        result.setdefault(pref.stream_id, {})[pref.offer_id] = pref
    return result


async def load_clicks_today(client: httpx.AsyncClient, campaign_id: int) -> dict[int, int] | None:
    try:
        response = await client.post("report/build", json={
            "range": {"interval": "today"},
            "dimensions": ["stream_id"],
            "measures": ["clicks"],
            "filters": [{"name": "campaign_id", "operator": "EQUALS", "expression": campaign_id}],
        })
        response.raise_for_status()
        report = ClickReport.model_validate_json(response.content)
    except (httpx.HTTPError, ValueError):
        return None
    return {row.stream_id: row.clicks for row in report.rows}


def build_editor_flow(
    flow: CampaignFlow,
    prefs: dict[int, StreamOfferPreference],
    clicks_today: int | None = None,
) -> EditorFlow:
    visible = {offer.offer_id for offer in flow.offers}
    active_offers = [
        EditorOffer(**offer.model_dump(), pinned=bool(prefs.get(offer.offer_id) and prefs[offer.offer_id].pinned))
        for offer in flow.offers
    ]
    removed = [
        EditorOffer(offer_id=offer_id, share=0, state="removed", pinned=prefs[offer_id].pinned)
        for offer_id in sorted(prefs.keys() - visible)
    ]
    return EditorFlow(
        id=flow.id,
        name=flow.name,
        state=flow.state,
        offers=active_offers + removed,
        clicks_today=clicks_today,
    )
