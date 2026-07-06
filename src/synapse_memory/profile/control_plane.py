"""Profile control-plane operations used by the CLI."""

from __future__ import annotations

import datetime as dt
import json
import re
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from synapse_memory.cli.common import FAIL, OK

ResolveVault = Callable[[Any | None], Path]


def list_pending_profiles(args: Any, *, resolve_vault: ResolveVault) -> int:
    from synapse_memory.config import get_config
    from synapse_memory.folders import find_candidate_files

    vault = resolve_vault(args)
    inbox = vault / get_config().vault_folders.system.ai.memory_inbox
    candidates = find_candidate_files(inbox, pattern="Profile-*.md")

    date_pattern = re.compile(r"^Profile-(\d{4})-(\d{2})-(\d{2})\.md$")
    pending: list[dict[str, str]] = []
    for path in candidates:
        match = date_pattern.match(path.name)
        if match is None:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "\nstatus: applied" in text or text.startswith("status: applied"):
            continue
        date = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
        status = "pending_review"
        if "\nstatus: " in text:
            for line in text.splitlines():
                if line.startswith("status:"):
                    status = line.split(":", 1)[1].strip()
                    break
        if status != "applied":
            pending.append({"date": date, "path": str(path), "status": status})

    pending.sort(key=lambda item: item["date"])
    if args.json:
        sys.stdout.write(json.dumps(pending, ensure_ascii=False))
        return 0
    if not pending:
        print("pending 후보가 없습니다.")
        return 0
    for entry in pending:
        print(f"{entry['date']} — {entry['path']}")
    return 0


def dismiss_profile(args: Any, *, resolve_vault: ResolveVault) -> int:
    from synapse_memory.profile.dismissed import append_dismissed, dismissed_path

    vault = resolve_vault(args)
    target = dismissed_path(vault)
    record = append_dismissed(
        args.kind,
        args.text,
        reason=args.reason,
        note=args.note,
        path=target,
    )

    if record is None:
        if not args.text.strip():
            print(f"{FAIL} --text 가 비어 있습니다.", file=sys.stderr)
            return 2
        print(f"{OK} 이미 dismissed 목록에 있음 (멱등): kind={args.kind} text={args.text!r}")
        return 0

    reason_note = f" reason={record.reason}" if record.reason else ""
    print(
        f"{OK} dismissed 추가: kind={record.kind} dismissed_at={record.dismissed_at}"
        f"{reason_note}\n"
        f"     fingerprint={record.fingerprint!r}\n"
        f"     file={target}\n"
        f"     해제하려면 위 파일에서 해당 라인을 삭제하거나, "
        f"profile.dismissed_ttl_days 일 경과를 기다리면 자동 재노출됩니다."
    )
    return 0


