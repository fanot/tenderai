"""HTTP-эндпоинты веб-сервиса."""
from __future__ import annotations

import time
from datetime import date

from fastapi import APIRouter, HTTPException, Query

from ..core.config import settings
from ..core.store import get_store
from ..rag import query_parser
from ..rag.query_parser import ParsedQuery
from .schemas import (
    AskRequest,
    AskResponse,
    SearchHit,
    SearchRequest,
    SearchResponse,
    SourceOut,
)

router = APIRouter(prefix="/api")

SORTERS = {
    "relevance": lambda h: -h["score"],
    "deadline": lambda h: h["deadline_at"],
    "nmck_desc": lambda h: -h["nmck"],
    "nmck_asc": lambda h: h["nmck"],
    "published": lambda h: (date(2100, 1, 1) - date.fromisoformat(h["published_at"])).days,
}


@router.get("/health")
def health() -> dict:
    store = get_store()
    return {
        "status": "ok",
        "version": settings.version,
        "tenders": len(store.tenders),
        "chunks": len(store.retriever.chunks),
        "index_build_ms": store.index_build_ms,
    }


@router.get("/meta")
def meta() -> dict:
    return get_store().meta()


def _merge(pq: ParsedQuery, req: SearchRequest) -> ParsedQuery:
    """Явные фильтры UI имеют приоритет над распознанными из текста запроса."""
    f = req.filters
    if f.law:
        pq.law = f.law
    if f.region:
        pq.region = f.region
    if f.category:
        pq.category = f.category
    if f.nmck_min is not None:
        pq.nmck_min = f.nmck_min
    if f.nmck_max is not None:
        pq.nmck_max = f.nmck_max
    if f.smp_only is not None:
        pq.smp_only = f.smp_only
    if f.only_active:
        pq.only_active = True
    return pq


@router.post("/search", response_model=SearchResponse)
def search(req: SearchRequest) -> SearchResponse:
    t0 = time.perf_counter()
    store = get_store()
    pq = query_parser.parse(req.query)
    parsed = pq.to_dict()
    pq = _merge(pq, req)

    hits = store.retriever.retrieve(pq, top_k=200)
    if req.filters.status:
        hits = [h for h in hits if h.tender["status"] == req.filters.status]

    today = date.today()
    rows = []
    for h in hits:
        t = h.tender
        rows.append(
            {
                **{k: t[k] for k in (
                    "id", "registry_number", "subject", "customer", "region", "category",
                    "law", "procedure", "platform", "nmck", "published_at", "deadline_at",
                    "status", "smp_only", "url",
                )},
                "days_left": (date.fromisoformat(t["deadline_at"]) - today).days,
                "score": h.score,
                "explain": h.explain,
                "snippet": (h.best_chunk.text if h.best_chunk else t["description"])[:260],
            }
        )

    rows.sort(key=SORTERS.get(req.sort, SORTERS["relevance"]))
    total = len(rows)
    start = max(0, (req.page - 1) * req.page_size)
    page_rows = rows[start : start + req.page_size]

    return SearchResponse(
        total=total,
        page=req.page,
        page_size=req.page_size,
        took_ms=round((time.perf_counter() - t0) * 1000, 2),
        parsed_filters=parsed,
        applied_filters=pq.to_dict(),
        results=[SearchHit(**r) for r in page_rows],
    )


@router.get("/tenders/{tender_id}")
def get_tender(tender_id: str) -> dict:
    store = get_store()
    tender = store.by_id.get(tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail="Тендер не найден")
    today = date.today()
    return {
        **tender,
        "days_left": (date.fromisoformat(tender["deadline_at"]) - today).days,
        "similar": _similar(tender_id, limit=4),
    }


def _similar(tender_id: str, limit: int = 4) -> list[dict]:
    store = get_store()
    tender = store.by_id[tender_id]
    pq = query_parser.parse(tender["subject"])
    pq.category = tender["category"]
    hits = store.retriever.retrieve(pq, top_k=limit + 1)
    return [
        {
            "id": h.tender["id"],
            "subject": h.tender["subject"],
            "nmck": h.tender["nmck"],
            "region": h.tender["region"],
            "deadline_at": h.tender["deadline_at"],
        }
        for h in hits
        if h.tender["id"] != tender_id
    ][:limit]


@router.get("/similar/{tender_id}")
def similar(tender_id: str, limit: int = Query(4, ge=1, le=20)) -> list[dict]:
    if tender_id not in get_store().by_id:
        raise HTTPException(status_code=404, detail="Тендер не найден")
    return _similar(tender_id, limit)


@router.post("/assistant/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    if not req.query.strip():
        raise HTTPException(status_code=422, detail="Пустой запрос")
    t0 = time.perf_counter()
    result = get_store().assistant.ask(req.query, top_k=req.top_k, context_query=req.context_query)
    return AskResponse(
        answer=result.answer,
        intent=result.intent,
        provider=result.provider,
        filters=result.filters,
        sources=[SourceOut(**s.__dict__) for s in result.sources],
        warnings=result.warnings,
        took_ms=round((time.perf_counter() - t0) * 1000, 2),
    )


@router.get("/analytics/overview")
def analytics() -> dict:
    store = get_store()
    today = date.today()
    by_cat: dict[str, dict] = {}
    by_region: dict[str, int] = {}
    by_law: dict[str, int] = {}
    timeline: dict[str, int] = {}

    for t in store.tenders:
        c = by_cat.setdefault(t["category"], {"count": 0, "nmck": 0.0})
        c["count"] += 1
        c["nmck"] += t["nmck"]
        by_region[t["region"]] = by_region.get(t["region"], 0) + 1
        by_law[t["law"]] = by_law.get(t["law"], 0) + 1
        timeline[t["published_at"][:7]] = timeline.get(t["published_at"][:7], 0) + 1

    active = [t for t in store.tenders if t["status"] == "Подача заявок"]
    closing = sorted(
        (t for t in active if 0 <= (date.fromisoformat(t["deadline_at"]) - today).days <= 7),
        key=lambda t: t["deadline_at"],
    )[:5]

    return {
        "total": len(store.tenders),
        "active": len(active),
        "total_nmck": round(sum(t["nmck"] for t in store.tenders), 2),
        "avg_nmck": round(sum(t["nmck"] for t in store.tenders) / len(store.tenders), 2),
        "smp_share": round(100 * sum(t["smp_only"] for t in store.tenders) / len(store.tenders), 1),
        "by_category": [
            {"category": k, "count": v["count"], "nmck": round(v["nmck"], 2)}
            for k, v in sorted(by_cat.items(), key=lambda kv: -kv[1]["count"])
        ],
        "by_region": [
            {"region": k, "count": v} for k, v in sorted(by_region.items(), key=lambda kv: -kv[1])
        ],
        "by_law": by_law,
        "timeline": [{"month": k, "count": v} for k, v in sorted(timeline.items())],
        "closing_soon": [
            {
                "id": t["id"],
                "subject": t["subject"],
                "deadline_at": t["deadline_at"],
                "nmck": t["nmck"],
                "days_left": (date.fromisoformat(t["deadline_at"]) - today).days,
            }
            for t in closing
        ],
    }
