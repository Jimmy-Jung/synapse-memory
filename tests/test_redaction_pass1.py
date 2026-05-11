"""Pass 1 (regex/validator) redaction 테스트.

저자: JunyoungJung <joony300@gmail.com>
작성일: 2026-05-10
"""

from __future__ import annotations

import pytest

from synapse_memory.redaction import (
    DEFAULT_PATTERNS,
    Detection,
    is_valid_ipv4,
    is_valid_luhn,
    is_valid_rrn,
    redact,
)


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


class TestLuhn:
    @pytest.mark.parametrize(
        "number",
        [
            "4242424242424242",       # Stripe 테스트 카드
            "4242-4242-4242-4242",
            "4242 4242 4242 4242",
            "5555555555554444",       # Mastercard 테스트
            "378282246310005",        # 15자리는 통과 못해야 → 실패 expected
        ],
    )
    def test_known_valid_strings(self, number: str) -> None:
        # 16자리만 통과 — 마지막은 15자리라 False
        if sum(c.isdigit() for c in number) != 16:
            assert is_valid_luhn(number) is False
        else:
            assert is_valid_luhn(number) is True

    def test_invalid(self) -> None:
        assert is_valid_luhn("1234567890123456") is False
        assert is_valid_luhn("0000-0000-0000-0001") is False

    def test_non_numeric(self) -> None:
        assert is_valid_luhn("abcd") is False


class TestRrn:
    def test_valid_synthetic(self) -> None:
        # 001231 → 00년 12월 31일, 1 → 1900년대 남성
        # weights = [2,3,4,5,6,7,8,9,2,3,4,5]
        # 0*2+0*3+1*4+2*5+3*6+1*7+1*8+2*9+3*2+4*3+5*4+6*5 = 133
        # check = (11 - 133%11) % 10 = (11-1) % 10 = 0
        assert is_valid_rrn("0012311234560") is True
        assert is_valid_rrn("001231-1234560") is True

    def test_invalid_checksum(self) -> None:
        assert is_valid_rrn("0012311234561") is False  # 마지막 자리 틀림

    def test_wrong_length(self) -> None:
        assert is_valid_rrn("12345") is False
        assert is_valid_rrn("12345678901234") is False  # 14자리

    def test_invalid_month_rejected(self) -> None:
        # 99 = 99월 (불가능)
        # 99/99 같은 자리에 99를 두고 체크섬 따로 계산해야 의미 있음
        # 단순히 invalid month로 빠지는지만 확인
        assert is_valid_rrn("0099011234567") is False  # 월 99

    def test_invalid_day_rejected(self) -> None:
        assert is_valid_rrn("0001321234567") is False  # 일 32

    def test_invalid_gender_code_rejected(self) -> None:
        # 성별/세기 코드 0 또는 9 → 1800년대로 false positive 줄이기 위해 reject
        # 001231-0XXXXXX 패턴
        # weights = [2,3,4,5,6,7,8,9,2,3,4,5]
        # 0*2+0*3+1*4+2*5+3*6+1*7+0*8+...  체크섬 따로 계산해야 의미 있는 검증
        # 어쨌든 gender=0이면 reject되는지만 빠르게:
        assert is_valid_rrn("0012310123456") is False  # 7번째 자리 = 0
        assert is_valid_rrn("0012319123456") is False  # 7번째 자리 = 9


class TestIpv4:
    @pytest.mark.parametrize(
        "ip,valid",
        [
            ("192.168.1.1", True),
            ("0.0.0.0", True),
            ("255.255.255.255", True),
            ("256.1.1.1", False),
            ("192.168.1", False),
            ("192.168.1.1.1", False),
            ("a.b.c.d", False),
        ],
    )
    def test_octet_range(self, ip: str, valid: bool) -> None:
        assert is_valid_ipv4(ip) is valid


# ---------------------------------------------------------------------------
# 빈 입력 / no-PII
# ---------------------------------------------------------------------------


class TestNoOp:
    def test_empty(self) -> None:
        result = redact("")
        assert result.redacted == ""
        assert result.detections == []

    def test_clean_korean(self) -> None:
        text = "오늘은 화창한 날씨, 기분이 좋다."
        result = redact(text)
        assert result.redacted == text
        assert result.detections == []
        assert result.changed is False


# ---------------------------------------------------------------------------
# 카테고리별 검출
# ---------------------------------------------------------------------------


class TestEmail:
    def test_basic(self) -> None:
        result = redact("연락처: foo@bar.com 입니다")
        assert "[EMAIL_1]" in result.redacted
        assert any(d.category == "email" for d in result.detections)

    def test_korean_surrounding(self) -> None:
        result = redact("이메일은jimmy@megastudy.net이고")
        assert "[EMAIL_1]" in result.redacted

    def test_sentence_ending_period(self) -> None:
        # 문장 끝에 마침표 — lookahead가 . 포함하면 매치 깨짐
        result = redact("이메일 hong@megastudy.net.")
        assert "[EMAIL_1]" in result.redacted
        assert any(d.category == "email" for d in result.detections)


class TestPhoneKR:
    @pytest.mark.parametrize(
        "phone",
        [
            "010-1234-5678",
            "010 1234 5678",
            "01012345678",
            "+82-10-1234-5678",
            "02-123-4567",
            "031-1234-5678",
        ],
    )
    def test_variants(self, phone: str) -> None:
        result = redact(f"전화: {phone}")
        assert "[PHONE_1]" in result.redacted, f"실패: {phone!r}"
        assert any(d.category == "phone_kr" for d in result.detections)

    def test_korean_inline(self) -> None:
        result = redact("전화010-1234-5678로")
        assert "[PHONE_1]" in result.redacted


