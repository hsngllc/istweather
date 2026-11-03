"""Termodinamik yardımcılar."""

from __future__ import annotations

from typing import overload

import numpy as np

from hava.processing.grid import FloatArray


@overload
def relative_humidity(temp_c: float, dewpoint_c: float) -> float: ...
@overload
def relative_humidity(temp_c: FloatArray, dewpoint_c: FloatArray) -> FloatArray: ...


def relative_humidity(
    temp_c: float | FloatArray, dewpoint_c: float | FloatArray
) -> float | FloatArray:
    """Magnus formülü (Alduchov & Eskridge 1996 katsayıları), %0–100 aralığına kırpılır."""

    def es(t: float | FloatArray) -> float | FloatArray:
        return 6.1094 * np.exp(17.625 * np.asarray(t) / (np.asarray(t) + 243.04))

    rh = np.minimum(100.0, 100.0 * es(dewpoint_c) / es(temp_c))
    return float(rh) if np.ndim(rh) == 0 else np.asarray(rh, dtype=np.float64)
