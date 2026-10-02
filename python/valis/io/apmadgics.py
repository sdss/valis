

import h5py
import numpy as np

from functools import lru_cache

from astropy.io import fits
from astropy.wcs import WCS
from astropy.table import Table
from valis.utils.paths import build_file_path


def _allvisit_path(star_prior: str, vers: str, release: str) -> str:
    """Get the file path for the allVisit apMADGICS file.

    Parameters
    ----------
    star_prior : str
        the star_prior type, either 'dd' or 'th'
    vers : str
        the version of the allVisit apMADGICS file
    release : str
        the data release, e.g., 'DR19'

    Returns
    -------
    str
        the allVisit apMADGICS file path

    Raises
    ------
    FileNotFoundError
        when the file could not be found
    """
    path = build_file_path({"star_prior_type": star_prior, "vers": vers}, "allVisit_MADGICS", release)
    if not path:
        raise FileNotFoundError(f"The allVisit_apMADGICS file for star_prior={star_prior} could not be found.")
    return path


def _read_columns(path: str, select=None) -> dict[str, np.ndarray]:
    """Read columns from the allVisit apMADGICS file

    Reads the specified columns from the allVisit file and
    returns them as native-endian numpy arrays.

    Parameters
    ----------
    path : str
        the path to the allVisit file
    select : callable, optional
        a function to select which columns to read, by default None

    Returns
    -------
    dict[str, np.ndarray]
        a dictionary mapping column names to numpy arrays
    """
    with fits.open(path, memmap=True) as hdulist:
        data = hdulist[1].data
        out = {}
        #rv_cols = ['rv_bary', 'rv_flag', 'rv_verr_sys']
        cols = ['sdss_id', 'map2madgics', 'mjd', 'plate', 'fiberid', 'field', 'telescope', 'apogee_id', 'gaiaedr3_source_id',
                   'cartVisit', 'ra', 'dec', 'glon', 'glat', 'rv_bary', 'rv_flag', 'rv_verr_sys']
        lnames = list(map(str.lower, data.columns.names))
        for name in (n.lower() for n in cols if n in lnames):
            if select and not select(name):
                continue
            arr = np.asarray(data[name]).ravel()
            # astype copies, so the arrays stay valid after the memmapped file closes
            out[name] = arr.astype(arr.dtype.newbyteorder("="))
        return out


@lru_cache
def get_merged_allvisit(vers: str = "v2024_03_16", release: str = "DR19"):
    """Get the merged allVisit apMADGICS table.

    Return a merged version of the allVisit file with the subset of
    metadata + RV columns from the dd star_prior and the RV columns
    from the th star_prior.  Appends the star_prior name (dd/th) to the
    RV columns in the merged table.

    Parameters
    ----------
    vers : str, optional
        the version of the allVisit apMADGICS data, by default "v2024_03_16"
    release : str, optional
        the data release, by default "DR19"

    Returns
    -------
    astropy.table.Table
        the merged table
    """
    dd = _read_columns(_allvisit_path('dd', vers, release))
    th = _read_columns(_allvisit_path('th', vers, release),
                       select=lambda n: n.startswith("rv_") or n == "map2madgics")

    # suffix RV columns by star_prior
    data = {}
    for name, arr in dd.items():
        data[f"{name}_dd" if name.startswith("rv_") else name] = arr
    for name, arr in th.items():
        if name.startswith("rv_"):
            data[f"{name}_th"] = arr

    tt = Table(data, names=list(data.keys()))
    tt.add_index('sdss_id')
    return tt


def get_madgic_rows(sdss_id: int, vers: str = 'v2024_03_16', release: str = 'DR19') -> Table:
    """Get the rows from the allVisit for a given sdss_id

    Retrieves the rows from the apMADGICS allVisit table for a given sdss_id.

    Parameters
    ----------
    sdss_id : int
        the sdss_id of the target
    vers : str, optional
        the version of the data, by default 'v2024_03_16'
    release : str, optional
        the data release, by default 'DR19'

    Returns
    -------
    astropy.table.Row or astropy.table.Table
        the row(s) corresponding to the given sdss_id

    Raises
    ------
    ValueError
        when the sdss_id is not found in the visit table
    """
    visit_table = get_merged_allvisit(vers=vers, release=release)
    sdss_in_table = sdss_id in visit_table['sdss_id']
    if not sdss_in_table:
        raise ValueError(f"SDSS ID {sdss_id} not found in the visit table.")
    return visit_table.loc[[sdss_id]]


