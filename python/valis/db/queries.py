# !/usr/bin/env python
# -*- coding: utf-8 -*-
#

# all resuable queries go here

import itertools
import packaging
from typing import Union, Generator

import astropy.units as u
import peewee
from astropy.coordinates import SkyCoord
from sdssdb.peewee.sdss5db import apogee_drpdb as apo
from sdssdb.peewee.sdss5db import boss_drp as boss
from sdssdb.peewee.sdss5db import targetdb, vizdb
from sdssdb.peewee.sdss5db import catalogdb as cat
from sdssdb.peewee.sdss5db import astradb as astra


from valis.io.spectra import extract_data, get_product_model
from valis.utils.paths import build_boss_path, build_apogee_path, build_astra_path
from valis.utils.versions import get_software_tag


def append_pipes(query: peewee.ModelSelect, table: str = 'stacked') -> peewee.ModelSelect:
    """ Joins a query to the SDSSidToPipes table

    Joines an existing query to the SDSSidToPipes table and returns
    the in_boss, in_apogee, and in_astra columns. The table kwarg
    is used inform which table you are joining from/to, either the
    vizdb.SDSSidStacked or vizdb.SDSSidFlat table. Assumes the input query is
    a select from one of those two.

    Parameters
    ----------
    query : peewee.ModelSelect
        the input query to join to
    table : str, optional
        the type of sdss_id table joining to, by default 'stacked'

    Returns
    -------
    peewee.ModelSelect
        the output query

    Raises
    ------
    ValueError
        when table kwarg does not match allowed values
    """
    if table not in {'stacked', 'flat'}:
        raise ValueError('table must be either "stacked" or "flat"')

    model = vizdb.SDSSidStacked if table == 'stacked' else vizdb.SDSSidFlat
    return query.select_extend(vizdb.SDSSidToPipes.in_boss,
                               vizdb.SDSSidToPipes.in_apogee,
                               vizdb.SDSSidToPipes.in_astra).\
        join(vizdb.SDSSidToPipes, on=(model.sdss_id == vizdb.SDSSidToPipes.sdss_id),
             attr='pipes').distinct(vizdb.SDSSidToPipes.sdss_id)


def get_pipes(sdss_id: int) -> peewee.ModelSelect:
    """ Get the pipelines for an sdss_id

    Get the table of boolean flags indicating which
    pipelines the sdss_id is present in.  Provides
    three flags for boss, apogee, astra pipelines.

    Parameters
    ----------
    sdss_id : int
        the input sdss_id

    Returns
    -------
    peewee.ModelSelect
        the output query
    """
    return vizdb.SDSSidToPipes.select(vizdb.SDSSidToPipes).\
        where(vizdb.SDSSidToPipes.sdss_id == sdss_id).\
        distinct(vizdb.SDSSidToPipes.sdss_id)


def convert_coords(ra: Union[str, float], dec: Union[str, float]) -> tuple:
    """ Convert sky coordinates to decimal degrees

    Convert the input RA, Dec sky coordinates into decimal
    degrees. Input format can either be decimal or hmsdms.

    Parameters
    ----------
    ra : str
        The Right Ascension
    dec : str
        The Declination

    Returns
    -------
    tuple
        the converted (RA, Dec)
    """
    is_hms = set('hms: ') & set(str(ra))
    if is_hms:
        ra = str(ra).replace(' ', ':')
        dec = str(dec).replace(' ', ':')
        unit = ('hourangle', 'degree') if is_hms else ('degree', 'degree')
        coord = SkyCoord(f'{ra} {dec}', unit=unit)
        ra = round(coord.ra.value, 5)
        dec = round(coord.dec.value, 5)
    return float(ra), float(dec)


def cone_search(ra: Union[str, float], dec: Union[str, float],
                radius: float, units: str = 'degree') -> peewee.ModelSelect:
    """ Perform a cone search against the vizdb sdss_id_stacked table

    Perform a cone search using the peewee ORM for SDSS targets in the
    vizdb sdss_id_stacked table.  We return the peewee ModelSelect
    directly here so it can be easily combined with other queries.

    In the route endpoint itself, remember to return wrap this in a list.

    Parameters
    ----------
    ra : Union[str, float]
        the Right Ascension coord
    dec : Union[str, float]
        the Declination coord
    radius : float
        the cone search radius
    units : str, optional
        the units of the search radius, by default 'degree'

    Returns
    -------
    peewee.ModelSelect
        the ORM query
    """

    # convert ra, dec to decimal if in hms-dms
    ra, dec = convert_coords(ra, dec)

    # convert radial units to degrees
    radius *= u.Unit(units)
    radius = radius.to(u.degree).value

    return vizdb.SDSSidStacked.select().\
        where(vizdb.SDSSidStacked.cone_search(ra, dec, radius,
                                              ra_col='ra_sdss_id',
                                              dec_col='dec_sdss_id'))


