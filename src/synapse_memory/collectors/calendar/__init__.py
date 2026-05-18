"""macOS Calendar 데이터 수집기.

소스: ``~/Library/Calendars/<UUID>.calendar/Events/*.ics``
       각 ICS 는 단일 VCALENDAR record (텍스트).
대상: ``~/.synapse/private/raw/calendar/`` 아래 동일 상대 경로.

EventKit / iCloud subscribe 가 아니라 macOS Calendar.app 이 디스크에 캐시한
ICS 파일을 mirror. iCloud-sync 활성 캘린더만 이 경로에 보인다.

저자: Synapse Memory Maintainers
"""

from synapse_memory.collectors.calendar.mirror import (
    DEFAULT_CALENDAR_HOME,
    CollectStats,
    collect_calendar,
)

__all__ = [
    "DEFAULT_CALENDAR_HOME",
    "CollectStats",
    "collect_calendar",
]
