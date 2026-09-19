"""User-side chat. Access is by the token in the link, nothing else."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_db
from app.models import SenderType
from app.schemas.chat import ChatView, MessageCreate, MessageOut
from app.services import message_service as svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


async def _get_thread(db: AsyncSession, token: str):
    try:
        return await svc.get_by_token(db, token)
    except svc.RequestNotFound:
        # 404 for both "no such token" and an expired-and-deleted thread. Do
        # not distinguish: a different response for a valid-but-dead token
        # would confirm to a guesser that the token was real.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found"
        ) from None


@router.get("/{token}", response_model=ChatView)
async def open_chat(
    token: str,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ChatView:
    """Open the thread. Loading it counts as reading it, which is what stops
    the 5 minute notifier emailing someone who is already looking at it."""
    request = await _get_thread(db, token)
    await svc.mark_read(db, request, SenderType.USER)
    await db.commit()
    await db.refresh(request)
    return svc.build_chat_view(request, settings)


@router.post(
    "/{token}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_message(
    token: str,
    payload: MessageCreate,
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    request = await _get_thread(db, token)
    try:
        message = await svc.send_message(
            db, request, SenderType.USER, payload.body
        )
    except svc.RequestClosed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This chat is closed",
        ) from None

    await db.commit()
    # Identifiers only. The body is patient data.
    logger.info("user message request_id=%s", request.id)
    return MessageOut.model_validate(message)
