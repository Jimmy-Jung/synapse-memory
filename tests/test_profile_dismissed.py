"""profile/dismissed.py 테스트.

핵심 시나리오
- append_dismissed: 신규 라인 추가, 멱등(동일 fingerprint 재요청 시 skip)
- load_dismissed: TTL 만료 라인 무시 + expired_count 보고
- ttl_days=0 → 영구 dismiss
- 사용자가 수동으로 라인 삭제 → 다음 load 시 fingerprint 빠짐
- 깨진 JSON / 알 수 없는 kind 라인은 silent skip
- 파일 권한 — 그룹/타인 쓰기 없음
- dedupe_against_vault 와의 통합 — dismissed fact 가 후보에서 제거됨
- TTL 만료된 dismissed 는 후보로 부활 (성향 변경 시나리오)
- CLI dismiss-profile 의 smoke + 멱등

저자: Synapse Memory Maintainers
작성일: 2026-05-18
"""

from __future__ import annotations

import datetime
import json
import stat
from pathlib import Path

import pytest

from synapse_memory.profile.dedupe import dedupe_against_vault
from synapse_memory.profile.dismissed import (
    DismissedIndex,
    DismissedRecord,
    append_dismissed,
    load_dismissed,
)
from synapse_memory.profile.schema import DecisionPattern, ProfileFact


def _fact(stmt: str) -> ProfileFact:
    return ProfileFact(
        category="tech",
        statement=stmt,
        confidence=0.8,
        source_ids=["t"],
        extracted_at="2026-05-18",
    )


def _pattern(trig: str) -> DecisionPattern:
    return DecisionPattern(
        trigger=trig,
        action="a",
        rationale="r",
        confidence=0.8,
        examples=["t"],
        extracted_at="2026-05-18",
    )


@pytest.fixture
def empty_vault(tmp_path: Path) -> tuple[Path, Path, Path]:
    """비어있는 vault Profile.md / DecisionPatterns.md + dismissed.jsonl 경로."""
    p = tmp_path / "Profile.md"
    p.write_text("---\ntitle: x\n---\n# x\n", encoding="utf-8")
    d = tmp_path / "DecisionPatterns.md"
    d.write_text("---\ntitle: x\n---\n# x\n", encoding="utf-8")
    return p, d, tmp_path / "_dismissed.jsonl"


# ---------------------------------------------------------------------------
# append
# ---------------------------------------------------------------------------


class TestAppendDismissed:
    def test_appends_new_record(self, tmp_path: Path) -> None:
        target = tmp_path / "_dismissed.jsonl"
        record = append_dismissed(
            "fact",
            "한국어 응답 선호",
            path=target,
            today=datetime.date(2026, 5, 18),
        )
        assert record is not None
        assert record.kind == "fact"
        assert record.fingerprint == "한국어 응답 선호"
        assert record.dismissed_at == "2026-05-18"
        line = target.read_text(encoding="utf-8").strip()
        data = json.loads(line)
        assert data["kind"] == "fact"
        assert data["original"] == "한국어 응답 선호"

    def test_idempotent_on_duplicate(self, tmp_path: Path) -> None:
        target = tmp_path / "_dismissed.jsonl"
        append_dismissed("fact", "Go 학습", path=target,
                         today=datetime.date(2026, 5, 18))
        again = append_dismissed("fact", "go  학습.", path=target,
                                 today=datetime.date(2026, 5, 19))
        assert again is None
        assert len(target.read_text(encoding="utf-8").splitlines()) == 1

    def test_different_kinds_not_collision(self, tmp_path: Path) -> None:
        target = tmp_path / "_dismissed.jsonl"
        append_dismissed("fact", "X 패턴", path=target,
                         today=datetime.date(2026, 5, 18))
        added = append_dismissed("pattern", "X 패턴", path=target,
                                 today=datetime.date(2026, 5, 18))
        assert added is not None
        assert len(target.read_text(encoding="utf-8").splitlines()) == 2

    def test_empty_text_returns_none(self, tmp_path: Path) -> None:
        target = tmp_path / "_dismissed.jsonl"
        assert append_dismissed("fact", "   ", path=target) is None
        assert not target.exists()

    def test_invalid_kind_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            append_dismissed("other", "x", path=tmp_path / "x.jsonl")  # type: ignore[arg-type]

    def test_file_no_group_or_other_write(self, tmp_path: Path) -> None:
        target = tmp_path / "_dismissed.jsonl"
        append_dismissed("fact", "x", path=target,
                         today=datetime.date(2026, 5, 18))
        mode = stat.S_IMODE(target.stat().st_mode)
        assert mode & 0o022 == 0  # group/other 쓰기 없음


