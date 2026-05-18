"""Gmail Sent → L0 mirror.

ID 별로 한 줄 JSONL append. 이미 본 id 는 skip — seen-ids meta 보존.

저장 포맷 (한 줄 = 한 message)::

    {
      "id": "<message-id>",
      "thread_id": "<thread-id>",
      "internal_date_ms": 1715610000000,
      "subject": "<first 200 chars of Subject header>",
      "snippet": "<gmail snippet>",
      "label_ids": ["SENT"]
    }

본 단계는 메타 + snippet 만 저장한다. 본문 (payload.body.data, MIME parts) 은
저장 volume 보호 + privacy 차원에서 별도 follow-up 단계에서 수집.

저자: Synapse Memory Maintainers
작성일: 2026-05-18
"""

from __future__ import annotations

import contextlib
import json
import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from synapse_memory.storage.l0 import (
    L0_FILE_MODE,
    ensure_l0_root_secure,
    ensure_secure_dir,
    l0_root,
)

ENV_ENABLE = "SYNAPSE_GMAIL_ENABLE"
ENV_CREDS = "SYNAPSE_GMAIL_CREDS"
ENV_TOKEN = "SYNAPSE_GMAIL_TOKEN"

DEFAULT_CREDS = (
    Path.home() / ".config" / "synapse-memory" / "gmail-credentials.json"
)
DEFAULT_TOKEN = (
    Path.home() / ".config" / "synapse-memory" / "gmail-token.json"
)

SUBPATH = Path("raw") / "gmail-sent"
JSONL_NAME = "sent.jsonl"
META_DIR = ".meta"
SEEN_IDS_FILE = "seen-ids.json"

GMAIL_SCOPES = ("https://www.googleapis.com/auth/gmail.readonly",)

__all__ = [
    "ENV_CREDS",
    "ENV_ENABLE",
    "ENV_TOKEN",
    "DEFAULT_CREDS",
    "DEFAULT_TOKEN",
    "SUBPATH",
    "GMAIL_SCOPES",
    "CollectStats",
    "GmailMessage",
    "GmailService",
    "collect_gmail_sent",
]


@dataclass
class GmailMessage:
    """축약된 Gmail message — JSONL 한 줄에 대응."""

    id: str
    thread_id: str
    internal_date_ms: int
    subject: str
    snippet: str
    label_ids: list[str]


@dataclass
class CollectStats:
    messages_listed: int = 0
    messages_added: int = 0
    bytes_added: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)
    disabled: bool = False

    def summary(self) -> str:
        if self.disabled:
            return "disabled"
        return (
            f"listed={self.messages_listed} added={self.messages_added} "
            f"bytes+={self.bytes_added} errors={len(self.errors)}"
        )


class GmailService(Protocol):
    """테스트와 실 구현 사이 추상화. 의존성 격리."""

    def list_sent_ids(self) -> Iterable[tuple[str, str]]:
        """(message_id, thread_id) iterator. 페이지 처리 책임 포함."""

    def get_message(self, message_id: str) -> GmailMessage:
        """단일 message 메타 + snippet 가져오기."""


def _load_seen_ids(meta_path: Path) -> set[str]:
    if not meta_path.exists():
        return set()
    try:
        raw = json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return set()
    if not isinstance(raw, list):
        return set()
    return {str(x) for x in raw}


def _save_seen_ids_atomic(meta_path: Path, ids: set[str]) -> None:
    ensure_secure_dir(meta_path.parent)
    payload = json.dumps(sorted(ids), ensure_ascii=False, indent=2)
    tmp = meta_path.with_suffix(meta_path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())
    with contextlib.suppress(OSError):
        os.chmod(tmp, L0_FILE_MODE)
    os.replace(tmp, meta_path)


