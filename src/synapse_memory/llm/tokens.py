"""토큰 추정 휴리스틱 (provider-neutral).

특정 백엔드에 묶이지 않은 순수 함수. claude/codex 어댑터가 사용한다.
"""

# 토큰 추정 휴리스틱 (실측 후 calibrate 가능)
KOREAN_CHARS_PER_TOKEN = 1.5
LATIN_CHARS_PER_TOKEN = 4.0

# 한글 음절 범위
_HANGUL_SYLLABLE_RANGE = ("가", "힣")


def _is_korean(char: str) -> bool:
    """한글 음절 여부 (자모 제외)."""
    return _HANGUL_SYLLABLE_RANGE[0] <= char <= _HANGUL_SYLLABLE_RANGE[1]


def estimate_tokens(text: str) -> int:
    """토큰 수 휴리스틱 추정.

    한국어: 1.5 char/token, 라틴/숫자: 4 char/token. 정확도 ±20%.
    """
    if not text:
        return 0
    korean_chars = sum(1 for c in text if _is_korean(c))
    other_chars = len(text) - korean_chars
    estimated = korean_chars / KOREAN_CHARS_PER_TOKEN + other_chars / LATIN_CHARS_PER_TOKEN
    return max(1, int(estimated) + 1)
