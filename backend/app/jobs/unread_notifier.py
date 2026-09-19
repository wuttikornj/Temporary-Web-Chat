"""Emails the consultee when a reply has gone unread.

The rule, from DECISIONS.md section 14: no email is sent when a request is
created. The only email this system sends is this one. If the resident has
replied and the doctor has not opened the thread within
UNREAD_EMAIL_DELAY_MINUTES, send them the link.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models import Message, Request, SenderType
from app.services.email import send_email
from app.services.request_service import build_chat_url, utc_now

logger = logging.getLogger(__name__)

SUBJECT = "You have a reply to your study request"

BODY = """A radiologist has replied to your study request.

Open the conversation here:
{url}

This link expires on {expires} and the conversation is deleted afterwards.
Do not forward this email: the link grants access to the conversation.
"""


async def notify_unread(
    session_factory=None,
    settings=None,
) -> int:
    """One pass. Returns how many notifications were sent.

    Runs every minute, so it must be cheap and it must be safe to run twice.
    `notified_at` is what makes it safe: a message that has been notified is
    never picked up again, even if this runs late, twice, or in two processes.
    """
    # Arguments exist so tests can drive this without patching module
    # globals. Production calls it with neither.
    settings = settings or get_settings()
    session_factory = session_factory or AsyncSessionLocal
    cutoff = utc_now() - timedelta(
        minutes=settings.UNREAD_EMAIL_DELAY_MINUTES
    )

    async with session_factory() as session:
        result = await session.execute(
            select(Message)
            .join(Request, Request.id == Message.request_id)
            .where(
                Message.sender_type == SenderType.ADMIN,
                Message.read_at.is_(None),
                Message.notified_at.is_(None),
                Message.sent_at <= cutoff,
                Request.expires_at > utc_now(),
            )
            .options(selectinload(Message.request))
            # One email per thread, not one per message. A resident who sends
            # four lines in a row should not produce four emails.
            .order_by(Message.request_id, Message.sent_at)
        )
        messages = result.scalars().all()

        if not messages:
            return 0

        seen_requests: set = set()
        sent = 0

        for message in messages:
            request = message.request

            # Mark every qualifying message notified, including the ones we
            # are collapsing into a single email. Otherwise the next run
            # emails again for the same thread.
            message.notified_at = utc_now()

            if request.id in seen_requests:
                continue
            seen_requests.add(request.id)

            ok = await send_email(
                settings,
                to=request.email,
                subject=SUBJECT,
                body=BODY.format(
                    url=build_chat_url(request, settings),
                    expires=request.expires_at.strftime("%d %b %Y"),
                ),
            )
            if ok:
                sent += 1

        await session.commit()

    if sent:
        logger.info("unread notifier sent %s email(s)", sent)
    return sent
