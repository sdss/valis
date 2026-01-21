# encoding: utf-8
#
# test_lvm_cutout.py

"""
Tests for LVM HiPS cutout endpoint
"""

import pytest
from typing import get_args


class TestCutoutLiteralTypes:
    """Test that Literal types are properly defined and usable"""

    def test_projection_literal_values(self):
        """Verify WCSProjectionLiteral contains expected projections"""
        from valis.routes.lvm.common import WCSProjectionLiteral, PROJECTION_DESCRIPTIONS

        projections = get_args(WCSProjectionLiteral)
        assert 'SIN' in projections
        assert 'TAN' in projections
        assert 'CAR' in projections
        assert len(projections) == 17

        # PROJECTION_DESCRIPTIONS should be derived from the Literal type
        assert 'SIN' in PROJECTION_DESCRIPTIONS
        assert 'TAN' in PROJECTION_DESCRIPTIONS

    def test_coordsys_literal_values(self):
        """Verify CoordinateSystemLiteral contains expected values"""
        from valis.routes.lvm.common import CoordinateSystemLiteral

        coordsys = get_args(CoordinateSystemLiteral)
        assert 'icrs' in coordsys
        assert 'galactic' in coordsys
        assert len(coordsys) == 2

    def test_format_literal_values(self):
        """Verify ImageFormatLiteral contains expected formats"""
        from valis.routes.lvm.common import ImageFormatLiteral

        formats = get_args(ImageFormatLiteral)
        assert 'png' in formats
        assert 'jpg' in formats
        assert 'jpeg' in formats
        assert 'fits' in formats

    def test_stretch_literal_values(self):
        """Verify ImageStretchLiteral contains expected stretch types"""
        from valis.routes.lvm.common import ImageStretchLiteral

        stretches = get_args(ImageStretchLiteral)
        assert 'linear' in stretches
        assert 'sqrt' in stretches
        assert 'log' in stretches
        assert 'asinh' in stretches

    def test_wcs_creation_with_literal_string(self):
        """Test that WCS can be created correctly with plain strings from Literal types"""
        from astropy.wcs import WCS

        # With Literal types, we get strings directly - no .value needed
        projection = 'SIN'

        wcs = WCS(header={
            'CRVAL1': 0.0, 'CRVAL2': 0.0, 'CRPIX1': 0.0, 'CRPIX2': 0.0,
            'CTYPE1': f'RA---{projection}', 'CTYPE2': f'DEC--{projection}',
            'CD1_1': 1.0, 'CD1_2': 0.0, 'CD2_1': 0.0, 'CD2_2': 1.0
        })
        assert wcs.wcs.ctype[0] == 'RA---SIN'
        assert wcs.wcs.ctype[1] == 'DEC--SIN'