@lru_cache
def get_madgic_wavelength() -> np.ndarray:
    """Build the apMADGICS wavelength array.

    Constructs the wavelength array for the apMADGICS spectra
    based on the WCS header information.

    Returns
    -------
    np.ndarray
        the wavelength array in Angstroms
    """
    n_wave = 8700
    hdr = {'CTYPE1': 'WAVE-LOG',
            'CUNIT1': 'Angstrom',
            'CRVAL1': 15074.74588598709,
            'CDELT1': 0.20826531094648318,
            'NAXIS1': n_wave,
            'CRPIX1': 1,
            'PC1_1': 1.0,
            'RESTWAV': 15074.74588598709}
    wcs = WCS(header=hdr)
    return wcs.pixel_to_world(np.arange(n_wave)).to('Angstrom').value


def get_madgic_index(sdss_id: int, mjd: int = None, plate: int = None, fiberid: int = None,
                     vers: str = 'v2024_03_16', release: str = 'DR19') -> int:
    """Get the index of the apMADGICS row for a given SDSS ID.

    Retrieves the index of the row in the apMADGICS allVisit table
    corresponding to the specified SDSS ID and optional observation parameters.
    The same index can be used in both the dd and th allVisit files.

    Parameters
    ----------
    sdss_id : int
        the SDSS ID of the target
    mjd : int, optional
        the MJD of the observation, by default None
    plate : int, optional
        the plate number of the observation, by default None
    fiberid : int, optional
        the fiber ID of the observation, by default None
    vers : str, optional
        the version of the data, by default 'v2024_03_16'
    release : str, optional
        the data release, by default 'DR19'

    Returns
    -------
    int
        the index of the row in the apMADGICS allVisit table

    Raises
    ------
    ValueError
        when the row for the given SDSS ID and criteria cannot be uniquely identified
    """
    # lookup the index
    rows = get_madgic_rows(sdss_id, vers=vers, release=release)

    if len(rows) == 1:
        idx = rows['map2madgics'].value[0]
    else:
        cond = None
        if mjd:
            cond = (rows['mjd']==mjd)
        if plate:
            cond = cond & (rows['plate']==plate) if cond is not None else (rows['plate']==plate)
        if fiberid:
            cond = cond & (rows['fiberid']==fiberid) if cond is not None else (rows['fiberid']==fiberid)
        if cond is not None:
            rows = rows[cond]
        if len(rows) == 1:
            idx = rows['map2madgics'].value[0]
        else:
            raise ValueError(f"Could not uniquely identify the row for SDSS ID {sdss_id} with the given criteria.")

    return idx


def get_madgic_spectrum(sdss_id: int = None, mjd: int = None, plate: int = None, fiberid: int = None,
                        magicid: int = None,
                        star_prior: str = 'dd', vers: str = 'v2024_03_16', release: str = 'DR19') -> dict:
    """Get the apMADGICS spectrum for a given SDSS ID and optional observation parameters.

    Retrieves the spectrum for the specified SDSS ID and optional observation parameters from the apMADGICS_apVisit HDF5 file.

    Parameters
    ----------
    sdss_id : int, optional
        the SDSS ID of the target, by default None
    mjd : int, optional
        the MJD of the observation, by default None
    plate : int, optional
        the plate number of the observation, by default None
    fiberid : int, optional
        the fiber ID of the observation, by default None
    magicid : int, optional
        the index of the row in the apMADGICS allVisit table, by default None
    star_prior : str, optional
        the star prior type, either 'dd' or 'th', by default 'dd'
    vers : str, optional
        the version of the data, by default 'v2024_03_16'
    release : str, optional
        the data release, by default 'DR19'

    Returns
    -------
    dict
        A dictionary containing the spectrum flux and wavelength, along with their units.

    Raises
    ------
    FileNotFoundError
        when the apMADGICS spectral file could not be found
    """

    path = build_file_path({'star_prior_type': star_prior, 'vers': vers}, 'apMADGICS_out_apVisit_v0', release)

    if not path:
        raise FileNotFoundError("The apMADGICS_out_apVisit_v0 file could not be found.")

    if not magicid:
        magicid = get_madgic_index(sdss_id, mjd=mjd, plate=plate, fiberid=fiberid,
                                    vers=vers, release=release)

    # create the output
    data = {"wavelength": get_madgic_wavelength(),
            "unit_wavelength": "Angstrom",
            "unit_flux": "1e-17 erg / (Angstrom cm2 s)"}

    # read the spectrum
    with h5py.File(path, "r") as hh:
        dd = hh["apVisit_v0"]

        # it is 1-indexed in the allVisit
        data["flux"] = dd[magicid - 1]
        return data
