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
from tree import Tree
from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel, validator
from typing import Type
from enum import Enum
from pydantic import ValidationError
import copy

router = APIRouter()


@router.get("/", summary='Get a list of SDSS tree environment variables')
async def get_envs():
    """ Get a list of SDSS tree environment variables """
    t = Tree()
    return {'envs': {k: list(v.keys()) for k, v in t.environ.items() if k != 'default'}}


# @router.get("/test")
# async def get_envs():
#     """ Get a list of SDSS tree environment variables """
#     t = Tree()
#     env = copy.deepcopy(t.environ)
#     env.pop('default')
#     return {'envs': env}


@router.get("/releases", summary='Get a list of SDSS data releases')
async def get_releases(public: bool = False):
    """ Get a list of SDSS releases """
    t = Tree()
    return t.get_available_releases(public=public)
