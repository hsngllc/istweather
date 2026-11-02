"""HTTP Range istekleriyle uzak bir dosyayı okunabilir/aranabilir dosya gibi sunar.

h5py bir Python dosya nesnesini doğrudan açabildiği için, büyük NetCDF-4/HDF5 dosyalarından
yalnızca gereken baytlar (meta veri ve ilgili chunk'lar) indirilir.
"""

from __future__ import annotations

import io
import time
from collections.abc import Callable

import httpx

RETRY_STATUS = {429, 500, 502, 503, 504}


class RemoteFileGone(Exception):
    """Dosya artık sunucuda yok (404); kayan arşivden silinmiş olabilir."""


def get_with_retry(
    client: httpx.Client,
    url: str,
    headers: dict[str, str] | None = None,
    attempts: int = 6,
    sleep: Callable[[float], None] = time.sleep,
    params: dict[str, str | list[str]] | None = None,
) -> httpx.Response:
    delay = 1.0
    for attempt in range(1, attempts + 1):
        try:
            resp = client.get(url, headers=headers, params=params)
        except (httpx.TransportError, httpx.TimeoutException):
            if attempt == attempts:
                raise
        else:
            if resp.status_code == 404:
                raise RemoteFileGone(url)
            if resp.status_code not in RETRY_STATUS:
                resp.raise_for_status()
                return resp
            if attempt == attempts:
                resp.raise_for_status()
        sleep(delay)
        delay = min(delay * 2, 30.0)
    raise AssertionError("unreachable")


class HttpRangeFile(io.RawIOBase):
    """Salt okunur uzak dosya.

    HDF5 meta veri okumaları küçük ve dağınıktır; bunlar ``block_size`` bloklarla önbelleklenir.
    ``direct_threshold`` ve üzeri okumalar (ör. sıkıştırılmış bir chunk) tam aralıkla, blok
    yuvarlaması olmadan tek istekte alınır. Böylece hem istek sayısı hem indirilen bayt düşük kalır.
    """

    def __init__(
        self,
        client: httpx.Client,
        url: str,
        size: int,
        block_size: int = 4096,
        direct_threshold: int = 16384,
    ):
        super().__init__()
        self._client = client
        self._url = url
        self._size = size
        self._block = block_size
        self._direct = direct_threshold
        self._pos = 0
        self._cache: dict[int, bytes] = {}
        self.requests = 0
        self.bytes_read = 0

    @classmethod
    def open(
        cls,
        client: httpx.Client,
        url: str,
        block_size: int = 4096,
        head_size: int = 16384,
        direct_threshold: int = 16384,
    ) -> HttpRangeFile:
        # Dosyanın başı (superblock ve kök grup) tek istekte alınır; Content-Range başlığından
        # dosya boyutu öğrenilir, ayrıca HEAD isteği gerekmez.
        if head_size % block_size:
            raise ValueError("head_size must be a multiple of block_size")
        resp = get_with_retry(client, url, headers={"Range": f"bytes=0-{head_size - 1}"})
        total = resp.headers.get("content-range", "").rpartition("/")[2]
        size = int(total) if total.isdigit() else len(resp.content)
        f = cls(client, url, size, block_size, direct_threshold)
        data = resp.content
        for b in range(0, (len(data) + block_size - 1) // block_size):
            f._cache[b] = data[b * block_size : (b + 1) * block_size]
        f.requests = 1
        f.bytes_read = len(data)
        return f

    @property
    def size(self) -> int:
        return self._size

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._pos

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            self._pos = offset
        elif whence == io.SEEK_CUR:
            self._pos += offset
        else:
            self._pos = self._size + offset
        return self._pos

    def _fetch(self, first: int, last: int) -> None:
        missing = [b for b in range(first, last + 1) if b not in self._cache]
        if not missing:
            return
        # Ardışık eksik blokları tek istekte al.
        start = missing[0]
        prev = start
        runs: list[tuple[int, int]] = []
        for b in missing[1:]:
            if b != prev + 1:
                runs.append((start, prev))
                start = b
            prev = b
        runs.append((start, prev))
        for b0, b1 in runs:
            lo = b0 * self._block
            hi = min((b1 + 1) * self._block, self._size) - 1
            resp = get_with_retry(self._client, self._url, headers={"Range": f"bytes={lo}-{hi}"})
            data = resp.content
            self.requests += 1
            self.bytes_read += len(data)
            for b in range(b0, b1 + 1):
                off = (b - b0) * self._block
                self._cache[b] = data[off : off + self._block]

    def readinto(self, buf: bytearray | memoryview) -> int:  # type: ignore[override]
        n = min(len(buf), self._size - self._pos)
        if n <= 0:
            return 0
        mv = memoryview(buf)
        if n >= self._direct:
            lo, hi = self._pos, self._pos + n - 1
            resp = get_with_retry(self._client, self._url, headers={"Range": f"bytes={lo}-{hi}"})
            data = resp.content
            self.requests += 1
            self.bytes_read += len(data)
            if len(data) != n:
                raise OSError(f"short read from {self._url}: {len(data)} != {n}")
            mv[:n] = data
            self._pos += n
            return n
        first = self._pos // self._block
        last = (self._pos + n - 1) // self._block
        self._fetch(first, last)
        out = bytearray()
        for b in range(first, last + 1):
            out += self._cache[b]
        start = self._pos - first * self._block
        mv[:n] = out[start : start + n]
        self._pos += n
        return n
