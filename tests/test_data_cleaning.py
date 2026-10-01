import io

import pandas as pd
from pandas.testing import assert_frame_equal

from data_cleaning import CleaningOptions, clean_records


def test_cleaning_preserves_original_order_and_counts_rows():
    frame = pd.DataFrame([
        {"Business name":"  Café   Elm \n", "Street":" Main  Road ", "Phone":" +44 (20)  123 ",
         "Website":" https://Example.com/Page?q=X ", "Email":" Office@Example.com ", "Country":" united kingdom ", "Latitude":51.5},
        {"Business name":"Unchanged", "Street":"Main Road", "Phone":"123", "Website":"example.com", "Email":"a@b.com", "Country":"GB", "Latitude":51.5},
    ], index=[7,7])
    original = frame.copy(deep=True)
    cleaned, changed = clean_records(frame)
    assert changed == 1
    assert cleaned.iloc[0]["Business name"] == "Café Elm"
    assert cleaned.iloc[0]["Street"] == "Main Road"
    assert cleaned.iloc[0]["Phone"] == "+44 (20)  123"
    assert cleaned.iloc[0]["Website"] == "https://Example.com/Page?q=X"
    assert cleaned.iloc[0]["Email"] == "Office@Example.com"
    assert cleaned.iloc[0]["Country"] == "GB"
    assert list(cleaned.columns) == list(frame.columns) and list(cleaned.index) == [7,7]
    assert_frame_equal(frame, original)
    csv = pd.read_csv(io.BytesIO(cleaned.to_csv(index=False).encode("utf-8-sig")))
    assert csv.iloc[0]["Business name"] == "Café Elm" and len(csv.columns) == len(frame.columns)


def test_missing_values_and_zero_false():
    frame = pd.DataFrame({"Example":[None, float("nan"), pd.NA, "", " \n\t", 0, False]}, dtype=object)
    cleaned, changed = clean_records(frame)
    assert cleaned["Example"].tolist() == ["", "", "", "", "", 0, False]
    assert changed == 4


def test_options_are_independent():
    frame = pd.DataFrame({"Business name":[" A  B "], "Phone":[" 12  34 "], "Country":["france"], "Other":[None]})
    off = CleaningOptions(False,False,False,False)
    cleaned, changed = clean_records(frame,off)
    assert_frame_equal(cleaned,frame)
    assert changed == 0 and cleaned is not frame
    for key, column, expected in [("name_address_spaces","Business name","A B"),
                                 ("contact_spaces","Phone","12  34"),
                                 ("country_codes","Country","FR"), ("missing_values","Other","")]:
        options = CleaningOptions(**{k:k==key for k in off.__dataclass_fields__})
        result,count = clean_records(frame,options)
        assert result.iloc[0][column] == expected and count == 1
        for other in frame.columns:
            if other != column:
                pd.testing.assert_series_equal(result[other],frame[other])


def test_country_unknown_values_and_no_enrichment():
    frame = pd.DataFrame({"Country":["gb","UK","France","Atlantis", "",None], "Phone":["123"]*6})
    result,_ = clean_records(frame)
    assert result["Country"].tolist() == ["GB","GB","FR","Atlantis","",""]
    assert result["Phone"].tolist() == ["123"]*6


def test_empty_absent_optional_columns_and_idempotence():
    for frame in (pd.DataFrame(), pd.DataFrame(columns=["Country"]), pd.DataFrame({"Latitude":[91.0]})):
        result,count = clean_records(frame)
        assert_frame_equal(result,frame)
        assert count == 0
    cleaned,_ = clean_records(pd.DataFrame({"Business name":[" A  B "]}))
    again,count = clean_records(cleaned)
    assert_frame_equal(again,cleaned)
    assert count == 0
