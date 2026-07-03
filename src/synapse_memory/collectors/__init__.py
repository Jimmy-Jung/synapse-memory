"""외부 데이터 수집기.

각 수집기는 외부 소스에서 변경분을 읽어 L0(``~/.synapse/private/raw/``)에
mirror한다. 분류는 별도 단계.

현재 컬렉터 (Tier 1~4 — 전 컬렉터)
----------------------------------
Tier 1 (PR #21):
- ``claude_code``           — Claude Code 세션 jsonl
- ``codex``                 — Codex CLI 세션 jsonl
- ``shell_history``         — ``~/.zsh_history``, ``~/.bash_history``
- ``cursor``                — Cursor IDE SQLite snapshot
- ``continue_dev``          — Continue.dev (VS Code) 세션 JSON
- ``aider``                 — Aider 터미널 AI pair 대화
- ``obsidian``              — Obsidian vault 마크다운

Tier 2 (PR #22):
- ``apple_notes``           — Apple Notes NoteStore.sqlite
- ``day_one``               — Day One Journal SQLite
- ``vscode_local_history``  — VS Code 파일별 auto-snapshot

Tier 3 (PR #23):
- ``imessage``              — iMessage chat.db (Full Disk Access 필요)
- ``gmail_sent``            — Gmail Sent (OAuth, ``SYNAPSE_GMAIL_ENABLE`` opt-in)
- ``calendar``              — macOS Calendar ICS

Tier 4 (본 PR):
- ``browser_history``       — Chrome/Safari/Arc History SQLite
- ``screen_time``           — macOS knowledgeC.db
- ``apple_health``          — iOS Health export*.zip drop-in

공통 헬퍼: ``_sqlite_mirror`` (sqlite3.backup + mtime/sha256 변경 감지) —
apple_notes / day_one 가 사용. cursor / imessage / browser_history /
screen_time 등은 본인 backup 코드 (후속 cleanup PR 에서 헬퍼로 통일 예정).

spec ``specs/016-collectors-expansion/plan.md`` 참고.

저자: Synapse Memory Maintainers
"""
