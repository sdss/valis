# !/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Filename: envs.py
# Project: routes
# Author: Brian Cherinka
# Created: Tuesday, 22nd September 2020 2:29:06 pm
# License: BSD 3-clause "New" or "Revised" License
# Copyright (c) 2020 Brian Cherinka
# Last Modified: Tuesday, 22nd September 2020 2:29:06 pm
# Modified By: Brian Cherinka


from __future__ import print_function, division, absolute_import
from fastapi import APIRouter, HTTPException
from fastapi_utils.cbv import cbv
import copy

from valis.routes.base import Base

router = APIRouter()

@cbv(router)
class Envs(Base):

    @router.get("/", summary='Get a list of SDSS tree environment variables')
    async def get_envs(self) -> dict:
        """ Get a list of SDSS tree environment variables """
        return {'envs': {k: list(v.keys()) for k, v in self.tree.environ.items() if k != 'default'}}


    @router.get("/resolve", summary='Resolve the SDSS tree environment variables into their paths')
    async def resolve_envs(self, name: str = None) -> dict:
        """ Get a list of SDSS tree environment variables """
        env = copy.deepcopy(self.tree.environ)
        env.pop('default')
        if name:
            td = self.tree.to_dict()
            if name not in td:
                raise HTTPException(status_code=404, detail=f'{name} not found in SDSS tree')
            return {name: td.get(name)}
        return {'envs': env}


    @router.get("/releases", summary='Get a list of SDSS data releases')
    async def get_releases(self, public: bool = False) -> list:
        """ Get a list of SDSS releases """
        return self.tree.get_available_releases(public=public)
