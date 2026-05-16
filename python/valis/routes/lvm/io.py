"""
Path resolution and async file I/O for LVM routes.

Public interface: LVMBase (used as a base class by endpoint CBVs).
Endpoints call: self.get_drpall_record / self.get_sframe_filename /
                self.get_dap_filenames / self.file_exists / self.run_sync.

LVMBase delegates to module-private free functions, injecting self.tree
and self.path (sdss_access objects supplied by valis.routes.base.Base).

Path resolution runs in 3 tiers (first match wins):
  1. sdss_access named path  -- path.full('lvm_frame', ...)
  2. env var from tree dict  -- LVM_SPECTRO_REDUX / LVM_SPECTRO_ANALYSIS
  3. hardcoded sdsswork path -- SAS_BASE_DIR + known directory layout

DR20 tree (4.1.2+) registers: lvm_drpall, lvm_sframe, lvm_frame, lvm_dap,
lvm_lv_dap, lvm_dapall, LVM_SPECTRO_ANALYSIS.
DR19 registers: lvm_sframe, lvm_frame, LVM_SPECTRO_REDUX.
Tier 1 activates automatically when the tree registers a new name.
"""
from __future__ import annotations

import os
import asyncio
from typing import Any, Dict, List, Optional, Tuple

from astropy.io import fits

from valis.routes.base import Base

from .common import LAST_DRP_VERSION


# --- Path resolver helpers (module-private) ----------------------------------

_SDSS_SAS_DEFAULT = '/data/sdss/sas'

# Hardcoded sdsswork layout used as last-resort tier 3 when tree/env lookup fails
# (DR19 tree omits LVM_SPECTRO_ANALYSIS; test fixtures provide only SAS_BASE_DIR).
_SDSSWORK_SUBPATHS = {
    'LVM_SPECTRO_REDUX': 'sdsswork/lvm/spectro/redux',
    'LVM_SPECTRO_ANALYSIS': 'sdsswork/lvm/spectro/analysis',
}


def _is_sdss_access_path(path_obj) -> bool:
    return path_obj.__class__.__module__.startswith('sdss_access')


def _path_bound_to_own_release(path_obj):
    """Return a fresh sdss_access Path for the release carried by path_obj.

    sdss_access keeps some tree state globally. If the same process creates
    Path objects for different releases, an older Path can resolve with the
    newer release. Recreating it here makes the release explicit at resolution.
    """
    release = getattr(path_obj, 'release', None)
    if not release or not _is_sdss_access_path(path_obj):
        return path_obj
    try:
        return path_obj.__class__(release=release)
    except Exception:
        return path_obj


def _resolve_named_path(path_obj, name: str, **kwargs) -> Optional[str]:
    """Return a registered sdss_access path, or None if it cannot resolve."""
    if path_obj is None:
        return None
    path_obj = _path_bound_to_own_release(path_obj)
    try:
        if name not in path_obj.lookup_names():
            return None
        return path_obj.full(name, **kwargs)
    except Exception:
        return None


def _resolve_env(tree, env: str) -> str:
    """Resolve SDSS env var: tree dict first, then SAS_BASE_DIR + hardcoded layout.
    The hardcoded fallback covers DR19 (no LVM_SPECTRO_ANALYSIS) and test fixtures
    that set only SAS_BASE_DIR."""
    d = tree.to_dict() if tree is not None else {}
    if env in d:
        return d[env]
    sas = d.get('SAS_BASE_DIR') or os.getenv('SAS_BASE_DIR', _SDSS_SAS_DEFAULT)
    return f"{sas}/{_SDSSWORK_SUBPATHS[env]}"


def _tile_prefix(tile_id: int) -> str:
    return f"{str(tile_id)[:4]}XX" if tile_id != 11111 else "0011XX"


def _drpall_path(drpver: str, tree=None, path=None) -> str:
    """Resolve drpall-{drpver}.fits path."""
    named = _resolve_named_path(path, 'lvm_drpall', drpver=drpver)
    if named:
        return named
    # tier 2/3 fallback
    return f"{_resolve_env(tree, 'LVM_SPECTRO_REDUX')}/{drpver}/drpall-{drpver}.fits"


def _sframe_path(drpver: str, tile_id: int, mjd: int, expnum: int, tree=None, path=None) -> str:
    """Resolve lvmSFrame path. `lvm_frame` (with kind=SFrame) is registered
    in sdsswork/DR19/DR20 templates, so tier 1 handles every known release."""
    named = _resolve_named_path(
        path, 'lvm_frame',
        drpver=drpver, tileid=tile_id, mjd=mjd, expnum=expnum, kind='SFrame',
    )
    if named:
        return named
    # tier 2/3 fallback
    prefix = _tile_prefix(tile_id)
    suffix = str(expnum).zfill(8)
    return f"{_resolve_env(tree, 'LVM_SPECTRO_REDUX')}/{drpver}/{prefix}/{tile_id}/{mjd}/lvmSFrame-{suffix}.fits"


