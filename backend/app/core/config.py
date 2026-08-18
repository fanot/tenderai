"""Конфигурация сервиса (12-factor: всё через переменные окружения)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]          # backend/app
PROJECT_DIR = BASE_DIR.parents[1]                        # корень репозитория


@dataclass(frozen=True)
class Settings:
    app_name: str = "TenderAI — умный поиск тендеров"
    version: str = "0.1.0-prototype"
    data_path: Path = BASE_DIR / "data" / "tenders.json"
    frontend_dir: Path = PROJECT_DIR / "frontend"
    site_dir: Path = PROJECT_DIR / "site"

    embeddings_provider: str = os.getenv("EMBEDDINGS_PROVIDER", "local")
    llm_provider: str = os.getenv("LLM_PROVIDER", "local")
    default_top_k: int = int(os.getenv("DEFAULT_TOP_K", "10"))
    cors_origins: str = os.getenv("CORS_ORIGINS", "*")


settings = Settings()
