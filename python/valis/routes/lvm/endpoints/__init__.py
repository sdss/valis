"""
LVM endpoints - combines domain-specific routers
"""
from fastapi import APIRouter

from .cutout import router as cutout_router
from .drp import router as drp_router
from .dap import router as dap_router
from .static import router as static_router

router = APIRouter()
router.include_router(cutout_router)
router.include_router(drp_router)
router.include_router(dap_router)
router.include_router(static_router)

__all__ = ['router']

