"""Generic semantic retrieval의 provider 환경 전파 회귀 테스트."""
from __future__ import annotations

from types import SimpleNamespace

from synapse_memory.retrieval import semantic


def test_retrieve_items_forwards_injected_ai_environment(monkeypatch) -> None:
    env = SimpleNamespace(provider="claude", model="sonnet")
    items = [SimpleNamespace(slug="rag")]
    captured: dict[str, object] = {}

    def fake_select_related(*_args, **kwargs):
        captured["env"] = kwargs.get("env")
        return ["rag"]

    monkeypatch.setattr(semantic, "select_related", fake_select_related)

    result = semantic.retrieve_items(
        "검색",
        items,
        build_index=lambda _items: SimpleNamespace(),
        item_id=lambda item: item.slug,
        top_k=5,
        env=env,
    )

    assert result == items
    assert captured["env"] is env
