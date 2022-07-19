# encoding: utf-8
#
import pytest

pytestmark = pytest.mark.usefixtures("monkeymask")

def get_data(response):
    assert response.status_code == 200
    return response.json()

def test_maskbits_list(client):
    import os
    print(os.getenv("SDSS_SVN_ROOT"))
    response = client.get("/maskbits/list")
    data = get_data(response)
    assert 'MANGA_DAPQUAL' in data['schema']
    assert 'APOGEE2_TARGET3' in data['schema']

def test_maskbits_schema(client):
    response = client.get("/maskbits/schema?schema=MANGA_DRP2QUAL")
    data = get_data(response)
    data = data['MANGA_DRP2QUAL']
    assert 'bit' in data
    assert 'RAMPAGINGBUNNY' in data['label']
    assert " Rampaging dust bunnies in IFU flats" in data['description']

def test_maskbits_bit_to_value(client):
    response = client.get("/maskbits/bits/value?bits=2&bits=8")
    data = get_data(response)
    assert data['value'] == 260

def test_maskbits_bit_to_labels(client):
    response = client.get("/maskbits/bits/labels?bits=2&bits=8&schema=MANGA_DRP2QUAL")
    data = get_data(response)
    assert data['labels'] == ["EXTRACTBRIGHT", "ARCFOCUS"]

def test_maskbits_labels_to_value(client):
    response = client.get("/maskbits/labels/value?labels=BADIFU&labels=SCATFAIL&schema=MANGA_DRP2QUAL")
    data = get_data(response)
    assert data['value'] == 80

def test_maskbits_labels_to_bits(client):
    response = client.get("/maskbits/labels/bits?labels=BADIFU&labels=SCATFAIL&schema=MANGA_DRP2QUAL")
    data = get_data(response)
    assert data['bits'] == [4, 6]

def test_maskbits_value_to_bits(client):
    response = client.get("/maskbits/value/bits?value=260&schema=MANGA_DRP2QUAL")
    data = get_data(response)
    assert data['bits'] == [2, 8]

def test_maskbits_value_to_labels(client):
    response = client.get("/maskbits/value/labels?value=260&schema=MANGA_DRP2QUAL")
    data = get_data(response)
    assert data['labels'] == ["EXTRACTBRIGHT", "ARCFOCUS"]




