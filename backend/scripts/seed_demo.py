"""Seed stations and a demo consult so the UI has something to show.

Run from backend/:   python -m scripts.seed_demo

Safe to run repeatedly. Stations are created only if missing, and each run
adds one new demo request so you can test the queue with several rows.
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from app.config import get_settings
from app.core.identity import Consultee
from app.database import AsyncSessionLocal
from app.models import Station
from app.schemas.questionnaire import RequestCreate
from app.services.request_service import build_chat_url, create_request

# From the sorting demo. These strings must match exactly what the caller's
# sorting system emits.
STATIONS = [
    "Neuro",
    "Chest",
    "CVS",
    "Abdomen",
    "MSK",
    "Ultrasound",
    "PED",
    "Manual sort",
]

DEMO = {
    "station": "Neuro",
    "patient_name": "สมชาย ใจดี",
    "sex": "male",
    "age_value": 62,
    "age_unit": "years",
    "hn": "JX1234",
    "qshc_hn": "QS00881",
    "modality": "CT",
    "body_region": "Brain, head and neck",
    "study": "CTA Brain",
    "time_period": "today",
    "patient_history": (
        "Sudden onset severe headache 2 hours ago, worst of life. "
        "GCS 14, no focal neurological deficit. BP 180/100. "
        "No history of trauma. On aspirin for AF."
    ),
    "md_name": "Dr Somchai Jaidee",
    "staff_name": "Prof Wichai Suksan",
    "tel": "081-234-5678",
}

DEMO_CONSULTEE = Consultee(email="doctor@example.com", name="Dr Somchai Jaidee")


async def main() -> None:
    settings = get_settings()

    async with AsyncSessionLocal() as session:
        existing = set(
            (await session.execute(select(Station.name))).scalars().all()
        )
        created = [n for n in STATIONS if n not in existing]
        for name in created:
            session.add(Station(name=name))
        if created:
            await session.flush()
            print(f"created stations: {', '.join(created)}")
        else:
            print("stations already present")

        payload = RequestCreate.model_validate(DEMO)
        request = await create_request(
            session, payload, DEMO_CONSULTEE, settings
        )
        await session.commit()

        print()
        print("demo request created")
        print(f"  request_id : {request.id}")
        print(f"  HN         : {request.external_id}")
        print(f"  station    : {payload.station}")
        print(f"  expires    : {request.expires_at}")
        print()
        print("Doctor's view:")
        print(f"  {build_chat_url(request, settings)}")
        print()
        print("Resident's view:")
        print(f"  {settings.PUBLIC_BASE_URL.rstrip('/')}/admin")
        print()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(1)
