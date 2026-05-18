"""사용자가 거부한 fact/pattern 영구 기록 + 성향 변경 시 해제.

저장 위치
--------
``<vault>/90_System/AI/MemoryInbox/_dismissed.jsonl``

vault 안에 두는 이유:
- 사용자가 Obsidian / 텍스트 에디터로 **직접 라인을 삭제**하면 다음 daily 에서
  자동으로 다시 후보로 등장 → "성향 바뀜" 시나리오를 명시적 액션 1개로 해결
- iCloud 등 vault sync 경로를 그대로 활용

자동 해제
--------
``ProfileConfig.dismissed_ttl_days`` (기본 90) 일이 지난 라인은 dedupe 시 무시.
0 이면 영구 dismiss. 만료된 라인을 물리적으로 삭제하지는 않음 — 사용자가
이력을 보존하고 싶을 수 있으니 압축은 별도 옵션으로.

라인 포맷 (한 줄 JSON)
---------------------
``{"kind":"fact"|"pattern","fingerprint":"<normalized>","original":"<원문>",
"dismissed_at":"YYYY-MM-DD"}``

저자: Synapse Memory Maintainers
작성일: 2026-05-18
"""

from __future__ import annotations

import datetime
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from synapse_memory.collectors.obsidian.mirror import get_vault_path
from synapse_memory.config import get_config
from synapse_memory.profile.dedupe import _normalize

DismissKind = Literal["fact", "pattern"]
DismissReason = Literal[
    "",               # 미상 (구 라인 호환 또는 CLI --reason 미지정)
    "one_time",       # 1회성 작업 — 진짜 성향 아님
    "misclassified",  # LLM 오추출 — 사실 자체가 틀림
    "user_changed",   # 사용자 성향이 바뀜 — 과거엔 맞았으나 지금 아님
    "irrelevant",     # 후보로 등장할 가치 없음 — 추출 자체가 noise
    "other",          # 기타 (자유 텍스트 — note 필드)
]
VALID_REASONS: frozenset[str] = frozenset(
    {"", "one_time", "misclassified", "user_changed", "irrelevant", "other"}
)
_DISMISSED_FILENAME = "_dismissed.jsonl"
_VALID_KINDS: frozenset[str] = frozenset({"fact", "pattern"})


# ---------------------------------------------------------------------------
# 경로
# ---------------------------------------------------------------------------


def dismissed_path(vault_path: Path | None = None) -> Path:
    """vault 내 dismissed 파일 절대 경로."""
    vault = (vault_path or get_vault_path()).expanduser().resolve()
    inbox = vault / get_config().vault_folders.system.ai.memory_inbox
    return inbox / _DISMISSED_FILENAME


# ---------------------------------------------------------------------------
# 데이터
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DismissedRecord:
    kind: DismissKind
    fingerprint: str
    original: str
    dismissed_at: str  # YYYY-MM-DD
    reason: str = ""   # DismissReason 중 하나 (구 라인은 빈 문자열)
    note: str = ""     # 자유 텍스트 — reason="other" 일 때 사용자 메모

    def to_dict(self) -> dict[str, str]:
        out: dict[str, str] = {
            "kind": self.kind,
            "fingerprint": self.fingerprint,
            "original": self.original,
            "dismissed_at": self.dismissed_at,
        }
        # reason / note 는 비어있으면 생략 — 구 라인 포맷과 동일하게 유지.
        if self.reason:
            out["reason"] = self.reason
        if self.note:
            out["note"] = self.note
        return out

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> DismissedRecord | None:
        kind = raw.get("kind")
        if kind not in _VALID_KINDS:
            return None
        fingerprint = raw.get("fingerprint")
        original = raw.get("original", "")
        dismissed_at = raw.get("dismissed_at", "")
        reason = raw.get("reason", "")
        note = raw.get("note", "")
        if not isinstance(fingerprint, str) or not fingerprint:
            return None
        if not isinstance(original, str):
            original = ""
        if not isinstance(dismissed_at, str):
            dismissed_at = ""
        if not isinstance(reason, str) or reason not in VALID_REASONS:
            reason = ""
        if not isinstance(note, str):
            note = ""
        return cls(
            kind=kind,  # type: ignore[arg-type]
            fingerprint=fingerprint,
            original=original,
            dismissed_at=dismissed_at,
            reason=reason,
            note=note,
        )


@dataclass(frozen=True)
class DismissedIndex:
    """dedupe 단계에 넘기는 즉시 사용 가능한 fingerprint set."""

    facts: frozenset[str]
    patterns: frozenset[str]
    expired_count: int  # TTL 만료로 무시된 라인 수 (관찰성)
    # reason 별 facts/patterns — extract prompt 의 강한 negative example 분류용.
    # 키는 ``DismissReason`` 중 하나. 빈 dict 면 기존 동작과 동일.
    facts_by_reason: dict[str, frozenset[str]] = field(default_factory=dict)
    patterns_by_reason: dict[str, frozenset[str]] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return len(self.facts) + len(self.patterns)

    def strong_facts(self) -> frozenset[str]:
        """LLM 이 절대 재출력 하면 안 되는 fact fingerprint — misclassified+irrelevant."""
        return (
            self.facts_by_reason.get("misclassified", frozenset())
            | self.facts_by_reason.get("irrelevant", frozenset())
        )

    def strong_patterns(self) -> frozenset[str]:
        return (
            self.patterns_by_reason.get("misclassified", frozenset())
            | self.patterns_by_reason.get("irrelevant", frozenset())
        )


# ---------------------------------------------------------------------------
# load
# ---------------------------------------------------------------------------


