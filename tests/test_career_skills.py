"""Career skill packaging and reference contracts.

Author: JunyoungJung
Created: 2026-09-22
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
NAMES = ("career-write", "career-interview", "career-tailor")


def _skill_roots() -> tuple[Path, Path]:
    claude = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
    catalog = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text())
    plugin = next(item for item in catalog["plugins"] if item["name"] == "sm")
    codex_root = ROOT / plugin["source"]["path"]
    codex = json.loads((codex_root / ".codex-plugin/plugin.json").read_text())
    return ROOT / claude["skills"], codex_root / codex["skills"]


@pytest.mark.parametrize("name", NAMES)
def test_career_skills_ship_identical_complete_reference_trees(name: str) -> None:
    roots = _skill_roots()
    trees = []
    for root in roots:
        skill = root / name
        entry = skill / "SKILL.md"
        assert entry.is_file(), entry
        metadata = yaml.safe_load(entry.read_text().split("---", 2)[1])
        assert metadata["name"] == name
        assert isinstance(metadata["description"], str) and metadata["description"].strip()
        assert f"`/sm:{name}`" in entry.read_text()
        assert f"`$sm:{name}`" in entry.read_text()
        tree = {p.relative_to(skill): p.read_bytes() for p in skill.rglob("*") if p.is_file()}
        for path in skill.rglob("*.md"):
            for target in re.findall(r"\[[^\]\n]+\]\(([^)\s]+)\)", path.read_text()):
                url = urlsplit(target)
                if url.scheme or not url.path:
                    continue
                linked = (path.parent / unquote(url.path)).resolve()
                assert linked.is_relative_to(root.resolve()), (path, target)
                assert linked.is_file(), (path, target)
        trees.append(tree)
    assert trees[0] == trees[1], f"Claude/Codex package drift: {name}"


def test_career_commands_delegate_without_running_provider_cli() -> None:
    for name in NAMES:
        command = ROOT / "commands" / f"{name}.md"
        content = command.read_text()
        target = f"../skills/{name}/SKILL.md"
        assert target in content
        assert (command.parent / target).resolve().is_file()
        assert "!`" not in content, "Career command must not execute a one-shot provider CLI"
        assert "$ARGUMENTS" in content
    assert not (ROOT / "commands/resume.md").exists()
    for root in _skill_roots():
        assert not (root / "resume").exists()


def test_codex_career_prompt_resolves_to_packaged_plugin_skill() -> None:
    for manifest in (
        ROOT / ".codex-plugin/plugin.json",
        ROOT / "plugins/sm/.codex-plugin/plugin.json",
    ):
        plugin = json.loads(manifest.read_text())
        prompts = "\n".join(plugin["interface"]["defaultPrompt"])
        references = re.findall(r"\$(\S*career-[\w-]+)", prompts)
        assert references
        for reference in references:
            namespace, separator, name = reference.partition(":")
            assert separator and namespace == plugin["name"], reference
            assert name in NAMES
            assert (manifest.parent.parent / plugin["skills"] / name / "SKILL.md").is_file()
