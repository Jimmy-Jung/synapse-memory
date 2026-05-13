# Quickstart Smoke Results — Timeline Recall

Author: Synapse Memory Maintainers
Date: 2026-05-12
Branch: `002-timeline-recall`
Commit: `e1263d4`

## Summary

T051 quickstart smoke was executed on the user machine after installing `apfel` and the project `rag` extra.

Result: **executed with failures documented**.

| Step | Command | Exit | Result |
|---|---:|---:|---|
| Preflight | `synapse-memory doctor` | 0 | PASS |
| Preflight | `synapse-memory card list` | 0 | PASS — 11 ProjectCards + 2 CompanyCards |
| Preflight | `synapse-memory rag index` | 0 | PASS — 13 vectors indexed |
| §1 | `me what-did-i-think "클린 아키텍처" --timeline` | 0 | PASS — timeline markdown rendered |
| §2a | `me what-did-i-think "클린 아키텍처" --by time` | 0 | PASS — same timeline result shape |
| §2b | `me what-did-i-think "클린 아키텍처" --by distance` | 1 | FAIL — Claude wrapper returned `envelope이 dict 아님: list` |
| §3 | `me what-did-i-think "클린 아키텍처" --timeline --by distance` | 1 | PASS — expected conflict |
| §4a | `me what-did-i-think "프로젝트" --timeline --limit 2` | 0 | PASS — two cards rendered |
| §4b | `me what-did-i-think "프로젝트" --timeline --limit 0` | 2 | PASS — expected limit validation |
| §5 | `me what-did-i-think "전혀 매칭 안 되는 주제 zzz" --timeline` | 0 | FAIL — vector search still returned 8 cards, so zero-result UX was not observed |
| §6 | `me what-did-i-think "어떤 주제" --timeline` | 0 | NOT VERIFIED — current vault does not provide an all-null metadata fixture |
| §7 | `me what-did-i-think "클린 아키텍처"` | 1 | FAIL — same distance-mode Claude wrapper envelope error |

Notes:
- The first attempt before `rag index` returned zero cards for timeline queries. After indexing, timeline mode produced actual card output.
- Hugging Face emitted unauthenticated download warnings during embedding model loads. This did not block timeline mode.
- The quickstart fixture in `quickstart.md` does not exactly match the current user vault. The observed card IDs reflect the current vault state.

## Transcript

