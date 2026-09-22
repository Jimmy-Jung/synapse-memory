"""Resolve relation locators locally without sending raw text to a provider.

Author: JunyoungJung
Created: 2026-09-22
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from synapse_memory.model import Entity, RelationEvidence, normalize_relation_target
from synapse_memory.model.entity import RELATION_FIELDS
from synapse_memory.wiki.rawdoc import _file_text, default_source_root

MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_EXCERPT_CHARS = 2000


@dataclass(frozen=True)
class EvidenceResult:
    evidence: RelationEvidence
    status: str
    excerpt: str = ""


def _resolve(evidence: RelationEvidence, raw_root: Path | None) -> EvidenceResult:
    source, _, relative = evidence.source.partition(":")
    root = (raw_root or default_source_root(source)).expanduser().resolve()
    if (
        evidence.end_byte - evidence.start_byte > MAX_SOURCE_BYTES
        or evidence.end_char - evidence.start_char > MAX_EXCERPT_CHARS
    ):
        return EvidenceResult(evidence, "too_large")
    try:
        path = (root / relative).resolve()
        if not path.is_relative_to(root):
            return EvidenceResult(evidence, "unsafe")
        if not path.is_file():
            return EvidenceResult(evidence, "missing")
        if path.stat().st_size < evidence.end_byte:
            return EvidenceResult(evidence, "changed")
        text = _file_text(
            path, source, start_byte=evidence.start_byte, end_byte=evidence.end_byte,
        )
    except (OSError, RuntimeError):
        return EvidenceResult(evidence, "unreadable")
    excerpt = text[evidence.start_char:evidence.end_char]
    if hashlib.sha256(excerpt.encode("utf-8")).hexdigest() != evidence.sha256:
        return EvidenceResult(evidence, "changed")
    return EvidenceResult(evidence, "verified", excerpt)


def resolve_relation_evidence(
    page: Entity,
    relation: str,
    target: str,
    *,
    raw_root: Path | None = None,
) -> list[EvidenceResult]:
    """Verify one actual edge's source ranges; legacy edges return no evidence.

    ``raw_root`` overrides the selected source's mirror directory for callers
    that also ingested with a custom raw root. This function never writes data.
    """
    if relation not in RELATION_FIELDS:
        raise ValueError("알 수 없는 관계입니다.")
    normalized = normalize_relation_target(target)
    targets = {normalize_relation_target(value) for value in getattr(page, relation)}
    if normalized not in targets:
        raise ValueError("해당 관계가 페이지에 없습니다.")
    return [
        _resolve(evidence, raw_root)
        for evidence in page.relation_evidence
        if evidence.relation == relation and evidence.target == normalized
    ]
