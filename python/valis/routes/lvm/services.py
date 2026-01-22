"""
Service layer for LVM routes: DRP extraction, DAP extraction, plotting utilities
"""
from __future__ import annotations

import os
import asyncio
from io import BytesIO
from functools import partial
from typing import Dict, Any, List, Tuple
import numpy as np
from astropy.io import fits
from fastapi.responses import StreamingResponse

from .common import ALLOWED_LINE_TYPES, arr2list


def extract_fiber_data(hdul: fits.HDUList,
                       fiberid: int,
                       spectrum_type: str = 'flux',
                       factor: float = 1e17) -> np.ndarray:
    """
    Extract DRP fiber spectrum data from SFrame FITS file.
    Used by both data endpoints and plot endpoints.
    """
    ifib = fiberid - 1

    if spectrum_type not in ALLOWED_LINE_TYPES:
        raise ValueError(f"Invalid spectrum type: {spectrum_type}. Allowed: {list(ALLOWED_LINE_TYPES)}")

    wave_shape = hdul['WAVE'].data.shape

    def err_from_ivar(ivar, shape):
        err = np.full(shape, np.nan)
        if ivar is None:
            return err
        valid = np.isfinite(ivar) & (ivar > 0)
        err[valid] = np.sqrt(1.0 / ivar[valid]) * factor
        return err

    extractors = {
        'flux': lambda h, i: h['FLUX'].data[i, :] * factor,
        'sky': lambda h, i: h['SKY'].data[i, :] * factor,
        'skyflux': lambda h, i: (h['SKY'].data[i, :] + h['FLUX'].data[i, :]) * factor,
        'err': lambda h, i: err_from_ivar(h['IVAR'].data[i, :] if 'IVAR' in h else None, wave_shape),
        'sky_err': lambda h, i: err_from_ivar(h['SKY_IVAR'].data[i, :] if 'SKY_IVAR' in h else None, wave_shape),
        'ivar': lambda h, i: h['IVAR'].data[i, :] / factor**2,
        'sky_ivar': lambda h, i: h['SKY_IVAR'].data[i, :] / factor**2,
        'lsf': lambda h, i: h['LSF'].data[i, :],
    }

    result = extractors[spectrum_type](hdul, ifib)
    return result


def aggregate_exposure_spectrum(hdul: fits.HDUList,
                                spectrum_type: str,
                                method: str,
                                telescope: str = 'Sci',
                                fibstatus: int = 0,
                                percentile_value: float = 50.0,
                                factor: float = 1e17) -> Tuple[np.ndarray, np.ndarray]:
    """
    Aggregate spectrum across multiple fibers in an exposure.
    """
    wave_data = hdul['WAVE'].data
    slitmap = hdul['SLITMAP'].data

    mask = (slitmap['telescope'] == telescope) & (slitmap['fibstatus'] == fibstatus)

    aggregation_functions = {
        'mean': partial(np.nanmean, axis=0),
        'median': partial(np.nanmedian, axis=0),
        'std': partial(np.nanstd, axis=0),
        'percentile': partial(np.nanpercentile, q=percentile_value, axis=0)
    }

    aggfunc = aggregation_functions[method]

    try:
        if spectrum_type in {'flux', 'sky', 'skyflux'}:
            if spectrum_type == 'flux':
                values = hdul['FLUX'].data[mask, :]
            elif spectrum_type == 'sky':
                values = hdul['SKY'].data[mask, :]
            elif spectrum_type == 'skyflux':
                values = hdul['SKY'].data[mask, :] + hdul['FLUX'].data[mask, :]
            spectrum_array = aggfunc(values) * factor

        elif spectrum_type == 'lsf':
            values = hdul['LSF'].data[mask, :]
            spectrum_array = aggfunc(values)  # LSF is no scaling

        elif spectrum_type in {'err', 'sky_err'}:
            if spectrum_type == 'err':
                ivar = hdul['IVAR'].data[mask, :]
            elif spectrum_type == 'sky_err':
                ivar = hdul['SKY_IVAR'].data[mask, :]
            spectrum_array = np.sqrt(aggfunc(1.0 / ivar)) * factor

        elif spectrum_type in {'ivar', 'sky_ivar'}:
            if spectrum_type == 'ivar':
                ivar = hdul['IVAR'].data[mask, :]
            elif spectrum_type == 'sky_ivar':
                ivar = hdul['SKY_IVAR'].data[mask, :]
            spectrum_array = aggfunc(ivar) / factor**2
    except ValueError as e:
        raise ValueError(f"Error processing aggregation: {str(e)}")

    return wave_data, spectrum_array


