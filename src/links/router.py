from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_async_session
from auth.users import current_active_user
from auth.models import User
from cache import get_cached_url, invalidate_url
from tasks import update_link_stats

from .service import LinkService
from .schemas import (
    CreateLinkResponse,
    UpdateLinkResponse,
    CreateLinkRequest,
    LinkStatsResponse,
    LinkSearchResponse,
    LinkSearchItem,
    LinkHistoryRequest,
    LinkHistoryResponse,
    LinkHistoryItem,
)


router = APIRouter(
    prefix="/links",
    tags=["Short Links"]
)


@router.post("/shorten", response_model=CreateLinkResponse)
async def shorten_link(
    request: CreateLinkRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User | None = Depends(current_active_user)
) -> CreateLinkResponse:
    try:
        service = LinkService(session)
        short_code = await service.create_link(
            request.url,
            user_id=user.id if user else None,
            expires_at=request.expires_at,
            custom_alias=request.custom_alias
        )
        if not short_code:
            return CreateLinkResponse(success=False, details="Failed to generate short link due to the hashing collisions.")
        return CreateLinkResponse(success=True, short_code=short_code)
    except ValueError as e:
        print(f"Error creating link: {e}")
        return CreateLinkResponse(success=False, details=str(e))


@router.post("/history", response_model=LinkHistoryResponse)
async def get_link_history(
    request: LinkHistoryRequest,
    session: AsyncSession = Depends(get_async_session),
    user: User | None = Depends(current_active_user)
) -> LinkHistoryResponse:
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    service = LinkService(session)
    history, total = await service.get_link_history(user.id, page=request.page, limit=request.limit)
    return LinkHistoryResponse(
        success=True,
        results=[LinkHistoryItem(
            original_url=h.original_url,
            short_code=h.short_code,
            created_at=h.created_at,
            expired_at=h.expired_at,
            access_count=h.access_count,
            deleted_by_user=h.deleted_by_user,
        ) for h in history],
        page=request.page,
        limit=request.limit,
        total=total,
    )


@router.get("/search", response_model=LinkSearchResponse)
async def search_links(
    original_url: str,
    session: AsyncSession = Depends(get_async_session)
) -> LinkSearchResponse:
    service = LinkService(session)
    links = await service.search_links(original_url)
    return LinkSearchResponse(
        success=True,
        results=[LinkSearchItem(short_code=l.short_code, expires_at=l.expires_at) for l in links]
    )


@router.get("/{short_code}", response_model=None)
async def redirect_to_original(
    short_code: str,
    session: AsyncSession = Depends(get_async_session)
) -> RedirectResponse | dict:
    cached = await get_cached_url(short_code)
    if cached:
        update_link_stats.delay(short_code)
        return RedirectResponse(cached)
    service = LinkService(session)
    link = await service.use_link(short_code)
    if link:
        return RedirectResponse(link.original_url)
    return {"error": "Short link not found"}


@router.delete("/{short_code}", status_code=204)
async def delete_link(
    short_code: str,
    session: AsyncSession = Depends(get_async_session),
    user: User | None = Depends(current_active_user)
) -> None:
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    service = LinkService(session)
    if not await service.delete_link(short_code, user.id):
        raise HTTPException(status_code=404, detail="Link not found or you don't have permission to delete it")
    await invalidate_url(short_code)


@router.put("/{short_code}", status_code=200, response_model=UpdateLinkResponse)
async def update_link(
    short_code: str,
    new_url: str,
    session: AsyncSession = Depends(get_async_session),
    user: User | None = Depends(current_active_user)
) -> UpdateLinkResponse:
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    service = LinkService(session)
    if not await service.update_link(short_code, new_url, user.id):
        return UpdateLinkResponse(success=False, details="Failed to update link. Link may not exist or you may not have permission to update it.")
    await invalidate_url(short_code)
    return UpdateLinkResponse(success=True)


@router.get("/{short_code}/stats", response_model=LinkStatsResponse)
async def get_link_stats(
    short_code: str,
    session: AsyncSession = Depends(get_async_session)
) -> LinkStatsResponse:
    service = LinkService(session)
    stats = await service.get_link(short_code)
    if not stats:
        raise HTTPException(status_code=404, detail="Short link not found")
    return LinkStatsResponse(
        success=True,
        original_url=stats.original_url,
        short_code=stats.short_code,
        created_at=stats.created_at,
        expires_at=stats.expires_at,
        last_accessed_at=stats.last_accessed_at,
        access_count=stats.access_count
    )