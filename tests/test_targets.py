# encoding: utf-8
#

from unittest.mock import Mock

import numpy as np
import pytest
from astropy.table import Table

from valis.routes import target as target_routes




def get_data(response):
    """check a response"""
    assert response.status_code == 200
    return response.json()


def test_resolve_target_name(client):
    """test we resolve a target name"""
    response = client.get("/target/resolve/name?name=MaNGA 7443-12701")
    data = get_data(response)
    assert data['coordinate']['value'] == [230.50745896, 43.53232817]
    assert data['coordinate']['unit'] == 'deg'
    assert data['name'] in ("LEDA 2223006", "2MASX J15220182+4331560")


def test_resolve_target_coord(client):
    """test we resolve a target coordinate"""
    response = client.get("/target/resolve/coord?coord=230.50745896&coord=43.53232817")
    data = get_data(response)
    assert len(data) == 3
    assert data[0]['main_id'] in ("LEDA 2223006", "2MASX J15220182+4331560")
    assert data[0]['ra'] == "15 22 01.7901"
    assert data[0]['dec'] == "+43 31 56.381"
    assert data[0]['distance_result']['value'] == 0
    assert data[0]['distance_result']['unit'] == 'arcsec'


def test_get_vacs(client, monkeypatch):
    rows = Table({
        "sdss_id": [101],
        "mjd": [59000],
        "plate": [100],
        "fiberid": [10],
        "map2madgics": [1],
        "rv_verr_sys_th": [0.1],
    })
    monkeypatch.setattr(target_routes, "get_madgic_rows", lambda sdss_id: rows)

    response = client.get("/target/vacs/101")
    data = get_data(response)

    assert response.status_code == 200
    assert data["apmadgics"][0]["sdss_id"] == 101
    assert data["apmadgics"][0]["rv_verr_sys_th"] == 0.1


def test_get_vacs_without_apmadgics_data(client, monkeypatch):
    def no_rows(sdss_id):
        raise ValueError(f"SDSS ID {sdss_id} not found")

    monkeypatch.setattr(target_routes, "get_madgic_rows", no_rows)

    response = client.get("/target/vacs/999")

    assert response.status_code == 200
    data = get_data(response)
    assert data == {}


def test_get_apmadgics_spectrum(client, monkeypatch):
    spectrum = {
        "flux": np.array([1.0, 2.0]),
        "wavelength": np.array([15000.0, 15001.0]),
        "unit_wavelength": "Angstrom",
        "unit_flux": "1e-17 erg / (Angstrom cm2 s)",
    }
    get_spectrum = Mock(return_value=spectrum)
    monkeypatch.setattr(target_routes, "get_madgic_spectrum", get_spectrum)

    response = client.get(
        "/target/apmadgics/101?magic_id=2&mjd=59001&plate=100&fiberid=11&star_prior=th"
    )

    assert response.status_code == 200
    data = get_data(response)
    assert data["flux"] == [1.0, 2.0]
    assert data["wavelength"] == [15000.0, 15001.0]
    get_spectrum.assert_called_once_with(
        sdss_id=101,
        magicid=2,
        mjd=59001,
        plate=100,
        fiberid=11,
        star_prior="th",
    )
