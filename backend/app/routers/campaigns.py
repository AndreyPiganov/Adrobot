from collections.abc import AsyncIterator
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import PositiveInt, ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.campaign_editor import (
    CampaignEditorData,
    CampaignEditorError,
    EditorFlow,
    UpdateFlowOffers,
    load_campaign_editor,
    update_flow_offers,
)
from app.config import Settings, get_settings
from app.db import get_session_factory
from app.keitaro import (
    CampaignCreationError,
    CampaignInput,
    CampaignOptions,
    CreatedCampaign,
    create_campaign,
    load_campaign_options,
)

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


async def get_editor_session() -> AsyncIterator[AsyncSession]:
    try:
        sessions = get_session_factory()
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    async with sessions() as session:
        yield session


async def get_keitaro_client(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncIterator[httpx.AsyncClient]:
    if not settings.keitaro_base_url or not settings.keitaro_api_key:
        raise HTTPException(
            status_code=503,
            detail="Укажите KEITARO_BASE_URL и KEITARO_API_KEY в файле .env.",
        )

    base_url = str(settings.keitaro_base_url).rstrip("/")
    async with httpx.AsyncClient(
        base_url=f"{base_url}/admin_api/v1/",
        headers={"Api-Key": settings.keitaro_api_key.get_secret_value()},
        timeout=10,
    ) as client:
        yield client


@router.get("/options")
async def get_campaign_options(
    client: Annotated[httpx.AsyncClient, Depends(get_keitaro_client)],
) -> CampaignOptions:
    try:
        return await load_campaign_options(client)
    except httpx.TimeoutException as error:
        raise HTTPException(status_code=504, detail="Keitaro не ответил вовремя.") from error
    except httpx.HTTPStatusError as error:
        if error.response.status_code in (401, 403):
            detail = "Keitaro отклонил API-ключ или у ключа нет прав на чтение."
        else:
            detail = "Keitaro вернул ошибку при загрузке справочников."
        raise HTTPException(status_code=502, detail=detail) from error
    except (httpx.RequestError, ValidationError) as error:
        raise HTTPException(
            status_code=502,
            detail="Не удалось загрузить справочники из Keitaro.",
        ) from error


@router.post("", status_code=201)
async def post_campaign(
    data: CampaignInput,
    client: Annotated[httpx.AsyncClient, Depends(get_keitaro_client)],
) -> CreatedCampaign:
    try:
        return await create_campaign(client, data)
    except CampaignCreationError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
    except httpx.TimeoutException as error:
        raise HTTPException(status_code=504, detail="Keitaro не ответил вовремя.") from error
    except httpx.HTTPStatusError as error:
        code = error.response.status_code
        if code in (400, 404, 406, 422):
            raise HTTPException(
                status_code=422,
                detail="Keitaro отклонил параметры кампании. Проверьте выбранные значения.",
            ) from error
        detail = "Keitaro вернул ошибку при создании кампании."
        if code in (401, 403):
            detail = "Keitaro отклонил API-ключ или у ключа нет прав на создание кампаний."
        raise HTTPException(status_code=502, detail=detail) from error
    except (httpx.RequestError, ValidationError) as error:
        raise HTTPException(status_code=502, detail="Не удалось получить ответ от Keitaro.") from error


@router.get("/{campaign_id}/editor")
async def get_campaign_editor(
    campaign_id: Annotated[PositiveInt, Path()],
    client: Annotated[httpx.AsyncClient, Depends(get_keitaro_client)],
    session: Annotated[AsyncSession, Depends(get_editor_session)],
) -> CampaignEditorData:
    try:
        return await load_campaign_editor(client, session, campaign_id)
    except SQLAlchemyError as error:
        raise HTTPException(status_code=503, detail="Не удалось загрузить настройки из PostgreSQL.") from error
    except httpx.TimeoutException as error:
        raise HTTPException(status_code=504, detail="Keitaro не ответил вовремя.") from error
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 404:
            raise HTTPException(status_code=404, detail="Кампания не найдена в Keitaro.") from error
        if error.response.status_code in (401, 403):
            detail = "Keitaro отклонил API-ключ или у ключа нет прав на чтение кампаний и офферов."
        else:
            detail = "Keitaro вернул ошибку при загрузке кампании."
        raise HTTPException(status_code=502, detail=detail) from error
    except (httpx.RequestError, ValidationError) as error:
        raise HTTPException(status_code=502, detail="Не удалось загрузить кампанию из Keitaro.") from error


@router.put("/{campaign_id}/streams/{flow_id}/offers")
async def put_flow_offers(
    campaign_id: Annotated[PositiveInt, Path()],
    flow_id: Annotated[PositiveInt, Path()],
    data: UpdateFlowOffers,
    client: Annotated[httpx.AsyncClient, Depends(get_keitaro_client)],
    session: Annotated[AsyncSession, Depends(get_editor_session)],
) -> EditorFlow:
    try:
        return await update_flow_offers(client, session, campaign_id, flow_id, data)
    except CampaignEditorError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=503, detail="Не удалось сохранить настройки в PostgreSQL. Обновите кампанию."
        ) from error
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 404:
            raise HTTPException(status_code=404, detail="Поток не найден в Keitaro.") from error
        if error.response.status_code in (400, 406, 422):
            raise HTTPException(status_code=422, detail="Keitaro отклонил список офферов или доли.") from error
        raise HTTPException(status_code=502, detail="Keitaro вернул ошибку при сохранении.") from error
    except (httpx.RequestError, ValidationError) as error:
        raise HTTPException(
            status_code=502,
            detail="Keitaro не подтвердил обновление офферов. Проверьте состояние кампании.",
        ) from error
