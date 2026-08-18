"""
Оценка качества поиска на размеченном наборе запросов.

Метрики:
  Recall@k — доля запросов, где эталонный документ попал в top-k
  MRR      — средний обратный ранг эталонного документа
  P@1      — точность на первой позиции

Эталонный набор строится детерминированно из корпуса: для случайных тендеров
формируется «пользовательский» перефразированный запрос (предмет + регион +
бюджетное ограничение), эталон — исходный тендер.
"""
from __future__ import annotations

import random

import pytest

from app.rag import query_parser

GOLD_SIZE = 60
SEED = 7


def _paraphrase(t: dict) -> str:
    """Имитация того, как пользователь сформулировал бы запрос по этой закупке."""
    words = t["subject"].split()
    core = " ".join(words[:8])
    tail = random.choice(
        [
            f" в регионе {t['region']}",
            f" {t['law']}",
            "",
            f" до {int(t['nmck'] * 1.5 // 1_000_000) + 1} млн",
        ]
    )
    return core + tail


@pytest.fixture(scope="module")
def gold(store):
    random.seed(SEED)
    sample = random.sample(store.tenders, GOLD_SIZE)
    return [(_paraphrase(t), t["id"]) for t in sample]


@pytest.fixture(scope="module")
def ranks(store, gold):
    out = []
    for query, gold_id in gold:
        pq = query_parser.parse(query)
        hits = store.retriever.retrieve(pq, top_k=20)
        ids = [h.tender["id"] for h in hits]
        out.append(ids.index(gold_id) + 1 if gold_id in ids else None)
    return out


def recall_at(ranks: list[int | None], k: int) -> float:
    return sum(1 for r in ranks if r is not None and r <= k) / len(ranks)


def mrr(ranks: list[int | None]) -> float:
    return sum(1 / r for r in ranks if r) / len(ranks)


def test_recall_at_1(ranks):
    assert recall_at(ranks, 1) >= 0.60, f"P@1={recall_at(ranks, 1):.2f}"


def test_recall_at_5(ranks):
    assert recall_at(ranks, 5) >= 0.90, f"Recall@5={recall_at(ranks, 5):.2f}"


def test_recall_at_10(ranks):
    assert recall_at(ranks, 10) >= 0.92, f"Recall@10={recall_at(ranks, 10):.2f}"


def test_mrr(ranks):
    assert mrr(ranks) >= 0.72, f"MRR={mrr(ranks):.3f}"


def test_hybrid_beats_lexical_only(store, gold):
    """Гибридный поиск не должен уступать чисто лексическому BM25."""
    hybrid, lexical = [], []
    for query, gold_id in gold:
        pq = query_parser.parse(query)
        ids = [h.tender["id"] for h in store.retriever.retrieve(pq, top_k=10)]
        hybrid.append(ids.index(gold_id) + 1 if gold_id in ids else None)

        lex_ids: list[str] = []
        for cid, _ in store.retriever.bm25.search(pq.text or pq.raw, top_k=200):
            tid = store.retriever.chunks[cid].tender_id
            if tid not in lex_ids and store.retriever.passes(tid and store.by_id[tid], pq):
                lex_ids.append(tid)
            if len(lex_ids) >= 10:
                break
        lexical.append(lex_ids.index(gold_id) + 1 if gold_id in lex_ids else None)

    assert mrr(hybrid) >= mrr(lexical) - 1e-9, f"hybrid={mrr(hybrid):.3f} lexical={mrr(lexical):.3f}"


def test_filters_are_strict(store):
    """Ни один результат не должен нарушать распознанные жёсткие фильтры."""
    pq = query_parser.parse("ремонт зданий в Москве до 30 млн по 44-ФЗ")
    for h in store.retriever.retrieve(pq, top_k=50):
        t = h.tender
        assert t["region"] == "г. Москва"
        assert t["law"] == "44-ФЗ"
        assert t["nmck"] <= 30_000_000


def test_registry_number_exact_lookup(store):
    """Точный поиск по реестровому номеру — классическая проверка лексической части."""
    target = store.tenders[10]
    pq = query_parser.parse(target["registry_number"])
    hits = store.retriever.retrieve(pq, top_k=3)
    assert hits and hits[0].tender["id"] == target["id"]
