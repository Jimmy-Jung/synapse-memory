"""RecipeRegistry — stateless scan of builtin + user recipe directories.

Spec: ``specs/007-me-recipes/spec.md`` FR-003, FR-010, FR-015
Research: ``specs/007-me-recipes/research.md`` R-7 (out of scope: daemon mode)

저자: JunyoungJung <joony300@gmail.com>
작성일: 2026-05-12
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from pathlib import Path

from synapse_memory.recipes.loader import RecipeValidationError, parse_recipe
from synapse_memory.recipes.recipe import GenerationRecipe, RecipeSource


class RecipeNotFoundError(LookupError):
    """``RecipeRegistry.get`` 에서 이름이 없을 때. 가까운 후보 ≤3 개 제공."""

    def __init__(self, name: str, suggestions: list[str]):
        self.name = name
        self.suggestions = suggestions
        msg = f"recipe '{name}' not found"
        if suggestions:
            msg += f". 가까운 후보: {', '.join(suggestions)}"
        super().__init__(msg)


@dataclass
class RecipeRegistry:
    """builtin + user recipe 디렉터리를 스캔해서 name → recipe 로 보유."""

    builtin_dir: Path
    user_dir: Path
    recipes: dict[str, GenerationRecipe] = field(default_factory=dict)
    skipped: list[tuple[Path, str]] = field(default_factory=list)

    def scan(self) -> None:
        """양쪽 디렉터리 fresh scan. 호출마다 ``recipes`` / ``skipped`` 재계산."""
        self.recipes.clear()
        self.skipped.clear()

        # builtin 먼저 → user 가 덮어쓰는 구조 (FR-003)
        self._load_dir(self.builtin_dir, source="builtin")
        self._load_dir(self.user_dir, source="user")

    def _load_dir(self, directory: Path, *, source: RecipeSource) -> None:
        if not directory.is_dir():
            return
        for path in sorted(directory.glob("*.md")):
            try:
                recipe = parse_recipe(path, source=source)
            except RecipeValidationError as exc:
                self.skipped.append((path, str(exc)))
                continue
            # 사용자 recipe 가 빌트인 이름과 충돌 → 사용자 우선
            self.recipes[recipe.name] = recipe

    def get(self, name: str) -> GenerationRecipe:
        if name in self.recipes:
            return self.recipes[name]
        suggestions = difflib.get_close_matches(
            name, list(self.recipes.keys()), n=3, cutoff=0.5
        )
        raise RecipeNotFoundError(name, suggestions)

    def list(self) -> list[GenerationRecipe]:
        """name 알파벳 순으로 정렬된 recipe list."""
        return [self.recipes[k] for k in sorted(self.recipes.keys())]
