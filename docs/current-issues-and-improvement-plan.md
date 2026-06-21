# 현재 문제점과 개선 방향

작성자: JunyoungJung  
작성일: 2026-06-21

이 문서는 2026-06-21 기준 `synapse-memory`의 현재 구조가 의도대로 동작하는지
검토한 결과를 후속 작업용으로 정리한 문서입니다. 핵심 결론은 다음과 같습니다.

- 제품 방향은 대체로 맞습니다. Claude/Codex 대화를 `~/.synapse/private/`에 미러하고,
  provider-only 방식으로 Obsidian wiki/card/profile로 통합하는 구조는 현재 코드와 맞습니다.
- 문제는 구현이 전혀 없는 것이 아니라, 정책 문서·운영 관측성·동시성·레거시 표현이
  현재 구현과 어긋나기 시작했다는 점입니다.
- 가장 먼저 정해야 할 것은 raw 대화를 외부 AI provider에 직접 보낼 것인지입니다. 이
  결정을 내린 뒤 문서, 테스트, 코드 경계를 한 방향으로 맞춰야 합니다.

## 감사 기준

| 항목 | 기준 |
| --- | --- |
| 감사 기준일 | 2026-06-21 |
| 기준 커밋 | `f9f3d55` |
| 검토 범위 | `README.md`, `docs/`, `specs/`, `src/synapse_memory/`, `tests/`, 실제 Documents vault 사용 흔적 |
| 검증 | targeted pytest 69개 통과, 전체 ruff 통과, 전체 pytest 1012개 통과(위임 검증), full strict mypy 24개 오류 |

## release/1.19.0 적용 결과

`release/1.19.0`에서는 이 문서의 Phase 0~3 개선을 phase별 커밋으로 적용했습니다.

| Phase | 적용 결과 |
| --- | --- |
| Phase 0 | raw-to-provider 정책 A를 공식화하고 `privacy_mode=raw_or_sampled_raw_to_provider`를 `ingest-audit`, `doctor`, `config show`, README/docs에 노출 |
| Phase 1 | provider error sanitization, shared ingest lock, source별 `watch status --json`, `launchctl` 실패 전파, doctor watermark/error freshness 점검 도입 |
| Phase 2 | `AGENTS.md` source-of-truth를 provider-only 설계로 교체, superseded spec 배너 추가, active CLI/config/source의 legacy RAG/Chroma/BM25/RRF 표현 정리 |
| Phase 3 | full strict mypy debt 해결, CI/release-check static gate를 전체 `src/synapse_memory`/`tests`로 확대 |

적용 후 검증:

- `uv run python -m ruff check src/synapse_memory tests` 통과
- `uv run python -m mypy --strict src/synapse_memory` 통과
- `uv run python -m pytest tests/ -W ignore::DeprecationWarning` → `1030 passed`

## 우선순위 요약

| 우선순위 | 문제 | 영향 | 개선 방향 |
| --- | --- | --- | --- |
| P0 | 개인정보/데이터 흐름 정책 충돌 | 사용자가 무엇이 외부 AI로 나가는지 잘못 이해할 수 있음 | raw-to-provider 정책 결정 후 문서와 코드 경계 통일 |
| P0 | vault-visible 운영 로그 누출 | provider error JSON, session id 같은 운영 식별자가 synced vault에 남음 | provider error sanitization 도입 |
| P1 | shared ingest lock 부재 | watch/manual ingest/backfill이 같은 vault page, watermark, `log.md`를 동시에 쓸 수 있음 | 모든 ingest writer를 같은 lock 정책으로 묶기 |
| P1 | source-of-truth drift | 새 agent가 superseded spec을 현재 설계로 오해할 수 있음 | `AGENTS.md`와 stale spec에 상태 배너 추가 |
| P1 | watch 관측성/설치 신뢰도 부족 | codex watermark가 숨겨지고 launchctl 실패가 성공처럼 보일 수 있음 | per-source status, install failure propagation, doctor 강화 |
| P2 | RAG/Chroma/hybrid 잔여 표현 | provider-only 구조를 다시 BM25/vector 구조로 오해할 수 있음 | CLI help, config, 주석, spec 정리 |
| P2 | CI static-check subset | CI green이 전체 type health를 의미하지 않음 | mypy/ruff gate 확대 또는 명시적 baseline 운영 |

