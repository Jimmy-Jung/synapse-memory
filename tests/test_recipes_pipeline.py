"""T008 — pipeline.generate() RED tests.

Covers full construction order:
  inputs validate → profile → locale → RAG → domain → render → invoke → save → last_answer.

이 시점에는 pipeline 모듈이 없으므로 ImportError 가 RED 의 정상 상태.
GREEN 후에는 mocked ai_api 와 in-memory store 로 동작 검증.
"""

from __future__ import annotations

import datetime
import textwrap
from pathlib import Path
from typing import Any
from unittest import mock

import pytest


def _build_vault(tmp_path: Path, *, profile_fm: str = "") -> Path:
    """minimal vault with wiki profile page."""
    vault = tmp_path / "vault"
    profile_dir = vault / "Profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    profile_body = "이름: 테스트\n강점: 명료한 글쓰기\n"
    profile_text = profile_fm + profile_body if profile_fm else profile_body
    (profile_dir / "user-profile.md").write_text(profile_text, encoding="utf-8")
    return vault


def _builtin_recipe_dir(tmp_path: Path) -> Path:
    """Create a tiny builtin recipe dir with a simple `echo` recipe."""
    d = tmp_path / "builtin"
    d.mkdir(parents=True, exist_ok=True)
    (d / "echo.md").write_text(
        textwrap.dedent("""
        ---
        name: echo
        description: echo recipe for tests
        input_schema:
          topic: required
        rag_filter: null
        rag_top_k: 3
        use_profile: true
        save_subpath: 30_Creative/Echos
        locale_aware: true
        domain_aware: false
        timeout: 30
        ---

        당신은 echo. locale={locale}, domain={domain}, today={today}, topic={topic}.
        """).lstrip(),
        encoding="utf-8",
    )
    return d


def _builtin_recipe_dir_with_rag_mode(tmp_path: Path, rag_mode: str) -> Path:
    d = _builtin_recipe_dir(tmp_path)
    recipe_path = d / "echo.md"
    text = recipe_path.read_text(encoding="utf-8")
    text = text.replace("rag_top_k: 3\n", f"rag_top_k: 3\nrag_mode: {rag_mode}\n")
    recipe_path.write_text(text, encoding="utf-8")
    return d


def _builtin_recipe_dir_with_options(
    tmp_path: Path,
    *,
    rag_mode: str = "dense",
    domain_aware: bool = False,
) -> Path:
    d = _builtin_recipe_dir(tmp_path)
    recipe_path = d / "echo.md"
    text = recipe_path.read_text(encoding="utf-8")
    text = text.replace("rag_top_k: 3\n", f"rag_top_k: 3\nrag_mode: {rag_mode}\n")
    text = text.replace(
        "domain_aware: false\n",
        f"domain_aware: {str(domain_aware).lower()}\n",
    )
    recipe_path.write_text(text, encoding="utf-8")
    return d


class _StoreStub:
    def __init__(self, hits: list[tuple[Any, float]] | None = None) -> None:
        self._hits = hits or []
        self.queries: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def query(self, *_args: Any, **_kwargs: Any) -> list[tuple[Any, float]]:
        self.queries.append((_args, _kwargs))
        return list(self._hits)


def test_pipeline_generate_minimal_happy_path(tmp_path: Path) -> None:
    from synapse_memory.recipes.pipeline import generate

    vault = _build_vault(tmp_path)
    builtin = _builtin_recipe_dir(tmp_path)

    captured: dict[str, str] = {}

    def fake_complete(prompt: str, *, system: str | None = None, **_kw: Any) -> str:
        captured["prompt"] = prompt
        captured["system"] = system or ""
        return "## Hello\nEchoed result body"

    with mock.patch(
        "synapse_memory.recipes.pipeline.ai_api_complete",
        side_effect=fake_complete,
    ):
        result = generate(
            "echo",
            inputs={"topic": "테스트주제"},
            vault_path=vault,
            store=_StoreStub(),
            builtin_dir=builtin,
            today=datetime.date(2026, 5, 12),
        )

    assert result.recipe_name == "echo"
    assert "Echoed result body" in result.answer_markdown
    assert result.profile_used is True
    # placeholders 가 렌더된 system prompt
    assert "topic=테스트주제" in captured["system"]
    assert "today=2026-05-12" in captured["system"]
    assert "locale=한국어" in captured["system"]  # default
    # Profile body 가 user prompt 에 첨부됨
    assert "명료한 글쓰기" in captured["prompt"]
    # 저장 경로
    assert result.saved_path is not None
    assert result.saved_path.is_file()
    assert "30_Creative/Echos" in str(result.saved_path)


def test_pipeline_generate_missing_required_input_fails_fast(tmp_path: Path) -> None:
    """FR-014 — missing required input MUST fail before LLM call."""
    from synapse_memory.recipes.pipeline import InputValidationError, generate

    vault = _build_vault(tmp_path)
    builtin = _builtin_recipe_dir(tmp_path)

    with mock.patch("synapse_memory.recipes.pipeline.ai_api_complete") as mocked:
        with pytest.raises(InputValidationError, match="topic"):
            generate(
                "echo",
                inputs={},  # topic 누락
                vault_path=vault,
                store=_StoreStub(),
                builtin_dir=builtin,
            )
        mocked.assert_not_called()


