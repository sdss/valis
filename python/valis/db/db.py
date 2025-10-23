# !/usr/bin/env python
# -*- coding: utf-8 -*-
#

import asyncio
from contextvars import ContextVar

import peewee
from fastapi import HTTPException, Depends
from sdssdb.peewee.sdss5db import database as pdb
from sdssdb.sqlalchemy.sdss5db import database as sdb

from valis.utils.versions import get_software_tag

# To make Peewee async-compatible, we need to hack the peewee connection state
# See FastAPI/Peewee docs at https://fastapi.tiangolo.com/how-to/sql-databases-peewee/

# create global context variables for the peewee connection state
db_state_default = {"closed": None, "conn": None, "ctx": None, "transactions": None}
db_state = ContextVar("db_state", default=db_state_default.copy())


async def reset_db_state():
    """ Sub-dependency for get_db that resets the context connection state """

    from valis.main import settings

    if settings.db_reset:
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

    if db.connected:
        return db

    profset = db.set_profile(settings.db_server) if settings.db_server else None
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

async def get_pw_db(db_state=Depends(reset_db_state), release: str | None = None):
    """ Dependency to connect a database with peewee

    dependency inputs act as query parameters, release input comes from the
    release qp dependency in routes/base.py
    """

    from valis.main import settings
    # connect to the db, yield None since we don't need the db in peewee
    if settings.db_reset:
        db = connect_db(pdb, orm='peewee')
    else:
        async with asyncio.Lock():
            db = connect_db(pdb, orm='peewee')

    # set the correct astra schema if needed
    try:
        vastra = get_software_tag(release, 'v_astra')
    except AttributeError:
        # case when release is None or invalid
        # uses default set astra schema defined in sdssdb
        pass
    else:
        # for dr19 or ipl3 set schema to 0.5.0 ; ipl4=0.8.0
        vastra = "0.5.0" if vastra in ("0.5.0", "0.6.0") else vastra
        schema = f"astra_{vastra.replace('.', '')}"
        pdb.set_astra_schema(schema)

    try:
        yield db
    finally:
        if db and settings.db_reset:
            db.close()


def get_sqla_db():
    """ Dependency to connect to a database with sqlalchemy """

    from valis.main import settings

    # connect to the db, yield the db Session object for sql queries
    db = connect_db(sdb, orm='sqla')
    db = db.Session()
    try:
        yield db
    finally:
        if db and settings.db_reset:
            db.close()