def get_targets_by_sdss_id(sdss_id: int) -> peewee.ModelSelect:
    """ Perform a search for SDSS targets on vizdb.SDSSidStacked based on the sdss_id.

    Perform a search for SDSS targets using the peewee ORM in the
    vizdb.SDSSidStacked table. We return the peewee ModelSelect
    directly here so it can be easily combined with other queries,
    if needed.

    In the route endpoint itself, remember to return wrap this in a list.

    Parameters
    ----------
    sdss_id : int
        the sdss_id

    Returns
    -------
    peewee.ModelSelect
        the ORM query
    """

    return vizdb.SDSSidStacked.select().where(vizdb.SDSSidStacked.sdss_id == sdss_id)


def get_targets_by_catalog_id(catalog_id: int) -> peewee.ModelSelect:
    """ Perform a search for SDSS targets on vizdb.SDSSidStacked based on the catalog_id.

    Perform a search for SDSS targets using the peewee ORM in the
    vizdb.SDSSidStacked table. We return the peewee ModelSelect
    directly here so it can be easily combined with other queries,
    if needed.

    In the route endpoint itself, remember to return wrap this in a list.

    Parameters
    ----------
    catalog_id : int
        the catalog_id

    Returns
    -------
    peewee.ModelSelect
        the ORM query
    """

    return vizdb.SDSSidStacked.select()\
                              .join(vizdb.SDSSidFlat, on=(vizdb.SDSSidStacked.sdss_id ==
                                                          vizdb.SDSSidFlat.sdss_id))\
                              .where(vizdb.SDSSidFlat.catalogid == catalog_id)


def carton_program_list(name_type: str) -> peewee.ModelSelect:
    """ Return a list of either all cartons or programs from targetdb

    Parameters
    ----------
    name_type: str
        Which type you are searching on, either 'carton' or 'program'

    Returns
    -------
    list
        list of either all cartons in programs sorted in alphabetical order
    """
    return sorted(targetdb.Carton.select(getattr(targetdb.Carton, name_type)).distinct().scalars())


def carton_program_map(key: str = 'program') -> dict:
    """ Return a mapping between programs and cartons

    Parameters
    ----------
    key: str
        what to do map grouping on

    Returns
    -------
    mapping: dict
        mapping between programs and cartons
    """
    model = targetdb.Carton.select(targetdb.Carton.carton, targetdb.Carton.program).dicts()

    mapping = {}
    kk = 'program' if key == 'carton' else 'carton'
    for k, g in itertools.groupby(sorted(model, key=lambda x: x[key]), key=lambda x: x[key]):
        mapping[k] = set(i[kk] for i in g)
    return mapping


def carton_program_search(name: str, name_type: str) -> peewee.ModelSelect:
    """ Perform a search on either carton or program

    Parameters
    ----------
    name: str
        Either the carton name or the program name
    name_type: str
        Which type you are searching on, either 'carton' or 'program'

    Returns
    -------
    peewee.ModelSelect
        the ORM query
    """
    model = vizdb.SDSSidFlat.select(peewee.fn.DISTINCT(vizdb.SDSSidFlat.sdss_id))\
                            .join(targetdb.Target,
                                  on=(targetdb.Target.catalogid == vizdb.SDSSidFlat.catalogid))\
                            .join(targetdb.CartonToTarget)\
                            .join(targetdb.Carton)\
                            .where(getattr(targetdb.Carton, name_type) == name)
    return vizdb.SDSSidStacked.select().join(
        model, on=(model.c.sdss_id == vizdb.SDSSidStacked.sdss_id)
    )


