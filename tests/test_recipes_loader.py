"""T004 — Recipe loader RED tests.

Covers spec FR-015, FR-016, FR-019 + research R-2 frontmatter schema.

본 파일은 구현 (T010 loader.py) 이 등장하기 전 RED 상태여야 한다.
ImportError 또는 NotImplementedError 가 정상 RED.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest


def _write(p: Path, body: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
    return p


def test_loader_parses_valid_frontmatter(tmp_path: Path) -> None:
    from synapse_memory.recipes.loader import parse_recipe

    p = _write(
        tmp_path / "weekly_report.md",
        """
        ---
        name: weekly_report
        description: 주간 보고
        input_schema:
          period: required
        rag_filter:
          source_kind: card_project
        rag_top_k: 10
        rag_mode: hybrid
        use_profile: true
        save_subpath: 30_Creative/Reports
        locale_aware: true
        domain_aware: false
        timeout: 120
        ---

        당신은 주간 보고 어시스턴트. period={period}, locale={locale}.
        """,
    )
    recipe = parse_recipe(p, source="builtin")
    assert recipe.name == "weekly_report"
    assert recipe.description == "주간 보고"
    assert recipe.input_schema == {"period": "required"}
    assert recipe.rag_filter == {"source_kind": "card_project"}
    assert recipe.rag_top_k == 10
    assert recipe.rag_mode == "hybrid"
    assert recipe.use_profile is True
    assert recipe.save_subpath == "30_Creative/Reports"
    assert recipe.locale_aware is True
    assert recipe.domain_aware is False
    assert recipe.timeout == 120
    assert recipe.source == "builtin"
    assert recipe.source_path == p
    assert "{period}" in recipe.system_prompt


@pytest.mark.parametrize("mode", ["dense", "hybrid"])
def test_loader_accepts_valid_rag_mode(tmp_path: Path, mode: str) -> None:
    from synapse_memory.recipes.loader import parse_recipe

    p = _write(
        tmp_path / f"{mode}_recipe.md",
        f"""
        ---
        name: {mode}_recipe
        description: valid rag mode
        input_schema: {{}}
        rag_mode: {mode}
        ---

        body
        """,
    )
    recipe = parse_recipe(p, source="user")
    assert recipe.rag_mode == mode


def test_loader_defaults_missing_rag_mode_to_dense(tmp_path: Path) -> None:
    from synapse_memory.recipes.loader import parse_recipe

    p = _write(
        tmp_path / "default_dense.md",
        """
        ---
        name: default_dense
        description: no rag mode
        input_schema: {}
        ---

        body
        """,
    )
    recipe = parse_recipe(p, source="user")
    assert recipe.rag_mode == "dense"


def test_loader_rejects_invalid_rag_mode(tmp_path: Path) -> None:
    from synapse_memory.recipes.loader import RecipeValidationError, parse_recipe

    p = _write(
        tmp_path / "invalid_mode.md",
        """
        ---
        name: invalid_mode
        description: bad rag mode
        input_schema: {}
        rag_mode: keyword
        ---

        body
        """,
    )
    with pytest.raises(RecipeValidationError, match="rag_mode"):
        parse_recipe(p, source="user")


def test_loader_rejects_malformed_yaml(tmp_path: Path) -> None:
    from synapse_memory.recipes.loader import RecipeValidationError, parse_recipe

    p = _write(
        tmp_path / "broken.md",
        """
        ---
        name: broken
        description: bad yaml
        input_schema: : : :
        ---

        body
        """,
    )
    with pytest.raises(RecipeValidationError):
        parse_recipe(p, source="user")


def test_loader_rejects_missing_required_field(tmp_path: Path) -> None:
    from synapse_memory.recipes.loader import RecipeValidationError, parse_recipe

    p = _write(
        tmp_path / "no_name.md",
        """
        ---
        description: no name
        input_schema:
          topic: optional
        ---

        body
        """,
    )
    with pytest.raises(RecipeValidationError):
        parse_recipe(p, source="user")


def test_loader_ignores_unknown_frontmatter_fields(tmp_path: Path) -> None:
    """Q2 — unknown field MUST be ignored silently."""
    from synapse_memory.recipes.loader import parse_recipe

    p = _write(
        tmp_path / "with_unknown.md",
        """
        ---
        name: with_unknown
        description: has unknown field
        input_schema:
          topic: required
        future_field_we_dont_know_yet: hello
        ---

        body
        """,
    )
    recipe = parse_recipe(p, source="user")
    assert recipe.name == "with_unknown"


def test_loader_rejects_oversize_system_prompt(tmp_path: Path) -> None:
    """FR-016 / Q4 — 32KB UTF-8 cap."""
    from synapse_memory.recipes.loader import RecipeValidationError, parse_recipe

    big_body = "x" * 33_000  # > 32 KB
    p = _write(
        tmp_path / "huge.md",
        f"""
        ---
        name: huge
        description: too big
        input_schema: {{}}
        ---

        {big_body}
        """,
    )
    with pytest.raises(RecipeValidationError, match=r"32"):
        parse_recipe(p, source="user")


def test_loader_rejects_unsafe_save_subpath(tmp_path: Path) -> None:
    from synapse_memory.recipes.loader import RecipeValidationError, parse_recipe

    for unsafe in ("/abs/path", "../escape", "30_Creative/../../etc"):
        p = _write(
            tmp_path / "unsafe.md",
            f"""
            ---
            name: unsafe
            description: bad save_subpath
            input_schema: {{}}
            save_subpath: "{unsafe}"
            ---

            body
            """,
        )
        with pytest.raises(RecipeValidationError):
            parse_recipe(p, source="user")


def test_loader_name_validation(tmp_path: Path) -> None:
    """name MUST match ^[a-z][a-z0-9_]{0,63}$"""
    from synapse_memory.recipes.loader import RecipeValidationError, parse_recipe

    for bad in ("BadCaps", "1starts_with_digit", "has-dash", "with space"):
        p = _write(
            tmp_path / "bad_name.md",
            f"""
            ---
            name: {bad}
            description: bad name
            input_schema: {{}}
            ---

            body
            """,
        )
        with pytest.raises(RecipeValidationError):
            parse_recipe(p, source="user")
