"""apfel CLI wrapper — Apple FoundationModels access via subprocess.

apfel docs: https://apfel.franzai.com
GitHub:     https://github.com/Arthur-Ficial/apfel

설계 원칙
---------
- 모든 호출은 timeout 강제 (영원히 매달리는 호출 금지).
- 비정상 종료 코드는 ApfelError로 변환 (stderr 메시지 보존).
- 환경 미충족(apfel 미설치, macOS<26, Intel Mac)은 ApfelUnavailableError.
- 외부 의존성 0. subprocess만 사용.
- 모든 호출에 ``-q``(quiet) 자동 적용 — progress bar/색상 제거.

apfel JSON envelope
-------------------
``-o json`` 사용 시 apfel은 다음 envelope을 반환::

    {"content": "<모델 응답 텍스트>", "metadata": {...}, "model": "..."}

- ``complete_json`` → envelope dict 그대로 반환 (메타데이터 보존이 필요할 때)
- ``complete_structured`` → envelope.content를 한 번 더 JSON parse (모델한테
  구조화 출력 요청한 경우)

검증 환경
---------
apfel v1.3.3 (2026-05-10) 기준. 옵션 변경 시 본 파일과 ``tests/test_apfel.py`` 동기화.

저자: Synapse Memory Maintainers
작성일: 2026-05-10
"""

from __future__ import annotations

import json
import platform
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any

from synapse_memory.cost.events import append_cost_event, build_cost_event
from synapse_memory.cost.pricing import price_usage

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------

APFEL_BIN = "apfel"
DEFAULT_TIMEOUT_SEC = 30
MIN_MACOS_MAJOR = 26  # Tahoe — FoundationModels 프레임워크 도입 버전
MAX_CONTEXT_TOKENS = 4096
SAFE_INPUT_TOKENS = 2400  # 응답 여유분 ~1500 토큰 확보

# 토큰 추정 휴리스틱 (실측 후 calibrate 가능)
KOREAN_CHARS_PER_TOKEN = 1.5
LATIN_CHARS_PER_TOKEN = 4.0

# 한글 음절 범위
_HANGUL_SYLLABLE_RANGE = ("가", "힣")

# 문장 분리 패턴 (한국어/영어/중국어/일본어 종결문자 + 공백)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。!?])\s+")

# 모델이 JSON을 마크다운 코드블록으로 감싸는 경우 처리
_CODE_FENCE_RE = re.compile(
    r"^\s*```(?:json|JSON)?\s*\n?(?P<body>.*?)\n?\s*```\s*$",
    re.DOTALL,
)

# complete_structured 기본 시스템 프롬프트.
# 소형 Apple 모델이 자유형 텍스트로 응답하는 것을 막기 위한 가드.
DEFAULT_STRUCTURED_SYSTEM = (
    "You output ONLY a single valid JSON value. "
    "No prose, no markdown code fences, no explanation. "
    "If you cannot answer, return {\"error\": \"<reason>\"} as JSON. "
    "Korean text inside JSON string values is allowed."
)


# ---------------------------------------------------------------------------
# 예외
# ---------------------------------------------------------------------------


class ApfelError(RuntimeError):
    """apfel 호출 일반 실패."""


class ApfelUnavailableError(ApfelError):
    """apfel 미설치 또는 시스템 사양 미달."""


# ---------------------------------------------------------------------------
# 환경 진단
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ApfelEnvironment:
    """apfel 사용 가능 여부를 표현하는 진단 결과."""

    apfel_path: str | None
    apfel_version: str | None
    macos_version: str
    is_apple_silicon: bool

    @property
    def macos_major(self) -> int | None:
        """macOS major 버전. 파싱 실패 시 None."""
        try:
            return int(self.macos_version.split(".")[0])
        except (ValueError, IndexError):
            return None

    @property
    def ready(self) -> bool:
        """모든 조건이 충족되어 호출 가능한 상태인지."""
        if self.apfel_path is None:
            return False
        if not self.is_apple_silicon:
            return False
        major = self.macos_major
        return major is not None and major >= MIN_MACOS_MAJOR

    def reasons_unavailable(self) -> list[str]:
        """미충족 사유 목록 (사람용 메시지)."""
        reasons: list[str] = []
        if self.apfel_path is None:
            reasons.append(
                "apfel CLI 미설치 — `brew install Arthur-Ficial/tap/apfel`"
            )
        if not self.is_apple_silicon:
            reasons.append("Apple Silicon 필요 (Intel Mac 미지원)")
        major = self.macos_major
        if major is None:
            reasons.append(f"macOS 버전 확인 실패: {self.macos_version!r}")
        elif major < MIN_MACOS_MAJOR:
            reasons.append(
                f"macOS Tahoe(26)+ 필요 — 현재 {self.macos_version}"
            )
        return reasons


