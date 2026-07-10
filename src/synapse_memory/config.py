"""사용자 설정 single source of truth — ``~/.synapse/config.yaml``.

우선순위 (12-factor 변형):

    CLI 인자 > 환경변수 > config.yaml > 코드 default

카테고리 분류:
- A (자유 변경): vault, ai_provider, models.*, top_k.*, cleanup.*, profile.*, cost.*,
  interactive_guard.*, automation.*
- C (advanced — 경고 후 변경): advanced.llm.*
- D (보안 핵심 — config 노출 X, set 시도 시 차단):
  ``storage.l0_permissions``, ``cleanup.protected_paths``

저자: JunyoungJung
작성일: 2026-05-13
"""

from __future__ import annotations

import contextlib
import datetime
import os
import tempfile
import typing
from dataclasses import asdict, dataclass, field, is_dataclass, replace
from pathlib import Path
from typing import Any, TypeVar, cast

import yaml

DEFAULT_CONFIG_PATH = Path.home() / ".synapse" / "config.yaml"
DEFAULT_VAULT_PATH = (
    Path.home() / "Library/Mobile Documents/iCloud~md~obsidian/Documents"
)
ENV_VAR_VAULT = "SYNAPSE_OBSIDIAN_VAULT"
T = TypeVar("T")


@dataclass
class ModelTasksConfig:
    """task별 기본 모델 이름."""

    classify: str = "gpt-5.5"
    card_generate: str = "gpt-5.5"
    ask: str | None = None  # None = provider default
    decide: str | None = None
    resume: str | None = None
    recall: str | None = None
    update_profile: str | None = None
    generate: str | None = None
    # 020: provider-only 관련 페이지 선별(LLM-as-retriever). 싼 티어.
    relevance: str = "gpt-5.5"


@dataclass
class ProviderModelOverrideConfig:
    """provider별 task 모델 override. None이면 task 기본값 사용."""

    default: str | None = None  # task 기본값도 None일 때 쓸 provider 기본 모델
    classify: str | None = None
    card_generate: str | None = None
    ask: str | None = None
    decide: str | None = None
    resume: str | None = None
    recall: str | None = None
    update_profile: str | None = None
    generate: str | None = None
    relevance: str | None = None


@dataclass
class ProviderModelOverridesConfig:
    claude: ProviderModelOverrideConfig = field(
        default_factory=lambda: ProviderModelOverrideConfig(
            default="sonnet",
            classify="haiku",
            card_generate="sonnet",
            relevance="haiku",
        )
    )
    codex: ProviderModelOverrideConfig = field(
        # Sol=복잡한 합성, Terra=일상 통합, Luna=대량 선별.
        default_factory=lambda: ProviderModelOverrideConfig(
            default="gpt-5.6-terra",
            classify="gpt-5.6-luna",
            card_generate="gpt-5.6-terra",
            ask="gpt-5.6-sol",
            decide="gpt-5.6-sol",
            resume="gpt-5.6-sol",
            recall="gpt-5.6-terra",
            update_profile="gpt-5.6-terra",
            generate="gpt-5.6-terra",
            relevance="gpt-5.6-luna",
        )
    )


# provider별 기본 모델 안전망 (config가 provider default 미지정 시).
_PROVIDER_FALLBACK_MODEL: dict[str, str] = {
    "codex": "gpt-5.6-terra",
    "claude": "sonnet",
}

_V2_0_1_TASK_DEFAULTS: dict[str, str | None] = {
    "classify": "gpt-5.5",
    "card_generate": "gpt-5.5",
    "ask": None,
    "decide": None,
    "resume": None,
    "recall": None,
    "update_profile": None,
    "relevance": "gpt-5.5",
}
_V2_0_1_CODEX_OVERRIDE_DEFAULTS: dict[str, str | None] = {
    "default": "gpt-5.5",
    **{task: None for task in _V2_0_1_TASK_DEFAULTS},
}
_V2_0_1_TASK_KEYS = frozenset(_V2_0_1_TASK_DEFAULTS)
_V2_0_1_CODEX_OVERRIDE_KEYS = frozenset(_V2_0_1_CODEX_OVERRIDE_DEFAULTS)
_CODEX_TASK_OVERRIDE_KEYS = _V2_0_1_TASK_KEYS | {"generate"}


