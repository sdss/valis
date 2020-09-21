# valis

![Versions](https://img.shields.io/badge/python->3.7-blue)
[![Documentation Status](https://readthedocs.org/projects/sdss-valis/badge/?version=latest)](https://sdss-valis.readthedocs.io/en/latest/?badge=latest)
[![Travis (.org)](https://img.shields.io/travis/sdss/valis)](https://travis-ci.org/sdss/valis)
[![codecov](https://codecov.io/gh/sdss/valis/branch/master/graph/badge.svg)](https://codecov.io/gh/sdss/valis)

the SDSS API for delivering and accessing remote information

## Installation
### Developer Install
```
git clone https://github.com/sdss/valis valis
cd valis
poetry install
```

## Deployment
### Running manually via gunicorn + nginx
 - Setup a local nginx server with a /valis location
 - export VALIS_SOCKET_DIR=/tmp/valis
 - run `gunicorn -c python/valis/wsgi_conf.py valis.wsgi:app`

### Running via the Docker Container
Currently the dockerfile only maps to tcp ports
TODO: get working with unix sockets
```
# build the image
docker build -t valis .

# run the container mapping to local port 8000
docker run -d --name valis -p 8000:80 valis
```
Then navigate to `http://localhost:8000/valis`. To stop the service, run `docker stop valis; docker rm valis;`

### Running Docker Compose
Currently the docker-compose only maps to tcp ports
TODO: get working with unix sockets; fold in nginx services
```
# setup the app mapping to local port 8000
docker-compose up -d
```
Then navigate to `http://localhost:8000/valis`.  To stop the service,
```
# stop the service
docker-compose stop

# take down the container
docker-compose down
```
