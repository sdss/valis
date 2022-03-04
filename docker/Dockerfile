FROM tiangolo/uvicorn-gunicorn-fastapi:python3.7

# Install Poetry
RUN curl -sSL https://raw.githubusercontent.com/python-poetry/poetry/master/get-poetry.py | POETRY_HOME=/opt/poetry python && \
    cd /usr/local/bin && \
    ln -s /opt/poetry/bin/poetry && \
    poetry config virtualenvs.create false

# Copy using poetry.lock* in case it doesn't exist yet
COPY ./pyproject.toml ./poetry.lock* ./

RUN poetry install --no-root --no-dev

# see https://github.com/tiangolo/uvicorn-gunicorn-fastapi-docker
# for docs on setup and configuration options

# copy over application
COPY ./python/valis /app/app

# copying over a pre-start script
COPY ./docker_prestart.sh /app/prestart.sh

# setting environment variables
ENV MODULE_NAME="valis.wsgi"

# set container socket directory to /tmp/valis ; push that to gunicorn conf
ENV VALIS_SOCKET_DIR='/tmp/valis'
ENV GUNICORN_CONF="/app/app/wsgi_conf.py"

# mount container socket directory
VOLUME ${VALIS_SOCKET_DIR}