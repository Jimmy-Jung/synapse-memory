"""클러스터 식별 — raw 데이터에서 같은 프로젝트로 묶기.

Project Card 자동 생성의 input. 휴리스틱 기반 (LLM 안 씀).

저자: JunyoungJung <joony300@gmail.com>
"""

from synapse_memory.clusters.identify import (
    VAULT_CLUSTER_TOP_LEVELS,
    ProjectCluster,
    extract_github_repos,
    extract_tags,
    identify_clusters,
)

__all__ = [
    "ProjectCluster",
    "VAULT_CLUSTER_TOP_LEVELS",
    "extract_github_repos",
    "extract_tags",
    "identify_clusters",
]
