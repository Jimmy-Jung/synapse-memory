# Spec 017 — Knowledge Compounding (지식 복리화)

> Karpathy "LLM Wiki" 패턴(https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)을
> synapse-memory에 참고 적용하는 개선 제안.
>
> 저자: JunyoungJung
> 작성일: 2026-06-11
> 상태: PROPOSAL
> 관련: spec 006 (Raw RAG Hybrid), spec 015 (Graph Viz/MOC), spec 003 (Feedback Loop)

---

## 1. 배경과 진단

### 1.1 Karpathy LLM Wiki 패턴 요약

핵심 주장: **query-time RAG는 축적이 없다.** 매 질문마다 LLM이 청크를 다시 찾아
다시 합성한다. 대신 LLM이 **영속적·복리형(persistent, compounding) wiki**를 직접
유지해야 한다.

- 소스 ingest 시 색인만 하지 않고 **기존 페이지를 갱신**하고, **모순을 표시**하고,
  **교차참조를 유지**한다. 소스 1개가 wiki 페이지 10~15개를 건드릴 수 있다.
- **좋은 답변은 다시 wiki에 파일링**한다. 비교·분석·발견이 채팅 히스토리로
  증발하지 않고 지식 베이스에 쌓인다.
- 주기적 **lint**: 모순, 낡은 주장, 고아 페이지, 빠진 개념 페이지를 점검한다.
- `index.md`(콘텐츠 카탈로그) + `log.md`(시간순 기록) 두 특수 파일로 탐색한다.

### 1.2 synapse-memory 현재 상태 진단

| Karpathy 패턴 | synapse-memory 현재 | 판정 |
|---|---|---|
| Raw sources (불변) | L0 mirror (`~/.synapse/private/`) | ✅ 이미 더 강력 (자동 collector + redaction) |
| 엔티티 페이지 | Project/Company Card | ⚠️ 2종뿐, 개념(concept) 페이지 없음 |
| 교차참조 (`[[링크]]`) | Card 간 링크 없음 — 고립된 카드 | ❌ 결손 |
| Ingest 시 기존 페이지 갱신·모순 플래그 | 새 cluster → 새 카드 생성 위주 | ❌ 결손 |
| Query 답변 → wiki 재파일링 | `last_response.json`에서 증발 | ❌ 결손 |
| Lint | 없음 | ❌ 결손 |
| index.md | MOC.md (spec 015) | ⚠️ 부분 |
| log.md | DailyReports | ✅ 거의 동등 |
| 검색 | ChromaDB + BM25 RRF | ✅ 이미 더 강력 |

**결론**: 직접 적용은 부적합 (Karpathy 패턴은 수동 큐레이션·~100 소스 전제).
그러나 "지식 복리" 루프 3개 — **write-back, 교차링크, 기존 카드 갱신** — 는
synapse의 빈 곳을 정확히 찌른다. 이를 도입하면 "검색 도구"에서
"축적되는 세컨드 브레인"으로 성격이 바뀐다.

---

## 2. 개선안 목록 (우선순위순)

| # | 개선안 | 효과 | 구현 비용 | 의존성 |
|---|---|---|---|---|
| P1 | 답변 write-back (InsightCard) | 질문할수록 brain이 똑똑해짐 | 낮음 | 없음 |
| P2 | Card 교차링크 (`related` + `[[링크]]`) | graph view 활성화, 탐색 복리 | 낮음 | 없음 |
| P3 | Ingest 시 기존 카드 갱신 + 모순 플래그 | 카드 증식 대신 synthesis | 중간 | P2 |
| P4 | `lint` 명령 (모순·낡음·고아 점검) | wiki 건강 유지 | 중간 | P2 |
| P5 | ConceptCard 타입 | 프로젝트 횡단 주제 페이지 | 중간 | P1, P2 |
| P6 | index.md 카탈로그 + log prefix 통일 | LLM의 저비용 탐색 경로 | 낮음 | 없음 |

---

## 3. 폴더 구조 변화

### 3.1 Vault (L2)

```
<vault>/
├── 00_Inbox/
├── 10_Active/<회사>/<프로젝트>/
├── 20_Reference/
│   ├── Projects/                  # ProjectCard (기존)
│   ├── Companies/                 # CompanyCard (기존)
│   ├── Concepts/                  # 🆕 P5: ConceptCard — 주제·개념 페이지
│   │   ├── tca.md
│   │   └── 이직-전략.md
│   └── Insights/                  # 🆕 P1: InsightCard — 저장된 답변
│       └── 2026/06/
│           └── 2026-06-11-tca-도입-이유.md
├── 30_Creative/Drafts/
└── 90_System/AI/
    ├── Profile.md
    ├── DecisionPatterns.md
    ├── MemoryInbox/<year>/<month>/
    ├── DailyReports/<year>/<month>/  # 🆕 P6: grep-friendly prefix 통일
    ├── LintReports/<year>/<month>/   # 🆕 P4: lint 결과
    ├── MOC.md                        # spec 015 (graph 진입점)
    └── index.md                      # 🆕 P6: 카드 카탈로그 (한 줄 요약)
```

