"""cli wiki ask / wiki reindex 서브커맨드 (ask_wiki/index_wiki_pages monkeypatch)."""
from __future__ import annotations

import synapse_memory.cli as cli
from synapse_memory.wiki.query import WikiAnswer


def test_cli_wiki_ask(monkeypatch, capsys):
    monkeypatch.setattr(cli, "ask_wiki",
        lambda query, **kw: WikiAnswer(query=query, answer="답", sources=["rag"]))
    rc = cli.main(["wiki", "ask", "RAG가 뭐야?"])
    assert rc == 0
    assert "답" in capsys.readouterr().out


def test_cli_wiki_reindex(monkeypatch, capsys):
    monkeypatch.setattr(cli, "index_wiki_pages", lambda **kw: 7)
    rc = cli.main(["wiki", "reindex"])
    assert rc == 0
    assert "7" in capsys.readouterr().out
