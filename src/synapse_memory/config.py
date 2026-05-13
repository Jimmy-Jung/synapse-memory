"""사용자 설정 single source of truth — ``~/.synapse/config.yaml``.

우선순위 (12-factor 변형):

    CLI 인자 > 환경변수 > config.yaml > 코드 default

카테고리 분류:
- A (자유 변경): vault, ai_provider, models.*, top_k.*, cleanup.*, profile.*, cost.*,
  interactive_guard.*, automation.*
- C (advanced — 경고 후 변경): advanced.rag.*, advanced.llm.*
- D (보안 핵심 — config 노출 X, set 시도 시 차단):
  ``storage.l0_permissions``, ``redaction.pass1_patterns``,
  ``redaction.pass2_enabled``, ``cleanup.protected_paths``

저자: JunyoungJung
작성일: 2026-05-13
"""

from __future__ import annotations

import datetime
import os
import tempfile
import typing
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG_PATH = Path.home() / ".synapse" / "config.yaml"


@dataclass
class ClaudeModelsConfig:
    """Claude 모델 이름 — haiku / sonnet / opus 체계."""

    classify: str = "haiku"
    card_generate: str = "sonnet"
    ask: str | None = None  # None = provider default (sonnet)
    decide: str | None = None
    resume: str | None = None
    recall: str | None = None
    update_profile: str | None = None


@dataclass
class CodexModelsConfig:
    """Codex 모델 이름 — gpt-5.4 등 OpenAI 체계."""

    classify: str = "gpt-5.4"
    card_generate: str = "gpt-5.4"
    ask: str | None = None  # None = provider default (gpt-5.4)
    decide: str | None = None
    resume: str | None = None
    recall: str | None = None
    update_profile: str | None = None


@dataclass
class ModelsConfig:
    """task별 모델 — provider 분리.

    ``ai_provider`` 값에 따라 ``models.claude.*`` 또는 ``models.codex.*``가 사용됨.
    ``ai_provider: auto``일 때는 detect_ai_environment가 자체 default로 폴백.
    """

    claude: ClaudeModelsConfig = field(default_factory=ClaudeModelsConfig)
    codex: CodexModelsConfig = field(default_factory=CodexModelsConfig)


@dataclass
class TopKConfig:
    ask: int = 5
    decide: int = 6
    recall: int = 8
    resume: int = 6
    rag_search: int = 5


@dataclass
class CleanupConfig:
    inbox_stale_days: int = 30
    dormant_project_days: int = 90
    old_resume_days: int = 90
    stale_memory_inbox_days: int = 60
    old_daily_reports_days: int = 90


@dataclass
class ProfileConfig:
    sample_lines: int = 200


@dataclass
class CostConfig:
    summary_days: int = 30
    monthly_cap_usd: float | None = None  # 미구현, 키만 예약


@dataclass
class InteractiveGuardConfig:
    enabled: bool = True
    delay_seconds: int = 3


@dataclass
class CodexPollerConfig:
    enabled: bool = True


@dataclass
class DailyCronConfig:
    enabled: bool = False
    time: str = "08:00"


@dataclass
class AutomationConfig:
    codex_poller: CodexPollerConfig = field(default_factory=CodexPollerConfig)
    daily_cron: DailyCronConfig = field(default_factory=DailyCronConfig)


@dataclass
class AdvancedRagConfig:
    rrf_k: int = 60
    embedding_model: str = "bge-m3"  # 변경 시 색인 재생성 필요


@dataclass
class AdvancedLLMConfig:
    claude_timeout_seconds: int = 60
    codex_timeout_seconds: int = 240


@dataclass
class AdvancedConfig:
    rag: AdvancedRagConfig = field(default_factory=AdvancedRagConfig)
    llm: AdvancedLLMConfig = field(default_factory=AdvancedLLMConfig)


@dataclass
class SynapseConfig:
    vault: str | None = None
    ai_provider: str = "claude"  # claude | codex | auto
    models: ModelsConfig = field(default_factory=ModelsConfig)
    top_k: TopKConfig = field(default_factory=TopKConfig)
    cleanup: CleanupConfig = field(default_factory=CleanupConfig)
    profile: ProfileConfig = field(default_factory=ProfileConfig)
    cost: CostConfig = field(default_factory=CostConfig)
    interactive_guard: InteractiveGuardConfig = field(default_factory=InteractiveGuardConfig)
    automation: AutomationConfig = field(default_factory=AutomationConfig)
    advanced: AdvancedConfig = field(default_factory=AdvancedConfig)