## 1. 개인정보/데이터 흐름 정책 충돌

### 현재 상태

문서와 코드가 서로 다른 개인정보 경계를 말합니다.

- `docs/privacy-and-cost.md`와 `docs/start-here.md`는 raw mirror가 외부 AI로 직접
  나가지 않고, 요약·마스킹·승인 경로를 거친다고 설명합니다.
- `README.md`의 pipeline 설명은 `~/.synapse/private/raw`에서 `ingest(LLM)`로
  Obsidian wiki를 만드는 흐름을 설명합니다.
- `src/synapse_memory/storage/l0.py`는 v2가 raw를 cloud CLI에 직접 전달하는 것을
  신뢰 전제로 둔다고 적고 있습니다.
- `src/synapse_memory/wiki/ingest.py`는 small doc 전체 또는 large doc sample을
  integration prompt로 만들고 provider를 호출합니다.
- `src/synapse_memory/llm/claude.py`는 raw text를 cloud Claude CLI에 전달하고
  redaction을 제거했다고 명시합니다.

즉 실제 구현이 몰래 다른 동작을 하는 문제라기보다, 현재 정책 표면이 서로 충돌합니다.

### 영향

- 사용자는 "raw는 절대 외부 AI로 직접 가지 않는다"고 이해할 수 있습니다.
- 운영자가 backfill/ingest 비용과 개인정보 경계를 판단하기 어렵습니다.
- 향후 agent가 문서만 보고 redaction 경로를 되살리거나, 반대로 privacy 문서를 계속
  방치할 수 있습니다.

### 개선 방향

먼저 둘 중 하나를 명시적으로 선택해야 합니다.

#### 선택 A: D4 raw-to-provider를 공식 정책으로 인정

이 경우 raw session text 또는 sampled raw text가 provider로 갈 수 있음을 문서와 CLI에
명확히 표시합니다.

필수 작업:

1. `docs/privacy-and-cost.md`를 `query/ask` 경로와 `ingest/backfill` 경로로 나눕니다.
2. `docs/start-here.md`의 "외부 AI에는 절대 직접 전송되지 않음" 표현을 수정합니다.
3. `synapse-memory ingest-audit` 또는 `backfill` 도움말에 예상 provider 호출 수와 raw/sample
   전송 여부를 표시합니다.
4. `doctor` 또는 `config`에 현재 privacy mode를 보여줍니다.

의사코드:

```python
def describe_privacy_mode(config: Config) -> PrivacyMode:
    if config.maintenance.engine in {"claude", "codex"}:
        return PrivacyMode(
            ingest="raw_or_sampled_raw_to_provider",
            query="wiki_cards_and_approved_profile_to_provider",
        )
    return PrivacyMode(ingest="local_only_or_disabled", query="provider_dependent")
```

#### 선택 B: redaction/summary gate를 복원

이 경우 provider 호출 전에 raw text를 반드시 redaction 또는 summary gate에 통과시킵니다.

필수 작업:

1. `wiki.ingest`에서 raw chunk를 prompt로 넘기기 전에 redaction/summary stage를 둡니다.
2. provider prompt capture 테스트에서 email, token-like string, local path, session id가
   raw 형태로 들어가지 않는지 확인합니다.
3. redaction 실패 시 fail-closed 할지, sampled summary만 보낼지 정책을 정합니다.
4. 비용 증가와 품질 저하를 `ingest-audit`에서 미리 보여줍니다.

의사코드:

```python
def prepare_ingest_prompt_text(raw_text: str, policy: PrivacyPolicy) -> str:
    if policy.allow_raw_provider_ingest:
        return raw_text

    redacted = redact_for_provider(raw_text)
    if redacted.has_blocking_findings:
        raise PrivacyBoundaryError(redacted.summary)
    return redacted.text
```

### 권장 결정

단기적으로는 선택 A를 명확히 문서화하는 편이 현실적입니다. 현재 구현은 이미 D4를 전제로
되어 있고, 즉시 redaction gate를 되살리면 품질·비용·테스트 범위가 크게 바뀝니다. 다만
문서화와 동시에 provider error log sanitization은 반드시 먼저 적용해야 합니다.

### 검증 기준

- `docs/privacy-and-cost.md`와 `docs/start-here.md`가 `ingest/backfill`의 provider 전송
  정책을 같은 문장으로 설명합니다.
