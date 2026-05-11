"""L0 저장소 권한/경로 테스트.

저자: JunyoungJung <joony300@gmail.com>
작성일: 2026-05-10
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from synapse_memory.storage.l0 import (
    L0_DIR_MODE,
    L0_ENV_VAR,
    L0_FILE_MODE,
    ensure_l0_root_secure,
    ensure_secure_dir,
    ensure_secure_file,
    l0_root,
    secure_write_text,
)


class TestL0Root:
    def test_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(L0_ENV_VAR, raising=False)
        assert l0_root() == Path.home() / ".synapse" / "private"

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv(L0_ENV_VAR, str(tmp_path))
        assert l0_root() == tmp_path.resolve()


class TestEnsureSecureDir:
    def test_creates_with_0700(self, tmp_path: Path) -> None:
        target = tmp_path / "private" / "raw"
        ensure_secure_dir(target)
        assert target.is_dir()
        mode = stat.S_IMODE(target.stat().st_mode)
        assert mode == L0_DIR_MODE

    def test_idempotent(self, tmp_path: Path) -> None:
        target = tmp_path / "x"
        ensure_secure_dir(target)
        ensure_secure_dir(target)
        assert target.is_dir()

    def test_resets_loose_perms(self, tmp_path: Path) -> None:
        target = tmp_path / "loose"
        target.mkdir()
        os.chmod(target, 0o755)
        ensure_secure_dir(target)
        assert stat.S_IMODE(target.stat().st_mode) == L0_DIR_MODE


class TestEnsureSecureFile:
    def test_chmod_existing(self, tmp_path: Path) -> None:
        f = tmp_path / "secret.txt"
        f.write_text("data")
        os.chmod(f, 0o644)
        ensure_secure_file(f)
        assert stat.S_IMODE(f.stat().st_mode) == L0_FILE_MODE

    def test_no_create(self, tmp_path: Path) -> None:
        f = tmp_path / "missing.txt"
        ensure_secure_file(f)  # raise 안 해야
        assert not f.exists()


class TestEnsureL0RootSecure:
    def test_fixes_loose_existing_root(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """이전 도구가 0755로 만들어둔 L0 루트도 0700으로 정정."""
        loose = tmp_path / "private"
        loose.mkdir()
        os.chmod(loose, 0o755)
        monkeypatch.setenv(L0_ENV_VAR, str(loose))

        result = ensure_l0_root_secure()

        assert result == loose.resolve()
        assert stat.S_IMODE(loose.stat().st_mode) == L0_DIR_MODE

    def test_creates_when_missing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        target = tmp_path / "private"
        monkeypatch.setenv(L0_ENV_VAR, str(target))
        ensure_l0_root_secure()
        assert target.is_dir()
        assert stat.S_IMODE(target.stat().st_mode) == L0_DIR_MODE


class TestSecureWriteText:
    def test_writes_with_perms(self, tmp_path: Path) -> None:
        f = tmp_path / "sub" / "note.md"
        secure_write_text(f, "한국어 콘텐츠")
        assert f.read_text(encoding="utf-8") == "한국어 콘텐츠"
        assert stat.S_IMODE(f.stat().st_mode) == L0_FILE_MODE
        assert stat.S_IMODE(f.parent.stat().st_mode) == L0_DIR_MODE
