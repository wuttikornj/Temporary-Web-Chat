from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.types import BigIntType, UUIDBinary


class SenderType(enum.StrEnum):
    """Plain VARCHAR in the database. See DECISIONS.md section 9."""

    USER = "user"
    ADMIN = "admin"


class Message(Base):
    """One message in a consult thread."""

    __tablename__ = "messages"
    __table_args__ = (
        # Reading a thread: every message for a request, in order.
        Index("ix_messages_request_sent", "request_id", "sent_at"),
        # The unread notifier's scan, which runs every minute. Without this it
        # is a full table scan of every message ever sent.
        Index("ix_messages_unread_scan", "read_at", "notified_at", "sent_at"),
    )

    id: Mapped[int] = mapped_column(
        BigIntType, primary_key=True, autoincrement=True
    )

    request_id: Mapped[uuid.UUID] = mapped_column(
        UUIDBinary,
        ForeignKey("requests.id", ondelete="CASCADE"),
        nullable=False,
    )

    sender_type: Mapped[str] = mapped_column(String(10), nullable=False)

    # TEXT, and encrypted at rest in Phase 10.
    body: Mapped[str] = mapped_column(Text, nullable=False)

    sent_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    # NULL until the other side has actually opened the thread.
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # NULL until the unread notification email has gone out. Separate from
    # read_at so the notifier can never send twice for the same message,
    # even if it runs late or twice.
    notified_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )

    request: Mapped["Request"] = relationship(back_populates="messages")

    def __repr__(self) -> str:
        return (
            f"<Message id={self.id} request_id={self.request_id} "
            f"sender={self.sender_type!r}>"
        )
