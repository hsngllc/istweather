"""Worker giriş noktası: ``python -m hava.scheduler``.

Faz 1'de yalnız kalp atışı işi var; gözlem (Faz 2) ve model (Faz 3) işleri buraya eklenecek.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime

import structlog
from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy.dialects.postgresql import insert

from hava.db.models import SourceHealth
from hava.db.session import session_scope
from hava.ops.logging import configure_logging

log = structlog.get_logger()


def heartbeat() -> None:
    """Worker'ın canlı olduğunu ``source_health`` tablosuna yazar."""
    now = datetime.now(UTC)
    stmt = insert(SourceHealth).values(
        source="worker", last_success_at=now, stale=False, updated_at=now
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[SourceHealth.source],
        set_={"last_success_at": now, "stale": False, "updated_at": now},
    )
    with session_scope() as session:
        session.execute(stmt)
        session.commit()
    log.info("heartbeat")


def main() -> int:
    configure_logging()
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        heartbeat,
        "interval",
        minutes=1,
        id="heartbeat",
        next_run_time=datetime.now(UTC),
        max_instances=1,
        coalesce=True,
    )
    log.info("worker_start", jobs=[j.id for j in scheduler.get_jobs()])
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("worker_stop")
    return 0


if __name__ == "__main__":
    sys.exit(main())
