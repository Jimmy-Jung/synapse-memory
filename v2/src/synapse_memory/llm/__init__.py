"""로컬/원격 LLM 호출 레이어.

- apfel : Apple FoundationModels (로컬, redaction/분류/태깅)
- claude: Claude Code CLI subprocess (원격, 합성/추론, --bare 모드).
          **redacted 입력만 허용.** API key 별도 발급 불필요 — 사용자 Claude Code 인증 그대로.
"""

from synapse_memory.llm import claude as claude_api
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
    estimate_tokens,
)
from synapse_memory.llm.claude import (
    ClaudeEnvironment,
    ClaudeError,
    ClaudeUnavailableError,
    detect_claude_environment,
)

__all__ = [
    "ApfelEnvironment",
    "ApfelError",
    "ApfelUnavailableError",
    "ClaudeEnvironment",
    "ClaudeError",
    "ClaudeUnavailableError",
    "chunk_by_paragraph",
    "claude_api",
    "complete",
    "complete_json",
    "complete_structured",
    "complete_with_input",
    "detect_claude_environment",
    "detect_environment",
    "estimate_tokens",
]
