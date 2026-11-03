"""ensemble_stats: çıkarım yöntemi ve satır ayrıntısı (ADR-0006).

``point_forecasts``'taki ``extraction``/``extra`` ile aynı amaç: yağış aralığı (``period_h``) ve hamle
tanımı (``gust_definition``) satırda saklanır.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ensemble_stats",
        sa.Column("extraction", sa.String(length=32), server_default="", nullable=False),
    )
    op.add_column(
        "ensemble_stats",
        sa.Column(
            "extra",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("ensemble_stats", "extra")
    op.drop_column("ensemble_stats", "extraction")
