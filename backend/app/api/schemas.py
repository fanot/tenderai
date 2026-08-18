"""Pydantic-схемы API."""
from __future__ import annotations

from pydantic import BaseModel, Field


class Filters(BaseModel):
    law: str | None = None
    region: str | None = None
    category: str | None = None
    status: str | None = None
    nmck_min: float | None = None
    nmck_max: float | None = None
    smp_only: bool | None = None
    only_active: bool = False


class SearchRequest(BaseModel):
    query: str = ""
    filters: Filters = Field(default_factory=Filters)
    page: int = 1
    page_size: int = 10
    sort: str = "relevance"  # relevance | deadline | nmck_desc | nmck_asc | published


class SearchHit(BaseModel):
    id: str
    registry_number: str
    subject: str
    customer: str
    region: str
    category: str
    law: str
    procedure: str
    platform: str
    nmck: float
    published_at: str
    deadline_at: str
    days_left: int
    status: str
    smp_only: bool
    url: str
    score: float
    explain: list[str]
    snippet: str


class SearchResponse(BaseModel):
    total: int
    page: int
    page_size: int
    took_ms: float
    parsed_filters: dict
    applied_filters: dict
    results: list[SearchHit]


class AskRequest(BaseModel):
    query: str
    top_k: int = 8
    # Текущий поисковый запрос пользователя: даёт ассистенту контекст,
    # когда вопрос сформулирован без предмета закупки («какие требования?»).
    context_query: str | None = None


class SourceOut(BaseModel):
    n: int
    tender_id: str
    registry_number: str
    title: str
    section: str
    snippet: str
    url: str


class AskResponse(BaseModel):
    answer: str
    intent: str
    provider: str
    filters: dict
    sources: list[SourceOut]
    warnings: list[str]
    took_ms: float
