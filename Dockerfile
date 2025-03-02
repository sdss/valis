# Stage 1: Development stage for Python dependencies
FROM python:3.10-slim as dep-stage

# Set up tmp dir
WORKDIR /tmp

# UV settings
# Enable bytecode compilation, copy from cache instal of links b/c mounted, dont download python
ENV UV_COMPILE_BYTECODE=1 
ENV UV_LINK_MODE=copy 
ENV UV_PYTHON_DOWNLOADS=0 

# Copy project files over
COPY ./pyproject.toml ./uv.lock /tmp

# Install system prereq packages
RUN apt-get update && \
    apt-get install -y \
        build-essential \
        git \
        # these are for h5py in sdss_explorer
        curl libhdf5-dev pkg-config \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# need github creds for install of private sdss_explorer
# Arguments to pass credentials
ARG GITHUB_TOKEN
ARG GITHUB_USER

# Configure git to use the token
RUN git config --global credential.helper 'store --file=/root/.git-credentials' && \
    echo "https://${GITHUB_USER}:${GITHUB_TOKEN}@github.com" > /root/.git-credentials

# Installing uv and then project dependencies
RUN pip install uv
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev --extra solara

# Stage 2: Development stage for the project
FROM dep-stage as dev-stage

# Copy the main project files over and install
COPY ./ ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra solara

# Remove credentials after use
RUN rm /root/.git-credentials && \
    git config --global --unset credential.helper

# Create dir for socket and logs
RUN mkdir -p /tmp/webapp

# Setting environment variables
# these can be manually overridden
ENV PATH="/tmp/.venv/bin:$PATH"
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
CMD ["uv", "run", "gunicorn", "-c", "python/valis/wsgi_conf.py", "valis.wsgi:app"]
