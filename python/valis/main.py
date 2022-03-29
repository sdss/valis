# !/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Filename: main.py
# Project: app
# Author: Brian Cherinka
# Created: Wednesday, 16th September 2020 10:16:46 pm
# License: BSD 3-clause "New" or "Revised" License
# Copyright (c) 2020 Brian Cherinka
# Last Modified: Wednesday, 16th September 2020 10:16:46 pm
# Modified By: Brian Cherinka


from __future__ import print_function, division, absolute_import
from fastapi import FastAPI, Depends
from fastapi.openapi.utils import get_openapi

import valis
from valis.routes import access, envs, files, auth
from valis.routes.base import release
from valis.routes.auth import set_auth


tags_metadata = [
    {
        "name": "default",
        "description": "Default API endpoints",
    },
    {
        "name": "paths",
        "description": "Lookup or construct SDSS filepaths using sdss_access",
        "externalDocs": {
            "description": "sdss_access docs",
            "url": "https://sdss-access.rtfd.io/",
        },
    },
    {
        "name": "envs",
        "description": "Explore the SDSS tree environment and data releases",
        "externalDocs": {
            "description": "sdss-tree docs",
            "url": "https://sdss-tree.rtfd.io/",
        },
    },
    {
        "name": "file",
        "description": "Download or stream SDSS files",
    },
    {
        "name": "auth",
        "description": "Authenticate SDSS users",
    },
]


app = FastAPI(title='Valis', description='The SDSS API', version=valis.__version__, 
              openapi_tags=tags_metadata, dependencies=[])
# submount app to allow for production /valis location
app.mount("/valis", app)


@app.get("/", summary='Hello World route')
def hello(release = Depends(release)):
    return {"Hello SDSS": "This is the FastAPI World", 'release': release}

app.include_router(access.router, prefix='/paths', tags=['paths'], dependencies=[Depends(set_auth)])
app.include_router(envs.router, prefix='/envs', tags=['envs'], dependencies=[Depends(set_auth)])
app.include_router(files.router, prefix='/file', tags=['file'], dependencies=[Depends(set_auth)])
app.include_router(auth.router, prefix='/auth', tags=['auth'])


def custom_openapi():
    """ Custom OpenAPI spec to remove "release" POST body param from GET requests in the docs """
    # cache the openapi schema
    if app.openapi_schema:
        return app.openapi_schema
    # generate the openapi schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=tags_metadata,
        servers=app.servers
    )
    
    # hack the schema to remove added "release" body parameter to all GET requests
    for content in openapi_schema['paths'].values():
        gcont = content.get('get', None)
        if not gcont:
            continue
        gcont.pop('requestBody', None)
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi
