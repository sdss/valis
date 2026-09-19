# !/usr/bin/env python
# -*- coding: utf-8 -*-
#

# all resuable queries go here

import inspect
import itertools
import os.path
import uuid
from enum import Enum

from typing import Generator, Union

import astropy.units as u
import deepmerge
import packaging
import peewee
from astropy.coordinates import SkyCoord
from astropy.io import fits
from peewee import Case
from playhouse.shortcuts import model_to_dict
from sdssdb.peewee.sdss5db import apogee_drpdb as apo
from sdssdb.peewee.sdss5db import astradb as astra
from sdssdb.peewee.sdss5db import boss_drp as boss
from sdssdb.peewee.sdss5db import catalogdb as cat
from sdssdb.peewee.sdss5db import targetdb, vizdb

# from valis.db.models import MapperName
from valis.io.spectra import extract_data, get_product_model
from valis.utils.paths import build_apogee_path, build_astra_path, build_boss_path, get_pathcomp
from valis.utils.versions import get_software_tag

from fastapi import HTTPException
import re


def lco_hack(query: peewee.ModelSelect, release: str = None) -> peewee.ModelSelect:
    """Remove SV-LCO targets from the query"""

    # only apply hack for public data releases
    if release and "DR" not in release:
        return query

    return query.where(
        vizdb.SDSSidToPipes.obs.is_null(True) |
        ((vizdb.SDSSidToPipes.obs == "apo")
        | ((vizdb.SDSSidToPipes.obs == "lco") & (vizdb.SDSSidToPipes.release == "dr17")))
    )


def append_pipes(
    query: peewee.ModelSelect, table: str = "stacked", observed: bool = True, release: str = None
) -> peewee.ModelSelect:
    """Joins a query to the SDSSidToPipes table

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
    observed : bool, optional
        Flag to filter on observed targets, by default True

    Returns
    -------
    peewee.ModelSelect
        the output query

    Raises
    ------
    ValueError
        when table kwarg does not match allowed values
    """
    if table not in {"stacked", "flat"}:
        raise ValueError('table must be either "stacked" or "flat"')

    # cannot create temp table if query is None
    if query is None:
        return query

    # Run initial query as a temporary table.
    temp = create_temporary_table(query, indices=["sdss_id"])

    qq = (
        temp.select(
            temp.__star__,
            vizdb.SDSSidToPipes.in_boss,
            vizdb.SDSSidToPipes.in_apogee,
            vizdb.SDSSidToPipes.in_bvs,
            vizdb.SDSSidToPipes.in_astra,
            vizdb.SDSSidToPipes.has_been_observed,
            vizdb.SDSSidToPipes.release,
            vizdb.SDSSidToPipes.obs,
            vizdb.SDSSidToPipes.mjd,
            vizdb.SDSSidToPipes.has_legacy_data,
        )
        .join(vizdb.SDSSidToPipes, on=(temp.c.sdss_id == vizdb.SDSSidToPipes.sdss_id))
        .distinct(temp.c.sdss_id)
    )

    # either observed or has legacy data
    if observed:
        qq = qq.where((vizdb.SDSSidToPipes.has_been_observed == observed)
                      | (~vizdb.SDSSidToPipes.has_been_observed and
                         vizdb.SDSSidToPipes.has_legacy_data))

    if release:
        # get the release
        rel = vizdb.Releases.select().where(vizdb.Releases.release == release).first()

        # if a release has no cutoff info, then force the cutoff to 0, query will return nothing
        # to fix this we want mjd cutoffs by survey for all older releases
        if not rel.mjd_cutoff_apo and not rel.mjd_cutoff_lco:
            rel.mjd_cutoff_apo = 0
            rel.mjd_cutoff_lco = 0

        # create the mjd cutoff condition
        cutoff_by_obs = Case(
            vizdb.SDSSidToPipes.obs,
            (("apo", rel.mjd_cutoff_apo), ("lco", rel.mjd_cutoff_lco)),
            None,
        )
        qq = qq.where(
            vizdb.SDSSidToPipes.mjd.is_null(True)
            | (vizdb.SDSSidToPipes.mjd <= cutoff_by_obs)
        )

    # for DR19, remove SV LCO targets, this is a hack for now
    if release.upper() in {"DR19", "IPL3"}:
        qq = lco_hack(qq, release)

    return qq


def get_pipes(sdss_id: int, release: str) -> peewee.ModelSelect:
    """Get the pipelines for an sdss_id

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
    qq = vizdb.SDSSidToPipes.select(vizdb.SDSSidToPipes).where(vizdb.SDSSidToPipes.sdss_id == sdss_id)
    # only hack out lco for DR19
    if release.upper() in {"DR19", "IPL3"}:
        qq = lco_hack(qq, release)
    return qq.distinct(vizdb.SDSSidToPipes.sdss_id)


def convert_coords(ra: Union[str, float], dec: Union[str, float]) -> tuple:
    """Convert sky coordinates to decimal degrees

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
    is_hms = set("hms: ") & set(str(ra))
    if is_hms:
        ra = str(ra).strip().replace(" ", ":")
        dec = str(dec).strip().replace(" ", ":")
        unit = ("hourangle", "degree") if is_hms else ("degree", "degree")
        coord = SkyCoord(f"{ra} {dec}", unit=unit)
        ra = round(coord.ra.value, 5)
        dec = round(coord.dec.value, 5)
    return float(ra), float(dec)


def cone_search(
    ra: Union[str, float], dec: Union[str, float], radius: float, units: str = "degree"
) -> peewee.ModelSelect:
    """Perform a cone search against the vizdb sdss_id_stacked table

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

    # compute the separation in degrees
    sep = peewee.fn.q3c_dist(ra, dec, vizdb.SDSSidStacked.ra_sdss_id, vizdb.SDSSidStacked.dec_sdss_id).alias("distance")

    return vizdb.SDSSidStacked.select(vizdb.SDSSidStacked, sep).where(
        vizdb.SDSSidStacked.cone_search(ra, dec, radius, ra_col="ra_sdss_id", dec_col="dec_sdss_id")
    )


def get_targets_by_sdss_id(sdss_id: Union[int, list[int]] = []) -> peewee.ModelSelect:
    """Perform a search for SDSS targets on vizdb.SDSSidStacked based on sdss_id values.

    Perform a search for SDSS targets using the peewee ORM in the
    vizdb.SDSSidStacked table, based on single or multiple sdss_ids values.
    We return the peewee ModelSelect directly here so it can be easily combined
    with other queries, if needed.

    In the route endpoint itself, remember to return wrap this in a list.

    Parameters
    ----------
    sdss_id : Union[int, list[int]]
        the sdss_id or list of sdss_id values

    Returns
    -------
    peewee.ModelSelect
        the ORM query
    """
    if type(sdss_id) in (int, str):
        sdss_id = [sdss_id]

    return vizdb.SDSSidStacked.select().where(vizdb.SDSSidStacked.sdss_id.in_(sdss_id))


def get_targets_by_catalog_id(catalog_id: int) -> peewee.ModelSelect:
    """Perform a search for SDSS targets on vizdb.SDSSidStacked based on the catalog_id.

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

    return (
        vizdb.SDSSidStacked.select()
        .join(vizdb.SDSSidFlat, on=(vizdb.SDSSidStacked.sdss_id == vizdb.SDSSidFlat.sdss_id))
        .where(vizdb.SDSSidFlat.catalogid == catalog_id)
    )


def carton_program_list(name_type: str) -> peewee.ModelSelect:
    """Return a list of either all cartons or programs from targetdb

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


def carton_program_map(key: str = "program") -> dict:
    """Return a mapping between programs and cartons

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
    kk = "program" if key == "carton" else "carton"
    for k, g in itertools.groupby(sorted(model, key=lambda x: x[key]), key=lambda x: x[key]):
        mapping[k] = list(set(i[kk] for i in g))
    return mapping


