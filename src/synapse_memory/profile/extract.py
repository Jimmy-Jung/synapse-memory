"""raw → ProfileFact / DecisionPattern 추출 (AI provider).

데이터 소스: L0 raw/claude-code/history.jsonl (사용자 명령 패턴 가장 풍부)

흐름::

    history.jsonl 마지막 N entry → redact_full → AI provider → JSON → ProfileFact 리스트
    → MemoryInbox/Profile-YYYY-MM-DD.md에 저장 (사용자 승인 후 vault 진실원본)

저자: Synapse Memory Maintainers
작성일: 2026-05-10
"""

from __future__ import annotations

import datetime
import json
from collections.abc import Mapping
from pathlib import Path

from synapse_memory.collectors.obsidian.mirror import get_vault_path
from synapse_memory.config import get_config
from synapse_memory.llm import ai_api
from synapse_memory.llm.ai_api import AIEnvironment, AIError
from synapse_memory.llm.apfel import ApfelEnvironment
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

# negative example 섹션에 포함할 최대 항목 수 — 토큰 비용 vs 품질 트레이드오프.
# 100개면 평균 ~50자 * 100 = 약 2000 tokens 추가.
_EXCLUDED_MAX_ITEMS = 100

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
# 프롬프트 negative example (LLM 추출 단계 dedupe)
# ---------------------------------------------------------------------------


def _dedupe_excluded(items: list[str]) -> list[str]:
    """대소문자/공백 기준 중복 제거 + ``_EXCLUDED_MAX_ITEMS`` cap."""
    seen: set[str] = set()
    unique: list[str] = []
    for s in items:
        s = (s or "").strip()
        if not s:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(s)
        if len(unique) >= _EXCLUDED_MAX_ITEMS:
            break
    return unique


def _build_excluded_section(label: str, items: list[str]) -> str:
    """user_prompt 에 붙일 일반 ``# 제외`` 섹션. 빈 리스트면 빈 문자열.

    중복 statement 제거 + 100개 cap. system 프롬프트는 건드리지 않아 prompt
    cache 유효성이 보존된다.
    """
    unique = _dedupe_excluded(items)
    if not unique:
        return ""
    bullets = "\n".join(f"- {s}" for s in unique)
    note = (
        f"\n(원본 {len(items)}개 중 상위 {_EXCLUDED_MAX_ITEMS}개)"
        if len(items) > _EXCLUDED_MAX_ITEMS
        else ""
    )
    return (
        "\n\n# 제외 — 이미 알고 있거나 사용자가 거부한 항목\n"
        "아래 목록과 동일하거나 단순 재진술인 항목은 절대 출력하지 마세요. "
        f"신규 신호만 추출하세요.{note}\n\n{bullets}\n"
    )


def _build_strong_excluded_section(label: str, items: list[str]) -> str:
    """강한 제외 섹션 — 사용자가 misclassified/irrelevant 로 명시한 항목.

    LLM 이 이 카테고리를 다시 출력하면 명시적 실패. 일반 제외보다 강한 어조 +
    한 화면에서 먼저 보이도록 sections 앞쪽에 배치한다.
    """
    unique = _dedupe_excluded(items)
    if not unique:
        return ""
    bullets = "\n".join(f"- {s}" for s in unique)
    note = (
        f"\n(원본 {len(items)}개 중 상위 {_EXCLUDED_MAX_ITEMS}개)"
        if len(items) > _EXCLUDED_MAX_ITEMS
        else ""
    )
    return (
        "\n\n# 제외 (강한 차단) — 사용자가 LLM 오추출 또는 noise 로 분류함\n"
        "**아래 항목은 사실 자체가 틀리거나 추출 가치가 전혀 없습니다. "
        f"같거나 유사한 항목을 출력하면 명백한 실패입니다.**{note}\n\n{bullets}\n"
    )


# ---------------------------------------------------------------------------
# Sample 가져오기
# ---------------------------------------------------------------------------


def _read_history_tail(path: Path, n: int) -> str:
    """claude-code history.jsonl 마지막 N 줄 → display 필드만 합쳐 단일 텍스트."""
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


