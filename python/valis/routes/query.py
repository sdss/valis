# !/usr/bin/env python
# -*- coding: utf-8 -*-
#

from enum import Enum
from typing import List, Union
from fastapi import APIRouter, Depends, Query
from fastapi_utils.cbv import cbv
from pydantic import BaseModel, Field

from valis.routes.base import Base
from valis.db.db import get_pw_db
from valis.db.models import SDSSidStackedBase
from valis.db.queries import cone_search, carton_program_search, carton_program_list


class SearchCoordUnits(str, Enum):
    """ Units of coordinate search radius """
    degree: str = "degree"
    arcmin: str = "arcmin"
    arcsec: str = "arcsec"


class SearchModel(BaseModel):
    """ Input main query body model """
    ra: Union[float, str] = Field(..., description='Right Ascension in degrees or hmsdms', example=315.01417)
    dec: Union[float, str] = Field(..., description='Declination in degrees or hmsdms', example=35.299)
    radius: float = Field(..., description='Search radius in specified units', example=0.01)
    units: SearchCoordUnits = Field('degree', description='Units of search radius', example='degree')


class MainResponse(SDSSidStackedBase):
    """ Combined model from all individual query models """
    pass


class MainSearchResponse(BaseModel):
    """ The main query response model """
    status: str = Field(..., description='the query return status')
    msg: str = Field(..., description='the response status message')
    data: List[MainResponse] = Field(..., description='the list of query results')


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

    @router.post('/main', summary='Main query for the UI or combining queries',
                 response_model=MainSearchResponse, dependencies=[Depends(get_pw_db)])
    async def main_search(self, body: SearchModel):
        """ Main query for UI and for combining queries together """
        print('form data', body)

        # build the coordinate query
        if body.ra and body.dec:
            query = cone_search(body.ra, body.dec, body.radius, units=body.units)

        return {'status': 'success', 'data': list(query), 'msg': 'data successfully retrieved'}

    @router.get('/cone', summary='Perform a cone search for SDSS targets with sdss_ids',
                response_model=List[SDSSidStackedBase], dependencies=[Depends(get_pw_db)])
    async def cone_search(self,
                          ra: Union[float, str] = Query(..., description='Right Ascension in degrees or hmsdms', example=315.01417),
                          dec: Union[float, str] = Query(..., description='Declination in degrees or hmsdms', example=35.299),
                          radius: float = Query(..., description='Search radius in specified units', example=0.01),
                          units: SearchCoordUnits = Query('degree', description='Units of search radius', example='degree')):
        """ Perform a cone search """
        return list(cone_search(ra, dec, radius, units=units))

    @router.get('/carton_program', summary='Search for all SDSS targets within a carton or program',
                response_model=List[SDSSidStackedBase], dependencies=[Depends(get_pw_db)])
    async def carton_program(self,
                             name: str = Query("manual_mwm_tess_ob",
                                               description='Carton or program name', example='manual_mwm_tess_ob'),
                             name_type: str = Query('carton', enum=['carton', 'program'],
                                                    description='Specify search on carton or program', example='carton')):
        """ Perform a search on carton or program """
        return list(carton_program_search(name, name_type))
