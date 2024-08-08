# !/usr/bin/env python
# -*- coding: utf-8 -*-
#

# all resuable Pydantic models of the ORMs go here

import datetime
import math
from typing import Optional, Annotated, Any, TypeVar
from pydantic import ConfigDict, BaseModel, Field, BeforeValidator, FieldSerializationInfo, field_serializer, field_validator, FieldValidationInfo
from enum import Enum


def coerce_nan_to_none(x: Any) -> Any:
    if x and math.isnan(x):
        return None
    return x

T = TypeVar('T')

FloatNaN = Annotated[Optional[T], BeforeValidator(coerce_nan_to_none)]

# for how to specify required, optional, default, etc, see
# https://docs.pydantic.dev/latest/migration/#required-optional-and-nullable-fields


class OrmBase(BaseModel):
    """ Base pydantic model for sqlalchemy ORMs """
    model_config = ConfigDict(from_attributes=True)


class PeeweeBase(OrmBase):
    """ Base pydantic model for peewee ORMs """
    model_config = ConfigDict(from_attributes=True)


# class SDSSidStackedBaseA(OrmBase):
#     """ Pydantic response model for the SQLA vizdb.SDSSidStacked ORM """

#     sdss_id: int = Field(..., description='the SDSS identifier')
#     ra_sdss_id: float = Field(..., description='Right Ascension of the most recent cross-match catalogid')
#     dec_sdss_id: float = Field(..., description='Declination of the most recent cross-match catalogid')
#     catalogid21: Optional[int] = Field(description='the version 21 catalog id')
#     catalogid25: Optional[int] = Field(description='the version 25 catalog id')
#     catalogid31: Optional[int] = Field(description='the version 31 catalog id')


class SDSSidStackedBase(PeeweeBase):
    """ Pydantic response model for the Peewee vizdb.SDSSidStacked ORM """

    sdss_id: Optional[int] = Field(..., description='the SDSS identifier')
    ra_sdss_id: Optional[float] = Field(..., description='Right Ascension of the most recent cross-match catalogid')
    dec_sdss_id: Optional[float] = Field(..., description='Declination of the most recent cross-match catalogid')
    catalogid21: Optional[int] = Field(None, description='the version 21 catalog id')
    catalogid25: Optional[int] = Field(None, description='the version 25 catalog id')
    catalogid31: Optional[int] = Field(None, description='the version 31 catalog id')


class SDSSidFlatBase(PeeweeBase):
    """ Pydantic response model for the Peewee vizdb.SDSSidFlat ORM """

    sdss_id: int = Field(..., description='the SDSS identifier')
    ra_sdss_id: float = Field(..., description='Right Ascension of the most recent cross-match catalogid')
    dec_sdss_id: float = Field(..., description='Declination of the most recent cross-match catalogid')
    catalogid: int = Field(..., description='the catalogid associated with the given sdss_id')
    version_id: Optional[int] = Field(None, description='the version of the catalog for a given catalogid')
    n_associated: int = Field(..., description='The total number of sdss_ids associated with that catalogid.')
    ra_catalogid: Optional[float] = Field(None, description='Right Ascension, in degrees, specific to the catalogid')
    dec_catalogid: Optional[float] = Field(None, description='Declination, in degrees, specific to the catalogid')


class SDSSidPipesBase(PeeweeBase):
    """ Pydantic response model for the Peewee vizdb.SDSSidToPipes ORM """

    sdss_id: int = Field(..., description='the SDSS identifier')
    in_boss: bool = Field(..., description='Flag if target is in the BHM reductions', examples=[False])
    in_apogee: bool = Field(..., description='Flag if target is in the MWM reductions', examples=[False])
    in_astra: bool = Field(..., description='Flag if the target is in the Astra reductions', examples=[False])
    has_been_observed: Optional[bool] = Field(False, validate_default=True, description='Flag if target has been observed or not', examples=[False])

    @field_validator('has_been_observed')
    @classmethod
    def is_observed(cls, v: str, info: FieldValidationInfo) -> str:
        """ validator for when has_been_observed was not available in table """
        if not v:
            return info.data['in_boss'] or info.data['in_apogee'] or info.data['in_astra']
        return v

class SDSSModel(SDSSidStackedBase, SDSSidPipesBase):
    """ Main Pydantic response for SDSS id plus Pipes flags """
    pass


class BossSpectrum(PeeweeBase):
    """ Pydantic response model for the BHM pipeline metadata """
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

