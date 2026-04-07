from redis import asyncio as aioredis
from config import REDIS_URL


LINK_CACHE_PREFIX = "short_link:"

_redis_client: aioredis.Redis | None = None


def make_redis() -> aioredis.Redis:
    return aioredis.from_url(REDIS_URL, decode_responses=True)


async def init_cache():
    global _redis_client
    _redis_client = make_redis()


async def close_cache():
    if _redis_client:
        await _redis_client.close()


def _redis() -> aioredis.Redis:
    return _redis_client


async def get_cached_url(short_code: str) -> str | None:
    return await _redis().get(f"{LINK_CACHE_PREFIX}{short_code}")


async def cache_url(short_code: str, original_url: str, ttl_seconds: int, redis=None):
    await (redis or _redis()).set(f"{LINK_CACHE_PREFIX}{short_code}", original_url, ex=ttl_seconds)


async def invalidate_url(short_code: str, redis=None):
    await (redis or _redis()).delete(f"{LINK_CACHE_PREFIX}{short_code}")
