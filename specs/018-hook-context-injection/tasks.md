# Tasks: Hook Context Injection

> 저자: JunyoungJung  
> 작성일: 2026-06-11  
> 범위: M1 cache + hook runner + hook install

## Phase 1 - Tests

- [X] T001 `projects.yaml` 저장 시 `projects.json` sidecar 생성 테스트
- [X] T002 `render_context_cache()` 생성/byte-limit 테스트
- [X] T003 등록 프로젝트 SessionStart hook 출력 테스트
- [X] T004 미등록 프로젝트 hook 무출력 테스트
- [X] T005 cache missing fallback 테스트
- [X] T006 hook install/uninstall/idempotency 테스트
- [X] T007 CLI parser hook command 테스트
- [X] T008 setup/sync 후 context cache 갱신 테스트

## Phase 2 - Implementation

- [X] T009 `projects.registry.save_registry()` JSON sidecar 병행 기록
- [X] T010 `projects.summary.render_context_cache()` 추가
- [X] T011 `hooks/session_start.py` stdlib-only runner 추가
- [X] T012 `hooks/install.py` settings.json install/uninstall 추가
- [X] T013 `cli.py` hook fast path 및 `hook` subcommand 추가
- [X] T014 `setup`/`sync` 성공 후 context cache 렌더 호출

## Phase 3 - Validation

- [X] T015 targeted pytest 실행
- [X] T016 ruff/mypy 실행
- [X] T017 diff/status 확인

## Phase 4 - Review Follow-up

- [X] T018 `context render` CLI parser/command 테스트 추가
- [X] T019 `synapse-memory context render` 구현
- [X] T020 `apply-profile` skill/command 문서에 승인 후 cache 갱신 단계 추가
- [X] T021 follow-up targeted pytest/ruff/mypy 실행

## Phase 5 - Remaining Follow-up

- [X] T022 `setup --no-marker` / `--target codex` parser 및 동작 테스트 추가
- [X] T023 `setup --no-marker` registry-only 등록 구현
- [X] T024 미등록 git repo env opt-in suggest_register 테스트/구현
- [X] T025 Claude Code hook 설치 상태 진단 테스트/구현
- [X] T026 `settings.json` 원자적 기록으로 변경
- [X] T027 `cli.py` 파일 전체 `E402` noqa 제거 및 import별 noqa로 축소
- [X] T028 setup skill/command 문서 갱신
- [X] T029 remaining follow-up targeted pytest/ruff/mypy 실행

## Phase 6 - M3 Completion

- [X] T030 `hook` config dataclass / validation / render 노출 테스트 추가
- [X] T031 hook runtime settings sidecar 렌더 테스트/구현
- [X] T032 SessionStart hook이 settings sidecar의 suggest/max_bytes를 읽도록 테스트/구현
- [X] T033 setup/sync/context render에서 hook settings sidecar 갱신
- [X] T034 M3 targeted pytest/ruff/mypy 실행
