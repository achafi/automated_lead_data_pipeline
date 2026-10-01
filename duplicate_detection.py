"""Read-only potential duplicate detection for small OSM result sets."""
import math
from dataclasses import dataclass
import re
import unicodedata
from itertools import combinations
from urllib.parse import urlsplit

import pandas as pd
from rapidfuzz.fuzz import ratio

COLUMN_MAPPING = {
    "name": "Business name", "phone": "Phone", "website": "Website",
    "latitude": "Latitude", "longitude": "Longitude",
}


@dataclass(frozen=True)
class DuplicateThresholds:
    contact_distance_m: float = 500
    name_distance_m: float = 150
    name_similarity: float = 90

    def __post_init__(self):
        values = (self.contact_distance_m, self.name_distance_m, self.name_similarity)
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
            raise ValueError("Duplicate thresholds must be finite numbers.")
        if self.contact_distance_m <= 0 or self.name_distance_m <= 0:
            raise ValueError("Duplicate distance limits must be positive.")
        if not 0 < self.name_similarity <= 100:
            raise ValueError("Name similarity must be greater than 0 and at most 100.")


DEFAULT_THRESHOLDS = DuplicateThresholds()


def _text(value):
    return "" if value is None or pd.isna(value) else str(value).strip()


def normalize_name(value):
    text = unicodedata.normalize("NFKC", _text(value)).casefold()
    text = "".join(c for c in text if not unicodedata.category(c).startswith("P"))
    return " ".join(text.split())


def normalize_phone(value):
    return re.sub(r"[^0-9]", "", _text(value))


def normalize_website_domain(value):
    text = _text(value)
    if not text:
        return ""
    try:
        parsed = urlsplit(text if "://" in text or text.startswith("//") else "//" + text)
        if parsed.scheme and parsed.scheme.lower() not in {"http", "https"}:
            return ""
        host = (parsed.hostname or "").lower().rstrip(".")
        host = host.removeprefix("www.").encode("idna").decode("ascii")
        return host if re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)+", host) else ""
    except (ValueError, UnicodeError):
        return ""


def haversine_distance(lat1, lon1, lat2, lon2):
    """Distance in metres, or None if either coordinate pair is unavailable/invalid."""
    values = (lat1, lon1, lat2, lon2)
    if any(isinstance(v, bool) for v in values):
        return None
    try:
        a, b, c, d = map(float, values)
    except (ValueError, TypeError, OverflowError):
        return None
    if not all(math.isfinite(v) for v in (a, b, c, d)):
        return None
    if not (-90 <= a <= 90 and -90 <= c <= 90 and -180 <= b <= 180 and -180 <= d <= 180):
        return None
    lat1, lon1, lat2, lon2 = map(math.radians, (a, b, c, d))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371008.8 * 2 * math.asin(math.sqrt(max(0, min(1, h))))


def _prepare(record):
    return {
        "name": normalize_name(record.get(COLUMN_MAPPING["name"])),
        "phone": normalize_phone(record.get(COLUMN_MAPPING["phone"])),
        "website": normalize_website_domain(record.get(COLUMN_MAPPING["website"])),
        "latitude": record.get(COLUMN_MAPPING["latitude"]),
        "longitude": record.get(COLUMN_MAPPING["longitude"]),
    }


def _matches(left, right, thresholds=DEFAULT_THRESHOLDS):
    distance = haversine_distance(left["latitude"], left["longitude"], right["latitude"], right["longitude"])
    if distance is None or distance > max(thresholds.contact_distance_m, thresholds.name_distance_m):
        return False
    if distance <= thresholds.contact_distance_m and any(left[field] and left[field] == right[field] for field in ("phone", "website")):
        return True
    return bool(distance <= thresholds.name_distance_m and left["name"] and right["name"]
                and ratio(left["name"], right["name"]) >= thresholds.name_similarity)


def records_match(left, right, thresholds=DEFAULT_THRESHOLDS):
    """Compare two records using the explicit DataFrame column mapping."""
    return _matches(_prepare(left), _prepare(right), thresholds)


def find_duplicate_groups(frame, thresholds=DEFAULT_THRESHOLDS):
    """Return connected groups of row positions, omitting singletons.

    Positions keep separate rows distinct even when DataFrame index labels repeat.
    Normalized comparison copies never replace values in the input DataFrame.
    """
    records = [_prepare(row) for row in frame.to_dict("records")]
    parents = list(range(len(records)))

    def root(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    for i, j in combinations(range(len(records)), 2):
        if _matches(records[i], records[j], thresholds):
            parents[root(j)] = root(i)
    groups = {}
    for i in range(len(records)):
        groups.setdefault(root(i), []).append(i)
    return [group for group in groups.values() if len(group) > 1]


def duplicate_summary(frame, thresholds=DEFAULT_THRESHOLDS):
    groups = find_duplicate_groups(frame, thresholds)
    return {"group_count": len(groups), "affected_records": sum(map(len, groups))}


def pair_evidence(left, right, thresholds=DEFAULT_THRESHOLDS):
    """Explain an existing match without changing the matching rules.

    Confidence scores are display heuristics, not probabilities: phone 95,
    website 90, name-only 80; identical nonmissing OSM identity raises it to 100.
    """
    a, b = _prepare(left), _prepare(right)
    if not _matches(a, b, thresholds):
        return None
    distance = haversine_distance(a["latitude"], a["longitude"], b["latitude"], b["longitude"])
    evidence, scores = [], []
    if distance <= thresholds.contact_distance_m and a["phone"] and a["phone"] == b["phone"]:
        evidence.append("Phone numbers match")
        scores.append(95)
    if distance <= thresholds.contact_distance_m and a["website"] and a["website"] == b["website"]:
        evidence.append("Website domains match")
        scores.append(90)
    similarity = ratio(a["name"], b["name"]) if a["name"] and b["name"] else None
    if similarity is not None and similarity >= thresholds.name_similarity and distance <= thresholds.name_distance_m:
        evidence.append(f"Names are {similarity:.1f}% similar")
        scores.append(80)
    identity_fields = ("OpenStreetMap element type", "OpenStreetMap element ID")
    if all(_text(left.get(k)) and _text(left.get(k)) == _text(right.get(k)) for k in identity_fields):
        evidence.append("Same OpenStreetMap element type and ID")
        scores.append(100)
    score = max(scores)
    evidence.append(f"Locations are {distance:.0f} metres apart")
    return {"score": score, "confidence": "High confidence" if score >= 90 else "Possible duplicate",
            "evidence": evidence, "distance_metres": distance}
