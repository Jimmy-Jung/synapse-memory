---
name: onboard
description: Use for FIRST-TIME users — "synapse-memory 어떻게 써?", "처음인데 뭐부터?", "맛 좀 보여줘". Picks the ONE biggest pain among 5 onboarding paths and walks the user through it end-to-end. Not a generic tutorial.
---

# /sm:onboard — 최초 사용자 인도

5 가지 답답함 (recall / decide / career / ask / daily) 중 사용자가 가장 크게 느끼는 **한 가지만** 끝까지 체험시키는 짧은 wedge.

## 실행

```bash
synapse-memory doctor
synapse-memory setup --dry-run
synapse-memory context render
synapse-memory daily --quick --dry-run
```

전용 `onboard` CLI는 없습니다. 이 skill이 사용자 답답함을 한 가지로 좁힌 뒤,
위의 실제 명령 중 필요한 read-only/dry-run 경로를 골라 시연합니다.

경력 작성이 목적이면 `career-write`(자료로 작성·수정), `career-interview`(자료 정리와 질문),
`career-tailor`(회사·공고 맞춤) 중 시작점을 고릅니다. 모두 자기소개와 이력서를 지원하고
현재 대화에서 작성합니다. 회사 카드 생성이나 `daily`를 선행 조건으로 요구하지 않습니다.
본문과 검토자료는 `00_Inbox/<작업명>/`에 분리 저장합니다. 별도 provider를 호출하는
`persona draft-resume` CLI를 경력 스킬 대신 자동 실행하지 않습니다.

여러 기능을 동시에 설명하지 마세요. 첫 사용자는 ONE wedge.
