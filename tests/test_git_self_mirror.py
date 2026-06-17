"""git_self mirror 테스트.

핵심 시나리오
- ``SYNAPSE_GIT_SELF_ROOTS`` 미설정 → silent (errors 0, scanned 0)
- root 안 repo 발견 + 본인 commit 만 추출
- 다른 author commit 은 skip
- incremental: 두 번째 호출 시 새 commit 만 append
- offset 파일 (.sha) 보존
- L0 권한
- daily wiring

실제 git 명령을 호출하므로 ``git`` PATH 필요 (CI 도 포함).

저자: Synapse Memory Maintainers
작성일: 2026-05-18
"""

from __future__ import annotations

import json
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from synapse_memory.collectors.git_self.mirror import (
    OFFSETS_DIR,
    collect_git_self,
)
from synapse_memory.storage.l0 import L0_DIR_MODE

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git not installed"
)


@pytest.fixture
def dst_root(tmp_path: Path) -> Path:
    return tmp_path / "l0" / "raw" / "git-self"


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    return tmp_path / "repos"


def _git(repo: Path, *args: str, env: dict | None = None) -> None:
    full_env = {
        "GIT_AUTHOR_NAME": "Self",
        "GIT_AUTHOR_EMAIL": "self@example.com",
        "GIT_COMMITTER_NAME": "Self",
        "GIT_COMMITTER_EMAIL": "self@example.com",
        "HOME": str(repo),
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
    }
    if env:
        full_env.update(env)
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env=full_env,
    )


def _init_repo(path: Path, user_email: str = "self@example.com") -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(path)],
        check=True,
        capture_output=True,
    )
    _git(path, "config", "user.email", user_email)
    _git(path, "config", "user.name", "Self")


def _commit(
    path: Path,
    filename: str,
    content: str,
    *,
    message: str,
    author_email: str | None = None,
) -> None:
    (path / filename).write_text(content, encoding="utf-8")
    _git(path, "add", filename)
    env = {}
    if author_email:
        env = {"GIT_AUTHOR_EMAIL": author_email, "GIT_COMMITTER_EMAIL": author_email}
    _git(path, "commit", "-q", "-m", message, env=env)


