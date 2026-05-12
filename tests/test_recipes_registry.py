"""T005 — RecipeRegistry RED tests.

Covers spec FR-003, FR-010, FR-015 + research R-2.

stateless fresh scan, user-over-builtin, malformed isolation, suggestion list.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest


def _write(p: Path, body: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
    return p


def _builtin_recipe(builtin_dir: Path, name: str, description: str = "...") -> Path:
    return _write(
        builtin_dir / f"{name}.md",
        f"""
        ---
        name: {name}
        description: {description}
        input_schema:
          topic: optional
        ---

        builtin system prompt for {name}
        """,
    )


def _user_recipe(user_dir: Path, name: str, description: str = "...") -> Path:
    return _write(
        user_dir / f"{name}.md",
        f"""
        ---
        name: {name}
        description: {description}
        input_schema:
          topic: optional
        ---

        user system prompt for {name}
        """,
    )


def test_registry_scans_builtin_only_when_user_dir_missing(tmp_path: Path) -> None:
    from synapse_memory.recipes.registry import RecipeRegistry

    builtin = tmp_path / "builtin"
    _builtin_recipe(builtin, "weekly_report")
    _builtin_recipe(builtin, "journal")

    user = tmp_path / "vault" / "90_System" / "AI" / "recipes"  # 미존재 OK
    reg = RecipeRegistry(builtin_dir=builtin, user_dir=user)
    reg.scan()
    assert set(reg.recipes.keys()) == {"weekly_report", "journal"}
    assert all(r.source == "builtin" for r in reg.recipes.values())


def test_registry_user_overrides_builtin(tmp_path: Path) -> None:
    from synapse_memory.recipes.registry import RecipeRegistry

    builtin = tmp_path / "builtin"
    user = tmp_path / "user"
    _builtin_recipe(builtin, "journal", description="builtin journal")
    _user_recipe(user, "journal", description="user override journal")

    reg = RecipeRegistry(builtin_dir=builtin, user_dir=user)
    reg.scan()
    j = reg.get("journal")
    assert j.source == "user"
    assert j.description == "user override journal"


def test_registry_lists_recipes_alphabetically(tmp_path: Path) -> None:
    from synapse_memory.recipes.registry import RecipeRegistry

    builtin = tmp_path / "builtin"
    _builtin_recipe(builtin, "weekly_report")
    _builtin_recipe(builtin, "brainstorm")
    _builtin_recipe(builtin, "journal")

    reg = RecipeRegistry(builtin_dir=builtin, user_dir=tmp_path / "user")
    reg.scan()
    names = [r.name for r in reg.list()]
    assert names == sorted(names)
    assert names == ["brainstorm", "journal", "weekly_report"]


def test_registry_get_unknown_suggests_close_names(tmp_path: Path) -> None:
    from synapse_memory.recipes.registry import RecipeNotFoundError, RecipeRegistry

    builtin = tmp_path / "builtin"
    _builtin_recipe(builtin, "weekly_report")
    _builtin_recipe(builtin, "journal")
    _builtin_recipe(builtin, "brainstorm")

    reg = RecipeRegistry(builtin_dir=builtin, user_dir=tmp_path / "user")
    reg.scan()
    with pytest.raises(RecipeNotFoundError) as exc:
        reg.get("weekly")  # typo
    assert "weekly_report" in exc.value.suggestions
    assert len(exc.value.suggestions) <= 3


def test_registry_malformed_user_recipe_isolated(tmp_path: Path) -> None:
    """spec FR-015 — malformed recipe MUST NOT block other recipes."""
    from synapse_memory.recipes.registry import RecipeRegistry

    builtin = tmp_path / "builtin"
    user = tmp_path / "user"
    _builtin_recipe(builtin, "weekly_report")
    _user_recipe(user, "diary")
    # malformed: invalid yaml
    _write(
        user / "broken.md",
        """
        ---
        name: broken
        invalid: : :
        ---
        body
        """,
    )

    reg = RecipeRegistry(builtin_dir=builtin, user_dir=user)
    reg.scan()
    assert "diary" in reg.recipes
    assert "weekly_report" in reg.recipes
    assert "broken" not in reg.recipes
    assert any("broken" in str(path) for path, _ in reg.skipped)


def test_registry_scan_is_stateless_per_instance(tmp_path: Path) -> None:
    """Q5 — each RecipeRegistry instance does a fresh scan; new files appear."""
    from synapse_memory.recipes.registry import RecipeRegistry

    builtin = tmp_path / "builtin"
    user = tmp_path / "user"
    _builtin_recipe(builtin, "weekly_report")

    reg1 = RecipeRegistry(builtin_dir=builtin, user_dir=user)
    reg1.scan()
    assert "diary" not in reg1.recipes

    # add user recipe mid-test
    _user_recipe(user, "diary")

    reg2 = RecipeRegistry(builtin_dir=builtin, user_dir=user)
    reg2.scan()
    assert "diary" in reg2.recipes
