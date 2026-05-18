"""Gmail Sent 컬렉터 (opt-in, OAuth).

소스: Gmail API ``users.messages.list(q="in:sent")`` + ``messages.get``
대상: ``~/.synapse/private/raw/gmail-sent/`` 아래 JSONL.

opt-in:
    - ``SYNAPSE_GMAIL_ENABLE=1`` 필수 — 미설정 시 silent skip.
    - ``SYNAPSE_GMAIL_CREDS`` — OAuth credentials.json 경로
      (기본: ``~/.config/synapse-memory/gmail-credentials.json``).
    - ``SYNAPSE_GMAIL_TOKEN`` — OAuth token cache 경로
      (기본: ``~/.config/synapse-memory/gmail-token.json``).

의존성:
    Optional — ``google-api-python-client``, ``google-auth-oauthlib``.
    미설치 시 errors 에 기록 후 빈 통계 반환 (daily 중단 안 됨).

저자: Synapse Memory Maintainers
"""

from synapse_memory.collectors.gmail_sent.mirror import (
    ENV_CREDS,
    ENV_ENABLE,
    ENV_TOKEN,
    CollectStats,
    GmailMessage,
    GmailService,
    collect_gmail_sent,
)

__all__ = [
    "ENV_CREDS",
    "ENV_ENABLE",
    "ENV_TOKEN",
    "CollectStats",
    "GmailMessage",
    "GmailService",
    "collect_gmail_sent",
]
