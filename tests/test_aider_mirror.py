"""Aider mirror 테스트.

핵심 시나리오 (append-only 파일을 같은 mirror_jsonl 로 재사용)
- chat.history.md + input.history 동시 mirror
- 둘 다 미존재 → silent
- 빈 파일 skip
- idempotent / incremental
- L0 권한
- daily wiring

저자: Synapse Memory Maintainers
작성일: 2026-05-18
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from synapse_memory.collectors.aider.mirror import OFFSETS_DIR, collect_aider
from synapse_memory.storage.l0 import L0_DIR_MODE


@pytest.fixture
def chat_history(tmp_path: Path) -> Path:
    return tmp_path / "aider-chat.md"


@pytest.fixture
def input_history(tmp_path: Path) -> Path:
    return tmp_path / "aider-input"


@pytest.fixture
def dst_root(tmp_path: Path) -> Path:
    return tmp_path / "l0" / "raw" / "aider"


def _append(path: Path, *lines: str) -> None:
    with open(path, "a", encoding="utf-8") as f:
        for line in lines:
            f.write(line if line.endswith("\n") else line + "\n")


class TestCollectAider:
    def test_mirrors_both(
        self,
        chat_history: Path,
        input_history: Path,
        dst_root: Path,
    ) -> None:
        _append(
            chat_history,
            "# aider chat session",
            "> add error handling to login.py",
            "Sure, here is the diff...",
        )
        _append(input_history, "add error handling", "/diff")

        stats = collect_aider(
            chat_history=chat_history,
            input_history=input_history,
            dst_root=dst_root,
        )

        assert stats.files_scanned == 2
        assert stats.files_mirrored == 2
        assert (dst_root / "chat.history.md").is_file()
        assert (dst_root / "input.history").is_file()
        assert "aider chat session" in (
            dst_root / "chat.history.md"
        ).read_text(encoding="utf-8")

    def test_silent_when_uninstalled(
        self,
        chat_history: Path,
        input_history: Path,
        dst_root: Path,
    ) -> None:
        stats = collect_aider(
            chat_history=chat_history,
            input_history=input_history,
            dst_root=dst_root,
        )
        assert stats.files_scanned == 0
        assert stats.errors == []

    def test_empty_skipped(
        self,
        chat_history: Path,
        input_history: Path,
        dst_root: Path,
    ) -> None:
        chat_history.touch()
        stats = collect_aider(
            chat_history=chat_history,
            input_history=input_history,
            dst_root=dst_root,
        )
        assert stats.skipped_empty == 1
        assert stats.files_mirrored == 0

    def test_idempotent_and_incremental(
        self,
        chat_history: Path,
        input_history: Path,
        dst_root: Path,
    ) -> None:
        _append(chat_history, "> q1")
        s1 = collect_aider(
            chat_history=chat_history,
            input_history=input_history,
            dst_root=dst_root,
        )
        s2 = collect_aider(
            chat_history=chat_history,
            input_history=input_history,
            dst_root=dst_root,
        )
        assert s1.bytes_added > 0
        assert s2.bytes_added == 0

        _append(chat_history, "> q2")
        s3 = collect_aider(
            chat_history=chat_history,
            input_history=input_history,
            dst_root=dst_root,
        )
        assert s3.bytes_added > 0
        assert "q2" in (dst_root / "chat.history.md").read_text(encoding="utf-8")

    def test_korean_preserved(
        self,
        chat_history: Path,
        input_history: Path,
        dst_root: Path,
    ) -> None:
        _append(chat_history, "> 한국어 질문")
        collect_aider(
            chat_history=chat_history,
            input_history=input_history,
            dst_root=dst_root,
        )
        assert "한국어 질문" in (
            dst_root / "chat.history.md"
        ).read_text(encoding="utf-8")

    def test_l0_perms(
        self,
        chat_history: Path,
        input_history: Path,
        dst_root: Path,
    ) -> None:
        _append(chat_history, "> q")
        collect_aider(
            chat_history=chat_history,
            input_history=input_history,
            dst_root=dst_root,
        )
        assert stat.S_IMODE(dst_root.stat().st_mode) == L0_DIR_MODE
        assert (dst_root / OFFSETS_DIR).is_dir()


class TestDailyStageWiring:
    def test_collect_aider_in_steps(self) -> None:
        from synapse_memory.daily import DAILY_STAGES, STEPS

        assert "collect_aider" in STEPS
        assert any(
            s.name == "collect_aider"
            and s.description == "Aider 대화 mirror"
            for s in DAILY_STAGES
        )

    def test_stage_actions_include_aider(self) -> None:
        from synapse_memory.daily import _build_stage_actions

        actions = _build_stage_actions(
            classify_model="haiku",
            generate_model="sonnet",
            profile_model="sonnet",
            profile_sample_lines=10,
            profile_facts_only=True,
            on_log=lambda _msg: None,
        )
        assert "collect_aider" in actions
        assert callable(actions["collect_aider"])
