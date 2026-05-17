"""Integration tests for the migrate-folders CLI subcommand (US2 contract)."""

from __future__ import annotations

from pathlib import Path

from synapse_memory.cli import main


def _scaffold(vault: Path) -> tuple[Path, Path]:
    inbox = vault / "90_System" / "AI" / "MemoryInbox"
    reports = vault / "90_System" / "AI" / "DailyReports"
    inbox.mkdir(parents=True)
    reports.mkdir(parents=True)
    (inbox / "Profile-2026-04-23.md").write_text("---\ntype: profile_update\n---\n")
    (inbox / "Profile-2026-05-17.md").write_text("---\ntype: profile_update\n---\n")
    (reports / "2026-05-17.md").write_text("---\ndate: 2026-05-17\n---\n")
    return inbox, reports


def test_cli_dry_run_zero_mutations(tmp_path: Path) -> None:
    inbox, reports = _scaffold(tmp_path)
    before = sorted(p.name for p in inbox.iterdir())

    rc = main(["migrate-folders", "--dry-run", "--vault", str(tmp_path)])

    assert rc == 0
    after = sorted(p.name for p in inbox.iterdir())
    assert before == after, "dry-run은 파일을 이동하면 안 됨"
    assert not (inbox / "2026").exists()
    assert (reports / "2026-05-17.md").is_file()


def test_cli_real_run_moves_files(tmp_path: Path) -> None:
    inbox, reports = _scaffold(tmp_path)

    rc = main(["migrate-folders", "--vault", str(tmp_path)])

    assert rc == 0
    assert (inbox / "2026" / "04" / "Profile-2026-04-23.md").is_file()
    assert (inbox / "2026" / "05" / "Profile-2026-05-17.md").is_file()
    assert (reports / "2026" / "05" / "2026-05-17.md").is_file()
    assert not (inbox / "Profile-2026-04-23.md").exists()
    assert not (reports / "2026-05-17.md").exists()


def test_cli_collision_returns_exit_1(tmp_path: Path) -> None:
    inbox, _ = _scaffold(tmp_path)
    nested = inbox / "2026" / "05"
    nested.mkdir(parents=True)
    (nested / "Profile-2026-05-17.md").write_text("existing")

    rc = main(["migrate-folders", "--vault", str(tmp_path)])

    assert rc == 1, "충돌 발생 시 종료 코드 1"
    assert (inbox / "Profile-2026-05-17.md").is_file(), "충돌 시 원본 보존"
    assert (
        nested / "Profile-2026-05-17.md"
    ).read_text() == "existing", "기존 파일 덮어쓰기 금지"


def test_cli_missing_vault_returns_exit_2(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    rc = main(["migrate-folders", "--vault", str(missing)])
    assert rc == 2