def get_targets_obs(release: str, obs: str, spectrograph: str) -> peewee.ModelSelect:
    """ Return all targets with spectra from a given observatory

    Parameters
    ----------
    release : str
        the data release to look up

    obs: str
        Observatory to get targets from. Either 'APO' or 'LCO'

    spectrograph: str
        Which spectrograph to return data from. Can be 'boss',
        'apogee' or 'all' for both.

    Returns
    -------
    peewee.ModelSelect
        the ORM query
    """
    # get the relevant software tag boss
    run2d = get_software_tag(release, 'run2d')

    query_boss = vizdb.SDSSidStacked.select()\
                                    .join(boss.BossSpectrum,
                                          on=(boss.BossSpectrum.sdss_id == vizdb.SDSSidStacked.sdss_id))\
                                    .where(boss.BossSpectrum.run2d == run2d,
                                           boss.BossSpectrum.obs == obs).distinct()

    # get the relevant software tag apogee
    apred = get_software_tag(release, 'apred_vers')

    # temporary, need to join with sdss_id when added
    query_ap = vizdb.SDSSidStacked.select()\
                                  .join(vizdb.SDSSidFlat,
                                        on=(vizdb.SDSSidFlat.sdss_id == vizdb.SDSSidStacked.sdss_id))\
                                  .join(apo.Star,
                                        on=(apo.Star.catalogid == vizdb.SDSSidFlat.catalogid))\
                                  .where(apo.Star.telescope == obs.lower() + '25m',
                                         apo.Star.apred_vers == apred).distinct()

    # return union of the above
    query_all = vizdb.SDSSidStacked.select()\
                                   .where((vizdb.SDSSidStacked.sdss_id << query_boss) |
                                          (vizdb.SDSSidStacked.sdss_id << query_ap))

    if spectrograph == 'boss':
        return query_boss
    elif spectrograph == 'apogee':
        return query_ap
    elif spectrograph == 'all':
        return query_all
    else:
        raise ValueError('Did not pass "boss", "apogee" or "all" to obsWave')


# test sdss ids
# 23326 - boss/astra
# 3350466 - apogee/astra
# 54392544 - all true
# 10 - all false
# 57651832 - my file on disk
# 57832526 - all true, in both astra snow_white, apogee_net (source_pk=912174,star_pk=2954029)


def get_boss_target(sdss_id: int, release: str, fields: list = None,
                    primary: bool = True) -> peewee.ModelSelect:
    """ Get BHM target metadata for an sdss_id

    Parameters
    ----------
    sdss_id : int
        the input sdss_id
    release : str
        the data release to look up
    fields : list, optional
        a list of fields to retrieve from the database, by default None
    primary : bool, default True
        Flag to only use the primary observation

    Returns
    -------
    peewee.ModelSelect
        the output query
    """
    # get the relevant software tag
    run2d = get_software_tag(release, 'run2d')

    if isinstance(run2d, list):
        vercond = boss.BossSpectrum.run2d.in_(run2d)
    else:
        vercond = boss.BossSpectrum.run2d == run2d

    # check fields
    fields = fields or [boss.BossSpectrum]
    if fields and isinstance(fields[0], str):
        fields = (getattr(boss.BossSpectrum, i) for i in fields)

    # query for the target
    query = boss.BossSpectrum.select(*fields).\
        where(boss.BossSpectrum.sdss_id == sdss_id,
              vercond)

    # filter on primary
    if primary:
        query = query.where(boss.BossSpectrum.specprimary == 1)

    return query


def get_apogee_target(sdss_id: int, release: str, fields: list = None):
    """ temporary placeholder for apogee """
    # get the relevant software tag
    apred = get_software_tag(release, 'apred_vers')

    if isinstance(apred, list):
        vercond = apo.Star.apred_vers.in_(apred)
    else:
        vercond = apo.Star.apred_vers == apred

    # check fields
    fields = fields or [apo.Star]
    if fields and isinstance(fields[0], str):
        fields = (getattr(apo.Star, i) for i in fields)

    s = get_astra_target(sdss_id, release)
    if not s:
        return

    a = s.first().apogee_visit_spectrum.first()
    if not a:
        return

    return apo.Star.select(*fields).where(apo.Star.pk == a.star_pk, vercond)


def get_astra_target(sdss_id: int, release: str, fields: list = None):
    """ temporary placeholder for astra """

    vastra = get_software_tag(release, 'v_astra')
    if not vastra or vastra != "0.5.0":
        print('astra only supports DR19 / IPL3 = version 0.5.0')
        return None

    # check fields
    fields = fields or [astra.Source]
    if fields and isinstance(fields[0], str):
        fields = (getattr(astra.Source, i) for i in fields)

    return astra.Source.select(*fields).where(astra.Source.sdss_id == sdss_id)


