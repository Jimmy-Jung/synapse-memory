---
description: 일일 통합 5분 워크플로 — collect / cluster / card generate / rag index / update profile 일괄
argument-hint: [--profile-facts-only]
---

!`synapse-memory daily $ARGUMENTS`

위 출력은 7-step incremental 파이프라인(collect_claude_code → collect_obsidian → classify → generate → index → update_profile → eval)의 단계별 진행 결과입니다. 각 step의 소요 시간 / 변경된 항목 수를 요약하고, 실패한 step이 있으면 강조하여 사용자에게 전달하세요.
