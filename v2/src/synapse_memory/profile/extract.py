"""raw → ProfileFact / DecisionPattern 추출 (Claude).

데이터 소스: L0 raw/claude-code/history.jsonl (사용자 명령 패턴 가장 풍부)

흐름::

    history.jsonl 마지막 N entry → redact_full → Claude → JSON → ProfileFact 리스트
    → MemoryInbox/Profile-YYYY-MM-DD.md에 저장 (사용자 승인 후 vault 진실원본)

저자: JunyoungJung <joony300@gmail.com>
작성일: 2026-05-10
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

from synapse_memory.collectors.obsidian.mirror import get_vault_path
from synapse_memory.llm import claude as claude_api
from synapse_memory.llm.apfel import ApfelEnvironment
from synapse_memory.llm.claude import ClaudeEnvironment, ClaudeError
from synapse_memory.profile.schema import (
    PROFILE_CATEGORIES,
    DecisionPattern,
    ProfileFact,
)
from synapse_memory.redaction import redact_full
from synapse_memory.storage.l0 import l0_root

DEFAULT_SAMPLE_LINES = 200       # history.jsonl 마지막 N 줄
DEFAULT_MODEL = "sonnet"
DEFAULT_TIMEOUT = 240
MEMORY_INBOX_SUBPATH = Path("90_System") / "AI" / "MemoryInbox"

PROFILE_SYSTEM = """당신은 사용자의 raw 활동 데이터에서 **안정적 성향 사실**을 추출하는 분석가입니다.

# 임무
사용자 입력 history(슬래시 명령, 자연어 질의)에서 **반복 패턴**으로 드러나는 성향을 추출.
1회성 변덕·일시적 작업은 제외.

# 카테고리 (이것 중 하나로 분류)
- work_style: 작업 방식 (예: "단계별 의사코드 후 코드 작성")
- preference: 선호 (예: "한국어 응답", "간결한 출력")
- strength: 강점 (예: "iOS 아키텍처 설계 능숙")
- weakness: 약점 / 의도적 회피
- tech: 기술 스택·도구 (예: "Swift+SwiftUI 주력")
- interest: 관심 도메인 (예: "AI 코딩 도구", "iOS 모듈화")
- workflow: 워크플로 패턴 (예: "plan → review → ship")
- value: 가치관 (예: "성능보다 가독성")

# 원칙
- 자료에 명시되거나 강하게 반복되는 것만
- 추측 금지 — 직접 신호 없으면 제외
- 각 fact에 confidence (0.5~1.0). 1.0 = 매우 강한 반복.
- 한국어로 작성.

# 출력 (절대 위반 금지: JSON만, 첫 문자 ``{``)
{"facts": [{"category": "work_style", "statement": "단계별 의사코드 후 코드 작성", "confidence": 0.85}, ...]}

추출 없으면 {"facts": []}."""


DECISION_PATTERN_SYSTEM = """당신은 사용자의 의사결정 패턴을 추출하는 분석가입니다.

# 임무
raw 활동에서 **"트리거 → 행동 → 이유"** 패턴 추출.
- trigger: 어떤 상황·신호가 발생하면
- action: 사용자가 취하는 행동
- rationale: 추정되는 이유

# 원칙
- 자료에 반복 등장하는 패턴만
- 1회성 행동 제외
- 한국어

