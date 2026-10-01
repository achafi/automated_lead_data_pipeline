"""Bounded Overpass requests and direct OSM-to-table mapping."""
import httpx
import pandas as pd

from categories import CATEGORY_TAGS
from map_utils import DEFAULT_MAX_AREA_KM2, validate_bbox

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
COLUMNS = ["Business name", "Selected category", "Latitude", "Longitude", "Street", "House number",
           "City", "Postcode", "Country", "Phone", "Website", "Email", "Opening hours",
           "OpenStreetMap element type", "OpenStreetMap element ID", "OpenStreetMap URL", "Data source"]


class OverpassError(Exception):
    """Safe, user-facing API error."""


def validate_maximum(maximum):
    if type(maximum) is not int or not 1 <= maximum <= 200:
        raise ValueError("Maximum results must be a whole number between 1 and 200.")


def build_query(category, bbox, maximum=50, max_area_km2=DEFAULT_MAX_AREA_KM2):
    validate_maximum(maximum)
    if category not in CATEGORY_TAGS:
        raise ValueError("Choose one of the supported business categories.")
    bbox = validate_bbox(bbox, max_area_km2)
    key, value = CATEGORY_TAGS[category]
    bounds = ",".join(str(v) for v in bbox)
    statements = "\n".join(f'  {kind}["{key}"="{value}"]({bounds});' for kind in ("node", "way", "relation"))
    # body includes node coordinates; tags-only output can omit node lat/lon.
    # The output limit bounds transfer size, not the server's search work.
    return f"[out:json][timeout:25][maxsize:16777216];\n(\n{statements}\n);\nout body center {maximum};"


def parse_response(payload, category, maximum=50):
    validate_maximum(maximum)
    if category not in CATEGORY_TAGS:
        raise ValueError("Choose one of the supported business categories.")
    if not isinstance(payload, dict):
        raise OverpassError("Overpass returned an unexpected response format. Please try again later.")
    if payload.get("remark"):
        if "timed out" in str(payload["remark"]).lower() or "timeout" in str(payload["remark"]).lower():
            raise OverpassError("Overpass timed out. Draw a smaller rectangle or try again later.")
        raise OverpassError("Overpass could not finish the search. Draw a smaller rectangle or try again later.")
    elements = payload.get("elements")
    if not isinstance(elements, list):
        raise OverpassError("Overpass returned an unexpected response format. Please try again later.")
    rows = []
    for element in elements[:maximum]:
        if not isinstance(element, dict):
            raise OverpassError("Overpass returned an unexpected element format.")
        kind, ident = element.get("type"), element.get("id")
        tags = element.get("tags", {})
        coords = element if kind == "node" else element.get("center", {})
        if (kind not in {"node", "way", "relation"} or type(ident) is not int or ident <= 0
                or not isinstance(tags, dict) or not isinstance(coords, dict)
                or any(not isinstance(v, str) for v in tags.values())):
            raise OverpassError("Overpass returned an unexpected element format.")
        rows.append([
            tags.get("name", ""), category, coords.get("lat", ""), coords.get("lon", ""),
            *[tags.get(f"addr:{key}", "") for key in ("street", "housenumber", "city", "postcode", "country")],
            *[tags.get(key) or tags.get(f"contact:{key}", "") for key in ("phone", "website", "email")],
            tags.get("opening_hours", ""), kind, ident,
            f"https://www.openstreetmap.org/{kind}/{ident}", "OpenStreetMap contributors",
        ])
    frame = pd.DataFrame(rows, columns=COLUMNS, dtype=object)
    return frame.where(frame.notna(), "")


def collect_businesses(category, bbox, maximum=50, max_area_km2=DEFAULT_MAX_AREA_KM2, *, transport=None):
    query = build_query(category, bbox, maximum, max_area_km2)
    try:
        with httpx.Client(timeout=httpx.Timeout(35, connect=10), transport=transport,
                          headers={"User-Agent": "MapBasedBusinessDataCollector/0.2 (portfolio demonstration)"}) as client:
            response = client.post(OVERPASS_URL, data={"data": query})
    except httpx.TimeoutException:
        raise OverpassError("Overpass timed out. Draw a smaller rectangle or try again later.") from None
    except httpx.RequestError:
        raise OverpassError("Could not reach Overpass. Check your connection and try again later.") from None
    if response.status_code == 429:
        raise OverpassError("Overpass is rate limiting requests. Please wait before trying again.")
    if response.status_code in (408, 504):
        raise OverpassError("Overpass timed out. Draw a smaller rectangle or try again later.")
    if response.status_code >= 500:
        raise OverpassError("The Overpass server is temporarily unavailable. Please try again later.")
    if not response.is_success:
        raise OverpassError("Overpass could not accept the search. Please try a smaller rectangle later.")
    try:
        payload = response.json()
    except ValueError:
        raise OverpassError("Overpass returned invalid JSON. Please try again later.") from None
    return parse_response(payload, category, maximum)
