import sys
import os
from typing import AsyncGenerator


os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASS", "test")
os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "testdb")
os.environ.setdefault("AUTH_SECRET", "test-secret-key-for-unit-testing-only")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


import pytest
import pytest_asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool
from sqlalchemy.dialects.sqlite import DATETIME as _SQLiteDateTime

from models import Base # type: ignore
from database import get_async_session # type: ignore
from main import app # type: ignore


_orig_result_processor = _SQLiteDateTime.result_processor


def _tz_aware_result_processor(self, dialect, coltype):
    proc = _orig_result_processor(self, dialect, coltype)
    if proc is None:
        return None

    def process(value):
        result = proc(value)
        if isinstance(result, datetime) and result.tzinfo is None:
            return result.replace(tzinfo=timezone.utc)
        return result

    return process


_SQLiteDateTime.result_processor = _tz_aware_result_processor


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with session_maker() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def mock_redis() -> AsyncMock:
    redis = AsyncMock()
    redis.get.return_value = None
    redis.set.return_value = True
    redis.delete.return_value = True
    redis.close = AsyncMock()
    return redis


@pytest_asyncio.fixture
async def client(db_session: AsyncSession, mock_redis: AsyncMock) -> AsyncGenerator[AsyncClient, None]:
    async def override_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_async_session] = override_session

    import cache as _cache  # type: ignore
    _cache._redis_client = mock_redis

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    _cache._redis_client = None
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_client(client: AsyncClient) -> AsyncClient:
    email, password = "testuser@example.com", "testpassword1"
    await client.post("/auth/register", json={"email": email, "password": password})
    resp = await client.post(
        "/auth/jwt/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    token = resp.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client

