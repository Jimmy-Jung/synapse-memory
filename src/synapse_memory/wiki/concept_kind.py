"""concept.kind 백필 — 키워드 휴리스틱 분류. dry-run 기본, --apply로 저장.

실행: python -m synapse_memory.wiki.concept_kind --vault /path [--apply]

저자: JunyoungJung
작성일: 2026-07-07

ponytail: 키워드 휴리스틱 분류기 — 정밀도 상한 존재, LLM 분류기로 교체 가능.
미분류 concept는 kind 없이 보존(억지 분류 안 함).
"""
from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable
from dataclasses import replace
from pathlib import Path

from synapse_memory.model import Entity
from synapse_memory.store import list_current_entities, save_page

Classifier = Callable[[Entity], "str | None"]

# 순서 = 우선순위. 더 구체적인 kind(algorithm)를 먼저 검사.
_KIND_KEYWORDS: dict[str, tuple[str, ...]] = {
    "algorithm": ("알고리즘", "algorithm", "정렬", "sort", "탐색", "search", "heap", "complexity", "빅오", "big-o"),
    "methodology": ("방법론", "methodology", "원칙", "principle", "패턴", "pattern", "tdd", "solid", "process", "워크플로", "workflow"),
    "tool": ("도구", "tool", "cli", "플러그인", "plugin", "sdk", "프레임워크", "framework", "라이브러리", "library", "명령어"),
    "technology": ("기술", "technology", "동시성", "concurrency", "프로토콜", "protocol", "api", "런타임", "runtime"),
}


def heuristic_kind(entity: Entity) -> str | None:
    """title/keywords/body에서 kind를 추정. 근거 없으면 None."""
    keywords = entity.attrs.get("keywords") or ()
    text = " ".join([entity.title, *(str(k) for k in keywords), entity.body]).lower()
    for kind, needles in _KIND_KEYWORDS.items():
        if any(needle.lower() in text for needle in needles):
            return kind
    return None


def propose_kind_updates(
    concepts: Iterable[Entity],
    classifier: Classifier = heuristic_kind,
) -> list[tuple[Entity, str]]:
    """kind 없는 concept에 대해 (entity, 제안kind). 이미 kind 있거나 미분류면 제외."""
    updates: list[tuple[Entity, str]] = []
    for concept in concepts:
        if concept.type != "concept" or concept.attrs.get("kind"):
            continue
        kind = classifier(concept)
        if kind:
            updates.append((concept, kind))
    return updates


def apply_kind_updates(
    updates: list[tuple[Entity, str]],
    *,
    vault_path: Path | None = None,
) -> list[str]:
    """제안 kind를 반영해 저장. 반환: 갱신된 slug 목록."""
    written: list[str] = []
    for concept, kind in updates:
        save_page(
            replace(concept, attrs={**concept.attrs, "kind": kind}),
            vault_path=vault_path,
        )
        written.append(concept.slug)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill concept.kind (dry-run 기본).")
    parser.add_argument("--vault", type=Path, default=None, help="vault root (기본: 설정)")
    parser.add_argument("--apply", action="store_true", help="실제 저장 (없으면 dry-run)")
    args = parser.parse_args(argv)

    concepts = list_current_entities("concept", vault_path=args.vault)
    updates = propose_kind_updates(concepts)
    if not updates:
        print("제안할 kind 없음 (모두 태깅됐거나 미분류).")
        return 0
    for concept, kind in updates:
        print(f"{'APPLY' if args.apply else 'DRY '}  {concept.slug} -> kind={kind}")
    if args.apply:
        written = apply_kind_updates(updates, vault_path=args.vault)
        print(f"{len(written)}개 저장.")
    else:
        print(f"dry-run: {len(updates)}개 제안. 반영하려면 --apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
