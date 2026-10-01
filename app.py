"""Map-Based Business Data Collector: select, collect, preview, download."""
import json
import os
import math
from pathlib import Path

import streamlit as st
from streamlit_folium import st_folium

from duplicate_detection import DuplicateThresholds, find_duplicate_groups
from duplicate_review import (
    DECISION_OPTIONS, KEEP_ALL, KEEP_RECOMMENDED, KEEP_SPECIFIC,
    apply_duplicate_decisions, build_deduplication_summary, comparison_table,
    recommend_record, recommendation_explanation, record_identifier, sync_review_state,
)
from data_validation import validate_records, issue_counts
from data_completion import deduplicate_and_complete
from data_cleaning import CleaningOptions, clean_records
from data_summary import summarize_records
from categories import CATEGORY_TAGS
from map_utils import (DEFAULT_MAX_AREA_KM2, DEMO_BBOX, bbox_from_geojson, build_map,
                       latest_rectangle, rectangle_geojson, sanitize_filename)
from overpass_client import OverpassError, collect_businesses, parse_response, validate_maximum

st.set_page_config(page_title="Map-Based Business Data Collector", page_icon="📍", layout="wide")
st.markdown("""
<style>
.st-key-original_export button {min-height: 3.5rem;}
.st-key-original_export button p {font-size: 1.1rem; font-weight: 600;}
</style>
""", unsafe_allow_html=True)
st.title("Map-Based Business Data Collector")

try:
    max_area = float(os.environ.get("MAX_RECTANGLE_AREA_KM2", DEFAULT_MAX_AREA_KM2))
    if not math.isfinite(max_area) or max_area <= 0:
        raise ValueError
except (ValueError, TypeError):
    st.error("MAX_RECTANGLE_AREA_KM2 must be a positive finite number.")
    st.stop()


def reset_duplicate_thresholds():
    st.session_state.contact_distance = 500
    st.session_state.name_distance = 150
    st.session_state.name_similarity = 90




@st.cache_data(ttl=300, max_entries=32, show_spinner=False)
def cached_search(category, bbox, maximum, area_limit):
    # Exceptions are not cached. Only explicitly submitted searches reach here.
    return collect_businesses(category, bbox, maximum, area_limit)


def reset_selection():
    seed = rectangle_geojson(DEMO_BBOX) if st.session_state.get("demo", False) else None
    st.session_state.selection = seed
    st.session_state.map_seed = seed
    st.session_state.pop("results", None)
    st.session_state.pop("error", None)
    st.session_state.revision = st.session_state.get("revision", 0) + 1


if "selection" not in st.session_state:
    reset_selection()

with st.sidebar:
    st.header("Search settings")
    st.checkbox("Use demo data", key="demo", on_change=reset_selection,
                help="Fictional sample businesses in a predefined London rectangle; no Overpass requests.")
    category = st.selectbox("Business category", list(CATEGORY_TAGS), key="business_category")
    maximum = st.number_input("Maximum results", value=50, step=1, help="Whole number from 1 to 200.")
    filename = st.text_input("CSV filename (optional)", placeholder="businesses.csv")
    st.divider()

# Preserve settings even when their widgets are hidden by Streamlit.
for key, default in (("contact_distance", 500), ("name_distance", 150), ("name_similarity", 90)):
    st.session_state[key] = st.session_state.get(key, default)
thresholds = DuplicateThresholds(st.session_state.contact_distance,
                                st.session_state.name_distance, st.session_state.name_similarity)
current_result = st.session_state.get("results")
has_duplicates = current_result is not None and bool(find_duplicate_groups(current_result["frame"], thresholds))
with st.sidebar:
    if st.session_state.demo:
        st.caption("Demo mode: fictional records in a fixed London rectangle.")
    st.caption(f"Maximum region: {max_area:g} km². Only the newest rectangle is used.")
    if has_duplicates:
        st.header("Duplicate detection settings")
        st.slider("Phone / website distance (metres)", 25, 2000, step=25, key="contact_distance")
        st.slider("Similar-name distance (metres)", 25, 1000, step=25, key="name_distance")
        st.slider("Minimum name similarity (%)", 70, 100, step=1, key="name_similarity")
        st.caption("Changes reset review decisions. No additional API requests are made.")

st.caption("Move and zoom the map, then draw one rectangle around the region you want to search.")

