import io

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from duplicate_detection import find_duplicate_groups, pair_evidence
from duplicate_review import (
    KEEP_ALL, KEEP_RECOMMENDED, KEEP_SPECIFIC, apply_duplicate_decisions,
    build_deduplication_summary, calculate_record_completeness, comparison_table,
    group_evidence, recommend_record, sync_review_state,
)


def test_completeness_missing_fields():
    assert calculate_record_completeness({"Business name":"A", "Website":" ", "Phone":None,
        "City":float("nan"), "Street":pd.NA, "Postcode":0, "Country":False}) == 3
    assert calculate_record_completeness({}) == 0


@pytest.mark.parametrize("rows,expected", [
    ([{"Business name":"A"}, {"Business name":"B", "Street":"Main"}], 1),
    ([{"Phone":"1"}, {"Website":"example.com"}], 1),
    ([{"City":"Paris"}, {"Phone":"1"}], 1),
    ([{"Phone":"1"}, {"Phone":"2"}], 0),
])
def test_recommendation_tie_breakers(rows, expected):
    frame = pd.DataFrame(rows)
    assert recommend_record(frame, [1, 0]) == expected


@pytest.fixture
def frame():
    return pd.DataFrame([
        {"Business name":"A", "Phone":"123", "Latitude":0, "Longitude":0},
        {"Business name":"B", "Phone":"123", "Website":"example.com", "Latitude":0, "Longitude":0},
        {"Business name":"C", "Website":"example.com", "Latitude":0, "Longitude":0},
        {"Business name":"D", "Phone":"456", "Latitude":0, "Longitude":0},
        {"Business name":"E", "Phone":"456", "Latitude":0, "Longitude":0},
        {"Business name":"Unique", "Phone":"789", "Latitude":0, "Longitude":0},
    ], index=[7] * 6)


def test_groups_and_pair_evidence(frame):
    groups = find_duplicate_groups(frame)
    assert groups == [[0, 1, 2], [3, 4]]
    edges = group_evidence(frame, groups[0])
    assert len(edges) == 2
    assert edges[0]["score"] == 95 and edges[0]["confidence"] == "High confidence"
    assert "Phone numbers match" in edges[0]["evidence"]
    assert any("Website domains match" in edge["evidence"] for edge in edges)
    assert all(any("metres apart" in e for e in edge["evidence"]) for edge in edges)
    table = comparison_table(frame, groups[0])
    assert table["Record identifier"].tolist() == ["R0001", "R0002", "R0003"]


def test_name_only_confidence_and_osm_identity():
    row = {"Business name":"Alder Dental", "Latitude":0, "Longitude":0}
    evidence = pair_evidence(row, row)
    assert evidence["confidence"] == "Possible duplicate" and evidence["score"] == 80
    assert "Names are 100.0% similar" in evidence["evidence"]
    row.update({"OpenStreetMap element type":"node", "OpenStreetMap element ID":123})
    evidence = pair_evidence(row, row)
    assert evidence["score"] == 100
    assert "Same OpenStreetMap element type and ID" in evidence["evidence"]


def test_defaults_and_empty_groups(frame):
    for groups in (find_duplicate_groups(frame), []):
        result = apply_duplicate_decisions(frame, groups, {})
        assert_frame_equal(result, frame)
        assert result is not frame


def test_recommended_specific_and_nondeduplicates(frame):
    original = frame.copy(deep=True)
    groups = find_duplicate_groups(frame)
    result = apply_duplicate_decisions(frame, groups, {
        0:{"action":KEEP_RECOMMENDED}, 1:{"action":KEEP_SPECIFIC, "record":4}})
    assert_frame_equal(result, original.iloc[[1, 4, 5]])
    assert_frame_equal(frame, original)
    assert build_deduplication_summary(frame,result,groups) == {
        "original":6, "groups_reviewed":2, "excluded":3, "final":3}
    csv = pd.read_csv(io.BytesIO(result.to_csv(index=False).encode("utf-8-sig")))
    assert csv["Business name"].tolist() == ["B","E","Unique"]
    assert list(csv.columns) == list(frame.columns)
    original_csv = pd.read_csv(io.StringIO(frame.to_csv(index=False)))
    assert len(original_csv) == 6


def test_keep_all_in_one_group(frame):
    result = apply_duplicate_decisions(frame, find_duplicate_groups(frame), {
        0:{"action":KEEP_ALL},1:{"action":KEEP_RECOMMENDED}})
    assert result["Business name"].tolist() == ["A","B","C","D","Unique"]


def test_reject_overlapping_groups_and_invalid_choices(frame):
    with pytest.raises(ValueError, match="overlap"):
        apply_duplicate_decisions(frame, [[0,1],[1,2]], {})
    with pytest.raises(ValueError, match="belonging"):
        apply_duplicate_decisions(frame, [[0,1]], {0:{"action":KEEP_SPECIFIC,"record":5}})
    with pytest.raises(ValueError, match="Unknown"):
        apply_duplicate_decisions(frame, [[0,1]], {0:{"action":"delete everything"}})


def test_state_preserved_and_reset_on_changed_data(frame):
    state = {}
    review = sync_review_state(state, frame)
    review["decisions"][0] = {"action":KEEP_RECOMMENDED}
    review["deduplicated"] = apply_duplicate_decisions(frame, review["groups"], review["decisions"])
    state["duplicate_choice_0"] = KEEP_RECOMMENDED
    state["duplicate_record_0"] = 1
    assert sync_review_state(state, frame.copy()) is review
    changed = frame.copy()
    changed.iloc[0,0] = "Changed business"
    new = sync_review_state(state, changed)
    assert new["decisions"] == {} and "deduplicated" not in new
    assert "duplicate_choice_0" not in state and "duplicate_record_0" not in state


def test_threshold_change_resets_decisions_and_export(frame):
    from duplicate_detection import DuplicateThresholds
    state = {}
    initial = sync_review_state(state, frame)
    initial["decisions"][0] = {"action": KEEP_RECOMMENDED}
    initial["deduplicated"] = frame.copy()
    state["duplicate_choice_0"] = KEEP_RECOMMENDED
    updated = sync_review_state(state, frame, DuplicateThresholds(100,100,95))
    assert updated is not initial
    assert updated["decisions"] == {} and "deduplicated" not in updated
    assert "duplicate_choice_0" not in state
    assert sync_review_state(state, frame, DuplicateThresholds(100,100,95)) is updated
