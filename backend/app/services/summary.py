"""Turns stored questionnaire answers into the summary shown at the top of
every chat.

This is the first thing both the doctor and the resident see. It exists as a
service rather than as frontend code so that the widget, the admin dashboard
and any future email or export all render the same thing in the same order.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.models import QuestionnaireAnswer
from app.schemas.chat import SummaryField

# Order matters: this is reading order for a resident triaging a request.
# Clinical history last, because it is the long one.
FIELD_LABELS: list[tuple[str, str]] = [
    ("patient_name", "Patient"),
    ("sex", "Sex"),
    ("age", "Age"),
    ("qshc_hn", "QSHC HN"),
    ("modality", "Modality"),
    ("body_region", "Body region"),
    ("study", "Study"),
    ("time_period", "Requested within"),
    ("specific_date", "Requested date"),
    ("md_name", "M.D."),
    ("staff_name", "Staff"),
    ("tel", "Tel"),
    ("patient_history", "History"),
]

TIME_PERIOD_LABELS = {
    "today": "Today",
    "1d": "Within 1 day",
    "2d": "Within 2 days",
    "3d": "Within 3 days",
    "1w": "Within 1 week",
    "2w": "Within 2 weeks",
    "1m": "Within 1 month",
    "2m": "Within 2 months",
    "3m": "Within 3 months",
    "6m": "Within 6 months",
    "specific": "Specific date",
}

SEX_LABELS = {"male": "Male", "female": "Female", "other": "Other"}

AGE_UNIT_LABELS = {"years": "years", "months": "months", "days": "days"}


def build_summary(answers: Iterable[QuestionnaireAnswer]) -> list[SummaryField]:
    """Render the answer rows in a fixed, readable order.

    Blank answers are dropped rather than shown as empty rows: an optional
    field nobody filled in is noise in a triage view.
    """
    raw = {a.field_key: a.field_value for a in answers}

    # Age is stored as value plus unit and must never be normalised to years.
    # A 7-day-old and a 7-year-old are different patients.
    value = raw.get("age_value")
    unit = raw.get("age_unit")
    if value and unit:
        raw["age"] = f"{value} {AGE_UNIT_LABELS.get(unit, unit)}"

    if raw.get("sex"):
        raw["sex"] = SEX_LABELS.get(raw["sex"], raw["sex"])
    if raw.get("time_period"):
        raw["time_period"] = TIME_PERIOD_LABELS.get(
            raw["time_period"], raw["time_period"]
        )

    out: list[SummaryField] = []
    for key, label in FIELD_LABELS:
        val = raw.get(key)
        if val:
            out.append(SummaryField(key=key, label=label, value=val))
    return out
