# Tasks: Knowledge Compounding

> 저자: JunyoungJung  
> 작성일: 2026-06-11  
> 범위: P1 `ask --save` InsightCard write-back

## Phase 1 - Tests

- [X] T001 `tests/test_cards_insight.py`에 InsightCard serialize/parse/save 경로 테스트 추가
- [X] T002 `tests/test_endpoints_ask.py`에 `ask(save=True)` 저장/경로/redaction 테스트 추가
- [X] T003 `tests/test_rag_indexer.py`에 `index_insight_card` metadata/upsert 테스트 추가
- [X] T004 `tests/test_rag_cli.py`에 `ask --save` parser contract 테스트 추가

## Phase 2 - Implementation

- [X] T005 `src/synapse_memory/config.py`에 `vault_folders.reference.insights` 기본 경로 추가
- [X] T006 `src/synapse_memory/cards/insight.py`에 InsightCard 모델과 markdown I/O 구현
- [X] T007 `src/synapse_memory/cards/__init__.py`에 InsightCard public export 추가
- [X] T008 `src/synapse_memory/rag/indexer.py`에 insight text/meta와 단건 upsert 구현
- [X] T009 `src/synapse_memory/endpoints/ask.py`에 `save` 옵션과 `saved_path` 결과 추가
- [X] T010 `src/synapse_memory/cli.py`에 `ask --save` 옵션과 저장 경로 출력 추가

## Phase 3 - Validation

- [X] T011 targeted pytest 실행
- [X] T012 `git diff`로 범위와 불필요한 변경 확인

## Phase 4 - Review Fixes

- [X] T013 `list_insight_cards()` 추가 및 `rag index --rebuild` Insight 재인덱싱 보장
- [X] T014 `index_cards()`가 InsightCard를 BM25 문서 목록에 포함하도록 수정
- [X] T015 Insight 저장 시 question/frontmatter/filename/index display_name redaction 적용
- [X] T016 동일 Insight ID 저장 시 `-2`, `-3` suffix로 덮어쓰기 방지

## Phase 5 - Re-review Fixes

- [X] T017 `include_raw=False` 카드-only 인덱싱 후 기존 raw BM25 문서 보존 테스트 추가
- [X] T018 기존 BM25 sidecar의 raw 문서를 보존하고 카드 계열 문서만 교체하는 병합 로직 추가
