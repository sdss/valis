# !/usr/bin/env python
# -*- coding: utf-8 -*-
#

# all resuable Pydantic models of the ORMs go here

import datetime
import math
from typing import Optional, Annotated, Any, TypeVar
from pydantic_core import to_jsonable_python
from pydantic import (ConfigDict, BaseModel, Field, BeforeValidator, FieldSerializationInfo, field_serializer,
                      field_validator, FieldValidationInfo, model_serializer, computed_field)

from valis.routes.maskbits import mask_values_to_labels
from valis.db.queries import has_legacy_data
from valis.exceptions import ValisError
from valis.utils.paths import build_legacy_path


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
    #catalogid31: Optional[int] = Field(None, description='the version 31 catalog id')  # TODO - uncomment when v1 crossmatch is made public
    last_updated: datetime.date = Field(None, description='the date the sdss_id row was last updated', exclude=True)

    @field_serializer('last_updated')
    def serialize_dt(self, date: datetime.date) -> str:
        return date.isoformat()


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
    rank: int = Field(..., description='Ranking when catalogid paired to multiple sdss_id, with rank 1 as priority.')

class SDSSidPipesBase(PeeweeBase):
    """ Pydantic response model for the Peewee vizdb.SDSSidToPipes ORM """

    sdss_id: int = Field(..., description='the SDSS identifier')
    in_boss: bool = Field(..., description='Flag if target is in the BHM reductions', examples=[False])
    in_apogee: bool = Field(..., description='Flag if target is in the MWM reductions', examples=[False])
    in_bvs: bool = Field(..., description='Flag if target is in the boss component of the Astra reductions', examples=[False], exclude=True)
    in_astra: bool = Field(..., description='Flag if the target is in the Astra reductions', examples=[False])
    has_been_observed: Optional[bool] = Field(False, validate_default=True, description='Flag if target has been observed or not', examples=[False])
    release: Optional[str] = Field(None, description='the Astra release field, either sdss5 or dr17')
    obs: Optional[str] = Field(None, description='the observatory the observation is from')
    mjd: Optional[int] = Field(None, description='the MJD of the data reduction')

    @field_validator('has_been_observed')
    @classmethod
    def is_observed(cls, v: str, info: FieldValidationInfo) -> str:
        """ validator for when has_been_observed was not available in table """
        if not v:
            return info.data.get('in_boss') or info.data.get('in_apogee') or info.data.get('in_astra')
        return v

class SDSSModel(SDSSidStackedBase, SDSSidPipesBase):
    """ Main Pydantic response for SDSS id plus Pipes flags """
    distance: Optional[float] = Field(None, description='Separation distance between input target and cone search results, in degrees')

    @computed_field(description='Flag if the target has legacy SDSS data available')
    @property
    def has_legacy_data(self) -> bool:
        return has_legacy_data(self.sdss_id)


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
    specobjid: Optional[int] = None
    z: Optional[float] = None
    zwarning: Optional[int|str] = None
    objclass: Optional[str] = None
    subclass: Optional[str] = None
    sn_median_all: Optional[float] = None
    on_target: Optional[bool] = None
    fiber_ra: Optional[float] = None
    fiber_dec: Optional[float] = None

    @field_serializer('zwarning')
    def serialize_zwarning(self, value: Optional[int|str]) -> Optional[str]:
        """ serialize the zwarning maskbits to their labels"""
        if value == 0:
            return ''

        try:
            labels = mask_values_to_labels(schema='ZWARNING', value=value)
        except ValisError:
            return str(value)
        else:
            return ', '.join(labels['labels'])


class AstraSource(PeeweeBase):
    """ Pydantic response model for the MWM Astra source metadata """
    sdss_id: int = None
    catalogid: int = None
    sdss4_apogee_id: Optional[str] = None
    gaia_dr2_source_id: Optional[int] = None
    gaia_dr3_source_id: Optional[int] = None
    tic_v8_id: Optional[int] = None
    healpix: int = None
    n_associated: Optional[int] = None
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
    n_boss_visits: Optional[int] = None
    n_apogee_visits: Optional[int] = None
    l: float = None
    b: float = None
    ebv: Optional[float] = None
    e_ebv: Optional[float] = None
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


class ParentCatalogModel(PeeweeBase):
    """Pydantic model for parent catalog information """

    sdss_id: Annotated[int, Field(description='The sdss_id associated with the parent catalogue data')]
    catalogid: Annotated[int, Field(description='The catalogid associated with the parent catalogue data')]

    # This model is usually instantiated with a dictionary of all the parent
    # catalogue columns so we allow extra fields.
    model_config = ConfigDict(extra='allow')

    @model_serializer(mode='wrap')
    def _dump(self, handler):
        # serializer to handle the extra fields that are Decimal
        # wrap mode wraps the default serialization logic vs replace, pydantic default serializes Decimal to str
        data = handler(self)  # includes extras in model_extra
        return to_jsonable_python(data, fallback=str)

class CatalogResponse(CatalogModel, SDSSidFlatBase):
    """ Response model for source catalog and sdss_id information """

    parent_catalogs: dict[str, Any] = Field(..., description='The parent catalog associations for a given catalogid')

    @field_serializer('parent_catalogs')
    def serialize_parent_catalogs(self, v: dict[str, Any], info: FieldSerializationInfo) -> dict[str, Any]:
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
    astra: Optional[list[str]] = None


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



