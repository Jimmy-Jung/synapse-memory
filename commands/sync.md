---
description: ~/.synapse/projects.yaml에 등록된 모든 프로젝트의 SYNAPSE-MEMORY marker 갱신. vault Profile/Patterns가 바뀐 뒤 1회 호출.
argument-hint: [--current]
---

!`synapse-memory sync $ARGUMENTS`

위 출력은 sync 결과입니다. 등록된 각 프로젝트의 `AGENTS.md`/`CLAUDE.md` marker 사이 내용이 최신 vault Profile/Patterns로 교체됐습니다.

## 사용 시점

- vault `Profile.md` 또는 `DecisionPatterns.md`를 수정한 뒤 등록된 프로젝트에 반영하고 싶을 때
- `/sm:apply-profile` (예정) 또는 수동 Profile 편집 후

## 옵션

- 없음 (기본): registry에 등록된 모든 프로젝트 갱신
- `--current`: cwd 프로젝트만 갱신 (cwd가 registry에 없으면 종료 코드 2)

## 동작

1. vault Profile/Patterns로 새 marker body 생성
2. 각 등록 프로젝트의 target 파일에 marker 교체 (marker 외부 라인 보존)
3. `~/.synapse/projects.yaml`의 `last_sync` 업데이트
4. 등록된 path가 사라진 entry는 `state: stale` 표시 (다른 entry는 정상 처리)

## 자동 트리거 없음

`/sm:daily`나 다른 명령이 sync를 자동 호출하지 않습니다. 사용자가 marker를 새로 고치고 싶을 때 명시적으로 부르세요.
