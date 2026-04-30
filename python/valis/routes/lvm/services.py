"""
Synchronous spectrum extraction and plotting helpers.

These helpers are designed to be called from a background executor
(see LVMBase.run_sync). `extract_fiber_data` and `aggregate_exposure_spectrum`
operate on an already-open astropy HDUList; `extract_dap_fiber_data` opens
the DAP files itself because it needs two HDULs at once.
"""
from __future__ import annotations

from io import BytesIO
from functools import partial
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from astropy.io import fits
from fastapi.responses import StreamingResponse

from .common import ALLOWED_LINE_TYPES


def extract_fiber_data(hdul: fits.HDUList,
                       fiberid: int,
                       spectrum_type: str = 'flux',
                       factor: float = 1e17) -> np.ndarray:
    """Extract DRP fiber spectrum from SFrame HDU list."""
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
    return extractors[spectrum_type](hdul, ifib)


def aggregate_exposure_spectrum(hdul: fits.HDUList,
                                spectrum_type: str,
                                method: str,
                                telescope: str = 'Sci',
                                fibstatus: int = 0,
                                percentile_value: float = 50.0,
                                factor: float = 1e17) -> Tuple[np.ndarray, np.ndarray]:
    """Aggregate spectrum across fibers in an exposure."""
    wave_data = hdul['WAVE'].data
    slitmap = hdul['SLITMAP'].data
    mask = (slitmap['telescope'] == telescope) & (slitmap['fibstatus'] == fibstatus)

    aggfunc = {
        'mean': partial(np.nanmean, axis=0),
        'median': partial(np.nanmedian, axis=0),
        'std': partial(np.nanstd, axis=0),
        'percentile': partial(np.nanpercentile, q=percentile_value, axis=0),
    }[method]

    try:
        if spectrum_type in {'flux', 'sky', 'skyflux'}:
            if spectrum_type == 'flux':
                values = hdul['FLUX'].data[mask, :]
            elif spectrum_type == 'sky':
                values = hdul['SKY'].data[mask, :]
            else:
                values = hdul['SKY'].data[mask, :] + hdul['FLUX'].data[mask, :]
            spectrum_array = aggfunc(values) * factor
        elif spectrum_type == 'lsf':
            spectrum_array = aggfunc(hdul['LSF'].data[mask, :])
        elif spectrum_type in {'err', 'sky_err'}:
            col = 'IVAR' if spectrum_type == 'err' else 'SKY_IVAR'
            spectrum_array = np.sqrt(aggfunc(1.0 / hdul[col].data[mask, :])) * factor
        elif spectrum_type in {'ivar', 'sky_ivar'}:
            col = 'IVAR' if spectrum_type == 'ivar' else 'SKY_IVAR'
            spectrum_array = aggfunc(hdul[col].data[mask, :]) / factor**2
        else:
            raise ValueError(f"Unsupported spectrum_type for aggregation: {spectrum_type}")
    except ValueError as e:
        raise ValueError(f"Error processing aggregation: {e}")

    return wave_data, spectrum_array


def extract_dap_fiber_data(dap_file: str,
                           output_file: str,
                           fiberid: int,
                           component_names: List[str],
                           factor: float = 1e17) -> Dict[str, Any]:
    """Extract DAP data for a specific fiber."""
    with fits.open(dap_file) as dap_hdul:
        pt_table = dap_hdul['PT'].data
        fiber_mask = pt_table['fiberid'] == fiberid
        if not np.any(fiber_mask):
            raise ValueError(f"Fiber {fiberid} not found in DAP PT table")
        fiber_idx = np.where(fiber_mask)[0][0]
        fiber_info = pt_table[fiber_idx]

    with fits.open(output_file) as out_hdul:
        data = (out_hdul[0].data[:, fiber_idx, :] * factor).astype(np.float32)
        hdr = out_hdul[0].header
        crval, cdelt, crpix = hdr['CRVAL1'], hdr['CDELT1'], hdr['CRPIX1']
        wave = (crval + cdelt * (np.arange(0, data.shape[1]) - (crpix - 1))).astype(np.float32)

        # Order defines plotting sequence (first = bottom, last = top)
        extractors = {
            'observed': lambda d: d[0, :],
            'residual_np': lambda d: d[4, :] - d[7, :] + d[6, :],
            'residual_pm': lambda d: d[4, :],
            'emission_np': lambda d: d[6, :],
            'emission_pm': lambda d: d[7, :],
            'stellar_continuum': lambda d: d[1, :],
            'full_model_np': lambda d: d[2, :] - d[7, :] + d[6, :],
            'full_model_pm': lambda d: d[2, :],
        }
        if 'all' in component_names:
            component_names = list(extractors.keys())
        components = {c: extractors[c](data) for c in component_names if c in extractors}

    return {
        'wave': wave,
        'components': components,
        'ra': float(fiber_info['ra']),
        'dec': float(fiber_info['dec']),
        'mask': bool(fiber_info['mask']),
    }


def create_spectrum_plot(wave: np.ndarray,
                         data: List[Dict[str, Any]],
                         width: float = 10.0,
                         height: float = 6.0,
                         xlabel: str = 'Wavelength [Å]',
                         ylabel: str = 'Flux',
                         title: Optional[str] = None,
                         legend: Optional[str] = None,
                         xmin: Optional[float] = None,
                         xmax: Optional[float] = None,
                         ymin: Optional[float] = None,
                         ymax: Optional[float] = None,
                         ypmin: float = 1.0,
                         ypmax: float = 99.0,
                         log: bool = False):
    """Build a matplotlib figure for a list of spectra dicts."""
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=(width, height))
    has_labels = False
    for d in data:
        kwargs = d.get('plot_kwargs', {})
        if kwargs.get('label'):
            has_labels = True
        else:
            label = None
            if legend and 'expnum' in d:
                if legend == 'short':
                    label = "{expnum} {method}({type})".format(**d)
                elif legend == 'long':
                    label = "{expnum} {method}({type}) {telescope} {drpver}".format(**d)
                has_labels = True
            if label:
                kwargs = {'label': label, **kwargs}
        try:
            plt.plot(wave, d['array'], **kwargs)
        except Exception as e:
            raise ValueError(f"Error creating plot: {e}")

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


def figure_response(fig, format: str, dpi: int) -> StreamingResponse:
    """Save matplotlib figure to buffer and return as streaming response."""
    import matplotlib.pyplot as plt
    buffer = BytesIO()
    fig.savefig(buffer, format=format, dpi=dpi, bbox_inches='tight')
    plt.close(fig)
    buffer.seek(0)
    media_types = {'png': 'image/png', 'jpg': 'image/jpeg', 'pdf': 'application/pdf', 'svg': 'image/svg+xml'}
    return StreamingResponse(buffer, media_type=media_types.get(format, 'image/png'))
