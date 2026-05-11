# 사용 시나리오

실제 사용 패턴별 예시.

## 시나리오 1. 일일 5분 워크플로

매일 아침 한 줄로 vault 자동 갱신:

```bash
synapse-memory daily --profile-facts-only
```

내부 동작 (모두 incremental):
1. **collect_claude_code** — 어제 추가된 Claude Code 활동 mirror (jsonl 새 줄만)
2. **collect_obsidian** — 변경된 vault .md만 mirror (mtime+hash 비교)
3. **classify** — 새 cluster만 분류 (haiku, ~$0.001/cluster)
4. **generate** — 신규 project/company kind cluster의 Card 자동 생성 (sonnet)
5. **index** — Card 변경분 벡터 DB upsert
6. **update_profile** — 오늘 활동 분석 → MemoryInbox PR

평균 소요 시간:
- 변경 없음 (모두 skip): ~30초
- 새 cluster 1-2개: 2-3분
- 큰 변경 (새 회사 추가 등): 5-10분

비용 예측:
- 일반 일: ~$0.10-0.30 (profile만)
- 새 cluster 발견: +$0.30-1.00

### 5분 검토

`Profile-YYYY-MM-DD.md` 생성됨 (vault `90_System/AI/MemoryInbox/`).

Obsidian에서 열어보고:
- 좋은 ProfileFact → `90_System/AI/Profile.md`로 복사 (진실원본)
- 좋은 DecisionPattern → `DecisionPatterns.md`로 복사
- 불필요한 후보 → 그대로 두거나 삭제

draft Card도 함께 검토 (`20_Reference/Projects/*.md` 중 `status: draft`):
- 내용 정확 → `status: active` 변경
- 정보 보강 필요 → 직접 편집
- 불필요 → 삭제

## 시나리오 2. 회사 맞춤 이력서

당근마켓 지원 준비:

```bash
# 1. (사전) Company Card가 비어있으면 채워두기
synapse-memory card show danggeun --type company
# 또는 vault에서 직접 편집

# 2. 회사 키워드 + 매칭 ProjectCard로 이력서 자동 생성
synapse-memory me draft-resume danggeun --model sonnet
```

출력:
```
✓ 이력서 생성: ~/Library/.../30_Creative/Drafts/Resume - 당근마켓 (2026-05).md
  매칭 ProjectCard (6):
    - dansim-ios
    - 이력서-2026
    - ai-symbiote
    ...
```

생성된 markdown:
- yaml frontmatter (company_id, generated, based_on)
- 한 줄 소개
- 핵심 경험 (회사 키워드 매칭 우선)
- 프로젝트 상세 (역할/문제/접근/영향/기술스택)
- 기술 스택 (회사 키워드 우선)

Obsidian에서 열어서 직접 편집·다듬은 뒤 docx 변환해 지원.

## 시나리오 3. 세컨드 브레인 회상

"X에 대해 내가 뭐라 했었지?"

```bash
synapse-memory me what-did-i-think "TCA 아키텍처"
```

답변 패턴:
- 첫 줄: 핵심 한 문장
- 시점별 정리 (시간순)
- 입장 변화 발견 시 명시 ("처음엔 X, 나중엔 Y")
- 자료에 없는 부분 솔직히 ("장단점 비교 자료 없음")
- 각 주장에 `[card_id]` 인용

```bash
synapse-memory me what-did-i-think "메가스터디에서 한 일"
synapse-memory me what-did-i-think "AI 코딩 도구 사용 경험"
synapse-memory me what-did-i-think "은퇴 자금 계획"
```

## 시나리오 4. 의사결정 코파일럿 (★ 진짜 클론 모드)

"나라면 어떻게 결정할까?"

```bash
synapse-memory me decide "이력서를 sonnet으로 갈지 opus로 갈지"
```

출력에 `(Profile/Patterns 사용 ✓)` 표시되면 클론 모드 동작 — `vault 90_System/AI/Profile.md`와 `DecisionPatterns.md`를 진짜 인용.

