---
description: 회사 맞춤 이력서 자동 생성 (vault Project/Company Card 매칭 + Claude 합성)
argument-hint: <회사 slug 또는 이름>
---

!`SYNAPSE_FROM_AGENT=1 synapse-memory me draft-resume "$ARGUMENTS"`

위 출력은 vault의 Project Card 중 해당 회사(JD/도메인)에 가장 매칭되는 항목을 추출하여 Claude API로 이력서 초안을 합성한 결과입니다. 생성된 파일 경로와 매칭 Card 목록을 사용자에게 전달하고, 추가 다듬기가 필요한지 묻습니다.
