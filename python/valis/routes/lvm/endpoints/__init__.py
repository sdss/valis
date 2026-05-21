"""
LVM endpoints: combined router with auth applied to every subrouter.

Each subrouter is domain-scoped:
    drp     -> /lvm/drp/*       (DRP fiber/exposure spectra, plots)
    dap     -> /lvm/dap/*       (DAP components, emission lines, plots)
    static  -> /lvm/planned, /lvm/observed, /lvm/analyzed
    cutout  -> /lvm/cutout/*    (HiPS image cutouts)
"""
from fastapi import APIRouter, Depends

from valis.routes.auth import set_auth

from .drp import router as drp_router
from .dap import router as dap_router
from .static import router as static_router
from .cutout import router as cutout_router

router = APIRouter()

for sub in (drp_router, dap_router, static_router, cutout_router):
    router.include_router(sub, dependencies=[Depends(set_auth)])

__all__ = ['router']