### 3.2 코드 (src/synapse_memory/)

```
src/synapse_memory/
├── cards/
│   ├── project.py                 # 기존 + related 필드 추가 (P2)
│   ├── company.py                 # 기존 + related 필드 추가 (P2)
│   ├── concept.py                 # 🆕 P5
│   ├── insight.py                 # 🆕 P1
│   └── linking.py                 # 🆕 P2: 교차링크 계산·주입
├── endpoints/
│   ├── ask.py                     # 수정: --save 지원 (P1)
│   ├── persona.py                 # 수정: decide/recall --save (P1)
│   └── lint.py                    # 🆕 P4
├── wiki/                          # 🆕 복리 루프 공통 모듈
│   ├── __init__.py
│   ├── merge.py                   # P3: 기존 카드 갱신 판단·병합
│   ├── contradiction.py           # P3/P4: 모순 감지
│   └── catalog.py                 # P6: index.md 생성
└── daily.py                       # 수정: link / lint stage 추가
```

---

## 4. 아키텍처

### 4.1 현재 (단방향 — 지식이 증발)

```
L0 raw ──classify──▶ cluster ──generate──▶ Card (신규 생성만)
                                              │
                                            index
                                              ▼
사용자 질문 ──ask──▶ RAG retrieve ──▶ Claude ──▶ 답변 ──▶ ❌ 증발
                                                          (last_response.json)
```

### 4.2 제안 (복리 루프 — 지식이 돌아온다)

```
L0 raw ──classify──▶ cluster ──┬─ 신규 ──generate──▶ 새 Card
                               │                        │
                               └─ 기존과 유사 ──merge──▶ 기존 Card 갱신   ◀ P3
                                  (모순 시 ⚠️ 플래그)        │
                                                            ▼
                                                     link (related 주입)  ◀ P2
                                                            │
                                                          index
                                                            ▼
사용자 질문 ──ask──▶ RAG retrieve ──▶ Claude ──▶ 답변
                                                  │
                                          가치 판단 / --save                ◀ P1
                                                  │
                                                  ▼
                                       InsightCard (20_Reference/Insights/)
                                                  │
                                            index (재인덱싱)
                                                  │
                                                  ▼
                                       다음 질문의 retrieve 대상 ✅ 복리

주기적: lint ──▶ 모순·낡음·고아·빠진 개념 ──▶ LintReport + 수정 제안  ◀ P4
```

핵심 불변식 (기존 보안 원칙 유지):
- InsightCard·ConceptCard도 vault(L2) 저장 전 `redact_full()` 통과.
- 자동 생성물은 전부 `status: draft`, `confidence ≤ 0.7`. 사용자 검토 후 승격.
- 기존 카드 **자동 덮어쓰기 금지** — P3의 merge는 섹션 append + 플래그 방식
  (Profile 승인 모델과 동일 철학).

---

## 5. 개선안 상세

---

### P1 — 답변 write-back (InsightCard)

#### 문제
`ask/decide/recall` 결과가 `~/.synapse/private/last_response.json`에 저장될 뿐
vault로 돌아오지 않는다. 같은 질문을 두 번 하면 두 번 다 풀 RAG + LLM 비용을
치르고, 첫 답변에서 발견한 연결은 사라진다.

#### 설계
- `AskResult`를 `InsightCard`로 변환해 `20_Reference/Insights/<yyyy>/<mm>/`에 저장.
- 저장 트리거 2가지:
  1. **명시적**: `synapse-memory ask "질문" --save` / `/sm:ask "질문" --save`
  2. **제안형**: 답변 출력 후 "이 답변을 저장할까요?" (slash command에서
     AskUserQuestion으로 1회 확인 — 자동 저장은 카드 오염 위험)
- InsightCard는 인용한 카드들을 `related`로 자동 연결 → P2의 그래프에 합류.
- `index` stage가 Insights/ 도 인덱싱 → 다음 질문의 retrieve 대상.

#### 데이터 모델 — `cards/insight.py`

