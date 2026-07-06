# Quickstart: Cost Observability

이 quickstart 는 실제 사용자 L0 를 오염시키지 않도록 임시 `SYNAPSE_L0_ROOT` 를 사용한다.

## 1. 격리된 L0 root 준비

```bash
tmp_root="$(mktemp -d /tmp/synapse-cost-smoke.XXXXXX)"
export SYNAPSE_L0_ROOT="$tmp_root/private"
mkdir -p "$SYNAPSE_L0_ROOT"
chmod 700 "$SYNAPSE_L0_ROOT"
```

## 2. doctor 확인

```bash
synapse-memory doctor
```

기대: L0 root 권한이 green 이고, apfel / Claude Code CLI 가 설치된 환경이면 ready.

## 3. mocked 또는 실제 AI 호출 1회 실행

```bash
SYNAPSE_FROM_AGENT=1 synapse-memory ask "최근 내가 비용 관측에 대해 뭘 정했지?"
```

실제 vault/RAG 환경이 없다면 테스트 fixture 또는 unit test 로 대체 가능하다.

## 4. cost event 확인

```bash
test -s "$SYNAPSE_L0_ROOT/cost.jsonl"
tail -1 "$SYNAPSE_L0_ROOT/cost.jsonl" | python3 -m json.tool
```

기대: `provider`, `model`, `command`, `input_tokens`, `output_tokens`, `usd`, `elapsed_s`, `status` 가 있고 prompt/response 원문 필드가 없다.

## 5. summary table

```bash
synapse-memory cost summary --days 30 --by command
```

기대: command 별 calls/token/usd/elapsed 합계와 TOTAL row 출력.

## 6. summary JSON

```bash
synapse-memory cost summary --days 30 --by model --json | python3 -m json.tool
```

기대: valid JSON 으로 parse 되고 table header 가 섞이지 않는다.

## 7. no-data branch

```bash
mv "$SYNAPSE_L0_ROOT/cost.jsonl" "$SYNAPSE_L0_ROOT/cost.jsonl.bak"
synapse-memory cost summary --days 30
```

기대: exit 0, "데이터 없음" 안내.

## 8. corrupt-tail recovery

```bash
printf '{bad json\\n' >> "$SYNAPSE_L0_ROOT/cost.jsonl"
synapse-memory cost summary --days 30
ls "$SYNAPSE_L0_ROOT"/cost.jsonl.bak.*
```

기대: readable prefix 로 summary 가 계속되고 corrupt tail backup 파일이 생성된다.
