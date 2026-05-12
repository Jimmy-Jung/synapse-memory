"""DecisionPatterns.md parsing tests.

저자: JunyoungJung <joony300@gmail.com>
작성일: 2026-05-12
"""

from __future__ import annotations

from pathlib import Path

from synapse_memory.profile.patterns import list_decision_patterns


def test_list_decision_patterns_from_markdown(tmp_path: Path) -> None:
    ai_dir = tmp_path / "90_System" / "AI"
    ai_dir.mkdir(parents=True)
    (ai_dir / "DecisionPatterns.md").write_text(
        "# DecisionPatterns\n\n"
        "- trigger: 큰 작업 시작\n"
        "  action: 계획 먼저 작성\n"
        "  rationale: 범위 관리\n"
        "  confidence: 0.8\n",
        encoding="utf-8",
    )

    patterns = list_decision_patterns(vault_path=tmp_path)

    assert len(patterns) == 1
    assert patterns[0].pattern_id == "pattern-b330dfadf791"
    assert patterns[0].trigger == "큰 작업 시작"
    assert patterns[0].action == "계획 먼저 작성"
