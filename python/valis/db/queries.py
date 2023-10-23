# !/usr/bin/env python
# -*- coding: utf-8 -*-
#

# all resuable queries go here

import astropy.units as u
from sdssdb.peewee.sdss5db import vizdb


def cone_search(ra: float, dec: float, radius: float, units: str = 'degree'):
    """ Perform a cone search against the vizdb sdss_id_stacked table

    Perform a cone search using the peewee ORM for SDSS targets in the
    vizdb sdss_id_stacked table.  We return the peewee ModelSelect
    directly here so it can be easily combined with other queries.

    In the route endpoint itself, remember to return wrap this in a list.
    """

    # convert radial units to degrees
    radius *= u.Unit(units)
    radius = radius.to(u.degree).value

    return vizdb.SDSSidStacked.select().\
        where(vizdb.SDSSidStacked.cone_search(ra, dec, radius,
                                              ra_col='ra_sdss_id',
                                              dec_col='dec_sdss_id'))
