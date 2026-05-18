"""사용자 본인 Git commit 수집기.

소스:
    환경변수 ``SYNAPSE_GIT_SELF_ROOTS`` (콜론 구분) 로 지정된 디렉토리 아래의
    모든 git repo. 본인 이메일 (``SYNAPSE_GIT_SELF_EMAIL`` 또는 repo 의
    ``git config user.email``) 인 commit 만.

대상:
    ``~/.synapse/private/raw/git-self/<repo-name>.jsonl``

각 줄 = 한 commit 의 메타 + (옵션) stats. diff 본문은 본 단계에서는 저장하지
않는다 (volume 보호). 후속 단계에서 필요 시 ``git show <sha>`` 로 lazy fetch.

저자: Synapse Memory Maintainers
"""

from synapse_memory.collectors.git_self.mirror import (
    ENV_ROOTS,
    ENV_SELF_EMAIL,
    CollectStats,
    collect_git_self,
)

__all__ = [
    "ENV_ROOTS",
    "ENV_SELF_EMAIL",
    "CollectStats",
    "collect_git_self",
]
