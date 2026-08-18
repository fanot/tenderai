"""Тесты RAG-ассистента: маршрутизация намерений, цитирование, guardrails."""
import pytest

from app.rag.assistant import TenderAssistant, detect_intent


@pytest.mark.parametrize(
    "query,intent",
    [
        ("какие требования к участникам", "requirements"),
        ("когда дедлайн подачи заявок", "deadline"),
        ("какая НМЦК по этим закупкам", "price"),
        ("сколько всего закупок по строительству", "analytics"),
        ("поставка молочной продукции", "search"),
    ],
)
def test_intent_routing(query, intent):
    assert detect_intent(query) == intent


def test_answer_cites_only_existing_sources(store):
    result = store.assistant.ask("требования при поставке медицинского оборудования")
    assert result.sources
    valid = {s.n for s in result.sources}
    import re

    cited = {int(m) for m in re.findall(r"\[(\d+)\]", result.answer)}
    assert cited
    assert cited <= valid
    assert result.warnings == []


def test_guardrail_detects_hallucinated_citation(store):
    """Ответ со ссылкой на несуществующий источник должен помечаться предупреждением."""
    result = store.assistant.ask("поставка ноутбуков")
    fake = result.answer + " Дополнительный вывод [999]."
    warnings = TenderAssistant.check_citations(fake, result.sources)
    assert warnings and "999" in warnings[0]


def test_guardrail_detects_missing_citations(store):
    result = store.assistant.ask("поставка ноутбуков")
    warnings = TenderAssistant.check_citations("Ответ без ссылок.", result.sources)
    assert warnings == ["Ответ не содержит ссылок на источники"]


def test_sources_are_traceable_to_real_tenders(store):
    result = store.assistant.ask("капитальный ремонт зданий в Москве")
    for s in result.sources:
        assert s.tender_id in store.by_id
        assert store.by_id[s.tender_id]["registry_number"] == s.registry_number


def test_no_results_answer_is_honest(store):
    """При отсутствии данных ассистент обязан сказать об этом, а не выдумать закупку."""
    result = store.assistant.ask("поставка космических аппаратов до 1000 рублей в Антарктиде")
    assert result.sources == [] or "не найдено" in result.answer.lower()
    if not result.sources:
        assert "не найдено" in result.answer.lower()


def test_answer_context_is_bounded(store):
    """Контекст не должен превышать бюджет по символам."""
    from app.rag.assistant import MAX_CONTEXT_CHARS

    hits = store.retriever.retrieve(__import__("app.rag.query_parser", fromlist=["parse"]).parse("закупка"), top_k=50)
    context, sources = TenderAssistant.build_context(hits)
    assert len(context) <= MAX_CONTEXT_CHARS + 1200
    assert len(sources) <= len(hits)


def test_filters_are_reported_to_user(store):
    result = store.assistant.ask("ИТ-закупки в Москве до 20 млн по 44-ФЗ")
    matched = result.filters["matched"]
    assert any("44-ФЗ" in m for m in matched)
    assert any("Москва" in m for m in matched)


def test_assistant_inherits_search_context(store):
    """Вопрос без предмета закупки должен опираться на текущий поисковый запрос."""
    plain = store.assistant.ask("какие требования к участникам")
    ctx = store.assistant.ask(
        "какие требования к участникам",
        context_query="капитальный ремонт здания от 10 млн до 100 млн",
    )
    assert any("Строительство" in m for m in ctx.filters["matched"])
    assert all(store.by_id[s.tender_id]["category"] == "Строительство и ремонт" for s in ctx.sources)
    assert {s.tender_id for s in ctx.sources} != {s.tender_id for s in plain.sources}


def test_context_does_not_override_explicit_query(store):
    """Явно названная в вопросе категория важнее контекста поисковой строки."""
    res = store.assistant.ask(
        "поставка лекарственных препаратов",
        context_query="капитальный ремонт здания",
    )
    assert any("Медицина" in m for m in res.filters["matched"])


def test_disclaimer_present(store):
    result = store.assistant.ask("поставка продуктов питания")
    assert "не являются юридической консультацией" in result.answer
