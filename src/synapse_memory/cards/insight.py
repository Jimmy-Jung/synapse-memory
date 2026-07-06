"""Insight entity compatibility helpers.

좋은 답변은 채팅에서 증발하지 않고 vault에 쌓인다.

저장 위치: ``<vault>/20_Reference/Insights/<yyyy>/<mm>/<insight_id>.md``
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from synapse_memory.cards.project import slugify
from synapse_memory.config import get_config, get_vault_path
from synapse_memory.model import Entity, parse_frontmatter, serialize_entity

DEFAULT_INSIGHTS_SUBPATH = Path("20_Reference") / "Insights"
INSIGHT_DEFAULT_ATTRS: dict[str, Any] = {
    "question": "",
    "command": "",
    "related": [],
    "keywords": [],
    "confidence": 0.7,
}


def InsightCard(
    insight_id: str,
    question: str,
    command: str,
    created: str | None = None,
    related: list[str] | None = None,
    keywords: list[str] | None = None,
    status: str = "draft",
    confidence: float = 0.7,
    observed_at: str | None = None,
    supersedes: list[str] | None = None,
    body: str = "",
) -> Entity:
    """Compatibility constructor returning the single Entity model."""
    attrs = _insight_attrs(
        question=question,
        command=command,
        related=list(related or []),
        keywords=list(keywords or []),
        confidence=confidence,
    )
    return Entity(
        slug=insight_id,
        title=question,
        type="insight",
        status=status,
        created=created,
        observed_at=observed_at,
        body=body,
        attrs=attrs,
        supersedes=tuple(supersedes or ()),
    )


def new_insight_id(question: str, *, now: datetime | None = None) -> str:
    """질문 → 날짜 prefix가 붙은 file-safe ID."""
    ts = now or datetime.now().astimezone()
    return f"{ts:%Y-%m-%d}-{slugify(question)[:40]}"


def insights_dir(created: str, *, vault_path: Path | None = None) -> Path:
    """InsightCard 년/월 저장 디렉토리."""
    vault = (vault_path or get_vault_path()).expanduser().resolve()
    root = vault / get_config().vault_folders.reference.insights
    yyyy = created[:4]
    mm = created[5:7]
    return root / yyyy / mm


def serialize_insight_card(card: Entity) -> str:
    """InsightCard → markdown 문자열."""
    return serialize_entity(card)


def parse_insight_card(text: str) -> Entity:
    """markdown 문자열 → InsightCard."""
    meta, body = parse_frontmatter(text)
    if "type" not in meta:
        meta = {
            **meta,
            "type": "insight",
            "slug": meta.get("insight_id"),
            "title": meta.get("question"),
        }
    if meta.get("type") != "insight":
        raise ValueError(f"알 수 없는 insight type: {meta.get('type')!r}")
    insight_id = meta.get("slug")
    question = meta.get("question")
    command = meta.get("command")
    created = meta.get("created")
    if not insight_id or not question or not command or not created:
        raise ValueError("필수 필드 누락: insight_id, question, command, created")

    return InsightCard(
        insight_id=str(insight_id),
        question=str(question),
        command=str(command),
        created=str(created),
        related=list(meta.get("related") or []),
        keywords=list(meta.get("keywords") or []),
        status=str(meta.get("status", "draft")),
        confidence=float(meta.get("confidence", 0.7)),
        observed_at=str(meta.get("observed_at", "")),
        supersedes=_relation_list(meta.get("supersedes")),
        body=body.strip(),
    )


def save_insight_card(
    card: Entity, *, vault_path: Path | None = None
) -> Path:
    """InsightCard를 vault에 저장한다."""
    directory = insights_dir(card.created, vault_path=vault_path)
    path = _unique_insight_path(directory, card.insight_id)
    if path.stem != card.insight_id:
        card.insight_id = path.stem
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_insight_card(card), encoding="utf-8")
    return path


def load_insight_card(
    insight_id: str,
    created: str,
    *,
    vault_path: Path | None = None,
) -> Entity:
    """ID와 created timestamp로 InsightCard를 로드한다."""
    path = insights_dir(created, vault_path=vault_path) / f"{insight_id}.md"
    if not path.is_file():
        raise FileNotFoundError(f"Insight Card 없음: {path}")
    return parse_insight_card(path.read_text(encoding="utf-8"))


def list_insight_cards(*, vault_path: Path | None = None) -> list[Entity]:
    """vault 안 모든 Insight Card 로드. parse 실패 파일은 skip."""
    vault = (vault_path or get_vault_path()).expanduser().resolve()
    root = vault / get_config().vault_folders.reference.insights
    if not root.is_dir():
        return []

    cards: list[Entity] = []
    for path in sorted(root.glob("**/*.md")):
        try:
            cards.append(parse_insight_card(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return sorted(cards, key=lambda card: (card.created, card.insight_id))


def _unique_insight_path(directory: Path, insight_id: str) -> Path:
    """기존 InsightCard를 덮어쓰지 않는 저장 경로."""
    path = directory / f"{insight_id}.md"
    if not path.exists():
        return path

    suffix = 2
    while True:
        candidate = directory / f"{insight_id}-{suffix}.md"
        if not candidate.exists():
            return candidate
        suffix += 1


def _insight_attrs(**values: Any) -> dict[str, Any]:
    return {**INSIGHT_DEFAULT_ATTRS, **values}


def _relation_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]
