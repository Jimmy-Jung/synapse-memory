"""Continue.dev mirror 테스트.

핵심 시나리오
- sessions/*.json + dev_data/*.jsonl 동시 mirror
- 최상위 index.json/config.json 제외
- 미설치 (~/.continue 없음) → errors 없이 빈 통계
- idempotent (변경 없으면 files_unchanged)
- 내용 변경 시 re-mirror
- L0 권한
- daily.py wiring

저자: Synapse Memory Maintainers
작성일: 2026-05-18
"""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from synapse_memory.collectors.continue_dev.mirror import (
    META_DIR,
    STATES_FILE,
    collect_continue,
)
from synapse_memory.storage.l0 import L0_DIR_MODE


@pytest.fixture
def continue_home(tmp_path: Path) -> Path:
    home = tmp_path / "continue"
    (home / "sessions").mkdir(parents=True)
    (home / "dev_data").mkdir(parents=True)
    (home / "config.json").write_text('{"model":"gpt-5"}', encoding="utf-8")
    return home


@pytest.fixture
def dst_root(tmp_path: Path) -> Path:
    return tmp_path / "l0" / "raw" / "continue"


class TestCollectContinue:
    def test_mirrors_sessions_and_devdata(
        self, continue_home: Path, dst_root: Path
    ) -> None:
        (continue_home / "sessions" / "sess-1.json").write_text(
            json.dumps({"id": "sess-1", "messages": [{"role": "user", "text": "hi"}]}),
            encoding="utf-8",
        )
        (continue_home / "dev_data" / "events.jsonl").write_text(
            '{"event": "completion", "ts": 1}\n', encoding="utf-8"
        )

        stats = collect_continue(continue_home=continue_home, dst_root=dst_root)

        assert stats.files_scanned == 2
        assert stats.files_mirrored == 2
        assert (dst_root / "sessions" / "sess-1.json").is_file()
        assert (dst_root / "dev_data" / "events.jsonl").is_file()

    def test_excludes_top_level_config(
        self, continue_home: Path, dst_root: Path
    ) -> None:
        """최상위 config.json 은 수집 안 됨."""
        stats = collect_continue(continue_home=continue_home, dst_root=dst_root)
        assert stats.files_scanned == 0
        assert not (dst_root / "config.json").exists()

    def test_silent_when_uninstalled(
        self, tmp_path: Path, dst_root: Path
    ) -> None:
        """~/.continue 미존재 → errors 0, files 0 (정상)."""
        stats = collect_continue(
            continue_home=tmp_path / "no-such",
            dst_root=dst_root,
        )
        assert stats.files_scanned == 0
        assert stats.errors == []

    def test_idempotent(
        self, continue_home: Path, dst_root: Path
    ) -> None:
        (continue_home / "sessions" / "sess.json").write_text(
            '{"id":"sess"}', encoding="utf-8"
        )
        s1 = collect_continue(continue_home=continue_home, dst_root=dst_root)
        s2 = collect_continue(continue_home=continue_home, dst_root=dst_root)
        assert s1.files_mirrored == 1
        assert s2.files_mirrored == 0
        assert s2.files_unchanged == 1

    def test_change_triggers_remirror(
        self, continue_home: Path, dst_root: Path
    ) -> None:
        src = continue_home / "sessions" / "sess.json"
        src.write_text('{"id":"sess","v":1}', encoding="utf-8")
        collect_continue(continue_home=continue_home, dst_root=dst_root)

        src.write_text('{"id":"sess","v":2}', encoding="utf-8")
        s2 = collect_continue(continue_home=continue_home, dst_root=dst_root)
        assert s2.files_mirrored == 1
        assert (dst_root / "sessions" / "sess.json").read_text(
            encoding="utf-8"
        ) == '{"id":"sess","v":2}'

    def test_korean_preserved(
        self, continue_home: Path, dst_root: Path
    ) -> None:
        (continue_home / "sessions" / "한글.json").write_text(
            json.dumps({"text": "한국어 메시지"}, ensure_ascii=False),
            encoding="utf-8",
        )
        collect_continue(continue_home=continue_home, dst_root=dst_root)
        content = (dst_root / "sessions" / "한글.json").read_text(encoding="utf-8")
        assert "한국어 메시지" in content

    def test_l0_perms(self, continue_home: Path, dst_root: Path) -> None:
        (continue_home / "sessions" / "x.json").write_text("{}", encoding="utf-8")
        collect_continue(continue_home=continue_home, dst_root=dst_root)
        assert stat.S_IMODE(dst_root.stat().st_mode) == L0_DIR_MODE
        assert (dst_root / META_DIR / STATES_FILE).is_file()


class TestDailyStageWiring:
    def test_collect_continue_in_steps(self) -> None:
        from synapse_memory.daily import DAILY_STAGES, STEPS

        assert "collect_continue" in STEPS
        assert any(
            s.name == "collect_continue"
            and s.description == "Continue.dev 세션 mirror"
            for s in DAILY_STAGES
        )

    def test_stage_actions_include_continue(self) -> None:
        from synapse_memory.daily import _build_stage_actions

        actions = _build_stage_actions(
            classify_model="haiku",
            generate_model="sonnet",
            profile_model="sonnet",
            profile_sample_lines=10,
            profile_facts_only=True,
            on_log=lambda _msg: None,
        )
        assert "collect_continue" in actions
        assert callable(actions["collect_continue"])
