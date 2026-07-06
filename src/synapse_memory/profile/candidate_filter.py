"""Candidate gate for profile extraction results.

Author: JunyoungJung
Created: 2026-07-06
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path

from synapse_memory.config import SynapseConfig, get_config, get_vault_path
from synapse_memory.profile.dedupe import (
    DedupeReport,
    dedupe_against_vault,
    parse_decision_pattern_triggers,
    parse_profile_facts,
)
from synapse_memory.profile.dismissed import (
    DismissedIndex,
    dismissed_path,
    load_dismissed,
)
from synapse_memory.profile.ledger import (
    LedgerEntry,
    PromotionReport,
    enrich_promoted_patterns,
    load_ledger,
    mark_promoted,
    promote_candidates,
    record_extraction,
    save_ledger,
)
from synapse_memory.profile.schema import DecisionPattern, ProfileFact
from synapse_memory.profile.wiki import profile_page_path


@dataclass(frozen=True)
class CandidateFilterResult:
    facts: list[ProfileFact]
    patterns: list[DecisionPattern]
    promotion_report: PromotionReport
    dedupe_report: DedupeReport
    dismissed: DismissedIndex
    ledger: dict[str, LedgerEntry]


class CandidateFilter:
    """Ledger, dismissed, and profile-page dedupe as one gate."""

    def __init__(
        self,
        *,
        vault_path: Path | None = None,
        config: SynapseConfig | None = None,
        ledger: dict[str, LedgerEntry] | None = None,
        dismissed: DismissedIndex | None = None,
    ) -> None:
        self.vault_path = (vault_path or get_vault_path()).expanduser().resolve()
        self.config = config or get_config()
        self.profile_path = profile_page_path(self.vault_path)
        self.dismissed = dismissed or load_dismissed(dismissed_path(self.vault_path))
        self.ledger = ledger if ledger is not None else load_ledger()

    def existing_facts(self) -> list[str]:
        return parse_profile_facts(self.profile_path)

    def existing_pattern_triggers(self) -> list[str]:
        return parse_decision_pattern_triggers(self.profile_path)

    def excluded_facts(self) -> list[str]:
        return self.existing_facts() + sorted(self.dismissed.facts)

    def excluded_pattern_triggers(self) -> list[str]:
        return self.existing_pattern_triggers() + sorted(self.dismissed.patterns)

    def strong_facts(self) -> list[str]:
        return sorted(self.dismissed.strong_facts())

    def strong_patterns(self) -> list[str]:
        return sorted(self.dismissed.strong_patterns())

    def dedupe(
        self,
        facts: list[ProfileFact],
        patterns: list[DecisionPattern],
    ) -> tuple[list[ProfileFact], list[DecisionPattern], DedupeReport]:
        return dedupe_against_vault(
            facts,
            patterns,
            profile_path=self.profile_path,
            decision_patterns_path=self.profile_path,
            dismissed_facts=self.dismissed.facts,
            dismissed_patterns=self.dismissed.patterns,
        )

    def filter(
        self,
        facts: list[ProfileFact],
        patterns: list[DecisionPattern],
        *,
        today: datetime.date | None = None,
        persist: bool = True,
    ) -> CandidateFilterResult:
        cfg = self.config.profile
        record_extraction(self.ledger, facts, patterns, today=today)
        promoted_facts, promoted_patterns, promotion_report = promote_candidates(
            self.ledger,
            facts_input=facts,
            patterns_input=patterns,
            min_count=cfg.promotion_min_count,
            window_days=cfg.promotion_window_days,
            fast_path_confidence=cfg.fast_path_confidence,
            today=today,
        )
        promoted_patterns = enrich_promoted_patterns(promoted_patterns, patterns)
        kept_facts, kept_patterns, dedupe_report = self.dedupe(
            promoted_facts,
            promoted_patterns,
        )
        mark_promoted(self.ledger, kept_facts, kept_patterns, today=today)
        if persist:
            save_ledger(self.ledger)
        return CandidateFilterResult(
            facts=kept_facts,
            patterns=kept_patterns,
            promotion_report=promotion_report,
            dedupe_report=dedupe_report,
            dismissed=self.dismissed,
            ledger=self.ledger,
        )
