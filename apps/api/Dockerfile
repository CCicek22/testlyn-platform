# syntax=docker/dockerfile:1.7
FROM python:3.13-slim AS builder

WORKDIR /build

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency manifests first for layer cache
COPY pyproject.toml .
COPY uv.lock* .

# Install only production deps into /build/.venv
RUN uv sync --frozen --no-dev --no-install-project

# Copy application source
COPY testlyn_api/ testlyn_api/

# Install the project itself
RUN uv sync --frozen --no-dev


FROM gcr.io/distroless/python3-debian12:nonroot

WORKDIR /app

# Copy venv from builder
COPY --from=builder /build/.venv /app/.venv
COPY --from=builder /build/testlyn_api /app/testlyn_api

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["/app/.venv/bin/uvicorn", "testlyn_api.main:app", "--host", "0.0.0.0", "--port", "8080"]
