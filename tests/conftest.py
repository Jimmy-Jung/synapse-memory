"""테스트 전역 fixture — L0 루트 기본값 격리.

`synapse_memory.storage.l0.l0_root()` 의 default 동작은 `~/.synapse/private/`
실 시스템 경로를 가리킨다. profile/extract, wiki ingest 등이 path 인자를 명시하지
않으면 그 default 가 적용돼 테스트 격리가 깨질 수 있다.

이 autouse fixture 는 `SYNAPSE_L0_ROOT` 를 tmp 디렉터리로 강제해 default 호출이
실 데이터에 닿지 않도록 보장한다. 개별 테스트가 자기 `monkeypatch.setenv` 로
다시 override 하면 그것이 우선.

저자: Synapse Memory Maintainers
작성일: 2026-05-21
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_l0_root(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """default L0 루트를 OS tempfile 디렉터리로 격리.

    pytest 의 `tmp_path` 인프라에 의존하지 않고 직접 `tempfile.mkdtemp` 로
    unique 디렉터리를 생성한다. 이렇게 하면 같은 prefix 의 numbered_dir
    한도(10) 와 무관하게 매 테스트가 안전하게 격리된다. 개별 테스트가
    `monkeypatch.setenv("SYNAPSE_L0_ROOT", ...)` 로 다시 override 하면
    그게 우선.
    """
    isolate = Path(tempfile.mkdtemp(prefix="syn-l0-"))
    monkeypatch.setenv("SYNAPSE_L0_ROOT", str(isolate))
    try:
        yield
    finally:
        shutil.rmtree(isolate, ignore_errors=True)


@pytest.fixture(autouse=True)
def _isolate_external_volumes_root(monkeypatch: pytest.MonkeyPatch) -> None:
    """watch 로그 외장 볼륨 판별 루트(`/Volumes`)를 존재하지 않는 가짜 경로로 교체.

    TMPDIR가 외장 볼륨이어도 `tmp_path`가 '내장'으로 판정되게 한다. 외장 경로가
    필요한 테스트는 `launchd._EXTERNAL_VOLUMES_ROOT / ...`를 쓴다.
    """
    fake_root = Path(tempfile.gettempdir()).resolve() / "syn-fake-Volumes"
    monkeypatch.setattr("synapse_memory.wiki.launchd._EXTERNAL_VOLUMES_ROOT", fake_root)


@pytest.fixture(autouse=True)
def _isolate_codex_catalog(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """`codex debug models` 실호출 차단 — 기본은 '조회 불가'(모델 대체 없음).

    카탈로그가 필요한 테스트는 `codex_catalog._run_catalog`를 다시 monkeypatch한 뒤
    `load_catalog.cache_clear()`를 호출한다.
    """
    from synapse_memory.llm import codex_catalog

    monkeypatch.setattr(codex_catalog, "_run_catalog", lambda: None)
    codex_catalog.load_catalog.cache_clear()
    codex_catalog._warned.clear()
    yield
    codex_catalog.load_catalog.cache_clear()
