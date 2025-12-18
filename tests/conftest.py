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


def create_fits(name='testfile.fits'):
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


def mocfits():
    """ create a test moc fits """
    # create the FITS HDUList
    header = fits.Header([('MOCTOOL', 'CDSjavaAPI-4.1', 'Name of the MOC generator'),
                          ('MOCORDER', 29, 'MOC resolution (best order)')])
    primary = fits.PrimaryHDU()
    cols = [fits.Column(name='NPIX', format='K', array=np.arange(5))]
    bindata = fits.BinTableHDU.from_columns(cols, name='MOC', header=header)
    return fits.HDUList([primary, bindata])


@pytest.fixture()
def testmoc(setup_sas):
    moc = os.getenv("SDSS_HIPS", "")
    path = pathlib.Path(moc) / 'dr17/manga/Moc.json'
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)

    # create fake json
    with open(path, 'w') as f:
        f.write("#MOCORDER 10\n")
        f.write("""{"9":[224407,224413,664253,664290,664292]}\n""")

    # create fake fits
    moc = mocfits()
    moc.writeto(path.with_suffix('.fits'), overwrite=True)


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


# LVM Test Fixtures

def create_mock_sframe(n_wave=100, n_fibers=20, expnum=43064):
    """Create minimal SFrame FITS for testing (DRP output)"""
    primary_hdr = fits.Header([
        ('EXPNUM', expnum, 'Exposure number'),
        ('MJD', 60859, 'Modified Julian Date'),
        ('TILEID', 1048982, 'Tile ID'),
    ])
    primary = fits.PrimaryHDU(header=primary_hdr)

    wave = np.linspace(3600, 9800, n_wave).astype(np.float32)
    flux = np.random.rand(n_fibers, n_wave).astype(np.float32) * 1e-17
    ivar = np.ones((n_fibers, n_wave), dtype=np.float32) * 1e34
    sky = np.random.rand(n_fibers, n_wave).astype(np.float32) * 1e-18
    lsf = np.ones((n_fibers, n_wave), dtype=np.float32) * 2.5

    # SLITMAP table with essential columns
    slitmap_cols = [
        fits.Column('fiberid', 'K', array=np.arange(1, n_fibers+1)),
        fits.Column('telescope', '5A', array=['Sci'] * (n_fibers-4) + ['SkyE', 'SkyW', 'Spec', 'Spec']),
        fits.Column('fibstatus', 'K', array=np.zeros(n_fibers, dtype=int)),
        fits.Column('ra', 'D', array=np.random.uniform(0, 360, n_fibers)),
        fits.Column('dec', 'D', array=np.random.uniform(-90, 90, n_fibers)),
    ]

    return fits.HDUList([
        primary,
        fits.ImageHDU(flux, name='FLUX'),
        fits.ImageHDU(ivar, name='IVAR'),
        fits.ImageHDU(wave, name='WAVE'),
        fits.ImageHDU(sky, name='SKY'),
        fits.ImageHDU(ivar.copy(), name='SKY_IVAR'),
        fits.ImageHDU(lsf, name='LSF'),
        fits.BinTableHDU.from_columns(slitmap_cols, name='SLITMAP'),
    ])


def create_mock_dap_output(n_wave=100, n_fibers=10):
    """Create minimal DAP output FITS"""
    # Shape: (n_components=9, n_fibers, n_wave)
    data = np.random.rand(9, n_fibers, n_wave).astype(np.float32) * 1e-17

    hdu = fits.PrimaryHDU(data)
    hdu.header['CRVAL1'] = 3600.0
    hdu.header['CDELT1'] = 0.5
    hdu.header['CRPIX1'] = 1

    return fits.HDUList([hdu])


def create_mock_dap_main(n_fibers=10, expnum=43064):
    """Create minimal DAP main FITS with PT table"""
    pt_cols = [
        fits.Column('id', '10A', array=[f'{expnum}.{i}' for i in range(3, 3+n_fibers)]),
        fits.Column('ra', 'D', array=np.random.uniform(0, 360, n_fibers)),
        fits.Column('dec', 'D', array=np.random.uniform(-90, 90, n_fibers)),
        fits.Column('mask', 'L', array=[True] * n_fibers),
        fits.Column('fiberid', 'K', array=np.arange(3, 3+n_fibers)),
        fits.Column('exposure', 'K', array=[expnum] * n_fibers),
    ]

    return fits.HDUList([
        fits.PrimaryHDU(),
        fits.BinTableHDU.from_columns(pt_cols, name='PT'),
    ])


def create_mock_drpall(expnum=43064, drpver='1.2.0'):
    """Create minimal drpall FITS file"""
    cols = [
        fits.Column('EXPNUM', 'K', array=[expnum]),
        fits.Column('MJD', 'K', array=[60859]),
        fits.Column('TILEID', 'K', array=[1048982]),
        fits.Column('location', '120A', array=[f'sdsswork/lvm/spectro/redux/{drpver}/1048XX/1048982/60859/lvmSFrame-{str(expnum).zfill(8)}.fits']),
        fits.Column('drpver', '10A', array=[drpver]),
    ]

    return fits.HDUList([
        fits.PrimaryHDU(),
        fits.BinTableHDU.from_columns(cols),
    ])


