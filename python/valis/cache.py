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

import hashlib
import json
import logging
from contextlib import asynccontextmanager
from functools import wraps
from inspect import Parameter, isawaitable, iscoroutinefunction
from typing import (
    TYPE_CHECKING,
    Awaitable,
    Callable,
    List,
    Optional,
    ParamSpec,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast
)

from fastapi.dependencies.utils import (
    get_typed_return_annotation,
    get_typed_signature
)
from fastapi_cache import Backend, FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from fastapi_cache.backends.redis import RedisBackend
from fastapi_cache.decorator import _augment_signature, _locate_param
from redis.asyncio.client import Redis
from starlette.requests import Request
from starlette.responses import Response
from starlette.status import HTTP_304_NOT_MODIFIED

from valis.settings import settings


if TYPE_CHECKING:
    from typing import AsyncIterator

    from fastapi import FastAPI
    from fastapi_cache.coder import Coder
    from fastapi_cache.types import KeyBuilder


__all__ = ['valis_cache', 'lifespan', 'valis_cache_key_builder']


P = ParamSpec("P")
R = TypeVar("R")


logger = logging.getLogger("uvicorn.error")

CACHE_TTL: float = 15_552_000 # 6 months


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    backend = settings.cache_backend
    if backend == 'in-memory':
        logger.info('Using in-memory backend for caching')
        FastAPICache.init(InMemoryBackend(),
                          prefix="fastapi-cache",
                          key_builder=valis_cache_key_builder)
    elif backend == 'redis':
        logger.info('Using Redis backend for caching')
        redis = Redis.from_url("redis://localhost")
        FastAPICache.init(RedisBackend(redis),
                          prefix="fastapi-cache",
                          key_builder=valis_cache_key_builder)
    elif backend == 'null' or not backend:
        logger.info('Using null backend for caching')
        FastAPICache.init(NullCacheBackend(),
                          prefix="fastapi-cache",
                          key_builder=valis_cache_key_builder)
    else:
        raise ValueError(f'Invalid cache backend {backend}')

    yield


async def valis_cache_key_builder(
    func,
    namespace: str = "",
    request: Request | None = None,
    _: Response | None = None,
    *args,
    **kwargs,
):
    query_params = request.query_params.items() if request else []

    try:
        body_json = await request.json()
        body = sorted(body_json.items()) if body_json else []
    except json.JSONDecodeError:
        body = []

    hash = hashlib.new('md5')
    for param,value in list(query_params) + body:
        hash.update(param.encode())
        hash.update(str(value).encode())

    params_hash = hash.hexdigest()[0:8]

    url = request.url.path.replace('/', '_') if request else ""
    if url.startswith('_'):
        url = url[1:]

    chunks = [
            namespace,
            request.method.lower() if request else "",
            url,
            params_hash,
        ]

    return ":".join(chunks)


