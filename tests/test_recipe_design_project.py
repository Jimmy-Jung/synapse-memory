"""M1c — design_project recipe end-to-end (mocked LLM).

검증 범위:
- recipe registry 가 design_project 로드
- Profile 내용이 LLM prompt 에 포함
- ProjectCard RAG hit 이 prompt 에 포함
- saved_path 가 20_Projects/Drafts 아래
- profile_used 플래그 (Profile 있으면 True, 없으면 False)
- input validation (idea 없으면 실패)

머지 조건 (plan):
- fixture vault (3 facts seed) → `[Profile:` 인용 ≥1 + "Swift" 등장 + "React"/"Flutter" 미등장
이 머지 조건은 mock LLM 으로는 "LLM 이 system prompt 를 따르는가" 자체를 검증할 수 없으므로
**system prompt 가 그 규칙을 명시하는지**, **fixture Profile 텍스트가 LLM 으로 전달되는지** 검증.
실사용 검증은 통합 단계 (사용자가 직접 호출) 에서 수행.

저자: Synapse Memory Maintainers
작성일: 2026-05-13
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from synapse_memory.recipes import (
    InputValidationError,
    generate,
)

_BUILTIN_DIR = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "synapse_memory"
    / "recipes"
    / "builtin"
)


def _make_vault(
    tmp_path: Path,
    *,
    profile_body: str | None = None,
) -> Path:
    """20_Projects/Drafts/ 및 wiki profile page 가 있는 최소 vault."""
    vault = tmp_path / "vault"
    (vault / "20_Projects" / "Drafts").mkdir(parents=True)
    (vault / "Profile").mkdir(parents=True)
    if profile_body is not None:
        (vault / "Profile" / "user-profile.md").write_text(
            profile_body, encoding="utf-8"
        )
    return vault


class _StoreStub:
    """RAG store stub — 고정된 ProjectCard 목록 반환."""

    def __init__(self, records: list[dict[str, Any]]) -> None:
        self._records = records

    def query(self, *_args: Any, **_kwargs: Any) -> list[tuple[Any, float]]:
        out: list[tuple[Any, float]] = []
        for i, meta in enumerate(self._records):
            rec = mock.Mock()
            rec.metadata = meta
            rec.document = meta.get("document", "")
            rec.id = meta.get("card_id", f"rec-{i}")
            out.append((rec, 0.10 + 0.01 * i))
        return out


PROFILE_WITH_TECH = """---
preferred_lang: 한국어
domain: software
---

# 사용자 Profile

## tech
- Swift+SwiftUI 주력 [conf 0.92]
- uv 로 Python 환경 관리 [conf 0.85]

## work_style
- 단계별 의사코드 후 코드 작성 [conf 0.88]

