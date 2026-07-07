# 온톨로지 아키텍처 사후 감사 — 재설계는 스키마만 바꿨고 데이터는 그대로다

- 저자: JunyoungJung
- 작성일: 2026-07-07
- 성격: **재설계 이후(post-implementation) 감사.** 2026-07-05 리뷰(제거됨 — git 히스토리 참조)가 권고한 경로(①타입 어휘 → ②스키마 코드화 → ③typed relations → ④시간성)가 실제로 shipped된 뒤, 그 결과를 라이브 vault로 검증한다.
- 배경 지식: [ontology-learning-guide.md](ontology-learning-guide.md)
- 근거: 코드(`schema.yaml`, `wiki/integration.py`, `model/entity.py`, `wiki/retrieval.py`, `wiki/lint.py`) + 라이브 vault 실측(2026-07-07) + 온톨로지/KG 레퍼런스 11종 재학습
- 방법: 18-agent workflow (자료 11 학습 → 온톨로지 렌즈 6 리뷰 → 종합). 6개 렌즈가 코드 라인 근거로 독립 수렴.

---

## 0. 요약 (TL;DR)

07-05 리뷰의 진단("온톨로지 없는 지식그래프")과 권고(마크다운-네이티브 경량 온톨로지 점진 도입)는 옳았다. 그리고 그 계획의 ①②③단계가 실제로 구현됐다 — `SCHEMA.md` prose가 `schema.yaml`로 코드화됐고, typed relation 6종이 domain/range와 함께 선언됐다.

**그런데 사후 감사 결과, ③단계(typed relations)는 스키마에만 존재하고 데이터는 한 개도 따라오지 않았다.**

- **현재 vault에 수집되는 데이터는 여전히 온톨로지가 아니다.** synapse 관리 391페이지 중 typed relation 사용 **0개**, 284개가 전부 무타입 `related`.
- 이것은 Hedden이 지목한 **"온톨로지를 따르지 않는 unharmonized KG"** = 최악 케이스. 조화 안 된 그래프는 LLM 성능을 오히려 해친다.
- 문제는 **스키마 부족이 아니라 TBox(스키마)는 있는데 ABox(데이터)가 그것을 인스턴스화하지 않는 것**이다. 07-05가 "표현력이 아니라 거버넌스 부재"라고 한 진단이 재설계 후에도 그대로 — 이제는 "스키마는 있는데 데이터가 스키마를 안 따름"으로 형태만 바뀌었다.
- **wiki는 사라질 필요가 없다.** Markdown 페이지 = 노드의 직렬화, wikilink = 엣지의 뷰. 엣지를 typed로 강제하면 wiki가 곧 graph다.
- 지금 필요한 건 더 정교한 스키마(axiom·bitemporal·subClass·Neo4j)가 아니라 **스키마를 실제로 따르는 데이터(harmonization)**. 그 전까지 추론 로드맵은 전부 사치.

---

## 1. 사용자의 두 의혹에 대한 직답

### 의혹 1 — "vault에 수집되는 데이터가 온톨로지가 아니라 기존과 동일한 방식 아닌가?"

**정확하다. 실측으로 확정.**

`schema.yaml`(L150–174)에 6종 typed relation과 domain/range/cardinality가 선언돼 있지만, synapse가 관리하는 **391페이지 중 typed relation 사용 0개**다. 284개가 전부 무타입 `related: [[x]]`. 온톨로지는 스키마와 ingest 프롬프트에만 존재하는 종이 위 픽션이고, 실제 vault는 예전 그대로다.

> 정정: workflow 종합 초안이 "typed 2건"이라 인용했으나 재검증 결과 그 2건은 전체 vault(2,240파일)에 섞인 **수기 노트**(`20_Reference/온톨로지-입문/...`, `40_Life/토스증권/투자원칙 IPS v2`)의 우연한 frontmatter 키다. synapse 산출물 기준으로는 6종 전부 **정확히 0개**.

### 의혹 2 — "온톨로지를 도입하면 Wiki 개념은 사라져야 하나?"

**아니다. 잘못된 이분법.**

Markdown 페이지는 노드의 *직렬화 표현*이고 wikilink는 엣지의 *뷰*다. wiki는 저장 계층, 온톨로지/그래프는 그 위 의미 계층 — 대체재가 아니라 층위가 다르다. 지금 문제는 "wiki라서"가 아니라 **"wikilink가 무타입이라서"**다. 엣지를 typed로 강제하는 순간 wiki가 곧 graph가 된다.

