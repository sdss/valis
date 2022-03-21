# encoding: utf-8
#
# main.py

from pytest import mark


def test_main(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"Hello SDSS": "This is the FastAPI World", 'release': "WORK"}
    
@mark.parametrize('release', ['WORK', 'DR17'])
def test_main_with_release(client, release):
    response = client.get("/", params={"release": release})
    assert response.status_code == 200
    assert response.json() == {"Hello SDSS": "This is the FastAPI World", 'release': release}
    
