"""
LVM DAP endpoints: fiber output data, emission line fluxes, and plots
"""
from __future__ import annotations

from typing import List, Annotated, Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi_restful.cbv import cbv
from fastapi.responses import StreamingResponse
import numpy as np
import pandas as pd
from astropy.io import fits

from valis.routes.base import Base
from valis.routes.files import ORJSONResponseCustom

from ..common import arr2list, parse_line_query_dap_fiber, validate_fiberid
from ..io import get_DAP_filenames, run_in_executor
from ..services import extract_dap_fiber_data, create_spectrum_plot, figure_response

# Default colors for DAP components when not specified
DAP_COMPONENT_COLORS = {
    'observed': '#1f77b4',
    'stellar_continuum': '#ff7f0e',
    'emission_np': '#2ca02c',
    'emission_pm': '#d62728',
    'full_model_pm': '#9467bd',
    'full_model_np': '#8c564b',
    'residual_pm': '#7f7f7f',
    'residual_np': '#e377c2',
}

router = APIRouter()


@cbv(router)
class DAP(Base):
    """DAP analysis endpoints"""

    @router.get('/dap/fiber/', summary='Get LVM DAP Fiber Output Data')
    async def get_dap_fiber(
        self,
        l: List[str] = Query(..., description="DAP fiber definition: `id:DAPversion/expnum/fiberid[;components:...]`")
    ) -> ORJSONResponseCustom:
        """
        # Get LVM DAP Fiber Output Data

        Retrieves DAP spectral components for specified fibers.

        ## Query Format

        `l=id:DAPversion/expnum/fiberid[;components:observed,stellar_continuum,...]`

        ## Components

        - `observed` - Observed spectrum
        - `stellar_continuum` - Stellar continuum model
        - `emission_np` - Non-parametric emission lines
        - `emission_pm` - Parametric emission lines
        - `full_model_pm` - Full model (parametric)
        - `full_model_np` - Full model (non-parametric)
        - `residual_pm` - Residual (observed - full_model_pm)
        - `residual_np` - Residual (observed - full_model_np)
        - `all` - All components

        ## Response

        `{wave: [...], spectra: [{filename, dapver, expnum, fiberid, ra, dec, mask, components: {...}}]}`

        ## Examples

        **All components:**
        ```
        /lvm/dap/fiber/?l=id:1.2.0/43064/532;components:all
        ```

        **Specific components:**
        ```
        /lvm/dap/fiber/?l=id:1.2.0/43064/532;components:observed,stellar_continuum
        ```

        **Multiple fibers:**
        ```
        /lvm/dap/fiber/?l=id:1.2.0/43064/532;components:observed&l=id:1.2.0/43064/533;components:observed
        ```
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

    @router.get('/dap/fiber/plot/', summary='Plot LVM DAP Fiber Spectrum')
    async def plot_dap_fiber(
        self,
        l: List[str] = Query(..., description="DAP fiber definitions with plot kwargs"),
        format: str = Query('png', description="Output: png, jpg, pdf, svg", example='png'),
        width: float = Query(10.0, description="Figure width (inches)", example=10.0),
        height: float = Query(6.0, description="Figure height (inches)", example=6.0),
        dpi: int = Query(100, description="DPI", example=100),
        xlabel: str = Query('Wavelength [Å]', description="X-axis label"),
        ylabel: str = Query('Flux [10⁻¹⁷ erg/s/cm²/Å]', description="Y-axis label"),
        title: Optional[str] = Query(None, description="Plot title"),
        legend: Optional[str] = Query(None, description="Legend: short, long, component"),
        xmin: Optional[float] = Query(None, description="X-axis min"),
        xmax: Optional[float] = Query(None, description="X-axis max"),
        ymin: Optional[float] = Query(None, description="Y-axis min"),
        ymax: Optional[float] = Query(None, description="Y-axis max"),
        ypmin: float = Query(1.0, description="Y percentile min"),
        ypmax: float = Query(99.0, description="Y percentile max"),
        log: bool = Query(False, description="Log y-axis"),
        show_residual: bool = Query(False, description="Show offset residual (observed - full_model_pm)"),
        residual_scale: float = Query(3.0, description="Residual offset: min(model) - scale * rms(residual)"),
        residual_color: str = Query('#7f7f7f', description="Color for residual line"),
        residual_lw: float = Query(0.5, description="Line width for residual"),
        residual_alpha: float = Query(1.0, description="Alpha (opacity) for residual line"),
        residual_linestyle: str = Query('-', description="Line style for residual: -, --, -., :"),
        refline_color: Optional[str] = Query(None, description="Reference line color (default: same as residual)"),
        refline_lw: float = Query(0.8, description="Reference line width"),
        refline_linestyle: str = Query('--', description="Reference line style: -, --, -., :")
    ) -> StreamingResponse:
        """
        # Plot LVM DAP Fiber Spectrum

        Plots DAP components for specified fibers with optional offset residual visualization.

        ## Query Format

        `l=id:DAPversion/expnum/fiberid[;components:...][;color:red][;lw:1.5][;alpha:0.8]`

        ## Components

        - `observed` - Observed spectrum
        - `stellar_continuum` - Stellar continuum model
        - `emission_np` - Non-parametric emission lines
        - `emission_pm` - Parametric emission lines
        - `full_model_pm` - Full model (parametric)
        - `full_model_np` - Full model (non-parametric)
        - `residual_pm` - Residual (observed - full_model_pm)
        - `residual_np` - Residual (observed - full_model_np)
        - `all` - All components

        ## Styling Options

        Any matplotlib plot kwargs: `color`, `lw`, `alpha`, `linestyle`, `zorder`, etc.

        ## Legend Options

        - `short` - fiberid + component name
        - `long` - expnum + fiberid + component + dapver
        - `component` - component name only

        ## Offset Residual

        When `show_residual=true`, displays offset residual with a reference line.
        Offset: `min(model) - residual_scale × rms(residual)`

        ## Examples

        **All components:**
        ```
        /lvm/dap/fiber/plot/?l=id:1.2.0/43064/532;components:all
        ```

        **Observed vs model:**
        ```
        /lvm/dap/fiber/plot/?l=id:1.2.0/43064/532;components:observed,full_model_pm&legend=component
        ```

        **Custom colors per component:**
        ```
        /lvm/dap/fiber/plot/?l=id:1.2.0/43064/532;components:observed;color:black&l=id:1.2.0/43064/532;components:full_model_pm;color:red&legend=component
        ```

        **With offset residual:**
        ```
        /lvm/dap/fiber/plot/?l=id:1.2.0/43064/532;components:observed,full_model_pm&show_residual=true
        ```

        **PDF with axis limits:**
        ```
        /lvm/dap/fiber/plot/?l=id:1.2.0/43064/532;components:all&xmin=4000&xmax=7000&format=pdf
        ```

        **Compare fibers:**
        ```
        /lvm/dap/fiber/plot/?l=id:1.2.0/43064/532;components:observed;color:blue&l=id:1.2.0/43064/533;components:observed;color:red&legend=short
        ```
        """
        if not l:
            raise HTTPException(status_code=400, detail="'l' parameter required")

        try:
            parsed_lines = [parse_line_query_dap_fiber(line) for line in l]
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        data, wave = [], None

        for parsed in parsed_lines:
            id_parts = parsed['id'].split('/')
            dapver, expnum, fiberid = id_parts[0], int(id_parts[1]), int(id_parts[2])

            try:
                validate_fiberid(fiberid)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

            try:
                dap_file, output_file, _ = await get_DAP_filenames(expnum, dapver)
            except FileNotFoundError as e:
                raise HTTPException(status_code=404, detail=str(e))

            try:
                result = await run_in_executor(
                    extract_dap_fiber_data, dap_file, output_file, fiberid, parsed['components']
                )
            except ValueError as e:
                raise HTTPException(status_code=404, detail=str(e))

            if wave is None:
                wave = result['wave']

            # Extract plot kwargs (exclude DAP-specific keys)
            exclude_keys = {'id', 'components', 'dapver', 'expnum', 'fiberid'}
            base_plot_kwargs = {k: v for k, v in parsed.items() if k not in exclude_keys}

            # Create plot entry for each component
            for comp_name, comp_data in result['components'].items():
                plot_kwargs = base_plot_kwargs.copy()
                if 'color' not in plot_kwargs:
                    plot_kwargs['color'] = DAP_COMPONENT_COLORS.get(comp_name, '#333333')

                label = None
                if legend == 'short':
                    label = f"{fiberid} {comp_name}"
                elif legend == 'long':
                    label = f"{expnum} {fiberid} {comp_name} {dapver}"
                elif legend == 'component':
                    label = comp_name

                data.append({
                    'array': comp_data,
                    'expnum': expnum,
                    'fiberid': fiberid,
                    'dapver': dapver,
                    'component': comp_name,
                    'plot_kwargs': {'label': label, **plot_kwargs} if label else plot_kwargs
                })

        if wave is None:
            raise HTTPException(status_code=404, detail="No valid DAP data found")

        # Calculate offset residual if requested
        residual_info = None
        if show_residual:
            # Find observed and full_model_pm from the extracted data
            observed_arr = None
            model_arr = None
            for d in data:
                if d['component'] == 'observed':
                    observed_arr = d['array']
                elif d['component'] == 'full_model_pm':
                    model_arr = d['array']

            if observed_arr is not None and model_arr is not None:
                residual = observed_arr - model_arr
                rms = np.sqrt(np.nanmean(residual**2))
                model_min = np.nanmin(model_arr)
                offset_level = model_min - residual_scale * rms
                offset_residual = residual + offset_level

                residual_label = 'residual (offset)' if legend else None
                data.append({
                    'array': offset_residual,
                    'component': 'residual_offset',
                    'plot_kwargs': {
                        'color': residual_color,
                        'lw': residual_lw,
                        'alpha': residual_alpha,
                        'linestyle': residual_linestyle,
                        'label': residual_label,
                        'zorder': 1
                    }
                })
                residual_info = {
                    'offset_level': offset_level,
                    'color': refline_color or residual_color,
                    'lw': refline_lw,
                    'linestyle': refline_linestyle
                }

        try:
            fig = create_spectrum_plot(
                wave, data, width, height, xlabel, ylabel, title, legend,
                xmin, xmax, ymin, ymax, ypmin, ypmax, log
            )

            # Add horizontal reference line for residual zero level
            if residual_info is not None:
                import matplotlib.pyplot as plt
                plt.axhline(
                    y=residual_info['offset_level'],
                    color=residual_info['color'],
                    linestyle=residual_info['linestyle'],
                    lw=residual_info['lw'],
                    alpha=0.7,
                    zorder=0
                )

        except ValueError as e:
            raise HTTPException(status_code=500, detail=str(e))

        return figure_response(fig, format, dpi)

    @router.get('/dap/lines/', summary='Get LVM DAP Emission Line Fluxes')
    async def get_dap_lines(
        self,
        expnum: Annotated[int, Query(description="Exposure number", example=43064)],
        dapver: Annotated[str, Query(description='DAP version (e.g., 1.2.0, 1.1.1)', example='1.2.0')] = '1.2.0',
        wl: str = Query('6562.85,4861.36', description='Emission lines (wavelengths)', example='6562.85,4861.36'),
    ):
        """
        # Get LVM DAP Emission Line Fluxes

        Extracts emission line fluxes from DAP files for all fibers.
        Uses lookup table to resolve file path from expnum and DAP version.

        ## Query Parameters

        - `expnum` - Exposure number
        - `dapver` - DAP version (default: 1.2.0)
        - `wl` - Comma-separated emission line wavelengths (Å)

        ## Response

        `{filename: "...", dapver: "...", expnum: ..., fiberid: [...], "6562.85": [...], "4861.36": [...]}`

        ## Examples

        **H-alpha and H-beta:**
        ```
        /lvm/dap/lines/?expnum=43064&wl=6562.85,4861.36
        ```

        **Multiple lines:**
        ```
        /lvm/dap/lines/?expnum=43064&wl=6562.85,4861.36,5007.0,4959.0
        ```

        **Specific DAP version:**
        ```
        /lvm/dap/lines/?expnum=43064&wl=6562.85&dapver=1.1.1
        ```
        """
        try:
            dap_file, _, relative_path = await get_DAP_filenames(expnum, dapver)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except IndexError:
            raise HTTPException(status_code=404, detail=f"Exposure {expnum} not found in drpall")

        def read_fluxes():
            dap_pm = fits.getdata(dap_file, 'PM_ELINES')
            df = pd.DataFrame({
                'id': np.array(dap_pm['id']).byteswap().newbyteorder(),
                'wl': np.array(dap_pm['wl']).byteswap().newbyteorder(),
                'flux': np.array(dap_pm['flux']).byteswap().newbyteorder()
            })
            df['fiberid'] = df['id'].str.split('.').str[1].astype(int)

            wlist = [float(w) for w in wl.split(',')]
            df_sub = df[df['wl'].isin(wlist)]
            df_pivot = df_sub.pivot(index='fiberid', columns='wl', values='flux').reset_index()

            output = {
                'filename': relative_path,
                'dapver': dapver,
                'expnum': expnum,
                'fiberid': df_pivot['fiberid'].tolist()
            }
            for w in wlist:
                output[f"{w}"] = df_pivot[w].tolist()
            return output

        return await run_in_executor(read_fluxes)