def _append_jsonl(dst: Path, messages: list[GmailMessage]) -> int:
    if not messages:
        return 0
    ensure_secure_dir(dst.parent)
    lines = [
        json.dumps(
            {
                "id": m.id,
                "thread_id": m.thread_id,
                "internal_date_ms": m.internal_date_ms,
                "subject": m.subject,
                "snippet": m.snippet,
                "label_ids": list(m.label_ids),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n"
        for m in messages
    ]
    blob = "".join(lines).encode("utf-8")
    with open(dst, "ab") as f:
        f.write(blob)
        f.flush()
        os.fsync(f.fileno())
    with contextlib.suppress(OSError):
        os.chmod(dst, L0_FILE_MODE)
    return len(blob)


def _build_default_service(
    creds_path: Path,
    token_path: Path,
) -> GmailService:
    """실 Gmail API 기반 GmailService. 의존성 dynamic import.

    Raises:
        ImportError: ``google-api-python-client`` 미설치.
        FileNotFoundError: credentials.json 미존재.
    """
    try:
        from google.auth.transport.requests import (  # type: ignore[import-not-found]
            Request,
        )
        from google.oauth2.credentials import (  # type: ignore[import-not-found]
            Credentials,
        )
        from google_auth_oauthlib.flow import (  # type: ignore[import-not-found]
            InstalledAppFlow,
        )
        from googleapiclient.discovery import (  # type: ignore[import-not-found]
            build,
        )
    except ImportError as exc:
        raise ImportError(
            "gmail_sent 컬렉터는 'google-api-python-client' + "
            "'google-auth-oauthlib' 설치 필요. "
            "pip install google-api-python-client google-auth-oauthlib"
        ) from exc

    if not creds_path.is_file():
        raise FileNotFoundError(
            f"Gmail credentials.json 없음: {creds_path}"
        )

    creds = None
    if token_path.is_file():
        creds = Credentials.from_authorized_user_file(
            str(token_path), GMAIL_SCOPES
        )
    if creds is None or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(creds_path), GMAIL_SCOPES
            )
            creds = flow.run_local_server(port=0)
        ensure_secure_dir(token_path.parent)
        token_path.write_text(creds.to_json(), encoding="utf-8")
        with contextlib.suppress(OSError):
            os.chmod(token_path, L0_FILE_MODE)

    service = build("gmail", "v1", credentials=creds)

    class _RealGmailService:
        def __init__(self, svc: object) -> None:
            self._svc = svc

        def list_sent_ids(self) -> Iterable[tuple[str, str]]:
            page_token: str | None = None
            while True:
                req = self._svc.users().messages().list(  # type: ignore[attr-defined]
                    userId="me",
                    labelIds=["SENT"],
                    pageToken=page_token,
                    maxResults=500,
                )
                resp = req.execute()
                for m in resp.get("messages", []) or []:
                    yield m["id"], m["threadId"]
                page_token = resp.get("nextPageToken")
                if not page_token:
                    return

        def get_message(self, message_id: str) -> GmailMessage:
            resp = (
                self._svc.users()  # type: ignore[attr-defined]
                .messages()
                .get(
                    userId="me",
                    id=message_id,
                    format="metadata",
                    metadataHeaders=["Subject"],
                )
                .execute()
            )
            headers = resp.get("payload", {}).get("headers", []) or []
            subject = ""
            for h in headers:
                if h.get("name", "").lower() == "subject":
                    subject = (h.get("value") or "")[:200]
                    break
            return GmailMessage(
                id=resp["id"],
                thread_id=resp.get("threadId", ""),
                internal_date_ms=int(resp.get("internalDate", 0)),
                subject=subject,
                snippet=(resp.get("snippet") or "")[:500],
                label_ids=list(resp.get("labelIds", []) or []),
            )

    return _RealGmailService(service)


def collect_gmail_sent(
    *,
    service: GmailService | None = None,
    enable_env: str | None = None,
    creds_path: Path | None = None,
    token_path: Path | None = None,
    dst_root: Path | None = None,
) -> CollectStats:
    """Gmail Sent 1회 수집 (incremental — message id seen set 기반).

    Args:
        service: GmailService 구현. 주어지면 dynamic 의존성 import 건너뜀
            (테스트용).
        enable_env: ``SYNAPSE_GMAIL_ENABLE`` env override.
        creds_path: credentials.json override.
        token_path: token cache override.
        dst_root: L0 mirror 루트 (기본: ``<l0_root>/raw/gmail-sent``).

    Returns:
        CollectStats. opt-in env 미설정 시 ``disabled=True`` + 빈 통계 반환.
    """
    enable_val = (
        enable_env if enable_env is not None else os.environ.get(ENV_ENABLE)
    )
    stats = CollectStats()
    if not enable_val or enable_val.lower() in ("0", "false", "no"):
        stats.disabled = True
        return stats

    dst = (dst_root or (l0_root() / SUBPATH)).expanduser().resolve()
    if dst.is_relative_to(l0_root().expanduser().resolve()):
        ensure_l0_root_secure()
    ensure_secure_dir(dst)
    ensure_secure_dir(dst / META_DIR)

    seen_path = dst / META_DIR / SEEN_IDS_FILE
    seen = _load_seen_ids(seen_path)

    if service is None:
        try:
            service = _build_default_service(
                creds_path=(
                    creds_path
                    or Path(os.environ.get(ENV_CREDS) or DEFAULT_CREDS)
                ).expanduser(),
                token_path=(
                    token_path
                    or Path(os.environ.get(ENV_TOKEN) or DEFAULT_TOKEN)
                ).expanduser(),
            )
        except (ImportError, FileNotFoundError, OSError) as exc:
            stats.errors.append(("gmail-service-init", str(exc)))
            return stats

    new_messages: list[GmailMessage] = []
    try:
        for msg_id, _thread_id in service.list_sent_ids():
            stats.messages_listed += 1
            if msg_id in seen:
                continue
            try:
                m = service.get_message(msg_id)
            except Exception as exc:  # noqa: BLE001 — Gmail API 클라이언트 다양한 예외
                stats.errors.append((msg_id, str(exc)))
                continue
            new_messages.append(m)
            seen.add(msg_id)
    except Exception as exc:  # noqa: BLE001 — list_sent_ids 자체 실패
        stats.errors.append(("list_sent_ids", str(exc)))

    if new_messages:
        added = _append_jsonl(dst / JSONL_NAME, new_messages)
        stats.messages_added = len(new_messages)
        stats.bytes_added = added
        _save_seen_ids_atomic(seen_path, seen)

    return stats