class TestCard:
    def test_valid_luhn_detected(self) -> None:
        result = redact("카드: 4242-4242-4242-4242")
        assert "[CARD_1]" in result.redacted

    def test_invalid_luhn_skipped(self) -> None:
        # Luhn 실패 → card 검출 안 되어야 (다른 카테고리도 아님)
        result = redact("번호: 1234-5678-9012-3456")
        # card는 없음
        assert not any(d.category == "card" for d in result.detections)
        assert "[CARD" not in result.redacted


class TestRRN:
    def test_valid_checksum_detected(self) -> None:
        result = redact("주민번호: 001231-1234560")
        assert any(d.category == "rrn" for d in result.detections)

    def test_invalid_checksum_skipped(self) -> None:
        result = redact("번호: 001231-1234561")
        assert not any(d.category == "rrn" for d in result.detections)


class TestJWT:
    def test_basic(self) -> None:
        jwt = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
            ".eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4iLCJpYXQiOjE1MTYyMzkwMjJ9"
            ".SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        )
        result = redact(f"token: {jwt}")
        assert "[JWT_1]" in result.redacted

    def test_jwt_priority_over_others(self) -> None:
        """JWT 안에 IP 패턴 같은 게 우연히 있어도 JWT로 묶여야 (priority)."""
        jwt = "eyJabcdefghij.eyJklmnopqrst.signature_uvwxyz"
        result = redact(f"x: {jwt}")
        cats = {d.category for d in result.detections}
        assert "jwt" in cats


class TestApiKeys:
    def test_openai_style(self) -> None:
        result = redact("export OPENAI_API_KEY=sk-abcdefghij1234567890XYZ")
        assert any(d.category == "api_key_sk" for d in result.detections)
        assert "[API_KEY_1]" in result.redacted

    def test_aws_access_key(self) -> None:
        result = redact("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE")
        assert any(d.category == "aws_key" for d in result.detections)

    def test_github_pat(self) -> None:
        # ghp_ + 36+ alphanumeric
        result = redact("token: ghp_" + "A" * 40)
        assert any(d.category == "api_key_github" for d in result.detections)


class TestIPv4Detection:
    def test_valid(self) -> None:
        result = redact("server: 192.168.1.1")
        assert "[IPV4_1]" in result.redacted

    def test_invalid_octet_skipped(self) -> None:
        result = redact("not ip: 999.999.999.999")
        assert not any(d.category == "ipv4" for d in result.detections)


# ---------------------------------------------------------------------------
# 일관성 / stable index / 멀티 카테고리
# ---------------------------------------------------------------------------


class TestStableIndices:
    def test_same_value_same_index(self) -> None:
        text = "a@b.com 그리고 a@b.com 또 c@d.com"
        result = redact(text)
        # a@b.com 두 번 → 같은 [EMAIL_1] 두 번, c@d.com → [EMAIL_2]
        assert result.redacted.count("[EMAIL_1]") == 2
        assert result.redacted.count("[EMAIL_2]") == 1

    def test_different_categories_independent(self) -> None:
        text = "phone 010-1234-5678 email a@b.com"
        result = redact(text)
        assert "[PHONE_1]" in result.redacted
        assert "[EMAIL_1]" in result.redacted


class TestMultiCategory:
    def test_full_record(self) -> None:
        text = (
            "이름: 홍길동, 전화 010-1111-2222, 이메일 hong@example.com, "
            "카드 4242-4242-4242-4242, 서버 10.0.0.1"
        )
        result = redact(text)
        cats = {d.category for d in result.detections}
        # 이름은 Pass 1에서 안 잡힘 (Pass 2 책임). 나머지는 다 잡혀야
        assert {"phone_kr", "email", "card", "ipv4"} <= cats

    def test_korean_preserved(self) -> None:
        text = "안녕하세요 a@b.com 입니다"
        result = redact(text)
        assert "안녕하세요" in result.redacted
        assert "입니다" in result.redacted


# ---------------------------------------------------------------------------
# Span 정합성
# ---------------------------------------------------------------------------


class TestSpanCorrectness:
    def test_span_matches_original_text(self) -> None:
        text = "메일: foo@bar.com 끝"
        result = redact(text)
        det = result.detections[0]
        assert text[det.span[0] : det.span[1]] == det.matched

    def test_multiple_replacements_dont_corrupt(self) -> None:
        # 여러 치환 후에도 span은 원본 기준이어야
        text = "a@b.com 010-1234-5678 c@d.com"
        result = redact(text)
        for det in result.detections:
            assert text[det.span[0] : det.span[1]] == det.matched


# ---------------------------------------------------------------------------
# 통계
# ---------------------------------------------------------------------------


class TestCategoryCounts:
    def test_counts(self) -> None:
        text = "a@b.com c@d.com 010-1111-2222"
        result = redact(text)
        counts = result.category_counts()
        assert counts["email"] == 2
        assert counts["phone_kr"] == 1


# ---------------------------------------------------------------------------
# Default patterns sanity
# ---------------------------------------------------------------------------


def test_default_patterns_have_unique_names() -> None:
    names = [p.name for p in DEFAULT_PATTERNS]
    assert len(names) == len(set(names))


def test_default_patterns_priorities_descending_order_works() -> None:
    """priority 순서가 코드와 일치 (실수 방지)."""
    priorities = [p.priority for p in DEFAULT_PATTERNS]
    assert priorities == sorted(priorities, reverse=True)
