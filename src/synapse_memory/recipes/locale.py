"""Locale precedence resolver.

Spec: ``specs/007-persona-recipes/spec.md`` FR-005 + clarify Q1.

precedence:
  1. CLI --language arg
  2. CompanyCard.resume_language
  3. Profile.md frontmatter `preferred_lang`
  4. default "한국어"

저자: Synapse Memory Maintainers
작성일: 2026-05-12
"""

from __future__ import annotations

import re
from typing import Any

from synapse_memory.recipes.recipe import LocaleSource

DEFAULT_LOCALE = "한국어"

# ISO short code → 사람이 읽는 표기. 부재 코드는 그대로 반환.
_LOCALE_ALIAS = {
    "ko": "한국어",
    "kor": "한국어",
    "en": "English",
    "eng": "English",
    "ja": "Japanese",
    "jp": "Japanese",
    "jpn": "Japanese",
    "zh": "Chinese",
    "cn": "Chinese",
    "zh-cn": "Chinese",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese",
}

_FRONTMATTER_RE = re.compile(
    r"^---\s*\n(?P<yaml>.*?)\n---\s*\n", re.DOTALL | re.MULTILINE
)
_FIELD_RE = re.compile(
    r"^\s*preferred_lang\s*:\s*(?P<v>['\"]?)(?P<value>[^\"'\n]+)(?P=v)\s*$",
    re.MULTILINE,
)


def _normalize(value: str) -> str:
    v = value.strip()
    if not v:
        return DEFAULT_LOCALE
    return _LOCALE_ALIAS.get(v.lower(), v)


def _parse_profile_preferred_lang(profile_text: str) -> str | None:
    if not profile_text:
        return None
    m = _FRONTMATTER_RE.search(profile_text)
    if not m:
        return None
    body = m.group("yaml")
    field = _FIELD_RE.search(body)
    if not field:
        return None
    return field.group("value").strip()


def resolve_locale(
    *,
    cli_arg: str | None = None,
    company: Any = None,
    profile_text: str = "",
) -> tuple[str, LocaleSource]:
    """precedence 에 따라 (locale, source) 결정."""
    if cli_arg and cli_arg.strip():
        return _normalize(cli_arg), "cli"

    if company is not None:
        company_lang = getattr(company, "resume_language", None)
        if isinstance(company_lang, str) and company_lang.strip():
            return _normalize(company_lang), "company_card"

    profile_lang = _parse_profile_preferred_lang(profile_text)
    if profile_lang:
        return _normalize(profile_lang), "profile"

    return DEFAULT_LOCALE, "default"
