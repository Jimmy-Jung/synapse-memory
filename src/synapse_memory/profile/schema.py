"""ProfileFact / DecisionPattern 데이터 모델.

저자: Synapse Memory Maintainers
작성일: 2026-05-10
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Profile 카테고리 — 안정적 사용자 성향
PROFILE_CATEGORIES: tuple[str, ...] = (
    "work_style",   # 작업 방식 (예: "단계별 의사코드 후 코드")
    "preference",   # 선호 (예: "한국어 응답, 간결")
    "strength",     # 강점
    "weakness",     # 약점/회피 영역
    "tech",         # 기술 스택/도구 선호
    "interest",     # 관심사/도메인
    "workflow",     # 워크플로 패턴
    "value",        # 가치관 (예: "성능보다 가독성 우선")
    "voice",        # 말투/문장 길이/표현 선호·금지 (예: "짧은 문장, 직설적, 한국어 우선")
)


@dataclass(frozen=True)
class ProfileFact:
    """사용자에 대한 안정적 사실. raw에서 반복 패턴으로 추출."""

    category: str
    statement: str
    confidence: float
    source_ids: list[str] = field(default_factory=list)
    extracted_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "statement": self.statement,
            "confidence": self.confidence,
            "source_ids": list(self.source_ids),
            "extracted_at": self.extracted_at,
        }


@dataclass(frozen=True)
class DecisionPattern:
    """의사결정 트리거 → 행동 → 이유 패턴."""

    trigger: str
    action: str
    rationale: str
    confidence: float
    examples: list[str] = field(default_factory=list)
    extracted_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "trigger": self.trigger,
            "action": self.action,
            "rationale": self.rationale,
            "confidence": self.confidence,
            "examples": list(self.examples),
            "extracted_at": self.extracted_at,
        }
