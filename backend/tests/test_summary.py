"""The intake summary shown at the top of both chat views."""

from app.models import QuestionnaireAnswer
from app.services.summary import build_summary


def answers(**kw) -> list[QuestionnaireAnswer]:
    return [
        QuestionnaireAnswer(field_key=k, field_value=v) for k, v in kw.items()
    ]


def labelled(fields) -> dict[str, str]:
    return {f.label: f.value for f in fields}


def test_age_keeps_its_unit():
    assert labelled(build_summary(answers(age_value="7", age_unit="days")))["Age"] == "7 days"
    assert labelled(build_summary(answers(age_value="7", age_unit="years")))["Age"] == "7 years"


def test_codes_are_rendered_as_labels():
    out = labelled(build_summary(answers(sex="male", time_period="1w")))
    assert out["Sex"] == "Male"
    assert out["Requested within"] == "Within 1 week"


def test_blank_answers_are_dropped():
    """An optional field nobody filled in is noise in a triage view."""
    out = labelled(build_summary(answers(patient_name="A", qshc_hn="")))
    assert "Patient" in out
    assert "QSHC HN" not in out


def test_order_is_triage_order_with_history_last():
    fields = build_summary(
        answers(
            patient_history="long text",
            study="CTA Brain",
            patient_name="A",
            modality="CT",
        )
    )
    assert [f.key for f in fields] == [
        "patient_name",
        "modality",
        "study",
        "patient_history",
    ]


def test_unknown_keys_are_ignored():
    """A caller sending a field this version does not render must not break
    the view."""
    out = labelled(build_summary(answers(patient_name="A", future_field="x")))
    assert out == {"Patient": "A"}
