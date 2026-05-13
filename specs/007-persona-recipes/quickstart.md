# Quickstart — Me Generator Recipes

**Feature**: 007-me-recipes
**예상 소요**: 5 분
**전제**: synapse-memory 설치, vault 경로 설정, `synapse-memory daily` 1 회 이상 실행

본 quickstart 는 빌트인 recipe 1 종 (`weekly_report`) 을 실행하고, 직접 만든
사용자 recipe (`diary`) 를 vault 에 떨어뜨려 즉시 사용할 수 있음을 보인다.

## 1. 사용 가능한 recipe 확인 (15 초)

```bash
$ synapse-memory me recipes list
NAME              SOURCE   REQUIRED INPUTS         DESCRIPTION
brainstorm        builtin  topic                   주제에 대한 발산형 아이디어
journal           builtin  date                    그날의 vault 활동을 일기로 정리
resume            builtin  company_id              회사 맞춤 이력서
weekly_report     builtin  period                  주간 보고
```

이 시점에는 사용자 recipe 가 없음.

## 2. (선택) Profile.md 에 voice·언어 힌트 등록 (30 초)

원한다면 `<vault>/90_System/AI/Profile.md` 의 frontmatter 에 다음을 추가:

```yaml
---
preferred_lang: 한국어
domain: software
---

이름: ...
강점: ...
지향: ...
```

이 두 필드는 optional. 없어도 정상 동작 (`한국어` / `generic` 으로 fallback).

## 3. 빌트인 recipe 실행 — weekly_report (1 분)

```bash
$ synapse-memory me generate weekly_report --period=2026-W19
[me.generate.weekly_report] locale=profile:한국어 domain=profile:software profile_used=true matched=4 duration=2841ms

---
title: 주간 보고 2026-W19
period: 2026-W19
generated: 2026-05-12
---

## 이번 주 한 일
- ...
## 핵심 의사결정
- ...
## 막힘 / 리스크
- ...
## 다음 주 계획
- ...

[saved] /Users/<you>/Documents/Vault/30_Creative/Reports/Weekly Report - 2026-W19 (2026-05-12).md
```

stderr 1 줄에 locale / domain / profile_used / matched / duration 이 표시된다.
저장 파일은 vault 의 `30_Creative/Reports/` 아래.

## 4. 사용자 recipe 추가 — `diary` (2 분)

빈 markdown 파일 한 장을 vault 의 `90_System/AI/recipes/diary.md` 에 만든다:

```markdown
---
name: diary
description: 오늘 vault 활동을 일기 톤으로 짧게 정리
input_schema:
  topic: optional
rag_filter:
  source_kind: card_project
rag_top_k: 5
use_profile: true
save_subpath: 10_Journal/Drafts
locale_aware: true
domain_aware: false
timeout: 90
---

당신은 사용자의 일기 작성 보조입니다.

# 임무
오늘 ({today}) vault 의 카드와 사용자 voice 로 일기를 한국어로 짧게 작성합니다.
주제(`{topic}`) 가 주어지면 그것을 중심으로, 없으면 가장 영향이 컸던 활동 중심으로.

# 원칙
- 1 인칭, 짧은 문장, 사실은 [card_id] 인용
- 자료 없는 부분은 추측 금지
- 결과는 markdown 본문만 (frontmatter 시작 금지)
```

저장 후 곧바로:

```bash
$ synapse-memory me recipes list
NAME              SOURCE   REQUIRED INPUTS         DESCRIPTION
brainstorm        builtin  topic                   ...
diary             user     (none)                  오늘 vault 활동을 일기 톤으로 짧게 정리
journal           builtin  date                    ...
resume            builtin  company_id              ...
weekly_report     builtin  period                  ...
```

`diary` 가 즉시 보임 — 재시작·등록 단계 없음 (FR-010 / Q5).

## 5. 사용자 recipe 실행 (30 초)

```bash
$ synapse-memory me generate diary
# 또는 주제 지정
$ synapse-memory me generate diary --topic=시간관리
```

결과가 stdout 으로 출력되고 `10_Journal/Drafts/Diary - 시간관리 (2026-05-12).md` 에 저장된다.

## 6. 이력서 — 영어 / 디자인 도메인 시나리오 (1 분)

Profile.preferred_lang 을 `en` 으로, domain 을 `design` 으로 바꾸고:

```bash
$ synapse-memory me generate resume --company_id=acme_co
```

출력이 영어로 생성되고, 섹션 구조가 "Case Studies / Tools / Impact" 가 된다
(spec User Story 2 / R-4).

회사 카드가 `resume_language: en` 을 가지면 Profile 보다 우선 (FR-005 precedence).

## 7. backward compatibility 확인

기존 명령이 그대로 동작:

```bash
$ synapse-memory me draft-resume acme_co
$ synapse-memory me decide "프레임워크 X 도입 여부"
$ synapse-memory me what-did-i-think "프로젝트 회고"
$ synapse-memory me what-did-i-think "프로젝트 회고" --timeline  # 002 contract 무변경
```

stdout / exit code / 저장 경로 차이 없음 (SC-005). `last_answer` 의 internal
`command` 필드만 `me.generate.<recipe>` 로 통일됨 (R-6).

## Troubleshooting

- **`recipe 'foo' not found`** → `me recipes list` 로 가용 목록 확인. 비슷한
  이름이 stderr 에 제안되어 있는지 본다.
- **`required input(s) missing: period`** → `--period=...` 같이 키-값을 명시.
- **`recipe rejected: system_prompt exceeds 32KB`** → recipe markdown body 를
  줄이거나 외부 참고 자료로 분리.
- **`matched 0 cards`** → `synapse-memory rag index` 가 최신인지 확인.
