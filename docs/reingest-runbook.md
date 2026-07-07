# Re-ingest Runbook

Author: JunyoungJung  
Created: 2026-07-06

이 절차는 구조 변경 뒤 vault를 L0 raw mirror에서 다시 구성할 때만 수동으로 실행한다.
provider 호출과 vault 쓰기가 발생하므로 sandbox나 CI에서 자동 실행하지 않는다.

1. vault와 `~/.synapse/private`를 복원 가능한 위치에 백업한다.
2. compact된 raw sidecar를 먼저 복원한다.

```bash
synapse-memory compact-raw --source all --rehydrate --apply --yes
```

3. 재생성할 generated wiki tree만 제거한다. 기본 tree는 `Entities/`, `Concepts/`,
   `Insights/`, `Logs/`, `Profile/`이다. 사용자 원본 노트와 백업은 삭제하지 않는다.
4. L0 raw에서 source별로 backfill을 실행한다. 먼저 작은 배치로 검증한다.

```bash
synapse-memory backfill --source claude-code --batch-size 5 --max-batches 1 --no-semantic-retrieval
synapse-memory backfill --source codex --batch-size 5 --max-batches 1 --no-semantic-retrieval
```

5. 샘플 결과가 맞으면 batch 제한을 풀고 source별로 완료할 때까지 실행한다.

```bash
synapse-memory backfill --source claude-code
synapse-memory backfill --source codex
synapse-memory lint --now
synapse-memory doctor
```

중단되면 같은 backfill 명령을 다시 실행한다. per-doc checkpoint와 별도 offset 저장소가
남은 raw부터 이어 처리한다.