def gen_misc_models():
    """ Generate metadata info for miscellaneous return columns

    This is a hack to handle cases where we return columns in search
    results that are not part of the original pipelines database ORM
    but we want to have the same metadata like "display_name" and
    "description".  For example, the "distance" column returned by cone
    searches, as part of the SDSSModel response.  This fakes the metadata
    framework so the front-end can use the same code. See usage for the
    info/database endpoint in "convert_metadata".

    Fakes a "misc" database schema and "misctab" table to hold these
    pseudo-columns.

    """
    params = [{'SDSSModel.distance': {'display_name': 'Distance [deg]',
                                      'unit': 'degree', 'sql_type': 'float'}},
              {'SDSSModel.has_legacy_data': {'display_name': 'Has Legacy SDSS Data',
                                      'unit': 'boolean', 'sql_type': 'boolean'}}
                                      ]

    for param in params:
        name, data = param.popitem()
        model, column = name.split('.')
        mod = globals()[model]
        # check model fields and computed fields
        col = mod.model_fields.get(column) or mod.model_computed_fields.get(column)
        if not col:
            col = type('Tmp', (), {'description':'no description available'})

        yield {"pk": 0, "schema": "miscdb", "table_name": "misctab",
               "column_name": column, "display_name": data["display_name"],
               "description": col.description,
               "unit": data["unit"], "sql_type": data["sql_type"]}


class AllSpecModel(PeeweeBase):
    """ Pydantic response model for all spectra """
    allspec_id: str = Field(None, description='a unique id for the object')
    multiplex_id: Optional[str] = Field(None, description='the multiplex id')
    sdss_id: Optional[int] = Field(None, description='the SDSS identifier')
    catalogid: Optional[int] = Field(None, description='the SDSS-V catalog id')
    ra: float = Field(None, description='Right Ascension in decimal degrees')
    dec: float = Field(None, description='Declination in decimal degrees')
    sdss_phase: int = Field(None, description='the SDSS phase number of the spectrum')
    observatory: str = Field(None, description='the observatory, APO or LCO')
    instrument: str = Field(None, description='the SDSS spectrograph instrument')
    survey: str = Field(None, description='The SDSS spectroscopic survey or sub-survey')
    programname: Optional[str] = Field(None, description='the spectroscopic program name')
    telescope: Optional[str] = Field(None, description='the SDSS telescope')
    file_spec: Optional[str] = Field(None, description='the data product file species name')
    cas_url: Optional[str] = Field(None, description='the CAS URL')
    sas_url: Optional[str] = Field(None, description='the SAS URL')
    sas_file: Optional[str] = Field(None, description='the SAS file name')
    plate: Optional[int] = Field(None, description='the legacy plate number')
    fps_field: Optional[int] = Field(None, description='the FPS field number')
    plate_or_fps_field: Optional[int] = Field(None, description='the plate or FPS field')
    mjd: Optional[int] = Field(None, description='the MJD of the observation')
    run2d: Optional[str] = Field(None, description='the BOSS 2d DRP version')
    run1d: Optional[str] = Field(None, description='the BOSS 1d DRP version')
    coadd: Optional[str] = Field(None, description='either epoch, daily, or custom (allepoch)')
    apred_vers: Optional[str] = Field(None, description='the APOGEE DRP version')
    drpver: Optional[str] = Field(None, description='the MaNGA DRP version')
    version: str = Field(..., description='any valid pipeline version')
    apogee_id: Optional[str] = Field(None, description='the APOGEE object id')
    apogee_field: Optional[str] = Field(None, description='the APOGEE field, pre-SDSS-V')
    apstar_id: Optional[str] = Field(None, description='the APOGEE star id')
    visit_id: Optional[str] = Field(None, description='the APOGEE visit id')
    mangaid: Optional[str] = Field(None, description='the MaNGA ID')
    specobjid: Optional[int] = Field(None, description='the spectroscopic object id')
    fiberid: Optional[int] = Field(None, description='the legacy SDSS fiber id')
    ifudsgn: Optional[int] = Field(None, description='the MaNGA IFU designation')
    release: Optional[str] = Field(None, description='the data release, e.g. DR17')

    @computed_field(description='The plate-ifu identifier for MaNGA')
    @property
    def plateifu(self) -> str:
        """ The plate-ifu identifier for MaNGA """
        return f"{self.plate}-{self.ifudsgn}" if self.plate and self.ifudsgn else None

    @computed_field(description='The plate-mjd-fiberid identifier for legacy SDSS')
    @property
    def plate_mjd_fiberid(self) -> str:
        """ The plate-mjd-fiberid identifier for legacy SDSS """
        return f"{self.plate}-{self.mjd}-{self.fiberid}" if self.plate and self.mjd and self.fiberid else None

    @computed_field(description='The field-mjd-catalogid identifier for SDSS-V')
    @property
    def field_mjd_catalogid(self) -> str:
        """ The field-mjd-catalogid identifier for SDSS-V """
        return f"{self.fps_field}-{self.mjd}-{self.catalogid}" if self.fps_field and self.mjd and self.catalogid else None

    @computed_field(description='The target identifier for the SDSS object')
    @property
    def id(self) -> str:
        """ The target identifier for the SDSS object """
        return self.plateifu or self.plate_mjd_fiberid or self.field_mjd_catalogid or self.apogee_id or self.mangaid or self.apstar_id or self.visit_id or self.specobjid

    @computed_field(description='The legacy SAS filepath for the SDSS object')
    @property
    def filepath(self) -> str:
        """ The legacy SAS filepath for the SDSS object """
        return build_legacy_path(self.__dict__, release=self.release, ignore_existence=True)

    @computed_field(description='The marvin URL identifier for the SDSS MaNGA target')
    @property
    def marvin_url(self) -> str:
        """ The marvin URL identifier for the SDSS object """
        return f"https://magrathea.sdss.org/marvin/galaxy/{self.plateifu}/" if self.plateifu else None
