# !/usr/bin/env python
# -*- coding: utf-8 -*-
#

from enum import Enum
from typing import List, Union, Dict, Annotated, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, Body
from fastapi_restful.cbv import cbv
from pydantic import BaseModel, Field, BeforeValidator

from valis.cache import valis_cache
from valis.routes.base import Base
from valis.db.db import get_pw_db
from valis.db.models import SDSSidStackedBase, SDSSidPipesBase, MapperName, SDSSModel
from valis.db.queries import (cone_search, append_pipes, carton_program_search,
                              carton_program_list, carton_program_map,
                              get_targets_by_sdss_id, get_targets_by_catalog_id,
                              get_targets_obs, get_paged_target_list_by_mapper,
                              get_target_by_altid, get_targets_by_altid)
from valis.routes.auth import set_auth
from sdssdb.peewee.sdss5db import database, catalogdb

# convert string floats to proper floats
Float = Annotated[Union[float, str], BeforeValidator(lambda x: float(x) if x and isinstance(x, str) else x)]


class SearchCoordUnits(str, Enum):
    """ Units of coordinate search radius """
    degree: str = "degree"
    arcmin: str = "arcmin"
    arcsec: str = "arcsec"


class SearchModel(BaseModel):
    """ Input main query body model """
    ra: Optional[Union[float, str]] = Field(None, description='Right Ascension in degrees or hmsdms', example=150.385)
    dec: Optional[Union[float, str]] = Field(None, description='Declination in degrees or hmsdms', example=1.02)
    radius: Optional[Float] = Field(None, description='Search radius in specified units', example=0.02)
    units: Optional[SearchCoordUnits] = Field('degree', description='Units of search radius', example='degree')
    id: Optional[Union[int, str]] = Field(None, description='The SDSS identifier', example=23326)
    altid: Optional[Union[int, str]] = Field(None, description='An alternative identifier', example=27021603187129892)
    idtype: Optional[str] = Field(None, description='The type of integer id, for ambiguous ids', example="catalogid")
    program: Optional[str] = Field(None, description='The program name', example='bhm_rm')
    carton: Optional[str] = Field(None, description='The carton name', example='bhm_rm_core')
    observed: Optional[bool] = Field(True, description='Flag to only include targets that have been observed', example=True)
    limit: Optional[int] = Field(None, description='Limit the number of returned targets', example=100)

class MainResponse(SDSSModel):
    """ Combined model from all individual query models """


class MainSearchResponse(BaseModel):
    """ The main query response model """
    status: str = Field(..., description='the query return status')
    msg: str = Field(..., description='the response status message')
    data: List[MainResponse] = Field(..., description='the list of query results')


class SDSSIdsModel(BaseModel):
    """Request body for the endpoint returning targets from an sdss_id list"""
    sdss_id_list: List[int] = Field(description='List of sdss_id values', example=[67660076, 67151446])

class AltEnum(str, Enum):
    """ Enum for the alternative id types """
    apogeeid = 'apogeeid'
    catalogid = 'catalogid'
    gaiaid = 'gaiaid'
    sdssid = 'sdssid'
    twomassid = 'twomassid'

