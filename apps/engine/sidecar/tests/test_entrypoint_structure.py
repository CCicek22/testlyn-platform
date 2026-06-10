"""Structural guards for entrypoint.sh signal/trap handling.

Full shell integration isn't practical in pytest (the script needs the GCP
metadata server), so these tests pin the load-bearing structure:

  * `bash -n` syntax-valid
  * a TERM trap exists and forwards to k6 + sidecar (tini without -g only
    signals bash — without forwarding there is no 30s drain and the run is
    stuck 'running')
  * the EXIT (cleanup/callback) trap is registered BEFORE the VUS validation
    block, so a validation exit still fires the callback
  * k6 runs in the background + `wait` (a foreground k6 blocks trap delivery)
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ENTRYPOINT = Path(__file__).resolve().parents[2] / "entrypoint.sh"
SRC = ENTRYPOINT.read_text()


def test_bash_syntax_valid() -> None:
    res = subprocess.run(
        ["bash", "-n", str(ENTRYPOINT)], capture_output=True, text=True, check=False
    )
    assert res.returncode == 0, res.stderr


def test_term_trap_forwards_to_children() -> None:
    assert "trap _on_term TERM" in SRC
    trap_body = SRC[SRC.index("_on_term()") : SRC.index("trap _on_term TERM")]
    assert 'kill -TERM "${K6_PID}"' in trap_body
    assert 'kill -TERM "${SIDECAR_PID}"' in trap_body


def test_exit_trap_registered_before_vus_validation() -> None:
    assert SRC.index("trap cleanup EXIT") < SRC.index('"${VUS}" -gt "${MAX_VUS}"')


def test_k6_runs_in_background_and_is_waited() -> None:
    assert "K6_PID=$!" in SRC
    assert 'wait "${K6_PID}"' in SRC
