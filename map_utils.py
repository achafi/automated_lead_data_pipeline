"""Rectangle geometry, safe presentation, and map construction."""
import html
import math
import re
from urllib.parse import urlsplit

import folium
from branca.element import MacroElement, Template
from folium.plugins import Draw, MarkerCluster

DEFAULT_MAX_AREA_KM2 = 25.0
DEMO_BBOX = (51.505, -0.14, 51.52, -0.115)
TOO_LARGE = "The selected region is too large for this demonstration. Draw a smaller rectangle and try again."


def valid_coordinates(lat, lon):
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
               for v in (lat, lon)) and -90 <= lat <= 90 and -180 <= lon <= 180


def validate_bbox(bbox, max_area_km2=DEFAULT_MAX_AREA_KM2):
    if not isinstance(bbox, (tuple, list)) or len(bbox) != 4:
        raise ValueError("Invalid rectangle. Draw a new rectangle on the map.")
    south, west, north, east = bbox
    if not (valid_coordinates(south, west) and valid_coordinates(north, east)):
        raise ValueError("Invalid rectangle coordinates. Draw within the world map bounds.")
    if south >= north or west >= east or east - west > 180:
        raise ValueError("Invalid rectangle. Zero-size and date-line-crossing regions are not supported.")
    if not math.isfinite(max_area_km2) or max_area_km2 <= 0:
        raise ValueError("MAX_RECTANGLE_AREA_KM2 must be a positive finite number.")
    # Spherical rectangle area, using Earth's mean radius in kilometres.
    area = 6371.0088 ** 2 * math.radians(east - west) * abs(
        math.sin(math.radians(north)) - math.sin(math.radians(south)))
    if area > max_area_km2:
        raise ValueError(TOO_LARGE)
    return tuple(float(v) for v in bbox)


def bbox_from_geojson(feature, max_area_km2=DEFAULT_MAX_AREA_KM2):
    if feature is None:
        raise ValueError("No rectangle selected. Draw a rectangle on the map first.")
    try:
        geometry = feature["geometry"] if feature.get("type") == "Feature" else feature
        rings = geometry["coordinates"]
        if geometry["type"] != "Polygon" or len(rings) != 1:
            raise ValueError
        ring = rings[0]
        if len(ring) != 5 or ring[0] != ring[-1]:
            raise ValueError
        if any(len(p) != 2 or not valid_coordinates(p[1], p[0]) for p in ring):
            raise ValueError
        west, east = min(p[0] for p in ring), max(p[0] for p in ring)
        south, north = min(p[1] for p in ring), max(p[1] for p in ring)
        if set(map(tuple, ring[:-1])) != {(west, south), (west, north), (east, south), (east, north)}:
            raise ValueError
        if any(a[0] != b[0] and a[1] != b[1] for a, b in zip(ring, ring[1:])):
            raise ValueError
    except (KeyError, TypeError, IndexError, AttributeError, ValueError):
        raise ValueError("Invalid rectangle. Draw a new rectangle on the map.") from None
    return validate_bbox((south, west, north, east), max_area_km2)


def rectangle_geojson(bbox):
    south, west, north, east = bbox
    return {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [
        [[west, south], [east, south], [east, north], [west, north], [west, south]]
    ]}}


def latest_rectangle(map_data, previous=None):
    # all_drawings=[] means deletion. last_active_drawing can remain stale.
    drawings = (map_data or {}).get("all_drawings")
    if drawings is None:
        return previous
    return drawings[-1] if drawings else None


def sanitize_filename(value):
    stem = re.sub(r"[^\w .-]", "", value or "", flags=re.UNICODE).strip(" .")
    if stem.lower().endswith(".csv"):
        stem = stem[:-4].strip(" .")
    stem = stem[:100].strip(" .") or "businesses"
    if stem.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]}:
        stem = "_" + stem
    return stem + ".csv"


def marker_popup(row, demo=False):
    def esc(value):
        # Also escape backticks and $: Folium embeds HTML in JS template literals.
        return html.escape(str(value), quote=True).replace("`", "&#96;").replace("$", "&#36;")
    parts = [f"<strong>{esc(row['Business name'] or 'Unnamed business')}</strong>", esc(row["Selected category"])]
    address = " ".join(str(row[k]) for k in ("House number", "Street", "City", "Postcode", "Country") if row[k] != "")
    if address:
        parts.append(esc(address))
    website = str(row["Website"])
    if website:
        try:
            parsed = urlsplit(website)
            safe = parsed.scheme in {"https", "http"} and bool(parsed.netloc)
        except ValueError:
            safe = False
        parts.append(f'<a href="{esc(website)}" target="_blank" rel="noopener noreferrer">Website</a>' if safe else esc(website))
    if row["OpenStreetMap URL"]:
        parts.append(f'<a href="{esc(row["OpenStreetMap URL"])}" target="_blank" rel="noopener noreferrer">OpenStreetMap</a>')
    if demo:
        parts.append("Demonstration data · fictional business")
    return "<br>".join(parts)


def build_map(seed=None, frame=None, demo=False):
    m = folium.Map(location=[51.5125, -0.1275], zoom_start=14, tiles="OpenStreetMap")
    selection = folium.FeatureGroup(name="Search rectangle").add_to(m)
    if seed:
        # Geometry has already been checked; allow displaying an oversized selection
        # so users can see what to replace when the collection guard rejects it.
        south, west, north, east = bbox_from_geojson(seed, float(1e12))
        folium.Rectangle([[south, west], [north, east]], color="#2563eb", fill=True, fill_opacity=.08).add_to(selection)
        m.fit_bounds([[south, west], [north, east]])
    # Register before Draw's created handlers so only the newest rectangle remains.
    single = MacroElement()
    single._template = Template("""{% macro script(this, kwargs) %}
    {{this._parent.get_name()}}.on('draw:created', function(e) {
        {{this.group.get_name()}}.clearLayers();
    });
    {% endmacro %}""")
    single.group = selection
    single.add_to(m)
    Draw(feature_group=selection, show_geometry_on_click=False,
         draw_options={"rectangle": True, "polyline": False, "polygon": False,
                       "circle": False, "circlemarker": False, "marker": False},
         edit_options={"edit": False, "remove": True}).add_to(m)
    cluster = MarkerCluster(name="Businesses").add_to(m)
    if frame is not None:
        for row in frame.to_dict("records"):
            if valid_coordinates(row["Latitude"], row["Longitude"]):
                folium.Marker([row["Latitude"], row["Longitude"]],
                              popup=folium.Popup(marker_popup(row, demo), max_width=320)).add_to(cluster)
    return m