def _read_codex_history_tail(path: Path, n: int, *, max_chars_per_line: int = 400) -> str:
    """codex history.jsonl 마지막 N 줄 → text 필드만 합쳐 단일 텍스트.

    claude-code 와 포맷이 다르므로 (``text`` 필드, project 없음) 별도 reader.
    줄 하나가 너무 길면 context 가 한쪽으로 편향되므로 ``max_chars_per_line`` 으로 컷.
    """
    if not path.is_file():
        return ""
    lines: list[str] = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    ev = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(ev, dict):
                    continue
                text = ev.get("text")
                if not isinstance(text, str) or not text:
                    continue
                # 개행을 공백으로 펴서 1줄 1입력 보장.
                flat = " ".join(text.split())
                if len(flat) > max_chars_per_line:
                    flat = flat[:max_chars_per_line] + "…"
                lines.append(f"[codex] {flat}")
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
    ai_env: AIEnvironment | None = None,
    apfel_env: ApfelEnvironment | None = None,
    history_path: Path | None = None,
    codex_history_path: Path | None = None,
    extra_text: str | None = None,
    excluded_statements: list[str] | None = None,
    excluded_statements_strong: list[str] | None = None,
) -> list[ProfileFact]:
    """Claude Code + Codex history (+ 선택적 외부 자료) → ProfileFact 후보.

    Args:
        sample_lines: 각 source 의 history.jsonl 마지막 N줄. 0 이면 history 무시.
        history_path: claude-code history override.
        codex_history_path: codex history override. 기본 ``<l0>/raw/codex/history.jsonl``.
            파일 없으면 silent skip — codex 미사용 환경도 정상 동작.
        extra_text: 이미 redacted 된 외부 자료. history 와 함께 사용 가능.

    Raises:
        AIError: AI provider 호출 실패.
        FileNotFoundError: 어떤 source 도 자료를 못 찾음.
    """
    history = history_path or (
        l0_root() / "raw" / "claude-code" / "history.jsonl"
    )
    codex_history = codex_history_path or (
        l0_root() / "raw" / "codex" / "history.jsonl"
    )

    sections: list[str] = []
    source_ids: list[str] = []

    if sample_lines > 0:
        raw_history = _read_history_tail(history, sample_lines)
        if raw_history:
            redacted_history = redact_full(raw_history, env=apfel_env).redacted
            if redacted_history:
                sections.append(
                    f"## claude-code history (최근 {sample_lines}건, redacted)\n\n"
                    f"{redacted_history}"
                )
                source_ids.append("claude-code/history.jsonl")
        raw_codex = _read_codex_history_tail(codex_history, sample_lines)
        if raw_codex:
            redacted_codex = redact_full(raw_codex, env=apfel_env).redacted
            if redacted_codex:
                sections.append(
                    f"## codex history (최근 {sample_lines}건, redacted)\n\n"
                    f"{redacted_codex}"
                )
                source_ids.append("codex/history.jsonl")

    if extra_text:
        sections.append(f"## 외부 첨부 자료 (redacted)\n\n{extra_text}")
        source_ids.append("persona-ingest")

    if not sections:
        raise FileNotFoundError(
            f"수집할 자료 없음: claude-code={history} codex={codex_history} "
            f"sample_lines={sample_lines} extra_text=None — "
            "`synapse-memory collect claude-code` / `daily --only collect_codex` "
            "또는 `persona ingest --file ...` 먼저"
        )

    combined = "\n\n---\n\n".join(sections)
    strong_section = _build_strong_excluded_section(
        "프로필 사실", excluded_statements_strong or []
    )
    excluded_section = _build_excluded_section(
        "프로필 사실", excluded_statements or []
    )
    user_prompt = (
        f"# 사용자 자료\n\n{combined}"
        f"{strong_section}"
        f"{excluded_section}\n"
        f"# 지시\n위에서 반복 패턴으로 드러나는 사용자 성향 사실을 JSON으로 추출."
    )

    response = ai_api.complete_structured(
        user_prompt,
        system=PROFILE_SYSTEM,
        model=model,
        env=ai_env,
        timeout=DEFAULT_TIMEOUT,
    )

    if not isinstance(response, dict):
        raise AIError(f"응답이 dict 아님: {type(response).__name__}")
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
                source_ids=list(source_ids),
                extracted_at=today,
            )
        )
    return facts


