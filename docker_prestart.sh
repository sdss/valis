#! /usr/bin/env bash

# create a symlink from /app/app to /app/valis so container
# understands that valis is an importable python package
#
ln -s app valis
