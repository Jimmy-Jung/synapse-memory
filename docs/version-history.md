# 버전 이력 (v2.0 이전)

작성자: JunyoungJung  
작성일: 2026-07-08

이 문서는 README에서 분리한 **v2.0 이전의 기능 도입 흐름**을 정리합니다. README는
현재(v2.0) 기준으로만 설명하고, 여기서는 각 기능이 언제 들어왔는지를 남깁니다.
버전별 전체 변경 내역은 [CHANGELOG.md](../CHANGELOG.md)를 참고하세요.

## 주요 이정표

| 버전 | 시점 | 도입된 것 |
| --- | --- | --- |
| **2.0.0** | 2026-07-07 | 구조 리디자인(big-bang) + 온톨로지 완성. 단일 Entity 모델, typed relation 지식그래프, valid-time 무효화, schema 기반 lint 검증 |
| **1.20.0** | 2026-07-03 | v2.0 재설계 직전의 마지막 1.x 정비 |
| **1.17.0** | 2026-06-15 | 자동 wiki 엔진 — `watch install` 한 번으로 대화가 20분마다 wiki에 자동 통합. collect→ingest→watch 파이프라인 확립 |
| **1.16.0** | 2026-06-11 | `ask --save` Insight 축적, 세션 자동 컨텍스트 주입 hook(`hook install`), `context render` |
| **0.9.0** | 2026-05-17 | Profile 항목별 GUI 승인(`apply-profile`), 프로젝트 컨텍스트 등록(`setup`)/갱신(`sync`), MemoryInbox/DailyReports 폴더 마이그레이션 |
| **0.6.x–0.8.x** | 2026-05-12~15 | 초기 CLI, raw mirror, persona(회상·이력서·의사결정) 기반 다지기 |

## 기능별 도입 배경

### 자동 wiki 엔진 (v1.17.0)

v1.17.0 이전에는 사용자가 매일 `daily`를 직접 돌려 정리했습니다. v1.17.0부터 launchd
기반 `watch`가 20분마다 collect+ingest를 자동 실행해, 대화가 쌓이는 대로 wiki가
유지되도록 바뀌었습니다. 이 파이프라인 동작 원리는 현재 README의
"파이프라인 동작 원리" 절에 그대로 이어집니다.

### Insight 축적과 컨텍스트 주입 (v1.16.x)

- `ask --save`: 좋은 답변을 `<vault>/Insights/YYYY/MM/`에 insight 엔티티로 남겨 다음
  질문의 검색 대상이 되게 했습니다.
- `hook install` + `context render`: 세션 시작 시 Profile/DecisionPatterns 요약을
  자동 주입하는 전역 hook을 도입해, 프로젝트마다 marker를 수동 관리하지 않아도
  되게 했습니다.

### Profile 승인과 프로젝트 등록 (v0.9.0)

- `apply-profile`: MemoryInbox candidate의 ProfileFact/DecisionPattern을 항목별로
  승인받아 Profile.md/DecisionPatterns.md에 반영합니다.
- `setup`/`sync`: repo 파일을 수정하지 않고 프로젝트를 registry에 등록하고, marker와
  캐시를 갱신합니다.

## v2.0 재설계 요약

v2.0.0은 그간 흩어져 있던 카드/리뷰 큐/다단계 인제스트를 걷어내고 다음으로 통일했습니다.

- **단일 Entity 모델**: 6종 엔티티(project/company/concept/insight/log/profile),
  단일 스키마 `src/synapse_memory/schema.yaml`.
- **typed relation 지식그래프**: `uses`/`part_of`/`broader`/`decided_in`/
  `supersedes`/`same_as`. 검색이 관계를 실제로 따라갑니다.
- **valid-time 무효화**: `supersedes`로 옛 사실 자동 무효화, 기본 검색은 현재 유효한
  사실만.
- **provider-only 검색**: 로컬 임베딩/벡터/BM25 제거, provider가 관련 페이지 선택.

내부 설계·검증 기록(참고한 외부 자료가 아니라 프로젝트 자체 문서):
[specs/021-unified-model/design.md](../specs/021-unified-model/design.md),
[specs/022-ontology-completion/review.md](../specs/022-ontology-completion/review.md).
설계에 참고한 외부 온톨로지/KG 자료는 최상위 [README](../README.md#설계-철학)의
"설계 철학" 절과 [specs/022-ontology-completion/learning-guide.md](../specs/022-ontology-completion/learning-guide.md)를 참고하세요.
