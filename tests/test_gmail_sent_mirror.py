"""gmail_sent mirror 테스트.

실 Gmail API 의존성 미설치/credentials 미설정 시에도 동작 검증.
FakeGmailService 를 직접 inject.

저자: Synapse Memory Maintainers
작성일: 2026-05-18
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

import pytest

from synapse_memory.collectors.gmail_sent.mirror import (
    JSONL_NAME,
    META_DIR,
    SEEN_IDS_FILE,
    GmailMessage,
    collect_gmail_sent,
)


@pytest.fixture
def dst_root(tmp_path: Path) -> Path:
    return tmp_path / "l0" / "raw" / "gmail-sent"


class FakeGmailService:
    def __init__(self, messages: list[GmailMessage]) -> None:
        self._messages = messages
        self.list_calls = 0
        self.get_calls: list[str] = []

    def list_sent_ids(self) -> Iterable[tuple[str, str]]:
        self.list_calls += 1
        for m in self._messages:
            yield m.id, m.thread_id

    def get_message(self, message_id: str) -> GmailMessage:
        self.get_calls.append(message_id)
        for m in self._messages:
            if m.id == message_id:
                return m
        raise KeyError(message_id)


def _make_msg(idx: int, subject: str = "Test") -> GmailMessage:
    return GmailMessage(
        id=f"msg-{idx}",
        thread_id=f"thr-{idx}",
        internal_date_ms=1715610000000 + idx * 1000,
        subject=subject,
        snippet=f"snippet {idx}",
        label_ids=["SENT"],
    )


class TestCollectGmailSent:
    def test_disabled_when_env_unset(self, dst_root: Path) -> None:
        stats = collect_gmail_sent(
            service=FakeGmailService([_make_msg(1)]),
            enable_env=None,
            dst_root=dst_root,
        )
        assert stats.disabled
        assert stats.messages_added == 0
        assert not (dst_root / JSONL_NAME).exists()

    def test_disabled_when_env_zero(self, dst_root: Path) -> None:
        stats = collect_gmail_sent(
            service=FakeGmailService([_make_msg(1)]),
            enable_env="0",
            dst_root=dst_root,
        )
        assert stats.disabled

    def test_collects_messages(self, dst_root: Path) -> None:
        svc = FakeGmailService([_make_msg(1, "안녕"), _make_msg(2, "Hi")])
        stats = collect_gmail_sent(
            service=svc,
            enable_env="1",
            dst_root=dst_root,
        )
        assert not stats.disabled
        assert stats.messages_listed == 2
        assert stats.messages_added == 2
        assert stats.bytes_added > 0

        jsonl = dst_root / JSONL_NAME
        assert jsonl.is_file()
        records = [
            json.loads(line)
            for line in jsonl.read_text(encoding="utf-8").splitlines()
            if line
        ]
        assert [r["id"] for r in records] == ["msg-1", "msg-2"]
        assert records[0]["subject"] == "안녕"

    def test_incremental_skips_seen(self, dst_root: Path) -> None:
        svc1 = FakeGmailService([_make_msg(1)])
        collect_gmail_sent(
            service=svc1, enable_env="1", dst_root=dst_root
        )
        svc2 = FakeGmailService([_make_msg(1), _make_msg(2)])
        s2 = collect_gmail_sent(
            service=svc2, enable_env="1", dst_root=dst_root
        )
        assert s2.messages_listed == 2
        assert s2.messages_added == 1
        # get_message 는 새 msg-2 에만 호출
        assert svc2.get_calls == ["msg-2"]

        records = [
            json.loads(line)
            for line in (dst_root / JSONL_NAME)
            .read_text(encoding="utf-8")
            .splitlines()
            if line
        ]
        assert [r["id"] for r in records] == ["msg-1", "msg-2"]

    def test_seen_ids_persisted(self, dst_root: Path) -> None:
        collect_gmail_sent(
            service=FakeGmailService([_make_msg(1), _make_msg(2)]),
            enable_env="1",
            dst_root=dst_root,
        )
        seen = json.loads(
            (dst_root / META_DIR / SEEN_IDS_FILE).read_text(encoding="utf-8")
        )
        assert set(seen) == {"msg-1", "msg-2"}

    def test_missing_dependency_recorded_in_errors(
        self, dst_root: Path
    ) -> None:
        """service=None + env enabled → credentials 누락으로 errors 누적."""
        stats = collect_gmail_sent(
            service=None,
            enable_env="1",
            creds_path=Path("/tmp/no-such-creds.json"),
            token_path=Path("/tmp/no-such-token.json"),
            dst_root=dst_root,
        )
        assert not stats.disabled
        # ImportError (의존성 미설치) 또는 FileNotFoundError (credentials)
        # 둘 중 하나가 errors 에 기록되어야 함
        assert len(stats.errors) == 1
        assert stats.errors[0][0] == "gmail-service-init"


class TestDailyStageWiring:
    def test_collect_gmail_sent_in_steps(self) -> None:
        from synapse_memory.daily import DAILY_STAGES, STEPS

        assert "collect_gmail_sent" in STEPS
        assert any(
            s.name == "collect_gmail_sent"
            and s.description == "Gmail Sent mirror (opt-in)"
            for s in DAILY_STAGES
        )

    def test_stage_actions_include_gmail_sent(self) -> None:
        from synapse_memory.daily import _build_stage_actions

        actions = _build_stage_actions(
            classify_model="haiku",
            generate_model="sonnet",
            profile_model="sonnet",
            profile_sample_lines=10,
            profile_facts_only=True,
            on_log=lambda _msg: None,
        )
        assert "collect_gmail_sent" in actions
        assert callable(actions["collect_gmail_sent"])