- `synapse-memory ingest-audit --source codex --limit 5` 출력에서 provider 호출과
  raw/sample 전송 여부를 사용자가 알 수 있습니다.
- privacy mode에 대한 단위 테스트가 있습니다.

## 2. vault-visible 운영 로그 누출

### 현재 상태

`src/synapse_memory/wiki/log.py`는 전달받은 message를 그대로 vault root의 `log.md`에
append합니다. `wiki.ingest`는 large doc 처리 실패 시 `type(exc).__name__`과 `exc` 문자열을
그대로 `append_log()`에 전달합니다.

실제 Documents vault의 `log.md`에는 provider 429 JSON, `session_id`, usage, service tier
조각이 남아 있었습니다. raw transcript, API key, token 누출 증거는 확인하지 못했지만,
synced vault와 git review surface에 남기기에는 과한 운영 payload입니다.

### 영향

- iCloud/Obsidian/git에 provider 내부 error payload가 남습니다.
- session id 같은 운영 식별자가 장기 보존됩니다.
- 로그가 너무 길어져 실제 ingest 성공/실패 흐름을 읽기 어려워집니다.

### 개선 방향

provider error를 그대로 문자열화하지 말고, vault에 남길 수 있는 안전한 요약으로 변환합니다.

필수 작업:

1. `summarize_provider_error(exc)`를 추가합니다.
2. JSON error payload에서 `session_id`, token-like field, raw response body를 제거합니다.
3. `log.md` 한 줄 길이를 제한합니다.
4. 상세 원문이 필요하면 `~/.synapse/private/` 아래 machine-local debug log에만 저장합니다.

의사코드:

```python
SAFE_ERROR_FIELDS = {"provider", "status", "category", "retry_after", "message"}

def summarize_provider_error(exc: Exception) -> str:
    payload = parse_provider_error_payload(str(exc))
    if payload is None:
        return truncate(redact_operational_ids(str(exc)), 240)

    safe = {key: payload[key] for key in SAFE_ERROR_FIELDS if key in payload}
    return truncate(json.dumps(safe, ensure_ascii=False), 240)
```

### 검증 기준

- provider 429 fixture를 넣었을 때 vault `log.md`에 `session_id`가 포함되지 않습니다.
- `tests/test_wiki_ingest.py`에 skipped large doc error sanitization 테스트가 추가됩니다.
- 로그는 사람이 읽을 수 있는 한 줄 요약으로 남습니다.

## 3. shared ingest lock 부재

### 현재 상태

watch 경로는 `FileLock`을 잡고 `ingest_source()`를 호출합니다. 그러나 manual
`synapse-memory ingest`와 `backfill`은 같은 `ingest_source()`를 직접 호출합니다.

공유되는 write surface:

- wiki page markdown
- source별 watermark
- vault root `log.md`
- `SCHEMA.md` 보장 파일

### 영향

- watch와 backfill이 동시에 돌면 같은 page를 서로 다른 순서로 갱신할 수 있습니다.
- watermark가 예상보다 먼저 전진하거나, 실패 재시도 정책이 꼬일 수 있습니다.
- `log.md`가 섞여 원인 추적이 어려워질 수 있습니다.

### 개선 방향

`ingest_source()` 자체는 순수 orchestrator로 유지하되, CLI/manual/backfill/watch entrypoint가
공통 lock wrapper를 사용하게 만듭니다.

의사코드:

```python
def run_locked_ingest(
    source: str,
    *,
    mode: Literal["watch", "manual", "backfill"],
    on_locked: Literal["skip", "fail", "wait"],
    **kwargs: object,
) -> IngestResult | LockedOutcome:
    try:
        with FileLock(default_lock_path()):
            return ingest_source(source, **kwargs)
    except LockHeldError:
        if on_locked == "skip":
            return LockedOutcome(source=source, mode=mode)
        if on_locked == "fail":
            raise IngestAlreadyRunningError(source, mode)
        return wait_and_retry(...)
```

권장 정책:

| entrypoint | lock 점유 중 동작 |
| --- | --- |
| `watch run` | skip, exit 0, `locked` 출력 |
| `ingest --now` | fail, exit non-zero, 현재 실행 중인 작업 안내 |
| `backfill` | fail 기본값, `--wait-lock` 옵션으로 대기 허용 |

