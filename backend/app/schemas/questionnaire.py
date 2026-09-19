"""Intake payload for a study-request consult.

This is a PUBLIC API CONTRACT. A caller we do not control (the requesting
system that owns the form and the sorting) depends on these field names and
these rules. Changing them is a breaking change. See DECISIONS.md section 11.
"""

from __future__ import annotations

import enum
import re
from datetime import date, datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

# DECISIONS.md section 6. Two shapes only.
HN_PATTERNS = (
    re.compile(r"^[A-Z]{2}[0-9]{4}$"),
    re.compile(r"^[0-9]{8}$"),
)


class Sex(enum.StrEnum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class AgeUnit(enum.StrEnum):
    """Never normalised to years. A 7-day-old and a 7-year-old are not the
    same patient and the resident must be able to see which."""

    YEARS = "years"
    MONTHS = "months"
    DAYS = "days"


class Modality(enum.StrEnum):
    CT = "CT"
    MRI = "MRI"
    US = "U/S"
    FLUOROSCOPY = "Fluoroscopy"


class TimePeriod(enum.StrEnum):
    TODAY = "today"
    D1 = "1d"
    D2 = "2d"
    D3 = "3d"
    W1 = "1w"
    W2 = "2w"
    M1 = "1m"
    M2 = "2m"
    M3 = "3m"
    M6 = "6m"
    SPECIFIC = "specific"


def _normalise_hn(value: str) -> str:
    """Strip, uppercase, then validate. Order matters: validating first would
    reject 'jx1234' and defeat the case rule in DECISIONS.md section 6."""
    cleaned = value.strip().upper()
    if not any(p.match(cleaned) for p in HN_PATTERNS):
        raise ValueError(
            "HN must be two letters followed by four digits (JX1234), "
            "or eight digits (12345678)"
        )
    return cleaned


class RequestCreate(BaseModel):
    """What the caller POSTs to create a consult chat."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    # --- routing, decided by the caller's sorting system ---
    station: Annotated[str, Field(min_length=1, max_length=100)]

    # --- patient ---
    patient_name: Annotated[str, Field(min_length=1, max_length=200)]
    sex: Sex
    age_value: Annotated[int, Field(ge=0, le=150)]
    age_unit: AgeUnit
    hn: Annotated[str, Field(min_length=6, max_length=16)]
    qshc_hn: Annotated[str | None, Field(max_length=32)] = None

    # --- study ---
    modality: Modality
    body_region: Annotated[str, Field(min_length=1, max_length=120)]
    study: Annotated[str, Field(min_length=1, max_length=200)]
    time_period: TimePeriod
    specific_date: date | None = None

    patient_history: Annotated[str, Field(min_length=1, max_length=20_000)]

    # --- who is asking ---
    md_name: Annotated[str, Field(min_length=1, max_length=200)]
    staff_name: Annotated[str, Field(min_length=1, max_length=200)]
    tel: Annotated[str, Field(min_length=1, max_length=40)]

    # NOTE: there is deliberately no email field here. The consultee's
    # address comes from the authenticated SSO session server-side, via
    # app.core.identity. An email in the body would be client-supplied and
    # therefore spoofable.

    @field_validator("hn")
    @classmethod
    def check_hn(cls, value: str) -> str:
        return _normalise_hn(value)

    @field_validator("qshc_hn")
    @classmethod
    def blank_to_none(cls, value: str | None) -> str | None:
        """An optional field sent as "" means absent, not empty string."""
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @model_validator(mode="after")
    def check_specific_date(self) -> "RequestCreate":
        """specific_date is required when, and only when, time_period asks for
        one. Enforced here rather than in the route so the rule lives with the
        contract it belongs to."""
        if self.time_period is TimePeriod.SPECIFIC and self.specific_date is None:
            raise ValueError(
                "specific_date is required when time_period is 'specific'"
            )
        if self.time_period is not TimePeriod.SPECIFIC and self.specific_date:
            raise ValueError(
                "specific_date may only be sent when time_period is 'specific'"
            )
        return self

    def answer_fields(self) -> dict[str, str | None]:
        """Everything that becomes a questionnaire_answers row.

        Excludes the fields promoted to columns on `requests`: hn becomes
        external_id and station becomes station_id. The email is not in
        this payload at all; it comes from the SSO session.
        See DECISIONS.md sections 13 and 15.
        """
        promoted = {"hn", "station"}
        out: dict[str, str | None] = {}
        for name, value in self.model_dump().items():
            if name in promoted:
                continue
            if value is None:
                out[name] = None
            elif isinstance(value, (date, datetime)):
                out[name] = value.isoformat()
            else:
                out[name] = str(value)
        return out


class RequestCreated(BaseModel):
    """What the caller gets back. Deliberately minimal: no patient data is
    echoed, so this response is safe to log on the caller's side."""

    request_id: str
    chat_url: str
    expires_at: datetime
    station: str