def valis_cache(
    expire: Optional[int] = CACHE_TTL,
    coder: Optional[Type[Coder]] = None,
    key_builder: Optional[KeyBuilder] = None,
    namespace: str = "valis-cache",
    injected_dependency_namespace: str = "__fastapi_cache",
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[Union[R, Response]]]]:
    """Caches an API route.

    This is a copy of the ``cache`` decorator from ``fastapi_cache`` with some
    modifications to allow using it with POST requests. This version should be used
    with a key builder that hashes the body of the request in addition to the function
    arguments.

    """

    injected_request = Parameter(
        name=f"{injected_dependency_namespace}_request",
        annotation=Request,
        kind=Parameter.KEYWORD_ONLY,
    )
    injected_response = Parameter(
        name=f"{injected_dependency_namespace}_response",
        annotation=Response,
        kind=Parameter.KEYWORD_ONLY,
    )

    def wrapper(
        func: Callable[P, Awaitable[R]]
    ) -> Callable[P, Awaitable[Union[R, Response]]]:
        # get_typed_signature ensures that any forward references are resolved first
        wrapped_signature = get_typed_signature(func)
        to_inject: List[Parameter] = []
        request_param = _locate_param(wrapped_signature, injected_request, to_inject)
        response_param = _locate_param(wrapped_signature, injected_response, to_inject)
        return_type = get_typed_return_annotation(func)

        @wraps(func)
        async def inner(*args: P.args, **kwargs: P.kwargs) -> Union[R, Response]:
            nonlocal coder
            nonlocal expire
            nonlocal key_builder

            async def ensure_async_func(*args: P.args, **kwargs: P.kwargs) -> R:
                """Run cached sync functions in thread pool just like FastAPI."""
                # if the wrapped function does NOT have request or response in
                # its function signature, make sure we don't pass them in as
                # keyword arguments
                kwargs.pop(injected_request.name, None)
                kwargs.pop(injected_response.name, None)

                if iscoroutinefunction(func):
                    # async, return as is.
                    # unintuitively, we have to await once here, so that caller
                    # does not have to await twice. See
                    # https://stackoverflow.com/a/59268198/532513
                    return await func(*args, **kwargs)
                else:
                    # sync, wrap in thread and return async
                    # see above why we have to await even although caller also awaits.
                    return await run_in_threadpool(func, *args, **kwargs)  # type: ignore[arg-type]

            copy_kwargs = kwargs.copy()
            request: Optional[Request] = copy_kwargs.pop(request_param.name, None)  # type: ignore[assignment]
            response: Optional[Response] = copy_kwargs.pop(response_param.name, None)  # type: ignore[assignment]

            prefix = FastAPICache.get_prefix()
            coder = coder or FastAPICache.get_coder()
            expire = expire or FastAPICache.get_expire()
            key_builder = key_builder or FastAPICache.get_key_builder()
            backend = FastAPICache.get_backend()
            cache_status_header = FastAPICache.get_cache_status_header()

            cache_key = key_builder(
                func,
                f"{prefix}:{namespace}",
                request=request,
                response=response,
                args=args,
                kwargs=copy_kwargs,
            )
            if isawaitable(cache_key):
                cache_key = await cache_key
            assert isinstance(cache_key, str)  # noqa: S101  # assertion is a type guard

            try:
                ttl, cached = await backend.get_with_ttl(cache_key)
            except Exception:
                logger.warning(
                    f"Error retrieving cache key '{cache_key}' from backend:",
                    exc_info=True,
                )
                ttl, cached = 0, None

            if cached is None  or (request is not None and request.headers.get("Cache-Control") == "no-cache"):  # cache miss
                result = await ensure_async_func(*args, **kwargs)
                to_cache = coder.encode(result)

                try:
                    await backend.set(cache_key, to_cache, expire)
                except Exception:
                    logger.warning(
                        f"Error setting cache key '{cache_key}' in backend:",
                        exc_info=True,
                    )

                if response:
                    response.headers.update(
                        {
                            "Cache-Control": f"max-age={expire}",
                            "ETag": f"W/{hash(to_cache)}",
                            cache_status_header: "MISS",
                        }
                    )

            else:  # cache hit
                if response:
                    etag = f"W/{hash(cached)}"
                    response.headers.update(
                        {
                            "Cache-Control": f"max-age={ttl}",
                            "ETag": etag,
                            cache_status_header: "HIT",
                        }
                    )

                    if_none_match = request and request.headers.get("if-none-match")
                    if if_none_match == etag:
                        response.status_code = HTTP_304_NOT_MODIFIED
                        return response

                result = cast(R, coder.decode_as_type(cached, type_=return_type))

            return result

        inner.__signature__ = _augment_signature(wrapped_signature, *to_inject)  # type: ignore[attr-defined]

        return inner

    return wrapper


class NullCacheBackend(Backend):
    """A null cache backend that does no caching and always runs the route."""

    async def get_with_ttl(self, key: str) -> Tuple[int, Optional[bytes]]:
        return 0, None

    async def get(self, key: str) -> Optional[bytes]:
        return None

    async def set(self, key: str, value: bytes, expire: Optional[int] = None) -> None:
        pass

    async def clear(self, namespace: Optional[str] = None, key: Optional[str] = None) -> int:
        pass
