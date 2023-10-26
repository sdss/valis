
# !/usr/bin/env python
# -*- coding: utf-8 -*-
#

import orjson
import pathlib
from typing import List, Dict
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Query
from fastapi_restful.cbv import cbv
from fastapi.responses import FileResponse, RedirectResponse
from valis.routes.base import Base
from valis.routes.files import ORJSONResponseCustom

from sdss_access.path import Path

def read_json(path):
    with open(path, 'r') as f:
        lines = f.readlines()
        first = lines[0]
        mocorder = int(first.split('\n')[0].split('#MOCORDER ')[-1])
        data = orjson.loads("\n".join(lines[1:]))
        return {'order': mocorder, 'moc': data}


class MocModel(BaseModel):
    """ Model representing the output Moc.json file from Hipsgen-cat """
    order: int = Field(..., description='the depth of the MOC')
    moc: Dict[str, List[int]] = Field(..., description='the MOC data')


router = APIRouter()
@cbv(router)
class Mocs(Base):
    """ Endpoints for interacting with SDSS MOCs """
    name: str = 'sdss_moc'

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
    async def get_moc(self, survey: str):
        """ Preview an individual survey MOC """
        return f'/static/mocs/{self.release.lower()}/{survey}/'

    @router.get('/json', summary='Get the MOC file in JSON format')
    async def get_json(self, survey: str = Query(..., description='The SDSS survey name', examples=['manga'])) -> MocModel:
        """ Get the MOC file in JSON format """
        # temporarily affixing the access path to sdss5 sandbox until
        # we decide on real org for DRs, etc
        spath = Path(release='sdss5')

        self.check_path_name(spath, self.name)
        path = spath.full(self.name, release=self.release.lower(), survey=survey, ext='json')
        self.check_path_exists(spath, path)
        return ORJSONResponseCustom(content=read_json(path), option=orjson.OPT_SERIALIZE_NUMPY)

    @router.get('/fits', summary='Download the MOC file in FITs format')
    async def get_fits(self, survey: str = Query(..., description='The SDSS survey name', examples=['manga'])):
        """ Download the MOC file in FITs format """
        # temporarily affixing the access path to sdss5 sandbox
        # we decide on real org for DRs, etc
        spath = Path(release='sdss5')

        self.check_path_name(spath, self.name)
        path = spath.full(self.name, release=self.release.lower(), survey=survey.lower(), ext='fits')
        self.check_path_exists(spath, path)
        pp = pathlib.Path(path)
        name = f'{survey.lower()}_{pp.name}'
        return FileResponse(path, filename=name, media_type='application/fits')