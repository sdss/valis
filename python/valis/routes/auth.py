# !/usr/bin/env python
# -*- coding: utf-8 -*-
#
from __future__ import print_function, division, absolute_import

import httpx
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from fastapi_restful.cbv import cbv

from valis.routes.base import Base, release

router = APIRouter()
auth_callback_router = APIRouter()


class Token(BaseModel):
    """ SDSS OAuth2 access token """
    access_token: str
    token_type: str
    refresh_token: str = None


class User(BaseModel):
    """ SDSS user"""
    username: str
    fullname: str = None
    email: str = None


class CredentialBase(BaseModel):
    msg: str


class Member(CredentialBase):
    """ SDSS member credentials """
    member: User


class Identity(CredentialBase):
    """ SDSS identity credentials """
    identity: str


class CredToken(CredentialBase):
    """ SDSS credentials token """
    access: str
    refresh: str = None


class SDSSAuthPasswordBearer(OAuth2PasswordBearer):

    async def __call__(self, request: Request, release: str = Depends(release)):
        self.release = release or "WORK"
        if 'DR' in self.release:
            return None
        await super().__call__(request)


oauth2_scheme = SDSSAuthPasswordBearer(tokenUrl="auth/login")


async def set_auth(token: str = Depends(oauth2_scheme), release: str = Depends(release)):
    return {"token": token, 'release': release}


auth_base = "https://api.sdss.org/crowd/credential"


@auth_callback_router.post(f"{auth_base}/member", response_model=Member)
def get_member():
    pass


@auth_callback_router.post(f"{auth_base}/identity", response_model=Identity)
def check_identity():
    pass


@auth_callback_router.post(f"{auth_base}/refresh", response_model=CredToken)
def refresh_token():
    pass


@auth_callback_router.post(f"{auth_base}", response_model=CredToken)
def get_token(username: str = Form(...), password: str = Form(...)):
    pass


# create a dict to reference just a single route
callback_dict = {i.name: [i] for i in auth_callback_router.routes}


async def verify_token(request: Request):
    hdrs = {'Credential': request.headers.get('Authorization', '')}
    async with httpx.AsyncClient() as client:
        rr = await client.post('https://api.sdss.org/crowd/credential/identity', headers=hdrs)
        if rr.is_error:
            raise HTTPException(status_code=rr.status_code, detail=rr.content)
        return rr.json()


@cbv(router)
class Auth(Base):

    @router.post("/login", summary='Login to the SDSS API', response_model=Token, callbacks=callback_dict['get_token'])
    async def get_token(self, form_data: OAuth2PasswordRequestForm = Depends()) -> Token:
        """ Authenticate your SDSS user credentials """
        async with httpx.AsyncClient() as client:
            rr = await client.post('https://api.sdss.org/crowd/credential',
                            data={'username': form_data.username, 'password': form_data.password})
            if rr.is_error:
                raise HTTPException(status_code=rr.status_code, detail=rr.content.decode())

            token = rr.json()
            return {"access_token": token['access'], "token_type": "bearer", "refresh_token": token['refresh']}

    @router.post("/verify", summary='Verify an auth token', response_model=Identity, callbacks=callback_dict['check_identity'], dependencies=[Depends(set_auth)])
    async def verify_token(self, user: str = Depends(verify_token)):
        """ Verify an auth token """
        return user

    @router.post("/user", summary='Get user information', response_model=User, callbacks=callback_dict['get_member'], dependencies=[Depends(set_auth)])
    async def get_user(self, request: Request):
        """ Get user information """
        hdrs = {'Credential': request.headers.get('Authorization', '')}
        async with httpx.AsyncClient() as client:
            rr = await client.post('https://api.sdss.org/crowd/credential/member', headers=hdrs)
            if rr.is_error:
                raise HTTPException(status_code=rr.status_code, detail=rr.content.decode())
            data = rr.json()
            return data['member']

    @router.post("/refresh", summary='Refresh your auth token', response_model=Token, callbacks=callback_dict['refresh_token'], dependencies=[Depends(set_auth)])
    async def refresh_token(self, request: Request):
        """ Refresh your auth token """
        hdrs = {'Credential': request.headers.get('Authorization', '')}
        async with httpx.AsyncClient() as client:
            rr = await client.post('https://api.sdss.org/crowd/credential/refresh', headers=hdrs)
            if rr.is_error:
                raise HTTPException(status_code=rr.status_code, detail=rr.content.decode())
            token = rr.json()
            return {"access_token": token['access'], "token_type": "bearer"}