# !/usr/bin/env python
# -*- coding: utf-8 -*-
#

from contextvars import ContextVar

import peewee
from fastapi import Depends, HTTPException
from sdssdb.peewee.sdss5db import database as pdb
from sdssdb.sqlalchemy.sdss5db import database as sdb

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


def connect_db(db, orm: str = 'peewee'):
    """ Connect to the peewee sdss5db database """

    from valis.main import settings
    profset = db.set_profile(settings.db_server)
    if settings.db_remote and not profset:
        port = settings.db_port
        user = settings.db_user
        host = settings.db_host
        passwd = settings.db_pass
        db.connect_from_parameters(dbname='sdss5db', host=host, port=port,
                                   user=user, password=passwd)

    # raise error if we cannot connect
    if not db.connected:
        raise HTTPException(status_code=503, detail=f'Could not connect to database via sdssdb {orm}.')

    return db


def get_pw_db(db_state=Depends(reset_db_state)):
    """ Dependency to connect a database with peewee """

    # connect to the db, yield None since we don't need the db in peewee
    db = connect_db(pdb, orm='peewee')
    try:
        yield db
    finally:
        if db:
            db.close()


def get_sqla_db():
    """ Dependency to connect to a database with sqlalchemy """

    # connect to the db, yield the db Session object for sql queries
    db = connect_db(sdb, orm='sqla')
    db = db.Session()
    try:
        yield db
    finally:
        if db:
            db.close()


