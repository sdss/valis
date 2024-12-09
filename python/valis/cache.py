#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Filename: main.py
# Project: app
# Author: José Sánchez-Gallego
# Created: Monday, 9th December 2024
# License: BSD 3-clause "New" or "Revised" License
# Copyright (c) 2020 José Sánchez-Gallego
# Last Modified: Monday, 9th December 2024
# Modified By: José Sánchez-Gallego

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from aiomcache import Client as MemcacheClient
from fastapi_cache import FastAPICache
from fastapi_cache.backends.memcached import MemcachedBackend
from fastapi_cache.backends.redis import RedisBackend
from redis.asyncio.client import Redis

from valis.settings import settings


if TYPE_CHECKING:
    from typing import AsyncIterator

    from fastapi import FastAPI, Request, Response


logger = logging.getLogger("uvicorn.error")

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    backend = settings.cache_backend
    if backend == 'memcached':
        logger.info('Using Memcached backend for caching')
        memcache_client = MemcacheClient('localhost', 11211)
        FastAPICache.init(MemcachedBackend(memcache_client),
                          prefix="fastapi-cache",
                          key_builder=valis_cache_key_builder)
    elif backend == 'redis':
        logger.info('Using Redis backend for caching')
        redis = Redis.from_url("redis://localhost")
        FastAPICache.init(RedisBackend(redis),
                          prefix="fastapi-cache",
                          key_builder=valis_cache_key_builder)
    else:
        raise ValueError(f'Invalid cache backend {backend}')

    yield


def valis_cache_key_builder(
    func,
    namespace: str = "",
    request: Request | None = None,
    response: Response | None = None,
    *args,
    **kwargs,
):
    return ":".join(
        [
            namespace,
            request.method.lower() if request else "",
            request.url.path if request else "",
            repr(sorted(request.query_params.items())) if request else "",
        ]
    )
