---
name: doctor
description: Use when the user reports installation issues, asks "환경 정상인지 봐줘", "synapse-memory 동작 확인", or before first run. Checks vault path/config consistency, v2 wiki pipeline (pages, watch daemon, maintenance engine), Obsidian Dataview plugin, SessionStart hook, and AI provider CLI availability.
---

# /sm:doctor — 환경 진단

Synapse Memory 가 의존하는 경로 / v2 wiki 파이프라인 / 런타임을 점검합니다.

## 점검 항목

- vault config 일관성 (config.yaml vault vs 자동 감지)
- v2 wiki 페이지 존재 (entity / concept / profile / insight)
- v2 wiki 자동 유지 watch 데몬(launchd) + maintenance engine
- Obsidian Dataview 플러그인 (MOC 동적 인덱스 의존성)
- Claude Code / Codex SessionStart hook 설치
- AI provider CLI 가용성

## 실행

```bash
synapse-memory doctor
```

✗ 또는 ⚠ 항목이 있으면 해결 방법을 안내하고, 자동 복구 가능하면 `fix` skill (`synapse-memory doctor --fix`) 을 제안하세요. 모두 ✓이면 다음 단계 (`daily` 또는 `ask`) 를 안내합니다.

## 언제 안 쓰는가

- 자동 복구까지 한 번에 → `fix` skill
- 비용 점검 → `cost` skill
