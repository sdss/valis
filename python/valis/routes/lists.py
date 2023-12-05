# !/usr/bin/env python
# -*- coding: utf-8 -*-
#

from enum import Enum
from typing import List, Union
from fastapi import APIRouter, Depends, Query
from fastapi_restful.cbv import cbv
from pydantic import BaseModel, Field

from valis.routes.base import Base
from valis.db.db import get_pw_db
from valis.db.models import SDSSidStackedBase, SDSSidPipesBase
from valis.db.queries import carton_program_list


class MainResponse(SDSSidPipesBase, SDSSidStackedBase):
    """ Combined model from all individual query models """


class MainSearchResponse(BaseModel):
    """ The main query response model """
    status: str = Field(..., description='the query return status')
    msg: str = Field(..., description='the response status message')
    data: List[MainResponse] = Field(..., description='the list of query results')


class SearchModel(BaseModel):
    """ Input main query body model """
    list_type: str = Field(..., description='Name of the search parameter to return a list of', example='carton')


router = APIRouter()


@cbv(router)
class QueryRoutes(Base):
    """ API routes for generating lists for query purposes """

    @router.post('/main', summary='Main query for the UI or combining list returns',
                 response_model=MainSearchResponse, dependencies=[Depends(get_pw_db)])
    async def main_search(self, body: SearchModel):
        """ Main query for UI and for combining queries together """
        print('form data', body)

        # gather the correct list
        if body.list_type in ['carton', 'program']:
            query = carton_program_list(body.list_type)
        else:
            raise ValueError("List choice not part of function options")

        return {'status': 'success', 'data': list(query.dicts()), 'msg': 'data successfully retrieved'}

    @router.get('/carton', summary='Return a list of all cartons',
                response_model=list, dependencies=[Depends(get_pw_db)])
    async def cartons(self,
                      name_type: str = Query('carton', enum=['carton'],
                                             description='Specify search on carton or program', example='carton')):
        """ Return a list of all cartons """
        return carton_program_list(name_type)

    @router.get('/program', summary='Return a list of all programs',
                response_model=list, dependencies=[Depends(get_pw_db)])
    async def programs(self,
                       name_type: str = Query('program', enum=['program'],
                                              description='Specify search on carton or program', example='program')):
        """ Return a list of all cartons """
        return carton_program_list(name_type)
