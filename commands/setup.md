---
description: 현재 프로젝트의 AGENTS.md / CLAUDE.md에 SYNAPSE-MEMORY marker 삽입 + ~/.synapse/projects.yaml에 등록. Claude Code와 Codex 양쪽이 같은 컨텍스트를 읽도록.
argument-hint: [--target agents|claude|both] [--dry-run]
---

!`synapse-memory setup $ARGUMENTS`

위 출력은 setup 결과입니다. 현재 디렉터리에 `AGENTS.md`(Codex 표준)와 `CLAUDE.md`(Claude Code 표준) 중 선택된 파일에 `<!-- SYNAPSE-MEMORY START -->` … `<!-- SYNAPSE-MEMORY END -->` marker로 감싼 컨텍스트 블록이 추가됐습니다. 외부 AI는 다음 세션부터 marker 안 내용을 자연스럽게 읽습니다.

## 사용 시점

- 새 프로젝트에서 처음으로 sm 컨텍스트를 활용하고 싶을 때
- 기존 프로젝트에 marker가 깨졌거나 빠졌을 때 (idempotent)

## 옵션

- `--target both` (기본): AGENTS.md + CLAUDE.md 둘 다
- `--target agents`: AGENTS.md만 (Codex 사용자)
- `--target claude`: CLAUDE.md만 (Claude Code 사용자)
- `--dry-run`: 의도된 변경만 출력, 파일·registry 변경 X

## 동작

1. vault Profile.md / DecisionPatterns.md 읽기
2. 상위 N개 fact + M개 pattern으로 marker body 생성
3. 대상 파일에 inject_or_replace (idempotent — 재실행 시 byte-level 동일)
4. `~/.synapse/projects.yaml`에 cwd 등록

## 후속

- vault Profile/Patterns가 바뀐 뒤 marker를 새 내용으로 갱신하려면 → `/sm:sync`
- 자동 트리거 없음. 명시 호출만.
