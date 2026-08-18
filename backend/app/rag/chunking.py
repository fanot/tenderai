"""Разбиение карточки тендера на чанки для индексации."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    tender_id: str
    section: str
    text: str


def money_ru(value: float) -> str:
    return f"{value:,.2f}".replace(",", " ").replace(".", ",")


def tender_to_chunks(t: dict) -> list[Chunk]:
    """3 чанка на тендер: карточка, условия, требования.

    Разделение по смысловым секциям даёт более точное цитирование в ответе
    ассистента, чем нарезка по фиксированному числу символов.
    """
    tid = t["id"]
    head = (
        f"{t['subject']}. Заказчик: {t['customer']} (ИНН {t['customer_inn']}). "
        f"Регион: {t['region']}. Категория: {t['category']}, ОКПД2 {t['okpd2']}. "
        f"Закон: {t['law']}. Способ: {t['procedure']}. Площадка: {t['platform']}. "
        f"Реестровый номер {t['registry_number']}."
    )
    terms = (
        f"НМЦК: {money_ru(t['nmck'])} руб. "
        f"Обеспечение заявки: {t['application_security_pct']}%, "
        f"обеспечение исполнения контракта: {t['contract_security_pct']}%. "
        f"Опубликовано: {t['published_at']}. Приём заявок до: {t['deadline_at']}. "
        f"Статус: {t['status']}. "
        + ("Закупка только для СМП и СОНКО. " if t["smp_only"] else "")
        + (t["advantages"] or "")
    )
    reqs = "Требования к участникам: " + " ".join(t["requirements"]) + " " + t["description"]

    return [
        Chunk(f"{tid}#0", tid, "Карточка закупки", head),
        Chunk(f"{tid}#1", tid, "Условия и сроки", terms),
        Chunk(f"{tid}#2", tid, "Требования и описание", reqs),
    ]
