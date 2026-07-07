"""card command."""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from typing import Any

from synapse_memory.cli.common import FAIL, OK, api


def cmd_card_list(args: argparse.Namespace) -> int:
    kind = args.type
    project_cards = api().list_project_cards() if kind in ("project", "all") else []
    company_cards = api().list_company_cards() if kind in ("company", "all") else []

    if args.json:
        print(
            json.dumps(
                {
                    "type": kind,
                    "total": len(project_cards) + len(company_cards),
                    "projects": [_project_card_payload(card) for card in project_cards],
                    "companies": [_company_card_payload(card) for card in company_cards],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    shown = 0
    if kind in ("project", "all") and project_cards:
        print(f"\n[Project Cards]   {api().projects_dir()}")
        print(f"{'ID':<25} {'STATUS':<12} {'ROLE':<25} {'PERIOD':<20}")
        print("-" * 85)
        for project_card in project_cards:
            period = project_card.period_start or ""
            if project_card.period_end:
                period = f"{period} ~ {project_card.period_end}"
            print(
                f"{project_card.project_id:<25} {project_card.status:<12} "
                f"{(project_card.role or '')[:24]:<25} {period:<20}"
            )
        shown += len(project_cards)

    if kind in ("company", "all") and company_cards:
        print(f"\n[Company Cards]   {api().companies_dir()}")
        print(f"{'ID':<25} {'STATUS':<14} {'COUNTRY':<8} {'POSITIONS':<5}")
        print("-" * 85)
        for company_card in company_cards:
            print(
                f"{company_card.company_id:<25} {company_card.status:<14} "
                f"{(company_card.country or ''):<8} {len(company_card.positions):<5}"
            )
        shown += len(company_cards)

    print(f"\n총 {shown}개" if shown else f"Card 0개 (type={kind})")
    return 0


def _project_card_payload(card: Any) -> dict[str, object]:
    return {
        "project_id": card.project_id,
        "display_name": card.display_name,
        "status": card.status,
        "role": getattr(card, "role", None),
        "period_start": getattr(card, "period_start", None),
        "period_end": getattr(card, "period_end", None),
        "domains": list(getattr(card, "domains", []) or []),
        "stack": list(getattr(card, "stack", []) or []),
        "keywords": list(getattr(card, "keywords", []) or []),
        "metrics": [
            m.to_dict() if hasattr(m, "to_dict") else dict(m)
            for m in getattr(card, "metrics", []) or []
        ],
        "sources": [
            s.to_dict() if hasattr(s, "to_dict") else dict(s)
            for s in getattr(card, "sources", []) or []
        ],
        "confidence": getattr(card, "confidence", 1.0),
        "created": getattr(card, "created", ""),
        "last_reviewed": getattr(card, "last_reviewed", ""),
        "body": getattr(card, "body", ""),
    }


def _company_card_payload(card: Any) -> dict[str, object]:
    return {
        "company_id": card.company_id,
        "display_name": card.display_name,
        "status": card.status,
        "country": getattr(card, "country", None),
        "size": getattr(card, "size", None),
        "website": getattr(card, "website", None),
        "positions": [
            p.to_dict() if hasattr(p, "to_dict") else dict(p)
            for p in getattr(card, "positions", []) or []
        ],
        "notes": getattr(card, "notes", ""),
        "sources": [
            s.to_dict() if hasattr(s, "to_dict") else dict(s)
            for s in getattr(card, "sources", []) or []
        ],
        "confidence": getattr(card, "confidence", 1.0),
        "created": getattr(card, "created", ""),
        "last_reviewed": getattr(card, "last_reviewed", ""),
        "body": getattr(card, "body", ""),
        "resume_language": getattr(card, "resume_language", None),
    }


def cmd_card_show(args: argparse.Namespace) -> int:
    try:
        if args.type == "company":
            print(api().serialize_company_card(api().load_company_card(args.card_id)))
        else:
            print(api().serialize_project_card(api().load_project_card(args.card_id)))
    except FileNotFoundError as exc:
        print(f"{FAIL} {exc}", file=sys.stderr)
        return 2
    return 0


def cmd_card_new(args: argparse.Namespace) -> int:
    cid = args.card_id
    today = datetime.date.today().isoformat()

    if args.type == "company":
        target = api().companies_dir() / f"{cid}.md"
        if target.exists() and not args.force:
            print(f"{FAIL} 이미 존재: {target}", file=sys.stderr)
            return 1
        card = api().CompanyCard(
            company_id=cid,
            display_name=args.display_name,
            status="target",
            created=today,
            last_reviewed=today,
            body=(
                "## 회사 개요\n\n\n"
                "## 기술 스택\n\n\n"
                "## 문화\n\n\n"
                "## 매칭되는 내 프로젝트\n\n\n"
                "## 메모\n"
            ),
        )
        path = api().save_company_card(card)
    else:
        target = api().projects_dir() / f"{cid}.md"
        if target.exists() and not args.force:
            print(f"{FAIL} 이미 존재: {target}", file=sys.stderr)
            return 1
        card = api().ProjectCard(
            project_id=cid,
            display_name=args.display_name,
            status="active",
            created=today,
            last_reviewed=today,
            body=(
                "## 문제\n\n\n"
                "## 접근\n\n\n"
                "## 영향\n\n\n"
                "## 기술 결정\n\n\n"
                "## 회고\n"
            ),
        )
        path = api().save_project_card(card)

    print(f"{OK} 생성: {path}")
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("card", help="Project/Company Card 관리")
    card_sub = parser.add_subparsers(dest="action", required=True, metavar="ACTION")

    p_list = card_sub.add_parser("list", help="Card 목록")
    p_list.add_argument("--type", choices=["project", "company", "all"], default="all")
    p_list.add_argument("--json", action="store_true", help="JSON 출력")
    p_list.set_defaults(func=cmd_card_list)

    p_show = card_sub.add_parser("show", help="Card 내용")
    p_show.add_argument("card_id", help="card 파일명 (확장자 제외)")
    p_show.add_argument("--type", choices=["project", "company"], default="project")
    p_show.set_defaults(func=cmd_card_show)

    p_new = card_sub.add_parser("new", help="Card 빈 템플릿 생성")
    p_new.add_argument("card_id", help="slug. 파일명이 됨")
    p_new.add_argument("display_name", help="사람 읽는 이름")
    p_new.add_argument("--type", choices=["project", "company"], default="project")
    p_new.add_argument("--force", action="store_true", help="기존 파일 덮어쓰기")
    p_new.set_defaults(func=cmd_card_new)
