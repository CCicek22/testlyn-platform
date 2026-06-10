#!/usr/bin/env bash
# =============================================================================
# Testlyn Engine entrypoint
# =============================================================================
#
# SANITY CHECK (MANDATORY — do not remove):
#   k6 is invoked as a subprocess only. This script does NOT import, compile,
#   vendor, or link k6 source. The binary at /usr/bin/k6 is the unmodified
#   official grafana/k6:1.3.0 binary copied verbatim from the upstream image.
#   See CLAUDE.md §2 rule #1 and ADR-003.
#
# Orchestration flow per docs/testlyn_bq_sidecar_spec.md §11:
#   1. Fetch k6 script from GCS (via curl + OIDC token — no gcloud SDK dep)
#   2. mkfifo /tmp/k6.jsonl — named pipe for streaming to sidecar
#   3. Start sidecar in background
#   4. Run k6 with --out json= pointing at the named pipe
#   5. Wait for sidecar to drain
#   6. Upload summary JSON to GCS
#   7. POST callback to API with run status
#   8. Exit with k6's exit code
#
# On ANY failure the callback always fires (trap + final block).
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Required env vars (injected by Cloud Run Job invoker)
# ---------------------------------------------------------------------------
: "${RUN_ID:?RUN_ID is required}"
: "${ORG_ID:?ORG_ID is required}"
: "${GCP_PROJECT:?GCP_PROJECT is required}"
: "${SCRIPT_GCS_URI:?SCRIPT_GCS_URI is required}"
: "${CALLBACK_URL:?CALLBACK_URL is required}"

# Optional with defaults
INTERNAL_TOKEN="${INTERNAL_TOKEN:-}"
VUS="${VUS:-10}"
DURATION="${DURATION:-30s}"
MAX_VUS="${MAX_VUS:-50000}"
SUMMARY_GCS_URI="${SUMMARY_GCS_URI:-gs://testlyn-prod-results/${ORG_ID}/${RUN_ID}/summary.json}"
SPOOL_GCS_BUCKET="${SPOOL_GCS_BUCKET:-testlyn-prod-spool}"
K6_OUTPUT_PATH="${K6_OUTPUT_PATH:-/tmp/k6.jsonl}"
K6_SUMMARY_PATH="${K6_SUMMARY_PATH:-/tmp/work/summary.json}"
EXIT_CODE_PATH="${EXIT_CODE_PATH:-/tmp/k6_exit_code}"
WORK_DIR="${WORK_DIR:-/tmp/work}"

mkdir -p "${WORK_DIR}"

# ---------------------------------------------------------------------------
# Track sidecar + k6 PIDs and k6 exit code for cleanup
# ---------------------------------------------------------------------------
SIDECAR_PID=""
K6_PID=""
K6_EXIT=1  # pessimistic default; overwritten after k6 actually runs

