"""FastAPI uygulama fabrikası. API hesap yapmaz; worker'ın yazdığı tabloları okur (spec §4)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from hava import __version__
from hava.api import health
from hava.ops.logging import configure_logging
from hava.settings import get_settings


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()
    app = FastAPI(
        title="İstanbul Hava API",
        version=__version__,
        description=(
            "İstanbul ilçeleri için çok modelli hava tahmini. Tahminler otomatik üretilir, "
            "resmi tahmin yerine geçmez."
        ),
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    app.include_router(health.router, prefix="/api/v1", tags=["health"])
    return app


app = create_app()
