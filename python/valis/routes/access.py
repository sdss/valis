# !/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Filename: access.py
# Project: routes
# Author: Brian Cherinka
# Created: Wednesday, 16th September 2020 6:16:40 pm
# License: BSD 3-clause "New" or "Revised" License
# Copyright (c) 2020 Brian Cherinka
# Last Modified: Wednesday, 16th September 2020 6:16:40 pm
# Modified By: Brian Cherinka


from __future__ import print_function, division, absolute_import
from sdss_access.path import Path
from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel, validator
from typing import Type
from enum import Enum
from pydantic import ValidationError


class PathPart(str, Enum):
    """ A set of pre-defined choices for the `part` query param
    """
    full = "full"
    url = "url"
    file = "file"
    location = "location"
    all = "all"


class PathModel(BaseModel):
    """ A validator class for sdss_access path names and kwargs
    """
    name: str
    kwargs: dict = None
    template: str = None
    full: str = None
    url: str = None
    file: str = None
    location: str = None
    exists: bool = None

    @validator('name')
    def is_name(cls, v):
        if v not in Path().lookup_names():
            raise ValueError(f'Validation error: path name {v} not a valid sdss_access name')
        return v

    @validator('kwargs')
    def good_kwargs(cls, v, values):
        name = values.get('name')
        keys = set(Path().lookup_keys(name))
        valid = set(v) & set(keys)
        if not valid:
            return None
        missing = set(keys) - set(v)
        if missing:
            mstr = ', '.join(missing)
            raise ValueError(f'Validation error: Missing kwargs {mstr} for name: {name}')
        return v

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        p = Path()
        self.template = p.templates[self.name]
        if self.kwargs:
            self.full = p.full(self.name, **self.kwargs)
            self.url = p.url(self.name, **self.kwargs)
            self.file = p.name(self.name, **self.kwargs)
            self.location = p.location(self.name, **self.kwargs)
            self.exists = p.exists(self.name, **self.kwargs)


async def extract_path(name: str, request: Request) -> Type[PathModel]:
    """ A dependency function to extract and parse generic query parameters
    """
    params = str(request.query_params)
    kwargs = dict(map(lambda x: x.split('='), params.split('&'))) if params else {}
    try:
        path = PathModel(name=name, kwargs=kwargs)
    except ValidationError as ee:
        raise HTTPException(status_code=422, detail=ee.errors()) from ee
    else:
        return path

router = APIRouter()


@router.get("/", summary='Get a list of all sdss_access path names')
async def get_paths():
    """ Get a list of sdss_access path names """
    p = Path()
    return {'names': list(p.lookup_names())}


@router.get("/keywords/{name}", summary='Get a list of keyword variables for a sdss_acccess path name.')
async def get_path_kwargs(path: Type[PathModel] = Depends(extract_path)):
    """ Get a list of input keyword arguments

    Given an sdss_access path name, get the list of input keywords needed
    to construct the full path.

    Parameters
    ----------
        name : str
            a sdss_access path name

    Returns
    -------
        A dict of path name and list of string keywords
    """

    p = Path()
    return {'name': path.name, 'kwargs': p.lookup_keys(path.name)}


@router.get("/{name}", summary='Get the template or resolved path for an sdss_access path name.')
async def get_path_name(path: Type[PathModel] = Depends(extract_path), part: PathPart = 'full',
                        exists: bool = False):
    """ Construct an sdss_access path

    Given a sdss_access path name, constructs the fully resolved path.  sdss_access path
    keyword arguments are passed in as url query parameters,
    e.g. `paths/mangacube?drpver=v2_4_3&wave=LOG&plate=8485&ifu=1901`.  When no query
    parameters, are specified, returns the sdss_access template.

    Parameters
    ----------
        name : str
            a sdss_access path name
        part : str
            the part of the path to extract
        exists : bool
            If set, checks for local file existence and returns True/False

    Returns
    -------
        A string path name

    """
    if not path.kwargs:
        return path.dict(include={'template'})
    elif exists:
        return path.dict(include={'exists'})
    else:
        return path.dict() if part == 'all' else path.dict(include={part})


@router.post("/{name}", summary='Get the template or resolved path for an sdss_access path name.')
async def post_path_name(name: str, kwargs: dict = None, part: PathPart = 'full',
                         exists: bool = False):
    """ Construct an sdss_access path

    Given an sdss_access path name and set of input keyword arguments,
    construct the file path using sdss_access methods.  Set `part` keyword to
    indicate the part of the path to form, e.g. "full", "url".  Set `exists` to
    check whether the file exists on the server.

    Parameters
    ----------
        name : str
            a sdss_access path name
        kwargs: dict
            a set of keyword arguments to construct the file path
        part : str
            the part of the path to extract.  Default is "full".
        exists : bool
            If set, checks for local file existence and returns True/False

    Returns
    -------
        A string path name

    """
    try:
        path = PathModel(name=name, kwargs=kwargs)
    except ValidationError as ee:
        raise HTTPException(status_code=422, detail=ee.errors()) from ee
    else:
        if not path.kwargs:
            return path.dict(include={'template'})
        elif exists:
            return path.dict(include={'exists'})
        else:
            return path.dict() if part == 'all' else path.dict(include={part})