@dataclass
class ModelsConfig:
    """task별 기본 모델 + provider override."""

    tasks: ModelTasksConfig = field(default_factory=ModelTasksConfig)
    overrides: ProviderModelOverridesConfig = field(
        default_factory=ProviderModelOverridesConfig
    )

    def model_for_task(self, provider: str, task: str) -> str | None:
        if not hasattr(self.tasks, task):
            return None
        base: str | None = getattr(self.tasks, task)
        provider_overrides: ProviderModelOverrideConfig | None = getattr(
            self.overrides, provider, None
        )
        override = (
            getattr(provider_overrides, task, None)
            if provider_overrides is not None
            else None
        )
        resolved = override if override is not None else base
        if resolved is not None:
            return resolved
        # task 기본값도 None → provider 기본 모델로 폴백 (codex=Terra, claude=sonnet).
        # config가 provider default를 지정하지 않았을 때의 안전망.
        provider_default = getattr(provider_overrides, "default", None)
        return provider_default or _PROVIDER_FALLBACK_MODEL.get(provider)


@dataclass
class TopKConfig:
    ask: int = 5
    decide: int = 6
    recall: int = 8
    resume: int = 6


@dataclass
class CleanupConfig:
    inbox_stale_days: int = 30
    dormant_project_days: int = 90
    old_resume_days: int = 90
    stale_memory_inbox_days: int = 60
    old_daily_reports_days: int = 90


@dataclass
class VaultCreativeFoldersConfig:
    root: str = "30_Creative"
    drafts: str = "30_Creative/Drafts"


@dataclass
class VaultSystemAiFoldersConfig:
    root: str = "90_System/AI"
    memory_inbox: str = "90_System/AI/MemoryInbox"
    daily_reports: str = "90_System/AI/DailyReports"
    cleanup_reports: str = "90_System/AI/CleanupReports"
    recipes: str = "90_System/AI/recipes"
    profile: str = "90_System/AI/Profile.md"
    decision_patterns: str = "90_System/AI/DecisionPatterns.md"


@dataclass
class VaultSystemFoldersConfig:
    root: str = "90_System"
    ai: VaultSystemAiFoldersConfig = field(default_factory=VaultSystemAiFoldersConfig)
    attachments: str = "90_System/Attachments"
    migration: str = "90_System/_migration"


@dataclass
class VaultWikiFoldersConfig:
    """v2 wiki 페이지 폴더 — vault root 기준 상대 경로.

    Karpathy LLM-wiki 패턴의 entity/concept/profile/insight 페이지 저장 위치.
    """

    projects: str = "Entities/Projects"
    companies: str = "Entities/Companies"
    people: str = "Entities/People"
    concepts: str = "Concepts"
    profile: str = "Profile"
    insights: str = "Insights"


@dataclass
class VaultFoldersConfig:
    """vault 내부 폴더 경로.

    모든 값은 vault root 기준 상대 경로다. 기본값은 기존 PARA 구조를 보존한다.
    """

    inbox: str = "00_Inbox"
    active: str = "10_Active"
    creative: VaultCreativeFoldersConfig = field(default_factory=VaultCreativeFoldersConfig)
    life: str = "40_Life"
    archive: str = "40_Archive"
    system: VaultSystemFoldersConfig = field(default_factory=VaultSystemFoldersConfig)
    wiki: VaultWikiFoldersConfig = field(default_factory=VaultWikiFoldersConfig)


