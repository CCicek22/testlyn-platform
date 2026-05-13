# syntax=docker/dockerfile:1
# Testlyn engine-a11y — WCAG 2.2 accessibility audit container
#
# Stage 1: Node deps + axe-core
# Stage 2: Final image with Playwright browsers + Python sidecar + tini
#
# Base: mcr.microsoft.com/playwright:v1.50.0-noble
# Python 3.13 is installed via deadsnakes PPA (noble ships 3.12; 3.13 not in default apt).
# tini handles PID-1 signal forwarding.

# ---- Stage 1: Node build ------------------------------------------------
FROM node:24-slim AS node-build

WORKDIR /app
COPY scripts/package.json scripts/package-lock.json* ./
RUN npm ci --omit=dev

# ---- Stage 2: Final runtime ---------------------------------------------
FROM mcr.microsoft.com/playwright:v1.50.0-noble

# Install tini, curl, Python 3.13
RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends \
        tini \
        curl \
        ca-certificates \
        software-properties-common && \
    add-apt-repository ppa:deadsnakes/ppa -y && \
    apt-get update -qq && \
    apt-get install -y --no-install-recommends \
        python3.13 \
        python3.13-venv \
        python3-pip && \
    rm -rf /var/lib/apt/lists/*

# Make python3.13 the default python3
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.13 1 && \
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.13 1

# Install the sidecar Python package from the workspace.
# In CI, the sidecar wheel is built by apps/engine/sidecar/ and pushed to
# Artifact Registry. The SIDECAR_WHEEL arg allows the Cloud Build trigger to
# inject the exact version.
ARG SIDECAR_WHEEL=testlyn-sidecar
RUN python -m pip install --no-cache-dir "${SIDECAR_WHEEL}"

# Copy Node modules from build stage
COPY --from=node-build /app/node_modules /node_modules

# Copy axe audit script and parser
COPY scripts/ /scripts/
COPY parser/ /parser/

# Entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Playwright already runs as root in the MS base image; keep it consistent.
# Cloud Run Job executes as the service account via Workload Identity.

ENTRYPOINT ["/usr/bin/tini", "--", "/entrypoint.sh"]
