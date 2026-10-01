import io

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from data_validation import validate_records, valid_email, valid_website, valid_phone, issue_counts, REPORT_COLUMNS


def good(**overrides):
    return {"Business name":"Café Elm","Street":"Main","City":"London","Postcode":"X",
            "Latitude":51.5,"Longitude":-.12,"Email":"a@example.com","Website":"https://example.com",**overrides}


def test_valid_unchanged_and_report_csv():
    frame = pd.DataFrame([good()])
    original = frame.copy(deep=True)
    report = validate_records(frame)
    assert report.empty and list(report.columns) == REPORT_COLUMNS
    assert_frame_equal(frame,original)
    assert list(pd.read_csv(io.StringIO(report.to_csv(index=False))).columns) == REPORT_COLUMNS


@pytest.mark.parametrize("value", [None,pd.NA,float('nan'),'', ' \t'])
def test_missing_separate_from_invalid(value):
    report = validate_records(pd.DataFrame([good(Latitude=value,Longitude=value,Email=value,Website=value,Phone=value,Street=value)]))
    assert report.empty


@pytest.mark.parametrize("value", ['abc',float('inf'),'NaN',True,91,-91])
def test_invalid_latitude(value):
    report=validate_records(pd.DataFrame([good(Latitude=value)]))
    assert len(report)==1 and report.iloc[0]['Issue type']=='Invalid'


@pytest.mark.parametrize("lat,lon", [(90,180),(-90,-180),(0,0),('51.5','-.12')])
def test_valid_coordinate_boundaries(lat,lon):
    assert validate_records(pd.DataFrame([good(Latitude=lat,Longitude=lon)])).empty


def test_longitude_range_and_false_not_missing():
    report=validate_records(pd.DataFrame([good(Longitude=181,Email=False)]))
    assert len(report)==2 and set(report['Issue type'])=={'Invalid'}


@pytest.mark.parametrize("email", ['hello@example.com','a+b@example.co.uk'])
def test_valid_email(email):
    assert valid_email(email)


@pytest.mark.parametrize("email", ['bad','a@','a@@b.com','a b@example.com','a..b@example.com','a@-bad.com',' a@example.com '])
def test_invalid_email(email):
    assert not valid_email(email)


@pytest.mark.parametrize("url", ['https://example.com/path?q=x','http://www.example.com','example.com/page','//example.com','https://127.0.0.1:8080'])
def test_valid_website(url):
    assert valid_website(url)


@pytest.mark.parametrize("url", ['https://','javascript:alert(1)','ftp://example.com','https://bad host.com','https://example.com:99999','https://[bad','https://-bad.com','https://a:b@example.com'])
def test_invalid_website(url):
    assert not valid_website(url)


def test_absent_columns_empty_and_counts():
    report=validate_records(pd.DataFrame(index=[1,1]))
    assert report.empty
    assert issue_counts(report).empty
    assert validate_records(pd.DataFrame()).empty
    assert issue_counts(validate_records(pd.DataFrame())).empty


def test_original_identifiers_and_multiple_issues():
    frame=pd.DataFrame([good(Latitude=120,Email='bad'),good()],index=[7,7])
    report=validate_records(frame,['R0002','R0005'])
    assert report['Record identifier'].tolist()==['R0002','R0002']
    assert set(report['Field'])=={'Latitude','Email'}
    with pytest.raises(ValueError):
        validate_records(frame,['R0002','R0002'])


@pytest.mark.parametrize('phone', ['+44 (20) 7946-0100','020 7946 0100','+1 202-555-0100 ext. 12','1234567','+442079460100 x123'])
def test_valid_phone_formats(phone):
    assert valid_phone(phone)


@pytest.mark.parametrize('phone', ['call-us','123','1234567890123456','++442079460100','(020 7946 0100',False,0])
def test_invalid_phone_formats(phone):
    assert not valid_phone(phone)
    report=validate_records(pd.DataFrame([good(Phone=phone)]))
    assert len(report)==1 and report.iloc[0]['Field']=='Phone'


def test_missing_fields_never_inflate_invalid_counts():
    frame=pd.DataFrame([{'Latitude':120}, {'Email':'bad'}, {'Phone':'call-me'}, {}])
    report=validate_records(frame)
    assert len(report)==3 and report['Record identifier'].nunique()==3
    assert set(report['Issue type'])=={'Invalid'}
    assert issue_counts(report)['Records affected'].sum()==3