```python
"""Insight Card — ask/decide/recall 답변의 영속화.

좋은 답변은 채팅에서 증발하지 않고 vault에 쌓인다 (knowledge compounding).

저장 위치: ``<vault>/20_Reference/Insights/<yyyy>/<mm>/<insight_id>.md``

저자: JunyoungJung
작성일: 2026-06-11
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from synapse_memory.cards.project import slugify
from synapse_memory.collectors.obsidian.mirror import get_vault_path
from synapse_memory.config import get_config


@dataclass
class InsightCard:
    """저장된 답변 1건. ask/decide/recall 공통."""

    insight_id: str                  # "2026-06-11-tca-도입-이유"
    question: str                    # 원 질문
    command: str                     # "ask" | "decide" | "recall"
    created: str                     # ISO 8601
    related: list[str] = field(default_factory=list)  # 인용한 card_id들
    keywords: list[str] = field(default_factory=list)
    status: str = "draft"            # draft → 사용자 검토 후 active
    confidence: float = 0.7
    body: str = ""                   # 답변 본문 (markdown)

    @property
    def filename(self) -> str:
        return f"{self.insight_id}.md"


def new_insight_id(question: str, *, now: datetime | None = None) -> str:
    """질문 → 날짜 prefix가 붙은 file-safe ID."""
    ts = now or datetime.now()
    return f"{ts:%Y-%m-%d}-{slugify(question)[:40]}"


def insights_dir(created: str, *, vault_path: Path | None = None) -> Path:
    """년/월 분리 저장 (spec 011 YearMonth Folders 관례 따름)."""
    vault = (vault_path or get_vault_path()).expanduser().resolve()
    root = vault / get_config().vault_folders.reference.insights
    yyyy, mm = created[:4], created[5:7]
    return root / yyyy / mm
```

frontmatter 직렬화는 `project.py`의 `serialize_project_card` 패턴 그대로
(yaml frontmatter + body, `tags: [node/insight]`).

#### 저장 결과 예시 — `20_Reference/Insights/2026/06/2026-06-11-tca-도입-이유.md`

```markdown
---
insight_id: 2026-06-11-tca-도입-이유
question: TCA를 왜 도입했지?
command: ask
created: 2026-06-11T14:32:00+09:00
related: [dansim-ios, webview-refactor]
keywords: [TCA, 아키텍처, 의사결정]
status: draft
confidence: 0.7
tags: [node/insight]
---

# TCA를 왜 도입했지?

[[dansim-ios]] 프로젝트에서 spaghetti code와 테스트 불가능한 구조를
해결하기 위해 도입했다. 모듈화·의존성 주입이 핵심 동기였고,
테스트 커버리지가 10% → 85%로 개선됐다 [dansim-ios].

[[webview-refactor]]에서도 동일 패턴을 재사용했다 [webview-refactor].
```

#### `endpoints/ask.py` 수정 (발췌)

```python
def ask(
    query: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    model: str | None = DEFAULT_MODEL,
    store: VectorStore | None = None,
    ai_env: AIEnvironment | None = None,
    where: dict[str, object] | None = None,
    hybrid: bool = False,
    save: bool = False,                      # 🆕
) -> AskResult:
    ...
    _record_last_answer(query, sources)
    result = AskResult(query=query, answer=answer, sources=sources)
    if save:
        result.saved_path = save_insight_from_ask(result)   # 🆕
    return result


def save_insight_from_ask(result: AskResult) -> Path:
    """AskResult → InsightCard 저장 + 즉시 재인덱싱.

    vault에 닿는 텍스트이므로 redact_full() 필수 통과.
    """
    from synapse_memory.cards.insight import (
        InsightCard, new_insight_id, save_insight_card,
    )
    from synapse_memory.rag.indexer import index_insight_card
    from synapse_memory.redaction import redact_full

    created = datetime.now().isoformat(timespec="seconds")
    card = InsightCard(
        insight_id=new_insight_id(result.query),
        question=result.query,
        command="ask",
        created=created,
        related=[s.card_id for s in result.sources],
        body=redact_full(result.answer).redacted,
    )
    path = save_insight_card(card)
    index_insight_card(card)   # 단건 upsert — 다음 질문부터 retrieve 대상
    return path
```

`indexer.py`에는 `PREFIX_INSIGHT = "card_insight:"` 와 단건 upsert 함수 추가:

```python
PREFIX_INSIGHT = "card_insight:"

def index_insight_card(
    card: InsightCard, *, store: VectorStore | None = None
) -> None:
    store = store or open_vector_store()
    text = insight_card_to_text(card)        # project_card_to_text 패턴
    vec = embed_texts([text])[0]
    store.upsert([
        VectorRecord(
            id=f"{PREFIX_INSIGHT}{card.insight_id}",
            document=text,
            embedding=vec,
            metadata={
                "source_kind": "card_insight",
                "card_id": card.insight_id,
                "display_name": card.question,
                "created": card.created,
                "confidence": card.confidence,
            },
        )
    ])
```

#### 플로우

```
/sm:ask "TCA를 왜 도입했지?" --save
  ↓
ask() → RAG retrieve → Claude 답변
  ↓
redact_full(answer)
  ↓
InsightCard 생성 (related = 인용 card_id)
  ↓
20_Reference/Insights/2026/06/...md 저장
  ↓
index_insight_card() → ChromaDB upsert
  ↓
다음 질문 "아키텍처 의사결정 기준이 뭐였지?"
  → 이 InsightCard가 retrieve됨 → 합성 비용↓, 일관성↑   ✅ 복리
```

---