# ---------------------------------------------------------------------------
# Cleanup trap — always runs, even on error
# On container shutdown (SIGTERM) tini forwards the signal here.
# ---------------------------------------------------------------------------
cleanup() {
    local final_status="failed"
    [ "${K6_EXIT}" -eq 0 ] && final_status="completed"

    # Persist the k6 exit code to a file the sidecar polls before writing
    # runs_summary (fix #7 of audit).  The previous `export K6_EXIT_CODE` was
    # racy: the sidecar already read its env at startup, long before k6 had
    # exited.  The env var is kept for back-compat with the sidecar's
    # fallback path in _read_exit_code().
    echo "${K6_EXIT}" > "${EXIT_CODE_PATH}" || true
    export K6_EXIT_CODE="${K6_EXIT}"

    # Wait for sidecar to drain — 30 s hard cap per spec §8.
    # Fix #11 of audit: bash builtin `wait` does NOT respect the timeout(1)
    # wrapper because timeout(1) execs a child for an external command, and
    # `wait` is a shell builtin.  Poll with kill -0 + sleep + counter, then
    # SIGKILL on expiry.
    if [ -n "${SIDECAR_PID}" ] && kill -0 "${SIDECAR_PID}" 2>/dev/null; then
        echo "[entrypoint] waiting for sidecar PID ${SIDECAR_PID} to drain (max 30s)..."
        local waited=0
        while [ "${waited}" -lt 30 ]; do
            if ! kill -0 "${SIDECAR_PID}" 2>/dev/null; then
                break
            fi
            sleep 1
            waited=$((waited + 1))
        done
        if kill -0 "${SIDECAR_PID}" 2>/dev/null; then
            echo "[entrypoint] sidecar did not drain within 30s — killing" >&2
            kill -KILL "${SIDECAR_PID}" 2>/dev/null || true
        fi
    fi

    # Upload summary if it exists
    if [ -f "${WORK_DIR}/summary.json" ]; then
        _gcs_upload "${WORK_DIR}/summary.json" "${SUMMARY_GCS_URI}" || true
    fi

    # Upload any spool that was not flushed (GCS replay path per spec §8)
    if [ -d "/tmp/spool" ] && [ "$(ls -A /tmp/spool 2>/dev/null)" ]; then
        echo "[entrypoint] uploading residual spool to GCS..."
        _gcs_upload_dir "/tmp/spool" "gs://${SPOOL_GCS_BUCKET}/${RUN_ID}/" || true
    fi

    # POST callback — always fires
    _post_callback "${final_status}" || true

    exit "${K6_EXIT}"
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# SIGTERM handling (spec §8 drain contract).
# tini (not -g) forwards SIGTERM to this bash process ONLY — children do not
# get it. Without forwarding, k6 + sidecar never see the signal: no 30s drain,
# spool lost, run stuck 'running'. Forward TERM to both; the interrupted
# `wait` below resumes, and the EXIT trap then runs the normal drain/callback.
# ---------------------------------------------------------------------------
_on_term() {
    echo "[entrypoint] SIGTERM received — forwarding to k6 + sidecar for graceful drain" >&2
    if [ -n "${K6_PID}" ] && kill -0 "${K6_PID}" 2>/dev/null; then
        kill -TERM "${K6_PID}" 2>/dev/null || true
    fi
    if [ -n "${SIDECAR_PID}" ] && kill -0 "${SIDECAR_PID}" 2>/dev/null; then
        kill -TERM "${SIDECAR_PID}" 2>/dev/null || true
    fi
}
trap _on_term TERM

# ---------------------------------------------------------------------------
# GCS helpers (curl + OIDC — no gcloud SDK required in the image)
# Workload Identity provides the metadata server at 169.254.169.254.
# ---------------------------------------------------------------------------
_oidc_token() {
    # Fetch a short-lived OIDC token from the metadata server
    curl -sf \
        -H "Metadata-Flavor: Google" \
        "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" \
        | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])"
}

_gcs_download() {
    local gcs_uri="${1}"  # gs://bucket/path
    local dest="${2}"
    # Convert gs:// URI to JSON API URL
    local bucket object encoded_obj token url
    bucket="${gcs_uri#gs://}"
    object="${bucket#*/}"
    bucket="${bucket%%/*}"
    encoded_obj="$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1], safe=''))" "${object}")"
    token="$(_oidc_token)"
    url="https://storage.googleapis.com/storage/v1/b/${bucket}/o/${encoded_obj}?alt=media"
    curl -fsSL -H "Authorization: Bearer ${token}" -o "${dest}" "${url}"
}

_gcs_upload() {
    local src="${1}"
    local gcs_uri="${2}"
    local bucket object token url
    bucket="${gcs_uri#gs://}"
    object="${bucket#*/}"
    bucket="${bucket%%/*}"
    token="$(_oidc_token)"
    url="https://storage.googleapis.com/upload/storage/v1/b/${bucket}/o?uploadType=media&name=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1], safe=''))" "${object}")"
    curl -fsSL -X POST -H "Authorization: Bearer ${token}" \
        -H "Content-Type: application/octet-stream" \
        --data-binary "@${src}" \
        "${url}" > /dev/null
}

_gcs_upload_dir() {
    local src_dir="${1}"
    local gcs_prefix="${2}"  # gs://bucket/prefix/
    find "${src_dir}" -type f | while IFS= read -r f; do
        local rel="${f#${src_dir}/}"
        _gcs_upload "${f}" "${gcs_prefix}${rel}" || true
    done
}

_post_callback() {
    local status="${1}"
    # Internal endpoints are gated by a shared secret (X-Internal-Token), not
    # OIDC. The OIDC token is still used for GCS download/upload above.
    curl -fsS -X POST "${CALLBACK_URL}" \
        -H "Content-Type: application/json" \
        ${INTERNAL_TOKEN:+-H "X-Internal-Token: ${INTERNAL_TOKEN}"} \
        -d "{\"run_id\":\"${RUN_ID}\",\"status\":\"${status}\",\"exit_code\":${K6_EXIT}}" \
        --max-time 10 || true
}

