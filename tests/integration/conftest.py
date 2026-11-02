"""Entegrasyon testleri için ortak fixture'lar (TimescaleDB gerekir; boş veritabanı varsayılır)."""

import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def migrated() -> str:
    if not os.environ.get("HAVA_DATABASE_URL"):
        pytest.skip("HAVA_DATABASE_URL tanımlı değil")
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(ROOT / "alembic.ini"))
    command.upgrade(cfg, "head")
    command.check(cfg)  # modeller ile migration arasında fark yok
    return os.environ["HAVA_DATABASE_URL"]


@pytest.fixture(scope="session")
def seeded(migrated: str) -> str:
    from hava.db.seed import seed_models, seed_region
    from hava.db.session import session_scope

    with session_scope() as session:
        seed_region(session, ROOT / "config/region.istanbul.yaml")
        seed_models(session, ROOT / "config/models.yaml")
        session.commit()
    return migrated
