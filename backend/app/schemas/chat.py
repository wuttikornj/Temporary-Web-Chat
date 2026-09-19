"""Shapes for the chat view, shared by the user side and the admin side."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sender_type: str
    body: str
    sent_at: datetime
    read_at: datetime | None = None


class MessageCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    body: Annotated[str, Field(min_length=1, max_length=20_000)]


class SummaryField(BaseModel):
    """One line of the intake summary, ready to render.

    The label is carried alongside the value so the widget does not have to
    hold its own copy of the field list. If the intake form gains a field,
    the chat header shows it without a frontend change.
    """

    key: str
    label: str
    value: str


class ChatView(BaseModel):
    """What both sides load when they open a thread: the request that started
    it, then the conversation."""

    request_id: str
    station: str
    hn: str
    status: str
    created_at: datetime
    expires_at: datetime
    summary: list[SummaryField]
    messages: list[MessageOut]

    # How long an unread reply waits before the consultee is emailed.
    # Sent to the client so on-screen copy stays true to config.
    notify_after_minutes: int
