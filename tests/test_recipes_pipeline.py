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
    """minimal vault with Profile.md + 1 ProjectCard."""
    vault = tmp_path / "vault"
    profile_dir = vault / "90_System" / "AI"
    profile_dir.mkdir(parents=True, exist_ok=True)
    profile_body = "이름: 테스트\n강점: 명료한 글쓰기\n"
    profile_text = profile_fm + profile_body if profile_fm else profile_body
    (profile_dir / "Profile.md").write_text(profile_text, encoding="utf-8")
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


def test_pipeline_result_reports_recipe_rag_mode(tmp_path: Path) -> None:
    from synapse_memory.recipes.pipeline import generate

    vault = _build_vault(tmp_path)
    builtin = _builtin_recipe_dir_with_rag_mode(tmp_path, "hybrid")

    with mock.patch("synapse_memory.recipes.pipeline.embed_query", return_value=[0.1]), mock.patch(
        "synapse_memory.recipes.pipeline.hybrid_search",
        return_value=[],
    ), mock.patch("synapse_memory.recipes.pipeline.ai_api_complete") as mocked:
        result = generate(
            "echo",
            inputs={"topic": "z"},
            vault_path=vault,
            store=_StoreStub(),
            builtin_dir=builtin,
            dry_run=True,
        )
        mocked.assert_not_called()

    assert result.rag_mode == "hybrid"


def test_pipeline_generate_embeds_dense_rag_query_before_store_query(tmp_path: Path) -> None:
    """Actual VectorStore requires a dense embedding, not ``None``."""
    from synapse_memory.recipes.pipeline import generate

    vault = _build_vault(tmp_path)
    builtin = _builtin_recipe_dir(tmp_path)
    store = _StoreStub()

    with mock.patch(
        "synapse_memory.recipes.pipeline.embed_query",
        return_value=[0.1, 0.2, 0.3],
    ) as mocked_embed, mock.patch(
        "synapse_memory.recipes.pipeline.ai_api_complete",
        return_value="ok",
    ):
        generate(
            "echo",
            inputs={"topic": "dense query smoke"},
            vault_path=vault,
            store=store,
            builtin_dir=builtin,
            dry_run=True,
        )

    mocked_embed.assert_called_once()
    assert "dense query smoke" in mocked_embed.call_args.args[0]
    assert store.queries
    assert store.queries[0][0][0] == [0.1, 0.2, 0.3]
    assert store.queries[0][1]["top_k"] == 3


def test_pipeline_dense_allows_query_owned_stub_without_embedding(tmp_path: Path) -> None:
    from synapse_memory.rag.embeddings import EmbeddingUnavailableError
    from synapse_memory.recipes.pipeline import generate

    vault = _build_vault(tmp_path)
    builtin = _builtin_recipe_dir(tmp_path)
    store = _StoreStub()

    with mock.patch(
        "synapse_memory.recipes.pipeline.embed_query",
        side_effect=EmbeddingUnavailableError("missing sentence-transformers"),
    ):
        result = generate(
            "echo",
            inputs={"topic": "stub query"},
            vault_path=vault,
            store=store,
            builtin_dir=builtin,
            dry_run=True,
        )

    assert result.rag_mode == "dense"
    assert store.queries == [((), {})]


def test_pipeline_generate_hybrid_uses_hybrid_search_and_adapts_hits(
    tmp_path: Path,
) -> None:
    from synapse_memory.rag.hybrid import RetrievalHit
    from synapse_memory.rag.vector_store import VectorRecord
    from synapse_memory.recipes.pipeline import generate

    vault = _build_vault(tmp_path)
    builtin = _builtin_recipe_dir_with_options(tmp_path, rag_mode="hybrid")
    store = _StoreStub()
    record = VectorRecord(
        id="card_project:hyb",
        document="Hybrid matched document with [EMAIL_1]",
        embedding=[],
        metadata={
            "source_kind": "card_project",
            "card_id": "hyb",
            "display_name": "Hybrid Project",
        },
    )

    with mock.patch(
        "synapse_memory.recipes.pipeline.embed_query",
        return_value=[0.4, 0.5],
    ), mock.patch(
        "synapse_memory.recipes.pipeline.hybrid_search",
        return_value=[
            RetrievalHit(
                record=record,
                dense_rank=2,
                dense_distance=0.4,
                bm25_rank=1,
                bm25_score=3.0,
                rrf_score=0.03,
            )
        ],
    ) as mocked_hybrid:
        result = generate(
            "echo",
            inputs={"topic": "hybrid smoke"},
            vault_path=vault,
            store=store,
            builtin_dir=builtin,
            dry_run=True,
        )

    mocked_hybrid.assert_called_once()
    assert mocked_hybrid.call_args.kwargs["store"] is store
    assert mocked_hybrid.call_args.kwargs["top_k"] == 3
    assert mocked_hybrid.call_args.kwargs["where"] is None
    assert result.source_ids == ["hyb"]
    assert "Hybrid matched document" in result.answer_markdown
    assert "[EMAIL_1]" in result.answer_markdown
    assert result.rag_mode == "hybrid"


