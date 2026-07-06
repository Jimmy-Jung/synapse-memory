"""Wiki profile decision pattern parsing tests.

저자: Synapse Memory Maintainers
작성일: 2026-05-12
"""

from __future__ import annotations

from pathlib import Path

from synapse_memory.profile.patterns import list_decision_patterns


def test_list_decision_patterns_from_markdown(tmp_path: Path) -> None:
    profile_dir = tmp_path / "Profile"
    profile_dir.mkdir(parents=True)
    (profile_dir / "user-profile.md").write_text(
        "## Decision Patterns - 2026-07-06\n\n"
        "### 큰 작업 시작\n\n"
        "- 행동: 계획 먼저 작성\n"
        "- 이유: 범위 관리\n"
        "- 신뢰도: 0.8\n",
        encoding="utf-8",
    )

    patterns = list_decision_patterns(vault_path=tmp_path)

    assert len(patterns) == 1
    assert patterns[0].pattern_id == "pattern-b330dfadf791"
    assert patterns[0].trigger == "큰 작업 시작"
    assert patterns[0].action == "계획 먼저 작성"