### 검증 기준

- watch와 manual ingest가 같은 lock file을 사용합니다.
- lock held fixture에서 `watch run`은 skip하고, manual `ingest`는 non-zero로 실패합니다.
- backfill batch loop 전체가 lock 안에서 실행되는지, batch마다 lock을 새로 잡을지 정책이
  테스트로 고정됩니다.

## 4. source-of-truth drift

### 현재 상태

root `AGENTS.md`는 현재 기능 맥락을 `specs/010-persona-os/plan.md`에서 읽으라고 합니다.
하지만 해당 plan은 파일 자체가 `SUPERSEDED`이며, 5-CLI/4-file Persona 구조가 거부됐다고
명시합니다.

또한 `specs/006-raw-rag-hybrid`, `specs/008-recipe-hybrid-retrieval`, `specs/020-provider-only-retrieval`
일부는 현재 provider-only 코드와 맞지 않는 BM25/vector/hybrid 전제를 남깁니다.

### 영향

- 새 agent가 superseded plan을 현재 설계로 오해할 수 있습니다.
- 제거된 BM25/hybrid/indexer 구조를 다시 살리는 PR이 생길 수 있습니다.
- 문서 기반 검토와 코드 기반 검토의 결론이 갈립니다.

### 개선 방향

문서 상태를 명시적으로 관리합니다.

필수 작업:

1. `AGENTS.md`의 SPECKIT pointer를 현재 source of truth로 교체합니다.
2. superseded spec 상단에 큰 배너를 추가합니다.
3. provider-only 이후 남겨둔 호환 표면과 제거된 표면을 표로 정리합니다.
4. ~~`docs/README.md`에 운영/아키텍처 점검 문서 링크를 둡니다.~~ (완료 — `docs/README.md`에 이미 이 문서 링크 존재)

권장 source of truth:

| 용도 | 문서 |
| --- | --- |
| 사용자 시작 | `docs/start-here.md` |
| 명령 reference | `docs/reference.md` |
| privacy/cost | `docs/privacy-and-cost.md` |
| 현재 이슈/개선 계획 | 이 문서 |
| provider-only 설계 | `specs/020-provider-only-retrieval/design.md` |

### 검증 기준

- `rg "specs/010-persona-os/plan.md" AGENTS.md docs specs` 결과가 현재 source pointer로
  남아 있지 않습니다.
- superseded spec은 첫 화면에서 상태를 알 수 있습니다.
- `docs/README.md`에서 이 문서로 이동할 수 있습니다.

## 5. watch 관측성/설치 신뢰도 부족

### 현재 상태

`watch run`은 `claude-code`와 `codex` 두 source를 순회하지만, `watch status`는
`claude-code` watermark만 출력합니다. README와 reference는 source별 watermark를 설명하므로
구현과 문서가 다릅니다.

또한 `install_watch()`는 `launchctl load` 실패를 warning으로만 출력하고 path를 반환합니다.
CLI는 그대로 `installed:`를 출력합니다.

### 영향

- codex ingest가 멈춰도 status에서는 보이지 않습니다.
- launchd 등록 실패를 사용자가 성공으로 오해할 수 있습니다.
- doctor가 설치/config만 확인하면 "살아 있지만 처리하지 않는" 상태를 놓칩니다.

### 개선 방향

1. `watch status`를 source별 출력으로 바꿉니다.
2. `launchctl load` 실패를 install 실패로 승격합니다.
3. `doctor`가 최근 성공 ingest 시각, watermark freshness, `watch.err.log` 최근 오류를 확인합니다.
4. `watch status --json`을 추가해 GUI/agent가 기계적으로 읽을 수 있게 합니다.

의사코드:

```python
def watch_status() -> WatchStatus:
    return WatchStatus(
        installed=plist_path().exists(),
        sources=[
            SourceStatus(name=source, watermark=load_watermark(source), pending=pending_count(source))
            for source in WATCH_SOURCES
        ],
        recent_errors=tail_watch_errors(limit=5),
    )
```

### 검증 기준

- `watch status` output에 `claude-code`와 `codex`가 모두 포함됩니다.
- launchctl failure fixture에서 `watch install`이 non-zero를 반환합니다.
- doctor fixture에서 stale watermark가 warning/fail로 표시됩니다.

