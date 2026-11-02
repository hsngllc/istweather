"""AWC ve IEM toplayıcıları: gerçek yanıtlar (fixtures/metar) MockTransport ile sunulur."""

import csv
import io
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path

import httpx
import pytest

from hava.ingest.obs.awc import AwcResponseError, fetch_awc
from hava.ingest.obs.iem import fetch_iem, month_windows

FIXTURES = Path(__file__).parent / "fixtures" / "metar"
AWC_URL = "https://aviationweather.example/api/data/metar"
IEM_URL = "https://iem.example/cgi-bin/request/asos.py"


def test_fetch_awc_uses_obs_time_and_raw_text() -> None:
    body = (FIXTURES / "awc_metar_2026-11-02.json").read_bytes()
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=body, headers={"content-type": "application/json"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        reports = fetch_awc(client, AWC_URL, ["LTBA", "LTFJ", "LTFM"], hours=6)
    assert seen[0].url.params["ids"] == "LTBA,LTFJ,LTFM"
    assert seen[0].url.params["format"] == "json" and seen[0].url.params["hours"] == "6"
    assert len(reports) == 33 and {r.source for r in reports} == {"awc"}
    first = reports[0]
    assert first.station == "LTFJ"
    assert first.observed_at == datetime(2026, 11, 2, 5, 20, tzinfo=UTC)
    assert first.text.startswith("METAR LTFJ 020520Z")


def test_fetch_awc_no_content_and_bad_shapes() -> None:
    def no_content(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    with httpx.Client(transport=httpx.MockTransport(no_content)) as client:
        assert fetch_awc(client, AWC_URL, ["LTFM"], hours=3) == []

    def not_a_list(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": "x"})

    with (
        httpx.Client(transport=httpx.MockTransport(not_a_list)) as client,
        pytest.raises(AwcResponseError),
    ):
        fetch_awc(client, AWC_URL, ["LTFM"], hours=3)


def test_fetch_iem_parses_csv_and_requests_routine_and_specials() -> None:
    with open(FIXTURES / "iem_2025_cases.csv", newline="", encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r["station"] == "LTFM"]
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["station", "valid", "metar"])
    for r in rows:
        w.writerow([r["station"], r["valid_utc"], r["metar"]])
    w.writerow(["LTFM", "2025-01-01 09:20", ""])  # boş METAR satırı atlanır
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text=out.getvalue())

    start = datetime(2025, 1, 1, tzinfo=UTC)
    end = datetime(2025, 2, 1, tzinfo=UTC)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        reports = fetch_iem(client, IEM_URL, "LTFM", start, end)
    params = seen[0].url.params
    assert params.get_list("report_type") == ["3", "4"]
    assert params["data"] == "metar" and params["sts"] == "2025-01-01T00:00Z"
    assert params["ets"] == "2025-02-01T00:00Z"
    assert len(reports) == len(rows) and {r.source for r in reports} == {"iem"}
    assert reports[0].observed_at == datetime(2025, 1, 1, 8, 50, tzinfo=UTC)


def test_month_windows_cover_range_without_overlap() -> None:
    start = datetime(2024, 1, 15, 6, tzinfo=UTC)
    end = datetime(2024, 4, 2, tzinfo=UTC)
    w = month_windows(start, end)
    assert w[0] == (start, datetime(2024, 2, 1, tzinfo=UTC))
    assert w[-1] == (datetime(2024, 4, 1, tzinfo=UTC), end)
    assert all(a[1] == b[0] for a, b in pairwise(w))
    assert len(w) == 4