@dataclass
class ProfileConfig:
    sample_lines: int = 200
    # 사용자가 /sm:apply-profile 에서 No 한 fact/pattern 을 _dismissed.jsonl 에
    # 기록하고, TTL 일수가 지나면 다시 후보로 노출. 0 이면 영구 dismiss.
    # 아래 reason 별 override 가 우선; reason="" / "other" 는 이 기본값 사용.
    dismissed_ttl_days: int = 90
    # reason 별 TTL 차등 — 의미별 적절한 차단 기간 (의미는 dismissed.py 참고).
    # 사용자 성향 변경은 짧게(빠른 재확인), 단순 noise 는 길게(불필요 재질문 차단).
    dismissed_ttl_user_changed: int = 30
    dismissed_ttl_misclassified: int = 90
    dismissed_ttl_one_time: int = 180
    dismissed_ttl_irrelevant: int = 365
    # 추출 ledger 기반 multi-day cross-validation — 같은 fact 가 K일 중 M번
    # 이상 추출돼야 candidate. 일시 변덕 / LLM noise 제거.
    promotion_min_count: int = 3
    promotion_window_days: int = 14
    # 단일 호출 confidence 가 이 값 이상이면 즉시 promote (fast path).
    # 0.95 는 LLM 출력 confidence 가 도달하기 너무 빠듯해서 (실측상 peak 가
    # 대부분 0.80~0.92 구간) 의미 있는 신호도 fast path 를 못 타고 누적만 되는
    # 문제가 발생. 0.90 으로 완화 — dedupe/dismissed 안전망이 vault 진입 전
    # 다시 거름.
    fast_path_confidence: float = 0.90


@dataclass
class CostConfig:
    summary_days: int = 30
    monthly_cap_usd: float | None = None  # 미구현, 키만 예약


@dataclass
class InteractiveGuardConfig:
    enabled: bool = True
    delay_seconds: int = 3


@dataclass
class HookConfig:
    enabled: bool = True
    max_inject_bytes: int = 2048
    suggest_register: bool = False


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
class MaintenanceConfig:
    """v2 wiki 자동 유지엔진 설정.

    engine: wiki 통합/lint를 수행할 CLI ("claude" | "codex"). 설치 시 선택.
    idle_minutes: watch 데몬이 "대화 종료"로 간주하는 무변경 임계값(분).
    """

    engine: str = "codex"
    # 토큰 절감: live 세션 jsonl이 자라며 settled를 반복 통과해 전문 재청구되는 것을
    # 막으려 30분으로 상향. 대화 종료 후 1회만 ingest(갱신 ~30분 지연 트레이드오프).
    idle_minutes: int = 30
    # 020: bounded 단명 잡 — 사이클당 doc 상한(메모리 천장) + 스케줄 주기(분).
    # 사이클당 LLM 호출 천장. checkpoint_each=True라 초과분은 다음 사이클로 무손실 이월.
    max_docs_per_cycle: int = 10
    # 토큰 절감: wakeup 빈도 ↓ (72→24회/일). idle_minutes(30)와 스케일 일치.
    # 변경 시 launchd plist 재설치 필요(StartInterval에 구워짐).
    interval_minutes: int = 60


@dataclass
class AdvancedLLMConfig:
    claude_timeout_seconds: int = 60
    codex_timeout_seconds: int = 240


@dataclass
class AdvancedConfig:
    llm: AdvancedLLMConfig = field(default_factory=AdvancedLLMConfig)


@dataclass
class SynapseConfig:
    vault: str | None = None
    vault_folders: VaultFoldersConfig = field(default_factory=VaultFoldersConfig)
    ai_provider: str = "codex"  # claude | codex | auto
    models: ModelsConfig = field(default_factory=ModelsConfig)
    top_k: TopKConfig = field(default_factory=TopKConfig)
    cleanup: CleanupConfig = field(default_factory=CleanupConfig)
    profile: ProfileConfig = field(default_factory=ProfileConfig)
    cost: CostConfig = field(default_factory=CostConfig)
    interactive_guard: InteractiveGuardConfig = field(default_factory=InteractiveGuardConfig)
    hook: HookConfig = field(default_factory=HookConfig)
    automation: AutomationConfig = field(default_factory=AutomationConfig)
    maintenance: MaintenanceConfig = field(default_factory=MaintenanceConfig)
    advanced: AdvancedConfig = field(default_factory=AdvancedConfig)


@dataclass(frozen=True)
class PrivacyMode:
    """현재 데이터 흐름의 외부 provider 전송 경계."""

    ingest: str
    query: str
    note: str


ADVANCED_PREFIXES: tuple[str, ...] = ("advanced.",)

PROTECTED_PREFIXES: tuple[str, ...] = (
    "storage.l0_permissions",
    "cleanup.protected_paths",
)


def is_advanced_path(path: str) -> bool:
    """advanced 섹션 키인지 — set 전 경고 대상."""
    return path.startswith(ADVANCED_PREFIXES)


