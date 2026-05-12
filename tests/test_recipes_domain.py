"""T007 — domain precedence RED tests.

Covers spec FR-006.

precedence: CLI arg → Profile.domain → top tag frequency ≥ 0.3 → "generic".
"""

from __future__ import annotations


def _profile(domain: str | None = None) -> str:
    if domain is None:
        return "이름: 테스트\n"
    return f"---\ndomain: {domain}\n---\n\n이름: 테스트\n"


class _RecordStub:
    """RAG match stub — only `.metadata['tags']` (list[str]) is read by domain resolver."""

    def __init__(self, tags: list[str]) -> None:
        self.metadata = {"tags": tags}


def _matches(tag_lists: list[list[str]]) -> list[tuple[_RecordStub, float]]:
    return [(_RecordStub(tags), 0.5) for tags in tag_lists]


def test_domain_cli_wins() -> None:
    from synapse_memory.recipes.domain import resolve_domain

    d, src = resolve_domain(
        cli_arg="research",
        profile_text=_profile(domain="software"),
        matched=_matches([["swiftui"], ["react"]]),
    )
    assert d == "research"
    assert src == "cli"


def test_domain_profile_when_no_cli() -> None:
    from synapse_memory.recipes.domain import resolve_domain

    d, src = resolve_domain(
        cli_arg=None,
        profile_text=_profile(domain="design"),
        matched=_matches([["swiftui"]]),
    )
    assert d == "design"
    assert src == "profile"


def test_domain_tag_frequency_when_no_profile() -> None:
    """4/5 cards tagged 'software' → frequency 0.8 ≥ 0.3 threshold."""
    from synapse_memory.recipes.domain import resolve_domain

    d, src = resolve_domain(
        cli_arg=None,
        profile_text=_profile(),
        matched=_matches([
            ["software"],
            ["software"],
            ["software"],
            ["software"],
            ["pm"],
        ]),
    )
    assert d == "software"
    assert src == "tags"


def test_domain_generic_when_tags_below_threshold() -> None:
    """No tag exceeds 0.3 frequency → fall back to generic."""
    from synapse_memory.recipes.domain import resolve_domain

    d, src = resolve_domain(
        cli_arg=None,
        profile_text=_profile(),
        matched=_matches([
            ["a"], ["b"], ["c"], ["d"], ["e"],
        ]),
    )
    assert d == "generic"
    assert src == "default"


def test_domain_generic_when_no_matches() -> None:
    from synapse_memory.recipes.domain import resolve_domain

    d, src = resolve_domain(cli_arg=None, profile_text="", matched=[])
    assert d == "generic"
    assert src == "default"
