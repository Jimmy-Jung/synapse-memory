# Feature Specification: Raw RAG Hybrid

**Feature Branch**: `006-raw-rag-hybrid`  
**Created**: 2026-05-12  
**Status**: Draft  
**Input**: User description: "raw chunk indexing and hybrid dense BM25 retrieval for ask and timeline recall"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Card가 아닌 raw 노트도 검색 근거로 쓰기 (Priority: P1)

사용자는 Card로 승격되지 않은 Obsidian `10_Active/` 노트와 redacted Claude Code 로그를 `rag index --include-raw`로 chunk 단위 인덱싱할 수 있어야 한다. 이후 `ask`는 Card와 raw chunk를 함께 검색 근거로 삼고, raw 결과에는 출처 경로와 chunk 번호가 표시되어야 한다.

**Why this priority**: 현재 RAG는 Card로 정리된 정보만 다룬다. 사용자가 아직 정리하지 않은 최신 학습자료, 회고, 대화 로그가 검색에서 빠지면 second brain이 실제 기억보다 좁게 동작한다.

**Independent Test**: 임시 vault에 Card 1개와 Card화되지 않은 `10_Active/raw-note.md`를 만들고 `index_cards(include_raw=True)`를 실행한다. captured vector records에 `source_kind=raw_obsidian`, `path`, `chunk_index`가 포함되고, raw chunk 문서가 redacted 상태인지 검증한다.

**Acceptance Scenarios**:

1. **Given** `10_Active/학습노트.md`가 Card화되지 않은 채 존재한다, **When** 사용자가 `synapse-memory rag index --include-raw`를 실행한다, **Then** 해당 노트가 chunk 단위로 인덱싱되고 `source_kind=raw_obsidian` 메타데이터를 가진다.
2. **Given** `~/.synapse/private/redacted/claude-code/session.jsonl`이 존재한다, **When** raw 포함 인덱싱을 실행한다, **Then** 로그 텍스트가 chunk 단위로 인덱싱되고 `source_kind=raw_claude_code` 메타데이터를 가진다.
3. **Given** raw source 파일이 비어 있거나 markdown frontmatter만 있다, **When** raw 포함 인덱싱을 실행한다, **Then** 빈 chunk는 만들지 않고 오류 없이 다음 파일을 처리한다.

---

### User Story 2 - 고유명사 검색에서 hybrid ranking 쓰기 (Priority: P2)

사용자는 `ask --hybrid`와 `me what-did-i-think --hybrid`로 dense vector 검색 결과와 BM25 keyword 검색 결과를 RRF(k=60)로 결합할 수 있어야 한다. 회사명, 사람 이름, 프로젝트 slug처럼 dense embedding만으로 놓칠 수 있는 정확 문자열은 상위 결과로 올라와야 한다.

**Why this priority**: v0.6의 핵심 품질 개선은 "당근마켓", "카카오뱅크", 사람 이름 같은 고유명사 recall이다. dense-only 검색은 의미 유사도에는 강하지만 정확 token match가 약할 수 있다.

**Independent Test**: dense 결과에서는 2위 이하인 record가 BM25 exact match에서는 1위가 되도록 fixture를 구성한다. `hybrid_search(..., k=60)` 결과에서 exact-match record가 top-1로 올라오는지 검증한다.

**Acceptance Scenarios**:

1. **Given** query가 회사명을 포함한다, **When** 사용자가 `synapse-memory ask "당근마켓 경험" --hybrid`를 실행한다, **Then** dense 결과와 BM25 결과가 RRF로 결합되고 exact keyword match가 상위에 표시된다.
2. **Given** 사용자가 `me what-did-i-think --hybrid`를 호출한다, **When** timeline 모드가 아닌 기본 회상 답변을 생성한다, **Then** AI prompt의 자료 순서는 hybrid ranking 결과를 따른다.
3. **Given** BM25 sidecar index가 아직 없다, **When** 사용자가 `--hybrid`를 호출한다, **Then** 명확한 안내와 함께 `rag index --include-raw` 또는 `rag index` 재실행을 제안한다.

---

### User Story 3 - raw가 외부 LLM으로 새지 않는 retrieval 안전망 (Priority: P3)

사용자는 raw chunk를 인덱싱하더라도 외부 AI provider로 전달되는 prompt가 Pass 1+Pass 2 redaction을 우회하지 않는다는 보장을 가져야 한다. 검색 품질 개선은 privacy invariant를 깨지 않아야 한다.

**Why this priority**: raw RAG는 검색 범위를 넓히지만, constitution상 raw unredacted payload의 외부 전송은 금지다. 기능이 좋아져도 보안 회귀가 있으면 머지 불가다.

**Independent Test**: synthetic PII marker가 포함된 raw note를 인덱싱하고 `ask --hybrid` prompt capture를 수행한다. provider로 넘어간 prompt에 원본 marker가 없고 redacted placeholder만 포함되는지 검증한다.

**Acceptance Scenarios**:

1. **Given** raw note에 이메일/전화/사용자 redact-list token이 있다, **When** raw 포함 인덱싱을 실행한다, **Then** vector document와 BM25 document에는 redacted 텍스트만 저장된다.
2. **Given** `ask --hybrid`가 raw chunk를 context로 선택한다, **When** AI provider wrapper가 호출된다, **Then** prompt에는 unredacted raw marker가 포함되지 않는다.
3. **Given** redaction eval golden을 재실행한다, **When** feature 변경 후 결과를 기록한다, **Then** Pass1 F1 ≥ 0.95, Pass2 F1 ≥ 0.80을 유지한다.