class AstraSource(PeeweeBase):
    """ Pydantic response model for the MWM Astra source metadata """
    sdss_id: int = None
    sdss4_apogee_id: Optional[int] = None
    gaia_dr2_source_id: Optional[int] = None
    gaia_dr3_source_id: Optional[int] = None
    tic_v8_id: Optional[int] = None
    healpix: int = None
    n_associated: int = None
    n_neighborhood: int = None
    sdss4_apogee_target1_flags: int = None
    sdss4_apogee_target2_flags: int = None
    sdss4_apogee2_target1_flags: int = None
    sdss4_apogee2_target2_flags: int = None
    sdss4_apogee2_target3_flags: int = None
    sdss4_apogee_member_flags: int = None
    sdss4_apogee_extra_target_flags: int = None
    ra: float = None
    dec: float = None
    n_boss_visits: int = None
    n_apogee_visits: int = None
    l: float = None
    b: float = None
    ebv: float = None
    e_ebv: float = None
    gaia_v_rad: FloatNaN[float] = None
    gaia_e_v_rad: FloatNaN[float] = None
    g_mag: FloatNaN[float] = None
    bp_mag: FloatNaN[float] = None
    rp_mag: FloatNaN[float] = None
    j_mag: FloatNaN[float] = None
    e_j_mag: FloatNaN[float] = None
    h_mag: FloatNaN[float] = None
    e_h_mag: FloatNaN[float] = None
    k_mag: FloatNaN[float] = None
    e_k_mag: FloatNaN[float] = None

class ApogeeStar(PeeweeBase):
    """ Pydantic response model for the MWM Apogee DRP pipeline star metadata """
    apogee_id: str = None
    file: str = None
    uri: str = None
    starver: int = None
    mjdbeg: int = None
    mjdend: int = None
    telescope: str = None
    apred_vers: str = None
    healpix: int = None
    snr: float = None
    ra: float = None
    dec: float = None
    glon: float = None
    glat: float = None
    jmag: float = None
    jerr: float = None
    hmag: float = None
    herr: float = None
    kmag: float = None
    kerr: float = None
    src_h: str = None
    apogee_target1: int = None
    apogee_target2: int = None
    apogee2_target1: int = None
    apogee2_target2: int = None
    apogee2_target3: int = None
    apogee2_target4: int = None
    catalogid: int = None
    gaiadr2_sourceid: int = None
    firstcarton: str = None
    targflags: str = None
    nvisits: int = None
    ngoodvisits: int = None
    ngoodrvs: int = None
    starflag: int = None
    starflags: str = None

class CatalogModel(PeeweeBase):
    """ Pydantic model for source catalog information """
    catalogid: int
    version: int
    lead: str
    ra: float
    dec: float
    pmra: Optional[float] = None
    pmdec: Optional[float] = None
    parallax: Optional[float] = None


class CatalogResponse(CatalogModel, SDSSidFlatBase):
    """ Response model for source catalog and sdss_id information """

    parent_catalogs: dict[str, Any] = Field(..., description='The parent catalog associations for a given catalogid')

    @field_serializer('parent_catalogs')
    def serialize_parent_catalogs(v: dict[str, Any], info: FieldSerializationInfo) -> dict[str, Any]:
        """ Serialize the parent catalogs, excluding None values and trimming strings."""

        if info.exclude_none:
            return {k: v.strip() if isinstance(v, str) else v for k, v in v.items() if v is not None}
        else:
            return v


class CartonModel(PeeweeBase):
    """ Response model for target and carton information """
    catalogid: int
    version: int
    ra: float
    dec: float
    pmra: Optional[float] = None
    pmdec: Optional[float] = None
    parallax: Optional[float] = None
    epoch: float
    program: str
    carton: str
    category: int
    run_on: Optional[datetime.datetime] = None


class PipeFiles(BaseModel):
    """ Pydantic model for lists of files """
    boss: Optional[str] = None
    apogee: Optional[str] = None
    astra: Optional[str] = None


class PipesModel(PeeweeBase):
    """ Pydantic model for pipeline metadata """
    boss: Optional[BossSpectrum] = None
    apogee: Optional[ApogeeStar] = None
    astra: Optional[AstraSource] = None
    files: Optional[PipeFiles] = None


class DbMetadata(PeeweeBase):
    """ Pydantic response model for the db metadata """
    dbschema: str = Field(..., description='the database schema name', alias='schema')
    table_name: str = Field(..., description='the database table name')
    column_name: str = Field(..., description='the database column name')
    display_name: str = Field(..., description='a human-readable display name for the column')
    description: str = Field(..., description='a description of the database column')
    unit: Optional[str] = Field(None, description='the unit if any for the database column')
    sql_type: Optional[str] = Field(None, description='the data type of the column')


class MapperName(str, Enum):
    """Mapper names"""
    MWM: str = 'MWM'
    BHM: str = 'BHM'
    LVM: str = 'LVM'
