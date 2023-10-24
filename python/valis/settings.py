# !/usr/bin/env python
# -*- coding: utf-8 -*-
#

from pydantic import BaseSettings, validator, Field, AnyHttpUrl
from enum import Enum
from typing import List, Union
from valis import config


def read_valis_config() -> dict:
    """ Read the valis config file

    Read the valis config and extract only
    the relevant keys for the app settings

    Returns
    -------
    dict
        the custom settings config
    """
    skeys = Settings.schema()['properties'].keys()
    return {k: v for k, v in config.items() if k in skeys}



class EnvEnum(str, Enum):
    dev = 'development'
    test = 'testing'
    prod = 'production'


class Settings(BaseSettings):
    valis_env: EnvEnum = EnvEnum.dev
    allow_origin: Union[str, List[AnyHttpUrl]] = Field([], env="VALIS_ALLOW_ORIGIN")
    db_server: str = 'pipelines'
    db_remote: bool = False
    db_port: int = 5432
    db_user: str = None
    db_host: str = 'localhost'
    db_pass: str = None

    class Config:
        env_prefix = "valis_"

    @validator('allow_origin')
    def must_be_list(cls, v):
        if not isinstance(v, list):
            return v.split(',') if ',' in v else [v]
        return v

