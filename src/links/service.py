from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
from datetime import datetime, timedelta, timezone

from .models import ShortLink, ExpiredLink
from .utils import generate_short_url
from .constants import (
    MAX_GENERATION_ATTEMPTS,
    SHORT_URL_LENGTH,
    DEFAULT_LINK_EXPIRATION_DAYS
)


class LinkService:

    def __init__(
        self, session: AsyncSession
    ) -> None:
        self.session = session

    async def create_link(
        self,
        original_url: str,
        user_id: Optional[int] = None,
        expires_at: Optional[datetime] = None,
        custom_alias: Optional[str] = None
    ) -> str | None:
        expiration = expires_at or datetime.now(timezone.utc) + timedelta(days=DEFAULT_LINK_EXPIRATION_DAYS)
        if custom_alias:
            if await self._get_or_cleanup_short_url(custom_alias):
                return None
            new_link = ShortLink(
                original_url=original_url,
                short_code=custom_alias,
                owner_id=user_id,
                expires_at=expiration
            )
            self.session.add(new_link)
            await self.session.commit()
            return custom_alias
        for i in range(1, MAX_GENERATION_ATTEMPTS + 1):
            short_url = generate_short_url(original_url, length=SHORT_URL_LENGTH)
            if await self._get_or_cleanup_short_url(short_url):  # борьба с коллизиями
                original_url += str(i)
                continue
            new_link = ShortLink(
                original_url=original_url,
                short_code=short_url,
                owner_id=user_id,
                expires_at=expiration
            )
            self.session.add(new_link)
            await self.session.commit()
            return short_url
        return None

    async def delete_expired(self) -> int:
        stmt = select(ShortLink).where(ShortLink.expires_at < datetime.now(timezone.utc))
        result = await self.session.execute(stmt)
        expired = result.scalars().all()
        now = datetime.now(timezone.utc)
        for link in expired:
            if link.owner_id is not None:
                self.session.add(ExpiredLink(
                    original_url=link.original_url,
                    short_code=link.short_code,
                    created_at=link.created_at,
                    expired_at=now,
                    access_count=link.access_count,
                    deleted_by_user=False,
                    owner_id=link.owner_id,
                ))
            await self.session.delete(link)
        await self.session.commit()
        return len(expired)

    async def delete_link(
        self,
        short_url: str,
        user_id: int
    ) -> bool:
        link = await self._get_link_by_short_url(short_url=short_url, owner_id=user_id)
        if link:
            self.session.add(ExpiredLink(
                original_url=link.original_url,
                short_code=link.short_code,
                created_at=link.created_at,
                expired_at=datetime.now(timezone.utc),
                access_count=link.access_count,
                deleted_by_user=True,
                owner_id=link.owner_id,
            ))
            await self.session.delete(link)
            await self.session.commit()
            return True
        return False
    
    async def update_link(
        self,
        short_url: str,
        new_url: str,
        user_id: int
    ) -> bool:
        link = await self._get_link_by_short_url(short_url=short_url, owner_id=user_id)
        if link:
            link.original_url = new_url
            await self.session.commit()
            return True
        return False
    
    async def use_link(self, short_url: str) -> ShortLink | None:
        link = await self._get_link_by_short_url(short_url=short_url)
        if link:
            link.access_count += 1
            link.last_accessed_at = datetime.now(timezone.utc)
            await self.session.commit()
        return link
    
    async def search_links(self, original_url: str) -> list[ShortLink]:
        return await self._get_links_by_original_url(original_url)

    async def get_link_history(self, user_id: int, page: int = 1, limit: int = 20) -> tuple[list[ExpiredLink], int]:
        now = datetime.now(timezone.utc)
        unarchived_result = await self.session.execute(
            select(ShortLink).where(ShortLink.owner_id == user_id, ShortLink.expires_at <= now)
        )
        unarchived = unarchived_result.scalars().all()
        for link in unarchived:
            self.session.add(ExpiredLink(
                original_url=link.original_url,
                short_code=link.short_code,
                created_at=link.created_at,
                expired_at=link.expires_at,
                access_count=link.access_count,
                deleted_by_user=False,
                owner_id=link.owner_id,
            ))
            await self.session.delete(link)
        if unarchived:
            await self.session.commit()

        base = select(ExpiredLink).where(ExpiredLink.owner_id == user_id)
        total_result = await self.session.execute(select(func.count()).select_from(base.subquery()))
        total = total_result.scalar_one()
        stmt = base.order_by(ExpiredLink.expired_at.desc()).offset((page - 1) * limit).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all(), total

    async def get_link(self, short_url: str) -> ShortLink | None:
        return await self._get_link_by_short_url(short_url=short_url)

    async def _get_or_cleanup_short_url(self, short_url: str) -> ShortLink | None:
        stmt = select(ShortLink).where(ShortLink.short_code == short_url)
        result = await self.session.execute(stmt)
        link = result.scalar_one_or_none()
        if link is None:
            return None
        if link.expires_at > datetime.now(timezone.utc):
            return link
        if link.owner_id is not None:
            self.session.add(ExpiredLink(
                original_url=link.original_url,
                short_code=link.short_code,
                created_at=link.created_at,
                expired_at=link.expires_at,
                access_count=link.access_count,
                deleted_by_user=False,
                owner_id=link.owner_id,
            ))
        await self.session.delete(link)
        await self.session.commit()
        return None

    async def _get_link_by_short_url(
        self,
        short_url: str,
        owner_id: Optional[int] = None
    ) -> ShortLink | None:
        try:
            if short_url:
                stmt = select(ShortLink).where(
                    ShortLink.short_code == short_url,
                    ShortLink.expires_at > datetime.now(timezone.utc)
                )
                if owner_id is not None:
                    stmt = stmt.where(ShortLink.owner_id == owner_id)
            else:
                raise ValueError("short_url must be provided")
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            print(f"Error fetching link: {e}")
            return None
        
    async def _get_links_by_original_url(self, original_url: str) -> list[ShortLink]:
        stmt = select(ShortLink).where(
            ShortLink.original_url == original_url,
            ShortLink.expires_at > datetime.now(timezone.utc)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()