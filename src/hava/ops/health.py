"""Kaynak sağlığı (``source_health``) ve tazelik denetimi (spec §14).

Kaynak adları:
- ``metar_awc``: AWC toplayıcısı; ``last_success_at`` son başarılı istek. Bayat: belirli süredir
  başarılı yanıt yok.
- ``metar:<ICAO>``: istasyonun veri tazeliği; ``last_success_at`` son gözlemin zamanı. Bayat: son
  gözlem eşikten eski (kaynak hangisi olursa olsun).
- ``metar_iem``: günlük IEM boşluk doldurma işi.
- ``model:<kod>``: modelin veri tazeliği; ``last_success_at`` son yüklenen çalıştırmanın başlangıç
  zamanı. Bayat: ``models.meta.stale_hours``'tan eski (yalnız bu anahtarı olan modeller izlenir).
- ``collector:<kod>``: model toplayıcısının son başarılı/başarısız denemesi.
- ``worker``: kalp atışı.

Bayatlık durumu değiştiğinde (bozuldu / düzeldi) bildirim gider; durum sürdükçe tekrar gönderilmez.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from hava.db.models import Model, ModelRun, Observation, SourceHealth, Station
from hava.db.session import session_scope
from hava.ops.notify import notify
from hava.settings import Settings, get_settings

log = structlog.get_logger()
ISTANBUL = ZoneInfo("Europe/Istanbul")


@dataclass(frozen=True)
class Transition:
    source: str
    stale: bool
    detail: str


def _upsert(session: Session, source: str, **values: object) -> None:
    stmt = insert(SourceHealth).values(source=source, **values)
    session.execute(stmt.on_conflict_do_update(index_elements=[SourceHealth.source], set_=values))


def record_success(session: Session, source: str, at: datetime) -> None:
    _upsert(session, source, last_success_at=at, updated_at=at)


def record_error(session: Session, source: str, at: datetime, error: BaseException | str) -> None:
    text = error if isinstance(error, str) else f"{type(error).__name__}: {error}"
    _upsert(session, source, last_error_at=at, last_error=text[:500], updated_at=at)


def _set_stale(session: Session, source: str, stale: bool, now: datetime) -> bool:
    """Bayatlık durumunu yazar; durum değiştiyse True."""
    prev = session.get(SourceHealth, source)
    if prev is None:
        _upsert(session, source, stale=stale, updated_at=now)
        return stale  # ilk kayıtta yalnız bozuk durum bildirilir
    if prev.stale == stale:
        return False
    prev.stale = stale
    prev.updated_at = now
    return True


def _fmt(ts: datetime | None, now: datetime) -> str:
    if ts is None:
        return "hiç yok"
    minutes = int((now - ts).total_seconds() // 60)
    return f"{ts.astimezone(ISTANBUL):%Y-%m-%d %H:%M} TSİ ({minutes} dk önce)"


def evaluate(session: Session, now: datetime, settings: Settings) -> list[Transition]:
    transitions: list[Transition] = []
    stations = session.execute(
        select(Station.id, Station.external_id).where(
            Station.source == "metar", Station.active.is_(True)
        )
    ).all()
    latest = dict(
        session.execute(
            select(Observation.station_id, func.max(Observation.observed_at))
            .where(Observation.observed_at > now - timedelta(days=30))
            .group_by(Observation.station_id)
        ).all()
    )
    limit = timedelta(minutes=settings.metar_stale_minutes)
    for sid, icao in stations:
        source = f"metar:{icao}"
        last = latest.get(sid)
        if last is not None:
            _upsert(session, source, last_success_at=last, updated_at=now)
        stale = last is None or now - last > limit
        if _set_stale(session, source, stale, now):
            transitions.append(Transition(source, stale, f"son gözlem {_fmt(last, now)}"))

    awc = session.get(SourceHealth, "metar_awc")
    if awc is not None:
        last_ok = awc.last_success_at
        stale = last_ok is None or now - last_ok > timedelta(
            minutes=settings.awc_fetch_stale_minutes
        )
        detail = f"son başarılı istek {_fmt(last_ok, now)}"
        if stale and awc.last_error:
            detail += f"; son hata: {awc.last_error}"
        if _set_stale(session, "metar_awc", stale, now):
            transitions.append(Transition("metar_awc", stale, detail))

    transitions += _evaluate_models(session, now)
    return transitions


def _evaluate_models(session: Session, now: datetime) -> list[Transition]:
    transitions: list[Transition] = []
    watched = session.execute(
        select(Model.id, Model.code, Model.meta).where(
            Model.active.is_(True), Model.meta.has_key("stale_hours")
        )
    ).all()
    for mid, code, meta in watched:
        last = session.execute(
            select(func.max(ModelRun.init_time)).where(
                ModelRun.model_id == mid, ModelRun.status == "loaded"
            )
        ).scalar_one_or_none()
        source = f"model:{code}"
        if last is not None:
            _upsert(session, source, last_success_at=last, updated_at=now)
        stale = last is None or now - last > timedelta(hours=float(meta["stale_hours"]))
        if _set_stale(session, source, stale, now):
            transitions.append(
                Transition(source, stale, f"son yüklenen çalıştırma {_fmt(last, now)}")
            )
    return transitions


def check_sources() -> list[Transition]:
    """Worker işi: tazeliği değerlendirir, durum değişikliklerini bildirir."""
    now = datetime.now(UTC)
    with session_scope() as session:
        transitions = evaluate(session, now, get_settings())
        session.commit()
    for t in transitions:
        if t.stale:
            notify(f"Veri kaynağı durdu: {t.source}", t.detail)
        else:
            notify(f"Veri kaynağı düzeldi: {t.source}", t.detail)
    return transitions
