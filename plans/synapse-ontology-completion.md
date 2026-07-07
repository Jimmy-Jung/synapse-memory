# Synapse Ontology Completion — 실행 블루프린트

- 저자: JunyoungJung
- 작성일: 2026-07-07
- 목표: typed-relation 배선(commit `e5fbf49` + `4da5afa`) 이후 남은 온톨로지 격차를 닫는다 — **harmonization 회귀 방지 → 측정 → 소비 → 시간/분류 → (게이트된) 공리/ER**.
- 근거·배경: [specs/022-ontology-completion/review.md](../specs/022-ontology-completion/review.md)
- 선행 플랜: [plans/synapse-structural-redesign.md](synapse-structural-redesign.md) (Step 10까지 완료, 커밋 `e5fbf49`/`4da5afa`가 후속 step 11)
- 실행 모드: git + gh 사용 가능(계정 Jimmy-Jung). 각 스텝은 `release/2.0.0`에서 분기 → PR → `release/2.0.0` 병합. 푸시/PR은 사용자 승인 후.
- 리뷰 게이트: strongest 모델 적대적 리뷰 통과(코드 대조). 지적된 C1(Step 4 `about` 3곳 동시 삭제 — 미반영 시 스키마 로드 크래시), H1(Step 3 역방향 CQ용 역인덱스 Task 추가), M1/M2(Step 7 RapidFuzz 미설치·`broader` 결합, Step 5 라인정정·`current_entities` 재사용) 전부 반영됨.

---

## 완료 현황 (2026-07-07) — 전 스텝 완료, `release/2.0.0` 통합

| Step | 커밋 | 상태 |
| --- | --- | --- |
| S1 측정 (CQ 스위트 + coverage 지표) | 88bce4a · 01791a5 · 3d02667 | ✅ |
| S2 Ingest Gatekeeper | 9113b89 · c17c0f2 | ✅ |
| S3 타입 인지 retrieval + 역인덱스 | 6b15a5b · 226d24f | ✅ |
| S4 `about` 삭제 | 7991d32 | ✅ |
| S5 supersedes 무효화 + valid-time | 1f9398f | ✅ |
| S6 `concept.kind` + decision→occurrent | ef6cf79 | ✅ |
| S7 `broader` 공리 + transitive/symmetric 확장 | 7456a43 | ✅ |

통합 병합 커밋: 404833a(step3 3-way merge). 나머지는 선형 ff. CQ 15개 중 **supported 11 / xfail 4**.

**유보 (정직한 backlog):**
- S7 하위: lint `part_of` 사이클 탐지(retrieval은 `walked` set으로 cycle-safe) · `same_as` ER *탐지* 래더(fuzzy/embedding/사람승인 merge — CQ08은 *알려진* same_as 대칭 확장으로 flip, *미지* 중복 탐지는 P2 유보).
- 미계획 CQ(xfail): CQ10 edge provenance · CQ11 ask 관계별 grouping · CQ12 episodic/semantic 분리 · CQ14 log→insight 승격.

---

## 이미 완료 (재계획 금지 — 참고 커밋)

| 커밋 | 내용 | 결과 |
| --- | --- | --- |
| `e5fbf49` | integration 파이프라인에 typed relation 배선 | `INTEGRATION_SCHEMA`+프롬프트가 6종 relation을 slug 리스트로 emit, Entity 운반·직렬화·merge, retrieval 1-hop이 typed union 확장 |
| `4da5afa` | WikiPage → Entity 단일 도메인 모델(step 11) | Entity end-to-end, per-type schema.yaml 필드 + temporal frontmatter emit |
| (재인제스트) | 신 파이프라인으로 vault 재적재 | 현 vault 22페이지 중 **typed relation coverage 86%(19/22)**, 고아 4%. 전방 파이프라인 작동 검증됨 |

**측정된 현재 상태(2026-07-07):** `uses` 12 · `part_of` 7 · `about` 4 · `decided_in` 12 · `supersedes` 0 · `same_as` 0 · `related` 6 (파일 기준). 즉 전방 emit은 되나 (a) 강제가 없어 회귀 위험, (b) `supersedes`/`same_as`는 배선/ER 부재로 실사용 0, (c) retrieval이 관계 타입을 flatten, (d) coverage/CQ 측정 수단 없음.

---

## 스텝 개요 + 의존 그래프

