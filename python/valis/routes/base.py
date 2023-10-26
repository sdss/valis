# !/usr/bin/env python
# -*- coding: utf-8 -*-
#

from typing import Optional
from pydantic import BaseModel, Field
from fastapi import Depends, HTTPException, Query
from tree import Tree
from sdss_access.path import Path


def validate_release(value: str) -> str:
    """ Validate a release value """
    if value.upper() not in Tree.get_available_releases():
        raise ValueError(f'Validation error: release {value} not a valid release')
    return value


class BaseBody(BaseModel):
    release: Optional[str] = Field(None, examples=['DR17'], description='The SDSS data release')


async def release(release: str = Query(None, example='DR17', description='The SDSS data release'),
                  body: BaseBody = None) -> str:
    """ Dependency to specify a release query or body parameter """
    try:
        final = validate_release(release or (body.release if body else None) or 'DR17')
    except ValueError as ee:
        raise HTTPException(status_code=422, detail=f'Validation Error: {ee}') from ee
    return final


async def get_tree(release: str = Depends(release)) -> Tree:
    """ Dependency to get a valid SDSS tree for a given release """
    # convert the release to a tree config
    config = release.lower().replace('-', '')
    # default to sdss5 config for work release
    # for tree >= 4.0, sdss5 is sdsswork
    config = 'sdsswork' if config in {'work', 'sdss5', 'sdss4', 'sdsswork'} else config
    return Tree(config)


async def get_access(release: str = Depends(release), tree: Tree = Depends(get_tree)) -> Path:
    """ Dependency to get a valid sdss_access Path for a given release """
    # default to sdss5 config for work release
    # for tree >= 4.0 is sdss5 is sdsswork
    return Path(release='sdsswork' if release == 'WORK' else release)


class Base:
    """ Base class for all API routes"""
    release: str = Depends(release)
    tree: Tree = Depends(get_tree)
    path: Path = Depends(get_access)

    def check_path_name(self, name: str):
        names = self.path.lookup_names()
        if name not in names:
            raise HTTPException(status_code=422, detail=f'path name {name} not in release.')

    def check_path_exists(self, path: str):
        if not self.path.exists('', full=path):
            raise HTTPException(status_code=422, detail=f'path {path} does not exist on disk.')
