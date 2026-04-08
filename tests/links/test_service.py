import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from links.service import LinkService  # type: ignore
from links.models import ShortLink, ExpiredLink  # type: ignore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

OWNER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _future(days: int = 30) -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=days)


def _past(days: int = 1) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


async def _add_link(session: AsyncSession, **kwargs) -> ShortLink:
    defaults = dict(
        original_url="https://example.com",
        short_code="abc123",
        expires_at=_future(),
        access_count=0,
    )
    defaults.update(kwargs)
    link = ShortLink(**defaults)
    session.add(link)
    await session.commit()
    await session.refresh(link)
    return link


# ---------------------------------------------------------------------------
# create_link
# ---------------------------------------------------------------------------

async def test_create_link_returns_short_code(db_session: AsyncSession):
    service = LinkService(db_session)
    code = await service.create_link("https://example.com")
    assert isinstance(code, str)
    assert len(code) == 6


async def test_create_link_custom_alias(db_session: AsyncSession):
    service = LinkService(db_session)
    code = await service.create_link("https://example.com", custom_alias="myalias")
    assert code == "myalias"


async def test_create_link_custom_alias_conflict_returns_none(db_session: AsyncSession):
    service = LinkService(db_session)
    await service.create_link("https://example.com", custom_alias="taken")
    result = await service.create_link("https://other.com", custom_alias="taken")
    assert result is None


async def test_create_link_stores_owner_id(db_session: AsyncSession):
    service = LinkService(db_session)
    code = await service.create_link("https://example.com", user_id=OWNER_ID)
    link = await service.get_link(code)
    assert link.owner_id == OWNER_ID


async def test_create_link_custom_expiry(db_session: AsyncSession):
    expiry = _future(days=7)
    service = LinkService(db_session)
    code = await service.create_link("https://example.com", expires_at=expiry)
    link = await service.get_link(code)
    assert abs((link.expires_at - expiry).total_seconds()) < 1


# ---------------------------------------------------------------------------
# get_link
# ---------------------------------------------------------------------------

async def test_get_link_returns_existing(db_session: AsyncSession):
    await _add_link(db_session, short_code="xyz999")
    service = LinkService(db_session)
    link = await service.get_link("xyz999")
    assert link is not None
    assert link.short_code == "xyz999"


async def test_get_link_returns_none_for_missing(db_session: AsyncSession):
    service = LinkService(db_session)
    link = await service.get_link("nope00")
    assert link is None


async def test_get_link_returns_none_for_expired(db_session: AsyncSession):
    await _add_link(db_session, short_code="old000", expires_at=_past())
    service = LinkService(db_session)
    link = await service.get_link("old000")
    assert link is None


# ---------------------------------------------------------------------------
# use_link
# ---------------------------------------------------------------------------

async def test_use_link_increments_access_count(db_session: AsyncSession):
    await _add_link(db_session, short_code="used00", access_count=3)
    service = LinkService(db_session)
    link = await service.use_link("used00")
    assert link.access_count == 4


async def test_use_link_updates_last_accessed_at(db_session: AsyncSession):
    before = datetime.now(timezone.utc)
    await _add_link(db_session, short_code="used01")
    service = LinkService(db_session)
    link = await service.use_link("used01")
    assert link.last_accessed_at >= before


async def test_use_link_returns_none_for_missing(db_session: AsyncSession):
    service = LinkService(db_session)
    result = await service.use_link("nope00")
    assert result is None


# ---------------------------------------------------------------------------
# update_link
# ---------------------------------------------------------------------------

async def test_update_link_changes_original_url(db_session: AsyncSession):
    await _add_link(db_session, short_code="upd000", owner_id=OWNER_ID)
    service = LinkService(db_session)
    success = await service.update_link("upd000", "https://new.com", user_id=OWNER_ID)
    assert success is True
    link = await service.get_link("upd000")
    assert link.original_url == "https://new.com"


async def test_update_link_wrong_owner_returns_false(db_session: AsyncSession):
    await _add_link(db_session, short_code="upd001", owner_id=OWNER_ID)
    service = LinkService(db_session)
    other_id = uuid.UUID("00000000-0000-0000-0000-000000000099")
    success = await service.update_link("upd001", "https://new.com", user_id=other_id)
    assert success is False


# ---------------------------------------------------------------------------
# delete_link
# ---------------------------------------------------------------------------

async def test_delete_link_removes_short_link(db_session: AsyncSession):
    await _add_link(db_session, short_code="del000", owner_id=OWNER_ID)
    service = LinkService(db_session)
    success = await service.delete_link("del000", user_id=OWNER_ID)
    assert success is True
    assert await service.get_link("del000") is None


async def test_delete_link_creates_expired_record(db_session: AsyncSession):
    await _add_link(db_session, short_code="del001", owner_id=OWNER_ID)
    service = LinkService(db_session)
    await service.delete_link("del001", user_id=OWNER_ID)
    from sqlalchemy import select
    result = await db_session.execute(
        select(ExpiredLink).where(ExpiredLink.short_code == "del001")
    )
    record = result.scalar_one_or_none()
    assert record is not None
    assert record.deleted_by_user is True


async def test_delete_link_wrong_owner_returns_false(db_session: AsyncSession):
    await _add_link(db_session, short_code="del002", owner_id=OWNER_ID)
    service = LinkService(db_session)
    other_id = uuid.UUID("00000000-0000-0000-0000-000000000099")
    success = await service.delete_link("del002", user_id=other_id)
    assert success is False


# ---------------------------------------------------------------------------
# delete_expired
# ---------------------------------------------------------------------------

async def test_delete_expired_removes_expired_links(db_session: AsyncSession):
    await _add_link(db_session, short_code="exp001", expires_at=_past())
    await _add_link(db_session, short_code="exp002", expires_at=_future())
    service = LinkService(db_session)
    count = await service.delete_expired()
    assert count == 1
    assert await service.get_link("exp002") is not None


async def test_delete_expired_archives_owned_links(db_session: AsyncSession):
    await _add_link(db_session, short_code="exp003", expires_at=_past(), owner_id=OWNER_ID)
    service = LinkService(db_session)
    await service.delete_expired()
    from sqlalchemy import select
    result = await db_session.execute(
        select(ExpiredLink).where(ExpiredLink.short_code == "exp003")
    )
    assert result.scalar_one_or_none() is not None


async def test_delete_expired_no_archive_for_anonymous_links(db_session: AsyncSession):
    await _add_link(db_session, short_code="exp004", expires_at=_past(), owner_id=None)
    service = LinkService(db_session)
    await service.delete_expired()
    from sqlalchemy import select
    result = await db_session.execute(
        select(ExpiredLink).where(ExpiredLink.short_code == "exp004")
    )
    assert result.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# search_links
# ---------------------------------------------------------------------------

async def test_search_links_finds_matching(db_session: AsyncSession):
    await _add_link(db_session, short_code="sch001", original_url="https://find.me")
    service = LinkService(db_session)
    results = await service.search_links("https://find.me")
    assert len(results) == 1
    assert results[0].short_code == "sch001"


async def test_search_links_excludes_expired(db_session: AsyncSession):
    await _add_link(db_session, short_code="sch002", original_url="https://find.me", expires_at=_past())
    service = LinkService(db_session)
    results = await service.search_links("https://find.me")
    assert len(results) == 0
