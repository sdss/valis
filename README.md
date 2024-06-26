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

### Solara Dependencies

The default install does not install any of the Solara dependencies for Jdaviz and the SDSS DataView Explorer.  To install these dependencies, run
```
poetry install -E solara
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

Additionally, you can set the environment variable `VALIS_DB_RESET=false` or add `db_reset: false` to `valis.yaml`. This will prevent the DB connection to be closed after a query completes and should speed up new queries. This setting should not be used in production.

## Deployment

This section describes a variety of deployment methods.  Valis uses gunicorn as its
wsgi http server. It binds the app both to port 8000, and a unix socket.  The defaut mode
is to start valis with an awsgi uvicorn server, with 4 workers.

### Deploying Zora + Valis together
See the SDSS [Zora+Valis Docker](https://github.com/sdss/zora_valis_dockers) repo page.

### Deploying at Utah in dataviz-dm
TBD

### Running manually via gunicorn + nginx
 - Setup a local nginx server with a /valis location
 - export VALIS_SOCKET_DIR=/tmp/valis
 - run `gunicorn -c python/valis/wsgi_conf.py valis.wsgi:app`

This also exposes valis to port 8000, and should be available at `http://localhost:8000`.

### Running the Docker

There are two dockerfiles, one for running in development mode and one for production.  To connect valis to the `sdss5db` database, you'll need to set several **VALIS_DB_XXX** environment variables during the `docker run` command.

- VALIS_DB_REMOTE: Set this to True
- VALIS_DB_HOST: the database host machine
- VALIS_DB_USER: the database user
- VALIS_DB_PASS: the database password
- VALIS_DB_PORT: the database port

You will also need to volume mount the SDSS SAS to `/root/sas`, e.g. `-v $SAS_BASE_DIR:/root/sas`.  You can also mount individual SAS directories, but you will need to explicitly set the `SAS_BASE_DIR` environment variable to point the root location, e.g. `-v local/sas/dr17:/data/sas/dr17 -e SAS_BASE_DIR=/data/sas`.

The following examples show how to connect the valis docker to a database running on the same machine, following the database setup instructions above.

**Development**

To build the docker image, run

`docker build -t valis-dev -f Dockerfile.dev .`

To start a container, run
```bash
docker run -p 8000:8000 -e VALIS_DB_REMOTE=True -e VALIS_DB_HOST=host.docker.internal -e VALIS_DB_USER=[user] -e VALIS_DB_PASS=[password] -e VALIS_DB_PORT=6000 -v $SAS_BASE_DIR:/root/sas valis-dev
```

**Production**

To build the docker image, run

`docker build -t valis -f Dockerfile .`

To start a container, run
```bash
docker run -p 8000:8000 -e VALIS_DB_REMOTE=True -e VALIS_DB_HOST=host.docker.internal -e VALIS_DB_USER=[user] -e VALIS_DB_PASS=[password] -e VALIS_DB_PORT=6000 -v $SAS_BASE_DIR:/root/sas valis
```
Note:  If your docker vm has only a small resource allocation, the production container may crash on start, due to the number of workers allocated. You can adjust the number of workers with the `VALIS_WORKERS` envvar.  For example, add `-e VALIS_WORKERS=2` to scale the number of workers down to 2.

### Podman

All dockerfiles work with `podman`, and the syntax is the same as above.  Simply replace `docker` with `podman`.