# Fill this after processing the map and search so the summary reflects current state.
results_overview = st.container()
result = st.session_state.get("results")
m = build_map(st.session_state.map_seed, result["frame"] if result else None,
              result["demo"] if result else False)
map_data = st_folium(m, key=f"search_map_{st.session_state.revision}", height=500,
                     use_container_width=True, returned_objects=["all_drawings"])
st.session_state.selection = latest_rectangle(map_data, st.session_state.selection)

if st.button("Clear selection"):
    reset_selection()
    st.session_state.selection = None
    st.session_state.map_seed = None
    st.rerun()
if has_duplicates or thresholds != DuplicateThresholds():
    st.button("Reset matching defaults", on_click=reset_duplicate_thresholds)

bbox = None
selection_error = None
try:
    bbox = bbox_from_geojson(st.session_state.selection, max_area)
    st.sidebar.caption("Selected region: " + ", ".join(f"{v:.4f}" for v in bbox))
except ValueError as exc:
    selection_error = str(exc)
    if st.session_state.selection is not None:
        st.warning(selection_error)

_, collect_column, _ = st.columns([1, 2, 1])
if collect_column.button("Collect Data", type="primary", width="stretch"):
    st.session_state.pop("results", None)
    st.session_state.pop("error", None)
    try:
        validate_maximum(maximum)
        if selection_error:
            raise ValueError(selection_error)
        with st.spinner("Collecting business records…"):
            if st.session_state.demo:
                fixture = json.loads((Path(__file__).parent / "sample_data/demo_businesses.json").read_text())
                key, value = CATEGORY_TAGS[category]
                elements = [e for e in fixture["elements"] if e.get("tags", {}).get(key) == value]
                frame = parse_response({"elements": elements}, category, maximum)
                # Fictional IDs must never link to unrelated real OSM elements.
                frame["OpenStreetMap element ID"] = ""
                frame["OpenStreetMap URL"] = ""
                frame["Data source"] = "Demonstration data (fictional)"
                bbox = DEMO_BBOX
                st.session_state.selection = rectangle_geojson(DEMO_BBOX)
            else:
                frame = cached_search(category, bbox, maximum, max_area)
        st.session_state.results = {"frame": frame, "category": category, "bbox": bbox,
                                    "demo": st.session_state.demo, "maximum": maximum}
        if st.session_state.demo:
            st.session_state.results["demo_scenarios"] = fixture.get("scenarios", [])
        st.session_state.map_seed = st.session_state.selection
        st.session_state.revision += 1
        st.rerun()
    except (ValueError, OverpassError) as exc:
        st.session_state.error = str(exc)
    except Exception:
        st.session_state.error = "Could not display the records. Please try again or check the local demo file."
    # Rebuild without old markers after a failed collection.
    st.session_state.map_seed = st.session_state.selection if bbox else None
    st.session_state.revision += 1
    st.rerun()

if "error" in st.session_state:
    st.error(st.session_state.error)

