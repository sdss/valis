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
from fastapi import FastAPI, Request, Depends

import valis
from valis.routes import access, envs, files
from valis.routes.base import release



app = FastAPI(title='Valis', description='The SDSS API', version=valis.__version__)
# submount app to allow for production /valis location
app.mount("/valis", app)


@app.get("/", summary='Hello World route')
def hello(release = Depends(release)):
    return {"Hello SDSS": "This is the FastAPI World", 'release': release}


app.include_router(access.router, prefix='/paths', tags=['paths'])
app.include_router(envs.router, prefix='/envs', tags=['envs'])
#app.include_router(files.router, prefix='/file', tags=['file'])
