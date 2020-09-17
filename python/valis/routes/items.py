# !/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Filename: items.py
# Project: routes
# Author: Brian Cherinka
# Created: Wednesday, 16th September 2020 10:17:15 pm
# License: BSD 3-clause "New" or "Revised" License
# Copyright (c) 2020 Brian Cherinka
# Last Modified: Wednesday, 16th September 2020 10:17:15 pm
# Modified By: Brian Cherinka


from __future__ import print_function, division, absolute_import
from fastapi import APIRouter, HTTPException
from typing import Optional
from pydantic import BaseModel

router = APIRouter()


class Item(BaseModel):
    name: str
    price: float
    is_offer: Optional[bool] = None


@router.get("/")
async def read_items():
    return [{"name": "Item Foo"}, {"name": "item Bar"}]


@router.get("/{item_id}")
def read_item(item_id: int, q: Optional[str] = None):
    return {"name": "Fake Specific Item", "item_id": item_id, "q": q}


@router.put("/{item_id}", tags=["custom"],
            responses={403: {"description": "Operation forbidden"}})
async def update_item(item_id: str, item: Item):
    if item_id != "foo":
        raise HTTPException(status_code=403, detail="You can only update the item: foo")
    return {"item_id": item_id, "name": "The Fighters", "item_price": item.price}
