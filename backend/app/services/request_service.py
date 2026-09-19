"""Business logic for creating a consult request.

Lives here, not in the route, because creating a request will eventually be
triggered from more than one place. A route that contains business logic has
to be copied the first time that happens.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.identity import Consultee
from app.models import QuestionnaireAnswer, Request, Station
from app.schemas.questionnaire import RequestCreate
from app.services.code_generator import generate_access_token


class UnknownStation(Exception):
    """The caller's sorting system named a Station this deployment has not
    been seeded with."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"Unknown station: {name!r}")


def utc_now() -> datetime:
    """Naive UTC.

    MySQL DATETIME carries no timezone, so an aware datetime would have its
    offset silently discarded on write and come back meaning something else.
    Store naive values that are always UTC, and convert in the browser.
    See DECISIONS.md section 8.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def resolve_station(session: AsyncSession, name: str) -> Station:
    """Map the caller's station name to a Station row.

    Strict lookup, deliberately. Auto-creating a Station from caller input
    would let a typo silently open a new folder that no resident is watching,
    and the request would sit there unanswered.
    """
    result = await session.execute(select(Station).where(Station.name == name))
    station = result.scalar_one_or_none()
    if station is None:
        raise UnknownStation(name)
    return station


async def create_request(
    session: AsyncSession,
    payload: RequestCreate,
    consultee: Consultee,
    settings: Settings,
) -> Request:
    """Create one consult chat and store the intake answers.

    Does not commit. The caller owns the transaction boundary, so a route can
    do several things atomically.
    """
    station = await resolve_station(session, payload.station)

    now = utc_now()
    request = Request(
        external_id=payload.hn,
        access_token=generate_access_token(),
        email=consultee.email,
        station_id=station.id,
        expires_at=now + timedelta(days=settings.REQUEST_EXPIRY_DAYS),
    )
    session.add(request)

    # flush, not commit: assigns request.id so the answers can reference it,
    # while leaving the transaction open.
    await session.flush()

    for key, value in payload.answer_fields().items():
        session.add(
            QuestionnaireAnswer(
                request_id=request.id,
                field_key=key,
                field_value=value,
            )
        )

    # The consultee's name is worth keeping alongside the typed md_name: one
    # is who logged in, the other is who they say owns the patient.
    if consultee.name:
        session.add(
            QuestionnaireAnswer(
                request_id=request.id,
                field_key="sso_name",
                field_value=consultee.name,
            )
        )

    await session.flush()
    return request


def build_chat_url(request: Request, settings: Settings) -> str:
    """The link that grants access. Built from configured base URL, never
    from the incoming Host header."""
    return f"{settings.PUBLIC_BASE_URL.rstrip('/')}/chat/{request.access_token}"
