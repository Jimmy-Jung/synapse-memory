"""synapse-memory CLI package.

`main()`은 parser 조립과 dispatch만 담당하고, 명령 구현은 noun별 모듈에 둔다.
"""

from __future__ import annotations

import argparse
import importlib
import sys
import time as _time
from typing import Any

from synapse_memory import __version__

time = _time

COMMAND_MODULES: tuple[str, ...] = (
    "doctor",
    "ingest",
    "setup",
    "hook",
    "profile",
    "cards",
    "wiki",
    "watch",
    "persona",
    "ask",
    "feedback",
    "cost",
    "daily",
    "config",
    "cleanup",
)


def __getattr__(name: str) -> Any:
    from synapse_memory.cli.compat import get_lazy_attr

    value = get_lazy_attr(name)
    globals()[name] = value
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="synapse-memory",
        description="Personal knowledge memory & provider-only Entity ontology.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="cmd", required=True, metavar="COMMAND")
    for module_name in COMMAND_MODULES:
        module = importlib.import_module(f"{__name__}.{module_name}")
        module.register(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    from synapse_memory.cost.events import command_context

    parser = build_parser()
    args = parser.parse_args(argv)
    with command_context(__getattr__("_command_name")(args)):
        try:
            return int(args.func(args))
        except SystemExit as exc:
            return int(exc.code) if isinstance(exc.code, int) else 1


if __name__ == "__main__":
    sys.exit(main())
