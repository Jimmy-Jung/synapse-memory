# Quickstart Results — Feedback Loop

Date: 2026-05-12
Mode: isolated smoke with temp SYNAPSE_L0_ROOT and temp SYNAPSE_OBSIDIAN_VAULT
Temp root: /tmp/synapse-feedback-smoke.ByBUbw

```text
$ synapse-memory doctor
Synapse Memory 환경 진단
============================================
✓ apfel 설치: /opt/homebrew/bin/apfel
  버전: apfel v1.3.3
✓ Apple Silicon (arm64)
✓ macOS 26.3.1 (Tahoe+)
✓ L0 루트: /private/tmp/synapse-feedback-smoke.ByBUbw/private (0700)
✓ Claude Code CLI: /Users/jimmy/.local/bin/claude [2.1.139 (Claude Code)] (model=sonnet)
============================================
✓ 준비 완료

$ synapse-memory rag index --rebuild
인덱싱 시작 (rebuild=True)
  [project] 1개 임베딩 중...

인덱싱 완료: project=1 company=0 bytes=505
총 벡터: 1

$ SYNAPSE_FROM_AGENT=1 synapse-memory ask "클린 아키텍처에서 내가 반복해서 말한 기준은?"
질문: 클린 아키텍처에서 내가 반복해서 말한 기준은?

**Domain, Data, Presentation 경계 분리 + 외부 SDK 의존성을 안쪽 계층으로 흘리지 않는 것**입니다. [dansim-ios]

추가로, ViewModel 책임을 줄이고 유스케이스 단위로 테스트 가능한 구조 유지도 반복 적용한 기준입니다. [dansim-ios]

============================================================
출처 (1):
  [0.442] card_project   dansim-ios — 단심 iOS

$ test -f "$SYNAPSE_L0_ROOT/last_response.json" && python3 -m json.tool "$SYNAPSE_L0_ROOT/last_response.json"
{
    "answer_id": "20260512T040232896225Z-d6faf31e",
    "citations": [
        {
            "display_name": "\ub2e8\uc2ec iOS",
            "source_kind": "card_project",
            "target_kind": "card",
            "target_ref": "dansim-ios"
        }
    ],
    "command": "ask",
    "query": "\ud074\ub9b0 \uc544\ud0a4\ud14d\ucc98\uc5d0\uc11c \ub0b4\uac00 \ubc18\ubcf5\ud574\uc11c \ub9d0\ud55c \uae30\uc900\uc740?",
    "session_id": null,
    "ts": "2026-05-12T04:02:32.896225Z"
}

$ synapse-memory feedback last --reject "관련 없음 - smoke test"
✓ Recorded reject for last answer 20260512T040232896225Z-d6faf31e (targets=1, weight=-0.30)
  → next index will apply updated feedback_score: dansim-ios

$ tail -1 "$SYNAPSE_L0_ROOT/feedback.jsonl" | python3 -m json.tool
{
    "action": "reject",
    "answer_id_context": "20260512T040232896225Z-d6faf31e",
    "event_id": "20260512T040234126223Z-70bb3094",
    "reason": "\uad00\ub828 \uc5c6\uc74c - smoke test",
    "target_kind": "card",
    "target_ref": "dansim-ios",
    "ts": "2026-05-12T04:02:34.125955Z",
    "weight": -0.3
}

$ synapse-memory feedback card dansim-ios --accept --vault-path "$SYNAPSE_OBSIDIAN_VAULT"
✓ Recorded accept for card dansim-ios (targets=1, weight=+0.20)
  → next index will apply updated feedback_score: dansim-ios

$ synapse-memory rag index
인덱싱 시작 (rebuild=False)
  [project] 1개 임베딩 중...

인덱싱 완료: project=1 company=0 bytes=505
총 벡터: 1

$ synapse-memory rag search "클린 아키텍처" --top-k 5 --show-snippet
쿼리: '클린 아키텍처'  (top 5, 거리 작을수록 가까움)
--------------------------------------------------------------------------------
  [0.497] card_project   card_project:dansim-ios        단심 iOS feedback=0.94
    # 단심 iOS 역할: iOS Lead 기간: 2024-01 ~ 2024-05 상태: completed 도메인: ios 기술 스택: Swift, Clean Architecture 키워드: 클린 아키텍처, SwiftUI  ## 클린 아키텍처 기준 단심 iOS에서는 Dom

$ mv "$SYNAPSE_L0_ROOT/last_response.json" "$SYNAPSE_L0_ROOT/last_response.json.bak"

$ synapse-memory feedback last --reject "대상 없음"
✗ No recent answer found. Run ask/me first, then retry feedback last.

$ tail -1 "$SYNAPSE_L0_ROOT/feedback.jsonl" | python3 -m json.tool
{
    "action": "accept",
    "answer_id_context": null,
    "event_id": "20260512T040234257127Z-5f1724c4",
    "reason": null,
    "target_kind": "card",
    "target_ref": "dansim-ios",
    "ts": "2026-05-12T04:02:34.256879Z",
    "weight": 0.2
}
```

## Result

- `last_response.json` was created after `ask`.
- `feedback last --reject` appended one reject event.
- `feedback card dansim-ios --accept` appended one accept event.
- Re-indexing surfaced `feedback=0.94` in `rag search`, confirming feedback score application.
- Removing `last_response.json` made `feedback last` no-op with the expected error and did not append a new event.
