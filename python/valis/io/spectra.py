# !/usr/bin/env python
# -*- coding: utf-8 -*-
#

import pathlib
import json
from functools import lru_cache
from typing import Union

import astropy.units as u
from astropy.io import fits
from astropy.nddata import InverseVariance
from astropy.wcs import WCS
import numpy as np

try:
    from specutils import Spectrum1D
except ImportError:
    Spectrum1D = None

# TODO - the models json should really be in the datamodel product


@lru_cache
def read_model_json() -> dict:
    """ Read the spectrum model JSON file """
    with open(pathlib.Path(__file__).parent / 'model_spectra_info.json') as f:
        return json.loads(f.read())


def get_product_model(product: str) -> dict:
    """ Get the product spectrum model

    Get the spectrum datamodel for the given product

    Parameters
    ----------
    product : str
        the name of the data product

    Returns
    -------
    dict
        the data model
    """
    data = read_model_json()
    prod = [i for i in data if i['product'] == product or product in i['aliases']]
    return prod[0] if prod else None


def extract_data(product: str, filepath: str, multispec: Union[int, str] = None) -> dict:
    """ Extract spectral data from a file

    Extract the spectral data for a given data product
    from the input filepath.  Uses the product datamodel to
    identify where in the file the relevant spectral information
    lives.  Extracts header, flux, error, mask and wavelength.

    If multispec provided, extracts the spectral information from that
    extension.  Currently assumes the same parameters for each extension,
    see the mwmStar file.

    Parameters
    ----------
    product : str
        the name of the data product
    filepath : str
        the filepath to open
    multispec : int | str
        the name or number of the extension in a multi-spectral extension file

    Returns
    -------
    dict
        the output spectrum information
    """
    # get the spectrum model
    prod = get_product_model(product)

    # extract the spectral data using the lookup model
    data = {}
    with fits.open(filepath) as hdulist:
        # get the header, remove keys delineating header groups
        data['header'] = {k: v for k, v in hdulist['PRIMARY'].header.items() if k}
        for param, info in prod["parameters"].items():
            extension = multispec or info['extension']
            if info["type"] == "table":
                # get the table data
                vals = hdulist[extension].data[info["column"]]

                # convert loglam wavelengths
                if info['column'] == 'LOGLAM':
                    vals = 10 ** vals

                data[param] = vals
            elif info["type"] == "wcs":
                wcs = WCS(data['header'])
                vals = wcs.array_index_to_world(range(info["nwave"]))

                # convert loglam wavelengths
                if info['column'] == "LOGLAM":
                    vals = 10 ** vals

                # convert quantity to array
                if isinstance(vals, u.Quantity):
                    vals = vals.value

                data[param] = vals
            else:
                data[param] = hdulist[extension].data

        # set dtype byteorder to the native
        for key, val in data.items():
            if key == 'header':
                continue
            data[key] = val.byteswap().newbyteorder('=')

        return data


# example for Spectrum1D serializer
# Flux = Annotated[list, BeforeValidator(lambda v: v.value)]
# Wave = Annotated[list, BeforeValidator(lambda v: v.value)]
# Uncer = Annotated[list, BeforeValidator(lambda v: v.array)]

# class Spec1DModel(BaseModel):
#     """ Pydantic model for serializing Spectrum1D objects """
#     model_config = ConfigDict(from_attributes=True)
#     meta: dict = Field(repr=False)
#     name: Optional[str] = Field(None, description='name', validate_default=True)
#     flux: Flux = Field(repr=False)
#     wavelength: Wave = Field(repr=False)
#     uncertainty: Uncer = Field(repr=False)
#     mask: list = Field(repr=False)

#     @field_validator('name')
#     @classmethod
#     def f(cls, v: str, info):
#         return info.data['meta'].get('name')

# import astropy.units as u
# from astropy.nddata import InverseVariance
# from specutils import Spectrum1D
# fu = u.Unit("1e-17 * erg / (s * cm**2 * Angstrom)")
# s = Spectrum1D(flux=e['flux']*fu, spectral_axis=e['wavelength']*u.Angstrom, mask=e['mask'],
#                uncertainty=InverseVariance(e['error']), meta={'header': e['header']})
# ss = Spec1DModel.model_validate(s)


def create_spectrum1d(specdata: dict, product: str, filename: str) -> Spectrum1D:
    """ Create a Spectrum1D object

    Create a ``specutils.Spectrum1D`` object from the extracted spectral
    data.

    Parameters
    ----------
    specdata : dict
        the extracted spectral data
    product : str
        the data product name
    filename : str
        the filepath on disk

    Returns
    -------
    Spectrum1D
        the spectrum object

    Raises
    ------
    ImportError
        when specutils is not installed
    KeyError
        when there are no flux units in the datamodel
    """
    if not Spectrum1D:
        raise ImportError('specutils package is not installed.')

    name = pathlib.Path(filename).stem
    prod = get_product_model(product)

    # get the valid units from the datamodel
    fu = prod['parameters']['flux'].get('units')
    wu = prod['parameters']['wavelength'].get('units', 'Angstroms')
    if not fu:
        raise KeyError(f'spectrum datamodel for {product} does not have specified flux units.')
    flux_unit = u.Unit(fu)
    wave_unit = u.Unit(wu)

    # create the spectrum1D object
    return Spectrum1D(flux=specdata['flux'] * flux_unit,
                      spectral_axis=specdata['wavelength'] * wave_unit,
                      mask=specdata['mask'] != 0,
                      uncertainty=InverseVariance(specdata['error']),
                      meta={'header': specdata['header'], 'name': name})
