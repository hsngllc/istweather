"""Referans verisini konfigürasyondan veritabanına yükler (idempotent).

- districts, stations, points: config/region.<bölge>.yaml
- models: config/models.yaml

Kullanım: ``python -m hava.db.seed``
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import structlog
import yaml
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from hava.db.models import District, Model, Point, Station
from hava.db.session import session_scope
from hava.ops.logging import configure_logging
from hava.settings import get_settings

log = structlog.get_logger()


def seed_region(session: Session, path: str | Path) -> dict[str, int]:
    raw: dict[str, Any] = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    region = str(raw["region"])
    for d in raw["districts"]:
        stmt = insert(District).values(slug=d["slug"], name=d["name"], region=region)
        session.execute(
            stmt.on_conflict_do_update(
                index_elements=[District.slug],
                set_={"name": stmt.excluded.name, "region": stmt.excluded.region},
            )
        )
    district_ids = dict(session.execute(select(District.slug, District.id)).tuples().all())

    for st in raw.get("stations", []):
        values = {
            "source": st["source"],
            "external_id": st["external_id"],
            "name": st["name"],
            "lat": st["lat"],
            "lon": st["lon"],
            "elevation_m": st["elevation_m"],
            "meta": {k: st[k] for k in ("wmo_id", "wigos_id", "coord_source") if k in st},
        }
        stmt = insert(Station).values(**values)
        session.execute(
            stmt.on_conflict_do_update(
                constraint="uq_stations_source_external_id",
                set_={k: stmt.excluded[k] for k in values if k not in ("source", "external_id")},
            )
        )
    station_ids = {
        f"{src}:{ext}": sid
        for src, ext, sid in session.execute(
            select(Station.source, Station.external_id, Station.id)
        ).tuples()
    }

    points: list[dict[str, Any]] = []
    for d in raw["districts"]:
        for idx, p in enumerate(d["points"]):
            points.append(
                {
                    "point_key": f"district:{d['slug']}:{idx}",
                    "district_id": district_ids[d["slug"]],
                    "station_id": None,
                    "kind": "district",
                    "ordinal": idx,
                    "lat": p["lat"],
                    "lon": p["lon"],
                    "elevation_m": p["elevation_m"],
                    "coastal": p.get("coastal"),
                    "source": p["source"],
                }
            )
    for st in raw.get("stations", []):
        points.append(
            {
                "point_key": f"station:{st['source']}:{st['external_id']}",
                "district_id": None,
                "station_id": station_ids[f"{st['source']}:{st['external_id']}"],
                "kind": "station",
                "ordinal": 0,
                "lat": st["lat"],
                "lon": st["lon"],
                "elevation_m": st["elevation_m"],
                "coastal": None,
                "source": st.get("coord_source", st["source"]),
            }
        )
    for values in points:
        stmt = insert(Point).values(**values)
        session.execute(
            stmt.on_conflict_do_update(
                index_elements=[Point.point_key],
                set_={k: stmt.excluded[k] for k in values if k != "point_key"},
            )
        )
    return {"districts": len(raw["districts"]), "stations": len(station_ids), "points": len(points)}


def seed_models(session: Session, path: str | Path) -> int:
    raw: dict[str, Any] = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    for m in raw["models"]:
        values = {
            "code": m["code"],
            "provider": m["provider"],
            "kind": m["kind"],
            "resolution": m["resolution"],
            "license": m["license"],
            "attribution_text": m["attribution_text"],
            "active": bool(m.get("active", True)),
            "internal_only": bool(m.get("internal_only", False)),
            "meta": m.get("meta", {}),
        }
        stmt = insert(Model).values(**values)
        session.execute(
            stmt.on_conflict_do_update(
                index_elements=[Model.code],
                set_={k: stmt.excluded[k] for k in values if k != "code"},
            )
        )
    return len(raw["models"])


def main() -> int:
    configure_logging()
    settings = get_settings()
    with session_scope() as session:
        counts = seed_region(session, settings.region_config)
        counts["models"] = seed_models(session, settings.models_config)
        session.commit()
    log.info("seed_done", **counts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
