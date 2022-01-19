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
from fastapi import FastAPI, Request

import valis
from valis.routes import access


app = FastAPI(title='Valis', description='The SDSS API', version=valis.__version__)
# submount app to allow for production /valis location
app.mount("/valis", app)


@app.get("/", summary='Hello World route')
def hello(request: Request):
    return {"Hello SDSS": "This is the FastAPI World"}


app.include_router(access.router, prefix='/paths', tags=['paths'])
