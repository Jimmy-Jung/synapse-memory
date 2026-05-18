"""apple_health mirror 테스트.

저자: Synapse Memory Maintainers
작성일: 2026-05-18
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from synapse_memory.collectors.apple_health.mirror import (
    META_DIR,
    STATES_FILE,
    collect_apple_health,
)
from synapse_memory.storage.l0 import L0_DIR_MODE


@pytest.fixture
def drop_dir(tmp_path: Path) -> Path:
    d = tmp_path / "Downloads"
    d.mkdir()
    return d


@pytest.fixture
def dst_root(tmp_path: Path) -> Path:
    return tmp_path / "l0" / "raw" / "apple-health"


class TestCollectAppleHealth:
    def test_mirrors_export_zip(
        self, drop_dir: Path, dst_root: Path
    ) -> None:
        (drop_dir / "export.zip").write_bytes(b"fake zip content")
        (drop_dir / "export-1.zip").write_bytes(b"another zip")
        # 무관 파일 — 무시되어야 함
        (drop_dir / "random.pdf").write_bytes(b"pdf")

        stats = collect_apple_health(
            drop_dir=drop_dir, dst_root=dst_root
        )
        assert stats.files_scanned == 2
        assert stats.files_mirrored == 2
        assert (dst_root / "export.zip").is_file()
        assert (dst_root / "export-1.zip").is_file()
        assert not (dst_root / "random.pdf").exists()

    def test_env_override(
        self, drop_dir: Path, dst_root: Path
    ) -> None:
        (drop_dir / "export.zip").write_bytes(b"x")
        stats = collect_apple_health(
            drop_dir_env=str(drop_dir),
            dst_root=dst_root,
        )
        assert stats.files_mirrored == 1

    def test_silent_when_drop_missing(
        self, tmp_path: Path, dst_root: Path
    ) -> None:
        stats = collect_apple_health(
            drop_dir=tmp_path / "no-such",
            dst_root=dst_root,
        )
        assert stats.files_scanned == 0
        assert stats.errors == []

    def test_silent_when_empty_drop(
        self, drop_dir: Path, dst_root: Path
    ) -> None:
        """drop_dir 존재하지만 export*.zip 없음."""
        stats = collect_apple_health(
            drop_dir=drop_dir, dst_root=dst_root
        )
        assert stats.files_scanned == 0
        assert stats.errors == []

    def test_idempotent(
        self, drop_dir: Path, dst_root: Path
    ) -> None:
        (drop_dir / "export.zip").write_bytes(b"data")
        collect_apple_health(drop_dir=drop_dir, dst_root=dst_root)
        s2 = collect_apple_health(drop_dir=drop_dir, dst_root=dst_root)
        assert s2.files_mirrored == 0
        assert s2.files_unchanged == 1

    def test_change_triggers_remirror(
        self, drop_dir: Path, dst_root: Path
    ) -> None:
        src = drop_dir / "export.zip"
        src.write_bytes(b"v1")
        collect_apple_health(drop_dir=drop_dir, dst_root=dst_root)
        src.write_bytes(b"v2 newer content")
        s2 = collect_apple_health(drop_dir=drop_dir, dst_root=dst_root)
        assert s2.files_mirrored == 1
        assert (dst_root / "export.zip").read_bytes() == b"v2 newer content"

    def test_l0_perms(self, drop_dir: Path, dst_root: Path) -> None:
        (drop_dir / "export.zip").write_bytes(b"x")
        collect_apple_health(drop_dir=drop_dir, dst_root=dst_root)
        assert stat.S_IMODE(dst_root.stat().st_mode) == L0_DIR_MODE
        assert (dst_root / META_DIR / STATES_FILE).is_file()


class TestDailyStageWiring:
    def test_collect_apple_health_in_steps(self) -> None:
        from synapse_memory.daily import DAILY_STAGES, STEPS

        assert "collect_apple_health" in STEPS
        assert any(
            s.name == "collect_apple_health"
            and s.description == "Apple Health export mirror"
            for s in DAILY_STAGES
        )

    def test_stage_actions_include_apple_health(self) -> None:
        from synapse_memory.daily import _build_stage_actions

        actions = _build_stage_actions(
            classify_model="haiku",
            generate_model="sonnet",
            profile_model="sonnet",
            profile_sample_lines=10,
            profile_facts_only=True,
            on_log=lambda _msg: None,
        )
        assert "collect_apple_health" in actions
        assert callable(actions["collect_apple_health"])
