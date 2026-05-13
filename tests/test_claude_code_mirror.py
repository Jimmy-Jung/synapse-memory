"""Claude Code mirror 테스트.

핵심 시나리오
- 신규 파일 mirror
- incremental tail (재호출 시 새 줄만)
- partial line 보호 (마지막 \\n 없으면 보류)
- rotation 감지 (src 작아짐)
- 빈 파일 skip
- projects/ 트리 walk
- history.jsonl 포함
- sessions/ 제외

저자: Synapse Memory Maintainers
작성일: 2026-05-10
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from synapse_memory.collectors.claude_code.mirror import (
    OFFSETS_DIR,
    collect_claude_code,
    mirror_jsonl,
)
from synapse_memory.storage.l0 import L0_DIR_MODE


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def claude_home(tmp_path: Path) -> Path:
    """가짜 ~/.claude 트리 구성."""
    home = tmp_path / "claude"
    (home / "projects" / "-Users-sampleuser-foo").mkdir(parents=True)
    (home / "projects" / "-Users-sampleuser-bar").mkdir(parents=True)
    (home / "sessions").mkdir()
    return home


@pytest.fixture
def dst_root(tmp_path: Path) -> Path:
    return tmp_path / "l0" / "raw" / "claude-code"


def _write_jsonl(path: Path, *events: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# mirror_jsonl 단위 테스트
# ---------------------------------------------------------------------------


class TestMirrorJsonl:
    def test_first_run_copies_all(self, tmp_path: Path) -> None:
        src = tmp_path / "src.jsonl"
        dst = tmp_path / "dst.jsonl"
        offset = tmp_path / "src.offset"
        _write_jsonl(src, {"i": 1}, {"i": 2}, {"i": 3})

        result = mirror_jsonl(src, dst, offset)
        assert result.bytes_added > 0
        assert dst.read_text(encoding="utf-8") == src.read_text(encoding="utf-8")
        assert offset.read_text() == str(src.stat().st_size)

    def test_incremental_appends_only_new(self, tmp_path: Path) -> None:
        src = tmp_path / "src.jsonl"
        dst = tmp_path / "dst.jsonl"
        offset = tmp_path / "src.offset"
        _write_jsonl(src, {"i": 1}, {"i": 2})
        mirror_jsonl(src, dst, offset)

        first_size = dst.stat().st_size
        _write_jsonl(src, {"i": 3})
        result2 = mirror_jsonl(src, dst, offset)

        assert result2.bytes_added > 0
        assert dst.stat().st_size > first_size
        # dst와 src가 일치
        assert dst.read_text(encoding="utf-8") == src.read_text(encoding="utf-8")

    def test_idempotent_when_no_change(self, tmp_path: Path) -> None:
        src = tmp_path / "src.jsonl"
        dst = tmp_path / "dst.jsonl"
        offset = tmp_path / "src.offset"
        _write_jsonl(src, {"i": 1})
        mirror_jsonl(src, dst, offset)
        result = mirror_jsonl(src, dst, offset)
        assert result.bytes_added == 0

    def test_partial_line_held_back(self, tmp_path: Path) -> None:
        """마지막에 \\n 없는 줄은 다음 호출까지 보류."""
        src = tmp_path / "src.jsonl"
        dst = tmp_path / "dst.jsonl"
        offset = tmp_path / "src.offset"
        # 완전한 줄 1개 + partial
        src.write_bytes(b'{"i":1}\n{"i":2}')  # "i":2 줄에 \n 없음

        result = mirror_jsonl(src, dst, offset)
        # 첫 줄만 mirror
        assert dst.read_bytes() == b'{"i":1}\n'
        assert int(offset.read_text()) == len(b'{"i":1}\n')
        assert result.bytes_added == len(b'{"i":1}\n')

        # partial 줄에 \n 추가
        with open(src, "ab") as f:
            f.write(b"\n")
        result2 = mirror_jsonl(src, dst, offset)
        assert dst.read_bytes() == b'{"i":1}\n{"i":2}\n'
        assert result2.bytes_added == len(b'{"i":2}\n')

    def test_partial_only_held_entirely(self, tmp_path: Path) -> None:
        """완전한 줄이 0개면 mirror 0 byte."""
        src = tmp_path / "src.jsonl"
        dst = tmp_path / "dst.jsonl"
        offset = tmp_path / "src.offset"
        src.write_bytes(b'partial without newline')
        result = mirror_jsonl(src, dst, offset)
        assert result.bytes_added == 0
        assert not dst.exists()

    def test_rotation_resets(self, tmp_path: Path) -> None:
        """src가 작아지면 처음부터 다시."""
        src = tmp_path / "src.jsonl"
        dst = tmp_path / "dst.jsonl"
        offset = tmp_path / "src.offset"
        _write_jsonl(src, {"i": 1}, {"i": 2}, {"i": 3})
        mirror_jsonl(src, dst, offset)
        assert dst.exists()

        # rotation: 더 작은 새 내용
        src.write_bytes(b'{"i":99}\n')
        result = mirror_jsonl(src, dst, offset)

        assert result.truncated_reset is True
        assert dst.read_bytes() == b'{"i":99}\n'

    def test_korean_content_preserved(self, tmp_path: Path) -> None:
        src = tmp_path / "src.jsonl"
        dst = tmp_path / "dst.jsonl"
        offset = tmp_path / "src.offset"
        _write_jsonl(src, {"display": "한국어 메시지", "timestamp": 1000})
        mirror_jsonl(src, dst, offset)
        assert "한국어 메시지" in dst.read_text(encoding="utf-8")

    def test_missing_src_returns_zero(self, tmp_path: Path) -> None:
        result = mirror_jsonl(
            tmp_path / "nope.jsonl",
            tmp_path / "dst.jsonl",
            tmp_path / "off",
        )
        assert result.bytes_added == 0


# ---------------------------------------------------------------------------
# collect_claude_code 통합
# ---------------------------------------------------------------------------


class TestCollectClaudeCode:
    def test_mirrors_history_and_projects(
        self, claude_home: Path, dst_root: Path
    ) -> None:
        # history.jsonl
        _write_jsonl(
            claude_home / "history.jsonl",
            {"display": "/help", "timestamp": 1000},
            {"display": "/init", "timestamp": 2000},
        )
        # projects/.../<id>.jsonl
        _write_jsonl(
            claude_home / "projects" / "-Users-sampleuser-foo" / "abc.jsonl",
            {"type": "user", "content": "안녕"},
            {"type": "assistant", "content": "안녕하세요"},
        )

        stats = collect_claude_code(claude_home=claude_home, dst_root=dst_root)

        assert stats.files_scanned == 2
        assert stats.files_mirrored == 2
        assert stats.bytes_added > 0
        assert stats.errors == []

        # mirror 위치 검증
        assert (dst_root / "history.jsonl").is_file()
        assert (
            dst_root / "projects" / "-Users-sampleuser-foo" / "abc.jsonl"
        ).is_file()

    def test_skips_sessions_dir(
        self, claude_home: Path, dst_root: Path
    ) -> None:
        # sessions에 메타 파일 (수집 제외 대상)
        (claude_home / "sessions" / "12345.json").write_text(
            '{"pid":12345}', encoding="utf-8"
        )
        _write_jsonl(
            claude_home / "history.jsonl", {"display": "x", "timestamp": 1}
        )
        stats = collect_claude_code(claude_home=claude_home, dst_root=dst_root)
        # sessions/는 enumerate 안 됨
        assert stats.files_scanned == 1

    def test_skips_empty_files(
        self, claude_home: Path, dst_root: Path
    ) -> None:
        (claude_home / "history.jsonl").touch()
        stats = collect_claude_code(claude_home=claude_home, dst_root=dst_root)
        assert stats.skipped_empty == 1
        assert stats.files_mirrored == 0

    def test_idempotent(
        self, claude_home: Path, dst_root: Path
    ) -> None:
        _write_jsonl(
            claude_home / "history.jsonl", {"display": "x", "timestamp": 1}
        )
        s1 = collect_claude_code(claude_home=claude_home, dst_root=dst_root)
        s2 = collect_claude_code(claude_home=claude_home, dst_root=dst_root)
        assert s1.bytes_added > 0
        assert s2.bytes_added == 0
        assert s2.files_mirrored == 0

    def test_l0_perms_set(
        self, claude_home: Path, dst_root: Path
    ) -> None:
        _write_jsonl(
            claude_home / "history.jsonl", {"display": "x", "timestamp": 1}
        )
        collect_claude_code(claude_home=claude_home, dst_root=dst_root)
        assert stat.S_IMODE(dst_root.stat().st_mode) == L0_DIR_MODE
        assert (dst_root / OFFSETS_DIR).is_dir()
        assert stat.S_IMODE((dst_root / OFFSETS_DIR).stat().st_mode) == L0_DIR_MODE

    def test_protects_loose_l0_root(
        self,
        claude_home: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """기존에 0755로 만들어진 L0 루트도 collect 호출로 0700 정정."""
        fake_l0 = tmp_path / "private"
        fake_l0.mkdir()
        os.chmod(fake_l0, 0o755)
        assert stat.S_IMODE(fake_l0.stat().st_mode) == 0o755

        monkeypatch.setenv("SYNAPSE_L0_ROOT", str(fake_l0))
        dst = fake_l0 / "raw" / "claude-code"

        _write_jsonl(
            claude_home / "history.jsonl", {"display": "x", "timestamp": 1}
        )
        collect_claude_code(claude_home=claude_home, dst_root=dst)

        assert stat.S_IMODE(fake_l0.stat().st_mode) == L0_DIR_MODE

    def test_missing_claude_home_returns_error(
        self, tmp_path: Path, dst_root: Path
    ) -> None:
        stats = collect_claude_code(
            claude_home=tmp_path / "nonexistent",
            dst_root=dst_root,
        )
        assert len(stats.errors) == 1
        assert stats.files_scanned == 0

    def test_offset_file_created(
        self, claude_home: Path, dst_root: Path
    ) -> None:
        _write_jsonl(
            claude_home / "history.jsonl", {"display": "x", "timestamp": 1}
        )
        collect_claude_code(claude_home=claude_home, dst_root=dst_root)
        offset_dir = dst_root / OFFSETS_DIR
        offsets = list(offset_dir.iterdir())
        assert len(offsets) >= 1
        # 파일명에 history.jsonl 흔적
        assert any("history" in p.name for p in offsets)


# ---------------------------------------------------------------------------
# 안전성 sanity
# ---------------------------------------------------------------------------


def test_no_overwrite_unrelated_files(
    claude_home: Path, tmp_path: Path
) -> None:
    """dst_root 밖 파일은 절대 손대지 않음."""
    sentinel = tmp_path / "sentinel.txt"
    sentinel.write_text("DO NOT TOUCH")
    sentinel_mtime = sentinel.stat().st_mtime
    _write_jsonl(
        claude_home / "history.jsonl", {"display": "x", "timestamp": 1}
    )
    collect_claude_code(
        claude_home=claude_home,
        dst_root=tmp_path / "l0" / "raw" / "claude-code",
    )
    assert sentinel.read_text() == "DO NOT TOUCH"
    assert sentinel.stat().st_mtime == sentinel_mtime
