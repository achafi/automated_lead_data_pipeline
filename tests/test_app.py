import io
from pathlib import Path

import httpx
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import overpass_client
import streamlit_folium
from map_utils import DEMO_BBOX, rectangle_geojson

APP = str(Path(__file__).parents[1] / "app.py")


@pytest.fixture
def map_state(monkeypatch):
    state = {"all_drawings": None}
    monkeypatch.setattr(streamlit_folium, "st_folium", lambda *a, **kw: state)
    monkeypatch.setattr(httpx.Client, "post", lambda *a, **kw: pytest.fail("Automated tests must never call Overpass"))
    return state


def button(app, text):
    return next(b for b in app.button if b.label == text)


def test_demo_every_category_and_csv(map_state):
    app = AppTest.from_file(APP).run()
    assert not app.exception
    assert len(app.text_input) == 1
    assert not app.metric
    app.checkbox[0].check().run()
    for category in ["Dentists", "Pharmacies", "Restaurants", "Cafés", "Hotels"]:
        app.selectbox(key="business_category").select(category).run()
        button(app,"Collect Data").click().run()
        assert not app.exception
        assert [metric.label for metric in app.metric] == [
            "Businesses collected", "With contact information", "Website present", "Complete address", "Potential duplicate groups"]
        assert [metric.value for metric in app.metric] == ["20", "18 / 20", "18 / 20", "16 / 20", "3"]
        assert [metric.delta for metric in app.metric[1:4]] == ["90.0%", "90.0%", "80.0%"]
        frame = app.session_state.results["frame"]
        assert set(frame["Selected category"]) == {category}
        assert frame["OpenStreetMap URL"].eq("").all()
        csv = frame.to_csv(index=False).encode("utf-8-sig")
        read = pd.read_csv(io.BytesIO(csv))
        assert len(read) == 20 and len(read.columns) == 17
        assert "Unnamed: 0" not in read.columns
        assert app.get("download_button")


def test_missing_rectangle(map_state):
    app = AppTest.from_file(APP).run()
    button(app,"Collect Data").click().run()
    assert "No rectangle selected" in app.error[0].value


def test_oversized_rectangle(map_state):
    map_state["all_drawings"] = [rectangle_geojson((50,-1,52,1))]
    app = AppTest.from_file(APP).run()
    button(app,"Collect Data").click().run()
    assert "too large" in app.error[0].value


def test_cached_search_and_deleted_selection(map_state, monkeypatch):
    calls=[]
    def fake_collect(*args):
        calls.append(args)
        return overpass_client.parse_response({"elements":[]}, "Dentists")
    monkeypatch.setattr(overpass_client, "collect_businesses", fake_collect)
    map_state["all_drawings"] = [rectangle_geojson(DEMO_BBOX)]
    app = AppTest.from_file(APP).run()
    import streamlit as st
    st.cache_data.clear()
    button(app,"Collect Data").click().run()
    button(app,"Collect Data").click().run()
    assert len(calls) == 1
    assert not app.metric
    assert any("Records returned: 0" in item.value for item in app.markdown)
    map_state["all_drawings"] = []
    app.run()
    button(app,"Collect Data").click().run()
    assert "No rectangle selected" in app.error[0].value
    assert len(calls) == 1
    st.cache_data.clear()


def test_failures_are_not_cached_or_shown_as_empty_results(map_state, monkeypatch):
    import streamlit as st
    st.cache_data.clear()
    calls=[]
    def fail(*args):
        calls.append(args)
        raise overpass_client.OverpassError("The Overpass server is temporarily unavailable. Please try again later.")
    monkeypatch.setattr(overpass_client, "collect_businesses", fail)
    map_state["all_drawings"] = [rectangle_geojson(DEMO_BBOX)]
    app = AppTest.from_file(APP).run()
    for _ in range(2):
        button(app,"Collect Data").click().run()
        assert not app.exception
        assert "temporarily unavailable" in app.error[0].value
        assert not app.metric
    assert len(calls) == 2
    st.cache_data.clear()


