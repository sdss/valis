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

import os
import pathlib
import shutil

import pytest
import numpy as np
from astropy.io import fits
from fastapi.testclient import TestClient

from tree import Tree
from sdss_access.path import Path
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


def create_fits(name = 'testfile.fits'):
    """ create a test fits hdulist """

    # create the FITS HDUList
    header = fits.Header([('filename', name, 'name of the file'),
                          ('testver', '0.1.0', 'version of the file')])
    primary = fits.PrimaryHDU(header=header)
    imdata = fits.ImageHDU(name='FLUX', data=np.ones([5, 5]))
    cols = [fits.Column(name='object', format='20A', array=['a', 'b', 'c']),
            fits.Column(name='param', format='E', array=np.random.rand(3), unit='m'),
            fits.Column(name='flag', format='I', array=np.arange(3))]
    bindata = fits.BinTableHDU.from_columns(cols, name='PARAMS')

    return fits.HDUList([primary, imdata, bindata])


@pytest.fixture()
def setup_sas(monkeypatch, tmp_path, mocker):
    """ fixtures that sets up temp SAS and a TEST_REDUX directory """
    sas_dir = tmp_path / 'sas'

    # create dirs for test
    test_dir = sas_dir / 'dr17' / 'test/spectro/redux'
    test_dir.mkdir(parents=True)
    monkeypatch.setenv("SAS_BASE_DIR", str(sas_dir))
    monkeypatch.setenv("TEST_REDUX", str(test_dir))

    # create dirs for mocs
    moc_dir = sas_dir / 'sdsswork/sandbox/hips'
    moc_dir.mkdir(parents=True)
    monkeypatch.setenv("SDSS_HIPS", str(moc_dir))

    mocker.patch('valis.routes.base.Tree', new=MockTree)
    mocker.patch('valis.routes.base.Path', new=MockPath)
    #mocker.patch('datamodel.validate.check.Tree', new=MockTree)


@pytest.fixture()
def testfile(setup_sas):
    # write out the file to the designated path
    name = 'testfile_A.fits'
    hdu = create_fits(name)

    redux = os.getenv("TEST_REDUX", "")
    path = pathlib.Path(redux) / 'v1' / name
    if not path.exists():
       path.parent.mkdir(parents=True, exist_ok=True)

    hdu.writeto(path, overwrite=True)
    return path


@pytest.fixture()
def testmoc(setup_sas):
    moc = os.getenv("SDSS_HIPS", "")
    path = pathlib.Path(moc) / 'dr17/manga/Moc.json'
    if not path.exists():
       path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, 'w') as f:
        f.write("#MOCORDER 10\n")
        f.write("""{"9":[224407,224413,664253,664290,664292]}\n""")

class MockTree(Tree):
    """ mock out the Tree class to insert test file """

    def _create_environment(self, cfg=None, sections=None):
        environ = super(MockTree, self)._create_environment(cfg=cfg, sections=sections)
        env = 'testwork' if self.config_name in ['sdsswork', 'sdss5'] else self.config_name.lower()
        path = os.getenv("TEST_REDUX").replace('testwork', env)
        environ['general'].update({'TEST_REDUX': path})
        return environ

    def _create_paths(self, cfg=None):
        paths = super(MockTree, self)._create_paths(cfg=cfg)
        paths.update({'test': '$TEST_REDUX/{ver}/testfile_{id}.fits'})
        paths.update({'sdss_moc': '$SDSS_HIPS/{release}/{survey}/Moc.{ext}'})
        return paths

class MockPath(Path):
    """ mock out the Path class to insert test file """

    def __init__(self, *args, **kwargs):
        super(MockPath, self).__init__(*args, **kwargs)
        self.templates.update({'test': '$TEST_REDUX/{ver}/testfile_{id}.fits'})
