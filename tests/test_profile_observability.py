"""관찰성 CLI 테스트 — dismiss-list / dismiss-purge-expired / ledger-show.

저자: Synapse Memory Maintainers
작성일: 2026-05-18
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest

from synapse_memory.profile.dismissed import append_dismissed
from synapse_memory.profile.ledger import (
    LedgerEntry,
    mark_promoted,
    record_extraction,
    save_ledger,
)
from synapse_memory.profile.schema import DecisionPattern, ProfileFact


def _fact(stmt: str, conf: float = 0.8) -> ProfileFact:
    return ProfileFact(
        category="tech",
        statement=stmt,
        confidence=conf,
        source_ids=["t"],
        extracted_at="2026-05-18",
    )


# ---------------------------------------------------------------------------
# dismiss-list
# ---------------------------------------------------------------------------


class TestDismissList:
    def _setup_vault(self, tmp_path: Path) -> Path:
        vault = tmp_path / "vault"
        (vault / "90_System" / "AI" / "MemoryInbox").mkdir(parents=True)
        return vault

    def test_empty_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from synapse_memory import cli

        vault = self._setup_vault(tmp_path)
        rc = cli.main(["dismiss-list", "--vault", str(vault)])
        assert rc == 0
        assert "비어 있" in capsys.readouterr().out

    def test_json_output(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from synapse_memory import cli
        from synapse_memory.profile.dismissed import dismissed_path

        vault = self._setup_vault(tmp_path)
        append_dismissed(
            "fact", "한국어 응답 선호", reason="user_changed",
            path=dismissed_path(vault), today=datetime.date(2026, 5, 17),
        )
        append_dismissed(
            "pattern", "1회성 패턴", reason="one_time",
            path=dismissed_path(vault), today=datetime.date(2026, 5, 17),
        )
        rc = cli.main(["dismiss-list", "--vault", str(vault), "--json"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert len(data) == 2
        kinds = {r["kind"] for r in data}
        assert kinds == {"fact", "pattern"}

    def test_kind_filter(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from synapse_memory import cli
        from synapse_memory.profile.dismissed import dismissed_path

        vault = self._setup_vault(tmp_path)
        append_dismissed("fact", "fact A", path=dismissed_path(vault))
        append_dismissed("pattern", "pattern B", path=dismissed_path(vault))
        rc = cli.main(
            ["dismiss-list", "--vault", str(vault), "--kind", "fact", "--json"]
        )
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert len(data) == 1
        assert data[0]["kind"] == "fact"

    def test_reason_filter(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from synapse_memory import cli
        from synapse_memory.profile.dismissed import dismissed_path

        vault = self._setup_vault(tmp_path)
        append_dismissed(
            "fact", "A", reason="one_time", path=dismissed_path(vault)
        )
        append_dismissed(
            "fact", "B", reason="user_changed", path=dismissed_path(vault)
        )
        rc = cli.main(
            ["dismiss-list", "--vault", str(vault),
             "--reason", "one_time", "--json"]
        )
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert len(data) == 1
        assert data[0]["reason"] == "one_time"

    def test_active_only_filter(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """user_changed 라인은 30일 TTL → 50일 전이면 expired, --active-only 로 제외."""
        from synapse_memory import cli
        from synapse_memory.profile.dismissed import dismissed_path

        vault = self._setup_vault(tmp_path)
        # 50일 전 user_changed (TTL 30일 → 만료)
        append_dismissed(
            "fact", "expired A", reason="user_changed",
            path=dismissed_path(vault),
            today=datetime.date(2026, 3, 29),
        )
        # 5일 전 one_time (TTL 180일 → active)
        append_dismissed(
            "fact", "active B", reason="one_time",
            path=dismissed_path(vault),
            today=datetime.date(2026, 5, 13),
        )

        # date.today() 를 2026-05-18 로 고정 — cli 내부의 datetime.date.today() 가 사용
        import datetime as _dt

        class _FakeDate(_dt.date):
            @classmethod
            def today(cls):
                return cls(2026, 5, 18)

        monkeypatch.setattr(_dt, "date", _FakeDate)

        rc = cli.main(
            ["dismiss-list", "--vault", str(vault),
             "--active-only", "--json"]
        )
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        fingerprints = {r["fingerprint"] for r in data}
        assert "active b" in fingerprints
        assert "expired a" not in fingerprints


# ---------------------------------------------------------------------------
# dismiss-purge-expired
# ---------------------------------------------------------------------------


class TestDismissPurgeExpired:
    def _setup_vault_with_lines(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> Path:
        from synapse_memory.profile.dismissed import dismissed_path

        vault = tmp_path / "vault"
        (vault / "90_System" / "AI" / "MemoryInbox").mkdir(parents=True)
        # 만료 라인 (user_changed, 60일 전 > 30일 TTL)
        append_dismissed(
            "fact", "expired", reason="user_changed",
            path=dismissed_path(vault),
            today=datetime.date(2026, 3, 19),
        )
        # 신선 라인 (one_time, 10일 전 < 180일 TTL)
        append_dismissed(
            "fact", "fresh", reason="one_time",
            path=dismissed_path(vault),
            today=datetime.date(2026, 5, 8),
        )

        import datetime as _dt

        class _FakeDate(_dt.date):
            @classmethod
            def today(cls):
                return cls(2026, 5, 18)

        monkeypatch.setattr(_dt, "date", _FakeDate)
        return vault

    def test_dry_run_does_not_modify(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from synapse_memory import cli
        from synapse_memory.profile.dismissed import dismissed_path

        vault = self._setup_vault_with_lines(tmp_path, monkeypatch)
        target = dismissed_path(vault)
        before = target.read_text(encoding="utf-8")

        rc = cli.main(["dismiss-purge-expired", "--vault", str(vault)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "만료 대상: 1건" in out
        assert "dry-run" in out
        assert target.read_text(encoding="utf-8") == before

    def test_apply_purges_and_backups(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from synapse_memory import cli
        from synapse_memory.profile.dismissed import dismissed_path

        vault = self._setup_vault_with_lines(tmp_path, monkeypatch)
        target = dismissed_path(vault)
        before_lines = target.read_text(encoding="utf-8").splitlines()
        assert len(before_lines) == 2

        rc = cli.main(["dismiss-purge-expired", "--vault", str(vault), "--apply"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "1건 삭제 완료" in out
        # 백업 생성됨
        backups = list(target.parent.glob(target.name + ".bak.*"))
        assert len(backups) == 1
        # 신선한 라인만 남음
        after = target.read_text(encoding="utf-8")
        assert "fresh" in after
        assert "expired" not in after

    def test_no_expired_skips_work(
        self, tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from synapse_memory import cli
        from synapse_memory.profile.dismissed import dismissed_path

        vault = tmp_path / "vault"
        (vault / "90_System" / "AI" / "MemoryInbox").mkdir(parents=True)
        append_dismissed(
            "fact", "fresh only",
            path=dismissed_path(vault),
            today=datetime.date.today(),
        )
        rc = cli.main(["dismiss-purge-expired", "--vault", str(vault)])
        assert rc == 0
        assert "만료된 라인 없음" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# ledger-show
# ---------------------------------------------------------------------------


class TestLedgerShow:
    def _seed_ledger(self, l0_root: Path) -> None:
        (l0_root / "state").mkdir(parents=True, exist_ok=True)
        ledger: dict[str, LedgerEntry] = {}
        # 4일 누적 promoted
        for day in (14, 15, 16, 17):
            record_extraction(
                ledger, [_fact("강한 신호", 0.9)], [],
                today=datetime.date(2026, 5, day),
            )
        mark_promoted(
            ledger, [_fact("강한 신호", 0.9)], [],
            today=datetime.date(2026, 5, 17),
        )
        # 1일만 등장 — awaiting
        record_extraction(
            ledger, [_fact("약한 신호", 0.6)], [],
            today=datetime.date(2026, 5, 18),
        )
        # pattern
        record_extraction(
            ledger, [], [DecisionPattern(
                trigger="대기 trigger", action="a", rationale="r",
                confidence=0.7, examples=[], extracted_at="2026-05-18",
            )],
            today=datetime.date(2026, 5, 18),
        )
        save_ledger(ledger, l0_root / "state" / "profile_ledger.jsonl")

    def test_missing_ledger(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from synapse_memory import cli

        monkeypatch.setenv("SYNAPSE_L0_ROOT", str(tmp_path / "l0"))
        rc = cli.main(["ledger-show"])
        assert rc == 0
        assert "ledger 파일 없음" in capsys.readouterr().out

    def test_json_full_output(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from synapse_memory import cli

        l0 = tmp_path / "l0"
        l0.mkdir()
        monkeypatch.setenv("SYNAPSE_L0_ROOT", str(l0))
        self._seed_ledger(l0)

        rc = cli.main(["ledger-show", "--json", "--top", "0"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert len(data) == 3  # 강한 fact + 약한 fact + 대기 pattern

    def test_status_filter_promoted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from synapse_memory import cli

        l0 = tmp_path / "l0"
        l0.mkdir()
        monkeypatch.setenv("SYNAPSE_L0_ROOT", str(l0))
        self._seed_ledger(l0)

        rc = cli.main(
            ["ledger-show", "--json", "--status", "promoted", "--top", "0"]
        )
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert len(data) == 1
        assert data[0]["promoted"] is True

    def test_kind_filter(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from synapse_memory import cli

        l0 = tmp_path / "l0"
        l0.mkdir()
        monkeypatch.setenv("SYNAPSE_L0_ROOT", str(l0))
        self._seed_ledger(l0)

        rc = cli.main(
            ["ledger-show", "--json", "--kind", "pattern", "--top", "0"]
        )
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert all(r["kind"] == "pattern" for r in data)
        assert len(data) == 1

    def test_top_limits_count(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from synapse_memory import cli

        l0 = tmp_path / "l0"
        l0.mkdir()
        monkeypatch.setenv("SYNAPSE_L0_ROOT", str(l0))
        self._seed_ledger(l0)

        rc = cli.main(["ledger-show", "--json", "--top", "1"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert len(data) == 1
        # seen_count 내림차순 — 강한 신호(4회)가 최상위
        assert "강한 신호" in data[0]["statements"][0]
