"""
Слой эмбеддингов с несколькими провайдерами.

Провайдер выбирается через переменные окружения (см. core/config.py):
  EMBEDDINGS_PROVIDER = local | openai | yandex | gigachat

`local` работает офлайн, без ключей и без сети: хеширующий векторизатор
(hashing trick) над символьными n-граммами и стеммированными токенами
с последующей L2-нормализацией. Этого достаточно, чтобы прототип
демонстрировал семантическую близость словоформ и опечаток.
"""
from __future__ import annotations

import hashlib
import math
import os
from abc import ABC, abstractmethod

from .text import char_ngrams, tokenize


class EmbeddingProvider(ABC):
    name: str = "base"
    dim: int = 256

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]: ...

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


def _l2(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    return [v / norm for v in vec] if norm else vec


class LocalHashingEmbeddings(EmbeddingProvider):
    """Детерминированный офлайн-эмбеддер. Не требует ключей и сети."""

    name = "local"

    def __init__(self, dim: int = 512, ngram: int = 4) -> None:
        self.dim = dim
        self.ngram = ngram

    def _hash(self, feature: str) -> tuple[int, float]:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        h = int.from_bytes(digest, "big")
        return h % self.dim, 1.0 if (h >> 63) & 1 else -1.0

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * self.dim
            words = tokenize(text)
            for w in words:
                i, sign = self._hash(f"w:{w}")
                vec[i] += sign * 1.0
            for bigram in zip(words, words[1:]):
                i, sign = self._hash("b:" + "_".join(bigram))
                vec[i] += sign * 0.7
            for g in char_ngrams(text, self.ngram):
                i, sign = self._hash(f"c:{g}")
                vec[i] += sign * 0.35
            out.append(_l2(vec))
        return out


class _HTTPEmbeddings(EmbeddingProvider):
    """Общая логика HTTP-провайдеров с деградацией к локальному эмбеддеру."""

    endpoint: str = ""
    model: str = ""

    def __init__(self, api_key: str | None, dim: int, fallback: EmbeddingProvider) -> None:
        self.api_key = api_key
        self.dim = dim
        self.fallback = fallback

    def _payload(self, texts: list[str]) -> dict:
        return {"model": self.model, "input": texts}

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _parse(self, data: dict) -> list[list[float]]:
        return [item["embedding"] for item in data["data"]]

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not self.api_key:
            return self.fallback.embed(texts)
        try:
            import httpx

            resp = httpx.post(
                self.endpoint, json=self._payload(texts), headers=self._headers(), timeout=30.0
            )
            resp.raise_for_status()
            return [_l2(v) for v in self._parse(resp.json())]
        except Exception:  # noqa: BLE001 — прототип не должен падать из-за внешнего API
            return self.fallback.embed(texts)


class OpenAIEmbeddings(_HTTPEmbeddings):
    name = "openai"
    endpoint = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1") + "/embeddings"
    model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")


class YandexEmbeddings(_HTTPEmbeddings):
    name = "yandex"
    endpoint = "https://llm.api.cloud.yandex.net/foundationModels/v1/textEmbedding"
    model = "text-search-doc"

    def _payload(self, texts: list[str]) -> dict:
        folder = os.getenv("YANDEX_FOLDER_ID", "")
        return {"modelUri": f"emb://{folder}/{self.model}/latest", "text": texts[0]}

    def _headers(self) -> dict:
        return {"Authorization": f"Api-Key {self.api_key}", "Content-Type": "application/json"}

    def _parse(self, data: dict) -> list[list[float]]:
        return [data["embedding"]]


class GigaChatEmbeddings(_HTTPEmbeddings):
    name = "gigachat"
    endpoint = "https://gigachat.devices.sberbank.ru/api/v1/embeddings"
    model = "Embeddings"

    def _parse(self, data: dict) -> list[list[float]]:
        return [item["embedding"] for item in data["data"]]


def get_embedding_provider(provider: str | None = None) -> EmbeddingProvider:
    provider = (provider or os.getenv("EMBEDDINGS_PROVIDER", "local")).lower()
    local = LocalHashingEmbeddings()
    if provider == "openai":
        return OpenAIEmbeddings(os.getenv("OPENAI_API_KEY"), 1536, local)
    if provider == "yandex":
        return YandexEmbeddings(os.getenv("YANDEX_API_KEY"), 256, local)
    if provider == "gigachat":
        return GigaChatEmbeddings(os.getenv("GIGACHAT_API_KEY"), 1024, local)
    return local
