# Stage 1: Development stage for Python dependencies
FROM python:3.10-slim as dep-stage

# Set up app dir
WORKDIR /tmp

# Copy project files over
COPY ./pyproject.toml ./poetry.lock ./

# Install system prereq packages
RUN apt-get update && \
    apt-get install -y \
        build-essential \
        git \
        # these are for h5py in sdss_explorer
        curl libhdf5-dev pkg-config \
        # these are for vaex
        libpcre3 libpcre3-dev gcc g++ libboost-all-dev \
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

# need github creds for install of private sdss_explorer
# Arguments to pass credentials
ARG GITHUB_TOKEN
ARG GITHUB_USER

# Configure git to use the token
RUN git config --global credential.helper 'store --file=/root/.git-credentials' && \
    echo "https://${GITHUB_USER}:${GITHUB_TOKEN}@github.com" > /root/.git-credentials

# Install poetry and project dependencies
RUN pip install poetry && \
    poetry config virtualenvs.create false && \
    poetry install -E solara --no-root && \
    rm -rf ~/.cache

# Remove credentials after use
RUN rm /root/.git-credentials && \
    git config --global --unset credential.helper

# Stage 2: Development stage for the project
FROM dep-stage as dev-stage

# Copy the main project files over and install
COPY ./ ./
RUN poetry install -E solara --only main

# Create dir for socket and logs
RUN mkdir -p /tmp/webapp

# Install hips2fits_cutout script
# It is not installable via packager managers (pip, poetry) since there is no setup.py
# Therefore install it manually and not through pyproject.toml dependancies.
RUN poetry add cdshealpix@^0.7.0
RUN git clone https://github.com/cds-astro/hips2fits-cutout.git /usr/lib/hips2fits-cutout
ENV PYTHONPATH=/usr/lib/hips2fits-cutout:$PYTHONPATH

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
FROM dev-stage as build-stage

# Set a label
LABEL org.opencontainers.image.source https://github.com/sdss/valis
LABEL org.opencontainers.image.description "valis production image"

# Expose the port
EXPOSE 8000

# Start the FastAPI app for production
CMD ["poetry", "run", "gunicorn", "-c", "python/valis/wsgi_conf.py", "valis.wsgi:app"]
