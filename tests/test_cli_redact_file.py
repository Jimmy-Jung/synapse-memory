"""Integration tests for `synapse-memory redact file <path>` (US1)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from synapse_memory.cli import main


@dataclass
class _FakeApfelEnv:
    apfel_path: None = None


def _force_pass1_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """detect_environment를 stub해 Pass 1 only fallback 경로를 강제."""
    monkeypatch.setattr(
        "synapse_memory.cli.detect_environment",
        lambda: _FakeApfelEnv(),
    )


def test_redact_file_basic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _force_pass1_only(monkeypatch)
    src = tmp_path / "memo.md"
    src.write_text("연락처: jimmy@example.com 010-1234-5678\n", encoding="utf-8")
    original = src.read_text(encoding="utf-8")

    rc = main(["redact", "file", str(src)])
    out = capsys.readouterr().out

    assert rc == 0
    assert "jimmy@example.com" not in out
    assert "010-1234-5678" not in out
    assert src.read_text(encoding="utf-8") == original, "원본 파일 보존"


def test_redact_file_out_option(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_pass1_only(monkeypatch)
    src = tmp_path / "memo.md"
    src.write_text("이메일: user@corp.example.com\n", encoding="utf-8")
    out_path = tmp_path / "redacted.md"

    rc = main(["redact", "file", str(src), "--out", str(out_path)])

    assert rc == 0
    assert out_path.is_file()
    out_text = out_path.read_text(encoding="utf-8")
    assert "user@corp.example.com" not in out_text


def test_redact_file_missing_path_exit_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "no-such-file.md"
    rc = main(["redact", "file", str(missing)])
    err = capsys.readouterr().err
    assert rc == 2
    assert "없" in err or "not" in err.lower() or "missing" in err.lower()


def test_redact_file_binary_exit_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bin_path = tmp_path / "image.bin"
    bin_path.write_bytes(b"\xff\xfe\x00\x01\x02not-utf8\xff")
    rc = main(["redact", "file", str(bin_path)])
    err = capsys.readouterr().err
    assert rc == 2
    assert "UTF-8" in err or "텍스트" in err or "binary" in err.lower()


def test_redact_file_size_limit_exit_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    big = tmp_path / "big.md"
    big.write_text("a" * (1 * 1024 * 1024 + 10), encoding="utf-8")
    rc = main(["redact", "file", str(big)])
    err = capsys.readouterr().err
    assert rc == 2
    assert "1" in err and ("MB" in err.upper() or "초과" in err)


def test_redact_file_apfel_fallback_emits_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _force_pass1_only(monkeypatch)
    src = tmp_path / "memo.md"
    src.write_text("hi", encoding="utf-8")

    rc = main(["redact", "file", str(src)])
    err = capsys.readouterr().err

    assert rc == 0
    assert "apfel" in err.lower()
    assert "pass 1" in err.lower() or "regex" in err.lower()


def test_redact_file_redactlist_masked_in_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_pass1_only(monkeypatch)
    monkeypatch.setattr(
        "synapse_memory.redaction.load_redactlist",
        lambda: ["AcmeCorp", "SecretProject"],
    )
    src = tmp_path / "memo.md"
    src.write_text(
        "AcmeCorp에서 SecretProject 진행 중\n",
        encoding="utf-8",
    )
    out_path = tmp_path / "redacted.md"

    rc = main(["redact", "file", str(src), "--out", str(out_path)])

    assert rc == 0
    out = out_path.read_text(encoding="utf-8")
    assert "AcmeCorp" not in out, "fallback에서도 redactlist 적용되어야 함"
    assert "SecretProject" not in out
