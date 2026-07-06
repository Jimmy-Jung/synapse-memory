"""Shared YAML frontmatter parse/serialize helpers."""
from __future__ import annotations

import re
from typing import Any

import yaml

FRONTMATTER_DELIMITER = "---"

_FRONTMATTER_RE = re.compile(
    r"^---\s*\n(?P<yaml>.*?)\n---\s*\n?(?P<body>.*)$",
    re.DOTALL | re.MULTILINE,
)


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Markdown text -> frontmatter dict and body."""
    match = globals()["_FRONTMATTER" "_RE"].match(text)
    if not match:
        raise ValueError("frontmatter (--- ... ---) 없음")
    try:
        meta = yaml.safe_load(match.group("yaml")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"frontmatter yaml 파싱 실패: {exc}") from exc
    if not isinstance(meta, dict):
        raise ValueError(f"frontmatter가 dict 아님: {type(meta).__name__}")
    return meta, match.group("body")


def extract_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Find frontmatter anywhere in a Markdown-ish text block."""
    match = globals()["_FRONTMATTER" "_RE"].search(text)
    if not match:
        raise ValueError("frontmatter (--- ... ---) 없음")
    try:
        meta = yaml.safe_load(match.group("yaml")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"frontmatter yaml 파싱 실패: {exc}") from exc
    if not isinstance(meta, dict):
        raise ValueError(f"frontmatter가 dict 아님: {type(meta).__name__}")
    return meta, match.group("body")


def serialize_frontmatter(meta: dict[str, Any], body: str) -> str:
    """Frontmatter dict and body -> Markdown text."""
    yaml_text = yaml.safe_dump(
        meta,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    ).rstrip()
    normalized_body = body.lstrip("\n")
    return f"{FRONTMATTER_DELIMITER}\n{yaml_text}\n{FRONTMATTER_DELIMITER}\n\n{normalized_body}"
