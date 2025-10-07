# Stage 1: Development stage for Python dependencies
FROM python:3.12-slim AS dep-stage

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_PYTHON_DOWNLOADS=0
ENV VIRTUAL_ENV=/app/venv

# Set up app dir
WORKDIR /tmp

# Copy project files over
COPY ./pyproject.toml ./uv.lock ./

# Install system prereq packages
RUN apt-get update && \
    apt-get install -y \
        build-essential \
        git \
        # these are for h5py in sdss_explorer
        curl libhdf5-dev pkg-config \
        # these are for vaex
        gcc g++ libboost-all-dev \
        libffi-dev python3-dev libxml2-dev libxslt-dev \
        libpq-dev zlib1g-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Rust for sdss_explorer
RUN curl https://sh.rustup.rs -sSf | sh -s -- -y && . /root/.cargo/env
ENV PATH="/root/.cargo/bin:$PATH"

# Add a command to check if cargo is available
RUN cargo --version

# setup correct wheels for vaex
# normal build hangs/fails like https://github.com/vaexio/vaex/issues/2382
# temp solution, see https://github.com/vaexio/vaex/pull/2331
ENV PIP_FIND_LINKS=https://github.com/ddelange/vaex/releases/expanded_assets/core-v4.17.1.post4
RUN pip install --force-reinstall vaex
ENV PIP_FIND_LINKS=

# # Install poetry and project dependencies
# RUN pip install poetry && \
#     poetry config virtualenvs.create false && \
#     poetry install -E solara --no-root && \
#     rm -rf ~/.cache

# Installing uv and then project dependencies
RUN pip install uv
RUN uv venv /app/venv # make venv
RUN --mount=type=cache,target=/root/.cache/uv \
    #--mount=type=bind,source=uv.lock,target=uv.lock \
    #--mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev --extra solara


# Stage 2: Development stage for the project
FROM dep-stage AS dev-stage

# Copy the main project files over and install
COPY ./ ./
#RUN poetry install -E solara --only main
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra solara

# Create dir for socket and logs
RUN mkdir -p /tmp/webapp

# Setting environment variables
# these can be manually overridden
ENV MODULE_NAME="valis.wsgi"
ENV VALIS_SOCKET_DIR='/tmp/webapp'
ENV VALIS_LOGS_DIR='/tmp/webapp'
ENV VALIS_ALLOW_ORIGIN="https://data.sdss5.org/zora/"
ENV VALIS_DB_REMOTE=True
ENV VALIS_ENV="production"
ENV SOLARA_CHECK_HOOKS="off"

# Stage 3: Build stage (inherits from dev-stage)
FROM dev-stage AS build-stage

# Set a label
LABEL org.opencontainers.image.source=https://github.com/sdss/valis
LABEL org.opencontainers.image.description="valis production image"

# Expose the port
EXPOSE 8000

# Start the FastAPI app for production
#CMD ["poetry", "run", "gunicorn", "-c", "python/valis/wsgi_conf.py", "valis.wsgi:app"]
CMD ["uv", "run", "gunicorn", "-c", "python/valis/wsgi_conf.py", "valis.wsgi:app"]
