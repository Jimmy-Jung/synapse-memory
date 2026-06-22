# tests/test_wiki_rawdoc.py
"""claude-code 미러 jsonl → RawDoc."""
from __future__ import annotations

import json
import os
from pathlib import Path

from synapse_memory.wiki.rawdoc import RawDoc, iter_new_raw


def _write_jsonl(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in events),
        encoding="utf-8",
    )


def test_extracts_text_from_message_events(tmp_path: Path) -> None:
    root = tmp_path / "raw" / "claude-code"
    f = root / "projects" / "demo" / "sess1.jsonl"
    _write_jsonl(
        f,
        [
            {"type": "user", "message": {"role": "user", "content": "프로젝트 구조 알려줘"}},
            {"type": "assistant", "message": {"role": "assistant",
             "content": [{"type": "text", "text": "MVVM 입니다"}]}},
        ],
    )
    docs = list(iter_new_raw("claude-code", since=None, root=root))
    assert len(docs) == 1
    assert isinstance(docs[0], RawDoc)
    assert "프로젝트 구조 알려줘" in docs[0].text
    assert "MVVM 입니다" in docs[0].text
    assert docs[0].ref == "claude-code:projects/demo/sess1.jsonl"


def test_since_filters_older_files(tmp_path: Path) -> None:
    root = tmp_path / "raw" / "claude-code"
    old = root / "old.jsonl"
    new = root / "new.jsonl"
    _write_jsonl(old, [{"message": {"role": "user", "content": "old"}}])
    _write_jsonl(new, [{"message": {"role": "user", "content": "new"}}])
    os.utime(old, (1_000_000_000, 1_000_000_000))
    os.utime(new, (2_000_000_000, 2_000_000_000))
    docs = list(iter_new_raw("claude-code", since="2020-01-01T00:00:00", root=root))
    texts = [d.text for d in docs]
    assert "new" in texts and "old" not in texts


def test_missing_root_returns_empty(tmp_path: Path) -> None:
    assert list(iter_new_raw("claude-code", since=None, root=tmp_path / "nope")) == []


def test_skips_unparseable_lines(tmp_path: Path) -> None:
    root = tmp_path / "raw" / "claude-code"
    f = root / "s.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text('{"message":{"role":"user","content":"ok"}}\nGARBAGE\n', encoding="utf-8")
    docs = list(iter_new_raw("claude-code", since=None, root=root))
    assert len(docs) == 1
    assert "ok" in docs[0].text


# ---------------------------------------------------------------------------
# codex 소스
# ---------------------------------------------------------------------------


def test_codex_extracts_user_and_assistant_messages(tmp_path: Path) -> None:
    root = tmp_path / "raw" / "codex"
    f = root / "sessions" / "2026" / "06" / "19" / "rollout-x.jsonl"
    _write_jsonl(
        f,
        [
            {"type": "session_meta", "payload": {"id": "abc", "cwd": "/x"}},
            {"type": "event_msg", "payload": {"type": "user_message",
             "message": "프로젝트 구조 알려줘"}},
            {"type": "response_item", "payload": {"type": "reasoning",
             "content": [{"type": "text", "text": "think..."}]}},
            {"type": "response_item", "payload": {"type": "message", "role": "assistant",
             "content": [{"type": "output_text", "text": "MVVM 구조입니다"}]}},
        ],
    )
    docs = list(iter_new_raw("codex", since=None, root=root))
    assert len(docs) == 1
    assert isinstance(docs[0], RawDoc)
    assert docs[0].source == "codex"
    assert "User: 프로젝트 구조 알려줘" in docs[0].text
    assert "Assistant: MVVM 구조입니다" in docs[0].text
    assert "think..." not in docs[0].text  # reasoning 제외
    assert docs[0].ref == "codex:sessions/2026/06/19/rollout-x.jsonl"


def test_codex_assistant_uses_response_item_not_truncated_agent_message(
    tmp_path: Path,
) -> None:
    """agent_message(잘린 도입부) 대신 response_item/message 전체 본문을 써야 한다."""
    root = tmp_path / "raw" / "codex"
    f = root / "sessions" / "s.jsonl"
    full = "도입부입니다.\n<proposed_plan>\n상세 계획 본문 전체\n</proposed_plan>\n마무리."
    _write_jsonl(
        f,
        [
            {"type": "event_msg", "payload": {"type": "agent_message",
             "message": "도입부입니다."}},  # 잘린 lead-in — 무시돼야
            {"type": "response_item", "payload": {"type": "message", "role": "assistant",
             "content": [{"type": "output_text", "text": full}]}},
        ],
    )
    docs = list(iter_new_raw("codex", since=None, root=root))
    assert len(docs) == 1
    # 전체 본문(구조블록 포함)이 보존돼야 한다.
    assert "상세 계획 본문 전체" in docs[0].text
    # agent_message 중복 라인이 추가로 들어가면 안 됨.
    assert docs[0].text.count("도입부입니다.") == 1


