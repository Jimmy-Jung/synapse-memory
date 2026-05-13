---
description: 사용자 설정 관리 — 자연어로 cleanup 임계값·모델·top_k·자동화 토글 변경 (~/.synapse/config.yaml)
argument-hint: (인자 없음 → 대화형) | "<자연어 변경 지시>" (예: "cleanup inbox 60일로")
---

!`SYNAPSE_FROM_AGENT=1 synapse-memory config show`

위 출력은 현재 효력 있는 설정입니다(default 또는 사용자 변경 반영). **변경 작업은 항상 사용자 동의 후에만**.

## 인자가 있을 때 (자연어 변경)

`$ARGUMENTS`에 자연어 지시가 있으면 → 아래 매핑 표로 적절한 키를 찾아 *변경 미리보기*를 보여주고 동의 받기.

### 자연어 → 키 매핑

| 사용자 표현 패턴 | config 키 |
|---|---|
| "cleanup inbox / 받은편지함 N일" | `cleanup.inbox_stale_days` |
| "휴면 프로젝트 / dormant N일" | `cleanup.dormant_project_days` |
| "이력서 초안 / drafts N일" | `cleanup.old_resume_days` |
| "MemoryInbox / 메모리 인박스 후보 N일" | `cleanup.stale_memory_inbox_days` |
| "DailyReports / 일일 리포트 N일" | `cleanup.old_daily_reports_days` |
| "claude 이력서 모델 opus / sonnet" | `models.claude.resume` |
| "codex 이력서 모델 …" | `models.codex.resume` |
| "claude 카드 생성 모델" | `models.claude.card_generate` |
| "codex 카드 생성 모델" | `models.codex.card_generate` |
| "claude 분류 모델 / codex 분류 모델" | `models.claude.classify` / `models.codex.classify` |
| "claude ask 모델 / codex ask 모델" | `models.claude.ask` / `models.codex.ask` |
| "ask 결과 N개" | `top_k.ask` |
| "decide 결과 N개" | `top_k.decide` |
| "recall 결과 N개" | `top_k.recall` |
| "resume 결과 N개" | `top_k.resume` |
| "AI를 codex로 / claude로 / auto로" | `ai_provider` |
| "vault 경로 …" | `vault` |
| "비용 요약 N일" | `cost.summary_days` |
| "interactive guard 끄기/켜기 / 안내 끄기" | `interactive_guard.enabled` |
| "guard 대기 N초" | `interactive_guard.delay_seconds` |
| "codex 자동 수집 끄기/켜기" | `automation.codex_poller.enabled` |
| "매일 자동 실행 N시" | `automation.daily_cron.time` (+ `automation.daily_cron.enabled=true`) |
| "profile sample N줄" | `profile.sample_lines` |

### 동의 흐름

```
변경 미리보기:
  키: <키 경로>
  현재: <synapse-memory config get으로 조회한 값>
  변경: <새 값>
  영향: <한 줄 안내, 매핑 표 아래 영향 가이드 참고>

이대로 적용할까요? (yes/no)
```

`yes`를 받으면 `SYNAPSE_FROM_AGENT=1 synapse-memory config set <키> <값>` 실행. 결과를 1줄로 보고.

## 인자가 없을 때 (대화형)

위 `config show` 결과를 카테고리별로 묶어 사람 말로 정리하고:

```
어떤 값을 바꾸고 싶나요? 자연어로 답해주세요.
  예: "cleanup inbox를 60일로", "이력서 모델은 opus로", "ask 결과는 8개"
  ("exit"라고 답하면 종료)
```

사용자 응답 → 위 자연어 매핑 → 변경 미리보기 → 동의 → set.
*한 번에 한 키만* 변경합니다 (안전).

## 영향 가이드 (동의 직전에 짚어줄 한 줄)

| 키 그룹 | 영향 |
|---|---|
| `cleanup.*_days` | 다음 `/synapse-cleanup` 부터 새 임계값 적용. 기존 archive에는 영향 없음. |
| `models.*` | 다음 호출부터 새 모델 사용. opus는 sonnet 대비 비용이 약 5배. |
| `top_k.*` | 다음 호출부터 새 매칭 개수. 늘리면 답변 컨텍스트 풍부 + 비용 증가. |
| `ai_provider` | `claude`/`codex`/`auto` 중 하나. 변경 시 비용·모델 이름 체계도 달라짐. |
| `vault` | 변경 즉시 새 vault 사용. **기존 vault의 카드·Profile은 옮겨지지 않습니다.** |
| `interactive_guard.enabled` | false 시 사람 직접 호출에서 안내가 사라짐 (자동화에 유용). |
| `automation.codex_poller.enabled` | launchd 데몬 동작 토글. 적용은 `synapse-memory install-agent` 재실행 필요 (미구현). |
| `cost.summary_days` | `/synapse-cost` 기본 윈도우. |

## advanced 키를 묻는 경우

사용자가 `advanced.rag.rrf_k`, `advanced.rag.embedding_model`, `advanced.llm.*_timeout_seconds`를 변경하려 하면 *추가 경고 단계* 한 번 더 거치세요.

```
⚠ advanced 키 변경: <키>
  영향:
    - rrf_k: 잘못 바꾸면 검색 품질 저하
    - embedding_model: 변경 즉시 전체 색인 재생성 필요(`rag index --rebuild`)
    - *_timeout_seconds: 네트워크 느릴 때만 늘리세요
  정말 변경할까요? (advanced/cancel)
```

`advanced`라고 정확히 답해야 진행. `yes` 같은 일반 동의는 거부. 실제 실행 시 `--force` 플래그 사용: `synapse-memory config set <키> <값> --force`.

## 절대 하지 말 것

- ❌ 한 번에 여러 키를 묶어서 set 호출
- ❌ 사용자 동의 없이 set 실행 (자연어 *매핑*만 보여주고 동의 후 실행)
- ❌ 보호된 키(`storage.l0_permissions`, `redaction.pass1_patterns`, `redaction.pass2_enabled`, `cleanup.protected_paths`)를 set 시도 — CLI가 차단하지만 슬래시도 사용자에게 "보안 핵심 키 — 코드 PR로만 변경" 안내
- ❌ vault 변경 시 기존 데이터를 임의로 옮기기 (이동은 사용자 몫)
- ❌ advanced 키를 일반 동의로 진행

## 백업

매 변경마다 자동 백업 — `~/.synapse/config.yaml.bak-YYYYMMDD-HHMMSS`. 롤백이 필요하면:

```bash
cp ~/.synapse/config.yaml.bak-<TIMESTAMP> ~/.synapse/config.yaml
```
