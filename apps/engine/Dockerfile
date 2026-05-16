# syntax=docker/dockerfile:1.7
# =============================================================================
# Testlyn Engine — 2-stage Dockerfile
# Build context MUST be the repo root (uv workspace member at apps/engine).
#   docker build -f apps/engine/Dockerfile -t testlyn-engine .
# =============================================================================
#
# Stage 1: Extract the unmodified stock k6 binary.
#   - Uses the official grafana/k6 image (pinned to 1.3.0).
#   - AGPL compliance: k6 is NEVER modified, compiled, or linked against.
#     It is copied as a pre-built binary and invoked ONLY via subprocess in
#     entrypoint.sh. No xk6 extensions. No Go vendoring of k6 source.
#     See CLAUDE.md §2 rule #1 and ADR-003.
#
# Stage 2: Builder — uv workspace sync for testlyn-engine.
# Stage 3: Runtime — copy venv + sidecar source.
#
# k6 version: 1.3.0 — re-verify JSON output schema on bump per spec §4.
# =============================================================================

# ---- Stage 1: extract k6 binary ----
FROM grafana/k6:1.3.0 AS k6

# ---- Stage 2: builder — install Python deps via uv workspace ----
FROM python:3.13-slim AS builder

WORKDIR /build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Workspace manifests for layer cache (mirrors apps/api/Dockerfile).
COPY pyproject.toml uv.lock ./
COPY apps/engine/pyproject.toml apps/engine/pyproject.toml

# Install only production deps for the engine workspace package.
RUN uv sync --frozen --no-dev --no-install-project --package testlyn-engine

# Project source (sidecar package lives under apps/engine/sidecar)
COPY apps/engine/sidecar/ apps/engine/sidecar/

RUN uv sync --frozen --no-dev --package testlyn-engine


# ---- Stage 3: runtime ----
FROM python:3.13-slim AS runtime

# tini for PID-1 (multi-process container: k6 + sidecar + entrypoint.sh)
ENV TINI_VERSION=v0.19.0
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
    && curl -fsSL "https://github.com/krallin/tini/releases/download/${TINI_VERSION}/tini-amd64" \
        -o /usr/local/bin/tini \
    && chmod +x /usr/local/bin/tini \
    && rm -rf /var/lib/apt/lists/*

# Copy k6 binary (unmodified — see header)
COPY --from=k6 /usr/bin/k6 /usr/bin/k6

WORKDIR /app

# Copy the venv at the SAME path it was built at so absolute-path shebangs
# in /build/.venv/bin/* stay valid. Symlink /app/.venv → /build/.venv so the
# WORKDIR-relative path also resolves.
COPY --from=builder /build/.venv /build/.venv
RUN ln -s /build/.venv /app/.venv

COPY --from=builder /build/apps/engine/sidecar /app/sidecar

# Copy entrypoint (lives in apps/engine — repo-root context path)
COPY apps/engine/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Spool dir (override via SPOOL_DIR env)
RUN mkdir -p /tmp/spool

ENV PATH="/build/.venv/bin:$PATH"
ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1

RUN useradd --system --uid 1000 --no-create-home sidecar \
    && chown -R sidecar:sidecar /app /tmp/spool /build
USER sidecar

EXPOSE 8081

ENTRYPOINT ["/usr/local/bin/tini", "--", "/entrypoint.sh"]
