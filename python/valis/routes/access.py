# !/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Filename: access.py
# Project: routes
# Author: Brian Cherinka
# Created: Wednesday, 16th September 2020 6:16:40 pm
# License: BSD 3-clause "New" or "Revised" License
# Copyright (c) 2020 Brian Cherinka
# Last Modified: Wednesday, 16th September 2020 6:16:40 pm
# Modified By: Brian Cherinka


from __future__ import absolute_import, division, print_function

import os
import pathlib
import re
from enum import Enum

from typing import Dict, List, Optional, Type, Union

from coverage.debug import pp
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import Path as FPath
from fastapi_restful.cbv import cbv
from pydantic import BaseModel, Field, PrivateAttr, StringConstraints, ValidationError, field_validator, model_validator
from sdss_access.path import Path
from typing_extensions import Annotated

from valis.routes.base import Base, BaseBody, get_access


class PathPart(str, Enum):
    """A set of pre-defined choices for the `part` query param"""

    full = "full"
    url = "url"
    file = "file"
    location = "location"
    all = "all"


class PathResponse(BaseModel):
    name: Optional[str] = None
    kwargs: Optional[dict] = {}
    template: Optional[str] = None
    full: Optional[str] = None
    url: Optional[str] = None
    file: Optional[str] = None
    location: Optional[str] = None
    exists: Optional[bool] = None
    needs_kwargs: Optional[bool] = Field(None, validate_default=True)
    warning: Optional[str] = None


def verify_path(name: str, filepath: str, release: str) -> pathlib.Path:
    """Verify the filepath

    Verify the filepath after resolution from sdss_access

    Parameters
    ----------
    name : str
        the access product name
    filepath : str
        the filepath
    release : str
        the release

    Returns
    -------
    pathlib.Path
        the resolved target path

    Raises
    ------
    ValueError
        if no authorized root is configured
    ValueError
        if the path contains an unresolved environment variable
    ValueError
        if the path is not absolute
    ValueError
        if the path resolves outside the authorized SAS root
    """
    release_name = release.lower()
    root = os.environ.get("SAS_BASE_DIR")
    if not root:
        raise ValueError("No authorized root configured")

    release_root = pathlib.Path(os.path.join(root, release_name)).resolve(strict=False)
    candidate = pathlib.Path(filepath)

    if candidate.parts[0].startswith("$"):
        raise ValueError("Path contains unresolved environment variable")

    if not candidate.is_absolute():
        raise ValueError("Expected an absolute file path")

    target = candidate.resolve(strict=False)
    if not target.is_relative_to(release_root):
        raise ValueError(f"Path for {name} resolves outside authorized SAS root")

    return target