### P2 — Card 교차링크

#### 문제
카드끼리 서로를 모른다. `related` 메타데이터도, 본문 `[[위키링크]]`도 없어
Obsidian graph view(spec 015)에서 카드가 전부 고아 노드로 뜬다.

#### 설계
- 모든 카드 타입에 `related: list[str]` frontmatter 필드 추가
  (ProjectCard/CompanyCard는 기존 파서에 1필드 추가 — 하위호환:
  필드 없으면 빈 리스트).
- `cards/linking.py`: 카드 텍스트를 쿼리 삼아 기존 인덱스를 검색,
  유사도 상위 카드를 `related` 후보로 산출. LLM 없이 임베딩만으로 동작
  (비용 0에 가까움).
- `generate` stage 직후 새 `link` stage에서 신규·갱신 카드에 주입.
- 본문 `[[링크]]`는 **본문을 변형하지 않고** 카드 하단 `## 관련` 섹션에만 추가
  (사용자가 편집한 본문 보존).

#### `cards/linking.py`

```python
"""Card 교차링크 — 임베딩 유사도 기반 related 후보 산출.

LLM 호출 없음. 기존 ChromaDB 인덱스 재사용 → 비용 ~0.

저자: JunyoungJung
작성일: 2026-06-11
"""

from __future__ import annotations

from dataclasses import dataclass

from synapse_memory.rag.embeddings import embed_query
from synapse_memory.rag.vector_store import VectorStore, open_vector_store

RELATED_TOP_K = 5
RELATED_MAX_DISTANCE = 0.45   # 이보다 멀면 관련 없음으로 간주


@dataclass(frozen=True)
class RelatedCandidate:
    card_id: str
    source_kind: str
    display_name: str
    distance: float


def find_related(
    card_text: str,
    *,
    self_id: str,
    store: VectorStore | None = None,
    top_k: int = RELATED_TOP_K,
) -> list[RelatedCandidate]:
    """카드 텍스트 → 유사 카드 후보 (자기 자신 제외, 거리 임계 적용)."""
    store = store or open_vector_store()
    vec = embed_query(card_text)
    results = store.query(vec, top_k=top_k + 1)  # 자기 자신 포함 가능성 +1
    out: list[RelatedCandidate] = []
    for rec, dist in results:
        meta = rec.metadata or {}
        cid = str(meta.get("card_id") or rec.id)
        if cid == self_id or dist > RELATED_MAX_DISTANCE:
            continue
        out.append(
            RelatedCandidate(
                card_id=cid,
                source_kind=str(meta.get("source_kind", "unknown")),
                display_name=str(meta.get("display_name", cid)),
                distance=dist,
            )
        )
    return out[:top_k]


def render_related_section(candidates: list[RelatedCandidate]) -> str:
    """카드 본문 하단에 append할 '## 관련' 섹션. 본문 변형 없음."""
    if not candidates:
        return ""
    lines = ["", "## 관련", ""]
    lines += [
        f"- [[{c.card_id}]] — {c.display_name}"
        for c in candidates
    ]
    return "\n".join(lines)
```

#### `daily.py` stage 추가

```python
DAILY_STAGES = (
    # ... 기존 collect_* ...
    DailyStage("classify", "신규 cluster 분류"),
    DailyStage("generate", "Project/Company Card 생성", ("classify",)),
    DailyStage("link", "Card 교차링크 (related 주입)", ("generate",)),   # 🆕 P2
    DailyStage("index", "Card RAG index", ("link",)),                    # 의존 변경
    DailyStage("lint", "Wiki 건강 점검 (주 1회)", ("index",)),           # 🆕 P4
    DailyStage(
        "update_profile",
        "ProfileFact/DecisionPattern 후보 추출",
        ("collect_claude_code", "classify", "generate"),
    ),
    DailyStage("report", "DailyReport 작성"),
)
```

#### 결과 예시 — ProjectCard frontmatter/본문 변화

```markdown
---
project_id: dansim-ios
display_name: Dansim iOS 리팩터링
...
related: [webview-refactor, tca, 2026-06-11-tca-도입-이유]   # 🆕
tags: [node/card]
---

# Dansim iOS 리팩터링
...기존 본문 그대로...

## 관련

- [[webview-refactor]] — WebView 리팩터링
- [[tca]] — TCA (개념)
- [[2026-06-11-tca-도입-이유]] — TCA를 왜 도입했지?
```

→ Obsidian graph view에서 즉시 프로젝트-개념-인사이트 군집이 보인다.

---

### P3 — Ingest 시 기존 카드 갱신 + 모순 플래그

#### 문제
`generate` stage는 새 cluster마다 새 카드를 만든다. 같은 프로젝트의 새 자료가
들어와도 기존 카드는 갱신되지 않고 비슷한 카드만 늘어난다. Karpathy 패턴의 핵심
"ingest가 기존 페이지를 revise하고 모순을 표시한다"가 없다.

