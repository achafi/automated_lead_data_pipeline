import math

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from duplicate_detection import (duplicate_summary, find_duplicate_groups, haversine_distance,
                                 normalize_name, normalize_phone, normalize_website_domain, records_match)


def record(**values):
    return {"Latitude": 0.0, "Longitude": 0.0, **values}


def test_normalization():
    assert normalize_name("  ALDER,   Dental! ") == "alder dental"
    assert normalize_phone("+44 (20) 7946-0100") == "442079460100"


@pytest.mark.parametrize("url", ["https://www.Example.com/path?q=1", "http://example.com/", "example.com/other", "//www.example.com", "https://example.com:443/a"])
def test_domains(url):
    assert normalize_website_domain(url) == "example.com"


@pytest.mark.parametrize("value", [None, pd.NA, float("nan"), "", " \t "])
def test_missing_values(value):
    assert normalize_name(value) == normalize_phone(value) == normalize_website_domain(value) == ""


@pytest.mark.parametrize("url", ["https://[bad", "javascript:alert(1)", "https://bad host.com", "https://"])
def test_invalid_websites(url):
    assert normalize_website_domain(url) == ""


def test_distance():
    assert haversine_distance(0, 0, 0, 0) == 0
    assert haversine_distance(0, 0, 0, 1) == pytest.approx(111195.08, abs=.1)
    assert haversine_distance(0, 179.999, 0, -179.999) == pytest.approx(222.39, abs=.1)


@pytest.mark.parametrize("bad", [None, "", pd.NA, float("nan"), math.inf, 91, True])
def test_invalid_distance(bad):
    assert haversine_distance(bad, 0, 0, 0) is None


def test_phone_matching_and_distance():
    left = record(Phone="+44 (20) 7946-0100")
    assert records_match(left, record(Phone="44 20 7946 0100", Longitude=.004))
    assert not records_match(left, record(Phone="442079460100", Longitude=.005))


def test_website_matching_and_distant_chain():
    left = record(Website="https://www.example.com/branch-a")
    assert records_match(left, record(Website="http://example.com/branch-b?q=x", Longitude=.004))
    assert not records_match(left, record(Website="example.com/branch-c", Longitude=.01))


def test_similar_names_near_and_far():
    left = record(**{"Business name": "Alder Dental Clinic"})
    right = record(**{"Business name": "Alder Dental Clinics", "Longitude": .001})
    assert records_match(left, right)
    right["Longitude"] = .002
    assert not records_match(left, right)
    assert not records_match(left, record(**{"Business name": "Other Company"}))


@pytest.mark.parametrize("field", ["Latitude", "Longitude"])
def test_missing_coordinates_for_all_rules(field):
    left = record(**{"Business name": "Same", "Phone": "123", "Website": "example.com"})
    right = dict(left)
    right.pop(field)
    assert not records_match(left, right)


def test_missing_identifiers_and_optional_columns():
    assert not records_match(record(), record())
    assert duplicate_summary(pd.DataFrame([record(), record()])) == {"group_count": 0, "affected_records": 0}
    assert duplicate_summary(pd.DataFrame(index=[0, 1])) == {"group_count": 0, "affected_records": 0}


def test_connected_chain():
    # A--B by phone, B--C by website; A and C share no matching identifier.
    frame = pd.DataFrame([record(Phone="123"), record(Phone="123", Website="example.com"), record(Website="example.com")])
    assert find_duplicate_groups(frame) == [[0, 1, 2]]
    assert duplicate_summary(frame) == {"group_count": 1, "affected_records": 3}


def test_multiple_groups_and_unchanged_records():
    frame = pd.DataFrame([record(Phone="123"), record(Phone="1-23"),
                          record(Website="example.com"), record(Website="https://www.example.com"),
                          record(Phone="456")], index=[7] * 5)
    original = frame.copy(deep=True)
    assert find_duplicate_groups(frame) == [[0, 1], [2, 3]]
    assert duplicate_summary(frame) == {"group_count": 2, "affected_records": 4}
    assert_frame_equal(frame, original)


def test_empty_and_singleton():
    for frame in (pd.DataFrame(), pd.DataFrame([record(Phone="123")])):
        assert find_duplicate_groups(frame) == []
        assert duplicate_summary(frame) == {"group_count": 0, "affected_records": 0}


def test_configurable_thresholds_and_consistent_evidence():
    from duplicate_detection import DuplicateThresholds, pair_evidence
    a = record(**{"Business name":"Alder Dental Clinic", "Phone":"123"})
    b = record(**{"Business name":"Alder Dental Clinics", "Phone":"123", "Longitude":.002})
    # About 222 m: name rule can be wider than contact rule, independently.
    narrow = DuplicateThresholds(100, 100, 90)
    wider_name = DuplicateThresholds(100, 250, 90)
    assert not records_match(a,b,narrow)
    assert records_match(a,b,wider_name)
    evidence = pair_evidence(a,b,wider_name)
    assert evidence["score"] == 80
    assert "Phone numbers match" not in evidence["evidence"]
    assert not records_match(a,b,DuplicateThresholds(100,250,100))
    assert records_match(a,b,DuplicateThresholds(250,100,100))
    assert pair_evidence(a,b,DuplicateThresholds(250,100,100))["score"] == 95
    assert find_duplicate_groups(pd.DataFrame([a,b]), narrow) == []
    assert duplicate_summary(pd.DataFrame([a,b]), wider_name)["group_count"] == 1


@pytest.mark.parametrize("values", [(0,150,90),(500,-1,90),(500,150,101),(500,150,0),
                                     (float('nan'),150,90),(500,True,90)])
def test_invalid_duplicate_thresholds(values):
    from duplicate_detection import DuplicateThresholds
    with pytest.raises(ValueError):
        DuplicateThresholds(*values)
