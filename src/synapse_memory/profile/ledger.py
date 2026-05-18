"""profile 추출 ledger — multi-day cross-validation 으로 정확도 강화.

문제
----
단일 daily 호출의 LLM 결과를 그대로 candidate 화하면:
- 일시적 변덕 / 단기 작업이 안정 fact 로 둔갑
- LLM noise (같은 입력에도 흔들리는 출력) 가 그대로 통과
- confidence 가 단일 호출 판단값 → 며칠 연속 등장해도 누적되지 않음

해결
----
각 fact/pattern 의 fingerprint 별 등장 이력을 ``profile_ledger.jsonl`` 에 축적:
- ``seen_count``: 누적 등장 횟수
- ``first_seen`` / ``last_seen``: 등장 일자 범위
- ``confidence_history``: 각 호출 confidence (최대 30개)

promotion 조건 (둘 중 하나):
1. ``seen_count >= promotion_min_count`` (기본 3) 그리고 ``last_seen`` 이
   ``promotion_window_days`` (기본 14) 내 → 안정 패턴
2. 단일 호출 ``confidence >= fast_path_confidence`` (기본 0.95) → 즉시 promote
   (LLM 이 매우 확신하는 경우 cross-validation 우회)

한 번 promote 된 fact 는 ``promoted=true`` 마크 — 다시 candidate 로 노출 안 됨
(사용자가 vault 에 반영했든 dismiss 했든 그 후속은 vault/dismissed 가 책임).

저장 위치
--------
``<l0_root>/state/profile_ledger.jsonl`` — 라인당 한 entry, 매 호출마다 전체 rewrite.
사용자 직접 편집 대상 아님 (vault 밖). dismissed 와는 별도 — dismissed 는
"사용자 거부 신호", ledger 는 "추출 빈도 신호".

저자: Synapse Memory Maintainers
작성일: 2026-05-18
"""

from __future__ import annotations

import contextlib
import datetime
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from synapse_memory.profile.dedupe import _normalize
from synapse_memory.profile.schema import DecisionPattern, ProfileFact
from synapse_memory.storage.l0 import L0_FILE_MODE, ensure_secure_dir, l0_root

_LEDGER_SUBPATH = Path("state") / "profile_ledger.jsonl"
_VALID_KINDS: frozenset[str] = frozenset({"fact", "pattern"})


# ---------------------------------------------------------------------------
# 데이터
# ---------------------------------------------------------------------------


@dataclass
class LedgerEntry:
    kind: str  # "fact" | "pattern"
    fingerprint: str
    statements: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    first_seen: str = ""
    last_seen: str = ""
    seen_count: int = 0
    confidence_history: list[float] = field(default_factory=list)
    promoted: bool = False
    promoted_at: str = ""

    _MAX_STATEMENTS = 5
    _MAX_CONFIDENCE_HISTORY = 30

    def best_statement(self) -> str:
        """가장 최근 원문 (없으면 fingerprint)."""
        return self.statements[-1] if self.statements else self.fingerprint

    def aggregated_confidence(self) -> float:
        if not self.confidence_history:
            return 0.0
        return sum(self.confidence_history) / len(self.confidence_history)

    def peak_confidence(self) -> float:
        return max(self.confidence_history, default=0.0)

    def record(
        self, *, statement: str, confidence: float, category: str, today: str
    ) -> None:
        """오늘 호출에서 다시 등장 — 카운트/이력 갱신."""
        if not self.first_seen:
            self.first_seen = today
        self.last_seen = today
        self.seen_count += 1
        self.confidence_history.append(max(0.0, min(1.0, confidence)))
        if len(self.confidence_history) > self._MAX_CONFIDENCE_HISTORY:
            del self.confidence_history[
                : len(self.confidence_history) - self._MAX_CONFIDENCE_HISTORY
            ]
        stmt = statement.strip()
        if stmt and stmt not in self.statements:
            self.statements.append(stmt)
            if len(self.statements) > self._MAX_STATEMENTS:
                del self.statements[: len(self.statements) - self._MAX_STATEMENTS]
        if category and self.kind == "fact" and category not in self.categories:
            self.categories.append(category)

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "fingerprint": self.fingerprint,
            "statements": list(self.statements),
            "categories": list(self.categories),
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "seen_count": self.seen_count,
            "confidence_history": list(self.confidence_history),
            "promoted": self.promoted,
            "promoted_at": self.promoted_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> LedgerEntry | None:
        kind = raw.get("kind")
        fingerprint = raw.get("fingerprint")
        if kind not in _VALID_KINDS:
            return None
        if not isinstance(fingerprint, str) or not fingerprint:
            return None
        statements = raw.get("statements") or []
        categories = raw.get("categories") or []
        confidence_history = raw.get("confidence_history") or []
        if not isinstance(statements, list):
            statements = []
        if not isinstance(categories, list):
            categories = []
        if not isinstance(confidence_history, list):
            confidence_history = []
        raw_seen = raw.get("seen_count", 0)
        seen_count = int(raw_seen) if isinstance(raw_seen, (int, float, str)) else 0
        return cls(
            kind=kind,
            fingerprint=fingerprint,
            statements=[str(s) for s in statements if isinstance(s, str)],
            categories=[str(c) for c in categories if isinstance(c, str)],
            first_seen=str(raw.get("first_seen", "")),
            last_seen=str(raw.get("last_seen", "")),
            seen_count=seen_count,
            confidence_history=[
                float(c) for c in confidence_history if isinstance(c, (int, float))
            ],
            promoted=bool(raw.get("promoted", False)),
            promoted_at=str(raw.get("promoted_at", "")),
        )