- Neo4j 이관은 391페이지 규모에서 **순수 YAGNI** — 병목은 순회 성능이 아니라 엣지 타이핑률 0. 로컬 우선·평문·git-diff·LLM 직독이라는 핵심 가치를 버리는 손해가 이득보다 크다. (07-05 §0 결론과 일치.)
- 바꿔야 할 것은 파일 포맷이 아니라 **자기규정**이다: *"personal wiki(문서가 지식 단위)"* → *"markdown으로 직렬화된 constraint-checked knowledge graph(노드/엣지가 지식 단위, 페이지는 그 뷰)"*.

---

## 2. 실측 증거 (스모킹 건)

| 항목 | 수치 | 의미 |
|---|---|---|
| synapse 관리 페이지 | 391 | Entities/Concepts/Insights/Logs/Profile |
| `uses` / `part_of` / `about` / `decided_in` / `supersedes` / `same_as` | **0 / 0 / 0 / 0 / 0 / 0** | typed relation 실사용 전무 |
| `related`(무타입) | 284 | 실제로 쓰이는 유일한 연결 = 폴크소노미 |
| `Logs`(활동로그) | 277 / 391 (71%) | episodic이 semantic을 익사시킴 |
| `concept` 클래스 | 31 (이질 범주 혼재) | 기술·도구·알고리즘·방법론·결정이 한 평면에 |
| retrieval | 문서선택 | provider가 slug top-k 선택 + 무타입 1-hop |

**온톨로지 스펙트럼상 위치**: taxonomy도, ontology도, KG도 아님. TBox(schema.yaml)는 존재하나 ABox(vault)가 그것을 전혀 인스턴스화하지 않는 **unharmonized 상태**. 07-05의 성숙도 평가(1.5~2단계)는 재설계로 스키마가 3단계 형태를 갖췄으나, **데이터 준수율 기준으로는 여전히 1.5단계**다.

---

## 3. 근본원인 — 왜 엣지가 0인가

LLM 게으름이 아니라, **시스템이 빈 그래프를 보상하도록 설계**됐다.

| # | 원인 | 위치 |
|---|---|---|
| A | ingest 출력 스키마가 관계를 optional로 둠. required = `[op, type, slug, title, body]` 5개뿐, 6종 관계·`related` 전부 optional array → 구조화 LLM은 채울 이유 없음 | `wiki/integration.py` `INTEGRATION_SCHEMA` |
| B | 프롬프트가 무타입 탈출구를 대놓고 허용. "**가능한 한** typed로", "related 유지 가능" soft 문구 → LLM은 최저비용 경로(생략/`related`) 선택 | `wiki/integration.py` `INTEGRATION_SYSTEM` |
| C | lint가 "있는" 관계만 검증. 존재하는 relation의 domain/range만 검사 → **관계 0개 페이지는 완벽히 유효**. 커버리지 게이트 없음 | `wiki/lint.py::_validate_relations` |
| D | retrieval이 typed/untyped를 한 바구니로 flatten. 관계 타입을 버리고 무타입 1-hop으로 소비 → **관계를 채워도 검색 결과 불변** → 채울 유인 0 | `wiki/retrieval.py::_expand_neighbors`, `wiki/links.py::neighbor_links` |

부수 확인: `model/entity.py::supersedes_history()`(L284)는 실제 시간추론 코드지만 supersedes 0건이라 **죽은 기능**. `SUPERSEDED_STATUS` 상수(정의됨)도 무효화 부수효과가 전무.

---

## 4. 렌즈별 결함 (6개 독립 리뷰 수렴)

### 4.1 클래스 설계 (taxonomy/ontology/KG + continuant/occurrent)
- continuant(project·company·concept·profile = 사물)과 occurrent(insight·log = 사건)이 한 평면에서 같은 관계 어휘를 공유.
- `concept` 만능통에 정보객체(swift-concurrency, solid-principles)와 decision(사건)이 혼재 — BFO상 범주 오류.
- subClassOf(subsumption) 계층 부재 → taxonomy조차 아님.

