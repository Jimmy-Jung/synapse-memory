"""Redaction — PII 제거 / 마스킹.

3-pass 아키텍처:
    Pass 1 (이 모듈)  결정적 regex/validator 기반. 빠르고 false-positive 적음.
    Pass 2            apfel(로컬 LLM) 맥락 검토 — 자유형 PII (이름, 주소 등).
    Pass 3            사용자 5분 다이제스트 검토 — 예외만.

cloud LLM(Claude 등)에 전달하기 전에 반드시 Pass 1+2를 통과시킨다.

저자: Synapse Memory Maintainers
"""

from synapse_memory.redaction.pass1 import (
    Detection,
    RedactionResult,
    redact,
)
from synapse_memory.redaction.pass2 import (
    PASS2_CATEGORIES,
    PASS2_PLACEHOLDERS,
    load_allowlist,
    redact_full,
)
from synapse_memory.redaction.patterns import (
    DEFAULT_PATTERNS,
    Pattern,
    is_valid_ipv4,
    is_valid_luhn,
    is_valid_rrn,
)
from synapse_memory.redaction.redactlist import (
    add_redactlist_item,
    build_redactlist_patterns,
    load_redactlist,
    remove_redactlist_item,
    write_redactlist,
)

__all__ = [
    "DEFAULT_PATTERNS",
    "Detection",
    "PASS2_CATEGORIES",
    "PASS2_PLACEHOLDERS",
    "Pattern",
    "RedactionResult",
    "add_redactlist_item",
    "build_redactlist_patterns",
    "is_valid_ipv4",
    "is_valid_luhn",
    "is_valid_rrn",
    "load_allowlist",
    "load_redactlist",
    "redact",
    "redact_full",
    "remove_redactlist_item",
    "write_redactlist",
]
