# syntax=docker/dockerfile:1.7
#
# Testlyn API Dockerfile.
# Build context MUST be the repo root (uv workspace member at apps/api).
#   docker build -f apps/api/Dockerfile -t testlyn-api .

FROM python:3.13-slim AS builder

WORKDIR /build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Workspace manifests for layer cache
COPY pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml

# Install only production deps for the api workspace package
RUN uv sync --frozen --no-dev --no-install-project --package testlyn-api

# Project source
COPY apps/api/testlyn_api/ apps/api/testlyn_api/
COPY apps/api/alembic.ini apps/api/alembic.ini
COPY apps/api/migrations/ apps/api/migrations/

RUN uv sync --frozen --no-dev --package testlyn-api


FROM python:3.13-slim AS runtime

WORKDIR /app

# Copy the venv at the SAME path it was built at so the absolute-path shebangs
# in /build/.venv/bin/* stay valid. Symlink /app/.venv → /build/.venv so the
# WORKDIR-relative path also resolves.
COPY --from=builder /build/.venv /build/.venv
RUN ln -s /build/.venv /app/.venv

COPY --from=builder /build/apps/api/testlyn_api /app/testlyn_api
COPY --from=builder /build/apps/api/alembic.ini /app/alembic.ini
COPY --from=builder /build/apps/api/migrations /app/migrations

ENV PATH="/build/.venv/bin:$PATH"
ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1

RUN useradd --system --uid 1000 --no-create-home app && chown -R app:app /app /build
USER app

EXPOSE 8080

CMD ["/build/.venv/bin/python", "-m", "uvicorn", "testlyn_api.main:app", "--host", "0.0.0.0", "--port", "8080"]
