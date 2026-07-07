"""Generate marker body markdown from Profile/DecisionPatterns."""

from __future__ import annotations

import json
import os
from pathlib import Path

from synapse_memory.profile.dedupe import (
    parse_decision_pattern_triggers,
    parse_profile_facts,
)
from synapse_memory.storage.l0 import secure_write_text

__all__ = [
    "RENDERED_MAX_BYTES",
    "generate_marker_body",
    "render_context_cache",
    "render_hook_settings_cache",
]

RENDERED_MAX_BYTES = 2048
_TRUNCATED_SUFFIX = "\n\n(요약 일부 — 상세: `/sm:ask`)"


def _synapse_home() -> Path:
    return Path(os.environ.get("SYNAPSE_HOME", "~/.synapse")).expanduser()


def _extract_bullets(text: str, limit: int) -> list[str]:
    bullets: list[str] = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("- ") and not stripped.startswith("- ["):
            bullets.append(stripped[2:].strip())
        if len(bullets) >= limit:
            break
    return bullets


def generate_marker_body(
    profile_path: Path,
    patterns_path: Path,
    *,
    fact_top_n: int = 5,
    pattern_top_m: int = 4,
) -> str:
    profile_text = (
        profile_path.read_text(encoding="utf-8") if profile_path.is_file() else ""
    )
    patterns_text = (
        patterns_path.read_text(encoding="utf-8") if patterns_path.is_file() else ""
    )

    facts = parse_profile_facts(profile_path)[:fact_top_n]
    patterns = parse_decision_pattern_triggers(patterns_path)[:pattern_top_m]
    if not facts:
        facts = _extract_bullets(profile_text, fact_top_n)
    if not patterns:
        patterns = _extract_bullets(patterns_text, pattern_top_m)

    lines: list[str] = [
        "## Second Brain (Synapse Memory)",
        "",
        f"Profile: {profile_path}",
        f"Patterns: {patterns_path}",
        "",
        "명령: `/sm:recall <topic>` · `/sm:ask <질문>` 으로 사용자 자료를 조회.",
        "",
        "### Quick reference",
        "",
    ]
    if facts:
        lines.append("**Facts**")
        for f in facts:
            lines.append(f"- {f}")
        lines.append("")
    if patterns:
        lines.append("**Decision patterns**")
        for p in patterns:
            lines.append(f"- {p}")
        lines.append("")

    return "\n".join(lines)


def render_context_cache(
    profile_path: Path,
    patterns_path: Path,
    *,
    out_path: Path | None = None,
    max_bytes: int = RENDERED_MAX_BYTES,
) -> Path:
    """Profile/Patterns → hook 주입용 context cache 파일."""
    out = out_path or _synapse_home() / "context" / "rendered.md"
    body = generate_marker_body(profile_path, patterns_path)
    body = _truncate_utf8(body, max_bytes=max_bytes)
    return secure_write_text(out, body)


def render_hook_settings_cache(
    *,
    enabled: bool,
    suggest_register: bool,
    max_inject_bytes: int,
    out_path: Path | None = None,
) -> Path:
    """hook runner가 stdlib-json만으로 읽는 runtime 설정 sidecar."""
    out = out_path or _synapse_home() / "context" / "settings.json"
    payload = {
        "version": 1,
        "hook": {
            "enabled": enabled,
            "suggest_register": suggest_register,
            "max_inject_bytes": max_inject_bytes,
        },
    }
    body = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    return secure_write_text(out, body)


def _truncate_utf8(text: str, *, max_bytes: int) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    suffix = _TRUNCATED_SUFFIX.encode("utf-8")
    if max_bytes <= len(suffix):
        return suffix[:max_bytes].decode("utf-8", errors="ignore")
    head = encoded[: max_bytes - len(suffix)].decode("utf-8", errors="ignore")
    return head.rstrip() + _TRUNCATED_SUFFIX
