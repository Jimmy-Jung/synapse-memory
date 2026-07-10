"""cli entity ask 서브커맨드 (ask_wiki monkeypatch)."""
from __future__ import annotations

from types import SimpleNamespace

import synapse_memory.cli as cli
from synapse_memory.wiki.query import WikiAnswer


def test_cli_entity_ask(monkeypatch, capsys):
    monkeypatch.setattr(cli, "ask_wiki",
        lambda query, **kw: WikiAnswer(query=query, answer="답", sources=["rag"]))
    rc = cli.main(["entity", "ask", "RAG가 뭐야?"])
    assert rc == 0
    assert "답" in capsys.readouterr().out


def test_cli_entity_ask_resolves_and_forwards_explicit_model(monkeypatch, capsys) -> None:
    env = SimpleNamespace(provider="codex", model="gpt-5.6-sol")
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        cli,
        "_resolve_model",
        lambda model, task: captured.update({"resolved": (model, task)}) or model,
    )
    monkeypatch.setattr(
        cli,
        "detect_ai_environment",
        lambda *, model: captured.update({"detected": model}) or env,
    )
    monkeypatch.setattr(
        cli,
        "ask_wiki",
        lambda query, **kwargs: captured.update({"query": query, "kwargs": kwargs})
        or WikiAnswer(query=query, answer="답", sources=[]),
    )

    rc = cli.main(["entity", "ask", "RAG가 뭐야?", "--model", "gpt-5.6-sol"])

    assert rc == 0
    assert captured["resolved"] == ("gpt-5.6-sol", "ask")
    assert captured["detected"] == "gpt-5.6-sol"
    assert captured["query"] == "RAG가 뭐야?"
    assert captured["kwargs"] == {
        "save": False,
        "model": "gpt-5.6-sol",
        "ai_env": env,
    }
    assert "답" in capsys.readouterr().out
