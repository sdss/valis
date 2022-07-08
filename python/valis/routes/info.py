# !/usr/bin/env python
# -*- coding: utf-8 -*-
#

from __future__ import print_function, division, absolute_import

from typing import List, Union, Dict
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi_utils.cbv import cbv
from fastapi_utils.enums import StrEnum
from enum import auto
from pydantic import BaseModel, create_model

try:
    from datamodel.products import SDSSDataModel
    from datamodel.models.surveys import Phases, Surveys
    from datamodel.models.releases import Releases
    from datamodel.models.versions import Tags
    from datamodel.models.yaml import ProductModel
    SchemaModel = create_model("SchemaModel", **ProductModel.schema())
except ImportError:
    SDSSDataModel = None
    Phases = Surveys = Releases = Tags = ProductModel = SchemaModel = None

from valis.routes.base import Base, release
from valis.routes.auth import set_auth

router = APIRouter()

def get_datamodel():
    if not SDSSDataModel:
        raise HTTPException(status_code=400, detail='Error: SDSS datamodel product not available.')
    return SDSSDataModel()

def get_products(release: str = Depends(release), dm: SDSSDataModel = Depends(get_datamodel)):
    products = dm.products.group_by("releases")
    return products.get(release, [])

class InfoModel(BaseModel):
    """ Resposne model for info endpoint """
    description: str = None
    phases: Phases = None
    surveys: Surveys = None
    releases: Releases = None


class TagGroup(StrEnum):
    """ Enum for grouping SDSS software tags """
    release = auto()
    survey = auto()

class TagModel(BaseModel):
    """ Response model for SDSS software tags """
    tags: Union[Tags, Dict[str, Dict[str, dict]]] = None

class ProductResponse(BaseModel):
    """ Response model for SDSS product names """
    products: List[str]


@cbv(router)
class DataModels(Base):

    @router.get("/", summary='Get general SDSS metadata', response_model=InfoModel)
    async def get_dm(self, dm: SDSSDataModel = Depends(get_datamodel)) -> dict:
        """ Retrieve general SDSS metadata """

        return {'description': 'General metadata for the Sloan Digital Sky Survey (SDSS)',
                'phases': dm.phases.dict()['__root__'],
                'surveys': dm.surveys.dict()['__root__'],
                'releases': dm.releases.dict()['__root__']}

    @router.get("/releases", summary='Get metadata on SDSS releases', response_model=InfoModel, response_model_exclude_unset=True)
    async def get_releases(self, dm: SDSSDataModel = Depends(get_datamodel)) -> dict:
        """ Retrieve a list of SDSS data releases """
        return {'releases': dm.releases.dict()['__root__']}

    @router.get("/phases", summary='Get metadata on SDSS phases', response_model=InfoModel, response_model_exclude_unset=True)
    async def get_phases(self, dm: SDSSDataModel = Depends(get_datamodel)) -> dict:
        """ Retrieve a list of SDSS phases """
        return {'phases': dm.phases.dict()['__root__']}

    @router.get("/surveys", summary='Get metadata on SDSS surveys', response_model=InfoModel, response_model_exclude_unset=True)
    async def get_surveys(self, dm: SDSSDataModel = Depends(get_datamodel)) -> dict:
        """ Retrieve a list of SDSS surveys """
        return {'surveys': dm.surveys.dict()['__root__']}

    @router.get("/tags", summary='Get metadata on SDSS software tags', response_model=TagModel, response_model_exclude_unset=True)
    async def get_tags(self, group: TagGroup = Query(None, description='group the tags by release or survey'),
                       dm: SDSSDataModel = Depends(get_datamodel)) -> dict:
        """ Retrieve a dictionary of SDSS software tags """
        if group == 'release':
            return {'tags': dm.tags.group_by('release')}
        elif group == 'survey':
            return {'tags': dm.tags.group_by('survey')}
        else:
            return {'tags': dm.tags.dict()['__root__']}

    @router.get("/products", summary='Get a list of SDSS data products', dependencies=[Depends(set_auth)], response_model=ProductResponse)
    async def list_products(self, prods: list = Depends(get_products)) -> dict:
        """ Get a list of SDSS data products that have defined SDSS datamodels """
        return {'products': [p.name for p in prods]}

    @router.get("/products/{name}", summary='Retrieve a datamodel for an SDSS product', dependencies=[Depends(set_auth)], response_model=ProductModel)
    async def get_product(self, name: str, prods: list = Depends(get_products)) -> dict:
        """ Get the JSON datamodel for an SDSS data product """
        product = [i for i in prods if i.name == name]
        if not product:
            raise HTTPException(status_code=400, detail=f'{name} not found a valid SDSS data product for release {self.release}')
        return product[0].get_content(by_alias=True)

    @router.get("/schema/{name}", summary='Retrieve the datamodel schema for an SDSS product', dependencies=[Depends(set_auth)], response_model=SchemaModel)
    async def get_schema(self, name: str, prods: list = Depends(get_products)) -> dict:
        """ Get the Pydantic schema describing an SDSS product """
        product = [i for i in prods if i.name == name]
        if not product:
            raise HTTPException(status_code=400, detail=f'{name} not found a valid SDSS data product for release {self.release}')
        return product[0].get_schema()
