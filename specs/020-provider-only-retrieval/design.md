# 020 — Provider-Only Retrieval: 로컬 ML 제거 + claude/codex 일원화

작성일: 2026-06-16
상태: 설계 → 구현
선행: [019-llm-wiki-redesign](../019-llm-wiki-redesign)

## 1. 배경 / 문제

watch 데몬이 메모리 footprint **16GB**까지 부풀어 24GB 맥을 스왑 스래싱으로 마비시킴.

근본 원인(소스 분석):

1. **상주 ML 프로세스** — `rag/embeddings.py`의 bge-m3(BAAI/bge-m3, ~2GB 가중치)를 `watch run` 데몬이 로드 후 영구 보관. idle에도 RAM 점유.
2. **무한정 동기 작업** — watermark 고착 시 `iter_new_raw`가 backlog 전체를 리스트로 materialize([rawdoc.py](../../src/synapse_memory/wiki/rawdoc.py)), doc마다 `find_related_pages`가 **세션 전문을 통째로 임베드**([retrieval.py:122](../../src/synapse_memory/wiki/retrieval.py)), MPS 캐시 미해제로 누적.
3. **watermark 사이클 끝에만 저장** → kill/OOM 시 전체 재처리 악순환([ingest.py:119-123](../../src/synapse_memory/wiki/ingest.py)).
4. **파일이벤트 트리거(WatchPaths)** — collect가 raw를 쓰면 self-trigger.

핵심 통찰: **상주 ML 데몬 + 파일이벤트 + 무한 동기작업** 조합이 틀림.

## 2. 목표

1. 로컬 ML(bge-m3 / torch / sentence-transformers / 벡터스토어) **완전 제거**.
2. 모든 추론(통합·관련선별·답변)을 **선택한 단일 provider(claude | codex)** 로 일원화.
3. 처리 잡을 **수명 짧은 bounded 프로세스**로 — 프로세스 종료가 메모리 보장.
4. kill돼도 **진행 보존**(doc별 watermark).
5. 회귀 테스트로 메모리 상한·재개·provider 선별 검증.

비목표: 멀티유저, 수천 페이지 스케일(개인 vault 수십~수백 페이지 가정).

## 3. 설계 원칙

- **Ephemeral > resident** — 작업 끝나면 종료, OS가 회수.
- **Bounded** — 실행당 doc·char 상한.
- **Durable & resumable** — watermark 체크포인트.
- **Provider 단일화** — `config.ai_provider` 하나가 검색·통합·답변 전부 결정.
- **경계 불변** — 통합 단계가 이미 doc 전문을 원격 provider에 보냄. 의미선별을 같은 provider로 옮겨도 신규 노출 없음.

## 4. 아키텍처

```
config.ai_provider: claude | codex            # 단일 진실원본 (기존)
config.models.<provider>.relevance: <싼모델>  # 신규 (haiku / gpt-5-mini)

Capture (싸다, 자주)
  SessionEnd hook / collect → raw mirror + watermark "pending"
        │ (디스크 = 큐, 별도 스토어 불필요)
        ▼
Process (스케줄·단명 잡; launchd StartInterval)
  page_index = build_page_index(all_pages)         # [slug,title,요약] 1회
  for doc in islice(lazy_raw(since), N):            # N = max_docs_per_cycle
     cand    = name_match(doc) + 1hop               # 로컬·무료
     related = ai_api.select_related(doc, index)    # provider(싼모델) ← embed 대체
     ops     = ai_api.integrate(doc, related)       # provider (기존)
     apply + write_page(text only)                  # 벡터 없음
     save_watermark(doc)                            # doc별 체크포인트
  EXIT  → OS가 전부 회수
Ask (/sm:ask)
  select_related(query, index) + ai_api.complete    # 벡터 없이 provider 선별+답변
```

### 메모리 결과

잡이 하는 일 = 문자열 처리 + claude/codex CLI 서브프로세스 호출. torch/모델 로드 0.
잡 메모리 ≈ doc 텍스트 + 페이지 인덱스(수십 KB) + subprocess → **수십 MB 상한**. 16GB 구조적 불가.

## 5. 제거 / 추가 / 변경

