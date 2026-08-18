"""
Адаптер источника данных: приведение выгрузки ЕИС (zakupki.gov.ru) к внутреннему формату.

Прототип работает на синтетическом корпусе (`tenders.json`), но интерфейс источника
вынесен отдельно, чтобы переход на реальные данные не затрагивал поиск и ассистента.

Способы получения данных из ЕИС (по состоянию на момент разработки прототипа):
  * витрина открытых данных ЕИС — выгрузки в XML по 44-ФЗ и 223-ФЗ;
  * FTP-архивы извещений, публикуемые по регионам и периодам;
  * коммерческие агрегаторы закупок с REST API.

Перед подключением проверьте актуальные условия использования и лимиты источника.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterable

REQUIRED_FIELDS = (
    "id", "registry_number", "subject", "description", "law", "procedure", "platform",
    "customer", "customer_inn", "region", "region_code", "category", "okpd2", "nmck",
    "currency", "application_security_pct", "contract_security_pct", "published_at",
    "deadline_at", "status", "smp_only", "requirements", "advantages", "url",
)


class TenderSource(ABC):
    """Интерфейс источника закупок."""

    @abstractmethod
    def fetch(self) -> list[dict]: ...


class JsonFileSource(TenderSource):
    """Источник по умолчанию: локальный JSON-файл."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def fetch(self) -> list[dict]:
        return json.loads(self.path.read_text(encoding="utf-8"))


class EISSource(TenderSource):
    """
    Заготовка коннектора к ЕИС.

    Реализация оставлена незаполненной осознанно: конкретный способ получения
    (XML-выгрузка, FTP-архив или API агрегатора) выбирается на этапе внедрения,
    а маппинг полей уже описан в `map_eis_notice`.
    """

    def __init__(self, raw_notices: Iterable[dict]) -> None:
        self.raw_notices = raw_notices

    def fetch(self) -> list[dict]:
        return [map_eis_notice(n) for n in self.raw_notices]


def map_eis_notice(notice: dict) -> dict:
    """
    Приведение извещения ЕИС к внутренней схеме.

    Ключи входного словаря соответствуют типовым названиям полей извещения;
    при подключении конкретной выгрузки достаточно скорректировать левую часть.
    """
    return {
        "id": notice.get("id") or f"EIS-{notice.get('purchaseNumber')}",
        "registry_number": notice.get("purchaseNumber", ""),
        "subject": notice.get("purchaseObjectInfo", ""),
        "description": notice.get("purchaseObjectInfo", ""),
        "law": "44-ФЗ" if notice.get("fz") == "44" else "223-ФЗ",
        "procedure": notice.get("placingWay", ""),
        "platform": notice.get("etp", {}).get("name", ""),
        "customer": notice.get("customer", {}).get("fullName", ""),
        "customer_inn": notice.get("customer", {}).get("inn", ""),
        "region": notice.get("customer", {}).get("region", ""),
        "region_code": notice.get("customer", {}).get("regionCode", ""),
        "category": notice.get("category", "Прочее"),
        "okpd2": notice.get("okpd2", ""),
        "nmck": float(notice.get("maxPrice") or 0),
        "currency": notice.get("currency", "RUB"),
        "application_security_pct": float(notice.get("applicationGuarantee") or 0),
        "contract_security_pct": float(notice.get("contractGuarantee") or 0),
        "published_at": (notice.get("publishDate") or "")[:10],
        "deadline_at": (notice.get("collectingEndDate") or "")[:10],
        "status": notice.get("stage", ""),
        "smp_only": bool(notice.get("smpOnly")),
        "requirements": notice.get("requirements", []),
        "advantages": notice.get("preferences", ""),
        "url": (
            "https://zakupki.gov.ru/epz/order/notice/view/common-info.html"
            f"?regNumber={notice.get('purchaseNumber', '')}"
        ),
    }


def validate(tenders: list[dict]) -> list[str]:
    """Проверка полноты записей — вызывается после любой загрузки данных."""
    problems: list[str] = []
    seen: set[str] = set()
    for i, t in enumerate(tenders):
        missing = [f for f in REQUIRED_FIELDS if f not in t]
        if missing:
            problems.append(f"запись #{i}: нет полей {missing}")
        tid = t.get("id")
        if tid in seen:
            problems.append(f"дублирующийся id: {tid}")
        seen.add(tid)
    return problems
