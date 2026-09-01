#!/usr/bin/env python3
from __future__ import annotations

"""Replay the bounded balance trace manifest through GardenGameEngine."""

import argparse
from copy import deepcopy
from hashlib import sha256
import json
import logging
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from typing import Optional, Sequence
from unittest.mock import patch
import uuid


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
os.environ.setdefault("ANKI_GARDEN_SKIP_STARTUP", "1")

from ankigarden.config import DEFAULT_CONFIG
from ankigarden.balance_catalog import (
    CONSUMABLES,
    CURRENT_CATALOG_SPECIES_ORDER,
    STAGES,
)
from ankigarden.economy_progression import (
    ContributionMode,
    GARDEN_LEGACY_LEVEL_COST_UNITS,
    LANDMARK_MAX_GROWTH_UNITS,
    MASTERY_MAX_GROWTH_UNITS,
    GrowthProjectAction,
    GrowthProjectConfirmation,
    GrowthProjectRequest,
    GrowthTargetRef,
    GrowthTargetType,
    build_growth_projects_snapshot,
    project_growth_project_request,
)
from ankigarden.game import GardenGameEngine
from ankigarden.garden_finds import (
    ENVIRONMENT_TIER_COMPLETION_PITY,
    ENVIRONMENT_TIER_RULES,
    consumption_id,
    resolve_environment_completion_pity,
    resolve_environment_find,
    resolve_standard_find,
    stable_answer_event_identity,
)
from ankigarden.models.state import ActivePlantPeriod, DailyStats, GardenState, Plant
from ankigarden.purchases import PurchaseKind, PurchaseRequest, PurchaseStatus
from ankigarden.reward_ledger import LEDGER_SCHEMA_VERSION
from ankigarden.storage import (
    DueObligationStatus,
    GardenStorage,
    HistoricalReviewEntry,
    HistoricalReviewSnapshot,
    STATE_VERSION,
)
from scripts.balance_analysis.catalog import load_catalog_facts
from scripts.balance_analysis.annual_parity import run_annual_parity
from scripts.balance_analysis.kernel import (
    DayEvents,
    EnvironmentDiscoveryEvent,
    simulate_scenario,
)
from scripts.balance_analysis.model import (
    CohortSpec,
    ScenarioSpec,
    SimulationConfig,
    StrategySpec,
    approved_scenarios,
)
from scripts.balance_analysis.trace import (
    GardenGameEngineReplayAdapter,
    REQUIRED_PARITY_BEHAVIORS,
    REQUIRED_PARITY_STATE_FIELDS,
    assert_release_state_parity,
    assert_release_parity_manifest,
    project_production_release_state,
    project_production_engine_trace_row,
    release_parity_manifest,
)


