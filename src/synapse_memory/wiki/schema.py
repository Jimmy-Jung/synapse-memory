"""SCHEMA.md — wiki의 "CLAUDE.md". vault 루트에 위치.

페이지 분류·작성 규칙·링크 규약 + ingest/query/lint 작업 지침을 한 파일에 정의한다.
어떤 에이전트(claude/codex/cursor)든 이 파일을 읽으면 wiki 유지법을 알게 된다.

저자: Synapse Memory Maintainers
작성일: 2026-06-14
"""
from __future__ import annotations

from pathlib import Path

from synapse_memory.collectors.obsidian.mirror import get_vault_path

SCHEMA_FILENAME = "SCHEMA.md"

SCHEMA_TEMPLATE = """\
# Synapse Memory — Wiki SCHEMA

이 vault는 LLM이 유지하는 개인 wiki(세컨드브레인)입니다. 어떤 에이전트든 이 파일을
읽고 아래 규약대로 페이지를 작성·갱신·정리합니다. 사람이 직접 편집해도 됩니다.

## 페이지 타입

| type | 폴더 | 용도 |
|------|------|------|
| project | `Entities/Projects/` | 프로젝트 진실원본 (이력서·면접 자산) |
| company | `Entities/Companies/` | 회사·지원내역·JD |
| person  | `Entities/People/`    | 인물 |
| concept | `Concepts/`           | 기술·의사결정원칙·반복 주제 |
| profile | `Profile/`            | 나에 대한 사실·선호·결정패턴 |
| insight | `Insights/<yyyy>/<mm>/`| 질의 답변 write-back |

## frontmatter 규약

```yaml
---
type: project|company|person|concept|profile|insight
slug: <파일명과 동일한 식별자>
title: <사람이 읽는 제목>
related: ["[[other-slug]]"]   # 양방향 링크 — A가 B를 링크하면 B에도 A 역링크
sources: ["claude_code:<날짜>/<세션>"]  # provenance: 이 내용이 어느 대화에서 왔는지
updated: YYYY-MM-DD
status: active|stale|review
---
```

## 작업: INGEST (새 대화/노트 통합)

1. 새 raw 조각을 읽고, **관련된 기존 페이지를 먼저 찾는다** (이름 매칭 + 의미 유사 + 링크 이웃).
2. **새 페이지를 함부로 만들지 말고**, 해당하는 기존 페이지를 **갱신**한다 (integrate-not-index).
3. 정말 새로운 엔티티/개념이면 새 페이지를 만든다.
4. 관련 페이지끼리 `[[slug]]`로 양방향 링크한다.
5. 갱신한 페이지의 `updated`와 `sources`를 채운다.

## 작업: QUERY (질문 답변)

1. wiki 페이지에서 근거를 찾아 답한다 (raw가 아니라 정제된 페이지 우선).
2. 각 주장에 `[[페이지]]`로 출처를 단다. 자료에 없는 내용은 추측하지 않는다.
3. 가치 있는 분석은 `Insights/`에 새 페이지로 남긴다 (write-back).

## 작업: LINT (정리)

- **자동 수정(구조)**: 끊긴 역링크 보강, 고아 페이지를 `index.md`에 연결, 죽은 `[[링크]]` 정리.
- **사람 검토 큐(진실)**: 사실 모순·낡음 의심·병합 후보는 `index.md` 검토 큐에 올린다. 임의로 진위를 단정하지 않는다.
"""


def schema_path(*, vault_path: Path | None = None) -> Path:
    """SCHEMA.md 경로 (vault 루트)."""
    vault = (vault_path or get_vault_path()).expanduser().resolve()
    return vault / SCHEMA_FILENAME


def write_schema(*, vault_path: Path | None = None) -> Path:
    """SCHEMA.md를 템플릿으로 (재)작성. 기존 파일 덮어씀."""
    path = schema_path(vault_path=vault_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(SCHEMA_TEMPLATE, encoding="utf-8")
    return path


def ensure_schema(*, vault_path: Path | None = None) -> Path:
    """SCHEMA.md가 없을 때만 작성. 사용자 편집 보존."""
    path = schema_path(vault_path=vault_path)
    if not path.is_file():
        write_schema(vault_path=vault_path)
    return path
