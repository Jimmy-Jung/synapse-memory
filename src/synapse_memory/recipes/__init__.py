"""Me Generator Recipes — markdown-recipe based generator framework.

Public API:
    - ``generate(recipe_name, inputs=…, …)`` — single orchestrator entry point.
    - ``RecipeRegistry`` — builtin + user recipe scanner.
    - ``GenerationRecipe`` / ``GenerationResult`` / ``GenerationContext`` — data model.
    - Errors: ``RecipeNotFoundError``, ``RecipeValidationError``, ``InputValidationError``.

Spec: ``specs/007-persona-recipes/spec.md``
Plan: ``specs/007-persona-recipes/plan.md``

저자: Synapse Memory Maintainers
작성일: 2026-05-12
"""

from __future__ import annotations

from synapse_memory.recipes.loader import RecipeValidationError
from synapse_memory.recipes.pipeline import (
    InputValidationError,
    RecipePromptTooLargeError,
    generate,
)
from synapse_memory.recipes.recipe import (
    GenerationContext,
    GenerationRecipe,
    GenerationResult,
)
from synapse_memory.recipes.registry import RecipeNotFoundError, RecipeRegistry

__all__ = [
    "GenerationContext",
    "GenerationRecipe",
    "GenerationResult",
    "InputValidationError",
    "RecipeNotFoundError",
    "RecipePromptTooLargeError",
    "RecipeRegistry",
    "RecipeValidationError",
    "generate",
]
