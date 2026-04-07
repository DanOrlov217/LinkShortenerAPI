from __future__ import annotations
from typing import TYPE_CHECKING

from datetime import datetime, timedelta, timezone
from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import mapped_column, Mapped, relationship

from models import Base

if TYPE_CHECKING:
    from auth.models import User

from .constants import DEFAULT_LINK_EXPIRATION_DAYS


class ShortLink(Base):
    __tablename__ = "short_links"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    original_url: Mapped[str] = mapped_column(nullable=False)
    short_code: Mapped[str] = mapped_column(nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_accessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    access_count: Mapped[int] = mapped_column(default=0)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc) + timedelta(days=DEFAULT_LINK_EXPIRATION_DAYS)
    )
    owner_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=True)

    owner: Mapped["User"] = relationship("User", back_populates="links")


class ExpiredLink(Base):
    __tablename__ = "expired_links"

    id: Mapped[int] = mapped_column(primary_key=True, index=True, autoincrement=True)
    original_url: Mapped[str] = mapped_column(nullable=False)
    short_code: Mapped[str] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    access_count: Mapped[int] = mapped_column(default=0)
    deleted_by_user: Mapped[bool] = mapped_column(default=False)
    owner_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=True)

    owner: Mapped["User"] = relationship("User", back_populates="links_history")