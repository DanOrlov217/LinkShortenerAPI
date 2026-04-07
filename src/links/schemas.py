from datetime import datetime, timezone
from pydantic import BaseModel, field_validator


class BaseResponse(BaseModel):
    success: bool
    details: str | None = None


class CreateLinkResponse(BaseResponse):
    short_code: str | None = None


class UpdateLinkResponse(BaseResponse):
    pass


class LinkStatsResponse(BaseResponse):
    original_url: str
    short_code: str
    created_at: datetime
    expires_at: datetime
    last_accessed_at: datetime
    access_count: int


class LinkSearchItem(BaseModel):
    short_code: str
    expires_at: datetime


class LinkSearchResponse(BaseResponse):
    results: list[LinkSearchItem] = []


class LinkHistoryItem(BaseModel):
    original_url: str
    short_code: str
    created_at: datetime
    expired_at: datetime
    access_count: int
    deleted_by_user: bool


class LinkHistoryRequest(BaseModel):
    page: int = 1
    limit: int = 20


class LinkHistoryResponse(BaseResponse):
    results: list[LinkHistoryItem] = []
    page: int
    limit: int
    total: int


class CreateLinkRequest(BaseModel):
    url: str
    expires_at: datetime | None = None
    custom_alias: str | None = None

    @field_validator("expires_at", mode="before")
    @classmethod
    def parse_expires_at(cls, v) -> datetime | None:
        if v is None or isinstance(v, datetime):
            return v
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(v, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        raise ValueError("Use format 'YYYY-MM-DD HH:MM' or 'YYYY-MM-DDTHH:MM:SSZ'")

    @field_validator("expires_at")
    @classmethod
    def must_be_future(cls, v: datetime | None) -> datetime | None:
        if v is not None and v <= datetime.now(timezone.utc):
            raise ValueError("expires_at must be a future datetime")
        return v