# !/usr/bin/env python
# -*- coding: utf-8 -*-
#

# all resuable queries go here

from typing import Union
import peewee
import astropy.units as u
from astropy.coordinates import SkyCoord
from sdssdb.peewee.sdss5db import vizdb
from sdssdb.peewee.sdss5db import targetdb


def append_pipes(query: peewee.ModelSelect, table: str = 'stacked') -> peewee.ModelSelect:
    """ Joins a query to the SDSSidToPipes table

    Joines an existing query to the SDSSidToPipes table and returns
    the in_boss, in_apogee, and in_astra columns. The table kwarg
    is used inform which table you are joining from/to, either the
    vizdb.SDSSidStacked or vizdb.SDSSidFlat table. Assumes the input query is
    a select from one of those two.

    Parameters
    ----------
    query : peewee.ModelSelect
        the input query to join to
    table : str, optional
        the type of sdss_id table joining to, by default 'stacked'

    Returns
    -------
    peewee.ModelSelect
        the output query

    Raises
    ------
    ValueError
        when table kwarg does not match allowed values
    """
    if table not in {'stacked', 'flat'}:
        raise ValueError('table must be either "stacked" or "flat"')

    model = vizdb.SDSSidStacked if table == 'stacked' else vizdb.SDSSidFlat
    return query.select_extend(vizdb.SDSSidToPipes.in_boss,
                               vizdb.SDSSidToPipes.in_apogee,
                               vizdb.SDSSidToPipes.in_astra).\
        join(vizdb.SDSSidToPipes, on=(model.sdss_id == vizdb.SDSSidToPipes.sdss_id),
             attr='pipes')


def convert_coords(ra: Union[str, float], dec: Union[str, float]) -> tuple:
    """ Convert sky coordinates to decimal degrees

    Convert the input RA, Dec sky coordinates into decimal
    degrees. Input format can either be decimal or hmsdms.

    Parameters
    ----------
    ra : str
        The Right Ascension
    dec : str
        The Declination

    Returns
    -------
    tuple
        the converted (RA, Dec)
    """
    is_hms = set('hms: ') & set(str(ra))
    if is_hms:
        ra = str(ra).replace(' ', ':')
        dec = str(dec).replace(' ', ':')
        unit = ('hourangle', 'degree') if is_hms else ('degree', 'degree')
        coord = SkyCoord(f'{ra} {dec}', unit=unit)
        ra = round(coord.ra.value, 5)
        dec = round(coord.dec.value, 5)
    return float(ra), float(dec)


def cone_search(ra: Union[str, float], dec: Union[str, float],
                radius: float, units: str = 'degree') -> peewee.ModelSelect:
    """ Perform a cone search against the vizdb sdss_id_stacked table

    Perform a cone search using the peewee ORM for SDSS targets in the
    vizdb sdss_id_stacked table.  We return the peewee ModelSelect
    directly here so it can be easily combined with other queries.

    In the route endpoint itself, remember to return wrap this in a list.

    Parameters
    ----------
    ra : Union[str, float]
        the Right Ascension coord
    dec : Union[str, float]
        the Declination coord
    radius : float
        the cone search radius
    units : str, optional
        the units of the search radius, by default 'degree'

    Returns
    -------
    peewee.ModelSelect
        the ORM query
    """

    # convert ra, dec to decimal if in hms-dms
    ra, dec = convert_coords(ra, dec)

    # convert radial units to degrees
    radius *= u.Unit(units)
    radius = radius.to(u.degree).value

    return vizdb.SDSSidStacked.select().\
        where(vizdb.SDSSidStacked.cone_search(ra, dec, radius,
                                              ra_col='ra_sdss_id',
                                              dec_col='dec_sdss_id'))


def carton_program_list(name_type: str) -> peewee.ModelSelect:
    """
    Return a list of either all cartons or programs from targetdb

    Parameters
    ----------
    name_type: str
        Which type you are searching on, either 'carton' or 'program'

    Returns
    -------
    list
        list of either all cartons in programs sorted in alphabetical order
    """
    model_list = sorted(targetdb.Carton.select(getattr(targetdb.Carton, name_type)).distinct().scalars())
    return model_list


def carton_program_search(name: str, name_type: str) -> peewee.ModelSelect:
    """
    Perform a search on either carton or program

    Parameters
    ----------
    name: str
        Either the carton name or the program name
    name_type: str
        Which type you are searching on, either 'carton' or 'program'

    Returns
    -------
    peewee.ModelSelect
        the ORM query
    """
    model = vizdb.SDSSidFlat.select(peewee.fn.DISTINCT(vizdb.SDSSidFlat.sdss_id))\
                            .join(targetdb.Target,
                                  on=(targetdb.Target.catalogid == vizdb.SDSSidFlat.catalogid))\
                            .join(targetdb.CartonToTarget)\
                            .join(targetdb.Carton)\
                            .where(getattr(targetdb.Carton, name_type) == name)
    model_stack = vizdb.SDSSidStacked.select()\
                                     .join(model, on=(model.c.sdss_id == vizdb.SDSSidStacked.sdss_id))
    return model_stack