## 6. RAG/Chroma/hybrid 잔여 표현

### 현재 상태

현재 구조는 provider-only입니다. `rag/__init__.py`도 local embeddings/vector/BM25/hybrid/indexer가
제거됐고 chunker만 남았다고 설명합니다. 그러나 다음 잔여 표현이 있습니다.

- `ask --hybrid` help가 dense + BM25 RRF라고 설명합니다.
- persona `what-did-i-think --hybrid` help도 BM25/RRF를 암시합니다.
- `config.py`에 `top_k.rag_search`, `advanced.rag.rrf_k`, `embedding_model = "bge-m3"`가 남아 있습니다.
- `daily.py`와 `endpoints/persona.py`에 ChromaDB 관련 설명이 남아 있습니다.
- 오래된 specs가 제거된 BM25/hybrid module을 현재처럼 설명합니다.

> **심각도 보정 (2026-06-21 재검토)**: `--hybrid`는 이미 동작상 no-op입니다. `endpoints/ask.py`는
> `hybrid` 인자를 "폐기 — provider 선별로 일원화 (시그니처 호환)"으로 명시하고, ranking 분기를
> 만들지 않습니다. 따라서 실제 ranking 오작동 위험은 없고, 남은 문제는 help/config 표현뿐인
> cosmetic 정리입니다.

### 영향

- 사용자가 `--hybrid`가 실제 ranking 차이를 만든다고 오해할 수 있습니다.
- 새 agent가 provider-only 이후 제거된 구조를 되살릴 수 있습니다.
- config surface가 현재 기능보다 넓어져 유지보수 비용이 늘어납니다.

### 개선 방향

1. `--hybrid`를 즉시 제거하지 말고 compatibility no-op으로 명시합니다.
2. CLI help를 "호환 플래그, 현재 provider-only에서는 ranking 차이 없음"으로 바꿉니다.
3. `advanced.rag.*`는 deprecation path를 둡니다.
4. ChromaDB 주석과 daily stage 설명을 현재 구조로 고칩니다.
5. 오래된 specs에는 `SUPERSEDED_BY_PROVIDER_ONLY` 배너를 붙입니다.

### 검증 기준

- `synapse-memory ask --help`가 BM25/RRF를 언급하지 않습니다.
- `rg "ChromaDB|BM25|RRF|bge-m3" src docs specs` 결과가 의도된 legacy/spec 문맥만 남습니다.
- config migration 테스트가 기존 `advanced.rag.*` 설정을 깨지 않고 deprecation warning으로 처리합니다.

## 7. CI static-check subset과 mypy debt

### 현재 상태

행동 테스트는 건강합니다.

- targeted pytest 69개 통과
- 전체 ruff 통과
- 전체 pytest 1012개 통과

하지만 full strict mypy는 `src/synapse_memory` 전체에서 9개 파일 24개 오류가 있습니다. CI는
mypy/ruff를 hard-coded subset에만 실행하므로 CI green이 전체 type health를 의미하지 않습니다.

### 영향

- provider-only refactor 이후 타입 계약 drift가 늦게 발견됩니다.
- 새 모듈이 CI static-check 대상에 빠질 수 있습니다.
- 전체 mypy를 갑자기 켜면 unrelated debt가 PR을 막습니다.

### 개선 방향

단계적으로 확대합니다.

1. 현재 CI subset을 문서화합니다.
2. full mypy 오류를 active module과 legacy module로 분류합니다.
3. active module부터 CI target에 추가합니다.
4. 마지막에 `src/synapse_memory` 전체 strict mypy를 CI로 승격합니다.

권장 순서:

| 단계 | 대상 | 목표 |
| --- | --- | --- |
| 1 | `wiki/rawdoc.py`, `wiki/page.py`, `wiki/lint.py` | wiki ingest 주변 type 안정화 |
| 2 | `cards/card_index.py` | provider selection contract 안정화 |
| 3 | `wiki/llm_retrieval.py`, `wiki/query.py`, `wiki/ingest.py` | AIEnvironment/provider type 정리 |
| 4 | `collectors/git_self/mirror.py` | collector metadata typing 정리 |
| 5 | CI 전체 mypy | subset drift 제거 |

### 검증 기준