def get_target_meta(sdss_id: int, release: str) -> dict:
    """ Get the target metadata for an sdss_id

    Get some basic metadata for a given target sdss_id.

    Parameters
    ----------
    sdss_id : int
        the input sdss_id
    release : str
        the data release to look up

    Returns
    -------
    dict
        the output data
    """
    # get the id and pipeline flags
    query = get_targets_by_sdss_id(sdss_id)
    pipes = append_pipes(query)
    return pipes.dicts().first()


def get_pipe_meta(sdss_id: int, release: str, pipeline: str) -> dict:
    """ Get the pipeline metadata for a pipeline

    Parameters
    ----------
    sdss_id : int
        the input sdss_id
    release : str
        the SDSS data release
    pipeline : str, optional
        the name of the pipeline

    Returns
    -------
    dict
        the output pipeline data
    """
    # get boss pipeline target
    if pipeline == 'boss' and (qq := get_boss_target(sdss_id, release)):
        res = qq.dicts().first()
        return {pipeline: res, 'files': {pipeline: build_boss_path(res, release)}}

    # get apogee pipeline target
    elif pipeline == 'apogee' and (qq := get_apogee_target(sdss_id, release)):
        res = qq.dicts().first()
        return {pipeline: res, 'files': {pipeline: build_apogee_path(res, release)}}

    # get astra pipeline target
    elif pipeline == 'astra' and (qq := get_astra_target(sdss_id, release)):
        res = qq.dicts().first()
        return {pipeline: res, 'files': {pipeline: build_astra_path(res, release)}}


def get_target_pipeline(sdss_id: int, release: str, pipeline: str = 'all') -> dict:
    """  Get the pipeline info for a target sdss id

    Get the pipeline info for a target sdss_id. Can specify either
    "boss", "apogee", or "astra" pipeline.  Defaults to getting all
    available pipeline info.

    Also returns any spectral filepaths associated with that
    pipeline data.

    Parameters
    ----------
    sdss_id : int
        the input sdss_id
    release : str
        the SDSS data release
    pipeline : str, optional
        the name of the pipeline, by default 'all'

    Returns
    -------
    dict
        a dictionary of pipeline result data
    """
    # get the pipeline lookup table
    pipes = get_pipes(sdss_id).dicts().first()

    # create initial dict
    data = {'info': {},
            'boss': {}, 'apogee': {}, 'astra': {},
            'files': {'boss': '', 'apogee': '', 'astra': ''}}
    data['info'].update(pipes)

    # get only a given pipeline data
    if pipeline in {'boss', 'apogee', 'astra'} and pipes[f'in_{pipeline}']:
        if (res := get_pipe_meta(sdss_id, release, pipeline)):
            data.update(res)

    # get everything
    elif pipeline == 'all':
        # get boss
        if pipes['in_boss'] and (res := get_pipe_meta(sdss_id, release, 'boss')):
            data.update(res)

        # get apogee
        if pipes['in_apogee'] and (res := get_pipe_meta(sdss_id, release, 'apogee')):
            data.update(res)

        # get astra
        if pipes['in_astra'] and  (res := get_pipe_meta(sdss_id, release, 'astra')):
            data.update(res)

    return data


def _yield_boss_spectrum(sdss_id: int, product: str, release: str) -> Generator:
    """ Yield a boss spectrum

    Yield the boss spectral data for a given target sdss_id and data release,
    and a SDSS data product, i.e. sdss_access path name.

    Parameters
    ----------
    sdss_id : int
        the input sdss_id
    product : str
        the name of the SDSS data product
    release : str
        the SDSS data release

    Yields
    -------
    generator
        the extracted spectral data from the file
    """

    query = get_boss_target(sdss_id, release)
    for row in query.dicts().iterator():
        filepath = build_boss_path(row, release)
        try:
            yield extract_data(product, filepath)
        except FileNotFoundError:
            yield None


