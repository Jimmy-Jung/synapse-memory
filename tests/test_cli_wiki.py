"""cli entity ask 서브커맨드 (ask_wiki monkeypatch)."""
from __future__ import annotations

import synapse_memory.cli as cli
from synapse_memory.wiki.query import WikiAnswer


def test_cli_entity_ask(monkeypatch, capsys):
    monkeypatch.setattr(cli, "ask_wiki",
        lambda query, **kw: WikiAnswer(query=query, answer="답", sources=["rag"]))
    rc = cli.main(["entity", "ask", "RAG가 뭐야?"])
    assert rc == 0
    assert "답" in capsys.readouterr().out