def _parse_date(value: str) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _ttl_for(
    reason: str,
    default: int,
    overrides: dict[str, int] | None,
) -> int:
    """reason 별 TTL 결정.

    overrides 에 키가 있으면 그 값, 없으면 default. ``one_time``, ``user_changed``,
    ``misclassified``, ``irrelevant`` 만 차등 의미가 있고, ``other``/``""`` 는 항상
    default 로 떨어진다 (정보 부족 → 보수적 기본).
    """
    if not overrides:
        return default
    if reason in ("", "other"):
        return default
    return overrides.get(reason, default)


def profile_to_ttl_overrides(profile_cfg: object) -> dict[str, int]:
    """ProfileConfig → reason 별 TTL dict. 호출 측에서 한 번 빌드해 재사용 권장.

    의도적으로 ``ProfileConfig`` 타입 import 를 피해 순환 의존을 줄였다.
    누락 필드는 default 로 폴백 — backward compat.
    """
    out: dict[str, int] = {}
    for reason, attr in (
        ("user_changed", "dismissed_ttl_user_changed"),
        ("misclassified", "dismissed_ttl_misclassified"),
        ("one_time", "dismissed_ttl_one_time"),
        ("irrelevant", "dismissed_ttl_irrelevant"),
    ):
        v = getattr(profile_cfg, attr, None)
        if isinstance(v, int) and v >= 0:
            out[reason] = v
    return out


def load_dismissed(
    path: Path | None = None,
    *,
    ttl_days: int | None = None,
    ttl_overrides: dict[str, int] | None = None,
    today: datetime.date | None = None,
) -> DismissedIndex:
    """dismissed 파일 → 만료되지 않은 fingerprint set.

    Args:
        path: dismissed 파일. None 이면 vault 기본 경로.
        ttl_days: 기본 만료 일수 (reason="" / "other" / unknown 에 적용).
            None 이면 ``ProfileConfig.dismissed_ttl_days``. 0 이면 영구 dismiss.
        ttl_overrides: ``{reason: ttl}`` 매핑. 라인의 reason 이 키에 있으면
            override 값이 사용됨. 없거나 키 없음 → ``ttl_days`` 폴백.
        today: 기준 날짜. 테스트 override 용.

    파일 없거나 비어있으면 빈 인덱스. 잘못된 라인은 silent skip.
    """
    target = path or dismissed_path()
    if not target.is_file():
        return DismissedIndex(frozenset(), frozenset(), 0)

    cfg = None
    if ttl_days is None or ttl_overrides is None:
        cfg = get_config().profile
        if ttl_days is None:
            ttl_days = cfg.dismissed_ttl_days
        if ttl_overrides is None:
            ttl_overrides = profile_to_ttl_overrides(cfg)
    today = today or datetime.date.today()

    fact_set: set[str] = set()
    pattern_set: set[str] = set()
    fact_by_reason: dict[str, set[str]] = {}
    pattern_by_reason: dict[str, set[str]] = {}
    expired = 0

    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        return DismissedIndex(frozenset(), frozenset(), 0)

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(raw, dict):
            continue
        record = DismissedRecord.from_dict(raw)
        if record is None:
            continue
        effective_ttl = _ttl_for(record.reason, ttl_days, ttl_overrides)
        if effective_ttl > 0:
            d = _parse_date(record.dismissed_at)
            if d is not None and (today - d).days > effective_ttl:
                expired += 1
                continue
        if record.kind == "fact":
            fact_set.add(record.fingerprint)
            fact_by_reason.setdefault(record.reason, set()).add(record.fingerprint)
        else:
            pattern_set.add(record.fingerprint)
            pattern_by_reason.setdefault(record.reason, set()).add(record.fingerprint)

    return DismissedIndex(
        facts=frozenset(fact_set),
        patterns=frozenset(pattern_set),
        expired_count=expired,
        facts_by_reason={r: frozenset(v) for r, v in fact_by_reason.items()},
        patterns_by_reason={r: frozenset(v) for r, v in pattern_by_reason.items()},
    )


# ---------------------------------------------------------------------------
# append
# ---------------------------------------------------------------------------


def append_dismissed(
    kind: DismissKind,
    original: str,
    *,
    reason: str = "",
    note: str = "",
    path: Path | None = None,
    today: datetime.date | None = None,
) -> DismissedRecord | None:
    """사용자 No 답을 한 줄 append. 같은 fingerprint 가 이미 있으면 멱등.

    Args:
        reason: ``DismissReason`` 중 하나. 빈 문자열이면 미상.
        note: ``reason="other"`` 일 때 자유 텍스트 메모.

    빈 ``original`` 은 skip (None 반환).
    """
    if kind not in _VALID_KINDS:
        raise ValueError(f"kind는 fact|pattern — 현재: {kind!r}")
    if reason and reason not in VALID_REASONS:
        raise ValueError(
            f"reason 은 {sorted(VALID_REASONS - {''})} 중 하나 — 현재: {reason!r}"
        )

    fingerprint = _normalize(original)
    if not fingerprint:
        return None

    target = path or dismissed_path()
    today = today or datetime.date.today()

    # 멱등 체크: 같은 (kind, fingerprint) 가 이미 있으면 append 안 함 (TTL 무시).
    # reason 이 새로 들어와도 첫 라인의 reason 을 보존 — 사용자 첫 판단 존중.
    existing = load_dismissed(target, ttl_days=0, today=today)
    pool = existing.facts if kind == "fact" else existing.patterns
    if fingerprint in pool:
        return None

    record = DismissedRecord(
        kind=kind,
        fingerprint=fingerprint,
        original=original.strip(),
        dismissed_at=today.isoformat(),
        reason=reason,
        note=note,
    )

    target.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record.to_dict(), ensure_ascii=False) + "\n"

    # O_APPEND 로 다중 프로세스 동시 No 답 시 라인 섞임 방지.
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)

    return record
