---
name: resume
description: Use when the user wants a company-tailored résumé draft (e.g. "당근마켓 지원할건데 이력서 써줘", "Y 회사용 resume 만들어줘", "<회사명> 자기소개서 초안"). Matches vault Project/Company Cards to the target company and synthesizes a draft.
---

# /sm:resume — 회사 맞춤 이력서 합성

회사 slug 또는 이름을 받아 vault 에 저장된 **Project Card** + 해당 **Company Card** + Profile.md 를 매칭한 뒤 회사 톤에 맞춘 이력서 초안을 생성합니다.

## 실행

```bash
SYNAPSE_FROM_AGENT=1 synapse-memory resume "<회사 slug 또는 이름>"
```

결과는 `20_Projects/Resumes/<company>-<date>.md` 에 저장됩니다. 사용자에게는 본문 미리보기와 함께 저장 위치를 안내하세요.
