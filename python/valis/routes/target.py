from __future__ import print_function, division, absolute_import

import math
import re
import httpx
import orjson
from typing import Any, Tuple, List, Union, Optional, Annotated
from pydantic import field_validator, model_validator, BaseModel, Field, model_serializer
from fastapi import APIRouter, HTTPException, Query, Path, Depends
from fastapi_restful.cbv import cbv
import astropy.units as u
from astropy.coordinates import SkyCoord
from astroquery.simbad import Simbad

from valis.routes.base import Base
from valis.db.queries import (get_target_meta, get_a_spectrum, get_catalog_sources,
                              get_parent_catalog_data, get_target_cartons,
                              get_target_pipeline)
from valis.db.db import get_pw_db
from valis.db.models import CatalogResponse, CartonModel, ParentCatalogModel, PipesModel, SDSSModel

router = APIRouter()

Simbad.add_votable_fields('distance_result')
Simbad.add_votable_fields('ra(d)', 'dec(d)')


class CoordModel(BaseModel):
    """ Pydantic model for a SkyCoord object """
    value: Tuple[float, float] = Field(..., description='The coordinate value', example=(230.50745896, 43.53232817))
    frame: str = Field(..., description='The coordinate frame', example='icrs')
    unit: str = Field(..., description='The coordinate units', example='deg')


class NameResponse(BaseModel):
    """ Response model for target name resolver endpoint """
    coordinate: CoordModel = Field(..., description='The resolved coordinate')
    object_type: str = Field(..., description='The resolved type of object', example='G')
    name: str = Field(..., description='The resolved common target name', example='2MASX J15220182+4331560')
    identifiers: List[str] = Field(..., description='A list of resolved target identifiers', example=["LEDA 2223006", "CASG 697"])


class DistModel(BaseModel):
    """ Model to represent the distance separation """
    value: float
    unit: str = 'arcsec'

    def to_quantity(self):
        return self.value * u.Unit(self.unit)


class SpectrumModel(BaseModel):
    """ Response model for a spectrum """
    header: dict = Field({}, description='The primary header')
    flux: list = Field([], description='The spectrum flux array')
    wavelength: list = Field([], description='The spectrum wavelength array')
    error: list = Field([], description='The spectrum uncertainty array')
    mask: list = Field([], description='The spectrum mask array')

    @model_serializer(when_used='json-unless-none')
    def spec_mod(self):
        return {'header': orjson.dumps(self.header),
                'flux': orjson.dumps(self.flux, option=orjson.OPT_SERIALIZE_NUMPY).decode(),
                'wavelength': orjson.dumps(self.wavelength, option=orjson.OPT_SERIALIZE_NUMPY).decode(),
                'error': orjson.dumps(self.error, option=orjson.OPT_SERIALIZE_NUMPY).decode(),
                'mask': orjson.dumps(self.mask, option=orjson.OPT_SERIALIZE_NUMPY).decode()}


class SimbadRow(BaseModel):
    """ Response Model for a Simbad query_region row result """
    main_id: str = Field(...)
    ra: str = Field(...)
    dec: str = Field(...)
    ra_prec: int = Field(...)
    dec_prec: int = Field(...)
    distance_result: Union[float, DistModel] = Field(...)
    ra_d: float = Field(...)
    dec_d: float = Field(...)
    coo_err_maja: Optional[float] = Field(None)
    coo_err_mina: Optional[float] = Field(None)
    coo_err_angle: Optional[int] = Field(None)
    coo_qual: Optional[str] = Field(None)
    coo_wavelength: Optional[str] = Field(None)
    coo_bibcode: Optional[str] = Field(None)
    script_number_id: Optional[int] = Field(None)

    @model_validator(mode="before")
    @classmethod
    def lower_and_nan(cls, values):
        return {
            k.lower(): None if not isinstance(v, str) and math.isnan(v) else v
            for k, v in values.items()
        }

    @field_validator('distance_result')
    @classmethod
    def parse_distance(cls, v):
        return DistModel(value=v)


