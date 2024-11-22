from __future__ import print_function, division, absolute_import

import math
import re
import os
import httpx
import orjson
from typing import Any, Tuple, List, Union, Optional, Annotated
from pydantic import field_validator, model_validator, BaseModel, Field, model_serializer
from enum import Enum
from fastapi import APIRouter, HTTPException, Query, Path, Depends, Response
from fastapi_restful.cbv import cbv
from fastapi.responses import StreamingResponse
import numpy as np
import pandas as pd
import astropy.units as u
from astropy.io import fits
from astropy.coordinates import SkyCoord
from astroquery.simbad import Simbad

from valis.routes.base import Base
from valis.db.queries import (get_target_meta, get_a_spectrum, get_catalog_sources,
                              get_parent_catalog_data, get_target_cartons,
                              get_target_pipeline, get_target_by_altid, append_pipes)
from valis.db.db import get_pw_db
from valis.db.models import CatalogResponse, CartonModel, ParentCatalogModel, PipesModel, SDSSModel
from io import BytesIO

from hips2fits_cutout import generate as hips2fits_generate


router = APIRouter()


class ImageFormat(str, Enum):
    png = "png"
    jpg = "jpg"
    jpeg = "jpeg"
    fits = "fits"


@cbv(router)
class LVM(Base):
    """ Endpoints for dealing with HiPS cutouts """

    @router.get("/cutout/image/{version}/{hips}", summary='Extract image cutout from HiPS maps')
    async def get_image(self,
                        version: str = Path(..., enum=['1.1.0', '1.0.3', '1.0.3b'], description="DRP/DAP version", example='1.1.0'),
                        hips: str = Path(..., description="HiPS name including version. Should be available at https://data.sdss5.org/sas/sdsswork/sandbox/data-viz/hips/sdsswork/lvm", example='hips_flx_Halpha'),
                        format: ImageFormat = Query('png', description='Format of the output image', example='png'),
                        ra: float = Query(..., description="Right Ascension in degrees (ICRS)", example=13.14033),
                        dec: float = Query(..., description="Declination in degrees (ICRS)", example=-72.79495),
                        fov: float = Query(1.0, description="Field of view in degrees. If width and height are not equal, then fov defines the largest dimension.", example=1.0),
                        width: int = Query(300, description="Width in pixels", example=300),
                        height: int = Query(300, description="Height in pixels. `Note:` `width` x `height` should not exceed 5000 x 5000 pixels.", example=300),
                        min: Optional[float] = Query(None, description="Minimum cut value. Used for jpg, png formats", example=0),
                        max: Optional[float] = Query(None, description="Maximum cut value. Used for jpg, png formats", example=10000),
                        stretch: Optional[str] = Query('linear', enum=['linear', 'sqrt', 'power', 'log', 'asinh', 'sinh'], description="Stretch for the image. Used for jpg, png formats.", example='linear'),
                        cmap: Optional[str] = Query('Greys_r', description="Colormap for the image. All Matplotlib colormaps are accepted. Used for jpg, png formats.", example='Greys_r'),
                        ) -> Response:
        """
        Provides image cutouts from LVM HiPS maps.

        This endpoint allows users to extract image cutouts from the LVM 
        HiPS (Hierarchical Progressive Survey) maps available at [https://data.sdss5.org/sas/sdsswork/sandbox/data-viz/hips/sdsswork/lvm](https://data.sdss5.org/sas/sdsswork/sandbox/data-viz/hips/sdsswork/lvm).
        

        Users can specify parameters such as sky coordinates, field of view,
        image dimensions, and output format to retrieve the desired cutout.
        The output image uses the `SIN` (orthographic) coordinate projection.

        
        This service utilizes the `hips2fits_cutout` script developed by CDS, Strasbourg Astronomical Observatory, France (DOI : 10.26093/2msf-n437).
        For more details, refer to GitHub repository [https://github.com/cds-astro/hips2fits-cutout](https://github.com/cds-astro/hips2fits-cutout).
        """

        HIPS_ROOT = "/data/sdss/sas/sdsswork/sandbox/data-viz/hips/sdsswork/lvm"
        hips_path = f"{HIPS_ROOT}/{version}/{hips}/"

        #  Check if HiPS path exists
        if not os.path.exists(hips_path):
            raise HTTPException(status_code=404, detail=f"Requested HiPS ({hips}, ver={version}) does not exist. Please check what is available in https://data.sdss5.org/sas/sdsswork/sandbox/data-viz/hips/sdsswork/lvm")

        # Check the size of the requested image
        if width * height > 5000 * 5000:
            raise HTTPException(status_code=400, detail="Requested image size (width x height) exceeds the maximum allowed limit of 5000x5000 pixels.")

        image_data = BytesIO()
        hips2fits_generate(ra, dec, fov, width, height, hips_path, image_data, format=format, min_cut=min, max_cut=max, stretch=stretch, cmap=cmap)
        image_data.seek(0)

        media_types = dict(jpg='image/jpeg', jpeg='image/jpeg', png='image/png', fits='application/fits')
        filename = f"lvm_cutout_{hips}_{ra}_{dec}_{fov}_{width}_{height}.{format}"

        return StreamingResponse(image_data,
                                 media_type=media_types[format],
                                 headers={'Content-Disposition': f'inline; filename="{filename}"'})

    @router.get('/spectrum_fiber/{tile_id}/{mjd}/{exposure}/{fiberid}',
                summary='Experimental endpoint to extract LVM fiber spectrum')
    async def get_spectrum_lvm_fiber(self,
                               tile_id: Annotated[int, Path(description="The tile_id of the LVM dither", example=1028790)],
                               mjd: Annotated[int, Path(desciption='The MJD of the observations', example=60314)],
                               exposure: Annotated[int, Path(desciption='The exposure number', example=10328)],
                               fiberid: Annotated[int, Path(desciption='Sequential ID of science fiber within Dither (1 to 1801)', example=777)],
                               version: Annotated[str, Query(description='DRP version', example='1.0.3')] = '1.0.3'):

        # construct file path for lvmSFrame-*.fits file
        suffix = str(exposure).zfill(8)
        if tile_id == 11111:
            filename = f"lvm/spectro/redux/{version}/0011XX/11111/{mjd}/lvmSFrame-{suffix}.fits"
        else:
            filename = f"lvm/spectro/redux/{version}/{str(tile_id)[:4]}XX/{tile_id}/{mjd}/lvmSFrame-{suffix}.fits"

        DATA_ROOT = f"/data/sdss/sas/sdsswork/"
        file = DATA_ROOT + filename

        # Check that file exists and return exception if not
        if not os.path.exists(file):
            raise HTTPException(status_code=404, detail=f"File {filename} does not exist.")

        # Check that file exists and return exception if not
        if fiberid < 1 or fiberid > 1801:
            raise HTTPException(status_code=400, detail=f"`fiberid` ({fiberid}) must be between 1 and 1801.")

        # Open file and read data
        with fits.open(file) as hdul:
            wave = hdul['WAVE'].data
            targettype = hdul['SLITMAP'].data['targettype']
            fiberid_in_stack = np.argwhere(targettype == 'science')[fiberid - 1][0]

            flux = hdul['FLUX'].data[fiberid_in_stack, :] * 1e17

        return dict(filename=filename,
                    version=version,
                    wave=arr2list(wave),
                    flux=arr2list(flux),)

    @router.get('/dap_lines/{tile_id}/{mjd}/{exposure}',
                summary='Experimental endpoint to extract LVM DAP emission line fluxes')
    async def get_dap_fluxes(self,
                             tile_id: Annotated[int, Path(description="The tile_id of the LVM pointing", example=1028790)],
                             mjd: Annotated[int, Path(desciption='The MJD of the observations', example=60314)],
                             exposure: Annotated[int, Path(desciption='The exposure number', example=10328)],
                             wl = Query('6562.85,4861.36', description='List of emission lines to be retrieved', example='6562.85,4861.36'),
                             version: Annotated[str, Query(description='DRP version', example='1.0.3')] = '1.0.3',
                             ):

        # construct file path for lvmSFrame-*.fits file
        suffix = str(exposure).zfill(8)
        if tile_id == 11111:
            filename = f"lvm/spectro/analysis/{version}/0011XX/11111/{mjd}/{suffix}/dap-rsp108-sn20-{suffix}.dap.fits.gz"
        else:
            filename = f"lvm/spectro/analysis/{version}/{str(tile_id)[:4]}XX/{tile_id}/{mjd}/{suffix}/dap-rsp108-sn20-{suffix}.dap.fits.gz"

        DATA_ROOT = f"/data/sdss/sas/sdsswork/"
        file = DATA_ROOT + filename

        # Check that file exists and return exception if not
        if not os.path.exists(file):
            raise HTTPException(status_code=404, detail=f"File {filename} does not exist.")

        # Read parametric emission line
        dap_pm = fits.getdata(file, 'PM_ELINES')

        # # Create DataFrames
        df_pm = pd.DataFrame({'id': np.array(dap_pm['id']).byteswap().newbyteorder(),
                            'wl': np.array(dap_pm['wl']).byteswap().newbyteorder(),
                            'flux': np.array(dap_pm['flux']).byteswap().newbyteorder()})

        # # extract from id column fiberid part
        df_pm['fiberid'] = df_pm['id'].str.split('.').str[1].astype(int)

        wlist = [float(w) for w in wl.split(',')]

        masked_lines = df_pm['wl'].isin(wlist)
        df_pm_sub = df_pm[masked_lines]

        df_pm_pivot = df_pm_sub.pivot(index='fiberid', columns='wl', values='flux').reset_index()

        output = dict(fiberid=df_pm_pivot['fiberid'].tolist())
        for wl in wlist:
            output[f"{wl}"] = df_pm_pivot[wl].tolist()

        return output
