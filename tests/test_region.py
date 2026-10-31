from pathlib import Path

from hava.region import load_region

CONFIG = Path(__file__).resolve().parents[1] / "config" / "region.istanbul.yaml"


def test_istanbul_region_has_39_districts_and_metar_stations() -> None:
    region = load_region(CONFIG)
    districts = [p for p in region.points if p.kind == "district"]
    stations = [p for p in region.points if p.kind == "station"]
    assert len({p.point_id.split(":")[1] for p in districts}) == 39
    assert {p.point_id for p in stations} == {
        "station:metar:LTFM",
        "station:metar:LTFJ",
        "station:metar:LTBA",
    }


def test_all_points_inside_region_bbox() -> None:
    region = load_region(CONFIG)
    for p in region.points:
        assert region.lat_min <= p.lat <= region.lat_max, p.point_id
        assert region.lon_min <= p.lon <= region.lon_max, p.point_id
