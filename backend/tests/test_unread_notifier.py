"""The 5 minute unread notification.

This is the behaviour most likely to be broken silently by a later change, and
the failure mode is doctors being emailed about replies they have already read.
"""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.jobs import unread_notifier
from app.models import Message, Request, SenderType, Station
from app.services.request_service import utc_now


@pytest.fixture
def sent_emails(monkeypatch) -> list[dict]:
    """Capture outgoing mail instead of sending it."""
    captured: list[dict] = []

    async def fake_send(settings, to, subject, body):
        captured.append({"to": to, "subject": subject, "body": body})
        return True

    monkeypatch.setattr(unread_notifier, "send_email", fake_send)
    return captured


async def make_request(session, **overrides) -> Request:
    station = (await session.execute(select(Station).limit(1))).scalar_one()
    fields = {
        "external_id": "JX1234",
        "access_token": "t" * 64,
        "email": "doctor@example.com",
        "station_id": station.id,
        "expires_at": utc_now() + timedelta(days=7),
        **overrides,
    }
    request = Request(**fields)
    session.add(request)
    await session.flush()
    return request


async def add_admin_message(session, request, *, minutes_ago: int, **kw) -> Message:
    message = Message(
        request_id=request.id,
        sender_type=SenderType.ADMIN,
        body="Please send prior imaging.",
        sent_at=utc_now() - timedelta(minutes=minutes_ago),
        **kw,
    )
    session.add(message)
    await session.flush()
    return message


async def run(session_factory, settings) -> int:
    return await unread_notifier.notify_unread(
        session_factory=session_factory, settings=settings
    )


async def test_emails_after_the_delay(db, session_factory, settings, sent_emails):
    request = await make_request(db)
    await add_admin_message(db, request, minutes_ago=6)
    await db.commit()

    assert await run(session_factory, settings) == 1
    assert sent_emails[0]["to"] == "doctor@example.com"


async def test_does_not_email_before_the_delay(db, session_factory, settings, sent_emails):
    request = await make_request(db)
    await add_admin_message(db, request, minutes_ago=2)
    await db.commit()

    assert await run(session_factory, settings) == 0
    assert sent_emails == []


async def test_does_not_email_a_message_already_read(db, session_factory, settings, sent_emails):
    """The whole point of the read tracking. Emailing someone who is already
    looking at the reply is worse than not emailing at all."""
    request = await make_request(db)
    await add_admin_message(db, request, minutes_ago=30, read_at=utc_now())
    await db.commit()

    assert await run(session_factory, settings) == 0
    assert sent_emails == []


async def test_never_emails_twice_for_the_same_message(db, session_factory, settings, sent_emails):
    """The job runs every minute. notified_at is what makes it idempotent."""
    request = await make_request(db)
    await add_admin_message(db, request, minutes_ago=10)
    await db.commit()

    assert await run(session_factory, settings) == 1
    assert await run(session_factory, settings) == 0
    assert await run(session_factory, settings) == 0
    assert len(sent_emails) == 1


async def test_several_replies_collapse_into_one_email(db, session_factory, settings, sent_emails):
    """A resident sending four short lines must not produce four emails."""
    request = await make_request(db)
    for _ in range(4):
        await add_admin_message(db, request, minutes_ago=10)
    await db.commit()

    assert await run(session_factory, settings) == 1
    assert len(sent_emails) == 1

    # Every collapsed message is marked, or the next run emails again.
    assert await run(session_factory, settings) == 0


async def test_does_not_email_for_the_doctors_own_messages(db, session_factory, settings, sent_emails):
    """Only unanswered replies chase the consultee. The resident is not
    emailed; they work from the dashboard."""
    request = await make_request(db)
    db.add(
        Message(
            request_id=request.id,
            sender_type=SenderType.USER,
            body="any update?",
            sent_at=utc_now() - timedelta(minutes=30),
        )
    )
    await db.commit()

    assert await run(session_factory, settings) == 0


async def test_ignores_expired_requests(db, session_factory, settings, sent_emails):
    """A thread past its expiry is about to be deleted. Emailing a link to it
    would send the doctor to a 404."""
    request = await make_request(db, expires_at=utc_now() - timedelta(days=1))
    await add_admin_message(db, request, minutes_ago=10)
    await db.commit()

    assert await run(session_factory, settings) == 0


async def test_email_contains_the_link_and_no_patient_data(db, session_factory, settings, sent_emails):
    """DECISIONS.md section 12. Hospital mail is forwarded and archived outside
    this system's control."""
    request = await make_request(db)
    await add_admin_message(db, request, minutes_ago=10)
    await db.commit()

    await run(session_factory, settings)
    email = sent_emails[0]
    blob = email["subject"] + email["body"]

    assert request.access_token in email["body"]
    for leak in ["JX1234", "Test Patient", "CTA Brain", "headache"]:
        assert leak not in blob