# ---------------------------------------------------------------------------
# 경로 / load / save
# ---------------------------------------------------------------------------


def ledger_path() -> Path:
    return l0_root() / _LEDGER_SUBPATH


def _ledger_key(kind: str, fingerprint: str) -> str:
    return f"{kind}::{fingerprint}"


def load_ledger(path: Path | None = None) -> dict[str, LedgerEntry]:
    """ledger 파일 → ``{(kind, fingerprint) key: entry}``. 없으면 빈 dict."""
    target = path or ledger_path()
    if not target.is_file():
        return {}
    entries: dict[str, LedgerEntry] = {}
    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        return {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        entry = LedgerEntry.from_dict(obj)
        if entry is None:
            continue
        entries[_ledger_key(entry.kind, entry.fingerprint)] = entry
    return entries


def save_ledger(ledger: dict[str, LedgerEntry], path: Path | None = None) -> Path:
    """전체 rewrite (atomic via temp + rename). 정렬: kind, fingerprint."""
    target = path or ledger_path()
    ensure_secure_dir(target.parent)
    sorted_entries = sorted(
        ledger.values(), key=lambda e: (e.kind, e.fingerprint)
    )
    tmp = target.with_suffix(target.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for entry in sorted_entries:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    with contextlib.suppress(OSError):
        os.chmod(tmp, L0_FILE_MODE)
    os.replace(tmp, target)
    return target


# ---------------------------------------------------------------------------
# record / promote
# ---------------------------------------------------------------------------


def record_extraction(
    ledger: dict[str, LedgerEntry],
    facts: list[ProfileFact],
    patterns: list[DecisionPattern],
    *,
    today: datetime.date | None = None,
) -> dict[str, LedgerEntry]:
    """오늘 추출 결과를 ledger 에 누적. 입력 ledger 를 mutate + 반환."""
    today_str = (today or datetime.date.today()).isoformat()

    for f in facts:
        fp = _normalize(f.statement)
        if not fp:
            continue
        key = _ledger_key("fact", fp)
        entry = ledger.get(key)
        if entry is None:
            entry = LedgerEntry(kind="fact", fingerprint=fp)
            ledger[key] = entry
        entry.record(
            statement=f.statement,
            confidence=f.confidence,
            category=f.category,
            today=today_str,
        )

    for p in patterns:
        fp = _normalize(p.trigger)
        if not fp:
            continue
        key = _ledger_key("pattern", fp)
        entry = ledger.get(key)
        if entry is None:
            entry = LedgerEntry(kind="pattern", fingerprint=fp)
            ledger[key] = entry
        entry.record(
            statement=p.trigger,
            confidence=p.confidence,
            category="",
            today=today_str,
        )

    return ledger


@dataclass(frozen=True)
class PromotionReport:
    promoted_fact_count: int
    promoted_pattern_count: int
    awaiting_fact_count: int
    awaiting_pattern_count: int

    def summary(self) -> str:
        return (
            f"promoted fact={self.promoted_fact_count} "
            f"pattern={self.promoted_pattern_count} | "
            f"awaiting fact={self.awaiting_fact_count} "
            f"pattern={self.awaiting_pattern_count}"
        )


def _within_window(last_seen: str, today: datetime.date, window_days: int) -> bool:
    if not last_seen:
        return False
    try:
        d = datetime.date.fromisoformat(last_seen)
    except ValueError:
        return False
    return 0 <= (today - d).days <= window_days


def promote_candidates(
    ledger: dict[str, LedgerEntry],
    *,
    facts_input: list[ProfileFact],
    patterns_input: list[DecisionPattern],
    min_count: int,
    window_days: int,
    fast_path_confidence: float,
    today: datetime.date | None = None,
) -> tuple[list[ProfileFact], list[DecisionPattern], PromotionReport]:
    """promotion 조건 충족 entry → (fact, pattern, report) 반환.

    promotion 조건 (둘 중 하나):
        - ``seen_count >= min_count`` AND ``last_seen`` 이 ``window_days`` 내
        - 또는 오늘 호출 confidence 가 ``fast_path_confidence`` 이상

    이미 ``promoted=True`` 인 entry 는 skip (재노출 방지).
    """
    today_d = today or datetime.date.today()

    today_fact_conf: dict[str, float] = {}
    for f in facts_input:
        fp = _normalize(f.statement)
        if fp:
            today_fact_conf[fp] = max(today_fact_conf.get(fp, 0.0), f.confidence)
    today_pattern_conf: dict[str, float] = {}
    for p in patterns_input:
        fp = _normalize(p.trigger)
        if fp:
            today_pattern_conf[fp] = max(today_pattern_conf.get(fp, 0.0), p.confidence)

    promoted_facts: list[ProfileFact] = []
    promoted_patterns: list[DecisionPattern] = []
    awaiting_facts = 0
    awaiting_patterns = 0

    for entry in ledger.values():
        if entry.promoted:
            continue
        in_window = _within_window(entry.last_seen, today_d, window_days)
        repeated = entry.seen_count >= min_count and in_window
        today_conf = (
            today_fact_conf.get(entry.fingerprint, 0.0)
            if entry.kind == "fact"
            else today_pattern_conf.get(entry.fingerprint, 0.0)
        )
        fast_path = today_conf >= fast_path_confidence

        if not (repeated or fast_path):
            if entry.kind == "fact":
                awaiting_facts += 1
            else:
                awaiting_patterns += 1
            continue

        if entry.kind == "fact":
            promoted_facts.append(
                ProfileFact(
                    category=entry.categories[-1] if entry.categories else "preference",
                    statement=entry.best_statement(),
                    confidence=entry.peak_confidence(),
                    source_ids=["ledger"],
                    extracted_at=entry.last_seen,
                )
            )
        else:
            promoted_patterns.append(
                DecisionPattern(
                    trigger=entry.best_statement(),
                    action="",
                    rationale="",
                    confidence=entry.peak_confidence(),
                    examples=["ledger"],
                    extracted_at=entry.last_seen,
                )
            )

    return (
        promoted_facts,
        promoted_patterns,
        PromotionReport(
            promoted_fact_count=len(promoted_facts),
            promoted_pattern_count=len(promoted_patterns),
            awaiting_fact_count=awaiting_facts,
            awaiting_pattern_count=awaiting_patterns,
        ),
    )


def mark_promoted(
    ledger: dict[str, LedgerEntry],
    promoted_facts: list[ProfileFact],
    promoted_patterns: list[DecisionPattern],
    *,
    today: datetime.date | None = None,
) -> dict[str, LedgerEntry]:
    """promote 된 entry 를 ``promoted=True`` 로 마크. 입력 ledger mutate."""
    today_str = (today or datetime.date.today()).isoformat()
    for f in promoted_facts:
        key = _ledger_key("fact", _normalize(f.statement))
        entry = ledger.get(key)
        if entry is not None and not entry.promoted:
            entry.promoted = True
            entry.promoted_at = today_str
    for p in promoted_patterns:
        key = _ledger_key("pattern", _normalize(p.trigger))
        entry = ledger.get(key)
        if entry is not None and not entry.promoted:
            entry.promoted = True
            entry.promoted_at = today_str
    return ledger


def enrich_promoted_patterns(
    promoted: list[DecisionPattern],
    today_patterns: list[DecisionPattern],
) -> list[DecisionPattern]:
    """promote 된 pattern 의 action/rationale 을 오늘 호출 결과로 보강.

    ledger 는 trigger fingerprint 만 추적하고 action/rationale 은 LLM 매번 변동.
    오늘 호출에 같은 trigger 가 있으면 그 action/rationale 사용.
    """
    today_by_trigger: dict[str, DecisionPattern] = {
        _normalize(p.trigger): p for p in today_patterns if _normalize(p.trigger)
    }
    enriched: list[DecisionPattern] = []
    for p in promoted:
        fp = _normalize(p.trigger)
        match = today_by_trigger.get(fp)
        if match is None:
            enriched.append(p)
            continue
        enriched.append(
            DecisionPattern(
                trigger=p.trigger,
                action=match.action,
                rationale=match.rationale,
                confidence=p.confidence,
                examples=match.examples or p.examples,
                extracted_at=p.extracted_at,
            )
        )
    return enriched
