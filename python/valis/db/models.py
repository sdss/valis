# !/usr/bin/env python
# -*- coding: utf-8 -*-
#

import peewee
from typing import Any, Optional
from pydantic import BaseModel, Field
from pydantic.utils import GetterDict


class PeeweeGetterDict(GetterDict):
    """ Class to convert peewee.ModelSelect into a list """
    def get(self, key: Any, default: Any = None):
        res = getattr(self._obj, key, default)
        if isinstance(res, peewee.ModelSelect):
            return list(res)
        return res


class OrmBase(BaseModel):
    """ Base pydantic model for sqlalchemy ORMs """

    class Config:
        orm_mode = True


class PeeweeBase(OrmBase):
    """ Base pydantic model for peewee ORMs """

    class Config:
        orm_mode = True
        getter_dict = PeeweeGetterDict


class SDSSidStackedBase(PeeweeBase):
    """ Pydantic model for the SQLA vizdb.SDSSidStacked ORM """

    sdss_id: int = Field(..., description='the SDSS identifier')
    ra_sdss_id: float = Field(..., description='Right Ascension of the most recent cross-match catalogid')
    dec_sdss_id: float = Field(..., description='Declination of the most recent cross-match catalogid')
    catalogid21: Optional[int] = Field(description='the version 21 catalog id')
    catalogid25: Optional[int] = Field(description='the version 25 catalog id')
    catalogid31: Optional[int] = Field(description='the version 31 catalog id')


class SDSSidFlatBase(PeeweeBase):
    """ Pydantic model for the SQLA vizdb.SDSSidFlat ORM """

    sdss_id: int = Field(..., description='the SDSS identifier')
    ra_sdss_id: float = Field(..., description='Right Ascension of the most recent cross-match catalogid')
    dec_sdss_id: float = Field(..., description='Declination of the most recent cross-match catalogid')
    catalogid: int = Field(..., descrption='the catalogid associated with the given sdss_id')
    version_id: int = Field(..., descrption='the version of the catalog for a given catalogid')
    n_associated: int = Field(..., description='The total number of sdss_ids associated with that catalogid.')
    ra_cat: float = Field(..., descrption='Right Ascension, in degrees, specific to the catalogid')
    dec_cat: float = Field(..., descrption='Declination, in degrees, specific to the catalogid')


class SDSSidPipesBase(PeeweeBase):
    """ Pydantic model for the SQLA vizdb.SDSSidToPipes ORM """

    sdss_id: int = Field(..., description='the SDSS identifier')
    in_boss: bool = Field(..., description='Flag if the sdss_id is in the BHM reductions')
    in_apogee: bool = Field(..., description='Flag if the sdss_id is in the Apogee/MWM reductions')
    in_astra: bool = Field(..., description='Flag if the sdss_id is in the Astra reductions')

