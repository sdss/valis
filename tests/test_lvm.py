# encoding: utf-8
#
# test_lvm.py

"""
Tests for LVM endpoints
"""

import pytest
import numpy as np
from io import BytesIO
from PIL import Image
from astropy.io import fits


class TestLVMParsers:
    """Test query string parsers"""

    def test_parse_line_query_fiber_valid(self):
        from valis.routes.lvm import parse_line_query_fiber

        result = parse_line_query_fiber('id:1.2.0/43064/532;type:flux')
        assert result['id'] == '1.2.0/43064/532'
        assert result['type'] == 'flux'

    def test_parse_line_query_fiber_default_type(self):
        from valis.routes.lvm import parse_line_query_fiber

        result = parse_line_query_fiber('id:1.2.0/43064/532')
        assert result['type'] == 'flux'  # default

    def test_parse_line_query_fiber_invalid_type(self):
        from valis.routes.lvm import parse_line_query_fiber

        with pytest.raises(ValueError, match="'type' must be one of"):
            parse_line_query_fiber('id:1.2.0/43064/532;type:invalid')

    def test_parse_line_query_exposure_valid(self):
        from valis.routes.lvm import parse_line_query_exposure

        result = parse_line_query_exposure('id:1.2.0/43064;type:flux;method:median;telescope:Sci')
        assert result['id'] == '1.2.0/43064'
        assert result['type'] == 'flux'
        assert result['method'] == 'median'
        assert result['telescope'] == 'Sci'

    def test_parse_line_query_exposure_defaults(self):
        from valis.routes.lvm import parse_line_query_exposure

        result = parse_line_query_exposure('id:1.2.0/43064')
        assert result['type'] == 'flux'
        assert result['method'] == 'median'
        assert result['telescope'] == 'Sci'
        assert result['fibstatus'] == 0

    def test_parse_line_query_exposure_percentile(self):
        from valis.routes.lvm import parse_line_query_exposure

        result = parse_line_query_exposure('id:1.2.0/43064;method:percentile_90.5')
        assert result['method'] == 'percentile'
        assert result['percentile_value'] == 90.5

    def test_parse_line_query_dap_fiber_valid(self):
        from valis.routes.lvm import parse_line_query_dap_fiber

        result = parse_line_query_dap_fiber('id:1.2.0/43064/532;components:observed,stellar_continuum')
        assert result['id'] == '1.2.0/43064/532'
        assert result['components'] == ['observed', 'stellar_continuum']

    def test_parse_line_query_dap_fiber_default_components(self):
        from valis.routes.lvm import parse_line_query_dap_fiber

        result = parse_line_query_dap_fiber('id:1.2.0/43064/532')
        assert result['components'] == ['all']


