#!/usr/bin/env python3
"""One-time migration: absorb deprecated about relation into related.

Author: JunyoungJung
Created: 2026-07-07
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, NamedTuple

from synapse_memory.model.frontmatter import parse_frontmatter, serialize_frontmatter


class AboutMigrationResult(NamedTuple):
    changed: tuple[Path, ...]
    skipped: tuple[tuple[Path, str], ...]


def migrate_about_to_related(
    vault_path: Path,
    *,
    dry_run: bool = True,
) -> AboutMigrationResult:
    changed: list[Path] = []
    skipped: list[tuple[Path, str]] = []
    for path in sorted(Path(vault_path).expanduser().rglob("*.md")):
        try:
            meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            skipped.append((path, str(exc)))
            continue
        if "about" not in meta:
            continue
        _absorb_about(meta)
        changed.append(path)
        if not dry_run:
            path.write_text(serialize_frontmatter(meta, body), encoding="utf-8")
    return AboutMigrationResult(changed=tuple(changed), skipped=tuple(skipped))


def _absorb_about(meta: dict[str, Any]) -> None:
    about_values = _as_list(meta.pop("about", ()))
    related_values = _as_list(meta.get("related"))
    merged: list[str] = []
    seen: set[str] = set()
    for value in [*related_values, *about_values]:
        if not value or value in seen:
            continue
        seen.add(value)
        merged.append(value)
    if merged:
        meta["related"] = merged
    else:
        meta.pop("related", None)


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return [str(value)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Move deprecated about frontmatter values into related."
    )
    parser.add_argument("--vault", required=True, type=Path)
    parser.add_argument("--apply", action="store_true", help="write migrated files")
    args = parser.parse_args(argv)

    vault = args.vault.expanduser()
    if not vault.is_dir():
        print(f"vault not found: {vault}", file=sys.stderr)
        return 2
    result = migrate_about_to_related(vault, dry_run=not args.apply)
    mode = "apply" if args.apply else "dry-run"
    print(f"{mode}: {len(result.changed)} files with about, skipped {len(result.skipped)}")
    for path in result.changed:
        print(f"  {path}")
    if not args.apply:
        print("no files written; rerun with --apply to modify the vault")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
