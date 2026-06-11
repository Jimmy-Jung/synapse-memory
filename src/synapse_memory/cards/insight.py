"""Insight Card — ask 답변의 영속화.

좋은 답변은 채팅에서 증발하지 않고 vault에 쌓인다.

저장 위치: ``<vault>/20_Reference/Insights/<yyyy>/<mm>/<insight_id>.md``

저자: JunyoungJung
작성일: 2026-06-11
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from synapse_memory.cards.project import FRONTMATTER_DELIMITER, slugify
from synapse_memory.collectors.obsidian.mirror import get_vault_path
from synapse_memory.config import get_config

DEFAULT_INSIGHTS_SUBPATH = Path("20_Reference") / "Insights"
_FRONTMATTER_RE = re.compile(
    r"^---\s*\n(?P<yaml>.*?)\n---\s*\n?(?P<body>.*)$",
    re.DOTALL,
)


@dataclass
class InsightCard:
    """저장된 답변 1건."""

    insight_id: str
    question: str
    command: str
    created: str
    related: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    status: str = "draft"
    confidence: float = 0.7
    body: str = ""

    @property
    def filename(self) -> str:
        return f"{self.insight_id}.md"


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


def serialize_insight_card(card: InsightCard) -> str:
    """InsightCard → markdown 문자열."""
    fm = _frontmatter_dict(card)
    yaml_text = yaml.safe_dump(
        fm,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    ).rstrip()
    body = card.body.lstrip("\n")
    return f"{FRONTMATTER_DELIMITER}\n{yaml_text}\n{FRONTMATTER_DELIMITER}\n\n{body}"


def parse_insight_card(text: str) -> InsightCard:
    """markdown 문자열 → InsightCard."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError("frontmatter (--- ... ---) 없음")

    try:
        meta = yaml.safe_load(match.group("yaml")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"frontmatter yaml 파싱 실패: {exc}") from exc

    if not isinstance(meta, dict):
        raise ValueError(f"frontmatter가 dict 아님: {type(meta).__name__}")

    insight_id = meta.get("insight_id")
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
        body=match.group("body").strip(),
    )


def save_insight_card(
    card: InsightCard, *, vault_path: Path | None = None
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
) -> InsightCard:
    """ID와 created timestamp로 InsightCard를 로드한다."""
    path = insights_dir(created, vault_path=vault_path) / f"{insight_id}.md"
    if not path.is_file():
        raise FileNotFoundError(f"Insight Card 없음: {path}")
    return parse_insight_card(path.read_text(encoding="utf-8"))


def list_insight_cards(*, vault_path: Path | None = None) -> list[InsightCard]:
    """vault 안 모든 Insight Card 로드. parse 실패 파일은 skip."""
    vault = (vault_path or get_vault_path()).expanduser().resolve()
    root = vault / get_config().vault_folders.reference.insights
    if not root.is_dir():
        return []

    cards: list[InsightCard] = []
    for path in sorted(root.glob("**/*.md")):
        try:
            cards.append(parse_insight_card(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return sorted(cards, key=lambda card: (card.created, card.insight_id))


def _frontmatter_dict(card: InsightCard) -> dict[str, Any]:
    d: dict[str, Any] = {
        "insight_id": card.insight_id,
        "question": card.question,
        "command": card.command,
        "created": card.created,
        "status": card.status,
        "confidence": card.confidence,
        "tags": ["node/insight"],
    }
    if card.related:
        d["related"] = card.related
    if card.keywords:
        d["keywords"] = card.keywords
    return d


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
