"""
Common utilities for LVM routes: constants, enums, parsers, validators, helpers
"""
from __future__ import annotations

import re
import numpy as np
from enum import Enum
from typing import Any, Dict

import matplotlib.pyplot as plt


# Constants
VALID_MATPLOTLIB_CMAPS = plt.colormaps()
LAST_DRP_VERSION = '1.2.0'

ALLOWED_LINE_TYPES = {'flux', 'skyflux', 'sky', 'ivar', 'sky_ivar', 'err', 'sky_err', 'lsf'}
ALLOWED_LINE_METHODS = {'mean', 'median', 'std'}
ALLOWED_LINE_TELESCOPES = {'Sci', 'SkyE', 'SkyW', 'Spec'}
ALLOWED_DAP_COMPONENTS = {
    'observed', 'stellar_continuum', 'emission_np', 'emission_pm',
    'full_model_pm', 'full_model_np', 'residual_np', 'all'
}

DEFAULTS_FOR_EXPOSURE = {
    "type": "flux",
    "method": "median",
    "telescope": "Sci",
    "fibstatus": 0,
}

DEFAULTS_FOR_FIBER = {
    "type": "flux",
}


# Enums
class CoordinateSystem(str, Enum):
    icrs = "icrs"
    galactic = "galactic"


class WCSProjection(str, Enum):
    """All WCS Projection types compatible with hips2fits_cutout script"""
    car = "CAR"  # Plate Carrée
    cea = "CEA"  # Cylindrical Equal Area
    mer = "MER"  # Mercator
    sfl = "SFL"  # Sanson-Flamsteed (Global Sinusoidal)
    coe = "COE"  # Conic Equal Area
    azp = "AZP"  # Perspective Zenithal
    szp = "SZP"  # Slant Zenithal Perspective
    tan = "TAN"  # Gnomonic
    stg = "STG"  # Stereographic
    sin = "SIN"  # Orthographic
    arc = "ARC"  # Zenithal Equidistant
    zea = "ZEA"  # Equal Area
    mol = "MOL"  # Mollweide
    ait = "AIT"  # Hammer-Aitoff
    csc = "CSC"  # COBE Quadrilateralized Spherical Cube
    hpx = "HPX"  # HEALPix
    xph = "XPH"  # HEALPix Polar


PROJECTION_DESCRIPTIONS = ", ".join([proj.value for proj in WCSProjection])


class ImageFormat(str, Enum):
    png = "png"
    jpg = "jpg"
    jpeg = "jpeg"
    fits = "fits"


class ImageStretch(str, Enum):
    linear = "linear"
    sqrt = "sqrt"
    power = "power"
    log = "log"
    asinh = "asinh"
    sinh = "sinh"


# Helper Functions
def arr2list(nparr, badmask=None):
    """
    Convert numpy array to list masking non-finite values for serialization.
    """
    if badmask is None:
        badmask = ~np.isfinite(nparr)
    return np.where(badmask, None, nparr).tolist()


def convert_to_number(value: str):
    """
    Convert a string to a number (int or float) if it represents one.
    Otherwise, return the string as is.
    """
    if value.isdigit():
        return int(value)
    try:
        return float(value)
    except ValueError:
        return value


# Query String Parsers
def parse_line_query_fiber(line: str) -> Dict[str, Any]:
    """
    Parse and validate a single `l` query string for get_spectrum_fiber_plot endpoint.
    """
    components = line.split(";")
    parsed = {}

    for component in components:
        if ":" not in component:
            raise ValueError(f"Invalid component: {component}. Must be in 'key:value' format.")
        key, value = component.split(":", 1)
        parsed[key] = convert_to_number(value)

    # Apply defaults
    for key, default_value in DEFAULTS_FOR_FIBER.items():
        if key not in parsed:
            parsed[key] = default_value

    # Validate mandatory fields
    if "id" not in parsed:
        raise ValueError("'id' must be provided in format drpversion/expnum/fiberid (e.g., 1.2.0/43064/532).")

    if "type" not in parsed or parsed["type"] not in ALLOWED_LINE_TYPES:
        raise ValueError(f"'type' must be one of {ALLOWED_LINE_TYPES}.")

    return parsed


