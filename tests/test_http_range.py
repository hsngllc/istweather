import httpx
import pytest

from hava.ingest.archive.http_range import HttpRangeFile, RemoteFileGone, get_with_retry

# Etiketli örnek veri: rastgele değil, konumu kendi baytından anlaşılan sentetik içerik.
SAMPLE = bytes(i % 251 for i in range(100_000))


def _range_handler(calls: list[str]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        rng = request.headers["range"].removeprefix("bytes=")
        calls.append(rng)
        lo, hi = (int(x) for x in rng.split("-"))
        body = SAMPLE[lo : hi + 1]
        return httpx.Response(
            206, content=body, headers={"content-range": f"bytes {lo}-{hi}/{len(SAMPLE)}"}
        )

    return httpx.MockTransport(handler)


def test_reads_match_source_and_use_few_requests() -> None:
    calls: list[str] = []
    with httpx.Client(transport=_range_handler(calls)) as client:
        f = HttpRangeFile.open(client, "https://example.test/f.nc")
        assert f.size == len(SAMPLE)
        f.seek(100)
        assert f.read(50) == SAMPLE[100:150]  # başlık önbelleğinden, yeni istek yok
        f.seek(90_000)
        assert f.read(300) == SAMPLE[90_000:90_300]  # küçük okuma: blok önbelleği
        f.seek(40_000)
        assert f.read(20_000) == SAMPLE[40_000:60_000]  # büyük okuma: tam aralık
        f.seek(-10, 2)
        assert f.read() == SAMPLE[-10:]
    assert calls[0] == "0-16383"
    assert "40000-59999" in calls
    assert f.requests == len(calls)


def test_404_raises_remote_file_gone() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(404))
    with httpx.Client(transport=transport) as client, pytest.raises(RemoteFileGone):
        get_with_retry(client, "https://example.test/missing.nc")


def test_retries_transient_errors() -> None:
    seen = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["n"] += 1
        return httpx.Response(503 if seen["n"] < 3 else 200, content=b"ok")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        resp = get_with_retry(client, "https://example.test/x", sleep=lambda s: None)
    assert resp.content == b"ok"
    assert seen["n"] == 3
