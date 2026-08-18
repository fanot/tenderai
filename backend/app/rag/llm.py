"""
Слой генерации ответов (LLM) с несколькими провайдерами и офлайн-фолбэком.

LLM_PROVIDER = local | openai | yandex | gigachat

`local` — экстрактивный генератор: собирает ответ из найденных фрагментов по
шаблонам. Он не «выдумывает» фактов вообще (каждое утверждение взято из
контекста), поэтому прототип пригоден для демонстрации без ключей и
одновременно служит нижней границей качества при сравнении с LLM.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod

SYSTEM_PROMPT = (
    "Ты — ассистент по государственным и корпоративным закупкам РФ (44-ФЗ и 223-ФЗ). "
    "Отвечай кратко, по-деловому, на русском языке. Используй ТОЛЬКО факты из блока "
    "КОНТЕКСТ. Если данных недостаточно — прямо скажи об этом и предложи уточнить запрос. "
    "После каждого утверждения ставь ссылку на источник в формате [n], где n — номер "
    "фрагмента из контекста. Не давай юридических гарантий и не выдумывай реестровые номера."
)


class LLMProvider(ABC):
    name = "base"

    @abstractmethod
    def generate(self, system: str, user: str) -> str: ...


class LocalExtractiveLLM(LLMProvider):
    """Офлайн-генератор. Ответ строится вызывающим кодом; здесь — passthrough."""

    name = "local"

    def generate(self, system: str, user: str) -> str:  # pragma: no cover - не используется
        return user


class _HTTPChatLLM(LLMProvider):
    endpoint = ""
    model = ""

    def __init__(self, api_key: str | None, fallback: LLMProvider) -> None:
        self.api_key = api_key
        self.fallback = fallback

    def _payload(self, system: str, user: str) -> dict:
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
        }

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _parse(self, data: dict) -> str:
        return data["choices"][0]["message"]["content"]

    def generate(self, system: str, user: str) -> str:
        if not self.api_key:
            raise RuntimeError("no api key")
        import httpx

        resp = httpx.post(
            self.endpoint, json=self._payload(system, user), headers=self._headers(), timeout=60.0
        )
        resp.raise_for_status()
        return self._parse(resp.json())


class OpenAIChatLLM(_HTTPChatLLM):
    name = "openai"
    endpoint = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1") + "/chat/completions"
    model = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")


class YandexGPT(_HTTPChatLLM):
    name = "yandex"
    endpoint = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    model = "yandexgpt"

    def _payload(self, system: str, user: str) -> dict:
        folder = os.getenv("YANDEX_FOLDER_ID", "")
        return {
            "modelUri": f"gpt://{folder}/{self.model}/latest",
            "completionOptions": {"temperature": 0.2, "maxTokens": 1200},
            "messages": [
                {"role": "system", "text": system},
                {"role": "user", "text": user},
            ],
        }

    def _headers(self) -> dict:
        return {"Authorization": f"Api-Key {self.api_key}", "Content-Type": "application/json"}

    def _parse(self, data: dict) -> str:
        return data["result"]["alternatives"][0]["message"]["text"]


class GigaChat(_HTTPChatLLM):
    name = "gigachat"
    endpoint = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
    model = "GigaChat"


def get_llm_provider(provider: str | None = None) -> LLMProvider:
    provider = (provider or os.getenv("LLM_PROVIDER", "local")).lower()
    local = LocalExtractiveLLM()
    if provider == "openai":
        return OpenAIChatLLM(os.getenv("OPENAI_API_KEY"), local)
    if provider == "yandex":
        return YandexGPT(os.getenv("YANDEX_API_KEY"), local)
    if provider == "gigachat":
        return GigaChat(os.getenv("GIGACHAT_API_KEY"), local)
    return local
