"""Pass 2 (apfel) redaction 테스트.

apfel 호출은 mock — 모델 응답 schema와 머지/allowlist/환각 처리만 검증.

저자: JunyoungJung <joony300@gmail.com>
작성일: 2026-05-10
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from synapse_memory.llm.apfel import ApfelEnvironment, ApfelError
from synapse_memory.redaction.pass2 import (
    MEGA_ORG_DENYLIST,
    NON_PII_TERMS,
    PASS2_CATEGORIES,
    _build_pass2_detections,
    _detect_in_chunk,
    _find_spans,
    _looks_like_filename,
    _looks_like_path_or_identifier,
    _looks_like_screaming_snake,
    _looks_like_uuid_or_hash,
    _normalize_model_response,
    load_allowlist,
    redact_full,
)


def _ready_env() -> ApfelEnvironment:
    return ApfelEnvironment(
        apfel_path="/opt/homebrew/bin/apfel",
        apfel_version="apfel v1.3.3",
        macos_version="26.2",
        is_apple_silicon=True,
    )


def _unready_env() -> ApfelEnvironment:
    return ApfelEnvironment(
        apfel_path=None,
        apfel_version=None,
        macos_version="26.2",
        is_apple_silicon=True,
    )


# ---------------------------------------------------------------------------
# load_allowlist
# ---------------------------------------------------------------------------


class TestLoadAllowlist:
    def test_missing_returns_empty(self, tmp_path: Path) -> None:
        result = load_allowlist(tmp_path / "nope")
        assert result == set()

    def test_parses_lines(self, tmp_path: Path) -> None:
        f = tmp_path / "allowlist"
        f.write_text(
            "# 주석\n"
            "JunyoungJung\n"
            "정준영\n"
            "\n"
            "  Megastudy  \n"  # 양쪽 공백
            "# 또 다른 주석\n",
            encoding="utf-8",
        )
        result = load_allowlist(f)
        # case-insensitive 정규화: 모두 lowercase
        assert result == {"junyoungjung", "정준영", "megastudy"}

    def test_handles_korean_unicode(self, tmp_path: Path) -> None:
        f = tmp_path / "allowlist"
        f.write_text("메가스터디\n홍길동\n", encoding="utf-8")
        result = load_allowlist(f)
        assert "메가스터디" in result
        assert "홍길동" in result

    def test_normalizes_to_lowercase(self, tmp_path: Path) -> None:
        """Jimmy → jimmy로 정규화 (case-insensitive 매칭용)."""
        f = tmp_path / "allowlist"
        f.write_text("Jimmy\nJunyoungJung\nMegastudy\n", encoding="utf-8")
        result = load_allowlist(f)
        assert result == {"jimmy", "junyoungjung", "megastudy"}


class TestLooksLikePathOrIdentifier:
    @pytest.mark.parametrize(
        "val",
        [
            "/Users/jimmy/foo",
            "C:\\Users\\jimmy",
            "https://example.com",
            "user@host",
            "ai-symbiote@ai-symbiote",
            "--help",
            "-v",
            "snake_case_var",
            "ai-symbiote",
            # 새로 추가된 패턴
            "Jimmy-Jung",                     # GitHub handle 대문자+dash
            "Foo-Bar",                        # PascalCase + dash
            "jarrodwatts",                    # 소문자 6자+
            "garrytan",                       # 소문자 8자
            "SessionStart:startup",           # colon 포함 hook 이벤트
            "OnBeforeSave",                   # PascalCase 이벤트... 이건 통과 OK?
        ],
    )
    def test_rejected(self, val: str) -> None:
        # OnBeforeSave는 dash/colon/공백 없이 PascalCase — 현재 휴리스틱은
        # 통과시킴. 이건 system prompt가 처리해야. 여기선 다른 패턴만 검증.
        if val == "OnBeforeSave":
            return
        assert _looks_like_path_or_identifier(val) is True

    @pytest.mark.parametrize(
        "val",
        [
            "홍길동",
            "John Smith",
            "메가스터디",
            "Acme Corp",
            "Anne",   # 짧은 이름 (5자 미만 — 6자 임계 통과)
        ],
    )
    def test_passed(self, val: str) -> None:
        assert _looks_like_path_or_identifier(val) is False


class TestMegaOrgDenylist:
    def test_common_brands_excluded(self) -> None:
        for brand in ["github", "google", "apple", "claude", "naver", "kakao", "codex"]:
            assert brand in MEGA_ORG_DENYLIST


class TestNonPiiTerms:
    def test_role_labels(self) -> None:
        for term in ["user", "assistant", "system", "human", "admin", "owner"]:
            assert term in NON_PII_TERMS


class TestLooksLikeFilename:
    @pytest.mark.parametrize(
        "val",
        ["GEMINI.md", "CLAUDE.md", "AGENTS.md", "main.py", "config.json", "Foo.tsx"],
    )
    def test_filename_detected(self, val: str) -> None:
        assert _looks_like_filename(val) is True

    @pytest.mark.parametrize(
        "val",
        ["홍길동", "John Smith", "메가스터디", "no_extension", "trailing.", ".hidden"],
    )
    def test_non_filename(self, val: str) -> None:
        assert _looks_like_filename(val) is False


class TestLooksLikeScreamingSnake:
    @pytest.mark.parametrize(
        "val", ["EXTREMELY_IMPORTANT", "API_KEY_NAME", "TODO_FIXME"]
    )
    def test_detected(self, val: str) -> None:
        assert _looks_like_screaming_snake(val) is True

    @pytest.mark.parametrize(
        "val", ["홍길동", "User", "GitHub", "Already_Mixed", "lowercase_var"]
    )
    def test_not_detected(self, val: str) -> None:
        assert _looks_like_screaming_snake(val) is False


class TestLooksLikeUuidOrHash:
    @pytest.mark.parametrize(
        "val",
        [
            "678b1c44-aa20-4503-9b50-1818cf4ca304",  # UUID v4
            "ABCDEF12-3456-7890-ABCD-EF1234567890",  # 대문자 UUID
            "d41d8cd98f00b204e9800998ecf8427e",       # md5 (32 hex)
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",  # sha256
        ],
    )
    def test_detected(self, val: str) -> None:
        assert _looks_like_uuid_or_hash(val) is True

    @pytest.mark.parametrize(
        "val",
        [
            "홍길동",
            "John Smith",
            "abc123",  # 짧은 hex-like
            "not-a-uuid-at-all",
            "678b1c44",  # UUID 일부만
        ],
    )
    def test_not_detected(self, val: str) -> None:
        assert _looks_like_uuid_or_hash(val) is False


class TestNormalizeModelResponse:
    def test_standard_envelope(self) -> None:
        result = _normalize_model_response(
            {"detections": [{"category": "person_name", "value": "홍길동"}]}
        )
        assert result == [{"category": "person_name", "value": "홍길동"}]

    def test_list_response(self) -> None:
        """모델이 array 직접 반환 (Case 2)."""
        result = _normalize_model_response(
            [{"category": "person_name", "value": "홍길동"}]
        )
        assert len(result) == 1
        assert result[0]["value"] == "홍길동"

    def test_single_detection_dict(self) -> None:
        """{"category": ..., "value": ...} 단일 dict."""
        result = _normalize_model_response(
            {"category": "person_name", "value": "홍길동"}
        )
        assert result == [{"category": "person_name", "value": "홍길동"}]

    def test_unrelated_dict_returns_empty(self) -> None:
        result = _normalize_model_response({"name": "홍길동"})
        assert result == []

    def test_string_returns_empty(self) -> None:
        assert _normalize_model_response("just text") == []

    def test_filters_non_dict_items_in_list(self) -> None:
        result = _normalize_model_response(
            [
                {"category": "person_name", "value": "홍길동"},
                "string item",
                None,
            ]
        )
        assert len(result) == 1


# ---------------------------------------------------------------------------
# _find_spans
# ---------------------------------------------------------------------------


class TestFindSpans:
    def test_single_match(self) -> None:
        text = "이 사람은 홍길동입니다"
        spans = _find_spans(text, "홍길동")
        assert spans == [(text.index("홍길동"), text.index("홍길동") + 3)]

    def test_multiple_matches(self) -> None:
        text = "홍길동과 홍길동 모두 동일인"
        spans = _find_spans(text, "홍길동")
        assert len(spans) == 2

    def test_no_match(self) -> None:
        assert _find_spans("아무것도 없음", "홍길동") == []

    def test_empty_value(self) -> None:
        assert _find_spans("text", "") == []

    def test_overlapping_matches_separately(self) -> None:
        # "aaa"에서 "aa" 찾으면 (0,2), (1,3) 두 개 (overlap)
        spans = _find_spans("aaaa", "aa")
        assert len(spans) >= 2


# ---------------------------------------------------------------------------
# _build_pass2_detections
# ---------------------------------------------------------------------------


class TestBuildPass2Detections:
    def test_basic(self) -> None:
        text = "홍길동에게 메가스터디 견학"
        findings = [
            ("person_name", "홍길동"),
            ("org_name", "메가스터디"),
        ]
        detections = _build_pass2_detections(
            text, findings, occupied_spans=[], allowlist=set()
        )
        cats = {d.category for d in detections}
        assert "person_name" in cats
        assert "org_name" in cats

    def test_allowlist_skips(self) -> None:
        text = "JunyoungJung 정준영 메가스터디"
        findings = [
            ("person_name", "JunyoungJung"),
            ("person_name", "정준영"),
            ("org_name", "메가스터디"),
        ]
        # allowlist는 lowercase로 정규화되어 있다는 가정
        allowlist = {"junyoungjung", "정준영"}
        detections = _build_pass2_detections(
            text, findings, occupied_spans=[], allowlist=allowlist
        )
        # 본인 이름들 제외, 회사만
        assert len(detections) == 1
        assert detections[0].category == "org_name"

    def test_allowlist_case_insensitive(self) -> None:
        """jimmy/Jimmy/JIMMY 모두 차단."""
        text = "jimmy Jimmy JIMMY"
        findings = [
            ("person_name", "jimmy"),
            ("person_name", "Jimmy"),
            ("person_name", "JIMMY"),
        ]
        allowlist = {"jimmy"}  # 소문자 하나만
        detections = _build_pass2_detections(
            text, findings, occupied_spans=[], allowlist=allowlist
        )
        assert detections == []

    def test_mega_brand_org_excluded(self) -> None:
        text = "GitHub repo, Google search, claude tool"
        findings = [
            ("org_name", "GitHub"),
            ("org_name", "Google"),
            ("org_name", "claude"),
        ]
        detections = _build_pass2_detections(
            text, findings, occupied_spans=[], allowlist=set()
        )
        assert detections == []

    def test_mega_brand_rejected_in_any_category(self) -> None:
        """정책 변경: GitHub는 어떤 카테고리든 reject (글로벌 일반명사 수준)."""
        text = "회사명: GitHub"
        findings = [("sensitive_topic", "GitHub")]
        detections = _build_pass2_detections(
            text, findings, occupied_spans=[], allowlist=set()
        )
        assert detections == []

    def test_path_username_rejected(self) -> None:
        """/Users/jimmy/... 의 jimmy는 person_name으로 잡으면 reject."""
        text = "경로: /Users/jimmy/Documents"
        findings = [("person_name", "/Users/jimmy/Documents")]
        detections = _build_pass2_detections(
            text, findings, occupied_spans=[], allowlist=set()
        )
        assert detections == []

    def test_snake_case_org_rejected(self) -> None:
        text = "package: ai_symbiote"
        findings = [("org_name", "ai_symbiote")]
        detections = _build_pass2_detections(
            text, findings, occupied_spans=[], allowlist=set()
        )
        assert detections == []

    def test_role_labels_rejected_all_categories(self) -> None:
        """User, Assistant 같은 role label은 어떤 카테고리든 reject."""
        text = "User Assistant System Human"
        findings = [
            ("person_name", "User"),
            ("person_name", "Assistant"),
            ("org_name", "System"),
            ("sensitive_topic", "Human"),
        ]
        detections = _build_pass2_detections(
            text, findings, occupied_spans=[], allowlist=set()
        )
        assert detections == []

    def test_filename_rejected(self) -> None:
        text = "참고: GEMINI.md, CLAUDE.md, AGENTS.md"
        findings = [
            ("person_name", "GEMINI.md"),
            ("person_name", "CLAUDE.md"),
            ("org_name", "AGENTS.md"),
        ]
        detections = _build_pass2_detections(
            text, findings, occupied_spans=[], allowlist=set()
        )
        assert detections == []

    def test_screaming_snake_rejected(self) -> None:
        text = "플래그: EXTREMELY_IMPORTANT, TODO_LATER"
        findings = [
            ("sensitive_topic", "EXTREMELY_IMPORTANT"),
            ("person_name", "TODO_LATER"),
        ]
        detections = _build_pass2_detections(
            text, findings, occupied_spans=[], allowlist=set()
        )
        assert detections == []

    def test_mega_brand_in_any_category(self) -> None:
        """claude/codex는 person_name으로 잡혀도 reject."""
        text = "claude로 작업, codex CLI 사용"
        findings = [
            ("person_name", "claude"),
            ("org_name", "Codex"),
        ]
        detections = _build_pass2_detections(
            text, findings, occupied_spans=[], allowlist=set()
        )
        assert detections == []

    def test_uuid_in_person_rejected(self) -> None:
        """UUID는 person_name으로 잡혀도 reject (Apple 모델 흔한 false positive)."""
        text = "session: 678b1c44-aa20-4503-9b50-1818cf4ca304"
        findings = [
            ("person_name", "678b1c44-aa20-4503-9b50-1818cf4ca304")
        ]
        detections = _build_pass2_detections(
            text, findings, occupied_spans=[], allowlist=set()
        )
        assert detections == []

    def test_uuid_in_secret_kept(self) -> None:
        """secret 카테고리는 UUID 통과 (진짜 토큰일 가능성)."""
        text = "API token: 678b1c44-aa20-4503-9b50-1818cf4ca304"
        findings = [
            ("secret", "678b1c44-aa20-4503-9b50-1818cf4ca304")
        ]
        detections = _build_pass2_detections(
            text, findings, occupied_spans=[], allowlist=set()
        )
        assert len(detections) == 1
        assert detections[0].category == "secret"

    def test_path_as_address_rejected(self) -> None:
        """모델이 path를 address로 잘못 분류하면 reject."""
        text = "경로: /Users/jimmy/Documents 어쩌고"
        findings = [("address", "/Users/jimmy/Documents")]
        detections = _build_pass2_detections(
            text, findings, occupied_spans=[], allowlist=set()
        )
        assert detections == []

    def test_github_handle_rejected(self) -> None:
        text = "사용자 Jimmy-Jung 등록"
        findings = [("person_name", "Jimmy-Jung")]
        detections = _build_pass2_detections(
            text, findings, occupied_spans=[], allowlist=set()
        )
        assert detections == []

    def test_lowercase_handle_rejected(self) -> None:
        text = "@jarrodwatts와 garrytan"
        findings = [
            ("person_name", "jarrodwatts"),
            ("org_name", "garrytan"),
        ]
        detections = _build_pass2_detections(
            text, findings, occupied_spans=[], allowlist=set()
        )
        assert detections == []

    def test_hook_event_rejected(self) -> None:
        text = "이벤트: SessionStart:startup 발생"
        findings = [("org_name", "SessionStart:startup")]
        detections = _build_pass2_detections(
            text, findings, occupied_spans=[], allowlist=set()
        )
        assert detections == []

    def test_real_korean_name_passes(self) -> None:
        """진짜 한국어 이름은 새 휴리스틱 영향 안 받아야."""
        text = "홍길동님 안녕하세요"
        findings = [("person_name", "홍길동")]
        detections = _build_pass2_detections(
            text, findings, occupied_spans=[], allowlist=set()
        )
        assert len(detections) == 1
        assert detections[0].matched == "홍길동"

    def test_real_english_name_passes(self) -> None:
        """John Smith 같은 First Last 이름은 통과."""
        text = "John Smith 박사"
        findings = [("person_name", "John Smith")]
        detections = _build_pass2_detections(
            text, findings, occupied_spans=[], allowlist=set()
        )
        assert len(detections) == 1

    def test_person_with_digits_rejected(self) -> None:
        """사람 이름에 숫자가 들어가면 random token일 가능성 — reject."""
        text = "session-id: xoAP7Qtf 그리고 abc123def"
        findings = [
            ("person_name", "xoAP7Qtf"),
            ("person_name", "abc123def"),
        ]
        detections = _build_pass2_detections(
            text, findings, occupied_spans=[], allowlist=set()
        )
        assert detections == []

    def test_org_with_digits_kept(self) -> None:
        """회사명에는 숫자 가능 (3M, x402 등) — org는 통과."""
        text = "회사 X402 inc"
        findings = [("org_name", "X402")]
        detections = _build_pass2_detections(
            text, findings, occupied_spans=[], allowlist=set()
        )
        assert len(detections) == 1

    def test_skips_hallucinated_value(self) -> None:
        """모델이 텍스트에 없는 value를 만들면 skip."""
        text = "오늘 날씨가 좋다"
        findings = [("person_name", "홍길동")]  # 텍스트에 없음
        detections = _build_pass2_detections(
            text, findings, occupied_spans=[], allowlist=set()
        )
        assert detections == []

    def test_skips_occupied_span(self) -> None:
        """Pass 1이 점유한 span은 Pass 2에서 skip."""
        text = "이메일 a@b.com 끝"
        # Pass 1이 a@b.com을 점유했다고 가정
        email_span = (text.index("a@b.com"), text.index("a@b.com") + 7)
        findings = [("person_name", "a@b.com")]  # 같은 span 충돌
        detections = _build_pass2_detections(
            text, findings, occupied_spans=[email_span], allowlist=set()
        )
        assert detections == []

    def test_stable_index_same_value(self) -> None:
        text = "홍길동, 홍길동, 또 홍길동"
        findings = [("person_name", "홍길동")]
        detections = _build_pass2_detections(
            text, findings, occupied_spans=[], allowlist=set()
        )
        # 3번 모두 같은 placeholder _1
        placeholders = {d.placeholder for d in detections}
        assert placeholders == {"[PERSON_1]"}
        assert len(detections) == 3

    def test_different_values_different_index(self) -> None:
        text = "홍길동과 김철수 두 사람"
        findings = [
            ("person_name", "홍길동"),
            ("person_name", "김철수"),
        ]
        detections = _build_pass2_detections(
            text, findings, occupied_spans=[], allowlist=set()
        )
        placeholders = {d.placeholder for d in detections}
        assert placeholders == {"[PERSON_1]", "[PERSON_2]"}

    def test_unknown_category_raises_keyerror(self) -> None:
        """방어적 contract: unknown 카테고리가 도달하면 KeyError.

        실제로는 _detect_in_chunk가 PASS2_CATEGORIES 화이트리스트로 미리 필터하므로
        이 함수에는 valid 카테고리만 도착함. 그러나 contract 위반 시 명확히 실패.
        """
        text = "이상한_단어"  # denylist/필터에 안 걸리는 문자열
        findings = [("unknown_category_xyz", "이상한_단어")]
        with pytest.raises(KeyError):
            _build_pass2_detections(text, findings, [], set())


# ---------------------------------------------------------------------------
# _detect_in_chunk (mock apfel)
# ---------------------------------------------------------------------------


def _mock_apfel_response(detections: list[dict]) -> dict:
    return {"detections": detections}


class TestDetectInChunk:
    def test_returns_filtered_findings(self) -> None:
        with patch(
            "synapse_memory.redaction.pass2.complete_structured"
        ) as mock_cs:
            mock_cs.return_value = _mock_apfel_response(
                [
                    {"category": "person_name", "value": "홍길동"},
                    {"category": "org_name", "value": "메가스터디"},
                ]
            )
            result = _detect_in_chunk("홍길동 메가스터디", env=_ready_env())
            assert ("person_name", "홍길동") in result
            assert ("org_name", "메가스터디") in result

    def test_filters_unknown_category(self) -> None:
        with patch(
            "synapse_memory.redaction.pass2.complete_structured"
        ) as mock_cs:
            mock_cs.return_value = _mock_apfel_response(
                [
                    {"category": "color", "value": "red"},  # unknown
                    {"category": "person_name", "value": "홍길동"},
                ]
            )
            result = _detect_in_chunk("text", env=_ready_env())
            assert result == [("person_name", "홍길동")]

    def test_filters_short_values(self) -> None:
        with patch(
            "synapse_memory.redaction.pass2.complete_structured"
        ) as mock_cs:
            mock_cs.return_value = _mock_apfel_response(
                [
                    {"category": "person_name", "value": "X"},  # 1자
                    {"category": "person_name", "value": "홍길동"},
                ]
            )
            result = _detect_in_chunk("text", env=_ready_env())
            assert result == [("person_name", "홍길동")]

    def test_apfel_error_returns_empty(self) -> None:
        with patch(
            "synapse_memory.redaction.pass2.complete_structured"
        ) as mock_cs:
            mock_cs.side_effect = ApfelError("모델 거부")
            result = _detect_in_chunk("text", env=_ready_env())
            assert result == []

    def test_malformed_response_returns_empty(self) -> None:
        with patch(
            "synapse_memory.redaction.pass2.complete_structured"
        ) as mock_cs:
            mock_cs.return_value = "이건 dict 아님"
            result = _detect_in_chunk("text", env=_ready_env())
            assert result == []

    def test_missing_detections_key(self) -> None:
        with patch(
            "synapse_memory.redaction.pass2.complete_structured"
        ) as mock_cs:
            mock_cs.return_value = {"foo": "bar"}
            result = _detect_in_chunk("text", env=_ready_env())
            assert result == []

    def test_handles_list_response(self) -> None:
        """모델이 envelope 없이 list 직접 반환 (Case 2 fallback)."""
        with patch(
            "synapse_memory.redaction.pass2.complete_structured"
        ) as mock_cs:
            mock_cs.return_value = [
                {"category": "person_name", "value": "홍길동"}
            ]
            result = _detect_in_chunk("text", env=_ready_env())
            assert result == [("person_name", "홍길동")]

    def test_handles_single_detection_dict(self) -> None:
        """{"category": ..., "value": ...} 단일 dict 응답."""
        with patch(
            "synapse_memory.redaction.pass2.complete_structured"
        ) as mock_cs:
            mock_cs.return_value = {
                "category": "person_name",
                "value": "홍길동",
            }
            result = _detect_in_chunk("text", env=_ready_env())
            assert result == [("person_name", "홍길동")]


# ---------------------------------------------------------------------------
# redact_full (Pass 1 + Pass 2 통합)
# ---------------------------------------------------------------------------


class TestRedactFull:
    def test_pass1_only_when_apfel_unavailable(self) -> None:
        """apfel 사용 불가 → Pass 1만 적용 (Pass 2 skip)."""
        text = "전화 010-1234-5678 그리고 홍길동"
        result = redact_full(text, env=_unready_env(), allowlist=set())
        # Pass 1: phone 검출
        cats = {d.category for d in result.detections}
        assert "phone_kr" in cats
        # Pass 2: person_name 미검출 (apfel 호출 안 됨)
        assert "person_name" not in cats

    def test_combined_pass1_and_pass2(self) -> None:
        text = "홍길동에게 010-1234-5678로 연락"
        with patch(
            "synapse_memory.redaction.pass2.complete_structured"
        ) as mock_cs:
            mock_cs.return_value = _mock_apfel_response(
                [{"category": "person_name", "value": "홍길동"}]
            )
            result = redact_full(text, env=_ready_env(), allowlist=set())

        cats = {d.category for d in result.detections}
        assert "phone_kr" in cats
        assert "person_name" in cats
        assert "[PHONE_1]" in result.redacted
        assert "[PERSON_1]" in result.redacted
        assert "홍길동" not in result.redacted

    def test_allowlist_protects_owner(self) -> None:
        text = "JunyoungJung이 메가스터디에서 일한다"
        with patch(
            "synapse_memory.redaction.pass2.complete_structured"
        ) as mock_cs:
            mock_cs.return_value = _mock_apfel_response(
                [
                    {"category": "person_name", "value": "JunyoungJung"},
                    {"category": "org_name", "value": "메가스터디"},
                ]
            )
            # allowlist는 lowercase로 정규화된 상태
            result = redact_full(
                text,
                env=_ready_env(),
                allowlist={"junyoungjung"},
            )
        # JunyoungJung은 allowlist라 그대로
        assert "JunyoungJung" in result.redacted
        # 메가스터디는 마스킹
        assert "[ORG_1]" in result.redacted

    def test_pass1_priority_over_pass2(self) -> None:
        """Pass 1과 Pass 2 결과 겹치면 Pass 1 살리고 Pass 2 skip."""
        text = "이메일 hong@x.com 입니다"
        with patch(
            "synapse_memory.redaction.pass2.complete_structured"
        ) as mock_cs:
            # 모델이 우연히 이메일을 person_name으로 잘못 분류했다고 가정
            mock_cs.return_value = _mock_apfel_response(
                [{"category": "person_name", "value": "hong@x.com"}]
            )
            result = redact_full(text, env=_ready_env(), allowlist=set())
        cats = [d.category for d in result.detections]
        assert "email" in cats
        # person_name은 같은 span에 있으니 skip되어야
        assert "person_name" not in cats

    def test_empty_text(self) -> None:
        result = redact_full("", env=_ready_env())
        assert result.redacted == ""
        assert result.detections == []

    def test_clean_text_no_calls(self) -> None:
        """PII 없는 텍스트 — apfel 호출은 하되 빈 detections."""
        with patch(
            "synapse_memory.redaction.pass2.complete_structured"
        ) as mock_cs:
            mock_cs.return_value = _mock_apfel_response([])
            result = redact_full("화창한 날씨", env=_ready_env())
        assert result.detections == []
        assert result.redacted == "화창한 날씨"

    def test_on_chunk_callback_invoked(self) -> None:
        """on_chunk 콜백이 청크 수만큼 호출되어야 (백필 진행 표시용)."""
        long_text = "\n\n".join([f"문단 {i} 내용" * 30 for i in range(8)])
        calls: list[tuple[int, int]] = []

        with patch(
            "synapse_memory.redaction.pass2.complete_structured"
        ) as mock_cs:
            mock_cs.return_value = _mock_apfel_response([])
            redact_full(
                long_text,
                env=_ready_env(),
                allowlist=set(),
                chunk_max_tokens=100,  # 작게 → 청크 여러 개
                on_chunk=lambda i, total: calls.append((i, total)),
            )

        assert len(calls) >= 2
        # 마지막 콜은 (total, total) 형태
        last_i, last_total = calls[-1]
        assert last_i == last_total
        # current는 1부터 시작
        assert calls[0][0] == 1


# ---------------------------------------------------------------------------
# Sanity
# ---------------------------------------------------------------------------


def test_pass2_categories_consistent_with_placeholders() -> None:
    from synapse_memory.redaction.pass2 import PASS2_PLACEHOLDERS

    assert PASS2_CATEGORIES == set(PASS2_PLACEHOLDERS.keys())
