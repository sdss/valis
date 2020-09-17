# !/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Filename: wsgi_conf.py
# Project: valis
# Author: Brian Cherinka
# Created: Thursday, 17th September 2020 3:32:41 pm
# License: BSD 3-clause "New" or "Revised" License
# Copyright (c) 2020 Brian Cherinka
# Last Modified: Thursday, 17th September 2020 3:32:41 pm
# Modified By: Brian Cherinka


from __future__ import print_function, division, absolute_import

# this is the config file for gunicorn + uvicorn, the ASGI gateway
#
# run the following from the project terminal or set up a system service
# gunicorn -c wsgi_conf.py valis.wsgi:app

bind = "unix:/tmp/mangawork/valis.sock"
workers = 4
worker_class = "uvicorn.workers.UvicornWorker"
errorlog = '-'
accesslog = '-'
root_path = '/valis'
