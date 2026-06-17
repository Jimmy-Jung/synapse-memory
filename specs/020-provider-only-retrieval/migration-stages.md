# 020 — 카드/persona provider 이전 단계 계획

작성일: 2026-06-17
선행: [design.md](design.md)

전체 로컬 ML 제거(embeddings/vector/bm25/hybrid) 결정. 단 persona/recipes/ask 검색은
서로 결합돼 있어 한 덩어리로 이전해야 안전. 단계별로 진행하되 각 단계 끝에 빌드 green 유지.

## 결정된 시맨틱 (사용자 승인 2026-06-17)
- **랭킹**: cosine 거리 → provider가 관련 카드 선별(점수 없음). CardIndex + `select_related`.
- **decide out-of-domain 가드**: distance 임계(0.6) → **provider가 0건 선별 = "자료 불충분" 거부.**
- **타임라인 정렬**: 벡터 메타 → 카드 파일에서 period_end/status/created/last_reviewed 직접 읽기(CardIndex.meta).
- **하이브리드(bm25+RRF)**: 폐기 — provider 선별로 일원화.

## Stage 1 — 토대 (완료, 커밋됨)
- `cards/card_index.py`: `CardIndex`/`build_card_index` — 카드 열거 + `select_related` 호환(entries/render/slugs).
- 기존 `wiki/llm_retrieval.select_related`를 카드에도 재사용.
- 테스트 `tests/test_card_index.py`.

## Stage 2 — recipes/pipeline provider 이전 (남음)
- `recipes/pipeline.py:261` `embed_query`+store.query → `build_card_index`+`select_related`.
- `_PrecomputedResultStore`(persona) 인터페이스 대체 — 선별된 card_id 리스트 직접 전달.
- recall/decide/resume가 공유하는 retrieve 계층이므로 먼저.

## Stage 3 — persona provider 이전 (남음, recipes 의존)
- `what_did_i_think`: distance-mode → select_cards → 카드 로드 → 합성. time-mode → CardIndex.meta로 타임라인.
- `decide`: select_cards 0건 → 거부(가드 대체). 통과 시 합성.
- `draft_resume`: project 카드 select_cards.
- VectorStore/embed_query/hybrid_search import 제거.

## Stage 4 — endpoints/ask + cli/daily (남음)
- `endpoints/ask.ask`: card RAG → `build_card_index`+`select_related`+합성. AskResult/SourceCitation 유지.
- cli `cmd_ask` 에러 핸들링에서 Embedding/VectorStore 예외 제거.
- cli `rag` 명령(벡터 검색)·`card index`·cluster 제거 또는 재정의.
- `daily.py` `index_cards` 스테이지 제거.

## Stage 5 — rag 모듈 + pyproject 제거 (남음, 마지막)
- `rag/embeddings.py`/`vector_store.py`/`bm25.py`/`hybrid.py`/`indexer.py` 제거.
- `wiki/index.py`(index_one_page/index_wiki_pages/wiki_page_to_record) 제거 + `wiki/__init__` export 정리.
- `pyproject.toml` `[rag]` extras에서 chromadb/sentence-transformers/rank-bm25 제거.
- 관련 테스트 전면 정리(test_rag_*, test_persona_*, test_endpoints_ask, test_recipes_*, test_wiki_index).

## 검증 게이트 (각 단계)
- 핫·질의 경로 `import` 시 torch/sentence_transformers/chromadb 미로드.
- 전체 pytest green, ruff 통과.
- 단계별 커밋.

## 주의
- Stage 2~3은 결합도가 높아 한 PR로 묶는 게 안전(중간 상태는 빌드 red).
- recall 랭킹 품질이 cosine→provider로 바뀜(사용자 승인). 회귀 테스트는 "선별 호출됨 + 합성됨" 수준으로 재작성(정확 순위 단언 제거).
