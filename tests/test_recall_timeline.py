"""recall.timeline module smoke tests."""

from __future__ import annotations

import datetime

from synapse_memory.recall.timeline import (
    _format_timeline_output,
    _group_by_quarter,
    _resolve_sort_ts,
)


def test_recall_timeline_groups_by_quarter() -> None:
    today = datetime.date(2026, 5, 12)
    card = _resolve_sort_ts(
        {
            "card_id": "project-a",
            "source_kind": "card_project",
            "period_end": "2026-04",
            "created": "2026-01-01",
            "status": "archived",
        },
        today,
        document="project body",
    )

    groups = _group_by_quarter([card])
    output = _format_timeline_output(groups, limit=10)

    assert groups[0].quarter_label == "2026 Q2"
    assert "project-a" in output