### Edge Cases

- `--include-raw`를 켰지만 vault `10_Active/` 또는 L0 redacted Claude Code 디렉터리가 없으면 Card 인덱싱은 계속되고 raw count는 0으로 표시된다.
- 동일 raw 파일을 재인덱싱하면 같은 `source_kind:path:chunk_index` 기반 id를 upsert하여 중복 vector를 만들지 않는다.
- chunk 크기보다 짧은 문서는 1개 chunk만 만든다.
- 매우 긴 파일은 512 token window와 64 token overlap 기준으로 결정적으로 chunking한다.
- markdown frontmatter, 빈 줄, code fence가 있어도 chunker는 텍스트 순서를 보존한다.
- `--kind project|company` 필터와 `--hybrid`가 함께 지정되면 Card 종류 필터는 card 결과에만 적용하고 raw 결과는 제외한다.
- BM25 package 또는 sidecar 파일이 없으면 dense-only로 조용히 fallback하지 않고 사용자가 알 수 있는 오류/안내를 낸다.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide deterministic raw text chunking with target window 512 tokens and overlap 64 tokens.
- **FR-002**: `synapse-memory rag index` MUST accept `--include-raw` and include raw chunk records in addition to Project/Company Cards.
- **FR-003**: Raw Obsidian chunks MUST be discovered under vault `10_Active/` markdown files.
- **FR-004**: Raw Claude Code chunks MUST be discovered under `~/.synapse/private/redacted/claude-code/`.
- **FR-005**: Raw chunk vector records MUST include metadata `source_kind`, `path`, `chunk_index`, `created`, and a display label.
- **FR-006**: Raw chunk record ids MUST be stable across rebuilds for the same source path and chunk index.
- **FR-007**: Raw chunk documents MUST be redacted before vector store upsert and before BM25 sidecar persistence.
- **FR-008**: System MUST maintain a local BM25 sidecar index for indexed records using a Korean/English tolerant tokenizer.
- **FR-009**: `ask` MUST accept `--hybrid` and use dense + BM25 RRF(k=60) retrieval when enabled.
- **FR-010**: `me what-did-i-think` MUST accept `--hybrid` for distance-mode retrieval and keep existing timeline behavior unchanged unless explicitly combined later.
- **FR-011**: Hybrid retrieval MUST preserve source metadata so citations can distinguish `card_project`, `card_company`, `raw_obsidian`, and `raw_claude_code`.
- **FR-012**: Hybrid retrieval MUST combine ranks using reciprocal rank fusion with k=60 and deterministic tie-breaking.
- **FR-013**: CLI output MUST show raw chunk citations with path and chunk index.
- **FR-014**: System MUST reject or clearly report unavailable BM25 sidecar state for `--hybrid`; it MUST NOT silently claim hybrid ranking while using dense-only retrieval.
- **FR-015**: External AI provider prompts produced by this feature MUST contain redacted context only and MUST NOT include unredacted raw source text.
- **FR-016**: Existing dense-only `rag index`, `rag search`, `ask`, and `me what-did-i-think` behavior MUST remain backward compatible when new flags are absent.

### Key Entities *(include if feature involves data)*

- **RawChunk**: A redacted searchable text slice from a raw source with source kind, path, chunk index, text, and created timestamp.
- **BM25Document**: Local sidecar document containing record id, redacted text, token list, and citation metadata.
- **RetrievalHit**: Unified retrieval result containing vector record, dense rank/distance, BM25 rank/score, RRF score, and final rank.
- **HybridRetrievalConfig**: User-selected retrieval mode, top-k, RRF k, and optional source filter.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `--include-raw` indexes fixture raw Obsidian and redacted Claude Code files with correct metadata in automated tests.
- **SC-002**: Re-running raw indexing on unchanged fixtures produces the same ids and no duplicate records.
- **SC-003**: In a synthetic 20-query retrieval eval, `--include-raw` improves NDCG@5 by at least +0.05 over Card-only.
- **SC-004**: In a 10-query proper-noun eval, `--hybrid` improves top-1 exact target accuracy by at least +20 percentage points over dense-only.
- **SC-005**: Captured AI provider prompts for raw-backed answers contain no synthetic unredacted PII markers.
- **SC-006**: Redaction golden eval remains Pass1 F1 ≥ 0.95 and Pass2 F1 ≥ 0.80.
- **SC-007**: Existing full pytest suite remains green after the feature is implemented.

## Assumptions

- Existing local embedding stack remains the dense retriever.
- `rank-bm25` is already part of the `rag` optional dependency set and no new runtime dependency is needed.
- Raw Obsidian files are local user data; any text stored in vector/BM25 indexes must be redacted text.
- FR-B3 `--preview-prompt`, FR-B4 `draft-reply`, and FR-B5 `card update` remain out of scope for this sub-feature and will be handled by later specs.
- Timeline sorting from `002-timeline-recall` remains the default behavior for `--timeline`; this feature only adds hybrid retrieval to distance-mode recall.
