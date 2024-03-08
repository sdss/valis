# !/usr/bin/env python
# -*- coding: utf-8 -*-
#

from enum import Enum
from typing import List, Union, Dict, Annotated, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi_restful.cbv import cbv
from pydantic import BaseModel, Field, BeforeValidator

from valis.routes.base import Base
from valis.db.db import get_pw_db
from valis.db.models import SDSSidStackedBase, SDSSidPipesBase
from valis.db.queries import (cone_search, append_pipes, carton_program_search,
                              carton_program_list, carton_program_map,
                              get_targets_by_sdss_id, get_targets_by_catalog_id,
                              get_targets_obs)
from sdssdb.peewee.sdss5db import database

# convert string floats to proper floats
Float = Annotated[Union[float, str], BeforeValidator(lambda x: float(x) if x and isinstance(x, str) else x)]


class SearchCoordUnits(str, Enum):
    """ Units of coordinate search radius """
    degree: str = "degree"
    arcmin: str = "arcmin"
    arcsec: str = "arcsec"


class SearchModel(BaseModel):
    """ Input main query body model """
    ra: Optional[Union[float, str]] = Field(None, description='Right Ascension in degrees or hmsdms', example=315.01417)
    dec: Optional[Union[float, str]] = Field(None, description='Declination in degrees or hmsdms', example=35.299)
    radius: Optional[Float] = Field(None, description='Search radius in specified units', example=0.01)
    units: Optional[SearchCoordUnits] = Field('degree', description='Units of search radius', example='degree')
    id: Optional[Union[int, str]] = Field(None, description='The SDSS identifier', example=23326)
    program: Optional[str] = Field(None, description='The program name', example='bhm_rm')
    carton: Optional[str] = Field(None, description='The carton name', example='bhm_rm_core')


class MainResponse(SDSSidPipesBase, SDSSidStackedBase):
    """ Combined model from all individual query models """


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

        # build the id query
        elif body.id:
            query = get_targets_by_sdss_id(body.id)

        # build the program/carton query
        elif body.program or body.carton:
            query = carton_program_search(body.program or body.carton, 'program' if body.program else 'carton')

        # append query to pipes
        query = append_pipes(query)

        return {'status': 'success', 'data': query.dicts().iterator(), 'msg': 'data successfully retrieved'}

    @router.get('/cone', summary='Perform a cone search for SDSS targets with sdss_ids',
                response_model=List[SDSSidStackedBase], dependencies=[Depends(get_pw_db)])
    async def cone_search(self,
                          ra: Annotated[Union[float, str], Query(description='Right Ascension in degrees or hmsdms', example=315.01417)],
                          dec: Annotated[Union[float, str], Query(description='Declination in degrees or hmsdms', example=35.299)],
                          radius: Annotated[float, Query(description='Search radius in specified units', example=0.01)],
                          units: Annotated[SearchCoordUnits, Query(description='Units of search radius', example='degree')] = "degree"):
        """ Perform a cone search """

        return list(cone_search(ra, dec, radius, units=units))

    @router.get('/sdssid', summary='Perform a search for an SDSS target based on the sdss_id',
                response_model=Union[SDSSidStackedBase, dict], dependencies=[Depends(get_pw_db)])
    async def sdss_id_search(self, sdss_id: Annotated[int, Query(description='Value of sdss_id', example=47510284)]):
        """ Perform an sdss_id search.

        Assumes a maximum of one target per sdss_id.
        Empty object returned when no match is found.

        """

        targets = get_targets_by_sdss_id(int(sdss_id)).dicts().first()

        # throw exception when it's a bad sdss_id
        if not targets:
            raise HTTPException(status_code=400, detail=f'Invalid sdss_id {sdss_id}.')

        return targets or {}

    @router.get('/catalogid', summary='Perform a search for SDSS targets based on the catalog_id',
                response_model=List[SDSSidStackedBase], dependencies=[Depends(get_pw_db)])
    async def catalog_id_search(self, catalog_id: Annotated[int, Query(description='Value of catalog_id', example=7613823349)]):
        """ Perform a catalog_id search """

        return list(get_targets_by_catalog_id(catalog_id))

    @router.get('/list/cartons', summary='Return a list of all cartons',
                response_model=list, dependencies=[Depends(get_pw_db)])
    async def cartons(self):
        """ Return a list of all carton or programs """

        return carton_program_list("carton")

    @router.get('/list/programs', summary='Return a list of all programs',
                response_model=list, dependencies=[Depends(get_pw_db)])
    async def programs(self):
        """ Return a list of all carton or programs """

        return carton_program_list("program")

    @router.get('/list/program-map', summary='Return a mapping of cartons in all programs',
                response_model=Dict[str, List[str]], dependencies=[Depends(get_pw_db)])
    async def program_map(self):
        """ Return a mapping of cartons in all programs """

        return carton_program_map()

    @router.get('/carton-program', summary='Search for all SDSS targets within a carton or program',
                response_model=List[SDSSidStackedBase], dependencies=[Depends(get_pw_db)])
    async def carton_program(self,
                             name: Annotated[str, Query(description='Carton or program name', example='manual_mwm_tess_ob')],
                             name_type: Annotated[str,
                                                  Query(enum=['carton', 'program'],
                                                        description='Specify search on carton or program',
                                                        example='carton')] = 'carton'):
        """ Perform a search on carton or program """
        with database.atomic() as transaction:
            database.execute_sql('SET LOCAL enable_seqscan=false;')
            return list(carton_program_search(name, name_type))

    @router.get('/obs', summary='Return targets with spectrum at observatory',
                response_model=List[SDSSidStackedBase], dependencies=[Depends(get_pw_db)])
    async def obs(self,
                  release: Annotated[str, Query(description='Data release to query', example='IPL3')],
                  obs: Annotated[str,
                                 Query(enum=['APO', 'LCO'],
                                       description='Observatory to get targets from. Either "APO" or "LCO"',
                                       example='APO')] = 'APO',
                  spectrograph: Annotated[str,
                                          Query(enum=['boss', 'apogee', 'all'],
                                                description='Which spectrograph to return data from',
                                                example='boss')] = 'boss'):
        """ Perform a search on carton or program """

        return list(get_targets_obs(release, obs, spectrograph))

