# encoding: utf-8
#

import pytest
from fastapi.testclient import TestClient
from valis.main import app
from valis.db.queries import convert_coords

client = TestClient(app)

@pytest.mark.parametrize('ra, dec, exp',
                         [('315.01417', '35.299', (315.01417, 35.299)),
                          ('315.01417', '-35.299', (315.01417, -35.299)),
                          (315.01417, -35.299, (315.01417, -35.299)),
                          ('21h00m03.4008s', '+35d17m56.4s', (315.01417, 35.299)),
                          ('21:00:03.4008', '+35:17:56.4', (315.01417, 35.299)),
                          ('21 00 03.4008', '+35 17 56.4', (315.01417, 35.299)),
                          ],
                         ids=['dec1', 'dec2', 'dec3', 'hms1', 'hms2', 'hms3'])
def test_convert_coords(ra, dec, exp):
    """ test we can convert coordinates correctly """
    coord = convert_coords(ra, dec)
    assert coord == exp

def test_upload_file_csv():
    with open("tests/data/valid_targets.csv", "rb") as file:
        response = client.post("/query/upload", files={"file": ("valid_targets.csv", file, "text/csv")})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert len(data["data"]) > 0

def test_upload_file_txt():
    with open("tests/data/valid_targets.txt", "rb") as file:
        response = client.post("/query/upload", files={"file": ("valid_targets.txt", file, "text/plain")})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert len(data["data"]) > 0

def test_upload_file_invalid_ids():
    with open("tests/data/invalid_targets.csv", "rb") as file:
        response = client.post("/query/upload", files={"file": ("invalid_targets.csv", file, "text/csv")})
    assert response.status_code == 400
    data = response.json()
    assert "Invalid target IDs" in data["detail"]

def test_upload_file_with_coordinates():
    with open("tests/data/valid_coordinates.csv", "rb") as file:
        response = client.post("/query/upload", files={"file": ("valid_coordinates.csv", file, "text/csv")})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert len(data["data"]) > 0

def test_upload_file_with_mixed_data():
    with open("tests/data/mixed_data.csv", "rb") as file:
        response = client.post("/query/upload", files={"file": ("mixed_data.csv", file, "text/csv")})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert len(data["data"]) > 0
