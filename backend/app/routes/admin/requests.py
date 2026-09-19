"""Admin-side chat. Every admin sees every station."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.identity import Admin, get_current_admin
from app.config import Settings, get_settings
from app.database import get_db
from app.models import Message, Request, SenderType, Station
from app.schemas.chat import ChatView, MessageCreate, MessageOut
from app.services import message_service as svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/requests")
async def list_requests(
    station: str | None = Query(default=None),
    admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """The queue. Optionally filtered to one station.

    Ordered by unread first, then oldest. A resident opening the dashboard
    should see what is waiting on them, not the most recent activity.
    """
    unread = (
        select(
            Message.request_id.label("rid"),
            func.count().label("unread_count"),
        )
        .where(
            Message.sender_type == SenderType.USER,
            Message.read_at.is_(None),
        )
        .group_by(Message.request_id)
        .subquery()
    )

    stmt = (
        select(Request, func.coalesce(unread.c.unread_count, 0))
        .join(Station, Station.id == Request.station_id)
        .outerjoin(unread, unread.c.rid == Request.id)
        .options(selectinload(Request.station), selectinload(Request.answers))
        .order_by(
            func.coalesce(unread.c.unread_count, 0).desc(),
            Request.created_at.asc(),
        )
    )
    if station:
        stmt = stmt.where(Station.name == station)

    rows = (await db.execute(stmt)).all()

    out = []
    for request, unread_count in rows:
        answers = {a.field_key: a.field_value for a in request.answers}
        out.append(
            {
                "request_id": str(request.id),
                "hn": request.external_id,
                "patient_name": answers.get("patient_name"),
                "modality": answers.get("modality"),
                "study": answers.get("study"),
                "station": request.station.name,
                "status": request.status,
                "created_at": request.created_at,
                "expires_at": request.expires_at,
                "unread_count": unread_count,
            }
        )
    return out


async def _get_thread(db: AsyncSession, request_id: str):
    try:
        parsed = uuid.UUID(request_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Request not found"
        ) from None
    try:
        return await svc.get_by_id(db, parsed)
    except svc.RequestNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Request not found"
        ) from None


@router.get("/requests/{request_id}", response_model=ChatView)
async def open_request(
    request_id: str,
    admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ChatView:
    request = await _get_thread(db, request_id)
    await svc.mark_read(db, request, SenderType.ADMIN)
    await db.commit()
    await db.refresh(request)
    return svc.build_chat_view(request, settings)


@router.post(
    "/requests/{request_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def reply(
    request_id: str,
    payload: MessageCreate,
    admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    request = await _get_thread(db, request_id)
    try:
        message = await svc.send_message(
            db, request, SenderType.ADMIN, payload.body
        )
    except svc.RequestClosed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This chat is closed",
        ) from None

    await db.commit()
    logger.info(
        "admin reply request_id=%s admin=%s", request.id, admin.email
    )
    return MessageOut.model_validate(message)
