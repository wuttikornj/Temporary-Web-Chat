"""Shared fixtures.

The suite runs against in-memory SQLite, so it needs no MySQL server and no
.env. That is a deliberate trade: these tests cover application behaviour, not
MySQL-specific behaviour. Anything that depends on the real engine (index use,
collation, cascade semantics) needs a MySQL integration test, which does not
exist yet.
"""

from __future__ import annotations

import os

# Must be set before app.config is imported anywhere.
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "3306")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ENCRYPTION_KEY", "test-encryption-key")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings, get_settings
from app.core.identity import (
    Admin,
    Consultee,
    get_current_admin,
    get_current_consultee,
)
from app.database import Base, get_db
from app.main import app
from app.models import Station

TEST_CONSULTEE = Consultee(email="doctor@example.com", name="Dr Somchai")
TEST_ADMIN = Admin(email="resident@example.com", name="Dr Resident")

STATIONS = ["Neuro", "Chest", "PED"]


@pytest.fixture
def settings() -> Settings:
    return Settings(
        DB_HOST="localhost",
        DB_PORT=3306,
        DB_USER="test",
        DB_PASSWORD="test",
        DB_NAME="test",
        SECRET_KEY="test-secret",
        ENCRYPTION_KEY="test-encryption-key",
        PUBLIC_BASE_URL="http://testserver",
        REQUEST_EXPIRY_DAYS=7,
        UNREAD_EMAIL_DELAY_MINUTES=5,
        SMTP_HOST="",
    )


@pytest_asyncio.fixture
async def session_factory():
    """A fresh in-memory database per test.

    StaticPool plus a shared connection is required: without it each new
    connection gets its own empty :memory: database and the tables vanish
    between statements.
    """
    from sqlalchemy.pool import StaticPool

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    async with factory() as session:
        for name in STATIONS:
            session.add(Station(name=name))
        await session.commit()

    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def db(session_factory) -> AsyncSession:
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(session_factory, settings) -> AsyncClient:
    """App wired to the test database, with identity stubbed to a known user.

    Overriding the identity dependencies rather than setting DEV_AUTH_STUB is
    deliberate: the tests should not depend on the development header stub,
    which is one of the things most likely to be replaced at integration time.
    """

    async def override_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_current_consultee] = lambda: TEST_CONSULTEE
    app.dependency_overrides[get_current_admin] = lambda: TEST_ADMIN

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c

    app.dependency_overrides.clear()


VALID_INTAKE = {
    "station": "Neuro",
    "patient_name": "Test Patient",
    "sex": "male",
    "age_value": 62,
    "age_unit": "years",
    "hn": "JX1234",
    "modality": "CT",
    "body_region": "Brain, head and neck",
    "study": "CTA Brain",
    "time_period": "today",
    "patient_history": "Sudden onset severe headache.",
    "md_name": "Dr Somchai",
    "staff_name": "Prof Wichai",
    "tel": "0812345678",
}


@pytest.fixture
def intake() -> dict:
    return dict(VALID_INTAKE)
