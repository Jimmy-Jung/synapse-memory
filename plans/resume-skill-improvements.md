---
plan: resume-skill-improvements
objective: Codex+Claude 이중 리뷰 결론을 반영해 resume 스킬과 쿠팡 산출물을 개선한다
created: '2026-07-01'
author: JunyoungJung
status: proposed
source_review: Codex built-in review + Claude review agent (2026-06-30)
repos:
- synapse-memory (스킬)  branch: feat/resume-skill-4phase-workflow
- obsidian vault (쿠팡 산출물)  20_Reference/Companies/coupang/
---

# Blueprint — resume 스킬 & 쿠팡 산출물 개선

## 배경 (리뷰 취합 결론)

- 산출물은 견고: 날조 없음, 초안→최종 정직성 루프 작동. Codex는 in-scope 이슈 0.
- 최대 레버리지 2개: **①정직성 게이트(초안 팩트체크 미해결 항목이 최종에 유출)** **②실질 tailoring(최종본이 기준 이력서 ~95% 복사)**.
- 부차: 실행정책 현실화, idempotency/status, 템플릿 정리.
- 기각: smart-report 링크 미해석 주장 → `smart-report.md` 실존, 정상 해석 (에이전트 오독).

의존: Step 1→2 직렬(둘 다 SKILL.md 편집). Step 3(vault)은 다른 repo라 Step 1/2와 **병렬** 가능. Step 4 선택·사용자 주도.

model tier: Step 3 = strongest(산문·정직성 판단). Step 1/2 = default(구조적 편집). Step 4 = default.

rollback: 스킬 = 이미 feat 브랜치 → step별 커밋, revert 가능. vault = 편집 전 파일 백업/‑git.

---

## Step 1 — [스킬·default] 정직성 게이트 + 실행정책 현실화 + idempotency

**Context brief**: `skills/resume/SKILL.md`는 4단계 워크플로. 리뷰가 지적: (a) Phase 3 draft의 "제출 전 팩트체크(증빙 준비/표현 주의)" 항목이 해결 안 된 채 Phase 4 최종본에 유출됨(쿠팡 AI-마스킹 문구 실제 사례), (b) "실행정책 필수(최고모델+Ultracode)"는 스킬이 강제 불가한 aspirational, (c) 재실행 시 승인된 resume.md 덮어쓰기 규칙 없음.

**Tasks**
1. Phase 4에 규칙 추가: "resume-draft.md의 '제출 전 팩트체크' 중 [증빙 준비]/[표현 주의] 항목은 **해결(완화·확인·증빙)되기 전 최종 resume.md에 반영 금지**. 미해결 시 해당 문장을 정성화하거나 제외한다."
2. 실행정책 §를 재작성: "필수" → "권장/best-effort. 하네스가 지원하면 조사 단계를 병렬 fan-out, 아니면 순차 실행 — **중요한 것은 단계 게이트지 병렬성이 아님**. 모델/effort는 호출 환경 설정이며 스킬이 강제할 수 없음을 명시."
3. Phase 0/산출물에 idempotency 규칙: "기존 resume.md 존재 시 사용자에게 덮어쓰기/버전 확인. 승인된(status: approved) 최종본은 자동 재생성 금지."
4. plugins/sm/skills/resume/SKILL.md 미러 동기화.

**Verification**
- `diff skills/resume/SKILL.md plugins/sm/skills/resume/SKILL.md` → 빈 출력.
- SKILL.md에 "팩트체크", "덮어쓰기", "best-effort"/"순차" 문자열 존재(grep).

**Exit criteria**: 두 SKILL 복사본 동일, 3개 규칙 반영, Phase 번호·구조 깨지지 않음.

---

## Step 2 — [스킬·default] 템플릿·엣지케이스 정리  (depends: Step 1)

**Context brief**: references/ 템플릿과 SKILL의 세부 불일치·미명세를 정리.

