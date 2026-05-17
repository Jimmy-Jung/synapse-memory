---
description: 단일 파일을 Pass 1+2 redaction (regex + apfel)으로 마스킹해 stdout 또는 --out 경로에 출력. apfel 미설치 시 Pass 1 only fallback.
argument-hint: <path> [--out <output-path>]
---

!`synapse-memory redact file $ARGUMENTS`

위 출력은 입력 파일에 Pass 1 (deterministic regex + redactlist) 과 Pass 2 (apfel 로컬 LLM 컨텍스트 검토)를 적용한 결과입니다. 원본 파일은 변경되지 않습니다. 외부 AI에 전달할 때는 이 결과만 복사하세요.

## 사용 시점

- vault `90_System/Private/` 같은 개인 메모를 외부 AI에 일부만 공유할 때
- 회사명·이름·연락처가 섞인 노트를 분석 의뢰할 때
- redactlist에 등록된 NDA 회사명을 의식적으로 마스킹할 때

## 옵션

- `<path>` — redact할 입력 파일 (필수)
- `--out PATH` — 결과를 stdout 대신 파일로 저장

## 제약

- UTF-8 텍스트만 (binary 파일은 skip + stderr 경고)
- 단일 파일 1 MB 한도
- apfel 미설치 환경 (macOS < 26 또는 Apple Silicon 아님)에서는 Pass 1 only fallback. Pass 2의 자유형 PII (이름·주소 등) 검출은 동작하지 않으니 결과를 한 번 더 사용자가 확인하세요.

## 종료 코드

- `0` — 정상
- `2` — 입력 파일 없음 / 1 MB 초과 / UTF-8 디코드 실패