ADVANCED_PREFIXES: tuple[str, ...] = ("advanced.",)

PROTECTED_PREFIXES: tuple[str, ...] = (
    "storage.l0_permissions",
    "redaction.pass1_patterns",
    "redaction.pass2_enabled",
    "cleanup.protected_paths",
)


def is_advanced_path(path: str) -> bool:
    """advanced 섹션 키인지 — set 전 경고 대상."""
    return path.startswith(ADVANCED_PREFIXES)


def is_protected_path(path: str) -> bool:
    """config로 변경 불가한 보안 핵심 키인지 — set 시 차단."""
    return any(path == p or path.startswith(p + ".") for p in PROTECTED_PREFIXES)


def _from_dict(cls, data: dict | None) -> Any:
    """nested dataclass를 dict에서 만들어줌. 알 수 없는 키는 무시."""
    if data is None or not isinstance(data, dict):
        return cls()
    try:
        annotations = typing.get_type_hints(cls)
    except Exception:  # noqa: BLE001
        annotations = getattr(cls, "__annotations__", {})
    kwargs: dict[str, Any] = {}
    for field_name, field_type in annotations.items():
        if field_name not in data:
            continue
        value = data[field_name]
        if isinstance(value, dict) and is_dataclass(field_type):
            kwargs[field_name] = _from_dict(field_type, value)
        else:
            kwargs[field_name] = value
    return cls(**kwargs)


def load_config(path: Path | None = None) -> SynapseConfig:
    """yaml에서 SynapseConfig 로드. 파일 없거나 빈 경우 default 반환."""
    path = path or DEFAULT_CONFIG_PATH
    if not path.exists():
        return SynapseConfig()
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return SynapseConfig()
    if not isinstance(raw, dict):
        return SynapseConfig()
    return _from_dict(SynapseConfig, raw)


def save_config(
    cfg: SynapseConfig, path: Path | None = None, *, make_backup: bool = True
) -> Path:
    """atomic write + 기존 파일이 있으면 백업."""
    path = path or DEFAULT_CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    if make_backup and path.exists():
        ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = path.with_name(f"{path.name}.bak-{ts}")
        backup.write_bytes(path.read_bytes())

    text = yaml.safe_dump(
        asdict(cfg),
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    fd, tmp = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def get_value(cfg: SynapseConfig, dotted_path: str) -> Any:
    """`cleanup.inbox_stale_days` 같은 점 표기로 값 조회."""
    parts = dotted_path.split(".")
    obj: Any = cfg
    for p in parts:
        if not hasattr(obj, p):
            raise KeyError(f"알 수 없는 키: {dotted_path}")
        obj = getattr(obj, p)
    return obj


def _parse_value(raw: Any, target_type_str: str) -> Any:
    """문자열 입력을 dataclass 필드 타입으로 변환."""
    if not isinstance(raw, str):
        return raw
    s = raw.strip()
    t = str(target_type_str)
    if "bool" in t:
        if s.lower() in ("true", "yes", "on", "1"):
            return True
        if s.lower() in ("false", "no", "off", "0"):
            return False
        raise ValueError(f"bool로 파싱 불가: {raw!r}")
    if "int | None" in t or "int|None" in t:
        return None if s.lower() in ("none", "null", "") else int(s)
    if "float | None" in t or "float|None" in t:
        return None if s.lower() in ("none", "null", "") else float(s)
    if "str | None" in t or "str|None" in t:
        return None if s.lower() in ("none", "null", "") else s
    if t == "int":
        return int(s)
    if t == "float":
        return float(s)
    return s


def set_value(cfg: SynapseConfig, dotted_path: str, value: Any) -> None:
    """`cleanup.inbox_stale_days=60` 같은 점 표기로 값 설정.

    카테고리 D(보안 핵심)는 ValueError. 알 수 없는 키도 KeyError.
    """
    if is_protected_path(dotted_path):
        raise ValueError(
            f"보호된 키 — config로 변경 불가: {dotted_path} "
            f"(보안 핵심 — 코드 수정·PR로만)"
        )
    parts = dotted_path.split(".")
    obj: Any = cfg
    for p in parts[:-1]:
        if not hasattr(obj, p):
            raise KeyError(f"알 수 없는 키: {dotted_path}")
        obj = getattr(obj, p)
    leaf = parts[-1]
    annotations = getattr(type(obj), "__annotations__", {})
    if leaf not in annotations:
        raise KeyError(f"알 수 없는 키: {dotted_path}")
    target_type = annotations[leaf]
    parsed = _parse_value(value, str(target_type))
    setattr(obj, leaf, parsed)


def validate_config(cfg: SynapseConfig) -> list[str]:
    """타입·범위 검증. 위반 메시지 리스트 (빈 리스트면 OK)."""
    errors: list[str] = []

    if cfg.ai_provider not in ("claude", "codex", "auto"):
        errors.append(
            f"ai_provider는 claude/codex/auto 중 하나 — 현재: {cfg.ai_provider!r}"
        )

    for field_name in (
        "inbox_stale_days",
        "dormant_project_days",
        "old_resume_days",
        "stale_memory_inbox_days",
        "old_daily_reports_days",
    ):
        v = getattr(cfg.cleanup, field_name)
        if not isinstance(v, int) or v < 1:
            errors.append(f"cleanup.{field_name}는 1 이상 정수 — 현재: {v!r}")

    for field_name in ("ask", "decide", "recall", "resume", "rag_search"):
        v = getattr(cfg.top_k, field_name)
        if not isinstance(v, int) or v < 1 or v > 50:
            errors.append(f"top_k.{field_name}는 1~50 — 현재: {v!r}")

    if not isinstance(cfg.profile.sample_lines, int) or cfg.profile.sample_lines < 10:
        errors.append(
            f"profile.sample_lines는 10 이상 — 현재: {cfg.profile.sample_lines!r}"
        )

    if cfg.interactive_guard.delay_seconds < 0:
        errors.append("interactive_guard.delay_seconds는 0 이상")

    if cfg.cost.summary_days < 1:
        errors.append("cost.summary_days는 1 이상")

    return errors


def _flatten(obj: Any, prefix: str = "") -> dict[str, Any]:
    """dataclass / dict → 점 표기 평탄화."""
    out: dict[str, Any] = {}
    if is_dataclass(obj) and not isinstance(obj, type):
        data = asdict(obj)
    elif isinstance(obj, dict):
        data = obj
    else:
        out[prefix.rstrip(".")] = obj
        return out
    for k, v in data.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flatten(v, prefix=key + "."))
        else:
            out[key] = v
    return out