@pytest.fixture()
def setup_lvm_sas(monkeypatch, tmp_path):
    """Create mock LVM directory structure for testing"""
    # Create mock SAS structure inside tmp_path
    sas_root = tmp_path / 'sas'
    sas_base = sas_root / 'sdsswork'
    
    drpver = '1.2.0'
    expnum = 43064
    tile_id = 1048982
    mjd = 60859

    # Create drpall
    drpall_dir = sas_base / 'lvm' / 'spectro' / 'redux' / drpver
    drpall_dir.mkdir(parents=True)
    drpall_file = drpall_dir / f'drpall-{drpver}.fits'
    create_mock_drpall(expnum, drpver).writeto(drpall_file)

    # Create SFrame (DRP output)
    sframe_dir = sas_base / 'lvm' / 'spectro' / 'redux' / drpver / f'{str(tile_id)[:4]}XX' / str(tile_id) / str(mjd)
    sframe_dir.mkdir(parents=True)
    sframe_file = sframe_dir / f'lvmSFrame-{str(expnum).zfill(8)}.fits'
    create_mock_sframe(n_wave=100, n_fibers=20, expnum=expnum).writeto(sframe_file)

    # Create DAP files
    dap_dir = sas_base / 'lvm' / 'spectro' / 'analysis' / drpver / f'{str(tile_id)[:4]}XX' / str(tile_id) / str(mjd) / str(expnum).zfill(8)
    dap_dir.mkdir(parents=True)

    dap_output_file = dap_dir / f'dap-rsp108-sn20-{str(expnum).zfill(8)}.output.fits'
    create_mock_dap_output(n_wave=100, n_fibers=10).writeto(dap_output_file)

    dap_main_file = dap_dir / f'dap-rsp108-sn20-{str(expnum).zfill(8)}.dap.fits.gz'
    create_mock_dap_main(n_fibers=10, expnum=expnum).writeto(dap_main_file)

    # Set SAS_BASE_DIR environment variable to point to mock directory
    # The lvm.py code constructs paths as: /data/sdss/sas/sdsswork/...
    # We need to replace /data/sdss/sas with our tmp_path/sas
    monkeypatch.setenv('SAS_BASE_DIR', str(sas_root))
    
    # Monkeypatch the hardcoded /data/sdss/sas path in lvm.py
    import valis.routes.lvm as lvm_module
    
    original_get_drpall = lvm_module.get_LVM_drpall_record
    original_get_sframe = lvm_module.get_SFrame_filename
    original_get_dap = lvm_module.get_DAP_filenames
    
    async def patched_get_drpall(expnum, drpver):
        import asyncio
        from astropy.io import fits
        loop = asyncio.get_event_loop()
        
        drp_file = str(sas_root / f"sdsswork/lvm/spectro/redux/{drpver}/drpall-{drpver}.fits")
        
        file_exists = await loop.run_in_executor(None, os.path.exists, drp_file)
        if not file_exists:
            drp_file = str(sas_root / f"sdsswork/lvm/spectro/redux/{lvm_module.LAST_DRP_VERSION}/drpall-{lvm_module.LAST_DRP_VERSION}.fits")
            file_exists = await loop.run_in_executor(None, os.path.exists, drp_file)
            if not file_exists:
                raise FileNotFoundError(f"DRPall file not found: {drp_file}")
        
        def read_fits():
            drpall = fits.getdata(drp_file)
            record = drpall[drpall['EXPNUM'] == expnum][0]
            # Return lowercase keys for consistency with real FITS behavior
            return {name.lower() if name.isupper() else name: record[name] for name in drpall.names}
        
        return await loop.run_in_executor(None, read_fits)
    
    async def patched_get_sframe(expnum, drpver):
        drp_record = await patched_get_drpall(expnum, drpver)
        location = drp_record['location'].decode() if isinstance(drp_record['location'], bytes) else drp_record['location']
        file = str(sas_root / location)
        
        if drp_record['drpver'] != drpver:
            file = file.replace(drp_record['drpver'], drpver)
        
        return file
    
    async def patched_get_dap(expnum, dapver):
        import asyncio
        drp_record = await patched_get_drpall(expnum, dapver)
        
        tile_id = int(drp_record['tileid'])
        mjd = int(drp_record['mjd'])
        suffix = str(expnum).zfill(8)
        tile_prefix = f"{str(tile_id)[:4]}XX" if tile_id != 11111 else "0011XX"
        
        base_path = sas_root / 'sdsswork' / 'lvm' / 'spectro' / 'analysis' / dapver / tile_prefix / str(tile_id) / str(mjd) / suffix
        relative_base = f"sdsswork/lvm/spectro/analysis/{dapver}/{tile_prefix}/{tile_id}/{mjd}/{suffix}"
        
        loop = asyncio.get_event_loop()
        
        async def find_file(base_name):
            for ext in ['.fits', '.fits.gz']:
                filepath = f"{base_name}{ext}"
                if await loop.run_in_executor(None, os.path.exists, filepath):
                    return filepath
            raise FileNotFoundError(f"Neither {base_name}.fits nor {base_name}.fits.gz exists")
        
        dap_file = await find_file(str(base_path / f'dap-rsp108-sn20-{suffix}.dap'))
        output_file = await find_file(str(base_path / f'dap-rsp108-sn20-{suffix}.output'))
        relative_path = f"{relative_base}/dap-rsp108-sn20-{suffix}.output.fits.gz"
        
        return dap_file, output_file, relative_path
    
    monkeypatch.setattr(lvm_module, 'get_LVM_drpall_record', patched_get_drpall)
    monkeypatch.setattr(lvm_module, 'get_SFrame_filename', patched_get_sframe)
    monkeypatch.setattr(lvm_module, 'get_DAP_filenames', patched_get_dap)

    return {
        'sas_base': sas_base,
        'sas_root': sas_root,
        'drpver': drpver,
        'expnum': expnum,
        'tile_id': tile_id,
        'mjd': mjd,
        'tmp_path': tmp_path,
    }
