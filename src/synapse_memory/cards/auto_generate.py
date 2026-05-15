"""Cluster → Project/Company Card 자동 생성 (AI provider).

흐름::

    1. classify된 project/company cluster 가져옴
    2. cluster의 모든 obsidian 노트 read
    3. redact_full (Pass 1+2) → redacted text
    4. cluster meta + redacted → AI provider → yaml frontmatter + body 초안
    5. parse → ProjectCard/CompanyCard
    6. status="draft", confidence=0.7로 vault에 저장 (검토 후 promote)

저자: Synapse Memory Maintainers
작성일: 2026-05-10
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path

from synapse_memory.cards.company import (
    CompanyCard,
    parse_company_card,
)
from synapse_memory.cards.project import (
    ProjectCard,
    parse_project_card,
)
from synapse_memory.clusters.identify import ProjectCluster
from synapse_memory.llm import ai_api
from synapse_memory.llm.ai_api import AIEnvironment
from synapse_memory.llm.apfel import ApfelEnvironment
from synapse_memory.redaction import redact_full

DEFAULT_GENERATE_MODEL = "sonnet"
SAMPLE_NOTES_FOR_CARD = 6        # 큰 cluster 처리 시간/비용 trade-off
NOTE_CHARS_FOR_CARD = 2000
MAX_RAW_TEXT_FOR_CARD = 12000     # ~3K input + 응답 4K → 60초 가능
DEFAULT_GENERATE_TIMEOUT = 180    # Card 생성은 단순 호출보다 김


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


PROJECT_CARD_SYSTEM = """당신은 사용자의 vault 자료로 Project Card를 추출하는 분석가입니다.

# 출력 (절대 위반 금지)
- 응답의 **첫 문자는 반드시 `-`** (즉 `---`로 시작)
- 인사, 분석, 사고 과정, Insight 박스, 코드 펜스 모두 금지
- yaml frontmatter (---로 둘러싸임) 다음에 markdown body
- 노트 정보가 부족해도 반드시 yaml로 시작 (필드를 빈 문자열로)

# 추출 지침
- display_name: 사람이 읽기 좋은 한국어 이름 (cluster_id 그대로 쓰지 말 것)
- role: 사용자가 무엇을 했는지 (예: "iOS Lead Engineer", "백엔드 개발자")
  추론 안 되면 빈 문자열
