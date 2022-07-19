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

import pathlib
import shutil

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


@pytest.fixture()
def monkeymask(monkeypatch, tmp_path):
    svn_dir = tmp_path / 'svn'
    mask_dir = svn_dir / 'repo/sdss/idlutils/trunk/data/sdss/sdssMaskbits.par'
    mask_dir.parent.mkdir(parents=True, exist_ok=True)
    testpath = pathlib.Path(__file__).parent / 'data/sdssMaskbits.par'
    shutil.copy2(testpath, mask_dir)

    monkeypatch.setenv('SDSS_SVN_ROOT', str(svn_dir))