def _is_work_release(tree=None, path=None) -> bool:
    if tree is None and path is None:
        return True
    release = str(getattr(path, 'release', '') or '').lower()
    config = str(getattr(tree, 'config_name', '') or '').lower()
    return release in {'work', 'sdsswork', 'sdss5', 'sdss4'} or config in {'work', 'sdsswork', 'sdss5', 'sdss4'}


def _drpver_from_dapver(dapver: str) -> str:
    """Infer the DRP version from a DAP build version when not provided."""
    parts = dapver.split('.')
    return '.'.join(parts[:3]) if len(parts) > 3 else dapver


def _normalise_lvm_dap_versions(drpver: str, dapver: str, tree=None, path=None) -> Tuple[str, str]:
    """Return versions as expected by the sdss_access lvm_dap template.

    WORK stores DAP products under one version directory. DR20 stores them
    under DRP version / DAP build version.
    """
    if _is_work_release(tree=tree, path=path) and dapver == drpver:
        return drpver, ''
    return drpver, dapver


def _append_unique(items: List[str], value: Optional[str]) -> None:
    if value and value not in items:
        items.append(value)


def _dap_build_versions(drpver: str, dapver: str, tree=None, path=None) -> List[str]:
    versions = [_normalise_lvm_dap_versions(drpver, dapver, tree=tree, path=path)[1]]
    if _is_work_release(tree=tree, path=path) or dapver != drpver:
        return versions

    root = f"{_resolve_env(tree, 'LVM_SPECTRO_ANALYSIS')}/{drpver}"
    try:
        for name in sorted(os.listdir(root)):
            full = f"{root}/{name}"
            if os.path.isdir(full) and name.startswith(f"{drpver}."):
                _append_unique(versions, name)
    except OSError:
        pass
    return versions


def _manual_dap_file_path(drpver: str, dapver: str, tile_id: int, mjd: int, expnum: int,
                          daptype: str, tree=None,
                          rspid: str = 'rsp108', snlevel: str = 'sn20',
                          lv: bool = False) -> str:
    prefix = _tile_prefix(tile_id)
    suffix = str(expnum).zfill(8)
    base = _resolve_env(tree, 'LVM_SPECTRO_ANALYSIS')
    version_path = f"{drpver}/{dapver}" if dapver else drpver
    name_prefix = 'LV_dap' if lv else 'dap'
    return f"{base}/{version_path}/{prefix}/{tile_id}/{mjd}/{suffix}/{name_prefix}-{rspid}-{snlevel}-{suffix}.{daptype}.fits"


def _dap_file_path_candidates(drpver: str, dapver: str, tile_id: int, mjd: int, expnum: int,
                              daptype: str, tree=None, path=None,
                              rspid: str = 'rsp108', snlevel: str = 'sn20',
                              lv: bool = False) -> List[str]:
    """Resolve DAP exposure-level product path candidates.

    Prefer sdss_access `lvm_dap` (or `lvm_lv_dap` when `lv=True`); keep a manual
    fallback for older trees/tests. Caller probes .fits vs .fits.gz afterwards.
    """
    template_name = 'lvm_lv_dap' if lv else 'lvm_dap'
    candidates: List[str] = []
    for build_ver in _dap_build_versions(drpver, dapver, tree=tree, path=path):
        named = _resolve_named_path(
            path, template_name,
            drpver=drpver, dapver=build_ver, tileid=tile_id, mjd=mjd,
            expnum=expnum, rspid=rspid, snlevel=snlevel, daptype=daptype,
        )
        _append_unique(candidates, named)
        # manual fallback for older trees / test fixtures
        _append_unique(
            candidates,
            _manual_dap_file_path(drpver, build_ver, tile_id, mjd, expnum, daptype, tree=tree,
                                  rspid=rspid, snlevel=snlevel, lv=lv)
        )
    return candidates


def _dap_file_path(drpver: str, dapver: str, tile_id: int, mjd: int, expnum: int,
                   daptype: str, tree=None, path=None,
                   rspid: str = 'rsp108', snlevel: str = 'sn20',
                   lv: bool = False) -> str:
    """Resolve the primary DAP exposure-level product path."""
    return _dap_file_path_candidates(
        drpver, dapver, tile_id, mjd, expnum, daptype, tree=tree, path=path,
        rspid=rspid, snlevel=snlevel, lv=lv,
    )[0]


# --- Async I/O (module-private) ---------------------------------------------


async def _file_exists(path_str: str) -> bool:
    return await asyncio.get_event_loop().run_in_executor(None, os.path.exists, path_str)


async def _get_drpall_record(expnum: int, drpver: str, tree=None, path=None) -> Dict[str, Any]:
    """Read drpall record for an exposure; falls back to LAST_DRP_VERSION."""
    target = _drpall_path(drpver, tree=tree, path=path)
    if not await _file_exists(target):
        target = _drpall_path(LAST_DRP_VERSION, tree=tree, path=path)
        if not await _file_exists(target):
            raise FileNotFoundError(f"DRPall file not found: {target}")

    def _read():
        rows = fits.getdata(target)
        rec = rows[rows['EXPNUM'] == expnum][0]
        return {name: rec[name] for name in rows.names}

    return await asyncio.get_event_loop().run_in_executor(None, _read)


