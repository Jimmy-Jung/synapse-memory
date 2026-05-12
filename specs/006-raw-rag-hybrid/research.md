# Research: Raw RAG Hybrid

**Feature**: `006-raw-rag-hybrid`  
**Date**: 2026-05-12

## R1. Raw chunk 크기

**Decision**: 512 token window, 64 token overlap을 기본으로 한다. 구현상 token은 외부 tokenizer 추가 없이 whitespace/punctuation 기반 lightweight token으로 계산한다.

**Rationale**: 로드맵 FR-B1이 512/64를 명시한다. bge-m3는 더 긴 context를 처리할 수 있지만 raw note는 검색 citation과 prompt budget을 고려하면 작은 chunk가 더 안정적이다.

**Alternatives considered**:

- 문단 단위 only: 긴 문단에서 chunk가 과대해지고 재현 가능한 overlap이 어렵다.
- 모델 tokenizer 의존: 품질은 좋지만 설치 비용과 테스트 복잡도가 증가한다.

## R2. Raw source discovery

**Decision**: Obsidian raw는 vault `10_Active/**/*.md`, Claude Code raw는 `~/.synapse/private/redacted/claude-code/**/*`의 text/json/jsonl/md 파일을 대상으로 한다.

**Rationale**: 로드맵은 `10_Active/`와 redacted Claude Code path를 명시한다. `redacted/claude-code`는 이미 L0 redaction output이므로 raw source 중 외부 prompt에 가장 안전하게 재사용 가능하다.

**Alternatives considered**:

- vault 전체 인덱싱: private/system/generated 문서까지 섞여 noise와 privacy risk가 커진다.
- raw Claude Code 원본 인덱싱: constitution 위반 가능성이 높아 배제한다.

## R3. Redaction placement

**Decision**: raw chunk 생성 후 각 chunk에 `redact_full()`을 적용하고, redacted text만 VectorRecord와 BM25 sidecar에 저장한다.

**Rationale**: 저장소 자체가 local-only라도 추후 prompt context로 재사용되므로 index 저장 시점부터 invariant를 강제하는 편이 안전하다.

**Alternatives considered**:

- prompt 직전에만 redaction: index와 search 출력에 raw가 남을 수 있다.
- file 전체 redaction 후 chunking: redaction placeholder가 길어지거나 줄 구조가 바뀔 때 chunk 경계가 덜 안정적이다.

## R4. BM25 tokenizer

**Decision**: 한글/영문/숫자 연속 문자열을 lower-case token으로 분리하고, 2글자 이상 한글/영문 token을 유지한다. `rank-bm25`의 `BM25Okapi`를 사용한다.

**Rationale**: 한국어 형태소 분석기를 새로 도입하지 않고도 회사명, 사람 이름, slug, 영문 stack 검색에는 충분한 exact token signal을 얻을 수 있다. `rank-bm25`는 pyproject의 rag extra에 이미 포함되어 있다.

**Alternatives considered**:

- 형태소 분석기 추가: 한국어 recall은 좋아질 수 있으나 설치/CI 비용이 크다.
- 자체 BM25 구현: 검증된 라이브러리를 다시 만드는 비용이 불필요하다.

## R5. RRF merge

**Decision**: dense와 BM25 결과를 `score += 1 / (k + rank)`로 결합하며 k=60을 사용한다. tie-break는 높은 BM25 점수, 낮은 dense distance, record id 순으로 결정한다.

**Rationale**: 로드맵 FR-B2가 RRF(k=60)를 명시한다. RRF는 score scale이 다른 dense distance와 BM25 score를 안정적으로 결합한다.

**Alternatives considered**:

- weighted sum: distance와 BM25 score normalization이 query마다 흔들린다.
- BM25-first rerank: semantic recall이 약해질 수 있다.

## R6. Missing BM25 sidecar behavior

**Decision**: `--hybrid`에서 sidecar가 없거나 비어 있으면 명시적인 `BM25IndexError`를 반환한다. dense-only로 silent fallback하지 않는다.

**Rationale**: 사용자가 `--hybrid`를 요청했는데 실제로 dense-only가 실행되면 품질 평가와 디버깅이 왜곡된다.

**Alternatives considered**:

- 자동 fallback: 편하지만 hybrid success criteria를 속인다.
- 호출 시 즉시 sidecar rebuild: 외부 embedding/redaction 비용이 숨어서 interactive endpoint가 느려진다.
