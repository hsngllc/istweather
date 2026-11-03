"""source_health: ilk kayıt zamanı.

Hiç yüklenmiş çalıştırması olmayan yeni bir model, toplayıcısı tazelik eşiği boyunca hiçbir şey
yükleyemezse bayat sayılır; eşik toplayıcı kaydının ilk oluştuğu andan ölçülür (ör. GDPS'in ilk
çalıştırması ancak AMQPS duyurularıyla gelir).

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "source_health",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("source_health", "created_at")