def extract_decision_patterns(
    *,
    sample_lines: int = DEFAULT_SAMPLE_LINES,
    model: str = DEFAULT_MODEL,
    ai_env: AIEnvironment | None = None,
    apfel_env: ApfelEnvironment | None = None,
    history_path: Path | None = None,
    codex_history_path: Path | None = None,
    excluded_triggers: list[str] | None = None,
    excluded_triggers_strong: list[str] | None = None,
) -> list[DecisionPattern]:
    history = history_path or (
        l0_root() / "raw" / "claude-code" / "history.jsonl"
    )
    codex_history = codex_history_path or (
        l0_root() / "raw" / "codex" / "history.jsonl"
    )

    sections: list[str] = []
    examples: list[str] = []
    cc_text = _read_history_tail(history, sample_lines)
    if cc_text:
        redacted = redact_full(cc_text, env=apfel_env).redacted
        if redacted:
            sections.append(
                f"## claude-code history (최근 {sample_lines}건, redacted)\n\n"
                f"{redacted}"
            )
            examples.append("claude-code/history.jsonl")
    codex_text = _read_codex_history_tail(codex_history, sample_lines)
    if codex_text:
        redacted_cx = redact_full(codex_text, env=apfel_env).redacted
        if redacted_cx:
            sections.append(
                f"## codex history (최근 {sample_lines}건, redacted)\n\n"
                f"{redacted_cx}"
            )
            examples.append("codex/history.jsonl")

    if not sections:
        raise FileNotFoundError(
            f"history 비어있음: claude-code={history} codex={codex_history}"
        )

    combined = "\n\n---\n\n".join(sections)
    strong_section = _build_strong_excluded_section(
        "결정 패턴 trigger", excluded_triggers_strong or []
    )
    excluded_section = _build_excluded_section(
        "결정 패턴 trigger", excluded_triggers or []
    )
    user_prompt = (
        f"# 사용자 명령 history\n\n"
        f"{combined}"
        f"{strong_section}"
        f"{excluded_section}\n"
        f"# 지시\n위에서 의사결정 패턴(트리거→행동→이유)을 JSON으로 추출."
    )

    response = ai_api.complete_structured(
        user_prompt,
        system=DECISION_PATTERN_SYSTEM,
        model=model,
        env=ai_env,
        timeout=DEFAULT_TIMEOUT,
    )

    if not isinstance(response, dict):
        raise AIError(f"응답이 dict 아님: {type(response).__name__}")
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
                examples=list(examples),
                extracted_at=today,
            )
        )
    return patterns


# ---------------------------------------------------------------------------
# 저장 — MemoryInbox에 PR
# ---------------------------------------------------------------------------


def _fact_score(fact: ProfileFact, entry: object | None) -> tuple[float, int]:
    """정렬 키 — (peak confidence, seen_count) 내림차순.

    ledger entry 가 있으면 누적 신호를 우선, 없으면 단일 호출 confidence 만 사용.
    """
    from synapse_memory.profile.ledger import LedgerEntry

    if isinstance(entry, LedgerEntry):
        return (entry.peak_confidence(), entry.seen_count)
    return (fact.confidence, 0)


def _pattern_score(pattern: DecisionPattern, entry: object | None) -> tuple[float, int]:
    from synapse_memory.profile.ledger import LedgerEntry

    if isinstance(entry, LedgerEntry):
        return (entry.peak_confidence(), entry.seen_count)
    return (pattern.confidence, 0)


def _meta_suffix(entry: object | None) -> str:
    """``- [0.92] 문장`` 뒤에 붙는 ledger 메타 한 줄. entry 없으면 빈 문자열."""
    from synapse_memory.profile.ledger import LedgerEntry

    if not isinstance(entry, LedgerEntry):
        return ""
    span_days = 0
    if entry.first_seen and entry.last_seen:
        try:
            d0 = datetime.date.fromisoformat(entry.first_seen)
            d1 = datetime.date.fromisoformat(entry.last_seen)
            span_days = (d1 - d0).days
        except ValueError:
            span_days = 0
    avg = entry.aggregated_confidence()
    peak = entry.peak_confidence()
    span_note = f", {span_days}일 간격" if span_days else ""
    return (
        f"  ↳ ledger: {entry.seen_count}회 등장{span_note} "
        f"(peak {peak:.2f} · avg {avg:.2f}, 첫 {entry.first_seen})"
    )