# ---------------------------------------------------------------------------
# Clamp VUS to MAX_VUS (fix #13 of audit).
# VUS arrives from the API as untrusted input; an unbounded value would let a
# customer schedule a run that DoSes the worker (memory + file-descriptor
# blow-up well before k6 itself errors).  MAX_VUS is operator-tunable.
# NOTE: this block MUST run after the EXIT trap + helper definitions above so
# a validation failure still fires the cleanup callback (otherwise the run is
# stuck in 'running' forever).
# ---------------------------------------------------------------------------
if ! [[ "${VUS}" =~ ^[0-9]+$ ]]; then
    echo "[entrypoint] VUS is not a non-negative integer: '${VUS}'" >&2
    K6_EXIT=2
    exit 2
fi
if [ "${VUS}" -gt "${MAX_VUS}" ]; then
    echo "[entrypoint] requested VUS=${VUS} exceeds MAX_VUS=${MAX_VUS}" >&2
    K6_EXIT=2
    exit 2
fi

# ---------------------------------------------------------------------------
# 1. Fetch k6 script from GCS
# ---------------------------------------------------------------------------
echo "[entrypoint] fetching script from ${SCRIPT_GCS_URI}"
_gcs_download "${SCRIPT_GCS_URI}" "${WORK_DIR}/script.js"

# ---------------------------------------------------------------------------
# 2. Create named pipe for k6 → sidecar streaming
# ---------------------------------------------------------------------------
[ -p "${K6_OUTPUT_PATH}" ] || mkfifo "${K6_OUTPUT_PATH}"

# ---------------------------------------------------------------------------
# 3. Start sidecar in background
# ---------------------------------------------------------------------------
echo "[entrypoint] starting sidecar..."
python3 -m sidecar.main &
SIDECAR_PID=$!
echo "[entrypoint] sidecar PID=${SIDECAR_PID}"

# Fail fast if sidecar dies before k6 starts
sleep 0.5
if ! kill -0 "${SIDECAR_PID}" 2>/dev/null; then
    echo "[entrypoint] sidecar exited early — aborting run" >&2
    K6_EXIT=1
    exit 1
fi

# ---------------------------------------------------------------------------
# 4. Run k6 (subprocess only — binary, unmodified)
# ---------------------------------------------------------------------------
echo "[entrypoint] starting k6 (vus=${VUS}, duration=${DURATION})"
set +e  # allow k6 to exit non-zero without killing the script
# k6 runs in the background so the TERM trap can fire while we `wait`:
# bash only delivers trapped signals between foreground commands, so a
# foreground k6 would block the trap until k6 exited on its own.
k6 run \
    --out "json=${K6_OUTPUT_PATH}" \
    --summary-export "${WORK_DIR}/summary.json" \
    --tag "run_id=${RUN_ID}" \
    --tag "org_id=${ORG_ID}" \
    --vus "${VUS}" \
    --duration "${DURATION}" \
    "${WORK_DIR}/script.js" &
K6_PID=$!
# `wait` returns 128+signum when interrupted by a trapped signal BEFORE the
# child actually exits — re-wait until k6 is really gone so K6_EXIT is k6's
# true exit code (k6 exits gracefully after the forwarded SIGTERM).
while :; do
    wait "${K6_PID}"
    K6_EXIT=$?
    if kill -0 "${K6_PID}" 2>/dev/null; then
        continue  # wait was interrupted by the TERM trap; k6 still running
    fi
    break
done
set -e
echo "[entrypoint] k6 exited with code ${K6_EXIT}"

# Drop the exit code where the sidecar polls it (fix #7).  Also written in
# cleanup() as a belt-and-braces in case of unusual exit paths.
echo "${K6_EXIT}" > "${EXIT_CODE_PATH}" || true

# ---------------------------------------------------------------------------
# 5. Monitor sidecar — if it dies mid-run something is wrong
# ---------------------------------------------------------------------------
if ! kill -0 "${SIDECAR_PID}" 2>/dev/null; then
    echo "[entrypoint] sidecar exited unexpectedly before drain" >&2
    K6_EXIT=1
fi

# cleanup trap handles the rest (wait sidecar, upload summary, callback)
