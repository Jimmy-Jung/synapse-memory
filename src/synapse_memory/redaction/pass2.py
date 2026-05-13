"""Pass 2 — apfel 기반 자유형 PII 검출.

Pass 1(regex/validator)이 못 잡는 카테고리:
    person_name / org_name / address / sensitive_topic / secret

흐름::

    text → 청크 분할 (4K 컨텍스트 안전 600 토큰)
         → 각 청크에 apfel.complete_structured 호출
         → 응답 detections를 텍스트에서 find → span 변환
         → allowlist 적용 (본인 이름/회사 제외)
         → Pass 1 detections와 머지 (Pass 1 우선, 겹치면 Pass 2 skip)
         → 통합 RedactionResult

핵심 안전장치
- 청크 단위 호출 실패는 silent (전체 백필이 한 청크 때문에 멈추지 않게)
- 모델 환각 (텍스트에 없는 value) 자동 제외
- value 길이 < 2자는 false positive로 간주
- 카테고리 화이트리스트 — 모델이 만든 카테고리 무시

저자: Synapse Memory Maintainers
작성일: 2026-05-10
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from pathlib import Path

from synapse_memory.llm.apfel import (
    ApfelEnvironment,
    ApfelError,
    chunk_by_paragraph,
    complete_structured,
    detect_environment,
)
from synapse_memory.redaction.pass1 import (
    Detection,
    RedactionResult,
    _apply_replacements,
)
from synapse_memory.redaction.pass1 import redact as run_pass1
from synapse_memory.redaction.pass2_prompts import (
    PASS2_SYSTEM,
    PASS2_USER_TEMPLATE,
)
from synapse_memory.redaction.patterns import DEFAULT_PATTERNS
from synapse_memory.redaction.redactlist import (
    build_redactlist_patterns,
    load_redactlist,
)
from synapse_memory.storage.l0 import l0_root

# Pass 2가 검출할 카테고리. 모델이 이외 카테고리 만들면 무시.
PASS2_CATEGORIES = frozenset(
    {"person_name", "org_name", "address", "sensitive_topic", "secret"}
)

PASS2_PLACEHOLDERS: dict[str, str] = {
    "person_name": "PERSON",
    "org_name": "ORG",
    "address": "ADDRESS",
    "sensitive_topic": "SENSITIVE",
    "secret": "SECRET",
}

MIN_VALUE_LEN = 2
# 600 → 1500: 호출 횟수 ~1/2.5로 줄여 백필 시간 단축.
# 4K 컨텍스트에서 입력 1500 + 시스템 프롬프트 ~500 + 응답 여유 ~500 안전.
PASS2_CHUNK_TOKENS = 1500
PASS2_DEFAULT_TIMEOUT = 30

# 메가 브랜드/도구/제품 — 이름이긴 하지만 PII로 간주 안 함 (글로벌 일반명사 수준).
# 모든 카테고리에 적용 (person_name도 포함 — "claude"가 사람 이름으로 잡히는 케이스).
MEGA_ORG_DENYLIST = frozenset(
    {
        # 빅테크
        "github", "google", "apple", "anthropic", "microsoft", "amazon",
        "meta", "facebook", "openai", "twitter", "x", "nvidia", "intel",
        "ibm", "oracle", "adobe", "slack", "notion", "discord", "zoom",
        "youtube", "instagram", "tiktok", "linkedin", "reddit",
        # 한국 빅테크/플랫폼
        "samsung", "lg", "naver", "kakao", "coupang", "nhn", "baemin",
        "toss", "tossinvest", "daum",
        # AI/도구 제품
        "claude", "gpt", "chatgpt", "gemini", "copilot", "codex",
        "cursor", "vscode", "vim", "emacs", "neovim",
        # OS/플랫폼
        "ios", "android", "macos", "linux", "windows", "unix",
        "ubuntu", "debian", "fedora",
        # 언어/런타임
        "python", "javascript", "typescript", "swift", "rust", "go", "java",
        "node", "deno", "bun",
        # 브라우저
        "firefox", "chrome", "safari", "edge", "brave",
    }
)

# Chat/메시지/시스템에서 흔한 role label·일반명사 — PII 아님.
NON_PII_TERMS = frozenset(
    {
        # role labels
        "user", "users", "assistant", "system", "human", "ai", "model",
        "admin", "administrator", "root", "guest", "anonymous", "owner",
        # generic person words
        "person", "people", "member", "team", "developer", "engineer",
        # 데이터 필드 이름
        "name", "value", "key", "data", "id", "type", "category",
        "token", "password", "secret", "auth", "credential", "rrn",
        # ALL_CAPS markers (코드 주석/플래그)
        "important", "warning", "error", "todo", "fixme", "note",
        "critical", "deprecated", "experimental", "wip",
        # commit/diff 키워드
        "feat", "fix", "chore", "docs", "refactor", "test", "perf",
    }
)

KOREAN_LOCATION_TERMS = frozenset(
    {
        "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
        "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남",
        "제주", "서울시", "부산시", "대구시", "인천시", "광주시", "대전시",
        "울산시", "세종시", "서울특별시", "부산광역시", "대구광역시",
        "인천광역시", "광주광역시", "대전광역시", "울산광역시",
    }
)

KOREAN_ORG_WATCHLIST = frozenset(
    {
        "샘플회사", "당근마켓", "토스", "카카오뱅크", "무신사", "야놀자",
        "컬리", "마켓컬리", "우아한형제들", "라인", "쿠팡", "토스뱅크",
        "비바리퍼블리카", "직방",
    }
)

ADDRESS_GENERIC_SUFFIXES = ("빌딩", "타워", "건물", "아파트")


def _is_role_label_phrase(val: str) -> bool:
    """``User Assistant System`` 같은 role label 묶음 — PII 아님."""
    words = val.split()
    return bool(words) and all(w.lower() in NON_PII_TERMS for w in words)


def _is_lowercase_ascii_handle(val: str) -> bool:
    """소문자 ASCII 단어는 사람 이름보다 handle/identifier일 가능성이 높다."""
    return val.islower() and val.isalpha() and val.isascii() and " " not in val


def _normalize_pass2_value(category: str, value: str) -> str:
    """모델 value를 eval/치환 가능한 정확 원문 단위로 보정."""
    if category != "address":
        return value

    normalized = value.strip()
    for suffix in ADDRESS_GENERIC_SUFFIXES:
        marker = f" {suffix}"
        if normalized.endswith(marker):
            return normalized[: -len(marker)].rstrip()
    return normalized


def _find_watchlist_orgs(text: str) -> list[tuple[str, str]]:
    """Apple 모델이 놓치기 쉬운 한국 회사명을 deterministic 보조 탐지."""
    return [
        ("org_name", org)
        for org in sorted(KOREAN_ORG_WATCHLIST, key=len, reverse=True)
        if org in text
    ]


def _looks_like_filename(val: str) -> bool:
    """``foo.md``, ``bar.py`` 등 ``name.ext`` 패턴 — PII 아님."""
    if "." not in val:
        return False
    name, _, ext = val.rpartition(".")
    if not name or not ext:
        return False
    # 일반 확장자 길이 (1-5자, 영숫자만)
    return 1 <= len(ext) <= 5 and ext.isalnum()


def _looks_like_screaming_snake(val: str) -> bool:
    """``EXTREMELY_IMPORTANT`` 같은 코드 상수 — PII 아님."""
    return val.isupper() and "_" in val


_UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _looks_like_uuid_or_hash(val: str) -> bool:
    """UUID 또는 32+ hex digit hash (md5/sha) — person/org PII 아님.

    Apple 모델이 ``678b1c44-aa20-...``를 person_name으로 분류하는 false positive 컷.
    secret 카테고리에선 진짜 토큰일 수 있어 별도 처리.
    """
    if _UUID_PATTERN.match(val):
        return True
    return len(val) >= 32 and all(c in "0123456789abcdefABCDEF" for c in val)


def _looks_like_path_or_identifier(val: str) -> bool:
    """경로/URL/CLI 옵션/identifier 패턴 — PII 카테고리에서 제외.

    Apple 모델이 자주 만드는 false positive 패턴:
        - ``/Users/sampleuser/...``의 ``sampleuser``를 person_name
        - ``ai-symbiote@ai-symbiote``를 org_name
        - ``sample-handle``(GitHub handle)을 person_name
        - ``jarrodwatts``/``garrytan``(소문자 핸들)을 person_name
        - ``SessionStart:startup``(hook 이벤트)을 org_name
    """
    if not val:
        return True
    if any(c in val for c in "/\\:"):
        return True
    if "://" in val or "@" in val:
        return True
    if val.startswith("-"):
        return True
    # snake_case (소문자 + underscore)
    if val.islower() and "_" in val:
        return True
    # kebab-case 소문자 (예: "ai-symbiote")
    if val.islower() and "-" in val:
        return True
    # dash + ASCII만 — GitHub handle 패턴 (예: "sample-handle", "Foo-Bar").
    # 진짜 hyphenated 영어 이름(Anne-Marie)도 cut되지만 한국어 위주 데이터에서
    # GitHub handle 흔도가 훨씬 높아 트레이드오프 수용.
    if "-" in val and val.isascii() and any(c.isalpha() for c in val):
        return True
    # 소문자 ASCII 단일 영어 단어 (예: "sampleuser", "jarrodwatts", "garrytan").
    return _is_lowercase_ascii_handle(val)


def _allowlist_path() -> Path:
    """기본 allowlist 위치 — 매번 호출 시 평가 (env override 추적)."""
    return l0_root() / ".allowlist"


def load_allowlist(path: Path | None = None) -> set[str]:
    """allowlist 파일 로드. 한 줄 = 한 항목, ``#`` 주석 / 빈 줄 무시.

    **case-insensitive 비교를 위해 모두 lowercase로 정규화한다.**
    매칭 시 후보값도 ``.lower()``로 비교 (``SampleUser``/``sampleuser``/``SAMPLEUSER`` 동일 처리).

    파일 없으면 빈 set 반환 (예외 안 던짐).
    """
    p = (path or _allowlist_path()).expanduser()
    if not p.exists():
        return set()
    items: set[str] = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        items.add(s.lower())
    return items


def _normalize_model_response(result: object) -> list[dict[str, object]]:
    """모델이 schema를 어겼을 때 가능한 형식들을 정규화.

    수용 가능한 형식 (apfel + Apple 소형 모델 관찰 기준):
        1. ``{"detections": [{"category", "value"}, ...]}``  — 표준
        2. ``[{"category", "value"}, ...]``                    — list 직접
        3. ``{"category": "...", "value": "..."}``             — 단일 dict
        4. 그 외                                               — 빈 리스트
    """
    if isinstance(result, list):
        return [d for d in result if isinstance(d, dict)]
    if isinstance(result, dict):
        if "detections" in result and isinstance(result["detections"], list):
            return [d for d in result["detections"] if isinstance(d, dict)]
        # 단일 detection dict
        if isinstance(result.get("category"), str) and isinstance(
            result.get("value"), str
        ):
            return [result]
    return []


def _detect_in_chunk(
    chunk: str,
    *,
    env: ApfelEnvironment,
    timeout: int = PASS2_DEFAULT_TIMEOUT,
    permissive: bool = True,
) -> list[tuple[str, str]]:
    """단일 청크 PII 검출 → ``[(category, value), ...]``.

    apfel 호출 실패는 silent — 빈 리스트 반환 (백필 진행 보호).
    모델 응답 schema 변형은 ``_normalize_model_response``로 흡수.
    """
    prompt = PASS2_USER_TEMPLATE.format(text=chunk)
    try:
        result = complete_structured(
            prompt,
            system=PASS2_SYSTEM,
            permissive=permissive,
            timeout=timeout,
            env=env,
        )
    except ApfelError:
        return []

    detections = _normalize_model_response(result)
    if not detections:
        return []

    out: list[tuple[str, str]] = []
    for d in detections:
        cat = d.get("category")
        val = d.get("value")
        if not isinstance(cat, str) or not isinstance(val, str):
            continue
        if cat not in PASS2_CATEGORIES:
            continue
        cleaned = val.strip()
        if len(cleaned) < MIN_VALUE_LEN:
            continue
        out.append((cat, cleaned))
    return out


def _find_spans(text: str, value: str) -> list[tuple[int, int]]:
    """텍스트에서 value의 모든 정확 일치 위치."""
    if not value:
        return []
    spans: list[tuple[int, int]] = []
    start = 0
    while True:
        pos = text.find(value, start)
        if pos < 0:
            break
        spans.append((pos, pos + len(value)))
        start = pos + 1
    return spans


def _build_pass2_detections(
    full_text: str,
    pass2_findings: Iterable[tuple[str, str]],
    occupied_spans: list[tuple[int, int]],
    allowlist: set[str],
) -> list[Detection]:
    """모델 응답을 Detection 객체로 변환.

    - allowlist 일치 (정확 일치) → skip
    - 텍스트에서 못 찾으면 (모델 환각) → skip
    - 점유된 span(Pass 1 또는 이전 Pass 2)과 겹치면 → skip
    - 같은 (category, value)는 stable index
    """
    counters: dict[str, dict[str, int]] = {}
    detections: list[Detection] = []
    seen: set[tuple[str, str]] = set()

    for cat, val in pass2_findings:
        if (cat, val) in seen:
            continue
        seen.add((cat, val))

        val = _normalize_pass2_value(cat, val)
        if len(val) < MIN_VALUE_LEN:
            continue

        # allowlist는 lowercase로 정규화되어 있음
        if val.lower() in allowlist:
            continue

        # 메가 브랜드/도구/제품 — 모든 카테고리에서 제외
        if val.lower() in MEGA_ORG_DENYLIST:
            continue

        # 일반 명사/role label — 모든 카테고리에서 제외
        if val.lower() in NON_PII_TERMS:
            continue

        # role label 묶음 — "User Assistant System" 등
        if _is_role_label_phrase(val):
            continue

        # 단순 도시/광역시명 — person/address false positive 컷
        if val in KOREAN_LOCATION_TERMS:
            continue

        # 파일명 패턴 (foo.md, bar.py)
        if _looks_like_filename(val):
            continue

        # SCREAMING_SNAKE 코드 상수
        if _looks_like_screaming_snake(val):
            continue

        # UUID/hash — secret 외 모든 카테고리에서 reject (token 가능성 보존)
        if cat != "secret" and _looks_like_uuid_or_hash(val):
            continue

        # path/URL/identifier는 person/org/address에서 제외
        # (모델이 path를 address로 자주 분류)
        if cat in (
            "person_name",
            "org_name",
            "address",
        ) and _looks_like_path_or_identifier(val):
            continue

        # person_name에서 소문자 ASCII 단어는 GitHub handle/identifier로 처리.
        if cat == "person_name" and _is_lowercase_ascii_handle(val):
            continue

        # 사람 이름에는 숫자가 들어가지 않는다 — 대소문자+숫자 혼합 토큰
        # (예: ``xoAP7Qtf`` 같은 short random ID) 차단.
        if cat == "person_name" and any(c.isdigit() for c in val):
            continue

        # 순수 숫자 13자+ 는 secret으로 보기 부적절 (RRN 후보지만 Pass 1
        # validator 통과 못한 random digit). secret 카테고리에서만 추가 검증.
        if cat == "secret" and val.isdigit() and len(val) >= 13:
            continue

        spans = _find_spans(full_text, val)
        if not spans:
            continue

        per_cat = counters.setdefault(cat, {})
        if val not in per_cat:
            per_cat[val] = len(per_cat) + 1
        idx = per_cat[val]
        placeholder = f"[{PASS2_PLACEHOLDERS[cat]}_{idx}]"

        for s, e in spans:
            if any(os < e and oe > s for os, oe in occupied_spans):
                continue
            occupied_spans.append((s, e))
            detections.append(
                Detection(
                    category=cat,
                    span=(s, e),
                    matched=val,
                    placeholder=placeholder,
                )
            )

    return detections


def redact_full(
    text: str,
    *,
    env: ApfelEnvironment | None = None,
    allowlist: set[str] | None = None,
    redactlist: list[str] | None = None,
    chunk_max_tokens: int = PASS2_CHUNK_TOKENS,
    timeout: int = PASS2_DEFAULT_TIMEOUT,
    permissive: bool = True,
    on_chunk: Callable[[int, int], None] | None = None,
) -> RedactionResult:
    """Pass 1 + Pass 2 통합 redaction.

    Args:
        text: 검사 대상 (전체 텍스트).
        env: apfel 환경 (사전 진단 결과 재사용 권장 — 백필처럼 다회 호출 시).
        allowlist: 본인 정보 등 화이트리스트. None이면 기본 파일 로드.
        redactlist: NDA 회사/프로젝트 강제 마스크 리스트. None이면 기본 파일 로드.
            Pass 1 패턴에 동적 합류 (priority=200, 모든 카테고리 우선).
        chunk_max_tokens: Pass 2 호출당 청크 토큰 상한.
        timeout: 청크당 apfel 타임아웃.
        permissive: Apple guardrail 완화 (한국어/특정 주제 거부 회피).
        on_chunk: ``(current_index, total)`` 콜백. 청크 처리 직전 호출. 백필
            진행 표시용. None이면 호출 안 함.

    Returns:
        통합 RedactionResult — Pass 1 + Pass 2 detections 위치 오름차순.
    """
    if not text:
        return RedactionResult(redacted=text)

    # Pass 1 패턴 = 기본 + 사용자 redact-list (동적)
    effective_redactlist = (
        redactlist if redactlist is not None else load_redactlist()
    )
    if effective_redactlist:
        pass1_patterns = list(DEFAULT_PATTERNS) + build_redactlist_patterns(
            effective_redactlist
        )
    else:
        pass1_patterns = list(DEFAULT_PATTERNS)

    pass1_result = run_pass1(text, patterns=pass1_patterns)
    occupied: list[tuple[int, int]] = [d.span for d in pass1_result.detections]

    env = env or detect_environment()
    if not env.ready:
        # apfel 사용 불가 — Pass 1만 반환
        return pass1_result

    effective_allowlist = allowlist if allowlist is not None else load_allowlist()

    chunks = [c for c in chunk_by_paragraph(text, max_tokens=chunk_max_tokens) if c.strip()]
    total = len(chunks)

    pass2_findings: list[tuple[str, str]] = []
    for i, chunk in enumerate(chunks, 1):
        if on_chunk is not None:
            on_chunk(i, total)
        pass2_findings.extend(
            _detect_in_chunk(
                chunk, env=env, timeout=timeout, permissive=permissive
            )
        )
        pass2_findings.extend(_find_watchlist_orgs(chunk))

    pass2_detections = _build_pass2_detections(
        text, pass2_findings, occupied, effective_allowlist
    )

    all_detections = pass1_result.detections + pass2_detections
    all_detections.sort(key=lambda d: d.span[0])

    redacted = _apply_replacements(text, all_detections)
    return RedactionResult(redacted=redacted, detections=all_detections)
