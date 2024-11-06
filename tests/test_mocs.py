# encoding: utf-8
#
import io
from astropy.io import fits

def get_data(response):
    assert response.status_code == 200
    return response.json()


def test_moc_json(client, testmoc):
    response = client.get("/mocs/json?survey=manga&release=DR17")
    data = get_data(response)

    assert data['order'] == 10
    assert data['moc']['9'] == [224407,224413,664253,664290,664292]


def test_moc_fits(client, testmoc):
    response = client.get("/mocs/fits?survey=manga&release=DR17")
    assert response.status_code == 200
    with fits.open(io.BytesIO(response.content)) as hdu:
        assert hdu[1].header['EXTNAME'] == 'MOC'
        assert hdu[1].header['MOCORDER'] == 29
        assert "NPIX" in hdu[1].data.columns.names


def test_list_mocs(client, testmoc):
    response = client.get("/mocs/list")
    data = get_data(response)

    assert 'dr17:manga' in data
