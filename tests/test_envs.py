# encoding: utf-8
#


def test_envs_default_dr17(client):
    response = client.get("/envs")
    assert response.status_code == 200
    data = response.json()

    assert 'BHM' not in data['envs']
    assert 'MANGA' in data['envs']
    assert 'APOGEE_THEJOKER' in data['envs']['APOGEE']

def test_envs_sdss5(client):
    response = client.get("/envs?release=WORK")
    assert response.status_code == 200
    data = response.json()

    assert 'BHM' in data['envs']
    assert 'ROBOSTRATEGY_DATA' in data['envs']['SANDBOX']
    assert 'APOGEE_DATA_N' in data['envs']['DATA']

def test_envs_releases(client):
    response = client.get("/envs/releases/")
    assert response.status_code == 200
    data = response.json()

    assert {'WORK', 'DR15', 'DR17', 'IPL2'}.issubset(set(data))
    assert not {'WORK', 'MPL10', 'IPL2'}.issubset(set(data))

def test_envs_resolve_sdss5(client):
    response = client.get("/envs/resolve?release=WORK")
    assert response.status_code == 200
    data = response.json()

    assert 'sdsswork/sandbox/robostrategy' in data['envs']['SANDBOX']['ROBOSTRATEGY_DATA']
    assert 'sdsswork/data/apogee/apo' in data['envs']['DATA']['APOGEE_DATA_N']

def test_envs_resolve_dr17(client):
    response = client.get("/envs/resolve?release=dr17")
    assert response.status_code == 200
    data = response.json()

    assert 'dr17/manga/spectro/redux' in data['envs']['MANGA']['MANGA_SPECTRO_REDUX']
    assert 'dr17/apogee/vac/apogee-thejoker' in data['envs']['APOGEE']['APOGEE_THEJOKER']