"""외부 데이터 수집기.

각 수집기는 외부 소스에서 변경분을 읽어 L0(``~/.synapse/private/raw/``)에
mirror한다. 분류/redaction은 별도 단계.

현재 컬렉터 (Tier 1~2)
----------------------
- ``claude_code``           — Claude Code 세션 jsonl
- ``codex``                 — Codex CLI 세션 jsonl
- ``shell_history``         — ``~/.zsh_history``, ``~/.bash_history``
- ``cursor``                — Cursor IDE SQLite snapshot
- ``continue_dev``          — Continue.dev (VS Code) 세션 JSON
- ``aider``                 — Aider 터미널 AI pair 대화
- ``git_self``              — 본인 git commit (``SYNAPSE_GIT_SELF_ROOTS`` opt-in)
- ``apple_notes``           — Apple Notes NoteStore.sqlite
- ``day_one``               — Day One Journal SQLite
- ``vscode_local_history``  — VS Code 파일별 auto-snapshot
- ``obsidian``              — Obsidian vault 마크다운

공통 헬퍼: ``_sqlite_mirror`` (sqlite3.backup + mtime/sha256 변경 감지).

후속 sprint (Tier 3~4): imessage, gmail_sent, calendar,
browser_history, screen_time, apple_health.
spec ``specs/016-collectors-expansion/plan.md`` 참고.

저자: Synapse Memory Maintainers
"""
