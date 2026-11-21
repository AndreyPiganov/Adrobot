import asyncio
from typing import Annotated, Literal
from uuid import uuid4

import httpx
from pydantic import (
    BaseModel,
    Field,
    Json,
    PositiveInt,
    StringConstraints,
    TypeAdapter,
    ValidationError,
)


class CatalogOption(BaseModel):
    id: PositiveInt
    name: str


class CampaignOptions(BaseModel):
    domains: list[CatalogOption]
    groups: list[CatalogOption]
    traffic_sources: list[CatalogOption]


class KeitaroCatalogItem(CatalogOption):
    state: str | None = None


class CampaignInput(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    country_code: Annotated[
        str,
        StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Za-z]{2}$"),
    ]
    offer_id: PositiveInt
    domain_id: PositiveInt
    group_id: PositiveInt
    traffic_source_id: PositiveInt


class CreatedCampaign(BaseModel):
    id: PositiveInt
    alias: str


class KeitaroCampaign(CreatedCampaign):
    state: Literal["active", "disabled"]
    domain_id: PositiveInt | None = None


class KeitaroCountryFilter(BaseModel):
    name: Literal["country"]
    mode: Literal["accept"]
    payload: list[str] | Json[list[str]]


class KeitaroRedirect(BaseModel):
    type: Literal["regular"]
    flow_schema: Literal["redirect"] = Field(validation_alias="schema")
    action_type: Literal["http"]
    action_payload: str
    filters: list[KeitaroCountryFilter]


class KeitaroFlowOffer(BaseModel):
    offer_id: PositiveInt
    share: int
    state: Literal["active"]


class KeitaroOfferFlow(BaseModel):
    type: Literal["default"]
    flow_schema: Literal["landings"] = Field(validation_alias="schema")
    offers: list[KeitaroFlowOffer]


class CampaignCreationError(Exception):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


GOOGLE_URL = "https://www.google.com/"
catalog_items = TypeAdapter(list[KeitaroCatalogItem])


async def load_campaign_options(client: httpx.AsyncClient) -> CampaignOptions:
    domains, groups, sources = await asyncio.gather(
        load_catalog(client, "domains"),
        load_catalog(client, "groups", params={"type": "campaigns"}),
        load_catalog(client, "traffic_sources"),
    )
    return CampaignOptions(domains=domains, groups=groups, traffic_sources=sources)


async def load_catalog(
    client: httpx.AsyncClient,
    path: str,
    params: dict[str, str] | None = None,
) -> list[CatalogOption]:
    response = await client.get(path, params=params)
    response.raise_for_status()
    items = catalog_items.validate_json(response.content)
    return [
        CatalogOption(id=item.id, name=item.name)
        for item in items
        if item.state != "deleted"
    ]


async def create_campaign(client: httpx.AsyncClient, data: CampaignInput) -> CreatedCampaign:
    offer = await client.get(f"offers/{data.offer_id}")
    if offer.status_code == 404:
        raise CampaignCreationError("Оффер с таким ID не найден в Keitaro.", 422)
    offer.raise_for_status()
    if KeitaroCatalogItem.model_validate_json(offer.content).state == "deleted":
        raise CampaignCreationError("Оффер удалён в Keitaro. Укажите другой ID.", 422)

    alias = f"adrobot_{uuid4().hex[:16]}"
    try:
        response = await client.post("campaigns", json={
            "name": data.name,
            "alias": alias,
            "type": "position",
            "state": "disabled",
            "domain_id": data.domain_id,
            "group_id": str(data.group_id),
            "traffic_source_id": data.traffic_source_id,
        })
        response.raise_for_status()
        campaign = KeitaroCampaign.model_validate_json(response.content)
    except (httpx.RequestError, ValidationError) as error:
        raise CampaignCreationError(
            f"Keitaro не подтвердил создание кампании. Перед повтором проверьте алиас {alias}."
        ) from error
    except httpx.HTTPStatusError as error:
        if error.response.status_code >= 500:
            raise CampaignCreationError(
                f"Keitaro вернул ошибку. Перед повтором проверьте алиас {alias}."
            ) from error
        raise

    if campaign.state != "disabled" or campaign.domain_id not in (None, data.domain_id):
        raise CampaignCreationError(
            f"Keitaro вернул неожиданные настройки кампании №{campaign.id}. Проверьте её в Keitaro."
        )

    try:
        await create_campaign_flows(client, campaign.id, data)
    except (httpx.HTTPError, ValidationError) as error:
        raise CampaignCreationError(
            f"Кампания №{campaign.id} осталась выключенной. "
            "Keitaro не подтвердил настройку обоих потоков."
        ) from error

    try:
        enabled = await client.post(f"campaigns/{campaign.id}/enable")
        enabled.raise_for_status()
        current = KeitaroCampaign.model_validate_json(enabled.content)
    except (httpx.HTTPError, ValidationError) as error:
        raise CampaignCreationError(
            f"Потоки кампании №{campaign.id} настроены. Проверьте статус кампании в Keitaro."
        ) from error
    if current.id != campaign.id:
        raise CampaignCreationError(f"Проверьте статус кампании №{campaign.id} в Keitaro.")
    if current.state != "active":
        raise CampaignCreationError(
            f"Потоки кампании №{campaign.id} настроены. Кампания осталась выключенной."
        )
    return CreatedCampaign(id=current.id, alias=current.alias)


async def create_campaign_flows(
    client: httpx.AsyncClient,
    campaign_id: int,
    data: CampaignInput,
) -> None:
    response = await client.post("streams", json={
        "campaign_id": campaign_id,
        "name": f"{data.country_code} → Google",
        "type": "regular",
        "position": 1,
        "schema": "redirect",
        "action_type": "http",
        "action_payload": GOOGLE_URL,
        "collect_clicks": True,
        "filters": [{"name": "country", "mode": "accept", "payload": [data.country_code]}],
    })
    response.raise_for_status()
    redirect = KeitaroRedirect.model_validate_json(response.content)
    expected_filter = KeitaroCountryFilter(name="country", mode="accept", payload=[data.country_code])
    if (
        redirect.action_payload.rstrip("/") != GOOGLE_URL.rstrip("/")
        or redirect.filters != [expected_filter]
    ):
        raise CampaignCreationError(
            f"Кампания №{campaign_id} осталась выключенной. "
            "Keitaro не подтвердил настройки потока в Google."
        )

    response = await client.post("streams", json={
        "campaign_id": campaign_id,
        "name": "Офферы",
        "type": "default",
        "position": 2,
        "schema": "landings",
        "action_type": "http",
        "collect_clicks": True,
        "offers": [{"offer_id": data.offer_id, "share": 100, "state": "active"}],
    })
    response.raise_for_status()
    offer_flow = KeitaroOfferFlow.model_validate_json(response.content)
    expected_offer = KeitaroFlowOffer(offer_id=data.offer_id, share=100, state="active")
    if offer_flow.offers != [expected_offer]:
        raise CampaignCreationError(
            f"Кампания №{campaign_id} осталась выключенной. "
            "Keitaro не подтвердил настройки потока офферов."
        )
