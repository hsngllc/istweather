"""Veritabanı şeması (spec §7).

Tüm zamanlar UTC (``timestamptz``); birimler SI: °C, m/s, mm, hPa, m. ★ ile işaretli tablolar
TimescaleDB hypertable'dır; hypertable ve sıkıştırma politikaları migration'da tanımlanır.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import (
    REAL,
    TIMESTAMP,
    BigInteger,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

TZ = TIMESTAMP(timezone=True)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map: ClassVar[dict[Any, Any]] = {dict[str, Any]: JSONB, datetime: TZ}


class District(Base):
    __tablename__ = "districts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    region: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Station(Base):
    __tablename__ = "stations"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_stations_source_external_id"),
        CheckConstraint("source IN ('mgm', 'metar', 'wis2')", name="source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(16))
    external_id: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(128))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    elevation_m: Mapped[float | None] = mapped_column(Float)
    district_id: Mapped[int | None] = mapped_column(ForeignKey("districts.id"))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    meta: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))


class Point(Base):
    """Model çıktısının çıkarıldığı nokta.

    ``point_key`` arşiv dosyalarındaki ``point_id`` ile aynıdır
    (``district:<slug>:<sıra>`` veya ``station:<kaynak>:<harici_id>``).
    """

    __tablename__ = "points"
    __table_args__ = (
        CheckConstraint("kind IN ('district', 'station')", name="kind"),
        CheckConstraint(
            "(kind = 'district' AND district_id IS NOT NULL AND station_id IS NULL)"
            " OR (kind = 'station' AND station_id IS NOT NULL)",
            name="kind_refs",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    point_key: Mapped[str] = mapped_column(String(128), unique=True)
    district_id: Mapped[int | None] = mapped_column(ForeignKey("districts.id"))
    station_id: Mapped[int | None] = mapped_column(ForeignKey("stations.id"))
    kind: Mapped[str] = mapped_column(String(16))
    ordinal: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    elevation_m: Mapped[float] = mapped_column(Float)
    coastal: Mapped[bool | None] = mapped_column(Boolean)
    source: Mapped[str] = mapped_column(Text)


class Observation(Base):  # ★
    __tablename__ = "observations"

    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id"), primary_key=True)
    observed_at: Mapped[datetime] = mapped_column(primary_key=True)
    temp_c: Mapped[float | None] = mapped_column(REAL)
    dewpoint_c: Mapped[float | None] = mapped_column(REAL)
    rh_pct: Mapped[float | None] = mapped_column(REAL)
    pressure_hpa: Mapped[float | None] = mapped_column(REAL)
    wind_speed_ms: Mapped[float | None] = mapped_column(REAL)
    wind_dir_deg: Mapped[float | None] = mapped_column(REAL)
    wind_gust_ms: Mapped[float | None] = mapped_column(REAL)
    precip_mm: Mapped[float | None] = mapped_column(REAL)
    precip_period_h: Mapped[float | None] = mapped_column(REAL)
    visibility_m: Mapped[float | None] = mapped_column(REAL)
    cloud_cover_pct: Mapped[float | None] = mapped_column(REAL)
    present_weather: Mapped[str | None] = mapped_column(String(64))
    qc_flags: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))
    raw: Mapped[dict[str, Any] | None] = mapped_column()


class Model(Base):
    __tablename__ = "models"
    __table_args__ = (CheckConstraint("kind IN ('deterministic', 'ensemble')", name="kind"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    provider: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16))
    resolution: Mapped[str] = mapped_column(String(64))
    license: Mapped[str] = mapped_column(Text)
    attribution_text: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    # Lisans gereği yalnız iç doğrulamada kullanılır (ör. UKMO, CC BY-SA kararı verilene kadar).
    internal_only: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    # Kaynak, hamle tanımları, model sürüm kırılma tarihleri vb.
    meta: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))


class ModelRun(Base):
    __tablename__ = "model_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'downloading', 'extracted', 'loaded', 'failed')", name="status"
        ),
    )

    model_id: Mapped[int] = mapped_column(ForeignKey("models.id"), primary_key=True)
    init_time: Mapped[datetime] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(16))
    discovered_at: Mapped[datetime] = mapped_column(server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column()
    files: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))
    error: Mapped[str | None] = mapped_column(Text)


class PointForecast(Base):  # ★ geniş format: model × çalıştırma × nokta × geçerlilik zamanı
    __tablename__ = "point_forecasts"

    model_id: Mapped[int] = mapped_column(ForeignKey("models.id"), primary_key=True)
    init_time: Mapped[datetime] = mapped_column(primary_key=True)
    point_id: Mapped[int] = mapped_column(ForeignKey("points.id"), primary_key=True)
    valid_time: Mapped[datetime] = mapped_column(primary_key=True)
    lead_h: Mapped[float] = mapped_column(REAL)
    temp_c: Mapped[float | None] = mapped_column(REAL)
    dewpoint_c: Mapped[float | None] = mapped_column(REAL)
    rh_pct: Mapped[float | None] = mapped_column(REAL)
    precip_mm: Mapped[float | None] = mapped_column(REAL)
    precip_period_h: Mapped[float | None] = mapped_column(REAL)
    snow_mm: Mapped[float | None] = mapped_column(REAL)
    precip_type: Mapped[str | None] = mapped_column(String(16))
    wind_u_ms: Mapped[float | None] = mapped_column(REAL)
    wind_v_ms: Mapped[float | None] = mapped_column(REAL)
    wind_gust_ms: Mapped[float | None] = mapped_column(REAL)
    mslp_hpa: Mapped[float | None] = mapped_column(REAL)
    cloud_cover_pct: Mapped[float | None] = mapped_column(REAL)
    low_cloud_pct: Mapped[float | None] = mapped_column(REAL)
    visibility_m: Mapped[float | None] = mapped_column(REAL)
    t850_c: Mapped[float | None] = mapped_column(REAL)
    # Noktaya indirme yöntemi (izlenebilirlik), ör. "bilinear_unmasked", "bilinear_lsm_lapse".
    extraction: Mapped[str] = mapped_column(String(32))
    # Modele özgü ek alanlar ve tanımlar (hamle tanımı, Tmax/Tmin penceresi vb.).
    extra: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))


class EnsembleStat(Base):  # ★
    __tablename__ = "ensemble_stats"

    model_id: Mapped[int] = mapped_column(ForeignKey("models.id"), primary_key=True)
    init_time: Mapped[datetime] = mapped_column(primary_key=True)
    point_id: Mapped[int] = mapped_column(ForeignKey("points.id"), primary_key=True)
    valid_time: Mapped[datetime] = mapped_column(primary_key=True)
    variable: Mapped[str] = mapped_column(String(32), primary_key=True)
    n_members: Mapped[int] = mapped_column(SmallInteger)
    mean: Mapped[float | None] = mapped_column(REAL)
    std: Mapped[float | None] = mapped_column(REAL)
    p10: Mapped[float | None] = mapped_column(REAL)
    p25: Mapped[float | None] = mapped_column(REAL)
    p50: Mapped[float | None] = mapped_column(REAL)
    p75: Mapped[float | None] = mapped_column(REAL)
    p90: Mapped[float | None] = mapped_column(REAL)
    exceed_probs: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))
    # Noktaya indirme yöntemi ve satır ayrıntısı (yağış aralığı, hamle tanımı) — izlenebilirlik.
    extraction: Mapped[str] = mapped_column(String(32), server_default="")
    extra: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))


class VerificationMetric(Base):
    __tablename__ = "verification_metrics"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    subject: Mapped[str] = mapped_column(String(64))  # model kodu veya "blend:<sürüm>"
    point_id: Mapped[int | None] = mapped_column(ForeignKey("points.id"))
    variable: Mapped[str] = mapped_column(String(32))
    lead_bucket: Mapped[str] = mapped_column(String(16))
    period_start: Mapped[datetime] = mapped_column()
    period_end: Mapped[datetime] = mapped_column()
    season: Mapped[str | None] = mapped_column(String(8))
    regime: Mapped[str | None] = mapped_column(String(32))
    n: Mapped[int] = mapped_column(Integer)
    mae: Mapped[float | None] = mapped_column(Float)
    rmse: Mapped[float | None] = mapped_column(Float)
    bias: Mapped[float | None] = mapped_column(Float)
    crps: Mapped[float | None] = mapped_column(Float)
    brier: Mapped[float | None] = mapped_column(Float)
    extra: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))
    computed_at: Mapped[datetime] = mapped_column(server_default=func.now())


class BiasParam(Base):
    __tablename__ = "bias_params"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    version: Mapped[str] = mapped_column(String(32))
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id"))
    point_id: Mapped[int | None] = mapped_column(ForeignKey("points.id"))
    group_key: Mapped[str | None] = mapped_column(String(64))  # hiyerarşik geri düşme düzeyi
    variable: Mapped[str] = mapped_column(String(32))
    lead_bucket: Mapped[str] = mapped_column(String(16))
    hour_of_day: Mapped[int | None] = mapped_column(SmallInteger)
    regime: Mapped[str | None] = mapped_column(String(32))
    value: Mapped[float] = mapped_column(Float)
    n: Mapped[int] = mapped_column(Integer)
    trained_from: Mapped[datetime] = mapped_column()
    trained_to: Mapped[datetime] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    meta: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))


class BlendWeight(Base):
    __tablename__ = "blend_weights"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    version: Mapped[str] = mapped_column(String(32))
    model_id: Mapped[int] = mapped_column(ForeignKey("models.id"))
    variable: Mapped[str] = mapped_column(String(32))
    lead_bucket: Mapped[str] = mapped_column(String(16))
    weight: Mapped[float] = mapped_column(Float)
    mse: Mapped[float | None] = mapped_column(Float)
    n: Mapped[int] = mapped_column(Integer)
    trained_from: Mapped[datetime] = mapped_column()
    trained_to: Mapped[datetime] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    meta: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))


class PublishedForecast(Base):  # ★ API yalnız bu tabloyu okur (spec §4)
    __tablename__ = "published_forecasts"
    __table_args__ = (
        CheckConstraint("resolution IN ('hourly', 'daily')", name="resolution"),
        CheckConstraint("confidence IN ('high', 'medium', 'low')", name="confidence"),
    )

    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id"), primary_key=True)
    issued_at: Mapped[datetime] = mapped_column(primary_key=True)
    valid_time: Mapped[datetime] = mapped_column(primary_key=True)
    resolution: Mapped[str] = mapped_column(String(8), primary_key=True)
    # Değişken başına {"p10", "p50", "p90"}; ör. {"temp_c": {...}, "wind_speed_ms": {...}}
    values: Mapped[dict[str, Any]] = mapped_column()
    pop: Mapped[float | None] = mapped_column(REAL)
    confidence: Mapped[str] = mapped_column(String(8))
    models_used: Mapped[dict[str, Any]] = mapped_column()
    blend_version: Mapped[str] = mapped_column(String(32))


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (CheckConstraint("level IN ('yellow', 'orange', 'red')", name="level"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id"))
    hazard: Mapped[str] = mapped_column(String(32))
    level: Mapped[str] = mapped_column(String(8))
    probability: Mapped[float] = mapped_column(REAL)
    valid_from: Mapped[datetime] = mapped_column()
    valid_to: Mapped[datetime] = mapped_column()
    issued_at: Mapped[datetime] = mapped_column()
    message_tr: Mapped[str] = mapped_column(Text)
    blend_version: Mapped[str] = mapped_column(String(32))


class SourceHealth(Base):
    __tablename__ = "source_health"

    source: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_success_at: Mapped[datetime | None] = mapped_column()
    last_error_at: Mapped[datetime | None] = mapped_column()
    last_error: Mapped[str | None] = mapped_column(Text)
    stale: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())
    # İlk kayıt zamanı (yeni eklenen modelin bekleme süresi için; güncellemede değişmez).
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