def carton_program_search(
    name: str, name_type: str, query: peewee.ModelSelect | None = None, limit: int | None = None
) -> peewee.ModelSelect:
    """Perform a search on either carton or program

    Parameters
    ----------
    name: str
        Either the carton name or the program name
    name_type: str
        Which type you are searching on, either 'carton' or 'program'
    query : ModelSelect
        An initial query to extend. If ``None``, a new query with all the unique
        ``sdss_id``s is created.
    limit : int
        Limit the number of results returned.

    Returns
    -------
    peewee.ModelSelect
        the ORM query
    """

    if query is None:
        query = vizdb.SDSSidStacked.select(vizdb.SDSSidStacked).distinct()

    # NOTE: These setting seem to help when querying some cartons or programs, mainly
    # those with small number of targets, and in some cases with these the query
    # actually applies the LIMIT more efficiently, but it's not a perfect solution.
    vizdb.database.execute_sql("SET enable_gathermerge = off;")
    vizdb.database.execute_sql("SET parallel_tuple_cost = 100;")
    vizdb.database.execute_sql("SET enable_bitmapscan = off;")

    query = (
        query.join(vizdb.SDSSidFlat, on=(vizdb.SDSSidFlat.sdss_id == vizdb.SDSSidStacked.sdss_id))
        .join(targetdb.Target, on=(targetdb.Target.catalogid == vizdb.SDSSidFlat.catalogid))
        .join(targetdb.CartonToTarget)
        .join(targetdb.Carton)
        .where(getattr(targetdb.Carton, name_type) == name)
    )

    if limit:
        query = query.limit(limit)

    return query


def get_targets_obs(release: str, obs: str, spectrograph: str) -> peewee.ModelSelect:
    """Return all targets with spectra from a given observatory

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
    run2d = get_software_tag(release, "run2d")

    query_boss = (
        vizdb.SDSSidStacked.select()
        .join(boss.BossSpectrum, on=(boss.BossSpectrum.sdss_id == vizdb.SDSSidStacked.sdss_id))
        .where(boss.BossSpectrum.run2d == run2d, boss.BossSpectrum.obs == obs)
        .distinct()
    )

    # get the relevant software tag apogee
    apred = get_software_tag(release, "apred_vers")

    # temporary, need to join with sdss_id when added
    query_ap = (
        vizdb.SDSSidStacked.select()
        .join(vizdb.SDSSidFlat, on=(vizdb.SDSSidFlat.sdss_id == vizdb.SDSSidStacked.sdss_id))
        .join(apo.Star, on=(apo.Star.catalogid == vizdb.SDSSidFlat.catalogid))
        .where(apo.Star.telescope == obs.lower() + "25m", apo.Star.apred_vers == apred)
        .distinct()
    )

    # return union of the above
    query_all = vizdb.SDSSidStacked.select().where(
        (vizdb.SDSSidStacked.sdss_id << query_boss) | (vizdb.SDSSidStacked.sdss_id << query_ap)
    )

    if spectrograph == "boss":
        return query_boss
    elif spectrograph == "apogee":
        return query_ap
    elif spectrograph == "all":
        return query_all
    else:
        raise ValueError('Did not pass "boss", "apogee" or "all" to obsWave')


# test sdss ids
# 23326 - boss/astra
# 25739 in astra 0.8.0 but not 0.5.0 sources
# 3350466 - apogee/astra
# 54392544 - all true
# 10 - all false
# 57651832 - my file on disk
# 57832526 - all true, in both astra snow_white, apogee_net (source_pk=912174,star_pk=2954029)
# 61731453 - in astra, false all else; dr17 release


def get_boss_target(
    sdss_id: int,
    release: str,
    fields: list = None,
    primary: bool = True,
    pk: int = None,
    mjd: int = None,
    coadd: str = None,
    field: int = None,
) -> peewee.ModelSelect:
    """Get BHM target metadata for an sdss_id

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
    pk : int, optional
        Optional internal database primary key for direct lookup, by default None
    mjd : int, optional
        Optional MJD of the observation, by default None
    coadd : str, optional
        Optional coadd label, either daily, epoch or allepoch, by default None
    field : int, optional
        Optional field number to filter on, by default None
    Returns
    -------
    peewee.ModelSelect
        the output query
    """
    # get the relevant software tag
    run2d = get_software_tag(release, "run2d")

    if isinstance(run2d, list):
        vercond = boss.BossSpectrum.run2d.in_(run2d)
    else:
        vercond = boss.BossSpectrum.run2d == run2d

    # check fields
    fields = fields or [boss.BossSpectrum]
    if fields and isinstance(fields[0], str):
        fields = (getattr(boss.BossSpectrum, i) for i in fields)

    # query for the target
    query = boss.BossSpectrum.select(*fields).where(boss.BossSpectrum.sdss_id == sdss_id, vercond)

    # extend with boss version info
    query = query.select_extend(boss.BossVersion.label.alias('label')).join(boss.BossVersion,
                                                       on=(boss.BossSpectrum.boss_version == boss.BossVersion.id))

    # filter on primary
    if primary:
        query = query.where(boss.BossSpectrum.specprimary == 1)

    # filter on primary key
    if pk:
        query = query.where(boss.BossSpectrum.id == pk)

    # filter on mjd
    if mjd:
        query = query.where(boss.BossSpectrum.mjd == mjd)

    # filter on coadd label
    if coadd:
        query = query.where(boss.BossVersion.label == coadd)

    # filter on field
    if field:
        query = query.where(boss.BossSpectrum.field == field)

    return query


def get_apogee_target(sdss_id: int, release: str, fields: list = None, table: str = 'star', pk: int = None, mjd: int = None, field: int = None) -> peewee.ModelSelect:
    """Get the Apogee target metadata for an sdss_id

    Retrieves the apogee pipeline data from the apogee_drp.star or visit table
    for the given sdss_id and data release.

    Parameters
    ----------
    sdss_id : int
        the input sdss_id
    release : str
        the data release to look up
    fields : list, optional
        a list of fields to retrieve from the database, by default None
    table : str, optional
        which apogee table to query, either 'star' or 'visit', by default 'star'

    Returns
    -------
    peewee.ModelSelect
        the output query
    """
    # get the relevant software tag
    apred = get_software_tag(release, "apred_vers")

    # set the table
    model = apo.Visit if table == 'visit' else apo.Star

    # create apogee version conditions
    if isinstance(apred, list):
        vercond = model.apred_vers.in_(apred)
    else:
        vercond = model.apred_vers == apred

    # check fields
    fields = fields or [model]
    if fields and isinstance(fields[0], str):
        fields = (getattr(model, i) for i in fields)

    # get the apogee star data
    query =  model.select(*fields).where(model.sdss_id == sdss_id, vercond)

    # filter on primary key
    if pk:
        query = query.where(model.pk == pk)

    # filter on mjd
    if mjd:
        col = model.mjd if table == 'visit' else model.starver
        query = query.where(col == mjd)

    # filter on field
    if field and table == 'visit':
        query = query.where(model.field == field)

    return query


def check_astra_release(release: str) -> str | None:
    """Check the astra tag release"""
    vastra = get_software_tag(release, "v_astra")
    vcheck = "0.5.0" if vastra in ("0.5.0", "0.6.0") else vastra
    if vcheck is None or vcheck.replace(".", "") not in astra.Source._meta.schema:
        print(
            f"warning: astra version for current release {release} does not match assigned astra schema {astra.Source._meta.schema}"
        )
        return None
    return vastra


def get_astra_target(sdss_id: int, release: str, fields: list = None) -> peewee.ModelSelect:
    """Get the Astra target metadata for an sdss_id

    Retrieves the astra source data from the astra.source table
    for the given sdss_id and data release.

    Parameters
    ----------
    sdss_id : int
        the input sdss_id
    release : str
        the data release to look up
    fields : list, optional
        a list of fields to retrieve from the database, by default None

    Returns
    -------
    peewee.ModelSelect
        the output query
    """
    # check the astra version against the assigned schema
    if check_astra_release(release) is None:
        return None

    # check fields
    fields = fields or [astra.Source]
    if fields and isinstance(fields[0], str):
        fields = (getattr(astra.Source, i) for i in fields)

    return astra.Source.select(*fields).where(astra.Source.sdss_id == sdss_id)


def get_target_meta(sdss_id: int, release: str) -> dict:
    """Get the target metadata for an sdss_id

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
    pipes = append_pipes(query, observed=False, release=release)
    return pipes.dicts().first()