class TestCollectGitSelf:
    def test_silent_when_roots_unset(self, dst_root: Path) -> None:
        stats = collect_git_self(roots_env="", dst_root=dst_root)
        assert stats.repos_scanned == 0
        assert stats.errors == []

    def test_collects_self_commits(
        self, repo_root: Path, dst_root: Path
    ) -> None:
        repo = repo_root / "myrepo"
        _init_repo(repo)
        _commit(repo, "a.txt", "hello\n", message="add a")
        _commit(repo, "b.txt", "world\n", message="add b")

        stats = collect_git_self(
            roots_env=str(repo_root),
            self_email_env="self@example.com",
            dst_root=dst_root,
        )

        assert stats.repos_scanned == 1
        assert stats.repos_mirrored == 1
        assert stats.commits_added == 2

        jsonl = dst_root / "myrepo.jsonl"
        assert jsonl.is_file()
        records = [
            json.loads(line)
            for line in jsonl.read_text(encoding="utf-8").splitlines()
            if line
        ]
        assert len(records) == 2
        assert records[0]["subject"] == "add a"
        assert records[1]["subject"] == "add b"
        assert records[0]["author_email"] == "self@example.com"
        assert len(records[0]["sha"]) == 40

    def test_excludes_other_authors(
        self, repo_root: Path, dst_root: Path
    ) -> None:
        repo = repo_root / "myrepo"
        _init_repo(repo)
        _commit(repo, "mine.txt", "x", message="my commit")
        _commit(
            repo,
            "other.txt",
            "y",
            message="other commit",
            author_email="other@example.com",
        )

        stats = collect_git_self(
            roots_env=str(repo_root),
            self_email_env="self@example.com",
            dst_root=dst_root,
        )
        assert stats.commits_added == 1
        records = [
            json.loads(line)
            for line in (dst_root / "myrepo.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line
        ]
        assert records[0]["subject"] == "my commit"

    def test_incremental(self, repo_root: Path, dst_root: Path) -> None:
        repo = repo_root / "myrepo"
        _init_repo(repo)
        _commit(repo, "a.txt", "1", message="c1")
        collect_git_self(
            roots_env=str(repo_root),
            self_email_env="self@example.com",
            dst_root=dst_root,
        )

        _commit(repo, "b.txt", "2", message="c2")
        s2 = collect_git_self(
            roots_env=str(repo_root),
            self_email_env="self@example.com",
            dst_root=dst_root,
        )
        assert s2.commits_added == 1

        records = [
            json.loads(line)
            for line in (dst_root / "myrepo.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line
        ]
        assert [r["subject"] for r in records] == ["c1", "c2"]

    def test_no_new_commits_idempotent(
        self, repo_root: Path, dst_root: Path
    ) -> None:
        repo = repo_root / "myrepo"
        _init_repo(repo)
        _commit(repo, "a.txt", "1", message="c1")
        collect_git_self(
            roots_env=str(repo_root),
            self_email_env="self@example.com",
            dst_root=dst_root,
        )
        s2 = collect_git_self(
            roots_env=str(repo_root),
            self_email_env="self@example.com",
            dst_root=dst_root,
        )
        assert s2.commits_added == 0
        assert s2.bytes_added == 0

    def test_offset_file_written(
        self, repo_root: Path, dst_root: Path
    ) -> None:
        repo = repo_root / "myrepo"
        _init_repo(repo)
        _commit(repo, "a.txt", "1", message="c1")
        collect_git_self(
            roots_env=str(repo_root),
            self_email_env="self@example.com",
            dst_root=dst_root,
        )
        offset = dst_root / OFFSETS_DIR / "myrepo.sha"
        assert offset.is_file()
        sha = offset.read_text(encoding="utf-8").strip()
        assert len(sha) == 40

    def test_multiple_repos(self, repo_root: Path, dst_root: Path) -> None:
        for name in ("alpha", "beta"):
            repo = repo_root / name
            _init_repo(repo)
            _commit(repo, "f.txt", name, message=f"init {name}")

        stats = collect_git_self(
            roots_env=str(repo_root),
            self_email_env="self@example.com",
            dst_root=dst_root,
        )
        assert stats.repos_scanned == 2
        assert stats.repos_mirrored == 2
        assert (dst_root / "alpha.jsonl").is_file()
        assert (dst_root / "beta.jsonl").is_file()

    def test_l0_perms(self, repo_root: Path, dst_root: Path) -> None:
        repo = repo_root / "myrepo"
        _init_repo(repo)
        _commit(repo, "a.txt", "1", message="c1")
        collect_git_self(
            roots_env=str(repo_root),
            self_email_env="self@example.com",
            dst_root=dst_root,
        )
        assert stat.S_IMODE(dst_root.stat().st_mode) == L0_DIR_MODE
        assert (dst_root / OFFSETS_DIR).is_dir()


class TestDailyStageWiring:
    def test_collect_git_self_in_steps(self) -> None:
        from synapse_memory.daily import DAILY_STAGES, STEPS

        assert "collect_git_self" in STEPS
        assert any(
            s.name == "collect_git_self"
            and s.description == "본인 Git commit mirror"
            for s in DAILY_STAGES
        )

    def test_stage_actions_include_git_self(self) -> None:
        from synapse_memory.daily import _build_stage_actions

        actions = _build_stage_actions(
            classify_model="haiku",
            generate_model="sonnet",
            profile_model="sonnet",
            profile_sample_lines=10,
            profile_facts_only=True,
            on_log=lambda _msg: None,
        )
        assert "collect_git_self" in actions
        assert callable(actions["collect_git_self"])
