
# !/usr/bin/env python
# -*- coding: utf-8 -*-
#

import orjson
import os
import pathlib
import re
from typing import List, Dict, Annotated
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Query
from fastapi_restful.cbv import cbv
from fastapi.responses import FileResponse, RedirectResponse
from valis.routes.base import Base
from valis.routes.files import ORJSONResponseCustom

from sdss_access.path import Path

def read_json(path: str) -> dict:
    """ Read a MOC.json file """
    with open(path, 'r') as f:
        lines = f.readlines()
        first = lines[0]
        if "MOCORDER" in first:
            # written by Hipsgen-cat
            mocorder = int(first.split('\n')[0].split('#MOCORDER ')[-1])
            sub = lines[1:]
        else:
            # written by MOCpy
            mocorder = int(max(map(int,re.findall(r'"(.*?)":', '\n'.join(lines)))))
            sub = lines
        data = orjson.loads("\n".join(sub))
        return {'order': mocorder, 'moc': data}


class MocModel(BaseModel):
    """ Model representing the output Moc.json file from Hipsgen-cat """
    order: int = Field(..., description='the depth of the MOC')
    moc: Dict[str, List[int]] = Field(..., description='the MOC data')


router = APIRouter()
@cbv(router)
class Mocs(Base):
    """ Endpoints for interacting with SDSS MOCs """

    def check_path_name(self, path, name: str):
        """ temp function until sort out directory org for """
        names = path.lookup_names()
        if name not in names:
            raise HTTPException(status_code=422, detail=f'path name {name} not in release.')

    def check_path_exists(self, spath, path: str):
        """ temp function until sort out directory org for """
        if not spath.exists('', full=path):
            raise HTTPException(status_code=422, detail=f'path {path} does not exist on disk.')

    @router.get('/preview', summary='Preview an individual survey MOC', response_class=RedirectResponse)
    async def get_moc(self, survey: Annotated[str, Query(..., description='The SDSS survey name')] = 'manga'):
        """ Preview an individual survey MOC """
        return f'/static/mocs/{self.release.lower()}/{survey}/'

    @router.get('/json', summary='Get the MOC file in JSON format')
    async def get_json(self, survey: Annotated[str, Query(..., description='The SDSS survey name')] = 'manga') -> MocModel:
        """ Get the MOC file in JSON format """
        # temporarily affixing the access path to sdss5 sandbox until
        # we decide on real org for DRs, etc
        spath = Path(release='sdsswork')

        self.check_path_name(spath, 'sdss_moc')
        path = spath.full('sdss_moc', release=self.release.lower(), survey=survey, ext='json')
        self.check_path_exists(spath, path)
        return ORJSONResponseCustom(content=read_json(path), option=orjson.OPT_SERIALIZE_NUMPY)

    @router.get('/fits', summary='Download the MOC file in FITs format')
    async def get_fits(self, survey: Annotated[str, Query(..., description='The SDSS survey name')] = 'manga'):
        """ Download the MOC file in FITs format """
        # temporarily affixing the access path to sdss5 sandbox
        # we decide on real org for DRs, etc
        spath = Path(release='sdsswork')

        self.check_path_name(spath, 'sdss_moc')
        path = spath.full('sdss_moc', release=self.release.lower(), survey=survey.lower(), ext='fits')
        self.check_path_exists(spath, path)
        pp = pathlib.Path(path)
        name = f'{survey.lower()}_{pp.name}'
        return FileResponse(path, filename=name, media_type='application/fits')

    @router.get('/list', summary='List the available MOCs')
    async def list_mocs(self) -> list[str]:
        """ List the available MOCs """
        Path(release='sdsswork')
        mocs = sorted(set([':'.join(i.parent.parts[-2:]) for i in pathlib.Path(os.getenv("SDSS_HIPS")).rglob('Moc.fits')]))
        return mocs