def test_live_cards_do_not_change_records_or_request_again(map_state, monkeypatch):
    import streamlit as st
    from pandas.testing import assert_frame_equal
    st.cache_data.clear()
    frame = overpass_client.parse_response({"elements": [
        {"type": "node", "id": 1, "lat": 51.51, "lon": -.12,
         "tags": {"phone": "123", "addr:street": "Main", "addr:city": "London", "addr:postcode": "X"}},
        {"type": "node", "id": 2, "lat": 51.51, "lon": -.12,
         "tags": {"website": "https://example.com"}},
    ]}, "Dentists")
    original = frame.copy(deep=True)
    calls = []
    def collect(*args):
        calls.append(args)
        return frame
    monkeypatch.setattr(overpass_client, "collect_businesses", collect)
    map_state["all_drawings"] = [rectangle_geojson(DEMO_BBOX)]
    app = AppTest.from_file(APP).run()
    button(app, "Collect Data").click().run()
    assert not app.exception
    assert [m.value for m in app.metric] == ["2", "2 / 2", "1 / 2", "1 / 2", "0"]
    assert [m.delta for m in app.metric[1:4]] == ["100.0%", "50.0%", "50.0%"]
    app.run()
    assert len(calls) == 1
    assert_frame_equal(frame, original)
    assert_frame_equal(app.session_state.results["frame"], original)
    st.cache_data.clear()


@pytest.mark.parametrize("phones,groups,affected", [
    (["100", "200", "300"], 0, 0),
    (["100", "100", "100"], 1, 3),
    (["100", "100", "200", "200", "300"], 2, 4),
])
@pytest.mark.parametrize("demo", [False, True])
def test_duplicate_card_fixtures(map_state, monkeypatch, phones, groups, affected, demo):
    import streamlit as st
    from pandas.testing import assert_frame_equal
    st.cache_data.clear()
    frame = overpass_client.parse_response({"elements": [
        {"type": "node", "id": i + 1, "lat": 51.51, "lon": -.12, "tags": {"phone": phone}}
        for i, phone in enumerate(phones)
    ]}, "Dentists")
    if demo:
        frame["OpenStreetMap element ID"] = ""
        frame["OpenStreetMap URL"] = ""
        frame["Data source"] = "Demonstration data (fictional)"
    original = frame.copy(deep=True)
    map_state["all_drawings"] = [rectangle_geojson(DEMO_BBOX)]
    app = AppTest.from_file(APP).run()
    app.session_state.results = {"frame": frame, "category": "Dentists", "bbox": DEMO_BBOX,
                                 "demo": demo, "maximum": 50}
    app.run()
    assert not app.exception
    assert len(app.metric) == 5
    assert app.metric[4].label == "Potential duplicate groups"
    assert app.metric[4].value == str(groups)
    caption = f"{affected} records affected" if groups else "No potential duplicates"
    assert any(c.value == caption for c in app.caption)
    assert_frame_equal(app.session_state.results["frame"], original)
    st.cache_data.clear()


def review_fixture():
    return overpass_client.parse_response({"elements": [
        {"type":"node", "id":i+1, "lat":51.51, "lon":-.12,
         "tags":{"name":name, **tags}}
        for i,(name,tags) in enumerate([
            ("A", {"phone":"123"}),
            ("B", {"phone":"123", "website":"example.com"}),
            ("C", {"website":"example.com"}),
            ("D", {"phone":"456"}),
            ("E", {"phone":"456"}),
            ("Unique", {"phone":"789"}),
        ])
    ]}, "Dentists")


def test_review_decisions_exports_and_reruns(map_state):
    from duplicate_review import KEEP_ALL, KEEP_RECOMMENDED, KEEP_SPECIFIC
    from pandas.testing import assert_frame_equal
    frame = review_fixture()
    original = frame.copy(deep=True)
    app = AppTest.from_file(APP).run()
    app.session_state.results = {"frame":frame, "category":"Dentists", "bbox":DEMO_BBOX,
                                 "demo":False, "maximum":50}
    app.run()
    assert not app.exception
    assert len(app.expander) == 2
    assert "3 records" in app.expander[0].label
    assert app.selectbox(key="duplicate_choice_0").value == KEEP_ALL
    assert len(app.get("download_button")) == 1
    button(app,"Create deduplicated results").click().run()
    assert_frame_equal(app.session_state.duplicate_review["deduplicated"], original)
    assert len(app.get("download_button")) == 3
    app.selectbox(key="duplicate_choice_0").select(KEEP_SPECIFIC).run()
    assert "deduplicated" not in app.session_state.duplicate_review
    app.selectbox(key="duplicate_record_0").select(2).run()
    app.run()
    assert app.selectbox(key="duplicate_record_0").value == 2
    assert app.selectbox(key="duplicate_choice_0").value == KEEP_SPECIFIC
    button(app,"Create deduplicated results").click().run()
    result = app.session_state.duplicate_review["deduplicated"]
    assert result["Business name"].tolist() == ["C","D","E","Unique"]
    assert len(app.get("download_button")) == 4
    assert app.session_state.duplicate_review["fill_report"]["Status"].eq("Skipped").all()
    assert "Excluded: 2" in " ".join(m.value for m in app.markdown)
    button(app,"Use all recommendations").click().run()
    assert not app.exception
    assert app.selectbox(key="duplicate_choice_0").value == KEEP_RECOMMENDED
    assert app.selectbox(key="duplicate_choice_1").value == KEEP_RECOMMENDED
    assert "deduplicated" not in app.session_state.duplicate_review
    assert any("3 records would be excluded" in item.value for item in app.info)
    button(app,"Create deduplicated results").click().run()
    result = app.session_state.duplicate_review["deduplicated"]
    assert result["Business name"].tolist() == ["B","D","Unique"]
    csv = pd.read_csv(io.BytesIO(result.to_csv(index=False).encode("utf-8-sig")))
    assert csv["Business name"].tolist() == ["B","D","Unique"]
    assert_frame_equal(app.session_state.results["frame"], original)
    button(app,"Reset duplicate decisions").click().run()
    assert not app.exception
    assert app.selectbox(key="duplicate_choice_0").value == KEEP_ALL
    assert app.selectbox(key="duplicate_choice_1").value == KEEP_ALL
    assert "deduplicated" not in app.session_state.duplicate_review
    button(app,"Create deduplicated results").click().run()
    assert_frame_equal(app.session_state.duplicate_review["deduplicated"], original)


