from __future__ import annotations

from pathlib import Path

import synapse_memory.wiki.lint as lint
from synapse_memory.wiki.lint import run_lint, validate_schema_rules


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_run_lint_reports_schema_value_folder_slug_relation_and_index_violations(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "Concepts" / "rag.md",
        """---
type: concept
slug: rag
title: RAG
status: active
---

concept
""",
    )
    _write(
        tmp_path / "Entities" / "Companies" / "acme.md",
        """---
type: company
slug: acme
title: Acme
status: target
size: giant
---

company
""",
    )
    _write(
        tmp_path / "Entities" / "Companies" / "bad-project.md",
        """---
type: project
slug: wrong-slug
title: Bad Project
status: invalid
uses:
  - "[[acme]]"
---

project
""",
    )
    _write(tmp_path / "index.md", "# Index\n\ntotal pages: 99\n")

    report = run_lint(vault_path=tmp_path)
    codes = {violation.code for violation in report.validation_violations}

    assert report.pages_checked == 3
    assert {
        "invalid_enum",
        "type_folder_mismatch",
        "slug_filename_mismatch",
        "relation_range",
        "index_stale",
    } <= codes
    assert "uses range 위반" in report.render_plain()


def test_validate_schema_rules_reports_missing_required_and_bad_type(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "Concepts" / "missing.md",
        """---
type: wibble
slug: missing
---

bad
""",
    )

    report = validate_schema_rules(vault_path=tmp_path)
    codes = [violation.code for violation in report.validation_violations]

    assert "missing_required" in codes
    assert "invalid_type" in codes


def test_run_lint_reports_even_when_private_log_is_not_writable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write(
        tmp_path / "Concepts" / "rag.md",
        """---
type: concept
slug: rag
title: RAG
status: active
---

concept
""",
    )
    monkeypatch.setattr(
        lint,
        "append_log",
        lambda *args, **kwargs: (_ for _ in ()).throw(PermissionError("denied")),
    )

    report = run_lint(vault_path=tmp_path)

    assert report.pages_checked == 1
