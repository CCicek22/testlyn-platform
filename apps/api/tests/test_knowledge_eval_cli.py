from __future__ import annotations

import pytest
from testlyn_api.knowledge.evaluation.__main__ import main


def test_cli_does_not_fall_back_to_test_postgres_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # pytest's database is wiped by the postgres suite; the CLI must not share it.
    monkeypatch.delenv("KNOWLEDGE_EVAL_DATABASE_URL", raising=False)
    monkeypatch.setenv("TEST_POSTGRES_URL", "postgresql+asyncpg://u:p@h/db")
    assert main([]) == 2
    assert "KNOWLEDGE_EVAL_DATABASE_URL" in capsys.readouterr().err