class PathModel(PathResponse):
    """A validator class for sdss_access path names and kwargs"""

    _path: Path = PrivateAttr()  # private attr so model has correct sdss_access pat

    def __new__(cls, *args, **kwargs):
        cls._path = kwargs.get("_path", None)
        return super(PathModel, cls).__new__(cls)

    @field_validator("name")
    @classmethod
    def is_name(cls, v):
        if v not in cls._path.lookup_names():
            release = "WORK" if cls._path.release in ("sdss5", "sdss4", "sdsswork") else cls._path.release.upper()
            raise ValueError(f"Validation error: path name {v} not a valid sdss_access name for release {release}")
        return v

    @field_validator("kwargs")
    @classmethod
    def good_kwargs(cls, v, info):
        name = info.data.get("name")
        keys = set(cls._path.lookup_keys(name))

        # return if no kwargs specified
        if not v:
            return {}

        # check for bad kwargs
        bad = set(v) - set(keys)
        if bad:
            bstr = ", ".join(bad)
            raise ValueError(f"Validation error: kwargs {bstr} not allowed for name: {name}")

        # check for missing kwargs
        missing = set(keys) - set(v)
        if missing:
            mstr = ", ".join(missing)
            raise ValueError(f"Validation error: Missing kwargs {mstr} for name: {name}")

        # validate the values against path traversal
        for key, value in v.items():
            text = str(value)
            if (
                not isinstance(value, (str, int, float))
                or text in {".", ".."}
                or re.fullmatch(r"[\w.-]+", text) is None
            ):
                raise ValueError(f"Invalid kwargs value for {key}: {value}")

        return v

    @model_validator(mode="after")
    def check_kwargs(self):
        """Check and assign the needs_kwargs attribute"""
        self.needs_kwargs = any(self._path.lookup_keys(self.name))
        return self

    @model_validator(mode="after")
    def check_full_path(self):
        """Ensure the resolved path stays inside the SAS base directory"""
        if not self.kwargs and self.needs_kwargs:
            return self

        # verify the path
        verify_path(self.name, self._path.full(self.name, **self.kwargs), self._path.release)

        return self

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.template = self._path.templates[self.name]
        if self.kwargs or not self.needs_kwargs:
            self.full = self._path.full(self.name, **self.kwargs)
            self.url = self._path.url(self.name, **self.kwargs)
            self.file = self._path.name(self.name, **self.kwargs)
            self.location = self._path.location(self.name, **self.kwargs)
            self.exists = self._path.exists(self.name, **self.kwargs)


class PathBody(BaseBody):
    """Body for SDSS access paths post requests"""

    kwargs: dict = Field(
        {},
        description="The keyword variable arguments defining a path",
        examples=[{"run2d": "v6_1_3", "fieldid": 112360, "mjd": 60052, "catalogid": 27021598150202075}],
    )
    part: PathPart = Field("full", description="The part of the path to return")
    exists: bool = Field(False, description="Flag to check if the path exists")


def _raise_http_path(ee: ValidationError):
    """Raise an HTTPException for a path validation error"""
    # pop the path object
    err = ee.errors(include_context=False)
    if isinstance(err[0]["input"], dict):
        err[0]["input"].pop("_path", None)
    raise HTTPException(status_code=422, detail=err) from ee


async def valid_name(
    name: str = FPath(description="the sdss access path name", example="specLite"), access: Path = Depends(get_access)
):
    """Dependency to validate a path name"""
    try:
        PathModel(name=name, _path=access)
    except ValidationError as ee:
        _raise_http_path(ee)
    else:
        return name


# path kwarg constraint
_PAIR = r"[A-Za-z0-9_]+=[A-Za-z0-9_]+(?:[.-][A-Za-z0-9_]+)*"
key_constr = Annotated[str, StringConstraints(pattern=rf"\A{_PAIR}(?:,{_PAIR})*\z", max_length=1024)]


# /Users/brian/Work/sdss/sas/ipl-3/spectro/boss/redux/v6_1_3/spectra/lite/112360/60052/spec-112360-60052-27021598150202075.fits
# examples
# DR17 - spec-lite; ["plateid=3606", "mjd=55182", "fiberid=22", "run2d=v5_13_2"]
# DR19 - specLite; ["fieldid=112360", "mjd=60052", "catalogid=27021598150202075", "run2d=v6_1_3"]


async def extract_path(
    name: str = Depends(valid_name),
    kwargs: Optional[List[key_constr]] = Query(
        None,
        description="the keyword variable arguments defining a path",
        example=["fieldid=112360", "mjd=60052", "catalogid=27021598150202075", "run2d=v6_1_3"],
    ),
    access: Path = Depends(get_access),
) -> Type[PathModel]:
    """Dependency to extract and parse path name and keyword arguments"""

    # parse the kwargs list into a dict
    params: dict[str, str] = {}
    for item in kwargs or []:
        for pair in item.split(","):
            key, _, value = pair.partition("=")  # the pattern guarantees one "=" per pair
            if key in params:
                raise HTTPException(status_code=422, detail=f"Duplicate keyword argument: {key}")
            params[key] = value

    # validate the name and kwargs with the Path model
    try:
        path = PathModel(name=name, kwargs=params, _path=access)
    except ValidationError as ee:
        _raise_http_path(ee)
    else:
        return path


