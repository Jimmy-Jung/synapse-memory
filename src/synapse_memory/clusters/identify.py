"""클러스터 식별 — raw mirror 스캔 → ProjectCluster 목록.

알고리즘:
    1. Claude Code projects/<slug>/<id>.jsonl 스캔
       → 각 파일 첫 N 줄에서 ``cwd`` 필드 추출 (정확한 경로)
       → cwd basename을 cluster_id로 (예: "dansim-ios")
       → 같은 cluster_id의 모든 jsonl 합류
    2. Obsidian 노트 스캔
       → 본문에서 ``/GitHub/<repo>`` path 또는 frontmatter ``tags`` 추출
       → cluster_id와 매칭되면 추가
    3. 신뢰도 계산
       cwd만               → 0.5
       + obsidian 노트      → +0.3 (= 0.8)
       + #dom/* 등 태그     → +0.1 (= 0.9)

저자: Synapse Memory Maintainers
작성일: 2026-05-10
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from synapse_memory.storage.l0 import l0_root

# Tag pattern: #dom/ios, #type/ref, #status/wip 등
_TAG_RE = re.compile(r"#([a-zA-Z][\w/]*)")
# /GitHub/<repo-name> 패턴 (사용자 환경 ~/Documents/GitHub/* 가정)
_GITHUB_PATH_RE = re.compile(r"/GitHub/([A-Za-z0-9_\-\.]+)")
# jsonl에서 cwd 추출 — 첫 N 줄만 검사
_CWD_PROBE_LINES = 30

# vault 폴더 cluster 발견에 쓰는 top-level 폴더 (의미적 작업 단위 위주).
# 90_System은 메타, 99_Archive는 동결, 00_Inbox는 미정 — 제외.
VAULT_CLUSTER_TOP_LEVELS: tuple[str, ...] = (
    "10_Active",
    "20_Reference",
    "30_Creative",
    "40_Life",
)
# 폴더 단위 cluster의 최소 노트 수 (1개는 cluster 아님 — 단발 노트)
VAULT_CLUSTER_MIN_FILES = 2
# 너무 광범위한 segment (도메인 단위) — 제외
VAULT_GENERIC_SEGMENTS = frozenset(
    {"Topics", "Drafts", "Skills", "Published", "Hobby", "Money", "Travel", "MOC"}
)
_SLUG_BAD_RE = re.compile(r"[^a-zA-Z0-9가-힣\-]+")


@dataclass
class ProjectCluster:
    """동일 프로젝트로 묶인 raw 데이터 모음.

    seed_kind: "claude_code"(cwd 기반) / "vault"(폴더 기반) / "merged"(둘 다)
    """

    cluster_id: str
    candidate_name: str
    cwd_paths: set[str] = field(default_factory=set)
    obsidian_files: list[str] = field(default_factory=list)
    claude_jsonl: list[str] = field(default_factory=list)
    tags: set[str] = field(default_factory=set)
    vault_folders: set[str] = field(default_factory=set)
    seed_kind: str = "claude_code"

    @property
    def confidence(self) -> float:
        # cwd 또는 vault folder 시드 = 0.5
        score = 0.5
        # 두 소스 다 있으면 +0.3 (강한 신호)
        if self.cwd_paths and self.obsidian_files:
            score += 0.3
        elif self.obsidian_files and len(self.obsidian_files) >= 3:
            # vault만 있어도 노트 3개+ 모이면 신뢰
            score += 0.2
        if self.tags:
            score += 0.1
        return min(score, 1.0)

    @property
    def total_sources(self) -> int:
        return len(self.obsidian_files) + len(self.claude_jsonl)


# ---------------------------------------------------------------------------
# 추출 유틸
# ---------------------------------------------------------------------------


def extract_tags(text: str) -> set[str]:
    """Obsidian 노트에서 태그 추출 — frontmatter ``tags:`` + 본문 ``#xxx``."""
    tags: set[str] = set()

    # frontmatter
    body = text
    if text.startswith("---\n") or text.startswith("---\r\n"):
        end = text.find("\n---", 4)
        if end > 0:
            try:
                meta = yaml.safe_load(text[4:end]) or {}
                if isinstance(meta, dict):
                    raw_tags = meta.get("tags")
                    if isinstance(raw_tags, list):
                        tags.update(str(t).lstrip("#") for t in raw_tags if t)
                    elif isinstance(raw_tags, str):
                        for t in raw_tags.split(","):
                            t = t.strip().lstrip("#")
                            if t:
                                tags.add(t)
            except yaml.YAMLError:
                pass
            body = text[end + 4 :]

    # body 본문 inline 태그
    for m in _TAG_RE.finditer(body):
        tags.add(m.group(1))
    return tags


def extract_github_repos(text: str) -> set[str]:
    """``/GitHub/<repo>`` path 패턴에서 repo 이름 추출."""
    return set(_GITHUB_PATH_RE.findall(text))


