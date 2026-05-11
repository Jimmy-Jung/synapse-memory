"""apfel wrapper 단위 테스트.

apfel 미설치 환경(예: CI/Linux)에서도 통과하도록 설계.
실제 apfel 호출 테스트는 별도 통합 테스트로 분리 (TODO: tests/integration/).

저자: JunyoungJung <joony300@gmail.com>
작성일: 2026-05-10
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest

from synapse_memory.llm.apfel import (
    MAX_CONTEXT_TOKENS,
    MIN_MACOS_MAJOR,
    ApfelEnvironment,
    ApfelError,
    ApfelUnavailableError,
    chunk_by_paragraph,
    complete,
    complete_json,
    complete_structured,
    detect_environment,
    estimate_tokens,
)


# ---------------------------------------------------------------------------
# 토큰 추정
# ---------------------------------------------------------------------------


class TestEstimateTokens:
    def test_empty(self) -> None:
        assert estimate_tokens("") == 0

    def test_korean_short(self) -> None:
        # "안녕하세요" 5음절 → 약 4토큰
        assert 1 <= estimate_tokens("안녕하세요") <= 6

    def test_english_short(self) -> None:
        # "Hello world" 11자 → 약 3-4토큰
        assert 1 <= estimate_tokens("Hello world") <= 5

    def test_mixed(self) -> None:
        result = estimate_tokens("Swift는 Apple의 언어")
        assert result > 0

    def test_monotonic(self) -> None:
        """긴 텍스트가 짧은 텍스트보다 토큰 많아야."""
        short = "짧은 글"
        long = "이것은 더 긴 한국어 문장입니다 그리고 더 많은 내용을 담고 있습니다"
        assert estimate_tokens(long) > estimate_tokens(short)


# ---------------------------------------------------------------------------
# 청크 분할
# ---------------------------------------------------------------------------


class TestChunkByParagraph:
    def test_empty(self) -> None:
        assert chunk_by_paragraph("") == []

    def test_whitespace_only(self) -> None:
        assert chunk_by_paragraph("   \n\n  \t\n") == []

    def test_short_text_single_chunk(self) -> None:
        text = "짧은 한 문단입니다."
        chunks = chunk_by_paragraph(text, max_tokens=100)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_multiple_paragraphs_split(self) -> None:
        # 각 문단이 ~40토큰, max_tokens=100이면 2-3 문단씩 묶임
        paragraphs = [f"문단 {i}번 내용 " * 10 for i in range(6)]
        text = "\n\n".join(paragraphs)
        chunks = chunk_by_paragraph(text, max_tokens=100)
        assert len(chunks) >= 2

    def test_long_paragraph_falls_back_to_sentences(self) -> None:
        # 한 문단이 max_tokens 초과 → 문장 단위 분할
        long_para = ("이것은 한국어 문장입니다. " * 100).strip()
        chunks = chunk_by_paragraph(long_para, max_tokens=100)
        assert len(chunks) >= 2

    def test_chunks_respect_size_loosely(self) -> None:
        """각 청크가 max_tokens의 2배를 크게 넘지 않아야 (휴리스틱이라 ±)."""
        text = "\n\n".join([f"문단 {i} " * 20 for i in range(10)])
        max_t = 100
        chunks = chunk_by_paragraph(text, max_tokens=max_t)
        for chunk in chunks:
            # 휴리스틱이라 정확하지 않지만 2배는 넘지 말아야
            assert estimate_tokens(chunk) <= max_t * 2

    def test_no_data_loss(self) -> None:
        """모든 단어가 어딘가에 들어있어야."""
        text = "문단A 한국어\n\n문단B 영어 English\n\n문단C 숫자 12345"
        chunks = chunk_by_paragraph(text, max_tokens=50)
        joined = " ".join(chunks)
        for token in ["문단A", "문단B", "문단C", "한국어", "English", "12345"]:
            assert token in joined


# ---------------------------------------------------------------------------
# 환경 진단
# ---------------------------------------------------------------------------


class TestDetectEnvironment:
    def test_returns_dataclass(self) -> None:
        env = detect_environment()
        assert isinstance(env, ApfelEnvironment)
        assert isinstance(env.is_apple_silicon, bool)
        assert isinstance(env.macos_version, str)
        assert isinstance(env.ready, bool)

    def test_no_crash_without_apfel(self) -> None:
        with patch("synapse_memory.llm.apfel.shutil.which", return_value=None):
            env = detect_environment()
            assert env.apfel_path is None
            assert env.apfel_version is None
            assert env.ready is False

    def test_ready_requires_all_conditions(self) -> None:
        # 셋 다 만족
        env = ApfelEnvironment(
            apfel_path="/opt/homebrew/bin/apfel",
            apfel_version="0.1.0",
            macos_version="26.2",
            is_apple_silicon=True,
        )
        assert env.ready is True

        # apfel 없음
        env_no_apfel = ApfelEnvironment(
            apfel_path=None,
            apfel_version=None,
            macos_version="26.2",
            is_apple_silicon=True,
        )
        assert env_no_apfel.ready is False

        # Intel Mac
        env_intel = ApfelEnvironment(
            apfel_path="/usr/local/bin/apfel",
            apfel_version="0.1.0",
            macos_version="26.2",
            is_apple_silicon=False,
        )
        assert env_intel.ready is False

        # 구버전 macOS
        env_old = ApfelEnvironment(
            apfel_path="/opt/homebrew/bin/apfel",
            apfel_version="0.1.0",
            macos_version="15.5",
            is_apple_silicon=True,
        )
        assert env_old.ready is False

    def test_macos_major_parsing(self) -> None:
        env = ApfelEnvironment(
            apfel_path=None,
            apfel_version=None,
            macos_version="26.2.1",
            is_apple_silicon=True,
        )
        assert env.macos_major == 26

        env_bad = ApfelEnvironment(
            apfel_path=None,
            apfel_version=None,
            macos_version="",
            is_apple_silicon=True,
        )
        assert env_bad.macos_major is None

    def test_reasons_unavailable_lists_all_problems(self) -> None:
        env = ApfelEnvironment(
            apfel_path=None,
            apfel_version=None,
            macos_version="14.0",
            is_apple_silicon=False,
        )
        reasons = env.reasons_unavailable()
        assert len(reasons) == 3
        assert any("apfel" in r for r in reasons)
        assert any("Apple Silicon" in r for r in reasons)
        assert any("Tahoe" in r or "macOS" in r for r in reasons)


# ---------------------------------------------------------------------------
# 호출 API (mock 기반)
# ---------------------------------------------------------------------------


def _ready_env() -> ApfelEnvironment:
    return ApfelEnvironment(
        apfel_path="/opt/homebrew/bin/apfel",
        apfel_version="0.1.0",
        macos_version="26.2",
        is_apple_silicon=True,
    )


def _mock_run(stdout: str = "", returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["apfel"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


class TestComplete:
    def test_returns_stdout(self) -> None:
        with patch("synapse_memory.llm.apfel.subprocess.run") as mock_run:
            mock_run.return_value = _mock_run(stdout="응답 텍스트\n")
            result = complete("프롬프트", env=_ready_env())
            assert result == "응답 텍스트"

    def test_quiet_flag_always_added(self) -> None:
        with patch("synapse_memory.llm.apfel.subprocess.run") as mock_run:
            mock_run.return_value = _mock_run(stdout="ok")
            complete("프롬프트", env=_ready_env())
            args = mock_run.call_args.args[0]
            assert "-q" in args

    def test_sampling_args_passed(self) -> None:
        with patch("synapse_memory.llm.apfel.subprocess.run") as mock_run:
            mock_run.return_value = _mock_run(stdout="ok")
            complete(
                "프롬프트",
                env=_ready_env(),
                temperature=0.0,
                seed=42,
                max_tokens=100,
            )
            args = mock_run.call_args.args[0]
            assert "--temperature" in args
            assert "0.0" in args
            assert "--seed" in args
            assert "42" in args
            assert "--max-tokens" in args
            assert "100" in args

    def test_system_prompt_passed(self) -> None:
        with patch("synapse_memory.llm.apfel.subprocess.run") as mock_run:
            mock_run.return_value = _mock_run(stdout="ok")
            complete("프롬프트", env=_ready_env(), system="You are a redactor.")
            args = mock_run.call_args.args[0]
            assert "--system" in args
            assert "You are a redactor." in args

    def test_raises_on_nonzero_exit(self) -> None:
        with patch("synapse_memory.llm.apfel.subprocess.run") as mock_run:
            mock_run.return_value = _mock_run(returncode=1, stderr="모델 로드 실패")
            with pytest.raises(ApfelError, match="모델 로드 실패"):
                complete("프롬프트", env=_ready_env())

    def test_raises_on_unavailable_env(self) -> None:
        env = ApfelEnvironment(None, None, "26.2", True)
        with pytest.raises(ApfelUnavailableError):
            complete("프롬프트", env=env)

    def test_timeout(self) -> None:
        with patch("synapse_memory.llm.apfel.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="apfel", timeout=1)
            with pytest.raises(ApfelError, match="타임아웃"):
                complete("프롬프트", env=_ready_env(), timeout=1)


class TestCompleteJson:
    """envelope 그대로 반환."""

    def test_returns_envelope(self) -> None:
        envelope = '{"content": "서울입니다.", "metadata": {"on_device": true}, "model": "apple-foundationmodel"}'
        with patch("synapse_memory.llm.apfel.subprocess.run") as mock_run:
            mock_run.return_value = _mock_run(stdout=envelope)
            result = complete_json("프롬프트", env=_ready_env())
            assert result["content"] == "서울입니다."
            assert result["metadata"]["on_device"] is True

    def test_raises_on_invalid_json(self) -> None:
        with patch("synapse_memory.llm.apfel.subprocess.run") as mock_run:
            mock_run.return_value = _mock_run(stdout="이건 JSON이 아님")
            with pytest.raises(ApfelError, match="envelope JSON 파싱 실패"):
                complete_json("프롬프트", env=_ready_env())

    def test_raises_on_non_dict_envelope(self) -> None:
        with patch("synapse_memory.llm.apfel.subprocess.run") as mock_run:
            mock_run.return_value = _mock_run(stdout="[1, 2, 3]")
            with pytest.raises(ApfelError, match="envelope이 dict 아님"):
                complete_json("프롬프트", env=_ready_env())


class TestCompleteStructured:
    """envelope unwrap + content를 한 번 더 JSON parse."""

    def _make_envelope(self, content: str) -> str:
        # apfel envelope을 흉내. content 안에 쌓일 JSON 문자열도 정상 escape되게
        # json.dumps로 만든다.
        return json.dumps({"content": content, "metadata": {}, "model": "x"})

    def test_unwraps_and_parses_content(self) -> None:
        envelope = self._make_envelope('{"has_pii": true, "spans": [[0, 5]]}')
        with patch("synapse_memory.llm.apfel.subprocess.run") as mock_run:
            mock_run.return_value = _mock_run(stdout=envelope)
            result = complete_structured("프롬프트", env=_ready_env())
            assert result == {"has_pii": True, "spans": [[0, 5]]}

    def test_default_temperature_is_zero(self) -> None:
        """결정성을 위해 기본 temperature=0."""
        envelope = self._make_envelope('{"x": 1}')
        with patch("synapse_memory.llm.apfel.subprocess.run") as mock_run:
            mock_run.return_value = _mock_run(stdout=envelope)
            complete_structured("프롬프트", env=_ready_env())
            args = mock_run.call_args.args[0]
            assert "--temperature" in args
            ti = args.index("--temperature")
            assert args[ti + 1] == "0.0"

    def test_raises_when_no_content_key(self) -> None:
        with patch("synapse_memory.llm.apfel.subprocess.run") as mock_run:
            mock_run.return_value = _mock_run(stdout='{"foo": "bar"}')
            with pytest.raises(ApfelError, match="content 필드 없음"):
                complete_structured("프롬프트", env=_ready_env())

    def test_raises_when_content_not_json(self) -> None:
        envelope = self._make_envelope("그냥 텍스트입니다")
        with patch("synapse_memory.llm.apfel.subprocess.run") as mock_run:
            mock_run.return_value = _mock_run(stdout=envelope)
            with pytest.raises(ApfelError, match="content가 JSON 아님"):
                complete_structured("프롬프트", env=_ready_env())

    def test_raises_when_content_not_string(self) -> None:
        bad_envelope = '{"content": 123, "metadata": {}, "model": "x"}'
        with patch("synapse_memory.llm.apfel.subprocess.run") as mock_run:
            mock_run.return_value = _mock_run(stdout=bad_envelope)
            with pytest.raises(ApfelError, match="content가 문자열 아님"):
                complete_structured("프롬프트", env=_ready_env())

    def test_strips_markdown_code_fence_with_json_label(self) -> None:
        # 모델이 ```json ... ``` 으로 감싼 경우
        envelope = self._make_envelope('```json\n{"city": "서울"}\n```')
        with patch("synapse_memory.llm.apfel.subprocess.run") as mock_run:
            mock_run.return_value = _mock_run(stdout=envelope)
            result = complete_structured("프롬프트", env=_ready_env())
            assert result == {"city": "서울"}

    def test_strips_plain_code_fence(self) -> None:
        # 라벨 없는 ``` ... ```
        envelope = self._make_envelope('```\n{"x": 1}\n```')
        with patch("synapse_memory.llm.apfel.subprocess.run") as mock_run:
            mock_run.return_value = _mock_run(stdout=envelope)
            result = complete_structured("프롬프트", env=_ready_env())
            assert result == {"x": 1}

    def test_strips_inline_fence_no_newline(self) -> None:
        envelope = self._make_envelope('```json{"y": 2}```')
        with patch("synapse_memory.llm.apfel.subprocess.run") as mock_run:
            mock_run.return_value = _mock_run(stdout=envelope)
            result = complete_structured("프롬프트", env=_ready_env())
            assert result == {"y": 2}

    def test_extracts_json_from_natural_language(self) -> None:
        # 모델이 prose에 JSON을 끼워 넣은 경우 — 첫 {..} 블록 추출
        envelope = self._make_envelope(
            '한국의 수도는 서울입니다. 다음과 같이 응답합니다: {"city": "서울"} 끝.'
        )
        with patch("synapse_memory.llm.apfel.subprocess.run") as mock_run:
            mock_run.return_value = _mock_run(stdout=envelope)
            result = complete_structured("프롬프트", env=_ready_env())
            assert result == {"city": "서울"}

    def test_extracts_array_too(self) -> None:
        envelope = self._make_envelope("앞 텍스트 [1, 2, 3] 뒤 텍스트")
        with patch("synapse_memory.llm.apfel.subprocess.run") as mock_run:
            mock_run.return_value = _mock_run(stdout=envelope)
            result = complete_structured("프롬프트", env=_ready_env())
            assert result == [1, 2, 3]

    def test_default_system_prompt_applied(self) -> None:
        envelope = self._make_envelope('{"x": 1}')
        with patch("synapse_memory.llm.apfel.subprocess.run") as mock_run:
            mock_run.return_value = _mock_run(stdout=envelope)
            complete_structured("프롬프트", env=_ready_env())
            args = mock_run.call_args.args[0]
            assert "--system" in args
            si = args.index("--system")
            # default 시스템 프롬프트의 한 부분이 들어있어야
            assert "JSON" in args[si + 1]

    def test_explicit_system_overrides_default(self) -> None:
        envelope = self._make_envelope('{"x": 1}')
        with patch("synapse_memory.llm.apfel.subprocess.run") as mock_run:
            mock_run.return_value = _mock_run(stdout=envelope)
            complete_structured(
                "프롬프트", env=_ready_env(), system="Custom system prompt"
            )
            args = mock_run.call_args.args[0]
            si = args.index("--system")
            assert args[si + 1] == "Custom system prompt"

    def test_permissive_flag_passed(self) -> None:
        envelope = self._make_envelope('{"x": 1}')
        with patch("synapse_memory.llm.apfel.subprocess.run") as mock_run:
            mock_run.return_value = _mock_run(stdout=envelope)
            complete_structured("프롬프트", env=_ready_env(), permissive=True)
            args = mock_run.call_args.args[0]
            assert "--permissive" in args

    def test_no_extractable_json_raises(self) -> None:
        envelope = self._make_envelope("그냥 자연어. JSON 없음.")
        with patch("synapse_memory.llm.apfel.subprocess.run") as mock_run:
            mock_run.return_value = _mock_run(stdout=envelope)
            with pytest.raises(ApfelError, match="JSON 아님"):
                complete_structured("프롬프트", env=_ready_env())


# ---------------------------------------------------------------------------
# 상수 sanity check
# ---------------------------------------------------------------------------


def test_constants_sane() -> None:
    assert MAX_CONTEXT_TOKENS == 4096
    assert MIN_MACOS_MAJOR == 26
