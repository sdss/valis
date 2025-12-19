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

