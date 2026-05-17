"""Generate marker body markdown from Profile/DecisionPatterns."""

from __future__ import annotations

from pathlib import Path

__all__ = ["generate_marker_body"]


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

    facts = _extract_bullets(profile_text, fact_top_n)
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
