"""Загрузка данных и сборка поискового индекса (синглтон на процесс)."""
from __future__ import annotations

import json
import time
from functools import lru_cache

from ..rag.assistant import TenderAssistant
from ..rag.embeddings import get_embedding_provider
from ..rag.llm import get_llm_provider
from ..rag.retriever import HybridRetriever
from .config import settings


def load_tenders() -> list[dict]:
    return json.loads(settings.data_path.read_text(encoding="utf-8"))


class Store:
    def __init__(self) -> None:
        t0 = time.perf_counter()
        self.tenders = load_tenders()
        self.by_id = {t["id"]: t for t in self.tenders}
        self.embedder = get_embedding_provider(settings.embeddings_provider)
        self.retriever = HybridRetriever(self.tenders, self.embedder)
        self.assistant = TenderAssistant(self.retriever, get_llm_provider(settings.llm_provider))
        self.index_build_ms = round((time.perf_counter() - t0) * 1000, 1)

    def meta(self) -> dict:
        def uniq(field: str) -> list[str]:
            return sorted({t[field] for t in self.tenders})

        return {
            "total": len(self.tenders),
            "categories": uniq("category"),
            "regions": uniq("region"),
            "laws": uniq("law"),
            "statuses": uniq("status"),
            "platforms": uniq("platform"),
            "procedures": uniq("procedure"),
            "nmck_min": min(t["nmck"] for t in self.tenders),
            "nmck_max": max(t["nmck"] for t in self.tenders),
            "embeddings_provider": self.embedder.name,
            "llm_provider": self.assistant.llm.name,
            "chunks": len(self.retriever.chunks),
            "index_build_ms": self.index_build_ms,
        }


@lru_cache(maxsize=1)
def get_store() -> Store:
    return Store()
