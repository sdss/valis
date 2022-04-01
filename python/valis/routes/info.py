# !/usr/bin/env python
# -*- coding: utf-8 -*-
#

from __future__ import print_function, division, absolute_import
from fastapi import APIRouter, HTTPException, Depends
from fastapi_utils.cbv import cbv

try:
    from datamodel.products import SDSSDataModel
except ImportError:
    SDSSDataModel = None

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


@cbv(router)
class DataModels(Base):

    @router.get("/", summary='Get general SDSS metadata')
    async def get_dm(self, dm: SDSSDataModel = Depends(get_datamodel)) -> dict:
        """ Retrieve general SDSS metadata """
        
        return {'description': 'General metadata for the Sloan Digital Sky Survey (SDSS)', 'phases': dm.phases.dict()['__root__'], 'surveys': dm.surveys.dict()['__root__'], 
                'releases': dm.releases.dict()['__root__']}

    @router.get("/releases", summary='Get metadata on SDSS releases')
    async def get_releases(self, dm: SDSSDataModel = Depends(get_datamodel)) -> dict:
        """ Retrieve a list of SDSS data releases """
        return {'releases': dm.releases.dict()['__root__']}

    @router.get("/phases", summary='Get metadata on SDSS phases')
    async def get_phases(self, dm: SDSSDataModel = Depends(get_datamodel)) -> dict:
        """ Retrieve a list of SDSS phases """
        return {'phases': dm.phases.dict()['__root__']}

    @router.get("/surveys", summary='Get metadata on SDSS surveys')
    async def get_surveys(self, dm: SDSSDataModel = Depends(get_datamodel)) -> dict:
        """ Retrieve a list of SDSS surveys """
        return {'surveys': dm.surveys.dict()['__root__']}
        
    @router.get("/products", summary='Get a list of SDSS data products', dependencies=[Depends(set_auth)])
    async def list_products(self, prods: list = Depends(get_products)) -> dict:
        """ Get a list of SDSS data products that have defined SDSS datamodels """
        return {'products': [p.name for p in prods]}

    @router.get("/products/{name}", summary='Retrieve a datamodel for an SDSS product', dependencies=[Depends(set_auth)])
    async def get_product(self, name: str, prods: list = Depends(get_products)) -> dict:
        """ Get the JSON datamodel for an SDSS data product """
        product = [i for i in prods if i.name == name]
        if not product:
            raise HTTPException(status_code=400, detail=f'{name} not found a valid SDSS data product for release {self.release}')
        return product[0].get_content()
