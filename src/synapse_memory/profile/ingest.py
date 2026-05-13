"""외부 markdown/txt 파일 → L0 private mirror → redacted 텍스트 반환.

M1b: `persona ingest --file <path>` 의 백엔드. 지인 기획자 use case
(회고록/일기 흡수) 와 본인 wedge use case (기술 스택 추출) 의 공통 입력 경로다.

흐름::

    paths → L0 raw mirror (0600) → redact_full → combined_redacted 문자열
                                                  └─→ extract_profile_facts(extra_text=...)

raw 텍스트는 ``~/.synapse/private/persona/<sha-prefix>/<filename>`` 에만 저장된다.
vault 에는 redacted 요약과 AI 추출 후보만 들어가는 게 contract.

저자: Synapse Memory Maintainers
작성일: 2026-05-13
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from synapse_memory.redaction import redact_full
from synapse_memory.storage.l0 import l0_root, secure_write_text

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".md", ".markdown", ".txt"})
"""ingest 가 받아들이는 파일 확장자. PDF 등은 M2 후보."""

PERSONA_PRIVATE_SUBDIR = Path("raw") / "persona"


@dataclass(frozen=True)
class IngestedFile:
    """단일 파일 ingest 결과."""

    source_path: Path
    private_path: Path
    redacted_text: str
    content_sha256: str
    skipped_reason: str | None = None  # None / "unsupported" / "empty_redacted"


@dataclass(frozen=True)
class IngestResult:
    """`persona ingest` 1회 호출 집계."""

    files: list[IngestedFile] = field(default_factory=list)
    combined_redacted: str = ""

    @property
    def accepted_count(self) -> int:
        return sum(1 for f in self.files if f.skipped_reason is None)

    @property
    def skipped_count(self) -> int:
        return sum(1 for f in self.files if f.skipped_reason is not None)


def _make_private_path(root: Path, sha: str, filename: str) -> Path:
    """L0 private 안의 mirror 경로. sha prefix 로 충돌 회피."""
    return root / PERSONA_PRIVATE_SUBDIR / sha[:16] / filename


def ingest_files(
    paths: list[Path] | list[str],
    *,
    l0_root_override: Path | None = None,
) -> IngestResult:
    """외부 파일들을 L0 private 에 mirror 후 redacted 텍스트로 묶어 반환.

    Args:
        paths: 흡수할 파일 경로 리스트.
        l0_root_override: L0 root 강제 지정 (테스트용). None 이면 ``l0_root()``.

    Returns:
        IngestResult. unsupported 확장자나 redaction 결과 비면 skipped 로 표시.

    Raises:
        FileNotFoundError: 경로에 파일이 없음.
    """
    root = (l0_root_override or l0_root()).expanduser().resolve()
    results: list[IngestedFile] = []
    combined_parts: list[str] = []

    for raw_path in paths:
        path = Path(raw_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"파일 없음: {path}")

        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            results.append(
                IngestedFile(
                    source_path=path,
                    private_path=path,  # placeholder — 안 씀
                    redacted_text="",
                    content_sha256="",
                    skipped_reason="unsupported",
                )
            )
            continue

        raw_text = path.read_text(encoding="utf-8", errors="replace")
        sha = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

        # L0 private mirror (raw 보존 — 사용자가 redactlist 조정 후 재처리 가능)
        private_path = _make_private_path(root, sha, path.name)
        secure_write_text(private_path, raw_text)

        # Redaction (Pass 1 + Pass 2 if apfel 가능)
        redacted = redact_full(raw_text).redacted
        if not redacted.strip():
            results.append(
                IngestedFile(
                    source_path=path,
                    private_path=private_path,
                    redacted_text="",
                    content_sha256=sha,
                    skipped_reason="empty_redacted",
                )
            )
            continue

        results.append(
            IngestedFile(
                source_path=path,
                private_path=private_path,
                redacted_text=redacted,
                content_sha256=sha,
            )
        )
        combined_parts.append(f"## [{path.name}]\n\n{redacted}")

    combined_redacted = "\n\n".join(combined_parts)
    return IngestResult(files=results, combined_redacted=combined_redacted)