def describe_privacy_mode(cfg: SynapseConfig) -> PrivacyMode:
    """현재 설정 기준 privacy/dataflow 정책을 사람이 읽을 수 있게 요약한다."""
    if cfg.maintenance.engine in {"claude", "codex"}:
        return PrivacyMode(
            ingest="raw_or_sampled_raw_to_provider",
            query="wiki_cards_and_approved_profile_to_provider",
            note=(
                "ingest/backfill/watch may send small raw docs or sampled raw text "
                "to the configured provider; query paths use wiki/cards/approved profile."
            ),
        )
    return PrivacyMode(
        ingest="local_only_or_disabled",
        query="provider_dependent",
        note="maintenance ingest is not configured for a supported provider engine.",
    )


def is_protected_path(path: str) -> bool:
    """config로 변경 불가한 보안 핵심 키인지 — set 시 차단."""
    return any(path == p or path.startswith(p + ".") for p in PROTECTED_PREFIXES)


def _from_dict(
    cls: type[T],
    data: dict[str, Any] | None,
    *,
    defaults: T | None = None,
) -> T:
    """nested dataclass를 dict에서 만들되 부모의 default_factory를 보존한다."""
    if data is None or not isinstance(data, dict):
        return defaults if defaults is not None else cls()
    default_value = defaults if defaults is not None else cls()
    try:
        annotations = typing.get_type_hints(cls)
    except Exception:
        annotations = getattr(cls, "__annotations__", {})
    kwargs: dict[str, Any] = {}
    for field_name, field_type in annotations.items():
        if field_name not in data:
            continue
        value = data[field_name]
        if isinstance(value, dict) and is_dataclass(field_type):
            kwargs[field_name] = _from_dict(
                cast(type[Any], field_type),
                value,
                defaults=getattr(default_value, field_name),
            )
        else:
            kwargs[field_name] = value
    return cast(T, replace(cast(Any, default_value), **kwargs))


def _normalize_config_raw(raw: dict[str, Any]) -> dict[str, Any]:
    """config.yaml 입력 호환성 정규화.

    기존 형식은 ``vault: /path`` 문자열이다. 이슈 #12에서 제안된 nested 형식
    ``vault: {path: /path, folders: ...}``도 받아서 내부 canonical 필드
    ``vault_folders``로 옮긴다.
    """
    normalized = dict(raw)
    models_value = normalized.get("models")
    if isinstance(models_value, dict):
        legacy_providers = {
            key: value
            for key, value in models_value.items()
            if key in {"claude", "codex"} and isinstance(value, dict)
        }
        if legacy_providers and "tasks" not in models_value and "overrides" not in models_value:
            codex_defaults = legacy_providers.get("codex", {})
            normalized["models"] = {
                "tasks": codex_defaults,
                "overrides": legacy_providers,
            }

    models_value = normalized.get("models")
    if isinstance(models_value, dict):
        overrides = models_value.get("overrides")
        codex_overrides = overrides.get("codex") if isinstance(overrides, dict) else None
        raw_tasks = models_value.get("tasks")
        task_values = raw_tasks if isinstance(raw_tasks, dict) else {}
        # 전체 v2.0.1 기본 snapshot만 자동 승격한다. 부분 config는 사용자 의도로 보존.
        if (
            isinstance(overrides, dict)
            and isinstance(codex_overrides, dict)
            and set(task_values) == _V2_0_1_TASK_KEYS
            and all(task_values[key] == value for key, value in _V2_0_1_TASK_DEFAULTS.items())
            and set(codex_overrides) == _V2_0_1_CODEX_OVERRIDE_KEYS
            and all(
                codex_overrides[key] == value
                for key, value in _V2_0_1_CODEX_OVERRIDE_DEFAULTS.items()
            )
        ):
            normalized_overrides = dict(overrides)
            normalized_overrides["codex"] = {}
            normalized_models = dict(models_value)
            normalized_models["overrides"] = normalized_overrides
            normalized["models"] = normalized_models
        elif "generate" not in task_values and (
            not isinstance(codex_overrides, dict) or "generate" not in codex_overrides
        ):
            # v2.0.1의 부분 설정에는 역할별 Codex override가 없었다. 새 기본값을
            # 그대로 상속하면 명시한 shared task/default가 가려지므로, 누락값을
            # 명시적 None으로 보완해 기존 우선순위를 보존한다.
            normalized_overrides = dict(overrides) if isinstance(overrides, dict) else {}
            normalized_codex = dict(codex_overrides) if isinstance(codex_overrides, dict) else {}
            changed = False
            if "default" in normalized_codex:
                for task_name in _CODEX_TASK_OVERRIDE_KEYS:
                    if task_name not in normalized_codex:
                        normalized_codex[task_name] = None
                        changed = True
            for task_name in task_values:
                if task_name in _CODEX_TASK_OVERRIDE_KEYS and task_name not in normalized_codex:
                    normalized_codex[task_name] = None
                    changed = True
            if changed:
                normalized_overrides["codex"] = normalized_codex
                normalized_models = dict(models_value)
                normalized_models["overrides"] = normalized_overrides
                normalized["models"] = normalized_models

    vault_value = normalized.get("vault")
    if not isinstance(vault_value, dict):
        return normalized

    vault_path = vault_value.get("path") or vault_value.get("root")
    normalized["vault"] = vault_path if isinstance(vault_path, str) else None

    folders = vault_value.get("folders")
    if isinstance(folders, dict) and "vault_folders" not in normalized:
        normalized["vault_folders"] = folders

    return normalized


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
    return _from_dict(SynapseConfig, _normalize_config_raw(raw))


