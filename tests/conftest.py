# encoding: utf-8
#
# conftest.py

"""
Here you can add fixtures that will be used for all the tests in this
directory. You can also add conftest.py files in underlying subdirectories.
Those conftest.py will only be applies to the tests in that subdirectory and
underlying directories. See https://docs.pytest.org/en/2.7.3/plugins.html for
more information.
"""

import pytest
from fastapi.testclient import TestClient
from valis.main import app
from valis.routes.auth import set_auth

async def override_auth():
    return {"token": None}

app.dependency_overrides[set_auth] = override_auth

@pytest.fixture(scope='module')
def client():
    yield TestClient(app)
