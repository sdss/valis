# !/usr/bin/env python
# -*- coding: utf-8 -*-
#

from fastapi import APIRouter, Depends
from fastapi_utils.cbv import cbv

from sdssdb.peewee.sdss5db import apogee_drpdb
from sdssdb.sqlalchemy.mangadb import datadb

from valis.routes.base import Base
from valis.db.db import get_db, get_sqla_db
from valis.db.models import ExpBase, CubeBase


router = APIRouter()


@cbv(router)
class Query(Base):

    @router.get("/testa", summary='slqa test', response_model=CubeBase)
    async def get_testa(self, db=Depends(get_sqla_db)) -> dict:
        """ Get a list of available SDSS maskbits schema or flag names """

        return db.query(datadb.Cube).first()

    @router.get("/testp", summary='peewee test', response_model=ExpBase,
                dependencies=[Depends(get_db)])
    async def get_testp(self) -> dict:
        """ Get a list of available SDSS maskbits schema or flag names """
        return apogee_drpdb.Exposure.select().first()
