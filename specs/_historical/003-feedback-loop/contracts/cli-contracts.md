# CLI Contracts — Feedback Loop

## `synapse-memory feedback last`

```bash
synapse-memory feedback last (--accept | --reject <reason> | --weight <delta>)
```

- **분류**: batch
- **입력**:
  - `--accept`: 직전 답변에 긍정 신호 기록
  - `--reject <reason>`: 직전 답변에 부정 신호 기록, reason 필수
  - `--weight <delta>`: 고급 사용자용 직접 가중치, `-1.0 <= delta <= 1.0`
- **성공 출력**:

```text
✓ Recorded reject for last answer <answer_id> (targets=2, weight=-0.30)
  → next index will apply updated feedback_score
```

- **Exit codes**:
  - `0`: 기록 성공
  - `1`: 직전 답변 없음, target 해석 실패, validation 실패
  - `2`: private storage 권한 오류

## `synapse-memory feedback card`

```bash
synapse-memory feedback card <card_id> (--accept | --reject <reason> | --weight <delta>)
```

- **분류**: batch
- **성공 조건**: `<card_id>` 가 확인 가능해야 한다.
- **부작용**: `target_kind="card"` event append.
- **성공 출력**:

```text
✓ Recorded reject for card <card_id> (weight=-0.30)
  → next index will apply feedback_score=0.85 if no other events exist
```

## `synapse-memory feedback pattern`

```bash
synapse-memory feedback pattern <pattern_id> --weight <delta>
```

- **분류**: batch
- **MVP 정책**: pattern existence 검증 경로가 준비되지 않은 경우 exit 1 로 명확히 거부한다.
- **성공 조건**: pattern id 를 검증할 수 있어야 한다.
- **부작용**: `target_kind="pattern"` event append.

## Common Validation

- `--accept`, `--reject`, `--weight` 는 상호 배타적이다.
- reject reason 은 공백만 있을 수 없다.
- weight delta 는 `[-1.0, 1.0]`.
- feedback command 는 apfel, Claude Code CLI, network 를 요구하지 않는다.
- feedback command 는 TTY 안내 prompt 를 출력하지 않는다.

## Slash Command Shim

`commands/synapse-feedback.md` 는 다음 실행 형태를 안내한다.

```bash
SYNAPSE_FROM_AGENT=1 synapse-memory feedback last --reject "<reason>"
SYNAPSE_FROM_AGENT=1 synapse-memory feedback card <card_id> --accept
```
