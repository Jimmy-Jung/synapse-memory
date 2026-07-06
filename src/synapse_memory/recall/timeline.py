"""Deterministic timeline recall.

저자: Synapse Memory Maintainers
작성일: 2026-07-06
"""

from __future__ import annotations

import calendar
import datetime
from dataclasses import dataclass
from typing import Literal

_SortTsSource = Literal[
    "period_end",
    "today_fallback",
    "created",
    "last_reviewed",
    "no_time_meta",
]


@dataclass(frozen=True)
class CardWithMeta:
    """Transient card metadata used for sorting, grouping, and rendering."""

    card_id: str
    display_name: str
    source_kind: Literal["card_project", "card_company"]
    sort_ts: datetime.datetime
    sort_ts_source: _SortTsSource
    created_ts: datetime.datetime
    distance: float | None
    citation_text: str
    body_redacted: str


@dataclass(frozen=True)
class TimelineGroup:
    """Cards grouped by the same year and quarter."""

    quarter_label: str
    year: int
    quarter: int
    sort_ts: datetime.datetime
    members: tuple[CardWithMeta, ...]
    months_present: tuple[int, ...]


_DT_MIN = datetime.datetime(datetime.MINYEAR, 1, 1)


def _parse_iso_or_yyyymm(s: str | None) -> datetime.date | None:
    """``YYYY-MM-DD`` 또는 ``YYYY-MM`` 문자열을 date로 변환한다."""
    if not s or not isinstance(s, str):
        return None
    parts = s.split("-")
    try:
        if len(parts) == 3:
            return datetime.date.fromisoformat(s)
        if len(parts) == 2:
            year = int(parts[0])
            month = int(parts[1])
            last_day = calendar.monthrange(year, month)[1]
            return datetime.date(year, month, last_day)
    except (ValueError, TypeError):
        return None
    return None


def _to_dt(d: datetime.date | None) -> datetime.datetime:
    """``date``를 자정 ``datetime``으로 바꾼다. None은 최솟값으로 둔다."""
    if d is None:
        return _DT_MIN
    return datetime.datetime.combine(d, datetime.time.min)


def _resolve_sort_ts(
    metadata: dict[str, str],
    today: datetime.date,
    *,
    distance: float | None = None,
    document: str = "",
) -> CardWithMeta:
    """Card metadata + today → ``CardWithMeta``."""
    card_id = str(metadata.get("card_id") or metadata.get("id") or "")
    raw_kind = str(metadata.get("source_kind") or "card_project")
    source_kind: Literal["card_project", "card_company"] = (
        "card_company" if raw_kind == "card_company" else "card_project"
    )
    display_name = str(metadata.get("display_name") or card_id)

    period_end = _parse_iso_or_yyyymm(metadata.get("period_end") or None)
    created = _parse_iso_or_yyyymm(metadata.get("created") or None)
    last_reviewed = _parse_iso_or_yyyymm(metadata.get("last_reviewed") or None)
    status = str(metadata.get("status") or "")

    sort_ts: datetime.datetime
    sort_ts_source: _SortTsSource

    if source_kind == "card_project":
        if period_end is not None:
            sort_ts = _to_dt(period_end)
            sort_ts_source = "period_end"
        elif status == "active":
            sort_ts = _to_dt(today)
            sort_ts_source = "today_fallback"
        elif created is not None:
            sort_ts = _to_dt(created)
            sort_ts_source = "created"
        else:
            sort_ts = _DT_MIN
            sort_ts_source = "no_time_meta"
    elif last_reviewed is not None:
        sort_ts = _to_dt(last_reviewed)
        sort_ts_source = "last_reviewed"
    elif created is not None:
        sort_ts = _to_dt(created)
        sort_ts_source = "created"
    else:
        sort_ts = _DT_MIN
        sort_ts_source = "no_time_meta"

    created_ts = _to_dt(created) if created is not None else _DT_MIN
    citation_text = f"[{source_kind}:{card_id}]"
    body_redacted = document or ""

    return CardWithMeta(
        card_id=card_id,
        display_name=display_name,
        source_kind=source_kind,
        sort_ts=sort_ts,
        sort_ts_source=sort_ts_source,
        created_ts=created_ts,
        distance=distance,
        citation_text=citation_text,
        body_redacted=body_redacted,
    )


def _sort_by_time(items: list[CardWithMeta]) -> list[CardWithMeta]:
    """``(sort_ts desc, created_ts desc)`` stable sort."""
    return sorted(items, key=lambda c: (c.sort_ts, c.created_ts), reverse=True)


