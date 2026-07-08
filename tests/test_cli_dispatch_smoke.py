"""CLI 디스패치 스모크 — 최상위 parser가 서브커맨드를 등록하고 func에 배선하는지.

`ask`가 endpoints/wiki 모듈과 이름 충돌해 dispatch가 깨졌던 버그(a1b874f/8aa97ef
계열)는 parser→func 배선 단에서 샜다. 단위테스트가 cmd_ask를 직접 호출해도 이
배선은 커버되지 않으므로, 여기서 build_parser() 산출물을 실제로 파싱해 막는다.

저자: JunyoungJung
작성일: 2026-07-08
"""
from __future__ import annotations

import argparse

from synapse_memory.cli import build_parser
from synapse_memory.cli.ask import cmd_ask


def _subcommand_names(parser: argparse.ArgumentParser) -> list[str]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return list(action.choices)
    return []


def test_build_parser_registers_subcommands() -> None:
    names = _subcommand_names(build_parser())
    assert "ask" in names
    assert len(names) > 5, f"서브커맨드가 비정상적으로 적음: {names}"


def test_ask_parses_and_dispatches_to_cmd_ask() -> None:
    # 이름 충돌 회귀 가드: `ask "질의"`가 실제로 cmd_ask에 배선돼야 한다.
    args = build_parser().parse_args(["ask", "질의"])
    assert getattr(args, "func", None) is cmd_ask
    assert args.query == "질의"
