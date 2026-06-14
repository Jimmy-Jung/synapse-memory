"""SCHEMA.md 생성 검증."""
from __future__ import annotations

from pathlib import Path

from synapse_memory.wiki.schema import (
    SCHEMA_FILENAME,
    ensure_schema,
    schema_path,
    write_schema,
)


def test_schema_path_is_vault_root(tmp_path: Path) -> None:
    assert schema_path(vault_path=tmp_path) == tmp_path.resolve() / SCHEMA_FILENAME


def test_write_schema_creates_file(tmp_path: Path) -> None:
    path = write_schema(vault_path=tmp_path)
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "ingest" in text.lower()
    assert "lint" in text.lower()
    assert "[[" in text


def test_ensure_schema_does_not_overwrite(tmp_path: Path) -> None:
    path = write_schema(vault_path=tmp_path)
    path.write_text("USER EDITED", encoding="utf-8")
    returned = ensure_schema(vault_path=tmp_path)
    assert returned == path
    assert path.read_text(encoding="utf-8") == "USER EDITED"
