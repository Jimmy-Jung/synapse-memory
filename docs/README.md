# Synapse Memory 문서

> Synapse Memory는 Obsidian vault와 Claude Code 활동 로그를 안전하게 정리해서,
> 개인 맥락을 검색·이력서 합성·의사결정에 활용하는 **로컬 우선** 메모리 도구입니다.

문서는 독자별로 분리되어 있습니다.

## 👤 비개발자라면 — [for-everyone/](for-everyone/)

처음 써보시는 분, 비유로 원리만 빠르게 이해하고 싶은 분.

| 문서 | 무엇 |
|---|---|
| [**5가지 답답함을 어떻게 풀었나**](for-everyone/how-it-works.md) | 통증 → 해결 → 담당 기능 매핑 (가장 먼저 읽기) |
| [**설계 개요**](for-everyone/architecture-overview.md) | 5가지 원칙·4단계 메모리로 *왜 이렇게 설계됐나* |
| [**무엇을 할 수 있는가**](for-everyone/what-you-can-do.md) | Before/After 5가지 활용 사례 + 슬래시 명령 예시 |
| [**설치 화면 가이드**](for-everyone/installer-walkthrough.md) | 더블클릭 설치 단계별 |
| [**Privacy · 비용 · 삭제 FAQ**](for-everyone/privacy-and-cost.md) | 자주 묻는 5가지 우려 |

## 🛠️ 매일 사용하시는 분 / CLI 사용자

| 문서 | 무엇 |
|---|---|
| [Getting Started](getting-started.md) | 수동 설치 + 첫 실행 (15~20분) |
| [사용 시나리오](usage.md) | 일일 워크플로 / 이력서 / 의사결정 / 회상 |
| [CLI 레퍼런스](commands.md) | 모든 명령 옵션 + 시나리오 예시 |

## 🧑‍💻 개발자 / 기여자

| 문서 | 무엇 |
|---|---|
| [아키텍처 (개발자판)](architecture.md) | 모듈 구조 · Redaction Pass 디테일 · Cluster 식별 · RAG 인덱싱 |
| [개발자 가이드](development.md) | 코드 구조 + 테스트 + 새 기능 추가 |

## 📖 모르는 단어가 나오면

[**용어집**](glossary.md) — Vault · Card · Profile · L0~L3 · RAG · apfel · slash command 일관 정의.

[**Config 레퍼런스**](config.md) — `~/.synapse/config.yaml` 키별 의미·default·변경 시 영향.

## 한눈에 보기

| 하고 싶은 일 | 먼저 볼 문서 | 대표 명령 |
| --- | --- | --- |
| 처음 설치하기 (비개발자) | [설치 화면 가이드](for-everyone/installer-walkthrough.md) | (zip 다운로드 → 더블클릭) |
| 처음 설치하기 (개발자) | [Getting Started](getting-started.md) | `synapse-memory doctor` |
| 매일 vault와 로그 갱신 | [사용 시나리오](usage.md) | `/synapse-daily` |
| 과거에 한 생각 찾기 | [무엇을 할 수 있는가](for-everyone/what-you-can-do.md) | `/synapse-recall "TCA"` |
| 내 자료로 질문하기 | [사용 시나리오](usage.md) | `/synapse-ask "..."` |
| 회사 맞춤 이력서 | [무엇을 할 수 있는가](for-everyone/what-you-can-do.md) | `/synapse-resume <회사>` |
| 개인정보 처리 확인 | [Privacy FAQ](for-everyone/privacy-and-cost.md) | (문서) |