def test_new_search_resets_review_decisions(map_state, monkeypatch):
    import streamlit as st
    from duplicate_review import KEEP_ALL, KEEP_RECOMMENDED
    st.cache_data.clear()
    calls=[]
    def collect(*args):
        frame = review_fixture()
        if calls:
            frame.loc[0,"Business name"] = "Changed business"
        calls.append(args)
        return frame
    monkeypatch.setattr(overpass_client,"collect_businesses",collect)
    map_state["all_drawings"] = [rectangle_geojson(DEMO_BBOX)]
    app = AppTest.from_file(APP).run()
    button(app,"Collect Data").click().run()
    app.selectbox(key="duplicate_choice_0").select(KEEP_RECOMMENDED).run()
    button(app,"Create deduplicated results").click().run()
    assert "deduplicated" in app.session_state.duplicate_review
    app.number_input[0].set_value(49).run()
    button(app,"Collect Data").click().run()
    assert not app.exception
    assert app.selectbox(key="duplicate_choice_0").value == KEEP_ALL
    assert "deduplicated" not in app.session_state.duplicate_review
    assert len(calls) == 2
    st.cache_data.clear()


@pytest.mark.parametrize("size,group_count", [(1,0),(3,1),(6,2)])
def test_review_zero_one_multiple_groups(map_state,size,group_count):
    frame = review_fixture().iloc[:size].copy()
    app = AppTest.from_file(APP).run()
    app.session_state.results = {"frame":frame,"category":"Dentists","bbox":DEMO_BBOX,
                                 "demo":True,"maximum":50}
    app.run()
    assert not app.exception
    assert len(app.expander) == group_count
    if group_count:
        assert any(h.value == "Potential Duplicate Review" for h in app.subheader)
    else:
        assert app.success[0].value == "No potential duplicate groups were detected."
        assert len(app.get("download_button")) == 1


def test_sidebar_threshold_changes_do_not_request_or_mutate(map_state,monkeypatch):
    import streamlit as st
    from duplicate_review import KEEP_ALL, KEEP_RECOMMENDED
    from pandas.testing import assert_frame_equal
    st.cache_data.clear()
    frame = overpass_client.parse_response({"elements":[
        {"type":"node","id":1,"lat":0,"lon":0,"tags":{"phone":"123"}},
        {"type":"node","id":2,"lat":0,"lon":.002,"tags":{"phone":"123"}},
    ]},"Dentists")
    original = frame.copy(deep=True)
    calls=[]
    def collect(*args):
        calls.append(args)
        return frame
    monkeypatch.setattr(overpass_client,"collect_businesses",collect)
    map_state["all_drawings"] = [rectangle_geojson(DEMO_BBOX)]
    app = AppTest.from_file(APP).run()
    button(app,"Collect Data").click().run()
    assert app.metric[4].value == "1"
    app.selectbox(key="duplicate_choice_0").select(KEEP_RECOMMENDED).run()
    button(app,"Create deduplicated results").click().run()
    app.slider(key="contact_distance").set_value(100).run()
    assert not app.exception
    assert app.metric[4].value == "0"
    assert "deduplicated" not in app.session_state.duplicate_review
    button(app,"Reset matching defaults").click().run()
    assert app.metric[4].value == "1"
    assert app.selectbox(key="duplicate_choice_0").value == KEEP_ALL
    assert app.slider(key="contact_distance").value == 500
    assert app.slider(key="name_distance").value == 150
    assert app.slider(key="name_similarity").value == 90
    assert len(calls) == 1
    assert_frame_equal(app.session_state.results["frame"],original)
    st.cache_data.clear()


