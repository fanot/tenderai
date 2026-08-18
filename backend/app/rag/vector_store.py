"""Векторное хранилище в памяти (косинусная близость).

Для прототипа достаточно плотного поиска по 140–10 000 документам.
Интерфейс совместим с заменой на pgvector / Qdrant / FAISS без изменения кода выше.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path


@dataclass
class VectorStore:
    ids: list[str]
    vectors: list[list[float]]

    @classmethod
    def empty(cls) -> "VectorStore":
        return cls(ids=[], vectors=[])

    def add(self, ids: list[str], vectors: list[list[float]]) -> None:
        self.ids.extend(ids)
        self.vectors.extend(vectors)

    def search(self, query_vec: list[float], top_k: int = 50) -> list[tuple[str, float]]:
        if not self.vectors:
            return []
        qn = math.sqrt(sum(q * q for q in query_vec)) or 1.0
        scored: list[tuple[str, float]] = []
        for doc_id, vec in zip(self.ids, self.vectors):
            dot = sum(a * b for a, b in zip(query_vec, vec))
            vn = math.sqrt(sum(v * v for v in vec)) or 1.0
            scored.append((doc_id, dot / (qn * vn)))
        scored.sort(key=lambda kv: kv[1], reverse=True)
        return scored[:top_k]

    def save(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps({"ids": self.ids, "vectors": self.vectors}), encoding="utf-8"
        )

    @classmethod
    def load(cls, path: str | Path) -> "VectorStore":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(ids=data["ids"], vectors=data["vectors"])

    def __len__(self) -> int:
        return len(self.ids)
