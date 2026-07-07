"""Codex CLI mirror 테스트.

핵심 시나리오
- history.jsonl 수집
- sessions/<YYYY>/<MM>/<DD>/*.jsonl 재귀 수집
- session_index.jsonl 제외 (인덱스 노이즈 회피)
- 잡파일 (config.toml, *.sqlite, auth.json) 제외
- incremental tail (재호출 시 새 줄만)
- 빈 파일 skip
- 누락된 codex_home → 에러 누적 (예외 없음)
- L0 권한 적용

저자: Synapse Memory Maintainers
작성일: 2026-05-18
"""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from synapse_memory.collectors.codex.mirror import (
    OFFSETS_DIR,
    collect_codex,
)
from synapse_memory.storage.l0 import L0_DIR_MODE


@pytest.fixture
def codex_home(tmp_path: Path) -> Path:
    """가짜 ~/.codex 트리 구성."""
    home = tmp_path / "codex"
    (home / "sessions" / "2026" / "05" / "18").mkdir(parents=True)
    (home / "sessions" / "2026" / "04" / "06").mkdir(parents=True)
    # 노이즈 파일들 — collector 가 무시해야 함
    (home / "config.toml").write_text("model='gpt-5'", encoding="utf-8")
    (home / "auth.json").write_text('{"token":"x"}', encoding="utf-8")
    (home / "logs_2.sqlite").write_bytes(b"SQLite format 3\x00")
    return home


@pytest.fixture
def dst_root(tmp_path: Path) -> Path:
    return tmp_path / "l0" / "raw" / "codex"


