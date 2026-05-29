"""Codex CLI adapter tests."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest

from synapse_memory.llm.codex import (
    CodexEnvironment,
    CodexError,
    _build_cmd,
    complete,
    complete_structured,
    detect_codex_environment,
)


def _ready_env() -> CodexEnvironment:
    return CodexEnvironment("/opt/homebrew/bin/codex", "codex 1.0", "gpt-5.5")


def _mock_run(stdout: str = "", returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["codex"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def test_detect_no_cli() -> None:
    with patch("synapse_memory.llm.codex.shutil.which", return_value=None):
        env = detect_codex_environment()

    assert env.ready is False


def test_build_cmd_uses_current_codex_exec_flags(tmp_path) -> None:
    cmd = _build_cmd(
        _ready_env(),
        model=None,
        output_path=tmp_path / "last-message.txt",
        schema_path=None,
    )

    assert "--ask-for-approval" not in cmd
    assert "--sandbox" in cmd
    assert "read-only" in cmd
    assert "--skip-git-repo-check" in cmd
    assert "--output-last-message" in cmd


def test_complete_reads_output_last_message(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("SYNAPSE_L0_ROOT", str(tmp_path / "private"))

    def fake_run(args, **_kwargs):
        out_path = args[args.index("--output-last-message") + 1]
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write("응답")
        return _mock_run(stdout="event noise")

    with patch("synapse_memory.llm.codex.subprocess.run", side_effect=fake_run):
        assert complete("prompt", env=_ready_env()) == "응답"

    data = json.loads((tmp_path / "private" / "cost.jsonl").read_text(encoding="utf-8"))
    assert data["provider"] == "codex"
    assert data["status"] == "success"
    assert "prompt" not in (tmp_path / "private" / "cost.jsonl").read_text(encoding="utf-8")


def test_complete_nonzero_exit_records_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("SYNAPSE_L0_ROOT", str(tmp_path / "private"))
    with patch("synapse_memory.llm.codex.subprocess.run") as mock_run:
        mock_run.return_value = _mock_run(returncode=1, stderr="not logged in")
        with pytest.raises(CodexError, match="not logged in"):
            complete("prompt", env=_ready_env())

    data = json.loads((tmp_path / "private" / "cost.jsonl").read_text(encoding="utf-8"))
    assert data["provider"] == "codex"
    assert data["status"] == "error"


def test_complete_structured_parses_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("SYNAPSE_L0_ROOT", str(tmp_path / "private"))

    def fake_run(args, **_kwargs):
        out_path = args[args.index("--output-last-message") + 1]
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write('{"x": 1}')
        return _mock_run()

    with patch("synapse_memory.llm.codex.subprocess.run", side_effect=fake_run):
        assert complete_structured("prompt", env=_ready_env()) == {"x": 1}
