# encoding: utf-8
#

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