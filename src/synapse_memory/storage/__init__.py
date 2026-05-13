"""저장 레이어 — L0(raw) / L1(candidate) / L2(validated).

이 패키지는 디스크 위 디렉토리 구조와 권한을 관리한다. 데이터 자체의 의미
(분류, redaction)는 다른 모듈 책임.

저자: Synapse Memory Maintainers
"""

from synapse_memory.storage.l0 import (
    L0_DEFAULT_ROOT,
    L0_DIR_MODE,
    L0_FILE_MODE,
    ensure_l0_root_secure,
    ensure_secure_dir,
    ensure_secure_file,
    l0_root,
)

__all__ = [
    "L0_DEFAULT_ROOT",
    "L0_DIR_MODE",
    "L0_FILE_MODE",
    "ensure_l0_root_secure",
    "ensure_secure_dir",
    "ensure_secure_file",
    "l0_root",
]