| Step | 제목 | 티어 | depends | 병렬 |
| --- | --- | --- | --- | --- |
| 1 | 측정 기반 — CQ 스위트 + coverage 지표 | default | — | (루트) |
| 2 | Ingest Gatekeeper — typed 강제·related 탈출구 차단 | default | 1 | ∥ 3 |
| 3 | 타입 인지 retrieval — 관계 소비 | default | 1 | ∥ 2 |
| 4 | 죽은 어휘 정리 — `about` 삭제·미사용 관계 보류 | default | 2 | — |
| 5 | 시간 무효화 — supersedes 배선 + valid-time | **strongest** | 3, 1 | ∥ 6 |
| 6 | concept 분류 — `kind` 속성 + decision→occurrent | default | 1, 4 | ∥ 5 |
| 7 | (게이트) 공리 + entity-resolution | **strongest** | 5, 6, coverage gate | — |

```
        ┌──────────────┐
        │   Step 1     │  측정 (모든 것의 선행)
        └──┬────────┬──┘
           │        │
      ┌────▼───┐ ┌──▼─────┐
      │ Step 2 │ │ Step 3 │   (병렬: integration/lint  vs  links/retrieval/query)
      └────┬───┘ └──┬─────┘
           │        │
      ┌────▼───┐    │
      │ Step 4 │    │       (about 삭제 — integration/schema, Step 2 뒤 직렬)
      └────┬───┘    │
           │   ┌────▼───┐
           └──►│ Step 5 │◄─ (strongest, retrieval 필터 dep Step 3)
               └───┬────┘
      ┌────────┐   │
      │ Step 6 │◄──┘        (∥ Step 5, 단 schema.yaml 편집 충돌 주의 → 직렬 권장)
      └───┬────┘
          │
     ┌────▼───┐
     │ Step 7 │  DEFER 게이트: coverage>20% 지속 + 대응 CQ 통과 시에만 착수
     └────────┘
```

**전역 불변식 (매 스텝 종료 후 검증):**
1. `pytest -q` 전부 통과 (Step 1의 신규 xfail 제외).
2. `ruff check src` 통과.
3. `typed_relation_coverage`(Step 1 지표)가 직전 스텝 대비 **하락하지 않음**. 이것이 harmonization 회귀 트립와이어.
4. `Entity`가 유일 도메인 모델 유지 — 신규 병렬 모델 금지(step 11 되돌리지 말 것).

---

## Step 1 — [default] 측정 기반: CQ 스위트 + coverage 지표  (depends: —)

**Context brief.** 온톨로지 리뷰(§4.4, §7)의 핵심 지적: 스키마가 CQ에서 도출된 적 없고, coverage를 볼 수단이 없어 회귀가 조용히 일어난다. 이후 모든 스텝은 이 지표로 검증되므로 **가장 먼저** 만든다. 신규 엔진/리팩터 금지 — 순수 측정 계층만.

**Tasks.**
1. `src/synapse_memory/competency_questions.yaml` 신설 — 리뷰 §7의 CQ 15개를 `{id, question, kind(relational|hierarchical|temporal|identity|classification|provenance|coverage), status(supported|xfail)}` 로 선언.
2. `tests/test_competency_questions.py` 신설 — 실행 가능한 CQ를 `find_related_pages`/`ask_wiki`(`wiki/query.py`) 위에서 assert. 현재 답 불가한 관계형·계층형·시간형 CQ는 `@pytest.mark.xfail(reason=...)`로 박제(삭제 아님 — 이후 스텝이 통과시킬 목표 목록).
3. `src/synapse_memory/wiki/metrics.py`(또는 기존 doctor 모듈에 함수) 신설 — vault 스캔으로 `typed_relation_coverage`(관계≥1개 페이지/전체), `legacy_related_residual`(related만 있고 typed 없는 페이지), `orphan_ratio`(관계 0개) 계산. Entity 로더(`store`/`retrieval.pages`) 재사용, 새 파서 금지.
4. `/sm:doctor`(`src/synapse_memory/cli/doctor.py` + `doctor.py`)에 위 3개 지표 출력 라인 추가.
5. `tests/test_metrics.py` — 합성 Entity 목록으로 세 지표 계산 검증.

**검증.** `pytest tests/test_competency_questions.py tests/test_metrics.py -q` (xfail 허용) · `python -m synapse_memory.cli doctor` 실행 시 coverage 라인 출력 확인 · `ruff check src`.

**Exit criteria.** doctor가 `typed_relation_coverage: N%` 를 출력하고, CQ 15개가 supported/xfail로 분류돼 테스트로 존재. 이후 스텝의 회귀 기준선 확보.

