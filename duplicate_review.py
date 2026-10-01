"""Pure review helpers; decisions create a copy and never alter collected records."""
import hashlib
from itertools import combinations

import pandas as pd

from duplicate_detection import DEFAULT_THRESHOLDS, find_duplicate_groups, pair_evidence

COLUMN_MAPPING = {
    "name": "Business name", "street": "Street", "house_number": "House number",
    "city": "City", "postcode": "Postcode", "country": "Country", "phone": "Phone",
    "website": "Website", "email": "Email", "opening_hours": "Opening hours",
    "latitude": "Latitude", "longitude": "Longitude",
    "osm_type": "OpenStreetMap element type", "osm_id": "OpenStreetMap element ID",
}
USEFUL_FIELDS = ("name", "street", "house_number", "city", "postcode", "country", "phone", "website", "email", "opening_hours")
KEEP_ALL = "Keep all records"
KEEP_RECOMMENDED = "Keep the recommended record only"
KEEP_SPECIFIC = "Keep a specific record"
DECISION_OPTIONS = [KEEP_ALL, KEEP_RECOMMENDED, KEEP_SPECIFIC]


def is_populated(value):
    return bool(value.strip()) if isinstance(value, str) else value is not None and not pd.isna(value)


def calculate_record_completeness(record):
    return sum(is_populated(record.get(COLUMN_MAPPING[key])) for key in USEFUL_FIELDS)


def record_identifier(position):
    return f"R{position + 1:04d}"


def recommend_record(frame, group):
    """Return the original row position, with deterministic completeness tie-breaks."""
    def priority(position):
        row = frame.iloc[position]
        return (calculate_record_completeness(row), is_populated(row.get(COLUMN_MAPPING["website"])),
                is_populated(row.get(COLUMN_MAPPING["phone"])), -position)
    return max(group, key=priority)


def recommendation_explanation(record):
    contacts = [label for key, label in (("website", "a website"), ("phone", "a telephone number"))
                if is_populated(record.get(COLUMN_MAPPING[key]))]
    extra = ", including " + " and ".join(contacts) if contacts else ""
    return f"Recommended because it contains {calculate_record_completeness(record)} populated fields{extra}."


def comparison_table(frame, group):
    rows = []
    for position in group:
        source = frame.iloc[position]
        def value(key):
            item = source.get(COLUMN_MAPPING[key], "")
            return item if is_populated(item) else ""
        rows.append({
            "Record identifier": record_identifier(position), "Business name": value("name"),
            "Address": ", ".join(str(value(k)) for k in ("house_number", "street", "city", "postcode", "country") if is_populated(value(k))),
            "Phone": value("phone"), "Website": value("website"), "Latitude": value("latitude"),
            "Longitude": value("longitude"), "Record completeness": f"{calculate_record_completeness(source)} / 10",
            "OpenStreetMap type": value("osm_type"), "OpenStreetMap ID": value("osm_id"),
        })
    return pd.DataFrame(rows)


def group_evidence(frame, group, thresholds=DEFAULT_THRESHOLDS):
    edges = []
    for i, j in combinations(group, 2):
        evidence = pair_evidence(frame.iloc[i], frame.iloc[j], thresholds)
        if evidence:
            edges.append({"left": i, "right": j, **evidence})
    return sorted(edges, key=lambda edge: -edge["score"])


def _validate_groups(frame, groups):
    seen = set()
    for group in groups:
        if len(group) < 2 or any(type(i) is not int or not 0 <= i < len(frame) for i in group):
            raise ValueError("Duplicate groups must contain at least two valid row positions.")
        if len(set(group)) != len(group) or seen.intersection(group):
            raise ValueError("Duplicate groups must not overlap. Use connected groups from the detector.")
        seen.update(group)


def apply_duplicate_decisions(df, groups, decisions):
    _validate_groups(df, groups)
    excluded = set()
    for number, group in enumerate(groups):
        decision = decisions.get(number, {"action": KEEP_ALL})
        action = decision.get("action", KEEP_ALL)
        if action == KEEP_ALL:
            continue
        if action == KEEP_RECOMMENDED:
            keep = recommend_record(df, group)
        elif action == KEEP_SPECIFIC:
            keep = decision.get("record")
            if type(keep) is not int or keep not in group:
                raise ValueError("Choose a record belonging to this duplicate group.")
        else:
            raise ValueError("Unknown duplicate decision.")
        excluded.update(i for i in group if i != keep)
    return df.iloc[[i for i in range(len(df)) if i not in excluded]].copy(deep=True)


def build_deduplication_summary(original_df, deduplicated_df, groups):
    return {"original": len(original_df), "groups_reviewed": len(groups),
            "excluded": len(original_df) - len(deduplicated_df), "final": len(deduplicated_df)}


def dataset_fingerprint(frame):
    data = frame.to_json(orient="split", date_format="iso", double_precision=15)
    return hashlib.sha256((data + repr(list(frame.dtypes.astype(str)))).encode()).hexdigest()


def sync_review_state(state, frame, thresholds=DEFAULT_THRESHOLDS):
    """Reset decisions and exports when data or matching thresholds change."""
    fingerprint = dataset_fingerprint(frame)
    review = state.get("duplicate_review")
    if review is None or review["fingerprint"] != fingerprint or review.get("thresholds") != thresholds:
        for key in list(state):
            if key.startswith(("duplicate_choice_", "duplicate_record_", "fill_confirm_")):
                del state[key]
        groups = find_duplicate_groups(frame, thresholds)
        review = {"fingerprint": fingerprint, "thresholds": thresholds, "groups": groups, "decisions": {},
                  "evidence": [group_evidence(frame, group, thresholds) for group in groups]}
        state["duplicate_review"] = review
    return review
