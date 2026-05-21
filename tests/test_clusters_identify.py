"""클러스터 식별 테스트.

저자: Synapse Memory Maintainers
작성일: 2026-05-10
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from synapse_memory.clusters.identify import (
    extract_github_repos,
    extract_tags,
    identify_clusters,
)

# ---------------------------------------------------------------------------
# extract_tags
# ---------------------------------------------------------------------------


class TestExtractTags:
    def test_inline_tags(self) -> None:
        text = "본문 #dom/ios #type/ref 끝 #status/wip"
        tags = extract_tags(text)
        assert tags == {"dom/ios", "type/ref", "status/wip"}

    def test_frontmatter_list(self) -> None:
        text = "---\ntags: [dom/swift, dom/architecture]\n---\n본문"
        tags = extract_tags(text)
        assert "dom/swift" in tags
        assert "dom/architecture" in tags

    def test_frontmatter_string_csv(self) -> None:
        text = "---\ntags: dom/ios, type/ref, status/wip\n---\n본문"
        tags = extract_tags(text)
        assert tags == {"dom/ios", "type/ref", "status/wip"}

    def test_combined_frontmatter_and_body(self) -> None:
        text = (
            "---\n"
            "tags: [dom/ios]\n"
            "---\n"
            "본문 #dom/swift #status/active"
        )
        tags = extract_tags(text)
        assert {"dom/ios", "dom/swift", "status/active"} <= tags

    def test_no_tags(self) -> None:
        assert extract_tags("그냥 평범한 본문") == set()


# ---------------------------------------------------------------------------
# extract_github_repos
# ---------------------------------------------------------------------------


class TestExtractGithubRepos:
    def test_basic(self) -> None:
        text = "경로: /Users/sampleuser/Documents/GitHub/dansim-ios/Sources"
        assert extract_github_repos(text) == {"dansim-ios"}

    def test_multiple(self) -> None:
        text = (
            "/Users/sampleuser/Documents/GitHub/foo "
            "/Users/sampleuser/Documents/GitHub/bar"
        )
        assert extract_github_repos(text) == {"foo", "bar"}

    def test_no_path(self) -> None:
        assert extract_github_repos("그냥 텍스트") == set()


# ---------------------------------------------------------------------------
# identify_clusters
# ---------------------------------------------------------------------------


def _write_jsonl(path: Path, *events: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")


@pytest.fixture
def cc_raw(tmp_path: Path) -> Path:
    """가짜 Claude Code mirror."""
    root = tmp_path / "cc"
    (root / "projects" / "-Users-sampleuser-Documents-GitHub-dansim-ios").mkdir(
        parents=True
    )
    return root


@pytest.fixture
def obs_raw(tmp_path: Path) -> Path:
    """가짜 Obsidian mirror."""
    root = tmp_path / "obs"
    (root / "10_Active").mkdir(parents=True)
    return root


class TestIdentifyClusters:
    def test_seeds_from_claude_code_cwd(
        self, cc_raw: Path, obs_raw: Path
    ) -> None:
        _write_jsonl(
            cc_raw
            / "projects"
            / "-Users-sampleuser-Documents-GitHub-dansim-ios"
            / "abc.jsonl",
            {"cwd": "/Users/sampleuser/Documents/GitHub/dansim-ios", "type": "user"},
        )
        clusters = identify_clusters(
            obsidian_raw=obs_raw, claude_code_raw=cc_raw
        )
        assert len(clusters) == 1
        c = clusters[0]
        assert c.cluster_id == "dansim-ios"
        assert c.cwd_paths == {"/Users/sampleuser/Documents/GitHub/dansim-ios"}
        assert len(c.claude_jsonl) == 1
        assert c.confidence == 0.5  # cwd만

    def test_obsidian_match_increases_confidence(
        self, cc_raw: Path, obs_raw: Path
    ) -> None:
        _write_jsonl(
            cc_raw
            / "projects"
            / "-Users-sampleuser-Documents-GitHub-dansim-ios"
            / "abc.jsonl",
            {"cwd": "/Users/sampleuser/Documents/GitHub/dansim-ios"},
        )
        (obs_raw / "10_Active" / "단심.md").write_text(
            "프로젝트 노트\n경로: /Users/sampleuser/Documents/GitHub/dansim-ios\n"
            "#dom/ios",
            encoding="utf-8",
        )
        clusters = identify_clusters(
            obsidian_raw=obs_raw, claude_code_raw=cc_raw
        )
        c = clusters[0]
        assert len(c.obsidian_files) == 1
        assert "dom/ios" in c.tags
        assert c.confidence == 0.9  # 0.5 + 0.3 + 0.1

    def test_multiple_jsonls_same_cluster(
        self, cc_raw: Path, obs_raw: Path
    ) -> None:
        slug_dir = (
            cc_raw / "projects" / "-Users-sampleuser-Documents-GitHub-dansim-ios"
        )
        _write_jsonl(
            slug_dir / "session1.jsonl",
            {"cwd": "/Users/sampleuser/Documents/GitHub/dansim-ios"},
        )
        _write_jsonl(
            slug_dir / "session2.jsonl",
            {"cwd": "/Users/sampleuser/Documents/GitHub/dansim-ios"},
        )
        clusters = identify_clusters(
            obsidian_raw=obs_raw, claude_code_raw=cc_raw
        )
        assert len(clusters) == 1
        assert len(clusters[0].claude_jsonl) == 2

    def test_obsidian_without_match_ignored(
        self, cc_raw: Path, obs_raw: Path
    ) -> None:
        """GitHub path 없는 노트는 cluster 없이 skip (현재 정책)."""
        (obs_raw / "10_Active" / "no-link.md").write_text(
            "그냥 노트", encoding="utf-8"
        )
        clusters = identify_clusters(
            obsidian_raw=obs_raw, claude_code_raw=cc_raw
        )
        assert clusters == []  # cwd 시드 자체 없음

    def test_jsonl_without_cwd_skipped(
        self, cc_raw: Path, obs_raw: Path
    ) -> None:
        _write_jsonl(
            cc_raw
            / "projects"
            / "-Users-sampleuser-Documents-GitHub-dansim-ios"
            / "no-cwd.jsonl",
            {"type": "queue-operation"},  # cwd 필드 없음
        )
        clusters = identify_clusters(
            obsidian_raw=obs_raw, claude_code_raw=cc_raw
        )
        assert clusters == []

    def test_sorted_by_confidence_desc(
        self, cc_raw: Path, obs_raw: Path
    ) -> None:
        # cluster A: cwd만
        _write_jsonl(
            cc_raw
            / "projects"
            / "-Users-sampleuser-Documents-GitHub-A"
            / "a.jsonl",
            {"cwd": "/Users/sampleuser/Documents/GitHub/A"},
        )
        # cluster B: cwd + obsidian
        _write_jsonl(
            cc_raw
            / "projects"
            / "-Users-sampleuser-Documents-GitHub-B"
            / "b.jsonl",
            {"cwd": "/Users/sampleuser/Documents/GitHub/B"},
        )
        (obs_raw / "10_Active" / "B.md").write_text(
            "/Users/sampleuser/Documents/GitHub/B 참고", encoding="utf-8"
        )
        clusters = identify_clusters(
            obsidian_raw=obs_raw, claude_code_raw=cc_raw
        )
        # B (0.8) → A (0.5)
        assert clusters[0].cluster_id == "B"
        assert clusters[1].cluster_id == "A"

    def test_empty_raws_return_empty(self, tmp_path: Path) -> None:
        clusters = identify_clusters(
            obsidian_raw=tmp_path / "no-obs",
            claude_code_raw=tmp_path / "no-cc",
        )
        assert clusters == []


class TestVaultFolderClusters:
    """vault 폴더 segment 기반 cluster 식별 (Day 4 enrichment)."""

    def test_active_subfolder_becomes_cluster(
        self, cc_raw: Path, obs_raw: Path
    ) -> None:
        # 10_Active/샘플회사/ 안 노트 2개 → cluster "샘플회사"
        (obs_raw / "10_Active" / "샘플회사").mkdir(parents=True)
        (obs_raw / "10_Active" / "샘플회사" / "note1.md").write_text(
            "본문 1", encoding="utf-8"
        )
        (obs_raw / "10_Active" / "샘플회사" / "note2.md").write_text(
            "본문 2", encoding="utf-8"
        )

        clusters = identify_clusters(
            obsidian_raw=obs_raw, claude_code_raw=cc_raw
        )
        ids = {c.cluster_id for c in clusters}
        assert "샘플회사" in ids
        c = next(c for c in clusters if c.cluster_id == "샘플회사")
        assert c.seed_kind == "vault"
        assert len(c.obsidian_files) == 2
        assert "10_Active/샘플회사" in c.vault_folders

    def test_min_files_enforced(self, cc_raw: Path, obs_raw: Path) -> None:
        # 1개 노트만 있는 폴더는 cluster 안 됨
        (obs_raw / "10_Active" / "Solo").mkdir(parents=True)
        (obs_raw / "10_Active" / "Solo" / "alone.md").write_text(
            "x", encoding="utf-8"
        )
        clusters = identify_clusters(
            obsidian_raw=obs_raw, claude_code_raw=cc_raw
        )
        assert all(c.cluster_id != "solo" for c in clusters)

    def test_generic_segment_skipped_one_level(
        self, cc_raw: Path, obs_raw: Path
    ) -> None:
        # 30_Creative/Drafts/AI/ → "Drafts"가 generic이라 → cluster "AI"
        (obs_raw / "30_Creative" / "Drafts" / "AI").mkdir(parents=True)
        for i in range(3):
            (obs_raw / "30_Creative" / "Drafts" / "AI" / f"note{i}.md").write_text(
                "글", encoding="utf-8"
            )
        clusters = identify_clusters(
            obsidian_raw=obs_raw, claude_code_raw=cc_raw
        )
        ids = {c.cluster_id for c in clusters}
        assert "ai" in ids
        # "Drafts"는 cluster 아님
        assert "drafts" not in ids

    def test_excluded_top_levels(self, cc_raw: Path, obs_raw: Path) -> None:
        # 90_System은 제외 대상
        (obs_raw / "90_System" / "AI").mkdir(parents=True)
        for i in range(5):
            (obs_raw / "90_System" / "AI" / f"x{i}.md").write_text(
                "x", encoding="utf-8"
            )
        clusters = identify_clusters(
            obsidian_raw=obs_raw, claude_code_raw=cc_raw
        )
        # 90_System 관련 cluster 없어야
        assert clusters == []

    def test_vault_and_cwd_merge(
        self, cc_raw: Path, obs_raw: Path
    ) -> None:
        """같은 cluster_id로 cwd cluster + vault cluster 만나면 머지."""
        # Claude Code: cluster "dansim-ios" (cwd 시드)
        _write_jsonl(
            cc_raw
            / "projects"
            / "-Users-sampleuser-Documents-GitHub-dansim-ios"
            / "abc.jsonl",
            {"cwd": "/Users/sampleuser/Documents/GitHub/dansim-ios"},
        )
        # Obsidian: 10_Active/dansim-ios/ 안 노트 2개
        (obs_raw / "10_Active" / "dansim-ios").mkdir(parents=True)
        (obs_raw / "10_Active" / "dansim-ios" / "회고.md").write_text(
            "회고", encoding="utf-8"
        )
        (obs_raw / "10_Active" / "dansim-ios" / "기술결정.md").write_text(
            "TCA 도입", encoding="utf-8"
        )

        clusters = identify_clusters(
            obsidian_raw=obs_raw, claude_code_raw=cc_raw
        )
        c = next(c for c in clusters if c.cluster_id == "dansim-ios")
        assert c.seed_kind == "merged"
        assert c.cwd_paths == {"/Users/sampleuser/Documents/GitHub/dansim-ios"}
        assert len(c.obsidian_files) == 2
        assert c.confidence >= 0.8  # cwd + vault → 0.8


# ---------------------------------------------------------------------------
# Codex sessions 시드 — 0.15.7
# ---------------------------------------------------------------------------


@pytest.fixture
def cx_raw(tmp_path: Path) -> Path:
    """가짜 Codex mirror — raw/codex 루트."""
    root = tmp_path / "cx"
    (root / "sessions" / "2026" / "05" / "19").mkdir(parents=True)
    return root


def _write_rollout(path: Path, cwd: str, *events: dict) -> None:
    """rollout-*.jsonl: session_meta 먼저, 이후 추가 events."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        meta = {
            "timestamp": "2026-05-19T11:00:00.000Z",
            "type": "session_meta",
            "payload": {"cwd": cwd, "cli_version": "0.131.0"},
        }
        f.write(json.dumps(meta, ensure_ascii=False) + "\n")
        for ev in events:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")