class TestLVMDataEndpoints:
    """Test data retrieval endpoints"""

    def test_get_fiber_spectrum_single(self, client, setup_lvm_sas):
        """Test retrieving single fiber spectrum"""
        response = client.get('/lvm/fiber_spectrum/?l=id:1.2.0/43064/5;type:flux')
        assert response.status_code == 200

        data = response.json()
        assert 'wave' in data
        assert 'spectra' in data
        assert len(data['spectra']) == 1

        spectrum = data['spectra'][0]
        assert spectrum['expnum'] == 43064
        assert spectrum['fiberid'] == 5
        assert spectrum['drpver'] == '1.2.0'
        assert spectrum['spectrum_type'] == 'flux'
        assert 'flux' in spectrum
        assert len(data['wave']) == len(spectrum['flux'])

    def test_get_fiber_spectrum_multiple(self, client, setup_lvm_sas):
        """Test retrieving multiple fiber spectra"""
        response = client.get('/lvm/fiber_spectrum/?l=id:1.2.0/43064/5;type:flux&l=id:1.2.0/43064/6;type:sky')
        assert response.status_code == 200

        data = response.json()
        assert len(data['spectra']) == 2
        assert data['spectra'][0]['spectrum_type'] == 'flux'
        assert data['spectra'][1]['spectrum_type'] == 'sky'

    def test_get_fiber_spectrum_invalid_fiberid(self, client, setup_lvm_sas):
        """Test with out-of-range fiberid"""
        response = client.get('/lvm/fiber_spectrum/?l=id:1.2.0/43064/2000;type:flux')
        assert response.status_code == 400
        assert 'fiberid' in response.json()['detail'].lower()

    def test_get_fiber_spectrum_query_params(self, client, setup_lvm_sas):
        """Test using direct query parameters instead of l"""
        response = client.get('/lvm/fiber_spectrum/?expnum=43064&fiberid=5&drpver=1.2.0&type=flux')
        assert response.status_code == 200

        data = response.json()
        assert len(data['spectra']) == 1
        assert data['spectra'][0]['fiberid'] == 5

    def test_get_fiber_spectrum_missing_params(self, client, setup_lvm_sas):
        """Test without required parameters"""
        response = client.get('/lvm/fiber_spectrum/')
        assert response.status_code == 400

    def test_get_dap_fiber_output(self, client, setup_lvm_sas):
        """Test retrieving DAP fiber output"""
        response = client.get('/lvm/dap_fiber_output/?l=id:1.2.0/43064/3;components:all')
        assert response.status_code == 200

        data = response.json()
        assert 'wave' in data
        assert 'spectra' in data
        assert len(data['spectra']) == 1

        spectrum = data['spectra'][0]
        assert spectrum['expnum'] == 43064
        assert spectrum['fiberid'] == 3
        assert 'components' in spectrum
        assert 'ra' in spectrum
        assert 'dec' in spectrum

    def test_get_dap_fiber_output_specific_components(self, client, setup_lvm_sas):
        """Test retrieving specific DAP components"""
        response = client.get('/lvm/dap_fiber_output/?l=id:1.2.0/43064/3;components:observed,stellar_continuum')
        assert response.status_code == 200

        data = response.json()
        components = data['spectra'][0]['components']
        assert 'observed' in components
        assert 'stellar_continuum' in components
        # Should not contain other components
        assert len(components) == 2


