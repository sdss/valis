# !/usr/bin/env python
# -*- coding: utf-8 -*-
#
from collections import ChainMap

try:
    from datamodel.models import releases
    from datamodel.models import tags
    from datamodel.models.releases import Release
except ImportError:
    releases = tags = Release = None


def get_tag_info(release: str) -> dict:
    """ Get the software tag info for a given release

    Get all of the pipeline software tags for a given release
    from the SDSS datamodel.  Outputs a dictionary of pipeline
    version keys and their values, e.g.
    ``{'apred_vers': '1.2', 'run2d': 'v6_1_1'}``

    Parameters
    ----------
    release : str
        the data release

    Returns
    -------
    dict
        the sofware tags
    """
    if not tags:
        raise RuntimeError('No tag models found.')

    # get the software tags and group by data release
    vers = tags.group_by('release')

    # collapse the dict down one level (i.e. remove the survey key)
    collapsed = {k: dict(ChainMap(*vers[k].values())) for k in vers}
    return collapsed.get(release)


def get_latest_release() -> Release:
    """ Get the latest data release

    Get the most recent data release by release date
    from the SDSS datamodel.

    Returns
    -------
    Release
        an SDSS datamodel Release
    """
    if not releases:
        raise RuntimeError()

    # sort the releases by date
    releases.sort('release_date')

    # return the 2nd to last one. last element is always WORK (unreleased)
    return releases[-2]


def get_latest_tag_info() -> dict:
    """ Get the latest tag info

    Get the latest pipeline software tag
    info from the most recent data release.

    Returns
    -------
    dict
        the software tags
    """
    # get the latest release and resolve its tags
    rel = get_latest_release()
    return get_tag_info(rel.name)


def get_tags(release: str) -> dict:
    """ Get the pipeline software tags

    Get the pipeline software tags for a given data release.
    A WORK release always grabs the latest data release, otherwise
    returns the tags for the requested release.

    Parameters
    ----------
    release : str
        the data release

    Returns
    -------
    dict
        the software tags
    """
    return get_latest_tag_info() if release == 'WORK' else get_tag_info(release)


def get_software_tag(release: str, key: str) -> str:
    """ Get a specific software tag for a data release

    Get a software tag, e.g. "run2d" from the tag info
    for a specific data release.

    Parameters
    ----------
    release : str
        the data release
    key : str
        the software tag key name

    Returns
    -------
    str
        the tag version
    """
    # get the relevant software tag
    return get_tags(release).get(key)
