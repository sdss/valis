# !/usr/bin/env python
# -*- coding: utf-8 -*-
#

from enum import Enum
from functools import lru_cache
from typing import List, Literal, Optional, Union

from pydantic import AnyHttpUrl, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    skeys = Settings.model_json_schema()['properties'].keys()
    return {k: v for k, v in config.items() if k in skeys}


class EnvEnum(str, Enum):
    dev = 'development'
    test = 'testing'
    prod = 'production'


class CacheBackendEnum(str, Enum):
    inmemory = 'in-memory'
    redis = 'redis'
    null = 'null'


class Settings(BaseSettings):
    env: EnvEnum = EnvEnum.dev
    allow_origin: Union[str, List[AnyHttpUrl]] = Field([])
    db_server: str | None = 'pipelines'
    db_remote: bool = False
    db_port: int = 5432
    db_user: Optional[str] = None
    db_host: Optional[str] = 'localhost'
    db_pass: Optional[str] = None
    db_reset: bool = True
    cache_backend: CacheBackendEnum | None = CacheBackendEnum.inmemory
    cache_ttl: int = 15552000 # 6 months
    # Header used for app Bearer tokens when an upstream proxy owns Authorization.
    app_auth_header: str = 'Authorization'
    # cookie settings for the HttpOnly refresh-token cookie; secure defaults to
    # True in production and False in dev/test to avoid HTTPS requirement locally
    cookie_name: str = 'sdss_refresh_token'
    cookie_secure: Optional[bool] = None
    cookie_samesite: Literal['strict', 'lax', 'none'] = 'strict'
    cookie_path: str = '/'
    cookie_max_age: int = 30 * 24 * 3600
    model_config = SettingsConfigDict(env_prefix="valis_")

    @model_validator(mode='after')
    def set_cookie_secure_default(self) -> 'Settings':
        if self.cookie_secure is None:
            self.cookie_secure = self.env == EnvEnum.prod
        return self

    # Keep VALIS_APP_AUTH_HEADER to a plain HTTP header name: no blanks,
    # colon, or line breaks from an accidentally pasted full header line.
    @field_validator('app_auth_header')
    @classmethod
    def valid_app_auth_header(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('app_auth_header must not be empty')
        if any(ch.isspace() or ch in ':\r\n' for ch in value):
            raise ValueError('app_auth_header must be a valid HTTP header name')
        return value

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


@lru_cache
def get_settings():
    """ Get the valis settings """
    cfg = read_valis_config()
    return Settings(**cfg)


settings = get_settings()
