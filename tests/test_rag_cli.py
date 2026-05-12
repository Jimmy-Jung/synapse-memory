"""RAG CLI contract tests.

저자: JunyoungJung <joony300@gmail.com>
작성일: 2026-05-12
"""

from __future__ import annotations

import argparse
from types import SimpleNamespace

import pytest

import synapse_memory.cli as cli_mod
from synapse_memory.cli import cmd_rag_index


def test_parser_has_rag_index_include_raw() -> None:
    parser = cli_mod.build_parser()

    args = parser.parse_args(["rag", "index", "--include-raw"])

    assert args.func is cmd_rag_index
    assert args.include_raw is True


def test_parser_has_ask_hybrid() -> None:
    parser = cli_mod.build_parser()

    args = parser.parse_args(["ask", "당근마켓", "--hybrid"])

    assert args.hybrid is True


def test_parser_has_me_what_did_i_think_hybrid() -> None:
    parser = cli_mod.build_parser()

    args = parser.parse_args(["me", "what-did-i-think", "당근마켓", "--hybrid"])

    assert args.hybrid is True


def test_me_timeline_hybrid_conflict(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli_mod.cmd_me_what_did_i_think(
        argparse.Namespace(
            topic="당근마켓",
            top_k=8,
            model="sonnet",
            timeline=True,
            by=None,
            limit=20,
            hybrid=True,
        )
    )

    assert rc == 1
    assert "--timeline and --hybrid conflict" in capsys.readouterr().err


def test_cmd_rag_index_prints_raw_counts(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli_mod, "open_vector_store", lambda: SimpleNamespace(count=lambda: 3))
    monkeypatch.setattr(
        cli_mod,
        "index_cards",
        lambda **_kwargs: SimpleNamespace(
            project_cards=0,
            company_cards=0,
            raw_obsidian_chunks=1,
            raw_claude_code_chunks=1,
            bm25_documents=2,
            bytes_indexed=42,
            failed=[],
        ),
    )

    rc = cmd_rag_index(argparse.Namespace(rebuild=False, include_raw=True))

    out = capsys.readouterr().out
    assert rc == 0
    assert "raw_obsidian=1" in out
    assert "raw_claude_code=1" in out
    assert "bm25=2" in out