- `uv run python -m mypy --strict src/synapse_memory`가 통과합니다.
- CI workflow에서 hard-coded subset 대신 전체 package 또는 명시적 typed package list를 검사합니다.
- 새 source file이 static-check 대상에서 빠지지 않습니다.

## 개선 로드맵

### Phase 0: 정책 결정과 문서 동기화

목표: 사용자가 무엇이 외부 AI로 나가는지 정확히 알 수 있게 합니다.

작업:

1. raw-to-provider 정책을 선택합니다.
2. `docs/privacy-and-cost.md`, `docs/start-here.md`, `README.md`를 같은 표현으로 맞춥니다.
3. `ingest-audit` 출력에 privacy/cost 정보를 추가합니다.

완료 기준:

- 세 문서가 서로 충돌하지 않습니다.
- `ingest/backfill`과 `ask/query`의 데이터 전송 경계가 분리 설명됩니다.

### Phase 1: 운영 안전성 보강

목표: 실제 사용 중 데이터 race와 log 누출을 막습니다.

작업:

1. shared ingest lock wrapper 도입
2. provider error log sanitization
3. `watch status` source별 출력
4. `watch install` launchctl failure propagation
5. doctor freshness check

완료 기준:

- lock collision 테스트가 있습니다.
- vault `log.md`에 provider session id가 남지 않습니다.
- `watch status`에서 `claude-code`와 `codex`를 모두 볼 수 있습니다.

### Phase 2: source-of-truth 정리

목표: 사람과 agent가 같은 현재 설계를 읽게 합니다.

작업:

1. `AGENTS.md` pointer 수정
2. superseded spec 배너 추가
3. provider-only 이후 호환/제거 표면 정리
4. `docs/README.md`에 이 문서 링크 추가

완료 기준:

- superseded plan이 현재 plan처럼 참조되지 않습니다.
- `rg "BM25|ChromaDB|RRF"` 결과를 리뷰해 의도된 문맥만 남습니다.

### Phase 3: type/static gate 확대

목표: CI green의 의미를 넓힙니다.

작업:

1. full mypy 24개 오류 triage
2. active module부터 strict typing 수정
3. CI static-check target 확대

완료 기준:

- full strict mypy 통과
- CI가 전체 source 또는 유지관리되는 typed target list를 검사

## 후속 PR 단위 제안

| PR | 범위 | 포함 파일 후보 |
| --- | --- | --- |
| PR 1 | privacy 문서 정책 정렬 | `docs/privacy-and-cost.md`, `docs/start-here.md`, `README.md`, `docs/reference.md` |
| PR 2 | log sanitization | `wiki/log.py`, `wiki/ingest.py`, `tests/test_wiki_ingest.py` |
| PR 3 | shared ingest lock | `wiki/daemon.py`, `cli.py`, `wiki/backfill.py`, lock 관련 tests |
| PR 4 | watch 관측성 | `cli.py`, `wiki/launchd.py`, `doctor.py`, watch/launchd tests |
| PR 5 | source-of-truth cleanup | `AGENTS.md`, `specs/*`, `docs/README.md` |
| PR 6 | RAG/Chroma wording cleanup | `cli.py`, `config.py`, `daily.py`, `endpoints/persona.py`, 관련 tests |
| PR 7 | mypy debt | type 오류 파일 중심 |

> **순서 권장 (2026-06-21 재검토)**: PR 2(log sanitization)를 가장 먼저 진행합니다. 실제
> Documents vault `log.md`에 provider session_id/429 payload가 이미 34줄 남아 있고 iCloud/git로
> sync되는 중입니다. P0-1 정책 결정(PR 1)과 독립적으로 단독 머지 가능합니다.

## 최종 검증 명령

후속 작업마다 최소 아래 명령을 실행합니다.

```bash
uv run python -m pytest tests/test_cli_watch.py tests/test_wiki_launchd.py tests/test_wiki_ingest.py -q
uv run python -m pytest tests/test_provider_retrieval_020.py tests/test_endpoints_ask.py tests/test_endpoints_persona.py tests/test_recipes_pipeline.py tests/test_config.py -q
uv run python -m ruff check src/synapse_memory tests
uv run python -m mypy --strict src/synapse_memory
```

full pytest는 release 또는 큰 구조 변경 전에 실행합니다.

```bash
uv run python -m pytest tests/ -W ignore::DeprecationWarning
```
