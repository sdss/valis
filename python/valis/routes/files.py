# !/usr/bin/env python
# -*- coding: utf-8 -*-
#
from __future__ import print_function, division, absolute_import

from fastapi import APIRouter, Depends, HTTPException, Query, Path
from fastapi.responses import FileResponse, ORJSONResponse, StreamingResponse
from fastapi_restful.cbv import cbv
import numpy as np
from pydantic import BaseModel, BeforeValidator
from typing import Type, Union, Dict, Any, Optional, Callable, List, Annotated
from astropy.io import fits
from astropy.table import Table
import pathlib
import orjson
import ast
from io import StringIO
from enum import Enum

from valis.routes.base import Base
from valis.routes.access import extract_path, PathModel

router = APIRouter()

VALIS_SUPPORTED_FILES = ['.fits']


Ext = Annotated[Union[int, str], BeforeValidator(lambda x: int(x) if str(x).isnumeric() else str(x)),
                Query(description='The HDU extension number or name')]


async def get_filepath(name: str = Path(..., description='The sdss access path name', example='spec-lite'),
                       path: Type[PathModel] = Depends(extract_path)) -> str:
    """ Depedency to get a filepath from sdss_access """
    data = path.model_dump(include={'full', 'exists'})
    filepath = data['full']

    # validate file existenence
    if not data['exists']:
        raise HTTPException(status_code=404, detail=f'File {filepath} not found')

    # validate file suffix type
    if set(pathlib.Path(filepath).suffixes).isdisjoint(VALIS_SUPPORTED_FILES):
        raise HTTPException(status_code=400, detail=f'File {filepath} is not yet a supported filetype.')

    return filepath


async def header(filename: str = Depends(get_filepath), ext: Ext = 0) -> dict:
    """ Dependency to retrieve a FITS header of a given HDU extension """
    with fits.open(filename) as hdu:
        yield hdu[ext].header


async def get_ext(filename: str = Depends(get_filepath), ext: Ext = 0):
    """ Dependency to get a FITS data, header """
    with fits.open(filename) as hdu:
        data = hdu[ext].data
        # convert binary table data into a dictionary
        if not hdu[ext].is_image:
            data = dict(zip(hdu[ext].data.columns.names, zip(*hdu[ext].data)))
        yield data, hdu[ext].header


# image/table hdu
def stream_bytes(data):
    yield numpy_to_bytes(data)


# image hdu
def stream_image_json(data):
    yield orjson.dumps(data, option=orjson.OPT_SERIALIZE_NUMPY, default=npdefault)


# imagehdu
def stream_image_csv(data):
    ii = StringIO()
    if 'float' in data.dtype.name:
        p = np.finfo(data.dtype).precision
    fmap = {'int16': '%d', 'int32': '%d', 'int64': '%d', 'float16': f'%.{p+1}f',
            'float32': f'%.{p+1}f', 'float64': f'%.{p+1}f', 'str': '%s'}
    fmt = fmap.get(data.dtype.name, '%s')
    np.savetxt(ii, data, delimiter=',', fmt=fmt)
    yield ii.getvalue()


# table hdu
def stream_table_json(data):
    yield orjson.dumps(data.tolist(), option=orjson.OPT_SERIALIZE_NUMPY, default=npdefault)


# table hdu
def stream_table_csv(data):
    ii = StringIO()
    t = Table(data)
    try:
        t.write(ii, format='ascii.csv')
    except ValueError:
        t.write(ii, format='ascii.ecsv')

    yield ii.getvalue()


class StreamFormat(str, Enum):
    """ A set of pre-defined choices for the stream format query param """
    json = "json"
    csv = "csv"
    bytes = "bytes"


async def get_stream(filename: str = Depends(get_filepath), ext: Ext = 0,
                     format: StreamFormat = 'json'):
    """ Dependency to stream FITS data """
    with fits.open(filename) as hdu:
        data = hdu[ext].data
        is_image = hdu[ext].is_image

        if format == 'json':
            media = 'application/json'
            stream = stream_image_json(data) if is_image else stream_table_json(data)
        elif format == 'csv':
            media = 'text/csv'
            stream = stream_image_csv(data) if is_image else stream_table_csv(data)
        else:
            media = 'application/octet-stream'
            stream = stream_bytes(data)

        return stream, media


