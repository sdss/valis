# !/usr/bin/env python
# -*- coding: utf-8 -*-
#

# all resuable queries go here

from typing import Union
import peewee
import astropy.units as u
from astropy.coordinates import SkyCoord
from sdssdb.peewee.sdss5db import vizdb, boss_drp as boss

from valis.utils.versions import get_software_tag
from valis.utils.paths import build_boss_path
from valis.io.spectra import extract_data


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


def get_pipes(sdss_id: int) -> peewee.ModelSelect:
    return vizdb.SDSSidToPipes.select().\
        where(vizdb.SDSSidToPipes.sdss_id == sdss_id).\
        distinct(vizdb.SDSSidToPipes.sdss_id)


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


# test sdss ids
# 23326 - boss/astra
# 3350466 - apogee/astra
# 54392544 - all true
# 10 - all false
# 57651832 - my file on disk
# 57832526 - all true, in both astra snow_white, apogee_net (source_pk=912174,star_pk=2954029)


# def get_target_info(sdss_id: int, release: str, fields: list = None):

#     pipes = get_pipes(sdss_id).dicts().first()
#     if pipes['in_boss']:
#         query = get_boss_target(sdss_id, release, fields=fields)

#     if pipes['in_astra']:
#         pass

#     if pipes['in_apogee']:
#         pass

#     return query


def get_boss_target(sdss_id: int, release: str, fields: list = None,
                    primary: bool = True) -> peewee.ModelSelect:
    """_summary_

    _extended_summary_

    Parameters
    ----------
    sdss_id : int
        _description_
    release : str
        _description_
    fields : list, optional
        _description_, by default None

    Returns
    -------
    peewee.ModelSelect
        _description_
    """
    # get the relevant software tag
    run2d = get_software_tag(release, 'run2d')

    # check fields
    fields = fields or []
    if fields and isinstance(fields[0], str):
        fields = (getattr(boss.BossSpectrum, i) for i in fields)

    # query for the target
    query = boss.BossSpectrum.select(*fields).\
        where(boss.BossSpectrum.sdss_id == sdss_id,
              boss.BossSpectrum.run2d == run2d)

    # filter on primary
    if primary:
        query = query.where(boss.BossSpectrum.specprimary == 1)

    return query


# def get_target():
#     get_pipes()
#     get_boss_target()
#     get_boss_target()
#     get_boss_target()
#     #In [94]: q.select(q.star, q2.star).join(q2, on=(q.c.sdss_id==q2.c.sdss_id)).with_cte(q,q2).execute()
#     return answer


def get_a_spectrum(sdss_id: int, product: str, release: str):
    # missing - query vizdb table to get sdss_id pipelines info
    # missing - query to get apogee, astra target info
    query = get_boss_target(sdss_id, release)
    for row in query.dicts().iterator():
        filepath = build_boss_path(row, release)
        try:
            yield extract_data(product, filepath)
        except FileNotFoundError:
            yield None


