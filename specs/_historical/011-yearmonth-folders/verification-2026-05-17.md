# Verification — 011-yearmonth-folders (2026-05-17)

**Branch**: `0.9.0/feature/011-yearmonth-folders`
**Executed by**: User vault migration

## Backup

- 경로: `/tmp/vault-backup-pre-migration-20260517-192548`
- 크기: 260K (MemoryInbox + DailyReports만, vault 전체 X)
- 백업 시각: 2026-05-17 19:25:48

## Pre-state

**MemoryInbox** (flat, 13 entries):
- Profile-2026-05-11/13/15/17.md (4 — 신규 패턴, migrate 대상)
- 2026-04-23/28/29/30.md, 2026-05-06/11/12/13.md (8 — legacy 패턴, Profile- prefix 도입 이전)
- README.md (가이드)

**DailyReports** (flat, 3 entries):
- 2026-05-13/15/17.md

## Decisions

- Legacy 8개 (`YYYY-MM-DD.md` in MemoryInbox)는 migrate-folders 패턴 불일치로 자동 skip
- 사용자 결정: 수동으로 `MemoryInbox/_legacy/`로 archive 이동 (사전 정리, migrate 전)

## Dry-run

```
synapse-memory migrate-folders --dry-run --report-unknown --vault <vault>
```

- MemoryInbox: 4건 예정, 충돌 0
- DailyReports: 3건 예정, 충돌 0
- Skipped 9건 (legacy 8 + README.md 1)
- Exit: 0

## Real execution

(사전에 legacy 8개를 `_legacy/`로 manual mv 후)

```
synapse-memory migrate-folders --vault <vault>
```

- MemoryInbox: 4건 이동, skipped 1 (README.md), exit 0
- DailyReports: 3건 이동, exit 0

## Post-state

**MemoryInbox**:
```
MemoryInbox/
├ README.md
├ 2026/05/
│  ├ Profile-2026-05-11.md
│  ├ Profile-2026-05-13.md
│  ├ Profile-2026-05-15.md
│  └ Profile-2026-05-17.md
└ _legacy/
   ├ 2026-04-23.md
   ├ 2026-04-28.md
   ├ 2026-04-29.md
   ├ 2026-04-30.md
   ├ 2026-05-06.md
   ├ 2026-05-11.md
   ├ 2026-05-12.md
   └ 2026-05-13.md
```

**DailyReports**:
```
DailyReports/
└ 2026/05/
   ├ 2026-05-13.md
   ├ 2026-05-15.md
   └ 2026-05-17.md
```

## US3 — Dataview compatibility

- 사용자 확인 필요 (Obsidian에서 직접 dataview 결과 검증)
- 일반적으로 dataview는 `FROM "folder"` 시 재귀 검색하므로 영향 없음 예상
- `_legacy/` 폴더가 dataview 결과에 포함되는지는 별도 확인 필요. 의도적으로 제외하려면 dataview query에 `WHERE !contains(file.folder, "_legacy")` 추가

## Status

✅ Migration 성공 (7건 이동, 0 충돌, 0 에러)
⏳ Dataview 회귀 검증은 사용자 수동 확인 대기
