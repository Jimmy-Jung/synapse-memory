"""Small formatting helpers shared by CLI/reporting paths."""

from __future__ import annotations


def _format_bytes(value: int) -> str:
    """바이트 수를 1024 기반 사람이 읽는 단위로 변환."""
    units = ("B", "KiB", "MiB", "GiB")
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{value} B"
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{value} B"
