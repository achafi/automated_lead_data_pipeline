import math

import pytest

from map_utils import (DEMO_BBOX, bbox_from_geojson, build_map, latest_rectangle,
                       marker_popup, rectangle_geojson, sanitize_filename, validate_bbox,
                       valid_coordinates)
from overpass_client import parse_response


def test_extract_rectangle_and_reversed_ring():
    feature = rectangle_geojson(DEMO_BBOX)
    assert bbox_from_geojson(feature) == DEMO_BBOX
    feature["geometry"]["coordinates"][0].reverse()
    assert bbox_from_geojson(feature) == DEMO_BBOX


def test_missing_rectangle():
    with pytest.raises(ValueError, match="No rectangle"):
        bbox_from_geojson(None)


@pytest.mark.parametrize("feature", [{}, {"type": "Point", "coordinates": [0, 0]},
    {"type": "Polygon", "coordinates": [[[0,0],[1,1],[2,0],[0,0]]]},
    {"type": "Polygon", "coordinates": [[[0,0],[1,1],[0,1],[1,0],[0,0]]]},
    {"type": "Polygon", "coordinates": [[[0,0],[1,0],[1,1],[0,1],[0,2]]]}])
def test_invalid_geojson(feature):
    with pytest.raises(ValueError, match="Invalid rectangle"):
        bbox_from_geojson(feature)


@pytest.mark.parametrize("bbox", [(0,0,0,1), (2,0,1,1), (0,2,1,1), (-91,0,0,1),
    (0,-181,1,0), (0,0,91,1), (0,0,1,181), (0,0,math.nan,1), (0,0,math.inf,1),
    (False,0,1,1), ("0",0,1,1), (0,0,1), (0,170,1,-170), (0,-179,1,179)])
def test_invalid_bbox(bbox):
    with pytest.raises(ValueError, match="Invalid rectangle"):
        validate_bbox(bbox)


def test_area_limit_configurable():
    with pytest.raises(ValueError, match="selected region is too large"):
        validate_bbox((51,-1,52,0))
    assert validate_bbox(DEMO_BBOX) == DEMO_BBOX
    with pytest.raises(ValueError, match="selected region is too large"):
        validate_bbox(DEMO_BBOX, .1)


def test_latest_selection_and_deletion():
    first = rectangle_geojson(DEMO_BBOX)
    last = rectangle_geojson((51.50,-.14,51.51,-.13))
    assert latest_rectangle({"all_drawings": [first, last]}, first) == last
    assert latest_rectangle({"all_drawings": [], "last_active_drawing": first}, first) is None
    assert latest_rectangle({"all_drawings": None}, first) == first


@pytest.mark.parametrize("raw,expected", [("", "businesses.csv"), ("   ", "businesses.csv"),
    ("leads", "leads.csv"), ("leads.CSV", "leads.csv"), ("../../bad\\file:?.csv", "badfile.csv"),
    (".csv", "csv.csv"), ("CON", "_CON.csv"), ("a\x00b\nc", "abc.csv")])
def test_filename(raw, expected):
    assert sanitize_filename(raw) == expected


def test_safe_popup_and_map():
    frame = parse_response({"elements": [{"type":"node", "id":1, "lat":51.51, "lon":-.12,
        "tags":{"name":"<script>alert(`x`)</script>${alert(1)}", "website":"javascript:alert(1)"}}]}, "Dentists")
    popup = marker_popup(frame.iloc[0])
    assert "<script>" not in popup and "${" not in popup and "`" not in popup
    assert 'href="javascript:' not in popup
    markup = build_map(rectangle_geojson(DEMO_BBOX), frame).get_root().render()
    assert "clearLayers" in markup and '"polygon": false' in markup
    assert "openstreetmap.org/copyright" in markup and "markerClusterGroup" in markup


@pytest.mark.parametrize("lat,lon", [("", ""), (91,0), (0,181), (None,1), (math.nan,1)])
def test_invalid_marker_coordinates(lat, lon):
    assert not valid_coordinates(lat, lon)
