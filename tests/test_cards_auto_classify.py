"""Cluster auto-classify 테스트.

AI provider API는 mock — 분류 흐름과 schema 정합성만 검증.

저자: JunyoungJung <joony300@gmail.com>
작성일: 2026-05-10
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from synapse_memory.cards.auto_classify import (
    VALID_KINDS,
    ClusterClassification,
    _build_user_prompt,
    _gather_sample_text,
    classify_cluster,
    load_classifications,
    save_classifications,
)
from synapse_memory.clusters.identify import ProjectCluster
from synapse_memory.llm.apfel import ApfelEnvironment
from synapse_memory.llm.claude import ClaudeEnvironment


def _ai_env() -> ClaudeEnvironment:
    return ClaudeEnvironment(
        claude_path="/opt/homebrew/bin/claude",
        claude_version="2.1.132",
        model="sonnet",
    )


def _apfel_disabled() -> ApfelEnvironment:
    """Pass 2 안 돌아가는 환경 (Pass 1만)."""
    return ApfelEnvironment(None, None, "0", False)


@pytest.fixture
def obs_root(tmp_path: Path) -> Path:
    root = tmp_path / "obs"
    root.mkdir()
    return root


def _make_cluster(
    cluster_id: str,
    obs_files: list[str] = (),
    folder: str | None = None,
) -> ProjectCluster:
    return ProjectCluster(
        cluster_id=cluster_id,
        candidate_name=cluster_id,
        obsidian_files=list(obs_files),
        vault_folders={folder} if folder else set(),
        seed_kind="vault" if folder else "claude_code",
    )


class TestGatherSample:
    def test_reads_files_with_cap(self, obs_root: Path) -> None:
        for i in range(3):
            (obs_root / f"note{i}.md").write_text(f"내용 {i}", encoding="utf-8")
        cluster = _make_cluster(
            "test", obs_files=[f"note{i}.md" for i in range(3)]
        )
        text = _gather_sample_text(cluster, obs_root, max_chars_per_note=100)
        for i in range(3):
            assert f"내용 {i}" in text

    def test_skips_missing_files(self, obs_root: Path) -> None:
        (obs_root / "exists.md").write_text("yes", encoding="utf-8")
        cluster = _make_cluster(
            "test", obs_files=["exists.md", "missing.md"]
        )
        text = _gather_sample_text(cluster, obs_root)
        assert "yes" in text


class TestBuildPrompt:
    def test_includes_metadata(self) -> None:
        cluster = _make_cluster("dansim", folder="10_Active/dansim")
        cluster.tags = {"dom/ios", "status/active"}
        prompt = _build_user_prompt(cluster, "내용")
        assert "dansim" in prompt
        assert "10_Active/dansim" in prompt
        assert "dom/ios" in prompt or "status/active" in prompt
        assert "내용" in prompt


class TestClassifyCluster:
    def _setup(self, obs_root: Path) -> ProjectCluster:
        (obs_root / "n1.md").write_text("프로젝트 회고", encoding="utf-8")
        return _make_cluster(
            "dansim", obs_files=["n1.md"], folder="10_Active/dansim"
        )

    def test_returns_classification(self, obs_root: Path) -> None:
        cluster = self._setup(obs_root)
        with patch(
            "synapse_memory.cards.auto_classify.ai_api.complete_structured"
        ) as mock_cs:
            mock_cs.return_value = {
                "kind": "project",
                "candidate_name": "단심 iOS",
                "rationale": "구체적 앱 개발",
            }
            cls = classify_cluster(
                cluster,
                obs_root=obs_root,
                ai_env=_ai_env(),
                apfel_env=_apfel_disabled(),
            )
        assert cls.cluster_id == "dansim"
        assert cls.kind == "project"
        assert cls.candidate_name == "단심 iOS"

    def test_invalid_kind_falls_back_to_skip(self, obs_root: Path) -> None:
        cluster = self._setup(obs_root)
        with patch(
            "synapse_memory.cards.auto_classify.ai_api.complete_structured"
        ) as mock_cs:
            mock_cs.return_value = {
                "kind": "weirdkind",
                "candidate_name": "x",
                "rationale": "y",
            }
            cls = classify_cluster(
                cluster,
                obs_root=obs_root,
                ai_env=_ai_env(),
                apfel_env=_apfel_disabled(),
            )
        assert cls.kind == "skip"

    def test_non_dict_response_raises(self, obs_root: Path) -> None:
        from synapse_memory.llm.ai_api import AIError
        cluster = self._setup(obs_root)
        with patch(
            "synapse_memory.cards.auto_classify.ai_api.complete_structured"
        ) as mock_cs:
            mock_cs.return_value = "not a dict"
            with pytest.raises(AIError, match="dict 아님"):
                classify_cluster(
                    cluster,
                    obs_root=obs_root,
                    ai_env=_ai_env(),
                    apfel_env=_apfel_disabled(),
                )


class TestPersistence:
    def test_save_load_roundtrip(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("SYNAPSE_L0_ROOT", str(tmp_path))
        items = {
            "a": ClusterClassification("a", "project", "A", "rationale-a"),
            "b": ClusterClassification("b", "company", "B", "rationale-b"),
        }
        path = save_classifications(items)
        assert path.is_file()

        loaded = load_classifications()
        assert set(loaded.keys()) == {"a", "b"}
        assert loaded["a"].kind == "project"
        assert loaded["b"].candidate_name == "B"

    def test_load_missing_returns_empty(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("SYNAPSE_L0_ROOT", str(tmp_path))
        assert load_classifications() == {}


def test_valid_kinds_consistent() -> None:
    assert set(VALID_KINDS) == {"project", "company", "domain", "life", "skip"}