#### 설계
- `wiki/merge.py`: 새 cluster 요약을 쿼리 삼아 기존 카드 검색 →
  거리 임계(`MERGE_DISTANCE = 0.25`) 이내면 **신규 생성 대신 갱신 경로**.
- 갱신은 **append-only**: 기존 본문 보존, `## 업데이트 (YYYY-MM-DD)` 섹션 추가.
  모순 감지 시 `## ⚠️ 모순 (YYYY-MM-DD)` 섹션 추가.
- 모순 판단은 LLM 1콜 (apfel 우선, 실패 시 Claude haiku) — 기존 카드 요지 vs
  새 자료 요지 비교.
- 자동 덮어쓰기 절대 금지. 사용자가 Obsidian에서 모순 섹션 보고 본문 정리 →
  `last_reviewed` 갱신.

#### `wiki/merge.py`

```python
"""신규 cluster → 기존 카드 갱신 판단·병합.

원칙: 자동 덮어쓰기 금지. append-only 섹션 + 모순 플래그.
사용자가 최종 정리한다 (MemoryInbox 승인 모델과 동일 철학).

저자: JunyoungJung
작성일: 2026-06-11
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from synapse_memory.cards.project import (
    ProjectCard,
    load_project_card,
    save_project_card,
)
from synapse_memory.rag.embeddings import embed_query
from synapse_memory.rag.vector_store import VectorStore, open_vector_store
from synapse_memory.wiki.contradiction import detect_contradiction

MERGE_DISTANCE = 0.25   # 이보다 가까우면 "같은 주제" — 갱신 경로


@dataclass(frozen=True)
class MergeDecision:
    action: str               # "create" | "update"
    target_card_id: str = ""  # action=update일 때


def decide_merge(
    cluster_summary: str,
    *,
    store: VectorStore | None = None,
) -> MergeDecision:
    """새 cluster 요약 → 신규 생성 vs 기존 카드 갱신 판단."""
    store = store or open_vector_store()
    vec = embed_query(cluster_summary)
    results = store.query(
        vec, top_k=1, where={"source_kind": "card_project"}
    )
    if results:
        rec, dist = results[0]
        if dist <= MERGE_DISTANCE:
            card_id = str((rec.metadata or {}).get("card_id") or rec.id)
            return MergeDecision(action="update", target_card_id=card_id)
    return MergeDecision(action="create")


def append_update_section(
    card_id: str,
    new_summary: str,
    *,
    today: date | None = None,
) -> ProjectCard:
    """기존 카드에 업데이트 섹션 append. 모순 시 ⚠️ 섹션 추가."""
    card = load_project_card(card_id)
    d = (today or date.today()).isoformat()

    verdict = detect_contradiction(card.body, new_summary)
    if verdict.contradicts:
        section = (
            f"\n\n## ⚠️ 모순 ({d})\n\n"
            f"기존 주장과 충돌:\n"
            f"> {verdict.existing_claim}\n\n"
            f"새 자료:\n"
            f"> {verdict.new_claim}\n\n"
            f"검토 후 본문을 정리하고 이 섹션을 삭제하세요."
        )
    else:
        section = f"\n\n## 업데이트 ({d})\n\n{new_summary}"

    card.body = card.body.rstrip() + section
    save_project_card(card)
    return card
```

#### `wiki/contradiction.py` (발췌)

```python
"""기존 카드 vs 새 자료 모순 감지 — 로컬 LLM(apfel) 우선."""

from __future__ import annotations

import json
from dataclasses import dataclass

from synapse_memory.llm import ai_api

_SYSTEM = """두 텍스트가 사실 차원에서 모순되는지 판단하라.
출력은 JSON만: {"contradicts": bool, "existing_claim": str, "new_claim": str}
모순 없으면 {"contradicts": false, "existing_claim": "", "new_claim": ""}."""


@dataclass(frozen=True)
class ContradictionVerdict:
    contradicts: bool
    existing_claim: str = ""
    new_claim: str = ""


def detect_contradiction(existing: str, new: str) -> ContradictionVerdict:
    prompt = f"# 기존\n{existing[:2000]}\n\n# 새 자료\n{new[:2000]}"
    raw = ai_api.complete(prompt, system=_SYSTEM, model="haiku", timeout=60)
    try:
        d = json.loads(raw)
        return ContradictionVerdict(
            contradicts=bool(d.get("contradicts")),
            existing_claim=str(d.get("existing_claim", "")),
            new_claim=str(d.get("new_claim", "")),
        )
    except (json.JSONDecodeError, TypeError):
        return ContradictionVerdict(contradicts=False)
```

#### generate stage 흐름 변화

