"""``GET /api/v1/health``: servis ve veri tazeliği durumu."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from hava import __version__
from hava.db.models import SourceHealth
from hava.db.session import get_session

router = APIRouter()
ISTANBUL = ZoneInfo("Europe/Istanbul")
# Worker çökerse kendi kaydını bayat işaretleyemez; kalp atışının yaşına API bakar.
WORKER_STALE = timedelta(minutes=3)


def _stale(row: SourceHealth, now: datetime) -> bool:
    if row.source == "worker":
        return row.last_success_at is None or now - row.last_success_at > WORKER_STALE
    return row.stale


def _ts(value: datetime | None) -> dict[str, str] | None:
    if value is None:
        return None
    return {
        "utc": value.astimezone(UTC).isoformat(),
        "local": value.astimezone(ISTANBUL).isoformat(),
    }


@router.get("/health")
def health(response: Response, session: Annotated[Session, Depends(get_session)]) -> dict[str, Any]:
    now = datetime.now(UTC)
    body: dict[str, Any] = {
        "status": "ok",
        "version": __version__,
        "time": _ts(now),
        "database": {"ok": True},
        "sources": [],
    }
    try:
        session.execute(text("SELECT 1"))
        rows = session.execute(select(SourceHealth).order_by(SourceHealth.source)).scalars()
        body["sources"] = [
            {
                "source": r.source,
                "stale": _stale(r, now),
                "last_success_at": _ts(r.last_success_at),
                "last_error_at": _ts(r.last_error_at),
            }
            for r in rows
        ]
    except SQLAlchemyError as exc:
        body["status"] = "degraded"
        body["database"] = {"ok": False, "error": type(exc).__name__}
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return body
    if any(s["stale"] for s in body["sources"]):
        body["status"] = "degraded"
    return body
