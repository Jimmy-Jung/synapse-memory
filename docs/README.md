# Synapse Memory 문서

Synapse Memory는 Obsidian vault와 Claude Code 활동 로그를 모아, 개인 맥락을 검색하고 답변에 활용하는 로컬 우선 메모리 도구입니다.

처음 읽는다면 아래 순서가 가장 빠릅니다.

1. [Getting Started](getting-started.md): 설치부터 첫 질문까지 따라 하기
2. [사용 시나리오](usage.md): 실제로 매일 어떤 식으로 쓰는지 보기
3. [CLI 명령 레퍼런스](commands.md): 필요한 명령과 옵션 찾기
4. [아키텍처](architecture.md): 데이터 흐름, 보안 모델, 설계 이유 이해하기
5. [개발자 가이드](development.md): 테스트, 구조, 새 기능 추가 방법
6. [Backlog](backlog.md): 알려진 한계와 다음 작업

## 한눈에 보기

| 하고 싶은 일 | 먼저 볼 문서 | 대표 명령 |
| --- | --- | --- |
| 처음 설치하고 실행하기 | [Getting Started](getting-started.md) | `synapse-memory doctor` |
| 매일 vault와 로그 갱신하기 | [사용 시나리오](usage.md) | `synapse-memory daily --profile-facts-only` |
| 과거에 한 생각을 찾기 | [사용 시나리오](usage.md) | `synapse-memory me what-did-i-think "TCA"` |
| 내 자료로 질문하기 | [CLI 명령 레퍼런스](commands.md) | `synapse-memory ask "..."` |
| 회사 맞춤 이력서 만들기 | [사용 시나리오](usage.md) | `synapse-memory me draft-resume danggeun` |
| 개인정보 처리 방식을 확인하기 | [아키텍처](architecture.md) | `synapse-memory redactlist show` |

## 핵심 개념

- **L0 raw**: 원본 로그와 vault mirror입니다. `~/.synapse/private/` 아래에 저장되며 외부 LLM에 보내지 않습니다.
- **Redaction**: 원본에서 이메일, 전화번호, 토큰, 회사명 같은 민감 정보를 마스킹하는 단계입니다.
- **Card**: 프로젝트나 회사를 요약한 Obsidian 문서입니다. 검색과 이력서 생성의 주요 재료입니다.
- **RAG index**: Card를 임베딩해서 자연어로 찾을 수 있게 만든 로컬 벡터 DB입니다.
- **Profile / DecisionPatterns**: 사용자가 검토해서 승인한 성향과 의사결정 패턴입니다. `me decide`가 이 자료를 사용합니다.

## 권장 읽기 방식

바로 써보고 싶다면 [Getting Started](getting-started.md)만 따라 하면 됩니다. 전체 구조가 궁금해졌을 때 [아키텍처](architecture.md)를 읽는 편이 이해가 쉽습니다.
