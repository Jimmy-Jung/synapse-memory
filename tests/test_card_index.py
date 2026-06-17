# tests/test_card_index.py
"""CardIndex (020 Stage 1) — provider-only 카드 인덱스 + select_related 호환."""
from __future__ import annotations

from pathlib import Path

from synapse_memory.cards.card_index import CardEntry, CardIndex, build_card_index
from synapse_memory.wiki import llm_retrieval as lr


def test_empty_vault_yields_empty_index() -> None:
    idx = build_card_index(vault_path=Path("/tmp/synapse_no_such_vault_020"))
    assert len(idx) == 0
    assert idx.slugs == frozenset()


def test_render_and_slugs() -> None:
    idx = CardIndex(entries=(
        CardEntry(card_id="proj-a", kind="project", title="Alpha", summary="요약 A"),
        CardEntry(card_id="co-b", kind="company", title="Beta Inc", summary=""),
    ))
    rendered = idx.render()
    assert "[proj-a] (project) Alpha — 요약 A" in rendered
    assert "[co-b] (company) Beta Inc" in rendered
    assert idx.slugs == {"proj-a", "co-b"}
    assert idx.by_id()["proj-a"].title == "Alpha"


def test_select_related_compatible(monkeypatch) -> None:
    # CardIndex가 select_related(entries/render/slugs) 계약을 만족 → 카드에도 재사용.
    idx = CardIndex(entries=(
        CardEntry(card_id="proj-a", kind="project", title="Alpha", summary="s"),
        CardEntry(card_id="co-b", kind="company", title="Beta", summary="s"),
    ))
    monkeypatch.setattr(
        lr.ai_api, "complete_structured",
        lambda *a, **k: {"related": ["proj-a", "ghost"]},
    )
    out = lr.select_related("질의", idx, max_pages=10)
    assert out == ["proj-a"]  # 유효 card_id만, ghost 제거
