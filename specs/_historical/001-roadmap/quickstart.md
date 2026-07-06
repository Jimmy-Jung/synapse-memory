# Quickstart — v0.5 출시 후 사용자 체험

본 quickstart 는 *P1 단독 출시* (v0.5) 만으로 사용자가 받게 되는 가치를 검증하는 시나리오다. v0.6 이상의 기능은 인용만 하고 본 시나리오 범위는 v0.5 에 한정한다.

## 전제

- 기존 `synapse-memory v0.4` 가 동작 중. vault 에 ProjectCard 10개·CompanyCard 2개 보유.
- macOS 26 + Apple Silicon + Python 3.11+.
- `synapse-memory doctor` 가 모두 green.

## 0. 업그레이드

```bash
cd ~/Documents/GitHub/synapse-memory
git switch main && git pull
uv tool install --editable '.[rag]'   # 또는 venv 모드의 uv pip install -e
synapse-memory doctor                 # 신규 디렉터리 검증 결과 확인
```

기대 출력 (발췌):

```
✓ macOS Tahoe 26.x
✓ apfel ready
✓ ~/.synapse/private/      0700
✓ ~/.synapse/private/feedback.jsonl   (생성 예정 — 첫 호출 시)
✓ ~/.synapse/private/cost.jsonl       (생성 예정 — 첫 호출 시)
✓ ~/.synapse/private/sessions/        0700  (신규)
```

## 1. 시간축 회상 (FR-A1)

```bash
synapse-memory me what-did-i-think "클린 아키텍처" --timeline
```

기대 출력:

```
## 2024 Q1 — 2024 Q2

### 2024-03 (period_end)
- sample-ios-app — "Domain–Data–Presentation 3계층 분리..." [card_project:sample-ios-app]

### 2024-05 (period_end)
- 이력서-2026 — "도입 기간 2024.01~05, Tuist 멀티 모듈화로 확장..." [card_project:이력서-2026]

## 2024 Q3 — 2024 Q4

### 2024-09 (period_end)
- mobile-ios-tablet-app — "Repository 패턴 + DIContainer 조합..." [card_project:mobile-ios-tablet-app]

(distance fallback 0건)
```

검증:
- SC-001 — 시간 정렬 Kendall τ ≥ 0.9 (수동 확인 시 P/Q/R 순서 일치)

## 2. Feedback 남기기 (FR-A2)

위 답변에서 두 번째 항목이 잘못된 인용이라 판단:

```bash
synapse-memory feedback last --reject "관련 없음 — Tuist 가 아니라 SwiftPM 이었음"
```

기대 출력:

```
✓ Recorded reject for card_project:이력서-2026 (weight=-0.30)
  → next index will apply feedback_score=0.85
```

검증:

```bash
tail -1 ~/.synapse/private/feedback.jsonl
```

```json
{"event_id":"01HZX...","ts":"2026-05-12T...","target_kind":"card",
 "target_ref":"이력서-2026","action":"reject","weight":-0.30,
 "reason":"관련 없음 — Tuist 가 아니라 SwiftPM 이었음",
 "answer_id_context":"01HZX..."}
```

## 3. 비용 확인 (FR-A3, FR-A4)

```bash
synapse-memory cost summary --days 7
```

기대 출력:

```
Last 7 days — total $1.23 / 47 calls / avg 2.4s per call

| Command        | Calls | Input tok | Output tok |   USD  |
|----------------|-------|-----------|------------|--------|
| me decide      |    5  |    8,300  |     2,100  |  0.45  |
| ask            |   18  |   24,000  |     6,500  |  0.61  |
| daily.classify |    7  |    3,200  |       800  |  0.06  |
| daily.generate |   17  |   18,000  |     5,200  |  0.11  |
```

검증:
- SC-003 — 합계 USD 가 실제 Anthropic dashboard 청구액과 비교 시 ±10% 이내.

## 4. Daily 실패 + 재개 시나리오 (FR-A6, FR-A7)

intentional 실패 주입 (테스트 fixture 사용):

```bash
SYNAPSE_FAULT_INJECT=classify synapse-memory daily
```

기대 출력 (단계별 표):

```
[collect_claude_code] 0.0s  ok      변경 없음
[collect_obsidian]    0.2s  ok      scanned=1356 mirrored=3
[classify]            0.3s  failed  ApfelTimeout
[generate]            0.0s  skipped (depends on classify)
[index]               0.0s  skipped (depends on generate)
[update_profile]      0.0s  skipped (depends on index)
[report]              0.1s  ok      DailyReport-2026-05-12.md saved

Daily 총 시간: 0.6s  errors=1  exit=1
```

재개:

```bash
synapse-memory daily --resume-from classify
```

기대: classify 부터 정상 진행, 5 stage 모두 ok.

검증:
- SC-004 — 사용자 개입 < 1회 (단 1번의 `--resume-from` 호출).

## 5. DailyReport 확인 (FR-A5)

```bash
ls -la ~/Library/Mobile\ Documents/iCloud~md~obsidian/Documents/<vault>/90_System/AI/DailyReports/2026-05-12.md
```

또는 Obsidian 에서 열기. `data-model.md §3` 의 frontmatter + 본문 표.

## 6. CI 게이트 (FR-A8)

```bash
git checkout -b test/ci-smoke
echo "# smoke" >> README.md
git commit -am "test: smoke"
git push -u origin test/ci-smoke
```

기대: GitHub Actions 에서 5분 내 다음 모두 green:
- `pytest`
- `ruff check`
- `mypy --strict`

PR 머지는 모두 green 후에만 가능.

---

## 검증 표 — v0.5 단독 출시 시 만족하는 Success Criteria

| Criteria | 검증 방법 | 결과 |
|---|---|---|
| SC-001 | §1 시간 정렬 Kendall τ | ≥ 0.9 |
| SC-002 | §2 feedback.jsonl 변화 | append 1줄 |
| SC-003 | §3 dashboard 비교 | ±10% 이내 |
| SC-004 | §4 의존 stage SKIP + resume 1회 | exit 1 → 0 |
| SC-005 | §6 CI 5분 green | green |
| SC-012 | 모든 PR ruff/mypy/pytest | green |
| SC-013 | eval golden Pass1/Pass2 F1 | ≥ 0.95 / ≥ 0.80 |

---

## v0.6+ 시나리오 (참고만)

v0.6 출시 후에는 다음이 추가:

```bash
synapse-memory rag index --include-raw            # FR-B1
synapse-memory ask "샘플회사B" --hybrid            # FR-B2
synapse-memory me decide "이직 제안" --preview-prompt  # FR-B3
synapse-memory me draft-reply "내일 회의 가능?"   # FR-B4
synapse-memory card update sample-ios-app --dry-run   # FR-B5
```

각 명령의 정확한 동작은 `contracts/cli-contracts.md` 참조. 시나리오는 `specs/006~009-*/quickstart.md` (각 sub-feature 자체 quickstart) 에서 확장.