**Rollback.** 신규 파일 3 + doctor 편집만 — revert 무해(런타임 데이터 불변).

---

## Step 2 — [default] Ingest Gatekeeper: typed 강제·related 탈출구 차단  (depends: 1)

**Context brief.** 근본원인 A+B(리뷰 §3): `INTEGRATION_SCHEMA.required`가 `op/type/slug/title/body` 5개뿐이고, 프롬프트가 "가능한 한"(soft) + `related` 폴백을 명시 허용해 LLM이 최저비용 경로로 회귀할 수 있다. 현재 coverage 86%는 강제가 아니라 프롬프트 유도의 산물이라 언제든 무너진다. **continuant 타입(project/company/concept/profile)의 새 연결은 typed 강제, `related`는 episodic(insight/log) 후방호환으로만 허용.**

**Tasks.**
1. `wiki/integration.py` `INTEGRATION_SYSTEM`: "가능한 한 typed relation" → "**반드시** typed relation 중 하나로 분류; 못 하면 연결을 만들지 마라". `related`는 insight/log에만 허용, project/company/concept/profile에서는 금지 명시.
2. `parse_ops`(L161): continuant 타입 op가 `related`에 값을 담아 오면 drop 후 경고 수집(무타입 연결을 조용히 통과시키지 않음). insight/log는 유지.
3. `wiki/lint.py`: **coverage gate** 추가 — continuant 페이지가 typed relation 0 + related≥1 이면 lint WARNING(회귀 신호). `_validate_relations`는 유지(있는 관계만 검사)하되 "무타입 잔존" 규칙 신설.
4. `INTEGRATION_SCHEMA`: `related`를 `description`으로 "insight/log 전용 legacy" 표기(스키마에서 제거하면 legacy 로드 깨지므로 유지, 의미만 축소).
5. 테스트: `tests/test_wiki_integration.py`에 continuant op의 related→drop, insight op의 related→유지 케이스. `tests/test_cli_lint.py`에 coverage-gate WARNING 케이스.

**검증.** `pytest tests/test_wiki_integration.py tests/test_wiki_apply.py tests/test_cli_lint.py -q` · Step 1 지표로 `legacy_related_residual` 비증가 확인 · `ruff check src`.

**Exit criteria.** continuant 타입에서 무타입 `related` 신규 유입 경로 차단. lint가 무타입 잔존을 WARNING으로 노출. 향후 인제스트에서 coverage 회귀 불가.

**Rollback.** integration/lint 편집 revert. 이미 저장된 페이지 불변(해가 없음).

**주의.** Step 3와 파일 비충돌(integration/lint vs links/retrieval/query) — 병렬 가능.

---

## Step 3 — [default] 타입 인지 retrieval: 관계 소비  (depends: 1)

**Context brief.** 근본원인 D(리뷰 §4.5): `links.py::neighbor_links`(L45-50)가 legacy related와 6종 typed relation을 **무타입 tuple로 flatten**해 retrieval이 `uses`/`decided_in`/`part_of`를 구분 못 한다. 관계를 채워도 검색 결과가 안 바뀌면 채울 유인(dogfood 압력)이 0. 엣지에 downstream 효과를 부여한다.

**Tasks.**
1. `wiki/links.py`: `typed_neighbors(page) -> dict[str, tuple[str,...]]`(관계명→대상 slug) 신설. 기존 `neighbor_links`는 `typed_neighbors` 위의 flat wrapper로 보존(후방호환).
2. `wiki/links.py`(또는 retrieval): **역인덱스** `reverse_relations(pages) -> dict[str, list[tuple[str, str]]]`(대상 slug → [(관계명, source slug)]) 신설 — 역방향 CQ(예: CQ1 "X를 uses하는 페이지는?")에 필수. 현재 그래프 순회(`neighbor_links`/`_expand_neighbors`)는 전부 페이지→대상 **전방향 전용**이라 이게 없으면 역방향 질의 불가.
3. `wiki/retrieval.py` `_expand_neighbors`(L36-52): 관계 타입별 가중/필터 인자 추가 — 무타입 `related` 최저 가중, typed 우선. 확장 순서를 관계 타입 기준으로.
4. `wiki/query.py` `_retrieve_wiki`: ask 경로가 seed→typed 이웃 확장을 **실제 호출**하게 배선(현재 ingest의 `find_related_pages`에서만 도는 확장을 조회에도 연결). provider 문서선택은 fallback 유지.
5. (선택) 질의 의도별 관계 우선순위 훅 — "결정/근거" 질의면 `decided_in`/`supersedes` 우선. 최소 구현, 과설계 금지.
6. 테스트: `tests/test_wiki_retrieval.py`에 typed 이웃이 무타입보다 우선/가중되는 케이스 + 역인덱스 케이스, `tests/test_wiki_query.py`에 ask가 typed 확장을 소비하는 케이스. Step 1의 관계형 CQ 중 일부 xfail 해제.

