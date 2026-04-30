"""
LVM Routes

HTTP endpoints for LVM spectral data access, analysis, and visualization.

Route Structure:
================

    lvm/
    ├── __init__.py           # Route exports
    ├── common.py             # Constants, enums, parsers, validators
    ├── io.py                 # LVMBase: async path resolution + run_sync + file_exists
    ├── services.py           # Synchronous FITS extraction + matplotlib plotting
    └── endpoints/            # FastAPI routers
        ├── __init__.py       # Combined router (auth applied per-subrouter)
        ├── cutout.py         # GET /cutout/image/{version}/{hips}
        ├── drp.py            # GET /drp/fiber/
        │                     # GET /drp/fiber/plot/
        │                     # GET /drp/exposure/plot/
        ├── dap.py            # GET /dap/fiber/
        │                     # GET /dap/fiber/plot/
        │                     # GET /dap/lines/
        └── static.py         # GET /analyzed, /observed, /planned

Layer Architecture:
===================

         ┌──────────────┐
         │  endpoints/  │  FastAPI CBVs, subclass LVMBase
         └───┬──────┬───┘
             │      │
      uses   │      │   uses
             ▼      ▼
    ┌──────────┐  ┌──────────┐
    │    io    │  │ services │  (sibling layers)
    │  LVMBase │  │          │
    └────┬─────┘  └────┬─────┘
         │             │
         └──────┬──────┘
                ▼
         ┌───────────┐
         │  common   │  constants, parsers, validators
         └───────────┘

io:       async path resolution (sdss_access/tree/hardcoded fallback),
          async file_exists, generic run_sync executor.
services: pure sync functions invoked via run_sync from endpoints
          (FITS extraction, matplotlib figure construction).
Endpoints orchestrate: parse request -> resolve path (io) ->
                       read+process (services via run_sync) -> build response.
"""

from .endpoints import router

__all__ = ['router']