### 4.2 관계 의미론
- `about(any→any)`은 `related`의 순수 중복(SKOS related). 방향·도메인 규율 0 → 추론 연료 0.
- `part_of(any→any)`는 meronymy가 아니라 만능관계 — "log part_of concept" 같은 존재론적 난센스가 스키마상 합법.
- 공리(transitive/inverse/symmetric) 0개. `schema.yaml`에 axioms 필드 자체가 없음.

### 4.3 시간 모델
- valid-time 부재. `company.status`(target→…→hired) 같은 *변하는 사실*이 제자리 덮어쓰기됨 → 무효화·이력화 불가.
- supersedes는 필드만 있고 배선 안 됨(0건 + `apply.py`에 무효화 로직 전무).
- retrieval에 status·시간 필터 전무 → superseded/rejected 페이지가 최신 대체물과 동일 랭크. (07-05 §4 Phase3 우선순위 상승 지적이 데이터로 확증됨.)

### 4.4 Competency Questions
- 스키마가 CQ(top-down)에서 도출된 게 아니라 수집기 산출물(bottom-up)에서 역산됨 → 어느 필드도 "이 CQ 때문에 존재한다"는 추적성 없음.
- 관계형·계층형·시간형 CQ **전멸**. 현재 데이터 기준, typed relation 6종을 **삭제해도 답 가능한 CQ 수가 불변** = 장식.

### 4.5 retrieval / 추론
- ask 경로(`_retrieve_wiki`→`select_related`)는 wikilink조차 안 쓰는 순수 provider 문서선택 — Partenit Stage2(그래프)에도 미달.
- 유일한 1-hop 확장(`_expand_neighbors`)은 ingest의 `find_related_pages`에서만 돌고 ask에서는 안 씀 → 온톨로지 값어치(추론·제약) 0% 실현.

---

## 5. 개선 로드맵 (측정 → harmonization → 그 다음)

원칙: **엣지가 0인 그래프 위에 axiom·bitemporal·Neo4j를 짓는 건 전부 사치.** P0는 오직 harmonization.

### P0 — 지금 (데이터-현실 격차 해소)

| # | 조치 | 규모 | 파일/구체안 |
|---|---|---|---|
| P0-1 | **CQ 스위트부터** | small | `competency_questions.yaml` + `tests/test_competency_questions.py`. 10~15개 대부분 FAIL/xfail 시작 — 실패 목록이 "어느 관계가 밥값 하는가"의 증거. **신규 엔진 금지, 측정만.** |
| P0-2 | **ingest Gatekeeper** (최고 레버리지) | small | `INTEGRATION_SCHEMA`에서 `related` 삭제, 프롬프트 "가능한 한"→"반드시", 무타입 탈출구 제거. 근본원인 A+B 동시 타격. 없으면 백필해도 도로 썩음. `parse_ops`의 related 파싱은 legacy 로드 호환용만 유지. |
| P0-3 | **related→typed 백필** | medium | 284개 `related`를 (source.type, target.type)로 domain/range 제약 하에 6종 중 하나로 LLM 재분류(json enum 강제, drop 허용). `/sm:apply-profile`식 사람 승인 UI 재사용. 미분류는 `related_untyped`로 격리해 부채 가시화. `sm:sync`에 relation-fill 스테이지 연결. |
| P0-4 | **retrieval 관계타입 인지화 + coverage 지표** | medium | `neighbor_links`를 `{rel: [targets]}` 반환으로, `_expand_neighbors`에 타입 가중/필터(무타입 최저). ask 경로(`query.py::_retrieve_wiki`)가 typed 이웃확장을 실제 호출하게 배선. `/sm:doctor`에 `typed_relation_coverage %` + `legacy_related` 잔존율 노출. 근본원인 D 수정. |
| P0-5 | **죽은 어휘 정리** | small | `about` 삭제(=related 중복; schema/`WikiPage.about`/`RELATION_FIELDS`/프롬프트에서 제거). supersedes/same_as/decided_in은 대응 CQ로 정당화 못 하면 삭제, 되면 "보류→강제 충전" 대상. |

### P1 — 커버리지 오른 뒤
- `concept.kind` enum(technology|tool|algorithm|methodology) **attribute-first** 태깅 + `decision`을 occurrent 레인으로 이동. **6개 클래스 big-bang 금지.**
- supersedes 배선 + 최소 valid-time: `t_invalid` 1필드 신설, 발행 시 대상 `status=superseded` + 무효화 시각 자동 기입(`apply.py`). retrieval 기본 필터 = 현재 유효만, `include_history`는 recall만.
- episodic/semantic 레인 분리: `sm:ask`는 log 감점, `sm:recall`은 log를 observed_at순 순회.