```
현재:
  new cluster ──▶ generate ──▶ 새 ProjectCard

제안:
  new cluster ──▶ decide_merge(cluster_summary)
                    ├─ "create"  ──▶ 새 ProjectCard (기존 경로)
                    └─ "update"  ──▶ append_update_section(card_id, summary)
                                       ├─ 모순 없음: "## 업데이트 (날짜)" append
                                       └─ 모순 감지: "## ⚠️ 모순 (날짜)" append
                                                     + DailyReport에 모순 목록 표기
```

#### 결과 예시 — 모순이 감지된 카드

```markdown
# Dansim iOS 리팩터링

## 영향
테스트 커버리지 10% → 85%, 배포 사이클 2주 → 3일

## ⚠️ 모순 (2026-06-11)

기존 주장과 충돌:
> 테스트 커버리지 10% → 85%

새 자료:
> 2026-06 회고 노트: "커버리지 측정 방식 변경으로 실제는 72%"

검토 후 본문을 정리하고 이 섹션을 삭제하세요.
```

---

### P4 — `lint` 명령 (wiki 건강 점검)

#### 문제
카드가 쌓일수록 모순·낡은 주장·고아 카드가 누적되지만 점검 장치가 없다.

#### 설계
- `synapse-memory lint` / `/sm:lint` 신설. daily pipeline에는 주 1회 stage로
  편입 (`lint` stage — 마지막 실행일 기록, 7일 미만이면 skipped).
- 4가지 점검:

| 점검 | 방식 | 비용 |
|---|---|---|
| 고아 카드 (inbound 링크 0) | `related` 그래프 역방향 계산 | 0 (순수 파이썬) |
| 낡은 카드 (`last_reviewed` > 180일 & status=active) | frontmatter 스캔 | 0 |
| 모순 (미해결 `## ⚠️ 모순` 섹션) | 본문 검색 | 0 |
| 빠진 개념 (여러 카드가 언급하나 페이지 없는 키워드) | keywords 빈도 집계 | 0 |

- LLM은 선택적 심화 모드(`--deep`)에서만: 카드 쌍 샘플링해 의미 모순 탐지.
- 결과는 `90_System/AI/LintReports/<yyyy>/<mm>/`에 저장 + 요약을 DailyReport에.

#### `endpoints/lint.py`

```python
"""wiki lint — 모순·낡음·고아·빠진 개념 점검.

기본 모드는 LLM 0콜 (frontmatter/그래프 연산만). --deep만 LLM 사용.

저자: JunyoungJung
작성일: 2026-06-11
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta

from synapse_memory.cards.company import list_company_cards
from synapse_memory.cards.project import list_project_cards

STALE_DAYS = 180
MISSING_CONCEPT_MIN_MENTIONS = 3


@dataclass
class LintReport:
    orphans: list[str] = field(default_factory=list)        # inbound 0
    stale: list[str] = field(default_factory=list)          # 오래 미검토
    contradictions: list[str] = field(default_factory=list) # ⚠️ 미해결
    missing_concepts: list[tuple[str, int]] = field(default_factory=list)

    @property
    def healthy(self) -> bool:
        return not (
            self.orphans
            or self.stale
            or self.contradictions
            or self.missing_concepts
        )


def lint_vault() -> LintReport:
    projects = list_project_cards()
    companies = list_company_cards()
    report = LintReport()

    # 1) 고아: 누군가의 related에 한 번도 등장하지 않는 카드
    all_ids = {c.project_id for c in projects} | {
        c.company_id for c in companies
    }
    linked: set[str] = set()
    for c in projects:
        linked.update(getattr(c, "related", []))
    for c in companies:
        linked.update(getattr(c, "related", []))
    report.orphans = sorted(all_ids - linked)

    # 2) 낡음: active인데 last_reviewed가 STALE_DAYS 초과
    cutoff = (date.today() - timedelta(days=STALE_DAYS)).isoformat()
    report.stale = sorted(
        c.project_id
        for c in projects
        if c.status == "active"
        and c.last_reviewed
        and c.last_reviewed[:10] < cutoff
    )

    # 3) 모순: 미해결 ⚠️ 섹션
    report.contradictions = sorted(
        c.project_id for c in projects if "## ⚠️ 모순" in c.body
    )

    # 4) 빠진 개념: keywords 빈도 상위인데 ConceptCard 없음
    counter: Counter[str] = Counter()
    for c in projects:
        counter.update(k.lower() for k in c.keywords)
    existing_concepts = _existing_concept_ids()
    report.missing_concepts = [
        (kw, n)
        for kw, n in counter.most_common(20)
        if n >= MISSING_CONCEPT_MIN_MENTIONS
        and kw not in existing_concepts
    ]
    return report


def _existing_concept_ids() -> set[str]:
    try:
        from synapse_memory.cards.concept import list_concept_cards
        return {c.concept_id for c in list_concept_cards()}
    except ImportError:   # P5 미도입 시에도 lint는 동작
        return set()
```

#### 출력 예시 — `/sm:lint`

