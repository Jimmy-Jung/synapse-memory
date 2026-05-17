---
name: redact
description: Use when the user wants to share a private/sensitive file with an external AI safely. Reads a local file, applies Pass 1 (regex + redactlist) + Pass 2 (apfel local LLM) redaction, and prints/saves the masked result. Use for files in vault `90_System/Private/`, notes with PII, or anything mentioning NDA companies.
---

# /sm:redact — 파일 단위 redaction

단일 파일을 로컬에서 마스킹해 외부 AI에 안전하게 전달할 수 있는 형태로 변환합니다. 원본 파일은 변경되지 않습니다.

## 실행

```bash
synapse-memory redact file <path> [--out <output-path>]
```

- `<path>` — redact할 입력 파일
- `--out PATH` — 결과를 파일로 저장 (생략 시 stdout)

## 흐름

1. Pass 1 — 결정적 regex + redactlist (NDA 회사명·프로젝트명)
2. Pass 2 — apfel 로컬 LLM이 이름·주소·자유형 PII 검출
3. 결과를 stdout/파일에 출력

## fallback

apfel 미설치 환경 (macOS < 26 또는 비 Apple Silicon) 에서는 Pass 1 only로 동작합니다. stderr에 경고가 출력되며, 종료 코드는 그대로 0 입니다. 사용자가 Pass 2 누락을 인지하고 결과를 한 번 더 검토해야 합니다.

## 제약

- UTF-8 텍스트만 (binary 파일은 skip)
- 단일 파일 1 MB 한도
- 종료 코드: `0` = 정상 / `2` = 입력 무효 (파일 없음 / 1 MB 초과 / binary)

## 권장 동반

- `synapse-memory doctor` — vault `90_System/Private/` 폴더에 대한 `.claude/settings.json` permissions.deny 설정 점검
- `synapse-memory redactlist add <단어>` — NDA 회사명·프로젝트명 강제 마스킹 단어 등록
