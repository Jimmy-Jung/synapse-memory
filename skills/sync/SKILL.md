---
name: sync
description: Use when the user updated vault Profile.md or DecisionPatterns.md and wants registered projects to see the new content. Refreshes marker contents in every project listed in `~/.synapse/projects.yaml`. Explicit invocation only — never auto-triggered.
---

# /sm:sync — 등록된 프로젝트 marker 갱신

vault Profile/Patterns가 바뀐 뒤 명시 호출. registry에 등록된 모든 프로젝트의 marker 사이 내용을 최신 vault 상태로 교체합니다.

## 실행

```bash
synapse-memory sync [--current]
```

- 옵션 없이: 등록 전체 갱신
- `--current`: cwd 프로젝트만 갱신

## 동작

1. vault Profile/Patterns로 새 marker body 계산
2. 각 등록 프로젝트의 `AGENTS.md`/`CLAUDE.md` marker 사이 교체 (marker 외부 라인 보존)
3. `~/.synapse/projects.yaml` 의 `last_sync` 업데이트
4. 등록 path가 사라진 entry는 `state: stale` 표시. 다른 entry는 정상 처리.

## 종료 코드

- `0` — 정상 (stale 표시도 정상 흐름)
- `1` — marker 파싱 실패 (어떤 프로젝트 파일이 unclosed marker로 깨짐)
- `2` — `--current` 인데 cwd가 registry에 없음

## 자동 트리거 없음

`/sm:daily` 또는 `synapse-memory daily` 같은 명령이 sync를 자동 호출하지 않습니다. 사용자가 명시적으로 호출할 때만 동작합니다.
