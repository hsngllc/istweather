"""``model_runs`` durum makinesi (spec §4): pending → downloading → extracted → loaded | failed.

Çalıştırma yeniden işlenebilir (idempotent); ``failed`` olan, deneme sınırına kadar tekrar denenir.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from hava.db.models import Model, ModelRun

MAX_ATTEMPTS = 3


def model_id(session: Session, code: str) -> int:
    return session.execute(select(Model.id).where(Model.code == code)).scalar_one()


def get_run(session: Session, mid: int, init_time: datetime) -> ModelRun | None:
    return session.get(ModelRun, (mid, init_time))


def should_process(run: ModelRun | None) -> bool:
    if run is None:
        return True
    if run.status == "loaded":
        return False
    return int((run.files or {}).get("attempts", 0)) < MAX_ATTEMPTS


def set_status(
    session: Session,
    mid: int,
    init_time: datetime,
    status: str,
    files: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    """Durumu yazar; ``files`` mevcut sözlüğe eklenir."""
    now = datetime.now(UTC)
    run = get_run(session, mid, init_time)
    if run is None:
        session.execute(
            insert(ModelRun).values(
                model_id=mid, init_time=init_time, status=status, files=files or {}, error=error
            )
        )
        return
    run.status = status
    run.files = {**(run.files or {}), **(files or {})}
    run.error = error
    if status in ("loaded", "failed"):
        run.completed_at = now
