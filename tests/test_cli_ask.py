"""cli ask 명령 회귀 테스트.

api()=synapse_memory.cli 패키지이고 cli/ask.py 서브모듈이 있어, `api().ask`가
lazy __getattr__ 대신 서브모듈 자신을 가리키던 이름 충돌 버그를 방어한다.
헤드라인 ask는 2.0.0 온톨로지 경로(wiki.query.ask_wiki)로 일원화되어 있다.

저자: JunyoungJung
작성일: 2026-07-08
"""
from __future__ import annotations

import argparse
from types import SimpleNamespace

import synapse_memory.cli.ask as cli_ask  # 서브모듈 import → 충돌 조건 재현
import synapse_memory.wiki.query as wiki_query


def test_cmd_ask_reaches_ask_wiki(monkeypatch) -> None:
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

    def fake_ask_wiki(query: str, **kwargs: object) -> SimpleNamespace:
        calls["query"] = query
        calls["kwargs"] = kwargs
        return SimpleNamespace(
            query=query, answer="A", sources=["some-slug"], saved_slug=None
        )

    # cmd_ask는 함수 내부에서 `from synapse_memory.wiki.query import ask_wiki`를
    # 실행하므로 모듈 속성 패치가 호출 시점에 반영된다.
    monkeypatch.setattr(wiki_query, "ask_wiki", fake_ask_wiki)

    args = argparse.Namespace(
        query="온톨로지 질의", top_k=None, model=None, kind=None, hybrid=False, save=False
    )
    rc = cli_ask.cmd_ask(args)

    assert rc == 0
    assert calls["query"] == "온톨로지 질의"
    # 옛 Card RAG 플래그(kind/hybrid/where)는 Entity 경로로 넘기지 않는다.
    assert "where" not in calls["kwargs"]
    assert "hybrid" not in calls["kwargs"]
