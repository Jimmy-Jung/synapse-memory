---
description: 환경 진단 — vault 경로 / v2 wiki 파이프라인(페이지·watch 데몬·engine) / Dataview / SessionStart hook / AI provider CLI 가용성 체크
---

!`synapse-memory doctor`

위 출력은 synapse-memory 동작에 필요한 항목(vault config 일관성, v2 wiki 페이지·자동 유지 데몬·maintenance engine, Obsidian Dataview 플러그인, SessionStart hook, AI provider CLI)의 상태를 정리한 결과입니다. ✗ 또는 ⚠ 표시된 항목이 있으면 해결 방법을 함께 안내하고, 자동 복구 가능한 항목이면 `/sm:fix` 또는 `synapse-memory doctor --fix`를 제안하세요. 모두 ✓이면 다음 단계(`/sm:daily` 또는 `/sm:ask`)를 제안하세요.
