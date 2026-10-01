from urllib.parse import parse_qs

import httpx
import pytest

from categories import CATEGORY_TAGS
from map_utils import DEMO_BBOX
from overpass_client import (COLUMNS, OVERPASS_URL, OverpassError, build_query,
                             collect_businesses, parse_response)


def element(kind="node", **tags):
    return {"type":kind, "id":123, **({"lat":51.51,"lon":-.12} if kind=="node" else {"center":{"lat":51.51,"lon":-.12}}), "tags":tags}


def run(handler, maximum=50):
    return collect_businesses("Dentists", DEMO_BBOX, maximum, transport=httpx.MockTransport(handler))


@pytest.mark.parametrize("category,tag", [("Dentists",("amenity","dentist")), ("Pharmacies",("amenity","pharmacy")),
    ("Restaurants",("amenity","restaurant")), ("Cafés",("amenity","cafe")), ("Hotels",("tourism","hotel"))])
def test_categories_and_queries(category, tag):
    assert CATEGORY_TAGS[category] == tag
    query = build_query(category, DEMO_BBOX, 50)
    for kind in ("node", "way", "relation"):
        assert f'{kind}["{tag[0]}"="{tag[1]}"](51.505,-0.14,51.52,-0.115);' in query
    assert "[timeout:25]" in query
    assert query.endswith("out body center 50;")


def test_request_and_response():
    def handler(request):
        assert request.method == "POST" and str(request.url) == OVERPASS_URL
        assert parse_qs(request.content.decode())["data"] == [build_query("Dentists", DEMO_BBOX)]
        assert request.extensions["timeout"]["read"] == 35
        return httpx.Response(200, json={"elements":[element(name="Example Dental")]})
    frame = run(handler)
    assert list(frame.columns) == COLUMNS
    assert frame.iloc[0]["Business name"] == "Example Dental"


@pytest.mark.parametrize("kind", ["node","way","relation"])
def test_coordinates(kind):
    row = parse_response({"elements":[element(kind)]}, "Dentists").iloc[0]
    assert row["Latitude"] == 51.51 and row["Longitude"] == -.12
    assert row["OpenStreetMap element type"] == kind
    assert row["OpenStreetMap URL"] == f"https://www.openstreetmap.org/{kind}/123"
    assert row["Data source"] == "OpenStreetMap contributors"


def test_missing_optional_fields():
    row = parse_response({"elements":[{"type":"way","id":1}]}, "Hotels").iloc[0]
    assert all(row[c] == "" for c in ["Business name", "Latitude", "Longitude", "Phone", "Website", "Opening hours", "City"])


def test_tags_and_fallback():
    tags = {"name":"Example", "addr:street":"Lane", "addr:housenumber":"7", "addr:city":"London",
        "addr:postcode":"ABC", "addr:country":"GB", "phone":"primary", "contact:phone":"fallback",
        "contact:website":"https://example.com", "email":"", "contact:email":"hi@example.com", "opening_hours":"24/7"}
    row = parse_response({"elements":[element(**tags)]}, "Dentists").iloc[0]
    assert row["Phone"] == "primary"
    assert row["Website"] == "https://example.com" and row["Email"] == "hi@example.com"
    assert [row[k] for k in ["Street","House number","City","Postcode","Country","Opening hours"]] == ["Lane","7","London","ABC","GB","24/7"]


def test_maximum_preserves_duplicate_elements():
    frame = run(lambda r: httpx.Response(200,json={"elements":[element()] * 8}), 3)
    assert len(frame) == 3


def test_empty():
    frame = run(lambda r: httpx.Response(200,json={"elements":[]}))
    assert frame.empty and list(frame.columns) == COLUMNS


@pytest.mark.parametrize("maximum", [0,-1,201,1.5,True,"50"])
def test_invalid_maximum(maximum):
    with pytest.raises(ValueError, match="whole number"):
        run(lambda r: pytest.fail("Must not request"), maximum)


def test_reject_arbitrary_category():
    with pytest.raises(ValueError, match="supported"):
        build_query('amenity";node;', DEMO_BBOX)


@pytest.mark.parametrize("status,match", [(429,"rate limiting"), (500,"server"), (502,"server"), (504,"timed out"), (400,"could not accept")])
def test_http_errors(status,match):
    with pytest.raises(OverpassError,match=match):
        run(lambda r: httpx.Response(status,text="Sensitive raw server details"))


@pytest.mark.parametrize("error,match", [(httpx.ReadTimeout,"timed out"),(httpx.ConnectError,"Could not reach")])
def test_network_errors(error,match):
    calls=[]
    def handler(request):
        calls.append(request)
        raise error("raw details",request=request)
    with pytest.raises(OverpassError,match=match):
        run(handler)
    assert len(calls)==1


def test_invalid_json():
    with pytest.raises(OverpassError,match="invalid JSON"):
        run(lambda r:httpx.Response(200,text="not JSON"))


@pytest.mark.parametrize("payload", [{}, [], {"elements":{}}, {"elements":[None]}, {"elements":[{"id":1,"type":"invalid"}]}, {"elements":[element(name={})]}])
def test_unexpected_response(payload):
    with pytest.raises(OverpassError,match="unexpected"):
        run(lambda r:httpx.Response(200,json=payload))


def test_runtime_timeout_is_not_empty_success():
    with pytest.raises(OverpassError,match="timed out"):
        run(lambda r:httpx.Response(200,json={"elements":[],"remark":"runtime error: Query timed out"}))


def test_partial_failure_is_not_success():
    with pytest.raises(OverpassError,match="could not finish"):
        run(lambda r:httpx.Response(200,json={"elements":[element()],"remark":"out of memory"}))