class TestLVMPlotEndpoints:
    """Test plotting endpoints"""

    def test_plot_fiber_spectrum_png(self, client, setup_lvm_sas):
        """Test fiber spectrum plot generation (PNG)"""
        response = client.get('/lvm/plot_fiber_spectrum/?l=id:1.2.0/43064/5;type:flux&format=png')
        assert response.status_code == 200
        assert response.headers['content-type'] == 'image/png'

        # Verify it's a valid PNG
        img = Image.open(BytesIO(response.content))
        assert img.format == 'PNG'

    def test_plot_fiber_spectrum_multiple_lines(self, client, setup_lvm_sas):
        """Test plotting multiple fiber spectra"""
        response = client.get('/lvm/plot_fiber_spectrum/?l=id:1.2.0/43064/5;type:flux;color:red&l=id:1.2.0/43064/6;type:flux;color:blue')
        assert response.status_code == 200

    def test_plot_fiber_spectrum_with_styling(self, client, setup_lvm_sas):
        """Test plot with custom styling parameters"""
        response = client.get('/lvm/plot_fiber_spectrum/?l=id:1.2.0/43064/5;type:flux;color:red;lw:2&width=10&height=6&dpi=150')
        assert response.status_code == 200

    def test_plot_fiber_spectrum_invalid_matplotlib_param(self, client, setup_lvm_sas):
        """Test with invalid matplotlib parameter - API should return 500 error"""
        response = client.get('/lvm/plot_fiber_spectrum/?l=id:1.2.0/43064/5;type:flux;invalid_param:value')
        assert response.status_code == 500  # Internal server error
        assert 'detail' in response.json()
        assert 'Error creating plot' in response.json()['detail']
        assert 'invalid_param' in response.json()['detail']

    def test_plot_exposure_spectrum_png(self, client, setup_lvm_sas):
        """Test exposure spectrum plot generation"""
        response = client.get('/lvm/plot_exposure_spectrum/?l=id:1.2.0/43064&format=png')
        assert response.status_code == 200
        assert response.headers['content-type'] == 'image/png'

    def test_plot_exposure_spectrum_method(self, client, setup_lvm_sas):
        """Test different aggregation methods"""
        response = client.get('/lvm/plot_exposure_spectrum/?l=id:1.2.0/43064;method:mean')
        assert response.status_code == 200

        response = client.get('/lvm/plot_exposure_spectrum/?l=id:1.2.0/43064;method:median')
        assert response.status_code == 200

        response = client.get('/lvm/plot_exposure_spectrum/?l=id:1.2.0/43064;method:std')
        assert response.status_code == 200

    def test_plot_exposure_spectrum_telescope(self, client, setup_lvm_sas):
        """Test filtering by telescope"""
        response = client.get('/lvm/plot_exposure_spectrum/?l=id:1.2.0/43064;telescope:Sci')
        assert response.status_code == 200

    def test_plot_exposure_spectrum_pdf(self, client, setup_lvm_sas):
        """Test PDF output format"""
        response = client.get('/lvm/plot_exposure_spectrum/?l=id:1.2.0/43064&format=pdf')
        assert response.status_code == 200
        assert response.headers['content-type'] == 'application/pdf'

    def test_plot_exposure_spectrum_svg(self, client, setup_lvm_sas):
        """Test SVG output format"""
        response = client.get('/lvm/plot_exposure_spectrum/?l=id:1.2.0/43064&format=svg')
        assert response.status_code == 200
        assert response.headers['content-type'] == 'image/svg+xml'

    def test_plot_dap_fiber_spectrum_png(self, client, setup_lvm_sas):
        """Test DAP fiber spectrum plot generation (PNG)"""
        response = client.get('/lvm/plot_dap_fiber_spectrum/?l=id:1.2.0/43064/3;components:all&format=png')
        assert response.status_code == 200
        assert response.headers['content-type'] == 'image/png'

        # Verify it's a valid PNG
        img = Image.open(BytesIO(response.content))
        assert img.format == 'PNG'

    def test_plot_dap_fiber_spectrum_specific_components(self, client, setup_lvm_sas):
        """Test DAP plot with specific components"""
        response = client.get('/lvm/plot_dap_fiber_spectrum/?l=id:1.2.0/43064/3;components:observed,stellar_continuum')
        assert response.status_code == 200
        assert response.headers['content-type'] == 'image/png'

    def test_plot_dap_fiber_spectrum_with_legend(self, client, setup_lvm_sas):
        """Test DAP plot with different legend options"""
        # Short legend
        response = client.get('/lvm/plot_dap_fiber_spectrum/?l=id:1.2.0/43064/3;components:observed,stellar_continuum&legend=short')
        assert response.status_code == 200

        # Long legend
        response = client.get('/lvm/plot_dap_fiber_spectrum/?l=id:1.2.0/43064/3;components:observed,stellar_continuum&legend=long')
        assert response.status_code == 200

        # Component legend
        response = client.get('/lvm/plot_dap_fiber_spectrum/?l=id:1.2.0/43064/3;components:observed,stellar_continuum&legend=component')
        assert response.status_code == 200

    def test_plot_dap_fiber_spectrum_with_styling(self, client, setup_lvm_sas):
        """Test DAP plot with custom styling parameters"""
        response = client.get('/lvm/plot_dap_fiber_spectrum/?l=id:1.2.0/43064/3;components:all;lw:2;alpha:0.8&width=12&height=8&dpi=150')
        assert response.status_code == 200

    def test_plot_dap_fiber_spectrum_pdf(self, client, setup_lvm_sas):
        """Test DAP plot PDF output format"""
        response = client.get('/lvm/plot_dap_fiber_spectrum/?l=id:1.2.0/43064/3;components:observed&format=pdf')
        assert response.status_code == 200
        assert response.headers['content-type'] == 'application/pdf'

    def test_plot_dap_fiber_spectrum_svg(self, client, setup_lvm_sas):
        """Test DAP plot SVG output format"""
        response = client.get('/lvm/plot_dap_fiber_spectrum/?l=id:1.2.0/43064/3;components:observed&format=svg')
        assert response.status_code == 200
        assert response.headers['content-type'] == 'image/svg+xml'

    def test_plot_dap_fiber_spectrum_axis_limits(self, client, setup_lvm_sas):
        """Test DAP plot with axis limits"""
        response = client.get('/lvm/plot_dap_fiber_spectrum/?l=id:1.2.0/43064/3;components:observed&xmin=4000&xmax=7000')
        assert response.status_code == 200

    def test_plot_dap_fiber_spectrum_invalid_fiberid(self, client, setup_lvm_sas):
        """Test DAP plot with out-of-range fiberid"""
        response = client.get('/lvm/plot_dap_fiber_spectrum/?l=id:1.2.0/43064/2000;components:all')
        assert response.status_code == 400
        assert 'fiberid' in response.json()['detail'].lower()

    def test_plot_dap_fiber_spectrum_missing_l_param(self, client, setup_lvm_sas):
        """Test DAP plot without required l parameter"""
        response = client.get('/lvm/plot_dap_fiber_spectrum/')
        assert response.status_code == 422  # Validation error

    def test_plot_dap_fiber_spectrum_with_residual(self, client, setup_lvm_sas):
        """Test DAP plot with offset residual via show_residual parameter"""
        response = client.get('/lvm/plot_dap_fiber_spectrum/?l=id:1.2.0/43064/3;components:observed,full_model_pm&show_residual=true')
        assert response.status_code == 200
        assert response.headers['content-type'] == 'image/png'

        img = Image.open(BytesIO(response.content))
        assert img.format == 'PNG'

    def test_plot_dap_fiber_spectrum_residual_with_scale(self, client, setup_lvm_sas):
        """Test DAP plot residual with custom scale factor"""
        response = client.get('/lvm/plot_dap_fiber_spectrum/?l=id:1.2.0/43064/3;components:observed,full_model_pm&show_residual=true&residual_scale=5.0')
        assert response.status_code == 200

    def test_plot_dap_fiber_spectrum_residual_custom_styling(self, client, setup_lvm_sas):
        """Test DAP plot residual with custom color and line width"""
        response = client.get('/lvm/plot_dap_fiber_spectrum/?l=id:1.2.0/43064/3;components:observed,full_model_pm&show_residual=true&residual_color=red&residual_lw=1.0')
        assert response.status_code == 200

    def test_plot_dap_fiber_spectrum_residual_pm(self, client, setup_lvm_sas):
        """Test DAP plot with residual_pm component (direct extraction)"""
        response = client.get('/lvm/plot_dap_fiber_spectrum/?l=id:1.2.0/43064/3;components:observed,residual_pm')
        assert response.status_code == 200


