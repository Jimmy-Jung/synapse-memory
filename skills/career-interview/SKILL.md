---
name: career-interview
description: Develop career material from the user's Obsidian Vault through focused questions, then draft a self-introduction or résumé with career-write. Use for 경력 정리, 경험 발굴, 쓸 내용이 부족한 자기소개·이력서; this is a fact-gathering interview, not a mock job interview.
metadata:
  author: JunyoungJung
  created: "2026-09-22"
---

# Career Interview — 경력 재료 정리와 질문

이미 있는 경력 자료를 읽고 부족한 경험·판단·결과를 질문으로 보완한다. 준비된 사실을 다시 묻는 설문을 만들지 않는다.

## 진행

1. [공통 자료·전달·저장 규칙](../career-write/references/workflow.md)을 읽고 문서 종류와 사용 목적을 파악한다. 회사 맞춤 스킬이 호출했다면 전달된 근거와 질문 범위를 그대로 이어받는다.
2. 핵심 경력 자료를 읽어 사용할 경험과 빠진 부분을 정리한다. 자기소개는 정체성·동기·태도를 뒷받침하는 경험, 이력서는 책임·판단·행동·결과를 중심으로 고른다.
3. [인터뷰 가이드](references/interview.md)에 따라 지금 글의 품질을 바꾸는 질문부터 작은 묶음으로 묻는다. 사용자가 답한 내용·문서에 분명한 내용은 반복하지 않는다.
4. 핵심 역할이나 기간이 충돌해 글 구성을 정할 수 없으면 해당 사실을 먼저 확인한다. 그 밖의 미확정 내용은 확인 목록에 두고 확보한 재료로 초안을 진행한다. 모르는 수치·말하고 싶지 않은 사생활·공개 불가 정보는 더 요구하지 않는다.
5. 답변을 근거와 확인 상태에 반영한다. 사용자가 말한 사실과 에이전트가 제안한 표현·해석을 구분한다. `검토자료.md`에 필요한 경력 사실만 요약하고 원문 대화나 Profile을 저장·수정하지 않는다.

## 작성으로 연결

독립 실행이면 [career-write](../career-write/SKILL.md)를 읽어 같은 작업에서 자기소개 또는 이력서를 작성한다. 본문과 검토 자료를 분리해 저장하고 확인할 사항을 함께 제공한다. 재료 정리만 요청한 경우에는 그 범위까지만 수행한다.

`career-tailor`에서 보완 요청을 받은 경우에는 근거 묶음만 호출자에게 반환한다. 회사 조사나 최종 작성을 중복 실행하지 않는다. 전달할 내용은 공통 규칙의 단계 간 전달 항목을 따른다.

Claude에서는 `/sm:career-interview`, Codex에서는 `$sm:career-interview`로 시작한다.
