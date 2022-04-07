# valis

![Versions](https://img.shields.io/badge/python->3.7-blue)
[![Documentation Status](https://readthedocs.org/projects/sdss-valis/badge/?version=latest)](https://sdss-valis.readthedocs.io/en/latest/?badge=latest)
[![codecov](https://codecov.io/gh/sdss/valis/branch/master/graph/badge.svg)](https://codecov.io/gh/sdss/valis)
[![Build Package](https://github.com/sdss/valis/actions/workflows/build.yml/badge.svg)](https://github.com/sdss/valis/actions/workflows/build.yml)

the SDSS API for delivering and accessing remote information.

This API is built using the [FastAPI](https://fastapi.tiangolo.com/) web server.  Python depdendices are managed with [poetry](https://python-poetry.org/).

## Installation
### Developer Install
```
git clone https://github.com/sdss/valis valis
cd valis
poetry install
```

### Updating Dependencies with Poetry
To update poetry itself, run
```
poetry self update
```

To update the package dependencies for `valis`, run
```
poetry update [package]
```
This will update all the packages, or the specified `[package]`, resolve all dependencies, and update the `poetry.lock` file.

To install new packages and add them to the `pyproject.toml` and `poetry.lock` files, run
```
poetry install [package]
```

### Local Development

To run a local instance for development, run the following from the top level of the `valis` repo.
```
uvicorn valis.wsgi:app --reload
```
This will start a local web server at `http://localhost:8000/valis/`.  The API documentation will be located at `http://localhost:8000/valis/docs`.  Or to see the alternate documentation, go to `http://localhost:8000/valis/redoc/`

## Deployment
### Deploying at Utah in api.sdss.org docker
- Login to `lore` or `manga` machines
- Login to the api.sdss.org docker with `ssh -p 2209 [unid]@api.sdss.org`
- If needed, load valis module with `ml load valis`
- cd to `$VALIS_DIR`
- run `run_valis` alias or `poetry run gunicorn -c python/valis/wsgi_conf.py valis.wsgi:app`

### Running manually via gunicorn + nginx
 - Setup a local nginx server with a /valis location
 - export VALIS_SOCKET_DIR=/tmp/valis
 - run `gunicorn -c python/valis/wsgi_conf.py valis.wsgi:app`
### Running Docker Compose
This builds and sets up the valis docker running with nginx, mapped to a unix socket at `unix:/tmp/valis/valis.sock`.  It binds the internal nginx port 8080 to localhost port 5000.

- Navigate to `docker` folder
- Run `docker-compose -f docker-compose.yml build` to build the docker images
- Run `docker-compose -f docker-compose.yml up -d` to start the containers in detached mode
- Navigate to `http://localhost:5000/valis`
- To stop the service and remove containers, run `docker-compose -f docker-compose.yml down`