def extract_dap_fiber_data(dap_file: str,
                           output_file: str,
                           fiberid: int,
                           component_names: List[str],
                           factor: float = 1e17) -> Dict[str, Any]:
    """
    Extract DAP data for specific fiber.
    """
    with fits.open(dap_file) as dap_hdul:
        pt_table = dap_hdul['PT'].data
        fiber_mask = pt_table['fiberid'] == fiberid

        if not np.any(fiber_mask):
            raise ValueError(f"Fiber {fiberid} not found in DAP PT table")

        fiber_idx = np.where(fiber_mask)[0][0]
        fiber_info = pt_table[fiber_idx]

    with fits.open(output_file) as output_hdul:
        data = output_hdul[0].data[:, fiber_idx, :] * factor
        data = data.astype(np.float32)
        hdr = output_hdul[0].header

        crval, cdelt, crpix = hdr['CRVAL1'], hdr['CDELT1'], hdr['CRPIX1']
        nx = data.shape[1]
        wave = crval + cdelt * (np.arange(0, nx) - (crpix - 1))
        wave = wave.astype(np.float32)

        # Order defines plotting sequence (first = bottom, last = top)
        component_extractors = {
            'observed': lambda d: d[0, :],
            'residual_np': lambda d: d[0, :] - (d[8, :] - d[7, :] + d[6, :]),
            'residual_pm': lambda d: d[0, :] - d[8, :],
            'emission_np': lambda d: d[6, :],
            'emission_pm': lambda d: d[7, :],
            'stellar_continuum': lambda d: d[8, :] - d[7, :],
            'full_model_np': lambda d: d[8, :] - d[7, :] + d[6, :],
            'full_model_pm': lambda d: d[8, :],
        }

        if 'all' in component_names:
            component_names = list(component_extractors.keys())

        # Preserve requested order using list comprehension
        valid_components = [c for c in component_names if c in component_extractors]
        components = {comp: component_extractors[comp](data) for comp in valid_components}

    return {
        'wave': wave,
        'components': components,
        'ra': float(fiber_info['ra']),
        'dec': float(fiber_info['dec']),
        'mask': bool(fiber_info['mask'])
    }


def create_spectrum_plot(wave: np.ndarray,
                         data: List[Dict[str, Any]],
                         width: float = 10.0,
                         height: float = 6.0,
                         xlabel: str = 'Wavelength [Å]',
                         ylabel: str = 'Flux',
                         title: str = None,
                         legend: str = None,
                         xmin: float = None,
                         xmax: float = None,
                         ymin: float = None,
                         ymax: float = None,
                         ypmin: float = 1.0,
                         ypmax: float = 99.0,
                         log: bool = False) -> 'matplotlib.figure.Figure':
    """
    Common plotting logic for spectrum visualization.
    """
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=(width, height))

    has_labels = False
    for d in data:
        plot_kwargs = d.get('plot_kwargs', {})

        # Check if label already exists and has a value in plot_kwargs
        if plot_kwargs.get('label'):
            has_labels = True
        else:
            # Create label for DRP data if legend parameter is set
            label = None
            if legend and 'expnum' in d:
                if legend == 'short':
                    label = "{expnum} {method}({type})".format(**d)
                elif legend == 'long':
                    label = "{expnum} {method}({type}) {telescope} {drpver}".format(**d)
                has_labels = True
            if label:
                plot_kwargs = {'label': label, **plot_kwargs}

        try:
            plt.plot(wave, d['array'], **plot_kwargs)
        except Exception as e:
            raise ValueError(f"Error creating plot: {str(e)}")

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

    if has_labels:
        plt.legend()

    return fig


async def process_spectrum_requests(spectrum_requests: List[Tuple[int, int, str, str]],
                                    get_sframe_fn,
                                    get_drpall_fn,
                                    factor: float = 1e17) -> Tuple[List[Dict[str, Any]], np.ndarray]:
    """
    Process spectrum requests and return spectra data with common wavelength.
    """
    from .io import async_file_exists

    spectra_data = []
    common_wave = None
    loop = asyncio.get_event_loop()

    for expnum, fiberid, drpver, spectrum_type in spectrum_requests:
        try:
            full_file_path = await get_sframe_fn(expnum, drpver)
            drp_record = await get_drpall_fn(expnum, drpver)
            location = drp_record['location']
            relative_sas_path = location.decode() if isinstance(location, bytes) else location
            rec_drpver = drp_record['drpver']
            rec_drpver = rec_drpver.decode() if isinstance(rec_drpver, bytes) else rec_drpver

            if rec_drpver != drpver:
                relative_sas_path = relative_sas_path.replace(rec_drpver, drpver)
        except IndexError:
            raise ValueError(f"Exposure {expnum} for DRP {drpver} not found")
        except FileNotFoundError as e:
            raise ValueError(f"DRPall file error: {e}")

        if not await async_file_exists(full_file_path):
            raise ValueError(f"SFrame file not found: {full_file_path}")

        def read_fits():
            with fits.open(full_file_path) as hdul:
                return hdul['WAVE'].data, extract_fiber_data(hdul, fiberid, spectrum_type, factor)

        wave_data, data_array = await loop.run_in_executor(None, read_fits)

        if common_wave is None:
            common_wave = wave_data

        spectra_data.append({
            'filename': relative_sas_path,
            'drpver': drpver,
            'expnum': expnum,
            'fiberid': fiberid,
            'spectrum_type': spectrum_type,
            spectrum_type: arr2list(data_array)
        })

    if not spectra_data:
        raise ValueError("No valid spectrum data retrieved")
    if common_wave is None:
        raise ValueError("Could not retrieve wavelength data")

    return spectra_data, common_wave


def figure_response(fig, format: str, dpi: int) -> StreamingResponse:
    """Save matplotlib figure to buffer and return as streaming response."""
    import matplotlib.pyplot as plt

    buffer = BytesIO()
    fig.savefig(buffer, format=format, dpi=dpi, bbox_inches='tight')
    plt.close(fig)
    buffer.seek(0)
    media_types = {
        'png': 'image/png',
        'jpg': 'image/jpeg',
        'pdf': 'application/pdf',
        'svg': 'image/svg+xml'
    }
    return StreamingResponse(buffer, media_type=media_types.get(format, 'image/png'))

