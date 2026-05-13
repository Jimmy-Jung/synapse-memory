"""월 비용 한도 가드.

``config.cost.monthly_cap_usd``와 현재 월(UTC) 누적 USD를 비교해
ask/me 계열 호출을 *사전 차단*한다.

우회: ``SYNAPSE_FORCE_COST=1`` 환경변수.

저자: JunyoungJung
작성일: 2026-05-13
"""

from __future__ import annotations

import datetime
import os
import sys
from dataclasses import dataclass

from synapse_memory.cost.events import load_cost_events

CAP_EXCEEDED_EXIT_CODE = 7
WARN_THRESHOLD_RATIO = 0.8
FORCE_ENV_VAR = "SYNAPSE_FORCE_COST"


@dataclass(frozen=True)
class CapStatus:
    """월 cap vs 누적 — 진단용 스냅샷."""

    cap_usd: float | None
    month_to_date_usd: float

    @property
    def over_cap(self) -> bool:
        return self.cap_usd is not None and self.month_to_date_usd >= self.cap_usd

    @property
    def usage_ratio(self) -> float:
        if not self.cap_usd:
            return 0.0
        return self.month_to_date_usd / self.cap_usd

    @property
    def remaining_usd(self) -> float:
        if self.cap_usd is None:
            return float("inf")
        return max(0.0, self.cap_usd - self.month_to_date_usd)


def _month_window(
    now: datetime.datetime,
) -> tuple[datetime.datetime, datetime.datetime]:
    """UTC 기준 이번 달 시작 ~ 다음 달 시작 (exclusive)."""
    utc = datetime.UTC
    start = datetime.datetime(now.year, now.month, 1, tzinfo=utc)
    if now.month == 12:
        next_start = datetime.datetime(now.year + 1, 1, 1, tzinfo=utc)
    else:
        next_start = datetime.datetime(now.year, now.month + 1, 1, tzinfo=utc)
    return start, next_start


def compute_month_to_date_usd(
    *, now: datetime.datetime | None = None
) -> float:
    """이번 월(UTC) 누적 USD 합산. cost.jsonl 없거나 비어 있으면 0.0."""
    now = now or datetime.datetime.now(datetime.UTC)
    start, end = _month_window(now)
    total = 0.0
    try:
        events = load_cost_events()
    except Exception:
        return 0.0
    for ev in events:
        try:
            ts = datetime.datetime.fromisoformat(ev.ts.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=datetime.UTC)
        if start <= ts < end:
            total += float(ev.usd)
    return total


def get_cap_status(*, now: datetime.datetime | None = None) -> CapStatus:
    """현재 cap과 누적 비교 — 핸들러·assistant·doctor에서 공통 사용."""
    cap_usd: float | None
    try:
        from synapse_memory.config import get_config

        cap_usd = get_config().cost.monthly_cap_usd
    except Exception:
        cap_usd = None
    mtd = compute_month_to_date_usd(now=now)
    return CapStatus(cap_usd=cap_usd, month_to_date_usd=mtd)


def enforce_cost_cap(command: str) -> None:
    """호출 직전 cap 검사 + 80% 도달 시 warn.

    동작:
    - cap=null → 즉시 반환 (제한 없음)
    - 누적 ≥ cap → ``SYNAPSE_FORCE_COST=1`` 없으면 SystemExit(7)
    - 누적 ≥ 80% of cap → stderr 경고만 (진행은 허용)
    """
    status = get_cap_status()
    if status.cap_usd is None:
        return

    if status.over_cap:
        if os.environ.get(FORCE_ENV_VAR):
            sys.stderr.write(
                f"⚠ 월 cap ${status.cap_usd:.2f} 초과 — "
                f"{FORCE_ENV_VAR}=1로 진행 ({command})\n"
            )
            sys.stderr.flush()
            return
        sys.stderr.write(
            f"✗ 월 cap 초과 — 진행 거부 ({command})\n"
            f"   cap:   ${status.cap_usd:.2f}\n"
            f"   누적:  ${status.month_to_date_usd:.2f}\n"
            f"   계속하려면:\n"
            f"     - 일시 우회: {FORCE_ENV_VAR}=1 synapse-memory {command} ...\n"
            f"     - cap 변경: synapse-memory config set "
            f"cost.monthly_cap_usd <새 한도>\n"
            f"     - cap 제거: synapse-memory config set "
            f"cost.monthly_cap_usd none\n"
        )
        sys.stderr.flush()
        raise SystemExit(CAP_EXCEEDED_EXIT_CODE)

    if status.usage_ratio >= WARN_THRESHOLD_RATIO:
        sys.stderr.write(
            f"⚠ 월 cap 사용량 {status.usage_ratio:.0%} "
            f"(${status.month_to_date_usd:.2f}/${status.cap_usd:.2f})\n"
        )
        sys.stderr.flush()
