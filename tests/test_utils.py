
# encoding: utf-8
#
import pytest

from valis.utils.paths import build_astra_path, build_boss_path, build_apogee_path, build_file_path, get_pathcomp


datamodel = pytest.importorskip("datamodel")


boss_res = {'field': 15078, 'mjd': 59187, 'run2d': 'v6_2_1', 'obs': 'APO',
            'nexp': 4, 'catalogid': 4291570940, 'sdss_id': 54392544}
astra_res = {'sdss_id': 54392544, 'catalogid': 27021597850854486, 'v_astra': '0.8.1'}
apogee_res = {'apogee_id': '2M00104221+5744297', 'starver': '59953', 'telescope': 'apo25m',
              'apred_vers': '1.5', 'healpix': 14966, 'mjd': '59953', 'fiberid': 199, 'plate': 102078, 'field': 15078}


@pytest.mark.parametrize('lite', [True, False])
def test_build_boss_path(lite):
    """ test we can create a boss spec path """
    path = build_boss_path(boss_res, 'DR20', lite=lite, ignore_existence=True)
    assert 'sas/dr20/spectro/boss/redux/' in path
    ll = 'lite' if lite else 'full'
    assert f'spectra/daily/{ll}/015XXX/015078/59187/spec-015078-59187-4291570940.fits' in path


@pytest.mark.parametrize('name, part, obj', [('apStar', 'stars', '2M00104221+5744297'),
                                  ('apVisit', 'visit', '102078-59953-199')],
                                  ids=['star', 'visit'])
def test_build_apstar_path(name, part, obj):
    """ test we can create a apogee apstar path """
    apogee_res.update({'file': f"{name}-{apogee_res['apogee_id']}-{apogee_res['starver']}.fits"})
    path = build_apogee_path(apogee_res, "DR20", ignore_existence=True)
    assert f'dr20/spectro/apogee/redux/1.5/{part}/apo25m' in path
    assert obj in path
    assert name in path


def test_build_file_path():
    """ test we can create a astra mwmstar path """
    path = build_file_path(astra_res, 'mwmStar', 'DR20', defaults={'component': ''}, ignore_existence=True)
    assert 'sas/dr20/spectro/astra/0.8.1/spectra' in path
    assert '25/44/mwmStar-0.8.1-54392544.fits' in path


@pytest.mark.parametrize('name', ['mwmStar', 'mwmVisit'])
def test_build_astra_path(name):
    """ test we can create a astra mwmstar path """
    path = build_astra_path(astra_res, "DR20", name=name, ignore_existence=True)
    assert 'dr20/spectro/astra/0.8.1/spectra' in path
    assert name in path

@pytest.mark.parametrize('piece, exp',
                         [('url', 'https://data.sdss5.org/sas/dr20/spectro'),
                          ('location', 'dr20/spectro/astra/'),
                          ('dir', '/tmp/sas/dr20/spectro'),
                          ('name', 'mwmStar-0.8.1-54459273.fits')],
                         ids=['url', 'location', 'dir', 'name'])
def test_get_pathcomp(monkeypatch, piece, exp):
    """ test we can get path components from a path """
    monkeypatch.setenv('SAS_BASE_DIR', '/tmp/sas')
    path = '/tmp/sas/dr20/spectro/astra/0.8.1/spectra/star/92/73/mwmStar-0.8.1-54459273.fits'
    comp = get_pathcomp(path, 'DR20', piece=piece)
    assert comp.startswith(exp)

    comp = get_pathcomp(path, 'DR20', piece='exists')
    assert comp is False