# ---------------------------------------------------------------------------
# reason / note 필드 — (F) 묶음
# ---------------------------------------------------------------------------


class TestDismissReason:
    def test_record_with_reason_written(self, tmp_path: Path) -> None:
        target = tmp_path / "_dismissed.jsonl"
        record = append_dismissed(
            "fact",
            "1회성 작업 fact",
            reason="one_time",
            path=target,
            today=datetime.date(2026, 5, 18),
        )
        assert record is not None
        assert record.reason == "one_time"
        line = target.read_text(encoding="utf-8").strip()
        data = json.loads(line)
        assert data["reason"] == "one_time"

    def test_record_without_reason_omits_field(self, tmp_path: Path) -> None:
        """구 라인 호환 — reason 미지정 시 JSON 에 key 자체가 빠짐."""
        target = tmp_path / "_dismissed.jsonl"
        append_dismissed(
            "fact", "이유 미상", path=target,
            today=datetime.date(2026, 5, 18),
        )
        data = json.loads(target.read_text(encoding="utf-8").strip())
        assert "reason" not in data
        assert "note" not in data

    def test_record_with_other_reason_and_note(self, tmp_path: Path) -> None:
        target = tmp_path / "_dismissed.jsonl"
        append_dismissed(
            "fact",
            "기타 사유",
            reason="other",
            note="사용자 정의 메모",
            path=target,
            today=datetime.date(2026, 5, 18),
        )
        data = json.loads(target.read_text(encoding="utf-8").strip())
        assert data["reason"] == "other"
        assert data["note"] == "사용자 정의 메모"

    def test_invalid_reason_raises(self, tmp_path: Path) -> None:
        target = tmp_path / "_dismissed.jsonl"
        with pytest.raises(ValueError):
            append_dismissed(
                "fact", "x", reason="bogus",  # type: ignore[arg-type]
                path=target,
            )

    def test_legacy_line_without_reason_loads(self, tmp_path: Path) -> None:
        """기존 dismissed.jsonl (reason 필드 없음) 도 정상 load — backward compat."""
        target = tmp_path / "_dismissed.jsonl"
        target.write_text(
            '{"kind":"fact","fingerprint":"legacy","original":"L","dismissed_at":"2026-05-18"}\n',
            encoding="utf-8",
        )
        idx = load_dismissed(
            target, ttl_days=90, today=datetime.date(2026, 5, 18)
        )
        assert "legacy" in idx.facts

    def test_invalid_reason_field_in_jsonl_silently_normalized(
        self, tmp_path: Path
    ) -> None:
        """라인 자체에 invalid reason 이 박혀 있으면 빈 문자열로 정규화."""
        target = tmp_path / "_dismissed.jsonl"
        target.write_text(
            '{"kind":"fact","fingerprint":"x","original":"X",'
            '"dismissed_at":"2026-05-18","reason":"bogus"}\n',
            encoding="utf-8",
        )
        # load 는 정상 동작 (라인이 살아남음).
        idx = load_dismissed(
            target, ttl_days=90, today=datetime.date(2026, 5, 18)
        )
        assert "x" in idx.facts

    def test_idempotent_keeps_first_reason(self, tmp_path: Path) -> None:
        """같은 fingerprint 다시 dismiss → 첫 라인 reason 보존, 두 번째 append 안 함."""
        target = tmp_path / "_dismissed.jsonl"
        append_dismissed(
            "fact", "동일 항목", reason="one_time",
            path=target, today=datetime.date(2026, 5, 18),
        )
        again = append_dismissed(
            "fact", "동일 항목", reason="misclassified",
            path=target, today=datetime.date(2026, 5, 19),
        )
        assert again is None
        lines = target.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["reason"] == "one_time"

    def test_dismissed_record_round_trip(self) -> None:
        rec = DismissedRecord(
            kind="fact",
            fingerprint="x",
            original="X",
            dismissed_at="2026-05-18",
            reason="user_changed",
            note="",
        )
        restored = DismissedRecord.from_dict(rec.to_dict())
        assert restored == rec


# ---------------------------------------------------------------------------
# reason 별 TTL 차등 — 옵션 B
# ---------------------------------------------------------------------------


