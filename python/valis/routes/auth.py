# !/usr/bin/env python
# -*- coding: utf-8 -*-
#
from __future__ import print_function, division, absolute_import

import requests
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_utils.cbv import cbv

from valis.routes.base import Base

router = APIRouter()

class Token(BaseModel):
    access_token: str
    token_type: str


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
        return {"access_token": token, "token_type": "bearer"}

