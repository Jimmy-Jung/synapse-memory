# tests/test_wiki_log.py
"""log.md append (시간순, grep 친화). vault 외부 ~/.synapse/private/ 에 기록된다."""
from __future__ import annotations

from pathlib import Path

import pytest

from synapse_memory.storage.l0 import L0_ENV_VAR, l0_root
from synapse_memory.wiki.log import append_log, log_path, summarize_provider_error


@pytest.fixture(autouse=True)
def _l0_in_tmp(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(L0_ENV_VAR, str(tmp_path / "private"))


def test_log_path_lives_in_l0_root() -> None:
    assert log_path() == l0_root() / "log.md"


def test_append_creates_and_appends() -> None:
    append_log("ingest claude-code: 2 pages (synapse-memory, rag)",
               when="2026-06-14T10:00:00")
    append_log("ingest claude-code: 1 page (acme)",
               when="2026-06-14T11:00:00")
    text = (l0_root() / "log.md").read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if ln.startswith("- ")]
    assert len(lines) == 2
    assert "2026-06-14T10:00:00" in lines[0]
    assert "synapse-memory" in lines[0]
    assert "acme" in lines[1]


def test_append_log_redacts_operational_ids_and_truncates() -> None:
    append_log(
        "provider failed session_id=sess_123456789 token=secret " + ("x" * 400),
        when="2026-06-21T10:00:00",
    )

    text = (l0_root() / "log.md").read_text(encoding="utf-8")
    assert "sess_123456789" not in text
    assert "secret" not in text
    assert "session_id=<redacted>" in text
    assert len(text.splitlines()[-1]) < 320


def test_append_log_redacts_bearer_authorization_values() -> None:
    append_log(
        "provider failed Authorization: Bearer sk-live-secret-123",
        when="2026-06-21T10:00:00",
    )

    text = (l0_root() / "log.md").read_text(encoding="utf-8")
    assert "Bearer" not in text
    assert "sk-live-secret-123" not in text
    assert "Authorization: <redacted>" in text


def test_summarize_provider_error_keeps_safe_json_fields_only() -> None:
    exc = RuntimeError(
        '{"error":{"message":"rate limited","type":"rate_limit_error"},'
        '"session_id":"sess_abc","usage":{"input_tokens":999},"retry_after":3}'
    )

    summary = summarize_provider_error(exc)

    assert "rate limited" in summary
    assert "rate_limit_error" in summary
    assert "retry_after" in summary
    assert "sess_abc" not in summary
    assert "usage" not in summary


def test_summarize_provider_error_redacts_bearer_values_in_message() -> None:
    exc = RuntimeError(
        '{"error":{"message":"Authorization: Bearer sk-live-secret-123",'
        '"type":"provider_error"}}'
    )

    summary = summarize_provider_error(exc)

    assert "Bearer" not in summary
    assert "sk-live-secret-123" not in summary
    assert "Authorization: <redacted>" in summary