class AltIdsModel(BaseModel):
    """Request body for the endpoint returning targets from an sdss_id list"""
    altid_list: List[str|int] = Field(description='List of altid values', example=['2M10193634+1952122', '2M14030226+5112480'])
    idtype: Optional[AltEnum] = Field(None, description='For ambiguous integer ids, the type of id, e.g. "catalogid"', example=['apogeeid'])


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
                 dependencies=[Depends(get_pw_db), Depends(set_auth)],
                 response_model=MainSearchResponse, response_model_exclude_unset=True,
                 response_model_exclude_none=True)
    @valis_cache(namespace='valis-query')
    async def main_search(self, body: SearchModel):
        """ Main query for UI and for combining queries together """

        print('form data', body)
        query = None

        # build the coordinate query
        if body.ra and body.dec:
            query = cone_search(body.ra, body.dec, body.radius, units=body.units)

        # build the id query
        elif body.id:
            query = get_targets_by_sdss_id(body.id)

        # build the altid query
        elif body.altid:
            query = get_target_by_altid(body.altid, body.idtype)

        # build the program/carton query
        if body.program or body.carton:
            query = carton_program_search(body.program or body.carton,
                                          'program' if body.program else 'carton',
                                          query=query)

        # DANGER!!! This limit applies *before* the append_pipes call. If the
        # append_pipes call includes observed=True we may have limited things in
        # such a way that only unobserved or very few targets are returned.
        if body.limit:
            query = query.limit(body.limit)

        # append query to pipes
        if query:
            query = append_pipes(query, observed=body.observed, release=self.release)

        # Results. Note that we cannot return an iterator in a cached route or the
        # initial query (when it does not hit the cache) will return an empty list.
        res = list(query.dicts()) if query else []

        return {'status': 'success', 'data': res, 'msg': 'data successfully retrieved'}

    @router.get('/cone', summary='Perform a cone search for SDSS targets with sdss_ids',
                response_model=List[SDSSModel], dependencies=[Depends(get_pw_db), Depends(set_auth)])
    @valis_cache(namespace='valis-query')
    async def cone_search(self,
                          ra: Annotated[Union[float, str], Query(description='Right Ascension in degrees or hmsdms', example=315.78)],
                          dec: Annotated[Union[float, str], Query(description='Declination in degrees or hmsdms', example=-3.2)],
                          radius: Annotated[float, Query(description='Search radius in specified units', example=0.02)],
                          units: Annotated[SearchCoordUnits, Query(description='Units of search radius', example='degree')] = "degree",
                          observed: Annotated[bool, Query(description='Flag to only include targets that have been observed', example=True)] = True):
        """ Perform a cone search """

        res = cone_search(ra, dec, radius, units=units)
        r = append_pipes(res, observed=observed, release=self.release)
        # return sorted by distance
        # doing this here due to the append_pipes distinct
        return sorted(r.dicts(), key=lambda x: x['distance'])

    @router.get('/sdssid', summary='Perform a search for an SDSS target based on the sdss_id',
                response_model=Union[SDSSidStackedBase, dict],
                dependencies=[Depends(get_pw_db), Depends(set_auth)])
    @valis_cache(namespace='valis-query')
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

    @router.post('/sdssid', summary='Perform a search for SDSS targets based on a list of sdss_id values',
                response_model=List[SDSSModel],
                dependencies=[Depends(get_pw_db), Depends(set_auth)])
    async def sdss_ids_search(self, body: SDSSIdsModel):
        """ Perform a search for SDSS targets based on a list of input sdss_id values."""
        return list(append_pipes(get_targets_by_sdss_id(body.sdss_id_list), release=self.release).dicts())
        #return list(get_targets_by_sdss_id(body.sdss_id_list))

    @router.post('/altids', summary='Performa search for SDSS targets based on a list of alternative ids',
                response_model=List[SDSSModel],
                dependencies=[Depends(get_pw_db), Depends(set_auth)])
    async def altids_search(self, body: AltIdsModel):
        """ Perform a search for SDSS targets based on a list of input altid values."""
        return list(append_pipes(get_targets_by_altid(body.altid_list, idtype=body.idtype), release=self.release).dicts())

    @router.get('/catalogid', summary='Perform a search for SDSS targets based on the catalog_id',
                response_model=List[SDSSidStackedBase],
                dependencies=[Depends(get_pw_db), Depends(set_auth)])
    async def catalog_id_search(self, catalog_id: Annotated[int, Query(description='Value of catalog_id', example=7613823349)]):
        """ Perform a catalog_id search """

        return list(get_targets_by_catalog_id(catalog_id))

    @router.get('/list/cartons', summary='Return a list of all cartons',
                response_model=list, dependencies=[Depends(get_pw_db)])
    @valis_cache(namespace='valis-query')
    async def cartons(self):
        """ Return a list of all carton or programs """

        return carton_program_list("carton")

    @router.get('/list/programs', summary='Return a list of all programs',
                response_model=list, dependencies=[Depends(get_pw_db)])
    @valis_cache(namespace='valis-query')
    async def programs(self):
        """ Return a list of all carton or programs """

        return carton_program_list("program")

    @router.get('/list/program-map', summary='Return a mapping of cartons in all programs',
                response_model=Dict[str, List[str]], dependencies=[Depends(get_pw_db)])
    @valis_cache(namespace='valis-query')
    async def program_map(self):
        """ Return a mapping of cartons in all programs """

        return carton_program_map()

    @router.get('/list/parents', summary='Return a list of available parent catalog tables',
                response_model=List[str])
    @valis_cache(namespace='valis-query')
    async def parent_catalogs(self):
        """Return a list of available parent catalog tables."""

        columns = catalogdb.SDSS_ID_To_Catalog._meta.fields.keys()

        # In sdss_id_to_catalog table, the parent catalog columns are named
        # as 'parent_catalog__parent_catalog_pk_column'.
        catalogs = [col.split('__')[0] for col in columns if '__' in col]

        return sorted(catalogs)

    @router.get('/carton-program', summary='Search for all SDSS targets within a carton or program',
                response_model=List[SDSSModel],
                dependencies=[Depends(get_pw_db), Depends(set_auth)])
    @valis_cache(namespace='valis-query')
    async def carton_program(self,
                             name: Annotated[str, Query(description='Carton or program name', example='manual_mwm_tess_ob')],
                             name_type: Annotated[str,
                                                  Query(enum=['carton', 'program'],
                                                        description='Specify search on carton or program',
                                                        example='carton')] = 'carton',
                             observed: Annotated[bool, Query(description='Flag to only include targets that have been observed', example=True)] = True,
                             limit: Annotated[int | None, Query(description='Limit the number of returned targets', example=100)] = None):
        """ Perform a search on carton or program """
        with database.atomic():
            if limit is False:
                # This tweak seems to do more harm than good when limit is passed.
                database.execute_sql('SET LOCAL enable_seqscan=false;')

            query = carton_program_search(name, name_type, limit=limit)
            query = append_pipes(query, observed=observed)

            # The list() is necessary here to not return a generator in the cached route.
            return list(query.dicts())

    @router.get('/obs', summary='Return targets with spectrum at observatory',
                response_model=List[SDSSidStackedBase],
                dependencies=[Depends(get_pw_db), Depends(set_auth)])
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

    @router.get('/mapper', summary='Perform a search for SDSS targets based on the mapper',
                response_model=List[SDSSidStackedBase],
                dependencies=[Depends(get_pw_db), Depends(set_auth)])
    async def get_target_list_by_mapper(self,
                                        mapper: Annotated[MapperName, Query(description='Mapper name', example=MapperName.MWM)] = MapperName.MWM,
                                        page_number: Annotated[int, Query(description='Page number of the returned items', gt=0, example=1)] = 1,
                                        items_per_page: Annotated[int, Query(description='Number of items displayed in a page', gt=0, example=10)] = 10):
        """ Return an ordered and paged list of targets based on the mapper."""
        targets = get_paged_target_list_by_mapper(mapper, page_number, items_per_page)
        return list(targets)
