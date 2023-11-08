from __future__ import print_function, division, absolute_import

import os
import pathlib
import numpy as np
from typing import List, Union, Dict

from astropy.table import Table
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi_restful.cbv import cbv
from pydantic import BaseModel, Field

from valis.io.yanny import yanny
from valis.exceptions import ValisError
from valis.routes.base import Base

router = APIRouter()


def get_file() -> pathlib.Path:
    """ Get the path to the sdssMaskbits.par file

    Get the path to the sdssMaskbits.par file from either
    the GIT or SVN respository path.  If both paths exist,
    then use the filepath with the most recent modification time.

    Returns
    -------
    pathlib.Path
        A path to the maskbits file

    Raises
    ------
    HTTPException
        when no masktbits file is found
    """
    git_mask = pathlib.Path(os.path.expandvars('$SDSS_GIT_ROOT')) / 'idlutils/master/data/sdss/sdssMaskbits.par'
    svn_mask = pathlib.Path(os.path.expandvars('$SDSS_SVN_ROOT')) / 'repo/sdss/idlutils/trunk/data/sdss/sdssMaskbits.par'

    if git_mask.exists() and svn_mask.exists():
        # return file with the most recent modification time
        return git_mask if git_mask.stat().st_mtime > svn_mask.stat().st_mtime else svn_mask
    elif git_mask.exists() and not svn_mask.exists():
        return git_mask
    elif svn_mask.exists() and not git_mask.exists():
        return svn_mask
    else:
        raise HTTPException(status_code=404, detail='Could not find a valid sdssMaskbits.par file. Check proper file paths.')


def read_maskbits(path: pathlib.Path = Depends(get_file)) -> np.recarray:
    """ Read the maskbits yanny file

    Read the sdssMasbits.par file with the yanny reader.

    Parameters
    ----------
    path : pathlib.Path, optional
        the path to the maskbits file.

    Returns
    -------
    np.recarray
        the "MASKBITS" data entry

    Raises
    ------
    HTTPException
        when the file cannot be read
    """
    try:
        data = yanny(str(path))
    except ValisError as e:
        raise HTTPException(status_code=400, detail=f'{e}') from e
    else:
        return data['MASKBITS']


def make_table(schema: str = Query(..., description='The name of the SDSS flag',
                                   example='MANGA_DRP2QUAL'), masks: np.recarray = Depends(read_maskbits)):
    """ Dependency to return an Astropy Table from the maskbits data

    _extended_summary_

    Parameters
    ----------
    schema : str, optional
        _description_, by default Query(..., description='The name of the SDSS flag', example='MANGA_DRP2QUAL')
    masks : np.recarray, optional
        _description_, by default Depends(read_maskbits)

    Returns
    -------
    _type_
        _description_
    """
    tt = Table(masks)
    return tt[tt["flag"] == schema] if schema else tt


class MaskBitResponse(BaseModel):
    """ The response object for the maskbits endpoint """
    flags: list = Field([], alias='schema', description='A list of SDSS flags')
    value: int = Field(None, description='The maskbit value')
    labels: List[str] = Field(None, description='A list of mask labels')
    bits: List[int] = Field(None, description='A list of integer mask bits')


class MaskSchema(BaseModel):
    """ SDSS maskbit schema response model """
    bit: List[int] = Field(None, description='A list of integer mask bits')
    label: List[str] = Field(None, description='A list of mask labels')
    description: List[str] = Field(None, description='A list of mask descriptions')


