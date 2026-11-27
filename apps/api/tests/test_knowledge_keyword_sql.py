"""Keyword leg SQL: the language is a bound parameter, never a text fragment."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.dialects import postgresql

from testlyn_api.knowledge.search import SEARCH_LANGUAGE, build_keyword_statement

ORG = uuid.UUID("00000000-0000-4000-8000-0000000000a1")


def _compile(stmt) -> tuple[str, dict[str, object]]:  # type: ignore[no-untyped-def]
    compiled = stmt.compile(dialect=postgresql.dialect())
    return str(compiled), dict(compiled.params)


@pytest.mark.parametrize("project_id", [None, uuid.uuid4()])
def test_keyword_statement_binds_language_not_literal(
    project_id: uuid.UUID | None,
) -> None:
    sql, params = _compile(
        build_keyword_statement(
            org_id=ORG, project_id=project_id, query="refund policy", limit=10
        )
    )

    assert f"'{SEARCH_LANGUAGE}'" not in sql
    assert SEARCH_LANGUAGE not in sql
    assert "CAST(" in sql.upper() and "REGCONFIG" in sql.upper()
    assert SEARCH_LANGUAGE in params.values()


def test_keyword_statement_uses_text_tsv_gin_column() -> None:
    sql, _ = _compile(
        build_keyword_statement(org_id=ORG, project_id=None, query="x", limit=3)
    )

    assert "text_tsv @@" in sql
    assert "ts_rank_cd(text_tsv" in sql