def detect_environment() -> ApfelEnvironment:
    """현재 시스템에서 apfel 사용 가능 여부 진단.

    부작용 없음. 실패 시에도 예외 없이 ApfelEnvironment 반환.
    """
    apfel_path = shutil.which(APFEL_BIN)

    apfel_version: str | None = None
    if apfel_path is not None:
        try:
            result = subprocess.run(
                [apfel_path, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode == 0:
                apfel_version = result.stdout.strip() or result.stderr.strip() or None
        except (subprocess.TimeoutExpired, OSError):
            apfel_version = None

    macos_version = platform.mac_ver()[0] or ""
    is_apple_silicon = platform.machine() == "arm64" and platform.system() == "Darwin"

    return ApfelEnvironment(
        apfel_path=apfel_path,
        apfel_version=apfel_version,
        macos_version=macos_version,
        is_apple_silicon=is_apple_silicon,
    )


def _ensure_ready(env: ApfelEnvironment) -> None:
    """ready 아니면 ApfelUnavailableError 발생."""
    if env.ready:
        return
    raise ApfelUnavailableError(" / ".join(env.reasons_unavailable()))


# ---------------------------------------------------------------------------
# 호출 API
# ---------------------------------------------------------------------------


def _build_sampling_args(
    *,
    temperature: float | None,
    seed: int | None,
    max_tokens: int | None,
    permissive: bool = False,
) -> list[str]:
    """apfel sampling/guardrail 옵션 → CLI 인자 리스트."""
    args: list[str] = []
    if temperature is not None:
        args.extend(["--temperature", str(temperature)])
    if seed is not None:
        args.extend(["--seed", str(seed)])
    if max_tokens is not None:
        args.extend(["--max-tokens", str(max_tokens)])
    if permissive:
        args.append("--permissive")
    return args


def _run_apfel(
    args: list[str],
    *,
    stdin_text: str | None = None,
    timeout: int = DEFAULT_TIMEOUT_SEC,
) -> str:
    """공통 subprocess 실행. 호출 측에서 ready 체크 선행 필요."""
    started = time.monotonic()
    prompt_text = _prompt_from_args(args)
    input_text = f"{prompt_text}\n{stdin_text or ''}".strip()
    try:
        result = subprocess.run(
            args,
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - started
        _record_apfel_cost(
            args=args,
            input_text=input_text,
            output_text="",
            status="timeout",
            elapsed_s=elapsed,
            error_kind="timeout",
        )
        raise ApfelError(f"apfel 호출 타임아웃 ({timeout}s)") from exc
    except OSError as exc:
        elapsed = time.monotonic() - started
        _record_apfel_cost(
            args=args,
            input_text=input_text,
            output_text="",
            status="error",
            elapsed_s=elapsed,
            error_kind="os_error",
        )
        raise ApfelError(f"apfel 실행 실패: {exc}") from exc
    elapsed = time.monotonic() - started

    if result.returncode != 0:
        _record_apfel_cost(
            args=args,
            input_text=input_text,
            output_text="",
            status="error",
            elapsed_s=elapsed,
            error_kind="nonzero_exit",
        )
        stderr = result.stderr.strip() or "(no stderr)"
        raise ApfelError(
            f"apfel 비정상 종료 exit={result.returncode}: {stderr}"
        )

    _record_apfel_cost(
        args=args,
        input_text=input_text,
        output_text=result.stdout,
        status="success",
        elapsed_s=elapsed,
    )
    return result.stdout.rstrip("\n")


def _record_apfel_cost(
    *,
    args: list[str],
    input_text: str,
    output_text: str,
    status: str,
    elapsed_s: float,
    error_kind: str | None = None,
) -> None:
    model = _model_from_apfel_args(args)
    input_tokens = estimate_tokens(input_text)
    output_tokens = estimate_tokens(output_text)
    priced = price_usage(
        provider="apfel",
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    try:
        append_cost_event(
            build_cost_event(
                provider="apfel",
                model=model,
                status=status,  # type: ignore[arg-type]
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                usd=priced.usd,
                pricing_source=priced.pricing_source,
                elapsed_s=elapsed_s,
                error_kind=error_kind,
            )
        )
    except Exception as exc:
        print(f"⚠ cost event 기록 실패: {exc}", file=sys.stderr)


def _prompt_from_args(args: list[str]) -> str:
    if not args:
        return ""
    return args[-1]


def _model_from_apfel_args(_args: list[str]) -> str:
    return "apple-foundationmodel"


def complete(
    prompt: str,
    *,
    system: str | None = None,
    temperature: float | None = None,
    seed: int | None = None,
    max_tokens: int | None = None,
    permissive: bool = False,
    timeout: int = DEFAULT_TIMEOUT_SEC,
    env: ApfelEnvironment | None = None,
) -> str:
    """단일 턴 텍스트 응답.

    Args:
        prompt: 사용자 프롬프트.
        system: 시스템 프롬프트 (옵션).
        temperature: 0.0=결정적, 1.0=다양. PII 검출 등 결정성 필요 시 0.
        seed: 재현 가능 출력. temperature와 함께 사용 권장.
        max_tokens: 응답 토큰 상한. 4K 컨텍스트에서 입력 여유 확보용.
        timeout: 초 단위 타임아웃.
        env: 사전 진단 결과 재사용 (옵션, 없으면 매 호출마다 진단).

    Returns:
        모델 응답 텍스트.
    """
    env = env or detect_environment()
    _ensure_ready(env)
    assert env.apfel_path is not None

    cmd: list[str] = [env.apfel_path, "-q"]
    if system:
        cmd.extend(["--system", system])
    cmd.extend(_build_sampling_args(
        temperature=temperature, seed=seed, max_tokens=max_tokens,
        permissive=permissive,
    ))
    cmd.append(prompt)

    return _run_apfel(cmd, timeout=timeout)


def complete_json(
    prompt: str,
    *,
    system: str | None = None,
    temperature: float | None = None,
    seed: int | None = None,
    max_tokens: int | None = None,
    permissive: bool = False,
    timeout: int = DEFAULT_TIMEOUT_SEC,
    env: ApfelEnvironment | None = None,
) -> dict[str, Any]:
    """apfel ``-o json`` 모드. envelope 그대로 반환.

    반환 형식 (apfel v1.3.3)::

        {"content": "<모델 응답>", "metadata": {...}, "model": "..."}

    모델한테 구조화 출력 요청한 경우 ``complete_structured`` 사용 권장.

    Raises:
        ApfelError: apfel 호출 실패 또는 envelope JSON 파싱 실패.
    """
    env = env or detect_environment()
    _ensure_ready(env)
    assert env.apfel_path is not None

    cmd: list[str] = [env.apfel_path, "-q", "-o", "json"]
    if system:
        cmd.extend(["--system", system])
    cmd.extend(_build_sampling_args(
        temperature=temperature, seed=seed, max_tokens=max_tokens,
        permissive=permissive,
    ))
    cmd.append(prompt)

    raw = _run_apfel(cmd, timeout=timeout)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ApfelError(f"envelope JSON 파싱 실패: {raw[:200]!r}") from exc
    if not isinstance(parsed, dict):
        raise ApfelError(f"envelope이 dict 아님: {type(parsed).__name__}")
    return parsed


def complete_structured(
    prompt: str,
    *,
    system: str | None = None,
    temperature: float | None = 0.0,
    seed: int | None = None,
    max_tokens: int | None = None,
    permissive: bool = False,
    timeout: int = DEFAULT_TIMEOUT_SEC,
    env: ApfelEnvironment | None = None,
) -> Any:
    """모델한테 JSON 응답 요청 → envelope unwrap → content를 JSON으로 강제 파싱.

    소형 Apple 모델이 자연어/마크다운으로 새지 않게 다중 가드:
        1. ``system`` 미지정 시 ``DEFAULT_STRUCTURED_SYSTEM`` 자동 적용
        2. ```` ``` ```` 코드 펜스 자동 제거
        3. content가 직접 JSON 아니면 첫 ``{...}`` 블록 추출 시도
        4. ``permissive=True``로 guardrail 완화 가능

    Args:
        prompt: JSON 형식 명시 권장 ("JSON 한 줄로: {key: ...}").
        system: 커스텀 시스템 프롬프트. None이면 default 사용.
        permissive: Apple 모델이 한국어/특정 주제에 거부할 때.

    Returns:
        모델이 반환한 JSON 객체 (보통 dict).

    Raises:
        ApfelError: envelope 형식 어긋남, JSON 추출도 실패.
    """
    effective_system = system if system is not None else DEFAULT_STRUCTURED_SYSTEM

    envelope = complete_json(
        prompt,
        system=effective_system,
        temperature=temperature,
        seed=seed,
        max_tokens=max_tokens,
        permissive=permissive,
        timeout=timeout,
        env=env,
    )
    if "content" not in envelope:
        raise ApfelError(f"envelope에 content 필드 없음: {list(envelope.keys())}")
    content = envelope["content"]
    if not isinstance(content, str):
        raise ApfelError(f"envelope.content가 문자열 아님: {type(content).__name__}")

    return _parse_json_with_fallback(content)


def _strip_code_fence(text: str) -> str:
    """``` ... ``` 또는 ```json ... ``` 코드블록을 벗기고 안쪽만 반환."""
    m = _CODE_FENCE_RE.match(text.strip())
    if m:
        return m.group("body").strip()
    return text.strip()


def _extract_first_json_value(text: str) -> str | None:
    """텍스트에서 첫 번째 균형 잡힌 ``{...}`` 또는 ``[...]`` 블록 추출.

    문자열 안의 brace는 무시 (간단한 state machine). escape는 \\\\ 인식.
    """
    in_string = False
    escape = False
    depth = 0
    start = -1
    open_char = ""
    close_char = ""

    for i, c in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_string = False
            continue
        if c == '"':
            in_string = True
            continue
        if depth == 0 and c in "{[":
            open_char = c
            close_char = "}" if c == "{" else "]"
            start = i
            depth = 1
        elif depth > 0:
            if c == open_char:
                depth += 1
            elif c == close_char:
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
    return None


def _parse_json_with_fallback(content: str) -> Any:
    """content 텍스트에서 JSON 추출 — 다단계 fallback.

    순서:
        1. 그대로 json.loads
        2. code fence 제거 후 json.loads
        3. 첫 ``{...}`` 또는 ``[...]`` 블록 추출 후 json.loads
        4. 다 실패 → ApfelError
    """
    candidates: list[str] = []
    candidates.append(content)
    stripped = _strip_code_fence(content)
    if stripped != content:
        candidates.append(stripped)
    extracted = _extract_first_json_value(stripped)
    if extracted is not None and extracted not in candidates:
        candidates.append(extracted)

    last_err: Exception | None = None
    for cand in candidates:
        try:
            return json.loads(cand)
        except json.JSONDecodeError as exc:
            last_err = exc
            continue

    raise ApfelError(
        f"envelope.content가 JSON 아님: {content[:200]!r}"
    ) from last_err


def complete_with_input(
    prompt: str,
    *,
    stdin_text: str,
    json_output: bool = False,
    system: str | None = None,
    temperature: float | None = None,
    seed: int | None = None,
    max_tokens: int | None = None,
    permissive: bool = False,
    timeout: int = DEFAULT_TIMEOUT_SEC,
    env: ApfelEnvironment | None = None,
) -> Any:
    """긴 텍스트는 stdin으로, 명령어는 인자로 전달.

    파이프 친화: ``cat note.md | apfel "이 텍스트 분류해" -o json``.

    Returns:
        json_output=True면 envelope dict, 아니면 plain 텍스트.
    """
    env = env or detect_environment()
    _ensure_ready(env)
    assert env.apfel_path is not None

    cmd: list[str] = [env.apfel_path, "-q"]
    if json_output:
        cmd.extend(["-o", "json"])
    if system:
        cmd.extend(["--system", system])
    cmd.extend(_build_sampling_args(
        temperature=temperature, seed=seed, max_tokens=max_tokens,
        permissive=permissive,
    ))
    cmd.append(prompt)

    raw = _run_apfel(cmd, stdin_text=stdin_text, timeout=timeout)
    if not json_output:
        return raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ApfelError(f"envelope JSON 파싱 실패: {raw[:200]!r}") from exc


# ---------------------------------------------------------------------------
# 토큰 추정 + 청크 분할
# ---------------------------------------------------------------------------


def _is_korean(char: str) -> bool:
    """한글 음절 여부 (자모 제외)."""
    return _HANGUL_SYLLABLE_RANGE[0] <= char <= _HANGUL_SYLLABLE_RANGE[1]


def estimate_tokens(text: str) -> int:
    """토큰 수 휴리스틱 추정.

    한국어: 1.5 char/token, 라틴/숫자: 4 char/token. 정확도 ±20%.
    apfel CLI가 정확한 카운트를 노출하면 그쪽으로 교체 권장.
    """
    if not text:
        return 0
    korean_chars = sum(1 for c in text if _is_korean(c))
    other_chars = len(text) - korean_chars
    estimated = korean_chars / KOREAN_CHARS_PER_TOKEN + other_chars / LATIN_CHARS_PER_TOKEN
    return max(1, int(estimated) + 1)


def chunk_by_paragraph(text: str, max_tokens: int = 600) -> list[str]:
    """문단 경계 기준 청크 분할.

    한 문단이 max_tokens 초과 시 문장 단위로 폴백 분할.
    각 청크는 (대략) max_tokens 이하를 보장 — 휴리스틱 추정이라 정확하지 않음.

    Args:
        text: 분할 대상 텍스트.
        max_tokens: 청크당 최대 토큰 수 (기본 600, 4K 컨텍스트의 ~15%).

    Returns:
        청크 문자열 리스트. 빈 입력 → [].
    """
    if not text or not text.strip():
        return []

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    buffer: list[str] = []
    buffer_tokens = 0

    def flush() -> None:
        nonlocal buffer, buffer_tokens
        if buffer:
            chunks.append("\n\n".join(buffer))
            buffer = []
            buffer_tokens = 0

    for para in paragraphs:
        para_tokens = estimate_tokens(para)

        if para_tokens > max_tokens:
            # 한 문단이 한도 초과 → 문장 단위로 폴백
            flush()
            chunks.extend(_split_long_paragraph(para, max_tokens))
        elif buffer_tokens + para_tokens > max_tokens:
            # 누적이 한도 초과 → flush 후 새 버퍼
            flush()
            buffer = [para]
            buffer_tokens = para_tokens
        else:
            buffer.append(para)
            buffer_tokens += para_tokens

    flush()
    return chunks


def _split_long_paragraph(para: str, max_tokens: int) -> list[str]:
    """문장 단위 폴백 분할. 한 문장이 또 한도 초과면 강제 길이 분할."""
    sentences = _SENTENCE_SPLIT_RE.split(para)
    chunks: list[str] = []
    buffer: list[str] = []
    buffer_tokens = 0

    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        sent_tokens = estimate_tokens(sent)

        if sent_tokens > max_tokens:
            # 문장조차 너무 김 → 문자 길이 기반 강제 분할
            if buffer:
                chunks.append(" ".join(buffer))
                buffer = []
                buffer_tokens = 0
            chunks.extend(_force_split(sent, max_tokens))
        elif buffer_tokens + sent_tokens > max_tokens:
            chunks.append(" ".join(buffer))
            buffer = [sent]
            buffer_tokens = sent_tokens
        else:
            buffer.append(sent)
            buffer_tokens += sent_tokens

    if buffer:
        chunks.append(" ".join(buffer))
    return chunks


def _force_split(text: str, max_tokens: int) -> list[str]:
    """문장조차 너무 길 때 강제 길이 분할 (문자 단위, 한국어 가정)."""
    chunk_chars = int(max_tokens * KOREAN_CHARS_PER_TOKEN)
    return [text[i : i + chunk_chars] for i in range(0, len(text), chunk_chars)]
