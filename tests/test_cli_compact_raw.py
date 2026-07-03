"""compact-raw CLI 배선 테스트.

저자: JunyoungJung
작성일: 2026-07-03
"""
from __future__ import annotations

from collections.abc import Callable
from typing import cast

import synapse_memory.cli as cli
from synapse_memory.wiki.compact import CompactSourceResult


def test_compact_raw_defaults_to_dry_run_and_wait_lock(monkeypatch, capsys) -> None:
    calls: list[dict[str, object]] = []

    def fake_compact(source: str, **kwargs: object) -> CompactSourceResult:
        calls.append({"source": source, **kwargs})
        return CompactSourceResult(source=source, dry_run=True, rehydrate=False, files_seen=1)

    def fake_locked(**kwargs: object) -> object:
        calls.append(
            {
                "lock_source": kwargs["source"],
                "mode": kwargs["mode"],
                "on_locked": kwargs["on_locked"],
            }
        )
        return cast(Callable[[], object], kwargs["operation"])()

    monkeypatch.setattr(cli, "compact_mirror_source", fake_compact)
    monkeypatch.setattr(cli, "run_with_ingest_lock", fake_locked)

    rc = cli.main(["compact-raw", "--source", "codex"])

    assert rc == 0
    assert {"lock_source": "codex", "mode": "compact", "on_locked": "wait"} in calls
    assert {"source": "codex", "apply": False, "rehydrate": False} in calls
    assert "dry-run" in capsys.readouterr().out


def test_compact_raw_apply_yes_passes_rehydrate(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_compact(source: str, **kwargs: object) -> CompactSourceResult:
        calls.append({"source": source, **kwargs})
        return CompactSourceResult(source=source, dry_run=False, rehydrate=True)

    monkeypatch.setattr(cli, "compact_mirror_source", fake_compact)
    def fake_locked(**kwargs: object) -> object:
        return cast(Callable[[], object], kwargs["operation"])()

    monkeypatch.setattr(cli, "run_with_ingest_lock", fake_locked)

    rc = cli.main(["compact-raw", "--source", "claude-code", "--rehydrate", "--apply", "--yes"])

    assert rc == 0
    assert calls == [{"source": "claude-code", "apply": True, "rehydrate": True}]
