import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from celery_app import celery

import auth.models
from cache import make_redis, cache_url, invalidate_url
from database import make_session_maker
from links.models import ShortLink
from links.service import LinkService
from links.constants import POPULAR_LINK_THRESHOLD


def _make_session_maker():
    return make_session_maker(nullpool=True)


@celery.task(name="tasks.cleanup_expired_links")
def cleanup_expired_links():
    asyncio.run(_cleanup_expired_links())


async def _cleanup_expired_links():
    session_maker = _make_session_maker()
    async with session_maker() as session:
        await LinkService(session).delete_expired()


@celery.task(name="tasks.update_link_stats")
def update_link_stats(short_code: str):
    asyncio.run(_update_link_stats(short_code))


async def _update_link_stats(short_code: str):
    session_maker = _make_session_maker()
    async with session_maker() as session:
        await LinkService(session).use_link(short_code)


@celery.task(name="tasks.sync_popular_links_cache")
def sync_popular_links_cache():
    asyncio.run(_sync_popular_links_cache())


async def _sync_popular_links_cache():
    redis = make_redis()
    try:
        session_maker = _make_session_maker()
        async with session_maker() as session:
            stmt = select(ShortLink).where(
                ShortLink.expires_at > datetime.now(timezone.utc)
            )
            result = await session.execute(stmt)
            links = result.scalars().all()
        now = datetime.now(timezone.utc)
        for link in links:
            ttl = max(1, int((link.expires_at - now).total_seconds()))
            if link.access_count >= POPULAR_LINK_THRESHOLD:
                await cache_url(link.short_code, link.original_url, ttl, redis=redis)
            else:
                await invalidate_url(link.short_code, redis=redis)
    finally:
        await redis.close()
