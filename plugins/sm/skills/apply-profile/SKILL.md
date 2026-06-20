---
name: apply-profile
description: Use when the user wants to review and approve MemoryInbox Profile candidates one-by-one before they land in Profile.md / DecisionPatterns.md. AskUserQuestion-driven GUI flow. Pass date as YYYY-MM-DD or `--all-pending`. Auto-suggested after `/sm:daily` when new candidate exists.
---

# /sm:apply-profile — MemoryInbox 후보 GUI 승인

`synapse-memory daily`가 만든 `Profile-YYYY-MM-DD.md` 후보를 항목별로 확인하고, 승인분만 vault `Profile.md` / `DecisionPatterns.md`에 반영합니다.

## 실행

```bash
/sm:apply-profile                  # 가장 최근 pending 후보
/sm:apply-profile 2026-05-17       # 특정 날짜
/sm:apply-profile --all-pending    # 오래된 순으로 전부
```

## 흐름

1. `synapse-memory list-pending-profiles --json` 으로 pending 목록 조회
2. 대상 후보 결정 (date 인자 또는 가장 최근)
3. 후보 파일 Read → ProfileFact + DecisionPattern 항목 평탄화
4. AskUserQuestion 4개씩 (Yes / No / Edit)
5. 승인분 → Profile.md (카테고리 섹션) / DecisionPatterns.md (`## Approved Patterns`)에 Edit으로 추가
6. 후보 파일 frontmatter `status: pending_review` → `status: applied` + `applied_date` 갱신
7. Bash로 `synapse-memory context render` 실행해 Claude hook context cache 갱신

## 자동 진입

`/sm:daily` 정상 종료 후(신규 후보 생성됐을 때) prompt가 자동으로 apply 흐름을 제안합니다. 사용자가 Yes 답해야 진입 — 강제 트리거는 없습니다.

## 종료 코드

- list-pending-profiles 호출이 0이면 정상 (vault 없음 = 2)
- 슬래시 자체는 사용자 응답에 따른 결과 (오류는 stderr 메시지 + AskUserQuestion 종료)

## 후속

- 승인분이 vault Profile.md에 들어가면 Claude hook context cache는 자동 갱신합니다.
- Codex/marker 기반 프로젝트 파일까지 갱신해야 할 때만 별도로 `/sm:sync`를 안내합니다.
