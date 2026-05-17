---
name: moc
description: Use when the user wants an Obsidian Graph entry point or wants to refresh MOC.md with the latest vault state. Generates `90_System/AI/MOC.md` with Dataview blocks for Projects, Companies, Profile updates, and Daily reports. Marker-based — user-edited content outside markers is preserved. Requires Dataview plugin.
---

# /sm:moc — Map of Contents 생성·갱신

vault `90_System/AI/MOC.md` 를 동적 인덱스로 만듭니다. Obsidian Graph view 진입점 + 노드 유형별 색상 분리 설정 안내.

## 실행

```bash
synapse-memory moc [--vault PATH]
```

## 동작

- Projects (`20_Reference/Projects`) — 최신 10
- Companies (`20_Reference/Companies`)
- Profile updates (`90_System/AI/MemoryInbox`) — pending_review 만
- Daily reports (`90_System/AI/DailyReports`) — 최신 14
- 본문 마지막에 Obsidian Graph 그룹 색상 설정 안내 (`#node/card`, `#node/profile-update`, `#node/daily-report` 등)

## 의존성

- **Dataview 플러그인 필요** — 미설치 시 dataview 블록은 빈 화면. `synapse-memory doctor` 로 점검.
- 015 sprint에서 도입한 `node/*` 태그가 frontmatter에 있어야 그룹 색상이 동작.

## 자동 트리거 없음

`/sm:daily` 등이 MOC를 자동 갱신하지 않습니다. 사용자가 명시 호출.
