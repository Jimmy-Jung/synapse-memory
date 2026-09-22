---
name: career-write
description: Write or revise a self-introduction or narrative résumé from the user's existing Obsidian Vault and supplied career facts. Use for 자기소개, 이력서, 경력기술서 작성·수정 when materials are ready; use career-interview to develop missing experience and career-tailor for company-specific research and matching.
metadata:
  author: JunyoungJung
  created: "2026-09-22"
---

# Career Write — 자기소개·서술형 이력서

실제 경험에서 정체성과 일하는 방식을 보여주는 자기소개, 책임·판단·행동·결과를 연결하는 이력서를 작성한다. Chris Lattner의 글에서 참고한 서술 원칙을 사용하되 그의 경력이나 말투를 사용자의 사실로 복제하지 않는다.

## 시작

1. [공통 자료·전달·저장 규칙](references/workflow.md)을 읽는다. 기존 Vault의 경력 자료를 사용하며, 다른 스킬에서 전달한 근거와 답변은 재사용한다.
2. 요청에서 문서 종류, 독자·게시 위치 또는 제출 양식, 분량·언어, 새 작성인지 수정을 원하는지 파악한다. 명확한 사항은 다시 묻지 않는다. 지정이 없으면 한국어로 작성하고, 분량은 자료와 용도에 맞춘다. 문서 종류 자체가 불명확하면 그것만 확인한다.
3. 자기소개는 [자기소개 가이드](references/introduction.md), 이력서는 [서술형 이력서 가이드](references/resume.md)를 읽는다. 두 종류를 요청하면 각각 작성하되 사실 근거와 검토 자료는 공유한다.

원문 분석이나 추가 예시가 필요하면 패키지에 포함된 [자기소개 상세 가이드](references/lattner-introduction-guide.md)와 [이력서 상세 가이드](references/lattner-resume-guide.md)를 참고한다.

## 작성·수정

- 핵심 자료부터 읽고 해당 경험의 근거가 필요할 때만 관련 문서로 확장한다. 초안에 쓸 주장과 출처, 개인의 역할, 실제 결과를 정리한다.
- 근거가 일치하는 내용으로 먼저 초안을 만든다. 미확정 내용은 본문에서 제외하고 검토 자료에 분리한다. 역할·재직 기간 등 글의 구성을 바꾸는 핵심 사실이 충돌하면 해당 사실만 먼저 질문한다.
- 수치가 없으면 확인된 구현·적용·출시 상태를 쓴다. 수치만 빼고 '크게 개선했다'처럼 미확정 효과를 남기지 않는다. 사용자 확인과 외부 증빙을 구분한다.
- 작성 단계에 들어온 뒤 자료가 조금 부족하다는 이유로 전체 인터뷰나 회사 조사를 다시 시작하지 않는다. 인터뷰·회사 맞춤 스킬에서 받은 확인 목록과 전략을 이어받는다. 별도 조사 요청이 새로 생겼을 때만 해당 스킬로 연결한다.
- 수정 요청은 대상 문장과 관련 근거에 집중한다. 사실, 사용자의 목소리, 지정한 형식과 분량을 유지하고 무관한 경력까지 다시 쓰지 않는다.

## 검토·전달

문서별 가이드로 역할·판단·결과의 연결, 자기평가의 근거, 팀 성과 귀속과 시제를 확인한다. 본문을 읽는 독자가 검토 자료 없이도 이해할 수 있게 쓴다.

[검토 자료 구성](references/review.md)에 근거와 확인할 사항을 남기고 공통 저장 규칙에 따라 본문과 분리한다. 출력 위치와 핵심 수정점, 남은 확인 사항을 알린다. 초안이 있다는 이유로 제출 승인·외부 검증을 받았다고 표현하지 않는다.

Claude에서는 `/sm:career-write`, Codex에서는 `$sm:career-write`로 시작한다. 이 스킬은 현재 에이전트가 수행한다. 별도 provider CLI로 본문 작성을 우회하지 않는다.
