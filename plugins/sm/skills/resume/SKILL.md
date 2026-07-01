---
name: resume
description: Use when the user wants a company-tailored résumé (e.g. "쿠팡 지원할건데 이력서 써줘", "Y 회사용 resume 만들어줘", "<회사명> 경력기술서 초안"). Runs a 4-phase native workflow — deep company research → project matching → draft → final résumé — using the vault's Entities/Projects cards and the reference quality bar in references/.
---

# /sm:resume — 회사 맞춤 이력서 (조사 → 매칭 → 초안 → 최종)

회사명/slug + 채용 공고를 받아 **4단계**로 회사 맞춤 경력기술서를 만든다.
얇은 한 방 합성이 아니라, 회사를 깊게 조사하고(웹 포함) → 내 프로젝트와 매칭 → 초안 검토 → 최종 산문화하는 네이티브 워크플로다.

품질 기준선: `references/resume-template.md` + `references/style-guide.md`. 산출물은 이 수준(기준 샘플 `정준영 2026_개선 0514.md`)에 맞춘다.

## 실행 정책 (권장 · best-effort)

스킬은 프롬프트이지 런타임이 아니다 — 모델/effort/병렬성을 **강제할 수 없다**. 아래는 호출 환경이 지원할 때의 권장이다.

- **모델·effort**: 가능하면 가장 높은 최신 모델 + 최고 effort로 실행. (호출 시 사용자/하네스가 설정)
- **오케스트레이션**: 하네스가 지원하면 무거운 단계(회사 조사·프로젝트 매칭)를 **Ultracode/멀티에이전트로 병렬 fan-out**, 아니면 **순차 실행**한다. Codex에서도 동급 최고 모델·reasoning 권장.
- **중요한 것은 병렬성이 아니라 단계 게이트**(특히 Phase 3 초안 검토, Phase 4 팩트체크)다. 병렬 불가 환경이어도 게이트만 지키면 품질은 유지된다.
- 본 스킬은 vault(Obsidian) 컨텍스트에서 동작하며 경로는 vault 루트 기준이다.

## 입력

- **회사**: 이름 또는 slug (예: `쿠팡`, `coupang`).
- **공고**: JD 텍스트 또는 URL(예: Wanted/회사 채용 페이지). 없으면 아래 "no-JD" 처리.

## 소스 자료 (synapse-memory 수집 데이터 전부 활용)

Entities/Projects 만이 아니라 vault 의 synapse-memory 수집 데이터를 **모두** 활용한다:

- `Entities/Projects/*.md` — 프로젝트 카드 (이력서 프로젝트의 1차 근거)
- `Profile/*.md` — voice·강점·의사결정 패턴·커리어 서사 (`jeong-junyoung-career-narrative.md`, `ios-development.md`, `decision-patterns.md`, `ai-profile.md`)
- `Concepts/*.md` — 기술·도구 노트 (AI 도구·자동화·CS 등 보조 근거)
- `Insights/**` — 회고·운영 로그 (서사·맥락 보강)
- 기존 이력서/자소서, `90_System/AI/Profile.md`, `Companies/*` 카드

Profile 은 톤·강점, Entities 는 프로젝트 사실, Concepts/Insights 는 보강 근거로 쓴다. 자료에 없는 사실은 만들지 않는다.

## Phase 0 — 준비 & cold-start 점검

1. 회사 slug 확정(영문 소문자, 예: `coupang`).
2. `20_Reference/Companies/<slug>/` 폴더를 만든다. 기존 flat `Companies/<slug>.md` 가 있으면 폴더로 옮겨 `_source-card.md` 로 보존한다(핵심 frontmatter는 analysis.md 로 흡수).
3. **소스 자료 점검**: 위 "소스 자료"(Entities/Profile/Concepts/Insights + 기존 이력서/자소서)에 경력 자료가 있는지 확인한다.
   - **있으면** → 그걸 1차 자료로 Phase 1 진행.
   - **첫 사용이고 이력서·자소서·프로젝트 카드가 전혀 없으면 → 인터뷰 모드**: `references/interview-guide.md` 를 따라 구조화 인터뷰로 경력 사실(회사·프로젝트 STAR·역량·학력·링크)을 수집해 `Companies/<slug>/interview-notes.md` 로 정리한 뒤 Phase 1 로 넘어간다. (interview-notes.md 가 유일한 sink; Profile 갱신은 별도 승인 흐름) 인터뷰로 드러난 프로젝트는 자동으로 카드화하지 않고, 승격 여부를 사용자에게 안내한다.
4. **복수 포지션**: 회사에 지원 가능 포지션이 여럿이면 대상 포지션 1개를 사용자에게 확정받고 그 하나의 키워드셋으로 매칭한다.
5. **idempotency**: `Companies/<slug>/resume.md` 가 이미 있으면 사용자에게 **덮어쓰기 / 버전 분기(`resume-v2.md`)** 를 확인한다. `status: approved` 인 최종본은 **자동 재생성하지 않는다**.
6. 소스 자료는 **읽기/링크 전용**이다. **새 프로젝트 폴더/카드를 만들지 않는다** — 기존 카드만 링크한다.

## Phase 1 — 회사 심층 조사 → `Companies/<slug>/analysis.md`

