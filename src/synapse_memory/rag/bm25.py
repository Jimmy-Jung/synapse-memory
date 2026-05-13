"""BM25 sidecar index for hybrid RAG retrieval.

저자: Synapse Memory Maintainers
작성일: 2026-05-12
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from synapse_memory.storage.l0 import l0_root, secure_write_text

DEFAULT_BM25_SUBPATH = Path("rag") / "bm25.jsonl"
_BM25_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9가-힣]+")
PROHIBITED_METADATA_KEYS = frozenset(
    {
        "raw_prompt",
        "raw_response",
        "raw_body",
        "note_body",
        "message_body",
        "api_key",
        "oauth_token",
        "access_token",
        "refresh_token",
    }
)


class BM25IndexError(RuntimeError):
    """BM25 sidecar 파일이 없거나 사용할 수 없는 상태."""


@dataclass(frozen=True)
class BM25Document:
    record_id: str
    text: str
    tokens: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)


def tokenize_for_bm25(text: str) -> list[str]:
    """Korean/English proper-noun friendly tokenizer."""
    return [match.group(0).lower() for match in _BM25_TOKEN_PATTERN.finditer(text)]


def default_bm25_path() -> Path:
    return l0_root() / DEFAULT_BM25_SUBPATH


def write_bm25_documents(
    documents: Sequence[BM25Document],
    *,
    path: Path | None = None,
) -> Path:
    """BM25 sidecar JSONL을 user-only file로 저장한다."""
    target = (path or default_bm25_path()).expanduser().resolve()
    for doc in documents:
        _validate_bm25_document(doc)
    lines = [json.dumps(asdict(doc), ensure_ascii=False, sort_keys=True) for doc in documents]
    content = "\n".join(lines)
    if content:
        content += "\n"
    return secure_write_text(target, content)


def load_bm25_documents(
    *,
    path: Path | None = None,
    require: bool = False,
) -> list[BM25Document]:
    """BM25 sidecar JSONL을 읽는다."""
    target = (path or default_bm25_path()).expanduser().resolve()
    if not target.exists():
        if require:
            raise BM25IndexError(f"BM25 sidecar 없음: {target}")
        return []

    documents: list[BM25Document] = []
    try:
        for line in target.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            raw = json.loads(line)
            documents.append(
                BM25Document(
                    record_id=str(raw["record_id"]),
                    text=str(raw["text"]),
                    tokens=[str(token) for token in raw.get("tokens", [])],
                    metadata=dict(raw.get("metadata", {})),
                )
            )
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise BM25IndexError(f"BM25 sidecar 읽기 실패: {target}: {exc}") from exc
    return documents


def search_bm25(
    query: str,
    documents: Sequence[BM25Document],
    *,
    top_k: int = 10,
) -> list[tuple[BM25Document, float]]:
    """BM25 keyword 검색 결과를 score 내림차순으로 반환한다."""
    query_tokens = tokenize_for_bm25(query)
    if not query_tokens or not documents:
        return []
    try:
        from rank_bm25 import BM25Okapi  # type: ignore[import-untyped]
    except ImportError as exc:
        raise BM25IndexError("rank-bm25 미설치 — `pip install -e '.[rag]'`") from exc

    corpus = [doc.tokens for doc in documents]
    bm25 = BM25Okapi(corpus)
    raw_scores = bm25.get_scores(query_tokens)

    ranked: list[tuple[BM25Document, float]] = []
    query_set = set(query_tokens)
    for doc, score in zip(documents, raw_scores, strict=True):
        overlap = len(query_set.intersection(doc.tokens))
        adjusted = float(score) + float(overlap)
        if adjusted > 0:
            ranked.append((doc, adjusted))

    ranked.sort(key=lambda item: (-item[1], item[0].record_id))
    return ranked[:top_k]


def _validate_bm25_document(document: BM25Document) -> None:
    for key in document.metadata:
        if str(key).lower() in PROHIBITED_METADATA_KEYS:
            raise ValueError(f"BM25 metadata field is prohibited: {key}")