**검증.** `pytest tests/test_wiki_retrieval.py tests/test_wiki_query.py tests/test_competency_questions.py -q` · 관계형 CQ(CQ1 역방향은 Task 2 역인덱스로, 또는 전방향 CQ3 `decided_in`) 최소 1개 xfail→pass · `ruff check src`.

**Exit criteria.** retrieval이 관계 타입을 보존·활용. ask가 그래프 이웃을 소비. 최소 1개 관계형 CQ 통과.

**Rollback.** links/retrieval/query revert. `neighbor_links` wrapper 유지로 호출부 안전.

---

## Step 4 — [default] 죽은 어휘 정리: `about` 삭제·미사용 관계 보류  (depends: 2)

**Context brief.** 리뷰 §4.2: `about(any→any)`은 `related`(SKOS related)의 순수 중복 — 방향·도메인 규율 0. 관계 어휘에 `about`과 `related`를 동시에 두는 것은 중복. `supersedes`/`same_as`는 대응 메커니즘(Step 5/7) 전까지 "보류" 표기. **Step 2 뒤 직렬**(둘 다 integration.py/schema 편집).

**Tasks.**
1. `about`을 **세 곳에서 함께** 제거 — 하나만 지우면 `_validate_schema`가 `set(RELATION_FIELDS) - set(relations)` 검사에서 `ValueError`를 던져 `load_schema`(`@lru_cache`, 거의 모든 모듈이 import 시 호출)가 크래시하고 전 테스트가 실패한다(근거: `model/schema.py:147-149`): ① `schema.yaml` relations, ② `model/schema.py:11-18`의 **하드코딩** `RELATION_FIELDS` 튜플 항목(L14), ③ (Task 2의) `Entity.about` 필드. `RELATION_FIELDS`는 동적 파싱이 아니라 하드코딩 상수이므로 "자동 반영"되지 않는다.
2. `model/entity.py`: `Entity.about` 필드(L78) 제거, 직렬화/파싱 목록에서 제외. 기존 `about` 값이 있는 4페이지는 마이그레이션 — `about`→`related`로 흡수하는 일회성 스크립트(`scripts/` 또는 `sm:sync` 훅), dry-run 우선.
3. `wiki/integration.py` `INTEGRATION_SYSTEM`에서 `about` 예시/규칙 삭제.
4. `schema.yaml`에 `supersedes`/`same_as` 주석 — "보류: Step 5(supersedes)/Step 7(same_as) 메커니즘 배선 전까지 emit 유도 안 함".
5. 테스트: `about` 참조 제거 후 `tests/` 전체 통과. `about` 마이그레이션 스크립트 idempotent 테스트.

**검증.** `grep -rn "about" src/synapse_memory | grep -v "# "` 로 잔존 참조 0 확인 · `pytest -q` · Step 1 지표로 관계 총량이 about 삭제분만큼만 감소(다른 관계 불변) 확인.

**Exit criteria.** `about` 어휘 완전 제거, 기존 값은 `related`로 흡수. 미사용 관계 2종 "보류" 명문화.

**Rollback.** schema/entity/integration revert + 마이그레이션 역스크립트(related→about 복원). 마이그레이션은 반드시 git-clean 상태 vault 백업 후 실행.

---

## Step 5 — [strongest] 시간 무효화: supersedes 배선 + valid-time  (depends: 3, 1)

**Context brief.** 리뷰 §4.3: `model/entity.py::supersedes_history()`(L297)와 `SUPERSEDED_STATUS` 상수(L26)는 존재하나 **런타임 배선 안 된 코드** — 호출처가 `model/__init__` 재export와 `tests/test_model_temporal.py`뿐, `apply.py`가 supersedes를 merge만 하고 대상 페이지를 무효화하지 않는다. valid-time 부재로 변하는 사실(company.status target→hired)이 제자리 덮어쓰기된다. **full bitemporal은 명시적 YAGNI** — valid-time 1축만. subtle한 무효화 의미론이라 strongest 티어.

