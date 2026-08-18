"""Тесты работоспособности HTTP-API веб-сервиса."""
import pytest


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["tenders"] > 0
    assert body["chunks"] == body["tenders"] * 3


def test_meta_lists_are_not_empty(client):
    m = client.get("/api/meta").json()
    for field in ("categories", "regions", "laws", "statuses", "platforms"):
        assert m[field], f"пустой справочник: {field}"
    assert m["nmck_min"] <= m["nmck_max"]


def test_search_empty_query_returns_showcase(client):
    r = client.post("/api/search", json={"query": "", "page": 1, "page_size": 10})
    assert r.status_code == 200
    assert len(r.json()["results"]) == 10


def test_search_returns_relevant_category(client):
    r = client.post("/api/search", json={"query": "поставка ноутбуков", "page_size": 10})
    results = r.json()["results"]
    assert results
    top = results[:5]
    assert all(t["category"] == "Поставка вычислительной техники" for t in top)


def test_search_respects_explicit_filters(client):
    r = client.post(
        "/api/search",
        json={"query": "закупка", "filters": {"law": "44-ФЗ", "region": "г. Москва"}, "page_size": 20},
    )
    results = r.json()["results"]
    assert results
    assert all(t["law"] == "44-ФЗ" and t["region"] == "г. Москва" for t in results)


def test_ui_filters_override_parsed_filters(client):
    """Явно выбранный в интерфейсе закон важнее упомянутого в тексте запроса."""
    r = client.post(
        "/api/search",
        json={"query": "закупки по 44-ФЗ", "filters": {"law": "223-ФЗ"}, "page_size": 10},
    )
    results = r.json()["results"]
    assert results
    assert all(t["law"] == "223-ФЗ" for t in results)


def test_search_budget_filter(client):
    r = client.post("/api/search", json={"query": "ремонт до 5 млн", "page_size": 20})
    assert all(t["nmck"] <= 5_000_000 for t in r.json()["results"])


@pytest.mark.parametrize("sort,key,reverse", [
    ("nmck_desc", "nmck", True),
    ("nmck_asc", "nmck", False),
    ("deadline", "deadline_at", False),
])
def test_sorting(client, sort, key, reverse):
    rows = client.post("/api/search", json={"query": "", "sort": sort, "page_size": 20}).json()["results"]
    values = [r[key] for r in rows]
    assert values == sorted(values, reverse=reverse)


def test_pagination_does_not_overlap(client):
    p1 = client.post("/api/search", json={"query": "", "page": 1, "page_size": 5}).json()["results"]
    p2 = client.post("/api/search", json={"query": "", "page": 2, "page_size": 5}).json()["results"]
    assert {t["id"] for t in p1}.isdisjoint({t["id"] for t in p2})


def test_tender_detail_and_similar(client, store):
    tid = store.tenders[0]["id"]
    body = client.get(f"/api/tenders/{tid}").json()
    assert body["id"] == tid
    assert body["requirements"]
    assert all(s["id"] != tid for s in body["similar"])


def test_tender_not_found(client):
    assert client.get("/api/tenders/T-999999").status_code == 404


def test_assistant_answer_has_sources(client):
    r = client.post("/api/assistant/ask", json={"query": "какие требования при закупке медицинского оборудования"})
    assert r.status_code == 200
    body = r.json()
    assert body["sources"]
    assert body["intent"] == "requirements"
    assert not body["warnings"]


def test_assistant_rejects_empty_query(client):
    assert client.post("/api/assistant/ask", json={"query": "  "}).status_code == 422


def test_analytics_overview(client):
    d = client.get("/api/analytics/overview").json()
    assert d["total"] == sum(c["count"] for c in d["by_category"])
    assert d["total"] == sum(c["count"] for c in d["by_region"])
    assert d["total"] == sum(d["by_law"].values())
    assert 0 <= d["smp_share"] <= 100


def test_openapi_schema_available(client):
    assert client.get("/openapi.json").status_code == 200
