"""Toplu upsert: çok satırlı INSERT ... ON CONFLICT, PostgreSQL parametre sınırıyla paketlenir."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import DeclarativeBase, Session

MAX_PARAMS = 65535  # PostgreSQL protokolünün sorgu başına bağlı parametre sınırı


def upsert(
    session: Session,
    model: type[DeclarativeBase],
    rows: Sequence[dict[str, Any]],
    constraint: str,
    key_cols: Sequence[str],
) -> int:
    """Satırları yazar; anahtar çakışırsa anahtar dışı sütunları günceller."""
    if not rows:
        return 0
    size = max(1, MAX_PARAMS // len(rows[0]))
    written = 0
    for i in range(0, len(rows), size):
        chunk = list(rows[i : i + size])
        stmt = insert(model).values(chunk)
        update = {c: stmt.excluded[c] for c in chunk[0] if c not in key_cols}
        session.execute(stmt.on_conflict_do_update(constraint=constraint, set_=update))
        written += len(chunk)
    return written