class _FocusedOracleEvidence:
    """Record exact pure-domain/production comparisons for focused behaviors.

    Expected values passed here are calculated from immutable catalog/domain
    contracts.  Production values are renderer-neutral state or durable ledger
    projections.  The recorder never derives an expected value by copying a
    post-event ``GardenGameEngine`` snapshot.
    """

    def __init__(self) -> None:
        self.checkpoints: list[dict[str, object]] = []
        self.trace_prefix: list[dict[str, object]] = []
        self.behavior_fields: dict[str, set[str]] = {}

    def compare(
        self,
        *,
        case_id: str,
        event_identity: str,
        behavior: str,
        expected: dict[str, object],
        actual: dict[str, object],
        state_fields: Sequence[str] = (),
        operation: str,
    ) -> None:
        fields = tuple(expected)
        self.trace_prefix.append({
            "case_id": case_id,
            "event_identity": event_identity,
            "operation": operation,
            "expected": expected,
        })
        assert_release_state_parity(
            expected,
            actual,
            event_identity=event_identity,
            fields=fields,
            trace_prefix=self.trace_prefix,
        )
        promoted = self.behavior_fields.setdefault(behavior, set())
        promoted.update(str(field) for field in state_fields)
        self.checkpoints.append({
            "case_id": case_id,
            "event_identity": event_identity,
            "behavior": behavior,
            "fields": list(fields),
            "state_fields": list(state_fields),
            "expected": expected,
            "actual": {field: actual[field] for field in fields},
        })

    def evidence(self) -> dict[str, object]:
        promoted_fields = tuple(
            field for field in REQUIRED_PARITY_STATE_FIELDS
            if any(
                field in fields for fields in self.behavior_fields.values()
            )
        )
        behaviors = tuple(
            behavior for behavior in REQUIRED_PARITY_BEHAVIORS
            if behavior in self.behavior_fields
        )
        payload = json.dumps(
            self.checkpoints,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        manifest = json.dumps(
            self.trace_prefix,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        return {
            "status": "pass",
            "oracle": "immutable catalog and pure domain transaction contracts",
            "storage_adapter": "GardenStorage+RewardLedger(SQLite)",
            "state_schema_version": STATE_VERSION,
            "ledger_schema_version": LEDGER_SCHEMA_VERSION,
            "case_count": len({
                str(row["case_id"]) for row in self.checkpoints
            }),
            "checkpoint_count": len(self.checkpoints),
            "covered_behaviors": list(behaviors),
            "covered_state_fields": list(promoted_fields),
            "behavior_state_fields": {
                behavior: sorted(fields)
                for behavior, fields in sorted(self.behavior_fields.items())
            },
            "state_pairs_sha256": sha256(payload).hexdigest(),
            "trace_manifest_sha256": sha256(manifest).hexdigest(),
        }


class _ParityConfig:
    def value(self, key, default=None):
        return DEFAULT_CONFIG.get(key, default)

    def nested(self, *keys, default=None):
        node = DEFAULT_CONFIG
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node


class _ParityStorage:
    """Fast arithmetic storage; never used as persistence evidence."""

    def __init__(self):
        self.day = "2026-08-30"
        self.now_ms = 1_788_100_000_000
        self.day_start_ms = self.now_ms - 10_000
        plant = Plant("p1", "bonsai", "Moss", 0)
        self.state = GardenState(
            plants=[plant],
            active_plant_id="p1",
            starter_selection_complete=True,
            garden_setup_version=1,
            unlocked_species=["bonsai"],
            daily_stats=DailyStats(day=self.day),
            active_plant_periods=[
                ActivePlantPeriod(self.day, "p1", self.now_ms - 1_000)
            ],
            reward_seed="parity-seed",
            reward_state_initialized=True,
            reward_activation_ms=self.day_start_ms,
            progression_activation_ms=self.day_start_ms,
            # Finds and environment discovery have their own focused engine
            # tests. This paired daily trace uses explicit sparse kernel events.
            garden_find_activation_ms=9_000_000_000_000,
        )
        self.addon_dir = REPOSITORY_ROOT / "ankigarden"
        self.assets_root = self.addon_dir / "assets"
        self.eligible_days: list[str] = []
        self.completion_days: set[str] = set()

    def save(self):
        return None

    def current_scheduler_day(self):
        return self.day

    def current_day_start_ms(self):
        return self.day_start_ms

    def current_time_ms(self):
        return self.now_ms

    def due_obligations(self):
        return DueObligationStatus()

    def load_asset_metadata(self):
        return {}

    def save_asset_metadata(self, _value):
        return None

    def eligible_study_days_before(self, day, *, limit=7):
        return tuple(
            value for value in self.eligible_days if value < str(day)
        )[-max(0, int(limit)):]

    def verified_today_cards_completion_days_before(self, day):
        return {value for value in self.completion_days if value < str(day)}

    def record_replay_day(self, day, *, complete, studied):
        if studied and day not in self.eligible_days:
            self.eligible_days.append(day)
            self.eligible_days.sort()
        if complete:
            self.completion_days.add(day)


class _DurableParityStorage(GardenStorage):
    """Real schema-27/ledger-3 storage rooted in a disposable directory.

    Only Anki's scheduler clock and revlog reader are replaced. Every Garden
    state, reward, economy, and idempotency write uses the production
    ``GardenStorage`` and ``RewardLedger`` commit/rollback path.
    """

    def __init__(
        self,
        root: Path,
        *,
        initial_state: GardenState | None = None,
        scheduler_day: str = "2026-08-30",
        now_ms: int = 1_788_100_000_000,
        review_history: list[HistoricalReviewEntry] | None = None,
    ) -> None:
        self.mw = None
        self.config = _ParityConfig()
        self.addon_dir = REPOSITORY_ROOT / "ankigarden"
        self.user_files_dir = Path(root)
        self.data_path = self.user_files_dir / "garden_state.json"
        self.database_path = self.user_files_dir / "garden_rewards.sqlite3"
        self.assets_root = self.addon_dir / "assets"
        self.metadata_dir = self.user_files_dir
        self.cache_dir = self.user_files_dir / "cache"
        self.asset_metadata = self.user_files_dir / "asset_metadata.json"
        self._reward_ledger = None
        self._ledger_revision = 0
        self.day = str(scheduler_day)
        self.now_ms = max(1, int(now_ms))
        self.day_start_ms = self.now_ms - 10_000
        self.review_history = review_history if review_history is not None else []
        self.fail_next_save = False
        self.user_files_dir.mkdir(parents=True, exist_ok=True)
        if self.database_path.exists():
            self.state = self._load_authoritative_state()
        else:
            if initial_state is None:
                raise ValueError("initial_state is required for a new parity ledger")
            self.state = deepcopy(initial_state)
            self._install_reward_database(self.state)

    def save(self) -> None:
        if self.fail_next_save:
            self.fail_next_save = False
            raise OSError("injected parity persistence failure")
        super().save()

    def close(self) -> None:
        if self._reward_ledger is not None:
            self._reward_ledger.close()
            self._reward_ledger = None

    def current_scheduler_day(self) -> str:
        return self.day

    def current_day_start_ms(self) -> int:
        return self.day_start_ms

    def current_time_ms(self) -> int:
        return self.now_ms

    def due_obligations(self) -> DueObligationStatus:
        return DueObligationStatus()

    def load_eligible_review_history(self) -> HistoricalReviewSnapshot:
        entries = tuple(sorted(
            self.review_history,
            key=lambda row: (row.revlog_id, row.card_id),
        ))
        return HistoricalReviewSnapshot(
            entries=entries,
            high_water_revlog_id=max(
                (row.revlog_id for row in entries), default=0
            ),
            fingerprint="durable-parity-history:" + str(len(entries)),
            answer_lineage_bindings=self.all_answer_lineage_bindings(),
        )


class _DurableParitySession:
    """Own a disposable ledger while allowing true close/reopen restarts."""

    def __init__(self, root: Path, initial_state: GardenState) -> None:
        self.root = Path(root)
        self.review_history: list[HistoricalReviewEntry] = []
        self.storage = _DurableParityStorage(
            self.root,
            initial_state=initial_state,
            review_history=self.review_history,
        )

    def engine(self) -> GardenGameEngine:
        return GardenGameEngine(_ParityConfig(), self.storage)

    def restart(self) -> GardenGameEngine:
        day = self.storage.day
        now_ms = self.storage.now_ms
        self.storage.close()
        self.storage = _DurableParityStorage(
            self.root,
            scheduler_day=day,
            now_ms=now_ms,
            review_history=self.review_history,
        )
        return self.engine()

    def close(self) -> None:
        self.storage.close()


_FOCUSED_SECRETS = {
    "natural": "parity-natural-21",
    "rare_natural": "parity-rare_environment-47",
    "very_rare_natural": "parity-very_rare_environment-17011",
    "ultra_rare_natural": "parity-ultra_environment-4945",
    "card_pity_simultaneous": "parity-card-pity",
    "completion_pity_simultaneous": "parity-completion-pity",
}


def _answer_identity(event, position: int = 1) -> str:
    values = event.payload
    revlog_id = max(1, int(values.get("revlog_base", 1))) + position
    card_id = max(1, int(values.get("card_base", 1))) + position
    lineage_id = f"parity:{revlog_id}:{card_id}"
    return stable_answer_event_identity(
        revlog_id,
        card_id=card_id,
        answered_at_ms=revlog_id,
        lineage_id=lineage_id,
    )


def _configure_focused_storage(storage: _ParityStorage, case) -> None:
    focused = next((
        event for event in case.events
        if event.payload.get("find_mode")
        or event.payload.get("environment_mode")
    ), None)
    if focused is None:
        return
    find_mode = str(focused.payload.get("find_mode", "") or "")
    environment_mode = str(
        focused.payload.get("environment_mode", "") or ""
    )
    storage.state.garden_find_activation_ms = storage.day_start_ms
    storage.state.reward_seed = _FOCUSED_SECRETS.get(
        find_mode or environment_mode,
        "parity-seed",
    )
    if find_mode == "forced":
        storage.state.garden_find_drought_count = 74
    if environment_mode == "card_pity_simultaneous":
        storage.state.environment_pity_misses = {
            "rare": ENVIRONMENT_TIER_RULES[
                "rare_environment"
            ].hard_pity_answers - 1,
            "very_rare": ENVIRONMENT_TIER_RULES[
                "very_rare_environment"
            ].hard_pity_answers - 1,
            "ultra": ENVIRONMENT_TIER_RULES[
                "ultra_environment"
            ].hard_pity_answers - 1,
        }
    if environment_mode == "completion_pity_simultaneous":
        storage.state.environment_completion_pity_misses = {
            "rare": ENVIRONMENT_TIER_COMPLETION_PITY[
                "rare_environment"
            ] - 1,
            "very_rare": ENVIRONMENT_TIER_COMPLETION_PITY[
                "very_rare_environment"
            ] - 1,
            "ultra": ENVIRONMENT_TIER_COMPLETION_PITY[
                "ultra_environment"
            ] - 1,
        }


def _focused_day_event(storage: _ParityStorage, event) -> DayEvents:
    values = event.payload
    find_mode = str(values.get("find_mode", "") or "")
    environment_mode = str(values.get("environment_mode", "") or "")
    find_count = 0
    find_coins = 0
    find_growth_units = 0
    inventory_items = ()
    environment_discoveries = []
    if find_mode or environment_mode:
        identity = _answer_identity(event)
        owned = {
            *(str(value) for value in storage.state.inventory.get(
                "garden_features", ()
            )),
            *(str(value) for value in storage.state.inventory.get(
                "scenery", ()
            )),
        }
        standard = resolve_standard_find(
            secret=storage.state.reward_seed,
            answer_identity=identity,
            drought_misses=storage.state.garden_find_drought_count,
            finds_today=0,
            eligible_answers_today=1,
            available_inventory_item_ids=storage.state.consumables.keys(),
            scheduler_day=str(values.get("scheduler_day", storage.day)),
            addon_version="2.2.0",
        )
        if find_mode and not standard.hit:
            raise AssertionError(
                f"focused {find_mode} Standard Find trace did not hit"
            )
        if find_mode == "forced" and standard.drought_answer_number != 75:
            raise AssertionError(
                "forced Standard Find trace did not use answer 75"
            )
        if find_mode == "natural" and (
            standard.drought_answer_number is None
            or standard.drought_answer_number >= 75
        ):
            raise AssertionError(
                "natural Standard Find trace reached the forced guarantee"
            )
        if environment_mode and standard.hit:
            raise AssertionError(
                "environment-focused trace unexpectedly hit Standard Finds"
            )
        if standard.hit and standard.reward is not None:
            reward = standard.reward
            find_count = 1
            if reward.reward_kind == "coins":
                find_coins = reward.amount
            elif reward.reward_kind == "growth":
                find_growth_units = reward.amount * 100
            elif reward.inventory_item_id:
                inventory_items = (reward.inventory_item_id,) * reward.amount

        card_misses = {
            "rare_environment": int(
                storage.state.environment_pity_misses.get("rare", 0)
            ),
            "very_rare_environment": int(
                storage.state.environment_pity_misses.get("very_rare", 0)
            ),
            "ultra_environment": int(
                storage.state.environment_pity_misses.get("ultra", 0)
            ),
        }
        environment = resolve_environment_find(
            secret=storage.state.reward_seed,
            answer_identity=identity,
            owned_environment_ids=owned,
            tier_pity_misses=card_misses,
        )
        expected_natural_tier = {
            "rare_natural": "rare_environment",
            "very_rare_natural": "very_rare_environment",
            "ultra_rare_natural": "ultra_environment",
        }.get(environment_mode)
        if expected_natural_tier and (
            not environment.hit
            or environment.tier != expected_natural_tier
            or environment.forced_by_pity
        ):
            raise AssertionError(
                f"focused environment trace missed {expected_natural_tier}"
            )
        if environment_mode == "card_pity_simultaneous" and (
            not environment.forced_by_pity or len(environment.items) != 3
        ):
            raise AssertionError(
                "simultaneous environment card-pity trace did not force 3 tiers"
            )
        if find_mode and environment.hit:
            raise AssertionError(
                "Standard-Find-focused trace unexpectedly discovered environment"
            )
        tier_ids = {
            "rare_environment": "rare",
            "very_rare_environment": "very_rare",
            "ultra_environment": "ultra",
        }
        for item in environment.items:
            environment_discoveries.append(EnvironmentDiscoveryEvent(
                item_id=item.item_id,
                tier_id=tier_ids[item.tier],
                route=(
                    "card_pity" if environment.forced_by_pity else "natural"
                ),
                eligible_card_index=card_misses[item.tier] + 1,
                simultaneous_forced=(
                    environment.forced_by_pity
                    and len(environment.items) > 1
                ),
            ))
            owned.add(item.item_id)
            owned.add(item.ownership_key)

        if bool(values.get("complete", False)):
            completion_misses = {
                "rare_environment": int(
                    storage.state.environment_completion_pity_misses.get(
                        "rare", 0
                    )
                ),
                "very_rare_environment": int(
                    storage.state.environment_completion_pity_misses.get(
                        "very_rare", 0
                    )
                ),
                "ultra_environment": int(
                    storage.state.environment_completion_pity_misses.get(
                        "ultra", 0
                    )
                ),
            }
            completion = resolve_environment_completion_pity(
                secret=storage.state.reward_seed,
                completion_identity=(
                    "today-cards:"
                    f"{values.get('scheduler_day', storage.day)}"
                ),
                owned_environment_ids=owned,
                tier_completion_misses=completion_misses,
            )
            if environment_mode == "completion_pity_simultaneous" and (
                environment.hit
                or len(completion.items) != 3
                or len(completion.forced_tiers) != 3
            ):
                raise AssertionError(
                    "simultaneous completion-pity trace did not force 3 tiers"
                )
            for item in completion.items:
                environment_discoveries.append(EnvironmentDiscoveryEvent(
                    item_id=item.item_id,
                    tier_id=tier_ids[item.tier],
                    route="completion_pity",
                    eligible_card_index=1,
                    simultaneous_forced=len(completion.items) > 1,
                ))
    return DayEvents(
        day=int(values["trace_day"]),
        study=True,
        answers=int(values["answers"]),
        standard_finds=find_count,
        find_coins=find_coins,
        find_growth_units=find_growth_units,
        inventory_items=tuple(inventory_items),
        environment_discoveries=tuple(environment_discoveries),
    )


def _scenario_storage(scenario) -> _ParityStorage:
    storage = _ParityStorage()
    facts = load_catalog_facts()
    if scenario.all_plants_complete:
        plants = [
            Plant(
                f"p{index + 1}",
                species_id,
                species_id.replace("_", " ").title(),
                index if index < 6 else None,
                growth_points=facts.full_bloom_growth,
                completed_on=storage.day,
            )
            for index, species_id in enumerate(facts.species_ids)
        ]
        storage.state.plants = plants
        storage.state.active_plant_id = plants[0].plant_id
        storage.state.active_plant_periods = [
            ActivePlantPeriod(storage.day, plants[0].plant_id, storage.now_ms - 1_000)
        ]
        storage.state.unlocked_species = list(facts.species_ids)
        storage.state.unlocked_slots = 6
        # These plants model opening state for the focused trace.  Their
        # already-applied Growth is not newly generated by a committed event,
        # so it must not be fabricated into the lifetime event counters.
        # The accelerated kernel records this separately as opening plant
        # Growth; production parity compares committed-event totals here.
        if scenario.landmark_mastery_spending:
            storage.state.active_growth_target_type = "landmark"
            storage.state.active_growth_target_id = "garden_landmark"
            storage.state.active_growth_target_activation_identity = (
                "parity-active-landmark"
            )
    if scenario.all_environments_owned:
        feature_ids = {"firefly_lantern", "prism_trellis"}
        storage.state.inventory["garden_features"] = list(dict.fromkeys((
            *storage.state.inventory["garden_features"],
            *(
                item for item in facts.environment_discovery_ids
                if item in feature_ids
            ),
        )))
        storage.state.inventory["scenery"] = list(dict.fromkeys((
            *storage.state.inventory["scenery"],
            *(
                item for item in facts.environment_discovery_ids
                if item not in feature_ids
            ),
        )))
        storage.state.lifetime_economy_aggregates.environment_discoveries = {
            item_id: 1 for item_id in facts.environment_discovery_ids
        }
    return storage


def _durable_answer_payload(
    *,
    scheduler_day: str = "2026-08-30",
    revlog_id: int = 1_788_100_000_001,
    card_id: int = 42,
    serial: int = 1,
    historical_sync: bool = False,
) -> dict[str, object]:
    lineage = f"v1|{scheduler_day}|{card_id}|{serial}"
    payload: dict[str, object] = {
        "queue": 2,
        "ease": 3,
        "revlog_id": revlog_id,
        "answered_at_ms": revlog_id,
        "card_id": card_id,
        "answer_identity": lineage,
        "scheduler_day": scheduler_day,
        "first_answer_of_day": True,
        "day_answer_number": 1,
        "history_counted": True,
        "emit_feedback": False,
    }
    if historical_sync:
        payload.update({
            "historical_sync": True,
            "environment_growth_known": True,
            "correlation_id": f"durable-sync:{revlog_id}",
        })
    return payload


def run_durable_persistence_checks() -> dict[str, object]:
    """Exercise real SQLite durability without claiming kernel equivalence.

    These cases prove exact production state across commit/restart, duplicate
    delivery, permanent request replay, rollback, and undo lineage. The
    top-level parity result remains fail-closed until the accelerated adapter
    independently covers the same behaviors.
    """

    checkpoints: list[dict[str, object]] = []
    trace_prefix: list[dict[str, object]] = []

    def record_checkpoint(
        case_id: str,
        event_identity: str,
        state: dict[str, object],
    ) -> None:
        checkpoints.append({
            "case_id": case_id,
            "event_identity": event_identity,
            "state": state,
        })

    def assert_restart(
        session: _DurableParitySession,
        engine: GardenGameEngine,
        *,
        case_id: str,
        event_identity: str,
    ) -> GardenGameEngine:
        before = dict(project_production_release_state(engine))
        record_checkpoint(case_id, event_identity + ":before", before)
        trace_prefix.append({
            "case_id": case_id,
            "event_identity": event_identity,
            "operation": "close_and_reopen_sqlite",
        })
        restarted = session.restart()
        after = dict(project_production_release_state(restarted))
        assert_release_state_parity(
            before,
            after,
            event_identity=event_identity,
            trace_prefix=trace_prefix,
        )
        record_checkpoint(case_id, event_identity + ":after", after)
        return restarted

    with TemporaryDirectory(prefix="anki-garden-parity-") as temporary:
        root = Path(temporary)

        reward_state = deepcopy(_ParityStorage().state)
        reward_state.garden_cycle_remainder = 4
        reward_state.garden_cycle_history_complete = True
        reward_state.garden_cycle_migration_version = STATE_VERSION
        reward_session = _DurableParitySession(root / "reward", reward_state)
        try:
            engine = reward_session.engine()
            engine.observe_due_start(DueObligationStatus(review_count=1))
            answer_payload = _durable_answer_payload()
            trace_prefix.append({
                "case_id": "reward_duplicate_restart",
                "event_identity": "reward:answer",
                "operation": "register_review",
                "payload": dict(answer_payload),
            })
            award = engine.register_review(answer_payload)
            if award.total_growth != 10:
                raise AssertionError("durable answer did not grant exact base Growth")
            trace_prefix.append({
                "case_id": "reward_duplicate_restart",
                "event_identity": "reward:fifth_completion",
                "operation": "evaluate_today_cards",
                "remaining_due": 0,
            })
            completed, _message = engine.evaluate_today_cards(
                DueObligationStatus(),
                record_completed_delta=True,
                emit_feedback=False,
            )
            if not completed or engine.state.garden_cycle_remainder != 0:
                raise AssertionError("durable fifth completion did not close its cycle")
            first_revlog_id = int(answer_payload["revlog_id"])
            lineage = str(answer_payload["answer_identity"])
            reward_session.review_history.append(HistoricalReviewEntry(
                revlog_id=first_revlog_id,
                card_id=int(answer_payload["card_id"]),
                ease=3,
                interval=1,
                last_interval=0,
                factor=2_500,
                response_time_ms=500,
                review_type=1,
                answer_ms=first_revlog_id,
                scheduler_day="2026-08-30",
                card_day_ordinal=1,
                answer_identity=lineage,
            ))
            committed = dict(project_production_release_state(engine))
            committed_plant = committed["plant_exact_growth_units"][0]
            if (
                committed_plant["completion_cards"] != 1
                or committed_plant["completion_active_days"] != 1
            ):
                raise AssertionError(
                    "pre-bloom completion pacing counters were not recorded"
                )
            if "completion_cycle_5" not in committed["coin_source_ids"]:
                raise AssertionError("durable Garden Cycle ledger source is absent")
            if (
                "completion_cycle_5:2026-08-30"
                not in committed["reward_identities"]
            ):
                raise AssertionError("durable Garden Cycle identity is absent")
            engine = assert_restart(
                reward_session,
                engine,
                case_id="reward_duplicate_restart",
                event_identity="reward:restart",
            )

            before_duplicate = dict(project_production_release_state(engine))
            trace_prefix.append({
                "case_id": "reward_duplicate_restart",
                "event_identity": "reward:duplicate_delivery",
                "operation": "register_review",
                "payload": dict(answer_payload),
            })
            duplicate = engine.register_review(dict(answer_payload))
            if duplicate.total_growth != 0:
                raise AssertionError("duplicate answer granted Growth")
            after_duplicate = dict(project_production_release_state(engine))
            assert_release_state_parity(
                before_duplicate,
                after_duplicate,
                event_identity="reward:duplicate_delivery",
                trace_prefix=trace_prefix,
            )
            record_checkpoint(
                "reward_duplicate_restart",
                "reward:duplicate_delivery",
                after_duplicate,
            )

            reward_session.review_history.clear()
            trace_prefix.append({
                "case_id": "undo_reanswer",
                "event_identity": "undo:remove_first_answer",
                "operation": "record_review_undo",
                "undo_at_ms": first_revlog_id + 100,
            })
            if not engine.record_review_undo(undo_at_ms=first_revlog_id + 100):
                raise AssertionError("durable undo did not identify its lineage")
            engine = assert_restart(
                reward_session,
                engine,
                case_id="undo_reanswer",
                event_identity="undo:restart_with_hint",
            )
            older_sync = _durable_answer_payload(
                revlog_id=first_revlog_id + 50,
                historical_sync=True,
            )
            trace_prefix.append({
                "case_id": "undo_reanswer",
                "event_identity": "undo:older_sync_alias",
                "operation": "register_review",
                "payload": dict(older_sync),
            })
            if engine.register_review(older_sync).total_growth != 0:
                raise AssertionError("older synced alias rerolled an undone answer")
            replacement = _durable_answer_payload(
                revlog_id=first_revlog_id + 100,
            )
            trace_prefix.append({
                "case_id": "undo_reanswer",
                "event_identity": "undo:replacement_alias",
                "operation": "register_review",
                "payload": dict(replacement),
            })
            if engine.register_review(replacement).total_growth != 0:
                raise AssertionError("replacement alias regranted consumed Growth")
            final_undo = dict(project_production_release_state(engine))
            if final_undo["undo_lineage"]["pending_reanswers"]:
                raise AssertionError("replacement alias did not clear undo hint")
            engine = assert_restart(
                reward_session,
                engine,
                case_id="undo_reanswer",
                event_identity="undo:restart_after_reanswer",
            )
        finally:
            reward_session.close()

        purchase_state = deepcopy(_ParityStorage().state)
        purchase_state.currency_balance = 1_000
        purchase_session = _DurableParitySession(
            root / "purchase", purchase_state
        )
        try:
            engine = purchase_session.engine()
            stale_request = PurchaseRequest.from_quote(
                engine.quote_purchase(
                    PurchaseKind.GROWTH_CHARGE,
                    "growth_charge_standard",
                    target_id="p1",
                ),
                request_id=str(uuid.uuid5(
                    uuid.NAMESPACE_URL, "anki-garden:parity:stale-purchase"
                )),
            )
            request = PurchaseRequest.from_quote(
                engine.quote_purchase(
                    PurchaseKind.GROWTH_CHARGE,
                    "growth_charge_small",
                    target_id="p1",
                ),
                request_id=str(uuid.uuid5(
                    uuid.NAMESPACE_URL, "anki-garden:parity:purchase"
                )),
            )
            trace_prefix.append({
                "case_id": "purchase_idempotency",
                "event_identity": "purchase:fresh",
                "operation": "confirm_purchase",
                "request_id": request.request_id,
                "item_id": request.item_id,
            })
            outcome = engine.confirm_purchase(request)
            if outcome.status is not PurchaseStatus.SUCCESS:
                raise AssertionError("durable purchase did not commit")
            committed = dict(project_production_release_state(engine))
            trace_prefix.append({
                "case_id": "purchase_idempotency",
                "event_identity": "purchase:repeat",
                "operation": "confirm_purchase",
                "request_id": request.request_id,
            })
            replay = engine.confirm_purchase(request)
            if replay != outcome:
                raise AssertionError("same-process purchase replay changed outcome")
            assert_release_state_parity(
                committed,
                dict(project_production_release_state(engine)),
                event_identity="purchase:repeat",
                trace_prefix=trace_prefix,
            )
            engine = assert_restart(
                purchase_session,
                engine,
                case_id="purchase_idempotency",
                event_identity="purchase:restart",
            )
            if engine.confirm_purchase(request) != outcome:
                raise AssertionError("restarted purchase replay changed outcome")
            assert_release_state_parity(
                committed,
                dict(project_production_release_state(engine)),
                event_identity="purchase:repeat_after_restart",
                trace_prefix=trace_prefix,
            )

            # Remove the bounded convenience history. The SQLite idempotency
            # record must remain sufficient to replay the exact outcome.
            purchase_session.storage.state.completed_purchase_requests = []
            purchase_session.storage.save()
            engine = purchase_session.restart()
            after_prune = dict(project_production_release_state(engine))
            if engine.confirm_purchase(request) != outcome:
                raise AssertionError("pruned purchase replay changed outcome")
            assert_release_state_parity(
                after_prune,
                dict(project_production_release_state(engine)),
                event_identity="purchase:repeat_after_history_prune",
                trace_prefix=trace_prefix,
            )
            before_stale = dict(project_production_release_state(engine))
            trace_prefix.append({
                "case_id": "purchase_idempotency",
                "event_identity": "purchase:stale_quote",
                "operation": "confirm_purchase",
                "request_id": stale_request.request_id,
            })
            stale = engine.confirm_purchase(stale_request)
            if stale.status is not PurchaseStatus.STALE_BALANCE:
                raise AssertionError("stale purchase quote was not rejected")
            assert_release_state_parity(
                before_stale,
                dict(project_production_release_state(engine)),
                event_identity="purchase:stale_quote",
                trace_prefix=trace_prefix,
            )
            record_checkpoint(
                "purchase_idempotency",
                "purchase:final",
                dict(project_production_release_state(engine)),
            )
        finally:
            purchase_session.close()

        failure_state = deepcopy(_ParityStorage().state)
        failure_state.currency_balance = 500
        failure_session = _DurableParitySession(root / "failure", failure_state)
        try:
            engine = failure_session.engine()
            request = PurchaseRequest.from_quote(
                engine.quote_purchase(
                    PurchaseKind.GROWTH_CHARGE,
                    "growth_charge_small",
                    target_id="p1",
                ),
                request_id=str(uuid.uuid5(
                    uuid.NAMESPACE_URL, "anki-garden:parity:failed-persistence"
                )),
            )
            before_failure = dict(project_production_release_state(engine))
            failure_session.storage.fail_next_save = True
            trace_prefix.append({
                "case_id": "failed_persistence",
                "event_identity": "purchase:failed_persistence",
                "operation": "confirm_purchase_with_injected_save_failure",
                "request_id": request.request_id,
            })
            game_logger = logging.getLogger("ankigarden.game")
            logger_was_disabled = game_logger.disabled
            game_logger.disabled = True
            try:
                failed = engine.confirm_purchase(request)
            finally:
                game_logger.disabled = logger_was_disabled
            if failed.status is not PurchaseStatus.PERSISTENCE_FAILURE:
                raise AssertionError("injected persistence failure was not reported")
            if failure_session.storage.reward_ledger_has_staged_writes():
                raise AssertionError("failed persistence retained staged ledger rows")
            assert_release_state_parity(
                before_failure,
                dict(project_production_release_state(engine)),
                event_identity="purchase:failed_persistence",
                trace_prefix=trace_prefix,
            )
            engine = assert_restart(
                failure_session,
                engine,
                case_id="failed_persistence",
                event_identity="purchase:restart_after_failure",
            )
        finally:
            failure_session.close()

        insufficient_state = deepcopy(_ParityStorage().state)
        insufficient_session = _DurableParitySession(
            root / "insufficient", insufficient_state
        )
        try:
            engine = insufficient_session.engine()
            quote = engine.quote_purchase(
                PurchaseKind.GROWTH_CHARGE,
                "growth_charge_small",
                target_id="p1",
            )
            request = PurchaseRequest.from_quote(
                quote,
                request_id=str(uuid.uuid5(
                    uuid.NAMESPACE_URL, "anki-garden:parity:insufficient"
                )),
            )
            before = dict(project_production_release_state(engine))
            trace_prefix.append({
                "case_id": "insufficient_coin_purchase",
                "event_identity": "purchase:insufficient_coins",
                "operation": "confirm_purchase",
                "request_id": request.request_id,
            })
            outcome = engine.confirm_purchase(request)
            if outcome.status is not PurchaseStatus.INSUFFICIENT_COINS:
                raise AssertionError("insufficient purchase was not rejected")
            assert_release_state_parity(
                before,
                dict(project_production_release_state(engine)),
                event_identity="purchase:insufficient_coins",
                trace_prefix=trace_prefix,
            )
            record_checkpoint(
                "insufficient_coin_purchase",
                "purchase:insufficient_coins",
                before,
            )
        finally:
            insufficient_session.close()

    encoded = json.dumps(
        checkpoints,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    trace_encoded = json.dumps(
        trace_prefix,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return {
        "status": "pass",
        "storage_adapter": "GardenStorage+RewardLedger(SQLite)",
        "state_schema_version": STATE_VERSION,
        "ledger_schema_version": LEDGER_SCHEMA_VERSION,
        "case_count": 5,
        "checkpoint_count": len(checkpoints),
        "behaviors": [
            "duplicate_sync_delivery",
            "application_restart",
            "fifth_garden_cycle_completion",
            "insufficient_coin_purchase",
            "stale_purchase_quote",
            "failed_persistence_rollback",
            "repeated_request_identity",
            "undo_and_reanswer_lineage",
        ],
        "compared_state_fields": list(REQUIRED_PARITY_STATE_FIELDS),
        "nontrivial_state_fields": [
            "garden_coin_wallet",
            "coin_ledger_entries",
            "coin_source_ids",
            "plant_exact_growth_units",
            "achievement_ownership",
            "garden_cycle_remainder",
            "todays_cards_completion_state",
            "daily_loadout_snapshot",
            "reward_identities",
            "purchase_identities",
            "undo_lineage",
            "state_revision",
        ],
        "checkpoint_sha256": sha256(encoded).hexdigest(),
        "trace_manifest_sha256": sha256(trace_encoded).hexdigest(),
        "kernel_equivalence_claimed": False,
        "pre_bloom_completion_counters_preserved": True,
        "note": (
            "Production durability passed on real temporary SQLite storage. "
            "These checks do not substitute for accelerated-kernel parity."
        ),
    }


def _project_event_record(record) -> dict[str, object]:
    if record is None:
        return {}
    return {
        "event_key": str(record.event_key),
        "event_kind": str(record.event_kind),
        "source_id": str(record.source_id),
        "sink_id": str(record.sink_id),
        "coins_spent": int(record.coins_spent),
        "item_id": str(record.item_id),
        "quantity": int(record.quantity),
        "growth_flow_kind": str(record.growth_flow_kind),
        "growth_generated_units": int(record.growth_generated_units),
        "growth_applied_to_plants_units": int(
            record.growth_applied_to_plants_units
        ),
        "growth_routed_to_storage_units_lifetime": int(
            record.growth_routed_to_storage_units_lifetime
        ),
        "stored_growth_balance_delta_units": int(
            record.stored_growth_balance_delta_units
        ),
        "growth_contributed_to_landmarks_units": int(
            record.growth_contributed_to_landmarks_units
        ),
        "growth_contributed_to_mastery_units": int(
            record.growth_contributed_to_mastery_units
        ),
        "growth_contributed_to_legacy_units": int(
            record.growth_contributed_to_legacy_units
        ),
        "project_allocations": dict(sorted(
            (
                str(target_key), int(units)
            )
            for target_key, units in dict(
                record.metric_deltas or {}
            ).get("project_allocations", {}).items()
        )),
    }


def _project_coin_deltas(state: GardenState) -> tuple[tuple[str, int, int], ...]:
    return tuple(
        (str(row.source), int(row.delta), int(row.balance))
        for row in state.currency_transactions
    )


def _opening_reserve_state(
    *,
    stored_units: int,
    wallet: int,
    full_bloom_species: Sequence[str] = ("bonsai",),
) -> GardenState:
    state = deepcopy(_ParityStorage().state)
    species = tuple(str(item) for item in full_bloom_species)
    state.plants = [
        Plant(
            f"p{index + 1}",
            species_id,
            species_id.replace("_", " ").title(),
            index if index < 6 else None,
            growth_points=35_000,
            completed_on=state.daily_stats.day,
        )
        for index, species_id in enumerate(species)
    ]
    state.active_plant_id = None
    state.active_plant_periods = [
        ActivePlantPeriod(state.daily_stats.day, None, 1_788_100_000_000)
    ]
    state.unlocked_species = list(species)
    state.currency_balance = max(0, int(wallet))
    state.stored_growth_balance_units = max(0, int(stored_units))
    state.stored_growth_opening_balance_units = max(0, int(stored_units))
    state.stored_growth_opening_balance_source = (
        "schema_27_migration_preserved_balance"
    )
    state.stored_growth_opening_balance_identity = (
        "migration:schema27:stored-growth-opening"
    )
    return state


def run_focused_kernel_equivalence_checks() -> dict[str, object]:
    """Pair focused production commits with an independent pure-domain oracle."""

    recorder = _FocusedOracleEvidence()
    with TemporaryDirectory(prefix="anki-garden-focused-parity-") as temporary:
        root = Path(temporary)

        # Full Bloom and earned beds are calculated from frozen stage and
        # achievement contracts, then compared to one durable production event.
        bloom_state = deepcopy(_ParityStorage().state)
        bloom_state.plants[0].growth_points = 34_990
        bloom_session = _DurableParitySession(root / "full-bloom", bloom_state)
        try:
            engine = bloom_session.engine()
            initial_revision = bloom_session.storage._ledger_revision
            engine.observe_due_start(DueObligationStatus(review_count=1))
            award = engine.register_review(_durable_answer_payload())
            actual = dict(project_production_release_state(engine))
            full_bloom_stage = STAGES[-1]
            full_bloom_coins = full_bloom_stage.checkpoint_coin_rewards[-1]
            expected_plant = ({
                "plant_id": "p1",
                "growth_units": full_bloom_stage.threshold_growth * 100,
                "stage": "rare",
                "checkpoint_flags": (),
                "stage_flags": ("rare",),
                "slot_index": 0,
                "fully_grown": True,
                "completion_cards": 1,
                "completion_active_days": 1,
            },)
            expected = {
                "garden_coin_wallet": 4 + full_bloom_coins,
                "coin_deltas": (
                    ("first_eligible_answer", 4, 4),
                    (
                        "plant_milestone",
                        full_bloom_coins,
                        4 + full_bloom_coins,
                    ),
                ),
                "plant_exact_growth_units": expected_plant,
                "stage_flags": {"p1": ("rare",)},
                "checkpoint_flags": {"p1": ()},
                "bed_ownership": {
                    "unlocked_slots": 4,
                    "earned_bed_unlocks": (3, 4),
                },
                "achievement_ownership": (
                    "first_canopy",
                    "first_full_bloom",
                ),
                "consumable_inventory": {
                    **{
                        item.consumable_id.value: 0 for item in CONSUMABLES
                    },
                    "growth_charge_small": 1,
                },
                "reward_identities": (
                    "achievement:first_canopy",
                    "achievement:first_full_bloom",
                    "daily_activity:2026-08-30",
                    "full_bloom:p1",
                    "stage:p1:rare",
                ),
                "state_revision": initial_revision + 2,
                "growth_delta": {
                    "requested_units": 1_000,
                    "applied_units": 1_000,
                    "stored_units": 0,
                    "project_units": 0,
                },
            }
            actual.update({
                "coin_deltas": _project_coin_deltas(engine.state),
                "growth_delta": {
                    "requested_units": int(award.total_growth_units),
                    "applied_units": int(award.applied_growth_units),
                    "stored_units": int(award.stored_growth_units),
                    "project_units": sum((
                        int(award.landmark_growth_units),
                        int(award.mastery_growth_units),
                        int(award.legacy_growth_units),
                    )),
                },
            })
            recorder.compare(
                case_id="full_bloom_and_bed",
                event_identity="focused:full-bloom:p1",
                behavior="full_bloom",
                expected=expected,
                actual=actual,
                state_fields=(
                    "garden_coin_wallet",
                    "coin_ledger_entries",
                    "coin_source_ids",
                    "plant_exact_growth_units",
                    "stage_flags",
                    "checkpoint_flags",
                    "bed_ownership",
                    "achievement_ownership",
                    "consumable_inventory",
                    "reward_identities",
                    "state_revision",
                ),
                operation="eligible answer crosses the Full Bloom threshold",
            )
            # The same committed event is the canonical first-Mature and
            # first-Full-Bloom achievement evaluation, so bed coverage is tied
            # to the exact paired checkpoint rather than metadata.
            recorder.behavior_fields["bed_achievement_unlock"] = set(
                recorder.behavior_fields["full_bloom"]
            )
        finally:
            bloom_session.close()

        project_state = _opening_reserve_state(
            stored_units=100_000_000,
            wallet=10_000,
        )
        project_session = _DurableParitySession(root / "projects", project_state)
        try:
            engine = project_session.engine()
            revision = project_session.storage._ledger_revision
            oracle = build_growth_projects_snapshot(
                state_revision=revision,
                stored_balance_units=100_000_000,
                wallet_balance_coins=10_000,
                full_bloom_species=("bonsai",),
            )

            def apply_project(
                request: GrowthProjectRequest,
                *,
                behavior: str,
                event_identity: str,
                state_fields: Sequence[str],
            ):
                nonlocal oracle
                expected_outcome = project_growth_project_request(
                    oracle, request
                )
                quote = engine.quote_growth_project(request)
                actual_outcome = engine.confirm_growth_project(
                    request, GrowthProjectConfirmation.from_quote(quote)
                )
                oracle = expected_outcome.snapshot
                actual_state = dict(project_production_release_state(engine))
                event_record = project_session.storage._reward_ledger.economy_event(
                    expected_outcome.ledger_identity
                )
                expected_event = {
                    "event_key": expected_outcome.ledger_identity,
                    "event_kind": f"growth_project_{request.action.value}",
                    "source_id": "",
                    "sink_id": request.target.target_id,
                    "coins_spent": expected_outcome.coins_spent,
                    "item_id": "",
                    "quantity": 0,
                    "growth_flow_kind": (
                        "manual_contribution"
                        if request.action is GrowthProjectAction.CONTRIBUTE
                        else "claim"
                        if request.action is GrowthProjectAction.CLAIM
                        else ""
                    ),
                    "growth_generated_units": 0,
                    "growth_applied_to_plants_units": 0,
                    "growth_routed_to_storage_units_lifetime": 0,
                    "stored_growth_balance_delta_units": (
                        expected_outcome.stored_balance_delta_units
                    ),
                    "growth_contributed_to_landmarks_units": (
                        expected_outcome.allocation.units
                        if expected_outcome.allocation is not None
                        and request.target.target_type
                        is GrowthTargetType.LANDMARK else 0
                    ),
                    "growth_contributed_to_mastery_units": (
                        expected_outcome.allocation.units
                        if expected_outcome.allocation is not None
                        and request.target.target_type
                        is GrowthTargetType.MASTERY else 0
                    ),
                    "growth_contributed_to_legacy_units": (
                        expected_outcome.allocation.units
                        if expected_outcome.allocation is not None
                        and request.target.target_type
                        is GrowthTargetType.LEGACY else 0
                    ),
                    "project_allocations": (
                        {
                            (
                                f"{expected_outcome.allocation.target_type.value}:"
                                f"{expected_outcome.allocation.target_id}"
                            ): expected_outcome.allocation.units
                        }
                        if expected_outcome.allocation is not None else {}
                    ),
                }
                if request.action is GrowthProjectAction.CLAIM:
                    expected_event["item_id"] = request.claim_id
                    expected_event["quantity"] = 1
                expected = {
                    "garden_coin_wallet": oracle.wallet_balance_coins,
                    "stored_growth_balance": oracle.stored_balance_units,
                    "landmark_funding": (
                        oracle.landmark_track.growth_units_funded
                    ),
                    "landmark_claims": sum(
                        tier.claimed for tier in oracle.landmark_track.tiers
                    ),
                    "mastery_funding_by_species": {
                        species_id: track.growth_units_funded
                        for species_id, track in (
                            oracle.mastery_tracks_by_species
                        )
                    },
                    "mastery_claims": {
                        species_id: track.highest_claimed_id
                        for species_id, track in (
                            oracle.mastery_tracks_by_species
                        )
                        if track.highest_claimed_id
                    },
                    "garden_legacy_progress": {
                        "level": oracle.legacy_track.level,
                        "progress_units": (
                            oracle.legacy_track.level_progress_units
                        ),
                    },
                    "state_revision": oracle.state_revision,
                    "resource_delta": {
                        "stored_growth_units": (
                            expected_outcome.stored_balance_delta_units
                        ),
                        "garden_coins": -expected_outcome.coins_spent,
                        "allocation": (
                            expected_outcome.allocation.to_dict()
                            if expected_outcome.allocation else None
                        ),
                    },
                    "ledger_event": expected_event,
                }
                actual_state.update({
                    "resource_delta": {
                        "stored_growth_units": (
                            actual_outcome.stored_balance_delta_units
                        ),
                        "garden_coins": -actual_outcome.coins_spent,
                        "allocation": (
                            actual_outcome.allocation.to_dict()
                            if actual_outcome.allocation else None
                        ),
                    },
                    "ledger_event": _project_event_record(event_record),
                })
                recorder.compare(
                    case_id="cumulative_projects",
                    event_identity=event_identity,
                    behavior=behavior,
                    expected=expected,
                    actual=actual_state,
                    state_fields=state_fields,
                    operation=(
                        f"{request.action.value} "
                        f"{request.target.target_type.value}:"
                        f"{request.target.target_id}"
                    ),
                )
                return expected_outcome, actual_outcome

            landmark = GrowthTargetRef(
                GrowthTargetType.LANDMARK, "garden_landmark"
            )
            apply_project(
                GrowthProjectRequest(
                    str(uuid.UUID(int=101)),
                    oracle.state_revision,
                    GrowthProjectAction.ACTIVATE,
                    landmark,
                ),
                behavior="landmark_contribution_and_claim",
                event_identity="focused:landmark:activate",
                state_fields=("state_revision",),
            )
            apply_project(
                GrowthProjectRequest(
                    str(uuid.UUID(int=102)),
                    oracle.state_revision,
                    GrowthProjectAction.CONTRIBUTE,
                    landmark,
                    ContributionMode.SPECIFIED,
                    10_000_000,
                ),
                behavior="landmark_contribution_and_claim",
                event_identity="focused:landmark:fund-two-tiers",
                state_fields=(
                    "stored_growth_balance",
                    "landmark_funding",
                    "state_revision",
                ),
            )
            apply_project(
                GrowthProjectRequest(
                    str(uuid.UUID(int=103)),
                    oracle.state_revision,
                    GrowthProjectAction.CLAIM,
                    landmark,
                    claim_id="mossy_stone_path",
                ),
                behavior="landmark_contribution_and_claim",
                event_identity="focused:landmark:claim-tier-1",
                state_fields=(
                    "garden_coin_wallet",
                    "coin_ledger_entries",
                    "coin_source_ids",
                    "landmark_funding",
                    "landmark_claims",
                    "state_revision",
                ),
            )
            apply_project(
                GrowthProjectRequest(
                    str(uuid.UUID(int=107)),
                    oracle.state_revision,
                    GrowthProjectAction.CLAIM,
                    landmark,
                    claim_id="birdbath_terrace",
                ),
                behavior="landmark_contribution_and_claim",
                event_identity="focused:landmark:claim-tier-2",
                state_fields=(
                    "garden_coin_wallet",
                    "coin_ledger_entries",
                    "coin_source_ids",
                    "landmark_funding",
                    "landmark_claims",
                    "state_revision",
                ),
            )

            mastery = GrowthTargetRef(GrowthTargetType.MASTERY, "bonsai")
            apply_project(
                GrowthProjectRequest(
                    str(uuid.UUID(int=104)),
                    oracle.state_revision,
                    GrowthProjectAction.ACTIVATE,
                    mastery,
                ),
                behavior="mastery_contribution_and_claim",
                event_identity="focused:mastery:activate",
                state_fields=("state_revision",),
            )
            apply_project(
                GrowthProjectRequest(
                    str(uuid.UUID(int=105)),
                    oracle.state_revision,
                    GrowthProjectAction.CONTRIBUTE,
                    mastery,
                    ContributionMode.SPECIFIED,
                    2_500_000,
                ),
                behavior="mastery_contribution_and_claim",
                event_identity="focused:mastery:fund-bronze",
                state_fields=(
                    "stored_growth_balance",
                    "mastery_funding_by_species",
                    "state_revision",
                ),
            )
            apply_project(
                GrowthProjectRequest(
                    str(uuid.UUID(int=106)),
                    oracle.state_revision,
                    GrowthProjectAction.CLAIM,
                    mastery,
                    claim_id="bronze",
                ),
                behavior="mastery_contribution_and_claim",
                event_identity="focused:mastery:claim-bronze",
                state_fields=(
                    "garden_coin_wallet",
                    "coin_ledger_entries",
                    "coin_source_ids",
                    "mastery_funding_by_species",
                    "mastery_claims",
                    "state_revision",
                ),
            )
        finally:
            project_session.close()

        consumable_state = deepcopy(_ParityStorage().state)
        consumable_state.consumables.update({
            "booster_potion": 1,
            "fertilizer_basic": 2,
            "fertilizer_quality": 1,
        })
        consumable_session = _DurableParitySession(
            root / "consumables", consumable_state
        )
        try:
            engine = consumable_session.engine()
            revision = consumable_session.storage._ledger_revision
            catalog_consumables = {
                item.consumable_id.value: item for item in CONSUMABLES
            }
            inventory = {
                item_id: 0 for item_id in catalog_consumables
            }
            inventory.update({
                "booster_potion": 1,
                "fertilizer_basic": 2,
                "fertilizer_quality": 1,
            })
            fertilizer_active: list[tuple[object, ...]] = []
            fertilizer_queued: list[tuple[object, ...]] = []
            booster_active: list[tuple[object, ...]] = []
            uuid_values = [uuid.UUID(int=index) for index in range(401, 405)]

            def consumable_event(event_key: str, item_id: str) -> dict[str, object]:
                return {
                    "event_key": f"consumable-use:{event_key}",
                    "event_kind": (
                        "booster_use" if item_id == "booster_potion"
                        else "fertilizer_use"
                    ),
                    "source_id": item_id,
                    "sink_id": "",
                    "coins_spent": 0,
                    "item_id": item_id,
                    "quantity": 1,
                    "growth_flow_kind": "",
                    "growth_generated_units": 0,
                    "growth_applied_to_plants_units": 0,
                    "growth_routed_to_storage_units_lifetime": 0,
                    "stored_growth_balance_delta_units": 0,
                    "growth_contributed_to_landmarks_units": 0,
                    "growth_contributed_to_mastery_units": 0,
                    "growth_contributed_to_legacy_units": 0,
                    "project_allocations": {},
                }

            def compare_consumable(
                *,
                behavior: str,
                event_identity: str,
                item_id: str,
                source_event_key: str,
                disposition: str,
                card_queue_delta: int,
            ) -> None:
                actual_state = dict(project_production_release_state(engine))
                record = consumable_session.storage._reward_ledger.economy_event(
                    f"consumable-use:{source_event_key}"
                )
                expected = {
                    "consumable_inventory": dict(sorted(inventory.items())),
                    "fertilizer_queues": ({
                        "plant_id": "p1",
                        "active": tuple(fertilizer_active),
                        "queued": tuple(fertilizer_queued),
                    },),
                    "booster_remaining_cards": ({
                        "plant_id": "p1",
                        "active": tuple(booster_active),
                        "queued": (),
                    },),
                    "state_revision": revision,
                    "stored_item_result": {
                        "disposition": disposition,
                        "card_queue_delta": card_queue_delta,
                        "expires_at_ms": None,
                    },
                    "ledger_event": consumable_event(
                        source_event_key, item_id
                    ),
                }
                stored_result = (
                    engine.last_fertilizer_stored_item_result
                    if item_id.startswith("fertilizer_") else None
                )
                actual_state.update({
                    "stored_item_result": {
                        "disposition": (
                            str(stored_result.disposition.value)
                            if stored_result is not None else ""
                        ),
                        "card_queue_delta": (
                            int(stored_result.card_queue_delta)
                            if stored_result is not None else 0
                        ),
                        "expires_at_ms": (
                            stored_result.expires_at_ms
                            if stored_result is not None else None
                        ),
                    },
                    "ledger_event": _project_event_record(record),
                })
                recorder.compare(
                    case_id="card_counted_consumables",
                    event_identity=event_identity,
                    behavior=behavior,
                    expected=expected,
                    actual=actual_state,
                    state_fields=(
                        "consumable_inventory",
                        "fertilizer_queues",
                        "booster_remaining_cards",
                        "state_revision",
                    ),
                    operation=f"activate {item_id}",
                )

            with patch("ankigarden.game.uuid.uuid4", side_effect=uuid_values):
                booster_key = f"booster:p1:{uuid_values[0].hex}"
                ok, _message = engine.use_booster_potion("p1")
                if not ok:
                    raise AssertionError("focused Booster activation failed")
                revision += 1
                inventory["booster_potion"] -= 1
                booster = catalog_consumables["booster_potion"]
                booster_active.append((
                    "booster_potion",
                    booster.growth_per_card * 100,
                    booster.card_count,
                    booster.card_count,
                    booster_key,
                ))
                compare_consumable(
                    behavior="booster_activation",
                    event_identity="focused:booster:activate",
                    item_id="booster_potion",
                    source_event_key=booster_key,
                    disposition="",
                    card_queue_delta=0,
                )

                for index, (tier, expected_disposition) in enumerate((
                    ("basic", "use"),
                    ("basic", "queue"),
                    ("quality", "queue"),
                ), start=1):
                    item_id = f"fertilizer_{tier}"
                    event_key = f"fertilizer-item:{uuid_values[index].hex}"
                    ok, _message, result = engine.use_fertilizer_item_with_result(
                        "p1", tier=tier
                    )
                    if not ok or result is None:
                        raise AssertionError(
                            f"focused {item_id} activation failed"
                        )
                    revision += 1
                    inventory[item_id] -= 1
                    item = catalog_consumables[item_id]
                    row = (
                        item_id,
                        item.growth_per_card * 100,
                        item.card_count,
                        item.card_count,
                        event_key,
                    )
                    if tier == "quality":
                        fertilizer_queued.append(row)
                    else:
                        fertilizer_active.append(row)
                    compare_consumable(
                        behavior="fertilizer_activation_and_queue_extension",
                        event_identity=(
                            f"focused:fertilizer:{tier}:{index}"
                        ),
                        item_id=item_id,
                        source_event_key=event_key,
                        disposition=expected_disposition,
                        card_queue_delta=item.card_count,
                    )

            # A real close/reopen must preserve both card-counted queues. The
            # pure oracle keeps the same immutable queue rows and inventory.
            engine = consumable_session.restart()
            revision = consumable_session.storage._ledger_revision
            restarted = dict(project_production_release_state(engine))
            recorder.compare(
                case_id="card_counted_consumables",
                event_identity="focused:consumables:restart",
                behavior="application_restart",
                expected={
                    "consumable_inventory": dict(sorted(inventory.items())),
                    "fertilizer_queues": ({
                        "plant_id": "p1",
                        "active": tuple(fertilizer_active),
                        "queued": tuple(fertilizer_queued),
                    },),
                    "booster_remaining_cards": ({
                        "plant_id": "p1",
                        "active": tuple(booster_active),
                        "queued": (),
                    },),
                    "state_revision": revision,
                },
                actual=restarted,
                state_fields=(
                    "consumable_inventory",
                    "fertilizer_queues",
                    "booster_remaining_cards",
                    "state_revision",
                ),
                operation="close and reopen card-counted effect ledger",
            )
        finally:
            consumable_session.close()

        # Card cadence is computed from the same frozen effect definitions as
        # the accelerated kernel, not from a production preview.
        counter_state = deepcopy(_ParityStorage().state)
        counter_state.inventory["garden_features"].append("wind_chime")
        counter_state.inventory["scenery"].append("spring")
        counter_state.loadout.active_garden_bonus_id = "wind_chime"
        counter_state.loadout.active_scenery_effect_id = "spring"
        counter_state.wind_chime_progress = 9
        counter_session = _DurableParitySession(
            root / "effect-counters", counter_state
        )
        try:
            engine = counter_session.engine()
            initial_revision = counter_session.storage._ledger_revision
            engine.observe_due_start(DueObligationStatus(review_count=1))
            award = engine.register_review(_durable_answer_payload())
            actual = dict(project_production_release_state(engine))
            expected = {
                "plant_exact_growth_units": ({
                    "plant_id": "p1",
                    "growth_units": 1_300,
                    "stage": "seed",
                    "checkpoint_flags": (),
                    "stage_flags": (),
                    "slot_index": 0,
                    "fully_grown": False,
                    "completion_cards": 1,
                    "completion_active_days": 1,
                },),
                "garden_bonus_counters": {
                    "wind_chime": 0,
                    "watering_station": 0,
                    "firefly_lantern": 0,
                    "prism_pending_growth_units": 0,
                    "hourglass_completion": 0,
                },
                "daily_loadout_snapshot": {
                    "scheduler_day": "2026-08-30",
                    "garden_feature_id": "wind_chime",
                    "scenery_id": "spring",
                    "locked_at_ms": 1_788_100_000_001,
                },
                "state_revision": initial_revision + 2,
                "growth_delta": {
                    "base_units": 1_000,
                    "garden_bonus_units": 100,
                    "scenery_units": 200,
                    "total_units": 1_300,
                },
            }
            actual["growth_delta"] = {
                "base_units": int(award.base_growth_units),
                "garden_bonus_units": int(award.weather_growth_units),
                "scenery_units": int(award.scenery_growth_units),
                "total_units": int(award.total_growth_units),
            }
            recorder.compare(
                case_id="effect_counters",
                event_identity="focused:wind-chime:tenth-answer",
                behavior="garden_bonus_counters",
                expected=expected,
                actual=actual,
                state_fields=(
                    "plant_exact_growth_units",
                    "garden_bonus_counters",
                    "daily_loadout_snapshot",
                    "state_revision",
                ),
                operation="tenth Wind Chime answer with Spring Scenery",
            )
        finally:
            counter_session.close()

        completion_state = deepcopy(_ParityStorage().state)
        completion_state.inventory["garden_features"].append(
            "herbalist_hourglass"
        )
        completion_state.inventory["scenery"].append("snowy")
        completion_state.loadout.active_garden_bonus_id = (
            "herbalist_hourglass"
        )
        completion_state.loadout.active_scenery_effect_id = "snowy"
        completion_state.hourglass_completion_progress = 29
        completion_state.snow_completion_progress = 1
        completion_session = _DurableParitySession(
            root / "completion-counters", completion_state
        )
        try:
            engine = completion_session.engine()
            initial_revision = completion_session.storage._ledger_revision
            engine.observe_due_start(DueObligationStatus(review_count=1))
            engine.register_review(_durable_answer_payload())
            completed, _message = engine.evaluate_today_cards(
                DueObligationStatus(),
                record_completed_delta=True,
                emit_feedback=False,
            )
            if not completed:
                raise AssertionError("focused Today’s Cards completion failed")
            actual = dict(project_production_release_state(engine))
            inventory = {
                item.consumable_id.value: 0 for item in CONSUMABLES
            }
            inventory["booster_potion"] = 1
            inventory["growth_charge_small"] = 1
            recorder.compare(
                case_id="effect_counters",
                event_identity="focused:completion:hourglass-snowy",
                behavior="scenery_counters",
                expected={
                    "consumable_inventory": dict(sorted(inventory.items())),
                    "garden_bonus_counters": {
                        "wind_chime": 0,
                        "watering_station": 0,
                        "firefly_lantern": 0,
                        "prism_pending_growth_units": 0,
                        "hourglass_completion": 0,
                    },
                    "scenery_counters": {
                        "snow_completion": 0,
                        "full_moon_completion": 0,
                        "prism_released_anki_day_id": "",
                    },
                    "garden_cycle_remainder": 1,
                    "todays_cards_completion_state": {
                        "scheduler_day": "2026-08-30",
                        "status": "complete",
                        "reward_claimed": True,
                        "completed_due_cards": True,
                    },
                    "daily_loadout_snapshot": {
                        "scheduler_day": "2026-08-30",
                        "garden_feature_id": "herbalist_hourglass",
                        "scenery_id": "snowy",
                        "locked_at_ms": 1_788_100_000_001,
                    },
                    "state_revision": initial_revision + 3,
                },
                actual=actual,
                state_fields=(
                    "consumable_inventory",
                    "garden_bonus_counters",
                    "scenery_counters",
                    "garden_cycle_remainder",
                    "todays_cards_completion_state",
                    "daily_loadout_snapshot",
                    "state_revision",
                ),
                operation=(
                    "valid completion advances Hourglass and Snowy counters"
                ),
            )
        finally:
            completion_session.close()

        legacy_state = _opening_reserve_state(
            stored_units=GARDEN_LEGACY_LEVEL_COST_UNITS,
            wallet=0,
            full_bloom_species=CURRENT_CATALOG_SPECIES_ORDER,
        )
        legacy_state.unlocked_slots = 6
        legacy_state.garden_project.landmark_growth_units_funded = (
            LANDMARK_MAX_GROWTH_UNITS
        )
        legacy_state.cultivation_mastery.growth_units_funded_by_species = {
            species_id: MASTERY_MAX_GROWTH_UNITS
            for species_id in CURRENT_CATALOG_SPECIES_ORDER
        }
        legacy_session = _DurableParitySession(root / "legacy", legacy_state)
        try:
            engine = legacy_session.engine()
            oracle = build_growth_projects_snapshot(
                state_revision=legacy_session.storage._ledger_revision,
                stored_balance_units=GARDEN_LEGACY_LEVEL_COST_UNITS,
                wallet_balance_coins=0,
                full_bloom_species=CURRENT_CATALOG_SPECIES_ORDER,
                landmark_growth_units_funded=LANDMARK_MAX_GROWTH_UNITS,
                mastery_growth_units_funded_by_species={
                    species_id: MASTERY_MAX_GROWTH_UNITS
                    for species_id in CURRENT_CATALOG_SPECIES_ORDER
                },
            )
            legacy_target = GrowthTargetRef(
                GrowthTargetType.LEGACY, "garden_legacy"
            )
            for number, action in (
                (501, GrowthProjectAction.ACTIVATE),
                (502, GrowthProjectAction.CONTRIBUTE),
            ):
                request = GrowthProjectRequest(
                    str(uuid.UUID(int=number)),
                    oracle.state_revision,
                    action,
                    legacy_target,
                    (
                        ContributionMode.SPECIFIED
                        if action is GrowthProjectAction.CONTRIBUTE
                        else ContributionMode.NONE
                    ),
                    (
                        GARDEN_LEGACY_LEVEL_COST_UNITS
                        if action is GrowthProjectAction.CONTRIBUTE else 0
                    ),
                )
                expected_outcome = project_growth_project_request(
                    oracle, request
                )
                quote = engine.quote_growth_project(request)
                actual_outcome = engine.confirm_growth_project(
                    request, GrowthProjectConfirmation.from_quote(quote)
                )
                oracle = expected_outcome.snapshot
                event = legacy_session.storage._reward_ledger.economy_event(
                    expected_outcome.ledger_identity
                )
                expected_event = {
                    "event_key": expected_outcome.ledger_identity,
                    "event_kind": f"growth_project_{action.value}",
                    "source_id": "",
                    "sink_id": "garden_legacy",
                    "coins_spent": 0,
                    "item_id": "",
                    "quantity": 0,
                    "growth_flow_kind": (
                        "manual_contribution"
                        if action is GrowthProjectAction.CONTRIBUTE else ""
                    ),
                    "growth_generated_units": 0,
                    "growth_applied_to_plants_units": 0,
                    "growth_routed_to_storage_units_lifetime": 0,
                    "stored_growth_balance_delta_units": (
                        expected_outcome.stored_balance_delta_units
                    ),
                    "growth_contributed_to_landmarks_units": 0,
                    "growth_contributed_to_mastery_units": 0,
                    "growth_contributed_to_legacy_units": (
                        GARDEN_LEGACY_LEVEL_COST_UNITS
                        if action is GrowthProjectAction.CONTRIBUTE else 0
                    ),
                    "project_allocations": (
                        {
                            "legacy:garden_legacy": (
                                GARDEN_LEGACY_LEVEL_COST_UNITS
                            )
                        }
                        if action is GrowthProjectAction.CONTRIBUTE else {}
                    ),
                }
                actual = dict(project_production_release_state(engine))
                actual.update({
                    "ledger_event": _project_event_record(event),
                    "resource_delta": {
                        "stored_growth_units": (
                            actual_outcome.stored_balance_delta_units
                        ),
                        "legacy_growth_units": (
                            actual_outcome.allocation.units
                            if actual_outcome.allocation else 0
                        ),
                        "garden_coins": -actual_outcome.coins_spent,
                    },
                })
                recorder.compare(
                    case_id="garden_legacy",
                    event_identity=f"focused:legacy:{action.value}",
                    behavior="garden_legacy_level",
                    expected={
                        "stored_growth_balance": oracle.stored_balance_units,
                        "garden_legacy_progress": {
                            "level": oracle.legacy_track.level,
                            "progress_units": (
                                oracle.legacy_track.level_progress_units
                            ),
                        },
                        "state_revision": oracle.state_revision,
                        "ledger_event": expected_event,
                        "resource_delta": {
                            "stored_growth_units": (
                                expected_outcome.stored_balance_delta_units
                            ),
                            "legacy_growth_units": (
                                expected_outcome.allocation.units
                                if expected_outcome.allocation else 0
                            ),
                            "garden_coins": -expected_outcome.coins_spent,
                        },
                    },
                    actual=actual,
                    state_fields=(
                        "stored_growth_balance",
                        "garden_legacy_progress",
                        "state_revision",
                    ),
                    operation=f"{action.value} Garden Legacy",
                )
        finally:
            legacy_session.close()

        # Purchase acceptance/rejection is projected from the immutable
        # catalog price and a known opening wallet. The expected state below
        # is not copied from a production quote or post-commit snapshot; only
        # the quote token needed to exercise production's confirm boundary is.
        purchase_state = deepcopy(_ParityStorage().state)
        purchase_state.currency_balance = 1_000
        purchase_session = _DurableParitySession(
            root / "focused-purchase", purchase_state
        )
        try:
            engine = purchase_session.engine()
            initial_revision = purchase_session.storage._ledger_revision
            small_definition = next(
                item for item in CONSUMABLES
                if item.consumable_id.value == "growth_charge_small"
            )
            small_price = int(small_definition.price_coins or 0)
            stale_quote = engine.quote_purchase(
                PurchaseKind.GROWTH_CHARGE,
                "growth_charge_standard",
                target_id="p1",
            )
            request_id = str(uuid.UUID(int=601))
            request = PurchaseRequest.from_quote(
                engine.quote_purchase(
                    PurchaseKind.GROWTH_CHARGE,
                    "growth_charge_small",
                    target_id="p1",
                ),
                request_id=request_id,
            )
            expected_inventory = {
                item.consumable_id.value: 0 for item in CONSUMABLES
            }
            expected_inventory["growth_charge_small"] = 1
            balance_after = 1_000 - small_price
            coin_event_key = f"purchase-request:{request_id}"
            expected_coin_ledger = ({
                "event_key": coin_event_key,
                "transaction_type": "debit",
                "source": "purchase",
                "source_id": coin_event_key,
                "scheduler_day": "2026-08-30",
                "correlation_id": coin_event_key,
                "delta": -small_price,
                "balance": balance_after,
            },)
            expected_purchase_event = {
                "event_key": f"purchase:{request_id}",
                "event_kind": "purchase",
                "source_id": "",
                "sink_id": "growth_charge:growth_charge_small",
                "coins_spent": small_price,
                "item_id": "growth_charge_small",
                "quantity": 1,
                "growth_flow_kind": "",
                "growth_generated_units": 0,
                "growth_applied_to_plants_units": 0,
                "growth_routed_to_storage_units_lifetime": 0,
                "stored_growth_balance_delta_units": 0,
                "growth_contributed_to_landmarks_units": 0,
                "growth_contributed_to_mastery_units": 0,
                "growth_contributed_to_legacy_units": 0,
                "project_allocations": {},
            }
            expected_purchase_state = {
                "garden_coin_wallet": balance_after,
                "coin_ledger_entries": expected_coin_ledger,
                "coin_source_ids": ("purchase",),
                "consumable_inventory": dict(sorted(
                    expected_inventory.items()
                )),
                "purchase_identities": (request_id,),
                "state_revision": initial_revision + 1,
                "outcome": {
                    "status": "success",
                    "amount_spent": small_price,
                    "new_balance": balance_after,
                    "disposition": "inventory",
                },
                "ledger_event": expected_purchase_event,
            }
            outcome = engine.confirm_purchase(request)
            event = purchase_session.storage._reward_ledger.economy_event(
                f"purchase:{request_id}"
            )
            actual = dict(project_production_release_state(engine))
            actual.update({
                "outcome": {
                    "status": outcome.status.value,
                    "amount_spent": outcome.amount_spent,
                    "new_balance": outcome.new_balance,
                    "disposition": outcome.disposition.value,
                },
                "ledger_event": _project_event_record(event),
            })
            recorder.compare(
                case_id="purchase_contract",
                event_identity="focused:purchase:fresh",
                behavior="repeated_request_identity",
                expected=expected_purchase_state,
                actual=actual,
                state_fields=(
                    "garden_coin_wallet",
                    "coin_ledger_entries",
                    "coin_source_ids",
                    "consumable_inventory",
                    "purchase_identities",
                    "state_revision",
                ),
                operation="confirm Small Growth Charge purchase",
            )

            replay = engine.confirm_purchase(request)
            replay_actual = dict(project_production_release_state(engine))
            replay_actual.update({
                "outcome": {
                    "status": replay.status.value,
                    "amount_spent": replay.amount_spent,
                    "new_balance": replay.new_balance,
                    "disposition": replay.disposition.value,
                },
                "ledger_event": _project_event_record(
                    purchase_session.storage._reward_ledger.economy_event(
                        f"purchase:{request_id}"
                    )
                ),
            })
            recorder.compare(
                case_id="purchase_contract",
                event_identity="focused:purchase:repeat",
                behavior="repeated_request_identity",
                expected=expected_purchase_state,
                actual=replay_actual,
                state_fields=(
                    "garden_coin_wallet",
                    "coin_ledger_entries",
                    "coin_source_ids",
                    "consumable_inventory",
                    "purchase_identities",
                    "state_revision",
                ),
                operation="repeat permanent purchase identity",
            )

            stale_request = PurchaseRequest.from_quote(
                stale_quote, request_id=str(uuid.UUID(int=602))
            )
            stale_outcome = engine.confirm_purchase(stale_request)
            stale_expected = dict(expected_purchase_state)
            stale_expected.update({
                "outcome": {
                    "status": "stale_balance",
                    "amount_spent": 0,
                    "new_balance": balance_after,
                    "disposition": "inventory",
                },
                "stale_ledger_event": {},
            })
            stale_actual = dict(project_production_release_state(engine))
            stale_actual.update({
                "outcome": {
                    "status": stale_outcome.status.value,
                    "amount_spent": stale_outcome.amount_spent,
                    "new_balance": stale_outcome.new_balance,
                    "disposition": stale_outcome.disposition.value,
                },
                "ledger_event": _project_event_record(
                    purchase_session.storage._reward_ledger.economy_event(
                        f"purchase:{request_id}"
                    )
                ),
                "stale_ledger_event": _project_event_record(
                    purchase_session.storage._reward_ledger.economy_event(
                        f"purchase:{stale_request.request_id}"
                    )
                ),
            })
            recorder.compare(
                case_id="purchase_contract",
                event_identity="focused:purchase:stale-balance",
                behavior="stale_purchase_quote",
                expected=stale_expected,
                actual=stale_actual,
                state_fields=(
                    "garden_coin_wallet",
                    "coin_ledger_entries",
                    "coin_source_ids",
                    "consumable_inventory",
                    "purchase_identities",
                    "state_revision",
                ),
                operation="reject stale pre-purchase wallet quote",
            )
        finally:
            purchase_session.close()

        for case_id, opening_wallet, request_number, expected_status in (
            (
                "insufficient_purchase",
                0,
                603,
                PurchaseStatus.INSUFFICIENT_COINS,
            ),
            (
                "failed_persistence",
                500,
                604,
                PurchaseStatus.PERSISTENCE_FAILURE,
            ),
        ):
            failure_state = deepcopy(_ParityStorage().state)
            failure_state.currency_balance = opening_wallet
            failure_session = _DurableParitySession(
                root / case_id, failure_state
            )
            try:
                engine = failure_session.engine()
                initial_revision = failure_session.storage._ledger_revision
                request = PurchaseRequest.from_quote(
                    engine.quote_purchase(
                        PurchaseKind.GROWTH_CHARGE,
                        "growth_charge_small",
                        target_id="p1",
                    ),
                    request_id=str(uuid.UUID(int=request_number)),
                )
                if expected_status is PurchaseStatus.PERSISTENCE_FAILURE:
                    failure_session.storage.fail_next_save = True
                    game_logger = logging.getLogger("ankigarden.game")
                    logger_disabled = game_logger.disabled
                    game_logger.disabled = True
                    try:
                        outcome = engine.confirm_purchase(request)
                    finally:
                        game_logger.disabled = logger_disabled
                else:
                    outcome = engine.confirm_purchase(request)
                actual = dict(project_production_release_state(engine))
                actual.update({
                    "outcome": {
                        "status": outcome.status.value,
                        "amount_spent": outcome.amount_spent,
                        "new_balance": outcome.new_balance,
                    },
                    "ledger_event": _project_event_record(
                        failure_session.storage._reward_ledger.economy_event(
                            f"purchase:{request.request_id}"
                        )
                    ),
                    "staged_writes": (
                        failure_session.storage.reward_ledger_has_staged_writes()
                    ),
                })
                empty_inventory = dict(sorted(
                    (
                        item.consumable_id.value, 0
                    ) for item in CONSUMABLES
                ))
                behavior = (
                    "failed_persistence_rollback"
                    if expected_status is PurchaseStatus.PERSISTENCE_FAILURE
                    else "insufficient_coin_purchase"
                )
                recorder.compare(
                    case_id=case_id,
                    event_identity=f"focused:purchase:{expected_status.value}",
                    behavior=behavior,
                    expected={
                        "garden_coin_wallet": opening_wallet,
                        "coin_ledger_entries": (),
                        "coin_source_ids": (),
                        "consumable_inventory": empty_inventory,
                        "purchase_identities": (),
                        "state_revision": initial_revision,
                        "outcome": {
                            "status": expected_status.value,
                            "amount_spent": 0,
                            "new_balance": opening_wallet,
                        },
                        "ledger_event": {},
                        "staged_writes": False,
                    },
                    actual=actual,
                    state_fields=(
                        "garden_coin_wallet",
                        "coin_ledger_entries",
                        "coin_source_ids",
                        "consumable_inventory",
                        "purchase_identities",
                        "state_revision",
                    ),
                    operation=(
                        "rollback injected persistence failure"
                        if expected_status is PurchaseStatus.PERSISTENCE_FAILURE
                        else "reject purchase with insufficient Garden Coins"
                    ),
                )
            finally:
                failure_session.close()

        # The lineage oracle is a pure mapping of each revlog alias to one
        # consumed answer identity. Undo adds a bounded re-answer hint; neither
        # an older synced alias nor its replacement may regrant resources.
        undo_state = deepcopy(_ParityStorage().state)
        undo_session = _DurableParitySession(root / "undo", undo_state)
        try:
            engine = undo_session.engine()
            initial_revision = undo_session.storage._ledger_revision
            revlog_id = 1_788_100_000_001
            card_id = 42
            lineage = "v1|2026-08-30|42|1"
            answer_identity = stable_answer_event_identity(
                revlog_id,
                card_id=card_id,
                answered_at_ms=revlog_id,
                lineage_id=lineage,
            )
            answer_key = consumption_id(answer_identity)
            correlation_id = f"answer:{answer_key}"
            expected_plant = ({
                "plant_id": "p1",
                "growth_units": 1_000,
                "stage": "seed",
                "checkpoint_flags": (),
                "stage_flags": (),
                "slot_index": 0,
                "fully_grown": False,
                "completion_cards": 1,
                "completion_active_days": 1,
            },)
            expected_coin_ledger = ({
                "event_key": "daily_activity:2026-08-30",
                "transaction_type": "credit",
                "source": "first_eligible_answer",
                "source_id": "2026-08-30",
                "scheduler_day": "2026-08-30",
                "correlation_id": correlation_id,
                "delta": 4,
                "balance": 4,
            },)

            def compare_undo(
                *,
                event_identity: str,
                revision_delta: int,
                bindings: dict[str, str],
                pending: dict[str, int],
                operation: str,
                expected_award_growth_units: int | None = None,
                actual_award_growth_units: int | None = None,
            ) -> None:
                actual = dict(project_production_release_state(engine))
                expected = {
                    "garden_coin_wallet": 4,
                    "coin_ledger_entries": expected_coin_ledger,
                    "coin_source_ids": ("first_eligible_answer",),
                    "plant_exact_growth_units": expected_plant,
                    "reward_identities": ("daily_activity:2026-08-30",),
                    "undo_lineage": {
                        "bindings": dict(sorted(bindings.items())),
                        "pending_reanswers": dict(sorted(pending.items())),
                    },
                    "state_revision": initial_revision + revision_delta,
                }
                if expected_award_growth_units is not None:
                    expected["award_growth_units"] = (
                        expected_award_growth_units
                    )
                    actual["award_growth_units"] = actual_award_growth_units
                recorder.compare(
                    case_id="undo_reanswer",
                    event_identity=event_identity,
                    behavior="undo_and_reanswer_lineage",
                    expected=expected,
                    actual=actual,
                    state_fields=(
                        "garden_coin_wallet",
                        "coin_ledger_entries",
                        "coin_source_ids",
                        "plant_exact_growth_units",
                        "reward_identities",
                        "undo_lineage",
                        "state_revision",
                    ),
                    operation=operation,
                )

            engine.observe_due_start(DueObligationStatus(review_count=1))
            initial_award = engine.register_review(_durable_answer_payload())
            compare_undo(
                event_identity="focused:undo:original-answer",
                revision_delta=2,
                bindings={str(revlog_id): lineage},
                pending={},
                operation="commit original answer lineage",
                expected_award_growth_units=1_000,
                actual_award_growth_units=int(initial_award.total_growth_units),
            )
            undo_session.review_history.append(HistoricalReviewEntry(
                revlog_id=revlog_id,
                card_id=card_id,
                ease=3,
                interval=1,
                last_interval=0,
                factor=2_500,
                response_time_ms=500,
                review_type=1,
                answer_ms=revlog_id,
                scheduler_day="2026-08-30",
                card_day_ordinal=1,
                answer_identity=lineage,
            ))
            undo_session.review_history.clear()
            if not engine.record_review_undo(undo_at_ms=revlog_id + 100):
                raise AssertionError("focused undo did not identify its lineage")
            compare_undo(
                event_identity="focused:undo:remove-original",
                revision_delta=3,
                bindings={str(revlog_id): lineage},
                pending={lineage: revlog_id + 100},
                operation="record durable undo hint",
            )
            engine = undo_session.restart()
            compare_undo(
                event_identity="focused:undo:restart-with-hint",
                revision_delta=3,
                bindings={str(revlog_id): lineage},
                pending={lineage: revlog_id + 100},
                operation="reload durable undo hint",
            )
            older_id = revlog_id + 50
            older_award = engine.register_review(_durable_answer_payload(
                revlog_id=older_id,
                historical_sync=True,
            ))
            compare_undo(
                event_identity="focused:undo:older-sync-alias",
                revision_delta=4,
                bindings={
                    str(revlog_id): lineage,
                    str(older_id): lineage,
                },
                pending={lineage: revlog_id + 100},
                operation="reject older synced alias without reroll",
                expected_award_growth_units=0,
                actual_award_growth_units=int(older_award.total_growth_units),
            )
            replacement_id = revlog_id + 100
            replacement_award = engine.register_review(
                _durable_answer_payload(revlog_id=replacement_id)
            )
            compare_undo(
                event_identity="focused:undo:replacement-alias",
                revision_delta=5,
                bindings={
                    str(revlog_id): lineage,
                    str(older_id): lineage,
                    str(replacement_id): lineage,
                },
                pending={},
                operation="consume replacement alias without regrant",
                expected_award_growth_units=0,
                actual_award_growth_units=int(
                    replacement_award.total_growth_units
                ),
            )
        finally:
            undo_session.close()

    return recorder.evidence()


def _aggregate_release_parity_evidence(
    *,
    bounded: dict[str, object],
    annual: dict[str, object],
    focused: dict[str, object],
    durable: dict[str, object],
    expected_scenario_ids: Sequence[str],
    randomized_case_ids: Sequence[str],
) -> dict[str, object]:
    """Union only coverage demonstrated by an exact comparison lane."""

    expected_ids = tuple(str(value) for value in expected_scenario_ids)
    actual_annual_ids = tuple(
        str(value) for value in annual.get("scenario_ids", ())
    )
    expected_randomized_ids = tuple(
        str(value) for value in randomized_case_ids
    )
    behavior_sources = {
        "bounded_accelerated_trace": tuple(
            str(value) for value in bounded.get("covered_behaviors", ())
        ),
        "focused_sqlite_oracle": tuple(
            str(value) for value in focused.get("covered_behaviors", ())
        ),
    }
    state_field_sources = {
        "bounded_accelerated_trace": tuple(
            str(value) for value in bounded.get("covered_state_fields", ())
        ),
        "annual_daily_checkpoints": tuple(
            str(value) for value in annual.get("covered_state_fields", ())
        ),
        "focused_sqlite_oracle": tuple(
            str(value) for value in focused.get("covered_state_fields", ())
        ),
    }
    covered_behavior_set = {
        value for values in behavior_sources.values() for value in values
    }
    covered_field_set = {
        value for values in state_field_sources.values() for value in values
    }
    covered_behaviors = tuple(
        value for value in REQUIRED_PARITY_BEHAVIORS
        if value in covered_behavior_set
    )
    missing_behaviors = tuple(
        value for value in REQUIRED_PARITY_BEHAVIORS
        if value not in covered_behavior_set
    )
    covered_state_fields = tuple(
        value for value in REQUIRED_PARITY_STATE_FIELDS
        if value in covered_field_set
    )
    missing_state_fields = tuple(
        value for value in REQUIRED_PARITY_STATE_FIELDS
        if value not in covered_field_set
    )

    annual_case_rows = tuple(
        row for row in annual.get("cases", ()) if isinstance(row, dict)
    )
    annual_identity_set_exact = bool(
        len(expected_ids) == 66
        and actual_annual_ids == expected_ids
        and int(annual.get("annual_scenario_trace_count", 0) or 0) == 66
        and len(annual_case_rows) == 66
        and tuple(
            str(row.get("scenario_id", "")) for row in annual_case_rows
        ) == expected_ids
        and all(
            int(row.get("days", 0) or 0) == 365
            and int(row.get("daily_checkpoints", 0) or 0) == 365
            and int(row.get("seed_index", -1)) == 0
            for row in annual_case_rows
        )
        and int(annual.get("checkpoint_count", 0) or 0) == 66 * 365
    )
    bounded_identity_set_exact = bool(
        int(bounded.get("scenario_smoke_trace_count", 0) or 0) == 66
        and int(bounded.get("randomized_trace_count", 0) or 0) == 32
        and int(bounded.get("trace_count", 0) or 0) == 98
        and len(expected_randomized_ids) == 32
        and len(set(expected_randomized_ids)) == 32
    )
    focused_exact = bool(
        focused.get("status") == "pass"
        and int(focused.get("checkpoint_count", 0) or 0) > 0
        and not missing_behaviors
    )
    durable_exact = bool(
        durable.get("status") == "pass"
        and int(durable.get("state_schema_version", 0) or 0) == STATE_VERSION
        and int(durable.get("ledger_schema_version", 0) or 0)
        == LEDGER_SCHEMA_VERSION
    )
    complete = bool(
        bounded_identity_set_exact
        and annual.get("status") == "pass"
        and annual_identity_set_exact
        and focused_exact
        and durable_exact
        and not missing_behaviors
        and not missing_state_fields
    )
    missing_trace_sets = () if annual_identity_set_exact else (
        "annual_365_day_scenario_traces",
    )
    combined_manifest = {
        "bounded": bounded.get("manifest_sha256", ""),
        "annual": annual.get("manifest_sha256", ""),
        "focused": focused.get("trace_manifest_sha256", ""),
        "durable": durable.get("trace_manifest_sha256", ""),
        "scenario_ids": list(actual_annual_ids),
        "expected_scenario_ids": list(expected_ids),
        "randomized_case_ids": list(expected_randomized_ids),
    }
    combined_state_pairs = {
        "bounded": bounded.get("state_pairs_sha256", ""),
        "annual": annual.get("manifest_sha256", ""),
        "focused": focused.get("state_pairs_sha256", ""),
    }
    combined_trace_pairs = {
        "bounded": bounded.get("trace_pairs_sha256", ""),
        "annual": annual.get("manifest_sha256", ""),
        "focused": focused.get("trace_manifest_sha256", ""),
    }
    def encode(value: object) -> bytes:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    bounded_checkpoints = int(bounded.get("checkpoint_count", 0) or 0)
    annual_checkpoints = int(annual.get("checkpoint_count", 0) or 0)
    focused_checkpoints = int(focused.get("checkpoint_count", 0) or 0)
    scenario_trace_count = int(
        bounded.get("scenario_trace_count", 0) or 0
    )
    scenario_smoke_trace_count = int(
        bounded.get("scenario_smoke_trace_count", 0) or 0
    )
    annual_scenario_trace_count = int(
        annual.get("annual_scenario_trace_count", 0) or 0
    )
    randomized_trace_count = int(
        bounded.get("randomized_trace_count", 0) or 0
    )
    return {
        **bounded,
        "status": "pass" if complete else "focused_incomplete",
        "production_engine_trace_equivalent": complete,
        "release_qualified": complete,
        "scenario_trace_count": scenario_trace_count,
        "scenario_smoke_trace_count": scenario_smoke_trace_count,
        "annual_scenario_trace_count": annual_scenario_trace_count,
        "randomized_trace_count": randomized_trace_count,
        "expected_scenario_smoke_trace_count": 66,
        "expected_annual_scenario_trace_count": 66,
        "expected_randomized_trace_count": 32,
        "bounded_trace_count": int(bounded.get("trace_count", 0) or 0),
        "trace_count": (
            int(bounded.get("trace_count", 0) or 0)
            + annual_scenario_trace_count
            + int(focused.get("case_count", 0) or 0)
        ),
        "bounded_checkpoint_count": bounded_checkpoints,
        "annual_checkpoint_count": annual_checkpoints,
        "focused_checkpoint_count": focused_checkpoints,
        "checkpoint_count": (
            bounded_checkpoints + annual_checkpoints + focused_checkpoints
        ),
        "scenario_ids": list(actual_annual_ids),
        "expected_scenario_ids": list(expected_ids),
        "randomized_case_ids": list(expected_randomized_ids),
        "annual_identity_set_exact": annual_identity_set_exact,
        "bounded_identity_set_exact": bounded_identity_set_exact,
        "required_behaviors": list(REQUIRED_PARITY_BEHAVIORS),
        "covered_behaviors": list(covered_behaviors),
        "missing_behaviors": list(missing_behaviors),
        "behavior_coverage_sources": {
            key: list(values) for key, values in behavior_sources.items()
        },
        "required_state_fields": list(REQUIRED_PARITY_STATE_FIELDS),
        "covered_state_fields": list(covered_state_fields),
        "missing_state_fields": list(missing_state_fields),
        "state_field_coverage_sources": {
            key: list(values) for key, values in state_field_sources.items()
        },
        "missing_trace_sets": list(missing_trace_sets),
        "bounded_manifest_sha256": str(
            bounded.get("manifest_sha256", "")
        ),
        "annual_manifest_sha256": str(annual.get("manifest_sha256", "")),
        "focused_manifest_sha256": str(
            focused.get("trace_manifest_sha256", "")
        ),
        "manifest_sha256": sha256(encode(combined_manifest)).hexdigest(),
        "trace_pairs_sha256": sha256(encode(combined_trace_pairs)).hexdigest(),
        "state_pairs_sha256": sha256(encode(combined_state_pairs)).hexdigest(),
        "annual_parity": annual,
        "focused_kernel_equivalence": focused,
        "durable_persistence": durable,
        "note": (
            "All 66 annual traces, 32 bounded randomized traces, focused "
            "SQLite/domain-oracle behaviors, and required release-state "
            "fields matched the production GardenGameEngine exactly."
            if complete else
            "Production parity remains blocked by the explicitly listed "
            "missing trace sets, behaviors, or state fields."
        ),
    }


def run_release_parity() -> dict[str, object]:
    facts = load_catalog_facts()
    scenarios = approved_scenarios()
    scenarios_by_id = {row.scenario_id: row for row in scenarios}
    cases = release_parity_manifest(row.scenario_id for row in scenarios)
    kernel_by_case = {}
    engine_by_case = {}
    for case in cases:
        if case.scenario_id:
            scenario = scenarios_by_id[case.scenario_id]
            events = (DayEvents(day=1, study=True, answers=1),)
            config = SimulationConfig(seeds=1, days=1, checkpoint_days=(1,))
            storage = _scenario_storage(scenario)
        else:
            scenario = ScenarioSpec(
                f"{case.case_id}:no_spend:baseline",
                CohortSpec(f"parity_{case.seed_index}", 1, 7, 80),
                StrategySpec(
                    "parity_manual",
                    "Parity manual loadout",
                    optimize_for="manual",
                    consumable_policy="never_use_earned",
                ),
            )
            storage = _ParityStorage()
            _configure_focused_storage(storage, case)
            events = tuple(
                _focused_day_event(storage, event)
                for event in case.events
            )
            final_day = max(row.day for row in events)
            config = SimulationConfig(
                seeds=1,
                days=final_day,
                checkpoint_days=(final_day,),
            )
        kernel = simulate_scenario(
            facts,
            scenario,
            config,
            case.seed_index,
            events=events,
            capture_trace=True,
        ).trace_rows
        expected = []
        for row, event in zip(kernel, case.events):
            projected = dict(row)
            projected["event_identity"] = event.event_identity
            expected.append(projected)
        if case.scenario_id:
            storage.state.loadout.active_garden_bonus_id = str(
                expected[0]["active_garden_bonus_id"]
            )
            storage.state.loadout.active_scenery_effect_id = str(
                expected[0]["active_scenery_id"]
            )
        production = GardenGameEngineReplayAdapter(
            lambda: GardenGameEngine(_ParityConfig(), storage),
            project_production_engine_trace_row,
        ).replay(case.events)
        kernel_by_case[case.case_id] = tuple(expected)
        engine_by_case[case.case_id] = production.rows
    bounded = dict(assert_release_parity_manifest(
        cases, kernel_by_case, engine_by_case
    ))
    focused = run_focused_kernel_equivalence_checks()
    durable = run_durable_persistence_checks()
    annual = dict(run_annual_parity(
        scenarios=scenarios,
        seed_index=0,
        days=365,
    ))
    randomized_case_ids = tuple(
        case.case_id for case in cases
        if case.case_kind == "deterministic_randomized_multi_event"
    )
    return _aggregate_release_parity_evidence(
        bounded=bounded,
        annual=annual,
        focused=focused,
        durable=durable,
        expected_scenario_ids=tuple(
            scenario.scenario_id for scenario in scenarios
        ),
        randomized_case_ids=randomized_case_ids,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    evidence = run_release_parity()
    text = json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output is None:
        print(text, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
