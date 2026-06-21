"""Git self-commits → L0 mirror.

전략
----
1. ``SYNAPSE_GIT_SELF_ROOTS`` 환경변수에서 root 디렉토리 목록 파싱.
   미설정 시 빈 list → silent skip (정상).
2. 각 root 아래 ``.git`` 디렉토리를 가진 디렉토리를 직계 자식까지 탐색.
3. repo 의 본인 commit 만 추출:
   ``git log --reverse --author=<self_email> --format=<json-fields>``
   - ``SYNAPSE_GIT_SELF_EMAIL`` 우선, 없으면 repo 의 ``user.email``.
4. 마지막으로 처리한 commit SHA 를 ``.offsets/<repo-name>.sha`` 에 보존.
   다음 호출 때 ``<last>..HEAD`` 범위만 처리 — incremental.

저장 포맷 (JSONL, 한 줄 = 한 commit)::

    {
      "repo": "<basename>",
      "sha": "<full 40-hex>",
      "date": "2026-05-18T10:00:00+09:00",
      "author_email": "<email>",
      "subject": "<first line of message>"
    }

diff stats 는 후속 단계에서 ``git show --stat <sha>`` 로 lazy fetch (저장 단계
복잡도/volume 보호).

저자: Synapse Memory Maintainers
작성일: 2026-05-18
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from synapse_memory.storage.l0 import (
    L0_FILE_MODE,
    ensure_l0_root_secure,
    ensure_secure_dir,
    l0_root,
)

ENV_ROOTS = "SYNAPSE_GIT_SELF_ROOTS"
ENV_SELF_EMAIL = "SYNAPSE_GIT_SELF_EMAIL"
SUBPATH = Path("raw") / "git-self"
OFFSETS_DIR = ".offsets"

_FIELD_SEP = "\x1f"   # Unit Separator
_LOG_FORMAT = _FIELD_SEP.join(["%H", "%aI", "%ae", "%s"])


@dataclass
class CollectStats:
    repos_scanned: int = 0
    repos_mirrored: int = 0
    commits_added: int = 0
    bytes_added: int = 0
    errors: list[tuple[Path, str]] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"scanned={self.repos_scanned} mirrored={self.repos_mirrored} "
            f"commits+={self.commits_added} bytes+={self.bytes_added} "
            f"errors={len(self.errors)}"
        )


def _parse_roots(raw: str | None) -> list[Path]:
    if not raw:
        return []
    return [Path(p).expanduser().resolve() for p in raw.split(":") if p.strip()]


def _find_repos(roots: list[Path]) -> list[Path]:
    """root 디렉토리 아래의 git repo 목록.

    root 자체가 repo 면 root, 아니면 직계 자식까지만 검사 (node_modules 깊이
    재귀 방지).
    """
    seen: set[Path] = set()
    out: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        if (root / ".git").is_dir():
            if root not in seen:
                seen.add(root)
                out.append(root)
            continue
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            if (child / ".git").is_dir() and child not in seen:
                seen.add(child)
                out.append(child)
    return out


def _resolve_self_email(repo: Path, override: str | None) -> str | None:
    if override:
        return override
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "config", "user.email"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    email = result.stdout.strip()
    return email or None


def _read_offset(offset_path: Path) -> str | None:
    if not offset_path.exists():
        return None
    try:
        sha = offset_path.read_text(encoding="utf-8").strip()
        return sha or None
    except OSError:
        return None


def _write_offset_atomic(offset_path: Path, sha: str) -> None:
    ensure_secure_dir(offset_path.parent)
    tmp = offset_path.with_suffix(offset_path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(sha)
        f.flush()
        os.fsync(f.fileno())
    with contextlib.suppress(OSError):
        os.chmod(tmp, L0_FILE_MODE)
    os.replace(tmp, offset_path)


def _git_log_records(
    repo: Path,
    self_email: str,
    last_sha: str | None,
) -> list[dict[str, str]]:
    """본인 commit 목록 (오래된 → 최신). 각 dict = JSONL record."""
    rev_range = f"{last_sha}..HEAD" if last_sha else "HEAD"
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "log",
                "--reverse",
                f"--author={self_email}",
                f"--format={_LOG_FORMAT}",
                rev_range,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        # 범위 invalid (last_sha 가 사라진 경우) — 처음부터 다시
        if last_sha:
            return _git_log_records(repo, self_email, None)
        return []

    out: list[dict[str, str]] = []
    repo_name = repo.name
    for line in result.stdout.splitlines():
        if _FIELD_SEP not in line:
            continue
        fields = line.split(_FIELD_SEP)
        if len(fields) < 4:
            continue
        sha, date, author_email, subject = fields[0], fields[1], fields[2], fields[3]
        out.append(
            {
                "repo": repo_name,
                "sha": sha,
                "date": date,
                "author_email": author_email,
                "subject": subject,
            }
        )
    return out


def _append_jsonl(dst: Path, records: list[dict[str, str]]) -> int:
    """records 를 dst 에 append. 반환: 추가된 byte 수."""
    if not records:
        return 0
    ensure_secure_dir(dst.parent)
    blob = "".join(
        json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in records
    ).encode("utf-8")
    with open(dst, "ab") as f:
        f.write(blob)
        f.flush()
        os.fsync(f.fileno())
    with contextlib.suppress(OSError):
        os.chmod(dst, L0_FILE_MODE)
    return len(blob)


def collect_git_self(
    *,
    roots_env: str | None = None,
    self_email_env: str | None = None,
    dst_root: Path | None = None,
) -> CollectStats:
    """본인 commit 1회 수집 (incremental, per-repo).

    Args:
        roots_env: ``SYNAPSE_GIT_SELF_ROOTS`` override (테스트용 — 콜론 구분).
        self_email_env: ``SYNAPSE_GIT_SELF_EMAIL`` override.
        dst_root: L0 mirror 루트 (기본: ``<l0_root>/raw/git-self``).

    Returns:
        CollectStats — 처리 통계. roots 미설정 시 errors 없이 빈 통계 반환
        (사용자 opt-in 전 — 정상).
    """
    raw_roots = roots_env if roots_env is not None else os.environ.get(ENV_ROOTS)
    email_override = (
        self_email_env
        if self_email_env is not None
        else os.environ.get(ENV_SELF_EMAIL)
    )
    dst = (dst_root or (l0_root() / SUBPATH)).expanduser().resolve()

    stats = CollectStats()

    roots = _parse_roots(raw_roots)
    if not roots:
        return stats

    repos = _find_repos(roots)
    if not repos:
        return stats

    if dst.is_relative_to(l0_root().expanduser().resolve()):
        ensure_l0_root_secure()
    ensure_secure_dir(dst)
    ensure_secure_dir(dst / OFFSETS_DIR)

    for repo in repos:
        stats.repos_scanned += 1
        try:
            self_email = _resolve_self_email(repo, email_override)
            if not self_email:
                continue

            offset_path = dst / OFFSETS_DIR / f"{repo.name}.sha"
            last_sha = _read_offset(offset_path)

            records = _git_log_records(repo, self_email, last_sha)
            if not records:
                continue

            dst_file = dst / f"{repo.name}.jsonl"
            added = _append_jsonl(dst_file, records)
            if added > 0:
                stats.repos_mirrored += 1
                stats.commits_added += len(records)
                stats.bytes_added += added
                _write_offset_atomic(offset_path, records[-1]["sha"])
        except OSError as exc:
            stats.errors.append((repo, str(exc)))

    return stats
