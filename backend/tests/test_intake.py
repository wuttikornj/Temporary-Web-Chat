"""POST /api/v1/requests, the public contract."""

from sqlalchemy import select

from app.models import QuestionnaireAnswer, Request


async def test_creates_request_and_returns_link(client, intake):
    res = await client.post("/api/v1/requests", json=intake)
    assert res.status_code == 201

    body = res.json()
    assert body["station"] == "Neuro"
    assert "/chat/" in body["chat_url"]
    assert body["expires_at"]

    # The response must not echo patient data: the caller may log it.
    text = res.text
    assert intake["patient_name"] not in text
    assert intake["patient_history"] not in text


async def test_email_comes_from_the_session_not_the_payload(client, intake, db):
    """DECISIONS.md section 15. The stored address is the authenticated one."""
    res = await client.post("/api/v1/requests", json=intake)
    assert res.status_code == 201

    request = (await db.execute(select(Request))).scalar_one()
    assert request.email == "doctor@example.com"


async def test_hn_is_stored_uppercased(client, intake, db):
    intake["hn"] = "jx1234"
    await client.post("/api/v1/requests", json=intake)

    request = (await db.execute(select(Request))).scalar_one()
    assert request.external_id == "JX1234"


async def test_access_token_is_long_and_unique(client, intake, db):
    await client.post("/api/v1/requests", json=intake)
    await client.post("/api/v1/requests", json=intake)

    tokens = (await db.execute(select(Request.access_token))).scalars().all()
    assert len(tokens) == 2
    assert len(set(tokens)) == 2
    assert all(len(t) == 64 for t in tokens)


async def test_same_hn_may_open_several_requests(client, intake, db):
    """external_id is identification, not a key. One doctor can open several
    consults for the same patient. Making it unique would break the model."""
    await client.post("/api/v1/requests", json=intake)
    res = await client.post("/api/v1/requests", json=intake)
    assert res.status_code == 201

    ids = (await db.execute(select(Request.external_id))).scalars().all()
    assert ids == ["JX1234", "JX1234"]


async def test_answers_are_stored_without_the_promoted_fields(client, intake, db):
    await client.post("/api/v1/requests", json=intake)

    rows = (await db.execute(select(QuestionnaireAnswer))).scalars().all()
    keys = {r.field_key for r in rows}

    assert "patient_name" in keys
    assert "patient_history" in keys
    # Promoted to columns on requests, so not duplicated as answers.
    assert "hn" not in keys
    assert "station" not in keys


async def test_age_is_not_normalised(client, intake, db):
    """A 7-day-old and a 7-year-old are different patients."""
    intake["age_value"] = 7
    intake["age_unit"] = "days"
    await client.post("/api/v1/requests", json=intake)

    rows = (await db.execute(select(QuestionnaireAnswer))).scalars().all()
    answers = {r.field_key: r.field_value for r in rows}
    assert answers["age_value"] == "7"
    assert answers["age_unit"] == "days"


async def test_unknown_station_is_rejected(client, intake):
    """Stations are never created on demand: a typo must not silently open a
    folder no resident is watching."""
    intake["station"] = "Nuero"
    res = await client.post("/api/v1/requests", json=intake)
    assert res.status_code == 422
    assert "Nuero" in res.text


async def test_invalid_hn_is_rejected_without_creating_anything(client, intake, db):
    intake["hn"] = "nonsense"
    res = await client.post("/api/v1/requests", json=intake)
    assert res.status_code == 422

    assert (await db.execute(select(Request))).first() is None
