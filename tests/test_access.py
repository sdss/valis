# encoding: utf-8
#
import pytest

def test_paths(client):
    response = client.get("/paths")
    assert response.status_code == 200
    data = response.json() 
    assert 'rsCompleteness' in data['names']
    assert 'mangacube' not in data['names']

def test_paths_with_release(client):
    response = client.get("/paths?release=DR17")
    assert response.status_code == 200
    data = response.json() 
    assert 'rsCompleteness' not in data['names']
    assert 'mangacube' in data['names']

def test_paths_with_templates(client):
    response = client.get("/paths?templates=True")
    assert response.status_code == 200
    data = response.json() 
    assert 'rsCompleteness' in data
    assert r'$ROBOSTRATEGY_DATA/allocations/{plan}/rsCompleteness-{plan}-{observatory}.fits' in data['rsCompleteness']
    
@pytest.mark.parametrize('name, kwargs', 
                         [('platePlans', []), ('mangacube', ['ifu', 'drpver', 'plate', 'wave'])])   
def test_paths_keywords(client, name, kwargs):
    response = client.get(f"/paths/keywords/{name}?release=DR16")
    assert response.status_code == 200
    data = response.json() 
    assert data['name'] == name
    assert set(data['kwargs']) == set(kwargs)
    
def test_path_names_nokwargs(client):
    response = client.get("/paths/mangacube?release=DR16")
    assert response.status_code == 200
    data = response.json() 
    assert 'warning' in data
    assert data['warning'] == 'Warning: No kwargs specified to construct a path.  Returning only template.'
    
@pytest.mark.parametrize('name, params, exp', 
                         [('platePlans', 'release=DR16', 'data/sdss/platelist/trunk/platePlans.par'), 
                          ('mangacube', 'plate=8485&ifu=1901&wave=LOG&drpver=v2_4_3&release=DR16', 
                           'dr16/manga/spectro/redux/v2_4_3/8485/stack/manga-8485-1901-LOGCUBE.fits.gz')]) 
def test_path_names(client, name, params, exp):
    response = client.get(f"/paths/{name}?{params}")
    assert response.status_code == 200
    data = response.json() 
    assert exp in data['full']
    
@pytest.mark.parametrize('part, exp', [('location', "dr16/manga/spectro/redux/v2_4_3/8485/stack/manga-8485-1901-LOGCUBE.fits.gz"), 
                                       ('url', 'https://data.sdss.org/sas/dr16/manga/spectro/redux/v2_4_3/8485/stack/manga-8485-1901-LOGCUBE.fits.gz'), 
                                       ('file', "manga-8485-1901-LOGCUBE.fits.gz")], 
                         ids=['location', 'url', 'file'])
def test_path_name_parts(client, part, exp):
    response = client.get(f"/paths/mangacube?plate=8485&ifu=1901&wave=LOG&drpver=v2_4_3&release=DR16&part={part}")
    assert response.status_code == 200
    data = response.json() 
    assert part in data
    assert data[part] == exp