def get_pipe_meta(sdss_id: int, release: str, pipeline: str) -> dict:
    """Get the pipeline reduction data for a pipeline

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
    if pipeline == "boss" and (qq := get_boss_target(sdss_id, release, primary=False)):
        output = {pipeline: [], "files": {pipeline: []}}
        for res in qq.dicts().iterator():
            filepath = build_boss_path(res, release=release, ignore_existence=False)
            res.update({"location": get_pathcomp(filepath, release, "location")})
            output[pipeline].append(res)
            output["files"][pipeline].append(filepath)
        return output

    # get apogee pipeline target
    elif pipeline == "apogee":
        output = {pipeline: {'stars': [], 'visits': []}, "files": {pipeline: []}}

        # apogee is disabled for DR20
        if release.upper() == "DR20":
            return output

        # stars
        if (qq := get_apogee_target(sdss_id, release, table='star')):
            for res in qq.dicts().iterator():
                filepath = build_apogee_path(res, release=release, ignore_existence=False)
                res.update({"location": get_pathcomp(filepath, release, "location")})
                output[pipeline]['stars'].append(res)
                output["files"][pipeline].append(filepath)
        # visits
        if (qq := get_apogee_target(sdss_id, release, table='visit')):
            for res in qq.dicts().iterator():
                filepath = build_apogee_path(res, release=release, ignore_existence=False)
                res.update({"location": get_pathcomp(filepath, release, "location")})
                output[pipeline]['visits'].append(res)
                output["files"][pipeline].append(filepath)
        return output

    # get astra pipeline target
    elif pipeline == "astra" and (qq := get_astra_target(sdss_id, release)):
        res = qq.dicts().first()
        output = {pipeline: {"source": res, 'products': []}, "files": {pipeline: []}}
        for item in ("mwmStar", "mwmVisit", "astraStarASPCAP", "astraStarThePayne", "astraStarSnowWhite", "astraVisitThePayne", "astraVisitSnowWhite"):
            filepath = build_astra_path(res, release=release, name=item, ignore_existence=False)

            if filepath and os.path.exists(filepath):
                with fits.open(filepath) as hdul:
                    ext_with_data = [ext for ext in range(len(hdul)) if hdul[ext].size > 0]
                    has_data = len(ext_with_data) > 0
            else:
                has_data = None

            output[pipeline]['products'].append({"product": item, "location": get_pathcomp(filepath, release, "location"), "has_data": has_data})

            if has_data:
                output["files"][pipeline].append(filepath)

        return output


def get_target_pipeline(sdss_id: int, release: str, pipeline: str = "all") -> dict:
    """Get the pipeline info for a target sdss id

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

    # spot check on target metadata
    target = get_target_meta(sdss_id, release=release)

    # get the pipeline lookup table
    pipes = get_pipes(sdss_id, release).dicts().first()

    # create initial dict
    data = {
        "info": {},
        "boss": [],
        "apogee": {},
        "astra": {},
        "files": {"boss": [], "apogee": [], "astra": []},
        "astra_pipelines": [],
    }
    data["info"].update(pipes or {})

    # if there is no match from vizdb, return nothing
    if not target or not pipes:
        return data

    # get only a given pipeline data
    if pipeline in {"boss", "apogee", "astra"} and pipes[f"in_{pipeline}"]:
        if res := get_pipe_meta(sdss_id, release, pipeline):
            data.update(res)

    # get everything
    elif pipeline == "all":
        # get boss
        if pipes["in_boss"] and (res := get_pipe_meta(sdss_id, release, "boss")):
            deepmerge.always_merger.merge(data, res)

        # get apogee
        if pipes["in_apogee"] and (res := get_pipe_meta(sdss_id, release, "apogee")):
            deepmerge.always_merger.merge(data, res)

        # get astra
        if pipes["in_astra"] and (res := get_pipe_meta(sdss_id, release, "astra")):
            deepmerge.always_merger.merge(data, res)

            if pipes["release"] == "dr17":
                s = get_astra_target(sdss_id, release)
                v = s.first().apogee_visit_spectrum.where(astra.ApogeeVisitSpectrum.apred == "dr17").dicts().first()
                path = build_apogee_path(v, "DR17")
                deepmerge.always_merger.merge(data, {"files": {"apogee": [path]}})

    # get any astra pipelines the target is in
    data["astra_pipelines"] = list_astra_pipelines(sdss_id, release)

    return data


def _yield_boss_spectrum(sdss_id: int, product: str, release: str) -> Generator:
    """Yield a boss spectrum

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
    for obj in query.iterator():
        row = model_to_dict(obj)
        filepath = build_boss_path(row, release)
        try:
            yield extract_data(product, filepath)
        except FileNotFoundError:
            yield None


def _yield_apogee_spectrum(sdss_id: int, product: str, release: str) -> Generator:
    """Yield an apogee spectrum

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
    for obj in query.iterator():
        row = model_to_dict(obj)
        filepath = build_apogee_path(row, release)
        try:
            yield extract_data(product, filepath)
        except FileNotFoundError:
            yield None


def _yield_astra_spectrum(sdss_id: int, product: str, release: str, ext: str) -> Generator:
    """Yield an astra spectrum

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
    ext : str
        the name of spectral extension

    Yields
    -------
    generator
        the extracted spectral data from the file
    """
    query = get_astra_target(sdss_id, release)
    for obj in query.iterator():
        row = model_to_dict(obj)
        filepath = build_astra_path(row, release)
        try:
            yield extract_data(product, filepath, multispec=ext)
        except FileNotFoundError:
            yield None


def get_a_spectrum(sdss_id: int, product: str, release: str, ext: str = None) -> Generator:
    """Yield a spectrum

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
    ext : str
        the name of the spectral extension, e.g. BOSS/APO

    Yields
    -------
    generator
        the extracted spectral data from the file
    """

    # if no pipeline info, return empty generator
    pipes = get_pipes(sdss_id, release).dicts().first()
    if not pipes:
        yield from ()
        return

    model = get_product_model(product)
    if model["pipeline"] == "boss":
        yield from _yield_boss_spectrum(sdss_id, product, release)
    elif model["pipeline"] == "apogee":
        yield from _yield_apogee_spectrum(sdss_id, product, release)
    elif model["pipeline"] == "astra":
        yield from _yield_astra_spectrum(sdss_id, product, release, ext=ext)


def get_catalog_sources(sdss_id: int) -> peewee.ModelSelect:
    """Get the catalog info for a target sdss_id

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

    s = vizdb.SDSSidFlat.select(vizdb.SDSSidFlat).where(vizdb.SDSSidFlat.sdss_id == sdss_id).alias("s")
    return (
        cat.Catalog.select(cat.Catalog, cat.SDSS_ID_To_Catalog, starfields(s))
        .join(s, on=(s.c.catalogid == cat.Catalog.catalogid))
        .join(cat.SDSS_ID_To_Catalog, on=(s.c.catalogid == cat.SDSS_ID_To_Catalog.catalogid))
        .order_by(cat.Catalog.version.desc())
    )


def get_parent_catalog_data(sdss_id: int, catalog: str, catalogid: int | None = None) -> peewee.ModelSelect:
    """Returns parent catalog data for a given target."""

    SID = cat.SDSS_ID_To_Catalog

    fqtn = f"catalogdb.{catalog}"
    if fqtn not in cat.database.models:
        raise ValueError(f"Catalog {catalog} not found in catalogdb.")

    ParentModel = cat.database.models[fqtn]

    cid_condition = (SID.catalogid == catalogid) if catalogid is not None else True

    return (
        SID.select(SID.sdss_id, SID.catalogid, ParentModel)
        .distinct(SID.sdss_id, SID.catalogid)
        .join(ParentModel)
        .where(SID.sdss_id == sdss_id)
        .where(cid_condition)
        .order_by(SID.catalogid)
    )


def get_target_cartons(sdss_id: int) -> peewee.ModelSelect:
    """Get the carton info for a target sdss_id

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

    return (
        vizdb.SDSSidFlat.select(targetdb.Target, targetdb.Carton)
        .join(targetdb.Target, on=(targetdb.Target.catalogid == vizdb.SDSSidFlat.catalogid))
        .join(targetdb.CartonToTarget)
        .join(targetdb.Carton)
        .where(vizdb.SDSSidFlat.sdss_id == sdss_id)
        .order_by(targetdb.Carton.run_on, vizdb.SDSSidFlat.catalogid)
    )


