# !/usr/bin/env python
# -*- coding: utf-8 -*-
#

from enum import Enum
from typing import List, Union
from fastapi import APIRouter, Depends, Query
from fastapi_utils.cbv import cbv

from valis.routes.base import Base
from valis.db.db import get_pw_db
from valis.db.models import SDSSidStackedBase
from valis.db.queries import cone_search


class SearchCoordUnits(str, Enum):
    """ Units of coordinate search radius """
    degree: str = "degree"
    arcmin: str = "arcmin"
    arcsec: str = "arcsec"


router = APIRouter()


@cbv(router)
class QueryRoutes(Base):
    """ API routes for performing queries against sdss5db """

    # @router.get('/test_sqla', summary='Perform a cone search for SDSS targets with sdss_ids',
    #             response_model=List[SDSSidStackedBaseA])
    # async def test_search(self,
    #                       ra=Query(..., description='right ascension in degrees', example=315.01417),
    #                       dec=Query(..., description='declination in degrees', example=35.299),
    #                       radius=Query(..., description='the search radius in degrees', example=0.01),
    #                       db=Depends(get_sqla_db)):
    #     """ Example for writing a route with a sqlalchemy ORM """
    #     from sdssdb.sqlalchemy.sdss5db import vizdb

    #     return db.query(vizdb.SDSSidStacked).\
    #         filter(vizdb.SDSSidStacked.cone_search(ra, dec, radius, ra_col='ra_sdss_id', dec_col='dec_sdss_id')).all()

    @router.get('/cone', summary='Perform a cone search for SDSS targets with sdss_ids',
                response_model=List[SDSSidStackedBase], dependencies=[Depends(get_pw_db)])
    async def cone_search(self,
                          ra: Union[float, str] = Query(..., description='Right Ascension in degrees', example=315.01417),
                          dec: Union[float, str] = Query(..., description='Declination in degrees', example=35.299),
                          radius: float = Query(..., description='Search radius in specified units', example=0.01),
                          units: SearchCoordUnits = Query('degree', description='Units of search radius', example='degree')):
        """ Perform a cone search """
        return list(cone_search(ra, dec, radius, units=units))

