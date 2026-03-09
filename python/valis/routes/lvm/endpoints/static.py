"""
LVM static SDSSDB JSON endpoints
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
DEFAULT_SDSSDB_VERSION = '1.2.1'


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

    @router.get('/analyzed', summary='Analyzed exposures with DRP/DAP')
    async def get_analyzed_sdssdb(
        self,
        drpver: Annotated[str, Query(description='DRP version (e.g., 1.2.1)', example='1.2.1')] = DEFAULT_SDSSDB_VERSION
    ):
        """Returns list of observed and analyzed exposures."""
        return await _serve_static_json('{sas_base}/sdsswork/lvm/sandbox/lvmvis/lvmvis-analyzed-sdssdb-{drpver}.json', drpver)

    @router.get('/observed', summary='Observed, not reduced exposures')
    async def get_observed_sdssdb(
        self,
        drpver: Annotated[str, Query(description='DRP version (e.g., 1.2.1)', example='1.2.1')] = DEFAULT_SDSSDB_VERSION
    ):
        """Returns list of observed exposures, which is not reduced yet."""
        return await _serve_static_json('{sas_base}/sdsswork/lvm/sandbox/lvmvis/lvmvis-observed-sdssdb-{drpver}.json', drpver)

    @router.get('/planned', summary='Planned tiles')
    async def get_planned_sdssdb(
        self,
        drpver: Annotated[str, Query(description='DRP version (e.g., 1.2.1)', example='1.2.1')] = DEFAULT_SDSSDB_VERSION
    ):
        """Returns list of planned tiles not observed."""
        return await _serve_static_json('{sas_base}/sdsswork/lvm/sandbox/lvmvis/lvmvis-planned-sdssdb-{drpver}.json', drpver)