result = st.session_state.get("results")
if result:
    frame = result["frame"]
    with results_overview:
        if result["demo"]:
            st.info("Demonstration data — fictional businesses, not actual OpenStreetMap listings.")
        if category != result["category"] or bbox != result["bbox"]:
            st.warning("The selection has changed. These results belong to the previous search; click Collect Data to update them.")
        if result.get("demo_scenarios"):
            with st.expander("Demo scenario guide"):
                st.write("This fixture intentionally contains duplicate candidates, formatting problems, and invalid or missing data.")
                st.caption("Use at least 20 results and default matching settings to see every case. Expected: 3 duplicate groups, 7 affected records; "
                           "keeping all recommendations excludes 4 records. Validation flags issues but does not remove records. "
                           "Records with invalid or missing coordinates remain in the table and CSV but have no map marker.")
                st.dataframe(result["demo_scenarios"], hide_index=True, width="stretch")
        st.write(f"Records returned: {len(frame)}")
        st.write(f"Category: {result['category']}")
        st.caption("Search bounding box (south, west, north, east): " + ", ".join(f"{v:.6f}" for v in result["bbox"]))
    review = sync_review_state(st.session_state, frame, thresholds)
    groups = review["groups"]
    summary = summarize_records(frame)
    if summary is not None:
        cards = st.columns(5)
        cards[0].metric("Businesses collected", summary["total"])
        for card, label, name in zip(cards[1:4],
                ("With contact information", "Website present", "Complete address"),
                ("contact", "website", "address")):
            values = summary[name]
            card.metric(label, f"{values['count']} / {summary['total']}",
                        delta=f"{values['percentage']:.1f}%", delta_color="off", delta_arrow="off")
        duplicates = {"group_count": len(groups), "affected_records": sum(map(len, groups))}
        cards[4].metric("Potential duplicate groups", duplicates["group_count"])
        cards[4].caption(f"{duplicates['affected_records']} records affected"
                         if duplicates["group_count"] else "No potential duplicates")
        st.caption('“Website present” means the website was available in the collected OpenStreetMap data. '
                   'A missing value does not prove that the business has no website.')
    if frame.empty:
        st.info("No businesses found. Try another category or draw a different rectangle.")
    else:
        if len(frame) == result["maximum"]:
            st.caption("Result limit reached; more matching OSM elements may exist in this region.")
        st.dataframe(frame, hide_index=True, width="stretch")
        export_name = sanitize_filename(filename)
        if result["demo"]:
            export_name = "demo_" + export_name
        _, export_column, _ = st.columns([1, 2, 1])
        with export_column:
            with st.container(key="original_export"):
                st.download_button("Download original CSV", frame.to_csv(index=False).encode("utf-8-sig"),
                                   file_name=export_name, mime="text/csv", type="primary", width="stretch")
    if not frame.empty:
        with st.sidebar:
            st.subheader("Data Cleaning")
            st.caption("Applied automatically when you create results.")
            options = CleaningOptions(
                name_address_spaces=st.checkbox("Remove extra spaces from names and address fields", value=True, key="clean_name_spaces"),
                missing_values=st.checkbox("Convert missing and whitespace-only values to blanks", value=True, key="clean_missing"),
                contact_spaces=st.checkbox("Remove surrounding spaces from phones, websites, and emails", value=True, key="clean_contact_spaces"),
                country_codes=st.checkbox("Standardize known country names to country codes", value=True, key="clean_countries"),
            )
            st.subheader("Data Validation")
            validation_enabled = st.checkbox("Check resulting data for invalid values", value=True, key="validate_output")
            st.caption("Checks coordinates, websites, emails and phones. Missing values are not errors. Flagged records are retained.")
        if review.get("processing_options") != (options, validation_enabled):
            review.pop("deduplicated", None)
            review["processing_options"] = (options, validation_enabled)
    if not groups:
        st.success("No potential duplicate groups were detected.")
    else:
        st.subheader("Potential Duplicate Review")
        st.write("Review only the groups flagged by the matching algorithm. The original collected data remains unchanged.")
        st.caption("Confidence is a rule-based indicator, not a probability: matching phone 95, website 90, "
                   "name-only 80, identical OSM identity 100. Groups show the highest pair confidence. "
                   "Connected records need not all match one another directly.")
        st.caption("Recommendations prefer populated useful fields, then website, then phone, then original order.")
        bulk, reset = st.columns(2)
        if bulk.button("Use all recommendations"):
            for number in range(len(groups)):
                review["decisions"][number] = {"action": KEEP_RECOMMENDED}
                st.session_state[f"duplicate_choice_{number}"] = KEEP_RECOMMENDED
            review.pop("deduplicated", None)
            count = len(frame) - len(apply_duplicate_decisions(frame, groups, review["decisions"]))
            st.info(f"Recommendations selected: {count} records would be excluded. Click Create deduplicated results to generate the separate export.")
        if reset.button("Reset duplicate decisions"):
            review["decisions"] = {}
            review.pop("deduplicated", None)
            for number in range(len(groups)):
                st.session_state[f"duplicate_choice_{number}"] = KEEP_ALL
            st.info("All groups are set to Keep all records.")
        for number, group in enumerate(groups):
            evidence = review["evidence"][number]
            strongest = evidence[0]
            recommended = recommend_record(frame, group)
            with st.expander(f"Group {number + 1} · {len(group)} records · {strongest['confidence']}"):
                st.write(f"Highest match confidence: {strongest['confidence']} ({strongest['score']}/100)")
                st.write(f"Strongest supporting pair: {record_identifier(strongest['left'])} and {record_identifier(strongest['right'])}")
                st.markdown("\n".join("- " + reason for reason in strongest["evidence"]))
                if len(group) > 2:
                    st.write("Pair-level matching evidence")
                    st.dataframe([{"Pair": f"{record_identifier(edge['left'])} – {record_identifier(edge['right'])}",
                                   "Confidence": edge["confidence"], "Score": edge["score"],
                                   "Evidence": "; ".join(edge["evidence"])} for edge in evidence],
                                 hide_index=True, width="stretch")
                st.dataframe(comparison_table(frame, group), hide_index=True, width="stretch")
                st.write(f"Recommended record: {record_identifier(recommended)}")
                st.caption(recommendation_explanation(frame.iloc[recommended]))
                old = review["decisions"].get(number, {"action": KEEP_ALL})
                choice_key = f"duplicate_choice_{number}"
                if choice_key not in st.session_state:
                    st.session_state[choice_key] = old["action"]
                action = st.selectbox(f"Decision for group {number + 1}", DECISION_OPTIONS, key=choice_key)
                decision = {"action": action}
                if action == KEEP_SPECIFIC:
                    record_key = f"duplicate_record_{number}"
                    if record_key not in st.session_state:
                        st.session_state[record_key] = old.get("record", recommended)
                    chosen = st.selectbox(f"Record to retain in group {number + 1}", group,
                        format_func=lambda i: f"{record_identifier(i)} · {frame.iloc[i].get('Business name', '')}",
                        key=record_key)
                    decision["record"] = chosen
                if decision != old:
                    review.pop("deduplicated", None)
                review["decisions"][number] = decision
        st.info("Keeping the recommended record or a specific record also fills its missing fields from the other records in that group when you create results. "
                "Keep all records leaves the group unchanged. Existing values are never overwritten; conflicting values and invalid contact formats are skipped.")
    if not frame.empty:
        st.caption("Create results applies your duplicate decisions, fills agreed missing fields, applies the sidebar cleaning options, and checks the result. Original records stay unchanged.")
        action_label = "Create deduplicated results" if groups else "Create processed results"
        if st.button(action_label, type="primary"):
            review["deduplicated"], review["fill_report"] = deduplicate_and_complete(frame, groups, review["decisions"])
            review["cleaned"] = clean_records(review["deduplicated"], options)
            kept = apply_duplicate_decisions(frame.reset_index(drop=True), groups, review["decisions"]).index.tolist()
            if validation_enabled:
                review["validation_report"] = validate_records(review["cleaned"][0], [record_identifier(i) for i in kept])
            else:
                review.pop("validation_report", None)
        if "deduplicated" not in review:
            review.pop("cleaned", None)
            review.pop("validation_report", None)
        if "deduplicated" in review and "cleaned" in review:
            final, changed = review["cleaned"]
            st.subheader("Final results")
            counts = build_deduplication_summary(frame, final, groups)
            st.write(f"Original: {counts['original']} · Excluded: {counts['excluded']} · Final: {counts['final']} · Records formatted: {changed}")
            st.caption("This preview and CSV include the selected cleaning options. Validation flags issues without removing records.")
            st.dataframe(final, hide_index=True, width="stretch")
            st.download_button("Download deduplicated CSV" if groups else "Download processed CSV",
                               final.to_csv(index=False).encode("utf-8-sig"),
                               file_name=export_name[:-4] + ("_deduplicated.csv" if groups else "_processed.csv"), mime="text/csv")
            fill_report = review["fill_report"]
            if not fill_report.empty:
                st.write(f"Fields filled from duplicate records: {len(fill_report[fill_report['Status'] == 'Filled'])}")
                st.dataframe(fill_report, hide_index=True, width="stretch")
                st.download_button("Download fill report", fill_report.to_csv(index=False).encode("utf-8-sig"),
                                   file_name=export_name[:-4] + "_fill_report.csv", mime="text/csv")
            if "validation_report" in review:
                report = review["validation_report"]
                st.subheader("Validation results")
                if report.empty:
                    st.success("No issues found by these checks.")
                else:
                    st.warning(f"{report['Record identifier'].nunique()} records flagged · {len(report)} field issues. These records remain in the export.")
                    st.dataframe(issue_counts(report), hide_index=True, width="stretch")
                    st.dataframe(report, hide_index=True, width="stretch")
                st.download_button("Download validation report", report.to_csv(index=False).encode("utf-8-sig"),
                                   file_name=export_name[:-4] + "_validation.csv", mime="text/csv")
st.caption("Data © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright)")
st.caption("OpenStreetMap coverage varies. Missing details stay blank. Public Overpass is a shared service; keep searches small and occasional.")
