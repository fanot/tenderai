"""Точка входа веб-сервиса TenderAI.

Запуск:  uvicorn app.main:app --reload --port 8000   (из каталога backend/)
Документация API:  http://localhost:8000/docs
Интерфейс:         http://localhost:8000/
Сайт стартапа:     http://localhost:8000/startup
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .api.routes import router
from .core.config import settings
from .core.store import get_store

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Прогрев индекса, чтобы первый запрос пользователя не ждал сборки."""
    get_store()
    yield


app = FastAPI(
    lifespan=lifespan,
    title=settings.app_name,
    version=settings.version,
    description=(
        "Прототип веб-сервиса умного поиска тендеров (44-ФЗ / 223-ФЗ) "
        "с RAG-ассистентом на базе гибридного поиска."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(settings.frontend_dir / "index.html")


@app.get("/startup", include_in_schema=False)
def startup_site() -> FileResponse:
    return FileResponse(settings.site_dir / "index.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> RedirectResponse:
    return RedirectResponse(url="/static/favicon.svg")


if settings.frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=settings.frontend_dir), name="static")
