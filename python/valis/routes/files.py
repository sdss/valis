# !/usr/bin/env python
# -*- coding: utf-8 -*-
#
from __future__ import print_function, division, absolute_import

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi_utils.cbv import cbv
from pydantic import BaseModel, validator
from typing import Type, Union, Dict
from astropy.io import fits
from enum import Enum
from pydantic import ValidationError
import copy
import pathlib
import orjson

from valis.routes.base import Base
from valis.routes.access import extract_path, PathModel

router = APIRouter()

async def get_filepath(name: str = None, path: Type[PathModel] = Depends(extract_path)) -> str:
    return path.dict(include={'full'})['full']

async def header(filename: str = Depends(get_filepath), ext: Union[int, str] = 0) -> dict:
    ''' get a FITS header '''
    with fits.open(filename) as hdu:
        return hdu[ext].header


@cbv(router)
class Files(Base):

    @router.get("/")
    async def get_file(self):
        """ Download a file """
        return {"info": "this route is for files"}

    @router.get("/download")
    async def download_file(self, filename: str = Depends(get_filepath)):
        """ Download a file """

        ppath = pathlib.Path(filename)
        if '.fits' in ppath.suffixes:
            media = 'application/fits'
        elif '.jpeg' in ppath.suffixes or '.jpg' in ppath.suffixes:
            media = 'image/jpeg'
        elif '.par' in ppath.suffixes:
            media = 'text/plain'
        else:
            media = 'application/octet-stream'
        return FileResponse(filename, filename=ppath.name, media_type=media)

    @router.get("/header")
    async def get_header(self, header: fits.Header = Depends(header)):
        """ Return a header """
        return {"header": dict(header.items()), 'comments': {k: header.comments[k] for k in header}}

class KeyModel(BaseModel):
    key: str
    value: Union[str, int, float]
    comment: str = None

class HeaderModel(BaseModel):
    header: Dict[str, Union[str, int, float]]
    comments: Dict[str, str] = None