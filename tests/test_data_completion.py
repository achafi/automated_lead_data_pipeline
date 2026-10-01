import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from data_completion import complete_records


@pytest.fixture
def frame():
    return pd.DataFrame([
        {'Business name':'Elm','Phone':'','Email':'','Website':'','City':'Existing','Latitude':None,'OpenStreetMap element ID':1},
        {'Business name':'Elm','Phone':'+44 20 7946 0100','Email':'hello@example.com','Website':'https://example.com','City':'London','Latitude':51.5,'OpenStreetMap element ID':2},
        {'Business name':'Elm','Phone':'+44 20 7946 0100','Email':'hello@example.com','Website':'https://example.com','City':'London','Latitude':51.5,'OpenStreetMap element ID':3},
        {'Business name':'Unrelated','Phone':'','Email':'','Website':'','City':'','Latitude':51.5,'OpenStreetMap element ID':4},
    ], index=[5]*4)


def test_unconfirmed_does_nothing(frame):
    result, report = complete_records(frame, [[0,1,2]], [])
    assert_frame_equal(result,frame)
    assert report.empty and result is not frame


def test_confirmed_agreement_and_sources(frame):
    original=frame.copy(deep=True)
    result,report=complete_records(frame,[[0,1,2]],[0])
    assert result.iloc[0]['Phone']=='+44 20 7946 0100'
    assert result.iloc[0]['City']=='Existing'
    assert pd.isna(result.iloc[0]['Latitude'])
    assert len(report)==3
    assert set(report['Source records'])=={'R0002, R0003'}
    assert set(report['Target record'])=={'R0001'}
    assert set(report['Status'])=={'Ready to fill'}
    assert_frame_equal(result.iloc[[3]],original.iloc[[3]])
    assert_frame_equal(frame,original)
    assert list(result.columns)==list(frame.columns) and list(result.index)==list(frame.index)


def test_conflicting_and_invalid_values_never_filled(frame):
    frame.iloc[2,frame.columns.get_loc('Phone')]='+44 20 7946 0200'
    frame['Website']=['','javascript:bad','javascript:bad','']
    result,report=complete_records(frame,[[0,1,2]],[0])
    assert result.iloc[0]['Phone']==result.iloc[0]['Website']==''
    assert report.loc[report.Field=='Phone','Reason'].iloc[0].startswith('Conflicting')
    assert report.loc[report.Field=='Website','Reason'].iloc[0]=='Source value fails the format check'
    assert result.iloc[0]['Email']=='hello@example.com'


def test_retained_row_can_use_excluded_donors(frame):
    result,report=complete_records(frame,[[0,1,2]],[0],positions=[0,3])
    assert len(result)==2 and result.iloc[0]['Phone']=='+44 20 7946 0100'
    assert set(report['Source records'])=={'R0002, R0003'}
    assert result.iloc[1]['Phone']==''


def test_no_available_value_no_guessing_and_zero_false():
    frame=pd.DataFrame({'City':['',None], 'Postcode':[0,False], 'Latitude':[0,1]})
    result,report=complete_records(frame,[[0,1]],[0])
    assert_frame_equal(result,frame)
    assert report.empty
    empty=pd.DataFrame()
    result,report=complete_records(empty,[],[])
    assert result.empty and report.empty


def test_disjoint_groups_and_confirmation_scope():
    frame=pd.DataFrame({'City':['','London','','Paris']})
    result,report=complete_records(frame,[[0,1],[2,3]],[1])
    assert result.City.tolist()==['','London','Paris','Paris']
    assert report['Target record'].tolist()==['R0003']
    with pytest.raises(ValueError):
        complete_records(frame,[[0,1],[1,2]],[0])
    with pytest.raises(ValueError):
        complete_records(frame,[[0,1]],[4])


def test_retention_decision_authorizes_filling_without_extra_confirmation(frame):
    from data_completion import deduplicate_and_complete
    from duplicate_review import KEEP_RECOMMENDED, KEEP_SPECIFIC
    frame.loc[:,'Opening hours']=['24/7','','','']
    original=frame.copy(deep=True)
    groups=[[0,1,2]]
    unchanged,report=deduplicate_and_complete(frame,groups,{})
    assert_frame_equal(unchanged,original)
    assert report.empty
    result,report=deduplicate_and_complete(frame,groups,{0:{'action':KEEP_RECOMMENDED}})
    assert len(result)==2
    assert result.iloc[0]['Opening hours']=='24/7'
    assert report.loc[report.Field=='Opening hours','Status'].iloc[0]=='Filled'
    result,report=deduplicate_and_complete(frame,groups,{0:{'action':KEEP_SPECIFIC,'record':0}})
    assert result.iloc[0]['Email']=='hello@example.com'
    assert result.iloc[0]['City']=='Existing'
    assert_frame_equal(frame,original)
