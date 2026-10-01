"""Keep the portfolio scenarios predictable under the default rules."""
import json
from pathlib import Path

import pytest
from pandas.testing import assert_frame_equal

from categories import CATEGORY_TAGS
from data_cleaning import clean_records
from data_validation import validate_records
from duplicate_detection import find_duplicate_groups, pair_evidence
from duplicate_review import KEEP_RECOMMENDED, apply_duplicate_decisions, recommend_record
from map_utils import valid_coordinates, build_map
from overpass_client import parse_response


@pytest.mark.parametrize('category', list(CATEGORY_TAGS))
def test_demo_scenarios(category):
    fixture = json.loads((Path(__file__).parents[1]/'sample_data/demo_businesses.json').read_text())
    key,value = CATEGORY_TAGS[category]
    frame = parse_response({'elements':[e for e in fixture['elements'] if e['tags'].get(key)==value]},category)
    original=frame.copy(deep=True)
    assert len(frame)==20
    groups=find_duplicate_groups(frame)
    assert groups==[[0,1,2],[3,4],[5,6]]
    assert recommend_record(frame,groups[0])==1
    assert pair_evidence(frame.iloc[0],frame.iloc[2]) is None
    assert pair_evidence(frame.iloc[0],frame.iloc[1])['score']==95
    assert pair_evidence(frame.iloc[1],frame.iloc[2])['score']==90
    assert pair_evidence(frame.iloc[5],frame.iloc[6])['score']==80
    assert pair_evidence(frame.iloc[7],frame.iloc[8]) is None
    assert pair_evidence(frame.iloc[0],frame.iloc[16]) is None
    report=validate_records(frame)
    assert len(report)==8
    assert set(report['Issue type'])=={'Invalid'}
    for ident,field in [('R0012','Email'),('R0013','Website'),('R0014','Latitude'),('R0015','Longitude'),('R0016','Latitude')]:
        assert not report[(report['Record identifier']==ident)&(report['Field']==field)&(report['Issue type']=='Invalid')].empty
    assert report[report['Record identifier'].isin(['R0010','R0019'])].empty
    assert report[report['Record identifier'].isin(['R0017','R0018','R0020'])].empty
    assert sum(valid_coordinates(r['Latitude'],r['Longitude']) for r in frame.to_dict('records'))==16
    build_map(frame=frame, demo=True).get_root().render()
    cleaned,changed=clean_records(frame)
    assert changed==2
    assert cleaned.iloc[10]['Country']=='GB'
    assert validate_records(cleaned).query('`Record identifier` == "R0011"').empty
    assert cleaned.iloc[13]['Latitude']==120
    dedup=apply_duplicate_decisions(frame,groups,{i:{'action':KEEP_RECOMMENDED} for i in range(len(groups))})
    assert len(dedup)==16
    assert all(i in dedup.index for i in range(7,20))
    assert_frame_equal(frame,original)
