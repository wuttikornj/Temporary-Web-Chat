"""The HN rules from DECISIONS.md section 6.

These are the rules a future change is most likely to loosen by accident, and
loosening them weakens the rejoin flow rather than producing an obvious bug.
"""

import pytest
from pydantic import ValidationError

from app.schemas.questionnaire import RequestCreate
from tests.conftest import VALID_INTAKE


def build(**overrides) -> RequestCreate:
    return RequestCreate.model_validate({**VALID_INTAKE, **overrides})


@pytest.mark.parametrize("value", ["JX1234", "AB0000", "12345678", "00000000"])
def test_accepts_both_formats(value):
    assert build(hn=value).hn == value


def test_lowercase_is_uppercased():
    """A doctor typing on a phone keyboard must still find their request."""
    assert build(hn="jx1234").hn == "JX1234"


def test_surrounding_whitespace_is_stripped():
    assert build(hn="  jx1234  ").hn == "JX1234"


@pytest.mark.parametrize(
    "value",
    [
        "JX123",       # too few digits
        "JX12345",     # too many digits
        "J1234",       # one letter
        "JXX1234",     # three letters
        "1234567",     # seven digits
        "123456789",   # nine digits
        "JX 1234",     # internal space
        "JX-1234",     # separator
        "",
    ],
)
def test_rejects_anything_else(value):
    """Strict validation is what makes HN spraying cheap to defend against:
    a malformed guess is rejected before any database query runs."""
    with pytest.raises(ValidationError):
        build(hn=value)


def test_specific_date_required_when_period_is_specific():
    with pytest.raises(ValidationError):
        build(time_period="specific")


def test_specific_date_rejected_when_period_is_not_specific():
    with pytest.raises(ValidationError):
        build(time_period="1d", specific_date="2026-10-01")


def test_specific_date_accepted_together():
    req = build(time_period="specific", specific_date="2026-10-01")
    assert req.specific_date.isoformat() == "2026-10-01"


def test_unknown_field_is_rejected():
    """extra='forbid'. A caller sending a field this API does not know about
    has misunderstood the contract, and silently dropping it would hide that."""
    with pytest.raises(ValidationError):
        build(consultee_email="doctor@example.com")


def test_email_is_not_part_of_the_contract():
    """DECISIONS.md section 15: the address comes from the SSO session. An
    email in the body would be client-supplied and therefore spoofable."""
    assert "consultee_email" not in RequestCreate.model_fields
    assert "email" not in RequestCreate.model_fields