# 출력 (JSON만)
{"patterns": [{"trigger": "...", "action": "...", "rationale": "...", "confidence": 0.X}, ...]}"""


# ---------------------------------------------------------------------------
# Sample 가져오기
# ---------------------------------------------------------------------------


def _read_history_tail(path: Path, n: int) -> str:
    """history.jsonl 마지막 N 줄 → display 필드만 합쳐 단일 텍스트."""
    if not path.is_file():
        return ""
    lines: list[str] = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(ev, dict):
                    display = ev.get("display")
                    project = ev.get("project", "")
                    if isinstance(display, str) and display:
                        lines.append(f"[{project[-30:] if project else '?'}] {display}")
    except OSError:
        return ""
    return "\n".join(lines[-n:])


# ---------------------------------------------------------------------------
# 추출
# ---------------------------------------------------------------------------


def extract_profile_facts(
    *,
    sample_lines: int = DEFAULT_SAMPLE_LINES,
    model: str = DEFAULT_MODEL,
    claude_env: ClaudeEnvironment | None = None,
    apfel_env: ApfelEnvironment | None = None,
    history_path: Path | None = None,
) -> list[ProfileFact]:
    """Claude Code history → ProfileFact 후보.

    Raises:
        ClaudeError: API 호출 실패.
        FileNotFoundError: history.jsonl 없음.
    """
    history = history_path or (
        l0_root() / "raw" / "claude-code" / "history.jsonl"
    )
    raw_text = _read_history_tail(history, sample_lines)
    if not raw_text:
        raise FileNotFoundError(
            f"history 비어있음 또는 없음: {history} — "
            f"`synapse-memory collect claude-code` 먼저"
        )

    # redaction (Pass 1+2)
    redacted = redact_full(raw_text, env=apfel_env).redacted

    user_prompt = (
        f"# 사용자 명령 history (최근 {sample_lines}건, redacted)\n\n"
        f"{redacted}\n\n"
        f"# 지시\n위에서 반복 패턴으로 드러나는 사용자 성향 사실을 JSON으로 추출."
    )

    response = claude_api.complete_structured(
        user_prompt,
        system=PROFILE_SYSTEM,
        model=model,
        env=claude_env,
        timeout=DEFAULT_TIMEOUT,
    )

    if not isinstance(response, dict):
        raise ClaudeError(f"응답이 dict 아님: {type(response).__name__}")
    raw_facts = response.get("facts", [])
    if not isinstance(raw_facts, list):
        return []

    today = datetime.date.today().isoformat()
    facts: list[ProfileFact] = []
    for f in raw_facts:
        if not isinstance(f, dict):
            continue
        cat = str(f.get("category", "")).strip()
        stmt = str(f.get("statement", "")).strip()
        if not cat or not stmt:
            continue
        if cat not in PROFILE_CATEGORIES:
            continue
        try:
            conf = float(f.get("confidence", 0.5))
        except (TypeError, ValueError):
            conf = 0.5
        facts.append(
            ProfileFact(
                category=cat,
                statement=stmt,
                confidence=max(0.0, min(1.0, conf)),
                source_ids=["claude-code/history.jsonl"],
                extracted_at=today,
            )
        )
    return facts


def extract_decision_patterns(
    *,
    sample_lines: int = DEFAULT_SAMPLE_LINES,
    model: str = DEFAULT_MODEL,
    claude_env: ClaudeEnvironment | None = None,
    apfel_env: ApfelEnvironment | None = None,
    history_path: Path | None = None,
) -> list[DecisionPattern]:
    history = history_path or (
        l0_root() / "raw" / "claude-code" / "history.jsonl"
    )
    raw_text = _read_history_tail(history, sample_lines)
    if not raw_text:
        raise FileNotFoundError(f"history 비어있음: {history}")

    redacted = redact_full(raw_text, env=apfel_env).redacted

    user_prompt = (
        f"# 사용자 명령 history (최근 {sample_lines}건, redacted)\n\n"
        f"{redacted}\n\n"
        f"# 지시\n위에서 의사결정 패턴(트리거→행동→이유)을 JSON으로 추출."
    )

    response = claude_api.complete_structured(
        user_prompt,
        system=DECISION_PATTERN_SYSTEM,
        model=model,
        env=claude_env,
        timeout=DEFAULT_TIMEOUT,
    )

    if not isinstance(response, dict):
        raise ClaudeError(f"응답이 dict 아님: {type(response).__name__}")
    raw_patterns = response.get("patterns", [])
    if not isinstance(raw_patterns, list):
        return []

    today = datetime.date.today().isoformat()
    patterns: list[DecisionPattern] = []
    for p in raw_patterns:
        if not isinstance(p, dict):
            continue
        trigger = str(p.get("trigger", "")).strip()
        action = str(p.get("action", "")).strip()
        rationale = str(p.get("rationale", "")).strip()
        if not trigger or not action:
            continue
        try:
            conf = float(p.get("confidence", 0.5))
        except (TypeError, ValueError):
            conf = 0.5
        patterns.append(
            DecisionPattern(
                trigger=trigger,
                action=action,
                rationale=rationale,
                confidence=max(0.0, min(1.0, conf)),
                examples=["claude-code/history.jsonl"],
                extracted_at=today,
            )
        )
    return patterns


# ---------------------------------------------------------------------------
# 저장 — MemoryInbox에 PR
# ---------------------------------------------------------------------------


def save_profile_update(
    facts: list[ProfileFact],
    patterns: list[DecisionPattern] | None = None,
    *,
    vault_path: Path | None = None,
) -> Path:
    """후보 → vault MemoryInbox에 markdown PR. 사용자 검토 후 진실원본 반영."""
    vault = (vault_path or get_vault_path()).expanduser().resolve()
    inbox = vault / MEMORY_INBOX_SUBPATH
    inbox.mkdir(parents=True, exist_ok=True)

    today = datetime.date.today().isoformat()
    path = inbox / f"Profile-{today}.md"

    lines: list[str] = [
        "---",
        f"type: profile_update",
        f"generated: {today}",
        f"fact_count: {len(facts)}",
        f"pattern_count: {len(patterns) if patterns else 0}",
        "status: pending_review",
        "---",
        "",
        f"# Profile 갱신 후보 ({today})",
        "",
        "검토 후 `90_System/AI/Profile.md` / `DecisionPatterns.md`에 반영.",
        "",
    ]

    if facts:
        lines.append("## ProfileFact 후보")
        lines.append("")
        by_cat: dict[str, list[ProfileFact]] = {}
        for f in facts:
            by_cat.setdefault(f.category, []).append(f)
        for cat in sorted(by_cat.keys()):
            lines.append(f"### {cat}")
            lines.append("")
            for f in sorted(by_cat[cat], key=lambda x: -x.confidence):
                lines.append(f"- [{f.confidence:.2f}] {f.statement}")
            lines.append("")

    if patterns:
        lines.append("## DecisionPattern 후보")
        lines.append("")
        for p in sorted(patterns, key=lambda x: -x.confidence):
            lines.append(f"### {p.trigger}")
            lines.append("")
            lines.append(f"- 행동: {p.action}")
            lines.append(f"- 이유: {p.rationale}")
            lines.append(f"- 신뢰도: {p.confidence:.2f}")
            lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path
