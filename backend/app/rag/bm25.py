"""Лексический поиск BM25 (Okapi) — реализация без внешних зависимостей."""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .text import tokenize


@dataclass
class BM25Index:
    k1: float = 1.5
    b: float = 0.75

    doc_ids: list[str] = field(default_factory=list)
    doc_len: list[int] = field(default_factory=list)
    postings: dict[str, list[tuple[int, int]]] = field(default_factory=lambda: defaultdict(list))
    avgdl: float = 0.0
    n_docs: int = 0

    def build(self, docs: list[tuple[str, str]]) -> "BM25Index":
        """docs: список (doc_id, text)."""
        self.doc_ids, self.doc_len = [], []
        self.postings = defaultdict(list)
        for idx, (doc_id, text) in enumerate(docs):
            tokens = tokenize(text)
            self.doc_ids.append(doc_id)
            self.doc_len.append(len(tokens))
            for term, tf in Counter(tokens).items():
                self.postings[term].append((idx, tf))
        self.n_docs = len(self.doc_ids)
        self.avgdl = (sum(self.doc_len) / self.n_docs) if self.n_docs else 0.0
        return self

    def _idf(self, term: str) -> float:
        df = len(self.postings.get(term, ()))
        if df == 0:
            return 0.0
        return math.log(1 + (self.n_docs - df + 0.5) / (df + 0.5))

    # ---------- исправление опечаток ----------
    @staticmethod
    def _edit_distance_le1(a: str, b: str) -> bool:
        """Расстояние Дамерау—Левенштейна <= 1 (быстрая проверка без матрицы)."""
        if a == b:
            return True
        la, lb = len(a), len(b)
        if abs(la - lb) > 1:
            return False
        if la == lb:  # замена одного символа или перестановка соседних
            diff = [i for i in range(la) if a[i] != b[i]]
            if len(diff) == 1:
                return True
            if len(diff) == 2 and diff[1] == diff[0] + 1:
                i, j = diff
                return a[i] == b[j] and a[j] == b[i]
            return False
        # вставка/удаление одного символа
        short, long = (a, b) if la < lb else (b, a)
        i = j = 0
        skipped = False
        while i < len(short) and j < len(long):
            if short[i] == long[j]:
                i += 1
                j += 1
            elif skipped:
                return False
            else:
                skipped = True
                j += 1
        return True

    def fuzzy_variants(self, term: str, max_variants: int = 3) -> list[str]:
        """Термины словаря, отличающиеся от запроса не более чем на одну правку."""
        if term in self.postings or len(term) < 5:
            return []
        prefix = term[:3]
        out = [
            t
            for t in self.postings
            if t[:3] == prefix and abs(len(t) - len(term)) <= 1 and self._edit_distance_le1(t, term)
        ]
        out.sort(key=lambda t: -len(self.postings[t]))
        return out[:max_variants]

    def search(self, query: str, top_k: int = 50, fuzzy: bool = True) -> list[tuple[str, float]]:
        q_terms = tokenize(query)
        if not q_terms or self.n_docs == 0:
            return []

        # (термин, вес): опечатанные термины подменяются близкими из словаря
        weighted: list[tuple[str, float, int]] = []
        for term, q_tf in Counter(q_terms).items():
            if term in self.postings:
                weighted.append((term, 1.0, q_tf))
            elif fuzzy:
                for variant in self.fuzzy_variants(term):
                    weighted.append((variant, 0.7, q_tf))

        scores: dict[int, float] = defaultdict(float)
        for term, weight, q_tf in weighted:
            idf = self._idf(term)
            if idf == 0.0:
                continue
            for idx, tf in self.postings[term]:
                dl = self.doc_len[idx] or 1
                denom = tf + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1))
                scores[idx] += weight * idf * (tf * (self.k1 + 1)) / denom * min(q_tf, 3)
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
        return [(self.doc_ids[i], s) for i, s in ranked]
