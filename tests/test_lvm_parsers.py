# encoding: utf-8
#
# test_lvm_parsers.py

"""
Tests for LVM parsers, validators, and helper functions
"""

import pytest
import numpy as np


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
