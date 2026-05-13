# 빠른 시작: Persona OS

**기능**: 010-persona-os
**작성일**: 2026-05-13
**작성자**: JunyoungJung

## 목표

Fixture vault 또는 실제 vault에서 Persona OS MVP가 다음 흐름을 만족하는지 검증한다.

```text
start → add → review → next → simulate
```

## 전제 조건

- Synapse Memory 개발 환경이 준비되어 있다.
- `synapse-memory doctor`가 기본 환경을 진단할 수 있다.
- 테스트 vault path를 알고 있다.
- 외부 LLM 호출은 테스트에서 mock할 수 있다.

## 시나리오 A - Persona skeleton 생성

단계:

```bash
synapse-memory persona start --vault "$VAULT"
```

기대 결과:

```text
$VAULT/90_System/AI/Persona/Profile.md
$VAULT/90_System/AI/Persona/Voice.md
$VAULT/90_System/AI/Persona/Boundaries.md
$VAULT/90_System/AI/Persona/Inbox.md
```

stdout에는 다음 값이 포함된다.

```text
Persona OS ready
next_question:
```

같은 명령을 다시 실행해도 기존 파일 내용은 덮어쓰지 않는다.

## 시나리오 B - 답변을 pending claim으로 추가

단계:

```bash
synapse-memory persona add "나는 길고 화려한 설명보다 근거가 분명한 짧은 답변을 선호한다." --vault "$VAULT"
```

기대 결과:

- `Persona/Inbox.md`에 pending claim이 추가된다.
- `Persona/Profile.md`, `Persona/Voice.md`, `Persona/Boundaries.md`는 아직 변경되지 않는다.
- raw 입력은 vault-visible 파일에 그대로 나타나지 않는다.
- L0 private evidence file 또는 `evidence.jsonl`에 evidence record가 생긴다.

## 시나리오 C - markdown 첨부 추가

단계:

```bash
synapse-memory persona add --file ./tests/fixtures/persona/sample-voice.md --vault "$VAULT"
```

기대 결과:

- 지원되는 markdown 파일은 evidence batch로 기록된다.
- claim 후보가 `Inbox.md`에 추가된다.
- stdout은 raw 파일 내용을 그대로 출력하지 않는다.

## 시나리오 D - unsupported PDF 첨부

단계:

```bash
synapse-memory persona add --file ./sample.pdf --vault "$VAULT"
```

기대 결과:

```text
unsupported file type: .pdf
```

명령은 non-zero exit code로 끝나고, partial evidence batch를 남기지 않는다.

## 시나리오 E - pending claim 검토와 승인

단계:

```bash
synapse-memory persona review --vault "$VAULT"
synapse-memory persona review --accept pc_YYYYMMDD_NNN --vault "$VAULT"
```

기대 결과:

- 첫 명령은 pending claim 목록을 보여준다.
- accept 후 claim category에 따라 `Profile.md`, `Voice.md`, 또는 `Boundaries.md`에 provenance와 함께 추가된다.
- `Inbox.md`의 해당 claim은 더 이상 pending으로 남지 않는다.

## 시나리오 F - 다음 질문 생성

단계:

```bash
synapse-memory persona next --vault "$VAULT"
```

기대 결과:

- 질문은 하나만 출력된다.
- coverage가 부족한 category가 함께 표시된다.
- pending claim 수가 threshold 이상이면 새 질문 대신 review 안내를 출력한다.

## 시나리오 G - 승인된 Persona로 시뮬레이션

단계:

```bash
synapse-memory persona simulate "면접에서 실패 경험을 묻는다면 어떻게 답할까?" --vault "$VAULT"
```

기대 결과:

- 충분한 accepted claim이 있으면 답변과 claim id를 출력한다.
- 근거가 부족하면 답변 대신 추가 질문을 출력한다.
- `Boundaries.md`의 accepted rule을 위반하는 상황이면 refusal을 출력한다.

## 검증 명령

계획 단계 이후 구현 PR에서 최소 다음 테스트를 제공한다.

```bash
python3 -m pytest \
  tests/test_persona_files.py \
  tests/test_persona_evidence.py \
  tests/test_persona_review.py \
  tests/test_persona_questions.py \
  tests/test_persona_simulate.py \
  tests/test_persona_cli.py -q
```
