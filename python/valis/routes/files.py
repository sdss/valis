# !/usr/bin/env python
# -*- coding: utf-8 -*-
#
from __future__ import print_function, division, absolute_import
from unicodedata import name

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi_utils.cbv import cbv
import numpy as np
from pydantic import BaseModel
from typing import Type, Union, Dict, Any, Optional, Callable
from astropy.io import fits
from astropy.table import Table
import pathlib
import orjson

from valis.routes.base import Base
from valis.routes.access import extract_path, PathModel

router = APIRouter()

async def get_filepath(name: str = None, path: Type[PathModel] = Depends(extract_path)) -> str:
    """ Depedency to get a filepath from sdss_access """
    return path.dict(include={'full'})['full']

async def header(filename: str = Depends(get_filepath), ext: Union[int, str] = 0) -> dict:
    """ Dependency to retrieve a FITS header of a given HDU extension """
    with fits.open(filename) as hdu:
        return hdu[ext].header

async def get_ext(filename: str = Depends(get_filepath), ext: Union[int, str] = 0):
    """ Dependency to get a FITS data, header """
    with fits.open(filename) as hdu:
        data = hdu[ext].data
        # convert binary table data into a dictionary
        if not hdu[ext].is_image:
            t = Table(hdu[ext].data)
            data = {c: t[c].data for c in t.columns}
        return data, hdu[ext].header

def npdefault(obj):
    """ Custom default function for orjson numpy array  serialization """
    if isinstance(obj, np.ndarray):
        if obj.dtype.type == np.str_:
            # for numpy string arrays
            return obj.tolist()
        elif obj.dtype.type == np.int16:
            # for numpy int16 arrays
            return obj.astype(np.int32)
        elif obj.dtype.type == np.uint16:
            # for numpy uint16 arrays
            return obj.astype(np.uint32)
    raise TypeError
     
class ORJSONResponseCustom(JSONResponse):
    """ Custom ORJSONResponse that allows passing options to orjson library """
    media_type = "application/json"
    option = None

    def __init__(self, option: Optional[int] = None, default: Callable = None, **kwds):
        self.option = option
        self.default = default
        super().__init__(**kwds)

    def render(self, content: Any) -> bytes:
        assert orjson is not None, "orjson must be installed to use ORJSONResponse"
        return orjson.dumps(content, option=self.option, default=self.default)


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

    @router.get("/data")
    async def get_filedata(self, fitsext: tuple = Depends(get_ext), header: bool = True):
        """ Download a file """
        # extract the FITS data
        data, hdr = fitsext
        # return a response 
        results = {'header': dict(hdr.items()) if header else None, 'data': data}
        return ORJSONResponseCustom(content=results, option=orjson.OPT_SERIALIZE_NUMPY, default=npdefault)

class KeyModel(BaseModel):
    key: str
    value: Union[str, int, float]
    comment: str = None

class HeaderModel(BaseModel):
    header: Dict[str, Union[str, int, float]]
    comments: Dict[str, str] = None
    
# class ImageHDU(BaseModel):
#     data
#     header: HeaderModel
#     name: str
#     is_image: bool = True
#     level: int = None
#     size: int = None
#     ver: int = None
#     shape: tuple = None
    

# class BinTableHDU(BaseModel):
#     pass

