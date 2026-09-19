"""Plain SMTP, so a self-hoster can point this at any mail server.

RULE, not a style preference: an email from this system contains a link and
nothing else. No patient name, no HN, no study, no clinical history, not in
the body and not in the subject. Hospital mail is forwarded, quoted and
archived in places this system has no control over.
See DECISIONS.md section 12.
"""

from __future__ import annotations

import logging
from email.message import EmailMessage

import aiosmtplib

from app.config import Settings

logger = logging.getLogger(__name__)


async def send_email(
    settings: Settings, to: str, subject: str, body: str
) -> bool:
    """Send one message. Returns True if it was handed to a mail server.

    With no SMTP_HOST configured, logs instead of sending and returns False.
    That keeps local development working with no mail server, and it keeps a
    misconfigured deployment noisy rather than silently dropping mail.
    """
    if not settings.SMTP_HOST:
        logger.warning(
            "SMTP not configured, email not sent. to=%s subject=%s", to, subject
        )
        return False

    message = EmailMessage()
    message["From"] = settings.SMTP_FROM_EMAIL or settings.SMTP_USER
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER or None,
            password=settings.SMTP_PASSWORD or None,
            start_tls=settings.SMTP_PORT == 587,
            use_tls=settings.SMTP_PORT == 465,
        )
    except Exception:
        # Never let a mail failure take down the job that called us. The
        # message stays un-notified and the next run tries again.
        logger.exception("failed to send email to=%s", to)
        return False

    logger.info("email sent to=%s subject=%s", to, subject)
    return True