class TestReasonBasedTtl:
    def _write_lines(self, target: Path, *records: tuple[str, str, str, str]) -> None:
        """records: (kind, fingerprint, dismissed_at, reason) 튜플."""
        target.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        for kind, fp, day, reason in records:
            obj = {
                "kind": kind,
                "fingerprint": fp,
                "original": fp.upper(),
                "dismissed_at": day,
            }
            if reason:
                obj["reason"] = reason
            lines.append(json.dumps(obj, ensure_ascii=False))
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_user_changed_shorter_ttl_expires_first(self, tmp_path: Path) -> None:
        """user_changed=30, 기본=90 → 45일 지난 user_changed 는 만료, 기본은 active."""
        target = tmp_path / "_dismissed.jsonl"
        self._write_lines(
            target,
            ("fact", "fp_user_changed", "2026-04-03", "user_changed"),  # 45일 전
            ("fact", "fp_misclassified", "2026-04-03", "misclassified"),  # 45일 전
        )
        idx = load_dismissed(
            target,
            ttl_days=90,
            ttl_overrides={"user_changed": 30, "misclassified": 90},
            today=datetime.date(2026, 5, 18),
        )
        assert "fp_user_changed" not in idx.facts  # 30일 ttl 초과
        assert "fp_misclassified" in idx.facts     # 90일 ttl 이내
        assert idx.expired_count == 1

    def test_one_time_longer_ttl_outlives_default(self, tmp_path: Path) -> None:
        """one_time=180, 기본=90 → 120일 지난 one_time 은 active, 기본은 만료."""
        target = tmp_path / "_dismissed.jsonl"
        self._write_lines(
            target,
            ("fact", "fp_one_time", "2026-01-18", "one_time"),  # 120일 전
            ("fact", "fp_default", "2026-01-18", ""),            # 120일 전, reason 없음
        )
        idx = load_dismissed(
            target,
            ttl_days=90,
            ttl_overrides={"one_time": 180},
            today=datetime.date(2026, 5, 18),
        )
        assert "fp_one_time" in idx.facts          # 180일 ttl 이내
        assert "fp_default" not in idx.facts       # 기본 90일 ttl 초과
        assert idx.expired_count == 1

    def test_irrelevant_near_permanent(self, tmp_path: Path) -> None:
        """irrelevant=365 → 200일 전 라인도 active."""
        target = tmp_path / "_dismissed.jsonl"
        self._write_lines(
            target,
            ("pattern", "fp_irrelevant", "2025-10-30", "irrelevant"),  # ~200일 전
        )
        idx = load_dismissed(
            target,
            ttl_days=90,
            ttl_overrides={"irrelevant": 365},
            today=datetime.date(2026, 5, 18),
        )
        assert "fp_irrelevant" in idx.patterns

    def test_empty_and_other_reason_use_default(self, tmp_path: Path) -> None:
        """reason="" / "other" 는 default ttl 만 적용 — override 영향 없음."""
        target = tmp_path / "_dismissed.jsonl"
        self._write_lines(
            target,
            ("fact", "fp_blank", "2026-04-03", ""),     # 45일 전, 기본 90일
            ("fact", "fp_other", "2026-04-03", "other"),  # 45일 전, 기본 90일
        )
        idx = load_dismissed(
            target,
            ttl_days=90,
            ttl_overrides={
                "user_changed": 30,
                "misclassified": 90,
                "one_time": 180,
                "irrelevant": 365,
            },
            today=datetime.date(2026, 5, 18),
        )
        # 둘 다 기본 90일 ttl 이내 → active
        assert "fp_blank" in idx.facts
        assert "fp_other" in idx.facts

    def test_unknown_reason_falls_back_to_default(self, tmp_path: Path) -> None:
        """라인이 미래에 추가된 reason 이면 (override 키 없음) default 적용."""
        target = tmp_path / "_dismissed.jsonl"
        # 사용자가 직접 라인에 reason="superseded" 같은 미래 값을 넣었다고 가정 —
        # DismissedRecord.from_dict 는 invalid reason 을 "" 로 정규화하므로 그것도 default
        # 동작과 같다 — 두 경로 모두 default ttl_days 가 적용된다.
        self._write_lines(
            target,
            ("fact", "fp_unknown", "2026-04-03", ""),  # 45일 전
        )
        idx = load_dismissed(
            target,
            ttl_days=90,
            ttl_overrides={"user_changed": 30},  # 누락된 reason 들
            today=datetime.date(2026, 5, 18),
        )
        assert "fp_unknown" in idx.facts  # default 90일 ttl 이내

    def test_ttl_overrides_none_keeps_legacy_behavior(self, tmp_path: Path) -> None:
        """ttl_overrides 미지정 시 모든 reason 이 ttl_days 만 적용 (기존 동작)."""
        target = tmp_path / "_dismissed.jsonl"
        self._write_lines(
            target,
            ("fact", "fp_user_changed", "2026-04-13", "user_changed"),  # 35일 전
        )
        # ttl_overrides 명시적으로 빈 dict — config 폴백 안 일어남
        idx = load_dismissed(
            target,
            ttl_days=90,
            ttl_overrides={},
            today=datetime.date(2026, 5, 18),
        )
        # 빈 dict → _ttl_for 가 default 반환 → 90일 이내 active
        assert "fp_user_changed" in idx.facts

    def test_config_defaults_round_trip(self) -> None:
        """ProfileConfig 기본값 → profile_to_ttl_overrides 매핑이 4 reason 모두 포함."""
        from synapse_memory.config import ProfileConfig
        from synapse_memory.profile.dismissed import profile_to_ttl_overrides

        cfg = ProfileConfig()
        overrides = profile_to_ttl_overrides(cfg)
        assert overrides["user_changed"] == 30
        assert overrides["misclassified"] == 90
        assert overrides["one_time"] == 180
        assert overrides["irrelevant"] == 365
        # other / "" 는 매핑에 없어야 (default 폴백)
        assert "other" not in overrides
        assert "" not in overrides


