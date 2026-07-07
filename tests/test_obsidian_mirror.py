"""Obsidian vault → L0 mirror 테스트.

저자: Synapse Memory Maintainers
작성일: 2026-05-10
"""

from __future__ import annotations

import json
import os
import stat
import time
from pathlib import Path

import pytest

from synapse_memory.collectors.obsidian.mirror import (
    META_DIR,
    STATES_FILE,
    CollectStats,
    _is_excluded,
    collect_obsidian,
)
from synapse_memory.config import ENV_VAR_VAULT, SynapseConfig, get_vault_path
from synapse_memory.storage.l0 import L0_DIR_MODE, L0_FILE_MODE
from synapse_memory.vault_detector import VaultCandidate, VaultSource

# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """가짜 Obsidian vault — 폴더 구조 + 일부 파일."""
    v = tmp_path / "vault"
    (v / "00_Inbox").mkdir(parents=True)
    (v / "10_Active").mkdir(parents=True)
    (v / "90_System" / "AI").mkdir(parents=True)
    (v / "90_System" / "Templates").mkdir(parents=True)
    (v / ".obsidian").mkdir()
    (v / ".trash").mkdir()
    return v


@pytest.fixture
def dst(tmp_path: Path) -> Path:
    return tmp_path / "l0" / "raw" / "obsidian"


def _write_md(vault: Path, rel: str, content: str) -> Path:
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# get_vault_path
# ---------------------------------------------------------------------------


