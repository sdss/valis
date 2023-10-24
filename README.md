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

### Database Connection

Valis uses the `sdssdb` package for all connections to databases.  The most relevant database for the API is the `sdss5db` on `pipelines.sdss.org`.  The easiest way to connect is through a local SSH tunnel. To set up a tunnel,

1. Add the following to your `~/.ssh/config`. Replace `unid` with your Utah unid.

```
Host pipe
        HostName pipelines.sdss.org
        User [unid]
        ForwardX11Trusted yes
        ProxyCommand ssh -A [unid]@mwm.sdss.org nc %h %p
```
1. In a terminal, create an ssh tunnel to the pipelines database localhost port 5432, to a some local port. E.g. this maps the remote db localhost port 5432 to local machine on port 6000.
```
    ssh -L 6000:localhost:5432 pipe
```
2. Optionally, update your `~/.pgass` file with the following lines. Replace `port`, `unid`, and `password`, with your tunneled port, Utah unid, and db password, respectively. Alternatively, just set the VALIS_DB_PASS environment variable with your database password.
```
localhost:[port]:*:[unid]:[password]
host.docker.internal:[port]:*:[unid]:[password]
```
3. Set the following environment variables.

- export VALIS_DB_PORT=6000
- export VALIS_DB_USER={unid}
- export VALIS_DB_PASS={password} (if skipped step 2.)

or optionally add them to the `~/.config/sdss/valis.yaml` configuration file.

```
allow_origin: ['http://localhost:3000']
db_remote: true
db_port: 6000
db_user: {unid}
```


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

