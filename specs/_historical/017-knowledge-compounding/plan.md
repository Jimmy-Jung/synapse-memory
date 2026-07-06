# 구현 계획: Knowledge Compounding

> 저자: JunyoungJung  
> 작성일: 2026-06-11  
> 브랜치: `release/1.16.0`  
> 상태: IMPLEMENTATION

## 요약

Spec 017은 synapse-memory가 매번 RAG로만 답을 합성하고 버리는 흐름을
축적형 지식 루프로 바꾸는 작업이다. 이번 release의 구현 단위는 proposal의
P1, 즉 `ask --save`로 좋은 답변을 `InsightCard`로 저장하고 다음 인덱싱 대상에
합류시키는 것까지로 제한한다.

P2-P6는 proposal에 설계가 있으나 카드 병합, graph link, lint stage까지 동시에
넓히면 release 위험이 커진다. P1은 기존 `ask`, `last_response`, card/indexer
경계에 작게 붙일 수 있고 사용자 가치가 즉시 확인된다.

## 기술 맥락

**언어/버전**: Python 3.11+ package  
**주요 의존성**: 기존 `synapse_memory` CLI, vault detector, redaction, RAG indexer  
**저장 위치**: `<vault>/20_Reference/Insights/<yyyy>/<mm>/<insight_id>.md`  
**테스트**: pytest unit/endpoint/CLI parser tests  
**대상 플랫폼**: macOS local-first CLI workflow  
**보안 원칙**: vault-visible 답변 본문은 저장 전 redaction을 통과한다.

## 구현 범위

### 포함

- `InsightCard` dataclass, markdown serialize/parse, save/list/load helper.
- `ask(..., save=True)`가 답변을 InsightCard로 저장하고 `saved_path`를 반환.
- CLI `synapse-memory ask "<query>" --save`.
- `rag.indexer`에 `card_insight:` 단건 upsert helper.
- config 기본 reference folder에 `insights` 경로 추가.
- `rag index --rebuild`가 기존 InsightCard를 다시 인덱싱한다.
- InsightCard 파일명 충돌 시 기존 파일을 덮어쓰지 않고 suffix를 붙인다.
- 질문과 답변 모두 vault 저장 전 redaction을 통과한다.
- `rag index`가 카드/Insight BM25 문서를 갱신할 때 기존 raw BM25 문서를
  조용히 지우지 않는다. `--include-raw`가 없으면 기존 sidecar의 raw 문서를
  보존하고 카드 계열 문서만 교체한다.

### 제외

- 자동 저장 프롬프트.
- `decide` / `recall` write-back.
- card related field 및 Obsidian wikilink 주입.
- merge/contradiction/lint/index.md stage.
- 단건 `ask --save` 직후 BM25 sidecar 증분 갱신. `rag index`를 다시 실행하면
  InsightCard가 dense/BM25 양쪽에 포함된다.

## Pseudocode

```text
cmd_ask(args):
    model/top_k/provider/guard 처리
    result = ask(query, ..., save=args.save)
    print answer and sources
    if result.saved_path:
        print saved path

ask(query, save=False):
    validate query
    retrieve records
    if no results:
        return AskResult(answer="자료 없음", sources=[])
    answer = ai.complete(prompt)
    sources = SourceCitation list
    record_last_answer(query, sources)
    result = AskResult(query, answer, sources)
    if save:
        result.saved_path = save_insight_from_ask(result)
    return result

save_insight_from_ask(result):
    created = now local ISO timestamp
    insight_id = date + slugified question
    body = redact_full(result.answer).redacted
    card = InsightCard(question, command="ask", related=source card ids, body=body)
    path = save_insight_card(card)
    try index_insight_card(card)
    if indexing unavailable, keep saved markdown and do not fail ask
    return path
```

## 헌법 검토

| 원칙 | 결과 | 근거 |
| --- | --- | --- |
| Local-First & Privacy | 통과 | InsightCard는 사용자 vault에만 저장하고 private vector store에만 인덱싱한다. |
| Two-Pass Redaction | 통과 | 저장 본문은 `redact_full()` 결과를 사용한다. apfel이 없으면 기존 구현처럼 Pass 1로 폴백된다. |
| Test-First Discipline | 통과 | card, endpoint, indexer, CLI parser 테스트를 먼저 추가한다. |
| Conversation Context | 통과 | 기존 `ask` endpoint와 interactive guard 정책을 유지한다. |
| Observability | 통과 | 저장 경로를 CLI에 출력하고 `last_response` 저장은 유지한다. |
| Consent Scoping | 통과 | 저장은 명시적 `--save`에서만 발생한다. |

## 파일 변경

```text
src/synapse_memory/cards/insight.py
src/synapse_memory/cards/__init__.py
src/synapse_memory/config.py
src/synapse_memory/endpoints/ask.py
src/synapse_memory/rag/indexer.py
src/synapse_memory/cli.py
tests/test_cards_insight.py
tests/test_endpoints_ask.py
tests/test_rag_indexer.py
tests/test_rag_cli.py
```

## 검증

```text
uv run pytest \
  tests/test_cards_insight.py \
  tests/test_endpoints_ask.py \
  tests/test_rag_indexer.py \
  tests/test_rag_cli.py
```
