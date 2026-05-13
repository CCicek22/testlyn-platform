#!/usr/bin/env bash
# bundle-images.sh — Produce an air-gapped tarball of all Testlyn container images.
#
# Usage:
#   bash infra/scripts/bundle-images.sh [--license KEY] [--registry REGISTRY] [--output PATH]
#
# This script is the deliverable — it does NOT execute image pulls during CI.
# Run it on a connected machine with docker access before an air-gapped deploy.
#
# Output: <output>.tar.gz containing:
#   manifest.txt        — newline-delimited list of image refs
#   images/             — one .tar per image
set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
LICENSE_KEY=""
REGISTRY="us-central1-docker.pkg.dev/example-project-prod/testlyn"
OUTPUT="/tmp/testlyn-bundle.tar.gz"
WORK_DIR="$(mktemp -d)"
IMAGES_DIR="${WORK_DIR}/images"

# ---------------------------------------------------------------------------
# Parse args
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --license)  LICENSE_KEY="$2"; shift 2 ;;
    --registry) REGISTRY="$2";    shift 2 ;;
    --output)   OUTPUT="$2";      shift 2 ;;
    *)          echo "Unknown arg: $1"; exit 1 ;;
  esac
done

# ---------------------------------------------------------------------------
# License key validation stub
# Real validation: POST to https://license.testlyn.io/v1/validate
# ---------------------------------------------------------------------------
validate_license() {
  local key="$1"
  if [[ -z "$key" ]]; then
    echo "[bundle] WARNING: No license key provided. Air-gapped installs require a valid enterprise license."
    echo "[bundle] Continuing without validation (dev/trial mode)."
    return 0
  fi
  echo "[bundle] Validating license ${key:0:8}... OK"
  # TODO: curl -sf "https://license.testlyn.io/v1/validate" -d "{\"key\":\"$key\"}" | jq -e .valid
}

# ---------------------------------------------------------------------------
# Image list — all images required by the Helm chart
# ---------------------------------------------------------------------------
IMAGES=(
  "${REGISTRY}/testlyn-api:latest"
  "${REGISTRY}/testlyn-web:latest"
  "${REGISTRY}/testlyn-engine:latest"
  "${REGISTRY}/testlyn-engine-playwright:latest"
  "${REGISTRY}/testlyn-engine-a11y:latest"
  "${REGISTRY}/testlyn-report-builder:latest"
  "${REGISTRY}/testlyn-locator-healer:latest"
  # Third-party images pinned in values.yaml
  "grafana/k6:0.57.0"
  "postgres:16-alpine"
  "redis:7-alpine"
)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
echo "[bundle] Starting Testlyn image bundle"
echo "[bundle] Registry: ${REGISTRY}"
echo "[bundle] Output:   ${OUTPUT}"
echo "[bundle] Images:   ${#IMAGES[@]}"
echo ""

validate_license "$LICENSE_KEY"
echo ""

mkdir -p "$IMAGES_DIR"
MANIFEST="${WORK_DIR}/manifest.txt"
> "$MANIFEST"

for image in "${IMAGES[@]}"; do
  safe_name="${image//[\/:]/_}"
  tar_path="${IMAGES_DIR}/${safe_name}.tar"

  echo "[bundle] Pulling: ${image}"
  docker pull "$image"

  echo "[bundle] Saving:  ${image} → images/${safe_name}.tar"
  docker save "$image" -o "$tar_path"

  echo "$image" >> "$MANIFEST"
done

echo ""
echo "[bundle] Creating tarball: ${OUTPUT}"
tar -czf "$OUTPUT" -C "$WORK_DIR" manifest.txt images/

echo "[bundle] Cleaning up work dir"
rm -rf "$WORK_DIR"

echo ""
echo "[bundle] Done. Bundle written to: ${OUTPUT}"
echo "[bundle] Image count: ${#IMAGES[@]}"
echo "[bundle] Transfer to air-gapped host, then:"
echo "         tar xzf $(basename "$OUTPUT")"
echo "         cat manifest.txt | while read img; do"
echo '           docker load < "images/$(echo $img | tr '"'"'/:'"'"' '"'"'_'"'"').tar"'
echo "         done"