def dismiss_list(args: Any, *, resolve_vault: ResolveVault) -> int:
    from synapse_memory.config import get_config
    from synapse_memory.profile.dismissed import (
        DismissedRecord,
        _ttl_for,
        dismissed_path,
        profile_to_ttl_overrides,
    )

    vault = resolve_vault(args)
    target = dismissed_path(vault)
    if not target.is_file():
        sys.stdout.write("[]" if args.json else "dismissed 목록이 비어 있습니다.\n")
        return 0

    cfg = get_config().profile
    overrides = profile_to_ttl_overrides(cfg)
    today = dt.date.today()
    rows: list[dict[str, object]] = []
    for raw_line in target.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        rec = DismissedRecord.from_dict(obj)
        if rec is None:
            continue
        if args.kind != "all" and rec.kind != args.kind:
            continue
        if args.reason is not None and rec.reason != args.reason:
            continue
        ttl = _ttl_for(rec.reason, cfg.dismissed_ttl_days, overrides)
        age_days: int | None = None
        expired = False
        try:
            date = dt.date.fromisoformat(rec.dismissed_at)
            age_days = (today - date).days
            expired = ttl > 0 and age_days > ttl
        except ValueError:
            pass
        if args.active_only and expired:
            continue
        rows.append(
            {
                "kind": rec.kind,
                "fingerprint": rec.fingerprint,
                "original": rec.original,
                "dismissed_at": rec.dismissed_at,
                "reason": rec.reason,
                "note": rec.note,
                "ttl_days": ttl,
                "age_days": age_days,
                "expired": expired,
            }
        )

    if args.json:
        sys.stdout.write(json.dumps(rows, ensure_ascii=False))
        return 0
    if not rows:
        print("조건에 맞는 dismissed 항목이 없습니다.")
        return 0
    print(f"총 {len(rows)}건 (vault: {vault}, file: {target.name})")
    print("-" * 90)
    for row in rows:
        flag = " [만료]" if row["expired"] else ""
        reason = row["reason"] or "—"
        age = row["age_days"]
        age_s = f"{age}일 전" if age is not None else "?"
        original = str(row["original"])[:60]
        if len(str(row["original"])) > 60:
            original += "…"
        print(
            f"[{row['kind']}] reason={reason:<14} age={age_s:>8} "
            f"ttl={row['ttl_days']}일{flag}\n"
            f"     {original}"
        )
    return 0


def dismiss_purge_expired(args: Any, *, resolve_vault: ResolveVault) -> int:
    from synapse_memory.config import get_config
    from synapse_memory.profile.dismissed import (
        DismissedRecord,
        _ttl_for,
        dismissed_path,
        profile_to_ttl_overrides,
    )

    vault = resolve_vault(args)
    target = dismissed_path(vault)
    if not target.is_file():
        print("dismissed.jsonl 파일이 없습니다.")
        return 0

    cfg = get_config().profile
    overrides = profile_to_ttl_overrides(cfg)
    today = dt.date.today()
    keep_lines: list[str] = []
    expired_records: list[DismissedRecord] = []
    invalid_kept = 0
    for raw_line in target.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            keep_lines.append(line)
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            keep_lines.append(line)
            invalid_kept += 1
            continue
        rec = DismissedRecord.from_dict(obj) if isinstance(obj, dict) else None
        if rec is None:
            keep_lines.append(line)
            invalid_kept += 1
            continue
        ttl = _ttl_for(rec.reason, cfg.dismissed_ttl_days, overrides)
        try:
            age = (today - dt.date.fromisoformat(rec.dismissed_at)).days
        except ValueError:
            keep_lines.append(line)
            continue
        if ttl > 0 and age > ttl:
            expired_records.append(rec)
        else:
            keep_lines.append(line)

    if not expired_records:
        print(f"만료된 라인 없음 (총 {len(keep_lines)}건 유효, invalid {invalid_kept}건)")
        return 0

    print(f"만료 대상: {len(expired_records)}건 (유지 {len(keep_lines)}건)")
    for rec in expired_records[:20]:
        original = rec.original[:50] + ("…" if len(rec.original) > 50 else "")
        print(
            f"  [{rec.kind}] reason={rec.reason or '—'} "
            f"dismissed_at={rec.dismissed_at} — {original}"
        )
    if len(expired_records) > 20:
        print(f"  ... ({len(expired_records) - 20}건 더)")

    if not args.apply:
        print(f"\n{OK} dry-run — 실제 삭제하려면 `--apply` 추가. 백업 파일이 자동 생성됩니다.")
        return 0

    backup = target.with_suffix(target.suffix + f".bak.{today.isoformat()}")
    shutil.copy2(target, backup)
    target.write_text("\n".join(keep_lines) + ("\n" if keep_lines else ""), encoding="utf-8")
    print(f"\n{OK} {len(expired_records)}건 삭제 완료. 백업: {backup.name}")
    return 0