```
Wiki Lint — 2026-06-11

⚠️ 모순 미해결 (1)
  - dansim-ios: "## ⚠️ 모순 (2026-06-11)" — 커버리지 85% vs 72%

🕸️ 고아 카드 (2)
  - legacy-batch-tool (inbound 링크 0 — archive 후보?)
  - examplecorp (회사 카드인데 어떤 프로젝트와도 연결 안 됨)

⏳ 낡은 카드 (1)
  - webview-refactor (last_reviewed: 2025-11-02, 221일 경과)

💡 빠진 개념 페이지 (2)
  - "모듈화" — 카드 5곳에서 언급, ConceptCard 없음
  - "ci-cd" — 카드 3곳에서 언급

→ LintReports/2026/06/2026-06-11.md 저장됨
→ 제안: /sm:lint --fix 로 개념 페이지 초안 생성
```

---

### P5 — ConceptCard (개념·주제 페이지)

#### 문제
Project/Company 2종뿐이라 "TCA", "이직 전략", "모듈화"처럼 프로젝트를 횡단하는
주제의 synthesis가 쌓일 자리가 없다. Karpathy 패턴의 entity/concept 페이지 중
concept 축이 비어 있다.

#### 설계
- `cards/concept.py` — Project/Company와 동일한 frontmatter+body 관례.
- 생성 경로 2가지:
  1. lint의 "빠진 개념" 후보 → `/sm:lint --fix`가 초안 생성 (관련 카드들
     retrieve → Claude로 synthesis → `status: draft`)
  2. 수동: `synapse-memory concept new "TCA"`
- ConceptCard의 가치는 **횡단 synthesis**: 어떤 프로젝트들이 이 개념을 어떻게
  썼고 결과가 무엇이었는지 한 페이지로.

#### 데이터 모델 — `cards/concept.py` (발췌)

```python
@dataclass
class ConceptCard:
    """프로젝트 횡단 개념·주제 페이지.

    저장 위치: ``<vault>/20_Reference/Concepts/<concept_id>.md``
    """

    concept_id: str                   # "tca", "이직-전략"
    display_name: str                 # "TCA (The Composable Architecture)"
    status: str = "draft"
    related: list[str] = field(default_factory=list)   # 이 개념을 쓰는 카드들
    keywords: list[str] = field(default_factory=list)
    confidence: float = 0.7
    created: str = ""
    last_reviewed: str = ""
    body: str = ""
```

#### 생성 결과 예시 — `20_Reference/Concepts/tca.md`

```markdown
---
concept_id: tca
display_name: TCA (The Composable Architecture)
status: draft
related: [dansim-ios, webview-refactor, 2026-06-11-tca-도입-이유]
keywords: [아키텍처, 상태관리, swift]
confidence: 0.7
tags: [node/concept]
---

# TCA (The Composable Architecture)

## 내 경험 요약
[[dansim-ios]]에서 처음 도입 (2025-10). 동기는 테스트 불가능한
spaghetti 구조 해소. 커버리지 10% → 85% [dansim-ios].
[[webview-refactor]]에서 패턴 재사용 — 도입 비용이 두 번째부터 크게 감소.

## 판단 기준 (언제 쓰나)
- 상태 복잡도 높고 테스트가 병목일 때 도입 가치 있음
- 소규모 화면 단위에는 과함 — [[2026-06-11-tca-도입-이유]] 참고
```

---

### P6 — index.md 카탈로그 + log prefix 통일

#### 문제
- LLM(slash command 세션)이 vault 전체 상황을 파악하려면 RAG를 돌려야 한다.
  Karpathy의 index.md처럼 "한 번 읽으면 전체가 보이는" 저비용 경로가 없다.
- DailyReports는 존재하나 엔트리 형식이 비정형이라 `grep` 파싱이 어렵다.

#### 설계
- `wiki/catalog.py`: 카드 전체 → `90_System/AI/index.md` 생성.
  `index` stage 끝에 자동 재생성 (덮어쓰기 — LLM 소유 파일, 사람 편집 비대상).
- DailyReports 엔트리 머리를 `## [YYYY-MM-DD] <stage> | <요약>` 형식으로 통일.
  → `grep "^## \[" report.md | tail -5` 로 최근 활동 파싱 가능.
- `/sm:*` slash command들이 RAG 전에 index.md를 먼저 읽도록 스킬 문서에 명시
  (top_k 검색으로 못 찾는 "전체 조망" 질문에 효과적).

#### `wiki/catalog.py` (발췌)

```python
INDEX_HEADER = """# Index — 자동 생성 (직접 편집 금지)

> `index` stage가 매번 재생성. 카드 전체 카탈로그.
"""


def render_index() -> str:
    projects = list_project_cards()
    companies = list_company_cards()
    lines = [INDEX_HEADER, "## Projects", ""]
    for c in projects:
        period = c.period_start or "?"
        lines.append(
            f"- [[{c.project_id}]] — {c.display_name}"
            f" ({c.status}, {period}, related {len(getattr(c, 'related', []))})"
        )
    lines += ["", "## Companies", ""]
    for c in companies:
        lines.append(f"- [[{c.company_id}]] — {c.display_name} ({c.status})")
    # Concepts / Insights 섹션도 동일 패턴 (P1/P5 도입 시)
    return "\n".join(lines) + "\n"
```

