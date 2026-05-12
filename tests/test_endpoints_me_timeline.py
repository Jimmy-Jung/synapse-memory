"""Timeline recall tests — FR-001~FR-017.

본 모듈은 `synapse-memory me what-did-i-think --timeline` 의 시간축 정렬 ·
분기 그룹화 · 폴백 · 모드 별칭 · 회귀 가드를 검증한다.

매핑:
- spec: ``specs/002-timeline-recall/spec.md`` (User Story 1/2/3, FR-001~017)
- plan: ``specs/002-timeline-recall/plan.md``
- contracts: ``specs/002-timeline-recall/contracts/cli-contracts.md``
- data-model: ``specs/002-timeline-recall/data-model.md``

테스트는 tasks.md T008~T016, T025~T026, T033~T036, T044 에서 채워진다.
본 파일은 T001 (skeleton) 으로 import 만 정의한다.
"""

from __future__ import annotations

import datetime as _datetime

import pytest

# Target functions (added in Phase 2 — T004~T006 stubs, filled in T018~T021)
# from synapse_memory.endpoints.me import (
#     CardWithMeta,
#     TimelineGroup,
#     _resolve_sort_ts,
#     _sort_by_time,
#     _group_by_quarter,
#     _format_timeline_output,
#     what_did_i_think,
# )

__all__: list[str] = []  # tests are discovered by pytest, not imported elsewhere


@pytest.fixture
def today() -> _datetime.date:
    """Deterministic 'today' for tests dependent on FR-003 today_fallback."""
    return _datetime.date(2026, 5, 12)
