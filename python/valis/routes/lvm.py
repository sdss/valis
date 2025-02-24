from __future__ import print_function, division, absolute_import

import re
import os
from functools import partial
import orjson
from typing import Any, Tuple, List, Dict, Union, Optional, Annotated, Literal
from enum import Enum
from fastapi import APIRouter, HTTPException, Query, Path, Depends, Response
from fastapi_restful.cbv import cbv
from fastapi.responses import StreamingResponse
import numpy as np
import pandas as pd
import astropy.units as u
from astropy.io import fits
from astropy.coordinates import SkyCoord

from valis.routes.base import Base
from valis.routes.files import ORJSONResponseCustom
from io import BytesIO

from hips2fits_cutout import _create_wcs_object, generate_from_wcs
import matplotlib.pyplot as plt


VALID_MATPLOTLIB_CMAPS = plt.colormaps()
LAST_DRP_VERSION = '1.1.1'

router = APIRouter()


def arr2list(nparr, badmask=None):
    """
    Function to convert numpy array to list masking non-number values.
    It used for serilization.
    """
    if badmask is None:
        badmask = ~np.isfinite(nparr)
    return np.where(badmask, None, nparr).tolist()


class CoordinateSystem(str, Enum):
    icrs = "icrs"
    galactic = "galactic"


class WCSProjection(str, Enum):
    """All WCS Projection types compartible with hips2fits_cutout script"""
    car = "CAR"  # Plate Carrée
    cea = "CEA"  # Cylindrical Equal Area
    mer = "MER"  # Mercator
    sfl = "SFL"  # Sanson-Flamsteed (Global Sinusoidal)
    coe = "COE"  # Conic Equal Area
    azp = "AZP"  # Perspective Zenithal
    szp = "SZP"  # Slant Zenithal Perspective
    tan = "TAN"  # Gnomonic
    stg = "STG"  # Stereographic
    sin = "SIN"  # Orthographic
    arc = "ARC"  # Zenithal Equidistant
    zea = "ZEA"  # Equal Area
    mol = "MOL"  # Mollweide
    ait = "AIT"  # Hammer-Aitoff
    csc = "CSC"  # COBE Quadrilateralized Spherical Cube
    hpx = "HPX"  # HEALPix
    xph = "XPH"  # HEALPix Polar

PROJECTION_DESCRIPTIONS = ", ".join([proj.value for proj in WCSProjection])

class ImageFormat(str, Enum):
    png = "png"
    jpg = "jpg"
    jpeg = "jpeg"
    fits = "fits"


class ImageStretch(str, Enum):
    linear = "linear"
    sqrt = "sqrt"
    power = "power"
    log = "log"
    asinh = "asinh"
    sinh = "sinh"


ALLOWED_LINE_TYPES = {'flux', 'skyflux', 'sky', 'ivar', 'sky_ivar', 'err', 'sky_err', 'lsf'}
ALLOWED_LINE_METHODS = {'mean', 'median', 'std'}
ALLOWED_LINE_TELESCOPES = {'Sci', 'SkyE', 'SkyW', 'Spec'}
DEFAULTS_FOR_EXPOSURE = {
    "type": "flux",
    "method": "median",
    "telescope": "Sci",
    "fibstatus": 0,
}
DEFAULTS_FOR_FIBER = {
    "type": "flux",
}


def convert_to_number(value: str):
    """
    Convert a string to a number (int or float) if it represents one.
    Otherwise, return the string as is.
    """
    if value.isdigit():  # Check if it's a positive integer
        return int(value)
    try:
        return float(value)  # Try converting to a float
    except ValueError:
        return value  # Return the original string if not a number


def parse_line_query_exposure(line: str) -> Dict[str, Any]:
    """
    Parse and validate a single `l` query string of get_spectrum_exposure_plot endpoint.
    """
    components = line.split(";")
    parsed = {}

    # Parse key-value pairs
    for component in components:
        if ":" not in component:
            raise ValueError(f"Invalid component: {component}. Must be in 'key:value' format.")
        key, value = component.split(":", 1)
        parsed[key] = convert_to_number(value)

    # Apply default values if key keys are missing
    for key, default_value in DEFAULTS_FOR_EXPOSURE.items():
        if key not in parsed:
            parsed[key] = default_value

    # Validate mandatory fields
    if "id" not in parsed:
        raise ValueError(f"'id' must be provided in shape drpversion/expnum i.e. 1.1.0/7591.")

    if "type" not in parsed or parsed["type"] not in ALLOWED_LINE_TYPES:
        raise ValueError(f"'type' must be one of {ALLOWED_LINE_TYPES}.")

    if "method" not in parsed or parsed["method"] not in ALLOWED_LINE_METHODS:
        if not parsed["method"].startswith("percentile_"):
            raise ValueError(f"'method' must be one of {ALLOWED_LINE_METHODS} or 'percentile_XX' (e.g., 'percentile_90.3').")
        # Validate percentile method
        match = re.fullmatch(r"percentile_(\d+(\.\d+)?)", parsed["method"])
        if not match:
            raise ValueError(f"Invalid percentile method: {parsed['method']}. Must be 'percentile_XX' where XX is a float.")
        parsed["method"] = "percentile"
        parsed["percentile_value"] = float(match.group(1))

    # Validate optional fields
    if "telescope" in parsed and parsed["telescope"] not in ALLOWED_LINE_TELESCOPES:
        raise ValueError(f"'telescope' must be one of {ALLOWED_LINE_TELESCOPES}.")

    return parsed


