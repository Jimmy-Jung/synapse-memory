---
name: career-tailor
description: Research a target company and job posting, match the user's Vault career evidence, and write a tailored self-introduction or résumé via career-write. Use for 회사 맞춤 이력서·자기소개, 채용공고 분석 후 지원 글 작성; use career-write when only editing supplied text without company research.
metadata:
  author: JunyoungJung
  created: "2026-09-22"
---

# Career Tailor — 회사 조사와 맞춤 작성

회사의 실제 문제와 지원 직무를 조사하고 사용자의 경험을 연결한다. 회사의 요구를 사용자의 보유 역량으로 바꾸어 쓰지 않는다.

## 조사와 매칭

1. [공통 자료·전달·저장 규칙](../career-write/references/workflow.md)을 읽는다. 회사, 지원 포지션, 공고 URL·텍스트, 문서 종류와 제출 조건을 파악한다. 회사가 모호하거나 서로 다른 포지션에 따라 강조할 경험이 달라지면 대상부터 확인한다.
2. 기존 회사·경력 자료를 읽고 [회사 조사 가이드](references/company-research.md)에 따라 공식 자료와 공고를 확인한다. 조사 내용·출처·확인일은 같은 작업의 `검토자료.md`에 모은다.
3. 공고의 주요 업무·필수·우대 요건을 구분하고 각 요건을 실제 경험·개인 기여·결과에 매칭한다. 직접 경험, 인접 경험, 근거 없는 영역을 구분한다. 맞지 않는 키워드를 억지로 넣지 않는다.
4. 부족한 사실 중 매칭을 바꿀 내용만 [career-interview](../career-interview/SKILL.md)로 보완한다. 이때 회사 조사·문서 종류·기존 답변·작업 폴더와 부족한 항목을 전달하고 **근거 묶음만 반환**하도록 한다. 자료가 충분하면 인터뷰를 생략한다.
5. 강조할 경험과 그 이유, 약한 영역과 실제 보완 가능성, 회사에 맞게 설명할 문제를 정리한다. 자기소개는 동기·태도와 경험의 연결, 이력서는 책임·행동·결과의 관련성을 조정한다. 자료에 없는 지원 동기·도메인 경험은 만들지 않는다.

## 작성과 결과

[career-write](../career-write/SKILL.md)를 읽고 조사·매칭·전략과 근거 묶음을 전달해 같은 작업에서 작성한다. 제목이나 프로젝트 순서만 바꾸는 데 그치지 않고, 실제 경험이 지원 직무의 어떤 문제와 연결되는지 본문에 설명한다.

결과는 `00_Inbox/<작업명>/`의 본문과 `검토자료.md`이다. 명시적으로 지정한 기존 작업을 이어 쓰면 그 폴더를 유지한다. 원래 `20_Reference/Companies/`에 있던 문서를 자동 이동하지 않는다.

공고가 없거나 웹 접근이 막혔을 때는 조사 가이드의 부분 진행 규칙을 따른다. 미확인 조사 결과를 최신 사실이나 맞춤 지원 근거로 포장하지 않는다.

Claude에서는 `/sm:career-tailor`, Codex에서는 `$sm:career-tailor`로 시작한다. 별도 CLI `persona draft-resume`은 다른 합성 경로이며 이 워크플로의 대체 단계로 자동 실행하지 않는다.