`references/company-analysis-template.md` 골격으로 작성. **JD 요약에서 그치지 않는다.**

- 웹 조사: 회사 홈페이지·제품, 기술블로그/컨퍼런스/오픈소스, 최근 뉴스·IR, 인재상·평판(장단점 균형).
- JD 는 키워드로 분해하고 "이 공고가 진짜 보는 것"을 추론한다.
- **no-JD**: 공고 텍스트/URL 이 없으면 회사 채용 페이지에서 유사 포지션 JD 를 조사해 §4 를 채운다. 그래도 없으면 Phase 1(회사 조사)까지만 진행하고 §7 매칭·초안은 보류한 뒤 사용자에게 JD 를 요청한다.
- 인터뷰 모드였다면 `interview-notes.md` 를 프로젝트 근거로 함께 읽는다.
- 모든 비자명 주장에 출처 URL. 검증 불가 수치는 적지 않는다.
- 웹 도구: WebSearch/WebFetch 또는 exa. **`mcp__claude-in-chrome__*` 는 사용하지 않는다** (인터랙티브 브라우징은 `/browse` 스킬).
- Ultracode(가능 시): 개요/제품/엔지니어링문화/문화·인재상/JD 를 별도 에이전트로 병렬 조사 후 통합.

## Phase 2 — 프로젝트 매칭

- `Entities/Projects/*.md` 를 스캔(glob)하고 회사 키워드와 매칭되는 카드를 랭킹한다. (Ultracode 가능 시 매칭 에이전트 fan-out)
- `Profile/*` 에서 voice·강점, `Concepts/`·`Insights/` 에서 보강 근거를 함께 끌어온다.
- analysis.md §7(키워드→프로젝트 표)을 채운다. 각 행에 `[[<file>]]` 링크(vault 가 basename 으로 유일 해석; 경로형 금지).
- 카드에 실재하는 사실·수치만 사용. 약하게 커버되는 요구사항은 gaps 로 남긴다.

## Phase 3 — 초안 → `Companies/<slug>/resume-draft.md`

`references/draft-template.md` 골격으로 작성.

- 키워드→프로젝트 매핑 확정(wikilink 필수), 한 줄 소개 후보, 경력 요약, 핵심 역량, 강조 프로젝트 3~5개의 STAR bullet 씨앗.
- 정량지표는 카드 근거 + 측정 맥락만(style-guide 정직성 규칙).
- **"제출 전 팩트체크" 섹션을 채운다**: 카드에 근거가 약하거나 프로필을 초과하는 주장은 `[증빙 준비]`/`[표현 주의]` 로 표시.
- **여기서 멈추고 사용자에게 초안을 검토받는다.** 승인 후 Phase 4.

## Phase 4 — 최종 → `Companies/<slug>/resume.md`

`references/resume-template.md` 구조 + `references/style-guide.md` 톤으로 초안을 산문화한다.

- **정직성 게이트(필수)**: resume-draft.md "제출 전 팩트체크"의 `[증빙 준비]`/`[표현 주의]` 항목은 **해결(완화·확인·증빙)되기 전 최종본에 그대로 반영 금지**. 미해결이면 그 문장을 정성화하거나 제외하고, 초안 팩트체크 항목도 `[해결]` 로 갱신한다.
- **실질 tailoring**: 섹션 재배치에 그치지 말고 analysis 의 회사 특이 인사이트(인재상/원칙 정렬, 도메인 프레이밍, JD 핵심 업무별 근거 지표)를 산문에 반영한다.
- 회사 매칭 프로젝트/역량을 상단 배치. 회사·학력·자격증 등 고정 정보는 기준 이력서에서 가져오되 강조 순서만 회사에 맞춘다.
- 자료에 없는 사실 금지. STAR 4블록(문제/역할/해결/성과), before→after 수치.
- frontmatter 에 `status: draft`. 사용자 승인 시 `status: approved` 로 갱신(재생성 방지).

## 산출물 (한 폴더)

```
20_Reference/Companies/<slug>/
  analysis.md        # 회사 심층 분석 (출처 포함)
  resume-draft.md    # 프로젝트 링크 + 섹션 재료 + 제출 전 팩트체크 (검토 게이트)
  resume.md          # 최종 경력기술서 (status: draft|approved)
  interview-notes.md # (cold-start 인터뷰 시에만)
  _source-card.md    # (기존 flat Companies/<slug>.md 이관본, 있을 때만)
```

각 산출물 생성 후 저장 위치 + 핵심 요약을 사용자에게 알린다.

## 빠른 fallback (선택)

깊은 조사 없이 초벌만 빠르게 뽑을 때만:

```bash
SYNAPSE_FROM_AGENT=1 synapse-memory persona draft-resume "<회사 slug 또는 이름>"
```

이 CLI 경로는 RAG 기반 1회 합성이라 웹 조사·초안 게이트가 없다. 정식 산출물은 위 4단계로 만든다.

## references/

- `resume-template.md` — 최종 이력서 골격
- `style-guide.md` — 톤·STAR·정량지표 정직성 규칙
- `company-analysis-template.md` — analysis.md 골격
- `draft-template.md` — resume-draft.md 골격
- `interview-guide.md` — cold-start(첫 사용·자료 없음) 인터뷰 질문 흐름
