"""GRIB mesajlarını eccodes ile çözer.

- Düzenli enlem-boylam: boylamlar artan sıraya getirilir (gerekirse sütunlar döndürülür); enlemler
  dosya sırasında kalır, yön düzeltmesi kırpmada yapılır (``hava.processing.grid.Crop``).
- Yapısal olmayan (ICON üçgen ızgarası): değerler tek boyutlu; koordinatlar mesajda yok, ayrı
  ``CLAT/CLON`` alanlarından gelir. Izgara kimliği ``meta["grid_id"]`` (``uuidOfHGrid``).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import eccodes
import numpy as np

from hava.processing.grid import FloatArray


class GribError(ValueError):
    """Mesaj beklenen biçimde değil."""


@dataclass(frozen=True)
class GribField:
    short_name: str
    type_of_level: str
    level: int
    end_step_h: float
    step_range: str
    units: str
    lat: FloatArray  # dosya sırasında (kuzeyden güneye olabilir); yapısal olmayanda boş
    lon: FloatArray  # artan; yapısal olmayanda boş
    values: FloatArray  # (Nj, Ni) ya da yapısal olmayanda (N,); eksik değer NaN
    meta: dict[str, Any] = field(default_factory=dict)


def split_messages(data: bytes) -> Iterator[bytes]:
    """Art arda eklenmiş GRIB1/GRIB2 mesajlarını ayırır."""
    pos = 0
    while pos < len(data):
        start = data.find(b"GRIB", pos)
        if start < 0:
            break
        edition = data[start + 7]
        if edition == 2:
            length = int.from_bytes(data[start + 8 : start + 16], "big")
        elif edition == 1:
            length = int.from_bytes(data[start + 4 : start + 7], "big")
        else:
            raise GribError(f"bilinmeyen GRIB sürümü {edition}")
        if length <= 0 or start + length > len(data):
            raise GribError("eksik GRIB mesajı")
        yield data[start : start + length]
        pos = start + length


def _get(h: Any, key: str, default: Any = None) -> Any:
    try:
        return eccodes.codes_get(h, key)
    except eccodes.KeyValueNotFoundError:
        return default


def _common(h: Any, lat: FloatArray, lon: FloatArray, values: FloatArray) -> GribField:
    return GribField(
        short_name=str(_get(h, "shortName")),
        type_of_level=str(_get(h, "typeOfLevel")),
        level=int(_get(h, "level", 0)),
        end_step_h=float(_get(h, "endStep")),
        step_range=str(_get(h, "stepRange")),
        units=str(_get(h, "units")),
        lat=lat,
        lon=lon,
        values=values,
        meta={
            "dataDate": _get(h, "dataDate"),
            "dataTime": _get(h, "dataTime"),
            "number": _get(h, "number"),
            "packingType": _get(h, "packingType"),
        },
    )


def _values(h: Any) -> FloatArray:
    values = np.asarray(eccodes.codes_get_values(h), dtype=np.float64)
    if int(_get(h, "bitmapPresent", 0)):
        values[values == float(_get(h, "missingValue"))] = np.nan
    return values


def decode_message(data: bytes) -> GribField:
    h = eccodes.codes_new_from_message(data)
    try:
        grid_type = _get(h, "gridType")
        eccodes.codes_set(h, "stepUnits", 1)  # adımlar saat cinsinden
        if grid_type == "unstructured_grid":
            empty = np.empty(0, dtype=np.float64)
            f = _common(h, empty, empty, _values(h))
            f.meta["grid_id"] = str(_get(h, "uuidOfHGrid"))
            f.meta["grid_number"] = _get(h, "numberOfGridUsed")
            return f
        if grid_type != "regular_ll":
            raise GribError(f"desteklenmeyen ızgara: {grid_type}")
        ni, nj = int(_get(h, "Ni")), int(_get(h, "Nj"))
        la1 = float(_get(h, "latitudeOfFirstGridPointInDegrees"))
        la2 = float(_get(h, "latitudeOfLastGridPointInDegrees"))
        lo1 = float(_get(h, "longitudeOfFirstGridPointInDegrees"))
        di = float(_get(h, "iDirectionIncrementInDegrees"))
        if int(_get(h, "iScansNegatively", 0)) != 0:
            raise GribError("doğudan batıya taranan ızgara desteklenmiyor")
        values = _values(h).reshape(nj, ni)
        lat = np.linspace(la1, la2, nj)
        lon = np.asarray(lo1 + di * np.arange(ni), dtype=np.float64)
        lon = np.where(lon >= 180.0, lon - 360.0, lon).astype(np.float64)
        if np.any(np.diff(lon) <= 0):  # ör. 0..360 → −180..180 dönüşümünde sütunları döndür
            shift = int(np.argmin(lon))
            lon = np.roll(lon, -shift)
            values = np.roll(values, -shift, axis=1)
        return _common(h, lat, lon, values)
    finally:
        eccodes.codes_release(h)
