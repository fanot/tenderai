"""
RAG-ассистент: понимание запроса -> поиск -> сборка контекста -> ответ с цитированием.

Конвейер:
  1. query_parser  — извлекает структурные фильтры (закон, регион, НМЦК, СМП…)
  2. HybridRetriever — BM25 + плотные векторы, RRF-слияние, фильтрация, реранк
  3. build_context  — нумерованные фрагменты источников с обрезкой по бюджету токенов
  4. LLM или экстрактивный генератор — ответ со ссылками [n]
  5. guardrails — проверка, что все ссылки [n] существуют
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from . import query_parser
from .chunking import money_ru
from .llm import SYSTEM_PROMPT, LLMProvider, LocalExtractiveLLM, get_llm_provider
from .retriever import HybridRetriever, Hit

MAX_CONTEXT_CHARS = 6000


@dataclass
class Source:
    n: int
    tender_id: str
    registry_number: str
    title: str
    section: str
    snippet: str
    url: str


@dataclass
class AssistantAnswer:
    answer: str
    sources: list[Source]
    filters: dict
    hits: list[Hit] = field(default_factory=list)
    provider: str = "local"
    intent: str = "search"
    warnings: list[str] = field(default_factory=list)


INTENT_PATTERNS = [
    ("requirements", r"требован|документ|лиценз|сро|допуск|что нужно|условия участ"),
    ("deadline", r"дедлайн|срок|когда|до какого|успе"),
    ("price", r"нмцк|цена|стоимост|бюджет|сколько сто|демпинг"),
    ("analytics", r"сколько всего|статистик|аналитик|распредел|топ |средн"),
    ("search", r".*"),
]


def detect_intent(query: str) -> str:
    q = query.lower()
    for intent, pattern in INTENT_PATTERNS:
        if re.search(pattern, q):
            return intent
    return "search"


class TenderAssistant:
    def __init__(self, retriever: HybridRetriever, llm: LLMProvider | None = None) -> None:
        self.retriever = retriever
        self.llm = llm or get_llm_provider()

    # ---------- контекст ----------
    @staticmethod
    def build_context(hits: list[Hit]) -> tuple[str, list[Source]]:
        sources: list[Source] = []
        parts: list[str] = []
        used = 0
        for i, hit in enumerate(hits, start=1):
            t = hit.tender
            chunk = hit.best_chunk
            body = chunk.text if chunk else t["description"]
            body = body[:900]
            block = (
                f"[{i}] {t['subject']}\n"
                f"    Реестровый №{t['registry_number']} | {t['law']} | {t['region']} | "
                f"НМЦК {money_ru(t['nmck'])} ₽ | заявки до {t['deadline_at']} | {t['status']}\n"
                f"    Заказчик: {t['customer']}\n"
                f"    Раздел «{chunk.section if chunk else 'Описание'}»: {body}\n"
            )
            if used + len(block) > MAX_CONTEXT_CHARS:
                break
            used += len(block)
            parts.append(block)
            sources.append(
                Source(
                    n=i,
                    tender_id=t["id"],
                    registry_number=t["registry_number"],
                    title=t["subject"],
                    section=chunk.section if chunk else "Описание",
                    snippet=body[:300],
                    url=t["url"],
                )
            )
        return "\n".join(parts), sources

    # ---------- экстрактивный генератор (офлайн) ----------
    @staticmethod
    def _extractive(query: str, intent: str, pq, hits: list[Hit]) -> str:
        if not hits:
            return (
                "По заданным условиям подходящих закупок не найдено. "
                "Попробуйте расширить бюджетный диапазон, убрать фильтр по региону "
                "или сформулировать предмет закупки короче."
            )
        today = date.today()
        head_filters = ", ".join(pq.matched) if pq.matched else "без дополнительных фильтров"
        lines = [f"Нашёл {len(hits)} подходящих закупок ({head_filters}).", ""]

        if intent == "requirements":
            lines.append("Ключевые требования к участникам по найденным закупкам:")
            for i, h in enumerate(hits[:5], 1):
                reqs = "; ".join(h.tender["requirements"][:3])
                lines.append(f"• {h.tender['subject']} — {reqs} [{i}]")
            lines.append("")
            lines.append(
                "Общее для всех закупок: отсутствие в РНП, отсутствие налоговой задолженности, "
                "соответствие ст. 31 44-ФЗ."
            )
        elif intent == "deadline":
            lines.append("Ближайшие сроки подачи заявок:")
            ordered = sorted(hits, key=lambda h: h.tender["deadline_at"])
            for i, h in enumerate(ordered[:5], 1):
                left = (date.fromisoformat(h.tender["deadline_at"]) - today).days
                mark = f"осталось {left} дн." if left >= 0 else "приём завершён"
                n = hits.index(h) + 1
                lines.append(f"• до {h.tender['deadline_at']} ({mark}) — {h.tender['subject']} [{n}]")
        elif intent == "price":
            values = [h.tender["nmck"] for h in hits]
            avg = sum(values) / len(values)
            lines.append(
                f"Диапазон НМЦК: от {money_ru(min(values))} ₽ до {money_ru(max(values))} ₽, "
                f"среднее — {money_ru(avg)} ₽."
            )
            lines.append("")
            for i, h in enumerate(sorted(hits, key=lambda x: -x.tender["nmck"])[:5], 1):
                n = hits.index(h) + 1
                lines.append(f"• {money_ru(h.tender['nmck'])} ₽ — {h.tender['subject']} [{n}]")
        elif intent == "analytics":
            by_cat: dict[str, int] = {}
            by_region: dict[str, int] = {}
            for h in hits:
                by_cat[h.tender["category"]] = by_cat.get(h.tender["category"], 0) + 1
                by_region[h.tender["region"]] = by_region.get(h.tender["region"], 0) + 1
            total = sum(h.tender["nmck"] for h in hits)
            lines.append(f"Суммарная НМЦК по выборке: {money_ru(total)} ₽.")
            top_cat = sorted(by_cat.items(), key=lambda kv: -kv[1])[:3]
            top_reg = sorted(by_region.items(), key=lambda kv: -kv[1])[:3]
            lines.append("Категории: " + ", ".join(f"{k} — {v}" for k, v in top_cat) + ".")
            lines.append("Регионы: " + ", ".join(f"{k} — {v}" for k, v in top_reg) + ".")
            lines.append("")
            for i, h in enumerate(hits[:3], 1):
                lines.append(f"• {h.tender['subject']} [{i}]")
        else:
            lines.append("Наиболее релевантные позиции:")
            for i, h in enumerate(hits[:5], 1):
                t = h.tender
                left = (date.fromisoformat(t["deadline_at"]) - today).days
                tail = f"заявки до {t['deadline_at']}" + (f" (осталось {left} дн.)" if left >= 0 else "")
                why = ", ".join(h.explain) if h.explain else "совпадение по тексту закупки"
                lines.append(
                    f"{i}. {t['subject']} — {t['customer']}, {t['region']}. "
                    f"НМЦК {money_ru(t['nmck'])} ₽, {t['law']}, {tail}. Почему в подборке: {why}. [{i}]"
                )

        lines.append("")
        lines.append(
            "Проверьте документацию на площадке перед подачей заявки: сведения приведены "
            "по данным карточек закупок и не являются юридической консультацией."
        )
        return "\n".join(lines)

    # ---------- guardrails ----------
    @staticmethod
    def check_citations(answer: str, sources: list[Source]) -> list[str]:
        warnings: list[str] = []
        valid = {s.n for s in sources}
        cited = {int(m) for m in re.findall(r"\[(\d+)\]", answer)}
        bogus = cited - valid
        if bogus:
            warnings.append(f"Ответ ссылается на несуществующие источники: {sorted(bogus)}")
        if sources and not cited:
            warnings.append("Ответ не содержит ссылок на источники")
        return warnings

    # ---------- основной вход ----------
    @staticmethod
    def _inherit_context(pq, context_query: str | None):
        """
        Вопросы вроде «какие требования к участникам?» не содержат предмета закупки.
        В этом случае ассистент опирается на текущий поисковый запрос пользователя:
        наследует его фильтры и добавляет его текст к поисковой строке.
        """
        if not context_query or not context_query.strip():
            return pq
        ctx = query_parser.parse(context_query)
        for field in ("law", "region", "category", "nmck_min", "nmck_max", "smp_only"):
            if getattr(pq, field) is None:
                setattr(pq, field, getattr(ctx, field))
        if not pq.only_active:
            pq.only_active = ctx.only_active
        for tag in ctx.matched:
            if tag not in pq.matched:
                pq.matched.append(tag)
        if len(pq.text.split()) < 2 and ctx.text:
            pq.text = f"{ctx.text} {pq.text}".strip()
        return pq

    def ask(self, query: str, top_k: int = 8, context_query: str | None = None) -> AssistantAnswer:
        pq = self._inherit_context(query_parser.parse(query), context_query)
        intent = detect_intent(query)
        hits = self.retriever.retrieve(pq, top_k=top_k)
        context, sources = self.build_context(hits)

        provider = self.llm.name
        if isinstance(self.llm, LocalExtractiveLLM):
            answer = self._extractive(query, intent, pq, hits)
        else:
            user = (
                f"ВОПРОС ПОЛЬЗОВАТЕЛЯ: {query}\n\n"
                f"РАСПОЗНАННЫЕ ФИЛЬТРЫ: {', '.join(pq.matched) or 'нет'}\n\n"
                f"КОНТЕКСТ (найденные закупки):\n{context}\n\n"
                "Дай ответ по инструкции, со ссылками [n]."
            )
            try:
                answer = self.llm.generate(SYSTEM_PROMPT, user)
            except Exception:  # noqa: BLE001 — деградируем к офлайн-режиму
                answer = self._extractive(query, intent, pq, hits)
                provider = "local (fallback)"

        return AssistantAnswer(
            answer=answer,
            sources=sources,
            filters=pq.to_dict(),
            hits=hits,
            provider=provider,
            intent=intent,
            warnings=self.check_citations(answer, sources),
        )
