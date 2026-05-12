"""Claude Code CLI subprocess wrapper 테스트.

저자: JunyoungJung <joony300@gmail.com>
작성일: 2026-05-10
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest

from synapse_memory.llm.claude import (
    ClaudeEnvironment,
    ClaudeError,
    ClaudeUnavailableError,
    _build_cmd,
    _extract_first_json_value,
    _parse_json_with_fallback,
    _strip_code_fence,
    complete,
    complete_structured,
    detect_claude_environment,
)


def _ready_env() -> ClaudeEnvironment:
    return ClaudeEnvironment(
        claude_path="/opt/homebrew/bin/claude",
        claude_version="2.1.132 (Claude Code)",
        model="sonnet",
    )


def _mock_envelope(result: str, *, is_error: bool = False) -> str:
    return json.dumps(
        {
            "type": "result",
            "subtype": "success" if not is_error else "error",
            "is_error": is_error,
            "result": result,
            "session_id": "test-session",
            "total_cost_usd": 0.001,
        }
    )


def _mock_event_stream(result: str, *, is_error: bool = False) -> str:
    return json.dumps(
        [
            {"type": "system", "subtype": "init", "session_id": "test-session"},
            {
                "type": "assistant",
                "message": {
                    "content": [{"type": "text", "text": result}],
                },
            },
            {
                "type": "result",
                "subtype": "success" if not is_error else "error",
                "is_error": is_error,
                "result": result,
                "session_id": "test-session",
                "total_cost_usd": 0.001,
            },
        ]
    )


def _mock_proc(stdout: str = "", returncode: int = 0, stderr: str = ""):
    return subprocess.CompletedProcess(
        args=["claude"], returncode=returncode, stdout=stdout, stderr=stderr
    )


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------


class TestEnvironment:
    def test_no_cli_unready(self) -> None:
        env = ClaudeEnvironment(claude_path=None, claude_version=None)
        assert env.ready is False
        assert "Claude Code CLI" in env.reasons_unavailable()[0]

    def test_with_cli_ready(self) -> None:
        env = ClaudeEnvironment(claude_path="/x", claude_version="1.0")
        assert env.ready is True

    def test_detect_no_cli(self) -> None:
        with patch("synapse_memory.llm.claude.shutil.which", return_value=None):
            env = detect_claude_environment()
            assert env.ready is False


# ---------------------------------------------------------------------------
# CLI args
# ---------------------------------------------------------------------------


class TestBuildCmd:
    def test_required_flags(self) -> None:
        cmd = _build_cmd(
            _ready_env(),
            system=None,
            model=None,
            json_schema=None,
            max_budget_usd=None,
        )
        assert "--print" in cmd
        assert "--no-session-persistence" in cmd
        assert "--output-format" in cmd
        assert "json" in cmd
        assert "--model" in cmd
        assert "--permission-mode" in cmd
        assert "bypassPermissions" in cmd
        # system-prompt 항상 명시 (default fallback이라도) — cache 35K 방지
        assert "--system-prompt" in cmd

    def test_no_bare_flag(self) -> None:
        """--bare는 OAuth 인증 무시하므로 사용 안 함."""
        cmd = _build_cmd(
            _ready_env(),
            system=None, model=None, json_schema=None, max_budget_usd=None,
        )
        assert "--bare" not in cmd

    def test_system_prompt(self) -> None:
        cmd = _build_cmd(
            _ready_env(),
            system="Be concise.",
            model=None,
            json_schema=None,
            max_budget_usd=None,
        )
        i = cmd.index("--system-prompt")
        assert cmd[i + 1] == "Be concise."

    def test_json_schema_serialized(self) -> None:
        schema = {"type": "object", "properties": {"x": {"type": "number"}}}
        cmd = _build_cmd(
            _ready_env(),
            system=None,
            model=None,
            json_schema=schema,
            max_budget_usd=None,
        )
        assert "--json-schema" in cmd
        i = cmd.index("--json-schema")
        assert "object" in cmd[i + 1]

    def test_budget_cap(self) -> None:
        cmd = _build_cmd(
            _ready_env(),
            system=None,
            model=None,
            json_schema=None,
            max_budget_usd=0.5,
        )
        assert "--max-budget-usd" in cmd
        i = cmd.index("--max-budget-usd")
        assert cmd[i + 1] == "0.5"

    def test_model_override(self) -> None:
        cmd = _build_cmd(
            _ready_env(),
            system=None,
            model="haiku",
            json_schema=None,
            max_budget_usd=None,
        )
        i = cmd.index("--model")
        assert cmd[i + 1] == "haiku"


# ---------------------------------------------------------------------------
# JSON parse fallback
# ---------------------------------------------------------------------------


class TestJsonParsing:
    def test_strip_fence(self) -> None:
        assert _strip_code_fence('```json\n{"x":1}\n```') == '{"x":1}'

    def test_extract_object(self) -> None:
        assert _extract_first_json_value('앞 {"a":1} 뒤') == '{"a":1}'

    def test_parse_clean(self) -> None:
        assert _parse_json_with_fallback('{"x":1}') == {"x": 1}

    def test_parse_fenced(self) -> None:
        assert _parse_json_with_fallback('```json\n{"x":1}\n```') == {"x": 1}

    def test_parse_embedded(self) -> None:
        assert _parse_json_with_fallback('응답: {"k":"v"} 끝') == {"k": "v"}

    def test_parse_fails(self) -> None:
        with pytest.raises(ClaudeError):
            _parse_json_with_fallback("그냥 텍스트")


# ---------------------------------------------------------------------------
# complete()
# ---------------------------------------------------------------------------


class TestComplete:
    def test_returns_result_field(self) -> None:
        with patch("synapse_memory.llm.claude.subprocess.run") as mock_run:
            mock_run.return_value = _mock_proc(stdout=_mock_envelope("응답"))
            assert complete("p", env=_ready_env()) == "응답"

    def test_records_cost_event_on_success(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        monkeypatch.setenv("SYNAPSE_L0_ROOT", str(tmp_path / "private"))
        monkeypatch.setenv("SYNAPSE_COMMAND", "ask")
        with patch("synapse_memory.llm.claude.subprocess.run") as mock_run:
            mock_run.return_value = _mock_proc(stdout=_mock_envelope("응답"))
            assert complete("prompt text", env=_ready_env()) == "응답"

        log = tmp_path / "private" / "cost.jsonl"
        data = json.loads(log.read_text(encoding="utf-8"))
        assert data["command"] == "ask"
        assert data["provider"] == "claude"
        assert data["model"] == "sonnet"
        assert data["status"] == "success"
        assert data["usd"] == 0.001
        assert "prompt text" not in log.read_text(encoding="utf-8")

    def test_returns_result_from_event_stream(self) -> None:
        """Claude Code 2.1+ may return a JSON event array instead of one dict."""
        with patch("synapse_memory.llm.claude.subprocess.run") as mock_run:
            mock_run.return_value = _mock_proc(stdout=_mock_event_stream("응답"))
            assert complete("p", env=_ready_env()) == "응답"

    def test_unavailable_raises(self) -> None:
        env = ClaudeEnvironment(claude_path=None, claude_version=None)
        with pytest.raises(ClaudeUnavailableError):
            complete("p", env=env)

    def test_nonzero_exit_raises(self) -> None:
        with patch("synapse_memory.llm.claude.subprocess.run") as mock_run:
            mock_run.return_value = _mock_proc(returncode=1, stderr="permission denied")
            with pytest.raises(ClaudeError, match="permission denied"):
                complete("p", env=_ready_env())

    def test_records_cost_event_on_nonzero_exit(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        monkeypatch.setenv("SYNAPSE_L0_ROOT", str(tmp_path / "private"))
        with patch("synapse_memory.llm.claude.subprocess.run") as mock_run:
            mock_run.return_value = _mock_proc(returncode=1, stderr="permission denied")
            with pytest.raises(ClaudeError, match="permission denied"):
                complete("p", env=_ready_env())

        data = json.loads((tmp_path / "private" / "cost.jsonl").read_text(encoding="utf-8"))
        assert data["status"] == "error"
        assert data["error_kind"] == "nonzero_exit"

    def test_cost_logging_failure_does_not_change_success(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr(
            "synapse_memory.llm.claude.append_cost_event",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")),
        )
        with patch("synapse_memory.llm.claude.subprocess.run") as mock_run:
            mock_run.return_value = _mock_proc(stdout=_mock_envelope("응답"))
            assert complete("p", env=_ready_env()) == "응답"

        assert "cost event 기록 실패" in capsys.readouterr().err

    def test_envelope_is_error(self) -> None:
        with patch("synapse_memory.llm.claude.subprocess.run") as mock_run:
            mock_run.return_value = _mock_proc(
                stdout=_mock_envelope("budget exceeded", is_error=True)
            )
            with pytest.raises(ClaudeError, match="budget exceeded"):
                complete("p", env=_ready_env())

    def test_event_stream_is_error(self) -> None:
        with patch("synapse_memory.llm.claude.subprocess.run") as mock_run:
            mock_run.return_value = _mock_proc(
                stdout=_mock_event_stream("budget exceeded", is_error=True)
            )
            with pytest.raises(ClaudeError, match="budget exceeded"):
                complete("p", env=_ready_env())

    def test_event_stream_without_result_raises(self) -> None:
        with patch("synapse_memory.llm.claude.subprocess.run") as mock_run:
            mock_run.return_value = _mock_proc(
                stdout=json.dumps([{"type": "system", "subtype": "init"}])
            )
            with pytest.raises(ClaudeError, match="result event"):
                complete("p", env=_ready_env())

    def test_invalid_envelope_json(self) -> None:
        with patch("synapse_memory.llm.claude.subprocess.run") as mock_run:
            mock_run.return_value = _mock_proc(stdout="not json")
            with pytest.raises(ClaudeError, match="envelope JSON"):
                complete("p", env=_ready_env())

    def test_timeout(self) -> None:
        with patch("synapse_memory.llm.claude.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="x", timeout=1)
            with pytest.raises(ClaudeError, match="타임아웃"):
                complete("p", env=_ready_env(), timeout=1)

    def test_passes_options(self) -> None:
        with patch("synapse_memory.llm.claude.subprocess.run") as mock_run:
            mock_run.return_value = _mock_proc(stdout=_mock_envelope("ok"))
            complete(
                "p",
                env=_ready_env(),
                system="You are X.",
                model="haiku",
                json_schema={"type": "object"},
                max_budget_usd=0.1,
            )
            args = mock_run.call_args.args[0]
            assert "--system-prompt" in args
            assert "You are X." in args
            assert "--model" in args
            assert "haiku" in args
            assert "--json-schema" in args
            assert "--max-budget-usd" in args
            assert "0.1" in args

    def test_system_prompt_always_set(self) -> None:
        """--system-prompt 항상 명시 — CLAUDE.md/memory cache 폭발 방지."""
        with patch("synapse_memory.llm.claude.subprocess.run") as mock_run:
            mock_run.return_value = _mock_proc(stdout=_mock_envelope("ok"))
            complete("p", env=_ready_env())
            args = mock_run.call_args.args[0]
            assert "--system-prompt" in args


class TestCompleteStructured:
    def test_returns_dict(self) -> None:
        with patch("synapse_memory.llm.claude.subprocess.run") as mock_run:
            mock_run.return_value = _mock_proc(
                stdout=_mock_envelope('{"x":1}')
            )
            assert complete_structured("p", env=_ready_env()) == {"x": 1}

    def test_strips_fence(self) -> None:
        with patch("synapse_memory.llm.claude.subprocess.run") as mock_run:
            mock_run.return_value = _mock_proc(
                stdout=_mock_envelope('```json\n{"y":2}\n```')
            )
            assert complete_structured("p", env=_ready_env()) == {"y": 2}

    def test_extracts_from_natural_language(self) -> None:
        with patch("synapse_memory.llm.claude.subprocess.run") as mock_run:
            mock_run.return_value = _mock_proc(
                stdout=_mock_envelope('응답: {"k":"v"} 끝')
            )
            assert complete_structured("p", env=_ready_env()) == {"k": "v"}
