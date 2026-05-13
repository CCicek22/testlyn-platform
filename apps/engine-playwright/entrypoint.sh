#!/usr/bin/env bash
# =============================================================================
# Testlyn Engine — Playwright entrypoint
# =============================================================================
#
# Flow:
#   1. Fetch Playwright TS script from GCS
#   2. mkfifo /tmp/pw.jsonl  (sidecar input)
#   3. Start sidecar in background (uses parsers/playwright.py)
#   4. Run npx playwright test --reporter=json, redirect to the named pipe
#   5. Wait for sidecar to drain
#   6. Upload summary JSON to GCS
#   7. POST callback to API
#   8. Exit with Playwright's exit code
# =============================================================================

set -euo pipefail

: "${RUN_ID:?RUN_ID is required}"
: "${ORG_ID:?ORG_ID is required}"
: "${GCP_PROJECT:?GCP_PROJECT is required}"
: "${SCRIPT_GCS_URI:?SCRIPT_GCS_URI is required}"
: "${CALLBACK_URL:?CALLBACK_URL is required}"

SUMMARY_GCS_URI="${SUMMARY_GCS_URI:-gs://testlyn-prod-results/${ORG_ID}/${RUN_ID}/pw-summary.json}"
SPOOL_GCS_BUCKET="${SPOOL_GCS_BUCKET:-testlyn-prod-spool}"
PW_OUTPUT_PATH="${PW_OUTPUT_PATH:-/tmp/pw.jsonl}"
WORK_DIR="${WORK_DIR:-/tmp/work}"

mkdir -p "${WORK_DIR}"

SIDECAR_PID=""
PW_EXIT=1

cleanup() {
    local final_status="failed"
    [ "${PW_EXIT}" -eq 0 ] && final_status="completed"

    export PW_EXIT_CODE="${PW_EXIT}"

    if [ -n "${SIDECAR_PID}" ] && kill -0 "${SIDECAR_PID}" 2>/dev/null; then
        echo "[entrypoint] waiting for sidecar PID ${SIDECAR_PID} to drain..."
        wait "${SIDECAR_PID}" || true
    fi

    if [ -f "${WORK_DIR}/pw-summary.json" ]; then
        _gcs_upload "${WORK_DIR}/pw-summary.json" "${SUMMARY_GCS_URI}" || true
    fi

    if [ -d "/tmp/spool" ] && [ "$(ls -A /tmp/spool 2>/dev/null)" ]; then
        _gcs_upload_dir "/tmp/spool" "gs://${SPOOL_GCS_BUCKET}/${RUN_ID}/" || true
    fi

    _post_callback "${final_status}" || true

    exit "${PW_EXIT}"
}
trap cleanup EXIT

_oidc_token() {
    curl -sf \
        -H "Metadata-Flavor: Google" \
        "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" \
        | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])"
}

_gcs_download() {
    local gcs_uri="${1}" dest="${2}"
    local bucket object encoded_obj token url
    bucket="${gcs_uri#gs://}"; object="${bucket#*/}"; bucket="${bucket%%/*}"
    encoded_obj="$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1], safe=''))" "${object}")"
    token="$(_oidc_token)"
    url="https://storage.googleapis.com/storage/v1/b/${bucket}/o/${encoded_obj}?alt=media"
    curl -fsSL -H "Authorization: Bearer ${token}" -o "${dest}" "${url}"
}

_gcs_upload() {
    local src="${1}" gcs_uri="${2}"
    local bucket object token url
    bucket="${gcs_uri#gs://}"; object="${bucket#*/}"; bucket="${bucket%%/*}"
    token="$(_oidc_token)"
    url="https://storage.googleapis.com/upload/storage/v1/b/${bucket}/o?uploadType=media&name=$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1], safe=''))" "${object}")"
    curl -fsSL -X POST -H "Authorization: Bearer ${token}" \
        -H "Content-Type: application/octet-stream" --data-binary "@${src}" "${url}" > /dev/null
}

_gcs_upload_dir() {
    local src_dir="${1}" gcs_prefix="${2}"
    find "${src_dir}" -type f | while IFS= read -r f; do
        local rel="${f#${src_dir}/}"
        _gcs_upload "${f}" "${gcs_prefix}${rel}" || true
    done
}

_post_callback() {
    local status="${1}"
    local token
    token="$(_oidc_token)" 2>/dev/null || token=""
    curl -fsS -X POST "${CALLBACK_URL}" \
        -H "Content-Type: application/json" \
        ${token:+-H "Authorization: Bearer ${token}"} \
        -d "{\"run_id\":\"${RUN_ID}\",\"status\":\"${status}\",\"exit_code\":${PW_EXIT}}" \
        --max-time 10 || true
}

# 1. Fetch script
echo "[entrypoint] fetching Playwright script from ${SCRIPT_GCS_URI}"
_gcs_download "${SCRIPT_GCS_URI}" "${WORK_DIR}/test.spec.ts"

# 2. Create named pipe
[ -p "${PW_OUTPUT_PATH}" ] || mkfifo "${PW_OUTPUT_PATH}"

# 3. Start sidecar (reads PW_OUTPUT_PATH via PLAYWRIGHT_OUTPUT_PATH env)
echo "[entrypoint] starting sidecar..."
PRODUCT=functional \
    PLAYWRIGHT_OUTPUT_PATH="${PW_OUTPUT_PATH}" \
    python3 -m sidecar.main &
SIDECAR_PID=$!
echo "[entrypoint] sidecar PID=${SIDECAR_PID}"

sleep 0.5
if ! kill -0 "${SIDECAR_PID}" 2>/dev/null; then
    echo "[entrypoint] sidecar exited early — aborting" >&2
    PW_EXIT=1; exit 1
fi

# 4. Run Playwright
# Playwright emits a single JSON blob on stdout; write directly to a temp file
# so we capture its true exit code via $?, then copy into the named pipe for
# the sidecar.  Using `tee` would capture tee's exit, not Playwright's.
echo "[entrypoint] running Playwright tests"
set +e
npx playwright test \
    --reporter=json \
    "${WORK_DIR}/test.spec.ts" \
    > "${WORK_DIR}/pw-summary.json" 2>&1
PW_EXIT=$?
set -e
# Feed the JSON blob into the sidecar's named pipe (sidecar reads one blob)
cat "${WORK_DIR}/pw-summary.json" > "${PW_OUTPUT_PATH}" &
echo "[entrypoint] playwright exited with code ${PW_EXIT}"

if ! kill -0 "${SIDECAR_PID}" 2>/dev/null; then
    echo "[entrypoint] sidecar exited unexpectedly" >&2
    PW_EXIT=1
fi

# cleanup trap fires from here
