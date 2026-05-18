"""외부 데이터 수집기.

각 수집기는 외부 소스에서 변경분을 읽어 L0(``~/.synapse/private/raw/``)에
mirror한다. 분류/redaction은 별도 단계.

현재 컬렉터 (Tier 1)
--------------------
- ``claude_code``    — Claude Code 세션 jsonl
- ``codex``          — Codex CLI 세션 jsonl
- ``shell_history``  — ``~/.zsh_history``, ``~/.bash_history``
- ``cursor``         — Cursor IDE SQLite snapshot
- ``continue_dev``   — Continue.dev (VS Code) 세션 JSON
- ``aider``          — Aider 터미널 AI pair 대화
- ``git_self``       — 본인 git commit (``SYNAPSE_GIT_SELF_ROOTS`` opt-in)
- ``obsidian``       — Obsidian vault 마크다운

후속 sprint (Tier 2~4): apple_notes, day_one, vscode_local_history,
imessage, gmail_sent, calendar, browser_history, screen_time, apple_health.
spec ``specs/016-collectors-expansion/plan.md`` 참고.

저자: Synapse Memory Maintainers
"""
