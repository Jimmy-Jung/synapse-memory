"""wiki profile page 기반 후보 dedupe.

목적
----
``update_profile`` stage 가 매일 같은 fact/pattern 후보를 만들어 사용자에게
중복 질문하는 비효율 제거. extract 결과를 vault 진실원본과 비교해 이미
적용된 항목은 candidate 에서 떨어낸다.

dedupe 정책
-----------
1. **정확 매치** — 정규화(소문자·공백 collapse·trailing punctuation strip) 후
   기존 statement 와 동일하면 중복.
2. **토큰 Jaccard ≥ 0.75** — 정규화 후 whitespace split 토큰 집합 비교. 한국어
   어순/조사 변형을 어느 정도 흡수.

DecisionPattern 은 ``trigger`` 기준으로 비교 (action 은 자유롭게 바뀔 수 있으므로
trigger 동일 = 같은 결정 상황).

저자: Synapse Memory Maintainers
작성일: 2026-05-18
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from synapse_memory.profile.schema import PROFILE_CATEGORIES, DecisionPattern, ProfileFact
from synapse_memory.profile.similarity import (
    jaccard as _jaccard,
    normalize as _normalize,
    token_set as _token_set,
)

_JACCARD_THRESHOLD = 0.75


# ---------------------------------------------------------------------------
def _is_duplicate(
    candidate: str,
    existing_norm: set[str],
    existing_tokens: list[frozenset[str]],
    *,
    threshold: float = _JACCARD_THRESHOLD,
) -> bool:
    norm = _normalize(candidate)
    if not norm:
        return False
    if norm in existing_norm:
        return True
    cand_tokens = _token_set(candidate)
    if not cand_tokens:
        return False
    return any(_jaccard(cand_tokens, ex) >= threshold for ex in existing_tokens)


# ---------------------------------------------------------------------------
# vault 파싱
# ---------------------------------------------------------------------------

_PROFILE_FRONTMATTER_PATTERN = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.DOTALL)
_H2_RE = re.compile(r"^##\s+(.+?)\s*$")
_H3_RE = re.compile(r"^###\s+(.+?)\s*$")
_BULLET_RE = re.compile(r"^\s*[-*]\s+(.+?)\s*$")
_CONFIDENCE_PREFIX_RE = re.compile(r"^\[[0-9.]+\]\s*")


def _strip_frontmatter(text: str) -> str:
    return _PROFILE_FRONTMATTER_PATTERN.sub("", text, count=1)


def parse_profile_facts(path: Path) -> list[str]:
    """wiki profile page → ProfileFact bullet statement 평탄화.

    legacy flat Profile.md 도 같은 markdown 구조면 파싱된다. Step 8c 이후 호출자는
    canonical ``Profile/user-profile.md`` 를 넘긴다.
    """
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    body = _strip_frontmatter(text)

    facts: list[str] = []
    in_decision = False
    in_category = False
    for raw_line in body.splitlines():
        h2 = _H2_RE.match(raw_line)
        if h2:
            label = h2.group(1).strip()
            normalized = _normalize(label)
            in_decision = normalized.startswith("decision patterns")
            if normalized.startswith("profile facts"):
                in_category = False
                continue
            in_category = not in_decision
            continue
        h3 = _H3_RE.match(raw_line)
        if h3:
            label = h3.group(1).strip()
            in_category = not in_decision and (
                label in PROFILE_CATEGORIES or in_category
            )
            continue
        if raw_line.startswith("# "):
            in_category = False
            in_decision = False
            continue
        if not in_category:
            continue
        m = _BULLET_RE.match(raw_line)
        if m:
            statement = _CONFIDENCE_PREFIX_RE.sub("", m.group(1).strip()).strip()
            if statement:
                facts.append(statement)
    return facts


def parse_decision_pattern_triggers(path: Path) -> list[str]:
    """wiki profile page → decision pattern ``### {trigger}`` 목록.

    legacy flat DecisionPatterns.md 도 ``## Approved Patterns`` 구조면 파싱된다.
    """
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    body = _strip_frontmatter(text)

    triggers: list[str] = []
    in_approved = False
    for raw_line in body.splitlines():
        h2 = _H2_RE.match(raw_line)
        if h2:
            label = _normalize(h2.group(1))
            in_approved = label == "approved patterns" or label.startswith(
                "decision patterns"
            )
            continue
        if not in_approved:
            continue
        h3 = _H3_RE.match(raw_line)
        if h3:
            triggers.append(h3.group(1).strip())
    return triggers


# ---------------------------------------------------------------------------
# dedupe
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DedupeReport:
    facts_kept: int
    facts_dropped: int
    patterns_kept: int
    patterns_dropped: int

    @property
    def total_dropped(self) -> int:
        return self.facts_dropped + self.patterns_dropped

    def summary(self) -> str:
        return (
            f"kept fact={self.facts_kept} pattern={self.patterns_kept} | "
            f"dropped fact={self.facts_dropped} pattern={self.patterns_dropped}"
        )


def dedupe_against_vault(
    facts: list[ProfileFact],
    patterns: list[DecisionPattern],
    *,
    profile_path: Path,
    decision_patterns_path: Path,
    dismissed_facts: frozenset[str] | set[str] | None = None,
    dismissed_patterns: frozenset[str] | set[str] | None = None,
) -> tuple[list[ProfileFact], list[DecisionPattern], DedupeReport]:
    """vault 진실원본 + dismissed 인덱스 기준으로 신규만 남김.

    Args:
        facts: extract_profile_facts 결과
        patterns: extract_decision_patterns 결과
        profile_path: vault Profile.md 절대 경로
        decision_patterns_path: vault DecisionPatterns.md 절대 경로
        dismissed_facts: 사용자가 No 답해 dismissed 된 fact fingerprint set
            (정규화된 statement). ``profile.dismissed`` 모듈의 ``load_dismissed`` 결과
            ``DismissedIndex.facts`` 를 그대로 넘길 수 있다.
        dismissed_patterns: 동일 형식, pattern trigger 용.

    Returns:
        (신규 facts, 신규 patterns, 통계)
    """
    existing_fact_statements = parse_profile_facts(profile_path)
    existing_pattern_triggers = parse_decision_pattern_triggers(
        decision_patterns_path
    )

    fact_norm = {_normalize(s) for s in existing_fact_statements}
    fact_tokens = [_token_set(s) for s in existing_fact_statements]
    trigger_norm = {_normalize(t) for t in existing_pattern_triggers}
    trigger_tokens = [_token_set(t) for t in existing_pattern_triggers]

    # dismissed 합치기 — vault 항목과 동일하게 정확 매치 + Jaccard 비교.
    if dismissed_facts:
        for fp in dismissed_facts:
            if fp:
                fact_norm.add(fp)
                fact_tokens.append(frozenset(fp.split()))
    if dismissed_patterns:
        for fp in dismissed_patterns:
            if fp:
                trigger_norm.add(fp)
                trigger_tokens.append(frozenset(fp.split()))

    new_facts: list[ProfileFact] = []
    dropped_facts = 0
    seen_within_batch_facts: set[str] = set()
    for f in facts:
        norm = _normalize(f.statement)
        if not norm:
            dropped_facts += 1
            continue
        if norm in seen_within_batch_facts:
            dropped_facts += 1
            continue
        if _is_duplicate(f.statement, fact_norm, fact_tokens):
            dropped_facts += 1
            continue
        seen_within_batch_facts.add(norm)
        new_facts.append(f)

    new_patterns: list[DecisionPattern] = []
    dropped_patterns = 0
    seen_within_batch_triggers: set[str] = set()
    for p in patterns:
        norm = _normalize(p.trigger)
        if not norm:
            dropped_patterns += 1
            continue
        if norm in seen_within_batch_triggers:
            dropped_patterns += 1
            continue
        if _is_duplicate(p.trigger, trigger_norm, trigger_tokens):
            dropped_patterns += 1
            continue
        seen_within_batch_triggers.add(norm)
        new_patterns.append(p)

    report = DedupeReport(
        facts_kept=len(new_facts),
        facts_dropped=dropped_facts,
        patterns_kept=len(new_patterns),
        patterns_dropped=dropped_patterns,
    )
    return new_facts, new_patterns, report
