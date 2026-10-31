"""Bölge konfigürasyonunu (config/region.<bölge>.yaml) okur.

Nokta listesi kodda sabitlenmez; ilçe ve istasyon noktaları konfigürasyondan gelir (spec §1, §6).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Point:
    """Model çıktısının çıkarılacağı nokta.

    point_id biçimleri: ``district:<slug>:<sıra>`` ve ``station:<kaynak>:<harici_id>``.
    """

    point_id: str
    kind: str
    lat: float
    lon: float
    elevation_m: float
    coastal: bool | None = None


@dataclass(frozen=True)
class Region:
    name: str
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float
    points: tuple[Point, ...]


def load_region(path: str | Path) -> Region:
    raw: dict[str, Any] = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    points: list[Point] = []
    for district in raw["districts"]:
        for idx, p in enumerate(district["points"]):
            points.append(
                Point(
                    point_id=f"district:{district['slug']}:{idx}",
                    kind="district",
                    lat=float(p["lat"]),
                    lon=float(p["lon"]),
                    elevation_m=float(p["elevation_m"]),
                    coastal=bool(p.get("coastal", False)),
                )
            )
    for st in raw.get("stations", []):
        points.append(
            Point(
                point_id=f"station:{st['source']}:{st['external_id']}",
                kind="station",
                lat=float(st["lat"]),
                lon=float(st["lon"]),
                elevation_m=float(st["elevation_m"]),
            )
        )
    ids = [p.point_id for p in points]
    if len(ids) != len(set(ids)):
        raise ValueError("region config contains duplicate point ids")
    bbox = raw["bbox"]
    return Region(
        name=str(raw["region"]),
        lat_min=float(bbox["lat_min"]),
        lat_max=float(bbox["lat_max"]),
        lon_min=float(bbox["lon_min"]),
        lon_max=float(bbox["lon_max"]),
        points=tuple(points),
    )