class TestLVMValidation:
    """Test validation logic"""

    def test_validate_fiberid_range(self):
        """Test fiberid validation"""
        from valis.routes.lvm import parse_line_query_fiber

        # Valid range
        result = parse_line_query_fiber('id:1.2.0/43064/1;type:flux')
        assert '1' in result['id']

        result = parse_line_query_fiber('id:1.2.0/43064/1944;type:flux')
        assert '1944' in result['id']

    def test_validate_spectrum_type(self):
        """Test spectrum type validation"""
        from valis.routes.lvm import parse_line_query_fiber, ALLOWED_LINE_TYPES

        # Valid types
        for spec_type in ALLOWED_LINE_TYPES:
            result = parse_line_query_fiber(f'id:1.2.0/43064/5;type:{spec_type}')
            assert result['type'] == spec_type

        # Invalid type
        with pytest.raises(ValueError):
            parse_line_query_fiber('id:1.2.0/43064/5;type:invalid_type')


class TestLVMHelperFunctions:
    """Test helper functions"""

    def test_arr2list_finite_values(self):
        """Test arr2list with finite values"""
        from valis.routes.lvm import arr2list

        arr = np.array([1.0, 2.0, 3.0])
        result = arr2list(arr)
        assert result == [1.0, 2.0, 3.0]

    def test_arr2list_with_nan(self):
        """Test arr2list with NaN values"""
        from valis.routes.lvm import arr2list

        arr = np.array([1.0, np.nan, 3.0])
        result = arr2list(arr)
        assert result[0] == 1.0
        assert result[1] is None
        assert result[2] == 3.0

    def test_arr2list_with_inf(self):
        """Test arr2list with inf values"""
        from valis.routes.lvm import arr2list

        arr = np.array([1.0, np.inf, 3.0])
        result = arr2list(arr)
        assert result[0] == 1.0
        assert result[1] is None
        assert result[2] == 3.0


