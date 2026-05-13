"""Profile / DecisionPatterns 자동 갱신 — 진짜 클론 인프라.

vault 90_System/AI/Profile.md / DecisionPatterns.md의 후보를 raw에서 추출.

흐름::

    L0 raw (Claude Code history) → sample → redact_full →
    Claude 분석 → ProfileFact / DecisionPattern 리스트 →
    MemoryInbox에 PR (사용자 승인 후 vault 진실원본)

저자: Synapse Memory Maintainers
"""

from synapse_memory.profile.extract import (
    extract_profile_facts,
    save_profile_update,
)
from synapse_memory.profile.schema import (
    PROFILE_CATEGORIES,
    DecisionPattern,
    ProfileFact,
)

__all__ = [
    "PROFILE_CATEGORIES",
    "DecisionPattern",
    "ProfileFact",
    "extract_profile_facts",
    "save_profile_update",
]
