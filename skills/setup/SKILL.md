---
name: setup
description: Use when the user wants a new project to see Synapse Memory context. Adds `<!-- SYNAPSE-MEMORY START/END -->` marker to AGENTS.md (Codex) and CLAUDE.md (Claude Code) with vault Profile/Patterns paths and quick reference. Registers cwd in `~/.synapse/projects.yaml`. Idempotent — safe to re-run.
---

# /sm:setup — 프로젝트에 sm 컨텍스트 등록

새 프로젝트(또는 marker가 없는 프로젝트)에서 한 번 실행. 그 다음부터 Claude Code/Codex 세션이 시작될 때 vault Profile·Patterns의 핵심 요약을 자동으로 인식합니다.

## 실행

```bash
synapse-memory setup [--target {agents,claude,both}] [--dry-run]
```

- `--target both` (기본): AGENTS.md + CLAUDE.md 둘 다
- `--target agents`: AGENTS.md만
- `--target claude`: CLAUDE.md만
- `--dry-run`: 의도된 변경만 출력

## 동작

1. vault `Profile.md` + `DecisionPatterns.md` 읽기
2. 상위 N개 fact + M개 pattern으로 marker body 생성
3. 대상 파일의 `<!-- SYNAPSE-MEMORY START -->`…`<!-- SYNAPSE-MEMORY END -->` 사이 교체 (또는 신규 생성)
4. `~/.synapse/projects.yaml` 에 cwd 등록

## 결과

- marker 외부 라인은 그대로 보존
- 재실행 시 byte-level idempotent (같은 vault 상태 → 같은 결과)
- 시스템 marker가 깨졌으면(START만 있고 END 없음 등) 종료 코드 1로 fail-closed

## 후속

- vault Profile/Patterns 갱신 후 다시 반영하려면 → `/sm:sync`
- 자동 트리거 없음