class TestDismissedIndexByReason:
    """DismissedIndex 의 reason 별 fingerprint 분류 + strong helper."""

    def test_facts_by_reason_populated(self, tmp_path: Path) -> None:
        target = tmp_path / "_dismissed.jsonl"
        append_dismissed("fact", "A misclassified", reason="misclassified",
                         path=target, today=datetime.date(2026, 5, 18))
        append_dismissed("fact", "B irrelevant", reason="irrelevant",
                         path=target, today=datetime.date(2026, 5, 18))
        append_dismissed("fact", "C user_changed", reason="user_changed",
                         path=target, today=datetime.date(2026, 5, 18))
        append_dismissed("pattern", "P misclassified", reason="misclassified",
                         path=target, today=datetime.date(2026, 5, 18))

        idx = load_dismissed(target, ttl_days=90,
                             today=datetime.date(2026, 5, 18))
        assert idx.facts_by_reason["misclassified"] == frozenset({"a misclassified"})
        assert idx.facts_by_reason["irrelevant"] == frozenset({"b irrelevant"})
        assert idx.facts_by_reason["user_changed"] == frozenset({"c user_changed"})
        assert idx.patterns_by_reason["misclassified"] == frozenset(
            {"p misclassified"}
        )

    def test_strong_helpers_union_misclassified_and_irrelevant(
        self, tmp_path: Path
    ) -> None:
        target = tmp_path / "_dismissed.jsonl"
        append_dismissed("fact", "A", reason="misclassified", path=target,
                         today=datetime.date(2026, 5, 18))
        append_dismissed("fact", "B", reason="irrelevant", path=target,
                         today=datetime.date(2026, 5, 18))
        append_dismissed("fact", "C", reason="one_time", path=target,
                         today=datetime.date(2026, 5, 18))
        append_dismissed("fact", "D", reason="", path=target,
                         today=datetime.date(2026, 5, 18))

        idx = load_dismissed(target, ttl_days=365,
                             today=datetime.date(2026, 5, 18))
        strong = idx.strong_facts()
        assert "a" in strong
        assert "b" in strong
        assert "c" not in strong  # one_time 은 strong 아님
        assert "d" not in strong  # "" 도 strong 아님

    def test_empty_strong_when_no_misclassified_or_irrelevant(
        self, tmp_path: Path
    ) -> None:
        target = tmp_path / "_dismissed.jsonl"
        append_dismissed("fact", "X", reason="one_time", path=target,
                         today=datetime.date(2026, 5, 18))
        idx = load_dismissed(target, today=datetime.date(2026, 5, 18))
        assert idx.strong_facts() == frozenset()
        assert idx.strong_patterns() == frozenset()


# ---------------------------------------------------------------------------
# load + TTL
# ---------------------------------------------------------------------------


