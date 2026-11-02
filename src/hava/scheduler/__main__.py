"""Worker giriş noktası: ``python -m hava.scheduler``.

İşler: kalp atışı (1 dk), canlı METAR (5 dk), kaynak tazeliği (5 dk), IEM boşluk doldurma (günlük).
Model işleri (Faz 3) buraya eklenecek. Bir iş üst üste ``FAILURE_THRESHOLD`` kez hata verirse
bildirim gider; düzelince tekrar bildirilir (spec §14).
"""

from __future__ import annotations

import sys
from collections import defaultdict
from datetime import UTC, datetime

import structlog
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, JobExecutionEvent
from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy.dialects.postgresql import insert

from hava.db.models import SourceHealth
from hava.db.session import session_scope
from hava.ingest.obs.iem import fill_recent
from hava.ingest.obs.jobs import collect_metar
from hava.ops.health import check_sources
from hava.ops.logging import configure_logging
from hava.ops.notify import notify

log = structlog.get_logger()
FAILURE_THRESHOLD = 3


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


class FailureWatch:
    """Üst üste hata veren işleri bildirir."""

    def __init__(self, threshold: int = FAILURE_THRESHOLD) -> None:
        self.threshold = threshold
        self.failures: dict[str, int] = defaultdict(int)

    def __call__(self, event: JobExecutionEvent) -> None:
        job = event.job_id
        if event.exception is not None:
            self.failures[job] += 1
            error = f"{type(event.exception).__name__}: {event.exception}"[:300]
            log.error("job_failed", job=job, consecutive=self.failures[job], error=error)
            if self.failures[job] == self.threshold:
                notify(
                    f"İş tekrar tekrar hata veriyor: {job}",
                    f"{self.threshold} kez üst üste. Son hata: {error}",
                )
            return
        if self.failures[job] >= self.threshold:
            notify(f"İş düzeldi: {job}", f"{self.failures[job]} hatadan sonra başarılı çalıştı.")
        self.failures[job] = 0


def build_scheduler() -> BlockingScheduler:
    scheduler = BlockingScheduler(timezone="UTC")
    now = datetime.now(UTC)
    common = {"max_instances": 1, "coalesce": True, "misfire_grace_time": 120}
    scheduler.add_job(heartbeat, "interval", minutes=1, id="heartbeat", next_run_time=now, **common)
    scheduler.add_job(
        collect_metar, "cron", minute="*/5", id="collect_metar", next_run_time=now, **common
    )
    scheduler.add_job(check_sources, "cron", minute="2-59/5", id="check_sources", **common)
    scheduler.add_job(fill_recent, "cron", hour=3, minute=15, id="iem_fill_recent", **common)
    scheduler.add_listener(FailureWatch(), EVENT_JOB_ERROR | EVENT_JOB_EXECUTED)
    return scheduler


def main() -> int:
    configure_logging()
    scheduler = build_scheduler()
    log.info("worker_start", jobs=[j.id for j in scheduler.get_jobs()])
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("worker_stop")
    return 0


if __name__ == "__main__":
    sys.exit(main())
