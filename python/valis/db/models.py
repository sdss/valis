# !/usr/bin/env python
# -*- coding: utf-8 -*-
#

import peewee
from typing import Any
from pydantic import BaseModel
from pydantic.utils import GetterDict


class PeeweeGetterDict(GetterDict):
    """ Class to convert peewee.ModelSelect into a list """
    def get(self, key: Any, default: Any = None):
        res = getattr(self._obj, key, default)
        if isinstance(res, peewee.ModelSelect):
            return list(res)
        return res


class OrmBase(BaseModel):
    """ Base pydantic model for ORMs """

    class Config:
        orm_mode = True


class PeeweeBase(OrmBase):
    """ Base pydantic model for Peewee ORMs """

    class Config:
        orm_mode = True
        getter_dict = PeeweeGetterDict


class SourceBase(PeeweeBase):
    source_id: int

    class Config:
        orm_mode = True


class ExpBase(PeeweeBase):
    exptime: float
    exptype: str

    class Config:
        orm_mode = True
        getter_dict = PeeweeGetterDict


class CubeBase(OrmBase):
    plateifu: str
    mangaid: str
    plate: int
    ra: float
    dec: float

    class Config:
        orm_mode = True
