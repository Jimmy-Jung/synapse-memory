"""M1b — 외부 markdown/txt ingest contract tests.

ingest_files 가:
- raw 텍스트를 L0 private 에 0600 권한으로 mirror
- 지원하지 않는 확장자는 skipped 로 표시 (vault 누수 0)
- raw 텍스트를 combined_redacted 로 반환 (D4 passthrough — extract_profile_facts(extra_text=...) 입력용)

저자: Synapse Memory Maintainers
작성일: 2026-05-13
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

import synapse_memory.profile.extract as ex_mod
from synapse_memory.llm.claude import ClaudeEnvironment
from synapse_memory.profile.extract import extract_profile_facts
from synapse_memory.profile.ingest import (
    SUPPORTED_EXTENSIONS,
    IngestResult,
    ingest_files,
)


def _ai_env() -> ClaudeEnvironment:
    return ClaudeEnvironment(
        claude_path="/opt/homebrew/bin/claude",
        claude_version="2.1",
        model="sonnet",
    )


@pytest.fixture
def diary_file(tmp_path: Path) -> Path:
    """기획자 use case 시뮬레이션 — 회고록/일기 내용."""
    p = tmp_path / "diary-2026.md"
    p.write_text(
        "# 2026 회고\n\n"
        "- Swift+SwiftUI 로 새 앱 시작했다. SwiftUI 가 편하다.\n"
        "- 단계별 의사코드 후 구현하는 게 내 방식이다.\n"
        "- 짧은 문장 선호. 직설적 표현.\n"
        "- 큰 실수: 요구사항 명확화 없이 구현 들어가서 두 번 갈아엎음.\n",
        encoding="utf-8",
    )
    return p


class TestIngestRawToL0:
    def test_raw_text_written_to_l0_private(
        self, diary_file: Path, tmp_path: Path
    ) -> None:
        l0 = tmp_path / "l0"
        result = ingest_files([diary_file], l0_root_override=l0)

        assert result.accepted_count == 1
        f = result.files[0]
        assert f.private_path.is_file()
        raw = f.private_path.read_text(encoding="utf-8")
        assert "Swift+SwiftUI" in raw
        assert "두 번 갈아엎음" in raw

    def test_l0_private_dir_and_file_perms(
        self, diary_file: Path, tmp_path: Path
    ) -> None:
        l0 = tmp_path / "l0"
        result = ingest_files([diary_file], l0_root_override=l0)

        f = result.files[0]
        parent_mode = oct(f.private_path.parent.stat().st_mode & 0o777)
        assert parent_mode == "0o700", f"L0 dir 권한 0700 위반: {parent_mode}"
        file_mode = oct(f.private_path.stat().st_mode & 0o777)
        assert file_mode == "0o600", f"L0 file 권한 0600 위반: {file_mode}"


class TestIngestSupportedExtensions:
    def test_markdown_accepted(
        self, diary_file: Path, tmp_path: Path
    ) -> None:
        l0 = tmp_path / "l0"
        result = ingest_files([diary_file], l0_root_override=l0)
        assert result.accepted_count == 1
        assert result.skipped_count == 0

    def test_txt_accepted(self, tmp_path: Path) -> None:
        p = tmp_path / "notes.txt"
        p.write_text("플레인 텍스트 메모입니다.\n", encoding="utf-8")
        l0 = tmp_path / "l0"
        result = ingest_files([p], l0_root_override=l0)
        assert result.accepted_count == 1

    def test_pdf_skipped_with_reason(self, tmp_path: Path) -> None:
        p = tmp_path / "doc.pdf"
        p.write_bytes(b"%PDF-1.4\nignored")
        l0 = tmp_path / "l0"

        result = ingest_files([p], l0_root_override=l0)

        assert result.accepted_count == 0
        assert result.skipped_count == 1
        assert result.files[0].skipped_reason == "unsupported"
        assert result.combined_redacted == ""

    def test_unsupported_files_dont_create_l0_entries(
        self, tmp_path: Path
    ) -> None:
        """vault 누수 0 contract: unsupported 면 L0 에도 안 씀."""
        p = tmp_path / "binary.bin"
        p.write_bytes(b"\x00\x01\x02")
        l0 = tmp_path / "l0"

        result = ingest_files([p], l0_root_override=l0)

        assert result.files[0].skipped_reason == "unsupported"
        # L0 디렉터리 자체는 만들어졌을 수 있지만, 이 파일은 안에 없어야 함
        if l0.exists():
            files_under_l0 = list(l0.rglob("binary.bin"))
            assert files_under_l0 == []


class TestIngestBatching:
    def test_multiple_files_combined(self, tmp_path: Path) -> None:
        a = tmp_path / "a.md"
        a.write_text("Swift 가 좋다.\n", encoding="utf-8")
        b = tmp_path / "b.md"
        b.write_text("Python 은 uv 로 관리.\n", encoding="utf-8")
        l0 = tmp_path / "l0"
        result = ingest_files([a, b], l0_root_override=l0)

        assert result.accepted_count == 2
        assert "Swift" in result.combined_redacted
        assert "uv" in result.combined_redacted

    def test_combined_includes_source_marker(
        self, diary_file: Path, tmp_path: Path
    ) -> None:
        """combined_redacted 에 출처 파일명 헤더가 포함되어야 한다."""
        l0 = tmp_path / "l0"
        result = ingest_files([diary_file], l0_root_override=l0)
        assert "diary-2026.md" in result.combined_redacted


class TestIngestErrors:
    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            ingest_files(
                [tmp_path / "does-not-exist.md"],
                l0_root_override=tmp_path / "l0",
            )

    def test_empty_text_skipped(self, tmp_path: Path) -> None:
        """본문이 공백뿐이면 LLM 으로 보내지 않게 skipped (passthrough — empty 그대로)."""
        p = tmp_path / "doc.md"
        p.write_text("   \n\t\n", encoding="utf-8")
        l0 = tmp_path / "l0"

        result = ingest_files([p], l0_root_override=l0)

        assert result.files[0].skipped_reason == "empty_redacted"
        # Raw 는 그래도 L0 에 남아야 함 (사용자가 재시도 가능)
        assert result.files[0].private_path.is_file()


class TestIngestResultShape:
    def test_result_is_dataclass_with_files(
        self, diary_file: Path, tmp_path: Path
    ) -> None:
        l0 = tmp_path / "l0"
        result = ingest_files([diary_file], l0_root_override=l0)
        assert isinstance(result, IngestResult)
        assert isinstance(result.files, list)
        assert isinstance(result.combined_redacted, str)

    def test_supported_extensions_constant(self) -> None:
        """공개 상수 — SKILL.md / docs 에서 사용 가능."""
        assert ".md" in SUPPORTED_EXTENSIONS
        assert ".txt" in SUPPORTED_EXTENSIONS
        assert ".pdf" not in SUPPORTED_EXTENSIONS


class TestExtractWithExtraText:
    """extract_profile_facts 가 history 없이도 extra_text 만으로 동작."""

    def test_extra_text_only_no_history(self, tmp_path: Path) -> None:
        """history 비어있어도 extra_text 만 있으면 LLM 호출 후 ProfileFact 반환."""
        empty_history = tmp_path / "history.jsonl"
        empty_history.write_text("", encoding="utf-8")

        with patch.object(
            ex_mod.ai_api,
            "complete_structured",
            return_value={
                "facts": [
                    {
                        "category": "tech",
                        "statement": "Swift+SwiftUI 주력",
                        "confidence": 0.9,
                    },
                    {
                        "category": "voice",
                        "statement": "짧은 문장 선호",
                        "confidence": 0.85,
                    },
                ]
            },
        ):
            facts = extract_profile_facts(
                history_path=empty_history,
                ai_env=_ai_env(),
                extra_text="## [diary.md]\n\nSwift 가 좋다. 짧은 문장 선호.",
            )
        assert len(facts) == 2
        # voice 카테고리도 통과해야 함 (M1a 에서 추가)
        assert any(f.category == "voice" for f in facts)
        # source_ids 가 persona-ingest 로 표시되어야 함
        assert "persona-ingest" in facts[0].source_ids

    def test_no_history_and_no_extra_text_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            extract_profile_facts(
                history_path=tmp_path / "missing.jsonl",
                codex_history_path=tmp_path / "missing_codex.jsonl",
                sample_lines=200,
                ai_env=_ai_env(),
                extra_text=None,
            )

    def test_sample_lines_zero_uses_extra_text_only(self, tmp_path: Path) -> None:
        """sample_lines=0 이면 history 무시 — `persona ingest` 가 호출하는 모드."""
        # history 가 존재해도 sample_lines=0 이면 무시되어야 함
        history = tmp_path / "history.jsonl"
        history.write_text('{"display": "/init"}\n', encoding="utf-8")

        with patch.object(
            ex_mod.ai_api,
            "complete_structured",
            return_value={
                "facts": [
                    {"category": "tech", "statement": "Swift", "confidence": 0.9}
                ]
            },
        ) as mock_complete:
            facts = extract_profile_facts(
                history_path=history,
                sample_lines=0,
                ai_env=_ai_env(),
                extra_text="외부 자료 텍스트",
            )

        assert len(facts) == 1
        # prompt 에 history 명령이 들어가지 않았는지 확인
        prompt = mock_complete.call_args[0][0]
        assert "/init" not in prompt
        assert "외부 자료 텍스트" in prompt
