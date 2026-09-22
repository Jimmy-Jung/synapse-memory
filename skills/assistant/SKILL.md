---
name: assistant
description: Use when the user says "오늘 뭐하면 좋을까", "synapse-memory 비서 모드", "추천 작업 알려줘", or wants proactive task suggestions. Recommends 1–3 actions from existing data, executes on user approval.
---

# /sm:assistant — 일상 비서 모드

vault / Card / 최근 활동을 종합해서 **오늘 추천 작업 1~3 개** 를 제안하고, 사용자가 동의하면 그 작업을 대신 실행합니다. (예: "오늘 X Card 갱신할까?" → 승인 시 daily 또는 career-tailor 등 다른 skill 호출).

## 실행

```bash
synapse-memory assistant-status
synapse-memory assistant-status --json
```

`assistant-status`는 read-only 진단과 추천만 출력합니다. 사용자가 번호 또는 자연어로
승인하면 추천에 적힌 실제 명령(`daily`, `cleanup scan` 등)이나 해당 스킬을 실행하세요.
경력 작업은 준비된 자료로 작성·수정하면 `career-write`, 자료 정리·질문부터 필요하면
`career-interview`, 회사·공고 맞춤이면 `career-tailor`로 연결합니다. 모두 자기소개와
이력서를 지원하고 `00_Inbox/<작업명>/`에 본문과 검토자료를 분리 저장합니다.
현재 세션에서 수행하는 스킬이므로 별도 provider를 호출하는 `persona draft-resume`
CLI를 자동 실행하지 않습니다. 비용은 세션과 도구 사용량에 따르며 고정 금액을 추정하지 않습니다.