@cbv(router)
class Maskbits(Base):
    """ API routes for interacting with SDSS maskbits, defined in sdssMaskbits.par """

    @router.get("/list", summary='List the available maskbits schema / flags',
                response_model=MaskBitResponse, response_model_exclude_unset=True)
    async def get_schema(self, masks=Depends(read_maskbits)) -> dict:
        """ Get a list of available SDSS maskbits schema or flag names """

        return {"schema": sorted({i[0].decode('utf-8') for i in masks})}

    @router.get("/schema", summary='Get the maskbits for a given schema / flag',
                response_model=Dict[str, MaskSchema])
    async def get_bits(self, schema: str, tab: Table = Depends(make_table)) -> dict:
        """ Get the SDSS maskbit schema for a given flag name """

        return {schema: {c: tab[c].tolist() for c in tab.columns if c != 'flag'}}

    @router.get("/bits/value", summary='Convert a list of bits into a maskbit value',
                response_model=MaskBitResponse, response_model_exclude_unset=True)
    async def bits_to_value(self, bits: Union[List[int], None] = Query([], description='A list of integer bits', example=[2, 8])) -> dict:
        """ Convert a list of integer bits into a maskbit value"""
        print('bits', bits, type(bits))
        return {'value': sum(1 << int(i) for i in bits)}

    @router.get("/bits/labels", summary='Convert a list of bits into their labels',
                response_model=MaskBitResponse, response_model_exclude_unset=True)
    async def bits_to_labels(self, bits: Union[List[int], None] = Query([], description='A list of integer bits', example=[2, 8]),
                             tab: Table = Depends(make_table)) -> dict:
        """ Convert a list of integer bits into their labels for a given schema """

        tab.add_index('bit')
        try:
            labels = tab.loc['bit', bits]["label"]
        except KeyError as e:
            raise HTTPException(status_code=400, detail=f'{e}') from e
        else:
            return {'labels': labels.tolist()}

    @router.get("/labels/value", summary='Convert a list of labels into a maskbit value',
                response_model=MaskBitResponse, response_model_exclude_unset=True)
    async def labels_to_value(self, labels: Union[List[str], None] = Query([], description='A list of mask labels', example=['BADIFU', 'SCATFAIL']),
                              tab: Table = Depends(make_table)) -> dict:
        """ Convert a list of mask labels into a maskbit value for a given schema """

        labels = [l.upper() for l in labels]
        tab.add_index('label')
        try:
            bits = tab.loc['label', labels]["bit"]
        except KeyError as e:
            raise HTTPException(status_code=400, detail=f'{e}') from e
        else:
            return {'value': sum(1 << int(i) for i in bits)}

    @router.get("/labels/bits", summary='Convert a list of labels into their bits',
                response_model=MaskBitResponse, response_model_exclude_unset=True)
    async def labels_to_bits(self, labels: Union[List[str], None] = Query([], description='A list of mask labels', example=['BADIFU', 'SCATFAIL']),
                             tab: Table = Depends(make_table)) -> dict:
        """ Convert a list of mask labels into their respective bits for a given schema """

        labels = [l.upper() for l in labels]
        tab.add_index('label')
        try:
            bits = tab.loc['label', labels]["bit"]
        except KeyError as e:
            raise HTTPException(status_code=400, detail=f'{e}') from e
        else:
            return {'bits': bits.tolist()}

    @router.get("/value/bits", summary='Decompose a maskbit value into a list of bits',
                response_model=MaskBitResponse, response_model_exclude_unset=True)
    async def value_to_bits(self, value: int = Query(..., description='A maskbit value', example=260), tab: Table = Depends(make_table)) -> dict:
        """ Decompose a maskbit value into its list of bits for a given schema """

        bits = tab['bit']
        return {'bits': [int(i) for i in bits if value & 1 << int(i)]}

    @router.get("/value/labels", summary='Decompose a maskbit value into a list of labels',
                response_model=MaskBitResponse, response_model_exclude_unset=True)
    async def value_to_labels(self, value: int = Query(..., description='A maskbit value', example=260), tab: Table = Depends(make_table)) -> dict:
        """ Decompose a maskbit value into its list of labels for a given schema """

        bits = [int(i) for i in tab['bit'] if value & 1 << int(i)]
        tab.add_index('bit')
        try:
            labels = tab.loc['bit', bits]["label"]
        except KeyError as e:
            raise HTTPException(status_code=400, detail=f'{e}') from e
        else:
            return {'labels': labels.tolist()}