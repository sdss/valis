# !/usr/bin/env python
# -*- coding: utf-8 -*-
#

from enum import Enum
from typing import List, Union, Optional
from valis import config
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator, Field, AnyHttpUrl


def read_valis_config() -> dict:
    """ Read the valis config file

    Read the valis config and extract only
    the relevant keys for the app settings

    Returns
    -------
    dict
        the custom settings config
    """
    skeys = Settings.model_json_schema()['properties'].keys()
    return {k: v for k, v in config.items() if k in skeys}


class EnvEnum(str, Enum):
    dev = 'development'
    test = 'testing'
    prod = 'production'


class Settings(BaseSettings):
    valis_env: EnvEnum = EnvEnum.dev
    allow_origin: Union[str, List[AnyHttpUrl]] = Field([])
    db_server: str = 'pipelines'
    db_remote: bool = False
    db_port: int = 5432
    db_user: Optional[str] = None
    db_host: Optional[str] = 'localhost'
    db_pass: Optional[str] = None
    model_config = SettingsConfigDict(env_prefix="valis_")

    @field_validator('allow_origin')
    @classmethod
    def must_be_list(cls, v):
        if not isinstance(v, list):
            return v.split(',') if ',' in v else [str(v)]
        return [str(i).rstrip('/') for i in v]

    @field_validator('allow_origin')
    @classmethod
    def strip_slash(cls, v):
        return [i.rstrip('/') for i in v]

