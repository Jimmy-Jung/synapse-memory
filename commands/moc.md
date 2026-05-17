---
description: vault 90_System/AI/MOC.md를 Dataview 동적 인덱스로 생성·갱신. Obsidian Graph 시각화의 진입점. marker 외부 사용자 영역은 보존.
argument-hint: [--vault PATH]
---

!`synapse-memory moc $ARGUMENTS`

위 출력은 MOC 갱신 결과입니다. MOC.md의 `<!-- SYNAPSE-MEMORY-MOC START/END -->` marker 사이가 Projects / Companies / Profile updates / Daily reports 각 영역의 dataview 블록으로 교체됐습니다.

## 사용 시점

- vault에 새 Card / Profile / DailyReport가 늘었을 때
- Obsidian Graph view에서 노드 유형별로 둘러보기 전
- 사용자가 MOC를 처음 만들 때

## 동작

1. vault 90_System/AI/MOC.md 위치 확인 (없으면 신규 생성)
2. marker 사이만 교체 (사용자 자유 메모는 보존)
3. byte-level idempotent — 같은 vault 상태로 재실행 시 결과 동일

## 의존성

- **Dataview 플러그인 필요** — MOC의 동적 인덱스가 동작하려면 Obsidian에 Dataview 설치·활성화. 미설치 시 MOC 본문은 그대로 보이지만 데이터 영역은 빈 화면. `synapse-memory doctor` 가 자동으로 점검합니다.

## 자동 트리거 없음

`/sm:daily` 등 다른 명령이 MOC를 자동 갱신하지 않습니다. 명시 호출만 — Constitution VI Installation Consent.