_QUARTER_OF_MONTH = {m: (m - 1) // 3 + 1 for m in range(1, 13)}


def _group_by_quarter(items: list[CardWithMeta]) -> list[TimelineGroup]:
    """정렬된 카드를 (year, quarter) 그룹으로 묶는다."""
    groups: list[TimelineGroup] = []
    current_key: tuple[int, int] | None = None
    current_members: list[CardWithMeta] = []

    def _close_group() -> None:
        if current_members and current_key is not None:
            year, quarter = current_key
            months = tuple(sorted({c.sort_ts.month for c in current_members}, reverse=True))
            groups.append(
                TimelineGroup(
                    quarter_label=f"{year} Q{quarter}",
                    year=year,
                    quarter=quarter,
                    sort_ts=current_members[0].sort_ts,
                    members=tuple(current_members),
                    months_present=months,
                )
            )

    for card in items:
        if card.sort_ts_source == "no_time_meta":
            continue
        year = card.sort_ts.year
        quarter = _QUARTER_OF_MONTH[card.sort_ts.month]
        key = (year, quarter)
        if current_key != key:
            _close_group()
            current_key = key
            current_members = []
        current_members.append(card)
    _close_group()

    return groups


def _label_for(card: CardWithMeta) -> str:
    """sort_ts_source를 출력 라벨로 변환한다."""
    if card.sort_ts_source == "period_end":
        return ""
    if card.sort_ts_source == "today_fallback":
        return f"(오늘 {card.sort_ts.date().isoformat()})"
    if card.sort_ts_source == "created":
        return "(created)"
    if card.sort_ts_source == "last_reviewed":
        return "(last reviewed)"
    return ""


def _render_card_line(card: CardWithMeta) -> str:
    """단일 카드 markdown 라인."""
    date_str = card.sort_ts.date().isoformat()
    label = _label_for(card)
    suffix = f" {label}" if label else ""
    head = f"- **{card.card_id}** ({card.display_name}) — {date_str}{suffix}"
    body = card.body_redacted.strip().splitlines()[0] if card.body_redacted.strip() else ""
    if len(body) > 200:
        body = body[:200].rstrip() + "..."
    body_line = f"  > {body}" if body else ""
    citation = f"  {card.citation_text}"
    parts = [head]
    if body_line:
        parts.append(body_line)
    parts.append(citation)
    return "\n".join(parts)


_EMPTY_MESSAGE = "관련 카드 없음. `synapse-memory daily` 로 vault 수집을 다시 확인하세요."
_FALLBACK_HEADER = "## 시간 정보 없음 — distance 순 폴백"


def _format_timeline_output(
    groups: list[TimelineGroup],
    limit: int,
    *,
    fallback_items: list[CardWithMeta] | None = None,
) -> str:
    """Timeline recall markdown output."""
    fallback_items = fallback_items or []
    timely_cards = sum(len(g.members) for g in groups)
    total = timely_cards + len(fallback_items)

    if total == 0:
        return _EMPTY_MESSAGE

    if total == 1:
        if groups:
            return _render_card_line(groups[0].members[0])
        return _render_card_line(fallback_items[0])

    out_parts: list[str] = []
    rendered = 0
    for group in groups:
        if rendered >= limit:
            break
        out_parts.append(f"## {group.quarter_label}")
        show_month_subheader = (
            len(group.members) >= 2 and len(group.months_present) >= 2
        )
        if show_month_subheader:
            current_month: int | None = None
            for card in group.members:
                if rendered >= limit:
                    break
                if card.sort_ts.month != current_month:
                    current_month = card.sort_ts.month
                    out_parts.append(f"### {card.sort_ts.year}-{current_month:02d}")
                out_parts.append(_render_card_line(card))
                rendered += 1
        else:
            for card in group.members:
                if rendered >= limit:
                    break
                out_parts.append(_render_card_line(card))
                rendered += 1

    if fallback_items and rendered < limit:
        out_parts.append(_FALLBACK_HEADER)
        fallback_sorted = sorted(
            fallback_items, key=lambda c: (c.distance is None, c.distance or 0.0)
        )
        for card in fallback_sorted:
            if rendered >= limit:
                break
            out_parts.append(_render_card_line(card))
            rendered += 1

    out_parts.append(f"\n총 {rendered}개 카드 (--limit {limit})")
    return "\n\n".join(out_parts)