class TestGetVaultPath:
    def test_default(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        detected = tmp_path / "detected"
        monkeypatch.delenv(ENV_VAR_VAULT, raising=False)
        monkeypatch.setattr("synapse_memory.config.get_config", lambda **_: SynapseConfig())
        monkeypatch.setattr(
            "synapse_memory.vault_detector.detect_vault_candidates",
            lambda: [
                VaultCandidate(
                    path=detected,
                    source=VaultSource.DOCUMENTS_OBSIDIAN,
                    display_name="detected",
                    has_obsidian_dir=True,
                    confidence=70,
                )
            ],
        )

        assert get_vault_path() == detected.resolve()

    def test_env_override(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv(ENV_VAR_VAULT, str(tmp_path))
        assert get_vault_path() == tmp_path.resolve()


# ---------------------------------------------------------------------------
# exclude 패턴
# ---------------------------------------------------------------------------


class TestIsExcluded:
    @pytest.mark.parametrize(
        "rel",
        [
            "90_System/AI/Profile.md",
            "90_System/AI/Inner/Deep.md",
            "90_System/Attachments/image.md",
            "90_System/_migration/snapshot.md",
            ".obsidian/config.md",
            ".trash/old.md",
            ".claude/agents/foo.md",
            ".codex/config.md",
            "00_Inbox/Note (sync-conflict 2026-01).md",
        ],
    )
    def test_excluded(self, rel: str) -> None:
        assert _is_excluded(Path(rel)) is True

    @pytest.mark.parametrize(
        "rel",
        [
            "00_Inbox/Note.md",
            "10_Active/Project.md",
            "90_System/Templates/Daily.md",  # 90_System은 OK, AI만 제외
            "90_System/Home.md",
            "20_Reference/Topic.md",
        ],
    )
    def test_included(self, rel: str) -> None:
        assert _is_excluded(Path(rel)) is False

    def test_configured_wiki_folders_are_excluded(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = SynapseConfig()
        monkeypatch.setattr("synapse_memory.config.get_config", lambda: cfg)

        generated = (
            "Entities/Projects/Auto.md",
            "Entities/Companies/Auto.md",
            "Entities/People/Auto.md",
            "Concepts/Auto.md",
            "Insights/Auto.md",
            "Profile/Auto.md",
        )

        for rel in generated:
            assert _is_excluded(Path(rel)) is True

        assert _is_excluded(Path("20_Reference/Projects/Human.md")) is False

    def test_configured_wiki_folders_use_overrides(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = SynapseConfig()
        cfg.vault_folders.wiki.projects = "Generated/Projects"
        monkeypatch.setattr("synapse_memory.config.get_config", lambda: cfg)

        assert _is_excluded(Path("Generated/Projects/Auto.md")) is True
        assert _is_excluded(Path("Entities/Projects/Human.md")) is False


# ---------------------------------------------------------------------------
# collect_obsidian
# ---------------------------------------------------------------------------


class TestCollectObsidian:
    def test_first_run_copies_md_files(
        self, vault: Path, dst: Path
    ) -> None:
        _write_md(vault, "00_Inbox/note1.md", "내용 1")
        _write_md(vault, "10_Active/project.md", "프로젝트")

        stats = collect_obsidian(vault_path=vault, dst_root=dst)

        assert stats.files_scanned == 2
        assert stats.files_mirrored == 2
        assert stats.files_unchanged == 0
        assert (dst / "00_Inbox" / "note1.md").read_text(encoding="utf-8") == "내용 1"
        assert (dst / "10_Active" / "project.md").read_text(encoding="utf-8") == "프로젝트"

    def test_meta_states_persisted(self, vault: Path, dst: Path) -> None:
        _write_md(vault, "00_Inbox/x.md", "x")
        collect_obsidian(vault_path=vault, dst_root=dst)
        meta = dst / META_DIR / STATES_FILE
        assert meta.is_file()
        data = json.loads(meta.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert any(item["rel_path"] == "00_Inbox/x.md" for item in data)

    def test_unchanged_files_skipped(
        self, vault: Path, dst: Path
    ) -> None:
        _write_md(vault, "00_Inbox/note.md", "동일")
        collect_obsidian(vault_path=vault, dst_root=dst)

        s2 = collect_obsidian(vault_path=vault, dst_root=dst)
        assert s2.files_unchanged == 1
        assert s2.files_mirrored == 0
        assert s2.bytes_added == 0

    def test_modified_file_remirrored(
        self, vault: Path, dst: Path
    ) -> None:
        f = _write_md(vault, "00_Inbox/note.md", "first")
        collect_obsidian(vault_path=vault, dst_root=dst)

        # 충분히 시간 지나서 mtime이 다르게
        time.sleep(0.05)
        f.write_text("second 내용", encoding="utf-8")

        s2 = collect_obsidian(vault_path=vault, dst_root=dst)
        assert s2.files_mirrored == 1
        assert (dst / "00_Inbox" / "note.md").read_text(encoding="utf-8") == "second 내용"

    def test_touch_only_no_recopy(
        self, vault: Path, dst: Path
    ) -> None:
        """mtime만 바뀌고 content는 같으면 hash 일치 → unchanged 카운트."""
        f = _write_md(vault, "00_Inbox/n.md", "same content")
        collect_obsidian(vault_path=vault, dst_root=dst)

        # mtime만 강제로 변경 (touch)
        new_time = f.stat().st_mtime + 100
        os.utime(f, (new_time, new_time))

        s2 = collect_obsidian(vault_path=vault, dst_root=dst)
        # hash 일치 → unchanged 분류, mirror 안 함
        assert s2.files_mirrored == 0
        assert s2.files_unchanged == 1

    def test_excluded_dirs_not_mirrored(
        self, vault: Path, dst: Path
    ) -> None:
        _write_md(vault, "00_Inbox/keep.md", "keep")
        _write_md(vault, "90_System/AI/Profile.md", "ai memory — 제외 대상")
        _write_md(vault, "90_System/Attachments/img.md", "attached")
        _write_md(vault, ".trash/old.md", "deleted")

        stats = collect_obsidian(vault_path=vault, dst_root=dst)
        assert stats.files_scanned == 1  # keep만 scan됨
        assert (dst / "00_Inbox" / "keep.md").is_file()
        assert not (dst / "90_System" / "AI" / "Profile.md").exists()

    def test_generated_wiki_folders_not_mirrored(
        self, vault: Path, dst: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = SynapseConfig()
        monkeypatch.setattr("synapse_memory.config.get_config", lambda: cfg)

        _write_md(vault, "00_Inbox/keep.md", "keep")
        _write_md(vault, "20_Reference/Projects/human.md", "human")
        _write_md(vault, "Entities/Projects/generated.md", "generated")
        _write_md(vault, "Concepts/generated.md", "generated")
        _write_md(vault, "90_System/AI/DailyReports/report.md", "generated")

        stats = collect_obsidian(vault_path=vault, dst_root=dst)

        assert stats.files_scanned == 2
        assert (dst / "00_Inbox" / "keep.md").is_file()
        assert (dst / "20_Reference" / "Projects" / "human.md").is_file()
        assert not (dst / "Entities" / "Projects" / "generated.md").exists()
        assert not (dst / "Concepts" / "generated.md").exists()
        assert not (dst / "90_System" / "AI" / "DailyReports" / "report.md").exists()

    def test_korean_filename_handled(
        self, vault: Path, dst: Path
    ) -> None:
        _write_md(vault, "00_Inbox/한국어 노트.md", "안녕")
        collect_obsidian(vault_path=vault, dst_root=dst)
        assert (dst / "00_Inbox" / "한국어 노트.md").read_text(encoding="utf-8") == "안녕"

    def test_l0_perms(self, vault: Path, dst: Path) -> None:
        _write_md(vault, "00_Inbox/n.md", "x")
        collect_obsidian(vault_path=vault, dst_root=dst)
        assert stat.S_IMODE(dst.stat().st_mode) == L0_DIR_MODE
        assert (
            stat.S_IMODE((dst / "00_Inbox" / "n.md").stat().st_mode) == L0_FILE_MODE
        )

    def test_protects_loose_l0_root(
        self,
        vault: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """기존에 0755로 만들어진 L0 루트도 collect 호출로 0700 정정."""
        fake_l0 = tmp_path / "private"
        fake_l0.mkdir()
        os.chmod(fake_l0, 0o755)

        monkeypatch.setenv("SYNAPSE_L0_ROOT", str(fake_l0))
        dst_in_l0 = fake_l0 / "raw" / "obsidian"

        _write_md(vault, "00_Inbox/n.md", "x")
        collect_obsidian(vault_path=vault, dst_root=dst_in_l0)

        assert stat.S_IMODE(fake_l0.stat().st_mode) == L0_DIR_MODE

    def test_missing_vault_returns_error(
        self, tmp_path: Path, dst: Path
    ) -> None:
        stats = collect_obsidian(
            vault_path=tmp_path / "nonexistent_vault",
            dst_root=dst,
        )
        assert len(stats.errors) == 1
        assert stats.files_scanned == 0

    def test_non_md_files_ignored(
        self, vault: Path, dst: Path
    ) -> None:
        _write_md(vault, "00_Inbox/note.md", "md")
        (vault / "00_Inbox" / "image.png").write_bytes(b"fake png")
        (vault / "00_Inbox" / "data.json").write_text('{"x": 1}', encoding="utf-8")

        stats = collect_obsidian(vault_path=vault, dst_root=dst)
        assert stats.files_scanned == 1  # md만
        assert not (dst / "00_Inbox" / "image.png").exists()
        assert not (dst / "00_Inbox" / "data.json").exists()


# ---------------------------------------------------------------------------
# 안전성
# ---------------------------------------------------------------------------


def test_no_overwrite_unrelated_files(
    vault: Path, tmp_path: Path
) -> None:
    sentinel = tmp_path / "sentinel.txt"
    sentinel.write_text("DO NOT TOUCH")
    _write_md(vault, "00_Inbox/n.md", "x")

    collect_obsidian(
        vault_path=vault,
        dst_root=tmp_path / "l0" / "raw" / "obsidian",
    )
    assert sentinel.read_text() == "DO NOT TOUCH"


# ---------------------------------------------------------------------------
# since_days cutoff (B1, --quick 모드)
# ---------------------------------------------------------------------------


class TestSinceDaysCutoff:
    """``--quick`` 모드의 mtime 기반 cutoff. vault 파일 손실 없음, 단지 mirror cycle skip."""

    def _set_mtime_days_ago(self, path: Path, days: float) -> None:
        ts = time.time() - days * 86400.0
        os.utime(path, (ts, ts))

    def test_recent_files_mirrored_old_files_skipped(
        self, vault: Path, dst: Path
    ) -> None:
        recent = _write_md(vault, "00_Inbox/recent.md", "최근")
        old = _write_md(vault, "00_Inbox/old.md", "오래된")
        self._set_mtime_days_ago(recent, 1.0)
        self._set_mtime_days_ago(old, 30.0)

        stats = collect_obsidian(vault_path=vault, dst_root=dst, since_days=7)

        assert stats.files_scanned == 2
        assert stats.files_mirrored == 1
        assert stats.files_skipped_by_cutoff == 1
        assert (dst / "00_Inbox" / "recent.md").is_file()
        assert not (dst / "00_Inbox" / "old.md").exists()

    def test_zero_days_skips_all_unmodified_recently(
        self, vault: Path, dst: Path
    ) -> None:
        """since_days=0 → cutoff = now → 모든 파일 skip (boundary)."""
        f = _write_md(vault, "00_Inbox/note.md", "x")
        self._set_mtime_days_ago(f, 0.5)  # 12시간 전

        stats = collect_obsidian(vault_path=vault, dst_root=dst, since_days=0)
        assert stats.files_skipped_by_cutoff == 1
        assert stats.files_mirrored == 0

    def test_no_cutoff_preserves_full_behavior(
        self, vault: Path, dst: Path
    ) -> None:
        """since_days=None → 기존 동작 그대로 (회귀 가드)."""
        _write_md(vault, "00_Inbox/recent.md", "a")
        old = _write_md(vault, "00_Inbox/old.md", "b")
        self._set_mtime_days_ago(old, 30.0)

        stats = collect_obsidian(vault_path=vault, dst_root=dst)  # no since_days
        assert stats.files_mirrored == 2
        assert stats.files_skipped_by_cutoff == 0

    def test_cutoff_preserves_prev_state_for_skipped_files(
        self, vault: Path, dst: Path
    ) -> None:
        """skip 된 오래된 파일의 prev_state 는 보존 — 다음 full mode 호출 시 unchanged 분류."""
        old = _write_md(vault, "00_Inbox/old.md", "기존")
        _write_md(vault, "00_Inbox/recent.md", "신규")

        # First full mode: 둘 다 mirror
        collect_obsidian(vault_path=vault, dst_root=dst)

        # 시간 흐름 시뮬레이션: old 의 mtime 을 30일 전으로
        self._set_mtime_days_ago(old, 30.0)

        # Quick mode: old 는 cutoff skip, 단 prev_state 는 유지
        s2 = collect_obsidian(vault_path=vault, dst_root=dst, since_days=7)
        assert s2.files_skipped_by_cutoff == 1
        assert s2.files_unchanged == 1  # recent

        # Next full mode (since_days=None): old 의 prev_state 가 보존되었으므로 unchanged
        # (그렇지 않으면 또 다시 mirror 됨)
        self._set_mtime_days_ago(old, 30.0)  # 안정화
        s3 = collect_obsidian(vault_path=vault, dst_root=dst)
        # old + recent 둘 다 unchanged 가 되어야 함 (mtime/size/sha 일치)
        assert s3.files_unchanged == 2
        assert s3.files_mirrored == 0

    def test_negative_since_days_rejected(self, vault: Path, dst: Path) -> None:
        with pytest.raises(ValueError):
            collect_obsidian(vault_path=vault, dst_root=dst, since_days=-1)

    def test_stats_summary_shows_cutoff_when_nonzero(
        self, vault: Path, dst: Path
    ) -> None:
        old = _write_md(vault, "00_Inbox/old.md", "x")
        self._set_mtime_days_ago(old, 30.0)
        stats = collect_obsidian(vault_path=vault, dst_root=dst, since_days=7)
        assert "cutoff_skip=1" in stats.summary()

        # since_days=None 일 때는 summary 에 cutoff 가 노출되지 않음 (clean)
        stats2 = CollectStats()
        assert "cutoff_skip" not in stats2.summary()
