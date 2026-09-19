from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.types import BigIntType


class Station(Base):
    """An admin-side folder. Requests are grouped into these."""

    __tablename__ = "stations"

    id: Mapped[int] = mapped_column(
        BigIntType, primary_key=True, autoincrement=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    requests: Mapped[list["Request"]] = relationship(
        back_populates="station",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Station id={self.id} name={self.name!r}>"