"""Doctor --fix CLI 테스트.

저자: Synapse Memory Maintainers
작성일: 2026-05-12
"""

from __future__ import annotations

import argparse

import pytest

import synapse_memory.cli as cli_mod
from synapse_memory.cli import cmd_doctor


def test_parser_has_doctor_fix() -> None:
    parser = cli_mod.build_parser()

    args = parser.parse_args(["doctor", "--fix"])

    assert args.func is cmd_doctor
    assert args.fix is True


def test_cmd_doctor_fix_delegates_to_repair_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: dict[str, bool] = {}

    def fake_fix(*, assume_yes: bool = False) -> int:
        called["fix"] = True
        called["assume_yes"] = assume_yes
        return 0

    monkeypatch.setattr(cli_mod, "run_doctor_fix", fake_fix)

    rc = cmd_doctor(argparse.Namespace(fix=True, yes=True))

    assert rc == 0
    assert called == {"fix": True, "assume_yes": True}
