# Quickstart Results: Raw RAG Hybrid

**Date**: 2026-05-12  
**Branch**: `006-raw-rag-hybrid`  
**Runner**: local macOS, `python3 -m synapse_memory.cli` from current checkout

## Notes

- Quickstart uses `synapse-memory`; this smoke used `python3 -m synapse_memory.cli` to ensure the current checkout was executed.
- Interactive endpoints were run with `SYNAPSE_FROM_AGENT=1`.
- Current local vault had Project/Company Cards but no discoverable raw source files under `10_Active/` or `~/.synapse/private/redacted/claude-code/`, so raw chunk counts were `0`.
- During the first `ask` smoke, Codex CLI compatibility issues were found and fixed:
  - removed obsolete `codex exec --ask-for-approval never`
  - changed interactive CLI default `--model` from Claude-only `sonnet` to provider default (`None` at argparse level)

## Transcript

### 0. 환경 확인

```text
$ python3 -m synapse_memory.cli doctor
Synapse Memory 환경 진단
============================================
✓ apfel 설치: /opt/homebrew/bin/apfel
  버전: apfel v1.3.3
✓ Apple Silicon (arm64)
✓ macOS 26.3.1 (Tahoe+)
✓ L0 루트: /Users/jimmy/.synapse/private (0700)
✓ AI provider (codex): /Users/jimmy/.nvm/versions/node/v22.18.0/bin/codex [codex-cli 0.128.0] (model=gpt-5.4)
============================================
✓ 준비 완료
```

```text
$ python3 -m pytest tests/test_rag_indexer.py -q
13 passed
```

### 1. Card-only baseline 인덱싱

```text
$ python3 -m synapse_memory.cli rag index --rebuild
인덱싱 시작 (rebuild=True, include_raw=False)
  [project] 11개 임베딩 중...
  [company] 2개 임베딩 중...

인덱싱 완료: project=11 company=2 raw_obsidian=0 raw_claude_code=0 bm25=0 bytes=12117
총 벡터: 13
```

```text
$ SYNAPSE_FROM_AGENT=1 python3 -m synapse_memory.cli ask "당근마켓 경험" --top-k 5
질문: 당근마켓 경험

자료상 당근마켓 관련 직접 경험은 확인되지 않습니다. 당근마켓 카드는 회사 기본 정보만 있고, 기술 스택·문화·매칭되는 내 프로젝트·메모 본문은 모두 미작성 상태입니다. [danggeun]

확인 가능한 내용은 당근마켓이 대한민국의 대형 타깃 회사이며, "대한민국 대표 하이퍼로컬 중고거래 플랫폼"으로만 정리돼 있다는 점까지입니다. [danggeun]

============================================================
출처 (5):
  [0.395] card_company   danggeun — 당근마켓
  [0.616] card_project   카뱅지원-2026 — 카카오뱅크 AI모바일개발팀 지원 (2026)
  [0.634] card_project   dansim-ios — 단심 (명상 앱)
  [0.638] card_project   -----2026 — 2026 프로젝트
  [0.651] card_project   Tablet — 태블릿 앱
```

### 2. raw 포함 인덱싱

```text
$ python3 -m synapse_memory.cli rag index --rebuild --include-raw
인덱싱 시작 (rebuild=True, include_raw=True)
  [project] 11개 임베딩 중...
  [company] 2개 임베딩 중...

인덱싱 완료: project=11 company=2 raw_obsidian=0 raw_claude_code=0 bm25=13 bytes=12117
총 벡터: 13
```

### 3. hybrid ask

```text
$ SYNAPSE_FROM_AGENT=1 python3 -m synapse_memory.cli ask "당근마켓 경험" --hybrid --top-k 5
질문: 당근마켓 경험

현재 자료상 당근마켓 관련 제 경험은 확인되지 않습니다. 매칭되는 프로젝트, 기술 스택, 문화 관련 내용이 비어 있고, 회사명과 기본 정보만 등록된 상태입니다. [danggeun]

상세히 말하면 당근마켓은 대한민국 대표 하이퍼로컬 중고거래 플랫폼으로만 정리되어 있으며, 관련 메모에도 "노트 본문 미작성. 회사명·기본 정보만 등록된 상태"라고 되어 있습니다. [danggeun]

============================================================
출처 (5):
  [0.033] card_company   danggeun — 당근마켓
  [0.031] card_company   메가스터디 — 메가스터디
  [0.016] card_project   카뱅지원-2026 — 카카오뱅크 AI모바일개발팀 지원 (2026)
  [0.016] card_project   dansim-ios — 단심 (명상 앱)
  [0.016] card_project   -----2026 — 2026 프로젝트
```

### 4. hybrid recall

```text
$ SYNAPSE_FROM_AGENT=1 python3 -m synapse_memory.cli me what-did-i-think "이직 제안" --hybrid --top-k 8
주제: 이직 제안

이직에 대해 사용자는 일관되게 "지금까지 쌓은 iOS·모듈화·AI 협업 역량을 더 잘 쓰는 다음 자리"를 탐색해왔고, 2026-05에는 카카오뱅크 지원으로 실제 행동까지 옮긴 흔적이 분명합니다. [메가스터디][카뱅지원-2026]

... 중략 ...

============================================================
출처 (8):
  - -----2026
  - 카뱅지원-2026
  - 메가스터디
  - dansim-ios
  - projects
  - Tablet
  - danggeun
  - 이력서-2026
```

### 5. prompt privacy smoke

```text
$ python3 -m pytest tests/test_endpoints_ask.py::TestAsk::test_hybrid_prompt_uses_redacted_raw_context -q
1 passed
```

## Result

Pass with caveat: raw source discovery returned 0 local raw chunks in this environment, so live raw citation output was not exercised. The raw indexing and no-raw-prompt behavior remain covered by automated fixture tests.
