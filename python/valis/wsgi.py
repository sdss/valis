# !/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Filename: wsgi.py
# Project: valis
# Author: Brian Cherinka
# Created: Thursday, 17th September 2020 3:31:40 pm
# License: BSD 3-clause "New" or "Revised" License
# Copyright (c) 2020 Brian Cherinka
# Last Modified: Thursday, 17th September 2020 3:31:40 pm
# Modified By: Brian Cherinka


from __future__ import print_function, division, absolute_import
from .main import app

if __name__ == "__main__":
    app.run()


