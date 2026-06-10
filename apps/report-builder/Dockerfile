# syntax=docker/dockerfile:1.7
# Testlyn report-builder — PDF + AI summary worker.
# Phase 1 ships as a stub; this Dockerfile is the production target shape.

FROM python:3.13-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libcairo2 libpango-1.0-0 libpangoft2-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5.0 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml ./
COPY report_builder ./report_builder
# Jinja templates live OUTSIDE the package (pdf.py resolves
# TEMPLATES_DIR = report_builder/../templates → /app/templates). Without this
# COPY every render raises TemplateNotFound at runtime.
COPY templates ./templates
RUN uv venv /opt/venv && \
    VIRTUAL_ENV=/opt/venv uv pip install --no-cache .

FROM python:3.13-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
        libcairo2 libpango-1.0-0 libpangoft2-1.0-0 tini \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app /app

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
USER 1000:1000

ENTRYPOINT ["tini", "--"]
CMD ["python", "-m", "report_builder.runner"]
