from __future__ import annotations

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


class QuestionnaireAnswer(Base):
    """One field from the intake form. Key/value so the field set can change
    without a migration. See DECISIONS.md sections 4 and 13."""

    __tablename__ = "questionnaire_answers"
    __table_args__ = (
        # Every read is "answers for this request", often for one key.
        Index("ix_answers_request_field", "request_id", "field_key"),
    )

    id: Mapped[int] = mapped_column(
        BigIntType, primary_key=True, autoincrement=True
    )

    request_id: Mapped[uuid.UUID] = mapped_column(
        UUIDBinary,
        ForeignKey("requests.id", ondelete="CASCADE"),
        nullable=False,
    )

    field_key: Mapped[str] = mapped_column(String(64), nullable=False)

    # TEXT, not VARCHAR: clinical history has no sensible limit, and Phase 10
    # encryption makes the stored value substantially longer than the input.
    # Nullable: an optional field left blank is a legitimate answer.
    field_value: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    request: Mapped["Request"] = relationship(back_populates="answers")

    def __repr__(self) -> str:
        return f"<QuestionnaireAnswer request_id={self.request_id} key={self.field_key!r}>"
