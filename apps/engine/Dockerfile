# =============================================================================
# Testlyn Engine — 2-stage Dockerfile
# =============================================================================
#
# Stage 1: Extract the unmodified stock k6 binary.
#   - Uses the official grafana/k6 image (pinned to 1.3.0).
#   - AGPL compliance: k6 is NEVER modified, compiled, or linked against.
#     It is copied as a pre-built binary and invoked ONLY via subprocess in
#     entrypoint.sh. No xk6 extensions. No Go vendoring of k6 source.
#     See CLAUDE.md §2 rule #1 and ADR-003.
#
# Stage 2: Python sidecar image.
#   - Base: python:3.13-slim (Debian bookworm slim)
#   - Why not distroless? The sidecar is a multi-process container: k6 binary
#     + Python sidecar, both supervised by tini + entrypoint.sh (a shell
#     script). Distroless has no shell, so we'd need an s6-overlay or similar
#     supervisor — significant complexity for minimal size benefit.
#     python:3.13-slim gives us bash, curl, and a standard Python runtime
#     in a small image (~200 MiB base). See ADR-009.
#   - tini provides proper PID-1 / zombie-reaping duties.
#   - gcloud CLI is NOT included in this image; GCS access is done via
#     signed-URL or the gsutil binary mounted via Cloud Run Job env.
#     entrypoint.sh uses curl + OIDC token for GCS object fetch (no SDK dep).
#
# k6 version: 1.3.0
#   - This is the version referenced in the Phase 1 design spec
#     (docs/superpowers/specs/2026-05-12-testlyn-phase1-vertical-slice-design.md)
#     and verified present as a real Docker Hub tag (sha256:3ddc8b1a33a2c3...).
#     k6 — 1.3.0 is the spec's explicit pin. Re-verify on bump per spec §4.
#   - To bump: update the FROM tag, run `docker build`, re-verify the k6 JSON
#     output format against https://grafana.com/docs/k6/latest/results-output/real-time/json/
#     and record the change in docs/DECISIONS.md.
#
# Target image size: <500 MiB (base ~200 MiB + k6 ~50 MiB + deps ~150 MiB).
# =============================================================================

# ---- Stage 1: extract k6 binary ----
# Pin to the exact stable tag. Never use :latest.
FROM grafana/k6:1.3.0 AS k6
# k6 binary is at /usr/bin/k6 in this image

# ---- Stage 2: Python sidecar runtime ----
# python:3.13-slim chosen over distroless — see header comment and ADR-009.
FROM python:3.13-slim AS runtime

# tini: proper PID-1 signal forwarding + zombie reaping for multi-process containers
ENV TINI_VERSION=v0.19.0
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
    && curl -fsSL "https://github.com/krallin/tini/releases/download/${TINI_VERSION}/tini-amd64" \
        -o /usr/local/bin/tini \
    && chmod +x /usr/local/bin/tini \
    && rm -rf /var/lib/apt/lists/*

# Copy k6 binary from stage 1 (unmodified — see header)
COPY --from=k6 /usr/bin/k6 /usr/bin/k6

# Install uv for fast Python dependency installation
COPY --from=ghcr.io/astral-sh/uv:0.7.2 /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency manifest first (layer cache)
COPY pyproject.toml ./

# Install runtime dependencies (no dev extras)
RUN uv pip install --system \
    "google-cloud-bigquery>=3.27" \
    "pydantic>=2" \
    "pydantic-settings>=2" \
    "structlog>=25.3" \
    "tenacity>=9.1" \
    "numpy>=2.4" \
    "aiohttp>=3.11" \
    "aiofiles>=24.1"

# Copy sidecar source code
COPY sidecar/ ./sidecar/

# Copy entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Spool directory (override via SPOOL_DIR env)
RUN mkdir -p /tmp/spool

# Cloud Run Jobs run as non-root by default; match that here
RUN useradd --system --uid 1000 --no-create-home sidecar \
    && chown -R sidecar:sidecar /app /tmp/spool
USER sidecar

# Health check (Cloud Run liveness probe)
EXPOSE 8081

# tini as PID 1, then entrypoint
ENTRYPOINT ["/usr/local/bin/tini", "--", "/entrypoint.sh"]
