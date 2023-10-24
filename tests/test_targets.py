# encoding: utf-8
#


def get_data(response):
    assert response.status_code == 200
    return response.json()


def test_resolve_target_name(client):
    response = client.get("/target/resolve/name?name=MaNGA 7443-12701")
    data = get_data(response)
    assert data['coordinate']['value'] == [230.50745896, 43.53232817]
    assert data['coordinate']['unit'] == 'deg'
    assert data['name'] in ("LEDA 2223006", "2MASX J15220182+433156")


def test_resolve_target_coord(client):
    response = client.get("/target/resolve/coord?coord=230.50745896&coord=43.53232817")
    data = get_data(response)
    assert len(data) == 1
    assert data[0]['main_id'] in ("LEDA 2223006", "2MASX J15220182+433156")
    assert data[0]['ra'] == "15 22 01.7901"
    assert data[0]['dec'] == "+43 31 56.381"
    assert data[0]['distance_result']['value'] == 0
    assert data[0]['distance_result']['unit'] == 'arcsec'

