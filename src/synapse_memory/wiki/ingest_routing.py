"""Ingest cost routing and sampling.

Author: JunyoungJung
Created: 2026-07-06
"""
from __future__ import annotations

from dataclasses import dataclass

LARGE_DOC_CHAR_THRESHOLD = 40_000
SAMPLED_DOC_CHAR_LIMIT = 120_000
SAMPLED_DOC_CHAR_BUDGET = 20_000
SAMPLED_DOC_EDGE_CHARS = 6_000
SAMPLED_DOC_SIGNAL_CHARS = 8_000
_SIGNAL_PATTERNS = (
    "/Users/",
    "Documents/Git",
    "Traceback",
    "Error",
    "Exception",
    "Timeout",
    "failed",
    "failed:",
    "User:",
    "Assistant:",
    "cwd=",
    "workdir",
    "pytest",
    "ruff",
    "git ",
)


@dataclass(frozen=True)
class IntegrationChunk:
    ref: str
    text: str
    sampled: bool = False


@dataclass(frozen=True)
class IngestRoute:
    """문서 크기별 ingest 라우팅 결과."""

    kind: str
    estimated_llm_calls: int
    text_chars: int


def classify_ingest_text(text: str, *, semantic_retrieval: bool = True) -> IngestRoute:
    """ingest 비용 정책을 단일 기준으로 분류한다."""
    text_chars = len(text)
    if text_chars <= LARGE_DOC_CHAR_THRESHOLD:
        return IngestRoute(
            kind="small",
            estimated_llm_calls=2 if semantic_retrieval else 1,
            text_chars=text_chars,
        )
    if text_chars <= SAMPLED_DOC_CHAR_LIMIT:
        return IngestRoute(kind="sampled", estimated_llm_calls=1, text_chars=text_chars)
    return IngestRoute(kind="oversize", estimated_llm_calls=0, text_chars=text_chars)


def integration_chunks(ref: str, text: str) -> list[IntegrationChunk]:
    route = classify_ingest_text(text)
    if route.kind == "small":
        return [IntegrationChunk(ref=ref, text=text)]
    if route.kind == "sampled":
        return [
            IntegrationChunk(
                ref=f"{ref}#sample",
                text=_budgeted_sample(text),
                sampled=True,
            )
        ]
    return []


def _budgeted_signal_block(text: str, max_chars: int) -> str:
    lines: list[str] = []
    used = 0
    for raw_line in text.splitlines():
        line = " ".join(raw_line.split())
        if not line or not any(pattern in line for pattern in _SIGNAL_PATTERNS):
            continue
        next_used = used + len(line) + 1
        if next_used > max_chars:
            break
        lines.append(line)
        used = next_used
    return "\n".join(lines)


def _budgeted_sample(text: str) -> str:
    head = text[:SAMPLED_DOC_EDGE_CHARS].strip()
    tail = text[-SAMPLED_DOC_EDGE_CHARS:].strip()
    signal = _budgeted_signal_block(text, SAMPLED_DOC_SIGNAL_CHARS)
    sample = (
        "# 원문 정보\n"
        f"- 원문 문자 수: {len(text)}\n"
        "- 처리 방식: 비용 제한 샘플. 전체 원문은 raw ref를 통해 보존됨.\n\n"
        "# 앞부분 샘플\n"
        f"{head}\n\n"
        "# 고신호 라인\n"
        f"{signal or '(추출된 고신호 라인 없음)'}\n\n"
        "# 뒷부분 샘플\n"
        f"{tail}"
    )
    return sample[:SAMPLED_DOC_CHAR_BUDGET].strip()
