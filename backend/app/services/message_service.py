"""Loading a thread, sending a message, tracking reads.

Every one of these is called from more than one place: the public routes, the
admin routes, and in Phase 5 the WebSocket handlers. Keeping them here is what
stops three copies of the same rules existing.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings
from app.models import Message, Request, RequestStatus, SenderType, Station
from app.schemas.chat import ChatView, MessageOut
from app.services.request_service import utc_now
from app.services.summary import build_summary


class RequestNotFound(Exception):
    """No request for that token or id."""


class RequestClosed(Exception):
    """The thread exists but is expired or closed, so it is read-only."""


async def _load(session: AsyncSession, whereclause) -> Request:
    """Load a request with its answers, messages and station in one round
    trip. selectinload, not lazy loading: a lazy load in async SQLAlchemy
    raises MissingGreenlet the moment it happens outside the session."""
    result = await session.execute(
        select(Request)
        .where(whereclause)
        .options(
            selectinload(Request.answers),
            selectinload(Request.messages),
            selectinload(Request.station),
        )
    )
    request = result.scalar_one_or_none()
    if request is None:
        raise RequestNotFound
    return request


async def get_by_token(session: AsyncSession, token: str) -> Request:
    """User side. The token in the link is the credential."""
    return await _load(session, Request.access_token == token)


async def get_by_id(session: AsyncSession, request_id: uuid.UUID) -> Request:
    """Admin side. Admins see every station, so no scoping here.
    See DECISIONS.md section 3."""
    return await _load(session, Request.id == request_id)


def is_writable(request: Request, now: datetime | None = None) -> bool:
    now = now or utc_now()
    return request.status == RequestStatus.OPEN and request.expires_at > now


async def mark_read(
    session: AsyncSession, request: Request, reader: SenderType
) -> None:
    """Mark the other side's messages as read.

    A reader marks messages they did NOT send. Opening your own thread does
    not mean you have read yourself.

    Also clears nothing about notified_at: a notification already sent stays
    sent. read_at stops future notifications, it does not undo past ones.
    """
    other = SenderType.ADMIN if reader is SenderType.USER else SenderType.USER
    await session.execute(
        update(Message)
        .where(
            Message.request_id == request.id,
            Message.sender_type == other,
            Message.read_at.is_(None),
        )
        .values(read_at=utc_now())
    )


async def send_message(
    session: AsyncSession,
    request: Request,
    sender: SenderType,
    body: str,
) -> Message:
    """Append a message. Does not commit; the caller owns the transaction."""
    if not is_writable(request):
        raise RequestClosed

    message = Message(
        request_id=request.id,
        sender_type=sender,
        body=body,
        sent_at=utc_now(),
    )
    session.add(message)
    await session.flush()
    return message


def build_chat_view(request: Request, settings: Settings) -> ChatView:
    """Assemble what a client renders: the intake summary first, then the
    conversation. Both sides get the same view, which is what makes the
    resident and the doctor certain they are looking at the same request."""
    return ChatView(
        notify_after_minutes=settings.UNREAD_EMAIL_DELAY_MINUTES,
        request_id=str(request.id),
        station=request.station.name,
        hn=request.external_id,
        status=request.status,
        created_at=request.created_at,
        expires_at=request.expires_at,
        summary=build_summary(request.answers),
        messages=[
            MessageOut.model_validate(m)
            for m in sorted(request.messages, key=lambda m: m.sent_at)
        ],
    )
