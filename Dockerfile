# Stage 1: Development stage for Python dependencies
FROM python:3.10-slim as dep-stage

# Set up app dir
WORKDIR /tmp

# Copy project files over
COPY ./pyproject.toml ./poetry.lock ./

# Install build-essential package
RUN apt-get update && \
    apt-get install -y \
        build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install poetry and project dependencies
RUN pip install poetry && \
    poetry config virtualenvs.create false && \
    poetry install --no-root && \
    rm -rf ~/.cache

# Stage 2: Development stage for the project
FROM dep-stage as dev-stage

# Copy the main project files over and install
COPY ./ ./
RUN poetry install --only main

# Create dir for socket and logs
RUN mkdir -p /tmp/webapp

# Setting environment variables
# these can be manually overridden
ENV MODULE_NAME="valis.wsgi"
ENV VALIS_SOCKET_DIR='/tmp/webapp'
ENV VALIS_LOGS_DIR='/tmp/webapp'
ENV VALIS_ALLOW_ORIGIN="http://localhost:8080"
ENV VALIS_DB_REMOTE=True

# Stage 3: Build stage (inherits from dev-stage)
FROM dev-stage as build-stage

# Set a label
LABEL org.opencontainers.image.source https://github.com/sdss/valis
LABEL org.opencontainers.image.description "valis production image"

# Expose the port
EXPOSE 8000

# Start the FastAPI app for production
CMD ["poetry", "run", "gunicorn", "-c", "python/valis/wsgi_conf.py", "valis.wsgi:app"]