def render_config(cfg: SynapseConfig, *, show_advanced: bool = False) -> str:
    """사람용 한 페이지 요약. advanced 섹션은 옵션."""
    flat = _flatten(cfg)
    lines: list[str] = []
    lines.append(f"# config: {DEFAULT_CONFIG_PATH}")
    lines.append("")
    sections: dict[str, list[tuple[str, Any]]] = {}
    for key, val in flat.items():
        top = key.split(".")[0]
        if top == "advanced" and not show_advanced:
            continue
        sections.setdefault(top, []).append((key, val))
    for top in (
        "vault",
        "ai_provider",
        "models",
        "top_k",
        "cleanup",
        "profile",
        "cost",
        "interactive_guard",
        "automation",
        "advanced",
    ):
        if top not in sections:
            continue
        lines.append(f"[{top}]")
        for key, val in sections[top]:
            display_val = "(미설정)" if val is None else val
            advanced_marker = " ⚠ advanced" if is_advanced_path(key) else ""
            lines.append(f"  {key} = {display_val}{advanced_marker}")
        lines.append("")
    if not show_advanced:
        lines.append("(advanced 섹션은 `synapse-memory config show --advanced`로 확인)")
    return "\n".join(lines).rstrip()


_cached: SynapseConfig | None = None
_cached_mtime: float | None = None


def get_config(*, refresh: bool = False) -> SynapseConfig:
    """프로세스 단위 캐시된 config 반환. config 파일 mtime 변경 시 자동 reload."""
    global _cached, _cached_mtime  # noqa: PLW0603
    path = DEFAULT_CONFIG_PATH
    current_mtime = path.stat().st_mtime if path.exists() else None
    if refresh or _cached is None or current_mtime != _cached_mtime:
        _cached = load_config(path)
        _cached_mtime = current_mtime
    return _cached


def clear_cache() -> None:
    """테스트용 캐시 무효화."""
    global _cached, _cached_mtime  # noqa: PLW0603
    _cached = None
    _cached_mtime = None