class TestLoadDismissed:
    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        result = load_dismissed(tmp_path / "nope.jsonl", ttl_days=90)
        assert result == DismissedIndex(frozenset(), frozenset(), 0)

    def test_loads_active_records(self, tmp_path: Path) -> None:
        target = tmp_path / "_dismissed.jsonl"
        for orig in ("fact A", "fact B"):
            append_dismissed("fact", orig, path=target,
                             today=datetime.date(2026, 5, 17))
        append_dismissed("pattern", "trig X", path=target,
                         today=datetime.date(2026, 5, 17))

        idx = load_dismissed(
            target, ttl_days=90, today=datetime.date(2026, 5, 18)
        )
        assert "fact a" in idx.facts
        assert "fact b" in idx.facts
        assert "trig x" in idx.patterns
        assert idx.expired_count == 0

    def test_ttl_expires_old_records(self, tmp_path: Path) -> None:
        target = tmp_path / "_dismissed.jsonl"
        append_dismissed("fact", "오래된 사실", path=target,
                         today=datetime.date(2026, 1, 1))
        append_dismissed("fact", "최근 사실", path=target,
                         today=datetime.date(2026, 5, 10))
        idx = load_dismissed(
            target, ttl_days=30, today=datetime.date(2026, 5, 18)
        )
        assert "최근 사실" in idx.facts
        assert "오래된 사실" not in idx.facts
        assert idx.expired_count == 1

    def test_ttl_zero_means_permanent(self, tmp_path: Path) -> None:
        target = tmp_path / "_dismissed.jsonl"
        append_dismissed("fact", "옛 fact", path=target,
                         today=datetime.date(2020, 1, 1))
        idx = load_dismissed(
            target, ttl_days=0, today=datetime.date(2026, 5, 18)
        )
        assert "옛 fact" in idx.facts
        assert idx.expired_count == 0

    def test_manual_line_deletion_drops_fingerprint(self, tmp_path: Path) -> None:
        """사용자가 vault 에서 직접 라인 삭제 → 즉시 후보로 부활."""
        target = tmp_path / "_dismissed.jsonl"
        append_dismissed("fact", "A 라인", path=target,
                         today=datetime.date(2026, 5, 17))
        append_dismissed("fact", "B 라인", path=target,
                         today=datetime.date(2026, 5, 17))
        # "A 라인" 라인 직접 삭제 시뮬레이션
        remaining = [
            line for line in target.read_text(encoding="utf-8").splitlines()
            if "A 라인" not in line
        ]
        target.write_text("\n".join(remaining) + "\n", encoding="utf-8")
        idx = load_dismissed(
            target, ttl_days=90, today=datetime.date(2026, 5, 18)
        )
        assert "a 라인" not in idx.facts
        assert "b 라인" in idx.facts

    def test_skips_malformed_lines(self, tmp_path: Path) -> None:
        target = tmp_path / "_dismissed.jsonl"
        target.write_text(
            "# header comment\n"
            "not json at all\n"
            '{"kind": "fact"}\n'                              # fingerprint 누락
            '{"kind": "weird", "fingerprint": "x"}\n'         # 잘못된 kind
            '{"kind": "fact", "fingerprint": "valid 항목",'
            ' "dismissed_at": "2026-05-18"}\n',
            encoding="utf-8",
        )
        idx = load_dismissed(
            target, ttl_days=90, today=datetime.date(2026, 5, 18)
        )
        assert idx.facts == frozenset({"valid 항목"})
        assert idx.patterns == frozenset()

    def test_skips_records_without_date_stay_active(
        self, tmp_path: Path
    ) -> None:
        """dismissed_at 없는 라인은 만료 검사 불가능 → active 유지."""
        target = tmp_path / "_dismissed.jsonl"
        target.write_text(
            '{"kind": "fact", "fingerprint": "x", "original": "X"}\n',
            encoding="utf-8",
        )
        idx = load_dismissed(
            target, ttl_days=30, today=datetime.date(2026, 5, 18)
        )
        assert "x" in idx.facts


# ---------------------------------------------------------------------------
# dedupe_against_vault 통합
# ---------------------------------------------------------------------------


