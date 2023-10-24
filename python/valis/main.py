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


from __future__ import absolute_import, division, print_function

import os
import pathlib
from typing import Dict
from functools import lru_cache

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.staticfiles import StaticFiles

import valis
from valis.routes import access, auth, envs, files, info, maskbits, mocs, target, query
from valis.routes.auth import set_auth
from valis.routes.base import release
from valis.settings import Settings, read_valis_config


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
    {
        "name": "info",
        "description": "Access metadata on SDSS, its datamodels and products",
    },
    {
        "name": "target",
        "description": "Explore astronomical targets in SDSS",
    },
    {
        "name": "maskbits",
        "description": "Work with SDSS maskbits",
    },
    {
        "name": "mocs",
        "description": "Access SDSS surveys MOCs",
    },
    {
        "name": "query",
        "description": "Query the SDSS databases",
    },
]


@lru_cache
def get_settings():
    """ Get the valis settings """
    cfg = read_valis_config()
    return Settings(**cfg)


settings = get_settings()

# create the application
app = FastAPI(title='Valis', description='The SDSS API', version=valis.__version__,
              openapi_tags=tags_metadata, dependencies=[])
# submount app to allow for production /valis location
app.mount("/valis", app)

# add CORS for cross-domain, for any sdss.org or sdss.utah.edu domain
app.add_middleware(CORSMiddleware, allow_origin_regex="^https://.*\.sdss5?\.(org|utah\.edu)$",
                   allow_origins=settings.allow_origin,
                   allow_credentials=True, allow_methods=['*'], allow_headers=['*'])

# mount the MOCs to a static path
hips_dir = pathlib.Path(os.getenv("SDSS_HIPS"))
if not (hips_dir.is_dir() or hips_dir.is_symlink()):
    hips_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static/mocs", StaticFiles(directory=hips_dir, html=True, follow_symlink=True), name="static")


@app.get("/", summary='Hello World route', response_model=Dict[str, str])
def hello(release=Depends(release)):
    return {"Hello SDSS": "This is the FastAPI World", 'release': release}


app.include_router(access.router, prefix='/paths', tags=['paths'], dependencies=[Depends(set_auth)])
app.include_router(envs.router, prefix='/envs', tags=['envs'], dependencies=[Depends(set_auth)])
app.include_router(files.router, prefix='/file', tags=['file'], dependencies=[Depends(set_auth)])
app.include_router(info.router, prefix='/info', tags=['info'])
app.include_router(auth.router, prefix='/auth', tags=['auth'])
app.include_router(target.router, prefix='/target', tags=['target'])
app.include_router(maskbits.router, prefix='/maskbits', tags=['maskbits'])
app.include_router(mocs.router, prefix='/mocs', tags=['mocs'])
app.include_router(query.router, prefix='/query', tags=['query'])


def hack_auth(dd):
    """ Hack the openapi docs for the auth login form """
    cc = dd.copy()
    for k, v in cc.items():
        # recurse for dicts, then continue
        if isinstance(v, dict):
            hack_auth(v)
            continue

        # continue for non string values
        if not isinstance(v, str):
            continue

        # update the login and callback routes
        b = 'get_token_auth_login_post'
        b2 = 'get_tokenhttps___api_sdss_org_crowd_credential_post'
        if b == v:
            dd[k] = 'AuthForm'
        elif b2 == v:
            dd[k] = 'CredForm'
        elif b in v:
            dd[k] = v.replace(f'Body_{b}', 'AuthForm')
        elif b2 in v:
            dd[k] = v.replace(f'Body_{b2}', 'CredForm')
    return dd


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

    # hack to rename ugly login auth schema for form fields to new names
    # update get_token_auth_login_post name to AuthForm
    # update get_tokenhttps___api_sdss_org_crowd_credential_post to CredForm

    # hack the paths for the Auth Forms
    hack_auth(openapi_schema['paths']['/auth/login'])

    # hack the schema to improve auth Form schema names
    cc = openapi_schema['components']['schemas'].copy()
    for key, vals in openapi_schema['components']['schemas'].items():
        if key == 'Body_get_token_auth_login_post':
            vals['title'] = 'AuthForm'
            cc['AuthForm'] = cc.pop(key)
        elif key.startswith('Body_get_tokenhttps'):
            vals['title'] = 'CredForm'
            cc['CredForm'] = cc.pop(key)

    openapi_schema['components']['schemas'] = dict(sorted(cc.items(), key=lambda x: x[0]))

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi
