"""Unit tests for synapse_memory.projects.summary (US1/US2)."""

from __future__ import annotations

import json
from pathlib import Path

from synapse_memory.projects.summary import (
    generate_marker_body,
    render_context_cache,
    render_hook_settings_cache,
)


def _make_profile(path: Path) -> None:
    path.write_text(
        "---\ntitle: AI Profile\n---\n"
        "# AI Profile\n\n"
        "## Tech\n\n"
        "- iOS 개발 주력\n"
        "- Swift 아키텍처\n"
        "- Obsidian + synapse-memory\n"
        "- Modular architecture\n"
        "- Debugging\n"
        "- Blog writing\n",
        encoding="utf-8",
    )


def _make_patterns(path: Path) -> None:
    path.write_text(
        "---\ntitle: Decision Patterns\n---\n"
        "# Decision Patterns\n\n"
        "## Approved Patterns\n\n"
        "- 변경완료 → 기능단위 커밋\n"
        "- 버그 발견 → 원인 분석 우선\n"
        "- 백그라운드 10분+ → 진행 상황 문의\n"
        "- speckit 시퀀스\n"
        "- 토큰 한도 → Codex 인계\n",
        encoding="utf-8",
    )


def test_generate_marker_body_basic(tmp_path: Path) -> None:
    profile = tmp_path / "Profile.md"
    patterns = tmp_path / "DecisionPatterns.md"
    _make_profile(profile)
    _make_patterns(patterns)

    body = generate_marker_body(profile, patterns)

    assert str(profile) in body, "Profile 절대 경로 포함"
    assert str(patterns) in body, "Patterns 절대 경로 포함"
    assert "iOS 개발 주력" in body
    assert "변경완료" in body or "기능단위" in body


def test_fact_top_n_limits_output(tmp_path: Path) -> None:
    profile = tmp_path / "Profile.md"
    patterns = tmp_path / "DecisionPatterns.md"
    _make_profile(profile)
    _make_patterns(patterns)

    body = generate_marker_body(profile, patterns, fact_top_n=2)

    assert "iOS 개발 주력" in body
    assert "Swift 아키텍처" in body
    assert "Modular architecture" not in body, "3번째 fact는 누락"


def test_pattern_top_m_limits_output(tmp_path: Path) -> None:
    profile = tmp_path / "Profile.md"
    patterns = tmp_path / "DecisionPatterns.md"
    _make_profile(profile)
    _make_patterns(patterns)

    body = generate_marker_body(profile, patterns, pattern_top_m=1)

    assert "변경완료" in body or "기능단위" in body
    assert "버그 발견" not in body, "2번째 pattern은 누락"


def test_render_context_cache_writes_bounded_file(tmp_path: Path) -> None:
    profile = tmp_path / "Profile.md"
    patterns = tmp_path / "DecisionPatterns.md"
    _make_profile(profile)
    _make_patterns(patterns)
    out = tmp_path / "context" / "rendered.md"

    path = render_context_cache(profile, patterns, out_path=out, max_bytes=4096)

    assert path == out
    text = out.read_text(encoding="utf-8")
    assert "Second Brain" in text
    assert "iOS 개발 주력" in text


def test_render_context_cache_truncates_to_byte_limit(tmp_path: Path) -> None:
    profile = tmp_path / "Profile.md"
    patterns = tmp_path / "DecisionPatterns.md"
    profile.write_text("\n".join(f"- fact {i} {'가' * 20}" for i in range(100)), encoding="utf-8")
    patterns.write_text("\n".join(f"- pattern {i} {'나' * 20}" for i in range(100)), encoding="utf-8")
    out = tmp_path / "context" / "rendered.md"

    render_context_cache(profile, patterns, out_path=out, max_bytes=512)

    content = out.read_bytes()
    assert len(content) <= 512
    assert "요약 일부" in content.decode("utf-8", errors="ignore")


def test_render_hook_settings_cache_writes_runtime_json(tmp_path: Path) -> None:
    out = tmp_path / "context" / "settings.json"

    path = render_hook_settings_cache(
        enabled=True,
        suggest_register=True,
        max_inject_bytes=1024,
        out_path=out,
    )

    assert path == out
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data == {
        "version": 1,
        "hook": {
            "enabled": True,
            "suggest_register": True,
            "max_inject_bytes": 1024,
        },
    }
