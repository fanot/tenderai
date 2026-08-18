"""
Гибридный ретривер: BM25 (лексика) + плотные векторы (семантика),
слияние через Reciprocal Rank Fusion, затем структурные фильтры и
лёгкий реранк по бизнес-признакам (свежесть, статус, совпадение фильтров).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .bm25 import BM25Index
from .chunking import Chunk, tender_to_chunks
from .embeddings import EmbeddingProvider, get_embedding_provider
from .query_parser import ParsedQuery
from .vector_store import VectorStore

# Параметры ранжирования.
# RRF_K мал специально: при большом K оценки RRF почти не различаются между
# соседними позициями, и любой бизнес-буст начинает перевешивать релевантность.
RRF_K = 10
# Вес семантической ветви относительно лексической. Локальный хеширующий
# эмбеддер шумнее BM25, поэтому его вклад меньше единицы.
SEMANTIC_WEIGHT = 0.5
# Максимальная надбавка за бизнес-признаки (свежесть, статус, совпадение фильтров).
# Ограничена так, чтобы не переставлять документы с разной релевантностью.
BUSINESS_WEIGHT = 0.20


@dataclass
class Hit:
    tender: dict
    score: float
    lexical_rank: int | None
    semantic_rank: int | None
    best_chunk: Chunk | None
    explain: list[str]


class HybridRetriever:
    def __init__(self, tenders: list[dict], embedder: EmbeddingProvider | None = None) -> None:
        self.tenders = {t["id"]: t for t in tenders}
        self.embedder = embedder or get_embedding_provider()
        self.chunks: dict[str, Chunk] = {}
        for t in tenders:
            for ch in tender_to_chunks(t):
                self.chunks[ch.chunk_id] = ch

        self.bm25 = BM25Index().build([(c.chunk_id, c.text) for c in self.chunks.values()])
        self.store = VectorStore.empty()
        ids = list(self.chunks)
        vectors = self.embedder.embed([self.chunks[i].text for i in ids])
        self.store.add(ids, vectors)

    # ---------- фильтры ----------
    @staticmethod
    def passes(t: dict, pq: ParsedQuery, today: date | None = None) -> bool:
        today = today or date.today()
        if pq.law and t["law"] != pq.law:
            return False
        if pq.region and t["region"] != pq.region:
            return False
        if pq.category and t["category"] != pq.category:
            return False
        if pq.nmck_min is not None and t["nmck"] < pq.nmck_min:
            return False
        if pq.nmck_max is not None and t["nmck"] > pq.nmck_max:
            return False
        if pq.smp_only and not t["smp_only"]:
            return False
        if pq.only_active and t["status"] != "Подача заявок":
            return False
        return True

    # ---------- поиск ----------
    def retrieve(self, pq: ParsedQuery, top_k: int = 10, candidates: int | None = None) -> list[Hit]:
        query = pq.text or pq.raw
        # Пул кандидатов по умолчанию — весь индекс: жёсткие фильтры применяются
        # после ранжирования, поэтому узкая выборка не должна отсекаться раньше времени.
        candidates = candidates or len(self.chunks)

        lex = self.bm25.search(query, top_k=candidates)
        sem = self.store.search(self.embedder.embed_one(query), top_k=candidates) if query else []

        lex_rank = {cid: i + 1 for i, (cid, _) in enumerate(lex)}
        sem_rank = {cid: i + 1 for i, (cid, _) in enumerate(sem)}

        fused: dict[str, float] = {}
        for cid, r in lex_rank.items():
            fused[cid] = fused.get(cid, 0.0) + 1.0 / (RRF_K + r)
        for cid, r in sem_rank.items():
            fused[cid] = fused.get(cid, 0.0) + SEMANTIC_WEIGHT / (RRF_K + r)

        # чанки -> тендеры (берём лучший чанк)
        by_tender: dict[str, tuple[float, str]] = {}
        for cid, score in fused.items():
            tid = self.chunks[cid].tender_id
            if tid not in by_tender or score > by_tender[tid][0]:
                by_tender[tid] = (score, cid)

        # Пустой запрос — работаем как «витрина»: ранжируем весь корпус по бизнес-признакам.
        if not query:
            by_tender = {tid: (1.0, f"{tid}#0") for tid in self.tenders}

        today = date.today()
        hits: list[Hit] = []
        for tid, (score, cid) in by_tender.items():
            t = self.tenders[tid]
            if not self.passes(t, pq, today):
                continue
            explain: list[str] = []
            # Бизнес-признаки нормированы в [0, 1] и влияют на итог не более чем
            # на BUSINESS_WEIGHT — релевантность остаётся определяющей.
            business = 0.0
            if t["status"] == "Подача заявок":
                business += 0.45
                explain.append("приём заявок открыт")
            days_left = (date.fromisoformat(t["deadline_at"]) - today).days
            if 0 <= days_left <= 7:
                business += 0.15
                explain.append(f"дедлайн через {days_left} дн.")
            age = (today - date.fromisoformat(t["published_at"])).days
            business += 0.20 * max(0.0, 1 - age / 60)
            if pq.category and t["category"] == pq.category:
                business += 0.13
                explain.append("совпадение по категории")
            if pq.region and t["region"] == pq.region:
                business += 0.07
                explain.append("совпадение по региону")

            hits.append(
                Hit(
                    tender=t,
                    score=round(score * (1 + BUSINESS_WEIGHT * min(business, 1.0)), 6),
                    lexical_rank=lex_rank.get(cid),
                    semantic_rank=sem_rank.get(cid),
                    best_chunk=self.chunks[cid],
                    explain=explain,
                )
            )

        hits.sort(key=lambda h: (h.score, -date.fromisoformat(h.tender["deadline_at"]).toordinal()), reverse=True)
        return hits[:top_k]
