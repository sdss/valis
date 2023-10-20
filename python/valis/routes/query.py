# !/usr/bin/env python
# -*- coding: utf-8 -*-
#

from typing import List
from fastapi import APIRouter, Depends, Query
from fastapi_utils.cbv import cbv

from sdssdb.peewee.sdss5db import vizdb

from valis.routes.base import Base
from valis.db.db import get_pw_db, get_sqla_db
from valis.db.models import SDSSidStackedBase


router = APIRouter()


@cbv(router)
class Query(Base):
    """ API routes for performing queries against sdss5db """

    @router.get("/testa", summary='slqa test')
    async def get_testa(self, db=Depends(get_sqla_db)) -> dict:
        """ Get a list of available SDSS maskbits schema or flag names """
        #if db and db.connected:
        from sdssdb.sqlalchemy.mangadb import datadb
        return db.query(datadb.Cube).first()
        #else:
        #    return {"message": "Not connected to database"}

    # @router.get("/testp", summary='peewee test', response_model=SourceBase,
    #             dependencies=[Depends(get_pw_db)])
    # async def get_testp(self) -> dict:
    #     """ Get a list of available SDSS maskbits schema or flag names """
    #     return catalogdb.Gaia_edr3_allwise_best_neighbour.select().first()

    # @router.get('/acone', summary='Perform a cone search for SDSS targets with sdss_ids',
    #             response_model=List[SDSSidStackedBase])
    # async def cone_search(self,
    #                       ra=Query(..., description='right ascension in degrees', example=315.01417),
    #                       dec=Query(..., description='declination in degrees', example=35.299),
    #                       radius=Query(..., description='the search radius in degrees', example=0.01),
    #                       db=Depends(get_sqla_db)):
    #     from sdssdb.sqlalchemy.sdss5db import vizdb

    #     return db.query(vizdb.SDSSidStacked).\
    #         filter(vizdb.SDSSidStacked.cone_search(ra, dec, radius, ra_col='ra_sdss_id', dec_col='dec_sdss_id')).all()

    @router.get('/cone', summary='Perform a cone search for SDSS targets with sdss_ids',
                response_model=List[SDSSidStackedBase], dependencies=[Depends(get_pw_db)])
    async def cone_search(self,
                          ra=Query(..., description='right ascension in degrees', example=315.01417),
                          dec=Query(..., description='declination in degrees', example=35.299),
                          radius=Query(..., description='the search radius in degrees', example=0.01)):
        return list(vizdb.SDSSidStacked.select().where(vizdb.SDSSidStacked.cone_search(ra, dec, radius, ra_col='ra_sdss_id', dec_col='dec_sdss_id')))
