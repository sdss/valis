# !/usr/bin/env python
# -*- coding: utf-8 -*-
#


from sdss_access.path import Path

from valis.utils.versions import get_tags


def build_file_path(values: dict, product: str, release: str, remap: dict = None) -> str:
    """ Build a filepath to an SDSS data product

    Constructs the SAS filepath on disk for an SDSS data product for a
    particular data release.  Takes an input ``values`` map of all the
    necessary keywords to populate the ``sdss_access`` path template for
    the input product.

    If a key in the input ``values`` does not match the name of the key in the
    path template, the ``remap`` kwarg can be used provide that remapping.  For
    example, the boss field id is specified as ``fieldid`` in the database, but as
    ``field`` in the specLite path template.  These can be remapped with
    ``{"fieldid": "field"}``.

    Parameters
    ----------
    values : dict
        the input data values to give to the path template
    product : str
        the sdss_access data product name
    release : str
        the data release
    remap : dict, optional
        a mapping between input keys and path template keys, by default None

    Returns
    -------
    str
        the filepath on disk

    Raises
    ------
    ValueError
        when the product is not in sdss_access
    ValueError
        when not all path template keywords can be found
    """
    if not values:
        print('No input values dictionary found.  Cannot build filepath.')
        return ''

    path = Path(release=release)

    if product not in path.lookup_names():
        raise ValueError(f'Path name {product} not in the list of sdss_access '
                         f'paths for release {release}. Check if the tree is correct.')

    # look up path template keys
    kwargs = path.lookup_keys(product)

    # get the software tags
    tags = get_tags(release)

    # build the path keyword dictionary
    # look for keyword values in order of:
    #   model fields, remapped model fields, or software tag
    new = {}
    remap = remap or {}
    for kwarg in kwargs:
        new[kwarg] = values.get(kwarg) or values.get(remap.get(kwarg)) or tags.get(kwarg)

    # check final kwargs
    if not all(new.values()):
        raise ValueError('Not all path keywords found in model fields or tags: '
                         f"{[k for k, v in new.items() if not v]}.  Can't build filepath.")

    # build the filepath
    return path.full(product, **new)


def build_boss_path(values: dict, release: str, lite: bool = True) -> str:
    """ Build a BOSS or BHWM file path

    Builds a BOSS or BHM file path to the specLite or specFull files.
    This handles the change in sdss_access path name after data
    release 18 from prior releases.

    It also remaps the database ``fieldid`` to path template ``field``.

    Parameters
    ----------
    values : dict
        the input data values to give to the path template
    release : str
        the data release
    lite : bool, optional
        Flag to indicate the specLite file, by default True

    Returns
    -------
    str
        the output file path
    """
    if 'IPL' in release or 'WORK' in release or int(release.split('DR')[-1]) >= 18:
        name = 'specLite' if lite else 'specFull'
    else:
        name = 'spec-lite' if lite else 'spec'

    return build_file_path(values, name, release, remap={'fieldid': 'field'})
