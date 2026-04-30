"""
LVM static JSON files endpoints.
"""
from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, HTTPException, Query
from fastapi_restful.cbv import cbv
from fastapi.responses import FileResponse

from ..io import LVMBase

router = APIRouter()
DEFAULT_DRPVER = '1.2.0'

_TEMPLATE = '{sas}/{release}/vap/lvm/lvmvis/{drpver}/lvmvis-{stage}.json'


@cbv(router)
class Static(LVMBase):
    """Static JSON endpoints (planned/observed/analyzed exposures)."""

    async def _serve(self, stage: str, drpver: str) -> FileResponse:
        sas = self.tree.to_dict()['SAS_BASE_DIR']
        release = 'sdsswork' if self.release == 'WORK' else self.release.lower()
        path = _TEMPLATE.format(sas=sas, release=release, stage=stage, drpver=drpver)
        if not await self.file_exists(path):
            raise HTTPException(status_code=404, detail=f"File not found: {path}")
        return FileResponse(path, media_type='application/json')

    @router.get('/analyzed', summary='Analyzed exposures with DRP/DAP')
    async def get_analyzed_sdssdb(
        self,
        drpver: Annotated[str, Query(description='DRP version (e.g., 1.2.0)', example='1.2.0')] = DEFAULT_DRPVER,
    ):
        """Returns list of observed and analyzed exposures."""
        return await self._serve('analyzed', drpver)

    @router.get('/observed', summary='Observed, not reduced exposures')
    async def get_observed_sdssdb(
        self,
        drpver: Annotated[str, Query(description='DRP version (e.g., 1.2.0)', example='1.2.0')] = DEFAULT_DRPVER,
    ):
        """Returns list of observed exposures that are not reduced yet."""
        return await self._serve('observed', drpver)

    @router.get('/planned', summary='Planned tiles')
    async def get_planned_sdssdb(
        self,
        drpver: Annotated[str, Query(description='DRP version (e.g., 1.2.0)', example='1.2.0')] = DEFAULT_DRPVER,
    ):
        """Returns list of planned tiles not yet observed."""
        return await self._serve('planned', drpver)
