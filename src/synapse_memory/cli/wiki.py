"""entity ask and lint commands."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from synapse_memory.cli.common import OK, api
from synapse_memory.model import ENTITY_TYPES, RELATION_FIELDS, normalize_relation_target
from synapse_memory.store import list_pages
from synapse_memory.wiki.provenance import resolve_relation_evidence


def cmd_wiki_ask(args: argparse.Namespace) -> int:
    args.model = api()._resolve_model(getattr(args, "model", None), "ask")
    ai_env = api().detect_ai_environment(model=args.model)
    result = api().ask_wiki(
        args.query,
        save=getattr(args, "save", False),
        model=args.model,
        ai_env=ai_env,
    )
    print(result.answer)
    if result.sources:
        print("\n출처: " + ", ".join(f"[[{source}]]" for source in result.sources))
    if result.saved_slug:
        print(f"{OK} insight 저장: {result.saved_slug}")
    return 0


def cmd_lint(args: argparse.Namespace) -> int:
    vault = getattr(args, "vault", None)
    kwargs = {"vault_path": Path(vault)} if vault else {}
    result = api().run_lint(**kwargs)
    print(result.render_plain())
    return 1 if result.has_violations else 0


def _terminal_text(text: str) -> str:
    """Escape terminal/bidi controls while retaining readable lines and tabs."""
    return "".join(
        char if char.isprintable() or char in "\n\t" else json.dumps(char)[1:-1]
        for char in text
    )


def cmd_entity_provenance(args: argparse.Namespace) -> int:
    """Show exact source excerpts only in this explicit local-only command."""
    page_type, separator, slug = args.entity.partition(":")
    if not separator or page_type not in ENTITY_TYPES or not slug:
        print("엔티티를 type:slug 형식으로 지정하세요.")
        return 2
    try:
        slug = normalize_relation_target(slug)
        vault = api()._resolve_vault(args, require_exists=True)
        pages = [page for page in list_pages(page_type, vault_path=vault) if page.slug == slug]
        if len(pages) != 1:
            print("엔티티를 찾을 수 없거나 같은 slug의 페이지가 여러 개입니다.")
            return 2
        results = resolve_relation_evidence(pages[0], args.relation, args.target)
    except (OSError, ValueError):
        print("엔티티 또는 관계 근거를 읽을 수 없습니다. 경로와 저장 형식을 확인하세요.")
        return 2
    if args.json:
        print(_terminal_text(json.dumps(
            [asdict(result) for result in results], ensure_ascii=False, indent=2,
        )))
    elif not results:
        print("근거 미기록 — 이 관계에 연결된 원문 위치가 없습니다.")
    else:
        labels = {
            "verified": "원문 일치", "changed": "원문 변경 또는 구간 불일치",
            "missing": "원문 없음", "unsafe": "허용된 원문 경로 밖",
            "unreadable": "원문 읽기 실패", "too_large": "원문 조회 범위 제한 초과",
        }
        for result in results:
            evidence = result.evidence
            print(f"[{labels[result.status]}] {evidence.source}")
            print(f"  bytes {evidence.start_byte}:{evidence.end_byte}, chars {evidence.start_char}:{evidence.end_char}")
            if result.excerpt:
                print(_terminal_text(result.excerpt))
    return 0 if all(result.status == "verified" for result in results) else 1


def _register_entity_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    name: str,
    *,
    help_text: str | None,
) -> None:
    parser = subparsers.add_parser(name, help=help_text)
    entity_sub = parser.add_subparsers(dest="action", required=True, metavar="ACTION")

    ask = entity_sub.add_parser("ask", help="Entity/온톨로지 근거 질의 (인용 포함)")
    ask.add_argument("query", help="자연어 질의")
    ask.add_argument("--model", default=None)
    ask.add_argument("--save", action="store_true", help="답변을 insight Entity로 환원")
    ask.set_defaults(func=cmd_wiki_ask)

    provenance = entity_sub.add_parser("provenance", help="관계 원문 근거 로컬 조회 (AI 호출 없음)")
    provenance.add_argument("entity", help="출발 엔티티 type:slug")
    provenance.add_argument("relation", choices=RELATION_FIELDS)
    provenance.add_argument("target", help="관계에 기록된 대상 slug 또는 type:slug")
    provenance.add_argument("--vault", help="조회할 vault 경로")
    provenance.add_argument("--json", action="store_true", help="상태·위치·검증된 원문을 JSON으로 출력")
    provenance.set_defaults(func=cmd_entity_provenance)


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    _register_entity_parser(
        subparsers,
        "entity",
        help_text="Entity/온톨로지 검색 + 답변 환원",
    )
    _register_entity_parser(subparsers, "wiki", help_text=argparse.SUPPRESS)

    lint = subparsers.add_parser("lint", help="schema.yaml 검증 + 죽은 링크 자동수정")
    lint.add_argument("--now", action="store_true", help="즉시 1회 실행")
    lint.add_argument("--vault", help="검증할 vault 경로")
    lint.set_defaults(func=cmd_lint)
