import json

import synapse_memory.cli as cli
from synapse_memory.wiki.daemon import CycleOutcome
from synapse_memory.wiki.ingest import IngestResult
from synapse_memory.wiki.launchd import LaunchctlError


def _per_source(results: dict):
    """source별 CycleOutcome 반환 monkeypatch. 미지정 source는 빈 사이클(ran=True)."""
    def _run(*, source="claude-code", **kw):
        res = results.get(source, IngestResult(source=source, docs_processed=0,
                                               pages_written=[]))
        return CycleOutcome(ran=True, result=res)
    return _run


def test_cli_watch_run(monkeypatch, capsys):
    result = IngestResult(source="claude-code", docs_processed=2, pages_written=["x"])
    monkeypatch.setattr(cli, "run_watch_cycle", _per_source({"claude-code": result}))
    assert cli.main(["watch", "run"]) == 0
    captured = capsys.readouterr()
    assert "watch run: docs=2, pages=1, errors=0" in captured.out
    assert "written: x" in captured.out
    assert captured.err == ""


def test_cli_watch_run_reports_errors(monkeypatch, capsys):
    result = IngestResult(
        source="claude-code",
        docs_processed=2,
        pages_written=[],
        errors=["doc-a: Claude Code CLI 미설치"],
    )
    monkeypatch.setattr(cli, "run_watch_cycle", _per_source({"claude-code": result}))

    assert cli.main(["watch", "run"]) == 1
    captured = capsys.readouterr()
    assert "watch run: docs=2, pages=0, errors=1" in captured.out
    assert "error: doc-a: Claude Code CLI 미설치" in captured.err


def test_cli_watch_run_ingests_both_sources(monkeypatch, capsys):
    """claude-code + codex 양쪽 ingest 결과 합산."""
    results = {
        "claude-code": IngestResult(source="claude-code", docs_processed=2,
                                    pages_written=["a"]),
        "codex": IngestResult(source="codex", docs_processed=3, pages_written=["b", "c"]),
    }
    monkeypatch.setattr(cli, "run_watch_cycle", _per_source(results))
    assert cli.main(["watch", "run"]) == 0
    out = capsys.readouterr().out
    assert "watch run: docs=5, pages=3, errors=0" in out
    assert "a" in out and "b" in out and "c" in out


def test_cli_watch_run_skipped(monkeypatch, capsys):
    monkeypatch.setattr(cli, "run_watch_cycle", lambda **kw: CycleOutcome(ran=False, skipped_reason="locked"))
    assert cli.main(["watch", "run"]) == 0
    assert "locked" in capsys.readouterr().out


def test_cli_watch_install(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "install_watch", lambda **kw: tmp_path / "x.plist")
    assert cli.main(["watch", "install"]) == 0


def test_cli_watch_install_returns_nonzero_on_launchctl_failure(monkeypatch, capsys):
    def fail_install(**kwargs):
        raise LaunchctlError("launchctl load failed")

    monkeypatch.setattr(cli, "install_watch", fail_install)

    assert cli.main(["watch", "install"]) == 1
    assert "launchctl load failed" in capsys.readouterr().err


def test_cli_watch_uninstall_returns_nonzero_on_launchctl_failure(monkeypatch, capsys):
    def fail_uninstall(**kwargs):
        raise LaunchctlError("launchctl unload failed")

    monkeypatch.setattr(cli, "uninstall_watch", fail_uninstall)

    assert cli.main(["watch", "uninstall"]) == 1
    assert "launchctl unload failed" in capsys.readouterr().err


def test_cli_watch_status_prints_all_sources(monkeypatch, tmp_path, capsys):
    plist = tmp_path / "watch.plist"
    plist.write_text("<plist></plist>", encoding="utf-8")
    monkeypatch.setattr(
        "synapse_memory.wiki.launchd.plist_path",
        lambda: plist,
    )
    monkeypatch.setattr(
        cli,
        "load_watermark",
        lambda source: {
            "claude-code": "2026-06-21T10:00:00",
            "codex": "2026-06-21T11:00:00",
        }.get(source),
    )

    assert cli.main(["watch", "status"]) == 0
    out = capsys.readouterr().out
    assert "installed: True" in out
    assert "claude-code watermark: 2026-06-21T10:00:00" in out
    assert "codex watermark: 2026-06-21T11:00:00" in out


def test_cli_watch_status_json_outputs_all_sources(monkeypatch, tmp_path, capsys):
    plist = tmp_path / "watch.plist"
    monkeypatch.setattr(
        "synapse_memory.wiki.launchd.plist_path",
        lambda: plist,
    )
    monkeypatch.setattr(
        cli,
        "load_watermark",
        lambda source: {"claude-code": "a", "codex": "b"}.get(source),
    )

    assert cli.main(["watch", "status", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["installed"] is False
    assert payload["sources"] == [
        {"source": "claude-code", "watermark": "a"},
        {"source": "codex", "watermark": "b"},
    ]
