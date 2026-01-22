# encoding: utf-8
#
# test_lvm_drp.py

"""
Tests for LVM DRP endpoints (fiber spectrum, exposure spectrum)
"""

import pytest
from io import BytesIO
from PIL import Image


class TestDRPDataEndpoints:
    """Test DRP data retrieval endpoints"""

    def test_get_drp_fiber_single(self, client, setup_lvm_sas):
        """Test retrieving single fiber spectrum"""
        response = client.get('/lvm/drp/fiber/?l=id:1.2.0/43064/5;type:flux')
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

    def test_get_drp_fiber_multiple(self, client, setup_lvm_sas):
        """Test retrieving multiple fiber spectra"""
        response = client.get('/lvm/drp/fiber/?l=id:1.2.0/43064/5;type:flux&l=id:1.2.0/43064/6;type:sky')
        assert response.status_code == 200

        data = response.json()
        assert len(data['spectra']) == 2
        assert data['spectra'][0]['spectrum_type'] == 'flux'
        assert data['spectra'][1]['spectrum_type'] == 'sky'

    def test_get_drp_fiber_invalid_fiberid(self, client, setup_lvm_sas):
        """Test with out-of-range fiberid"""
        response = client.get('/lvm/drp/fiber/?l=id:1.2.0/43064/2000;type:flux')
        assert response.status_code == 400
        assert 'fiberid' in response.json()['detail'].lower()

    def test_get_drp_fiber_query_params(self, client, setup_lvm_sas):
        """Test using direct query parameters instead of l"""
        response = client.get('/lvm/drp/fiber/?expnum=43064&fiberid=5&drpver=1.2.0&type=flux')
        assert response.status_code == 200

        data = response.json()
        assert len(data['spectra']) == 1
        assert data['spectra'][0]['fiberid'] == 5

    def test_get_drp_fiber_missing_params(self, client, setup_lvm_sas):
        """Test without required parameters"""
        response = client.get('/lvm/drp/fiber/')
        assert response.status_code == 400


class TestDRPPlotEndpoints:
    """Test DRP plotting endpoints"""

    def test_plot_drp_fiber_png(self, client, setup_lvm_sas):
        """Test fiber spectrum plot generation (PNG)"""
        response = client.get('/lvm/drp/fiber/plot/?l=id:1.2.0/43064/5;type:flux&format=png')
        assert response.status_code == 200
        assert response.headers['content-type'] == 'image/png'

        # Verify it's a valid PNG
        img = Image.open(BytesIO(response.content))
        assert img.format == 'PNG'

    def test_plot_drp_fiber_multiple_lines(self, client, setup_lvm_sas):
        """Test plotting multiple fiber spectra"""
        response = client.get('/lvm/drp/fiber/plot/?l=id:1.2.0/43064/5;type:flux;color:red&l=id:1.2.0/43064/6;type:flux;color:blue')
        assert response.status_code == 200

    def test_plot_drp_fiber_with_styling(self, client, setup_lvm_sas):
        """Test plot with custom styling parameters"""
        response = client.get('/lvm/drp/fiber/plot/?l=id:1.2.0/43064/5;type:flux;color:red;lw:2&width=10&height=6&dpi=150')
        assert response.status_code == 200

    def test_plot_drp_fiber_invalid_matplotlib_param(self, client, setup_lvm_sas):
        """Test with invalid matplotlib parameter - API should return 500 error"""
        response = client.get('/lvm/drp/fiber/plot/?l=id:1.2.0/43064/5;type:flux;invalid_param:value')
        assert response.status_code == 500  # Internal server error
        assert 'detail' in response.json()
        assert 'Error creating plot' in response.json()['detail']
        assert 'invalid_param' in response.json()['detail']

    def test_plot_drp_exposure_png(self, client, setup_lvm_sas):
        """Test exposure spectrum plot generation"""
        response = client.get('/lvm/drp/exposure/plot/?l=id:1.2.0/43064&format=png')
        assert response.status_code == 200
        assert response.headers['content-type'] == 'image/png'

    def test_plot_drp_exposure_method(self, client, setup_lvm_sas):
        """Test different aggregation methods"""
        response = client.get('/lvm/drp/exposure/plot/?l=id:1.2.0/43064;method:mean')
        assert response.status_code == 200

        response = client.get('/lvm/drp/exposure/plot/?l=id:1.2.0/43064;method:median')
        assert response.status_code == 200

        response = client.get('/lvm/drp/exposure/plot/?l=id:1.2.0/43064;method:std')
        assert response.status_code == 200

    def test_plot_drp_exposure_telescope(self, client, setup_lvm_sas):
        """Test filtering by telescope"""
        response = client.get('/lvm/drp/exposure/plot/?l=id:1.2.0/43064;telescope:Sci')
        assert response.status_code == 200

    def test_plot_drp_exposure_pdf(self, client, setup_lvm_sas):
        """Test PDF output format"""
        response = client.get('/lvm/drp/exposure/plot/?l=id:1.2.0/43064&format=pdf')
        assert response.status_code == 200
        assert response.headers['content-type'] == 'application/pdf'

    def test_plot_drp_exposure_svg(self, client, setup_lvm_sas):
        """Test SVG output format"""
        response = client.get('/lvm/drp/exposure/plot/?l=id:1.2.0/43064&format=svg')
        assert response.status_code == 200
        assert response.headers['content-type'] == 'image/svg+xml'