def test_cleaning_original_preview_export_and_options(map_state):
    from pandas.testing import assert_frame_equal
    frame = review_fixture()
    frame.loc[0,"Business name"] = "  Café   Elm "
    frame.loc[0,"Country"] = "united kingdom"
    frame.loc[0,"Email"] = " hello@example.com "
    original = frame.copy(deep=True)
    app = AppTest.from_file(APP).run()
    assert not any(s.value == "Data Cleaning" for s in app.subheader)
    app.session_state.results = {"frame":frame,"category":"Dentists","bbox":DEMO_BBOX,"demo":True,"maximum":50}
    app.run()
    button(app,"Create deduplicated results").click().run()
    assert not app.exception
    cleaned,count = app.session_state.duplicate_review["cleaned"]
    assert cleaned.iloc[0]["Business name"] == "Café Elm"
    assert cleaned.iloc[0]["Country"] == "GB" and count == 1
    assert_frame_equal(app.session_state.results["frame"],original)
    csv = pd.read_csv(io.BytesIO(cleaned.to_csv(index=False).encode("utf-8-sig")))
    assert len(csv)==6 and csv.iloc[0]["Email"] == "hello@example.com"
    app.run()
    assert "cleaned" in app.session_state.duplicate_review
    app.checkbox(key="clean_name_spaces").uncheck().run()
    assert "cleaned" not in app.session_state.duplicate_review
    button(app,"Create deduplicated results").click().run()
    assert app.session_state.duplicate_review["cleaned"][0].iloc[0]["Business name"] == "  Café   Elm "
    changed = original.copy()
    changed.loc[0,"Business name"] = "A different search"
    app.session_state.results = {"frame":changed,"category":"Dentists","bbox":DEMO_BBOX,"demo":True,"maximum":50}
    app.run()
    assert "cleaned" not in app.session_state.duplicate_review


def test_cleaning_deduplicated_and_decision_invalidation(map_state):
    from pandas.testing import assert_frame_equal
    frame = review_fixture()
    frame.loc[1,"Website"] = " example.com "
    original = frame.copy(deep=True)
    app = AppTest.from_file(APP).run()
    app.session_state.results = {"frame":frame,"category":"Dentists","bbox":DEMO_BBOX,"demo":False,"maximum":50}
    app.run()
    button(app,"Use all recommendations").click().run()
    button(app,"Create deduplicated results").click().run()
    dedup_original = app.session_state.duplicate_review["deduplicated"].copy(deep=True)
    button(app,"Create deduplicated results").click().run()
    assert not app.exception
    cleaned,count = app.session_state.duplicate_review["cleaned"]
    assert len(cleaned) == 3 and cleaned.iloc[0]["Website"] == "example.com" and count == 1
    assert_frame_equal(app.session_state.results["frame"],original)
    assert_frame_equal(app.session_state.duplicate_review["deduplicated"],dedup_original)
    button(app,"Reset duplicate decisions").click().run()
    assert not app.exception
    assert "cleaned" not in app.session_state.duplicate_review


def test_validation_sources_ids_and_report_invalidation(map_state):
    from pandas.testing import assert_frame_equal
    frame = review_fixture()
    frame.loc[1, "Email"] = " a@example.com "
    original = frame.copy(deep=True)
    app = AppTest.from_file(APP).run()
    app.session_state.results = {"frame": frame, "category": "Dentists", "bbox": DEMO_BBOX, "demo": False, "maximum": 50}
    app.run()
    assert not app.sidebar.button
    button(app, "Use all recommendations").click().run()
    button(app, "Create deduplicated results").click().run()
    report = app.session_state.duplicate_review["validation_report"]
    assert set(report["Record identifier"]) == {"R0002", "R0004", "R0006"}
    assert report[report["Field"] == "Email"].empty
    assert_frame_equal(app.session_state.results["frame"], original)
    app.run()
    assert "validation_report" in app.session_state.duplicate_review
    app.checkbox(key="validate_output").uncheck().run()
    assert "validation_report" not in app.session_state.duplicate_review
    assert "cleaned" not in app.session_state.duplicate_review
    button(app, "Create deduplicated results").click().run()
    assert "validation_report" not in app.session_state.duplicate_review
    assert "cleaned" in app.session_state.duplicate_review
    changed = original.copy()
    changed.loc[0, "Business name"] = "New search"
    app.session_state.results = {"frame": changed, "category": "Dentists", "bbox": DEMO_BBOX, "demo": False, "maximum": 50}
    app.run()
    assert "cleaned" not in app.session_state.duplicate_review