def test_pipeline_generate_hybrid_preserves_domain_tags(tmp_path: Path) -> None:
    from synapse_memory.rag.hybrid import RetrievalHit
    from synapse_memory.rag.vector_store import VectorRecord
    from synapse_memory.recipes.pipeline import generate

    vault = _build_vault(tmp_path)
    builtin = _builtin_recipe_dir_with_options(
        tmp_path,
        rag_mode="hybrid",
        domain_aware=True,
    )
    record = VectorRecord(
        id="card_project:domain",
        document="domain aware document",
        embedding=[],
        metadata={
            "source_kind": "card_project",
            "card_id": "domain",
            "display_name": "Domain Project",
            "tags": ["software"],
        },
    )

    with mock.patch(
        "synapse_memory.recipes.pipeline.embed_query",
        return_value=[0.1],
    ), mock.patch(
        "synapse_memory.recipes.pipeline.hybrid_search",
        return_value=[
            RetrievalHit(
                record=record,
                dense_rank=None,
                dense_distance=None,
                bm25_rank=1,
                bm25_score=2.0,
                rrf_score=0.02,
            )
        ],
    ):
        result = generate(
            "echo",
            inputs={"topic": "domain"},
            vault_path=vault,
            store=_StoreStub(),
            builtin_dir=builtin,
            dry_run=True,
        )

    assert result.domain == "software"
    assert result.domain_source == "tags"


def test_pipeline_rag_mode_override_dense_wins_over_hybrid_recipe(tmp_path: Path) -> None:
    from synapse_memory.recipes.pipeline import generate

    vault = _build_vault(tmp_path)
    builtin = _builtin_recipe_dir_with_options(tmp_path, rag_mode="hybrid")
    store = _StoreStub()

    with mock.patch(
        "synapse_memory.recipes.pipeline.embed_query",
        return_value=[0.1],
    ), mock.patch("synapse_memory.recipes.pipeline.hybrid_search") as mocked_hybrid:
        result = generate(
            "echo",
            inputs={"topic": "override"},
            vault_path=vault,
            store=store,
            builtin_dir=builtin,
            dry_run=True,
            rag_mode_override="dense",
        )

    mocked_hybrid.assert_not_called()
    assert store.queries
    assert result.rag_mode == "dense"


def test_pipeline_rag_mode_override_hybrid_wins_over_dense_recipe(tmp_path: Path) -> None:
    from synapse_memory.rag.hybrid import RetrievalHit
    from synapse_memory.rag.vector_store import VectorRecord
    from synapse_memory.recipes.pipeline import generate

    vault = _build_vault(tmp_path)
    builtin = _builtin_recipe_dir_with_options(tmp_path, rag_mode="dense")
    record = VectorRecord(
        id="card_project:override",
        document="override hybrid document",
        embedding=[],
        metadata={"source_kind": "card_project", "card_id": "override"},
    )

    with mock.patch(
        "synapse_memory.recipes.pipeline.embed_query",
        return_value=[0.1],
    ), mock.patch(
        "synapse_memory.recipes.pipeline.hybrid_search",
        return_value=[
            RetrievalHit(
                record=record,
                dense_rank=1,
                dense_distance=0.1,
                bm25_rank=None,
                bm25_score=None,
                rrf_score=0.01,
            )
        ],
    ) as mocked_hybrid:
        result = generate(
            "echo",
            inputs={"topic": "override"},
            vault_path=vault,
            store=_StoreStub(),
            builtin_dir=builtin,
            dry_run=True,
            rag_mode_override="hybrid",
        )

    mocked_hybrid.assert_called_once()
    assert result.source_ids == ["override"]
    assert result.rag_mode == "hybrid"


def test_pipeline_hybrid_unavailable_error_mentions_reindex(tmp_path: Path) -> None:
    from synapse_memory.rag.bm25 import BM25IndexError
    from synapse_memory.recipes.pipeline import RecipeHybridUnavailableError, generate

    vault = _build_vault(tmp_path)
    builtin = _builtin_recipe_dir_with_options(tmp_path, rag_mode="hybrid")
    store = _StoreStub()

    with mock.patch(
        "synapse_memory.recipes.pipeline.embed_query",
        return_value=[0.1],
    ), mock.patch(
        "synapse_memory.recipes.pipeline.hybrid_search",
        side_effect=BM25IndexError("BM25 sidecar 없음"),
    ), pytest.raises(RecipeHybridUnavailableError, match="rag index --include-raw"):
        generate(
            "echo",
            inputs={"topic": "missing sidecar"},
            vault_path=vault,
            store=store,
            builtin_dir=builtin,
            dry_run=True,
        )

    assert store.queries == []


def test_pipeline_hybrid_requires_available_store(tmp_path: Path) -> None:
    from synapse_memory.recipes.pipeline import RecipeHybridUnavailableError, generate

    vault = _build_vault(tmp_path)
    builtin = _builtin_recipe_dir_with_options(tmp_path, rag_mode="hybrid")

    with pytest.raises(RecipeHybridUnavailableError, match="rag index --include-raw"):
        generate(
            "echo",
            inputs={"topic": "missing vector store"},
            vault_path=vault,
            store=None,
            builtin_dir=builtin,
            dry_run=True,
        )


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
    assert ref.command == "me.generate.echo"
    assert "x" in ref.query
    assert result.last_answer_ref is ref
