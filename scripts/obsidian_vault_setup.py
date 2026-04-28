#!/usr/bin/env python3
"""
Initialize a Synapse-style Obsidian Vault folder structure.

Author: JunyoungJung
Date: 2026-04-28
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any


BASE_DIRS = [
    "00_Inbox",
    "10_Active",
    "20_Reference",
    "20_Reference/Principles",
    "20_Reference/Patterns",
    "20_Reference/Snippets",
    "20_Reference/Topics",
    "30_Creative",
    "30_Creative/Drafts",
    "30_Creative/Skills",
    "30_Creative/Published",
    "40_Life",
    "40_Life/Money",
    "40_Life/Travel",
    "40_Life/Hobby",
    "90_System",
    "90_System/Templates",
    "90_System/Attachments",
    "99_Archive",
]

AI_MEMORY_DIRS = [
    "90_System/AI",
    "90_System/AI/MemoryInbox",
    "90_System/AI/Policies",
    "90_System/AI/Schemas",
    "90_System/AI/Scripts",
    "90_System/AI/Tests",
    "90_System/AI/Sessions",
    "90_System/AI/Prompts",
]


def today() -> str:
    return dt.date.today().isoformat()


def frontmatter(title: str, category: str, author: str) -> str:
    return f"""---
title: {title}
date: {today()}
category: {category}
author: {author}
tags:
  - dom/meta
  - type/system
---
"""


def home_md(author: str) -> str:
    return frontmatter("Home", "System", author) + """
# Home

## Active

- [[10_Active/MOC - 진행중]]

## System

- [[90_System/AI/README]]
"""


def active_moc(author: str) -> str:
    return frontmatter("MOC - 진행중", "Active", author) + """
# MOC - 진행중

현재 진행 중인 작업을 연결합니다.
"""


def ai_readme(author: str) -> str:
    return frontmatter("Synapse AI Memory", "System/AI", author) + """
# Synapse AI Memory

이 폴더는 AI가 참조할 수 있는 승인된 장기 기억 계층입니다.

raw conversation, near-raw transcript, parser output, redaction report는 이 Vault에 저장하지 않습니다.
"""


def planned_files(author: str, *, with_ai_memory: bool) -> dict[str, str]:
    files = {
        "90_System/Home.md": home_md(author),
        "10_Active/MOC - 진행중.md": active_moc(author),
    }
    if with_ai_memory:
        files["90_System/AI/README.md"] = ai_readme(author)
    return files


def plan(vault_root: Path, *, with_ai_memory: bool, author: str) -> dict[str, Any]:
    dirs = list(BASE_DIRS)
    if with_ai_memory:
        dirs.extend(AI_MEMORY_DIRS)
    files = planned_files(author, with_ai_memory=with_ai_memory)
    return {
        "vault_root": str(vault_root),
        "directories": [str(vault_root / item) for item in dirs],
        "files": [str(vault_root / item) for item in files],
    }


def apply_setup(vault_root: Path, *, with_ai_memory: bool, author: str, overwrite: bool = False) -> dict[str, Any]:
    setup_plan = plan(vault_root, with_ai_memory=with_ai_memory, author=author)
    created_dirs: list[str] = []
    created_files: list[str] = []
    skipped_files: list[str] = []

    for raw in setup_plan["directories"]:
        path = Path(raw)
        existed = path.exists()
        path.mkdir(parents=True, exist_ok=True)
        if not existed:
            created_dirs.append(str(path))

    for rel, content in planned_files(author, with_ai_memory=with_ai_memory).items():
        path = vault_root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not overwrite:
            skipped_files.append(str(path))
            continue
        path.write_text(content.strip() + "\n", encoding="utf-8")
        created_files.append(str(path))

    return {
        **setup_plan,
        "created_dirs": created_dirs,
        "created_files": created_files,
        "skipped_files": skipped_files,
        "applied": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Initialize a Synapse-style Obsidian Vault")
    parser.add_argument("--vault-root", type=Path, required=True)
    parser.add_argument("--author", default="JunyoungJung")
    parser.add_argument("--with-ai-memory", action="store_true", default=True)
    parser.add_argument("--without-ai-memory", action="store_false", dest="with_ai_memory")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)

    if args.apply:
        result = apply_setup(
            args.vault_root.expanduser(),
            with_ai_memory=args.with_ai_memory,
            author=args.author,
            overwrite=args.overwrite,
        )
    else:
        result = {
            **plan(args.vault_root.expanduser(), with_ai_memory=args.with_ai_memory, author=args.author),
            "applied": False,
        }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
