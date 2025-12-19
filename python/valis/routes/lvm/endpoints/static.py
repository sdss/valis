"""
LVM static JSON file endpoints
"""
from __future__ import annotations

import os
from typing import Annotated
from fastapi import APIRouter, HTTPException, Query
from fastapi_restful.cbv import cbv
from fastapi.responses import FileResponse

from valis.routes.base import Base
from ..io import async_file_exists

router = APIRouter()


async def _serve_static_json(filename_template: str, drpver: str) -> FileResponse:
    """Serve static JSON file with version substitution."""
    sas_base = os.getenv('SAS_BASE_DIR', '/data/sdss/sas')
    path = filename_template.format(sas_base=sas_base, drpver=drpver)
    if not await async_file_exists(path):
        raise HTTPException(status_code=404, detail=f"File not found for DRP version: {drpver}")
    return FileResponse(path, media_type='application/json')


@cbv(router)
class Static(Base):
    """Static data file endpoints"""

    @router.get('/observed-pointings', summary='Observed pointings JSON')
    async def get_observed_pointings(
        self,
        drpver: Annotated[str, Query(description='DRP version (e.g., 1.2.0, 1.1.1)', example='1.2.0')] = '1.2.0'
    ):
        """Returns observed pointings from static JSON file."""
        return await _serve_static_json('{sas_base}/sdsswork/lvm/sandbox/lvmvis/lvmvis-drpall-{drpver}.json', drpver)

    @router.get('/planned-tiles', summary='Planned tiles JSON')
    async def get_planned_tiles(
        self,
        drpver: Annotated[str, Query(description='DRP version (e.g., 1.2.0, 1.1.1)', example='1.2.0')] = '1.2.0'
    ):
        """Returns planned tiles from static JSON file."""
        return await _serve_static_json('{sas_base}/sdsswork/lvm/sandbox/lvmvis/lvmvis-planned-tiles-after-drpall-{drpver}.json', drpver)

