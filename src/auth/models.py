from __future__ import annotations
from typing import TYPE_CHECKING

from datetime import datetime, timezone
from fastapi import Depends
from fastapi_users.db import SQLAlchemyBaseUserTableUUID, SQLAlchemyUserDatabase
from sqlalchemy import DateTime
from sqlalchemy.orm import mapped_column, Mapped, relationship
from sqlalchemy.ext.asyncio import AsyncSession
from database import engine, get_async_session
from models import Base

if TYPE_CHECKING:
    from links.models import ShortLink, ExpiredLink


class User(SQLAlchemyBaseUserTableUUID, Base):
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    links: Mapped[list["ShortLink"]] = relationship("ShortLink", back_populates="owner")
    links_history: Mapped[list["ExpiredLink"]] = relationship("ExpiredLink", back_populates="owner")


async def create_db_and_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_user_db(session: AsyncSession = Depends(get_async_session)):
    yield SQLAlchemyUserDatabase(session, User)