def _write_jsonl(path: Path, *events: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")


class TestCollectCodex:
    def test_mirrors_history_and_sessions(
        self, codex_home: Path, dst_root: Path
    ) -> None:
        _write_jsonl(
            codex_home / "history.jsonl",
            {"session_id": "sid-1", "ts": 1773362408, "text": "안녕"},
            {"session_id": "sid-2", "ts": 1773362500, "text": "hi"},
        )
        _write_jsonl(
            codex_home / "sessions" / "2026" / "05" / "18" / "rollout-abc.jsonl",
            {
                "timestamp": "2026-05-18T10:00:00.000Z",
                "type": "session_meta",
                "payload": {"id": "abc"},
            },
            {
                "timestamp": "2026-05-18T10:00:01.000Z",
                "type": "event_msg",
                "payload": {"type": "task_started"},
            },
        )
        _write_jsonl(
            codex_home / "sessions" / "2026" / "04" / "06" / "rollout-old.jsonl",
            {
                "timestamp": "2026-04-06T14:49:45.754Z",
                "type": "session_meta",
                "payload": {"id": "old"},
            },
        )

        stats = collect_codex(codex_home=codex_home, dst_root=dst_root)

        assert stats.files_scanned == 3
        assert stats.files_mirrored == 3
        assert stats.bytes_added > 0
        assert stats.errors == []

        assert (dst_root / "history.jsonl").is_file()
        assert (
            dst_root / "sessions" / "2026" / "05" / "18" / "rollout-abc.jsonl"
        ).is_file()
        assert (
            dst_root / "sessions" / "2026" / "04" / "06" / "rollout-old.jsonl"
        ).is_file()

    def test_skips_session_index(
        self, codex_home: Path, dst_root: Path
    ) -> None:
        """session_index.jsonl 은 메타라서 수집 제외."""
        _write_jsonl(
            codex_home / "session_index.jsonl",
            {
                "id": "abc",
                "thread_name": "x",
                "updated_at": "2026-05-18T00:00:00Z",
            },
        )
        stats = collect_codex(codex_home=codex_home, dst_root=dst_root)
        assert stats.files_scanned == 0
        assert not (dst_root / "session_index.jsonl").exists()

    def test_skips_non_jsonl_noise(
        self, codex_home: Path, dst_root: Path
    ) -> None:
        """config.toml / auth.json / *.sqlite 같은 비-JSONL 파일은 무시."""
        stats = collect_codex(codex_home=codex_home, dst_root=dst_root)
        assert stats.files_scanned == 0
        assert not (dst_root / "config.toml").exists()
        assert not (dst_root / "auth.json").exists()

    def test_skips_empty_files(
        self, codex_home: Path, dst_root: Path
    ) -> None:
        (codex_home / "history.jsonl").touch()
        stats = collect_codex(codex_home=codex_home, dst_root=dst_root)
        assert stats.skipped_empty == 1
        assert stats.files_mirrored == 0

    def test_idempotent(self, codex_home: Path, dst_root: Path) -> None:
        _write_jsonl(
            codex_home / "history.jsonl",
            {"session_id": "sid-1", "ts": 1, "text": "x"},
        )
        s1 = collect_codex(codex_home=codex_home, dst_root=dst_root)
        s2 = collect_codex(codex_home=codex_home, dst_root=dst_root)
        assert s1.bytes_added > 0
        assert s2.bytes_added == 0
        assert s2.files_mirrored == 0

    def test_incremental_tail(self, codex_home: Path, dst_root: Path) -> None:
        rollout = (
            codex_home / "sessions" / "2026" / "05" / "18" / "rollout-x.jsonl"
        )
        _write_jsonl(
            rollout,
            {
                "timestamp": "2026-05-18T00:00:00.000Z",
                "type": "session_meta",
                "payload": {},
            },
        )
        collect_codex(codex_home=codex_home, dst_root=dst_root)
        dst = (
            dst_root / "sessions" / "2026" / "05" / "18" / "rollout-x.jsonl"
        )
        first_size = dst.stat().st_size

        _write_jsonl(
            rollout,
            {
                "timestamp": "2026-05-18T00:00:01.000Z",
                "type": "event_msg",
                "payload": {"type": "task_started"},
            },
        )
        s2 = collect_codex(codex_home=codex_home, dst_root=dst_root)
        assert s2.bytes_added > 0
        assert dst.stat().st_size > first_size

    def test_korean_content_preserved(
        self, codex_home: Path, dst_root: Path
    ) -> None:
        _write_jsonl(
            codex_home / "history.jsonl",
            {"session_id": "sid", "ts": 1, "text": "한국어 메시지"},
        )
        collect_codex(codex_home=codex_home, dst_root=dst_root)
        content = (dst_root / "history.jsonl").read_text(encoding="utf-8")
        assert "한국어 메시지" in content

    def test_missing_codex_home_returns_error(
        self, tmp_path: Path, dst_root: Path
    ) -> None:
        stats = collect_codex(
            codex_home=tmp_path / "no-such-codex",
            dst_root=dst_root,
        )
        assert len(stats.errors) == 1
        assert stats.files_scanned == 0

    def test_l0_perms_set(self, codex_home: Path, dst_root: Path) -> None:
        _write_jsonl(
            codex_home / "history.jsonl",
            {"session_id": "sid", "ts": 1, "text": "x"},
        )
        collect_codex(codex_home=codex_home, dst_root=dst_root)
        assert stat.S_IMODE(dst_root.stat().st_mode) == L0_DIR_MODE
        assert (dst_root / OFFSETS_DIR).is_dir()
        assert (
            stat.S_IMODE((dst_root / OFFSETS_DIR).stat().st_mode) == L0_DIR_MODE
        )

    def test_offset_file_created(
        self, codex_home: Path, dst_root: Path
    ) -> None:
        _write_jsonl(
            codex_home / "sessions" / "2026" / "05" / "18" / "rollout-a.jsonl",
            {
                "timestamp": "2026-05-18T00:00:00.000Z",
                "type": "session_meta",
                "payload": {},
            },
        )
        collect_codex(codex_home=codex_home, dst_root=dst_root)
        offset_dir = dst_root / OFFSETS_DIR
        offsets = list(offset_dir.iterdir())
        assert len(offsets) >= 1
        # 디렉토리 구분자가 __ 로 평탄화됨
        assert any("rollout-a" in p.name for p in offsets)
        assert any("sessions__" in p.name for p in offsets)


class TestDailyStageWiring:
    """daily.run_daily 에 codex stage 가 실제로 endpoint 로 노출되는지 sanity."""

    def test_collect_codex_in_steps(self) -> None:
        from synapse_memory.daily import DAILY_STAGES, STEPS

        assert "collect_codex" in STEPS
        assert any(
            s.name == "collect_codex"
            and s.description == "Codex CLI 로그 mirror"
            for s in DAILY_STAGES
        )

    def test_stage_actions_include_codex(self) -> None:
        from synapse_memory.daily import _build_stage_actions

        actions = _build_stage_actions(
            on_log=lambda _msg: None,
            ingest_model=None,
        )
        assert "collect_codex" in actions
        assert callable(actions["collect_codex"])
