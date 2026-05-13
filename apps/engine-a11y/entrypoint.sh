#!/bin/sh
# entrypoint.sh — Testlyn engine-a11y
#
# Invoked by tini as PID 1. Runs one axe-core audit per URL batch.
#
# Required env:
#   RUN_ID           — test run UUID (injected by Cloud Run Job)
#   AUDIT_URLS       — comma-separated target URLs
#   BQ_DATASET       — BigQuery dataset name (testlyn_metrics)
#   GCP_PROJECT      — GCP project ID
#   CALLBACK_URL     — POST after run completes
#
# Optional env:
#   MAX_DEPTH        — crawl depth (default 1)
#   WCAG_TAGS        — axe-core tag filter (default wcag2a,wcag2aa,wcag21aa,wcag22aa)
#   ORG_ID           — org context for BQ rows (default 'unknown')
#   REGION           — GCP region label for BQ rows (default us-central1)

set -eu

: "${RUN_ID:?RUN_ID is required}"
: "${AUDIT_URLS:?AUDIT_URLS is required}"
: "${BQ_DATASET:?BQ_DATASET is required}"
: "${GCP_PROJECT:?GCP_PROJECT is required}"
: "${CALLBACK_URL:?CALLBACK_URL is required}"

MAX_DEPTH="${MAX_DEPTH:-1}"
WCAG_TAGS="${WCAG_TAGS:-wcag2a,wcag2aa,wcag21aa,wcag22aa}"
ORG_ID="${ORG_ID:-unknown}"
REGION="${REGION:-us-central1}"

export RUN_ID AUDIT_URLS MAX_DEPTH WCAG_TAGS

echo "[engine-a11y] run_id=${RUN_ID} urls=${AUDIT_URLS} depth=${MAX_DEPTH}"

# Run axe audit, pipe JSONL stdout into the BQ sidecar parser.
# The sidecar is responsible for batching rows and streaming to BQ.
# On error, exit non-zero so Cloud Run Job marks the execution failed.
node /scripts/run-axe.js \
  | python /sidecar/main.py \
      --product a11y \
      --parser axe \
      --run-id "${RUN_ID}" \
      --org-id "${ORG_ID}" \
      --region "${REGION}" \
      --bq-dataset "${BQ_DATASET}" \
      --gcp-project "${GCP_PROJECT}"

EXIT_CODE=$?

# Notify API of completion regardless of exit code.
curl -sf -X POST "${CALLBACK_URL}" \
  -H "Content-Type: application/json" \
  -d "{\"exit_code\": ${EXIT_CODE}}" || true

exit "${EXIT_CODE}"
