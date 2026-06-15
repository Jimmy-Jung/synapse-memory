"""원격 LLM 호출 레이어.

- ai_api: Claude/Codex runtime facade (원격, 합성/추론).
- claude/codex: concrete CLI adapters.
- tokens: provider-neutral 토큰 추정 휴리스틱.
"""

from synapse_memory.llm import ai_api
from synapse_memory.llm.ai_api import (
    AIEnvironment,
    AIError,
    AIUnavailableError,
    detect_ai_environment,
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
    "ClaudeEnvironment",
    "ClaudeError",
    "ClaudeUnavailableError",
    "CodexEnvironment",
    "CodexError",
    "CodexUnavailableError",
    "ai_api",
    "detect_ai_environment",
    "detect_claude_environment",
    "detect_codex_environment",
    "estimate_tokens",
]
