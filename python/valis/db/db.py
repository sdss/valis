# !/usr/bin/env python
# -*- coding: utf-8 -*-
#

from contextvars import ContextVar

import peewee
from fastapi import Depends
from sdssdb.peewee.sdss5db import database as pdb
from sdssdb.sqlalchemy.mangadb import database as sdb

# To make Peewee async-compatible, we need to hack the peewee connection state
# See FastAPI/Peewee docs at https://fastapi.tiangolo.com/how-to/sql-databases-peewee/

# create global context variables for the peewee connection state
db_state_default = {"closed": None, "conn": None, "ctx": None, "transactions": None}
db_state = ContextVar("db_state", default=db_state_default.copy())


async def reset_db_state():
    """ Sub-depdency for get_db that resets the context connection state """
    pdb._state._state.set(db_state_default.copy())
    pdb._state.reset()


class PeeweeConnectionState(peewee._ConnectionState):
    """ Custom Connection State for Peewee """
    def __init__(self, **kwargs):
        super().__setattr__("_state", db_state)
        super().__init__(**kwargs)

    def __setattr__(self, name, value):
        self._state.get()[name] = value

    def __getattr__(self, name):
        return self._state.get()[name]


# override the database connection state, after db connection
pdb._state = PeeweeConnectionState()


def connect_db():
    """ Connect to the peewee sdss5db database """
    from valis.main import settings
    profset = pdb.set_profile(settings.valis_db_server)
    if settings.valis_db_remote and not profset:
        port = settings.valis_db_port
        user = settings.valis_db_user
        host = settings.valis_db_host
        passwd = settings.valis_db_pass
        pdb.connect_from_parameters(dbname='sdss5db', host=host, port=port,
                                    user=user, password=passwd)

    if not pdb.connected:
        pass

    return pdb


def get_db(db_state=Depends(reset_db_state)):
    db = connect_db()
    try:
        yield None
    finally:
        if db:
            db.close()


def get_sqla_db():
    db = sdb.Session()
    try:
        yield db
    finally:
        if db:
            db.close()


