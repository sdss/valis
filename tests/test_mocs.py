# encoding: utf-8
#


def get_data(response):
    assert response.status_code == 200
    return response.json()


def test_moc_json(client, testmoc):
    response = client.get("/mocs/json?survey=manga&release=DR17")
    data = get_data(response)

    assert data['order'] == 10
    assert data['moc']['9'] == [224407,224413,664253,664290,664292]