### P2 — coverage >20% 도달 이후에만
- 관계 공리 활성화: `schema.yaml` relations에 axioms 선언(`part_of` transitive+inverse=has_part, `broader` 신설 transitive+inverse=narrower). retrieval을 depth≤2 transitive closure로(폭주 캡). lint에 `part_of` 사이클 탐지.
- `same_as` entity-resolution/merge: 동일 type(+kind) 내 exact slug → fuzzy title(RapidFuzz) → semantic embedding ladder. ≥0.95 자동 supersedes 후보, 0.85~0.95 same_as 후보로 사람 승인. **자동 merge 절대 금지**(거짓 merge는 조용하고 복구불가).
- **명시적 DEFER(착수 금지)**: full bitemporal(valid×transaction 이중축), subClass 정식 승격, Neo4j 이관, constraint-engine 추론기. 단일 사용자·수천 페이지 미만에서 전부 YAGNI. full bitemporal은 supersedes 체인이 소급정정 CQ에 실패할 때만 승격.

---

## 6. 목표 온톨로지 (스케치)

```
Thing
├─ Continuant (사물 — 시간에 걸쳐 동일성 유지)
│    Project, Company, Profile,
│    Concept ▷ {Technology, Tool, Algorithm, Methodology}
└─ Occurrent (사건 — 시간 위에서 일어남)
     Insight, Log(episodic 활동로그, retrieval 별도 레인), Decision(← concept에서 분리)

관계
  uses        (Project/Company/Concept/Insight/Profile → Concept)              공리 none
  part_of     (Project/Company/Concept 내)          transitive, inverse=has_part
  broader     (Concept 내, 신설 SKOS broader)        transitive, inverse=narrower
  decided_in  (Decision/Project/Company → Insight/Log)                         공리 none
  supersedes  (동일 type)   무효화 축 — 발행 시 대상 t_invalid=observed_at 자동
  same_as     (동일 type)   symmetric+transitive — ER 파이프라인 있을 때만 keep
  ✗ about     삭제 (related의 순수 중복)

시간
  valid-time만 도입 (created=t_valid 재사용 + t_invalid 1필드 신설).
  transaction-time은 observed_at/updated로 근사. full bitemporal은 YAGNI.
  retrieval 기본 필터 = t_invalid null(현재 유효)만. include_history/recall만 전체 이력.

provenance
  관계마다 근거 slug/문장 필드 필수화 (Graphiti식 edge fact) — 무효화·감사 가능하게.
```

> 주의: 목표 트리이되 **즉시 6개 클래스 폭발 금지**. 1단계는 `Concept.kind` enum 속성 태깅(attribute-first), 특정 kind가 고유 관계/속성을 요구할 때만 정식 subClass 승격(YAGNI).

---

## 7. Competency Questions (측정 백본)

온톨로지를 "답해야 할 질문"으로 역검증. P0-1에서 테스트로 박제.

1. `swift-concurrency`를 uses하는 project는? *(관계형: uses 역방향)*
2. 특정 company의 status가 target→applied→hired로 언제 바뀌었나? *(시간형: 상태 이력)*
3. 이 decision이 decided_in된 log/insight는? *(인과·근거형)*
4. concept X의 broader는 무엇이고 narrower에는 무엇이 있나? *(계층형)*
5. project A가 part_of로 속한 모든 상위 맥락(조상 전체)은? *(이행형: transitive closure)*
6. 지금 유효한 사실만 보여줘 — 무효화(t_invalid)된 과거 제외 *(시간형: active filter)*
7. 주제 X에 대한 내 입장이 시간순으로 어떻게 바뀌었나? *(supersedes 체인 / recall)*
8. `swift-concurrency`와 'Swift Concurrency'는 같은 개체인가? 중복 concept는? *(동일성: same_as/ER)*
9. concept 중 kind가 methodology인 것만 / technology인 것만 나열 *(분류형)*
10. 이 typed edge('X uses Y')의 근거가 된 원본 문장/페이지는? *(provenance)*
11. company Z 관련 project·insight·log를 관계 타입별로 묶어 보여줘 *(다중관계형)*
12. log 제외, 지식 노드(concept/insight)만으로 X 검색 *(episodic/semantic 분리)*
13. 가장 최근에 어떤 사실이 무엇을 supersedes 했나? *(무효화 감사)*
14. 이 project에서 반복 등장한 log 패턴에서 승격할 insight/decision은? *(episodic→semantic 승격)*
15. 관계가 하나도 없는(고아) 페이지는? *(그래프 격리 노드 — 커버리지 진단)*