def test_validation_with_no_issues(map_state):
    frame = overpass_client.parse_response({'elements':[{'type':'node','id':1,'lat':0,'lon':0,
        'tags':{'name':'Example','addr:street':'Main','addr:city':'London','addr:postcode':'X',
                'email':'a@example.com','website':'https://example.com'}}]},'Dentists')
    app = AppTest.from_file(APP).run()
    app.session_state.results = {'frame':frame,'category':'Dentists','bbox':DEMO_BBOX,'demo':True,'maximum':50}
    app.run()
    button(app,'Create processed results').click().run()
    assert not app.exception
    assert app.session_state.duplicate_review['validation_report'].empty
    assert any(item.value=='No issues found by these checks.' for item in app.success)
    assert len(app.get('download_button'))==3


def test_expanded_demo_full_walkthrough(map_state):
    from pandas.testing import assert_frame_equal
    app = AppTest.from_file(APP).run()
    app.checkbox(key='demo').check().run()
    button(app,'Collect Data').click().run()
    original = app.session_state.results['frame'].copy(deep=True)
    assert len(original)==20
    assert any(e.label=='Demo scenario guide' for e in app.expander)
    button(app,'Create deduplicated results').click().run()
    assert len(app.session_state.duplicate_review['validation_report'])==6
    button(app,'Use all recommendations').click().run()
    app.run()
    button(app,'Create deduplicated results').click().run()
    assert not app.exception
    assert len(app.session_state.duplicate_review['deduplicated'])==16
    assert_frame_equal(app.session_state.results['frame'],original)



def test_automatic_fill_on_specific_retention_and_invalidation(map_state):
    from duplicate_review import KEEP_SPECIFIC, KEEP_ALL
    from pandas.testing import assert_frame_equal
    frame=review_fixture()
    frame.loc[1,'Email']='hello@example.com'
    original=frame.copy(deep=True)
    app=AppTest.from_file(APP).run()
    app.session_state.results={'frame':frame,'category':'Dentists','bbox':DEMO_BBOX,'demo':True,'maximum':50}
    app.run()
    assert not any(c.key.startswith('fill_confirm_') for c in app.checkbox if c.key)
    button(app,'Create deduplicated results').click().run()
    assert_frame_equal(app.session_state.duplicate_review['deduplicated'],original)
    assert app.session_state.duplicate_review['fill_report'].empty
    app.selectbox(key='duplicate_choice_0').select(KEEP_SPECIFIC).run()
    app.selectbox(key='duplicate_record_0').select(0).run()
    button(app,'Create deduplicated results').click().run()
    assert not app.exception
    result=app.session_state.duplicate_review['deduplicated']
    assert len(result)==4 and result.iloc[0]['Email']=='hello@example.com'
    assert_frame_equal(app.session_state.results['frame'],original)
    assert 'Filled' in app.session_state.duplicate_review['fill_report']['Status'].values
    app.run()
    assert app.session_state.duplicate_review['deduplicated'].iloc[0]['Email']=='hello@example.com'
    button(app,'Create deduplicated results').click().run()
    button(app,'Create deduplicated results').click().run()
    assert set(app.session_state.duplicate_review['validation_report']['Record identifier']) <= {'R0001','R0004','R0005','R0006'}
    app.selectbox(key='duplicate_choice_0').select(KEEP_ALL).run()
    assert 'deduplicated' not in app.session_state.duplicate_review
    assert 'cleaned' not in app.session_state.duplicate_review
    assert 'validation_report' not in app.session_state.duplicate_review


def test_duplicate_settings_only_with_groups(map_state):
    app = AppTest.from_file(APP).run()
    assert not app.slider
    frame = review_fixture()
    app.session_state.results = {"frame": frame.iloc[:1], "category": "Dentists",
                                 "bbox": DEMO_BBOX, "demo": False, "maximum": 50}
    app.run()
    assert not app.slider
    app.session_state.results = {"frame": frame, "category": "Dentists",
                                 "bbox": DEMO_BBOX, "demo": False, "maximum": 50}
    app.run()
    assert len(app.sidebar.slider) == 3
    assert not app.exception
