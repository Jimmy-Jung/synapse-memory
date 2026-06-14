"""Cluster → 카테고리 자동 분류 (AI provider).

흐름::

    cluster의 sample notes (3-5개)
        ↓ redact_full (Pass 1+2 통과 — 외부 API에 raw 노출 금지)
        ↓ AI provider (ai_api.complete_structured)
    ClusterClassification (kind / candidate_name / rationale)

분류 카테고리:
    project — 구체 프로젝트 (Project Card 대상)
    company — 회사 (Company Card 대상)
    domain  — 학습/도메인 카테고리 (iOS/Swift 등) — Card 안 만듦
    life    — 개인 생활/취미 — Card 안 만듦
    skip    — 메타·아카이브 (Card 부적절)

저자: Synapse Memory Maintainers
작성일: 2026-05-10
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import asdict, dataclass
from pathlib import Path

from synapse_memory.clusters.identify import ProjectCluster
from synapse_memory.llm import ai_api
from synapse_memory.llm.ai_api import AIEnvironment
from synapse_memory.llm.apfel import ApfelEnvironment
from synapse_memory.storage.l0 import l0_root

VALID_KINDS = ("project", "company", "domain", "life", "skip")
SAMPLE_NOTES = 5
SAMPLE_NOTE_CHARS = 1500   # 노트당 최대 문자 (redact 전)
MAX_RAW_TEXT = 8000         # AI provider 입력 총량 제한
DEFAULT_CLASSIFY_MODEL = "haiku"  # 단순 분류 작업 — haiku로 비용 1/3

# codex rollout 신호 — Claude Code 매칭 못한 GitLab/사내 프로젝트도
# cluster 분류 입력에 포함되도록 user message 일부만 발췌.
CODEX_SAMPLE_ROLLOUTS = 2
CODEX_SAMPLE_MESSAGES_PER_ROLLOUT = 6
CODEX_SAMPLE_CHARS_PER_MESSAGE = 240
_CODEX_INSTRUCTION_PREFIX_MARKERS: tuple[str, ...] = (
    "# AGENTS.md instructions for ",
    "# CLAUDE.md instructions for ",
    "<INSTRUCTIONS>",
    "<system-reminder>",
    "<user-prompt-submit-hook>",
)

CLASSIFY_SYSTEM = (
    "당신은 사용자의 vault 폴더(cluster)를 보고 카테고리를 분류하는 분석가입니다.\n"
    "다음 5개 중 하나를 정확히 골라 JSON 한 줄로만 답하세요.\n"
    "\n"
    "- project: 구체적 deliverable이 있는 작업/프로젝트\n"
    "  예: 단심 앱 개발, 이력서-2026, 카뱅 지원 준비\n"
    "- company: 회사·조직 (지원/근무 중)\n"
    "  예: 샘플회사, 당근마켓\n"
    "- domain: 학습 주제/기술 도메인 (작업이 아닌 카테고리)\n"
    "  예: iOS, Swift, Algorithm, CS 노트 모음\n"
    "- life: 개인 생활·취미\n"
    "  예: 한자, 천자문, 토익, 임신과 출산\n"
    "- skip: 메타/아카이브/너무 광범위해서 Card 부적절\n"
    "\n"
    "출력 형식 (절대 위반 금지):\n"
    '{"kind": "...", "candidate_name": "사람 읽는 이름", "rationale": "한 문장"}\n'
    "\n"
    "JSON 외 텍스트, 마크다운, 설명 금지."
)


@dataclass
class ClusterClassification:
    cluster_id: str
    kind: str
    candidate_name: str
    rationale: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _gather_sample_text(
    cluster: ProjectCluster,
    obs_root: Path,
    *,
    max_notes: int = SAMPLE_NOTES,
    max_chars_per_note: int = SAMPLE_NOTE_CHARS,
) -> str:
    """cluster의 sample 노트 모아 단일 문자열로. 길이 cap."""
    parts: list[str] = []
    used = 0
    for rel in cluster.obsidian_files[:max_notes]:
        path = obs_root / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        snippet = text[:max_chars_per_note]
        block = f"--- {rel} ---\n{snippet}\n"
        if used + len(block) > MAX_RAW_TEXT:
            break
        parts.append(block)
        used += len(block)
    return "".join(parts)


def _gather_codex_sample(
    cluster: ProjectCluster,
    codex_root: Path,
    *,
    used_chars: int,
    max_rollouts: int = CODEX_SAMPLE_ROLLOUTS,
    max_messages_per_rollout: int = CODEX_SAMPLE_MESSAGES_PER_ROLLOUT,
    max_chars_per_message: int = CODEX_SAMPLE_CHARS_PER_MESSAGE,
) -> str:
    """cluster에 매핑된 rollout-*.jsonl 에서 user message 일부 발췌.

    obsidian 노트 sample 만으로는 Claude Code 매칭 안 된 GitLab/사내 프로젝트가
    domain/skip 으로 오분류될 수 있다. 짧은 codex user message 몇 줄을
    sample text 끝에 붙여 분류 정확도를 보강한다.

    Args:
        used_chars: 이미 obsidian sample 이 차지한 문자 수. ``MAX_RAW_TEXT`` 잔량 계산용.

    Returns:
        ``--- codex: <rel> ---`` 블록을 합친 문자열. cluster에 codex 신호 없거나
        잔량 부족 시 ``""``.
    """
    if not cluster.codex_jsonl:
        return ""
    remaining = MAX_RAW_TEXT - used_chars
    if remaining <= 0:
        return ""

    parts: list[str] = []
    consumed = 0
    # mtime 내림차순 — 최신 rollout 우선.
    candidates: list[tuple[float, Path, str]] = []
    for rel in cluster.codex_jsonl[: max_rollouts * 4]:  # mtime 정렬용 약간 여유
        path = codex_root / rel
        if not path.is_file():
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        candidates.append((mtime, path, rel))
    candidates.sort(key=lambda t: t[0], reverse=True)

    for _mtime, path, rel in candidates[:max_rollouts]:
        messages = _extract_user_messages(
            path,
            max_messages=max_messages_per_rollout,
            max_chars=max_chars_per_message,
        )
        if not messages:
            continue
        body = "\n".join(messages)
        block = f"--- codex: {rel} ---\n{body}\n"
        if consumed + len(block) > remaining:
            break
        parts.append(block)
        consumed += len(block)
    return "".join(parts)


def _extract_user_messages(
    rollout_path: Path,
    *,
    max_messages: int,
    max_chars: int,
) -> list[str]:
    """rollout-*.jsonl 에서 user message text 만 추출.

    ``response_item.payload.{type=='message', role=='user'}`` 만 채택.
    AGENTS.md / CLAUDE.md instruction prefix 가 붙은 첫 turn 은 노이즈로 스킵.
    """
    messages: list[str] = []
    try:
        with open(rollout_path, encoding="utf-8", errors="replace") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    ev = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(ev, Mapping):
                    continue
                if ev.get("type") != "response_item":
                    continue
                payload = ev.get("payload")
                if not isinstance(payload, Mapping):
                    continue
                if payload.get("type") != "message" or payload.get("role") != "user":
                    continue
                content = payload.get("content")
                if not isinstance(content, list):
                    continue
                parts: list[str] = []
                for item in content:
                    if not isinstance(item, Mapping):
                        continue
                    text = item.get("text")
                    if isinstance(text, str) and text:
                        parts.append(text)
                if not parts:
                    continue
                combined = " ".join(parts).lstrip()
                if any(
                    combined.startswith(marker)
                    for marker in _CODEX_INSTRUCTION_PREFIX_MARKERS
                ):
                    continue
                flat = " ".join(combined.split())
                if not flat:
                    continue
                if len(flat) > max_chars:
                    flat = flat[:max_chars] + "…"
                messages.append(f"- {flat}")
                if len(messages) >= max_messages:
                    break
    except OSError:
        return messages
    return messages


def _build_user_prompt(
    cluster: ProjectCluster, redacted_sample: str
) -> str:
    folders = ", ".join(sorted(cluster.vault_folders)) or "(없음)"
    cwds = ", ".join(sorted(cluster.cwd_paths)) or "(없음)"
    tags = ", ".join(sorted(cluster.tags)[:15]) or "(없음)"
    return (
        f"# Cluster 정보\n"
        f"- cluster_id: {cluster.cluster_id}\n"
        f"- candidate_name (휴리스틱): {cluster.candidate_name}\n"
        f"- vault_folders: {folders}\n"
        f"- cwd_paths: {cwds}\n"
        f"- 노트 수: {len(cluster.obsidian_files)}\n"
        f"- claude jsonl 수: {len(cluster.claude_jsonl)}\n"
        f"- codex rollout 수: {len(cluster.codex_jsonl)}\n"
        f"- 태그: {tags}\n"
        f"\n"
        f"# Sample (redacted — vault 노트 + codex user message)\n"
        f"{redacted_sample if redacted_sample else '(자료 없음)'}\n"
        f"\n"
        f"위 cluster의 카테고리는?"
    )


def classify_cluster(
    cluster: ProjectCluster,
    *,
    obs_root: Path,
    ai_env: AIEnvironment,
    apfel_env: ApfelEnvironment | None = None,
    model: str = DEFAULT_CLASSIFY_MODEL,
    codex_root: Path | None = None,
) -> ClusterClassification:
    """단일 cluster 분류.

    sample (vault notes + codex user messages) → redact_full → AI provider
    → ClusterClassification.

    Args:
        model: 분류용 모델 (기본 haiku — 단순 분류라 충분).
        codex_root: ``~/.synapse/private/raw/codex`` (기본). cluster.codex_jsonl 의
            상대 경로 해석에 사용. 미지정 시 ``<l0>/raw/codex``.

    Raises:
        AIError: AI provider 호출 실패 또는 응답 schema 어긋남.
    """
    raw_sample = _gather_sample_text(cluster, obs_root)
    cx_root = (codex_root or (l0_root() / "raw" / "codex")).expanduser().resolve()
    codex_sample = _gather_codex_sample(cluster, cx_root, used_chars=len(raw_sample))
    combined_sample = raw_sample + codex_sample

    user_prompt = _build_user_prompt(cluster, combined_sample)

    # json_schema 안 씀 — sonnet에서 빈 응답 만드는 케이스 발견됨.
    # system prompt + complete_structured fallback parser가 처리.
    response = ai_api.complete_structured(
        user_prompt,
        system=CLASSIFY_SYSTEM,
        model=model,
        env=ai_env,
    )

    if not isinstance(response, dict):
        from synapse_memory.llm.ai_api import AIError

        raise AIError(f"분류 응답이 dict 아님: {type(response).__name__}")

    kind = str(response.get("kind", "skip")).strip().lower()
    if kind not in VALID_KINDS:
        kind = "skip"
    candidate_name = str(response.get("candidate_name") or cluster.candidate_name)
    rationale = str(response.get("rationale") or "")

    return ClusterClassification(
        cluster_id=cluster.cluster_id,
        kind=kind,
        candidate_name=candidate_name,
        rationale=rationale,
    )


# ---------------------------------------------------------------------------
# 결과 영속화 (cluster scan과 함께 사용)
# ---------------------------------------------------------------------------


CLASSIFICATIONS_FILE = "classifications.json"


def _classifications_path() -> Path:
    return l0_root() / "clusters" / CLASSIFICATIONS_FILE


def load_classifications() -> dict[str, ClusterClassification]:
    """이전 분류 결과 로드 (cluster_id → 분류). 재실행 시 skip 가능."""
    import json
    p = _classifications_path()
    if not p.is_file():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, ClusterClassification] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        cid = item.get("cluster_id")
        if not cid:
            continue
        out[cid] = ClusterClassification(
            cluster_id=str(cid),
            kind=str(item.get("kind", "skip")),
            candidate_name=str(item.get("candidate_name", "")),
            rationale=str(item.get("rationale", "")),
        )
    return out


def save_classifications(
    classifications: dict[str, ClusterClassification],
) -> Path:
    """전체 분류 결과 저장."""
    import json
    import os

    from synapse_memory.storage.l0 import (
        L0_FILE_MODE,
        ensure_l0_root_secure,
        ensure_secure_dir,
    )

    ensure_l0_root_secure()
    p = _classifications_path()
    ensure_secure_dir(p.parent)
    payload = [c.to_dict() for c in classifications.values()]
    p.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    with suppress(OSError):
        os.chmod(p, L0_FILE_MODE)
    return p
