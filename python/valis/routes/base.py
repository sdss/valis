# !/usr/bin/env python
# -*- coding: utf-8 -*-
#

from fastapi import Depends, HTTPException, Query
from tree import Tree
from sdss_access.path import Path
from pydantic import BaseModel, Field
from typing import Optional


def validate_release(value: str) -> str:
    """ Validate a release value """
    if value.upper() not in Tree.get_available_releases():
        raise ValueError(f'Validation error: release {value} not a valid release')
    return value

class BaseBody(BaseModel):
    release: Optional[str] = Field(None, example='WORK')
    
# class Release:
#     def __init__(self, body: BaseBody = None, query: BaseBody = Depends()):
#         print('brelease', body, body.release if body else None)
#         print('qrelease', query, query.release if query else None)
#         self.release = (query.release if query else None) or (body.release if body else None) or "WORK"


# async def release(release: Release = Depends()):
#     print('release', release)
#     return release.release or 'WORK'

async def release(release: str = Query(None, example='WORK'), body: BaseBody = None) -> str:
    """ Dependency to specify a release query or body parameter """
    try:
        final = validate_release(release or (body.release if body else None) or 'WORK')
    except ValueError as ee:
        raise HTTPException(status_code=422, detail=f'Validation Error: {ee}') from ee
    return final

async def get_tree(release: str = Depends(release)) -> Tree:
    """ Dependency to get a valid SDSS tree for a given release """
    # convert the release to a tree config
    config = release.lower().replace('-', '')
    # default to sdss5 config for work release
    config = 'sdss5' if config in ['work', 'sdss5', 'sdss4', 'sdsswork'] else config
    return Tree(config)

async def get_access(release: str = Depends(release), tree: Tree = Depends(get_tree)) -> Path:
    """ Dependency to get a valid sdss_access Path for a given release """
    # default to sdss5 config for work release
    return Path(release='sdss5' if release == 'WORK' else release)

class Base:
    """ Base class for all API routes"""
    release: str = Depends(release)
    tree: Tree = Depends(get_tree)
    path: Path = Depends(get_access)