"""`synapse_memory.assistant_status` — 비서 모드 진단 묶음 테스트.

저자: JunyoungJung
작성일: 2026-05-13
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

from synapse_memory.assistant_status import (
    AssistantStatus,
    gather_status,
    recommend_actions,
    render_status,
)
from synapse_memory.cards.company import CompanyCard, JobPosition, save_company_card
from synapse_memory.cards.project import ProjectCard, save_project_card
from synapse_memory.doctor import DiagnosticResult, DiagnosticStatus


def _make_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    (vault / "20_Reference" / "Projects").mkdir(parents=True)
    (vault / "20_Reference" / "Companies").mkdir(parents=True)
    (vault / "90_System" / "AI" / "MemoryInbox").mkdir(parents=True)
    return vault


def _mock_ok_diag():
    return mock.patch(
        "synapse_memory.assistant_status.diagnose_private_permissions",
        return_value=DiagnosticResult(
            check_id="private_permissions",
            status=DiagnosticStatus.OK,
            message="ok",
        ),
    )


def _mock_no_status():
    return mock.patch(
        "synapse_memory.assistant_status.read_status", return_value=None
    )


def test_gather_status_empty_vault_returns_zero_counts(tmp_path):
    vault = _make_vault(tmp_path)
    with _mock_no_status(), _mock_ok_diag():
        status = gather_status(vault_path=vault)

    assert status.vault_path == str(vault)
    assert status.project_card_count == 0
    assert status.company_card_count == 0
    assert status.draft_project_count == 0
    assert status.draft_company_count == 0
    assert status.empty_company_count == 0
    assert status.inbox_pending_count == 0
    assert status.inbox_pending_latest is None
    assert status.last_daily_at is None
    assert status.doctor_ok is True


def test_gather_status_counts_draft_cards(tmp_path):
    vault = _make_vault(tmp_path)
    save_project_card(
        ProjectCard(project_id="active-one", display_name="A", status="active"),
        vault_path=vault,
    )
    save_project_card(
        ProjectCard(project_id="draft-one", display_name="D", status="draft"),
        vault_path=vault,
    )
    save_company_card(
        CompanyCard(
            company_id="empty-co",
            display_name="Empty",
            status="target",
            positions=[],
        ),
        vault_path=vault,
    )
    save_company_card(
        CompanyCard(
            company_id="draft-co",
            display_name="Draft Co",
            status="draft",
            positions=[JobPosition(title="iOS Engineer")],
        ),
        vault_path=vault,
    )

    with _mock_no_status(), _mock_ok_diag():
        status = gather_status(vault_path=vault)

    assert status.project_card_count == 2
    assert status.draft_project_count == 1
    assert status.company_card_count == 2
    assert status.draft_company_count == 1
    assert status.empty_company_count == 1  # empty-co (positions=[])


def test_gather_status_finds_latest_memory_inbox_file(tmp_path):
    vault = _make_vault(tmp_path)
    inbox = vault / "90_System" / "AI" / "MemoryInbox"
    (inbox / "Profile-2026-05-10.md").write_text("old", encoding="utf-8")
    (inbox / "Profile-2026-05-13.md").write_text("new", encoding="utf-8")
    (inbox / "Profile-2026-05-12.md").write_text("mid", encoding="utf-8")

    with _mock_no_status(), _mock_ok_diag():
        status = gather_status(vault_path=vault)

    assert status.inbox_pending_count == 3
    assert status.inbox_pending_latest is not None
    assert status.inbox_pending_latest.endswith("Profile-2026-05-13.md")


def test_gather_status_handles_missing_vault(tmp_path):
    with _mock_no_status(), _mock_ok_diag():
        status = gather_status(vault_path=tmp_path / "nonexistent")

    assert status.vault_path is not None
    assert status.project_card_count == 0
    assert status.company_card_count == 0


def test_gather_status_includes_doctor_issue_when_permission_bad(tmp_path):
    vault = _make_vault(tmp_path)

    with _mock_no_status(), mock.patch(
        "synapse_memory.assistant_status.diagnose_private_permissions",
        return_value=DiagnosticResult(
            check_id="private_permissions",
            status=DiagnosticStatus.FAIL,
            message="권한이 0755입니다. 0700이 필요합니다.",
        ),
    ):
        status = gather_status(vault_path=vault)

    assert status.doctor_ok is False
    assert any("0700" in m for m in status.doctor_issues)


def test_recommend_actions_doctor_issue_first():
    status = AssistantStatus(
        vault_path="/some/vault",
        project_card_count=0,
        company_card_count=0,
        draft_project_count=0,
        draft_company_count=0,
        empty_company_count=0,
        inbox_pending_count=0,
        inbox_pending_latest=None,
        last_daily_at=None,
        last_daily_state=None,
        doctor_ok=False,
        doctor_issues=["권한 문제"],
    )
    recs = recommend_actions(status)
    assert recs[0].startswith("환경 문제")


def test_recommend_actions_missing_vault_stops_other_suggestions():
    status = AssistantStatus(
        vault_path=None,
        project_card_count=0,
        company_card_count=0,
        draft_project_count=0,
        draft_company_count=0,
        empty_company_count=0,
        inbox_pending_count=5,  # vault 없으면 무시되어야 함
        inbox_pending_latest=None,
        last_daily_at=None,
        last_daily_state=None,
        doctor_ok=True,
    )
    recs = recommend_actions(status)
    assert len(recs) == 1
    assert "SYNAPSE_OBSIDIAN_VAULT" in recs[0]


def test_recommend_actions_priority_order():
    status = AssistantStatus(
        vault_path="/some/vault",
        project_card_count=5,
        company_card_count=3,
        draft_project_count=2,
        draft_company_count=1,
        empty_company_count=2,
        inbox_pending_count=4,
        inbox_pending_latest="/some/vault/.../Profile-2026-05-13.md",
        last_daily_at="2026-05-12T08:00:00+00:00",
        last_daily_state="done",
        doctor_ok=True,
    )
    recs = recommend_actions(status)
    assert any("MemoryInbox 검토" in r for r in recs)
    assert any("draft 카드" in r for r in recs)
    assert any("키워드 비어 있는 회사 카드" in r for r in recs)
    inbox_idx = next(i for i, r in enumerate(recs) if "MemoryInbox" in r)
    draft_idx = next(i for i, r in enumerate(recs) if "draft 카드" in r)
    assert inbox_idx < draft_idx


def test_recommend_actions_fallback_to_free_ask():
    status = AssistantStatus(
        vault_path="/some/vault",
        project_card_count=10,
        company_card_count=5,
        draft_project_count=0,
        draft_company_count=0,
        empty_company_count=0,
        inbox_pending_count=0,
        inbox_pending_latest=None,
        last_daily_at="2026-05-13T08:00:00+00:00",
        last_daily_state="done",
        doctor_ok=True,
    )
    recs = recommend_actions(status)
    assert len(recs) == 1
    assert "/sm:ask" in recs[0]


def test_to_json_round_trip():
    status = AssistantStatus(
        vault_path="/v",
        project_card_count=1,
        company_card_count=2,
        draft_project_count=0,
        draft_company_count=1,
        empty_company_count=1,
        inbox_pending_count=0,
        inbox_pending_latest=None,
        last_daily_at=None,
        last_daily_state=None,
        doctor_ok=True,
    )
    parsed = json.loads(status.to_json())
    assert parsed["vault_path"] == "/v"
    assert parsed["company_card_count"] == 2
    assert parsed["draft_company_count"] == 1


def test_gather_status_includes_cleanup_signals(tmp_path):
    """cleanup 후보가 있으면 status에 카운트가 잡히고 recommendation에 등장."""
    import datetime
    import os

    vault = _make_vault(tmp_path)
    stale = vault / "00_Inbox" / "stale.md"
    (vault / "00_Inbox").mkdir(exist_ok=True)
    stale.write_text("old", encoding="utf-8")
    target = (
        datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=60)
    ).timestamp()
    os.utime(stale, (target, target))

    with _mock_no_status(), _mock_ok_diag():
        status = gather_status(vault_path=vault)

    assert status.cleanup_candidate_count >= 1
    assert "inbox_stale" in status.cleanup_by_kind

    recs = recommend_actions(status)
    assert any("/sm:cleanup" in r for r in recs)


def test_render_status_includes_recommendations():
    status = AssistantStatus(
        vault_path="/v",
        project_card_count=0,
        company_card_count=0,
        draft_project_count=0,
        draft_company_count=0,
        empty_company_count=0,
        inbox_pending_count=2,
        inbox_pending_latest="/v/.../Profile-2026-05-13.md",
        last_daily_at="2026-05-13T08:00:00+00:00",
        last_daily_state="done",
        doctor_ok=True,
    )
    out = render_status(status)
    assert "추천 작업" in out
    assert "MemoryInbox" in out
