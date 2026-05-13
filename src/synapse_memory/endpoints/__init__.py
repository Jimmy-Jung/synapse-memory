"""사용자 endpoint 레이어 — AI 비서 / 세컨드 브레인 / 클론.

각 submodule을 직접 import해서 쓰세요::

    from synapse_memory.endpoints.ask import ask, AskResult
    # (W5 이후) from synapse_memory.endpoints.me import draft_resume

__init__에서 re-export 안 함 — module name(ask)과 function name(ask) 충돌 회피.

저자: Synapse Memory Maintainers
"""
