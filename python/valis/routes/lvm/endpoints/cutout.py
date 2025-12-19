"""
LVM HiPS image cutout endpoint
"""
from __future__ import annotations

import os
from io import BytesIO
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Path, Response
from fastapi_restful.cbv import cbv
from fastapi.responses import StreamingResponse
from astropy.coordinates import SkyCoord

from valis.routes.base import Base
from hips2fits_cutout import _create_wcs_object, generate_from_wcs

from ..common import (
    VALID_MATPLOTLIB_CMAPS, CoordinateSystem, WCSProjection,
    ImageFormat, ImageStretch, PROJECTION_DESCRIPTIONS
)

router = APIRouter()


@cbv(router)
class Cutout(Base):
    """HiPS image cutout endpoints"""

    @router.get("/cutout/image/{version}/{hips}", summary='Extract image cutout from HiPS maps')
    async def get_image(
        self,
        version: str = Path(..., enum=['1.2.0', '1.1.1', '1.1.0', '1.0.3', '1.0.3b'], description="DRP/DAP version", example='1.2.0'),
        hips: str = Path(..., description="HiPS name. Available at https://data.sdss5.org/sas/sdsswork/sandbox/data-viz/hips/sdsswork/lvm", example='hips_flx_Halpha'),
        format: ImageFormat = Query('png', description='Output format', example='png'),
        ra: float = Query(..., description="RA (ICRS) or Galactic l if coordsys=galactic", example=13.14033),
        dec: float = Query(..., description="Dec (ICRS) or Galactic b if coordsys=galactic", example=-72.79495),
        coordsys: Optional[CoordinateSystem] = Query('icrs', description="Coordinate system", example='icrs'),
        projection: Optional[WCSProjection] = Query('SIN', description=f"WCS projection: {PROJECTION_DESCRIPTIONS}", example='SIN'),
        pa: float = Query(0.0, description="Position angle (deg)", example=45),
        fov: float = Query(1.0, gt=0, description="Field of view (deg)", example=1.0),
        width: int = Query(300, gt=1, description="Width (px)", example=300),
        height: int = Query(300, gt=1, description="Height (px). Max: 5000x5000", example=300),
        min: Optional[float] = Query(None, description="Min cut value (jpg/png)", example=0),
        max: Optional[float] = Query(None, description="Max cut value (jpg/png)", example=10000),
        stretch: Optional[ImageStretch] = Query('linear', description="Image stretch (jpg/png)", example='linear'),
        cmap: Optional[str] = Query('magma', description="Matplotlib colormap (jpg/png)", example='Greys_r'),
    ) -> Response:
        """
        ## Image cutouts from LVM HiPS maps

        Extract cutouts from HiPS maps at https://data.sdss5.org/sas/sdsswork/sandbox/data-viz/hips/sdsswork/lvm

        Uses hips2fits_cutout (CDS, DOI: 10.26093/2msf-n437).

        **Note:** LVM HiPS pixel size is 3.22 arcsec (NSIDE=2^16). Set fov/width/height
        such that `fov * 3600 / max(width, height) >= 3.22` for optimal resolution.
        """
        LVM_HIPS = os.getenv("LVM_HIPS")
        hips_path = f"{LVM_HIPS}/{version}/{hips}/"

        if not os.path.exists(hips_path):
            raise HTTPException(status_code=404, detail=f"HiPS ({hips}, ver={version}) not found")

        if width * height > 5000 * 5000:
            raise HTTPException(status_code=400, detail="Image size exceeds 5000x5000 limit")

        if cmap not in VALID_MATPLOTLIB_CMAPS:
            raise HTTPException(status_code=400, detail=f"Invalid colormap '{cmap}'")

        image_data = BytesIO()
        sc = SkyCoord(ra, dec, frame=coordsys, unit='deg')
        wcs = _create_wcs_object(sc, width, height, fov, coordsys=coordsys, projection=projection, rotation_angle=pa)
        generate_from_wcs(wcs, hips_path, image_data, format=format, min_cut=min, max_cut=max, stretch=stretch, cmap=cmap)
        image_data.seek(0)

        media_types = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png', 'fits': 'application/fits'}
        filename = f"lvm_cutout_{hips}_{ra}_{dec}_{fov}_{width}_{height}.{format}"

        return StreamingResponse(
            image_data, media_type=media_types[format],
            headers={'Content-Disposition': f'inline; filename="{filename}"'}
        )

