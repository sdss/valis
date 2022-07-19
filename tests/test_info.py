# encoding: utf-8
#

import pytest
try:
    from datamodel.products import SDSSDataModel
except ImportError:
    SDSSDataModel = None


pytestmark = pytest.mark.skipif(not SDSSDataModel, reason="SDSS datamodel product not available.")


def get_data(response):
    assert response.status_code == 200
    return response.json()


def test_info(client):
    response = client.get("/info")
    data = get_data(response)
    assert 'releases' in data
    assert 'surveys' in data
    assert 'phases' in data
    assert "General metadata for the Sloan Digital Sky Survey (SDSS)" in data['description']


def test_info_releases(client):
    response = client.get("/info/releases")
    data = get_data(response)
    assert 'releases' in data

    rel = {"name": "DR17", "description": "SDSS public data release 17",
           "public": True, "release_date": "2021-12-06"}
    assert rel in data['releases']


def test_info_surveys(client):
    response = client.get("/info/surveys")
    data = get_data(response)
    assert 'surveys' in data

    surv =     {"name": "MaNGA", "long": "Mapping Nearby Galaxies at Apache Point Observatory",
                "description": "A wide-field optical spectroscopic IFU survey of extragalactic sources to study galaxy dynamics and kinematics",
                "phase": { "name": "Phase-IV", "id": 4, "start": 2014, "end": 2020, "active": False},
                "id": "manga", "aliases": []}
    assert surv in data['surveys']


def test_info_phases(client):
    response = client.get("/info/phases")
    data = get_data(response)
    assert 'phases' in data

    phase = {"name": "Phase-III", "id": 3, "start": 2008, "end": 2014, "active": False}
    assert phase in data['phases']


def test_info_tags(client):
    response = client.get("/info/tags")
    data = get_data(response)
    assert 'tags' in data

    tag = {"version": {"name": "drpver",
                       "description": "software tag key for the MaNGA Data Reduction Pipeline (DRP)"
                       },
           "tag": "v3_1_1",
           "release": {"name": "DR17", "description": "SDSS public data release 17",
                       "public": True, "release_date": "2021-12-06"},
            "survey": {"name": "MaNGA",
                       "long": "Mapping Nearby Galaxies at Apache Point Observatory",
                       "description": "A wide-field optical spectroscopic IFU survey of extragalactic sources to study galaxy dynamics and kinematics",
                       "phase": {"name": "Phase-IV", "id": 4, "start": 2014,
                                 "end": 2020, "active": False},
                       "id": "manga",
                       "aliases": []
                       }
            }
    assert tag in data['tags']


def test_info_tags_release(client):
    response = client.get("/info/tags?group=release")
    data = get_data(response)
    assert 'tags' in data
    assert 'DR17' in data['tags']
    assert 'manga' in data['tags']['DR17']
    exp = {"drpver": "v3_1_1", "dapver": "3.1.0"}
    assert exp == data['tags']['DR17']['manga']


def test_info_tags_survey(client):
    response = client.get("/info/tags?group=survey")
    data = get_data(response)
    assert 'tags' in data
    assert 'manga' in data['tags']
    assert 'DR17' in data['tags']['manga']
    exp = {"drpver": "v3_1_1", "dapver": "3.1.0"}
    assert exp == data['tags']['manga']['DR17']


def test_info_products(client):
    response = client.get("/info/products?release=DR15")
    data = get_data(response)
    assert 'sdR' in data['products']


def test_info_products_model(client):
    response = client.get("/info/products/sdR?release=DR15")
    data = get_data(response)
    assert 'general' in data
    assert data["general"]['name'] == "sdR"
    assert data["general"]['short'] == "BOSS spectrograph data"


def test_info_products_schema(client):
    response = client.get("/info/schema/sdR?release=DR15")
    data = get_data(response)
    assert data["title"] == "ProductModel"
    assert "Pydantic model representing a data product JSON file" in data['description']