def test_no_skip_with_shared_second_mtimes_and_limit(tmp_path: Path) -> None:
    """같은 초에 미러된 파일이 limit를 초과해도 watch 루프가 전량 처리(누락 0).

    회귀: 과거 초 단위 mtime 절삭 + 경로순 + max-mtime watermark + limit 조합은
    같은 초의 나머지 파일을 영구 skip시켜 대량 백필의 94%를 잃었다.
    """
    import itertools

    root = tmp_path / "raw" / "codex"
    base_ts = 1_700_000_000  # 동일 정수 초
    for i in range(5):
        f = root / "sessions" / f"s{i}.jsonl"
        _write_jsonl(
            f,
            [{"type": "event_msg", "payload": {"type": "user_message",
              "message": f"msg{i}"}}],
        )
        # 같은 초, 서로 다른 마이크로초 (미러 순차 기록 재현).
        os.utime(f, (base_ts + i * 0.001, base_ts + i * 0.001))

    # watch 루프 시뮬: 사이클당 limit=2, watermark를 처리한 doc의 max mtime_iso로 전진.
    seen: list[str] = []
    since: str | None = None
    for _ in range(10):
        docs = list(itertools.islice(iter_new_raw("codex", since=since, root=root), 2))
        if not docs:
            break
        seen.extend(d.ref for d in docs)
        since = max(d.mtime_iso for d in docs)

    assert len(seen) == 5, f"전량 처리돼야 함, got {seen}"
    assert len(set(seen)) == 5, f"중복 없어야 함, got {seen}"


def test_offsets_send_only_appended_tail(tmp_path: Path) -> None:
    """레버 2: offset 이후 tail만 읽고, byte_size로 새 offset을 노출한다."""
    root = tmp_path / "raw" / "claude-code"
    f = root / "s.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    first = '{"message":{"role":"user","content":"첫줄"}}\n'
    f.write_text(first, encoding="utf-8")

    # 1회차: offset 없음 → 전문.
    d1 = next(iter(iter_new_raw("claude-code", since=None, root=root)))
    assert "첫줄" in d1.text
    assert d1.byte_size == len(first.encode("utf-8"))

    # append 후 2회차: 이전 byte_size를 offset으로 주면 새 줄만.
    f.write_text(first + '{"message":{"role":"user","content":"둘째줄"}}\n', encoding="utf-8")
    d2 = next(
        iter(iter_new_raw("claude-code", since=None, root=root, offsets={d1.ref: d1.byte_size}))
    )
    assert "둘째줄" in d2.text
    assert "첫줄" not in d2.text  # 이미 ingest한 부분 재전송 안 함
    assert d2.byte_size > d1.byte_size


def test_offset_past_eof_reparses_full(tmp_path: Path) -> None:
    """offset이 현재 크기를 벗어나면(로테이션/축소) 전문 재처리 — 데이터 유실 방지."""
    root = tmp_path / "raw" / "claude-code"
    f = root / "s.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text('{"message":{"role":"user","content":"리셋후"}}\n', encoding="utf-8")
    docs = list(
        iter_new_raw("claude-code", since=None, root=root, offsets={"claude-code:s.jsonl": 999_999})
    )
    assert len(docs) == 1
    assert "리셋후" in docs[0].text  # offset 무시하고 전문


def test_codex_filters_noise_events(tmp_path: Path) -> None:
    """developer 보일러플레이트 / token_count / function_call / user role-주입 은 제외."""
    root = tmp_path / "raw" / "codex"
    f = root / "sessions" / "s.jsonl"
    _write_jsonl(
        f,
        [
            {"type": "response_item", "payload": {"type": "message", "role": "developer",
             "content": [{"type": "input_text", "text": "<permissions instructions>"}]}},
            {"type": "response_item", "payload": {"type": "message", "role": "user",
             "content": [{"type": "input_text", "text": "# AGENTS.md 주입"}]}},
            {"type": "event_msg", "payload": {"type": "token_count"}},
            {"type": "response_item", "payload": {"type": "function_call",
             "name": "shell", "arguments": "{}"}},
        ],
    )
    docs = list(iter_new_raw("codex", since=None, root=root))
    # 노이즈만 있으면 텍스트 0 → doc 생성 안 됨.
    assert docs == []
