"""로컬/원격 LLM 호출 레이어.

- apfel : Apple FoundationModels (로컬, redaction/분류/태깅)
- ai_api: Claude/Codex runtime facade (원격, 합성/추론).
- claude/codex: concrete CLI adapters.
"""

from synapse_memory.llm import ai_api
from synapse_memory.llm.ai_api import (
    AIEnvironment,
    AIError,
    AIUnavailableError,
    detect_ai_environment,
)
from synapse_memory.llm.apfel import (
    ApfelEnvironment,
    ApfelError,
    ApfelUnavailableError,
    chunk_by_paragraph,
    complete,
    complete_json,
    complete_structured,
    complete_with_input,
    detect_environment,
)
from synapse_memory.llm.claude import (
    ClaudeEnvironment,
    ClaudeError,
    ClaudeUnavailableError,
    detect_claude_environment,
)
from synapse_memory.llm.codex import (
    CodexEnvironment,
    CodexError,
    CodexUnavailableError,
    detect_codex_environment,
)
from synapse_memory.llm.tokens import estimate_tokens

__all__ = [
    "AIEnvironment",
    "AIError",
    "AIUnavailableError",
    "ApfelEnvironment",
    "ApfelError",
    "ApfelUnavailableError",
    "ClaudeEnvironment",
    "ClaudeError",
    "ClaudeUnavailableError",
    "CodexEnvironment",
    "CodexError",
    "CodexUnavailableError",
    "ai_api",
    "chunk_by_paragraph",
    "complete",
    "complete_json",
    "complete_structured",
    "complete_with_input",
    "detect_ai_environment",
    "detect_claude_environment",
    "detect_codex_environment",
    "detect_environment",
    "estimate_tokens",
]
