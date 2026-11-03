"""UKMO canlı işi: çalıştırma tamlığı kuralı (sentetik dosya listeleriyle)."""

from datetime import UTC, datetime, timedelta

from hava.ingest.archive.ukmo import FileRef
from hava.ingest.models import ukmo

INIT = datetime(2026, 11, 3, 0, tzinfo=UTC)


def _refs(init: datetime, last_h: int, params: int = 3) -> list[FileRef]:
    return [
        FileRef(f"k{p}-{h}", init, init + timedelta(hours=h), h * 60, f"param{p}")
        for p in range(params)
        for h in range(0, last_h + 1, 3)
    ]


def test_long_run_needs_full_horizon() -> None:
    assert not ukmo.run_complete(_refs(INIT, 165), INIT, None)  # 168 sa'e ulaşmadı
    assert ukmo.run_complete(_refs(INIT, 168), INIT, None)
    assert not ukmo.run_complete([], INIT, None)


def test_short_runs_end_at_69_hours() -> None:
    six = INIT.replace(hour=6)
    refs = [r for r in _refs(six, 72) if r.lead_min <= 69 * 60]
    refs.append(FileRef("k-69", six, six + timedelta(hours=69), 69 * 60, "param0"))
    assert ukmo.run_complete(refs, six, None)


def test_fewer_files_than_previous_run_is_not_complete() -> None:
    refs = _refs(INIT, 168, params=3)
    assert not ukmo.run_complete(refs, INIT, previous=len(refs) + 1)  # yükleme sürüyor
    assert ukmo.run_complete(refs, INIT, previous=len(refs))
