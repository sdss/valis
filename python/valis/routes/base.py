# !/usr/bin/env python
# -*- coding: utf-8 -*-
#

from fastapi import Depends
from tree import Tree
from sdss_access.path import Path
from pydantic import BaseModel

class BaseBody(BaseModel):
    release: str = 'WORK'


async def release(release: str = 'WORK') -> str:
    """ Dependency to specify a release query parameter """
    return release

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