### 제거
- `rag/embeddings.py` (bge-m3 wrapper) 핫패스 의존
- `pyproject.toml` `[rag]` extras의 `sentence-transformers`, `chromadb`(핫패스), torch
- `retrieval._default_semantic`의 embed_query 경로
- `index_one_page`의 벡터 인덱싱(텍스트 페이지 쓰기만 유지)

### 추가
- `ai_api.select_related(doc_text, page_index, *, env, model) -> list[str]`  (관련 slug)
- claude.py / codex.py에 provider 선별 프롬프트 구현
- `wiki/page_index.py` — `build_page_index(pages) -> PageIndex` (slug/title/요약)
- `MaintenanceConfig`: `max_docs_per_cycle:int=25`, `interval_minutes:int=20`
- `models.<provider>.relevance` 키

### 변경
- `wiki/retrieval.find_related_pages` — semantic_fn을 provider 기반으로(또는 인덱스 주입식 select_related)
- `wiki/daemon.run_watch_cycle` → `run_bounded_cycle(limit, checkpoint_each=True)`
- `wiki/launchd.py` — plist `WatchPaths` → `StartInterval`(+ ThrottleInterval), RunAtLoad=false
- `wiki/ingest.ingest_source` — `_all_pages` 루프 밖 1회 로드, lazy raw + islice

## 6. 인터페이스 계약

```python
# ai_api.py
def select_related(
    doc_text: str, page_index: "PageIndex", *,
    env: object | None = None, model: str | None = None, timeout: int = 60,
) -> list[str]:
    """page_index에서 doc과 관련된 페이지 slug 목록(최대 max_pages). provider 호출.
    실패/빈 인덱스 → []. (graceful — ingest는 계속)"""
```

```python
# wiki/page_index.py
@dataclass(frozen=True)
class PageEntry:
    slug: str
    title: str
    summary: str            # 1줄 요약 또는 본문 첫 N자

@dataclass(frozen=True)
class PageIndex:
    entries: tuple[PageEntry, ...]
    def render(self) -> str:  # 프롬프트용 "[slug] title — summary" 라인
```

## 7. 트레이드오프

| 항목 | 영향 | 완화 |
|---|---|---|
| 비용 | doc당 LLM +1(선별) | 싼 티어, 후보 적으면 스킵, 캐시 |
| 확장 | LLM-over-인덱스 ~수백 페이지 | 이름매칭 1차 필터 후 LLM |
| 품질 | 의미매칭 일부 손실 가능 | 인덱스에 요약 포함 |
| 프라이버시 | 선별 텍스트 원격行 | 경계 불변(통합이 이미 전송) |
| 오프라인 | 로컬임베딩 상실 | 통합이 이미 네트워크 필요 |

## 8. 테스트

- `test_bounded_cycle` — 대량 mock doc + 거대 텍스트 → limit개만 처리, lazy(미읽은 파일 read 안 됨).
- `test_checkpoint_resume` — 중간 doc 예외 → watermark가 직전 성공까지 전진.
- `test_select_related_provider` — fake provider로 slug 선별, 빈 인덱스 graceful [].
- `test_no_torch_import` — 핫패스 import에 torch/sentence_transformers 없음.

## 9. 마이그레이션

1. dev repo 패치 + 테스트 green.
2. embeddings/벡터스토어/torch 제거, 의존성 정리.
3. 재설치 `uv tool install --editable '.[rag]'`(또는 rag extras 슬림화).
4. **bounded catch-up** — 새 잡 반복 실행으로 5/29→현재 watermark 따라잡기(메모리 평탄).
5. `com.synapse-memory.cycle`(StartInterval) 설치. provider는 `config.ai_provider` 토글.

## 10. 결론

| | 기존 watch | v2 (provider-only) |
|---|---|---|
| 로컬 ML | bge-m3 ~2GB 상주 | 없음 |
| 메모리 천장 | 없음 → 16GB | 수십 MB |
| 추론 | 로컬임베딩+원격LLM 혼합 | claude or codex 하나 |
| 의존성 | torch/ST/벡터DB | CLI 서브프로세스 |
| 트리거 | 파일이벤트 | 스케줄 |
| 죽으면 | 전체 재처리 | doc 체크포인트 재개 |