## voice
- 짧은 문장, 직설적 [conf 0.80]
"""


@pytest.fixture
def vault_with_profile(tmp_path: Path) -> Path:
    return _make_vault(tmp_path, profile_body=PROFILE_WITH_TECH)


@pytest.fixture
def vault_no_profile(tmp_path: Path) -> Path:
    return _make_vault(tmp_path, profile_body=None)


@pytest.fixture
def project_store() -> _StoreStub:
    return _StoreStub(
        [
            {
                "card_id": "prj-todo-ios-2025",
                "display_name": "iOS Todo 앱",
                "source_kind": "card_project",
                "document": "SwiftUI 기반 todo. CoreData 사용. 단계별 plan 으로 진행.",
            }
        ]
    )


def _fake_complete_designed_output(
    prompt: str, *, system: str | None = None, **_kw: Any
) -> str:
    """LLM 이 system prompt 의 규칙을 잘 따랐다고 가정한 출력."""
    return (
        "---\n"
        "title: iOS Todo 앱 프로젝트 설계\n"
        "generated: 2026-05-13\n"
        "language: 한국어\n"
        "domain: software\n"
        "based_on_profile: true\n"
        "based_on_cards:\n"
        "  - prj-todo-ios-2025\n"
        "---\n\n"
        "## 요약\n새 todo 앱을 본인 스타일로 빠르게 시작.\n\n"
        "## 추천 기술 스택\n"
        "- Swift + SwiftUI [Profile: tech]\n"
        "- CoreData 로컬 저장 [prj-todo-ios-2025]\n\n"
        "## 단계별 진행 [Profile: work_style]\n"
        "1. 의사코드로 데이터 모델 정리\n"
        "2. 화면 흐름 → 코드\n"
        "3. CoreData 통합\n"
    )


class TestDesignProjectRecipeWiring:
    def test_loads_and_executes(
        self,
        vault_with_profile: Path,
        project_store: _StoreStub,
    ) -> None:
        """recipe registry 에서 design_project 로딩 + 실행 성공."""
        with mock.patch(
            "synapse_memory.recipes.pipeline.ai_api_complete",
            side_effect=_fake_complete_designed_output,
        ), mock.patch(
            "synapse_memory.recipes.pipeline.save_last_answer",
            return_value=vault_with_profile / "fake_last.json",
        ):
            result = generate(
                "design_project",
                inputs={"idea": "iOS Todo 앱"},
                vault_path=vault_with_profile,
                store=project_store,
                builtin_dir=_BUILTIN_DIR,
            )

        assert result.recipe_name == "design_project"
        assert result.profile_used is True
        assert result.saved_path is not None
        assert result.saved_path.is_file()

    def test_save_path_under_drafts(
        self,
        vault_with_profile: Path,
        project_store: _StoreStub,
    ) -> None:
        with mock.patch(
            "synapse_memory.recipes.pipeline.ai_api_complete",
            side_effect=_fake_complete_designed_output,
        ), mock.patch(
            "synapse_memory.recipes.pipeline.save_last_answer",
            return_value=vault_with_profile / "fake_last.json",
        ):
            result = generate(
                "design_project",
                inputs={"idea": "iOS Todo 앱"},
                vault_path=vault_with_profile,
                store=project_store,
                builtin_dir=_BUILTIN_DIR,
            )

        assert result.saved_path is not None
        assert "20_Projects/Drafts" in str(result.saved_path), (
            f"saved_path must be under 20_Projects/Drafts, got {result.saved_path}"
        )


class TestDesignProjectPromptContents:
    def test_profile_text_reaches_llm(
        self,
        vault_with_profile: Path,
        project_store: _StoreStub,
    ) -> None:
        """fixture Profile 내용이 LLM user prompt 에 그대로 포함 (provider 선별)."""
        from synapse_memory.cards.project import ProjectCard, save_project_card

        save_project_card(
            ProjectCard(
                project_id="prj-todo-ios-2025",
                display_name="iOS Todo 앱",
                status="active",
                body="SwiftUI 기반 todo. CoreData 사용. 단계별 plan 으로 진행.",
            ),
            vault_path=vault_with_profile,
        )

        captured: dict[str, str] = {}

        def capture(prompt: str, *, system: str | None = None, **_kw: Any) -> str:
            captured["prompt"] = prompt
            captured["system"] = system or ""
            return _fake_complete_designed_output(prompt, system=system, **_kw)

        with mock.patch(
            "synapse_memory.recipes.pipeline.ai_api_complete",
            side_effect=capture,
        ), mock.patch(
            "synapse_memory.recipes.pipeline.select_related",
            return_value=["prj-todo-ios-2025"],
        ), mock.patch(
            "synapse_memory.recipes.pipeline.save_last_answer",
            return_value=vault_with_profile / "fake_last.json",
        ):
            generate(
                "design_project",
                inputs={"idea": "iOS Todo 앱"},
                vault_path=vault_with_profile,
                builtin_dir=_BUILTIN_DIR,
            )

        # Profile 의 핵심 키워드들이 prompt 에 포함
        assert "Swift+SwiftUI 주력" in captured["prompt"], (
            "Profile tech fact 가 LLM 으로 전달되어야 함"
        )
        assert "단계별 의사코드" in captured["prompt"]
        assert "짧은 문장" in captured["prompt"]
        # ProjectCard RAG hit 도 포함
        assert "prj-todo-ios-2025" in captured["prompt"]
        # idea input 도 포함
        assert "iOS Todo 앱" in captured["prompt"]

    def test_system_prompt_enforces_profile_citation(
        self,
        vault_with_profile: Path,
        project_store: _StoreStub,
    ) -> None:
        """system prompt 가 [Profile: <category>] 인용 규칙을 명시해야 한다."""
        captured: dict[str, str] = {}

        def capture(prompt: str, *, system: str | None = None, **_kw: Any) -> str:
            captured["system"] = system or ""
            return _fake_complete_designed_output(prompt, system=system, **_kw)

        with mock.patch(
            "synapse_memory.recipes.pipeline.ai_api_complete",
            side_effect=capture,
        ), mock.patch(
            "synapse_memory.recipes.pipeline.save_last_answer",
            return_value=vault_with_profile / "fake_last.json",
        ):
            generate(
                "design_project",
                inputs={"idea": "iOS Todo 앱"},
                vault_path=vault_with_profile,
                store=project_store,
                builtin_dir=_BUILTIN_DIR,
            )

        # 머지 조건: system prompt 가 인용 규칙을 강제하는지
        assert "[Profile:" in captured["system"], (
            "system prompt 가 [Profile: <category>] 인용 규칙을 명시해야 함"
        )
        # 사용자가 안 쓰는 기술 도입 금지 규칙
        assert (
            "안 쓰는 기술 도입 금지" in captured["system"]
            or "프레임워크" in captured["system"]
        ), "system prompt 가 비사용 기술 도입 금지 규칙을 포함해야 함"

    def test_idea_input_required(
        self,
        vault_with_profile: Path,
    ) -> None:
        """idea 입력 없으면 InputValidationError."""
        with pytest.raises(InputValidationError):
            generate(
                "design_project",
                inputs={},
                vault_path=vault_with_profile,
                store=None,
                builtin_dir=_BUILTIN_DIR,
            )


class TestDesignProjectProfileEmpty:
    def test_profile_used_false_when_no_profile(
        self,
        vault_no_profile: Path,
        project_store: _StoreStub,
    ) -> None:
        """Profile.md 없으면 profile_used=False — CLI 가 nudge 메시지 출력 가능."""
        with mock.patch(
            "synapse_memory.recipes.pipeline.ai_api_complete",
            side_effect=_fake_complete_designed_output,
        ), mock.patch(
            "synapse_memory.recipes.pipeline.save_last_answer",
            return_value=vault_no_profile / "fake_last.json",
        ):
            result = generate(
                "design_project",
                inputs={"idea": "iOS Todo 앱"},
                vault_path=vault_no_profile,
                store=project_store,
                builtin_dir=_BUILTIN_DIR,
            )

        assert result.profile_used is False
