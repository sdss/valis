FROM tiangolo/uvicorn-gunicorn-fastapi:python3.7

# Git checkout of valis
WORKDIR /tmp
RUN git clone --depth 1 https://github.com/sdss/valis project

# Install Poetry
RUN curl -sSL https://raw.githubusercontent.com/python-poetry/poetry/master/get-poetry.py | POETRY_HOME=/opt/poetry python && \
    cd /usr/local/bin && \
    ln -s /opt/poetry/bin/poetry && \
    poetry config virtualenvs.create false

# Install the project and its dependencies
WORKDIR /tmp/project
RUN poetry install --no-dev

# copy over application
RUN cp -r python/valis /app

WORKDIR /app

# copying over a pre-start script
COPY ./docker_prestart.sh /app/prestart.sh

# see https://github.com/tiangolo/uvicorn-gunicorn-fastapi-docker
# for docs on setup and configuration options

# setting environment variables
ENV MODULE_NAME="valis.wsgi"

# set container socket directory to /tmp/valis ; push that to gunicorn conf
ENV VALIS_SOCKET_DIR='/tmp/valis'
ENV GUNICORN_CONF="/app/app/wsgi_conf.py"

