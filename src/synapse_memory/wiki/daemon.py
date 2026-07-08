# src/synapse_memory/wiki/daemon.py
"""watch 사이클 — launchd가 변화 시 1회 호출하는 짧은 통합 루프.

단일 동시성 락을 잡고, settled(유휴) 필터를 건 ingest를 1회 돌린다. 이미 다른
사이클이 실행 중이면(=락 보유) skip한다. 핵심 로직은 순수/주입 가능 —
``ingest_source``는 모듈 레벨 심볼이라 테스트가 monkeypatch할 수 있다.

저자: Synapse Memory Maintainers
작성일: 2026-06-15
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from synapse_memory.config import get_config
from synapse_memory.wiki.ingest import ingest_source
from synapse_memory.wiki.lock import LockedOutcome, default_lock_path, run_with_ingest_lock

# 분 → 초.
SECONDS_PER_MINUTE = 60


@dataclass
class CycleOutcome:
    """watch 사이클 결과."""

    ran: bool
    skipped_reason: str | None = None
    result: object | None = None


def run_watch_cycle(
    *,
    source: str = "claude-code",
    lock_path: Path | None = None,
    idle_minutes: int | None = None,
    vault_path: Path | None = None,
) -> CycleOutcome:
    """락 아래 settled-필터 ingest를 1회 실행. 이미 실행 중이면 skip.

    idle_minutes 미지정 시 ``config.maintenance.idle_minutes``를 사용한다.
    """
    cfg = get_config().maintenance
    if idle_minutes is None:
        idle_minutes = cfg.idle_minutes
    if lock_path is None:
        lock_path = default_lock_path(source)
    # 020: bounded 단명 사이클 — limit로 메모리 천장, checkpoint_each로 doc별
    # watermark 저장(중단/kill돼도 다음 사이클이 이어서 = 재처리 악순환 차단).
    outcome = run_with_ingest_lock(
        source=source,
        mode="watch",
        on_locked="skip",
        lock_path=lock_path,
        operation=lambda: ingest_source(
            source,
            min_age_seconds=idle_minutes * SECONDS_PER_MINUTE,
            vault_path=vault_path,
            limit=cfg.max_docs_per_cycle,
            checkpoint_each=True,
        ),
    )
    if isinstance(outcome, LockedOutcome):
        return CycleOutcome(ran=False, skipped_reason=outcome.reason)
    return CycleOutcome(ran=True, skipped_reason=None, result=outcome)