**Tasks.**
1. `schema.yaml`: 공통 필드에 `t_invalid`(무효화 시각, valid-time 종료) 추가. `created`를 t_valid 시작으로 재사용(신규 필드 최소화).
2. `wiki/apply.py`: op에 `supersedes=[X]`가 있으면 대상 페이지 X를 로드해 `status=superseded`(SUPERSEDED_STATUS) + `t_invalid=observed_at/updated` 자동 기입 후 재저장. 단순 링크 병합이 아니라 **부수효과** 발생.
3. `wiki/retrieval.py` + `wiki/query.py`: 기본 조회 필터 = `t_invalid is None` 且 `status != superseded`(현재 유효만) — **기존 `current_entities`(entity.py:292)/`list_current_entities`(store/page.py) 재사용, 재구현 금지**(status 필터 절반은 이미 card_index·pipeline에서 사용 중). 신규분은 `t_invalid` 필터 + ask 경로(query.py) 배선뿐. `include_history=True`(recall 경로만)에서 전체 이력. `sm:recall`이 `supersedes_history()`를 실제 호출하도록 배선.
4. company.status류 상태 전이는 새 mutable 필드 대신 supersedes 체인 또는 log episode로 표현(리뷰 권고) — 최소 구현.
5. 테스트: `tests/test_wiki_apply.py`에 supersedes→대상 status/t_invalid 자동 세팅. `tests/test_wiki_retrieval.py`에 superseded 페이지가 기본 조회 제외/ recall 포함. Step 1 시간형 CQ(6/7/13) xfail 해제.

**검증.** `pytest tests/test_wiki_apply.py tests/test_wiki_retrieval.py tests/test_competency_questions.py -q` · 시간형 CQ 통과 · `ruff check src`.

**Exit criteria.** supersedes 발행이 대상을 무효화. 기본 조회는 현재 유효만. `supersedes_history()` 죽은 코드 부활. 시간형 CQ 통과.

**Rollback.** apply/retrieval/query revert. `t_invalid` 필드는 무시되면 무해(직렬화만). 되돌려도 데이터 정합.

---

## Step 6 — [default] concept 분류: `kind` 속성 + decision→occurrent  (depends: 1, 4)

**Context brief.** 리뷰 §4.1: `concept`가 기술·도구·알고리즘·방법론·결정을 한 평면에 담은 만능통(BFO상 continuant/occurrent 혼재). **attribute-first** — 6개 클래스 big-bang 금지, `kind` 속성 하나로 태깅하고 특정 kind가 고유 관계/속성을 요구할 때만 정식 subclass 승격(YAGNI). `decision`은 사건이므로 occurrent 레인(insight/log)으로.

**Tasks.**
1. `schema.yaml` `concept.fields`에 `kind: {type: enum, values: [technology, tool, algorithm, methodology]}` 추가.
2. 기존 concept 페이지 LLM 배치 태깅 — `sm:sync` 또는 일회성 스크립트, dry-run + 사람 승인(apply-profile UI 재사용). 미분류는 태그 없이 보존.
3. `wiki/integration.py` `INTEGRATION_SYSTEM`: concept 생성 시 `kind` 채우도록 유도. decision성 내용은 concept가 아니라 insight/log로 유도.
4. retrieval/CQ: Step 1 분류형 CQ(CQ9: kind별 필터) xfail 해제 — `kind` 필터 조회 지원.
5. 테스트: `tests/test_wiki_page.py`/스키마 테스트에 `concept.kind` enum 검증. CQ9 통과.

**검증.** `pytest -q` · CQ9(kind 분류) 통과 · `ruff check src` · schema round-trip 테스트.

**Exit criteria.** concept가 `kind`로 하위분류됨. decision은 occurrent로 유도. 분류형 CQ 통과. 클래스 수는 불변(속성만 추가).

**Rollback.** schema/integration revert. `kind` 필드 무시되면 무해.

**주의.** Step 5와 둘 다 `schema.yaml` 편집 — 병렬 시 충돌. **직렬(5 → 6) 권장** 또는 schema 편집만 rebase.

---

## Step 7 — [strongest] (게이트) 공리 + entity-resolution  (depends: 5, 6, coverage gate)

