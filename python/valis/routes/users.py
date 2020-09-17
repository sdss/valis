# !/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Filename: users.py
# Project: routes
# Author: Brian Cherinka
# Created: Wednesday, 16th September 2020 10:17:21 pm
# License: BSD 3-clause "New" or "Revised" License
# Copyright (c) 2020 Brian Cherinka
# Last Modified: Wednesday, 16th September 2020 10:17:22 pm
# Modified By: Brian Cherinka


from __future__ import print_function, division, absolute_import
from fastapi import APIRouter

router = APIRouter()


@router.get("/users/", tags=["users"])
async def read_users():
    return [{"username": "Foo"}, {"username": "Bar"}]


@router.get("/users/me", tags=["users"])
async def read_user_me():
    return {"username": "fakecurrentuser"}


@router.get("/users/{username}", tags=["users"])
async def read_user(username: str):
    return {"username": username}
