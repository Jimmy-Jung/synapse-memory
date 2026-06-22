---
description: 현재 프로젝트를 ~/.synapse/projects.yaml에 등록하고, 선택적으로 AGENTS.md / CLAUDE.md에 SYNAPSE-MEMORY marker 삽입.
argument-hint: [--target agents|claude|both|codex] [--dry-run]
---

!`synapse-memory setup $ARGUMENTS`

위 출력은 setup 결과입니다. 현재 디렉터리를 Synapse Memory registry에 등록합니다. `--target`을 지정한 경우에만 `AGENTS.md`(Codex 표준)와 `CLAUDE.md`(Claude Code 표준) 중 선택된 파일에 `<!-- SYNAPSE-MEMORY START -->` … `<!-- SYNAPSE-MEMORY END -->` marker로 감싼 컨텍스트 블록을 추가합니다.

## 사용 시점

- 새 프로젝트에서 처음으로 sm 컨텍스트를 활용하고 싶을 때
- 기존 프로젝트에 marker가 깨졌거나 빠졌을 때 (idempotent)

## 옵션

- 기본: marker 파일 수정 없이 registry + hook cache만 등록
- `--target both`: AGENTS.md + CLAUDE.md 둘 다
- `--target agents`: AGENTS.md만 (Codex 사용자)
- `--target codex`: AGENTS.md만 (`agents` alias)
- `--target claude`: CLAUDE.md만 (Claude Code 사용자)
- `--dry-run`: 의도된 변경만 출력, 파일·registry 변경 X

## 동작

1. vault Profile.md / DecisionPatterns.md 읽기
2. 상위 N개 fact + M개 pattern으로 context body 생성
3. `--target`이 있으면 대상 파일에 inject_or_replace (idempotent — 재실행 시 byte-level 동일)
4. `~/.synapse/projects.yaml`에 cwd 등록
5. Claude hook용 `~/.synapse/context/rendered.md` cache 갱신

## 후속

- Claude hook cache만 갱신하려면 → `synapse-memory context render`
- Codex/marker 파일까지 갱신하려면 → `/sm:sync`
- 미등록 git repo에서 등록 힌트를 받고 싶으면 → `synapse-memory config set hook.suggest_register true`
- 자동 트리거 없음. 명시 호출만.
