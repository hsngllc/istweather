"""Alembic ortamı: bağlantı adresi uygulama ayarlarından gelir."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from hava.db.models import Base
from hava.settings import get_settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# TimescaleDB'nin kendi şemalarındaki nesneler karşılaştırmaya girmesin.
_TIMESCALE_SCHEMAS = {"_timescaledb_internal", "_timescaledb_catalog", "timescaledb_information"}


def include_object(obj, name, type_, reflected, compare_to):  # type: ignore[no-untyped-def]
    schema = getattr(obj, "schema", None)
    return schema not in _TIMESCALE_SCHEMAS


def run_migrations_offline() -> None:
    url = get_settings().sqlalchemy_url
    context.configure(
        url=url if isinstance(url, str) else url.render_as_string(hide_password=False),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(get_settings().sqlalchemy_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