#### index.md 결과 예시

```markdown
# Index — 자동 생성 (직접 편집 금지)

## Projects

- [[dansim-ios]] — Dansim iOS 리팩터링 (active, 2025-10, related 3)
- [[webview-refactor]] — WebView 리팩터링 (active, 2025-12, related 2)

## Companies

- [[examplecorp]] — ExampleCorp (draft)

## Concepts

- [[tca]] — TCA (draft, related 3)

## Insights

- [[2026-06-11-tca-도입-이유]] — "TCA를 왜 도입했지?" (ask, 2026-06-11)
```

---

## 6. 설정 추가 (config.py)

```python
@dataclass
class VaultReferenceFoldersConfig:
    root: str = "20_Reference"
    projects: str = "20_Reference/Projects"
    companies: str = "20_Reference/Companies"
    concepts: str = "20_Reference/Concepts"     # 🆕 P5
    insights: str = "20_Reference/Insights"     # 🆕 P1


@dataclass
class WikiConfig:                                # 🆕 신규 섹션
    """knowledge compounding 동작 설정."""

    insight_save_mode: str = "ask"     # "ask"(제안형) | "flag"(--save만) | "off"
    related_top_k: int = 5
    related_max_distance: float = 0.45
    merge_distance: float = 0.25
    lint_interval_days: int = 7
    stale_days: int = 180
```

`VaultSystemAiFoldersConfig`에는 `lint_reports: str = "90_System/AI/LintReports"`,
`index: str = "90_System/AI/index.md"` 추가.

---

## 7. 도입 순서 (마일스톤)

```
M1 (P1 + P6) — 복리 루프 최소 완성                    예상 규모: 소
  ├─ cards/insight.py + indexer PREFIX_INSIGHT
  ├─ ask/decide/recall --save
  ├─ wiki/catalog.py + index stage 연동
  └─ DailyReports prefix 통일
  ✓ 검증: ask --save 후 같은 주제 재질문 시 InsightCard가 인용되는가

M2 (P2) — 그래프 활성화                                예상 규모: 소
  ├─ ProjectCard/CompanyCard related 필드 (하위호환)
  ├─ cards/linking.py
  └─ daily link stage
  ✓ 검증: Obsidian graph view에서 카드 군집 형성

M3 (P3) — ingest 갱신 경로                             예상 규모: 중
  ├─ wiki/merge.py + contradiction.py
  └─ generate stage 분기 (create vs update)
  ✓ 검증: 기존 프로젝트 새 노트 추가 → 새 카드가 아니라 업데이트 섹션

M4 (P4 + P5) — lint + 개념 페이지                      예상 규모: 중
  ├─ endpoints/lint.py + LintReports
  ├─ cards/concept.py + lint --fix 초안 생성
  └─ daily lint stage (주 1회)
  ✓ 검증: 의도적 모순 주입 → lint가 검출
```

각 마일스톤 독립 배포 가능. M1만으로도 "축적되는 brain" 효과 시작.

---

## 8. 비용 영향

| 기능 | 추가 LLM 호출 | 비고 |
|---|---|---|
| P1 write-back | 0 (저장만) | 임베딩 1건 (로컬) |
| P2 linking | 0 | 임베딩 재사용 |
| P3 merge 판단 | 0 | 임베딩만 |
| P3 모순 감지 | 갱신 카드당 1콜 (haiku/apfel) | 신규 cluster 있을 때만 |
| P4 lint 기본 | 0 | 순수 파이썬 |
| P4 lint --deep | 샘플당 1콜 | opt-in |
| P5 concept 초안 | 개념당 1콜 (sonnet) | lint --fix 명시 실행 시만 |
| P6 index.md | 0 | 직렬화만 |

오히려 장기 절감: InsightCard 재사용으로 반복 질문의 retrieve 품질↑,
합성 토큰↓.

---

## 9. 비채택 결정 (Karpathy 패턴 중 적용 안 하는 것)

| 항목 | 사유 |
|---|---|
| 수동 ingest (소스 1개씩 사람이 투입) | synapse 정체성은 자동 수집. collector 유지 |
| index.md만으로 검색 대체 | 이미 hybrid RAG 보유. index.md는 보조 경로로만 |
| qmd 도입 | ChromaDB+BM25 RRF가 동등 이상. 중복 |
| LLM의 자유 wiki 편집 (사람 페이지 직접 revise) | redaction·승인 모델과 충돌. append-only + 플래그로 제한 |
| Marp/슬라이드 출력 | 범위 밖. 필요 시 별도 spec |
