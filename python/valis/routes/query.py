# !/usr/bin/env python
# -*- coding: utf-8 -*-
#

from fastapi import APIRouter, Depends
from fastapi_utils.cbv import cbv

from sdssdb.peewee.sdss5db import catalogdb

from valis.routes.base import Base
from valis.db.db import get_db, get_sqla_db
from valis.db.models import SourceBase, CubeBase


router = APIRouter()


@cbv(router)
class Query(Base):

    @router.get("/testa", summary='slqa test', response_model=CubeBase)
    async def get_testa(self, db=Depends(get_sqla_db)) -> dict:
        """ Get a list of available SDSS maskbits schema or flag names """
        if db and db.connected:
            from sdssdb.sqlalchemy.mangadb import datadb
            return db.query(datadb.Cube).first()
        else:
            return {"message": "Not connected to database"}

    @router.get("/testp", summary='peewee test', response_model=SourceBase,
                dependencies=[Depends(get_db)])
    async def get_testp(self) -> dict:
        """ Get a list of available SDSS maskbits schema or flag names """
        return catalogdb.Gaia_edr3_allwise_best_neighbour.select().first()