class TestCutoutEndpoint:
    """Comprehensive tests for cutout image endpoint parameters"""

    @pytest.fixture
    def setup_cutout_mocks(self, client, setup_lvm_sas, monkeypatch):
        """Setup mock HiPS directory and patch functions for cutout tests"""
        from unittest.mock import patch

        # Create mock HiPS directories for different versions
        for version in ['1.2.0', '1.1.1', '1.1.0', '1.0.3']:
            hips_dir = setup_lvm_sas['sas_root'] / f'sdsswork/sandbox/data-viz/hips/sdsswork/lvm/{version}/test_hips'
            hips_dir.mkdir(parents=True, exist_ok=True)
            (hips_dir / 'properties').write_text('hips_frame=equatorial\n')

        monkeypatch.setenv('LVM_HIPS', str(setup_lvm_sas['sas_root'] / 'sdsswork/sandbox/data-viz/hips/sdsswork/lvm'))

        captured = {'wcs_params': {}, 'generate_params': {}}

        def mock_create_wcs_object(skycoord, width, height, fov, coordsys='icrs', projection='SIN', rotation_angle=0, inverse_longitude=False):
            captured['wcs_params'] = {
                'skycoord': skycoord,
                'width': width,
                'height': height,
                'fov': fov,
                'coordsys': coordsys,
                'projection': projection,
                'rotation_angle': rotation_angle,
            }
            from astropy.wcs import WCS
            ctype_prefix = 'GLON-' if coordsys == 'galactic' else 'RA---'
            ctype_prefix2 = 'GLAT-' if coordsys == 'galactic' else 'DEC--'
            return WCS(header={
                'CRVAL1': 0.0, 'CRVAL2': 0.0, 'CRPIX1': float(width/2), 'CRPIX2': float(height/2),
                'CTYPE1': f'{ctype_prefix}{projection}', 'CTYPE2': f'{ctype_prefix2}{projection}',
                'CDELT1': -0.01, 'CDELT2': 0.01, 'NAXIS1': width, 'NAXIS2': height
            })

        def mock_generate_from_wcs(wcs, hips_path, output, format='fits', min_cut=None, max_cut=None, stretch='linear', cmap='Greys_r'):
            captured['generate_params'] = {
                'format': format,
                'min_cut': min_cut,
                'max_cut': max_cut,
                'stretch': stretch,
                'cmap': cmap,
            }
            from PIL import Image
            import numpy as np
            from astropy.io import fits as pyfits
            from io import BytesIO

            if format == 'fits':
                hdu = pyfits.PrimaryHDU(np.zeros((100, 100)))
                buf = BytesIO()
                hdu.writeto(buf)
                buf.seek(0)
                output.write(buf.read())
            else:
                fmt = 'JPEG' if format in ['jpg', 'jpeg'] else 'PNG'
                img = Image.new('RGB', (100, 100), color='black')
                img.save(output, format=fmt)

        patcher1 = patch('valis.routes.lvm.endpoints.cutout._create_wcs_object', mock_create_wcs_object)
        patcher2 = patch('valis.routes.lvm.endpoints.cutout.generate_from_wcs', mock_generate_from_wcs)
        patcher1.start()
        patcher2.start()

        yield {'client': client, 'captured': captured, 'setup': setup_lvm_sas}

        patcher1.stop()
        patcher2.stop()

    # === Projection Tests ===

    @pytest.mark.parametrize("projection", ['SIN', 'TAN', 'CAR', 'AIT', 'MOL', 'ZEA', 'STG', 'ARC'])
    def test_cutout_projections(self, setup_cutout_mocks, projection):
        """Test various WCS projections are passed correctly"""
        client = setup_cutout_mocks['client']
        captured = setup_cutout_mocks['captured']

        response = client.get(
            f'/lvm/cutout/image/1.1.0/test_hips?ra=10.0&dec=-70.0&projection={projection}'
        )
        assert response.status_code == 200
        assert captured['wcs_params']['projection'] == projection

    # === Coordinate System Tests ===

    def test_cutout_icrs_coordinates(self, setup_cutout_mocks):
        """Test ICRS coordinate system"""
        client = setup_cutout_mocks['client']
        captured = setup_cutout_mocks['captured']

        response = client.get(
            '/lvm/cutout/image/1.1.0/test_hips?ra=13.158&dec=-72.8&coordsys=icrs'
        )
        assert response.status_code == 200
        assert captured['wcs_params']['coordsys'] == 'icrs'

    def test_cutout_galactic_coordinates(self, setup_cutout_mocks):
        """Test galactic coordinate system"""
        client = setup_cutout_mocks['client']
        captured = setup_cutout_mocks['captured']

        response = client.get(
            '/lvm/cutout/image/1.1.0/test_hips?ra=302.8&dec=-44.3&coordsys=galactic'
        )
        assert response.status_code == 200
        assert captured['wcs_params']['coordsys'] == 'galactic'

    # === Position Angle Tests ===

    @pytest.mark.parametrize("pa", [0, 45, 90, 180, -45, 270, 359.9])
    def test_cutout_position_angle(self, setup_cutout_mocks, pa):
        """Test various position angles"""
        client = setup_cutout_mocks['client']
        captured = setup_cutout_mocks['captured']

        response = client.get(
            f'/lvm/cutout/image/1.1.0/test_hips?ra=10.0&dec=-70.0&pa={pa}'
        )
        assert response.status_code == 200
        assert captured['wcs_params']['rotation_angle'] == pa

    # === Field of View Tests ===

    @pytest.mark.parametrize("fov", [0.1, 0.5, 1.0, 5.0, 10.0])
    def test_cutout_field_of_view(self, setup_cutout_mocks, fov):
        """Test various field of view values"""
        client = setup_cutout_mocks['client']
        captured = setup_cutout_mocks['captured']

        response = client.get(
            f'/lvm/cutout/image/1.1.0/test_hips?ra=10.0&dec=-70.0&fov={fov}'
        )
        assert response.status_code == 200
        assert captured['wcs_params']['fov'] == fov

    # === Image Size Tests ===

    @pytest.mark.parametrize("width,height", [(100, 100), (300, 300), (600, 400), (1000, 500), (2000, 2000)])
    def test_cutout_image_dimensions(self, setup_cutout_mocks, width, height):
        """Test various image dimensions"""
        client = setup_cutout_mocks['client']
        captured = setup_cutout_mocks['captured']

        response = client.get(
            f'/lvm/cutout/image/1.1.0/test_hips?ra=10.0&dec=-70.0&width={width}&height={height}'
        )
        assert response.status_code == 200
        assert captured['wcs_params']['width'] == width
        assert captured['wcs_params']['height'] == height

    # === Output Format Tests ===

    def test_cutout_format_png(self, setup_cutout_mocks):
        """Test PNG output format"""
        client = setup_cutout_mocks['client']
        captured = setup_cutout_mocks['captured']

        response = client.get(
            '/lvm/cutout/image/1.1.0/test_hips?ra=10.0&dec=-70.0&format=png'
        )
        assert response.status_code == 200
        assert response.headers['content-type'] == 'image/png'
        assert captured['generate_params']['format'] == 'png'

    def test_cutout_format_jpg(self, setup_cutout_mocks):
        """Test JPG output format"""
        client = setup_cutout_mocks['client']
        captured = setup_cutout_mocks['captured']

        response = client.get(
            '/lvm/cutout/image/1.1.0/test_hips?ra=10.0&dec=-70.0&format=jpg'
        )
        assert response.status_code == 200
        assert response.headers['content-type'] == 'image/jpeg'
        assert captured['generate_params']['format'] == 'jpg'

    def test_cutout_format_jpeg(self, setup_cutout_mocks):
        """Test JPEG output format (alias for jpg)"""
        client = setup_cutout_mocks['client']
        captured = setup_cutout_mocks['captured']

        response = client.get(
            '/lvm/cutout/image/1.1.0/test_hips?ra=10.0&dec=-70.0&format=jpeg'
        )
        assert response.status_code == 200
        assert response.headers['content-type'] == 'image/jpeg'
        assert captured['generate_params']['format'] == 'jpeg'

    def test_cutout_format_fits(self, setup_cutout_mocks):
        """Test FITS output format"""
        client = setup_cutout_mocks['client']
        captured = setup_cutout_mocks['captured']

        response = client.get(
            '/lvm/cutout/image/1.1.0/test_hips?ra=10.0&dec=-70.0&format=fits'
        )
        assert response.status_code == 200
        assert response.headers['content-type'] == 'application/fits'
        assert captured['generate_params']['format'] == 'fits'

    # === Image Stretch Tests ===

    @pytest.mark.parametrize("stretch", ['linear', 'sqrt', 'power', 'log', 'asinh', 'sinh'])
    def test_cutout_stretch_types(self, setup_cutout_mocks, stretch):
        """Test various image stretch types"""
        client = setup_cutout_mocks['client']
        captured = setup_cutout_mocks['captured']

        response = client.get(
            f'/lvm/cutout/image/1.1.0/test_hips?ra=10.0&dec=-70.0&stretch={stretch}'
        )
        assert response.status_code == 200
        assert captured['generate_params']['stretch'] == stretch

    # === Min/Max Cut Tests ===

    def test_cutout_min_max_cuts(self, setup_cutout_mocks):
        """Test min and max cut values"""
        client = setup_cutout_mocks['client']
        captured = setup_cutout_mocks['captured']

        response = client.get(
            '/lvm/cutout/image/1.1.0/test_hips?ra=10.0&dec=-70.0&min=100&max=10000'
        )
        assert response.status_code == 200
        assert captured['generate_params']['min_cut'] == 100.0
        assert captured['generate_params']['max_cut'] == 10000.0

    def test_cutout_only_min_cut(self, setup_cutout_mocks):
        """Test with only min cut specified"""
        client = setup_cutout_mocks['client']
        captured = setup_cutout_mocks['captured']

        response = client.get(
            '/lvm/cutout/image/1.1.0/test_hips?ra=10.0&dec=-70.0&min=50'
        )
        assert response.status_code == 200
        assert captured['generate_params']['min_cut'] == 50.0
        assert captured['generate_params']['max_cut'] is None

    def test_cutout_only_max_cut(self, setup_cutout_mocks):
        """Test with only max cut specified"""
        client = setup_cutout_mocks['client']
        captured = setup_cutout_mocks['captured']

        response = client.get(
            '/lvm/cutout/image/1.1.0/test_hips?ra=10.0&dec=-70.0&max=5000'
        )
        assert response.status_code == 200
        assert captured['generate_params']['min_cut'] is None
        assert captured['generate_params']['max_cut'] == 5000.0

    # === Colormap Tests ===

    @pytest.mark.parametrize("cmap", ['inferno', 'viridis', 'magma', 'plasma', 'Greys_r', 'hot', 'coolwarm'])
    def test_cutout_colormaps(self, setup_cutout_mocks, cmap):
        """Test various matplotlib colormaps"""
        client = setup_cutout_mocks['client']
        captured = setup_cutout_mocks['captured']

        response = client.get(
            f'/lvm/cutout/image/1.1.0/test_hips?ra=10.0&dec=-70.0&cmap={cmap}'
        )
        assert response.status_code == 200
        assert captured['generate_params']['cmap'] == cmap

    # === Version Tests ===

    @pytest.mark.parametrize("version", ['1.2.0', '1.1.1', '1.1.0', '1.0.3'])
    def test_cutout_versions(self, setup_cutout_mocks, version):
        """Test various DRP/DAP versions"""
        client = setup_cutout_mocks['client']

        response = client.get(
            f'/lvm/cutout/image/{version}/test_hips?ra=10.0&dec=-70.0'
        )
        assert response.status_code == 200

    # === Combined Parameters Test ===

    def test_cutout_all_parameters(self, setup_cutout_mocks):
        """Test with all parameters specified"""
        client = setup_cutout_mocks['client']
        captured = setup_cutout_mocks['captured']

        response = client.get(
            '/lvm/cutout/image/1.1.0/test_hips'
            '?ra=13.158&dec=-72.8&fov=2.5&format=png'
            '&coordsys=icrs&projection=TAN&pa=45'
            '&width=800&height=600&min=100&max=5000'
            '&stretch=asinh&cmap=viridis'
        )
        assert response.status_code == 200

        assert captured['wcs_params']['coordsys'] == 'icrs'
        assert captured['wcs_params']['projection'] == 'TAN'
        assert captured['wcs_params']['rotation_angle'] == 45.0
        assert captured['wcs_params']['fov'] == 2.5
        assert captured['wcs_params']['width'] == 800
        assert captured['wcs_params']['height'] == 600

        assert captured['generate_params']['format'] == 'png'
        assert captured['generate_params']['min_cut'] == 100.0
        assert captured['generate_params']['max_cut'] == 5000.0
        assert captured['generate_params']['stretch'] == 'asinh'
        assert captured['generate_params']['cmap'] == 'viridis'

    # === Error Cases ===

    def test_cutout_hips_not_found(self, setup_cutout_mocks):
        """Test 404 when HiPS directory doesn't exist"""
        client = setup_cutout_mocks['client']

        response = client.get(
            '/lvm/cutout/image/1.1.0/nonexistent_hips?ra=10.0&dec=-70.0'
        )
        assert response.status_code == 404
        assert 'not found' in response.json()['detail'].lower()

    def test_cutout_image_size_limit(self, setup_cutout_mocks):
        """Test 400 when image size exceeds 5000x5000"""
        client = setup_cutout_mocks['client']

        response = client.get(
            '/lvm/cutout/image/1.1.0/test_hips?ra=10.0&dec=-70.0&width=6000&height=5000'
        )
        assert response.status_code == 400
        assert 'exceeds' in response.json()['detail'].lower()

    def test_cutout_invalid_colormap(self, setup_cutout_mocks):
        """Test 400 when invalid colormap is specified"""
        client = setup_cutout_mocks['client']

        response = client.get(
            '/lvm/cutout/image/1.1.0/test_hips?ra=10.0&dec=-70.0&cmap=invalid_colormap_xyz'
        )
        assert response.status_code == 400
        assert 'colormap' in response.json()['detail'].lower()

    def test_cutout_missing_ra(self, setup_cutout_mocks):
        """Test validation error when RA is missing"""
        client = setup_cutout_mocks['client']

        response = client.get(
            '/lvm/cutout/image/1.1.0/test_hips?dec=-70.0'
        )
        assert response.status_code == 422

    def test_cutout_missing_dec(self, setup_cutout_mocks):
        """Test validation error when Dec is missing"""
        client = setup_cutout_mocks['client']

        response = client.get(
            '/lvm/cutout/image/1.1.0/test_hips?ra=10.0'
        )
        assert response.status_code == 422

    def test_cutout_invalid_fov(self, setup_cutout_mocks):
        """Test validation error when FOV is invalid (<=0)"""
        client = setup_cutout_mocks['client']

        response = client.get(
            '/lvm/cutout/image/1.1.0/test_hips?ra=10.0&dec=-70.0&fov=-1'
        )
        assert response.status_code == 422

    def test_cutout_invalid_width(self, setup_cutout_mocks):
        """Test validation error when width is invalid (<=1)"""
        client = setup_cutout_mocks['client']

        response = client.get(
            '/lvm/cutout/image/1.1.0/test_hips?ra=10.0&dec=-70.0&width=0'
        )
        assert response.status_code == 422