def _yield_apogee_spectrum(sdss_id: int, product: str, release: str) -> Generator:
    """ Yield a apogee spectrum

    Yield the apogee spectral data for a given target sdss_id and data release,
    and a SDSS data product, i.e. sdss_access path name.

    Parameters
    ----------
    sdss_id : int
        the input sdss_id
    product : str
        the name of the SDSS data product
    release : str
        the SDSS data release

    Yields
    -------
    generator
        the extracted spectral data from the file
    """
    query = get_apogee_target(sdss_id, release)
    for row in query.dicts().iterator():
        filepath = build_apogee_path(row, release)
        try:
            yield extract_data(product, filepath)
        except FileNotFoundError:
            yield None


def _yield_astra_spectrum(sdss_id: int, product: str, release: str) -> Generator:
    """ Yield a astra spectrum

    Yield the astra spectral data for a given target sdss_id and data release,
    and a SDSS data product, i.e. sdss_access path name.

    Parameters
    ----------
    sdss_id : int
        the input sdss_id
    product : str
        the name of the SDSS data product
    release : str
        the SDSS data release

    Yields
    -------
    generator
        the extracted spectral data from the file
    """
    query = get_astra_target(sdss_id, release)
    for row in query.dicts().iterator():
        filepath = build_astra_path(row, release)
        try:
            yield extract_data(product, filepath)
        except FileNotFoundError:
            yield None


def get_a_spectrum(sdss_id: int, product: str, release: str) -> Generator:
    """ Yield a spectrum

    Yield the spectral data for a given target sdss_id and data release,
    and a SDSS data product, i.e. sdss_access path name.

    Parameters
    ----------
    sdss_id : int
        the input sdss_id
    product : str
        the name of the SDSS data product
    release : str
        the SDSS data release

    Yields
    -------
    generator
        the extracted spectral data from the file
    """
    model = get_product_model(product)
    if model['pipeline'] == 'boss':
        yield from _yield_boss_spectrum(sdss_id, product, release)
    elif model['pipeline'] == 'apogee':
        yield from _yield_apogee_spectrum(sdss_id, product, release)
    elif model['pipeline'] == 'astra':
        yield from _yield_astra_spectrum(sdss_id, product, release)


def get_catalog_sources(sdss_id: int) -> peewee.ModelSelect:
    """ Get the catalog info for a target sdss_id

    Retrieve the catalog info from catalogdb.Catalog table
    for a given sdss_id.

    Parameters
    ----------
    sdss_id : int
        the input sdss_id

    Returns
    -------
    peewee.ModelSelect
        the output query
    """

    s = vizdb.SDSSidFlat.select(vizdb.SDSSidFlat).where(vizdb.SDSSidFlat.sdss_id == sdss_id).alias('s')
    return cat.Catalog.select(cat.Catalog, starfields(s)).\
        join(s, on=(s.c.catalogid == cat.Catalog.catalogid)).order_by(cat.Catalog.version.desc())


def get_target_cartons(sdss_id: int) -> peewee.ModelSelect:
    """ Get the carton info for a target sdss_id

    Retrieve all available carton/program info for a given
    sdss_id.

    Parameters
    ----------
    sdss_id : int
        the input sdss_id

    Returns
    -------
    peewee.ModelSelect
        the output query
    """

    return vizdb.SDSSidFlat.select(targetdb.Target, targetdb.Carton).\
        join(targetdb.Target, on=(targetdb.Target.catalogid == vizdb.SDSSidFlat.catalogid)).\
        join(targetdb.CartonToTarget).join(targetdb.Carton).where(vizdb.SDSSidFlat.sdss_id == sdss_id).\
        order_by(targetdb.Carton.run_on, vizdb.SDSSidFlat.catalogid)


def get_db_metadata(schema: str = None) -> peewee.ModelSelect:
    """ Get the sdss5db database metadata

    Get the sdss5db database table and column metadata.
    By default returns all schema, but a specific one can be
    specified with the ``schema`` keyword.

    Parameters
    ----------
    schema : str, optional
        the database schema name, by default None

    Returns
    -------
    peewee.ModelSelect
        the output query
    """
    query = vizdb.DbMetadata.select()
    if schema:
        query = query.where(vizdb.DbMetadata.schema == schema)
    return query


def starfields(model: peewee.ModelSelect) -> peewee.NodeList:
    """ Return the peewee star fields

    Peewee moved its "star" field to "__star__" in versions
    3.17.1+ to avoid real fields named "star".
    """
    pw_ver = peewee.__version__
    oldver = packaging.version.parse(pw_ver) < packaging.version.parse('3.17.1')
    return model.star if oldver else model.__star__