class TestDAPComponentExtraction:
    """Test DAP component extraction formulas"""

    def test_extract_dap_components_formulas(self, tmp_path):
        """Test that DAP component formulas match reference implementation"""
        from valis.routes.lvm.services import extract_dap_fiber_data

        # Create test data with known values
        n_wave = 50
        n_fibers = 5
        fiberid = 3
        fiber_idx = 0  # fiberid 3 is at index 0 in PT table

        # Create mock output data with predictable values
        # Shape: (9, n_fibers, n_wave)
        data = np.zeros((9, n_fibers, n_wave), dtype=np.float32)
        data[0, fiber_idx, :] = 10.0  # observed
        data[6, fiber_idx, :] = 1.0   # emission_np
        data[7, fiber_idx, :] = 2.0   # emission_pm
        data[8, fiber_idx, :] = 8.0   # full_model_pm (stellar + pm_emission)

        output_hdu = fits.PrimaryHDU(data)
        output_hdu.header['CRVAL1'] = 3600.0
        output_hdu.header['CDELT1'] = 1.0
        output_hdu.header['CRPIX1'] = 1

        output_file = tmp_path / 'test.output.fits'
        fits.HDUList([output_hdu]).writeto(output_file)

        # Create mock DAP file with PT table
        pt_cols = [
            fits.Column('fiberid', 'K', array=[3, 4, 5, 6, 7]),
            fits.Column('ra', 'D', array=[100.0] * n_fibers),
            fits.Column('dec', 'D', array=[20.0] * n_fibers),
            fits.Column('mask', 'L', array=[True] * n_fibers),
        ]
        dap_file = tmp_path / 'test.dap.fits'
        fits.HDUList([
            fits.PrimaryHDU(),
            fits.BinTableHDU.from_columns(pt_cols, name='PT'),
        ]).writeto(dap_file)

        # Extract with factor=1 for easier verification
        result = extract_dap_fiber_data(
            str(dap_file), str(output_file), fiberid, ['all'], factor=1.0
        )

        components = result['components']

        # Verify formulas (without factor scaling)
        np.testing.assert_array_almost_equal(components['observed'], 10.0)
        np.testing.assert_array_almost_equal(components['emission_np'], 1.0)
        np.testing.assert_array_almost_equal(components['emission_pm'], 2.0)
        np.testing.assert_array_almost_equal(components['full_model_pm'], 8.0)

        # stellar_continuum = d[8] - d[7] = 8 - 2 = 6
        np.testing.assert_array_almost_equal(components['stellar_continuum'], 6.0)

        # full_model_np = d[8] - d[7] + d[6] = 8 - 2 + 1 = 7
        np.testing.assert_array_almost_equal(components['full_model_np'], 7.0)

        # residual_pm = d[0] - d[8] = 10 - 8 = 2
        np.testing.assert_array_almost_equal(components['residual_pm'], 2.0)

        # residual_np = d[0] - (d[8] - d[7] + d[6]) = 10 - 7 = 3
        np.testing.assert_array_almost_equal(components['residual_np'], 3.0)

    def test_extract_dap_float32_output(self, tmp_path):
        """Test that DAP extraction returns float32 arrays"""
        from valis.routes.lvm.services import extract_dap_fiber_data

        n_wave = 50
        n_fibers = 3

        # Create output with float64 to verify conversion
        data = np.random.rand(9, n_fibers, n_wave).astype(np.float64) * 1e-17

        output_hdu = fits.PrimaryHDU(data)
        output_hdu.header['CRVAL1'] = 3600.0
        output_hdu.header['CDELT1'] = 1.0
        output_hdu.header['CRPIX1'] = 1

        output_file = tmp_path / 'test.output.fits'
        fits.HDUList([output_hdu]).writeto(output_file)

        pt_cols = [
            fits.Column('fiberid', 'K', array=[1, 2, 3]),
            fits.Column('ra', 'D', array=[100.0] * n_fibers),
            fits.Column('dec', 'D', array=[20.0] * n_fibers),
            fits.Column('mask', 'L', array=[True] * n_fibers),
        ]
        dap_file = tmp_path / 'test.dap.fits'
        fits.HDUList([
            fits.PrimaryHDU(),
            fits.BinTableHDU.from_columns(pt_cols, name='PT'),
        ]).writeto(dap_file)

        result = extract_dap_fiber_data(
            str(dap_file), str(output_file), 1, ['all']
        )

        # Verify wave is float32
        assert result['wave'].dtype == np.float32

        # Verify all components are float32
        for comp_name, comp_data in result['components'].items():
            assert comp_data.dtype == np.float32, f"{comp_name} is not float32"

    def test_extract_dap_factor_scaling(self, tmp_path):
        """Test that factor scaling is applied correctly"""
        from valis.routes.lvm.services import extract_dap_fiber_data

        n_wave = 10
        n_fibers = 2
        raw_value = 1e-17  # typical flux value

        data = np.full((9, n_fibers, n_wave), raw_value, dtype=np.float32)

        output_hdu = fits.PrimaryHDU(data)
        output_hdu.header['CRVAL1'] = 3600.0
        output_hdu.header['CDELT1'] = 1.0
        output_hdu.header['CRPIX1'] = 1

        output_file = tmp_path / 'test.output.fits'
        fits.HDUList([output_hdu]).writeto(output_file)

        pt_cols = [
            fits.Column('fiberid', 'K', array=[1, 2]),
            fits.Column('ra', 'D', array=[100.0, 100.0]),
            fits.Column('dec', 'D', array=[20.0, 20.0]),
            fits.Column('mask', 'L', array=[True, True]),
        ]
        dap_file = tmp_path / 'test.dap.fits'
        fits.HDUList([
            fits.PrimaryHDU(),
            fits.BinTableHDU.from_columns(pt_cols, name='PT'),
        ]).writeto(dap_file)

        # Test with default factor=1e17
        result = extract_dap_fiber_data(
            str(dap_file), str(output_file), 1, ['observed']
        )

        # raw_value * 1e17 = 1e-17 * 1e17 = 1.0
        expected = raw_value * 1e17
        np.testing.assert_array_almost_equal(result['components']['observed'], expected)


