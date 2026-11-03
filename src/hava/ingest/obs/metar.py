"""METAR ayrıştırıcı (WMO FM 15; Türk havalimanlarının kullandığı alt küme).

AWC ve IEM, değerleri kendi birimlerine çevirip yuvarlıyor (görüş mil, sıcaklık °F). Canlı ve geçmiş
gözlem birebir tutarlı olsun diye ikisinde de ham METAR metni bu modülle çözülür. Yalnız gövde
okunur: trend (NOSIG/BECMG/TEMPO) ve RMK sonrası alınmaz. Tanınmayan gruplar ``unparsed``'a düşer;
değer uydurulmaz.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from hava.processing.thermo import relative_humidity

PARSER_VERSION = "metar-1"

KT_TO_MS = 0.514444
KMH_TO_MS = 1 / 3.6
FT_TO_M = 0.3048
SM_TO_M = 1609.344
INHG_TO_HPA = 33.8639

# Katman örtüsü → yüzde (okta aralığının orta noktası). VV (gök kapalı/görünmüyor) tam örtü sayılır.
COVER_PCT = {"FEW": 18.75, "SCT": 43.75, "BKN": 75.0, "OVC": 100.0}

_TREND = {"NOSIG", "BECMG", "TEMPO"}
_WIND = re.compile(
    r"^(?P<dir>\d{3}|VRB|///)(?P<spd>\d{2,3}|//)(?:G(?P<gust>\d{2,3}))?(?P<unit>KT|MPS|KMH)$"
)
_WIND_VAR = re.compile(r"^(?P<a>\d{3})V(?P<b>\d{3})$")
_VIS = re.compile(r"^(?P<m>\d{4})(?P<ndv>NDV)?$")
_VIS_DIR = re.compile(r"^(?P<m>\d{4})(?P<dir>N|NE|E|SE|S|SW|W|NW)$")
_VIS_SM = re.compile(r"^(?P<p>[PM])?(?:(?P<whole>\d+)|(?P<num>\d)/(?P<den>\d{1,2}))SM$")
_RVR = re.compile(r"^R\d{2}[LCR]?/(?:[PM]?\d{4}(?:V[PM]?\d{4})?(?:FT)?[UDN/]?|/{4,})$")
_RUNWAY_STATE = re.compile(r"^R\d{2}[LCR]?/(?:[\d/]{6}|CLRD//)$|^R/SNOCLO$")
_DESCRIPTORS = "MI|PR|BC|DR|BL|SH|TS|FZ"
_PHENOMENA = "DZ|RA|SN|SG|IC|PL|GR|GS|UP|BR|FG|FU|VA|DU|SA|HZ|PY|PO|SQ|FC|SS|DS"
_WX = re.compile(rf"^(?P<int>[+-]|VC)?(?P<desc>{_DESCRIPTORS})?(?P<ph>(?:{_PHENOMENA})+)?$")
_RECENT = re.compile(rf"^RE(?:{_DESCRIPTORS})?(?:{_PHENOMENA})*$")
_CLOUD = re.compile(r"^(?P<cover>FEW|SCT|BKN|OVC)(?P<base>\d{3}|///)(?P<type>CB|TCU|///)?$")
_VV = re.compile(r"^VV(?P<h>\d{3}|///)$")
_TEMP = re.compile(r"^(?P<t>M?\d{2}|//)/(?P<d>M?\d{2}|//)?$")
_QNH = re.compile(r"^Q(?P<p>\d{4}|////)$")
_ALT = re.compile(r"^A(?P<p>\d{4})$")
_SEA = re.compile(r"^W(?:M)?\d{2}/(?:S\d|H\d+)$")
_TIME = re.compile(r"^(?P<d>\d{2})(?P<h>\d{2})(?P<m>\d{2})Z$")


class MetarParseError(ValueError):
    """İstasyon/zaman başlığı okunamayan METAR."""


@dataclass(frozen=True)
class CloudLayer:
    cover: str  # FEW | SCT | BKN | OVC
    base_m: float | None
    cloud_type: str | None  # CB | TCU


@dataclass(frozen=True)
class Metar:
    raw: str
    station: str
    day: int
    hour: int
    minute: int
    report_type: str = "METAR"
    auto: bool = False
    correction: bool = False
    nil: bool = False
    wind_dir_deg: float | None = None
    wind_variable: bool = False  # VRB veya dddVddd
    wind_speed_ms: float | None = None
    wind_gust_ms: float | None = None
    visibility_m: float | None = None
    visibility_ge_10km: bool = False  # 9999 / CAVOK / P6SM: "10 km veya daha fazla"
    visibility_min_m: float | None = None
    cavok: bool = False
    weather: tuple[str, ...] = ()
    recent_weather: tuple[str, ...] = ()
    clouds: tuple[CloudLayer, ...] = ()
    sky_clear: bool = False  # SKC / CLR
    no_significant_cloud: bool = False  # NSC / NCD
    sky_obscured: bool = False  # VVhhh: gök görünmüyor
    vertical_visibility_m: float | None = None
    temp_c: float | None = None
    dewpoint_c: float | None = None
    qnh_hpa: float | None = None
    unparsed: tuple[str, ...] = field(default=())

    @property
    def present_weather(self) -> str | None:
        return " ".join(self.weather) or None

    @property
    def cloud_cover_pct(self) -> float | None:
        """Bildirilen en yoğun katmanın okta orta noktası.

        NSC/NCD/CAVOK 1500 m üstünü söylemediği için bilinmiyor (None) sayılır; SKC/CLR 0'dır.
        """
        if self.sky_obscured:
            return 100.0
        if self.clouds:
            return max(COVER_PCT[c.cover] for c in self.clouds)
        if self.sky_clear:
            return 0.0
        return None

    @property
    def rh_pct(self) -> float | None:
        if self.temp_c is None or self.dewpoint_c is None:
            return None
        return relative_humidity(self.temp_c, self.dewpoint_c)


def _speed(value: str, unit: str) -> float:
    factor = {"KT": KT_TO_MS, "MPS": 1.0, "KMH": KMH_TO_MS}[unit]
    return round(int(value) * factor, 2)


def _temp(value: str | None) -> float | None:
    if value is None or value == "//":
        return None
    return -float(value[1:]) if value.startswith("M") else float(value)


def parse_metar(text: str) -> Metar:
    """Ham METAR metnini çözer. Başlık (istasyon + zaman) yoksa ``MetarParseError``."""
    raw = " ".join(text.replace("=", " ").split())
    tokens = raw.split()
    i = 0
    report_type = "METAR"
    if tokens and tokens[0] in ("METAR", "SPECI"):
        report_type = tokens[0]
        i += 1
    correction = False
    if i < len(tokens) and tokens[i] == "COR":
        correction = True
        i += 1
    if i + 1 >= len(tokens) or not re.fullmatch(r"[A-Z][A-Z0-9]{3}", tokens[i]):
        raise MetarParseError(f"istasyon kodu yok: {raw!r}")
    station = tokens[i]
    tm = _TIME.match(tokens[i + 1])
    if tm is None:
        raise MetarParseError(f"zaman grubu yok: {raw!r}")
    i += 2

    v: dict[str, Any] = {
        "raw": raw,
        "station": station,
        "day": int(tm["d"]),
        "hour": int(tm["h"]),
        "minute": int(tm["m"]),
        "report_type": report_type,
        "correction": correction,
    }
    weather: list[str] = []
    recent: list[str] = []
    clouds: list[CloudLayer] = []
    unparsed: list[str] = []
    sm_whole = 0  # "1 1/2SM" gibi iki parçalı mil görüşünün tam kısmı

    while i < len(tokens):
        tok = tokens[i]
        i += 1
        if tok in _TREND or tok == "RMK":
            break
        if tok == "AUTO":
            v["auto"] = True
        elif tok == "COR":
            v["correction"] = True
        elif tok == "NIL":
            v["nil"] = True
        elif m := _WIND.match(tok):
            if m["spd"] != "//":
                v["wind_speed_ms"] = _speed(m["spd"], m["unit"])
            if m["gust"]:
                v["wind_gust_ms"] = _speed(m["gust"], m["unit"])
            if m["dir"] == "VRB":
                v["wind_variable"] = True
            elif m["dir"] != "///" and not (m["dir"] == "000" and m["spd"] == "00"):
                v["wind_dir_deg"] = float(m["dir"])
        elif _WIND_VAR.match(tok):
            v["wind_variable"] = True
        elif tok == "CAVOK":
            v.update(cavok=True, visibility_m=10000.0, visibility_ge_10km=True)
        elif tok == "////":
            continue  # görüş ölçülemedi: boş kalır (IEM burada 10 km yazıyor, biz yazmıyoruz)
        elif m := _VIS.match(tok):
            meters = int(m["m"])
            if meters == 9999:
                v.update(visibility_m=10000.0, visibility_ge_10km=True)
            else:
                v["visibility_m"] = float(meters)
        elif m := _VIS_DIR.match(tok):
            v["visibility_min_m"] = float(m["m"])
        elif m := _VIS_SM.match(tok):
            miles = float(m["whole"]) if m["whole"] else int(m["num"]) / int(m["den"])
            miles += sm_whole
            sm_whole = 0
            v["visibility_m"] = float(round(miles * SM_TO_M))
            v["visibility_ge_10km"] = m["p"] == "P" and miles * SM_TO_M >= 9999
        elif len(tok) == 1 and tok.isdigit() and i < len(tokens) and tokens[i].endswith("SM"):
            sm_whole = int(tok)
        elif _RVR.match(tok) or _RUNWAY_STATE.match(tok) or _SEA.match(tok):
            continue
        elif tok == "WS":
            # Rüzgâr kesmesi: "WS R06" veya "WS ALL RWY"; değer üretmez.
            i += 2 if i < len(tokens) and tokens[i] == "ALL" else 1
        elif _RECENT.match(tok):
            recent.append(tok)
        elif (m := _WX.match(tok)) and (m["desc"] or m["ph"]):
            weather.append(tok)
        elif m := _CLOUD.match(tok):
            base = None if m["base"] == "///" else int(m["base"]) * 100 * FT_TO_M
            ctype = m["type"] if m["type"] in ("CB", "TCU") else None
            clouds.append(CloudLayer(m["cover"], None if base is None else round(base), ctype))
        elif m := _VV.match(tok):
            v["sky_obscured"] = True
            if m["h"] != "///":
                v["vertical_visibility_m"] = float(round(int(m["h"]) * 100 * FT_TO_M))
        elif tok in ("SKC", "CLR"):
            v["sky_clear"] = True
        elif tok in ("NSC", "NCD"):
            v["no_significant_cloud"] = True
        elif m := _TEMP.match(tok):
            v["temp_c"] = _temp(m["t"])
            v["dewpoint_c"] = _temp(m["d"])
        elif m := _QNH.match(tok):
            if m["p"] != "////":
                v["qnh_hpa"] = float(m["p"])
        elif m := _ALT.match(tok):
            v["qnh_hpa"] = round(int(m["p"]) / 100 * INHG_TO_HPA, 1)
        else:
            unparsed.append(tok)

    return Metar(
        **v,
        weather=tuple(weather),
        recent_weather=tuple(recent),
        clouds=tuple(clouds),
        unparsed=tuple(unparsed),
    )


def observation_values(metar: Metar, observed_at: datetime, source: str) -> dict[str, Any]:
    """METAR'ı ``observations`` satırına çevirir (station_id ve qc_flags hariç).

    ``pressure_hpa`` QNH'dir (ISA ile deniz seviyesine indirgenmiş), MSLP değil; ``raw``'da
    belirtilir. Türk METAR'larında yağış miktarı yoktur → ``precip_mm`` boş kalır.
    """
    return {
        "observed_at": observed_at,
        "temp_c": metar.temp_c,
        "dewpoint_c": metar.dewpoint_c,
        "rh_pct": None if metar.rh_pct is None else round(metar.rh_pct, 1),
        "pressure_hpa": metar.qnh_hpa,
        "wind_speed_ms": metar.wind_speed_ms,
        "wind_dir_deg": metar.wind_dir_deg,
        "wind_gust_ms": metar.wind_gust_ms,
        "precip_mm": None,
        "precip_period_h": None,
        "visibility_m": metar.visibility_m,
        "cloud_cover_pct": metar.cloud_cover_pct,
        "present_weather": None if metar.present_weather is None else metar.present_weather[:64],
        "raw": {
            "source": source,
            "parser": PARSER_VERSION,
            "metar": metar.raw,
            "report_type": metar.report_type,
            "correction": metar.correction,
            "auto": metar.auto,
            "pressure_kind": "qnh",
            "wind_variable": metar.wind_variable,
            "visibility_ge_10km": metar.visibility_ge_10km,
            "visibility_min_m": metar.visibility_min_m,
            "cavok": metar.cavok,
            "clouds": [
                {"cover": c.cover, "base_m": c.base_m, "type": c.cloud_type} for c in metar.clouds
            ],
            "sky_clear": metar.sky_clear,
            "no_significant_cloud": metar.no_significant_cloud,
            "sky_obscured": metar.sky_obscured,
            "vertical_visibility_m": metar.vertical_visibility_m,
            "recent_weather": list(metar.recent_weather),
            "unparsed": list(metar.unparsed),
        },
    }