**Context brief.** 리뷰 §5 P2: 관계 공리(transitivity/inverse)와 `same_as` entity-resolution은 온톨로지가 순회에서 실제 값을 내는 지점이지만, **엣지가 충분히 없으면 무의미**. **DEFER 게이트**: Step 1 `typed_relation_coverage`가 지속적으로 >20% 且 대응 CQ(5 이행, 8 동일성)가 실가치를 입증할 때만 착수. full bitemporal / Neo4j 이관은 착수 금지(YAGNI).

**Tasks.**
1. `schema.yaml` relations에 `axioms` 선언 — `part_of: {transitive: true, inverse: has_part}`. `broader`(신설 concept 계층 SKOS): `{transitive: true, inverse: narrower}` — **신설 관계는 C1과 동일한 결합**이므로 `schema.yaml` relations + `model/schema.py` `RELATION_FIELDS` 상수 + `Entity` 데이터클래스 relation 필드 **세 곳 동시 추가**(하나만 추가하면 `_validate_schema` 또는 `Entity(**relation_values)`에서 크래시).
2. `wiki/retrieval.py`: `part_of`/`broader` 확장을 depth≤2 transitive closure로(폭주 방지 캡). inverse(has_part/narrower)는 저장 안 하고 조회 시 역인덱스 계산.
3. `wiki/lint.py`: `part_of` 사이클 탐지 추가.
4. `same_as` entity-resolution 파이프라인 — 동일 type(+kind) 내 exact slug → fuzzy title(RapidFuzz — **미설치**: `pyproject.toml` deps는 `PyYAML`뿐. 착수 시 의존 추가하거나 fuzzy 단계 생략) → semantic embedding ladder. ≥0.95 supersedes 후보 / 0.85~0.95 same_as 후보로 **사람 승인**. **자동 merge 금지**(거짓 merge는 조용·복구불가). merge=canonical 지정 + 엣지 재연결.
5. 테스트: 이행 CQ5(part_of 조상 전체), 동일성 CQ8(중복 concept) xfail 해제. 사이클 탐지 테스트.

**검증.** `pytest tests/test_competency_questions.py -q` (CQ5/CQ8 통과) · closure depth 캡 테스트 · `ruff check src`.

**Exit criteria.** coverage 게이트 충족 시에만 착수돼, 이행·동일성 CQ 통과. 자동 merge 없음.

**Rollback.** schema axioms + retrieval closure revert. ER은 사람 승인 전 자동변경 없으므로 데이터 안전.

**착수 금지(명시적 YAGNI/DEFER).** full bitemporal(valid×transaction 이중축), 정식 subclass 승격, Neo4j 이관, constraint-engine 추론기. 단일 사용자·수천 페이지 미만 상한. full bitemporal은 supersedes 체인이 소급정정 CQ에 실패할 때만 재검토.

---

## 플랜 변이 프로토콜

- **분할**: Step 3의 "질의 의도별 우선순위"(Task 4)가 커지면 Step 3.5로 분리.
- **삽입**: 재인제스트로 coverage가 다시 무너지면 Step 2.5(백필 재실행)를 Step 2 뒤 삽입.
- **재정렬**: Step 2 ∥ Step 3(비충돌). Step 5·6은 schema.yaml 충돌로 직렬 권장.
- **포기**: Step 7은 coverage 게이트 미충족 시 무기한 보류 — 실패 아님, 설계상 DEFER.
- **감사 추적**: 각 스텝 완료 시 이 파일 상단 표의 상태를 갱신하고 커밋 해시 기록.

## 보류 (명시적 범위 밖)

- full bitemporal(2축), Neo4j/트리플스토어 이관, RDF/OWL 직렬화, 정식 다중 subclass 클래스 폭발, constraint-engine 추론기(Partenit Stage4).
- Obsidian Graph/Dataview/MOC 재도입(선행 플랜에서 죽은 UI로 제거됨).

## 예상 순효과

- **측정 우선**: Step 1이 coverage/CQ 트립와이어를 세워 이후 회귀를 가시화.
- **회귀 방지 + 소비**: Step 2·3이 harmonization을 강제하고 엣지에 downstream 효과 부여 → dogfood 압력 발생.
- **의미 심화**: Step 4·5·6이 어휘 정리·시간 무효화·분류로 온톨로지 성숙도를 3단계(검증 계층)에서 4단계(추론 준비)로.
- **게이트된 추론**: Step 7은 데이터가 준비됐을 때만 공리/ER을 켠다 — 엣지 없는 그래프에 추론기 짓는 낭비 방지.
