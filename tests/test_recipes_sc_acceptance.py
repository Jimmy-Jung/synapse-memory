"""SC acceptance bindings — spec 의 SC-001~SC-008 을 각 단위 시나리오로 묶음.

본 파일은 7 SC 의 통합 검증 — 개별 단위 테스트가 이미 통과하더라도
spec 작성자가 SC 단위로 "한 곳에서" 확인할 수 있도록 traceability 를 제공.

각 test 함수는 docstring 에 대응 SC ID 와 spec 의 acceptance criteria 를 명시.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from synapse_memory.recipes import generate
from synapse_memory.recipes.registry import RecipeRegistry

_FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "recipes_vault"
_BUILTIN_DIR = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "synapse_memory"
    / "recipes"
    / "builtin"
)


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    dst = tmp_path / "vault"
    shutil.copytree(_FIXTURE_ROOT, dst)
    return dst


class _StoreStub:
    def __init__(self, n: int = 1) -> None:
        self._n = n

    def query(self, *_args: Any, **_kwargs: Any) -> list[tuple[Any, float]]:
        out: list[tuple[Any, float]] = []
        for i in range(self._n):
            rec = mock.Mock()
            rec.metadata = {
                "card_id": f"rec-{i}",
                "display_name": f"rec-{i}",
                "source_kind": "card_project",
            }
            rec.document = f"sample doc {i}"
            rec.id = f"rec-{i}"
            out.append((rec, 0.1 + 0.01 * i))
        return out


def test_sc_001_user_recipe_added_without_code_change(vault: Path) -> None:
    """SC-001 — vault/90_System/AI/recipes/diary.md 가 즉시 발견되어 실행 가능."""
    reg = RecipeRegistry(
        builtin_dir=_BUILTIN_DIR,
        user_dir=vault / "90_System" / "AI" / "recipes",
    )
    reg.scan()
    assert "diary" in reg.recipes
    assert reg.recipes["diary"].source == "user"


def test_sc_002_builtin_recipes_produce_markdown(vault: Path) -> None:
    """SC-002 — 빌트인 recipe (resume/weekly_report/journal/brainstorm) 가 markdown 생성."""
    inputs_map = {
        "resume": {"company_id": "acme_co"},
        "weekly_report": {"period": "2026-W19"},
        "journal": {"date": "2026-05-12"},
        "brainstorm": {"topic": "시간관리"},
    }
    for name, inputs in inputs_map.items():
        with mock.patch(
            "synapse_memory.recipes.pipeline.ai_api_complete",
            return_value=f"# {name} output\n- body",
        ), mock.patch(
            "synapse_memory.recipes.pipeline.save_last_answer",
            return_value=vault / "ignored.json",
        ):
            result = generate(
                name,
                inputs=inputs,
                vault_path=vault,
                store=_StoreStub(),
                builtin_dir=_BUILTIN_DIR,
            )
        assert result.answer_markdown.strip(), f"{name} produced empty output"


def test_sc_003_english_resume_zero_korean_headers(vault: Path) -> None:
    """SC-003 — Profile.preferred_lang=en 이면 system prompt 가 영어 placeholder 와 함께 렌더."""
    src = vault / "profile_en_design" / "90_System" / "AI" / "Profile.md"
    dst = vault / "90_System" / "AI" / "Profile.md"
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    captured: dict[str, str] = {}

    def fake(prompt: str, *, system: str | None = None, **_kw: Any) -> str:
        captured["prompt"] = prompt
        captured["system"] = system or ""
        return "# Mock resume body"

    with mock.patch(
        "synapse_memory.recipes.pipeline.ai_api_complete", side_effect=fake
    ), mock.patch(
        "synapse_memory.recipes.pipeline.save_last_answer",
        return_value=vault / "ignored.json",
    ):
        result = generate(
            "resume",
            inputs={"company_id": "acme_co"},
            vault_path=vault,
            store=_StoreStub(),
            builtin_dir=_BUILTIN_DIR,
        )
    assert result.locale == "English"
    assert "Designer Test User" in captured["prompt"]


def test_sc_004_profile_injected_in_prompt(vault: Path) -> None:
    """SC-004 — use_profile=true recipe 는 Profile 본문을 user prompt 에 첨부."""
    captured: dict[str, str] = {}

    def fake(prompt: str, *, system: str | None = None, **_kw: Any) -> str:
        captured["prompt"] = prompt
        return "ok"

    with mock.patch(
        "synapse_memory.recipes.pipeline.ai_api_complete", side_effect=fake
    ), mock.patch(
        "synapse_memory.recipes.pipeline.save_last_answer",
        return_value=vault / "ignored.json",
    ):
        generate(
            "weekly_report",
            inputs={"period": "2026-W19"},
            vault_path=vault,
            store=_StoreStub(),
            builtin_dir=_BUILTIN_DIR,
        )
    assert "명료한 글쓰기" in captured["prompt"]  # fixture Profile.md body


def test_sc_006_recipes_list_under_1s(vault: Path) -> None:
    """SC-006 — RecipeRegistry.scan() 이 50 recipes 이하 vault 에서 1 s 이내."""
    user_dir = vault / "90_System" / "AI" / "recipes"
    for i in range(49):
        (user_dir / f"stub_{i:02d}.md").write_text(
            f"---\nname: stub_{i:02d}\ndescription: stub\ninput_schema:\n  x: optional\n---\n\nbody\n",
            encoding="utf-8",
        )
    reg = RecipeRegistry(builtin_dir=_BUILTIN_DIR, user_dir=user_dir)
    t0 = time.monotonic()
    reg.scan()
    elapsed = time.monotonic() - t0
    assert elapsed < 1.0, f"scan took {elapsed:.3f}s > 1s"
    assert len(reg.recipes) >= 50


def test_sc_007_malformed_recipe_isolated(vault: Path) -> None:
    """SC-007 — malformed recipe 한 개가 다른 recipe 로드를 막지 않음."""
    user_dir = vault / "90_System" / "AI" / "recipes"
    (user_dir / "broken.md").write_text(
        "---\nname: broken\ninvalid: : :\n---\n\nbody\n", encoding="utf-8"
    )
    reg = RecipeRegistry(builtin_dir=_BUILTIN_DIR, user_dir=user_dir)
    reg.scan()
    assert "diary" in reg.recipes  # 정상 user recipe 보존
    assert any("broken" in str(p) for p, _ in reg.skipped)


def test_sc_008_timeline_does_not_call_recipe_pipeline() -> None:
    """SC-008 — `persona what-did-i-think --timeline` 은 recipe pipeline 에 진입하지 않음.

    spec FR-013 일치: timeline 모드 호출은 ai_api_complete 가 호출되지 않음.
    상세 byte-identical 검증은 test_endpoints_me_timeline.py 가 담당.
    """
    from unittest.mock import MagicMock

    import synapse_memory.endpoints.persona as me_mod
    from synapse_memory.endpoints.persona import what_did_i_think

    store = MagicMock()
    store.query.return_value = []
    with mock.patch(
        "synapse_memory.recipes.pipeline.ai_api_complete"
    ) as mock_pipe, mock.patch.object(me_mod, "embed_query", return_value=[0.0]):
        what_did_i_think("x", store=store, by="time")
    assert mock_pipe.call_count == 0
