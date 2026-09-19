"""Messaging, both directions, and read tracking."""

from sqlalchemy import select

from app.models import Message, Request, SenderType


async def open_consult(client, intake) -> tuple[str, str]:
    res = await client.post("/api/v1/requests", json=intake)
    body = res.json()
    return body["request_id"], body["chat_url"].rsplit("/", 1)[-1]


async def test_summary_is_visible_before_any_message(client, intake):
    """The request details are the first thing both sides see."""
    _, token = await open_consult(client, intake)

    view = (await client.get(f"/api/v1/chat/{token}")).json()
    labels = {f["label"]: f["value"] for f in view["summary"]}

    assert view["hn"] == "JX1234"
    assert view["messages"] == []
    assert labels["Patient"] == "Test Patient"
    assert labels["Age"] == "62 years"
    assert labels["Study"] == "CTA Brain"


async def test_both_sides_see_the_same_summary(client, intake):
    request_id, token = await open_consult(client, intake)

    doctor = (await client.get(f"/api/v1/chat/{token}")).json()
    resident = (await client.get(f"/api/v1/admin/requests/{request_id}")).json()

    assert doctor["summary"] == resident["summary"]


async def test_messages_flow_both_ways(client, intake):
    request_id, token = await open_consult(client, intake)

    assert (
        await client.post(
            f"/api/v1/admin/requests/{request_id}/messages",
            json={"body": "Please send prior imaging."},
        )
    ).status_code == 201

    assert (
        await client.post(
            f"/api/v1/chat/{token}/messages", json={"body": "Attached now."}
        )
    ).status_code == 201

    view = (await client.get(f"/api/v1/chat/{token}")).json()
    assert [m["sender_type"] for m in view["messages"]] == ["admin", "user"]
    assert view["messages"][0]["body"] == "Please send prior imaging."


async def test_opening_a_thread_marks_the_other_side_read(client, intake, db):
    request_id, token = await open_consult(client, intake)
    await client.post(
        f"/api/v1/admin/requests/{request_id}/messages", json={"body": "hello"}
    )

    message = (await db.execute(select(Message))).scalar_one()
    assert message.read_at is None

    await client.get(f"/api/v1/chat/{token}")

    await db.refresh(message)
    assert message.read_at is not None


async def test_reading_does_not_mark_your_own_messages_read(client, intake, db):
    """Opening your own thread does not mean you have read yourself."""
    request_id, token = await open_consult(client, intake)
    await client.post(f"/api/v1/chat/{token}/messages", json={"body": "hi"})

    await client.get(f"/api/v1/chat/{token}")

    message = (await db.execute(select(Message))).scalar_one()
    assert message.sender_type == SenderType.USER
    assert message.read_at is None


async def test_unknown_token_is_404(client):
    assert (await client.get("/api/v1/chat/" + "0" * 64)).status_code == 404


async def test_empty_message_is_rejected(client, intake):
    _, token = await open_consult(client, intake)
    res = await client.post(f"/api/v1/chat/{token}/messages", json={"body": "   "})
    assert res.status_code == 422


async def test_closed_thread_is_read_only(client, intake, db):
    _, token = await open_consult(client, intake)

    request = (await db.execute(select(Request))).scalar_one()
    request.status = "closed"
    await db.commit()

    res = await client.post(f"/api/v1/chat/{token}/messages", json={"body": "hi"})
    assert res.status_code == 409


async def test_queue_orders_unread_first(client, intake, db):
    """A resident opening the dashboard sees what is waiting on them."""
    quiet_id, _ = await open_consult(client, intake)
    busy_id, busy_token = await open_consult(client, intake)

    await client.post(f"/api/v1/chat/{busy_token}/messages", json={"body": "?"})

    queue = (await client.get("/api/v1/admin/requests")).json()
    assert queue[0]["request_id"] == busy_id
    assert queue[0]["unread_count"] == 1
    assert queue[1]["request_id"] == quiet_id


async def test_queue_filters_by_station(client, intake):
    await open_consult(client, intake)
    intake["station"] = "Chest"
    await open_consult(client, intake)

    chest = (await client.get("/api/v1/admin/requests?station=Chest")).json()
    assert len(chest) == 1
    assert chest[0]["station"] == "Chest"