def get_db_metadata(schema: str = None) -> peewee.ModelSelect:
    """Get the sdss5db database metadata

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


class MapperName(str, Enum):
    """Mapper names"""

    MWM: str = "MWM"
    BHM: str = "BHM"
    LVM: str = "LVM"


def get_paged_target_list_by_mapper(
    mapper: MapperName = MapperName.MWM, page_number: int = 1, items_per_page: int = 10
) -> peewee.ModelSelect:
    """Return a paged list of target rows, based on the mapper.

    Return paginated and ordered target rows (of a particular mapper)
    from the vizdb.SDSSidStacked table,
    using the peewee ORM. We return the peewee ModelSelect
    directly here so it can be easily combined with other queries,
    if needed.

    Parameters
    ----------
    mapper : MapperName
        Enum denoting the mapper name.
    page_number : int
        Page number of the returned target rows.
    items_per_page : int
        Number of target rows displayed in the page.

    Returns
    -------
    peewee.ModelSelect
        the ORM query
    """

    if mapper is MapperName.MWM:
        where_condition = vizdb.SDSSidToPipes.in_apogee == True
    elif mapper is MapperName.BHM:
        where_condition = vizdb.SDSSidToPipes.in_boss == True
    else:
        where_condition = False

    return (
        vizdb.SDSSidStacked.select()
        .join(vizdb.SDSSidToPipes, on=(vizdb.SDSSidStacked.sdss_id == vizdb.SDSSidToPipes.sdss_id))
        .where(where_condition)
        .order_by(vizdb.SDSSidStacked.sdss_id)
        .paginate(page_number, items_per_page)
    )


def starfields(model: peewee.ModelSelect) -> peewee.NodeList:
    """Return the peewee star fields

    Peewee moved its "star" field to "__star__" in versions
    3.17.1+ to avoid real fields named "star".
    """
    pw_ver = peewee.__version__
    oldver = packaging.version.parse(pw_ver) < packaging.version.parse("3.17.1")
    return model.star if oldver else model.__star__


def get_sdssid_by_altid(id: str | int, idtype: str = None) -> peewee.ModelSelect:
    """Get an sdss_id by an alternative id

    This query attempts to identify a target sdss_id from an
    alternative id, which can be a string or integer.  It tries
    to distinguish between the following formats:

     - a (e)BOSS plate-mjd-fiberid, e.g. "10235-58127-0020"
     - a BOSS field-mjd-catalogid, e.g. "101077-59845-27021603187129892"
     - an SDSS-IV APOGEE ID, e.g "2M23595980+1528407"
     - a MaNGA plate-ifu, e.g. "8485-1901"
     - an SDSS specobjid, e.g. 3259575414686771200
     - an SDSS-V catalogid, e.g. 2702160318712989
     - a GAIA DR3 ID, e.g. 4110508934728363520

     It queries either the boss_drp.boss_spectrum, astra.source,
     or vizb.allspec tables for the sdss_id.  For pure integer ids,
     use the ``idtype`` parameter to specify the type of id
     (e.g. 'specobjid', 'catalogid', 'gaiaid', 'sdssid').

    Parameters
    ----------
    id : str | int
        the input alternative id
    idtype : str, optional
        the type of integer id, by default None

    Returns
    -------
    peewee.ModelSelect
        the ORM query
    """

    # cast to str
    if isinstance(id, int):
        id = str(id)

    # temp for now; maybe we make a single "altid" db column somewhere
    ndash = id.count("-")
    final = id.rsplit("-", 1)[-1]
    if ndash == 2 and len(final) <= 4 and final.isdigit() and int(final) <= 1000:
        # boss/eboss plate-mjd-fiberid e.g '10235-58127-0020'
        plate, mjd, fiberid = id.split("-")
        targ = vizdb.AllSpec.select(vizdb.AllSpec.sdss_id).where(
            vizdb.AllSpec.plate == int(plate), vizdb.AllSpec.mjd == int(mjd), vizdb.AllSpec.fiberid == int(fiberid)
        )
    elif ndash == 2 and len(final) > 5:
        # field-mjd-catalogid, e.g. '101077-59845-27021603187129892'
        field, mjd, catalogid = id.split("-")
        targ = boss.BossSpectrum.select(boss.BossSpectrum.sdss_id).where(
            boss.BossSpectrum.catalogid == catalogid, boss.BossSpectrum.mjd == mjd, boss.BossSpectrum.field == field
        )
    elif ndash == 1 and not id.replace("-", "").isdigit():
        # apogee south, e.g. '2M17282323-2415476'
        targ = astra.Source.select(astra.Source.sdss_id).where(astra.Source.sdss4_apogee_id.in_([id]))
    elif ndash == 1 and id.replace("-", "").isdigit():
        # mangaid '3-109500752' or plateifu '8485-1901'
        prefix = len(id.split("-")[0])
        if prefix in {4, 5}:
            # plateifu
            plate, ifu = id.split("-")
            targ = vizdb.AllSpec.select(vizdb.AllSpec.sdss_id).where(
                vizdb.AllSpec.plate == int(plate), vizdb.AllSpec.ifudsgn == int(ifu)
            )
        else:
            # mangaid
            targ = vizdb.AllSpec.select(vizdb.AllSpec.sdss_id).where(vizdb.AllSpec.mangaid == id)
    elif ndash == 0 and not id.isdigit():
        # apogee obj id
        targ = astra.Source.select(astra.Source.sdss_id).where(astra.Source.sdss4_apogee_id.in_([id]))
    elif ndash == 0 and idtype == "specobjid":
        # specobjid
        targ = vizdb.AllSpec.select(vizdb.AllSpec.sdss_id).where(vizdb.AllSpec.specobjid.in_([id]))
    elif ndash == 0 and id.isdigit():
        # single integer id
        if idtype == "catalogid":
            # catalogid , e.g. 27021603187129892
            field = "catalogid"
        elif idtype == "gaiaid":
            # gaia dr3 id , e.g. 4110508934728363520
            field = "gaia_dr3_source_id"
        elif idtype == "sdssid":
            # sdss id, e.g. 23326
            field = "sdss_id"
        else:
            field = "catalogid"

        targ = astra.Source.select(astra.Source.sdss_id).where(getattr(astra.Source, field).in_([id]))

    return targ


def get_target_by_altid(id: str | int, idtype: str = None) -> peewee.ModelSelect:
    """Get a target by an alternative id

    This retrieves the target info from vizdb.sdss_id_stacked,
    given an alternative id.  It first tries to identify the proper
    sdss_id for the given altid, then it retrieves the basic target
    info. See ``get_sdssid_by_altid`` for details on the altid formats.

    Parameters
    ----------
    id : str | int
        the input alternative id
    idtype : str, optional
        the type of integer id, by default None

    Returns
    -------
    peewee.ModelSelect
        the ORM query
    """
    # if idtype is explicitly sdss_id, return it directly
    if idtype == "sdssid":
        return get_targets_by_sdss_id(id)

    # get the sdss_id
    targ = get_sdssid_by_altid(id, idtype=idtype)
    res = targ.get_or_none() if targ else None
    if not res:
        return

    # get the sdss_id metadata info
    return get_targets_by_sdss_id(res.sdss_id)


def get_targets_by_altid(ids: list, idtype: str = None) -> peewee.ModelSelect:
    """Get a list of targets by altid

    Gets targets from a list of alternative identifier.  Iterates
    to get the sdss_id for each id, then retrieves the list
    of objects at once.

    Parameters
    ----------
    id : str | int
        the input alternative id
    idtype : str, optional
        the type of integer id, by default None

    Returns
    -------
    peewee.ModelSelect
        the ORM query
    """
    res = (j.sdss_id for i in ids for j in get_sdssid_by_altid(i, idtype=idtype) if j)
    return get_targets_by_sdss_id(list(res))


def create_temporary_table(
    query: peewee.ModelSelect, indices: list[str] | None = None
) -> Generator[None, None, peewee.Table]:
    """Create a temporary table from a query."""

    table_name = uuid.uuid4().hex[0:8]

    table = peewee.Table(table_name)
    table.bind(vizdb.database)

    query.create_table(table_name, temporary=True)

    if indices:
        for index in indices:
            vizdb.database.execute_sql(f'CREATE INDEX ON "{table_name}" ({index})')

    vizdb.database.execute_sql(f'ANALYZE "{table_name}"')

    return table


def get_legacy_allspec(sdss_id: int, phase: int = 5) -> peewee.ModelSelect:
    """Get rows from the allspec table for a given sdss_id

    Get legacy SDSS data from the allspec table for a given sdss_id.  By default
    it returns legacy rows via a phase < 5, but you can return all rows by
    setting phase to 0.

    Parameters
    ----------
    sdss_id : int
        the sdss_id to look up
    phase : int, optional
        the SDSS phase, by default 5

    Returns
    -------
    peewee.ModelSelect
        the ORM query
    """
    # join with releases to get the release name out instead of pk
    query = vizdb.AllSpec.select(vizdb.AllSpec, vizdb.Releases.release.alias("release")).join(
        vizdb.Releases, on=(vizdb.AllSpec.releases_pk == vizdb.Releases.pk)
    )

    # if no phase, return all id matches
    if not phase:
        return query.where(vizdb.AllSpec.sdss_id == sdss_id)

    return query.where(vizdb.AllSpec.sdss_id == sdss_id, vizdb.AllSpec.sdss_phase < phase)


def get_legacy_catalogs(sdss_id: int) -> dict:
    """Get legacy catalog info for a given sdss_id

    Returns the legacy SDSS parent catalog info for a given sdss_id. It
    filters on legacy SDSS parent catalog names from catalogdb, and returns a dict
    of the catalog name and its primary key lookup value.

    Parameters
    ----------
    sdss_id : int
        the sdss_id to look up

    Returns
    -------
    dict
        the legacy catalog info
    """
    # create condition
    legacy = {
        "mastar_goodstars",
        "sdss_dr13_photoobj",
        "sdss_dr17_specobj",
        "mangatarget",
        "marvels_dr11_star",
        "marvels_dr12_star",
        "allstar_dr17_synspec_rev1",
    }
    # construct a not null condition for the legacy catalogs
    cond = None
    for k in legacy:
        if cond is None:
            cond = getattr(cat.SDSS_ID_To_Catalog, k).is_null(False)
        else:
            cond = (cond) | (getattr(cat.SDSS_ID_To_Catalog, k).is_null(False))

    # filter out the field names and only include
    tmp = {}
    for row in (
        cat.SDSS_ID_To_Catalog.select().where(cat.SDSS_ID_To_Catalog.sdss_id == sdss_id, cond).dicts().iterator()
    ):
        cat_data = {k.split("__")[0]: v for k, v in row.items() if "__" in k and v}
        tt = {k: v for k, v in cat_data.items() if k in legacy and k not in tmp}
        tmp.update(tt)

    return tmp


def has_legacy_data(sdss_id: int, phase: int = 5) -> bool:
    """Check if a target has legacy SDSS data

    Checks if a target has legacy SDSS data by looking up valid rows in the
    allspec table, and checks against the legacy SDSS parent catalogs from catalogdb.

    Parameters
    ----------
    sdss_id : int
        the sdss_id to look up
    phase : int, optional
        the SDSS phase, by default 5

    Returns
    -------
    bool
        True if the target has legacy SDSS data, False otherwise
    """
    in_allspec = get_legacy_allspec(sdss_id, phase).count()
    # fix this; this can return no legacy in allspec but has parent catalog from photoobj, e.g. 62245293
    has_legcats = {}  # get_legacy_catalogs(sdss_id)
    return in_allspec > 0 or has_legcats != {}


def list_astra_pipelines(sdss_id: int, release: str) -> list:
    """List the astra pipelines available for a given target

    Lists the astra pipelines available for a given target sdss_id and data release.

    Parameters
    ----------
    sdss_id : int
        the input sdss_id
    release : str
        the SDSS data release

    Returns
    -------
    list
        the list of available astra pipelines for the target
    """
    # check the astra version against the assigned schema
    if (vastra := check_astra_release(release)) is None:
        return []

    # drp pipeline versions, flatten if multi-listed
    vers = (get_software_tag(release, "run2d"), get_software_tag(release, "apred_vers"))
    vers = [i for v in vers for i in (v if isinstance(v, list) else [v])]

    ss = (
        vizdb.SDSSidToAstraPipeline.select(vizdb.SDSSidToAstraPipeline.pipeline_name)
        .where(
            vizdb.SDSSidToAstraPipeline.v_astra == vastra,
            vizdb.SDSSidToAstraPipeline.sdss_id == sdss_id,
            vizdb.SDSSidToAstraPipeline.drp_version.in_(vers),
        )
        .distinct()
        .scalars()
    )

    return list(ss)


def get_astra_pipeline(sdss_id: int, release: str, pipeline: str) -> dict:
    """Get the Astra pipeline data for a given target and pipeline name

    Retrieves the astra pipeline data from the astra.source table
    for a given target sdss_id, data release, and astra pipeline name.

    Parameters
    ----------
    sdss_id : int
        the input sdss_id
    release : str
        the SDSS data release
    pipeline : str
        the name of the astra pipeline

    Returns
    -------
    peewee.ModelSelect
        the output query
    """
    # check the astra version against the assigned schema
    if (vastra := check_astra_release(release)) is None:
        return None

    tables = {
        v._meta.table_name: v for v in astra.__dict__.values() if inspect.isclass(v) and issubclass(v, astra.AstraBase)
    }
    tables["apogee_net"] = tables.get("apogee_net", tables.get("apogee_net_v2"))

    if pipeline not in tables:
        raise ValueError(f"Astra pipeline {pipeline} not found in astra schema {vastra}.")

    # drp pipeline versions, flatten if multi-listed
    vers = (get_software_tag(release, "run2d"), get_software_tag(release, "apred_vers"))
    vers = [i for v in vers for i in (v if isinstance(v, list) else [v])]

    # lookup the pipeline for the target sdss_id
    pipes = list(
        vizdb.SDSSidToAstraPipeline.select().where(
            vizdb.SDSSidToAstraPipeline.v_astra == vastra,
            vizdb.SDSSidToAstraPipeline.sdss_id == sdss_id,
            vizdb.SDSSidToAstraPipeline.pipeline_name == pipeline,
            vizdb.SDSSidToAstraPipeline.drp_version.in_(vers),
        )
    )

    # no pipelines
    if not pipes:
        return None

    # if more than one result, then likely different runs in pipeline tables, try to select the relevant one
    # based on the latest pipeline tag for the given release.
    if len(pipes) > 1:
        specpks = [p.spectrum_pk for p in pipes]
        if pipeline == "boss_net":
            version = get_software_tag(release, "run2d")
            res = (
                astra.BossVisitSpectrum.select()
                .where(astra.BossVisitSpectrum.spectrum.in_(specpks), astra.BossVisitSpectrum.run2d == version)
                .get_or_none()
            )
        else:
            version = get_software_tag(release, "apred_vers")
            res = (
                astra.ApogeeVisitSpectrum.select()
                .where(astra.ApogeeVisitSpectrum.spectrum.in_(specpks), astra.ApogeeVisitSpectrum.apred == version)
                .get_or_none()
            )
        # select the matching pipe result
        if res:
            pipe = [p for p in pipes if p.source_pk == res.source.pk and p.spectrum_pk == res.spectrum.pk]

    # query the astra pipeline table
    pipe = pipes[0]
    model = tables[pipeline]
    query = model.select().where(model.source == pipe.source_pk, model.spectrum == pipe.spectrum_pk)
    res = list(query.dicts())

    # return the most recent pipeline data if there are multiple entries
    # or None if none found
    return max(res, key=lambda i: i["created"]) if res else None

# Below in regex, we match plus sign due to below column.
# sdss5db=> select max(apogee_id) from vizdb.allspec limit 4;
#         max
# --------------------
#  AP22304103+3917301
# (1 row)
# if you give above in url then + becomes space.
# google
# how to give + sign in rest api url
#
# To pass a literal + sign in a REST API URL, you must use its percent-encoded format: %2B

# Regular dash, en dash and em dash do not require special encoding in REST API URL

# Below has en dash
# sdss5db=> select allspec_id from vizdb.allspec limit 1;
#              allspec_id
# ---------------------------------------
#  sdss4–lco–apogee–dr17–12010–58795–220


def is_alphanum(text):
    # ^ matches start, $ matches end, [a-zA-Z0-9]+ matches 1 or more alphanumeric characters
    # the first dash is regular dash
    # the second dash is em dash
    # the third is en dash
    if len(text) > 100:
        return False
    return bool(re.match(r"^[a-zA-Z0-9\_\-\+\N{EM DASH}\N{EN DASH}]+$", text))


def is_alphanum_list(text_list):
    # ^ matches start, $ matches end, [a-zA-Z0-9]+ matches 1 or more alphanumeric characters
    # the first dash is regular dash
    # the second dash is em dash
    # the third is en dash
    for text in text_list:
        if len(text) > 100:
            return False
        is_match = bool(re.match(r"^[a-zA-Z0-9\_\-\+\N{EM DASH}\N{EN DASH}]+$", text))
        if (is_match is False):
            return False

    return True


def cast_int_list(int_list):
    for i in range(len(int_list)):
        int_list[i] = int(int_list[i])

    return int_list


def get_targets_allspec_id(
        allspec_id: str,
        multiplex_id: str,
        releases_pk: int,
        sdss_phase: int,
        observatory: str,
        instrument: str,
        sdss_id: int,
        catalogid: int,
        fiberid: int,
        ifudsgn: int,
        plate: int,
        fps_field: int,
        plate_or_fps_field: int,
        mjd: int,
        run2d: str,
        run1d: str,
        coadd: str,
        apred_vers: str,
        drpver: str,
        version: str,
        programname: str,
        survey: str,
        healpix: int,
        healpixgrp: int,
        apogee_id: str) -> peewee.ModelSelect:

    """Perform a search for SDSS targets on vizdb.allspec
    based on allpsec_id and other integer or string column values.

    Perform a search for SDSS targets using the peewee ORM in the
    vizdb.allspec table, based on allspec_id etc. values.
    We return the peewee ModelSelect directly here so it can be easily combined
    with other queries, if needed.

    In the route endpoint itself, remember to return wrap this in a list.

    Parameters
    ----------
        allspec_id: str,
        multiplex_id: str,
        releases_pk: int,
        sdss_phase: int,
        observatory: str,
        instrument: str,
        sdss_id: int,
        catalogid: int,
        fiberid: int,
        ifudsgn: int,
        plate: int,
        fps_field: int,
        plate_or_fps_field: int,
        mjd: int,
        run2d: str,
        run1d: str,
        coadd: str,
        apred_vers: str,
        drpver: str,
        version: str,
        programname: str,
        survey: str,
        healpix: int,
        healpixgrp: int,
        apogee_id: str

    Returns

    peewee.ModelSelect
        the ORM query
    """

    # The below expression is not an arithmetic expression.
    # The below expression has type <class 'peewee.Expression'>
    # vizdb.AllSpec.allspec_id == allspec_id

    where_peewee_exprs = []
    if allspec_id is not None:
        if (not is_alphanum(allspec_id)):
            raise HTTPException(status_code=400, detail=f"Invalid allspec_id {allspec_id}.")
        where_peewee_exprs.append(vizdb.AllSpec.allspec_id == allspec_id)

    if multiplex_id is not None:
        if (not is_alphanum(multiplex_id)):
            raise HTTPException(status_code=400, detail=f"Invalid multiplex_id {multiplex_id}.")
        where_peewee_exprs.append(vizdb.AllSpec.multiplex_id == multiplex_id)

    if releases_pk is not None:
        releases_pk = int(releases_pk)
        where_peewee_exprs.append(vizdb.AllSpec.releases_pk == releases_pk)

    if sdss_phase is not None:
        sdss_phase = int(sdss_phase)
        where_peewee_exprs.append(vizdb.AllSpec.sdss_phase == sdss_phase)

    if observatory is not None:
        if (not is_alphanum(observatory)):
            raise HTTPException(status_code=400, detail=f"Invalid observatory {observatory}.")
        where_peewee_exprs.append(vizdb.AllSpec.observatory == observatory)

    if instrument is not None:
        if (not is_alphanum(instrument)):
            raise HTTPException(status_code=400, detail=f"Invalid instrument {instrument}.")
        where_peewee_exprs.append(vizdb.AllSpec.instrument == instrument)

    if sdss_id is not None:
        sdss_id = int(sdss_id)
        where_peewee_exprs.append(vizdb.AllSpec.sdss_id == sdss_id)

    if catalogid is not None:
        catalogid = int(catalogid)
        where_peewee_exprs.append(vizdb.AllSpec.catalogid == catalogid)

    if fiberid is not None:
        fiberid = int(fiberid)
        where_peewee_exprs.append(vizdb.AllSpec.fiberid == fiberid)

    if ifudsgn is not None:
        ifudsgn = int(ifudsgn)
        where_peewee_exprs.append(vizdb.AllSpec.ifudsgn == ifudsgn)

    if plate is not None:
        plate = int(plate)
        where_peewee_exprs.append(vizdb.AllSpec.plate == plate)

    if fps_field is not None:
        fps_field = int(fps_field)
        where_peewee_exprs.append(vizdb.AllSpec.fps_field == fps_field)

    if plate_or_fps_field is not None:
        plate_or_fps_field = int(plate_or_fps_field)
        where_peewee_exprs.append(vizdb.AllSpec.plate_or_fps_field == plate_or_fps_field)

    if mjd is not None:
        mjd = int(mjd)
        where_peewee_exprs.append(vizdb.AllSpec.mjd == mjd)

    if run2d is not None:
        if (not is_alphanum(run2d)):
            raise HTTPException(status_code=400, detail=f"Invalid run2d {run2d}.")
        where_peewee_exprs.append(vizdb.AllSpec.run2d == run2d)

    if run1d is not None:
        if (not is_alphanum(run1d)):
            raise HTTPException(status_code=400, detail=f"Invalid run1d {run1d}.")
        where_peewee_exprs.append(vizdb.AllSpec.run1d == run1d)

    if coadd is not None:
        if (not is_alphanum(coadd)):
            raise HTTPException(status_code=400, detail=f"Invalid coadd {coadd}.")
        where_peewee_exprs.append(vizdb.AllSpec.coadd == coadd)

    if apred_vers is not None:
        if (not is_alphanum(apred_vers)):
            raise HTTPException(status_code=400, detail=f"apred_vers {apred_vers}.")
        where_peewee_exprs.append(vizdb.AllSpec.apred_vers == apred_vers)

    if drpver is not None:
        if (not is_alphanum(drpver)):
            raise HTTPException(status_code=400, detail=f"Invalid drpver {drpver}.")
        where_peewee_exprs.append(vizdb.AllSpec.drpver == drpver)

    if version is not None:
        if (not is_alphanum(version)):
            raise HTTPException(status_code=400, detail=f"Invalid version {version}.")
        where_peewee_exprs.append(vizdb.AllSpec.version == version)

    if programname is not None:
        if (not is_alphanum(programname)):
            raise HTTPException(status_code=400, detail=f"Invalid programname {programname}.")
        where_peewee_exprs.append(vizdb.AllSpec.programname == programname)

    if survey is not None:
        if (not is_alphanum(survey)):
            raise HTTPException(status_code=400, detail=f"Invalid survey {survey}.")
        where_peewee_exprs.append(vizdb.AllSpec.survey == survey)

    if healpix is not None:
        healpix = int(healpix)
        where_peewee_exprs.append(vizdb.AllSpec.healpix == healpix)

    if healpixgrp is not None:
        healpixgrp = int(healpixgrp)
        where_peewee_exprs.append(vizdb.AllSpec.healpixgrp == healpixgrp)

    if apogee_id is not None:
        if (not is_alphanum(apogee_id)):
            raise HTTPException(status_code=400, detail=f"Invalid apogee_id {apogee_id}.")
        where_peewee_exprs.append(vizdb.AllSpec.apogee_id == apogee_id)

    if (len(where_peewee_exprs) == 0):
        raise HTTPException(status_code=400, detail="There is no column for the SQL WHERE clause of the query. Please give at least one column of the table vizdb.allspec.")

    # The below "select count" takes very little time compared
    # to the peewee_query below. So we run it before running the peewee_query.
    row_count = vizdb.AllSpec.select().where(*where_peewee_exprs).count()

    print(row_count)

    max_row_count = 10000
    if (row_count > max_row_count):
        raise HTTPException(status_code=400, detail=f"Query returned {row_count} rows. Maximum number of returned rows allowed is {max_row_count}. Please make the query more specific i.e. add more column conditions to reduce the number of returned rows.")

    peewee_query = vizdb.AllSpec.select().where(*where_peewee_exprs)

    return peewee_query


def get_targets_allspec_cone(
        ra: float,
        dec: float,
        radius: float) -> peewee.ModelSelect:

    """Perform a cone search for SDSS targets on vizdb.allspec
    based on ra, dec, and radius of search. Units are degrees.
    Maximum allowed value of radius is 1 degree.

    Perform a search for SDSS targets using the peewee ORM in the
    vizdb.allspec table, based on ra, dec, radius values.
    We return the peewee ModelSelect directly here so it can be easily combined
    with other queries, if needed.

    In the route endpoint itself, remember to return wrap this in a list.

    Parameters
    ----------
        ra: float,
        dec: float,
        radius: float

    Returns

    peewee.ModelSelect
        the ORM query
    """

    if ra is not None:
        ra = float(ra)
    else:
        raise HTTPException(status_code=400, detail=f"Missing ra {ra}.")

    if dec is not None:
        dec = float(dec)
    else:
        raise HTTPException(status_code=400, detail=f"Missing dec {dec}.")

    if radius is not None:
        radius = float(radius)
    else:
        raise HTTPException(status_code=400, detail=f"Missing radius {radius}.")

    if (ra < 0) or (ra > 360):
        raise HTTPException(status_code=400, detail=f"Invalid ra {ra}.")

    if (dec < -90) or (dec > 90):
        raise HTTPException(status_code=400, detail=f"Invalid dec {dec}.")

    if (radius < 0) or (radius > 1):
        raise HTTPException(status_code=400, detail=f"Invalid radius {radius}. Maximum allowed value is 1 degree.")

    # The below "select count" takes very little time compared
    # to the peewee_query below. So we run it before running the peewee_query.
    row_count = vizdb.AllSpec.select().where(
                      peewee.fn.q3c_radial_query(
                          vizdb.AllSpec.ra,
                          vizdb.AllSpec.dec,
                          ra,
                          dec,
                          radius)).count()

    print(row_count)

    max_row_count = 10000
    if (row_count > max_row_count):
        raise HTTPException(status_code=400, detail=f"Query returned {row_count} rows. Maximum number of returned rows allowed is {max_row_count}. Please make the query more specific i.e. reduce the radius to reduce the number of returned rows.")

    peewee_query = vizdb.AllSpec.select().where(
                      peewee.fn.q3c_radial_query(
                          vizdb.AllSpec.ra,
                          vizdb.AllSpec.dec,
                          ra,
                          dec,
                          radius))

    return peewee_query


def get_targets_allspec_id_like(
        allspec_id_like: str
 ) -> peewee.ModelSelect:

    """Perform a search for SDSS targets on vizdb.allspec
    based on part of an allspec_id (i.e. query will use SQL LIKE).

    Perform a search for SDSS targets using the peewee ORM in the
    vizdb.allspec table, based on part of an allspec_id.
    We return the peewee ModelSelect directly here so it can be easily combined
    with other queries, if needed.

    In the route endpoint itself, remember to return wrap this in a list.

    Parameters
    ----------
        allspec_id_like: str

    Returns

    peewee.ModelSelect
        the ORM query
    """

    if allspec_id_like is not None:
        if (not is_alphanum(allspec_id_like)):
            raise HTTPException(status_code=400, detail=f"Invalid allspec_id_like {allspec_id_like}.")
    else:
        raise HTTPException(status_code=400, detail=f"Missing allspec_id_like {allspec_id_like}.")

    # The below "select count" takes very little time compared
    # to the peewee_query below. So we run it before running the peewee_query.
    row_count = vizdb.AllSpec.select().where(vizdb.AllSpec.allspec_id.contains(allspec_id_like)).count()

    print(row_count)

    max_row_count = 10000
    if (row_count > max_row_count):
        raise HTTPException(status_code=400, detail=f"Query returned {row_count} rows. Maximum number of returned rows allowed is {max_row_count}. Please make the query more specific i.e. increase the length of the allspec_id_like string to reduce the number of returned rows.")

    peewee_query = vizdb.AllSpec.select().where(vizdb.AllSpec.allspec_id.contains(allspec_id_like))

    return peewee_query


def get_targets_allspec_id_in(
        allspec_id: list[str],
        multiplex_id: list[str],
        releases_pk: list[int],
        sdss_phase: list[int],
        observatory: list[str],
        instrument: list[str],
        sdss_id: list[int],
        catalogid: list[int],
        fiberid: list[int],
        ifudsgn: list[int],
        plate: list[int],
        fps_field: list[int],
        plate_or_fps_field: list[int],
        mjd: list[int],
        run2d: list[str],
        run1d: list[str],
        coadd: list[str],
        apred_vers: list[str],
        drpver: list[str],
        version: list[str],
        programname: list[str],
        survey: list[str],
        healpix: list[int],
        healpixgrp: list[int],
        apogee_id: list[str]) -> peewee.ModelSelect:

    """Perform a search for SDSS targets on vizdb.allspec
    based on allpsec_id and other integer or string column values.
    This search uses SQL IN. The URL can contain multiple entries
    for the same column. For example:
    Below sdss_id is repeated two times. So it is equivalent to the SQL IN clause "sdss_id  in (70050164, 92310876)".
    /query/allspec_id_in?sdss_id=70050164&sdss_id=92310876&instrument=boss

    Perform a search for SDSS targets using the peewee ORM in the
    vizdb.allspec table, based on allspec_id etc. values.
    We return the peewee ModelSelect directly here so it can be easily combined
    with other queries, if needed.

    In the route endpoint itself, remember to return wrap this in a list.

    Parameters
    ----------
        allspec_id: list[str],
        multiplex_id: list[str],
        releases_pk: list[int],
        sdss_phase: list[int],
        observatory: list[str],
        instrument: list[str],
        sdss_id: list[int],
        catalogid: list[int],
        fiberid: list[int],
        ifudsgn: list[int],
        plate: list[int],
        fps_field: list[int],
        plate_or_fps_field: list[int],
        mjd: list[int],
        run2d: list[str],
        run1d: list[str],
        coadd: list[str],
        apred_vers: list[str],
        drpver: list[str],
        version: list[str],
        programname: list[str],
        survey: list[str],
        healpix: list[int],
        healpixgrp: list[int],
        apogee_id: list[str]

    Returns

    peewee.ModelSelect
        the ORM query
    """

    # The below expression is not an arithmetic expression.
    # The below expression has type <class 'peewee.Expression'>
    # vizdb.AllSpec.allspec_id == allspec_id

    # this is max number of choices in SQL IN statement
    max_num_choices = 100

    where_peewee_exprs = []

    if allspec_id is not None:
        num_choices = len(allspec_id)
        if (num_choices > max_num_choices):
            raise HTTPException(status_code=400, detail=f"Number of choices for allspec_id = {num_choices}. Maximum number of choices allowed is {max_num_choices}. Please reduce the number of choices.")

        if (not is_alphanum_list(allspec_id)):
            raise HTTPException(status_code=400, detail=f"Invalid allspec_id {allspec_id}.")

        where_peewee_exprs.append(vizdb.AllSpec.allspec_id.in_(allspec_id))

    if multiplex_id is not None:
        num_choices = len(multiplex_id)
        if (num_choices > max_num_choices):
            raise HTTPException(status_code=400, detail=f"Number of choices for multiplex_id = {num_choices}. Maximum number of choices allowed is {max_num_choices}. Please reduce the number of choices.")

        if (not is_alphanum_list(multiplex_id)):
            raise HTTPException(status_code=400, detail=f"Invalid multiplex_id {multiplex_id}.")

        where_peewee_exprs.append(vizdb.AllSpec.multiplex_id.in_(multiplex_id))

    if releases_pk is not None:
        num_choices = len(releases_pk)
        if (num_choices > max_num_choices):
            raise HTTPException(status_code=400, detail=f"Number of choices for releases_pk = {num_choices}. Maximum number of choices allowed is {max_num_choices}. Please reduce the number of choices.")

        releases_pk = cast_int_list(releases_pk)

        where_peewee_exprs.append(vizdb.AllSpec.releases_pk.in_(releases_pk))

    if sdss_phase is not None:
        num_choices = len(sdss_phase)
        if (num_choices > max_num_choices):
            raise HTTPException(status_code=400, detail=f"Number of choices for sdss_phase = {num_choices}. Maximum number of choices allowed is {max_num_choices}. Please reduce the number of choices.")

        sdss_phase = cast_int_list(sdss_phase)

        where_peewee_exprs.append(vizdb.AllSpec.sdss_phase.in_(sdss_phase))

    if observatory is not None:
        num_choices = len(observatory)
        if (num_choices > max_num_choices):
            raise HTTPException(status_code=400, detail=f"Number of choices for observatory = {num_choices}. Maximum number of choices allowed is {max_num_choices}. Please reduce the number of choices.")

        if (not is_alphanum_list(observatory)):
            raise HTTPException(status_code=400, detail=f"Invalid observatory {observatory}.")

        where_peewee_exprs.append(vizdb.AllSpec.observatory.in_(observatory))

    if instrument is not None:
        num_choices = len(instrument)
        if (num_choices > max_num_choices):
            raise HTTPException(status_code=400, detail=f"Number of choices for instrument = {num_choices}. Maximum number of choices allowed is {max_num_choices}. Please reduce the number of choices.")

        if (not is_alphanum_list(instrument)):
            raise HTTPException(status_code=400, detail=f"Invalid instrument {instrument}.")

        where_peewee_exprs.append(vizdb.AllSpec.instrument.in_(instrument))

    if sdss_id is not None:
        num_choices = len(sdss_id)
        if (num_choices > max_num_choices):
            raise HTTPException(status_code=400, detail=f"Number of choices for sdss_id = {num_choices}. Maximum number of choices allowed is {max_num_choices}. Please reduce the number of choices.")

        sdss_id = cast_int_list(sdss_id)

        where_peewee_exprs.append(vizdb.AllSpec.sdss_id.in_(sdss_id))

    if catalogid is not None:
        num_choices = len(catalogid)
        if (num_choices > max_num_choices):
            raise HTTPException(status_code=400, detail=f"Number of choices for catalogid = {num_choices}. Maximum number of choices allowed is {max_num_choices}. Please reduce the number of choices.")

        catalogid = cast_int_list(catalogid)

        where_peewee_exprs.append(vizdb.AllSpec.catalogid.in_(catalogid))

    if fiberid is not None:
        num_choices = len(fiberid)
        if (num_choices > max_num_choices):
            raise HTTPException(status_code=400, detail=f"Number of choices for fiberid = {num_choices}. Maximum number of choices allowed is {max_num_choices}. Please reduce the number of choices.")

        fiberid = cast_int_list(fiberid)

        where_peewee_exprs.append(vizdb.AllSpec.fiberid.in_(fiberid))

    if ifudsgn is not None:
        num_choices = len(ifudsgn)
        if (num_choices > max_num_choices):
            raise HTTPException(status_code=400, detail=f"Number of choices for ifudsgn = {num_choices}. Maximum number of choices allowed is {max_num_choices}. Please reduce the number of choices.")

        ifudsgn = cast_int_list(ifudsgn)

        where_peewee_exprs.append(vizdb.AllSpec.ifudsgn.in_(ifudsgn))

    if plate is not None:
        num_choices = len(plate)
        if (num_choices > max_num_choices):
            raise HTTPException(status_code=400, detail=f"Number of choices for plate = {num_choices}. Maximum number of choices allowed is {max_num_choices}. Please reduce the number of choices.")

        plate = cast_int_list(plate)
        where_peewee_exprs.append(vizdb.AllSpec.plate.in_(plate))

    if fps_field is not None:
        num_choices = len(fps_field)
        if (num_choices > max_num_choices):
            raise HTTPException(status_code=400, detail=f"Number of choices for fps_field = {num_choices}. Maximum number of choices allowed is {max_num_choices}. Please reduce the number of choices.")

        fps_field = cast_int_list(fps_field)
        where_peewee_exprs.append(vizdb.AllSpec.fps_field.in_(fps_field))

    if plate_or_fps_field is not None:
        num_choices = len(plate_or_fps_field)
        if (num_choices > max_num_choices):
            raise HTTPException(status_code=400, detail=f"Number of choices for plate_or_fps_field = {num_choices}. Maximum number of choices allowed is {max_num_choices}. Please reduce the number of choices.")

        plate_or_fps_field = cast_int_list(plate_or_fps_field)
        where_peewee_exprs.append(vizdb.AllSpec.plate_or_fps_field.in_(plate_or_fps_field))

    if mjd is not None:
        num_choices = len(mjd)
        if (num_choices > max_num_choices):
            raise HTTPException(status_code=400, detail=f"Number of choices for mjd = {num_choices}. Maximum number of choices allowed is {max_num_choices}. Please reduce the number of choices.")

        mjd = cast_int_list(mjd)
        where_peewee_exprs.append(vizdb.AllSpec.mjd.in_(mjd))

    if run2d is not None:
        num_choices = len(run2d)
        if (num_choices > max_num_choices):
            raise HTTPException(status_code=400, detail=f"Number of choices for run2d = {num_choices}. Maximum number of choices allowed is {max_num_choices}. Please reduce the number of choices.")

        if (not is_alphanum_list(run2d)):
            raise HTTPException(status_code=400, detail=f"Invalid run2d {run2d}.")
        where_peewee_exprs.append(vizdb.AllSpec.run2d.in_(run2d))

    if run1d is not None:
        num_choices = len(run1d)
        if (num_choices > max_num_choices):
            raise HTTPException(status_code=400, detail=f"Number of choices for run1d = {num_choices}. Maximum number of choices allowed is {max_num_choices}. Please reduce the number of choices.")

        if (not is_alphanum_list(run1d)):
            raise HTTPException(status_code=400, detail=f"Invalid run1d {run1d}.")
        where_peewee_exprs.append(vizdb.AllSpec.run1d.in_(run1d))

    if coadd is not None:
        num_choices = len(coadd)
        if (num_choices > max_num_choices):
            raise HTTPException(status_code=400, detail=f"Number of choices for coadd = {num_choices}. Maximum number of choices allowed is {max_num_choices}. Please reduce the number of choices.")

        if (not is_alphanum_list(coadd)):
            raise HTTPException(status_code=400, detail=f"Invalid coadd {coadd}.")
        where_peewee_exprs.append(vizdb.AllSpec.coadd.in_(coadd))

    if apred_vers is not None:
        num_choices = len(apred_vers)
        if (num_choices > max_num_choices):
            raise HTTPException(status_code=400, detail=f"Number of choices for apred_vers = {num_choices}. Maximum number of choices allowed is {max_num_choices}. Please reduce the number of choices.")

        if (not is_alphanum_list(apred_vers)):
            raise HTTPException(status_code=400, detail=f"apred_vers {apred_vers}.")
        where_peewee_exprs.append(vizdb.AllSpec.apred_vers.in_(apred_vers))

    if drpver is not None:
        num_choices = len(drpver)
        if (num_choices > max_num_choices):
            raise HTTPException(status_code=400, detail=f"Number of choices for drpver = {num_choices}. Maximum number of choices allowed is {max_num_choices}. Please reduce the number of choices.")

        if (not is_alphanum_list(drpver)):
            raise HTTPException(status_code=400, detail=f"Invalid drpver {drpver}.")
        where_peewee_exprs.append(vizdb.AllSpec.drpver.in_(drpver))

    if version is not None:
        num_choices = len(version)
        if (num_choices > max_num_choices):
            raise HTTPException(status_code=400, detail=f"Number of choices for version = {num_choices}. Maximum number of choices allowed is {max_num_choices}. Please reduce the number of choices.")

        if (not is_alphanum_list(version)):
            raise HTTPException(status_code=400, detail=f"Invalid version {version}.")
        where_peewee_exprs.append(vizdb.AllSpec.version.in_(version))

    if programname is not None:
        num_choices = len(programname)
        if (num_choices > max_num_choices):
            raise HTTPException(status_code=400, detail=f"Number of choices for programname = {num_choices}. Maximum number of choices allowed is {max_num_choices}. Please reduce the number of choices.")

        if (not is_alphanum_list(programname)):
            raise HTTPException(status_code=400, detail=f"Invalid programname {programname}.")
        where_peewee_exprs.append(vizdb.AllSpec.programname.in_(programname))

    if survey is not None:
        num_choices = len(survey)
        if (num_choices > max_num_choices):
            raise HTTPException(status_code=400, detail=f"Number of choices for survey = {num_choices}. Maximum number of choices allowed is {max_num_choices}. Please reduce the number of choices.")

        if (not is_alphanum_list(survey)):
            raise HTTPException(status_code=400, detail=f"Invalid survey {survey}.")
        where_peewee_exprs.append(vizdb.AllSpec.survey.in_(survey))

    if healpix is not None:
        num_choices = len(healpix)
        if (num_choices > max_num_choices):
            raise HTTPException(status_code=400, detail=f"Number of choices for healpix = {num_choices}. Maximum number of choices allowed is {max_num_choices}. Please reduce the number of choices.")

        healpix = cast_int_list(healpix)
        where_peewee_exprs.append(vizdb.AllSpec.healpix.in_(healpix))

    if healpixgrp is not None:
        num_choices = len(healpixgrp)
        if (num_choices > max_num_choices):
            raise HTTPException(status_code=400, detail=f"Number of choices for healpixgrp = {num_choices}. Maximum number of choices allowed is {max_num_choices}. Please reduce the number of choices.")

        healpixgrp = cast_int_list(healpixgrp)
        where_peewee_exprs.append(vizdb.AllSpec.healpixgrp.in_(healpixgrp))

    if apogee_id is not None:
        num_choices = len(apogee_id)
        if (num_choices > max_num_choices):
            raise HTTPException(status_code=400, detail=f"Number of choices for apogee_id = {num_choices}. Maximum number of choices allowed is {max_num_choices}. Please reduce the number of choices.")

        if (not is_alphanum_list(apogee_id)):
            raise HTTPException(status_code=400, detail=f"Invalid apogee_id {apogee_id}.")
        where_peewee_exprs.append(vizdb.AllSpec.apogee_id.in_(apogee_id))

    if (len(where_peewee_exprs) == 0):
        raise HTTPException(status_code=400, detail="There is no column for the SQL WHERE clause of the query. Please give at least one column of the table vizdb.allspec.")

    # The below "select count" takes very little time compared
    # to the peewee_query below. So we run it before running the peewee_query.
    row_count = vizdb.AllSpec.select().where(*where_peewee_exprs).count()

    print(row_count)

    max_row_count = 10000
    if (row_count > max_row_count):
        raise HTTPException(status_code=400, detail=f"Query returned {row_count} rows. Maximum number of returned rows allowed is {max_row_count}. Please make the query more specific i.e. add more column conditions to reduce the number of returned rows.")

    peewee_query = vizdb.AllSpec.select().where(*where_peewee_exprs)

    return peewee_query
