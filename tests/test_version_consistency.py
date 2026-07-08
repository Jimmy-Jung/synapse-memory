"""릴리즈 게이트 — 모든 매니페스트 version이 pyproject과 일치하는지 강제한다.

2.0.0에서 codex 매니페스트 2개(plugins/sm/.codex-plugin/plugin.json,
.agents/plugins/marketplace.json)가 1.20.0에 정체한 live drift 재발 방지.
release.sh가 파일을 bump하더라도 이 테스트가 사후 정합을 CI에서 실증한다.

저자: JunyoungJung
작성일: 2026-07-08
"""
from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

# top-level "version"을 가진 플러그인 매니페스트.
_PLUGIN_MANIFESTS = (
    ".claude-plugin/plugin.json",
    ".codex-plugin/plugin.json",
    "plugins/sm/.codex-plugin/plugin.json",
)
# plugins[].version(중첩)을 가진 마켓플레이스 카탈로그.
_MARKETPLACE_MANIFESTS = (
    ".claude-plugin/marketplace.json",
    ".agents/plugins/marketplace.json",
)


def _canonical_version() -> str:
    data = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = data.get("project", {})
    if "version" in project:
        return str(project["version"])
    return str(data["tool"]["poetry"]["version"])


def _dunder_version() -> str:
    text = (_ROOT / "src/synapse_memory/__init__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    assert match is not None, "__version__ not found in __init__.py"
    return match.group(1)


def _collect_versions() -> dict[str, str]:
    """{표시경로: version} — 존재하고 version 필드를 가진 모든 소스."""
    found: dict[str, str] = {"src/synapse_memory/__init__.py": _dunder_version()}
    for rel in _PLUGIN_MANIFESTS:
        path = _ROOT / rel
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if "version" in data:
            found[rel] = str(data["version"])
    for rel in _MARKETPLACE_MANIFESTS:
        path = _ROOT / rel
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for plugin in data.get("plugins", []):
            if isinstance(plugin, dict) and "version" in plugin:
                found[f"{rel}#{plugin.get('name', '?')}"] = str(plugin["version"])
    return found


def test_all_manifest_versions_match_pyproject() -> None:
    expected = _canonical_version()
    found = _collect_versions()
    mismatched = {source: v for source, v in found.items() if v != expected}
    assert not mismatched, f"version drift (pyproject={expected}): {mismatched}"


def test_at_least_the_known_manifests_are_present() -> None:
    # drift 감시가 대상 파일 삭제로 무력화되지 않도록 최소 커버리지를 고정한다.
    found = _collect_versions()
    for rel in (".codex-plugin/plugin.json", "plugins/sm/.codex-plugin/plugin.json"):
        assert rel in found, f"{rel} 누락 — 버전 정합 게이트 커버리지 구멍"