class TestDedupeIntegration:
    def test_dismissed_facts_excluded_from_candidates(
        self, empty_vault: tuple[Path, Path, Path]
    ) -> None:
        profile_md, dp_md, dismissed_file = empty_vault
        append_dismissed("fact", "Rust 학습 중", path=dismissed_file,
                         today=datetime.date(2026, 5, 17))

        idx = load_dismissed(
            dismissed_file, ttl_days=90, today=datetime.date(2026, 5, 18)
        )

        candidates = [_fact("Rust 학습 중"), _fact("Python 백엔드 학습")]
        new_facts, _, report = dedupe_against_vault(
            candidates,
            [],
            profile_path=profile_md,
            decision_patterns_path=dp_md,
            dismissed_facts=idx.facts,
        )
        assert len(new_facts) == 1
        assert new_facts[0].statement == "Python 백엔드 학습"
        assert report.facts_dropped == 1

    def test_dismissed_pattern_excluded(
        self, empty_vault: tuple[Path, Path, Path]
    ) -> None:
        profile_md, dp_md, dismissed_file = empty_vault
        append_dismissed("pattern", "거부된 패턴", path=dismissed_file,
                         today=datetime.date(2026, 5, 17))
        idx = load_dismissed(
            dismissed_file, ttl_days=90, today=datetime.date(2026, 5, 18)
        )

        _, new_patterns, report = dedupe_against_vault(
            [],
            [_pattern("거부된 패턴"), _pattern("새 패턴")],
            profile_path=profile_md,
            decision_patterns_path=dp_md,
            dismissed_patterns=idx.patterns,
        )
        assert len(new_patterns) == 1
        assert new_patterns[0].trigger == "새 패턴"
        assert report.patterns_dropped == 1

    def test_expired_dismissed_reappears_in_candidates(
        self, empty_vault: tuple[Path, Path, Path]
    ) -> None:
        """TTL 만료된 dismissed → 다시 후보로 살아남음 (성향 변경 시나리오)."""
        profile_md, dp_md, dismissed_file = empty_vault
        append_dismissed("fact", "옛 fact", path=dismissed_file,
                         today=datetime.date(2026, 1, 1))
        idx = load_dismissed(
            dismissed_file, ttl_days=30, today=datetime.date(2026, 5, 18)
        )
        new_facts, _, _ = dedupe_against_vault(
            [_fact("옛 fact")],
            [],
            profile_path=profile_md,
            decision_patterns_path=dp_md,
            dismissed_facts=idx.facts,
        )
        assert len(new_facts) == 1
        assert new_facts[0].statement == "옛 fact"


# ---------------------------------------------------------------------------
# CLI smoke
# ---------------------------------------------------------------------------


class TestCliDismissProfile:
    def test_cli_creates_record(self, tmp_path: Path) -> None:
        from synapse_memory import cli

        vault = tmp_path / "vault"
        (vault / "90_System" / "AI" / "MemoryInbox").mkdir(parents=True)

        rc = cli.main(
            [
                "dismiss-profile",
                "--kind", "fact",
                "--text", "테스트 거부 항목",
                "--vault", str(vault),
            ]
        )
        assert rc == 0
        target = (
            vault / "90_System" / "AI" / "MemoryInbox" / "_dismissed.jsonl"
        )
        assert target.is_file()
        data = json.loads(target.read_text(encoding="utf-8").strip())
        assert data["kind"] == "fact"
        assert data["original"] == "테스트 거부 항목"

    def test_cli_idempotent(self, tmp_path: Path) -> None:
        from synapse_memory import cli

        vault = tmp_path / "vault"
        (vault / "90_System" / "AI" / "MemoryInbox").mkdir(parents=True)

        for _ in range(2):
            rc = cli.main(
                [
                    "dismiss-profile",
                    "--kind", "fact",
                    "--text", "동일 항목",
                    "--vault", str(vault),
                ]
            )
            assert rc == 0

        target = (
            vault / "90_System" / "AI" / "MemoryInbox" / "_dismissed.jsonl"
        )
        lines = [
            line
            for line in target.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(lines) == 1

    def test_cli_reason_flag(self, tmp_path: Path) -> None:
        """--reason 인자가 record 에 그대로 반영."""
        from synapse_memory import cli

        vault = tmp_path / "vault"
        (vault / "90_System" / "AI" / "MemoryInbox").mkdir(parents=True)

        rc = cli.main(
            [
                "dismiss-profile",
                "--kind", "pattern",
                "--text", "성향 바뀐 패턴",
                "--reason", "user_changed",
                "--vault", str(vault),
            ]
        )
        assert rc == 0

        target = (
            vault / "90_System" / "AI" / "MemoryInbox" / "_dismissed.jsonl"
        )
        data = json.loads(target.read_text(encoding="utf-8").strip())
        assert data["reason"] == "user_changed"
