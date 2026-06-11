"""~/.synapse/projects.yaml registry for cross-project marker tracking."""

from __future__ import annotations

import contextlib
import datetime
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml

__all__ = [
    "ProjectEntry",
    "load_registry",
    "mark_stale",
    "save_registry",
    "upsert_entry",
]


@dataclass(eq=True)
class ProjectEntry:
    path: Path
    target: str
    registered_at: datetime.date
    last_sync: datetime.date | None = None
    state: str = "active"


def _entry_to_dict(e: ProjectEntry) -> dict[str, object]:
    return {
        "path": str(e.path),
        "target": e.target,
        "registered_at": e.registered_at.isoformat(),
        "last_sync": e.last_sync.isoformat() if e.last_sync else None,
        "state": e.state,
    }


def _dict_to_entry(d: dict[str, object]) -> ProjectEntry:
    last_sync_raw = d.get("last_sync")
    return ProjectEntry(
        path=Path(str(d["path"])),
        target=str(d["target"]),
        registered_at=datetime.date.fromisoformat(str(d["registered_at"])),
        last_sync=(
            datetime.date.fromisoformat(str(last_sync_raw))
            if last_sync_raw
            else None
        ),
        state=str(d.get("state", "active")),
    )


def load_registry(registry_path: Path) -> list[ProjectEntry]:
    if not registry_path.is_file():
        return []
    data = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    raw_projects = data.get("projects", []) or []
    return [_dict_to_entry(d) for d in raw_projects]


def save_registry(entries: list[ProjectEntry], registry_path: Path) -> None:
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "projects": [_entry_to_dict(e) for e in entries],
    }
    serialized = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    fd, tmp = tempfile.mkstemp(
        prefix="projects-", suffix=".yaml.tmp", dir=str(registry_path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(serialized)
        os.replace(tmp, registry_path)
        _save_json_sidecar(entries, registry_path.with_suffix(".json"))
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _save_json_sidecar(entries: list[ProjectEntry], path: Path) -> None:
    payload = {
        "version": 1,
        "projects": [_entry_to_dict(e) for e in entries],
    }
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    fd, tmp = tempfile.mkstemp(
        prefix="projects-", suffix=".json.tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(serialized)
        os.replace(tmp, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def upsert_entry(
    entries: list[ProjectEntry], new: ProjectEntry
) -> list[ProjectEntry]:
    result: list[ProjectEntry] = []
    replaced = False
    for e in entries:
        if e.path == new.path:
            result.append(new)
            replaced = True
        else:
            result.append(e)
    if not replaced:
        result.append(new)
    return result


def mark_stale(entries: list[ProjectEntry], path: Path) -> list[ProjectEntry]:
    result: list[ProjectEntry] = []
    for e in entries:
        if e.path == path:
            result.append(
                ProjectEntry(
                    path=e.path,
                    target=e.target,
                    registered_at=e.registered_at,
                    last_sync=e.last_sync,
                    state="stale",
                )
            )
        else:
            result.append(e)
    return result
