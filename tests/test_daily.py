"""Daily 파이프라인 테스트 — 각 step mock으로.

저자: Synapse Memory Maintainers
작성일: 2026-05-10
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from synapse_memory.daily import (
    STEPS,
    DailyStage,
    StageStatus,
    StepResult,
    render_daily_report,
    run_daily,
    validate_daily_stages,
)


def _ok(summary: str):
    def step() -> str:
        return summary

    return step


def _fail(message: str):
    def step() -> str:
        raise RuntimeError(message)

    return step


class TestRunDaily:
    def test_dry_run_lists_steps(self, capsys: pytest.CaptureFixture) -> None:
        result = run_daily(dry_run=True)
        captured = capsys.readouterr()
        for s in STEPS:
            assert s in captured.out
        assert result.steps == []

    def test_dry_run_with_only(self, capsys: pytest.CaptureFixture) -> None:
        run_daily(only={"collect_obsidian", "report"}, dry_run=True)
        out = capsys.readouterr().out
        assert "[x] collect_obsidian" in out
        assert "[x] report" in out
        assert "[ ] collect_claude_code" in out

    def test_skip_works(self, capsys: pytest.CaptureFixture) -> None:
        run_daily(skip={"update_profile", "generate"}, dry_run=True)
        out = capsys.readouterr().out
        assert "[ ] update_profile" in out
        assert "[ ] generate" in out
        assert "[x] collect_claude_code" in out

    def test_steps_constant_complete(self) -> None:
        # STEPS는 daily 단계 모두 포함
        assert "collect_claude_code" in STEPS
        assert "collect_obsidian" in STEPS
        assert "classify" in STEPS
        assert "generate" in STEPS
        assert "index" not in STEPS  # 020: RAG index 단계 제거
        assert "update_profile" in STEPS
        assert "report" in STEPS
        assert STEPS[-1] == "lint"

    def test_daily_stage_validation_rejects_duplicate_names(self) -> None:
        stages = (
            DailyStage("a", "A", ()),
            DailyStage("a", "B", ()),
        )

        with pytest.raises(ValueError, match="duplicate"):
            validate_daily_stages(stages)

    def test_daily_stage_validation_rejects_unknown_dependency(self) -> None:
        stages = (DailyStage("a", "A", ("missing",)),)

        with pytest.raises(ValueError, match="unknown dependency"):
            validate_daily_stages(stages)

    def test_step_result_status_properties(self) -> None:
        assert StepResult.skipped("generate", "requires classify").status == "skipped"
        assert StepResult.skipped("generate", "requires classify").skip_reason
        assert StepResult.failed("classify", 1.2, "boom").status == "failed"
        assert StepResult.success("index", 0.5, "cards=1").ok is True

    def test_successful_collector_errors_are_counted_as_warnings(self) -> None:
        result = run_daily(
            only={"collect_cursor"},
            stage_actions={
                "collect_cursor": _ok("mirrored=0 unchanged=0 bytes+=0 errors=2")
            },
            on_log=lambda _line: None,
        )

        assert result.errors == 0
        assert result.warnings == 2
        text = render_daily_report(result, date="2026-05-18", est_usd=0.0)
        assert "warnings_count: 2" in text

    def test_dependency_failure_skips_downstream(self) -> None:
        calls: list[str] = []

        def track(name: str, fn):
            def step():
                calls.append(name)
                return fn()

            return step

        result = run_daily(
            stage_actions={
                "collect_claude_code": track("collect_claude_code", _ok("mirrored=0")),
                "collect_obsidian": track("collect_obsidian", _ok("mirrored=0")),
                "classify": track("classify", _fail("AI provider 미설치")),
                "report": track("report", _ok("report skipped in test")),
                "lint": track("lint", _ok("lint skipped in test")),
            },
            on_log=lambda _line: None,
        )

        by_name = {step.name: step for step in result.steps}
        assert calls == [
            "collect_claude_code",
            "collect_obsidian",
            "classify",
            "report",
            "lint",
        ]
        assert by_name["classify"].status == StageStatus.FAILED
        assert by_name["generate"].status == StageStatus.SKIPPED
        assert by_name["generate"].skip_reason == "requires classify"
        assert by_name["update_profile"].status == StageStatus.SKIPPED
        assert result.errors == 1
        assert result.skipped == 2

    def test_resume_from_marks_previous_stages_skipped(self) -> None:
        calls: list[str] = []

        def track(name: str):
            def step() -> str:
                calls.append(name)
                return f"{name}=ok"

            return step

        result = run_daily(
            resume_from="classify",
            stage_actions={
                "classify": track("classify"),
                "generate": track("generate"),
                "update_profile": track("update_profile"),
                "report": track("report"),
                "lint": track("lint"),
            },
            on_log=lambda _line: None,
        )

        by_name = {step.name: step for step in result.steps}
        assert calls == ["classify", "generate", "update_profile", "report", "lint"]
        assert by_name["collect_claude_code"].status == StageStatus.SKIPPED
        assert by_name["collect_claude_code"].skip_reason == "resume before classify"
        assert by_name["collect_obsidian"].status == StageStatus.SKIPPED
        assert by_name["classify"].status == StageStatus.SUCCESS

    def test_unknown_resume_stage_raises_before_execution(self) -> None:
        called = False

        def step() -> str:
            nonlocal called
            called = True
            return "ok"

        with pytest.raises(ValueError, match="unknown daily stage"):
            run_daily(
                resume_from="nope",
                stage_actions={"collect_claude_code": step},
                on_log=lambda _line: None,
            )

        assert called is False

    def test_unknown_only_stage_raises_before_execution(self) -> None:
        with pytest.raises(ValueError, match="unknown daily stage in only"):
            run_daily(only={"nope"}, dry_run=True)

    def test_unknown_skip_stage_raises_before_execution(self) -> None:
        with pytest.raises(ValueError, match="unknown daily stage in skip"):
            run_daily(skip={"nope"}, dry_run=True)

    def test_only_stage_without_dependency_is_skipped(self) -> None:
        calls: list[str] = []

        def generate() -> str:
            calls.append("generate")
            return "generated"

        result = run_daily(
            only={"generate"},
            stage_actions={"generate": generate},
            on_log=lambda _line: None,
        )

        assert calls == []
        assert [(s.name, s.status, s.skip_reason) for s in result.steps] == [
            ("generate", StageStatus.SKIPPED, "requires classify")
        ]

    def test_dry_run_with_resume_from(self, capsys: pytest.CaptureFixture[str]) -> None:
        run_daily(resume_from="classify", dry_run=True)
        out = capsys.readouterr().out

        assert "[ ] collect_claude_code (resume skip)" in out
        assert "[ ] collect_obsidian (resume skip)" in out
        assert "[x] classify" in out

    def test_render_daily_report_profile_pipeline_section(self) -> None:
        """update_profile 메타가 있으면 Profile Pipeline 섹션이 렌더링."""
        from synapse_memory.daily import DailyResult

        result = DailyResult()
        result.profile_meta = {
            "raw_facts": 8,
            "raw_patterns": 3,
            "promoted_facts": 2,
            "promoted_patterns": 1,
            "awaiting_facts": 6,
            "awaiting_patterns": 2,
            "vault_dropped": 4,
            "dismissed_total": 12,
            "dismissed_expired": 1,
            "candidate_facts": 2,
            "candidate_patterns": 1,
            "dismissed_reason_counts": {
                "user_changed": 3,
                "one_time": 5,
                "": 2,
                "irrelevant": 2,
            },
        }
        text = render_daily_report(result, date="2026-05-18", est_usd=0.0)
        assert "## Profile Pipeline" in text
        assert "raw 추출: fact 8 · pattern 3" in text
        assert "promoted (ledger 통과): fact 2 · pattern 1" in text
        assert "awaiting (ledger 대기): fact 6 · pattern 2" in text
        assert "vault dedupe 제거: 4" in text
        assert "dismissed index: 활성 12, 만료 재노출 1" in text
        assert "### dismissed reason 분포" in text
        # 카운트 내림차순
        assert text.index("one_time: 5") < text.index("user_changed: 3")
        # 빈 reason 은 (미상) 라벨
        assert "(미상): 2" in text

    def test_render_daily_report_no_profile_section_when_meta_empty(self) -> None:
        from synapse_memory.daily import DailyResult

        result = DailyResult()  # profile_meta = {}
        text = render_daily_report(result, date="2026-05-18", est_usd=0.0)
        assert "## Profile Pipeline" not in text

    def test_render_daily_report_excludes_raw_fields(self, tmp_path: Path) -> None:
        result = run_daily(
            stage_actions={
                "collect_claude_code": _ok("mirrored=0"),
                "collect_obsidian": _ok("mirrored=0"),
                "classify": _fail("AI provider 미설치"),
                "report": _ok("report skipped in test"),
                "lint": _ok("lint skipped in test"),
            },
            on_log=lambda _line: None,
        )

        text = render_daily_report(result, date="2026-05-12", est_usd=0.0)

        assert "prompt" not in text.lower()
        assert "response" not in text.lower()
        assert "classify" in text
        assert "requires classify" in text

    def test_default_report_includes_final_elapsed_and_report_row(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import synapse_memory.collectors.obsidian as obsidian_mod

        monkeypatch.setattr(obsidian_mod, "get_vault_path", lambda: tmp_path)

        def slow_collect() -> str:
            time.sleep(0.11)
            return "mirrored=0"

        result = run_daily(
            only={"collect_claude_code", "report"},
            stage_actions={"collect_claude_code": slow_collect},
            on_log=lambda _line: None,
        )

        assert result.report_path is not None
        text = result.report_path.read_text(encoding="utf-8")
        assert "total_elapsed_s: 0.0" not in text
        assert "| report | success |" in text
        assert result.total_elapsed >= 0.1


# ---------------------------------------------------------------------------
# Summary humanization (0.13.1, DailyReport readability)
# ---------------------------------------------------------------------------


class TestHumanizeSummary:
    """`_humanize_stage_summary` 가 stage 별 raw 카운터를 사람 문장으로 변환."""

    def test_collect_claude_code_with_bytes_renders_size(self) -> None:
        from synapse_memory.daily import _humanize_stage_summary

        raw = (
            "scanned=252 mirrored=9 bytes+=73888700 truncations=0 "
            "skipped_empty=0 errors=0"
        )
        out = _humanize_stage_summary("collect_claude_code", raw)
        assert "9개 mirror" in out
        assert "MB" in out  # 70.5 MB 정도
        # 정상 케이스에서는 truncations/errors 가 0 이라 노이즈 안 붙음
        assert "잘림" not in out
        assert "에러" not in out

    def test_collect_claude_code_surfaces_anomalies(self) -> None:
        from synapse_memory.daily import _humanize_stage_summary

        raw = "scanned=5 mirrored=3 bytes+=1024 truncations=2 skipped_empty=1 errors=1"
        out = _humanize_stage_summary("collect_claude_code", raw)
        assert "잘림 2" in out
        assert "빈 파일 1" in out
        assert "에러 1" in out

    def test_collect_codex_shares_format_with_claude(self) -> None:
        from synapse_memory.daily import _humanize_stage_summary

        raw = "scanned=10 mirrored=3 bytes+=2048 truncations=0 skipped_empty=0 errors=0"
        out = _humanize_stage_summary("collect_codex", raw)
        assert "Codex 활동 로그 3개 mirror" in out
        assert "KB" in out

    def test_collect_obsidian_includes_unchanged(self) -> None:
        from synapse_memory.daily import _humanize_stage_summary

        raw = "scanned=1365 mirrored=17 unchanged=1348 bytes+=214273 errors=0"
        out = _humanize_stage_summary("collect_obsidian", raw)
        assert "17개 mirror" in out
        assert "변경 없음 1348" in out
        assert "KB" in out

    def test_update_profile_preserves_path(self) -> None:
        from synapse_memory.daily import _humanize_stage_summary

        raw = "fact=13 pattern=13 → Profile-2026-05-18.md"
        out = _humanize_stage_summary("update_profile", raw)
        assert "Fact 13개" in out
        assert "Pattern 13개" in out
        assert "Profile-2026-05-18.md" in out

    def test_already_human_summaries_pass_through(self) -> None:
        from synapse_memory.daily import _humanize_stage_summary

        assert (
            _humanize_stage_summary("classify", "신규 cluster 없음")
            == "신규 cluster 없음"
        )
        assert (
            _humanize_stage_summary("generate", "신규 Card 1개 생성")
            == "신규 Card 1개 생성"
        )

    def test_unknown_stage_or_empty_returns_raw(self) -> None:
        from synapse_memory.daily import _humanize_stage_summary

        assert _humanize_stage_summary("unknown_stage", "foo=1 bar=2") == "foo=1 bar=2"
        assert _humanize_stage_summary("collect_claude_code", "") == ""

    def test_render_inserts_human_summary_and_raw_details(self) -> None:
        result = run_daily(
            stage_actions={
                "collect_claude_code": _ok(
                    "scanned=10 mirrored=2 bytes+=4096 truncations=0 "
                    "skipped_empty=0 errors=0"
                ),
                "collect_obsidian": _ok(
                    "scanned=100 mirrored=5 unchanged=95 bytes+=1024 errors=0"
                ),
                "classify": _ok("신규 cluster 없음"),
                "generate": _ok("신규 Card 1개 생성"),
                "update_profile": _ok(
                    "fact=13 pattern=13 → Profile-2026-05-18.md"
                ),
                "report": _ok("report skipped in test"),
                "lint": _ok("lint skipped in test"),
            },
            on_log=lambda _line: None,
        )

        text = render_daily_report(result, date="2026-05-18", est_usd=0.5)

        # 사람 친화 문장이 표에 들어 있어야 함
        assert "Claude 활동 로그 2개 mirror" in text
        assert "vault 노트 5개 mirror" in text
        assert "Fact 13개" in text
        # raw 카운터는 details 블록으로 보존
        assert "<details>" in text
        assert "scanned=10 mirrored=2" in text
        assert "fact=13 pattern=13" in text


# ---------------------------------------------------------------------------
# Quick mode (B1, eng-review 2026-05-13)
# ---------------------------------------------------------------------------


class TestQuickMode:
    """``run_daily(quick=True)`` 의 cutoff 적용 + update_profile auto-skip 검증."""

    def test_quick_auto_skips_update_profile(self) -> None:
        """quick=True 시 only= 안 지정하면 update_profile auto-skip."""
        calls: list[str] = []

        def track(name: str):
            def step() -> str:
                calls.append(name)
                return f"{name}=ok"

            return step

        result = run_daily(
            quick=True,
            stage_actions={
                name: track(name) for name in (
                    "collect_claude_code", "collect_obsidian", "classify",
                    "generate", "update_profile", "report", "lint",
                )
            },
            on_log=lambda _line: None,
        )

        assert "update_profile" not in calls
        by_name = {s.name: s for s in result.steps}
        # update_profile 은 `selected -= update_profile` 효과로 result.steps 에 없음
        assert "update_profile" not in by_name

    def test_quick_with_explicit_only_respects_dependencies(self) -> None:
        """only= 로 명시해도 resume 없이 dependency 를 우회하지 않는다."""
        calls: list[str] = []

        def track(name: str):
            def step() -> str:
                calls.append(name)
                return f"{name}=ok"

            return step

        result = run_daily(
            quick=True,
            only={"update_profile"},
            stage_actions={"update_profile": track("update_profile")},
            on_log=lambda _line: None,
        )
        assert calls == []
        assert [(s.name, s.status, s.skip_reason) for s in result.steps] == [
            ("update_profile", StageStatus.SKIPPED, "requires collect_claude_code")
        ]

    def test_resume_from_update_profile_runs_explicit_stage(self) -> None:
        calls: list[str] = []

        def track(name: str):
            def step() -> str:
                calls.append(name)
                return f"{name}=ok"

            return step

        result = run_daily(
            quick=True,
            only={"update_profile"},
            resume_from="update_profile",
            stage_actions={"update_profile": track("update_profile")},
            on_log=lambda _line: None,
        )

        assert calls == ["update_profile"]
        assert result.steps[-1].name == "update_profile"
        assert result.steps[-1].status == StageStatus.SUCCESS

    def test_quick_false_preserves_full_behavior(self) -> None:
        """quick=False (기본) 시 모든 stage 실행 — 회귀 가드."""
        calls: list[str] = []

        def track(name: str):
            def step() -> str:
                calls.append(name)
                return f"{name}=ok"

            return step

        run_daily(
            stage_actions={
                name: track(name) for name in (
                    "collect_claude_code", "collect_obsidian", "classify",
                    "generate", "update_profile", "report", "lint",
                )
            },
            on_log=lambda _line: None,
        )
        assert "update_profile" in calls

    def test_lint_stage_uses_existing_wiki_lint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from synapse_memory.wiki.lint import LintReport

        called = False

        def fake_run_lint() -> LintReport:
            nonlocal called
            called = True
            return LintReport(backlinks_added=2, dead_links_removed=1)

        monkeypatch.setattr("synapse_memory.wiki.lint.run_lint", fake_run_lint)

        result = run_daily(
            only={"lint"},
            on_log=lambda _line: None,
        )

        assert called is True
        assert result.steps[-1].name == "lint"
        assert result.steps[-1].summary == (
            "backlinks+=2 dead_links-=1 orphans=0 review=0"
        )

    def test_quick_negative_days_rejected(self) -> None:
        with pytest.raises(ValueError):
            run_daily(quick=True, quick_days=-1, dry_run=True)

    def test_quick_negative_max_clusters_rejected(self) -> None:
        with pytest.raises(ValueError):
            run_daily(quick=True, quick_max_clusters=-1, dry_run=True)

    def test_quick_passes_through_to_stage_actions(self) -> None:
        """quick=True 시 _build_stage_actions 에 quick_since_days / quick_max_new_clusters 전달."""
        # 직접 _build_stage_actions 를 호출해 cutoff 가 적용된 build 인지 확인
        from synapse_memory.daily import _build_stage_actions

        actions = _build_stage_actions(
            classify_model="haiku",
            generate_model="sonnet",
            profile_model="sonnet",
            profile_sample_lines=200,
            profile_facts_only=False,
            on_log=lambda _line: None,
            quick_since_days=7,
            quick_max_new_clusters=5,
        )
        # collect_obsidian 은 closure — invoke 시 since_days=7 로 collect_obsidian 호출
        # 단위 test 에서는 정확한 closure 인자 확인이 어려움. 일단 인터페이스만 검증.
        assert "collect_obsidian" in actions
        assert "classify" in actions
