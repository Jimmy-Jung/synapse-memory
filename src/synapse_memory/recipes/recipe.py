"""Recipe dataclasses — GenerationRecipe / GenerationContext / GenerationResult.

Spec: ``specs/007-me-recipes/data-model.md`` §1-§4.

본 모듈은 transient (in-memory) 데이터 모델만 정의한다. 영속 상태는
loader / registry / pipeline 이 다룬다.

저자: JunyoungJung <joony300@gmail.com>
작성일: 2026-05-12
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

RecipeSource = Literal["builtin", "user"]
InputRequirement = Literal["required", "optional"]
LocaleSource = Literal["cli", "company_card", "profile", "default"]
DomainSource = Literal["cli", "profile", "tags", "default"]


@dataclass(frozen=True)
class GenerationRecipe:
    """Recipe markdown 한 장의 파싱 결과 (data-model.md §1)."""

    name: str
    description: str
    source: RecipeSource
    source_path: Path
    input_schema: dict[str, InputRequirement]
    system_prompt: str
    rag_filter: dict[str, str] | None = None
    rag_top_k: int = 8
    use_profile: bool = True
    save_subpath: str | None = None
    locale_aware: bool = True
    domain_aware: bool = False
    timeout: int = 120
    model: str = "sonnet"

    @property
    def required_inputs(self) -> tuple[str, ...]:
        return tuple(k for k, v in self.input_schema.items() if v == "required")

    @property
    def optional_inputs(self) -> tuple[str, ...]:
        return tuple(k for k, v in self.input_schema.items() if v == "optional")


@dataclass
class GenerationContext:
    """단일 generate() 호출 동안의 working state (data-model.md §3)."""

    recipe: GenerationRecipe
    inputs: dict[str, str]
    profile_text: str
    profile_used: bool
    locale: str
    locale_source: LocaleSource
    domain: str
    domain_source: DomainSource
    matched_records: list[tuple[Any, float]]
    today: datetime.date
    rendered_system_prompt: str = ""
    rendered_user_prompt: str = ""


@dataclass(frozen=True)
class GenerationResult:
    """generate() 의 return value (data-model.md §4)."""

    recipe_name: str
    answer_markdown: str
    saved_path: Path | None
    source_ids: list[str] = field(default_factory=list)
    profile_used: bool = False
    locale: str = "한국어"
    locale_source: LocaleSource = "default"
    domain: str = "generic"
    domain_source: DomainSource = "default"
    last_answer_ref: Any = None  # storage.last_response.LastAnswerReference | None
