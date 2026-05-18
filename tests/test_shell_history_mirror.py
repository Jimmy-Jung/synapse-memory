"""Shell history mirror 테스트.

핵심 시나리오
- zsh_history / bash_history 동시 mirror
- 빈 파일 skip
- 누락 시 조용한 skip (errors 0, files_scanned 0)
- incremental tail (재호출 시 새 줄만)
- idempotent
- rotation (src 크기가 마지막 offset 보다 작아짐) 복구
- 한국어 명령 줄 보존
- L0 권한 적용
- daily.py stage wiring

저자: Synapse Memory Maintainers
작성일: 2026-05-18
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from synapse_memory.collectors.shell_history.mirror import (
    OFFSETS_DIR,
    collect_shell_history,
)
from synapse_memory.storage.l0 import L0_DIR_MODE


@pytest.fixture
def dst_root(tmp_path: Path) -> Path:
    return tmp_path / "l0" / "raw" / "shell-history"


@pytest.fixture
def zsh_history(tmp_path: Path) -> Path:
    return tmp_path / "zsh_history"


@pytest.fixture
def bash_history(tmp_path: Path) -> Path:
    return tmp_path / "bash_history"


def _write_lines(path: Path, *lines: str) -> None:
    with open(path, "a", encoding="utf-8") as f:
        for line in lines:
            f.write(line if line.endswith("\n") else line + "\n")


class TestCollectShellHistory:
    def test_mirrors_zsh_and_bash(
        self,
        zsh_history: Path,
        bash_history: Path,
        dst_root: Path,
    ) -> None:
        _write_lines(
            zsh_history,
            ": 1715610000:0;git status",
            ": 1715610010:0;ls -la",
        )
        _write_lines(bash_history, "git pull", "make test")

        stats = collect_shell_history(
            zsh_history=zsh_history,
            bash_history=bash_history,
            dst_root=dst_root,
        )

        assert stats.files_scanned == 2
        assert stats.files_mirrored == 2
        assert stats.bytes_added > 0
        assert stats.errors == []

        assert (dst_root / "zsh_history").is_file()
        assert (dst_root / "bash_history").is_file()
        assert "git status" in (dst_root / "zsh_history").read_text(encoding="utf-8")
        assert "make test" in (dst_root / "bash_history").read_text(encoding="utf-8")

    def test_zsh_only(
        self,
        zsh_history: Path,
        bash_history: Path,
        dst_root: Path,
    ) -> None:
        """bash 미존재여도 zsh 만으로 수집."""
        _write_lines(zsh_history, "ls")
        stats = collect_shell_history(
            zsh_history=zsh_history,
            bash_history=bash_history,  # 존재 안 함
            dst_root=dst_root,
        )
        assert stats.files_scanned == 1
        assert (dst_root / "zsh_history").is_file()
        assert not (dst_root / "bash_history").exists()

    def test_neither_exists_silent(
        self,
        zsh_history: Path,
        bash_history: Path,
        dst_root: Path,
    ) -> None:
        """둘 다 미존재 시 errors 없이 조용히 0 반환."""
        stats = collect_shell_history(
            zsh_history=zsh_history,
            bash_history=bash_history,
            dst_root=dst_root,
        )
        assert stats.files_scanned == 0
        assert stats.errors == []

    def test_empty_file_skipped(
        self,
        zsh_history: Path,
        bash_history: Path,
        dst_root: Path,
    ) -> None:
        zsh_history.touch()
        stats = collect_shell_history(
            zsh_history=zsh_history,
            bash_history=bash_history,
            dst_root=dst_root,
        )
        assert stats.skipped_empty == 1
        assert stats.files_mirrored == 0

    def test_idempotent(
        self,
        zsh_history: Path,
        bash_history: Path,
        dst_root: Path,
    ) -> None:
        _write_lines(zsh_history, "echo hi")
        s1 = collect_shell_history(
            zsh_history=zsh_history,
            bash_history=bash_history,
            dst_root=dst_root,
        )
        s2 = collect_shell_history(
            zsh_history=zsh_history,
            bash_history=bash_history,
            dst_root=dst_root,
        )
        assert s1.bytes_added > 0
        assert s2.bytes_added == 0
        assert s2.files_mirrored == 0

    def test_incremental_tail(
        self,
        zsh_history: Path,
        bash_history: Path,
        dst_root: Path,
    ) -> None:
        _write_lines(zsh_history, "echo first")
        collect_shell_history(
            zsh_history=zsh_history,
            bash_history=bash_history,
            dst_root=dst_root,
        )
        first_size = (dst_root / "zsh_history").stat().st_size

        _write_lines(zsh_history, "echo second")
        s2 = collect_shell_history(
            zsh_history=zsh_history,
            bash_history=bash_history,
            dst_root=dst_root,
        )
        assert s2.bytes_added > 0
        assert (dst_root / "zsh_history").stat().st_size > first_size
        assert "echo second" in (dst_root / "zsh_history").read_text(encoding="utf-8")

    def test_rotation_recovery(
        self,
        zsh_history: Path,
        bash_history: Path,
        dst_root: Path,
    ) -> None:
        """source 가 truncated (HISTSIZE 도달 후 prune) → 처음부터 다시."""
        _write_lines(zsh_history, "line-1", "line-2", "line-3")
        collect_shell_history(
            zsh_history=zsh_history,
            bash_history=bash_history,
            dst_root=dst_root,
        )
        # source rotation: 짧은 내용으로 덮어쓰기
        zsh_history.write_text("new-1\n", encoding="utf-8")
        stats = collect_shell_history(
            zsh_history=zsh_history,
            bash_history=bash_history,
            dst_root=dst_root,
        )
        assert stats.truncations == 1
        # dst 도 같이 reset 되어 new content 만 보유
        assert (dst_root / "zsh_history").read_text(encoding="utf-8") == "new-1\n"

    def test_korean_preserved(
        self,
        zsh_history: Path,
        bash_history: Path,
        dst_root: Path,
    ) -> None:
        _write_lines(zsh_history, "echo '한글 메시지'")
        collect_shell_history(
            zsh_history=zsh_history,
            bash_history=bash_history,
            dst_root=dst_root,
        )
        content = (dst_root / "zsh_history").read_text(encoding="utf-8")
        assert "한글 메시지" in content

    def test_l0_perms(
        self,
        zsh_history: Path,
        bash_history: Path,
        dst_root: Path,
    ) -> None:
        _write_lines(zsh_history, "ls")
        collect_shell_history(
            zsh_history=zsh_history,
            bash_history=bash_history,
            dst_root=dst_root,
        )
        assert stat.S_IMODE(dst_root.stat().st_mode) == L0_DIR_MODE
        offsets = dst_root / OFFSETS_DIR
        assert offsets.is_dir()
        assert stat.S_IMODE(offsets.stat().st_mode) == L0_DIR_MODE


class TestDailyStageWiring:
    """daily.run_daily 에 shell_history stage 등록 sanity."""

    def test_collect_shell_in_steps(self) -> None:
        from synapse_memory.daily import DAILY_STAGES, STEPS

        assert "collect_shell_history" in STEPS
        assert any(
            s.name == "collect_shell_history"
            and s.description == "Shell history mirror"
            for s in DAILY_STAGES
        )

    def test_stage_actions_include_shell(self) -> None:
        from synapse_memory.daily import _build_stage_actions

        actions = _build_stage_actions(
            classify_model="haiku",
            generate_model="sonnet",
            profile_model="sonnet",
            profile_sample_lines=10,
            profile_facts_only=True,
            on_log=lambda _msg: None,
        )
        assert "collect_shell_history" in actions
        assert callable(actions["collect_shell_history"])
