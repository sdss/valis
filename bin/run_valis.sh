#!/bin/bash
# startup script for valis; called by the api.sdss.org docker

# create the unix socket directory
mkdir -p /tmp/valis

# cd to valis repo
cd $VALIS_DIR

# run the alias-ed command
run_valis