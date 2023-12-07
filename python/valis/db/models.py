# !/usr/bin/env python
# -*- coding: utf-8 -*-
#

# all resuable Pydantic models of the ORMs go here

import peewee
from typing import Any, Optional
from pydantic import ConfigDict, BaseModel, Field
#from pydantic.utils import GetterDict


# class PeeweeGetterDict(GetterDict):
#     """ Class to convert peewee.ModelSelect into a list """
#     def get(self, key: Any, default: Any = None):
#         res = getattr(self._obj, key, default)
#         if isinstance(res, peewee.ModelSelect):
#             return list(res)
#         return res


class OrmBase(BaseModel):
    """ Base pydantic model for sqlalchemy ORMs """
    model_config = ConfigDict(from_attributes=True)


class PeeweeBase(OrmBase):
    """ Base pydantic model for peewee ORMs """
    # TODO[pydantic]: The following keys were removed: `getter_dict`.
    # Check https://docs.pydantic.dev/dev-v2/migration/#changes-to-config for more information.
    model_config = ConfigDict(from_attributes=True) #, getter_dict=PeeweeGetterDict)


# class SDSSidStackedBaseA(OrmBase):
#     """ Pydantic model for the SQLA vizdb.SDSSidStacked ORM """

#     sdss_id: int = Field(..., description='the SDSS identifier')
#     ra_sdss_id: float = Field(..., description='Right Ascension of the most recent cross-match catalogid')
#     dec_sdss_id: float = Field(..., description='Declination of the most recent cross-match catalogid')
#     catalogid21: Optional[int] = Field(description='the version 21 catalog id')
#     catalogid25: Optional[int] = Field(description='the version 25 catalog id')
#     catalogid31: Optional[int] = Field(description='the version 31 catalog id')


class SDSSidStackedBase(PeeweeBase):
    """ Pydantic model for the Peewee vizdb.SDSSidStacked ORM """

    sdss_id: int = Field(..., description='the SDSS identifier')
    ra_sdss_id: float = Field(..., description='Right Ascension of the most recent cross-match catalogid')
    dec_sdss_id: float = Field(..., description='Declination of the most recent cross-match catalogid')
    catalogid21: Optional[int] = Field(None, description='the version 21 catalog id')
    catalogid25: Optional[int] = Field(None, description='the version 25 catalog id')
    catalogid31: Optional[int] = Field(None, description='the version 31 catalog id')


class SDSSidFlatBase(PeeweeBase):
    """ Pydantic model for the Peewee vizdb.SDSSidFlat ORM """

    sdss_id: int = Field(..., description='the SDSS identifier')
    ra_sdss_id: float = Field(..., description='Right Ascension of the most recent cross-match catalogid')
    dec_sdss_id: float = Field(..., description='Declination of the most recent cross-match catalogid')
    catalogid: int = Field(..., description='the catalogid associated with the given sdss_id')
    version_id: int = Field(..., description='the version of the catalog for a given catalogid')
    n_associated: int = Field(..., description='The total number of sdss_ids associated with that catalogid.')
    ra_cat: float = Field(..., description='Right Ascension, in degrees, specific to the catalogid')
    dec_cat: float = Field(..., description='Declination, in degrees, specific to the catalogid')


class SDSSidPipesBase(PeeweeBase):
    """ Pydantic model for the Peewee vizdb.SDSSidToPipes ORM """

    sdss_id: int = Field(..., description='the SDSS identifier')
    in_boss: bool = Field(..., description='Flag if target is in the BHM reductions', examples=[False])
    in_apogee: bool = Field(..., description='Flag if target is in the MWM reductions', examples=[False])
    in_astra: bool = Field(..., description='Flag if the target is in the Astra reductions', examples=[False])


class BossSpectrum(PeeweeBase):
    sdss_id: int = None
    field: int = None
    mjd: int = None
    catalogid: int = None
    nexp: int = None
    exptime: float = None
    survey: str = None
    firstcarton: str = None
    objtype: str = None
    specobjid: int = None


class TargetMeta(SDSSidPipesBase, BossSpectrum):
    pass


# field': 101077,
#  'mjd': 59845,
#  'mjd_final': 59845.207,
#  'obs': 'APO',
#  'run2d': 'v6_1_1',
#  'run1d': 'v6_1_1',
#  'nexp': 4,
#  'exptime': 3600.0,
#  'target_index': 242,
#  'spec_file': 'spec-101077-59845-27021603187129892.fits',
#  'programname': 'ops_sky',
#  'survey': 'OPS',
#  'cadence': ' ',
#  'firstcarton': 'ops_sky_boss_good',
#  'sdss5_target_flags': <memory at 0x124360a00>,
#  'objtype': 'SKY',
#  'catalogid': 27021603187129892,
#  'sdss_id': 23326,
#  'specobjid': 3122187127310111744,