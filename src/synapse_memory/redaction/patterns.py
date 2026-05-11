"""PII 정규식 사전 + validator.

각 Pattern은 (name, regex, placeholder, priority, validator?) 5튜플로 정의.

priority: 높을수록 먼저 매치. 긴/구체적 패턴(JWT, AWS key 등)을 짧은 패턴(전화,
IP)보다 우선시켜 겹침 시 긴 쪽이 살아남음.

validator: 정규식 매치 후 추가 검증 (Luhn 체크섬, RRN 체크섬, IPv4 옥텟 범위 등).
False positive 줄이는 핵심 안전장치.

저자: JunyoungJung <joony300@gmail.com>
작성일: 2026-05-10
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Pattern as RePattern

# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


def is_valid_luhn(s: str) -> bool:
    """카드번호 Luhn 알고리즘 검증.

    16자리 숫자만 통과. 구분자(-, 공백) 자동 제거.
    """
    digits = [int(c) for c in s if c.isdigit()]
    if len(digits) != 16:
        return False
    checksum = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def is_valid_rrn(s: str) -> bool:
    """한국 주민등록번호 13자리 — 다중 검증 (false positive 컷).

    1. 길이 13
    2. 생년월일 (YYMMDD): 월 1-12, 일 1-31
    3. 성별/세기 코드: 1-8만 (0/9는 1800년대로 현실에 거의 없음)
    4. 표준 체크섬: weights=[2,3,4,5,6,7,8,9,2,3,4,5], check=(11-sum%11)%10

    랜덤 13자리 ID가 우연히 체크섬만 만족하는 false positive를 크게 줄임.
    """
    digits = [int(c) for c in s if c.isdigit()]
    if len(digits) != 13:
        return False

    # 생년월일 sanity
    month = digits[2] * 10 + digits[3]
    day = digits[4] * 10 + digits[5]
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return False

    # 성별/세기 코드 — 1~8만 valid (1/2: 1900년대, 3/4: 2000년대,
    # 5~8: 외국인). 0,9는 1800년대 — 현실 데이터에 등장 시 false positive.
    gender = digits[6]
    if gender < 1 or gender > 8:
        return False

    weights = [2, 3, 4, 5, 6, 7, 8, 9, 2, 3, 4, 5]
    total = sum(d * w for d, w in zip(digits[:12], weights, strict=True))
    expected = (11 - total % 11) % 10
    return expected == digits[12]


def is_valid_ipv4(s: str) -> bool:
    """IPv4 4옥텟 0-255 검증."""
    parts = s.split(".")
    if len(parts) != 4:
        return False
    for p in parts:
        if not p.isdigit() or len(p) > 3:
            return False
        n = int(p)
        if n < 0 or n > 255:
            return False
    return True


# ---------------------------------------------------------------------------
# Pattern
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Pattern:
    """단일 PII 카테고리 정의."""

    name: str
    regex: RePattern[str]
    placeholder_prefix: str  # 예: "PHONE" → "[PHONE_1]"
    priority: int = 0
    validator: Callable[[str], bool] | None = None

    def make_placeholder(self, index: int) -> str:
        return f"[{self.placeholder_prefix}_{index}]"


# ---------------------------------------------------------------------------
# Default patterns (priority 내림차순)
# ---------------------------------------------------------------------------


DEFAULT_PATTERNS: list[Pattern] = [
    # JWT — 가장 긴/구체적 패턴이라 최우선
    Pattern(
        name="jwt",
        regex=re.compile(
            r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,}"
        ),
        placeholder_prefix="JWT",
        priority=100,
    ),
    # AWS Access Key ID
    Pattern(
        name="aws_key",
        regex=re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        placeholder_prefix="AWS_KEY",
        priority=95,
    ),
    # OpenAI/Anthropic style API keys
    Pattern(
        name="api_key_sk",
        regex=re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b"),
        placeholder_prefix="API_KEY",
        priority=90,
    ),
    # GitHub PAT/OAuth
    Pattern(
        name="api_key_github",
        regex=re.compile(r"\b(?:ghp|ghs|gho|ghu|ghr)_[A-Za-z0-9]{36,}\b"),
        placeholder_prefix="API_KEY",
        priority=90,
    ),
    # Bearer 토큰 (HTTP Authorization)
    Pattern(
        name="bearer",
        regex=re.compile(r"Bearer\s+[A-Za-z0-9_\-\.=]{16,}"),
        placeholder_prefix="BEARER",
        priority=85,
    ),
    # 이메일 — RFC 5322 단순화
    # \b는 ASCII boundary만 인식하므로 한국어 옆에서 동작 안 함.
    # 대신 email-char 아닌 것으로 둘러싸이는 lookaround 사용.
    # lookahead에서 `.` 제외 — 그래야 문장 끝 마침표 ("hong@x.com.") 지원.
    Pattern(
        name="email",
        regex=re.compile(
            r"(?<![A-Za-z0-9._%+\-@])"
            r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"
            r"(?![A-Za-z0-9_\-])"
        ),
        placeholder_prefix="EMAIL",
        priority=80,
    ),
    # 한국 주민등록번호 + 체크섬
    Pattern(
        name="rrn",
        regex=re.compile(r"(?<!\d)\d{6}[-\s]?\d{7}(?!\d)"),
        placeholder_prefix="RRN",
        priority=75,
        validator=is_valid_rrn,
    ),
    # 신용카드 + Luhn
    Pattern(
        name="card",
        regex=re.compile(r"(?<!\d)\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}(?!\d)"),
        placeholder_prefix="CARD",
        priority=70,
        validator=is_valid_luhn,
    ),
    # 한국 휴대전화/유선번호
    # 휴대: 010/011/016/017/018/019 + 3-4자리 + 4자리
    # 유선: 02 (서울) 또는 0XX (지역) + 3-4자리 + 4자리
    Pattern(
        name="phone_kr",
        regex=re.compile(
            r"(?<!\d)(?:\+?82[-\s]?|0)1[0-9][-\s]?\d{3,4}[-\s]?\d{4}(?!\d)"
            r"|(?<!\d)0\d{1,2}[-\s]?\d{3,4}[-\s]?\d{4}(?!\d)"
        ),
        placeholder_prefix="PHONE",
        priority=65,
    ),
    # IPv4 + 옥텟 범위
    Pattern(
        name="ipv4",
        regex=re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)"),
        placeholder_prefix="IPV4",
        priority=60,
        validator=is_valid_ipv4,
    ),
]