async def _get_sframe_filename(expnum: int, drpver: str, tree=None, path=None) -> str:
    """Resolve DRP lvmSFrame path. Uses tile_id/mjd from drpall record."""
    rec = await _get_drpall_record(expnum, drpver, tree=tree, path=path)
    return _sframe_path(drpver, int(rec['tileid']), int(rec['mjd']), expnum, tree=tree, path=path)


async def _find_dap_file(drpver: str, dapver: str, tile_id: int, mjd: int, expnum: int,
                         daptype: str, tree=None, path=None, lv: bool = False) -> str:
    checked = []
    for base in _dap_file_path_candidates(drpver, dapver, tile_id, mjd, expnum, daptype,
                                          tree=tree, path=path, lv=lv):
        if await _file_exists(base):
            return base
        gz = f"{base}.gz"
        if await _file_exists(gz):
            return gz
        checked.extend([base, gz])
    if len(checked) == 2:
        raise FileNotFoundError(f"Neither {checked[0]} nor {checked[1]} exists")
    raise FileNotFoundError(f"None of these files exist: {', '.join(checked)}")


def _relative_to_sas(file_path: str, tree=None) -> str:
    d = tree.to_dict() if tree is not None else {}
    sas = d.get('SAS_BASE_DIR') or os.getenv('SAS_BASE_DIR', _SDSS_SAS_DEFAULT)
    return file_path.replace(f"{sas}/", "")


async def _get_dap_filename(expnum: int, dapver: str, daptype: str,
                            drpver: Optional[str] = None, tree=None, path=None,
                            lv: bool = False) -> Tuple[str, str]:
    """
    Resolve a single DAP file. Returns (file, relative_path).
    Probes .fits first, falls back to .fits.gz. When `lv=True`, resolves the
    LV_dap-* sibling product (sdss_access template `lvm_lv_dap`).
    """
    drpver = drpver or _drpver_from_dapver(dapver)
    rec = await _get_drpall_record(expnum, drpver, tree=tree, path=path)
    file_path = await _find_dap_file(
        drpver, dapver, int(rec['tileid']), int(rec['mjd']), expnum, daptype,
        tree=tree, path=path, lv=lv,
    )
    return file_path, _relative_to_sas(file_path, tree=tree)


async def _get_dap_filenames(expnum: int, dapver: str, drpver: Optional[str] = None,
                             tree=None, path=None, lv: bool = False) -> Tuple[str, str, str]:
    """
    Resolve DAP spectra files. Returns (dap_file, model/output_file, relative_path).
    Probes model before output, and .fits before .fits.gz for each product.
    When `lv=True`, resolves the LV_dap-* variant.
    """
    dap_file, _ = await _get_dap_filename(expnum, dapver, 'dap', drpver=drpver,
                                          tree=tree, path=path, lv=lv)
    checked_errors = []
    for daptype in ('model', 'output'):
        try:
            spectra_file, relative_path = await _get_dap_filename(
                expnum, dapver, daptype, drpver=drpver, tree=tree, path=path, lv=lv,
            )
            return dap_file, spectra_file, relative_path
        except FileNotFoundError as e:
            checked_errors.append(str(e))

    raise FileNotFoundError("; ".join(checked_errors))


# --- Public interface for endpoint classes -----------------------------------


class LVMBase(Base):
    """Base class for LVM endpoint CBVs.

    Wraps module-private resolvers, binding them to the per-request
    sdss_access tree / path objects. Also exposes a generic `run_sync`
    for executing blocking I/O (FITS, pandas) in the default executor.
    """

    async def file_exists(self, p: str) -> bool:
        return await _file_exists(p)

    async def run_sync(self, func, *args):
        """Run a blocking callable in the default executor."""
        return await asyncio.get_event_loop().run_in_executor(None, func, *args)

    async def get_drpall_record(self, expnum: int, drpver: str) -> Dict[str, Any]:
        return await _get_drpall_record(expnum, drpver, tree=self.tree, path=self.path)

    async def get_sframe_filename(self, expnum: int, drpver: str) -> str:
        return await _get_sframe_filename(expnum, drpver, tree=self.tree, path=self.path)

    async def get_dap_filenames(self, expnum: int, dapver: str,
                                drpver: Optional[str] = None,
                                lv: bool = False) -> Tuple[str, str, str]:
        return await _get_dap_filenames(expnum, dapver, drpver=drpver,
                                        tree=self.tree, path=self.path, lv=lv)

    async def get_dap_filename(self, expnum: int, dapver: str, daptype: str,
                               drpver: Optional[str] = None,
                               lv: bool = False) -> Tuple[str, str]:
        return await _get_dap_filename(expnum, dapver, daptype, drpver=drpver,
                                       tree=self.tree, path=self.path, lv=lv)
