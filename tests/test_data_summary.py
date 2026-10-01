import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from data_summary import summarize_records

FIELDS = ["Website", "Phone", "Email", "Street", "City", "Postcode"]


def test_populated_and_unchanged():
    frame = pd.DataFrame([dict.fromkeys(FIELDS, "value")] * 2)
    original = frame.copy(deep=True)
    result = summarize_records(frame)
    assert result["total"] == 2
    for name in ("contact", "website", "address"):
        assert result[name] == {"count": 2, "percentage": 100.0}
    assert_frame_equal(frame, original)


@pytest.mark.parametrize("missing", [None, float("nan"), pd.NA, "", " \t\n"])
def test_missing_values(missing):
    result = summarize_records(pd.DataFrame([dict.fromkeys(FIELDS, missing)]))
    for name in ("contact", "website", "address"):
        assert result[name] == {"count": 0, "percentage": 0.0}


@pytest.mark.parametrize("value", [0, False])
def test_zero_and_false_are_present(value):
    result = summarize_records(pd.DataFrame([dict.fromkeys(FIELDS, value)]))
    assert all(result[name]["count"] == 1 for name in ("contact", "website", "address"))


def test_counts_and_percentages():
    frame = pd.DataFrame([
        {"Website": "example.com", "Street": "Main", "City": "London", "Postcode": "X"},
        {"Phone": "123", "Street": "Main", "City": "London", "Postcode": " "},
        {"Email": "a@example.com", "Street": "Main", "Postcode": "X"},
        {"Website": " ", "Phone": None, "Email": "", "City": "London", "Postcode": "X"},
    ])
    result = summarize_records(frame)
    assert result == {"total": 4, "contact": {"count": 3, "percentage": 75.0},
                      "website": {"count": 1, "percentage": 25.0},
                      "address": {"count": 1, "percentage": 25.0}}


def test_absent_optional_columns():
    result = summarize_records(pd.DataFrame({"Phone": ["123", ""]}))
    assert result["contact"] == {"count": 1, "percentage": 50.0}
    assert result["website"]["count"] == result["address"]["count"] == 0
    result = summarize_records(pd.DataFrame(index=[0, 1]))
    assert result["total"] == 2 and result["contact"]["count"] == 0


@pytest.mark.parametrize("frame", [pd.DataFrame(), pd.DataFrame(columns=FIELDS)])
def test_empty(frame):
    assert summarize_records(frame) is None
