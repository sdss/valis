
# encoding: utf-8
#
import pytest

from valis.utils.paths import build_boss_path, build_apogee_path, build_file_path


boss_res = {'field': 15078, 'mjd': 59187, 'run2d': 'v6_1_2', 'obs': 'APO',
            'nexp': 4, 'catalogid': 4291570940, 'sdss_id': 54392544}
astra_res = {'sdss_id': 54392544, 'catalogid': 27021597850854486, 'v_astra': '0.5.0'}
apogee_res = {'apogee_id': '2M00104221+5744297', 'starver': '59953', 'telescope': 'apo25m',
              'apred_vers': '1.2', 'healpix': 14966}


@pytest.mark.parametrize('lite', [True, False])
def test_build_boss_path(lite):
    """ test we can create a boss spec path """
    path = build_boss_path(boss_res, 'IPL3', lite=lite, ignore_existence=True)
    assert 'sas/ipl-3/spectro/boss/redux/' in path
    ll = 'lite' if lite else 'full'
    assert f'spectra/{ll}/015078/59187/spec-015078-59187-4291570940.fits' in path


def test_build_apstar_path():
    """ test we can create a apogee apstar path """
    path = build_apogee_path(apogee_res, "IPL3", ignore_existence=True)
    assert 'ipl-3/spectro/apogee/redux/1.2/stars/apo25m' in path
    assert '2M00104221+5744297' in path


def test_build_file_path():
    """ test we can create a astra mwmstar path """
    path = build_file_path(astra_res, 'mwmStar', 'IPL3', defaults={'component': ''}, ignore_existence=True)
    assert 'sas/ipl-3/spectro/astra/0.5.0/spectra' in path
    assert '25/44/mwmStar-0.5.0-54392544.fits' in path

def test_build_fails():
    """ test build filepath fails correctly """
    with pytest.raises(ValueError, match="Not all path keywords found in model fields or tags: ['component']*"):
        build_file_path(astra_res, 'mwmStar', 'IPL3', ignore_existence=True)
