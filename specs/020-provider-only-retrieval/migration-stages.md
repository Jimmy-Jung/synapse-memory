# 020 — 카드/persona provider 이전 단계 상태

작성일: 2026-06-17
갱신일: 2026-06-21
선행: [design.md](design.md)

전체 로컬 ML 제거(embeddings/vector/bm25/hybrid) 결정. 단 persona/recipes/ask 검색은
서로 결합돼 있어 한 덩어리로 이전해야 안전했다. 현재 코드는 provider-only 이전이 완료됐고,
이 문서는 historical migration checklist와 현재 호환 표면을 구분해 보관한다.

## 결정된 시맨틱 (사용자 승인 2026-06-17)
- **랭킹**: cosine 거리 → provider가 관련 카드 선별(점수 없음). CardIndex + `select_related`.
- **decide out-of-domain 가드**: distance 임계(0.6) → **provider가 0건 선별 = "자료 불충분" 거부.**
- **타임라인 정렬**: 벡터 메타 → 카드 파일에서 period_end/status/created/last_reviewed 직접 읽기(CardIndex.meta).
- **하이브리드(bm25+RRF)**: 폐기 — provider 선별로 일원화.

## Stage 1 — 토대 (완료, 커밋됨)
- `cards/card_index.py`: `CardIndex`/`build_card_index` — 카드 열거 + `select_related` 호환(entries/render/slugs).
- 기존 `wiki/llm_retrieval.select_related`를 카드에도 재사용.
- 테스트 `tests/test_card_index.py`.

## Stage 2 — recipes/pipeline provider 이전 (완료)
- `recipes/pipeline.py`는 `build_card_index` + `select_related` 기반으로 카드 후보를 선별한다.
- recipe 결과는 local vector store가 아니라 provider-selected card ids를 사용한다.

## Stage 3 — persona provider 이전 (완료)
- `what_did_i_think`, `decide`, `draft_resume`은 CardIndex/provider 선별과 카드 파일 metadata를 사용한다.
- `--hybrid` 플래그는 호환 no-op이며 provider-only ranking 차이를 만들지 않는다.

## Stage 4 — endpoints/ask + cli/daily (완료)
- `endpoints/ask.ask`는 `build_card_index` + `select_related` + 합성 경로를 사용한다.
- CLI help는 provider-only 호환 플래그를 설명한다.
- `daily.py`는 local vector indexing이 아니라 provider-only context refresh 흐름을 설명한다.

## Stage 5 — rag 모듈 + pyproject 제거 (완료)
- `rag/`에는 provider-only 이후에도 유효한 raw chunking utility만 남았다.
- local embeddings/vector/BM25/hybrid/indexer 모듈과 무거운 ML 의존성은 제거됐다.
- `advanced.rag.*`와 `top_k.rag_search`는 기존 사용자 config 호환을 위한 legacy no-op surface다.

## 검증 게이트
- 핫·질의 경로 `import` 시 torch/sentence_transformers/chromadb 미로드.
- 전체 pytest green, ruff 통과.
- `uv run synapse-memory ask --help`와
  `uv run synapse-memory persona what-did-i-think --help`는 BM25/RRF를 현재 동작처럼
  설명하지 않는다.

## 주의
- Stage 2~3은 결합도가 높아 한 PR로 묶는 게 안전(중간 상태는 빌드 red).
- recall 랭킹 품질이 cosine→provider로 바뀜(사용자 승인). 회귀 테스트는 "선별 호출됨 + 합성됨" 수준으로 재작성(정확 순위 단언 제거).
