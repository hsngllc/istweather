"""Météo-France ARPEGE adaptörü: dosya adları, paket planı ve dosyadan mesaj seçimi.

GRIB mesajları sentetiktir (``synthetic_message``); ağ kullanılmaz.
"""

from datetime import UTC, datetime
from pathlib import Path

import eccodes

from hava.ingest.models import arpege

INIT = datetime(2026, 10, 31, 0, tzinfo=UTC)


def synthetic_message(
    disc: int, cat: int, num: int, stat: int | None = None, surf: int = 1, level: int = 0
) -> bytes:
    """Kimliği verilen sentetik GRIB2 mesajı (``stat``: 1 birikim, 2 en yüksek, 3 en düşük)."""
    h = eccodes.codes_grib_new_from_samples("regular_ll_sfc_grib2")
    try:
        if stat is not None:
            eccodes.codes_set(h, "productDefinitionTemplateNumber", 8)
            eccodes.codes_set(h, "typeOfStatisticalProcessing", stat)
            eccodes.codes_set(h, "stepUnits", 1)
            eccodes.codes_set(h, "lengthOfTimeRange", 1)
            eccodes.codes_set(h, "forecastTime", 2)
        eccodes.codes_set(h, "discipline", disc)
        eccodes.codes_set(h, "parameterCategory", cat)
        eccodes.codes_set(h, "parameterNumber", num)
        eccodes.codes_set(h, "typeOfFirstFixedSurface", surf)
        if surf == 103:
            eccodes.codes_set(h, "scaleFactorOfFirstFixedSurface", 0)
            eccodes.codes_set(h, "scaledValueOfFirstFixedSurface", level)
        return bytes(eccodes.codes_get_message(h))
    finally:
        eccodes.codes_release(h)


def test_file_names_follow_package_layout() -> None:
    assert arpege.file_url(arpege.BASE_URL, INIT, "SP1", 0, 12) == (
        "https://meteofrance-pnt.s3.rbx.io.cloud.ovh.net/pnt/2026-10-31T00:00:00Z/arpege/01/SP1/"
        "arpege__01__SP1__000H012H__2026-10-31T00:00:00Z.grib2"
    )
    files = arpege.files_for(168)
    assert len(files) == 18 and files[0] == ("SP1", 0, 12) and files[-1] == ("SP2", 97, 102)
    assert arpege.files_for(12) == [("SP1", 0, 12), ("SP2", 0, 12)]


def test_iter_wanted_selects_by_identity_not_name(tmp_path: Path) -> None:
    messages = [
        synthetic_message(0, 0, 0, surf=103, level=2),  # 2t → t2m
        synthetic_message(0, 0, 0),  # yüzey sıcaklığı (aynı kimlik, farklı seviye) → alınmaz
        synthetic_message(0, 0, 0, stat=2, surf=103, level=2),  # Tmax → alınmaz
        synthetic_message(0, 1, 52, stat=1),  # tp → precip_acc
        synthetic_message(0, 2, 22, stat=2, surf=103, level=10),  # hamle (son 1 sa en yüksek)
        synthetic_message(0, 19, 0, stat=3),  # görüş (son 1 sa en düşük)
        synthetic_message(0, 6, 1),  # toplam bulut (eccodes adı "unknown")
        synthetic_message(0, 1, 19, stat=0),  # yağış tipi → alınmaz (yerel kod belirsiz)
        synthetic_message(0, 3, 6),  # arazi yüksekliği
    ]
    path = tmp_path / "SP.grib2"
    path.write_bytes(b"".join(messages))
    got = [w.var for w, _ in arpege.iter_wanted(path)]
    assert got == ["t2m", "precip_acc", "gust", "vis", "tcc", "orog"]
    scales = {w.var: w.scale for w, _ in arpege.iter_wanted(path)}
    assert scales["tcc"] == 0.01 and scales["t2m"] == 1.0
