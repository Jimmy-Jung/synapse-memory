"""Redact-list 테스트.

저자: Synapse Memory Maintainers
작성일: 2026-05-10
"""

from __future__ import annotations

from pathlib import Path

import pytest

from synapse_memory.redaction.pass1 import redact
from synapse_memory.redaction.pass2 import redact_full
from synapse_memory.redaction.patterns import DEFAULT_PATTERNS
from synapse_memory.redaction.redactlist import (
    REDACTLIST_PRIORITY,
    add_redactlist_item,
    build_redactlist_patterns,
    load_redactlist,
    remove_redactlist_item,
    write_redactlist,
)


class TestLoadWrite:
    def test_load_missing_returns_empty(self, tmp_path: Path) -> None:
        assert load_redactlist(tmp_path / "nope") == []

    def test_write_and_load(self, tmp_path: Path) -> None:
        path = tmp_path / "rl"
        write_redactlist(["샘플회사", "ProjectX"], path)
        items = load_redactlist(path)
        assert items == ["샘플회사", "ProjectX"]

    def test_load_skips_comments_and_blanks(self, tmp_path: Path) -> None:
        path = tmp_path / "rl"
        path.write_text(
            "# 주석\n\nSampleCorp\n\n# 또 주석\nProjectY\n",
            encoding="utf-8",
        )
        assert load_redactlist(path) == ["SampleCorp", "ProjectY"]

    def test_load_dedupes(self, tmp_path: Path) -> None:
        path = tmp_path / "rl"
        path.write_text("X\nY\nX\nZ\n", encoding="utf-8")
        assert load_redactlist(path) == ["X", "Y", "Z"]


class TestAddRemove:
    def test_add_new(self, tmp_path: Path) -> None:
        path = tmp_path / "rl"
        assert add_redactlist_item("Acme", path) is True
        assert load_redactlist(path) == ["Acme"]

    def test_add_existing_returns_false(self, tmp_path: Path) -> None:
        path = tmp_path / "rl"
        add_redactlist_item("Acme", path)
        assert add_redactlist_item("Acme", path) is False

    def test_add_empty_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            add_redactlist_item("   ", tmp_path / "rl")

    def test_remove(self, tmp_path: Path) -> None:
        path = tmp_path / "rl"
        write_redactlist(["A", "B", "C"], path)
        assert remove_redactlist_item("B", path) is True
        assert load_redactlist(path) == ["A", "C"]

    def test_remove_missing_returns_false(self, tmp_path: Path) -> None:
        assert remove_redactlist_item("Nope", tmp_path / "rl") is False


class TestPatternBuild:
    def test_empty(self) -> None:
        assert build_redactlist_patterns([]) == []

    def test_priority_above_defaults(self) -> None:
        patterns = build_redactlist_patterns(["샘플회사"])
        assert all(p.priority == REDACTLIST_PRIORITY for p in patterns)
        max_default = max(p.priority for p in DEFAULT_PATTERNS)
        assert REDACTLIST_PRIORITY > max_default

    def test_case_insensitive(self) -> None:
        patterns = build_redactlist_patterns(["Acme"])
        regex = patterns[0].regex
        assert regex.search("acme corp")
        assert regex.search("ACME")
        assert regex.search("Acme")

    def test_special_chars_escaped(self) -> None:
        patterns = build_redactlist_patterns(["A.B+C"])
        regex = patterns[0].regex
        # literal A.B+C 매치, A_B_C는 매치 안 됨
        assert regex.search("A.B+C") is not None
        assert regex.search("A_B_C") is None

    def test_longer_first(self) -> None:
        """긴 항목이 먼저 매치되도록 정렬."""
        patterns = build_redactlist_patterns(["Project", "ProjectXYZ"])
        # 첫 패턴이 긴 것
        assert "ProjectXYZ" in patterns[0].regex.pattern
        assert "Project" in patterns[1].regex.pattern


class TestPass1Integration:
    def test_redactlist_masks_in_pass1(self) -> None:
        """Pass 1 패턴에 redact-list 합치면 우선 매치."""
        patterns = list(DEFAULT_PATTERNS) + build_redactlist_patterns(["샘플회사"])
        text = "샘플회사 본사 방문"
        result = redact(text, patterns=patterns)
        assert "[REDACT_1]" in result.redacted
        assert any(d.category == "redactlist" for d in result.detections)

    def test_redactlist_overrides_other_patterns(self) -> None:
        """priority 200으로 다른 카테고리 우선."""
        patterns = list(DEFAULT_PATTERNS) + build_redactlist_patterns(["Acme"])
        text = "Acme 회사 방문"
        result = redact(text, patterns=patterns)
        # redactlist가 매치됨 (다른 카테고리는 안 잡음)
        cats = {d.category for d in result.detections}
        assert "redactlist" in cats


class TestRedactFullIntegration:
    def test_load_default_redactlist(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SYNAPSE_L0_ROOT 안 .redactlist 파일을 자동 로드."""
        monkeypatch.setenv("SYNAPSE_L0_ROOT", str(tmp_path))
        rl = tmp_path / ".redactlist"
        rl.write_text("ProjectXYZ\n", encoding="utf-8")

        # apfel 미사용 환경 — Pass 1만 동작
        from synapse_memory.llm.apfel import ApfelEnvironment
        env = ApfelEnvironment(None, None, "0", False)

        text = "ProjectXYZ에서 일했다"
        result = redact_full(text, env=env)
        assert "[REDACT_1]" in result.redacted

    def test_explicit_redactlist_arg(self) -> None:
        """redactlist 인자로 직접 전달."""
        from synapse_memory.llm.apfel import ApfelEnvironment
        env = ApfelEnvironment(None, None, "0", False)

        text = "BetaCorp 인터뷰"
        result = redact_full(text, env=env, redactlist=["BetaCorp"])
        assert "[REDACT_1]" in result.redacted

    def test_empty_redactlist_no_effect(self) -> None:
        from synapse_memory.llm.apfel import ApfelEnvironment
        env = ApfelEnvironment(None, None, "0", False)

        result = redact_full("일반 텍스트", env=env, redactlist=[])
        assert result.detections == []
