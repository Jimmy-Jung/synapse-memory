# Implementation Plan: 외부 데이터 수집기 확장 (Collectors v2)

**Branch**: `release/1.14.0` | **Date**: 2026-05-18 | **Spec**: [spec.md](./spec.md)

## Summary

현재 컬렉터는 `claude_code` / `codex` / `obsidian` 3종뿐. 사용자 본인이 남기는 흔적은 훨씬 넓다 — shell, 다른 AI 도구, 글쓰기 앱, 커뮤니케이션, 행동 신호. 본 sprint에서는 **Tier 1 (file-mirror 패턴 재활용 가능, PII 가벼움) 5종을 ship**하고 Tier 2~4 (10종)는 골격 + spec 만 남기고 후속 sprint 에서 단계 진행.

### 본 sprint 범위 (Tier 1, 5개)

| # | 컬렉터 | 소스 | 패턴 |
|---|---|---|---|
| 1 | `shell_history` | `~/.zsh_history`, `~/.bash_history` | `mirror_jsonl` 재사용 (텍스트 append-only) |
| 2 | `cursor` | `~/Library/Application Support/Cursor/User/workspaceStorage/*/state.vscdb` + `~/.cursor/` | SQLite read-only copy + JSON mirror |
| 3 | `continue_dev` | `~/.continue/sessions/*.json` | JSON 파일 단위 mirror (obsidian 패턴) |
| 4 | `aider` | `~/.aider.chat.history.md`, `~/.aider.input.history` | `mirror_jsonl` 재사용 |
| 5 | `git_self` | 사용자 소유 repo 의 본인 commit log + patch | git plumbing → JSONL 직렬화 후 mirror |

### 후속 sprint 범위 (Tier 2~4, 10개)

| Tier | 컬렉터 | 비고 |
|---|---|---|
| 2 | `apple_notes` | NoteStore.sqlite read-only + 텍스트 export |
| 2 | `day_one` | Day One JSON export 또는 SQLite |
| 2 | `vscode_local_history` | `~/Library/Application Support/Code/User/History/` |
| 3 | `imessage` | `~/Library/Messages/chat.db` — **Full Disk Access 필수**, redact 강제 |
| 3 | `gmail_sent` | Gmail API + OAuth, Sent 라벨만 |
| 3 | `calendar` | EventKit (PyObjC) 또는 ICS export |
| 4 | `browser_history` | Chrome/Safari/Arc SQLite, read-only copy |
| 4 | `screen_time` | `knowledgeC.db` 앱 사용시간 |
| 4 | `apple_health` | Apple Health export.zip 수동 import |

## Constitution Check

| 원칙 | 결과 | 근거 |
|---|---|---|
| I. Local-First & Privacy | ✅ | Tier 1~2/4 전부 로컬. Tier 3 `gmail_sent` 만 외부 API (사용자 본인 데이터, OAuth) |
| II. Two-Pass Redaction | ✅ | mirror 단계는 raw 그대로. redact 는 별도 stage (이미 daily 파이프라인에 존재) |
| III. Test-First Discipline | ✅ | 컬렉터마다 ≥6 시나리오 (수집 / 제외 / idempotent / incremental / 권한 / 누락 home) |
| IV. Conversation-Context-Aware | ✅ N/A | |
| V. Reproducible Pipeline | ✅ | daily.py 에 stage 추가 — quick 모드 동일 cutoff 적용 |
| VI. Installation Consent Scoping | ⚠️ | Tier 3 (imessage / gmail / calendar) 는 opt-in 명시 필요. `~/.synapse/config.yaml` 에 `collectors.enabled` 화이트리스트로 제어 |

## Phase 1: Tier 1 Design (본 sprint)

### 공통 패턴 — 신규 컬렉터 5종 모두 동일 구조

```
src/synapse_memory/collectors/<name>/
    __init__.py     # public surface
    mirror.py       # 수집 로직
tests/test_<name>_mirror.py
```

`mirror.py` 는 `claude_code.mirror.mirror_jsonl` 또는 `obsidian.mirror` 의 sha256
diff 패턴 중 적합한 쪽 재사용. 신규 인프라 코드는 최소화.

### daily.py 통합

`DAILY_STAGES` 에 5개 `collect_*` stage 추가. 위치는 `collect_codex` 직후 (다른 AI/dev 활동 묶음). `update_profile.requires` 에는 추가하지 않는다 (profile 추출은 기존 3종으로 충분, 향후 별도 PR 에서 평가).