def npdefault(obj):
    """ Custom default function for orjson numpy array serialization

    orjson < 3.8 does not support np.int16. Support added
    in >3.8, but still does not support string arrays

    """
    if isinstance(obj, np.ndarray):
        if obj.dtype.type == np.str_:
            # for numpy string arrays
            return obj.tolist()
    elif isinstance(obj, bytes):
        return obj.decode()
    raise TypeError


def numpy_to_bytes(arr: np.array, sep: str = '|') -> bytes:
    """ Convert numpy data to bytes """
    arr_dtype = bytearray(str(arr.dtype), 'utf-8')
    arr_shape = bytearray(','.join([str(a) for a in arr.shape]), 'utf-8')
    sep = bytearray(sep, 'utf-8')
    arr_bytes = arr.ravel().tobytes()
    return bytes(arr_dtype + sep + arr_shape + sep + arr_bytes)


def bytes_to_numpy(serialized_arr: bytes, sep: str = '|', record=False) -> np.array:
    """ Convert bytes data back to numpy"""
    sep = sep.encode('utf-8')
    i_0 = serialized_arr.find(sep)
    i_1 = serialized_arr.find(sep, i_0 + 1)
    arr_dtype = serialized_arr[:i_0].decode('utf-8')
    arr_shape = tuple(
        int(a)
        for a in serialized_arr[i_0 + 1:i_1].decode('utf-8').split(',')
    )
    arr_str = serialized_arr[i_1 + 1:]

    # for normal numpy ndarrays i.e. ImageHDUs
    if not record:
        return np.frombuffer(arr_str, dtype=arr_dtype).reshape(arr_shape)

    # for numpy.records i.e. BinTableHDUs
    dd = np.dtype((np.record, ast.literal_eval(arr_dtype[arr_dtype.find('['):-1])))
    return np.frombuffer(arr_str, dtype=dd)


class ORJSONResponseCustom(ORJSONResponse):
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


class FileResponseModel(BaseModel):
    """ Response for file data endpoint"""
    header: dict = None
    comments: dict = None
    data: dict = None


class FileInfoModel(BaseModel):
    """ Response for file info endpoint """
    info: List[str]


@cbv(router)
class Files(Base):

    @router.get("/", summary='Default endpoint.  Does nothing.', response_model=dict)
    async def get_file(self):
        """ Default endpoint """
        return {"info": "this route is for files"}

    @router.get("/{name}/download", summary='Download an SDSS file')
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

    @router.get("/{name}/info", summary='Retrieve information on a FITS file',
                response_model=FileInfoModel)
    async def get_info(self, filename: str = Depends(get_filepath)):
        """ Return the output from FITS hdu.info """
        s = StringIO()
        with fits.open(filename) as hdu:
            hdu.info(output=s)
            s.seek(0)
            ee = s.read()
            info = ee.split('\n')
            return {"info": info}

    @router.get("/{name}/header", summary='Retrieve a FITS file header',
                response_model=FileResponseModel, response_model_exclude_unset=True)
    async def get_header(self, header: fits.Header = Depends(header)):
        """ Return a FITS header """
        return {"header": dict(header.items()), 'comments': {k: header.comments[k] for k in header}}

    @router.get("/{name}/data", summary='Retrieve FITS file data.  Loads entire data into memory.',
                response_model=FileResponseModel, response_model_exclude_unset=True)
    async def get_filedata(self, fitsext: tuple = Depends(get_ext),
                           header: bool = Query(True, description='Flag to return header info or not.')):
        """ Return file data content to the client """
        # extract the FITS data
        data, hdr = fitsext
        # return a response
        results = {'header': dict(hdr.items()) if header else None, 'data': data}
        return ORJSONResponseCustom(content=results, option=orjson.OPT_SERIALIZE_NUMPY, default=npdefault)

    @router.get("/{name}/stream", summary='Stream FITS file data to the client')
    async def stream_filedata(self, streamdata: tuple = Depends(get_stream)):
        """ Stream file data content to the client """
        stream, media = streamdata
        return StreamingResponse(stream, media_type=media)


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