class TestDAPFileResolution:
    """Test DAP file resolution with .fits/.fits.gz priority"""

    def _create_mock_drpall(self, drpall_dir, drpver, expnum, tile_id, mjd):
        """Helper to create mock drpall with lowercase column names (as io.py expects)."""
        cols = [
            fits.Column('EXPNUM', 'K', array=[expnum]),
            fits.Column('mjd', 'K', array=[mjd]),
            fits.Column('tileid', 'K', array=[tile_id]),
            fits.Column('location', '120A', array=[f'sdsswork/lvm/spectro/redux/{drpver}/1048XX/{tile_id}/{mjd}/lvmSFrame-{str(expnum).zfill(8)}.fits']),
            fits.Column('drpver', '10A', array=[drpver]),
        ]
        fits.HDUList([
            fits.PrimaryHDU(),
            fits.BinTableHDU.from_columns(cols),
        ]).writeto(drpall_dir / f'drpall-{drpver}.fits')

    def test_dap_prefers_uncompressed(self, tmp_path, monkeypatch):
        """Test that .fits is preferred over .fits.gz"""
        import asyncio
        from valis.routes.lvm.io import get_DAP_filenames

        sas_root = tmp_path / 'sas'
        drpver = '1.2.0'
        expnum = 99999
        tile_id = 1048982
        mjd = 60859

        drpall_dir = sas_root / 'sdsswork/lvm/spectro/redux' / drpver
        drpall_dir.mkdir(parents=True)
        self._create_mock_drpall(drpall_dir, drpver, expnum, tile_id, mjd)

        suffix = str(expnum).zfill(8)
        dap_dir = sas_root / 'sdsswork/lvm/spectro/analysis' / drpver / '1048XX' / str(tile_id) / str(mjd) / suffix
        dap_dir.mkdir(parents=True)

        # Create BOTH .fits and .fits.gz
        (dap_dir / f'dap-rsp108-sn20-{suffix}.dap.fits').touch()
        (dap_dir / f'dap-rsp108-sn20-{suffix}.dap.fits.gz').touch()
        (dap_dir / f'dap-rsp108-sn20-{suffix}.output.fits').touch()
        (dap_dir / f'dap-rsp108-sn20-{suffix}.output.fits.gz').touch()

        monkeypatch.setenv('SAS_BASE_DIR', str(sas_root))

        dap_file, output_file, relative_path = asyncio.run(get_DAP_filenames(expnum, drpver))

        # Should prefer .fits over .fits.gz
        assert dap_file.endswith('.fits')
        assert not dap_file.endswith('.fits.gz')
        assert output_file.endswith('.fits')
        assert not output_file.endswith('.fits.gz')
        assert relative_path.endswith('.fits')

    def test_dap_falls_back_to_gz(self, tmp_path, monkeypatch):
        """Test fallback to .fits.gz when .fits not available"""
        import asyncio
        from valis.routes.lvm.io import get_DAP_filenames

        sas_root = tmp_path / 'sas'
        drpver = '1.2.0'
        expnum = 99998
        tile_id = 1048982
        mjd = 60859

        drpall_dir = sas_root / 'sdsswork/lvm/spectro/redux' / drpver
        drpall_dir.mkdir(parents=True)
        self._create_mock_drpall(drpall_dir, drpver, expnum, tile_id, mjd)

        suffix = str(expnum).zfill(8)
        dap_dir = sas_root / 'sdsswork/lvm/spectro/analysis' / drpver / '1048XX' / str(tile_id) / str(mjd) / suffix
        dap_dir.mkdir(parents=True)

        # Only create .fits.gz files
        (dap_dir / f'dap-rsp108-sn20-{suffix}.dap.fits.gz').touch()
        (dap_dir / f'dap-rsp108-sn20-{suffix}.output.fits.gz').touch()

        monkeypatch.setenv('SAS_BASE_DIR', str(sas_root))

        dap_file, output_file, relative_path = asyncio.run(get_DAP_filenames(expnum, drpver))

        assert dap_file.endswith('.fits.gz')
        assert output_file.endswith('.fits.gz')
        assert relative_path.endswith('.fits.gz')

    def test_dap_file_not_found(self, tmp_path, monkeypatch):
        """Test error when neither .fits nor .fits.gz exists"""
        import asyncio
        from valis.routes.lvm.io import get_DAP_filenames

        sas_root = tmp_path / 'sas'
        drpver = '1.2.0'
        expnum = 99997
        tile_id = 1048982
        mjd = 60859

        drpall_dir = sas_root / 'sdsswork/lvm/spectro/redux' / drpver
        drpall_dir.mkdir(parents=True)
        self._create_mock_drpall(drpall_dir, drpver, expnum, tile_id, mjd)

        suffix = str(expnum).zfill(8)
        dap_dir = sas_root / 'sdsswork/lvm/spectro/analysis' / drpver / '1048XX' / str(tile_id) / str(mjd) / suffix
        dap_dir.mkdir(parents=True)
        # Don't create any files

        monkeypatch.setenv('SAS_BASE_DIR', str(sas_root))

        with pytest.raises(FileNotFoundError, match="Neither .* nor .* exists"):
            asyncio.run(get_DAP_filenames(expnum, drpver))


class TestDAPEndpointResidualPM:
    """Test DAP endpoints with residual_pm component"""

    def test_dap_fiber_output_residual_pm(self, client, setup_lvm_sas):
        """Test retrieving residual_pm component"""
        response = client.get('/lvm/dap_fiber_output/?l=id:1.2.0/43064/3;components:residual_pm')
        assert response.status_code == 200

        data = response.json()
        components = data['spectra'][0]['components']
        assert 'residual_pm' in components
        assert len(components) == 1

    def test_dap_fiber_output_both_residuals(self, client, setup_lvm_sas):
        """Test retrieving both residual components"""
        response = client.get('/lvm/dap_fiber_output/?l=id:1.2.0/43064/3;components:residual_pm,residual_np')
        assert response.status_code == 200

        data = response.json()
        components = data['spectra'][0]['components']
        assert 'residual_pm' in components
        assert 'residual_np' in components
        assert len(components) == 2

    def test_plot_dap_residual_np_component(self, client, setup_lvm_sas):
        """Test DAP plot with residual_np component"""
        response = client.get('/lvm/plot_dap_fiber_spectrum/?l=id:1.2.0/43064/3;components:observed,residual_np')
        assert response.status_code == 200
        assert response.headers['content-type'] == 'image/png'

