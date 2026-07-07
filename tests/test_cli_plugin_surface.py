"""플러그인 진입점에서 쓰는 CLI 표면 계약 테스트.

저자: JunyoungJung
작성일: 2026-06-21
"""
from __future__ import annotations

import json

import synapse_memory.cli as cli
from synapse_memory.cards.company import CompanyCard, JobPosition
from synapse_memory.cards.project import ProjectCard


def test_card_list_json_outputs_project_and_company_cards(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "list_project_cards",
        lambda: [
            ProjectCard(
                project_id="alpha",
                display_name="Alpha",
                status="active",
                role="iOS",
            )
        ],
    )
    monkeypatch.setattr(
        cli,
        "list_company_cards",
        lambda: [
            CompanyCard(
                company_id="bravo",
                display_name="Bravo",
                status="target",
                country="KR",
                positions=[JobPosition(title="Engineer")],
            )
        ],
    )

    rc = cli.main(["card", "list", "--json"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["type"] == "all"
    assert payload["total"] == 2
    assert payload["projects"][0]["project_id"] == "alpha"
    assert payload["companies"][0]["positions"][0]["title"] == "Engineer"


def test_cleanup_scan_accepts_dry_run_alias(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "_resolve_vault", lambda *a, **kw: tmp_path)

    rc = cli.main(["cleanup", "scan", "--dry-run", "--json"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["vault_path"] == str(tmp_path)


def test_cleanup_apply_accepts_explicit_dry_run(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "_resolve_vault", lambda *a, **kw: tmp_path)

    rc = cli.main(["cleanup", "apply", "--dry-run"])

    assert rc == 0
    assert "선택된 후보 없음" in capsys.readouterr().out