현행 데이터로는 1~14 사실상 전멸, 15만 부분 가능.

---

## 8. 07-05 리뷰 대비 — 무엇이 확증되고 무엇이 갱신됐나

| 07-05 리뷰 | 07-07 사후 감사 |
|---|---|
| "온톨로지 없는 지식그래프" 진단 | 확증. 재설계로 스키마는 생겼으나 데이터가 안 따라와 여전히 유효 |
| "RDF/OWL/그래프DB 전환 비권장, 마크다운 유지" | 확증. Neo4j = YAGNI, wiki는 graph의 물리적 뷰 |
| 권고 경로 ①타입→②스키마코드화→③typed relations→④시간성 | ①②③ shipped. **단 ③은 스키마 선언만, 데이터 준수 0** — 새 발견 |
| "표현력이 아니라 거버넌스 부재" | 형태 갱신: 이제 "스키마는 있는데 데이터가 스키마를 안 따름"(unharmonized) |
| MOC/Dataview/Graph는 삭제 대상(07-06 개정) | 무관 — 죽은 UI 아니라 죽은 **엣지**가 핵심 병목 |
| Phase3 시간성 우선순위 상승 | 확증. supersedes 죽은 코드 + valid-time 부재 데이터로 확인 |

**핵심 갱신**: 07-05는 "관계를 도입하라"였고, 07-07은 "관계를 **강제**하고 **소비**하고 **측정**하라"다. 선언(declare)과 준수(harmonize)는 다른 문제다.

---

## 9. 핵심 한 줄

**지금 필요한 건 더 정교한 스키마가 아니라 스키마를 실제로 따르는 데이터다.** axiom·bitemporal·Neo4j 논쟁은 엣지가 채워진 뒤의 사치. **P0 = harmonization**: Gatekeeper로 강제 → 백필로 채움 → retrieval이 소비 → CQ로 측정. wiki는 사라지지 않는다 — graph의 물리적 뷰가 된다.

---

## 부록 A. 학습한 레퍼런스

| 분류 | 자료 | 핵심 |
|---|---|---|
| 표준/정의 | Neo4j — Taxonomy vs Ontology vs KG | taxonomy/ontology=설계도, KG=구현. taxonomy는 KG 필수 선행조건 아님 |
| 표준/정의 | Hedden — Ontologies vs KG | KG=ontology의 인스턴스화. **온톨로지를 따르는 KG라야 LLM 성능↑** |
| 표준/정의 | Jay Wang — OWL/RDF/RDFS/SKOS | RDF=방향+타입 엣지(트리플), RDFS=subClassOf, OWL=추론 공리, SKOS=broader/narrower 경량 |
| 표준/정의 | PuppyGraph — KG vs Ontology | 온톨로지는 데이터가 요구할 때 자란다 |
| 방법론 | ER2023 — Competency Questions survey | CQ로 온톨로지 범위 검증. 답 못 하는 CQ = 누락 신호 |
| 방법론 | CACM — Lightweight/Rapid Ontology Engineering | UPON Lite식 점진 단계(용어→분류→관계→parthood) |
| 에이전트 메모리 | Graphiti 가이드 | bitemporal edge, entity/edge extraction, fact invalidation |
| 에이전트 메모리 | Partenit — Ontological Memory Roadmap | Knowledge Store → Constraint Engine 단계 진화 |
| 에이전트 메모리 | Zylos — AI Agent Memory Architectures | Zep/Graphiti 벤치마크, episodic/semantic 분리 |
| 에이전트 메모리 | decodingai — Neo4j Agent Memory | POLE(Person/Object/Location/Event) 상위 온톨로지 |
| 개인 KG | Pavlyshyn — Personal KG in Obsidian | 문서→그래프 전환, typed link |
