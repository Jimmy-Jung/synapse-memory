"""외부 데이터 수집기.

각 수집기는 외부 소스에서 변경분을 읽어 L0(``~/.synapse/private/raw/``)에
mirror한다. 분류는 별도 단계.

현재 컬렉터
-----------
Tier 1 (PR #21):
- ``claude_code``           — Claude Code 세션 jsonl
- ``codex``                 — Codex CLI 세션 jsonl
- ``obsidian``              — Obsidian vault 마크다운

spec ``specs/016-collectors-expansion/plan.md`` 참고.

저자: Synapse Memory Maintainers
"""