@cbv(router)
class Target(Base):
    """ Endpoints for dealing with individual targets """

    @router.get("/resolve/name", summary='Resolve a target name with Sesame', response_model=NameResponse)
    async def get_name(self, name: str = Query(..., description='the target name', example='MaNGA 7443-12701')) -> dict:
        """ Resolve a target name using the Sesame Name Resolver service

        Sesame resolves against Simbad, NED, and Vizier databases, in that order.
        Returns the first successful match found.
        """
        # sesame name resolver URL
        url = f'https://cdsweb.u-strasbg.fr/cgi-bin/nph-sesame/-oI/?{name.strip()}'

        async with httpx.AsyncClient() as client:
            rr = await client.get(url)
            if rr.is_error:
                raise HTTPException(status_code=rr.status_code, detail=rr.content)

            data = rr.content.decode('utf-8')

            bad_rows = re.findall(r'#!(.*?)\n', data)
            if bad_rows:
                raise HTTPException(status_code=400, detail=f'Could not resolve target name {name}.')

            coord = re.findall(r'%J\s*([0-9.]+)\s*([+-.0-9]+)', data)[0]
            coord = {'value': coord, 'frame': 'icrs', 'unit': 'deg'}
            obj = re.findall(r'%C.0(.*?)\n', data)[0].strip()
            name = re.findall(r'%I.0(.*?)\n', data)[0].split("NAME")[-1].strip()
            names = [i for i in re.findall(r'%I (.*?)\n', data) if 'NAME' not in i]
            return {'coordinate': coord, 'object_type': obj, 'name': name, 'identifiers': names}

    @router.get("/resolve/coord", summary='Resolve a target coordinate with Simbad')
    async def get_coord(self,
                        coord: tuple = Query(None, description='the target coordinate', example=(230.50745896, 43.53232817)),
                        cunit: str = Query('deg', description='the coordinate unit', example='deg'),
                        name: str = Query(None, description='the target name', example='MaNGA 7443-12701'),
                        radius: float = Query(1.0, description='the radius to search around the coordinate', example=1.0),
                        runit: str = Query('arcmin', description='the unit of radius unit', example='arcmin')) -> List[SimbadRow]:
        """ Resolve a coordinate using astroquery Simbad.query_region

        Perform a cone search using astroquery Simbad.query_region around
        a given coordinate or target name, with a specified radius. Returns a list
        of results from Simbad service.
        """
        # convert the name or coordinate into an astropy SkyCoord
        if name:
            s = SkyCoord.from_name(name)
        elif coord:
            s = SkyCoord(*coord, unit=cunit)

        # perform the cone search
        res = Simbad.query_region(s, radius=radius * u.Unit(runit))

        # raise an error if no result found
        if not res:
            raise HTTPException(status_code=404, detail=Simbad.last_parsed_result.error_raw)

        # return successful result
        return res.to_pandas().to_dict('records')

    @router.get('/ids/{sdss_id}', summary='Retrieve pipeline metadata for a target sdss_id',
                dependencies=[Depends(get_pw_db)],
                response_model=Union[SDSSModel, dict],
                response_model_exclude_unset=True, response_model_exclude_none=True)
    async def get_target(self, sdss_id: int = Path(title="The sdss_id of the target to get", example=23326)):
        """ Return target metadata for a given sdss_id """
        return get_target_meta(sdss_id, self.release) or {}

    @router.get('/spectra/{sdss_id}', summary='Retrieve a spectrum for a target sdss_id',
                dependencies=[Depends(get_pw_db)],
                response_model=List[SpectrumModel])
    async def get_spectrum(self, sdss_id: Annotated[int, Path(title="The sdss_id of the target to get", example=23326)],
                           product: Annotated[str, Query(description='The file species or data product name', example='specLite')],
                           ext: Annotated[str, Query(description='For multi-extension spectra, e.g. mwmStar, the name of the spectral extension', example='BOSS/APO')] = None,
                           ):
        return get_a_spectrum(sdss_id, product, self.release, ext=ext)

    @router.get('/catalogs/{sdss_id}', summary='Retrieve catalog information for a target sdss_id',
                dependencies=[Depends(get_pw_db)],
                response_model=List[CatalogResponse],
                response_model_exclude_unset=True, response_model_exclude_none=True)
    async def get_catalogs(self, sdss_id: int = Path(title="The sdss_id of the target to get", example=23326)):
        """ Return catalog information for a given sdss_id """

        sdss_id_data = get_catalog_sources(sdss_id).dicts()

        # The response has the parent catalogs at the same level as the other
        # columns. For the response we want to nest them under a parent_catalogs key.
        # This takes advantage that all the parent catalog columns have '__' in the name.
        response_data: list[dict[str, Any]] = []
        for row in sdss_id_data:
            s_data = {k: v for k, v in row.items() if '__' not in k}
            cat_data = {k.split('__')[0]: v for k, v in row.items() if '__' in k}
            response_data.append({**s_data, 'parent_catalogs': cat_data})

        return response_data

    @router.get('/parents/{catalog}/{sdss_id}',
                dependencies=[Depends(get_pw_db)],
                response_model=list[ParentCatalogModel],
                responses={400: {'description': 'Invalid input sdss_id or catalog'}},
                summary='Retrieve parent catalog information for a taget by sdss_id')
    async def get_parents(self,
                          catalog: Annotated[str, Path(description='The parent catalog to search',
                                                       example='gaia_dr3_source')],
                          sdss_id: Annotated[int, Path(description='The sdss_id of the target to get',
                                                       example=129047350)],
                          catalogid: Annotated[int, Query(description='Restrict the list of returned entries to this catalogid',
                                                          example=63050396587194280)]=None):
        """Return parent catalog information for a given sdss_is.

        Returns a list of mappings for each set of parent catalogs associated
        with the catalogid and sdss_id.

        """

        try:
            result = get_parent_catalog_data(sdss_id, catalog, catalogid=catalogid).dicts()
            if len(result) == 0:
                raise ValueError(f'No parent catalog data found for sdss_id {sdss_id}')
        except Exception as e:
            raise HTTPException(status_code=400, detail=f'Error: {e}')

        return result

    @router.get('/cartons/{sdss_id}', summary='Retrieve carton information for a target sdss_id',
                dependencies=[Depends(get_pw_db)],
                response_model=List[CartonModel],
                response_model_exclude_unset=True, response_model_exclude_none=True)
    async def get_cartons(self, sdss_id: int = Path(title="The sdss_id of the target to get", example=23326)):
        """ Return carton information for a given sdss_id """
        return get_target_cartons(sdss_id).dicts().iterator()

    @router.get('/pipelines/{sdss_id}', summary='Retrieve pipeline data for a target sdss_id',
                dependencies=[Depends(get_pw_db)],
                response_model=PipesModel,
                response_model_exclude_unset=True)
    async def get_pipeline(self, sdss_id: int = Path(title="The sdss_id of the target to get", example=23326),
                           pipe: Annotated[str,
                                           Query(enum=['all', 'boss', 'apogee', 'astra'],
                                                 description='Specify search on specific pipeline',
                                                 example='boss')] = 'all'):

        return get_target_pipeline(sdss_id, self.release, pipe)
