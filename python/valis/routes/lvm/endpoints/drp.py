"""
LVM DRP endpoints: fiber spectrum data and plots
"""
from __future__ import annotations

import os
from io import BytesIO
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi_restful.cbv import cbv
from fastapi.responses import StreamingResponse
import matplotlib.pyplot as plt
from astropy.io import fits

from valis.routes.base import Base
from valis.routes.files import ORJSONResponseCustom

from ..common import (
    LAST_DRP_VERSION, ALLOWED_LINE_TYPES, DEFAULTS_FOR_FIBER, arr2list,
    parse_line_query_fiber, parse_line_query_exposure, validate_fiberid,
    build_spectrum_requests
)
from ..io import get_LVM_drpall_record, get_SFrame_filename, async_file_exists, run_in_executor
from ..services import (
    extract_fiber_data, aggregate_exposure_spectrum, create_spectrum_plot,
    process_spectrum_requests
)

router = APIRouter()
FACTOR = 1e17


@cbv(router)
class DRP(Base):
    """DRP fiber spectrum endpoints"""

    @router.get('/fiber_spectrum/', summary='Get LVM DRP Fiber Spectrum Data')
    async def get_fiber_spectrum(
        self,
        l: List[str] = Query(None, description="Spectrum definitions: `id:DRPversion/expnum/fiberid;type:flux`", example=['id:1.2.0/43064/532;type:flux', 'id:1.1.1/7371/532;type:flux']),
        expnum_q: Optional[int] = Query(None, alias="expnum", description="Exposure number (if l not provided)", example=43064),
        fiberid_q: Optional[int] = Query(None, alias="fiberid", description="FiberID 1-1944 (if l not provided)", example=532),
        drpver_q: str = Query(LAST_DRP_VERSION, alias="drpver", description="DRP version (if l not provided)", example=LAST_DRP_VERSION),
        type_q: str = Query(DEFAULTS_FOR_FIBER["type"], alias="type", description=f"Spectrum type: {list(ALLOWED_LINE_TYPES)}", example="flux")
    ) -> ORJSONResponseCustom:
        """
        # Get LVM DRP Fiber Spectrum Data

        Retrieves spectral data for fibers from DRP SFrame files.

        **Format:** `l=id:DRPversion/expnum/fiberid[;type:spectrum_type]`

        Returns `{wave: [...], spectra: [{filename, drpver, expnum, fiberid, spectrum_type, <type>: [...]}]}`
        """
        try:
            requests = build_spectrum_requests(l, expnum_q, fiberid_q, drpver_q, type_q)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        try:
            spectra_data, common_wave = await process_spectrum_requests(
                requests, get_SFrame_filename, get_LVM_drpall_record, FACTOR
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

        return ORJSONResponseCustom(content={"wave": arr2list(common_wave), "spectra": spectra_data})

    @router.get('/plot_fiber_spectrum/', summary='Plot LVM DRP Fiber Spectrum')
    async def plot_fiber_spectrum(
        self,
        l: List[str] = Query(..., description="Spectrum definitions with plot kwargs"),
        format: str = Query('png', description="Output: png, jpg, pdf, svg", example='png'),
        width: float = Query(10.0, description="Figure width (inches)", example=10.0),
        height: float = Query(6.0, description="Figure height (inches)", example=6.0),
        dpi: int = Query(100, description="DPI", example=100),
        xlabel: str = Query('Wavelength [Å]', description="X-axis label"),
        ylabel: str = Query('Flux [10⁻¹⁷ erg/s/cm²/Å]', description="Y-axis label"),
        title: Optional[str] = Query(None, description="Plot title"),
        legend: Optional[str] = Query(None, description="Legend: short, long"),
        xmin: Optional[float] = Query(None, description="X-axis min"),
        xmax: Optional[float] = Query(None, description="X-axis max"),
        ymin: Optional[float] = Query(None, description="Y-axis min"),
        ymax: Optional[float] = Query(None, description="Y-axis max"),
        ypmin: float = Query(1.0, description="Y percentile min"),
        ypmax: float = Query(99.0, description="Y percentile max"),
        log: bool = Query(False, description="Log y-axis")
    ) -> StreamingResponse:
        """
        # Plot LVM DRP Fiber Spectrum

        **Format:** `l=id:DRPversion/expnum/fiberid[;type:flux][;color:red][;lw:1.5]`
        """
        if not l:
            raise HTTPException(status_code=400, detail="'l' parameter required")

        try:
            parsed_lines = [parse_line_query_fiber(line) for line in l]
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        data, wave = [], None

        for d in parsed_lines:
            id_parts = d['id'].split('/')
            if len(id_parts) != 3:
                raise HTTPException(status_code=400, detail=f"Invalid ID: {d['id']}")

            drpver, expnum, fiberid = id_parts[0], int(id_parts[1]), int(id_parts[2])
            validate_fiberid(fiberid)

            try:
                file = await get_SFrame_filename(expnum, drpver)
            except FileNotFoundError as e:
                raise HTTPException(status_code=404, detail=str(e))

            if not await async_file_exists(file):
                raise HTTPException(status_code=404, detail=f"File not found for DRP {drpver}")

            def read_fits():
                with fits.open(file) as hdul:
                    return hdul['WAVE'].data, extract_fiber_data(hdul, fiberid, d['type'], FACTOR)

            wave_data, spectrum = await run_in_executor(read_fits)
            if wave is None:
                wave = wave_data

            d.update({'array': spectrum, 'expnum': expnum, 'drpver': drpver})
            d['plot_kwargs'] = {k: v for k, v in d.items() if k not in {'id', 'drpver', 'expnum', 'type', 'array', 'fiberid'}}
            data.append(d)

        try:
            fig = create_spectrum_plot(wave, data, width, height, xlabel, ylabel, title, legend, xmin, xmax, ymin, ymax, ypmin, ypmax, log)
        except ValueError as e:
            raise HTTPException(status_code=500, detail=str(e))

        return _figure_response(fig, format, dpi)

    @router.get('/plot_exposure_spectrum/', summary='Plot LVM DRP Exposure Aggregate Spectrum')
    async def plot_exposure_spectrum(
        self,
        l: List[str] = Query(..., description="Exposure spectrum definitions"),
        format: str = Query('png', description="Output: png, jpg, pdf, svg"),
        width: float = Query(10.0, description="Figure width (inches)"),
        height: float = Query(6.0, description="Figure height (inches)"),
        dpi: int = Query(100, description="DPI"),
        xlabel: str = Query('Wavelength [Å]', description="X-axis label"),
        ylabel: str = Query('Flux [10⁻¹⁷ erg/s/cm²/Å]', description="Y-axis label"),
        title: Optional[str] = Query(None, description="Plot title"),
        legend: Optional[str] = Query(None, description="Legend: short, long"),
        xmin: Optional[float] = Query(None, description="X-axis min"),
        xmax: Optional[float] = Query(None, description="X-axis max"),
        ymin: Optional[float] = Query(None, description="Y-axis min"),
        ymax: Optional[float] = Query(None, description="Y-axis max"),
        ypmin: float = Query(1.0, description="Y percentile min"),
        ypmax: float = Query(99.0, description="Y percentile max"),
        log: bool = Query(False, description="Log y-axis")
    ) -> StreamingResponse:
        """
        # Plot LVM DRP Exposure Aggregate Spectrum

        **Format:** `l=id:DRPversion/expnum[;type:flux][;method:median][;telescope:Sci]`
        """
        if not l:
            raise HTTPException(status_code=400, detail="'l' parameter required")

        try:
            parsed_lines = [parse_line_query_exposure(line) for line in l]
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        data, wave = [], None

        for d in parsed_lines:
            id_parts = d['id'].split('/')
            if len(id_parts) != 2:
                raise HTTPException(status_code=400, detail=f"Invalid ID: {d['id']}")

            drpver, expnum = id_parts[0], int(id_parts[1])

            try:
                file = await get_SFrame_filename(expnum, drpver)
            except FileNotFoundError as e:
                raise HTTPException(status_code=404, detail=str(e))

            if not await async_file_exists(file):
                raise HTTPException(status_code=404, detail=f"File not found for DRP {drpver}")

            def read_fits():
                with fits.open(file) as hdul:
                    return aggregate_exposure_spectrum(
                        hdul, d['type'], d['method'], d.get('telescope', 'Sci'),
                        d.get('fibstatus', 0), d.get('percentile_value', 50.0), FACTOR
                    )

            wave_data, spectrum = await run_in_executor(read_fits)
            if wave is None:
                wave = wave_data

            d.update({'array': spectrum, 'expnum': expnum, 'drpver': drpver})
            exclude = {'id', 'drpver', 'tile_id', 'mjd', 'expnum', 'type', 'method', 'telescope', 'fibstatus', 'array', 'percentile_value'}
            d['plot_kwargs'] = {k: v for k, v in d.items() if k not in exclude}
            data.append(d)

        try:
            fig = create_spectrum_plot(wave, data, width, height, xlabel, ylabel, title, legend, xmin, xmax, ymin, ymax, ypmin, ypmax, log)
        except ValueError as e:
            raise HTTPException(status_code=500, detail=str(e))

        return _figure_response(fig, format, dpi)


def _figure_response(fig, format: str, dpi: int) -> StreamingResponse:
    """Save figure to buffer and return as streaming response."""
    buffer = BytesIO()
    fig.savefig(buffer, format=format, dpi=dpi, bbox_inches='tight')
    plt.close(fig)
    buffer.seek(0)
    media_types = {'png': 'image/png', 'jpg': 'image/jpeg', 'pdf': 'application/pdf', 'svg': 'image/svg+xml'}
    return StreamingResponse(buffer, media_type=media_types.get(format, 'image/png'))