def ledger_show(args: Any) -> int:
    from synapse_memory.profile.ledger import ledger_path, load_ledger

    target = ledger_path()
    if not target.is_file():
        sys.stdout.write("[]" if args.json else "ledger 파일 없음 — 아직 update_profile 호출이 없습니다.\n")
        return 0

    ledger = load_ledger()
    entries = list(ledger.values())
    if args.kind != "all":
        entries = [entry for entry in entries if entry.kind == args.kind]
    if args.status == "promoted":
        entries = [entry for entry in entries if entry.promoted]
    elif args.status == "awaiting":
        entries = [entry for entry in entries if not entry.promoted]

    entries.sort(key=lambda entry: (-entry.seen_count, -entry.peak_confidence()))
    if args.top and args.top > 0:
        entries = entries[: args.top]

    if args.json:
        sys.stdout.write(json.dumps([entry.to_dict() for entry in entries], ensure_ascii=False))
        return 0
    if not entries:
        print("조건에 맞는 ledger 항목이 없습니다.")
        return 0

    total = len(ledger)
    promoted = sum(1 for entry in ledger.values() if entry.promoted)
    awaiting = total - promoted
    print(
        f"ledger 총 {total}건 (promoted {promoted} / awaiting {awaiting}). "
        f"표시: {len(entries)}건 (kind={args.kind}, status={args.status})"
    )
    print("-" * 90)
    for entry in entries:
        flag = "✓ promoted" if entry.promoted else "  awaiting"
        snippet = entry.best_statement()[:60]
        if len(entry.best_statement()) > 60:
            snippet += "…"
        print(
            f"[{entry.kind}] {flag}  seen={entry.seen_count:>3}  "
            f"peak={entry.peak_confidence():.2f}  "
            f"avg={entry.aggregated_confidence():.2f}  "
            f"({entry.first_seen} → {entry.last_seen})\n"
            f"     {snippet}"
        )
    return 0


def review_awaiting(args: Any, *, resolve_vault: ResolveVault) -> int:
    from synapse_memory.config import get_config
    from synapse_memory.profile.candidate_filter import CandidateFilter
    from synapse_memory.profile.extract import save_profile_update
    from synapse_memory.profile.ledger import (
        collect_review_candidates,
        load_ledger,
        mark_promoted,
        save_ledger,
    )

    cfg = get_config()
    vault = resolve_vault(None)
    candidate_filter = CandidateFilter(vault_path=vault, config=cfg)
    ledger = load_ledger()
    if not ledger:
        print("ledger 비어있음 — 먼저 'synapse-memory daily' 를 실행하세요.")
        return 0

    window_days = cfg.profile.promotion_window_days
    min_conf = args.min_confidence
    candidate_facts, candidate_patterns = collect_review_candidates(
        ledger,
        min_confidence=min_conf,
        window_days=window_days,
    )
    if not candidate_facts and not candidate_patterns:
        print(f"임계치 peak ≥ {min_conf:.2f} & window {window_days}일 내 awaiting 항목 없음.")
        return 0

    facts, patterns, report = candidate_filter.dedupe(candidate_facts, candidate_patterns)
    if args.dry_run:
        print(
            f"[dry-run] 후보 fact={len(facts)} pattern={len(patterns)} "
            f"(dedupe 제외 -{report.total_dropped}) — peak ≥ {min_conf:.2f}"
        )
        for fact in facts[:10]:
            print(f"  fact    [{fact.confidence:.2f}] {fact.statement[:80]}")
        for pattern in patterns[:10]:
            print(f"  pattern [{pattern.confidence:.2f}] {pattern.trigger[:80]}")
        return 0

    if not facts and not patterns:
        print("dedupe 후 남은 후보 없음 (vault 또는 dismissed 와 중복).")
        return 0

    mark_promoted(ledger, facts, patterns)
    save_ledger(ledger)
    path = save_profile_update(facts, patterns, ledger=ledger)
    print(
        f"{OK} fact={len(facts)} pattern={len(patterns)} → {path.name} "
        f"(peak ≥ {min_conf:.2f}, vault dedupe -{report.total_dropped})"
    )
    return 0
