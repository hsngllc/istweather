"""İlk şema (spec §7): tablolar, TimescaleDB hypertable'ları ve sıkıştırma politikaları.

Tablo tanımları ``hava.db.models``'ten Alembic oluşturucusuyla üretilip donduruldu; modeller
değişirse yeni bir migration eklenir (CI'da ``alembic check`` farkı yakalar).

Revision ID: 0001
Revises:
Create Date: 2026-11-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (tablo, zaman sütunu, chunk aralığı, segmentby, orderby, sıkıştırma gecikmesi)
HYPERTABLES = [
    ("observations", "observed_at", "30 days", "station_id", "observed_at DESC", "60 days"),
    (
        "point_forecasts",
        "valid_time",
        "7 days",
        "model_id, point_id",
        "valid_time DESC, init_time DESC",
        "30 days",
    ),
    (
        "ensemble_stats",
        "valid_time",
        "7 days",
        "model_id, point_id, variable",
        "valid_time DESC, init_time DESC",
        "30 days",
    ),
    (
        "published_forecasts",
        "valid_time",
        "30 days",
        "district_id, resolution",
        "valid_time DESC, issued_at DESC",
        "60 days",
    ),
]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
    op.create_table(
        "districts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("region", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_districts")),
        sa.UniqueConstraint("slug", name=op.f("uq_districts_slug")),
    )
    op.create_table(
        "models",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("resolution", sa.String(length=64), nullable=False),
        sa.Column("license", sa.Text(), nullable=False),
        sa.Column("attribution_text", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("internal_only", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "meta",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint("kind IN ('deterministic', 'ensemble')", name=op.f("ck_models_kind")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_models")),
        sa.UniqueConstraint("code", name=op.f("uq_models_code")),
    )
    op.create_table(
        "source_health",
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("last_success_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_error_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("stale", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("source", name=op.f("pk_source_health")),
    )
    op.create_table(
        "alerts",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("district_id", sa.Integer(), nullable=False),
        sa.Column("hazard", sa.String(length=32), nullable=False),
        sa.Column("level", sa.String(length=8), nullable=False),
        sa.Column("probability", sa.REAL(), nullable=False),
        sa.Column("valid_from", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("valid_to", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("issued_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("message_tr", sa.Text(), nullable=False),
        sa.Column("blend_version", sa.String(length=32), nullable=False),
        sa.CheckConstraint("level IN ('yellow', 'orange', 'red')", name=op.f("ck_alerts_level")),
        sa.ForeignKeyConstraint(
            ["district_id"], ["districts.id"], name=op.f("fk_alerts_district_id_districts")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alerts")),
    )
    op.create_table(
        "blend_weights",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("model_id", sa.Integer(), nullable=False),
        sa.Column("variable", sa.String(length=32), nullable=False),
        sa.Column("lead_bucket", sa.String(length=16), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("mse", sa.Float(), nullable=True),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column("trained_from", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("trained_to", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "meta",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["model_id"], ["models.id"], name=op.f("fk_blend_weights_model_id_models")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_blend_weights")),
    )
    op.create_table(
        "model_runs",
        sa.Column("model_id", sa.Integer(), nullable=False),
        sa.Column("init_time", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "discovered_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "files",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'downloading', 'extracted', 'loaded', 'failed')",
            name=op.f("ck_model_runs_status"),
        ),
        sa.ForeignKeyConstraint(
            ["model_id"], ["models.id"], name=op.f("fk_model_runs_model_id_models")
        ),
        sa.PrimaryKeyConstraint("model_id", "init_time", name=op.f("pk_model_runs")),
    )
    op.create_table(
        "published_forecasts",
        sa.Column("district_id", sa.Integer(), nullable=False),
        sa.Column("issued_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("valid_time", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("resolution", sa.String(length=8), nullable=False),
        sa.Column("values", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("pop", sa.REAL(), nullable=True),
        sa.Column("confidence", sa.String(length=8), nullable=False),
        sa.Column("models_used", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("blend_version", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "confidence IN ('high', 'medium', 'low')",
            name=op.f("ck_published_forecasts_confidence"),
        ),
        sa.CheckConstraint(
            "resolution IN ('hourly', 'daily')", name=op.f("ck_published_forecasts_resolution")
        ),
        sa.ForeignKeyConstraint(
            ["district_id"],
            ["districts.id"],
            name=op.f("fk_published_forecasts_district_id_districts"),
        ),
        sa.PrimaryKeyConstraint(
            "district_id",
            "issued_at",
            "valid_time",
            "resolution",
            name=op.f("pk_published_forecasts"),
        ),
    )
    op.create_table(
        "stations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("external_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("elevation_m", sa.Float(), nullable=True),
        sa.Column("district_id", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "meta",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint("source IN ('mgm', 'metar', 'wis2')", name=op.f("ck_stations_source")),
        sa.ForeignKeyConstraint(
            ["district_id"], ["districts.id"], name=op.f("fk_stations_district_id_districts")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stations")),
        sa.UniqueConstraint("source", "external_id", name="uq_stations_source_external_id"),
    )
    op.create_table(
        "observations",
        sa.Column("station_id", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("temp_c", sa.REAL(), nullable=True),
        sa.Column("dewpoint_c", sa.REAL(), nullable=True),
        sa.Column("rh_pct", sa.REAL(), nullable=True),
        sa.Column("pressure_hpa", sa.REAL(), nullable=True),
        sa.Column("wind_speed_ms", sa.REAL(), nullable=True),
        sa.Column("wind_dir_deg", sa.REAL(), nullable=True),
        sa.Column("wind_gust_ms", sa.REAL(), nullable=True),
        sa.Column("precip_mm", sa.REAL(), nullable=True),
        sa.Column("precip_period_h", sa.REAL(), nullable=True),
        sa.Column("visibility_m", sa.REAL(), nullable=True),
        sa.Column("cloud_cover_pct", sa.REAL(), nullable=True),
        sa.Column("present_weather", sa.String(length=64), nullable=True),
        sa.Column(
            "qc_flags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ["station_id"], ["stations.id"], name=op.f("fk_observations_station_id_stations")
        ),
        sa.PrimaryKeyConstraint("station_id", "observed_at", name=op.f("pk_observations")),
    )
    op.create_table(
        "points",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("point_key", sa.String(length=128), nullable=False),
        sa.Column("district_id", sa.Integer(), nullable=True),
        sa.Column("station_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("ordinal", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("elevation_m", sa.Float(), nullable=False),
        sa.Column("coastal", sa.Boolean(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "(kind = 'district' AND district_id IS NOT NULL AND station_id IS NULL) OR (kind = 'station' AND station_id IS NOT NULL)",
            name=op.f("ck_points_kind_refs"),
        ),
        sa.CheckConstraint("kind IN ('district', 'station')", name=op.f("ck_points_kind")),
        sa.ForeignKeyConstraint(
            ["district_id"], ["districts.id"], name=op.f("fk_points_district_id_districts")
        ),
        sa.ForeignKeyConstraint(
            ["station_id"], ["stations.id"], name=op.f("fk_points_station_id_stations")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_points")),
        sa.UniqueConstraint("point_key", name=op.f("uq_points_point_key")),
    )
    op.create_table(
        "bias_params",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("model_id", sa.Integer(), nullable=False),
        sa.Column("point_id", sa.Integer(), nullable=True),
        sa.Column("group_key", sa.String(length=64), nullable=True),
        sa.Column("variable", sa.String(length=32), nullable=False),
        sa.Column("lead_bucket", sa.String(length=16), nullable=False),
        sa.Column("hour_of_day", sa.SmallInteger(), nullable=True),
        sa.Column("regime", sa.String(length=32), nullable=True),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column("trained_from", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("trained_to", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "meta",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["model_id"], ["models.id"], name=op.f("fk_bias_params_model_id_models")
        ),
        sa.ForeignKeyConstraint(
            ["point_id"], ["points.id"], name=op.f("fk_bias_params_point_id_points")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bias_params")),
    )
    op.create_table(
        "ensemble_stats",
        sa.Column("model_id", sa.Integer(), nullable=False),
        sa.Column("init_time", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("point_id", sa.Integer(), nullable=False),
        sa.Column("valid_time", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("variable", sa.String(length=32), nullable=False),
        sa.Column("n_members", sa.SmallInteger(), nullable=False),
        sa.Column("mean", sa.REAL(), nullable=True),
        sa.Column("std", sa.REAL(), nullable=True),
        sa.Column("p10", sa.REAL(), nullable=True),
        sa.Column("p25", sa.REAL(), nullable=True),
        sa.Column("p50", sa.REAL(), nullable=True),
        sa.Column("p75", sa.REAL(), nullable=True),
        sa.Column("p90", sa.REAL(), nullable=True),
        sa.Column(
            "exceed_probs",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["model_id"], ["models.id"], name=op.f("fk_ensemble_stats_model_id_models")
        ),
        sa.ForeignKeyConstraint(
            ["point_id"], ["points.id"], name=op.f("fk_ensemble_stats_point_id_points")
        ),
        sa.PrimaryKeyConstraint(
            "model_id",
            "init_time",
            "point_id",
            "valid_time",
            "variable",
            name=op.f("pk_ensemble_stats"),
        ),
    )
    op.create_table(
        "point_forecasts",
        sa.Column("model_id", sa.Integer(), nullable=False),
        sa.Column("init_time", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("point_id", sa.Integer(), nullable=False),
        sa.Column("valid_time", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("lead_h", sa.REAL(), nullable=False),
        sa.Column("temp_c", sa.REAL(), nullable=True),
        sa.Column("dewpoint_c", sa.REAL(), nullable=True),
        sa.Column("rh_pct", sa.REAL(), nullable=True),
        sa.Column("precip_mm", sa.REAL(), nullable=True),
        sa.Column("precip_period_h", sa.REAL(), nullable=True),
        sa.Column("snow_mm", sa.REAL(), nullable=True),
        sa.Column("precip_type", sa.String(length=16), nullable=True),
        sa.Column("wind_u_ms", sa.REAL(), nullable=True),
        sa.Column("wind_v_ms", sa.REAL(), nullable=True),
        sa.Column("wind_gust_ms", sa.REAL(), nullable=True),
        sa.Column("mslp_hpa", sa.REAL(), nullable=True),
        sa.Column("cloud_cover_pct", sa.REAL(), nullable=True),
        sa.Column("low_cloud_pct", sa.REAL(), nullable=True),
        sa.Column("visibility_m", sa.REAL(), nullable=True),
        sa.Column("t850_c", sa.REAL(), nullable=True),
        sa.Column("extraction", sa.String(length=32), nullable=False),
        sa.Column(
            "extra",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["model_id"], ["models.id"], name=op.f("fk_point_forecasts_model_id_models")
        ),
        sa.ForeignKeyConstraint(
            ["point_id"], ["points.id"], name=op.f("fk_point_forecasts_point_id_points")
        ),
        sa.PrimaryKeyConstraint(
            "model_id", "init_time", "point_id", "valid_time", name=op.f("pk_point_forecasts")
        ),
    )
    op.create_table(
        "verification_metrics",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("subject", sa.String(length=64), nullable=False),
        sa.Column("point_id", sa.Integer(), nullable=True),
        sa.Column("variable", sa.String(length=32), nullable=False),
        sa.Column("lead_bucket", sa.String(length=16), nullable=False),
        sa.Column("period_start", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("period_end", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("season", sa.String(length=8), nullable=True),
        sa.Column("regime", sa.String(length=32), nullable=True),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column("mae", sa.Float(), nullable=True),
        sa.Column("rmse", sa.Float(), nullable=True),
        sa.Column("bias", sa.Float(), nullable=True),
        sa.Column("crps", sa.Float(), nullable=True),
        sa.Column("brier", sa.Float(), nullable=True),
        sa.Column(
            "extra",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "computed_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["point_id"], ["points.id"], name=op.f("fk_verification_metrics_point_id_points")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_verification_metrics")),
    )

    for table, column, chunk, segmentby, orderby, compress_after in HYPERTABLES:
        # Birincil anahtar zaman sütununu içerdiği için varsayılan zaman indeksine gerek yok.
        op.execute(
            f"SELECT create_hypertable('{table}', by_range('{column}', INTERVAL '{chunk}'),"
            " create_default_indexes => false)"
        )
        op.execute(
            f"ALTER TABLE {table} SET (timescaledb.compress,"
            f" timescaledb.compress_segmentby = '{segmentby}',"
            f" timescaledb.compress_orderby = '{orderby}')"
        )
        op.execute(f"SELECT add_compression_policy('{table}', INTERVAL '{compress_after}')")


def downgrade() -> None:
    op.drop_table("verification_metrics")
    op.drop_table("point_forecasts")
    op.drop_table("ensemble_stats")
    op.drop_table("bias_params")
    op.drop_table("points")
    op.drop_table("observations")
    op.drop_table("stations")
    op.drop_table("published_forecasts")
    op.drop_table("model_runs")
    op.drop_table("blend_weights")
    op.drop_table("alerts")
    op.drop_table("source_health")
    op.drop_table("models")
    op.drop_table("districts")