def save_config(cfg: SynapseConfig, path: Path | None = None, *, make_backup: bool = True) -> Path:
    """atomic write + 기존 파일이 있으면 백업."""
    path = path or DEFAULT_CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    if make_backup and path.exists():
        ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = path.with_name(f"{path.name}.bak-{ts}")
        backup.write_bytes(path.read_bytes())
        _prune_config_backups(path)

    text = yaml.safe_dump(
        asdict(cfg),
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def _prune_config_backups(path: Path, *, keep: int = 3) -> None:
    backups = sorted(path.parent.glob(f"{path.name}.bak-*"), key=lambda p: p.name, reverse=True)
    for backup in backups[keep:]:
        with contextlib.suppress(OSError):
            backup.unlink()


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
            f"보호된 키 — config로 변경 불가: {dotted_path} (보안 핵심 — 코드 수정·PR로만)"
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
        errors.append(f"ai_provider는 claude/codex/auto 중 하나 — 현재: {cfg.ai_provider!r}")

    if cfg.maintenance.engine not in ("claude", "codex"):
        errors.append(
            f"maintenance.engine는 claude/codex 중 하나 — 현재: {cfg.maintenance.engine!r}"
        )

    if cfg.maintenance.idle_minutes < 1:
        errors.append(
            f"maintenance.idle_minutes는 1 이상 — 현재: {cfg.maintenance.idle_minutes}"
        )

    if cfg.maintenance.max_docs_per_cycle < 1:
        errors.append(
            "maintenance.max_docs_per_cycle는 1 이상 — 현재: "
            f"{cfg.maintenance.max_docs_per_cycle}"
        )

    if cfg.maintenance.interval_minutes < 1:
        errors.append(
            "maintenance.interval_minutes는 1 이상 — 현재: "
            f"{cfg.maintenance.interval_minutes}"
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

    for field_name in ("ask", "decide", "recall", "resume"):
        v = getattr(cfg.top_k, field_name)
        if not isinstance(v, int) or v < 1 or v > 50:
            errors.append(f"top_k.{field_name}는 1~50 — 현재: {v!r}")

    if not isinstance(cfg.profile.sample_lines, int) or cfg.profile.sample_lines < 10:
        errors.append(f"profile.sample_lines는 10 이상 — 현재: {cfg.profile.sample_lines!r}")
    if (
        not isinstance(cfg.profile.dismissed_ttl_days, int)
        or cfg.profile.dismissed_ttl_days < 0
    ):
        errors.append(
            "profile.dismissed_ttl_days는 0 이상 정수 — "
            f"현재: {cfg.profile.dismissed_ttl_days!r}"
        )
    for ttl_field in (
        "dismissed_ttl_user_changed",
        "dismissed_ttl_misclassified",
        "dismissed_ttl_one_time",
        "dismissed_ttl_irrelevant",
    ):
        v = getattr(cfg.profile, ttl_field)
        if not isinstance(v, int) or v < 0:
            errors.append(
                f"profile.{ttl_field}는 0 이상 정수 (0=영구 dismiss) — 현재: {v!r}"
            )
    if (
        not isinstance(cfg.profile.promotion_min_count, int)
        or cfg.profile.promotion_min_count < 1
    ):
        errors.append(
            "profile.promotion_min_count는 1 이상 정수 — "
            f"현재: {cfg.profile.promotion_min_count!r}"
        )
    if (
        not isinstance(cfg.profile.promotion_window_days, int)
        or cfg.profile.promotion_window_days < 1
    ):
        errors.append(
            "profile.promotion_window_days는 1 이상 정수 — "
            f"현재: {cfg.profile.promotion_window_days!r}"
        )
    if (
        not isinstance(cfg.profile.fast_path_confidence, (int, float))
        or not 0.0 <= float(cfg.profile.fast_path_confidence) <= 1.0
    ):
        errors.append(
            "profile.fast_path_confidence는 0.0~1.0 — "
            f"현재: {cfg.profile.fast_path_confidence!r}"
        )

    if cfg.interactive_guard.delay_seconds < 0:
        errors.append("interactive_guard.delay_seconds는 0 이상")

    if not isinstance(cfg.hook.max_inject_bytes, int) or cfg.hook.max_inject_bytes < 1:
        errors.append(
            "hook.max_inject_bytes는 1 이상 정수 — "
            f"현재: {cfg.hook.max_inject_bytes!r}"
        )

    if cfg.cost.summary_days < 1:
        errors.append("cost.summary_days는 1 이상")

    for key, value in _flatten(cfg.vault_folders, prefix="vault_folders.").items():
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{key}는 비어 있지 않은 상대 경로 문자열이어야 함")
            continue
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            errors.append(f"{key}는 vault root 기준 안전한 상대 경로여야 함 — 현재: {value!r}")

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
    privacy_mode = describe_privacy_mode(cfg)
    lines: list[str] = []
    lines.append(f"# config: {DEFAULT_CONFIG_PATH}")
    lines.append("")
    lines.append("[privacy_mode]")
    lines.append(f"  ingest = {privacy_mode.ingest}")
    lines.append(f"  query = {privacy_mode.query}")
    lines.append(f"  note = {privacy_mode.note}")
    lines.append("")
    sections: dict[str, list[tuple[str, Any]]] = {}
    for key, val in flat.items():
        top = key.split(".")[0]
        if top == "advanced" and not show_advanced:
            continue
        sections.setdefault(top, []).append((key, val))
    for top in (
        "vault",
        "vault_folders",
        "ai_provider",
        "models",
        "top_k",
        "cleanup",
        "profile",
        "cost",
        "interactive_guard",
        "hook",
        "automation",
        "maintenance",
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
    global _cached, _cached_mtime
    path = DEFAULT_CONFIG_PATH
    current_mtime = path.stat().st_mtime if path.exists() else None
    if refresh or _cached is None or current_mtime != _cached_mtime:
        _cached = load_config(path)
        _cached_mtime = current_mtime
    return _cached


def get_vault_path(*, cfg: SynapseConfig | None = None, refresh_config: bool = False) -> Path:
    """vault 경로 SSOT.

    해석 순서: ``SYNAPSE_OBSIDIAN_VAULT`` env → config.vault → vault detector.
    """
    raw_env = os.environ.get(ENV_VAR_VAULT)
    if raw_env and raw_env.strip():
        return Path(raw_env).expanduser().resolve()

    active_cfg = cfg if cfg is not None else get_config(refresh=refresh_config)
    if active_cfg.vault and active_cfg.vault.strip():
        return Path(active_cfg.vault).expanduser().resolve()

    from synapse_memory.vault_detector import (
        detect_vault_candidates,
        select_default_candidate,
    )

    candidates = detect_vault_candidates()
    candidate = select_default_candidate(candidates) or candidates[0]
    return candidate.path.expanduser().resolve()


def clear_cache() -> None:
    """테스트용 캐시 무효화."""
    global _cached, _cached_mtime
    _cached = None
    _cached_mtime = None
