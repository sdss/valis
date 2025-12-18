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

from typing import Dict, List, Union
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Query
from fastapi_restful.cbv import cbv
import copy

from valis.routes.base import Base

router = APIRouter()


class EnvsResponse(BaseModel):
    """ Response model for Tree environment """
    envs: Dict[str, List[str]]


@cbv(router)
class Envs(Base):

    @router.get("/", summary='Get a list of SDSS tree environment variables', response_model=EnvsResponse)
    async def get_envs(self) -> dict:
        """ Get a list of SDSS tree environment variables """
        return {'envs': {k: list(v.keys()) for k, v in self.tree.environ.items() if k != 'default'}}

    @router.get("/resolve", summary='Resolve the SDSS tree environment variables into their paths',
                response_model=Union[Dict[str, dict], Dict[str, str]])
    async def resolve_envs(self, name: str = Query(None, descripion='the SDSS environment variable',
                                                   example='BOSS_SPECTRO_REDUX')) -> dict:
        """ Resolve an SDSS tree environment variable into its path """
        env = copy.deepcopy(self.tree.environ)
        env.pop('default')
        if name:
            td = self.tree.to_dict()
            if name not in td:
                raise HTTPException(status_code=404, detail=f'{name} not found in SDSS tree')
            return {name: td.get(name)}
        return {'envs': env}

    @router.get("/releases", summary='Get a list of SDSS data releases', response_model=List[str])
    async def get_releases(self, public: bool = Query(False, description='Flag for public releases only')) -> list:
        """ Get a list of SDSS releases """
        return self.tree.get_available_releases(public=public)
