---
name: daily
description: Use when the user asks "오늘자 정리 돌려줘", "synapse-memory daily 실행", "오늘 회상/Card 갱신해줘", or wants the full daily ingest pipeline. Runs raw mirror → redact → extract → embed → index in one shot.
---

# /sm:daily — 일일 통합 워크플로

vault + Claude Code 활동 로그를 mirror → redact → Card 추출 → embed → index 까지 한 번에 수행합니다. 실패한 stage 는 격리되고 다음 호출 때 `--resume-from` 으로 재개됩니다.

## 실행

```bash
synapse-memory daily [--quick] [--profile-facts-only] [--resume-from <stage>]
```

- **첫 호출은 `--quick` 권장** (전체 vault 대신 최근 변경분만)
- `--profile-facts-only`: ProfileFact 추출만
- `--resume-from`: 실패 지점부터 이어서

종료 시 `DailyReport-YYYY-MM-DD.md` 가 vault `90_System/AI/DailyReports/` 에 생성됩니다.
