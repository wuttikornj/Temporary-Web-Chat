from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import CHAR, BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.types import BigIntType, UUIDBinary, new_uuid


class RequestStatus(enum.StrEnum):
    """Stored as a plain VARCHAR. See DECISIONS.md section 9."""

    OPEN = "open"
    CLOSED = "closed"
    EXPIRED = "expired"


class Request(Base):
    """One chat thread, created when a questionnaire is submitted."""

    __tablename__ = "requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUIDBinary, primary_key=True, default=new_uuid
    )

    # Identification, not authentication. Indexed, deliberately NOT unique.
    external_id: Mapped[str] = mapped_column(
        String(16), nullable=False, index=True
    )

    # The actual secret. Lives in the chat link.
    access_token: Mapped[str] = mapped_column(
        CHAR(64), nullable=False, unique=True
    )

    email: Mapped[str] = mapped_column(String(255), nullable=False)

    station_id: Mapped[int] = mapped_column(
        BigIntType,
        ForeignKey("stations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=RequestStatus.OPEN,
        server_default=RequestStatus.OPEN.value,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    # Computed in Python from REQUEST_EXPIRY_DAYS. Indexed: the cleanup
    # job queries on it every run.
    expires_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, index=True
    )

    station: Mapped["Station"] = relationship(back_populates="requests")

    messages: Mapped[list["Message"]] = relationship(
        back_populates="request",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Message.sent_at",
    )

    answers: Mapped[list["QuestionnaireAnswer"]] = relationship(
        back_populates="request",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return (
            f"<Request id={self.id} external_id={self.external_id!r} "
            f"status={self.status!r}>"
        )