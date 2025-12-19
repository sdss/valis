"""
LVM Routes

HTTP endpoints for LVM spectral data access, analysis, and visualization.

Route Structure:
================

    lvm/
    ├── __init__.py           # Route exports
    ├── common.py             # Constants, enums, parsers, validators
    ├── io.py                 # File resolution, async FITS reading
    ├── services.py           # DRP, DAP extraction & plotting
    └── endpoints/            # FastAPI routers
        ├── __init__.py       # Combined router
        ├── cutout.py         # GET /cutout/image/{version}/{hips}
        ├── drp.py            # GET /fiber_spectrum/
        │                     # GET /plot_fiber_spectrum/
        │                     # GET /plot_exposure_spectrum/
        ├── dap.py            # GET /dap_fiber_output/
        │                     # GET /dap_lines/{tile_id}/{mjd}/{exposure}
        └── static.py         # GET /observed-pointings
                              # GET /planned-tiles

Layer Architecture:
===================

    ┌─────────────┐
    │  endpoints/ │  ← FastAPI routes (HTTP handlers)
    └──────┬──────┘
           │ calls
    ┌──────▼──────┐
    │  services   │  ← Business logic (extraction, plotting)
    └──────┬──────┘
           │ uses
    ┌──────▼──────┐
    │     io      │  ← Async file I/O (FITS reading)
    └──────┬──────┘
           │ validates with
    ┌──────▼──────┐
    │   common    │  ← Shared utilities (parsers, validators)
    └─────────────┘
"""

from .endpoints import router
from .common import (
    LAST_DRP_VERSION, ALLOWED_LINE_TYPES, arr2list,
    parse_line_query_fiber, parse_line_query_exposure, parse_line_query_dap_fiber,
    build_spectrum_requests
)
from .io import get_LVM_drpall_record, get_SFrame_filename, get_DAP_filenames
from .services import extract_fiber_data, extract_dap_fiber_data, process_spectrum_requests

__all__ = [
    'router',
    'LAST_DRP_VERSION',
    'ALLOWED_LINE_TYPES',
    'arr2list',
    'parse_line_query_fiber',
    'parse_line_query_exposure',
    'parse_line_query_dap_fiber',
    'build_spectrum_requests',
    'get_LVM_drpall_record',
    'get_SFrame_filename',
    'get_DAP_filenames',
    'extract_fiber_data',
    'extract_dap_fiber_data',
    'process_spectrum_requests',
]