def parse_line_query_fiber(line: str) -> Dict[str, Any]:
    """
    Parse and validate a single `l` query string of get_spectrum_fiber_plot endpoint.
    """
    components = line.split(";")
    parsed = {}

    # Parse key-value pairs
    for component in components:
        if ":" not in component:
            raise ValueError(f"Invalid component: {component}. Must be in 'key:value' format.")
        key, value = component.split(":", 1)
        parsed[key] = convert_to_number(value)

    # Apply default values if key keys are missing
    for key, default_value in DEFAULTS_FOR_FIBER.items():
        if key not in parsed:
            parsed[key] = default_value

    # Validate mandatory fields
    if "id" not in parsed:
        raise ValueError(f"'id' must be provided in shape drpversion/expnum/fiberid i.e. 1.1.0/7591/532.")

    if "type" not in parsed or parsed["type"] not in ALLOWED_LINE_TYPES:
        raise ValueError(f"'type' must be one of {ALLOWED_LINE_TYPES}.")

    return parsed


def get_LVM_drpall_record(expnum: int, drpver: int) -> Dict[str, Any]:
    "Function to get record from drpall file for a given exposure number"

    drp_file = f"/data/sdss/sas/sdsswork/lvm/spectro/redux/{drpver}/drpall-{drpver}.fits"
    if not os.path.exists(drp_file):
        drp_file = f"/data/sdss/sas/sdsswork/lvm/spectro/redux/{LAST_DRP_VERSION}/drpall-{LAST_DRP_VERSION}.fits"

    drpall = fits.getdata(drp_file)
    record = drpall[drpall['EXPNUM'] == expnum][0]

    return {name: record[name] for name in drpall.names}


def get_SFrame_filename(expnum: int, drpver: int) -> str:
    "Function to get SFrame filename for a given exposure number"

    drp_record = get_LVM_drpall_record(expnum, drpver)
    file = f"/data/sdss/sas/" + drp_record['location']

    # if drpall.fits file does not exist for the given drpver, it tries to the last version
    # But we interested in the requested drpver SFrame, need to replace it in the file path
    if drp_record['drpver'] != drpver:
        file = file.replace(drp_record['drpver'], drpver)

    return file