- period_start/end: YYYY-MM 형식. 노트의 날짜에서 추론. 모르면 빈 문자열
- domains: ios, mobile, web, backend, ai 등 (소문자)
- stack: Swift, SwiftUI, TCA, Python 등 (원문 case 보존)
- keywords: 프로젝트 핵심 단어 5-10개
- metrics: 수치 지표 ({name, before, after} 또는 {name, value}). 없으면 생략
- body: 4개 섹션 (## 문제, ## 접근, ## 영향, ## 회고). 정보 없으면 빈 줄

# 형식 (정확히 이 구조)
---
project_id: <cluster_id 그대로>
display_name: <한국어 이름>
status: draft
role: <또는 빈 문자열>
period_start: <YYYY-MM 또는 빈 문자열>
period_end: <YYYY-MM 또는 빈 문자열>
domains: [...]
stack: [...]
keywords: [...]
metrics:
  - { name: ..., value: ... }
confidence: 0.7
---

# <display_name>

## 문제

...

## 접근

...

## 영향

...

## 회고

...
"""


COMPANY_CARD_SYSTEM = """당신은 사용자의 vault 자료로 Company Card를 추출하는 분석가입니다.

# 출력 (절대 위반 금지)
- 응답의 **첫 문자는 반드시 `-`** (즉 `---`로 시작)
- 인사, 분석, 사고 과정, Insight 박스, 코드 펜스 모두 금지
- yaml frontmatter 다음에 markdown body
- 노트 정보가 부족해도 반드시 yaml로 시작

# 추출 지침
- display_name: 회사 정식 한국어 이름
- status: target/applied/interviewing/offered/rejected/hired 중 추론. 모르면 "target"
- country: ISO 코드 (KR, US 등)
- size: startup/small/medium/large/mega
- website: 알려진 도메인
- positions: 노트에서 언급된 포지션 ({title, seniority, keywords})
- body: ## 회사 개요, ## 기술 스택, ## 문화, ## 매칭되는 내 프로젝트, ## 메모

# 형식
---
company_id: <cluster_id 그대로>
display_name: <한국어>
status: target
country: <또는 비워둠>
size: <또는 비워둠>
website: <또는 비워둠>
positions:
  - { title: ..., seniority: ..., keywords: [...] }
confidence: 0.7
---

# <display_name>

## 회사 개요

...
"""


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass
class CardGenerationResult:
    cluster_id: str
    kind: str  # "project" | "company"
    saved_path: Path
    chars_input: int
    skipped_reason: str = ""

    @property
    def skipped(self) -> bool:
        return bool(self.skipped_reason)


# ---------------------------------------------------------------------------
# 공통
# ---------------------------------------------------------------------------


def _gather_redacted_text(
    cluster: ProjectCluster,
    obs_root: Path,
    *,
    apfel_env: ApfelEnvironment | None,
    max_notes: int = SAMPLE_NOTES_FOR_CARD,
    chars_per_note: int = NOTE_CHARS_FOR_CARD,
    max_total: int = MAX_RAW_TEXT_FOR_CARD,
) -> str:
    """cluster 노트들 → redacted 단일 텍스트."""
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
        snippet = text[:chars_per_note]
        block = f"--- {rel} ---\n{snippet}\n\n"
        if used + len(block) > max_total:
            break
        parts.append(block)
        used += len(block)

    raw = "".join(parts)
    if not raw:
        return ""

    return redact_full(raw, env=apfel_env).redacted


def _build_user_prompt(
    cluster: ProjectCluster, redacted: str, candidate_name: str
) -> str:
    folders = ", ".join(sorted(cluster.vault_folders)) or "(없음)"
    cwds = ", ".join(sorted(cluster.cwd_paths)) or "(없음)"
    tags = ", ".join(sorted(cluster.tags)[:20]) or "(없음)"
    return (
        f"# Cluster 정보\n"
        f"- cluster_id: {cluster.cluster_id}\n"
        f"- 추정 이름: {candidate_name}\n"
        f"- vault_folders: {folders}\n"
        f"- cwd_paths: {cwds}\n"
        f"- 태그: {tags}\n"
        f"- 노트 수: {len(cluster.obsidian_files)}\n"
        f"\n"
        f"# Sample notes (redacted)\n"
        f"{redacted if redacted else '(노트 없음)'}\n"
        f"\n"
        f"위 정보로 Card를 생성하세요."
    )


# ---------------------------------------------------------------------------
# Project Card 생성
# ---------------------------------------------------------------------------


def generate_project_card(
    cluster: ProjectCluster,
    candidate_name: str,
    *,
    obs_root: Path,
    ai_env: AIEnvironment,
    apfel_env: ApfelEnvironment | None = None,
    model: str = DEFAULT_GENERATE_MODEL,
) -> ProjectCard:
    """cluster → ProjectCard. yaml frontmatter parse까지 수행.

    Raises:
        AIError: 호출 실패 또는 응답 형식 오류.
        ValueError: yaml 파싱 실패.
    """
    redacted = _gather_redacted_text(cluster, obs_root, apfel_env=apfel_env)
    user_prompt = _build_user_prompt(cluster, redacted, candidate_name)

    text = ai_api.complete(
        user_prompt,
        system=PROJECT_CARD_SYSTEM,
        model=model,
        env=ai_env,
        timeout=DEFAULT_GENERATE_TIMEOUT,
    )

    # ```...``` 코드 펜스 제거 (모델이 가끔 감쌈)
    cleaned = _strip_outer_fence(text)
    try:
        card = parse_project_card(cleaned)
    except ValueError as exc:
        raise ValueError(
            f"{exc} — AI 응답 시작 200자: {cleaned[:200]!r}"
        ) from exc

    today = datetime.date.today().isoformat()
    if not card.created:
        card.created = today
    if not card.last_reviewed:
        card.last_reviewed = today
    return card


# ---------------------------------------------------------------------------
# Company Card 생성
# ---------------------------------------------------------------------------


def generate_company_card(
    cluster: ProjectCluster,
    candidate_name: str,
    *,
    obs_root: Path,
    ai_env: AIEnvironment,
    apfel_env: ApfelEnvironment | None = None,
    model: str = DEFAULT_GENERATE_MODEL,
) -> CompanyCard:
    redacted = _gather_redacted_text(cluster, obs_root, apfel_env=apfel_env)
    user_prompt = _build_user_prompt(cluster, redacted, candidate_name)

    text = ai_api.complete(
        user_prompt,
        system=COMPANY_CARD_SYSTEM,
        model=model,
        env=ai_env,
        timeout=DEFAULT_GENERATE_TIMEOUT,
    )

    cleaned = _strip_outer_fence(text)
    try:
        card = parse_company_card(cleaned)
    except ValueError as exc:
        raise ValueError(
            f"{exc} — AI 응답 시작 200자: {cleaned[:200]!r}"
        ) from exc

    today = datetime.date.today().isoformat()
    if not card.created:
        card.created = today
    if not card.last_reviewed:
        card.last_reviewed = today
    return card


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------


def _strip_outer_fence(text: str) -> str:
    """``` ... ``` 외각 펜스 제거 + frontmatter 시작 위치 추출.

    Claude가 yaml 앞에 prose(★ Insight, 인사 등)를 추가하는 경우 — frontmatter
    `---\\n` 첫 위치를 찾아 그 앞을 잘라낸다.
    """
    s = text.strip()
    # 코드 펜스 제거
    if s.startswith("```"):
        nl = s.find("\n")
        if nl >= 0:
            s = s[nl + 1:]
        if s.endswith("```"):
            s = s[:-3]
        s = s.strip()
    # frontmatter 시작 위치 찾기 — 처음 등장하는 ``---\\n``
    # (앞에 prose가 있으면 그 부분 잘라냄)
    for marker in ("\n---\n", "\n---\r\n"):
        idx = s.find(marker)
        if idx >= 0:
            # marker는 빈 줄 후 ---. 첫 ---는 frontmatter 시작.
            # 단 텍스트가 ---로 시작하면 그게 frontmatter 시작.
            if not s.startswith("---"):
                # marker 위치 +1 (첫 \n 건너뛰고 --- 부터)
                s = s[idx + 1:]
            break
    return s.strip()