class TestCodexSessionsCluster:
    def test_extract_cwd_from_rollout(self, cx_raw: Path) -> None:
        from synapse_memory.clusters.identify import _extract_cwd_from_rollout

        rollout = cx_raw / "sessions" / "2026" / "05" / "19" / "rollout-a.jsonl"
        _write_rollout(rollout, "/work/gitlab-proj")
        assert (
            _extract_cwd_from_rollout(rollout) == "/work/gitlab-proj"
        )

    def test_extract_cwd_missing_returns_none(self, cx_raw: Path) -> None:
        from synapse_memory.clusters.identify import _extract_cwd_from_rollout

        rollout = cx_raw / "sessions" / "2026" / "05" / "19" / "rollout-a.jsonl"
        rollout.write_text(
            json.dumps({"type": "event_msg", "payload": {}}) + "\n",
            encoding="utf-8",
        )
        assert _extract_cwd_from_rollout(rollout) is None

    def test_codex_only_cluster_seeded(
        self, cc_raw: Path, obs_raw: Path, cx_raw: Path
    ) -> None:
        """Claude Code 매칭 없는 codex-only 프로젝트도 cluster 시드."""
        rollout = cx_raw / "sessions" / "2026" / "05" / "19" / "rollout-a.jsonl"
        _write_rollout(rollout, "/work/gitlab-proj-x")
        clusters = identify_clusters(
            obsidian_raw=obs_raw, claude_code_raw=cc_raw, codex_raw=cx_raw
        )
        c = next(c for c in clusters if c.cluster_id == "gitlab-proj-x")
        assert c.seed_kind == "codex"
        assert "/work/gitlab-proj-x" in c.cwd_paths
        assert len(c.codex_jsonl) == 1
        assert c.claude_jsonl == []

    def test_claude_and_codex_merge(
        self, cc_raw: Path, obs_raw: Path, cx_raw: Path
    ) -> None:
        """같은 cwd basename 으로 Claude Code + Codex 만나면 머지."""
        _write_jsonl(
            cc_raw
            / "projects"
            / "-Users-sampleuser-Documents-GitHub-dansim-ios"
            / "abc.jsonl",
            {"cwd": "/Users/sampleuser/Documents/GitHub/dansim-ios"},
        )
        rollout = cx_raw / "sessions" / "2026" / "05" / "19" / "rollout-x.jsonl"
        _write_rollout(rollout, "/Users/sampleuser/Documents/GitHub/dansim-ios")

        clusters = identify_clusters(
            obsidian_raw=obs_raw, claude_code_raw=cc_raw, codex_raw=cx_raw
        )
        c = next(c for c in clusters if c.cluster_id == "dansim-ios")
        assert c.seed_kind == "merged"
        assert len(c.claude_jsonl) == 1
        assert len(c.codex_jsonl) == 1
        assert c.total_sources >= 2

    def test_codex_raw_missing_silent(
        self, cc_raw: Path, obs_raw: Path, tmp_path: Path
    ) -> None:
        """codex_raw 경로 자체가 없어도 에러 없이 동작."""
        clusters = identify_clusters(
            obsidian_raw=obs_raw,
            claude_code_raw=cc_raw,
            codex_raw=tmp_path / "nope",
        )
        # codex 없어도 정상 종료
        assert isinstance(clusters, list)