def save_profile_update(
    facts: list[ProfileFact],
    patterns: list[DecisionPattern] | None = None,
    *,
    vault_path: Path | None = None,
    date: datetime.date | None = None,
    ledger: Mapping[str, object] | None = None,
) -> Path:
    """후보 → vault MemoryInbox에 markdown PR. 사용자 검토 후 진실원본 반영.

    Args:
        ledger: ``profile/ledger.py`` 의 ``load_ledger`` 결과. 있으면 각 fact/pattern
            아래에 누적 메타(``seen_count`` / peak conf / 첫 등장)를 출력하고
            ledger 기반으로 정렬 — apply 단계 판단 보조.
    """
    from synapse_memory.folders import year_month_path
    from synapse_memory.profile.ledger import LedgerEntry, _ledger_key

    vault = (vault_path or get_vault_path()).expanduser().resolve()
    inbox_base = vault / get_config().vault_folders.system.ai.memory_inbox
    today_date = date or datetime.date.today()
    inbox = year_month_path(inbox_base, today_date)
    inbox.mkdir(parents=True, exist_ok=True)

    today = today_date.isoformat()
    path = inbox / f"Profile-{today}.md"

    # ledger lookup helper — fact/pattern fingerprint 기준.
    from synapse_memory.profile.dedupe import _normalize

    def _lookup(kind: str, text: str) -> LedgerEntry | None:
        if not ledger:
            return None
        entry = ledger.get(_ledger_key(kind, _normalize(text)))
        return entry if isinstance(entry, LedgerEntry) else None

    # 평균 confidence 한 줄 — apply 스킬의 bulk 화면 요약용.
    def _avg(items: list[float]) -> float:
        return sum(items) / len(items) if items else 0.0

    fact_confs = [f.confidence for f in facts]
    pattern_confs = [p.confidence for p in (patterns or [])]

    lines: list[str] = [
        "---",
        "type: profile_update",
        f"generated: {today}",
        f"fact_count: {len(facts)}",
        f"pattern_count: {len(patterns) if patterns else 0}",
        f"fact_avg_confidence: {_avg(fact_confs):.2f}",
        f"pattern_avg_confidence: {_avg(pattern_confs):.2f}",
        "status: pending_review",
        "tags:",
        "  - node/profile-update",
        "---",
        "",
        f"# Profile 갱신 후보 ({today})",
        "",
        "검토 후 `90_System/AI/Profile.md` / `DecisionPatterns.md`에 반영.",
        "각 항목의 `↳ ledger:` 라인은 multi-day 누적 신호 — 등장 횟수가 많고 peak 가 높을수록 안정 신호.",
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
            ordered = sorted(
                by_cat[cat],
                key=lambda x: _fact_score(x, _lookup("fact", x.statement)),
                reverse=True,
            )
            for f in ordered:
                entry = _lookup("fact", f.statement)
                lines.append(f"- [{f.confidence:.2f}] {f.statement}")
                meta = _meta_suffix(entry)
                if meta:
                    lines.append(meta)
            lines.append("")

    if patterns:
        lines.append("## DecisionPattern 후보")
        lines.append("")
        ordered_p = sorted(
            patterns,
            key=lambda p: _pattern_score(p, _lookup("pattern", p.trigger)),
            reverse=True,
        )
        for p in ordered_p:
            entry = _lookup("pattern", p.trigger)
            lines.append(f"### {p.trigger}")
            lines.append("")
            lines.append(f"- 행동: {p.action}")
            lines.append(f"- 이유: {p.rationale}")
            lines.append(f"- 신뢰도: {p.confidence:.2f}")
            meta = _meta_suffix(entry)
            if meta:
                lines.append(meta)
            lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path