```text
$ synapse-memory doctor
Synapse Memory 환경 진단
============================================
✓ apfel 설치: /opt/homebrew/bin/apfel
  버전: apfel v1.3.3
✓ Apple Silicon (arm64)
✓ macOS 26.3.1 (Tahoe+)
✓ L0 루트: /Users/<user>/.synapse/private (0700)
✓ Claude Code CLI: /Users/<user>/.local/bin/claude [2.1.139 (Claude Code)] (model=sonnet)
============================================
✓ 준비 완료
[exit 0]

$ synapse-memory card list

[Project Cards]   /Users/<user>/Library/Mobile Documents/iCloud~md~obsidian/Documents/20_Reference/Projects
ID                        STATUS       ROLE                      PERIOD
-------------------------------------------------------------------------------------
-----2026                 draft
CareLog                   draft
Smart_Report              draft
Tablet                    draft
ai-symbiote               draft
dansim-ios                active
mobile-ios-slc-tablet     draft        iOS 개발자
projects                  draft                                   ~ 2026-05
v2                        draft
이력서-2026                  draft        iOS 개발자                   2023-11
샘플지원-2026                 draft        iOS 엔지니어 (지원자)            2026-05 ~ 2026-05

[Company Cards]   /Users/<user>/Library/Mobile Documents/iCloud~md~obsidian/Documents/20_Reference/Companies
ID                        STATUS         COUNTRY  POSITIONS
-------------------------------------------------------------------------------------
danggeun                  target         KR       0
샘플회사                     hired          KR       2

총 13개
[exit 0]

$ synapse-memory rag index
인덱싱 시작 (rebuild=False)
  [project] 11개 임베딩 중...
  [company] 2개 임베딩 중...

인덱싱 완료: project=11 company=2 bytes=12117
총 벡터: 13
[exit 0]

$ synapse-memory me what-did-i-think 클린 아키텍처 --timeline
주제: 클린 아키텍처

## 2026 Q2

- **projects** (프로젝트 포트폴리오) — 2026-05-31
  > # 프로젝트 포트폴리오
  [card_project:projects]

- **샘플지원-2026** (카카오뱅크 AI모바일개발팀 지원 (2026)) — 2026-05-31
  > # 카카오뱅크 AI모바일개발팀 지원 (2026)
  [card_project:샘플지원-2026]

- **danggeun** (당근마켓) — 2026-05-11 (last reviewed)
  > # 당근마켓
  [card_company:danggeun]

- **v2** (Synapse Memory v2) — 2026-05-11 (created)
  > # Synapse Memory v2
  [card_project:v2]

- **이력서-2026** (수학에심장을달다 iOS 개발) — 2026-05-10 (created)
  > # 수학에심장을달다 iOS 개발
  [card_project:이력서-2026]

- **샘플회사** (샘플회사) — 2026-05-10 (last reviewed)
  > # 샘플회사
  [card_company:샘플회사]

- **-----2026** (2026 프로젝트) — 2026-05-10 (created)
  > # 2026 프로젝트
  [card_project:-----2026]

- **CareLog** (케어로그) — 2026-05-10 (created)
  > # 케어로그
  [card_project:CareLog]

총 8개 카드 (--limit 20)

============================================================
출처 (8):
  - projects
  - 샘플지원-2026
  - danggeun
  - v2
  - 이력서-2026
  - 샘플회사
  - -----2026
  - CareLog
[exit 0]

$ synapse-memory me what-did-i-think 클린 아키텍처 --by time
주제: 클린 아키텍처

## 2026 Q2

- **projects** (프로젝트 포트폴리오) — 2026-05-31
  > # 프로젝트 포트폴리오
  [card_project:projects]

- **샘플지원-2026** (카카오뱅크 AI모바일개발팀 지원 (2026)) — 2026-05-31
  > # 카카오뱅크 AI모바일개발팀 지원 (2026)
  [card_project:샘플지원-2026]

- **danggeun** (당근마켓) — 2026-05-11 (last reviewed)
  > # 당근마켓
  [card_company:danggeun]

- **v2** (Synapse Memory v2) — 2026-05-11 (created)
  > # Synapse Memory v2
  [card_project:v2]

- **이력서-2026** (수학에심장을달다 iOS 개발) — 2026-05-10 (created)
  > # 수학에심장을달다 iOS 개발
  [card_project:이력서-2026]

- **샘플회사** (샘플회사) — 2026-05-10 (last reviewed)
  > # 샘플회사
  [card_company:샘플회사]

- **-----2026** (2026 프로젝트) — 2026-05-10 (created)
  > # 2026 프로젝트
  [card_project:-----2026]

- **CareLog** (케어로그) — 2026-05-10 (created)
  > # 케어로그
  [card_project:CareLog]

총 8개 카드 (--limit 20)

============================================================
출처 (8):
  - projects
  - 샘플지원-2026
  - danggeun
  - v2
  - 이력서-2026
  - 샘플회사
  - -----2026
  - CareLog
[exit 0]

$ synapse-memory me what-did-i-think 클린 아키텍처 --by distance
✗ envelope이 dict 아님: list
[exit 1]

$ synapse-memory me what-did-i-think 클린 아키텍처 --timeline --by distance
error: --timeline and --by distance conflict — pick one.
[exit 1]

$ synapse-memory me what-did-i-think 프로젝트 --timeline --limit 2
주제: 프로젝트

## 2026 Q2

- **projects** (프로젝트 포트폴리오) — 2026-05-31
  > # 프로젝트 포트폴리오
  [card_project:projects]

- **dansim-ios** (단심 (명상 앱)) — 2026-05-12 (오늘 2026-05-12)
  > # 단심 (명상 앱)
  [card_project:dansim-ios]

총 2개 카드 (--limit 2)

============================================================
출처 (2):
  - projects
  - dansim-ios
[exit 0]

$ synapse-memory me what-did-i-think 프로젝트 --timeline --limit 0
error: --limit must be in [1, 100], got 0
[exit 2]

$ synapse-memory me what-did-i-think 전혀 매칭 안 되는 주제 zzz --timeline
주제: 전혀 매칭 안 되는 주제 zzz

## 2026 Q2

- **projects** (프로젝트 포트폴리오) — 2026-05-31
  > # 프로젝트 포트폴리오
  [card_project:projects]

- **샘플지원-2026** (카카오뱅크 AI모바일개발팀 지원 (2026)) — 2026-05-31
  > # 카카오뱅크 AI모바일개발팀 지원 (2026)
  [card_project:샘플지원-2026]

- **v2** (Synapse Memory v2) — 2026-05-11 (created)
  > # Synapse Memory v2
  [card_project:v2]

- **danggeun** (당근마켓) — 2026-05-11 (last reviewed)
  > # 당근마켓
  [card_company:danggeun]

- **ai-symbiote** (AI 심바이오트) — 2026-05-10 (created)
  > # AI 심바이오트
  [card_project:ai-symbiote]

- **-----2026** (2026 프로젝트) — 2026-05-10 (created)
  > # 2026 프로젝트
  [card_project:-----2026]

- **이력서-2026** (수학에심장을달다 iOS 개발) — 2026-05-10 (created)
  > # 수학에심장을달다 iOS 개발
  [card_project:이력서-2026]

- **Tablet** (태블릿 앱) — 2026-05-10 (created)
  > # 태블릿 앱
  [card_project:Tablet]

총 8개 카드 (--limit 20)

============================================================
출처 (8):
  - projects
  - 샘플지원-2026
  - v2
  - danggeun
  - ai-symbiote
  - -----2026
  - 이력서-2026
  - Tablet
[exit 0]

$ synapse-memory me what-did-i-think 어떤 주제 --timeline
주제: 어떤 주제

## 2026 Q2

- **projects** (프로젝트 포트폴리오) — 2026-05-31
  > # 프로젝트 포트폴리오
  [card_project:projects]

- **dansim-ios** (단심 (명상 앱)) — 2026-05-12 (오늘 2026-05-12)
  > # 단심 (명상 앱)
  [card_project:dansim-ios]

- **danggeun** (당근마켓) — 2026-05-11 (last reviewed)
  > # 당근마켓
  [card_company:danggeun]

- **-----2026** (2026 프로젝트) — 2026-05-10 (created)
  > # 2026 프로젝트
  [card_project:-----2026]

- **Tablet** (태블릿 앱) — 2026-05-10 (created)
  > # 태블릿 앱
  [card_project:Tablet]

- **ai-symbiote** (AI 심바이오트) — 2026-05-10 (created)
  > # AI 심바이오트
  [card_project:ai-symbiote]

- **CareLog** (케어로그) — 2026-05-10 (created)
  > # 케어로그
  [card_project:CareLog]

- **Smart_Report** (스마트 리포트) — 2026-05-10 (created)
  > # 스마트 리포트
  [card_project:Smart_Report]

총 8개 카드 (--limit 20)

============================================================
출처 (8):
  - projects
  - dansim-ios
  - danggeun
  - -----2026
  - Tablet
  - ai-symbiote
  - CareLog
  - Smart_Report
[exit 0]

$ synapse-memory me what-did-i-think 클린 아키텍처
✗ envelope이 dict 아님: list
[exit 1]
```
