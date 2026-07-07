"""cli ask 명령 회귀 테스트.

api()=synapse_memory.cli 패키지이고 cli/ask.py 서브모듈이 있어, `api().ask`가
lazy __getattr__ 대신 서브모듈 자신을 가리키던 이름 충돌 버그를 방어한다.

저자: JunyoungJung
작성일: 2026-07-07
"""
from __future__ import annotations

import argparse
from types import SimpleNamespace

import synapse_memory.cli.ask as cli_ask  # 서브모듈 import → 충돌 조건 재현
import synapse_memory.endpoints.ask as ep_ask


def test_cmd_ask_reaches_endpoints_ask(monkeypatch) -> None:
    import synapse_memory.cli as cli_pkg

    monkeypatch.setattr(cli_pkg, "_arg_or_config", lambda *a, **k: 5, raising=False)
    monkeypatch.setattr(cli_pkg, "_resolve_model", lambda *a, **k: "m", raising=False)
    monkeypatch.setattr(cli_pkg, "_enforce_cost_cap", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(cli_pkg, "_interactive_guard", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(
        cli_pkg,
        "detect_ai_environment",
        lambda **k: SimpleNamespace(ready=True, reasons_unavailable=lambda: []),
        raising=False,
    )

    calls: dict[str, object] = {}

    def fake_ask(query: str, **kwargs: object) -> SimpleNamespace:
        calls["query"] = query
        return SimpleNamespace(query=query, answer="A", sources=[], saved_path=None)

    monkeypatch.setattr(ep_ask, "ask", fake_ask)

    args = argparse.Namespace(
        query="온톨로지 질의", top_k=None, model=None, kind=None, hybrid=False, save=False
    )
    rc = cli_ask.cmd_ask(args)

    assert rc == 0
    assert calls["query"] == "온톨로지 질의"
