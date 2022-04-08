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
# see https://www.uvicorn.org/ for uvicorn docs and
# https://docs.gunicorn.org/en/latest/settings.html for available gunicorn
# settings.
#
# run the following from the project terminal or set up a system service
# gunicorn -c wsgi_conf.py valis.wsgi:app
import os

socket_dir = os.getenv("VALIS_SOCKET_DIR", '/tmp/valis')
bind = f"unix:{socket_dir}/valis.sock"
workers = 4
worker_class = "uvicorn.workers.UvicornWorker"
daemon = True
errorlog = os.path.join(os.getenv("VALIS_LOGS_DIR", '/var/www/valis/logs'), 'valis_app_error.log')
accesslog = os.path.join(os.getenv("VALIS_LOGS_DIR", '/var/www/valis/logs'), 'valis_app_access.log')
root_path = '/valis'