def parse_line_query_exposure(line: str) -> Dict[str, Any]:
    """
    Parse and validate a single `l` query string for get_spectrum_exposure_plot endpoint.
    """
    components = line.split(";")
    parsed = {}

    for component in components:
        if ":" not in component:
            raise ValueError(f"Invalid component: {component}. Must be in 'key:value' format.")
        key, value = component.split(":", 1)
        parsed[key] = convert_to_number(value)

    # Apply defaults
    for key, default_value in DEFAULTS_FOR_EXPOSURE.items():
        if key not in parsed:
            parsed[key] = default_value

    # Validate mandatory fields
    if "id" not in parsed:
        raise ValueError("'id' must be provided in format drpversion/expnum (e.g., 1.2.0/43064).")

    if "type" not in parsed or parsed["type"] not in ALLOWED_LINE_TYPES:
        raise ValueError(f"'type' must be one of {ALLOWED_LINE_TYPES}.")

    if "method" not in parsed or parsed["method"] not in ALLOWED_LINE_METHODS:
        if not parsed["method"].startswith("percentile_"):
            raise ValueError(f"'method' must be one of {ALLOWED_LINE_METHODS} or 'percentile_XX' (e.g., 'percentile_90.3').")
        # Validate percentile method
        match = re.fullmatch(r"percentile_(\d+(\.\d+)?)", parsed["method"])
        if not match:
            raise ValueError(f"Invalid percentile method: {parsed['method']}. Must be 'percentile_XX' where XX is a float.")
        parsed["method"] = "percentile"
        parsed["percentile_value"] = float(match.group(1))

    # Validate optional fields
    if "telescope" in parsed and parsed["telescope"] not in ALLOWED_LINE_TELESCOPES:
        raise ValueError(f"'telescope' must be one of {ALLOWED_LINE_TELESCOPES}.")

    return parsed


def parse_line_query_dap_fiber(line: str) -> Dict[str, Any]:
    """
    Parse and validate a single `l` query string for DAP fiber output endpoint.
    """
    components = line.split(";")
    parsed = {}

    for component in components:
        if ":" not in component:
            raise ValueError(f"Invalid component: {component}. Must be in 'key:value' format.")
        key, value = component.split(":", 1)

        if key == 'components':
            parsed['components'] = [c.strip() for c in value.split(',')]
        else:
            parsed[key] = convert_to_number(value)

    if 'id' not in parsed:
        raise ValueError("'id' must be provided in format: DAPversion/expnum/fiberid")

    id_parts = parsed['id'].split('/')
    if len(id_parts) != 3:
        raise ValueError("ID must be in format: DAPversion/expnum/fiberid (e.g., 1.2.0/43064/532)")

    if 'components' not in parsed:
        parsed['components'] = ['all']

    for comp in parsed['components']:
        if comp not in ALLOWED_DAP_COMPONENTS:
            raise ValueError(f"Invalid component '{comp}'. Allowed: {ALLOWED_DAP_COMPONENTS}")

    return parsed


# Validators
def validate_fiberid(fiberid: int) -> None:
    """Validate that fiberid is in the valid range [1, 1944]."""
    if not (1 <= fiberid <= 1944):
        raise ValueError(f"fiberid ({fiberid}) must be between 1 and 1944.")


def validate_spectrum_type(spectrum_type: str) -> None:
    """Validate that spectrum type is allowed."""
    if spectrum_type not in ALLOWED_LINE_TYPES:
        raise ValueError(f"Invalid spectrum type: {spectrum_type}. Allowed: {list(ALLOWED_LINE_TYPES)}")


def validate_drp_version(version: str) -> None:
    """Validate DRP version format."""
    if not re.match(r'^\d+\.\d+\.\d+[a-z]?$', version):
        raise ValueError(f"Invalid DRP version format: {version}. Expected format: X.Y.Z or X.Y.Za")


# Request Builders
def build_spectrum_requests(l_params, expnum_q, fiberid_q, drpver_q, type_q):
    """
    Build list of spectrum requests from either 'l' params or individual query params.
    Returns list of (expnum, fiberid, drpver, spectrum_type) tuples.
    Raises ValueError on validation failure.
    """
    if not l_params and (expnum_q is None or fiberid_q is None):
        raise ValueError("Either 'l' parameters or both 'expnum' and 'fiberid' must be provided.")

    requests = []

    if l_params:
        if not isinstance(l_params, list):
            l_params = [l_params]

        for l_param in l_params:
            parsed = parse_line_query_fiber(l_param)
            id_parts = parsed['id'].split('/')
            if len(id_parts) != 3:
                raise ValueError(f"ID must be DRPversion/expnum/fiberid: {l_param}")

            drpver, expnum, fiberid = id_parts[0], int(id_parts[1]), int(id_parts[2])
            spectrum_type = parsed['type']

            validate_fiberid(fiberid)
            if spectrum_type not in ALLOWED_LINE_TYPES:
                raise ValueError(f"Invalid type '{spectrum_type}' in '{l_param}'")

            requests.append((expnum, fiberid, drpver, spectrum_type))
    else:
        validate_fiberid(fiberid_q)
        if type_q not in ALLOWED_LINE_TYPES:
            raise ValueError(f"Invalid type: {type_q}")
        requests.append((expnum_q, fiberid_q, drpver_q, type_q))

    return requests

