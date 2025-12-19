"""
LVM DAP endpoints: fiber output data and emission line fluxes
"""
from __future__ import annotations

import os
from typing import List, Annotated
from fastapi import APIRouter, HTTPException, Query, Path
from fastapi_restful.cbv import cbv
import numpy as np
import pandas as pd
from astropy.io import fits

from valis.routes.base import Base
from valis.routes.files import ORJSONResponseCustom

from ..common import arr2list, parse_line_query_dap_fiber, validate_fiberid
from ..io import get_DAP_filenames, async_file_exists, run_in_executor
from ..services import extract_dap_fiber_data

router = APIRouter()


@cbv(router)
class DAP(Base):
    """DAP analysis endpoints"""

    @router.get('/dap_fiber_output/', summary='Get LVM DAP Fiber Output Data')
    async def get_dap_fiber_output(
        self,
        l: List[str] = Query(..., description="DAP fiber definition: `id:DAPversion/expnum/fiberid[;components:...]`")
    ) -> ORJSONResponseCustom:
        """
        # Get LVM DAP Fiber Output Data

        **Format:** `l=id:DAPversion/expnum/fiberid[;components:observed,stellar_continuum,...]`

        **Components:** observed, stellar_continuum, emission_np, emission_pm, full_model_pm, full_model_np, residual_np, all

        Returns `{wave: [...], spectra: [{filename, dapver, expnum, fiberid, ra, dec, mask, components: {...}}]}`
        """
        if not l:
            raise HTTPException(status_code=400, detail="Query parameter 'l' is mandatory")

        try:
            parsed_data = [parse_line_query_dap_fiber(line) for line in l]
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        common_wave = None
        spectra_results = []

        for parsed in parsed_data:
            id_parts = parsed['id'].split('/')
            dapver, expnum, fiberid = id_parts[0], int(id_parts[1]), int(id_parts[2])
            validate_fiberid(fiberid)

            try:
                dap_file, output_file, relative_path = await get_DAP_filenames(expnum, dapver)
            except FileNotFoundError as e:
                raise HTTPException(status_code=404, detail=str(e))

            try:
                result = await run_in_executor(
                    extract_dap_fiber_data, dap_file, output_file, fiberid, parsed['components']
                )
            except ValueError as e:
                raise HTTPException(status_code=404, detail=str(e))

            if common_wave is None:
                common_wave = result['wave']

            spectra_results.append({
                'filename': relative_path,
                'dapver': dapver,
                'expnum': expnum,
                'fiberid': fiberid,
                'ra': result['ra'],
                'dec': result['dec'],
                'mask': result['mask'],
                'components': {comp: arr2list(data) for comp, data in result['components'].items()}
            })

        return ORJSONResponseCustom(content={'wave': arr2list(common_wave), 'spectra': spectra_results})

    @router.get('/dap_lines/{tile_id}/{mjd}/{exposure}', summary='Extract LVM DAP emission line fluxes')
    async def get_dap_fluxes(
        self,
        tile_id: Annotated[int, Path(description="Tile ID", example=1028790)],
        mjd: Annotated[int, Path(description="MJD", example=60314)],
        exposure: Annotated[int, Path(description="Exposure number", example=10328)],
        wl=Query('6562.85,4861.36', description='Emission lines (wavelengths)', example='6562.85,4861.36'),
        version: Annotated[str, Query(description='DAP version (e.g., 1.2.0, 1.1.1)', example='1.2.0')] = '1.2.0',
    ):
        """
        # Get LVM DAP Emission Line Fluxes

        Experimental endpoint to extract emission line fluxes from DAP files.
        """
        suffix = str(exposure).zfill(8)
        sas_base = os.getenv('SAS_BASE_DIR', '/data/sdss/sas')
        tile_prefix = "0011XX" if tile_id == 11111 else f"{str(tile_id)[:4]}XX"
        file = f"{sas_base}/sdsswork/lvm/spectro/analysis/{version}/{tile_prefix}/{tile_id}/{mjd}/{suffix}/dap-rsp108-sn20-{suffix}.dap.fits.gz"

        if not await async_file_exists(file):
            raise HTTPException(status_code=404, detail=f"DAP file not found for version {version}")

        def read_fluxes():
            dap_pm = fits.getdata(file, 'PM_ELINES')
            df = pd.DataFrame({
                'id': np.array(dap_pm['id']).byteswap().newbyteorder(),
                'wl': np.array(dap_pm['wl']).byteswap().newbyteorder(),
                'flux': np.array(dap_pm['flux']).byteswap().newbyteorder()
            })
            df['fiberid'] = df['id'].str.split('.').str[1].astype(int)

            wlist = [float(w) for w in wl.split(',')]
            df_sub = df[df['wl'].isin(wlist)]
            df_pivot = df_sub.pivot(index='fiberid', columns='wl', values='flux').reset_index()

            output = {'fiberid': df_pivot['fiberid'].tolist()}
            for w in wlist:
                output[f"{w}"] = df_pivot[w].tolist()
            return output

        return await run_in_executor(read_fluxes)