```python
DAILY_STAGES = (
    DailyStage("collect_claude_code", "Claude Code 로그 mirror"),
    DailyStage("collect_codex",       "Codex CLI 로그 mirror"),
    DailyStage("collect_shell",       "Shell history mirror"),       # NEW
    DailyStage("collect_cursor",      "Cursor IDE 로그 mirror"),     # NEW
    DailyStage("collect_continue",    "Continue.dev 세션 mirror"),   # NEW
    DailyStage("collect_aider",       "Aider 대화 mirror"),          # NEW
    DailyStage("collect_git_self",    "본인 Git commit mirror"),     # NEW
    DailyStage("collect_obsidian",    "Obsidian vault mirror"),
    ...
)
```

각 stage 의 `_humanize_stage_summary` 에 한국어 요약 분기 추가.

### Affected modules

| 파일 | 변경 |
|---|---|
| `src/synapse_memory/collectors/shell_history/{__init__,mirror}.py` | 신규 |
| `src/synapse_memory/collectors/cursor/{__init__,mirror}.py` | 신규 |
| `src/synapse_memory/collectors/continue_dev/{__init__,mirror}.py` | 신규 |
| `src/synapse_memory/collectors/aider/{__init__,mirror}.py` | 신규 |
| `src/synapse_memory/collectors/git_self/{__init__,mirror}.py` | 신규 |
| `src/synapse_memory/daily.py` | 5 stage 추가 + summary humanize |
| `tests/test_shell_history_mirror.py` | 신규 |
| `tests/test_cursor_mirror.py` | 신규 |
| `tests/test_continue_dev_mirror.py` | 신규 |
| `tests/test_aider_mirror.py` | 신규 |
| `tests/test_git_self_mirror.py` | 신규 |
| `docs/reference.md` | "외부 데이터 수집기" 섹션 확장 |

### TDD 순서 (각 컬렉터 동일)

1. **Red**: `test_<name>_mirror.py` — 정상 수집 / idempotent / incremental / 잡파일 제외 / 권한 / 누락 home
2. **Green**: `mirror.py` 구현
3. **Refactor**: 패턴 통일 (`mirror_jsonl` 재사용 가능한 경우 그대로)
4. **Integration**: `daily.py` stage 등록 + `TestDailyStageWiring` sanity 추가

## Phase 2~4: Tier 2~4 Design (후속 sprint)

별도 PR. 각 Tier 진입 시 spec 확장 + 별도 sprint 처리.

### Tier 3 PII 정책 (사전 결정)

- `imessage` / `gmail_sent` / `calendar` 는 **opt-in 필수**.
- `~/.synapse/config.yaml`:
  ```yaml
  collectors:
    enabled:
      - claude_code
      - codex
      - obsidian
      - shell_history
      - cursor
      - continue_dev
      - aider
      - git_self
    # opt-in 필요:
    # - imessage
    # - gmail_sent
    # - calendar
  ```
- 비활성 컬렉터는 daily stage 에서 `StageStatus.SKIPPED` (skip_reason="opt-out").

## Risks / Open Questions

- **shell_history**: zsh `EXTENDED_HISTORY` 미설정 사용자는 timestamp 없음 — 그래도 텍스트 mirror 는 의미 있음 (line 자체에 가치).
- **cursor**: SQLite 파일은 Cursor 실행 중 lock 가능 → `sqlite3 immutable=1` URI 또는 `.shm`/`.wal` 함께 copy 후 처리.
- **git_self**: "owned repo" 의 정의 — 본 sprint 에선 `git config user.email == <self>` 인 모든 repo. 디렉토리 root 는 환경변수 `SYNAPSE_GIT_SELF_ROOTS` (콜론 구분) 로 지정.

## Success Criteria

- Tier 1 5개 컬렉터 모두 `pytest tests/test_<name>_mirror.py` 통과.
- `pytest tests/` 전체 회귀 통과.
- `synapse-memory daily --quick` 로 Tier 1 5개 stage 모두 ≤2s 끝남 (각 home 디렉토리 비어있어도 graceful).
- `docs/reference.md` 의 "외부 데이터 수집기" 표가 8종 (기존 3 + 신규 5) 으로 확장.