def _extract_cwd_from_jsonl(path: Path) -> str | None:
    """jsonl 첫 N 줄에서 ``cwd`` 필드 첫 발견 시 반환."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for _ in range(_CWD_PROBE_LINES):
                line = f.readline()
                if not line:
                    break
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(ev, dict):
                    cwd = ev.get("cwd")
                    if isinstance(cwd, str) and cwd:
                        return cwd
    except OSError:
        return None
    return None


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def _default_obsidian_raw() -> Path:
    return l0_root() / "raw" / "obsidian"


def _default_claude_code_raw() -> Path:
    return l0_root() / "raw" / "claude-code"


def _slug_from_segment(name: str) -> str:
    """폴더 이름 → slug. NFC 정규화 필수 (macOS는 NFD 저장 → 한글 자모 분해)."""
    s = unicodedata.normalize("NFC", name).strip().lower().replace(" ", "-")
    s = _SLUG_BAD_RE.sub("-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "untitled"


def _enumerate_vault_folder_clusters(
    obs_root: Path,
) -> dict[str, dict[str, Any]]:
    """vault 폴더 segment 기반 cluster 후보.

    규칙:
        - top-level이 VAULT_CLUSTER_TOP_LEVELS 안에 있어야
        - depth 2 segment를 cluster_id 후보로
            예: 10_Active/샘플회사/X.md → cluster "샘플회사"
            예: 10_Active/샘플회사/iOS 파트.../1주차/X.md → cluster "샘플회사"
        - VAULT_GENERIC_SEGMENTS는 더 깊은 단계 사용 (Drafts/AI/X.md → cluster "AI")
        - cluster당 최소 VAULT_CLUSTER_MIN_FILES 노트

    Returns:
        ``{cluster_id: {"folder": "<top>/<segment>", "files": [rel_path,...]}}``
    """
    if not obs_root.is_dir():
        return {}

    from synapse_memory.config import get_config

    folders = get_config().vault_folders
    cluster_top_levels = (
        Path(folders.active).parts[0],
        Path(folders.reference.root).parts[0],
        Path(folders.creative.root).parts[0],
        Path(folders.life).parts[0],
    )

    by_id: dict[str, dict[str, Any]] = {}
    for md in sorted(obs_root.rglob("*.md")):
        rel = md.relative_to(obs_root)
        parts = rel.parts
        if len(parts) < 3:  # top + segment + file 최소
            continue
        top = parts[0]
        if top not in cluster_top_levels:
            continue

        # depth 2 segment 가져오되, generic이면 한 단계 더
        seg_idx = 1
        while seg_idx < len(parts) - 1 and parts[seg_idx] in VAULT_GENERIC_SEGMENTS:
            seg_idx += 1
        if seg_idx >= len(parts) - 1:
            continue
        segment = parts[seg_idx]
        cid = _slug_from_segment(segment)
        folder = "/".join(parts[: seg_idx + 1])

        entry = by_id.setdefault(cid, {"folder": folder, "files": []})
        entry["files"].append(str(rel))

    return {k: v for k, v in by_id.items() if len(v["files"]) >= VAULT_CLUSTER_MIN_FILES}


def identify_clusters(
    *,
    obsidian_raw: Path | None = None,
    claude_code_raw: Path | None = None,
) -> list[ProjectCluster]:
    """raw mirror 스캔 → ProjectCluster 목록 (신뢰도 내림차순).

    Args:
        obsidian_raw: ``~/.synapse/private/raw/obsidian`` (기본).
        claude_code_raw: ``~/.synapse/private/raw/claude-code`` (기본).
    """
    obs_root = (obsidian_raw or _default_obsidian_raw()).expanduser().resolve()
    cc_root = (claude_code_raw or _default_claude_code_raw()).expanduser().resolve()

    clusters: dict[str, ProjectCluster] = {}

    # 1. Claude Code 시드 — projects/<slug>/<id>.jsonl
    proj_dir = cc_root / "projects"
    if proj_dir.is_dir():
        for slug_dir in sorted(proj_dir.iterdir()):
            if not slug_dir.is_dir():
                continue
            for jsonl in sorted(slug_dir.glob("*.jsonl")):
                cwd = _extract_cwd_from_jsonl(jsonl)
                if not cwd:
                    continue
                cwd_path = Path(cwd)
                cid = cwd_path.name or "untitled"
                cluster = clusters.setdefault(
                    cid,
                    ProjectCluster(cluster_id=cid, candidate_name=cid),
                )
                cluster.cwd_paths.add(cwd)
                cluster.claude_jsonl.append(str(jsonl.relative_to(cc_root)))

    # 2. Obsidian 노트 → 기존 Claude Code cluster 매칭 (GitHub path)
    if obs_root.is_dir():
        for md in sorted(obs_root.rglob("*.md")):
            try:
                text = md.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            tags = extract_tags(text)
            repos = extract_github_repos(text)

            matched: ProjectCluster | None = None
            for repo in repos:
                if repo in clusters:
                    matched = clusters[repo]
                    break

            if matched is not None:
                rel = str(md.relative_to(obs_root))
                if rel not in matched.obsidian_files:
                    matched.obsidian_files.append(rel)
                matched.tags.update(tags)

    # 3. vault 폴더 segment cluster — Claude Code cwd 매칭 못한 vault 노트들
    vault_clusters = _enumerate_vault_folder_clusters(obs_root)
    for cid, payload in vault_clusters.items():
        if cid in clusters:
            # 기존 Claude Code cluster와 머지
            cluster = clusters[cid]
            cluster.seed_kind = "merged"
            cluster.vault_folders.add(payload["folder"])
            for f in payload["files"]:
                if f not in cluster.obsidian_files:
                    cluster.obsidian_files.append(f)
        else:
            # vault만으로 새 cluster
            cluster = ProjectCluster(
                cluster_id=cid,
                candidate_name=Path(payload["folder"]).name,
                obsidian_files=list(payload["files"]),
                vault_folders={payload["folder"]},
                seed_kind="vault",
            )
            clusters[cid] = cluster

        # vault cluster의 모든 노트에서 태그 합산
        for rel in payload["files"]:
            try:
                text = (obs_root / rel).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            cluster.tags.update(extract_tags(text))

    return sorted(
        clusters.values(),
        key=lambda c: (-c.confidence, -c.total_sources, c.cluster_id),
    )
