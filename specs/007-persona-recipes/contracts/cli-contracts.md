# Phase 1 CLI Contracts — Me Generator Recipes

**Feature**: 007-me-recipes
**Date**: 2026-05-12

본 문서는 [plan.md](../plan.md) 의 Phase 1 산출물 중 CLI 인터페이스 contract.
새 서브커맨드 3 종 (`me generate`, `me recipes list`, `me recipes show`) 의
정확한 입력·출력·exit code 를 명세한다. tasks 단계의 contract test 가 본 문서를
기준으로 작성된다.

## 1. `synapse-memory me generate <recipe> [--key=value ...]`

### Classification

- **Interactive endpoint** (constitution Principle IV).
- TTY 가드 적용: 직접 호출 시 3 초 안내 후 진행. `SYNAPSE_FROM_AGENT=1` 시 bypass.

### Positional argument

| Arg | 필수 | 설명 |
|-----|------|------|
| `<recipe>` | ✅ | recipe name. registry 에서 lookup. |

### Optional flags

| Flag | 타입 | Default | 설명 |
|------|------|---------|------|
| `--key=value` (반복) | str | — | recipe `input_schema` 의 키-값. required 키는 반드시 1 회 이상. |
| `--language=<locale>` | str | (precedence) | locale precedence 의 0 순위 (CLI override) |
| `--domain=<domain>` | str | (precedence) | domain precedence 의 0 순위 |
| `--model=<alias>` | str | recipe 기본값 | LLM 모델 override |
| `--vault=<path>` | path | env / default | vault 경로 override |
| `--today=<YYYY-MM-DD>` | date | 시스템 today | `{today}` placeholder 값 override (테스트용) |
| `--dry-run` | flag | off | LLM 호출 직전까지 진행 후 prompt 만 stdout 출력, 저장·last_answer 건너뜀 |

### Stdout

성공 시:
```
<answer markdown — recipe.system_prompt 가 지시한 형식 그대로>
```

`save_subpath` 가 set 일 때 마지막 줄에 1 줄 요약 추가:
```
[saved] <absolute path>
```

### Stderr

진행 로그 (constitution Principle V observability):
```
[me.generate.<recipe_name>] locale=<src:value> domain=<src:value> profile_used=<bool> matched=<count> duration=<ms>
```

### Exit codes

| Code | 의미 |
|------|------|
| `0` | 성공 |
| `2` | recipe 미발견 (근접 이름 제안 stderr 출력) |
| `3` | required input 누락 (FR-014, 누락 키 목록 stderr) |
| `4` | recipe 검증 실패 (32 KB 초과 등 — `me recipes show` 권유) |
| `5` | RAG matched 0 건 + recipe 의 fallback 메시지 |
| `10` | AI provider 호출 실패 (timeout/네트워크) |
| `1` | 일반 에러 (vault not found 등) |

### Side effects

- `save_subpath` 가 set 이고 LLM 호출이 성공한 경우에만 vault 에 파일 저장.
  같은 이름 존재 시 R-5 의 timestamp suffix fallback.
- `last_answer` 가 갱신됨 (성공 케이스만).

### Examples

```bash
# 빌트인 recipe
$ synapse-memory me generate weekly_report --period=2026-W19

# 사용자 recipe
$ synapse-memory me generate diary --topic=오늘회고

# locale override
$ synapse-memory me generate resume --company_id=acme_co --language=en

# dry-run (prompt 미리보기)
$ synapse-memory me generate brainstorm --topic="시간관리 도구" --dry-run
```

## 2. `synapse-memory me recipes list`

### Classification

- **Batch endpoint** (LLM 미호출, TTY 가드 없음).

### Optional flags

| Flag | 타입 | Default | 설명 |
|------|------|---------|------|
| `--source=<builtin\|user\|all>` | enum | `all` | 출력 범위 필터 |
| `--vault=<path>` | path | env / default | vault 경로 override |
| `--verbose` | flag | off | skipped recipe (검증 실패) 도 표시 |
| `--json` | flag | off | machine-readable JSON 출력 |

### Stdout (default)

```
NAME              SOURCE   REQUIRED INPUTS         DESCRIPTION
brainstorm        builtin  topic                   주제에 대한 발산형 아이디어 생성
journal           builtin  date                    그날의 vault 활동을 일기 형태로 정리
resume            builtin  company_id              회사 맞춤 이력서
weekly_report     builtin  period                  주간 보고
diary             user     topic                   (사용자 정의)
```

(공백 정렬, name asc.)

### Stdout (`--json`)

```json
[
  {
    "name": "brainstorm",
    "source": "builtin",
    "description": "...",
    "required_inputs": ["topic"],
    "optional_inputs": ["audience"],
    "save_subpath": "30_Creative/Brainstorms",
    "locale_aware": true,
    "domain_aware": false
  }
]
```

### Exit codes

| Code | 의미 |
|------|------|
| `0` | 성공 (recipe 0 건이어도 0 — 빈 표 출력) |
| `1` | vault not found / IO 에러 |

## 3. `synapse-memory me recipes show <recipe>`

### Classification

- **Batch endpoint**.

### Positional argument

| Arg | 필수 | 설명 |
|-----|------|------|
| `<recipe>` | ✅ | recipe name |

### Optional flags

| Flag | 타입 | Default | 설명 |
|------|------|---------|------|
| `--vault=<path>` | path | env / default | — |
| `--json` | flag | off | JSON 출력 |
| `--full` | flag | off | system prompt 전체 출력 (default 는 처음 20 줄) |

### Stdout (default)

```
name:           weekly_report
source:         builtin
source_path:    /…/src/synapse_memory/recipes/builtin/weekly_report.md
description:    주간 보고
input_schema:
  - period (required)
  - audience (optional)
rag_filter:     {"source_kind": "card_project"}
rag_top_k:      10
use_profile:    true
save_subpath:   30_Creative/Reports
locale_aware:   true
domain_aware:   false
timeout:        120
model:          sonnet

system_prompt (first 20 lines):
당신은 사용자의 주간 보고 작성 어시스턴트입니다.
…
```

### Exit codes

| Code | 의미 |
|------|------|
| `0` | 성공 |
| `2` | recipe 미발견 (`me recipes list` 권유) |
| `1` | IO 에러 |

## 4. Backward compatibility — 기존 서브커맨드

다음 기존 서브커맨드는 stdout · exit code · 저장 경로가 본 feature 도입 후에도
변하지 않는다 (SC-005 / FR-008).

- `me draft-resume <company_id> [--top-k-projects=N] [--model=...]`
- `me what-did-i-think <topic> [--top-k=N] [--by=time|distance] [--timeline] [--limit=N] [--hybrid]`
- `me decide <situation> [--top-k=N] [--model=...]`

내부적으로 wrapper 가 `generate()` 를 호출하지만 외부 관찰자에게는 차이가 없다.
단 `last_answer` 의 `command` 필드는 `me.generate.resume` / `me.generate.recall` /
`me.generate.decide` 로 통일된다 (R-6 — 의도된 변경).

## 5. JSON envelope (모든 `--json` 출력)

```json
{
  "ok": true,
  "data": "<subcommand-specific>",
  "errors": []
}
```

실패 시:

```json
{
  "ok": false,
  "data": null,
  "errors": [
    {"code": "RECIPE_NOT_FOUND", "message": "...", "suggestions": ["..."]}
  ]
}
```