def test_pipeline_generate_no_profile_sets_profile_used_false(tmp_path: Path) -> None:
    from synapse_memory.recipes.pipeline import generate

    vault = tmp_path / "vault"
    vault.mkdir()
    # Profile.md 없음 의도
    builtin = _builtin_recipe_dir(tmp_path)

    with mock.patch(
        "synapse_memory.recipes.pipeline.ai_api_complete",
        return_value="ok",
    ):
        result = generate(
            "echo",
            inputs={"topic": "x"},
            vault_path=vault,
            store=_StoreStub(),
            builtin_dir=builtin,
        )
    assert result.profile_used is False


def test_pipeline_generate_dry_run_skips_llm_and_save(tmp_path: Path) -> None:
    from synapse_memory.recipes.pipeline import generate

    vault = _build_vault(tmp_path)
    builtin = _builtin_recipe_dir(tmp_path)

    with mock.patch("synapse_memory.recipes.pipeline.ai_api_complete") as mocked:
        result = generate(
            "echo",
            inputs={"topic": "z"},
            vault_path=vault,
            store=_StoreStub(),
            builtin_dir=builtin,
            dry_run=True,
        )
        mocked.assert_not_called()
    assert result.saved_path is None
    # answer_markdown should expose rendered prompts (preview)
    assert "topic=z" in result.answer_markdown
    assert result.rag_mode == "dense"


def test_pipeline_provider_select_matches_loaded_as_entity_text(tmp_path: Path) -> None:
    """020 — provider 선별된 entity slug → full text 로드 → user prompt 합성."""
    from synapse_memory.cards.project import ProjectCard, ProjectMetric, save_project_card
    from synapse_memory.recipes.pipeline import generate

    vault = _build_vault(tmp_path)
    builtin = _builtin_recipe_dir(tmp_path)
    save_project_card(
        ProjectCard(
            project_id="hyb",
            display_name="Hybrid Project",
            status="active",
            period_start="2026-01",
            period_end="2026-03",
            metrics=[ProjectMetric(name="latency", before="2s", after="1s")],
            body="provider selected body",
        ),
        vault_path=vault,
    )

    captured: dict[str, str] = {}

    def fake_complete(prompt: str, **_kw: Any) -> str:
        captured["prompt"] = prompt
        return "ok"

    with mock.patch(
        "synapse_memory.recipes.pipeline.select_related", return_value=["hyb"]
    ) as mocked_select, mock.patch(
        "synapse_memory.recipes.pipeline.ai_api_complete", side_effect=fake_complete
    ):
        result = generate(
            "echo",
            inputs={"topic": "provider smoke"},
            vault_path=vault,
            builtin_dir=builtin,
        )

    mocked_select.assert_called_once()
    assert mocked_select.call_args.kwargs["max_pages"] == 3
    assert result.source_ids == ["hyb"]
    assert "기간: 2026-01 ~ 2026-03" in captured["prompt"]
    assert "latency: 2s -> 1s" in captured["prompt"]
    assert "provider selected body" in captured["prompt"]


def test_entity_text_preserves_company_typed_fields() -> None:
    from synapse_memory.cards.company import CompanyCard, JobPosition
    from synapse_memory.recipes.pipeline import entity_to_text

    text = entity_to_text(
        CompanyCard(
            company_id="acme",
            display_name="Acme",
            resume_language="en",
            positions=[
                JobPosition(
                    title="Staff iOS Engineer",
                    seniority="staff",
                    keywords=["Swift", "UIKit"],
                )
            ],
        )
    )
    assert "이력서 언어: en" in text
    assert "Staff iOS Engineer (staff; Swift, UIKit)" in text


def test_pipeline_provider_zero_selection_yields_no_matches(tmp_path: Path) -> None:
    """020 — provider 0건 선별 → matched 비어있음 (require_matched 시 ValueError)."""
    from synapse_memory.recipes.pipeline import generate

    vault = _build_vault(tmp_path)
    builtin = _builtin_recipe_dir(tmp_path)

    with mock.patch(
        "synapse_memory.recipes.pipeline.select_related", return_value=[]
    ), mock.patch(
        "synapse_memory.recipes.pipeline.ai_api_complete", return_value="ok"
    ):
        result = generate(
            "echo",
            inputs={"topic": "no match"},
            vault_path=vault,
            builtin_dir=builtin,
        )
    assert result.source_ids == []


def test_pipeline_generate_records_last_answer(tmp_path: Path) -> None:
    """FR-011 — every successful AI call updates last_answer."""
    from synapse_memory.recipes.pipeline import generate

    vault = _build_vault(tmp_path)
    builtin = _builtin_recipe_dir(tmp_path)

    save_calls: list[Any] = []

    def fake_save(ref: Any, **_kw: Any) -> Path:
        save_calls.append(ref)
        return tmp_path / "last_response.json"

    with mock.patch(
        "synapse_memory.recipes.pipeline.ai_api_complete",
        return_value="answer body",
    ), mock.patch(
        "synapse_memory.recipes.pipeline.save_last_answer",
        side_effect=fake_save,
    ):
        result = generate(
            "echo",
            inputs={"topic": "x"},
            vault_path=vault,
            store=_StoreStub(),
            builtin_dir=builtin,
        )
    assert len(save_calls) == 1
    ref = save_calls[0]
    assert ref.command == "persona.generate.echo"
    assert "x" in ref.query
    assert result.last_answer_ref is ref
