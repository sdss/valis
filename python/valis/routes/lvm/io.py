"""
I/O utilities for LVM routes: file resolution, async FITS reading
"""
from __future__ import annotations

import os
import asyncio
from typing import Dict, Any, Tuple
from astropy.io import fits

from .common import LAST_DRP_VERSION


async def get_LVM_drpall_record(expnum: int, drpver: str) -> Dict[str, Any]:
    """
    Async function to get record from drpall file for a given exposure number.
    """
    loop = asyncio.get_event_loop()
    sas_base = os.getenv('SAS_BASE_DIR', '/data/sdss/sas')

    drp_file = f"{sas_base}/sdsswork/lvm/spectro/redux/{drpver}/drpall-{drpver}.fits"

    file_exists = await loop.run_in_executor(None, os.path.exists, drp_file)
    if not file_exists:
        drp_file = f"{sas_base}/sdsswork/lvm/spectro/redux/{LAST_DRP_VERSION}/drpall-{LAST_DRP_VERSION}.fits"
        file_exists = await loop.run_in_executor(None, os.path.exists, drp_file)
        if not file_exists:
            raise FileNotFoundError(f"DRPall file not found: {drp_file}")

    def read_fits():
        drpall = fits.getdata(drp_file)
        record = drpall[drpall['EXPNUM'] == expnum][0]
        return {name: record[name] for name in drpall.names}

    return await loop.run_in_executor(None, read_fits)


async def get_SFrame_filename(expnum: int, drpver: str) -> str:
    """
    Async function to get DRP lvmSFrame filename for a given exposure number.
    """
    sas_base = os.getenv('SAS_BASE_DIR', '/data/sdss/sas')
    drp_record = await get_LVM_drpall_record(expnum, drpver)
    file = f"{sas_base}/" + drp_record['location']

    if drp_record['drpver'] != drpver:
        file = file.replace(drp_record['drpver'], drpver)

    return file


async def get_DAP_filenames(expnum: int, dapver: str) -> Tuple[str, str, str]:
    """
    Async function to get DAP filenames for a given exposure number.
    Returns: (dap_file, output_file, relative_path)
    Validates file existence and handles both .fits and .fits.gz extensions.
    """
    sas_base = os.getenv('SAS_BASE_DIR', '/data/sdss/sas')
    drp_record = await get_LVM_drpall_record(expnum, dapver)

    tile_id = int(drp_record['tileid'])
    mjd = int(drp_record['mjd'])

    suffix = str(expnum).zfill(8)
    tile_prefix = f"{str(tile_id)[:4]}XX" if tile_id != 11111 else "0011XX"

    base_path = f"{sas_base}/sdsswork/lvm/spectro/analysis/{dapver}/{tile_prefix}/{tile_id}/{mjd}/{suffix}"
    relative_base = f"sdsswork/lvm/spectro/analysis/{dapver}/{tile_prefix}/{tile_id}/{mjd}/{suffix}"

    loop = asyncio.get_event_loop()

    async def find_file(base_name: str) -> str:
        """Find file with .fits or .fits.gz extension, preferring uncompressed."""
        for ext in ['.fits', '.fits.gz']:
            filepath = f"{base_name}{ext}"
            if await loop.run_in_executor(None, os.path.exists, filepath):
                return filepath
        raise FileNotFoundError(f"Neither {base_name}.fits nor {base_name}.fits.gz exists")

    dap_file = await find_file(f"{base_path}/dap-rsp108-sn20-{suffix}.dap")
    output_file = await find_file(f"{base_path}/dap-rsp108-sn20-{suffix}.output")

    # Build relative_path matching the actual extension found
    output_ext = '.fits.gz' if output_file.endswith('.gz') else '.fits'
    relative_path = f"{relative_base}/dap-rsp108-sn20-{suffix}.output{output_ext}"

    return dap_file, output_file, relative_path


async def async_file_exists(filepath: str) -> bool:
    """Reusable async file existence check."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, os.path.exists, filepath)


async def run_in_executor(func, *args):
    """Wrapper for CPU-bound FITS operations."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, func, *args)