답변 형식:
1. **추천**: 한 줄 결정
2. **근거**: Profile/Patterns/Card 인용
3. **대안**: 1-2개 + 트레이드오프
4. **추가 고려**: 사용자 자체 판단할 부분

```bash
synapse-memory me decide "다음 분기 어디에 시간 투자?"
synapse-memory me decide "이 PR을 리뷰할까 그냥 머지할까"
synapse-memory me decide "이력서 보낼 회사 우선순위"
```

**중요**: Profile.md / DecisionPatterns.md가 비어있으면 `(Profile 없음 — 일반 모드)` 메시지. 클론 가치 발생하려면:
1. `synapse-memory me update-profile` 실행 → MemoryInbox PR
2. 사용자가 검토 후 좋은 항목을 `90_System/AI/Profile.md`, `DecisionPatterns.md`에 복사

## 시나리오 5. 자연어 질의 (일반 ask)

가장 자유로운 endpoint. 특정 카테고리 필터 가능:

```bash
# 일반
synapse-memory ask "iOS 개발에서 클린 아키텍처 어떻게 적용했지?"

# 회사만
synapse-memory ask "어떤 회사 다녔지?" --kind company

# 프로젝트만 + retrieval 넓히기
synapse-memory ask "기술 스택 전반 정리" --kind project --top-k 8

# haiku로 비용 절감
synapse-memory ask "메가스터디 정보 요약" --model haiku
```

## 시나리오 6. 진행 중 작업 추가

새 프로젝트 시작했을 때:

```bash
# 빈 Card 생성 (Obsidian 편집기에서 채움)
synapse-memory card new my-new-project "내 새 프로젝트"

# 또는 vault에 직접 노트 N개 작성하고 daily가 자동 인식
# (단 폴더 단위 cluster — 10_Active/<프로젝트명>/ 안에 노트 2개+)
```

새 회사 관심 추가:

```bash
synapse-memory card new acme "Acme Corp" --type company
# 또는 vault 20_Reference/Companies/acme.md 직접 편집
```

## 시나리오 7. NDA 회사 마스킹

특정 회사·프로젝트 키워드를 모든 raw에서 강제 마스킹:

```bash
synapse-memory redactlist add "프로젝트X"
synapse-memory redactlist add "비공개사명"
synapse-memory redactlist show
```

이후 모든 redact / ask / me 호출에서 `[REDACT_*]`로 자동 치환됩니다. Pass 1 단계에서 처리 (priority 200, 모든 다른 카테고리 우선).

## 시나리오 8. 백필 / 재인덱싱

vault에 큰 변경 있어 처음부터:

```bash
# Card 모두 재생성 (--force 덮어쓰기, 비용 큼)
synapse-memory card generate --force --kind all

# RAG 재인덱싱
synapse-memory rag index --rebuild

# Pass 1+2 redaction 전체 백필 (오래 걸림)
synapse-memory redact backfill claude-code --max-bytes-per-file 50000
```

## 비용 예상 (참고)

| 명령 | 모델 | 평균 비용 |
|---|---|---|
| `daily` (변경 없음) | - | ~$0 |
| `daily --profile-facts-only` | sonnet | ~$0.10-0.20 |
| `daily` (풀, 새 cluster 3개) | sonnet | ~$1.0-1.5 |
| `me draft-resume` | sonnet | ~$0.3/이력서 |
| `ask "<짧은 질의>"` | sonnet | ~$0.10 |
| `me decide` | sonnet | ~$0.15 |
| `me what-did-i-think` | sonnet | ~$0.10-0.20 |
| `me update-profile` | sonnet | ~$0.30-0.60 |
| `cluster classify --resume` (5개) | haiku | ~$0.005 |
| `card generate` (1개) | sonnet | ~$0.30 |
| `rag index` | (로컬 임베딩) | $0 |

Pro/Max 구독 안에서 사용량 카운트. API 별도 비용 없음.

## 다음 단계

- [아키텍처](architecture.md)
- [명령 레퍼런스](commands.md)
