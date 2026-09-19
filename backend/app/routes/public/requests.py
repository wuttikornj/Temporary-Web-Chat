"""Intake endpoint. Creates a consult chat from a sorted study request."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.identity import Consultee, get_current_consultee
from app.database import get_db
from app.schemas.questionnaire import RequestCreate, RequestCreated
from app.services.request_service import (
    UnknownStation,
    build_chat_url,
    create_request,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["public"])


@router.post(
    "/requests",
    response_model=RequestCreated,
    status_code=status.HTTP_201_CREATED,
)
async def create_consult_request(
    payload: RequestCreate,
    consultee: Consultee = Depends(get_current_consultee),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RequestCreated:
    """Create a chat thread for a study request that has already been sorted.

    The route is deliberately thin: validate (Pydantic), authenticate
    (dependency), delegate (service), commit, respond.
    """
    try:
        request = await create_request(db, payload, consultee, settings)
    except UnknownStation as exc:
        # 422, not 500: the caller sent a station this deployment does not
        # have. That is a contract problem on their side, and the message
        # names the value so they can fix it. No patient data in the message.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown station: {exc.name}",
        ) from exc

    await db.commit()

    # Log identifiers only. Never the payload: it carries patient data.
    # See DECISIONS.md section 12.
    logger.info(
        "created request id=%s station=%s", request.id, payload.station
    )

    return RequestCreated(
        request_id=str(request.id),
        chat_url=build_chat_url(request, settings),
        expires_at=request.expires_at,
        station=payload.station,
    )