class KeywordModel(BaseModel):
    """Response model for path keywords"""

    name: str
    kwargs: List[str]


router = APIRouter()


@cbv(router)
class Paths(Base):
    @router.get(
        "/",
        summary="Get a list of all sdss_access path names or templates",
        response_model=Union[Dict[str, List[str]], Dict[str, str]],
    )
    async def get_paths(
        self, templates: bool = Query(False, description="Flag to return templates definitions with names")
    ):
        """Get a list of sdss_access path names"""
        if templates:
            return self.path.templates
        else:
            return {"names": list(self.path.lookup_names())}

    @router.get(
        "/keywords/{name}",
        summary="Get a list of keyword variables for a sdss_acccess path name.",
        response_model=KeywordModel,
    )
    async def get_path_kwargs(self, name: str = Depends(valid_name)):
        """Get a list of input keyword arguments

        Given an sdss_access path name, get the list of input keywords needed
        to construct the full path.

        Parameters
        ----------
            name : str
                a sdss_access path name

        Returns
        -------
            A dict of path name and list of string keywords
        """
        return {"name": name, "kwargs": self.path.lookup_keys(name)}

    @router.get(
        "/{name}",
        summary="Get the template or resolved path for an sdss_access path name.",
        response_model=PathResponse,
        response_model_exclude_unset=True,
    )
    async def get_path_name(
        self,
        path: Type[PathModel] = Depends(extract_path),
        part: PathPart = Query("full", description="The part of the path to return"),
        exists: bool = Query(False, description="Flag to check if the path exists"),
    ):
        """Construct an sdss_access path

        Given a sdss_access path name, constructs the fully resolved path.  sdss_access path
        keyword arguments are passed in as url query parameters,
        e.g. `paths/mangacube?drpver=v2_4_3&wave=LOG&plate=8485&ifu=1901`.  When no query
        parameters, are specified, returns the sdss_access template.

        Parameters
        ----------
            name : str
                a sdss_access path name
            part : str
                the part of the path to extract
            exists : bool
                If set, checks for local file existence and returns True/False

        Returns
        -------
            A string path name

        """
        return self.process_path(path, part, exists)

    @router.post(
        "/{name}",
        summary="Get the template or resolved path for an sdss_access path name.",
        response_model=PathResponse,
        response_model_exclude_unset=True,
    )
    async def post_path_name(
        self, name: str = FPath(description="the sdss access path name", example="specLite"), body: PathBody = None
    ):
        """Construct an sdss_access path

        Given an sdss_access path name and set of input keyword arguments,
        construct the file path using sdss_access methods.  Set `part` keyword to
        indicate the part of the path to form, e.g. "full", "url".  Set `exists` to
        check whether the file exists on the server.

        Parameters
        ----------
            name : str
                a sdss_access path name
            kwargs: dict
                a set of keyword arguments to construct the file path
            part : str
                the part of the path to extract.  Default is "full".
            exists : bool
                If set, checks for local file existence and returns True/False

        Returns
        -------
            A string path name

        """
        # if no kwargs set to empty dict
        kwargs = body.kwargs or {}
        try:
            path = PathModel(name=name, kwargs=kwargs, _path=self.path)
        except ValidationError as ee:
            _raise_http_path(ee)
        else:
            return self.process_path(path, body.part, body.exists)

    def process_path(self, path: Type[PathModel], part: PathPart, exists: bool) -> dict:
        if not path.kwargs and path.needs_kwargs:
            out = path.model_dump(include={"template"})
            out["warning"] = "Warning: No kwargs specified to construct a path.  Returning only template."
            return out
        elif exists:
            return path.model_dump(include={"exists"})
        else:
            return path.model_dump() if part == "all" else path.model_dump(include={part})
