# !/usr/bin/env python
# -*- coding: utf-8 -*-
#

from pydantic import BaseSettings
from enum import Enum


class EnvEnum(str, Enum):
    dev = 'development'
    test = 'testing'
    prod = 'production'


class Settings(BaseSettings):
    valis_env: EnvEnum = EnvEnum.dev


settings = Settings()
