# src/synapse_memory/llm/codex_catalog.py
"""Codex 모델 카탈로그 — 역할별 최신 모델 제안 + 사라진 모델 실행 중 대체.

정책(2026-10-19 결정):
- 우선순위 기반 매핑. 기본·고급 task = 카탈로그 priority 1순위(codex 기본 모델),
  저가 task(classify, relevance) = priority가 가장 높은 ``-luna``. 티어 이름의 의미가
  세대마다 바뀌므로(5.6 sol=고급 → 6.1 sol=workhorse) 구조화 필드인 priority만 쓴다.
- 새 세대 등장은 자동 적용하지 않는다 — doctor 알림 → ``models refresh``로 확인 후 적용.
- 설정 모델이 카탈로그에서 사라졌을 때만 실행 중 자동 대체한다(중단 방지).

``codex debug models``는 debug 명령이라 출력 포맷이 바뀔 수 있다. 조회·파싱 실패는
``None``으로 처리해 기존 설정을 그대로 쓴다. ``_run_catalog``가 유일한 subprocess
seam이라 테스트는 이를 monkeypatch한다.

저자: JunyoungJung
작성일: 2026-10-19
"""
from __future__ import annotations

import functools
import json
import subprocess
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from synapse_memory.config import ModelsConfig

CODEX_TASKS = (
    "default",
    "classify",
    "card_generate",
    "ask",
    "decide",
    "resume",
    "recall",
    "update_profile",
    "generate",
    "relevance",
)
CHEAP_TASKS = frozenset({"classify", "relevance"})
_CHEAP_SUFFIX = "-luna"
_CATALOG_TIMEOUT_SEC = 30

_warned: set[str] = set()


def _run_catalog() -> str | None:
    """``codex debug models`` stdout — 실패 시 None. 유일한 subprocess seam."""
    try:
        result = subprocess.run(
            ["codex", "debug", "models"],
            capture_output=True,
            text=True,
            timeout=_CATALOG_TIMEOUT_SEC,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


@functools.cache
def load_catalog() -> tuple[str, ...] | None:
    """모델 선택기에 노출되는 모델 slug — priority 오름차순. 실패 시 None.

    프로세스당 1회 조회(watch 잡은 사이클마다 새 프로세스). codex가 자체 캐시를 써서 빠르다.
    """
    raw = _run_catalog()
    if raw is None:
        return None
    try:
        models = json.loads(raw)["models"]
        listed = sorted(
            (m for m in models if m.get("visibility") == "list"),
            key=lambda m: m["priority"],
        )
        slugs = tuple(str(m["slug"]) for m in listed)
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
    return slugs or None


def propose(catalog: tuple[str, ...]) -> dict[str, str]:
    """task → 제안 모델. 기본·고급 = 1순위, 저가 = 최우선 luna(없으면 1순위)."""
    default = catalog[0]
    cheap = next((slug for slug in catalog if slug.endswith(_CHEAP_SUFFIX)), default)
    return {task: cheap if task in CHEAP_TASKS else default for task in CODEX_TASKS}


def current_models(models: ModelsConfig) -> dict[str, str | None]:
    """config 기준 codex task별 실제 사용 모델."""
    from synapse_memory.config import _PROVIDER_FALLBACK_MODEL

    current: dict[str, str | None] = {
        task: models.model_for_task("codex", task) for task in CODEX_TASKS if task != "default"
    }
    current["default"] = models.overrides.codex.default or _PROVIDER_FALLBACK_MODEL["codex"]
    return {task: current[task] for task in CODEX_TASKS}


def pending_changes(
    models: ModelsConfig, catalog: tuple[str, ...]
) -> list[tuple[str, str | None, str]]:
    """(task, 현재, 제안) — 제안과 다른 task만."""
    proposal = propose(catalog)
    return [
        (task, current, proposal[task])
        for task, current in current_models(models).items()
        if current != proposal[task]
    ]


def apply_changes(models: ModelsConfig, changes: list[tuple[str, str | None, str]]) -> None:
    """제안 모델을 ``models.overrides.codex``에 기록 (저장은 호출자 몫)."""
    for task, _current, proposed in changes:
        setattr(models.overrides.codex, task, proposed)


def replacement_for(model: str) -> str | None:
    """카탈로그에서 사라진 모델의 대체 모델. 있거나 조회 실패면 None.

    호출 맥락(task)을 모르므로 이름으로 역할을 추정한다: ``-luna``면 저가, 아니면 기본.
    """
    catalog = load_catalog()
    if catalog is None or model in catalog:
        return None
    proposal = propose(catalog)
    replacement = proposal["classify"] if model.endswith(_CHEAP_SUFFIX) else proposal["default"]
    if model not in _warned:
        _warned.add(model)
        print(
            f"warning: codex 모델 {model}이(가) 카탈로그에 없어 이번 실행은 {replacement}로 대체합니다. "
            "`synapse-memory models refresh`로 config를 갱신하세요.",
            file=sys.stderr,
        )
    return replacement
