"""profile/dedupe.py 테스트.

핵심 시나리오
- Profile.md 카테고리 bullet 파싱
- DecisionPatterns.md Approved Patterns 섹션 ### trigger 파싱
- 정확 매치 dedupe
- 토큰 Jaccard 유사도 dedupe (어순/조사 변형)
- 정규화 (대소문자, 공백, 마침표)
- 빈 vault → 입력 그대로 통과
- 배치 내 중복 제거
- daily.py _build_update_profile_action 이 빈 결과 시 save 호출 skip

저자: Synapse Memory Maintainers
작성일: 2026-05-18
"""

from __future__ import annotations

from pathlib import Path

import pytest

from synapse_memory.profile.dedupe import (
    DedupeReport,
    _is_duplicate,
    _jaccard,
    _normalize,
    _token_set,
    dedupe_against_vault,
    parse_decision_pattern_triggers,
    parse_profile_facts,
)
from synapse_memory.profile.schema import DecisionPattern, ProfileFact

# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def profile_md(tmp_path: Path) -> Path:
    path = tmp_path / "Profile.md"
    path.write_text(
        "---\n"
        "title: AI Profile\n"
        "date: 2026-05-18\n"
        "---\n"
        "\n"
        "# AI Profile\n"
        "\n"
        "## Tech / Domain\n"
        "\n"
        "- iOS 개발 주력. SwiftUI는 학습 중입니다.\n"
        "- Obsidian + synapse-memory 를 지식관리 인프라로 사용합니다.\n"
        "\n"
        "## Stable Preferences\n"
        "\n"
        "- 기본 응답 언어는 한국어입니다.\n"
        "- 성능보다 가독성을 우선합니다.\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def decision_patterns_md(tmp_path: Path) -> Path:
    path = tmp_path / "DecisionPatterns.md"
    path.write_text(
        "---\n"
        "title: Decision Patterns\n"
        "---\n"
        "\n"
        "# Decision Patterns\n"
        "\n"
        "## Approved Patterns\n"
        "\n"
        "### 안전한 자동화 선호\n"
        "\n"
        "- 자동화는 선호하지만, 검토 단계가 있어야 합니다.\n"
        "\n"
        "### 장기 유지보수성 중시\n"
        "\n"
        "- 빠른 데모보다 유지 가능한 구조를 선호합니다.\n"
        "\n"
        "## Pending Patterns\n"
        "\n"
        "### 검토 중인 패턴 X\n"
        "\n"
        "- 아직 승인 전.\n",
        encoding="utf-8",
    )
    return path


def _fact(category: str, statement: str, conf: float = 0.8) -> ProfileFact:
    return ProfileFact(
        category=category,
        statement=statement,
        confidence=conf,
        source_ids=["test"],
        extracted_at="2026-05-18",
    )


def _pattern(trigger: str, action: str = "act", conf: float = 0.8) -> DecisionPattern:
    return DecisionPattern(
        trigger=trigger,
        action=action,
        rationale="r",
        confidence=conf,
        examples=["test"],
        extracted_at="2026-05-18",
    )


# ---------------------------------------------------------------------------
# 정규화 / 유사도
# ---------------------------------------------------------------------------


class TestNormalize:
    def test_lowercase_and_collapse_whitespace(self) -> None:
        assert _normalize("  Hello   World  ") == "hello world"

    def test_strips_trailing_punctuation(self) -> None:
        assert _normalize("iOS 개발 주력입니다.") == "ios 개발 주력입니다"
        assert _normalize("test...") == "test"
        assert _normalize("좋아요!") == "좋아요"

    def test_empty(self) -> None:
        assert _normalize("   ") == ""
        assert _normalize("") == ""


class TestJaccard:
    def test_identical_sets(self) -> None:
        a = frozenset({"x", "y", "z"})
        assert _jaccard(a, a) == 1.0

    def test_disjoint_sets(self) -> None:
        assert _jaccard(frozenset({"a"}), frozenset({"b"})) == 0.0

    def test_partial_overlap(self) -> None:
        a = frozenset({"a", "b", "c"})
        b = frozenset({"b", "c", "d"})
        # intersection=2, union=4 → 0.5
        assert _jaccard(a, b) == 0.5

    def test_empty_returns_zero(self) -> None:
        assert _jaccard(frozenset(), frozenset({"x"})) == 0.0


class TestIsDuplicate:
    def test_exact_match(self) -> None:
        tokens = [_token_set("iOS 개발 주력")]
        norms = {_normalize("iOS 개발 주력")}
        assert _is_duplicate("ios 개발 주력", norms, tokens) is True

    def test_jaccard_high_overlap(self) -> None:
        existing = "iOS 개발 주력 메가스터디 소속"
        tokens = [_token_set(existing)]
        norms = {_normalize(existing)}
        # 5 tokens vs 4 overlapping → 4/5 = 0.8 >= 0.75
        assert _is_duplicate(
            "iOS 개발 주력 메가스터디", norms, tokens
        ) is True

    def test_low_overlap_not_duplicate(self) -> None:
        existing = "iOS 개발 주력"
        tokens = [_token_set(existing)]
        norms = {_normalize(existing)}
        assert _is_duplicate(
            "Python 백엔드 학습 중", norms, tokens
        ) is False


# ---------------------------------------------------------------------------
# 파서
# ---------------------------------------------------------------------------


class TestParseProfileFacts:
    def test_extracts_all_bullets_across_categories(
        self, profile_md: Path
    ) -> None:
        facts = parse_profile_facts(profile_md)
        assert len(facts) == 4
        assert any("iOS 개발 주력" in f for f in facts)
        assert "기본 응답 언어는 한국어입니다." in facts

    def test_excludes_frontmatter_and_h1(self, profile_md: Path) -> None:
        facts = parse_profile_facts(profile_md)
        assert all("title:" not in f for f in facts)
        assert all(f != "AI Profile" for f in facts)

    def test_missing_file(self, tmp_path: Path) -> None:
        assert parse_profile_facts(tmp_path / "missing.md") == []

    def test_empty_file(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.md"
        p.write_text("", encoding="utf-8")
        assert parse_profile_facts(p) == []


class TestParseDecisionPatternTriggers:
    def test_only_approved_section(self, decision_patterns_md: Path) -> None:
        triggers = parse_decision_pattern_triggers(decision_patterns_md)
        assert "안전한 자동화 선호" in triggers
        assert "장기 유지보수성 중시" in triggers
        # Pending 섹션은 제외
        assert "검토 중인 패턴 X" not in triggers
        assert len(triggers) == 2

    def test_missing_file(self, tmp_path: Path) -> None:
        assert parse_decision_pattern_triggers(tmp_path / "x.md") == []

    def test_no_approved_section(self, tmp_path: Path) -> None:
        p = tmp_path / "DP.md"
        p.write_text("# DP\n\n## Pending\n\n### trigger\n", encoding="utf-8")
        assert parse_decision_pattern_triggers(p) == []


# ---------------------------------------------------------------------------
# dedupe_against_vault
# ---------------------------------------------------------------------------


class TestDedupeAgainstVault:
    def test_drops_exact_existing_facts(
        self, profile_md: Path, decision_patterns_md: Path
    ) -> None:
        candidates = [
            _fact("preference", "기본 응답 언어는 한국어입니다."),  # 중복
            _fact("tech", "Rust 시스템 프로그래밍 학습 중"),  # 신규
        ]
        new_facts, _, report = dedupe_against_vault(
            candidates,
            [],
            profile_path=profile_md,
            decision_patterns_path=decision_patterns_md,
        )
        assert report.facts_kept == 1
        assert report.facts_dropped == 1
        assert new_facts[0].statement == "Rust 시스템 프로그래밍 학습 중"

    def test_drops_jaccard_similar_facts(
        self, profile_md: Path, decision_patterns_md: Path
    ) -> None:
        # 기존: "Obsidian + synapse-memory 를 지식관리 인프라로 사용합니다."
        candidates = [
            _fact("tech", "Obsidian + synapse-memory 를 지식관리 인프라로 사용"),
        ]
        new_facts, _, report = dedupe_against_vault(
            candidates,
            [],
            profile_path=profile_md,
            decision_patterns_path=decision_patterns_md,
        )
        assert report.facts_dropped == 1
        assert new_facts == []

    def test_drops_existing_pattern_triggers(
        self, profile_md: Path, decision_patterns_md: Path
    ) -> None:
        candidates = [
            _pattern("안전한 자동화 선호", "확인 단계 추가"),  # 중복
            _pattern("새로운 결정 패턴", "new action"),  # 신규
        ]
        _, new_patterns, report = dedupe_against_vault(
            [],
            candidates,
            profile_path=profile_md,
            decision_patterns_path=decision_patterns_md,
        )
        assert report.patterns_kept == 1
        assert report.patterns_dropped == 1
        assert new_patterns[0].trigger == "새로운 결정 패턴"

    def test_pending_pattern_not_blocking(
        self, profile_md: Path, decision_patterns_md: Path
    ) -> None:
        """Pending 섹션 trigger 는 dedupe 기준 아님 → 신규로 살아남음."""
        candidates = [_pattern("검토 중인 패턴 X")]
        _, new_patterns, report = dedupe_against_vault(
            [], candidates,
            profile_path=profile_md,
            decision_patterns_path=decision_patterns_md,
        )
        assert report.patterns_kept == 1
        assert new_patterns[0].trigger == "검토 중인 패턴 X"

    def test_drops_batch_internal_duplicates(
        self, profile_md: Path, decision_patterns_md: Path
    ) -> None:
        candidates = [
            _fact("tech", "Kubernetes 운영 경험"),
            _fact("tech", "Kubernetes 운영 경험"),  # 배치 내 중복
            _fact("tech", "kubernetes  운영 경험."),  # 정규화 후 동일
        ]
        _new_facts, _, report = dedupe_against_vault(
            candidates,
            [],
            profile_path=profile_md,
            decision_patterns_path=decision_patterns_md,
        )
        assert report.facts_kept == 1
        assert report.facts_dropped == 2

    def test_empty_vault_passes_through(self, tmp_path: Path) -> None:
        candidates = [_fact("tech", "Go 시작")]
        patterns = [_pattern("새 패턴")]
        new_facts, new_patterns, report = dedupe_against_vault(
            candidates,
            patterns,
            profile_path=tmp_path / "nope.md",
            decision_patterns_path=tmp_path / "nope2.md",
        )
        assert report == DedupeReport(
            facts_kept=1, facts_dropped=0, patterns_kept=1, patterns_dropped=0
        )
        assert new_facts == candidates
        assert new_patterns == patterns

    def test_drops_empty_statement(
        self, profile_md: Path, decision_patterns_md: Path
    ) -> None:
        candidates = [_fact("tech", "   ")]
        new_facts, _, report = dedupe_against_vault(
            candidates,
            [],
            profile_path=profile_md,
            decision_patterns_path=decision_patterns_md,
        )
        assert new_facts == []
        assert report.facts_dropped == 1


# ---------------------------------------------------------------------------
# Daily integration sanity — _build_update_profile_action 가 dedupe 후
# 빈 결과면 save_profile_update 를 호출하지 않는다.
# ---------------------------------------------------------------------------


class TestDailyIntegration:
    def test_skips_save_when_all_deduped(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        profile_md: Path,
        decision_patterns_md: Path,
    ) -> None:
        import synapse_memory.config as config_mod
        from synapse_memory import daily

        # 실 ~/.synapse/private 격리 — ledger.save 가 실 ledger 를 건드리지 않게.
        fake_l0 = tmp_path / "private"
        fake_l0.mkdir()
        monkeypatch.setenv("SYNAPSE_L0_ROOT", str(fake_l0))

        vault_root = tmp_path / "vault"
        (vault_root / "90_System" / "AI").mkdir(parents=True)
        (vault_root / "90_System" / "AI" / "Profile.md").write_bytes(
            profile_md.read_bytes()
        )
        (vault_root / "90_System" / "AI" / "DecisionPatterns.md").write_bytes(
            decision_patterns_md.read_bytes()
        )

        monkeypatch.setattr(config_mod, "get_vault_path", lambda: vault_root)

        class FakeEnv:
            ready = True

        monkeypatch.setattr(
            "synapse_memory.llm.detect_ai_environment",
            lambda *a, **kw: FakeEnv(),
        )

        def fake_extract_facts(**_kw):
            # vault 와 100% 중복
            return [_fact("preference", "기본 응답 언어는 한국어입니다.")]

        def fake_extract_patterns(**_kw):
            return [_pattern("안전한 자동화 선호")]

        monkeypatch.setattr(
            "synapse_memory.profile.extract.extract_profile_facts",
            fake_extract_facts,
        )
        monkeypatch.setattr(
            "synapse_memory.profile.extract.extract_decision_patterns",
            fake_extract_patterns,
        )

        save_called = {"n": 0}

        def fake_save(*_a, **_kw):
            save_called["n"] += 1
            return vault_root / "should_not_exist.md"

        monkeypatch.setattr(
            "synapse_memory.profile.extract.save_profile_update", fake_save
        )

        action = daily._build_update_profile_action(
            profile_model="haiku",
            profile_sample_lines=50,
            profile_facts_only=False,
        )
        summary = action()
        assert save_called["n"] == 0
        assert "신규 fact/pattern 없음" in summary
        # 새 흐름: ledger promotion 단계 추가 — 첫 등장 fact 는 promotion 대기.
        # vault/dismissed 와 100% 중복인 경우라도 추출된 raw 가 ledger 에 누적 후
        # 후처리 dedupe 에서 drop 되어 candidate 0 으로 종료.
        assert "ledger" in summary
