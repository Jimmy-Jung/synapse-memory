"""Local relation evidence lookup and provider privacy boundary.

Author: JunyoungJung
Created: 2026-09-22
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

import synapse_memory.cli as cli
import synapse_memory.wiki.query as query_module
from synapse_memory.model import Entity, RelationEvidence, parse_frontmatter, serialize_frontmatter
from synapse_memory.storage.l0 import l0_root
from synapse_memory.store import save_page
from synapse_memory.wiki.provenance import resolve_relation_evidence
from synapse_memory.wiki.rawdoc import _file_text

QUOTE = "Alpha 프로젝트는 Python을 사용한다."


def _example(source: str = "claude-code", quote: str = QUOTE) -> tuple[Entity, Path]:
    path = l0_root() / "raw" / source / "session.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    event = (
        {"message": {"role": "user", "content": quote}}
        if source == "claude-code"
        else {"type": "event_msg", "payload": {"type": "user_message", "message": quote}}
    )
    path.write_text(json.dumps(event, ensure_ascii=False) + "\n")
    text = _file_text(path, source)
    start = text.index(quote)
    evidence = RelationEvidence(
        relation="uses", target="python", source=f"{source}:session.jsonl",
        start_byte=0, end_byte=path.stat().st_size,
        start_char=start, end_char=start + len(quote),
        sha256=hashlib.sha256(quote.encode()).hexdigest(),
    )
    return Entity(
        type="project", slug="alpha", title="Alpha", body="프로젝트 개요",
        uses=("python",), relation_evidence=(evidence,),
    ), path


@pytest.mark.parametrize("source", ["claude-code", "codex"])
def test_local_lookup_verifies_both_sources_after_append(source: str) -> None:
    page, path = _example(source)
    with path.open("a") as stream:
        stream.write('{"message":{"content":"나중에 추가된 내용"}}\n')

    result = resolve_relation_evidence(page, "uses", "python")

    assert len(result) == 1
    assert result[0].status == "verified"
    assert result[0].excerpt == QUOTE
    assert result[0].evidence.source == f"{source}:session.jsonl"


@pytest.mark.parametrize("change", ["edit", "truncate", "delete", "escape"])
def test_lookup_never_returns_unverified_excerpt(tmp_path: Path, change: str) -> None:
    page, path = _example()
    if change == "edit":
        path.write_text(path.read_text().replace("Python", "Kotlin"))
    elif change == "truncate":
        path.write_text("{}\n")
    elif change == "delete":
        path.unlink()
    else:
        outside = tmp_path / "outside.jsonl"
        outside.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(outside)

    result = resolve_relation_evidence(page, "uses", "python")

    assert len(result) == 1
    assert result[0].status == {
        "edit": "changed", "truncate": "changed", "delete": "missing", "escape": "unsafe",
    }[change]
    assert result[0].excerpt == ""


def test_legacy_relation_has_no_fabricated_provenance() -> None:
    page = Entity(type="project", slug="old", title="Old", uses=("python",))
    assert resolve_relation_evidence(page, "uses", "python") == []
    with pytest.raises(ValueError, match="관계"):
        resolve_relation_evidence(page, "uses", "missing")


def test_cli_lookup_is_local_and_does_not_change_vault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    page, _ = _example()
    saved = save_page(page, vault_path=tmp_path)
    before = saved.read_bytes()
    monkeypatch.setattr(query_module.ai_api, "complete", lambda *a, **k: pytest.fail("LLM call"))

    result = cli.main([
        "entity", "provenance", "project:alpha", "uses", "python",
        "--vault", str(tmp_path), "--json",
    ])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["status"] == "verified"
    assert payload[0]["excerpt"] == QUOTE
    assert saved.read_bytes() == before
    assert QUOTE not in saved.read_text()


def test_cli_reports_legacy_missing_evidence(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    save_page(Entity(type="project", slug="old", title="Old", uses=("python",)), vault_path=tmp_path)
    assert cli.main([
        "entity", "provenance", "project:old", "uses", "python", "--vault", str(tmp_path),
    ]) == 0
    assert "근거 미기록" in capsys.readouterr().out


@pytest.mark.parametrize("as_json", [False, True])
def test_cli_escapes_terminal_controls(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], as_json: bool,
) -> None:
    quote = QUOTE + "\x1b]52;c;ZXhhbXBsZQ==\x07\x9b2J\u202e\n\t끝"
    page, _ = _example(quote=quote)
    save_page(page, vault_path=tmp_path)

    assert cli.main([
        "entity", "provenance", "project:alpha", "uses", "python",
        "--vault", str(tmp_path), *(["--json"] if as_json else []),
    ]) == 0
    output = capsys.readouterr().out
    assert all(char not in output for char in ("\x1b", "\x07", "\x9b", "\u202e"))
    if as_json:
        assert json.loads(output)[0]["excerpt"] == quote
    else:
        assert "\\u001b]52;" in output
        assert "\n\t끝" in output


def test_ask_uses_locators_without_loading_raw(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    page, path = _example()
    page = replace(page, uses=("python", "legacy"))
    path.unlink()
    prompts: list[str] = []
    monkeypatch.setattr(query_module, "_retrieve_wiki", lambda *a, **k: [page])

    def answer(prompt: str, **_kwargs: object) -> str:
        prompts.append(prompt)
        return "근거 위치가 기록되어 있습니다. 원문은 로컬 조회로 확인하세요. [[alpha]]"

    monkeypatch.setattr(query_module.ai_api, "complete", answer)
    result = query_module.ask_wiki("alpha uses python의 근거는?", vault_path=tmp_path, save=True)

    assert result.saved_slug
    assert "claude-code:session.jsonl" in prompts[0]
    assert "legacy" in prompts[0] and "근거 미기록" in prompts[0]
    assert "원문 미조회" in prompts[0]
    assert QUOTE not in prompts[0]
    assert all(QUOTE not in p.read_text() for p in tmp_path.rglob("*.md"))


def test_ask_tolerates_a_legacy_malformed_relation() -> None:
    page = Entity(type="project", slug="old", title="Old", uses=("../bad",))
    assert query_module._build_provenance_context([page]) == ""


def test_lint_reports_invalid_evidence_without_echoing_raw_text(tmp_path: Path) -> None:
    from synapse_memory.wiki.lint import validate_schema_rules

    page, _ = _example()
    saved = save_page(page, vault_path=tmp_path)
    meta, body = parse_frontmatter(saved.read_text())
    meta["relation_evidence"][0]["quote"] = "private-source-example"
    saved.write_text(serialize_frontmatter(meta, body))

    report = validate_schema_rules(vault_path=tmp_path)

    assert any(item.code == "invalid_relation_evidence" for item in report.validation_violations)
    assert "private-source-example" not in report.render_plain()


def test_oversized_source_span_does_not_read_file() -> None:
    page, path = _example()
    evidence = replace(page.relation_evidence[0], end_byte=65 * 1024 * 1024)
    page = replace(page, relation_evidence=(evidence,))
    path.unlink()
    result = resolve_relation_evidence(page, "uses", "python")
    assert result[0].status == "too_large"
    assert not result[0].excerpt
