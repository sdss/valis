# !/usr/bin/env python
# -*- coding: utf-8 -*-
#
from __future__ import print_function, division, absolute_import

import requests
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from fastapi_utils.cbv import cbv

from valis.routes.base import Base, release

router = APIRouter()

class Token(BaseModel):
    access_token: str
    token_type: str
    refresh_token: str

class User(BaseModel):
    username: str
    fullname: str = None
    email: str = None


class SDSSAuthPasswordBearer(OAuth2PasswordBearer):
    
    async def __call__(self, request: Request, release: str = Depends(release)):
        self.release = release or "WORK"
        if self.release != 'WORK':
            return None
        await super().__call__(request)
        
oauth2_scheme = SDSSAuthPasswordBearer(tokenUrl="auth/login")

async def set_auth(token: str = Depends(oauth2_scheme), release: str = Depends(release)):
    return {"token": token, 'release': release}


def verify_token(request: Request):
    hdrs = {'Credential': request.headers.get('Authorization')}
    rr = requests.post('https://api.sdss.org/collaboration/credential/identity', headers=hdrs)
    if not rr.ok:
        raise HTTPException(status_code=rr.status_code, detail=rr.json())
    return rr.json()

@cbv(router)
class Auth(Base):
    
    @router.post("/login", summary='Login to the SDSS API', response_model=Token)
    async def get_token(self, form_data: OAuth2PasswordRequestForm = Depends()) -> dict:
        """ Authenticate your SDSS user credentials """

        rr = requests.post('https://api.sdss.org/collaboration/credential', 
                           data={'username': form_data.username, 'password': form_data.password})
        if not rr.ok:
            raise HTTPException(status_code=rr.status_code, detail=rr.json())
        
        token = rr.json()
        return {"access_token": token['access'], "token_type": "bearer", "refresh_token": token['refresh']}

    @router.post("/verify", summary='Verify an auth token')
    async def verify_token(self, user: str = Depends(verify_token)):
        return user

    @router.post("/user", summary='Get user information', response_model=User)
    async def get_user(self, request: Request):
        hdrs = {'Credential': request.headers.get('Authorization')}
        rr = requests.post('https://api.sdss.org/collaboration/credential/member', headers=hdrs)
        if not rr.ok:
            raise HTTPException(status_code=rr.status_code, detail=rr.json())
        data = rr.json()
        return data['member']
    
    @router.post("/refresh", summary='Refresh your auth token', response_model=Token)
    async def refresh_token(self, request: Request):
        hdrs = {'Credential': request.headers.get('Authorization')}
        rr = requests.post('https://api.sdss.org/collaboration/credential/refresh', headers=hdrs)
        if not rr.ok:
            raise HTTPException(status_code=rr.status_code, detail=rr.json())
        token = rr.json()
        return {"access_token": token['access'], "token_type": "bearer"}   