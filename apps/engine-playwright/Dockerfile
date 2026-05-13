# =============================================================================
# Testlyn Engine — Playwright 2-stage Dockerfile
# =============================================================================
#
# Stage 1: Playwright base (Node + browsers + Python 3.13)
# Stage 2: Add sidecar, tini, and entrypoint.
#
# Playwright version: v1.50.0-noble
# =============================================================================

# ---- Stage 1: Playwright base ----
FROM mcr.microsoft.com/playwright:v1.50.0-noble AS playwright-base

# Install Python 3.13 and uv
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.13 \
        python3.13-venv \
        python3-pip \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.7.2 /uv /usr/local/bin/uv

# ---- Stage 2: Runtime ----
FROM playwright-base AS runtime

ENV TINI_VERSION=v0.19.0
RUN curl -fsSL "https://github.com/krallin/tini/releases/download/${TINI_VERSION}/tini-amd64" \
        -o /usr/local/bin/tini \
    && chmod +x /usr/local/bin/tini

WORKDIR /app

# Copy pyproject so uv can install deps first (layer-cache)
COPY pyproject.toml ./

# Install sidecar runtime deps (no dev extras)
RUN uv pip install --system \
    "google-cloud-bigquery>=3.27" \
    "pydantic>=2" \
    "pydantic-settings>=2" \
    "structlog>=25.3" \
    "tenacity>=9.1" \
    "aiohttp>=3.11" \
    "aiofiles>=24.1"

# Copy sidecar source from apps/engine/sidecar (build context = repo root)
COPY apps/engine/sidecar/ ./sidecar/

# Copy the Playwright-specific parser plugin into its own subdirectory so it
# does NOT overwrite base.py or k6.py that were just copied from the sidecar.
COPY apps/engine-playwright/parser/ ./sidecar/parsers/playwright/

# Copy entrypoint
COPY apps/engine-playwright/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

RUN mkdir -p /tmp/spool /tmp/work

RUN useradd --system --uid 1001 --no-create-home playwright-runner \
    && chown -R playwright-runner:playwright-runner /app /tmp/spool /tmp/work

USER playwright-runner

EXPOSE 8081

ENTRYPOINT ["/usr/local/bin/tini", "--", "/entrypoint.sh"]