**Tasks**
1. **wikilink 형식 통일**: `resume-template.md`, `company-analysis-template.md`, `draft-template.md`, `style-guide.md`의 `[[Entities/Projects/<file>]]` → bare `[[<file>]]` (vault shortest-path 해석). 한 줄 주석: "vault가 basename으로 유일 해석; 경로형 금지".
2. **no-JD 모드**: SKILL Phase 1 / company-analysis §4에 추가 — "JD 없으면 회사 채용 페이지에서 유사 포지션 JD를 조사해 §4를 채우거나, JD 없이는 Phase 1까지만 진행하고 매칭은 보류."
3. **산출물 스펙에 `_source-card.md` 명시**: SKILL "산출물(한 폴더)" 블록에 "기존 flat 카드 이관본" 라인 추가(또는 Phase 0에서 analysis.md frontmatter로 병합 후 삭제하도록 규칙화 — 택1).
4. **resume-template frontmatter에 `status: draft|approved`** 필드 추가.
5. minor: 복수 포지션이면 대상 포지션 1개 확정받기(1줄); interview-notes.md를 Phase 1이 명시적으로 소비; plugin 복사본 상단에 `# generated mirror — edit skills/, not plugins/` 주석.
6. 미러 동기화.

**Verification**
- 템플릿에 경로형 wikilink(`[[Entities/Projects/...]]`) 잔존 0(grep).
- 미러 parity 동일.

**Exit criteria**: 템플릿 5종·SKILL 일관, 엣지케이스 3종 명세, 미러 동일.

---

## Step 3 — [vault·strongest] 쿠팡 resume.md 실질 tailoring + 정직성  (parallel with Step 1/2)

**Context brief**: `20_Reference/Companies/coupang/resume.md`가 기준 이력서와 ~95% 동일. `analysis.md`가 만든 쿠팡 인사이트가 산문에 미반영. 초안 팩트체크의 AI-마스킹 문구가 최종에 그대로 실림.

**Tasks**
1. **Leadership Principles 정렬**: 간단한 소개 or 경력 요약에 "Influence without Authority" 예시 1문장 — 수학에심장을달다 클린아키텍처 도입 시 회의적 팀장을 샘플·지표로 설득한 서사(기준 이력서 L190 근거).
2. **O2O/트래픽 프레이밍**: 경력 요약에 analysis가 세운 "대규모·실시간 서비스의 안정성/모듈화" 프레이밍을 명시적으로.
3. **JD #2(빠르고 안정적 사용성) 근거 보강**: 캐시히트 90%(자가측정) 단일 의존 축소 → 크래시율 2.1→0.8% 등 검증된 안정성 지표를 duty #2에 함께 배치.
4. **AI-마스킹 문구 정직성**: resume.md 핵심역량의 "외부 LLM 전 자동 마스킹·인간 최종 승인을 도구 레벨에서 강제" → 프로필 근거 수준으로 완화(예: "외부 LLM 사용 전 마스킹·인간 승인 단계를 두는 방식으로 설계") 또는 본인 보증 시 유지. 초안 팩트체크 항목도 [해결]로 갱신.
5. minor: 모듈 프로젝트 "책임별 4개 패키지" 수치 복원(기준 L72); resume.md frontmatter `status: draft`.

**Verification**
- resume.md에 Leadership Principle/O2O 프레이밍 문장 존재.
- AI-마스킹 문구가 프로필 근거 범위 내(초과 주장 제거).
- 재-팩트체크(경량): 새 주장 모두 analysis/카드/기준 이력서에 추적.

**Exit criteria**: 사용자 검토 게이트 — tailoring이 "재배치 이상"임을 사용자가 확인, 정직성 항목 클리어.

---

## Step 4 — [vault·선택·사용자] 중복·무관 정리

**Context brief**: 리뷰 부수 발견.

**Tasks**
1. `30_Creative/Drafts/Resume - 쿠팡 (2026-06).md`(기존 별도 쿠팡 이력서) — 신규 `Companies/coupang/resume.md`와 중복. 사용자 결정: archive/merge/삭제.
2. (무관·별건) Codex P2: `Concepts/vault-commit.md:420-424` 커밋해시 표 손상(`2f1f7c1` 미해결·root 행 누락) — 이번 작업과 무관하나 실재. 사용자 확인 후 복원.

**Verification**: 사용자 확인. (자동 삭제 금지 — 사용자 소유·비생성 파일)

**Exit criteria**: 사용자가 중복 처리 방침 결정.

---

## 실행 순서 요약

```
Step 1 (스킬 게이트/정책)  ─┐
Step 2 (템플릿 정리)        ─┴─ 직렬 (SKILL.md 공유)      [default 모델]
Step 3 (쿠팡 resume tailoring)  ── 병렬 (다른 repo)        [strongest 모델]
Step 4 (중복 정리)          ── 선택·사용자 주도 (언제든)   [default]
```

우선순위: **Step 1 + Step 3** 먼저(정직성 누수·핵심 tailoring). Step 2·4는 후속.
