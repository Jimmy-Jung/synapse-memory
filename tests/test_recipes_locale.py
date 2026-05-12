"""T006 — locale precedence RED tests.

Covers spec FR-005 + clarify Q1.

precedence: CLI arg → CompanyCard.resume_language → Profile.preferred_lang → default "한국어".
"""

from __future__ import annotations


def _profile(preferred_lang: str | None = None, domain: str | None = None) -> str:
    """Return Profile.md raw text (with optional frontmatter)."""
    if preferred_lang is None and domain is None:
        return "이름: 테스트\n강점: ...\n"
    fm_lines = ["---"]
    if preferred_lang:
        fm_lines.append(f"preferred_lang: {preferred_lang}")
    if domain:
        fm_lines.append(f"domain: {domain}")
    fm_lines.append("---\n")
    return "\n".join(fm_lines) + "\n이름: 테스트\n"


class _CompanyStub:
    def __init__(self, resume_language: str | None = None) -> None:
        self.resume_language = resume_language


def test_locale_cli_arg_wins() -> None:
    from synapse_memory.recipes.locale import resolve_locale

    loc, src = resolve_locale(
        cli_arg="English",
        company=_CompanyStub(resume_language="日本語"),
        profile_text=_profile(preferred_lang="한국어"),
    )
    assert loc == "English"
    assert src == "cli"


def test_locale_company_card_when_no_cli() -> None:
    from synapse_memory.recipes.locale import resolve_locale

    loc, src = resolve_locale(
        cli_arg=None,
        company=_CompanyStub(resume_language="en"),
        profile_text=_profile(preferred_lang="한국어"),
    )
    # "en" → English 로 normalize 권장. 최소한 영문 alpha 가 그대로 들어가는 것은 X.
    assert loc in ("English", "en")
    assert src == "company_card"


def test_locale_profile_when_no_cli_no_company() -> None:
    from synapse_memory.recipes.locale import resolve_locale

    loc, src = resolve_locale(
        cli_arg=None,
        company=None,
        profile_text=_profile(preferred_lang="日本語"),
    )
    assert loc in ("日本語", "Japanese")
    assert src == "profile"


def test_locale_default_korean_when_nothing() -> None:
    from synapse_memory.recipes.locale import resolve_locale

    loc, src = resolve_locale(
        cli_arg=None,
        company=None,
        profile_text=_profile(),
    )
    assert loc == "한국어"
    assert src == "default"


def test_locale_default_korean_when_profile_missing_field() -> None:
    """Profile.md frontmatter 자체는 있으나 preferred_lang 필드 없음."""
    from synapse_memory.recipes.locale import resolve_locale

    loc, src = resolve_locale(
        cli_arg=None,
        company=None,
        profile_text=_profile(domain="software"),
    )
    assert loc == "한국어"
    assert src == "default"