@cbv(router)
class LVM(Base):
    """ Endpoints for dealing with HiPS cutouts """

    @router.get("/cutout/image/{version}/{hips}", summary='Extract image cutout from HiPS maps')
    async def get_image(self,
                        version: str = Path(..., enum=['1.1.1', '1.1.0', '1.0.3', '1.0.3b'], description="DRP/DAP version", example='1.1.0'),
                        hips: str = Path(..., description="HiPS name including version. Should be available at https://data.sdss5.org/sas/sdsswork/sandbox/data-viz/hips/sdsswork/lvm", example='hips_flx_Halpha'),
                        format: ImageFormat = Query('png', description='Format of the output image', example='png'),
                        ra: float = Query(..., description="Right Ascension in degrees (ICRS) or Galactic longitude `l` (in degrees) if `coordsys` is `galactic`.", example=13.14033),
                        dec: float = Query(..., description="Declination in degrees (ICRS) or Galactic latitude `b` (in degrees) if `coordsys` is `galactic`.", example=-72.79495),
                        coordsys: Optional[CoordinateSystem] = Query('icrs', description="Coordinate system, either `icrs` or `galactic`. If `galactic` then `ra` and `dec` are expected to be galactic longitude `l` and latitude `b`.", example='icrs'),
                        projection: Optional[WCSProjection] = Query('SIN', description=f"Projection type for WCS. Possible values: {PROJECTION_DESCRIPTIONS}.", example='SIN'),
                        pa: float = Query(0.0, description="Positional angle in degrees", example=45),
                        fov: float = Query(1.0, gt=0, description="Field of view in degrees. If width and height are not equal, then fov defines the largest dimension.", example=1.0),
                        width: int = Query(300, gt=1, description="Width in pixels", example=300),
                        height: int = Query(300, gt=1, description="Height in pixels. `Note:` `width` x `height` should not exceed 5000 x 5000 pixels.", example=300),
                        min: Optional[float] = Query(None, description="Minimum cut value. Used for jpg, png formats", example=0),
                        max: Optional[float] = Query(None, description="Maximum cut value. Used for jpg, png formats", example=10000),
                        stretch: Optional[ImageStretch] = Query('linear', description="Stretch for the image. Used for jpg, png formats.", example='linear'),
                        cmap: Optional[str] = Query('magma', description="Colormap for the image. All [Matplotlib colormaps](https://matplotlib.org/stable/users/explain/colors/colormaps.html) are accepted. Used for jpg, png formats.", example='Greys_r'),
                        ) -> Response:
        """
        ## Image cutouts service for LVM HiPS maps.

        This endpoint allows users to extract image cutouts from the LVM 
        HiPS (Hierarchical Progressive Survey) maps available at [https://data.sdss5.org/sas/sdsswork/sandbox/data-viz/hips/sdsswork/lvm](https://data.sdss5.org/sas/sdsswork/sandbox/data-viz/hips/sdsswork/lvm).


        Users can specify parameters such as sky coordinates (`ra`, `dec`), field of view (`fov`), image dimensions (`width`, `height`), and output format to retrieve the desired cutout (`png`, `jpg`, `fits`). The output image uses the `SIN` (orthographic) coordinate projection.


        This service utilizes the `hips2fits_cutout` script developed by CDS, Strasbourg Astronomical Observatory, France (DOI : 10.26093/2msf-n437).
        For more details, refer to GitHub repository [https://github.com/cds-astro/hips2fits-cutout](https://github.com/cds-astro/hips2fits-cutout).


        ### Examples:

        1. [https://data.sdss5.org/valis-lvmvis-api/lvm/cutout/image/1.1.0/hips_flx_Halpha?ra=84.0&dec=-68.92](https://data.sdss5.org/valis-lvmvis-api/lvm/cutout/image/1.1.0/hips_flx_Halpha?ra=84.0&dec=-68.92)

            Default 1 degree cutout from `1.1.0/hips_flx_Halpha` around ra=84 and dec=-68.92 (near 30 Doradus in LMC)

        2. [https://data.sdss5.org/valis-lvmvis-api/lvm/cutout/image/1.1.0/hips_vel_Halpha?ra=13.13&dec=-72.79&fov=2&stretch=linear&cmap=turbo&min=120&max=200](https://data.sdss5.org/valis-lvmvis-api/lvm/cutout/image/1.1.0/hips_vel_Halpha?ra=13.13&dec=-72.79&fov=2&stretch=linear&cmap=turbo&min=120&max=200)

            A two degree cutout from the velocity HiPS showing the SMC velocty field in range 120-200 km/s.

        3. [https://data.sdss5.org/valis-lvmvis-api/lvm/cutout/image/1.1.0/hips_ratio_log_SII6717and31_Ha?ra=154.385088&dec=-57.9132434&fov=0.51&width=700&height=630&format=fits](https://data.sdss5.org/valis-lvmvis-api/lvm/cutout/image/1.1.0/hips_ratio_log_SII6717and31_Ha?ra=154.385088&dec=-57.9132434&fov=0.51&width=700&height=630&format=fits)

            A `fits` image of log [SII]6717,31 / Halpha around NGC 3199 nebular (ra=154.385088 and dec=-57.9132434). An output `fits` image will have pixel size `0.51 * 3600 / 700 = 2.62 arcsec` which is comparable to the HEALPix pixel size of 3.22 arcsec.


        **Note:**
            LVM HiPS generated for `NSIDE=2**16` corresponds to a minimum HEALPix pixel angular size of 3.22 arcsec. To ensure a pixel size of output image comparable to 3.22 arcsec set `fov`, `width`, `height` parameters such that `fov * 3600 / max(width, height)` is comparable or higher than 3.22 arcsec.

        """

        LVM_HIPS = os.getenv("LVM_HIPS")
        hips_path = f"{LVM_HIPS}/{version}/{hips}/"

        #  Check if HiPS path exists
        if not os.path.exists(hips_path):
            raise HTTPException(status_code=404, detail=f"Requested HiPS ({hips}, ver={version}) does not exist. Please check what is available in https://data.sdss5.org/sas/sdsswork/sandbox/data-viz/hips/sdsswork/lvm")

        # Check the size of the requested image
        if width * height > 5000 * 5000:
            raise HTTPException(status_code=400, detail="Requested image size (width x height) exceeds the maximum allowed limit of 5000x5000 pixels.")

        # check that provided `cmap` is valid
        if cmap not in VALID_MATPLOTLIB_CMAPS:
            raise HTTPException(status_code=400, detail=f"Invalid colormap '{cmap}'. Valid options are: {', '.join(VALID_MATPLOTLIB_CMAPS)}. See also https://matplotlib.org/stable/users/explain/colors/colormaps.html")

        image_data = BytesIO()

        # Main part of generation cutout using hips2fits_cutout function
        sc = SkyCoord(ra, dec, frame=coordsys, unit='deg')
        wcs = _create_wcs_object(sc, width, height, fov, coordsys=coordsys, projection=projection, rotation_angle=pa)
        generate_from_wcs(wcs, hips_path, image_data, format=format, min_cut=min, max_cut=max, stretch=stretch, cmap=cmap)

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
                               version: Annotated[str, Query(description='DRP version', example='1.1.0')] = '1.1.0'):
        # construct file path for lvmSFrame-*.fits file
        suffix = str(exposure).zfill(8)
        if tile_id == 11111:
            filename = f"lvm/spectro/redux/{version}/0011XX/11111/{mjd}/lvmSFrame-{suffix}.fits"
        else:
            filename = f"lvm/spectro/redux/{version}/{str(tile_id)[:4]}XX/{tile_id}/{mjd}/lvmSFrame-{suffix}.fits"

        file = f"/data/sdss/sas/sdsswork/" + filename

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

    @router.get('/plot_fiber_spectrum/',
                summary='Endpoint to plot fiber spectra retrieved from LVM SFrame file.')
    async def plot_fiber_spectrum(
        self,
        l: List[str] = Query(None, description="Defines spectra to be plotted."),
        format: Annotated[Literal['png', 'jpg', 'jpeg', 'pdf', 'svg'], Query(description="Format of the output plot")] = 'png',
        width: Annotated[int, Query(description="Figure width in inches", gt=0)] = 15,
        height: Annotated[int, Query(description="Figure height in inches", gt=0)] = 5,
        dpi: Annotated[int, Query(description="Dots per inch (DPI) of the output image applied for rasterized formats.", gt=10, lt=600)] = 100,
        tight_layout: Annotated[bool, Query(description="Apply `tight_layout` to the plot")] = True,
        log: Annotated[bool, Query(description="Weather Y-axis logarithmically scaled")] = False,
        xlabel: Annotated[str, Query(description="X-axis label")] = "Wavelength, A",
        ylabel: Annotated[str, Query(description="Y-axis label")] = "Flux, erg/s/cm2/A",
        title: Annotated[Optional[str], Query(description="Title of the plot")] = None,
        ypmin: Annotated[float, Query(description="Y-axis minimal value (percentile)", ge=0, le=100)] = 0.1,
        ypmax: Annotated[float, Query(description="Y-axis maximal value (percentile)", ge=0, le=100)] = 99.9,
        ymin: Annotated[Optional[float], Query(description="Y-axis minimal value, overriding **ypmin**.")] = None,
        ymax: Annotated[Optional[float], Query(description="Y-axis maximal value, overriding **ypmax**.")] = None,
        xmin: Annotated[Optional[float], Query(description="X-axis minimal value")] = None,
        xmax: Annotated[Optional[float], Query(description="X-axis maximal value")] = None,
        legend: Annotated[Optional[Literal['short', 'long', '', None]],
                          Query(description="Controls the legend display. Options: 'short' (default), 'long', or None.")] = 'short',
        ) -> Response:
        """
        # Plot spectra from individual fiber/fibers

        ## Parameters

        ### **l** query parameter _(mandatory)_

        This parameter defines spectra extracted from LVM SFrame FITS cube and
        specifies plotting options. Multiple **l** parameter
        will be processed as multiple spectra to be plotted. The format for
        **l** parameter is as follows:

        ```l=key1:value1;key2:value2;...```

        The following *keys* are supported:


        - **id** (mandatory)

            Specifies the SFrame RSS file used to retrieve the averaged spectrum.
            The paramter signature is as follows:

            ```DRPversion/expnum/fiberid```

            For example, `id:1.1.1/7371/3`.

            _NOTE:_ Queries with identifiers for non-existing files will
            return a **404 NotFound** error. Incorrect formatting of the `id`
            parameter will result in a **400 Bad Request** error. `fiberid` outside
            the range [1, 1944] will also result in a **400 Bad Request** error.
            `fiberid` can point to Sci or any other fibers in the RSS file. See
            `SLITMAP` extension for more details.


        - **type** (optional, default: *flux*)

            Specifies the type of data to plot. Allowed values are:
            - **flux**: the `FLUX` extension of the SFrame file is used.
            - **sky**: the `SKY` extension of the SFrame file is used.
            - **skyflux**: the sum of `FLUX` and `SKY` extensions is used
                to retrieve the output spectrum without sky subtraction.
            - **ivar**: represents the inverse variance, `IVAR` extension.
            - **sky_ivar**: represents the sky inverse variance, `SKY_IVAR` extension.
            - **err**: calculated error from `IVAR` extensions as `1/np.sqrt(ivar)`.
            - **sky_err**: same as `err` but calculated using `SKY_IVAR`.
            - **lsf**: the line spread function extnsion `LSF`.


        - Other keys are assumed to be Matplotlib `plt.plot()` parameters like
            *color*, *marker*, *linestyle* or *ls*, *linewidth* or *lw*,
            *markersize* or *ms*, *alpha*, *zorder*, *markeredgecolor* or *mec*,
            *markerfacecolor* or *mfc*, *markeredgewidth* or *mew*, etc.
            See details in [Matplotlib documentation](https://matplotlib.org/stable/api/_as_gen/matplotlib.pyplot.plot.html).
            If unexpected keyword argumen provided, the endpoint will return a
            **400 Bad Request** error.

            Examples of Matplotlib related keys: `color:blue;alpha:0.4;linestyle:dotted`.


        ### Other parameters

        Other parameters define the plot appearance and output format. See details in the section below.


        ## Examples

        TO BE ADDED

        """

        FACTOR = 1

        if not l:
            raise HTTPException(status_code=400, detail="Query parameter 'l' is mandatory query parameter. See `lvm/spectrum_fiber_plot` documentation.")
        try:
            data = [parse_line_query_fiber(line) for line in l]
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # Iterate over spectra to be plotted
        for d in data:
            # Parse id into LVM identifiers
            try:
                drpver, expnum, fiberid = d['id'].split('/')
                expnum, fiberid = int(expnum), int(fiberid)

                if not 1 <= fiberid <= 1944:
                    raise HTTPException(status_code=400,
                                        detail=f"`fiberid` ({fiberid}) must be between 1 and 1944.")

                d['drpver'], d['expnum'], d['fiberid'] = drpver, expnum, fiberid
            except ValueError as e:
                raise HTTPException(status_code=400,
                                    detail=("Invalid `id` parameter. Must be in the format `DRPversion/expnum/fiberid` "
                                            "i.e. `id:1.1.0/7371/532`"))

            file = get_SFrame_filename(expnum, drpver)

            if not os.path.exists(file):
                raise HTTPException(status_code=404, detail=f"File {filename} does not exist.")

            # Read data and construct required spectrum to be plotted
            with fits.open(file) as hdul:
                wave = hdul['WAVE'].data
                ifib = fiberid - 1

                extractor = {
                    'flux': lambda hdul, ifib: hdul['FLUX'].data[ifib, :],
                    'sky': lambda hdul, ifib: hdul['SKY'].data[ifib, :],
                    'skyflux': lambda hdul, ifib: hdul['SKY'].data[ifib, :] + hdul['FLUX'].data[ifib, :],
                    'err': lambda hdul, ifib: np.sqrt(1 / hdul['IVAR'].data[ifib, :]),
                    'sky_err': lambda hdul, ifib: np.sqrt(1 / hdul['SKY_IVAR'].data[ifib, :]),
                    'ivar': lambda hdul, ifib: hdul['IVAR'].data[ifib, :],
                    'sky_ivar': lambda hdul, ifib: hdul['SKY_IVAR'].data[ifib, :],
                    'lsf': lambda hdul, ifib: hdul['LSF'].data[ifib, :],
                }

                try:
                    d['array'] = extractor[d['type']](hdul, ifib) * FACTOR
                except KeyError:
                    raise ValueError(f"Invalid type: {d['type']}")

            # Extract additional plotting kwargs
            non_plot_keys = {'id', 'drpver', 'expnum', 'fiberid', 'type', 'array'}
            d['plot_kwargs'] = {key: value for key, value in d.items() if key not in non_plot_keys}

        # Create a plot
        fig = plt.figure(figsize=(width, height))

        for d in data:
            legend_options = dict(
                short="{expnum} {fiberid}".format(**d),
                long="{expnum} {fiberid} {drpver}".format(**d),
            )
            label  = legend_options.get(legend, None)
            try:
                plt.plot(wave, d['array'], label=label, **d['plot_kwargs'])
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))

        plt.xlabel(xlabel)
        plt.ylabel(ylabel)

        if title is not None:
            plt.title(title)

        ymin = ymin if ymin is not None else np.nanpercentile([d['array'] for d in data], ypmin)
        ymax = ymax if ymax is not None else np.nanpercentile([d['array'] for d in data], ypmax)
        plt.ylim(ymin, ymax)

        xmin = xmin if xmin is not None else np.nanmin(wave)
        xmax = xmax if xmax is not None else np.nanmax(wave)
        plt.xlim(xmin, xmax)

        if log:
            plt.yscale('log')

        if tight_layout:
            plt.tight_layout()

        if legend is not None:
            plt.legend()

        # write output plot
        buffer = BytesIO()
        fig.savefig(buffer, format=format, dpi=dpi)
        plt.close()
        buffer.seek(0)

        media_types = dict(jpg='image/jpeg',
                           jpeg='image/jpeg',
                           png='image/png',
                           svg='image/svg+xml',
                           pdf='application/pdf')

        return StreamingResponse(buffer,
                                 media_type=media_types[format],
                                 headers={"Content-Disposition": f'inline; filename=lvm_spectrum_{expnum}_{fiberid}.{format}',
                                          "Content-Length": str(buffer.getbuffer().nbytes)})

    @router.get('/plot_exposure_spectrum/',
                summary='Endpoint to plot averaged spectra retrieved from LVM SFrame file.')
    async def plot_exposure_spectrum(
        self,
        l: List[str] = Query(None, description="Defines spectra to be plotted."),
        format: Annotated[Literal['png', 'jpg', 'jpeg', 'pdf', 'svg'], Query(description="Format of the output plot")] = 'png',
        width: Annotated[int, Query(description="Figure width in inches", gt=0)] = 15,
        height: Annotated[int, Query(description="Figure height in inches", gt=0)] = 5,
        dpi: Annotated[int, Query(description="Dots per inch (DPI) of the output image applied for rasterized formats.", gt=10, lt=600)] = 100,
        tight_layout: Annotated[bool, Query(description="Apply `tight_layout` to the plot")] = True,
        log: Annotated[bool, Query(description="Weather Y-axis logarithmically scaled")] = False,
        xlabel: Annotated[str, Query(description="X-axis label")] = "Wavelength, A",
        ylabel: Annotated[str, Query(description="Y-axis label")] = "Flux, erg/s/cm2/A",
        title: Annotated[Optional[str], Query(description="Title of the plot")] = None,
        ypmin: Annotated[float, Query(description="Y-axis minimal value (percentile)", ge=0, le=100)] = 0.1,
        ypmax: Annotated[float, Query(description="Y-axis maximal value (percentile)", ge=0, le=100)] = 99.9,
        ymin: Annotated[Optional[float], Query(description="Y-axis minimal value, overriding **ypmin**.")] = None,
        ymax: Annotated[Optional[float], Query(description="Y-axis maximal value, overriding **ypmax**.")] = None,
        xmin: Annotated[Optional[float], Query(description="X-axis minimal value")] = None,
        xmax: Annotated[Optional[float], Query(description="X-axis maximal value")] = None,
        legend: Annotated[Optional[Literal['short', 'long', '', None]],
                          Query(description="Controls the legend display. Options: 'short' (default), 'long', or None.")] = 'short',
        ) -> Response:
        """
        # Plot spectra from individual exposure

        This endpoint plots averaged spectra retrieved from LVM SFrame FITS files.

        ## Parameters

        ### **l** query parameter _(mandatory)_

        This parameter defines how spectra extracted from exposure
        FITS files and specifies plotting options. Multiple **l** parameter
        will be processed as multiple spectra to be plotted. The format for
        **l** parameter is as follows:

        ```l=key1:value1;key2:value2;...```

        The following *keys* are supported:


        - **id** (mandatory)

            Specifies the SFrame RSS file used to retrieve the averaged spectrum.
            The paramter signature is as follows:

            ```DRPversion/expnum```

            For example, `id:1.1.0/07371`.

            _NOTE:_ Queries with identifiers for non-existing files will
            return a **404 NotFound** error. Incorrect formatting of the `id`
            parameter will result in a **400 Bad Request** error.


        - **type** (optional, default: *flux*)

            Specifies the type of data to plot. Allowed values are:
            - **flux**: the `FLUX` extension of the SFrame file is used.
            - **sky**: the `SKY` extension of the SFrame file is used.
            - **skyflux**: the sum of `FLUX` and `SKY` extensions is used
                to retrieve the output spectrum without sky subtraction.
            - **ivar**: represents the inverse variance, `IVAR` extension.
            - **sky_ivar**: represents the sky inverse variance, `SKY_IVAR` extension.
            - **err**: calculated error from `IVAR` extensions as `1/np.sqrt(ivar)`.
            - **sky_err**: same as `err` but calculated using `SKY_IVAR`.
            - **lsf**: the line spread function extnsion `LSF`.



        - **method** (optional, default: *median*)

            Specifies the aggregation method used to process the data. Allowed
            values are:

            - **mean**: Calculate the mean value using `np.nanmean()`.
            - **median**: Calculate the median value using `np.nanmedian()`.
            - **std**: Calculate the standard deviation using `np.std()`.
            - **percentile_XX**: Calculate a specific percentile using
                `np.percentile()`, where **XX** is the desired percentile
                value (e.g., **percentile_90.3**). Percentile value must be in
                the range [0, 100].


        - **telescope** (optional, default: *Sci*):

            Specifies the fibers corresponding to the
            selected telescope used for averaging the output spectrum. The same
            values in the **telescope** column in the `SLITMAP` extension.
            Allowed values are:

            - **Sci**: Science telescope data.
            - **SkyE**: Sky East telescope data.
            - **SkyW**: Sky West telescope data.
            - **Spec**: Photometrical spectral standard telescope fibers.


        - **fibstatus** (optional, default: *0*): Specifies the fiber status to filter the
            fibers in RSS file. The same values in the **fibstatus** column in
            the `SLITMAP` extension.

        - Other keys are assumed to be Matplotlib `plt.plot()` parameters like
            *color*, *marker*, *linestyle* or *ls*, *linewidth* or *lw*,
            *markersize* or *ms*, *alpha*, *zorder*, *markeredgecolor* or *mec*,
            *markerfacecolor* or *mfc*, *markeredgewidth* or *mew*, etc.
            See details in [Matplotlib documentation](https://matplotlib.org/stable/api/_as_gen/matplotlib.pyplot.plot.html).
            If unexpected keyword argumen provided, the endpoint will return a
            **400 Bad Request** error.

            Examples of Matplotlib related keys: `color:blue;alpha:0.4;linestyle:dotted`.


        ### Other parameters

        Other parameters define the plot appearance and output format. See details in the section below.


        ## Examples


        1. `https://data.sdss5.org/valis-lvmvis-api/lvm/plot_exposure_spectrum/?l=id:1.1.0/11121`

            A minimal example showing the default median spectrum of good science
            fibers for exposure 11121.

            [![Example1](https://data.sdss5.org/valis-lvmvis-api/lvm/plot_exposure_spectrum/?l=id:1.1.0/11121 "Click to open image URL")](https://data.sdss5.org/valis-lvmvis-api/lvm/plot_exposure_spectrum/?l=id:1.1.0/11121)

        2. ```
            https://data.sdss5.org/valis-lvmvis-api/lvm/plot_exposure_spectrum/?
                l=id:1.1.0/15084;type:flux;method:mean;lw:0.5;color:red&
                xmin=6540&xmax=6750&ymin=0&ymax=1.5e-13&width=4&height=5
            ```
            This example demonstrates the spectrum around the H-alpha line with
            custom size of the plot.

            [![Example2](https://data.sdss5.org/valis-lvmvis-api/lvm/plot_exposure_spectrum/?l=id:1.1.0/15084;type:flux;method:mean;lw:0.5;color:red&xmin=6540&xmax=6750&ymin=0&ymax=1.5e-13&width=4&height=5 "Click to open image URL")](https://data.sdss5.org/valis-lvmvis-api/lvm/plot_exposure_spectrum/?l=id:1.1.0/15084;type:flux;method:mean;lw:0.5;color:red&xmin=6540&xmax=6750&ymin=0&ymax=1.5e-13&width=4&height=5)


        3. ```
            https://data.sdss5.org/valis-lvmvis-api/lvm/plot_exposure_spectrum/?
                l=id:1.1.0/15084;type:skyflux;method:mean;color:blue;lw:0.3&
                l=id:1.1.0/15084;type:err;method:mean;color:gray;alpha:0.7&
                l=id:1.1.0/15084;type:flux;method:mean;color:darkred&
                ypmax=99
            ```
            Plotting three spectra retrieved from the same SFrame (exposure
            15084): the mean spectrum, spectrum + sky, and error. The error,
            derived from the `IVAR` extension, is calculated as
            `err = np.sqrt(np.mean(1 / IVAR))`.

            [![Example3](https://data.sdss5.org/valis-lvmvis-api/lvm/plot_exposure_spectrum/?l=id:1.1.0/15084;type:skyflux;method:mean;color:blue;lw:0.3&l=id:1.1.0/15084;type:err;method:mean;color:gray;alpha:0.7&l=id:1.1.0/15084;type:flux;method:mean;color:darkred&ypmax=99 "Click to open image URL")](https://data.sdss5.org/valis-lvmvis-api/lvm/plot_exposure_spectrum/?l=id:1.1.0/15084;type:skyflux;method:mean;color:blue;lw:0.3&l=id:1.1.0/15084;type:err;method:mean;color:gray;alpha:0.7&l=id:1.1.0/15084;type:flux;method:mean;color:darkred&ypmax=99)

        4. ```
            https://data.sdss5.org/valis-lvmvis-api/lvm/plot_exposure_spectrum/?
                l=id:1.0.3/15084;color:red;lw:0.4&
                l=id:1.1.0/15084;color:purple&
                legend=long&ymin=-2e-13&ymax=2e-13&
                title=Comparison%20DRP%201.1.0%20vs.%201.0.3%20for%20exposure=15084
            ```

            Example of spectra retrieved from separate SFrames: one for DRP version 1.0.3 and another for 1.1.0.

            [![Example4](https://data.sdss5.org/valis-lvmvis-api/lvm/plot_exposure_spectrum/?l=id:1.0.3/15084;color:red;lw:0.4&l=id:1.1.0/15084;color:purple&legend=long&ymin=-2e-13&ymax=2e-13&title=Comparison%20DRP%201.1.0%20vs.%201.0.3%20for%20exposure=15084 "Click to open image URL")](https://data.sdss5.org/valis-lvmvis-api/lvm/plot_exposure_spectrum/?l=id:1.0.3/15084;color:red;lw:0.4&l=id:1.1.0/15084;color:purple&legend=long&ymin=-2e-13&ymax=2e-13&title=Comparison%20DRP%201.1.0%20vs.%201.0.3%20for%20exposure=15084)
        """

        FACTOR = 1

        if not l:
            raise HTTPException(status_code=400, detail="Query parameter 'l' is mandatory query parameter. See `lvm/spectrum_exposures_plot` documentation.")

        try:
            data = [parse_line_query_exposure(line) for line in l]
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # iterate over spectra to be plotted
        for d in data:
            # parse id into standard LVM id and create full path to SFRame
            try:
                drpver, expnum = d['id'].split('/')
                expnum = int(expnum)
                d['drpver'], d['expnum'] = drpver, expnum
            except ValueError as e:
                raise HTTPException(
                    status_code=400,
                    detail=("Invalid `id` parameter. Must be in the format `DRPversion/expnum` "
                            "i.e. `id:1.1.0/7371`"))

            file = get_SFrame_filename(expnum, drpver)

            if not os.path.exists(file):
                raise HTTPException(status_code=404, detail=f"File {filename} does not exist.")

            # read data and construct required spectrum to be plotted

            with fits.open(file) as hdul:
                wave = hdul['WAVE'].data
                slitmap = hdul['SLITMAP'].data

                mask = (slitmap['telescope'] == d.get('telescope', 'Sci')) & (slitmap['fibstatus'] == d.get('fibstatus', 0))

                aggregation_functions = {
                    'mean': partial(np.nanmean, axis=0),
                    'median': partial(np.nanmedian, axis=0),
                    'std': partial(np.nanstd, axis=0),
                    'percentile': partial(np.nanpercentile, q=d.get('percentile_value', 50), axis=0)
                }

                aggfunc = aggregation_functions[d['method']]

                try:
                    if d['type'] in {'flux', 'sky', 'skyflux', 'lsf'}:
                        if d['type'] == 'flux':
                            values = hdul['FLUX'].data[mask, :]
                        elif d['type'] == 'sky':
                            values = hdul['SKY'].data[mask, :]
                        elif d['type'] == 'lsf':
                            values = hdul['LSF'].data[mask, :]
                        elif d['type'] == 'skyflux':
                            values = (hdul['SKY'].data[mask, :] +
                                      hdul['FLUX'].data[mask, :])
                        # Directly apply the aggregation function
                        d['array'] = aggfunc(values) * FACTOR

                    elif d['type'] in {'err', 'sky_err'}:
                        if d['type'] == 'err':
                            ivar = hdul['IVAR'].data[mask, :]
                        elif d['type'] == 'sky_err':
                            ivar = hdul['SKY_IVAR'].data[mask, :]
                        # Convert IVAR to VAR, apply the aggregation function,
                        # and then convert back to ERR
                        d['array'] = np.sqrt(aggfunc(1.0 / ivar)) * FACTOR

                    elif d['type'] in {'ivar', 'sky_ivar'}:
                        if d['type'] == 'ivar':
                            ivar = hdul['IVAR'].data[mask, :]
                        elif d['type'] == 'sky_ivar':
                            ivar = hdul['SKY_IVAR'].data[mask, :]
                        d['array'] = aggfunc(ivar) * FACTOR
                except ValueError as e:
                    # this will handle error if percentile value is out of range [0, 100]
                    raise HTTPException(status_code=400, detail=str(e))

            # Extract additional plotting kwargs
            non_plot_keys = {'id', 'drpver', 'tile_id', 'mjd', 'expnum', 'type',
                             'method', 'telescope', 'fibstatus', 'array', 'percentile_value'}
            d['plot_kwargs'] = {key: value for key, value in d.items() if key not in non_plot_keys}

        # Create a plot
        fig = plt.figure(figsize=(width, height))

        for d in data:
            legend_options = dict(
                short="{expnum} {method}({type})".format(**d),
                long="{expnum} {method}({type}) {telescope} {drpver}".format(**d),
            )
            label  = legend_options.get(legend, None)
            try:
                plt.plot(wave, d['array'], label=label, **d['plot_kwargs'])
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))

        plt.xlabel(xlabel)
        plt.ylabel(ylabel)

        if title is not None:
            plt.title(title)

        ymin = ymin if ymin is not None else np.nanpercentile([d['array'] for d in data], ypmin)
        ymax = ymax if ymax is not None else np.nanpercentile([d['array'] for d in data], ypmax)
        plt.ylim(ymin, ymax)

        xmin = xmin if xmin is not None else np.nanmin(wave)
        xmax = xmax if xmax is not None else np.nanmax(wave)
        plt.xlim(xmin, xmax)

        if log:
            plt.yscale('log')

        if tight_layout:
            plt.tight_layout()

        if legend is not None:
            plt.legend()

        # write output plot
        buffer = BytesIO()
        fig.savefig(buffer, format=format, dpi=dpi)
        plt.close()
        buffer.seek(0)

        media_types = dict(jpg='image/jpeg',
                           jpeg='image/jpeg',
                           png='image/png',
                           svg='image/svg+xml',
                           pdf='application/pdf')

        return StreamingResponse(buffer,
                                 media_type=media_types[format],
                                 headers={"Content-Disposition": f'inline; filename=lvm_spectrum_{expnum}.{format}',
                                          "Content-Length": str(buffer.getbuffer().nbytes)})

    @router.get('/dap_lines/{tile_id}/{mjd}/{exposure}',
                summary='Experimental endpoint to extract LVM DAP emission line fluxes')
    async def get_dap_fluxes(self,
                             tile_id: Annotated[int, Path(description="The tile_id of the LVM pointing", example=1028790)],
                             mjd: Annotated[int, Path(desciption='The MJD of the observations', example=60314)],
                             exposure: Annotated[int, Path(desciption='The exposure number', example=10328)],
                             wl = Query('6562.85,4861.36', description='List of emission lines to be retrieved', example='6562.85,4861.36'),
                             version: Annotated[str, Query(description='DRP version', example='1.1.0')] = '1.1.0',
                             ):

        # construct file path for lvmSFrame-*.fits file
        suffix = str(exposure).zfill(8)
        if tile_id == 11111:
            filename = f"lvm/spectro/analysis/{version}/0011XX/11111/{mjd}/{suffix}/dap-rsp108-sn20-{suffix}.dap.fits.gz"
        else:
            filename = f"lvm/spectro/analysis/{version}/{str(tile_id)[:4]}XX/{tile_id}/{mjd}/{suffix}/dap-rsp108-sn20-{suffix}.dap.fits.gz"

        file = f"/data/sdss/sas/sdsswork/" + filename

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
