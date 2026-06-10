"""Review-finding tests: when the exit-code file is missing AND K6_EXIT_CODE
is unset, the sidecar must NOT default to 0 — that recorded
runs_summary.status='completed' for runs whose real outcome was unknown.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sidecar.main import EXIT_CODE_UNKNOWN, _read_exit_code


def test_missing_file_and_env_returns_unknown_sentinel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("K6_EXIT_CODE", raising=False)
    code = _read_exit_code(str(tmp_path / "nope"))
    assert code == EXIT_CODE_UNKNOWN
    assert code != 0


def test_file_value_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("K6_EXIT_CODE", "5")
    p = tmp_path / "exit_code"
    p.write_text("3\n")
    assert _read_exit_code(str(p)) == 3


def test_env_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("K6_EXIT_CODE", "5")
    assert _read_exit_code(str(tmp_path / "nope")) == 5


def test_garbage_env_returns_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("K6_EXIT_CODE", "not-an-int")
    assert _read_exit_code(str(tmp_path / "nope")) == EXIT_CODE_UNKNOWN
