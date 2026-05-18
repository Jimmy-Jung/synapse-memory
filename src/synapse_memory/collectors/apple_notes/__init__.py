"""Apple Notes 데이터 수집기.

소스 (macOS):
    ``~/Library/Group Containers/group.com.apple.notes/NoteStore.sqlite``
대상:
    ``~/.synapse/private/raw/apple-notes/``

NoteStore.sqlite 의 본문은 ZICCLOUDSYNCINGOBJECT.ZNOTEDATA 등 protobuf 압축
blob 으로 저장돼 있어 본 단계에선 backup snapshot 만 뜨고, 본문 추출은 후속
단계의 책임이다.

저자: Synapse Memory Maintainers
"""

from synapse_memory.collectors.apple_notes.mirror import (
    DEFAULT_NOTES_HOME,
    CollectStats,
    collect_apple_notes,
)

__all__ = [
    "DEFAULT_NOTES_HOME",
    "CollectStats",
    "collect_apple_notes",
]
