"""Profile wiki page 자동 갱신 — 진짜 클론 인프라.

vault Profile/user-profile.md를 raw에서 추출한 안정 신호로 갱신.

흐름::

    L0 raw (Claude Code history) → sample →
    Claude 분석 → ProfileFact / DecisionPattern 리스트 →
    wiki profile page에 반영

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
