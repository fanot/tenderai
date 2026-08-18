"""Устойчивость к формулировкам и производительность поиска."""
from __future__ import annotations

import time

import pytest

from app.rag import query_parser


def _top_categories(store, query: str, k: int = 5) -> list[str]:
    pq = query_parser.parse(query)
    return [h.tender["category"] for h in store.retriever.retrieve(pq, top_k=k)]


@pytest.mark.parametrize(
    "query,expected_category",
    [
        ("ноутбуки", "Поставка вычислительной техники"),
        ("ноутбуков", "Поставка вычислительной техники"),
        ("ноутбуками", "Поставка вычислительной техники"),
        ("капремонт зданий", "Строительство и ремонт"),
        ("лекарства", "Медицина и фармацевтика"),
    ],
)
def test_word_forms_are_normalized(store, query, expected_category):
    """Стемминг и символьные n-граммы должны сглаживать словоформы."""
    cats = _top_categories(store, query)
    assert cats.count(expected_category) >= 3, cats


def test_typo_tolerance(store):
    """Опечатка в одной букве не должна разрушать выдачу (вклад n-грамм)."""
    clean = {h.tender["id"] for h in store.retriever.retrieve(query_parser.parse("поставка ноутбуков"), top_k=10)}
    typo = {h.tender["id"] for h in store.retriever.retrieve(query_parser.parse("поставка ноутбков"), top_k=10)}
    assert len(clean & typo) >= 3, f"пересечение {len(clean & typo)} из 10"


def test_search_latency(store):
    queries = [
        "разработка информационной системы в Москве до 20 млн по 44-ФЗ",
        "капитальный ремонт здания школы",
        "поставка лекарственных препаратов",
        "уборка помещений для СМП",
        "видеонаблюдение на объектах",
    ]
    timings = []
    for q in queries * 4:
        t0 = time.perf_counter()
        store.retriever.retrieve(query_parser.parse(q), top_k=10)
        timings.append((time.perf_counter() - t0) * 1000)
    timings.sort()
    p95 = timings[int(len(timings) * 0.95) - 1]
    assert p95 < 500, f"p95={p95:.0f} мс"


def test_index_covers_whole_corpus(store):
    assert len(store.retriever.chunks) == len(store.tenders) * 3
    assert len(store.retriever.store) == len(store.retriever.chunks)


def test_no_duplicate_tenders_in_results(store):
    """Один тендер разбит на 3 чанка — в выдаче он должен появиться один раз."""
    hits = store.retriever.retrieve(query_parser.parse("поставка оборудования"), top_k=20)
    ids = [h.tender["id"] for h in hits]
    assert len(ids) == len(set(ids))


def test_embedding_provider_falls_back_without_key(monkeypatch):
    """Без API-ключа HTTP-провайдер обязан деградировать к локальному, а не падать."""
    from app.rag.embeddings import OpenAIEmbeddings, LocalHashingEmbeddings

    provider = OpenAIEmbeddings(api_key=None, dim=1536, fallback=LocalHashingEmbeddings())
    vecs = provider.embed(["тестовый текст закупки"])
    assert len(vecs) == 1 and len(vecs[0]) == 512


def test_llm_provider_falls_back_without_key(store):
    """Ассистент обязан ответить даже при недоступной LLM."""
    from app.rag.assistant import TenderAssistant
    from app.rag.llm import OpenAIChatLLM, LocalExtractiveLLM

    broken = OpenAIChatLLM(api_key=None, fallback=LocalExtractiveLLM())
    assistant = TenderAssistant(store.retriever, broken)
    result = assistant.ask("поставка ноутбуков")
    assert result.answer
    assert result.provider.startswith("local")
