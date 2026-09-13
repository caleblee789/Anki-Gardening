from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import shutil
import time
import uuid
from bisect import bisect_left, bisect_right
from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, Iterable, Mapping
from .performance import timed

from .balance_catalog import (
    LANDMARKS,
    MASTERY_RANKS,
)
from .environment import (
    DEFAULT_GARDEN_FEATURE_ID,
    DEFAULT_SCENERY_ID,
    DEFAULT_WEATHER_ID,
    LEGACY_WEATHER_TO_GARDEN_FEATURE,
    canonical_garden_feature_id,
)
from .models.state import (
    ActivePlantPeriod,
    Achievement,
    CURRENT_CATALOG_SPECIES_ORDER,
    CurrencyTransaction,
    COSMETIC_DISPLAY_IDS,
    CULTIVATION_MASTERY_CUMULATIVE_GROWTH_THRESHOLDS_UNITS,
    CULTIVATION_MASTERY_RANKS,
    DailyEconomySnapshot,
    DEFAULT_GARDEN_NAME,
    GARDEN_PROJECT_CUMULATIVE_GROWTH_THRESHOLDS_UNITS,
    GARDEN_PROJECT_IDS,
    GARDEN_LEGACY_LEVEL_COST_UNITS,
    GardenFindOutcome,
    GardenState,
    GROWTH_STAGES,
    GROWTH_THRESHOLDS,
    LifetimeEconomyAggregates,
    LANDMARK_MAX_GROWTH_UNITS,
    MASTERY_MAX_GROWTH_UNITS_PER_SPECIES,
    MAX_PROCESSED_REVLOG_IDS,
    MAX_TRANSACTION_HISTORY,
    OnboardingProgress,
    OnboardingStep,
    Plant,
    PlantMemory,
    PLANT_MEMORY_KINDS,
    PLANT_SPECIES,
    PendingEconomyMigrationGrant,
    STATE_VERSION,
    STORED_GROWTH_OPENING_IDENTITY_NEW_PROFILE,
    STORED_GROWTH_OPENING_IDENTITY_MIGRATION,
)
from .reward_ledger import (
    AnswerConsumptionRecord,
    AnswerLineageRecord,
    DailyEconomySnapshotRecord,
    EconomyEventRecord,
    FinalizedDayRecord,
    FindOutcomeRecord,
    IdempotencyRecord,
    LedgerCheckpoint,
    RevlogAliasRecord,
    RewardEventRecord,
    RewardLedger,
    RewardLedgerCorruptionError,
    RewardLedgerSchemaError,
    UNBOUNDED_STATE_AUTHORITY_KEYS,
)


logger = logging.getLogger(__name__)

PREVIOUS_STATE_VERSION = 10
MODERN_PREVIOUS_STATE_VERSIONS = frozenset({
    11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29,
})
LEGACY_GROWTH_THRESHOLDS = [0, 80, 220, 480, 900, 1_400]
MAX_HISTORICAL_REVLOG_ENTRIES = 1_000_000
DEFAULT_HISTORY_PAGE_SIZE = 5_000
REWARD_DATABASE_FILENAME = "garden_state.sqlite3"
RECENT_FIND_CACHE_LIMIT = 32
SCHEMA27_ECONOMY_AUTHORITY_OPERATION_ID = (
    "migration:schema27:economy-authorities"
)
SCHEMA27_ENDGAME_RECONCILIATION_VERSION = 1
LANDMARK_COIN_COST_BY_ID = {
    str(item.landmark_id): int(item.coin_cost) for item in LANDMARKS
}
MASTERY_COIN_COST_BY_ID = {
    str(item.rank_id): int(item.coin_cost) for item in MASTERY_RANKS
}


class StatePreservationError(RuntimeError):
    """Raised when a required recovery backup cannot be created safely."""


class RevlogReadError(RuntimeError):
    """Raised when same-day review history cannot be read reliably."""


class SchedulerBoundaryError(RevlogReadError):
    """Raised when Anki's scheduler-day boundary is unavailable or invalid."""


def unprocessed_revlog_entries(
    state: Any,
    rows: list[tuple[Any, ...]],
) -> list[tuple[Any, ...]]:
    """Diff a scheduler-day history read against its persisted id ledger."""
    floor = int(getattr(state, "processed_revlog_floor", 0) or 0)
    processed = {
        int(value)
        for value in (getattr(state, "processed_revlog_ids", []) or [])
        if isinstance(value, int) and not isinstance(value, bool)
    }
    return [
        row for row in rows
        if int(row[0]) > floor and int(row[0]) not in processed
    ]


def _answer_lineage_key(scheduler_day: str, card_id: int, serial: int) -> str:
    return f"v1|{scheduler_day}|{int(card_id)}|{int(serial)}"


def _parse_answer_lineage_key(value: object) -> tuple[str, int, int] | None:
    if not isinstance(value, str):
        return None
    parts = value.split("|")
    if len(parts) != 4 or parts[0] != "v1":
        return None
    try:
        scheduler_day = date.fromisoformat(parts[1]).isoformat()
        card_id = int(parts[2])
        serial = int(parts[3])
    except (TypeError, ValueError):
        return None
    if scheduler_day != parts[1] or card_id <= 0 or serial <= 0:
        return None
    return scheduler_day, card_id, serial


def assign_stable_answer_identities(
    events: list[tuple[int, int, str]],
    existing_bindings: Mapping[str, str] | None = None,
    reanswer_hints: Mapping[str, int] | None = None,
    *,
    present_lineages: Iterable[str] = (),
) -> tuple[dict[int, str], dict[str, str]]:
    """Bind revlog rows to insertion-stable, undo-resistant answer lineages.

    Exact revlog IDs retain their prior lineage. If an old row disappeared and
    a new row for the same card and Anki day appeared, the orphaned lineage is
    reused (the normal undo/reanswer shape). A late synced row added alongside
    all existing rows receives a new monotonically allocated lineage, so it
    cannot shift or reroll any earlier answer.

    Callers supplying only a window of history must also supply lineages whose
    aliases still exist outside that window. Omitted history is not an Undo.
    """

    normalized = sorted({
        (int(revlog_id), int(card_id), date.fromisoformat(str(day)).isoformat())
        for revlog_id, card_id, day in events
        if int(revlog_id) > 0 and int(card_id) > 0
    })
    bindings = {
        str(raw_revlog_id): str(lineage)
        for raw_revlog_id, lineage in (existing_bindings or {}).items()
        if str(raw_revlog_id).isdigit()
        and int(str(raw_revlog_id)) > 0
        and _parse_answer_lineage_key(lineage) is not None
    }
    hinted_reanswers = {
        str(lineage): max(1, int(minimum_revlog_id))
        for lineage, minimum_revlog_id in (reanswer_hints or {}).items()
        if _parse_answer_lineage_key(lineage) is not None
        and isinstance(minimum_revlog_id, int)
        and not isinstance(minimum_revlog_id, bool)
        and minimum_revlog_id > 0
    }
    identities: dict[int, str] = {}

    lineage_aliases: dict[str, list[int]] = {}
    lineage_context: dict[str, tuple[str, int, int]] = {}
    context_alias_high_water: dict[tuple[str, int], int] = {}
    for raw_revlog_id, lineage in bindings.items():
        parsed = _parse_answer_lineage_key(lineage)
        if parsed is None:
            continue
        lineage_context[lineage] = parsed
        alias = int(raw_revlog_id)
        lineage_aliases.setdefault(lineage, []).append(alias)
        context = parsed[:2]
        context_alias_high_water[context] = max(
            context_alias_high_water.get(context, 0),
            alias,
        )

    for revlog_id, card_id, scheduler_day in normalized:
        lineage = bindings.get(str(revlog_id), "")
        parsed = _parse_answer_lineage_key(lineage)
        # A revlog ID is immutable.  Its existing binding stays authoritative
        # even if a later cutoff/timezone change maps that row to another Anki
        # day; otherwise the same answer could acquire a fresh reward lineage.
        if parsed is not None:
            identities[revlog_id] = lineage

    class _AvailableRows:
        """Successor set over sorted revlog IDs with near-constant removal."""

        def __init__(self, values: list[int]) -> None:
            self.values = values
            self.parent = list(range(len(values) + 1))

        def _find(self, index: int) -> int:
            trail = index
            while self.parent[trail] != trail:
                trail = self.parent[trail]
            while self.parent[index] != index:
                parent = self.parent[index]
                self.parent[index] = trail
                index = parent
            return trail

        def discard(self, value: int) -> None:
            index = bisect_left(self.values, value)
            if (
                index < len(self.values)
                and self.values[index] == value
                and self._find(index) == index
            ):
                self.parent[index] = self._find(index + 1)

        def take_after(self, value: int) -> int | None:
            index = self._find(bisect_right(self.values, value))
            if index >= len(self.values):
                return None
            selected = self.values[index]
            self.parent[index] = self._find(index + 1)
            return selected

    # Reuse disappeared lineages only for a later row of the same card.  A
    # lower-ID synced insertion must never consume an orphan that belongs to an
    # undo/reanswer replacement.  Prefer the same Anki day, but retain the
    # lineage across a day-boundary reanswer as the anti-reroll fail-safe.
    assigned_lineages = set(identities.values()) | set(present_lineages)
    orphaned_lineages = [
        lineage
        for lineage in lineage_context
        if lineage not in assigned_lineages
    ]
    orphaned_lineages.sort(
        key=lambda lineage: (
            max(lineage_aliases.get(lineage, [0])),
            lineage,
        ),
        reverse=True,
    )
    unassigned_by_card: dict[int, list[int]] = {}
    unassigned_by_context: dict[tuple[str, int], list[int]] = {}
    day_by_revlog_id: dict[int, str] = {}
    for revlog_id, card_id, scheduler_day in normalized:
        if revlog_id in identities:
            continue
        unassigned_by_card.setdefault(card_id, []).append(revlog_id)
        unassigned_by_context.setdefault((scheduler_day, card_id), []).append(
            revlog_id
        )
        day_by_revlog_id[revlog_id] = scheduler_day
    available_by_card = {
        card_id: _AvailableRows(rows)
        for card_id, rows in unassigned_by_card.items()
    }
    available_by_context = {
        context: _AvailableRows(rows)
        for context, rows in unassigned_by_context.items()
    }
    for lineage in orphaned_lineages:
        parsed = lineage_context[lineage]
        original_day, card_id, _serial = parsed
        latest_alias = max(lineage_aliases.get(lineage, [0]))
        context_rows = available_by_context.get((original_day, card_id))
        card_rows = available_by_card.get(card_id)
        hinted_floor = hinted_reanswers.get(lineage)
        if hinted_floor is not None:
            # The undo hook records the earliest possible reanswer revlog ID.
            # Rows below it may be late sync insertions and must not consume
            # the orphaned lineage. If no qualifying row exists yet, leave the
            # lineage pending for a later history read.
            preferred_floor = max(latest_alias, hinted_floor - 1)
            replacement_id = (
                context_rows.take_after(preferred_floor)
                if context_rows is not None
                else None
            )
            if replacement_id is None and card_rows is not None:
                replacement_id = card_rows.take_after(preferred_floor)
                if replacement_id is not None:
                    replacement_day = day_by_revlog_id[replacement_id]
                    available_by_context[(replacement_day, card_id)].discard(
                        replacement_id
                    )
            elif replacement_id is not None and card_rows is not None:
                card_rows.discard(replacement_id)
            if replacement_id is not None:
                identities[replacement_id] = lineage
                bindings[str(replacement_id)] = lineage
            continue
        # A row newer than every previously known alias in this card/day is
        # the least ambiguous undo/reanswer replacement. Prefer it before an
        # interleaved lower-ID sync insertion; if no such row exists, retain
        # the closer fallback for clock-skewed or remapped replacements.
        preferred_floor = max(
            latest_alias,
            context_alias_high_water.get((original_day, card_id), 0),
        )
        replacement_id = (
            context_rows.take_after(preferred_floor)
            if context_rows is not None
            else None
        )
        if replacement_id is not None:
            if card_rows is not None:
                card_rows.discard(replacement_id)
        elif card_rows is not None:
            replacement_id = card_rows.take_after(preferred_floor)
            if replacement_id is not None:
                replacement_day = day_by_revlog_id[replacement_id]
                available_by_context[(replacement_day, card_id)].discard(
                    replacement_id
                )
        if replacement_id is None and preferred_floor > latest_alias:
            replacement_id = (
                context_rows.take_after(latest_alias)
                if context_rows is not None
                else None
            )
            if replacement_id is not None:
                if card_rows is not None:
                    card_rows.discard(replacement_id)
            elif card_rows is not None:
                replacement_id = card_rows.take_after(latest_alias)
                if replacement_id is not None:
                    replacement_day = day_by_revlog_id[replacement_id]
                    available_by_context[(replacement_day, card_id)].discard(
                        replacement_id
                    )
        if replacement_id is None:
            continue
        identities[replacement_id] = lineage
        bindings[str(replacement_id)] = lineage

    rows_by_context: dict[tuple[str, int], list[int]] = {}
    for revlog_id, card_id, scheduler_day in normalized:
        rows_by_context.setdefault((scheduler_day, card_id), []).append(revlog_id)
    max_serial_by_context: dict[tuple[str, int], int] = {}
    for parsed in lineage_context.values():
        context = parsed[:2]
        max_serial_by_context[context] = max(
            max_serial_by_context.get(context, 0),
            parsed[2],
        )
    for (scheduler_day, card_id), context_rows in sorted(rows_by_context.items()):
        new_rows = [
            revlog_id for revlog_id in context_rows if revlog_id not in identities
        ]
        next_serial = max_serial_by_context.get((scheduler_day, card_id), 0)
        for revlog_id in new_rows:
            next_serial += 1
            lineage = _answer_lineage_key(scheduler_day, card_id, next_serial)
            identities[revlog_id] = lineage
            bindings[str(revlog_id)] = lineage
    return identities, bindings


def _required_backup(source: Path, destination: Path) -> None:
    try:
        shutil.copy2(source, destination)
    except Exception as error:
        raise StatePreservationError(
            "Anki Garden could not preserve the saved garden; startup was stopped before any overwrite."
        ) from error


def _required_sqlite_family_backup(source: Path, destination: Path) -> None:
    """Preserve a SQLite file and any live WAL family under one new basename."""

    _required_backup(source, destination)
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(source) + suffix)
        if sidecar.exists():
            _required_backup(sidecar, Path(str(destination) + suffix))


def _legacy_nonnegative_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return max(0, value)


def _migrate_legacy_growth(value: Any) -> int:
    """Preserve a schema-10 plant's stage and progress within that stage."""
    growth = min(LEGACY_GROWTH_THRESHOLDS[-1], _legacy_nonnegative_int(value))
    if growth >= LEGACY_GROWTH_THRESHOLDS[-1]:
        return GROWTH_THRESHOLDS[-1]
    stage_index = max(
        index for index, threshold in enumerate(LEGACY_GROWTH_THRESHOLDS) if growth >= threshold
    )
    old_start = LEGACY_GROWTH_THRESHOLDS[stage_index]
    old_end = LEGACY_GROWTH_THRESHOLDS[stage_index + 1]
    new_start = GROWTH_THRESHOLDS[stage_index]
    new_end = GROWTH_THRESHOLDS[stage_index + 1]
    fraction = (growth - old_start) / (old_end - old_start)
    return min(new_end, new_start + int(math.floor((new_end - new_start) * fraction + 0.5)))


def _migrate_legacy_memories(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in value[:64]:
        if not isinstance(raw, dict):
            continue
        kind = raw.get("kind")
        memory_id = raw.get("memory_id")
        if kind == "first_focus":
            kind = "first_nurture"
            memory_id = "nurture:first"
        if (
            kind not in PLANT_MEMORY_KINDS
            or not isinstance(memory_id, str)
            or not memory_id
            or memory_id in seen
        ):
            continue
        seen.add(memory_id)
        result.append({
            "memory_id": memory_id,
            "kind": kind,
            "occurred_on": raw.get("occurred_on"),
            "value": _legacy_nonnegative_int(raw.get("value")),
            "previous_stage": raw.get("previous_stage"),
            "new_stage": raw.get("new_stage"),
        })
    return result


def _materialize_unlocked_species(state: GardenState) -> GardenState:
    """Turn species entitlements into usable shelved collection records.

    Schemas 10 through 13 can contain an unlocked species without the Plant
    row that the current Nursery collection uses. Keeping only the entitlement
    makes the species look owned while leaving nothing the learner can place.
    """
    existing_species = {
        plant.species for plant in state.plants if plant.species in PLANT_SPECIES
    }
    existing_ids = {plant.plant_id for plant in state.plants}
    occurred_on = state.last_active_day or state.daily_stats.day
    materialized = False
    for species in dict.fromkeys(state.unlocked_species):
        if species not in PLANT_SPECIES or species in existing_species:
            continue
        base_id = f"legacy_unlocked_{species}"
        plant_id = base_id
        suffix = 2
        while plant_id in existing_ids:
            plant_id = f"{base_id}_{suffix}"
            suffix += 1
        label = species.replace("_", " ").title()
        state.plants.append(Plant(
            plant_id=plant_id,
            species=species,
            name=f"{label} Plant",
            slot_index=None,
            growth_points=0,
            bonus_remainder=0,
            personality="balanced",
            planted_on=occurred_on,
            memories=[PlantMemory("planted", "planted", occurred_on)],
            name_customized=False,
        ))
        existing_species.add(species)
        existing_ids.add(plant_id)
        materialized = True
    if materialized:
        # An entitlement can only come from an established pre-starter Garden
        # release; it is not a brand-new starter-selection state.
        state.starter_selection_complete = True
        if state.onboarding.step == OnboardingStep.INTRODUCTION and state.plants:
            state.onboarding = OnboardingProgress(
                step=OnboardingStep.DONE,
                starter_plant_id=state.plants[0].plant_id,
            )
    return state


def _add_legacy_fertilizer_activation_boundaries(
    payload: dict[str, Any],
    migrated_at: float,
) -> None:
    """Preserve remaining legacy duration without rewarding older sync rows."""
    plants = payload.get("plants")
    if not isinstance(plants, list):
        return
    boundary = max(0.0, float(migrated_at))
    for plant in plants:
        fertilizer = plant.get("fertilizer") if isinstance(plant, dict) else None
        if not isinstance(fertilizer, dict):
            continue
        started = fertilizer.get("started_at")
        if isinstance(started, (int, float)) and not isinstance(started, bool) and started >= 0:
            continue
        expires = fertilizer.get("expires_at")
        if not isinstance(expires, (int, float)) or isinstance(expires, bool) or expires < 0:
            continue
        # An unexpired legacy purchase begins at migration time; an already
        # expired purchase remains inactive. Either way, answers timestamped
        # before migration can never receive a retroactive bonus.
        fertilizer["started_at"] = min(float(expires), boundary)


def _migrate_loadout_payload(payload: dict[str, Any]) -> None:
    """Collapse legacy appearance mirrors into schema 19's one authority."""

    inventory = payload.get("inventory")
    if not isinstance(inventory, dict):
        inventory = {}
        payload["inventory"] = inventory
    backgrounds = inventory.get("backgrounds")
    scenery = inventory.get("scenery")
    legacy_scenery = backgrounds if isinstance(backgrounds, list) else []
    current_scenery = scenery if isinstance(scenery, list) else []
    inventory["scenery"] = list(dict.fromkeys(
        item for item in [*legacy_scenery, *current_scenery]
        if isinstance(item, str) and item
    ))
    inventory.pop("backgrounds", None)

    equipped = payload.get("equipped")
    equipped = equipped if isinstance(equipped, dict) else {}
    visibility = payload.get("environment_visibility")
    if not isinstance(visibility, dict):
        visibility = {"weather": True, "scenery": True}
    payload["loadout"] = {
        "weather_id": payload.get(
            "selected_weather", equipped.get("weather", DEFAULT_WEATHER_ID)
        ),
        "scenery_id": payload.get(
            "selected_background", equipped.get("background", DEFAULT_SCENERY_ID)
        ),
        "visibility": {
            "weather": bool(visibility.get("weather", True)),
            "scenery": bool(visibility.get("scenery", True)),
        },
    }
    for legacy_key in (
        "selected_weather",
        "selected_background",
        "equipped",
        "environment_visibility",
    ):
        payload.pop(legacy_key, None)


def _migrate_growth_accounting_payload(payload: dict[str, Any]) -> None:
    """Preserve pre-schema-20 daily Growth without inventing allocation roles."""

    stats = payload.get("daily_stats")
    if not isinstance(stats, dict):
        stats = {}
        payload["daily_stats"] = stats
    old_total = _legacy_nonnegative_int(stats.get("growth_earned"))
    old_plant_growth = stats.get("plant_growth")
    legacy_plant_growth = (
        {
            str(plant_id): max(0, int(points))
            for plant_id, points in old_plant_growth.items()
            if (
                isinstance(plant_id, str)
                and plant_id
                and isinstance(points, int)
                and not isinstance(points, bool)
            )
        }
        if isinstance(old_plant_growth, dict)
        else {}
    )
    stats["legacy_unattributed_growth"] = old_total
    stats["legacy_plant_growth"] = legacy_plant_growth
    stats["growth_accounting_stale"] = bool(old_total or legacy_plant_growth)
    for field_name in (
        "base_growth",
        "streak_bonus_growth",
        "fertilizer_growth",
        "booster_growth",
        "weather_growth",
        "scenery_growth",
        "charge_growth",
        "direct_reward_growth",
        "bonus_growth",
        "growth_earned",
    ):
        stats[field_name] = 0
    stats["plant_growth"] = {}
    stats["plant_nurtured_growth"] = {}
    stats["plant_passive_growth_fifths"] = {}
    stats["plant_passive_growth_credited"] = {}
    stats["plant_charge_growth"] = {}
    stats["plant_direct_reward_growth"] = {}
    payload.setdefault("completed_growth_charge_requests", [])
    plants = payload.get("plants")
    if isinstance(plants, list):
        for plant in plants:
            if isinstance(plant, dict):
                plant.setdefault("passive_growth_remainder_fifths", 0)


def _migrate_reward_state_payload(payload: dict[str, Any]) -> None:
    """Add schema-21 reward authorities without replaying legacy behavior.

    Visible legacy transactions, drops, inventory, and counters stay intact.
    Only exact persisted transaction event keys seed the new unbounded grant
    authority. The old aggregate eligible-answer count is intentionally not a
    Garden Find drought counter; the old Ultra miss counter is the one reliable
    special-pool state that can be carried forward.
    """

    legacy_event_keys: list[str] = []
    transactions = payload.get("currency_transactions")
    if isinstance(transactions, list):
        for transaction in transactions:
            if not isinstance(transaction, dict):
                continue
            delta = transaction.get("delta", 0)
            if (
                isinstance(delta, (int, float))
                and not isinstance(delta, bool)
                and delta < 0
            ) or transaction.get("transaction_type") == "debit":
                # Purchases have their own idempotency ledger and must not be
                # reclassified as already-applied reward grants.
                continue
            event_key = transaction.get("event_key")
            if isinstance(event_key, str) and event_key:
                legacy_event_keys.append(event_key)
    existing_event_keys = payload.get("applied_reward_event_keys")
    if isinstance(existing_event_keys, list):
        legacy_event_keys.extend(
            key for key in existing_event_keys if isinstance(key, str) and key
        )
    claimed_streaks = payload.get("claimed_streak_rewards")
    if isinstance(claimed_streaks, list):
        legacy_event_keys.extend(
            f"streak:{milestone}"
            for milestone in claimed_streaks
            if isinstance(milestone, int) and not isinstance(milestone, bool)
            and milestone in {7, 14, 30, 100}
        )

    payload["reward_state_initialized"] = False
    payload["reward_activation_ms"] = 0
    payload["progression_activation_ms"] = 0
    payload["applied_reward_event_keys"] = list(dict.fromkeys(legacy_event_keys))
    payload.setdefault("recent_reward_receipts", [])
    payload.setdefault("processed_answer_keys", [])
    payload.setdefault("answer_lineage_bindings", {})
    payload.setdefault("pending_reanswer_lineages", {})
    payload.setdefault("achievement_history_fingerprint", "")
    payload.setdefault("achievement_history_high_water_revlog_id", 0)
    payload.setdefault("finalized_day_fingerprints", {})
    payload.setdefault("current_non_again_run", 0)
    payload.setdefault("lifetime_eligible_answers", 0)
    payload["garden_find_activation_ms"] = 0
    payload["garden_find_drought_count"] = 0
    payload["garden_find_daily_counts"] = {}
    payload["garden_find_reward_daily_counts"] = {}
    payload["garden_find_outcomes"] = {}
    payload["garden_find_ultra_misses"] = _legacy_nonnegative_int(
        payload.get("ultra_pity_misses")
    )
    # Pre-schema-21 badge IDs described materially different criteria and
    # payouts. Reusing those flags would silently reclassify old development
    # data (including fabricating the new live-only All Clear). The add-on has
    # no released users, so current achievements are rebuilt from authoritative
    # history after initialization while old wallet/item transactions remain.
    payload["achievements"] = {}

    stats = payload.get("daily_stats")
    if not isinstance(stats, dict):
        stats = {}
        payload["daily_stats"] = stats
    stats["due_started_with_cards"] = None
    consumables = payload.get("consumables")
    if not isinstance(consumables, dict):
        consumables = {}
        payload["consumables"] = consumables
    for fertilizer_id in (
        "fertilizer_basic",
        "fertilizer_quality",
        "fertilizer_premium",
    ):
        consumables.setdefault(fertilizer_id, 0)


def _legacy_booster_card_effect_batch(
    value: Any,
    *,
    migrated_at: float,
) -> dict[str, Any] | None:
    """Preserve one active wall-clock Booster as a full card-counted dose.

    Booster Potions became card-counted in schema 22. A legacy duration cannot
    reveal how many cards remained, so the complete fixed dose is the only
    migration that cannot destroy paid value. Fertilizer remains timed and is
    deliberately not handled here.
    """

    if not isinstance(value, dict):
        return None
    started_at = value.get("started_at")
    expires_at = value.get("expires_at")
    if (
        isinstance(started_at, bool)
        or not isinstance(started_at, (int, float))
        or isinstance(expires_at, bool)
        or not isinstance(expires_at, (int, float))
        or float(started_at) > migrated_at
        or float(expires_at) <= migrated_at
    ):
        return None
    effect_id = "booster_potion"
    cards = 100
    growth_units = 500
    return {
        "effect_id": effect_id,
        "growth_per_card_units": growth_units,
        "total_cards": cards,
        "remaining_cards": cards,
        "activated_at": datetime.fromtimestamp(
            float(started_at), tz=timezone.utc
        ).isoformat(),
        "source_event_key": f"schema21:{effect_id}:{int(float(started_at) * 1000)}",
    }


# Schema 26 makes Fertilizer card-counted. These values intentionally live
# beside the migration instead of importing the game engine and creating a
# storage dependency cycle.
_TIMED_FERTILIZER_MIGRATION_SPECS: dict[str, tuple[str, int, int, int]] = {
    # effect id: (tier, Growth units per card, full duration seconds, cards)
    "fertilizer_basic": ("basic", 100, 60 * 60, 100),
    "fertilizer_quality": ("quality", 200, 2 * 60 * 60, 200),
    "fertilizer_premium": ("premium", 300, 4 * 60 * 60, 400),
}


def _finite_timestamp(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) and result >= 0.0 else None


def _timed_fertilizer_interval(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, dict):
        return None
    if value.get("tier") not in {"basic", "quality", "premium"}:
        return None
    started_at = _finite_timestamp(value.get("started_at"))
    expires_at = _finite_timestamp(value.get("expires_at"))
    if started_at is None or expires_at is None or started_at >= expires_at:
        return None
    return started_at, expires_at


def _migrate_timed_fertilizer_to_card_queue(
    payload: dict[str, Any],
    *,
    migrated_at: float,
) -> bool:
    """Convert each unexpired timed Fertilizer interval to a FIFO card batch."""

    migration_time = max(0.0, float(migrated_at))
    changed = False
    plants = payload.get("plants")
    for plant in plants if isinstance(plants, list) else []:
        if not isinstance(plant, dict):
            continue
        queue = plant.get("card_effect_queue")
        if not isinstance(queue, dict):
            queue = {}
        raw_batches = queue.get("fertilizer_batches")
        batches = list(raw_batches) if isinstance(raw_batches, list) else []
        if not batches:
            for field_name in ("fertilizer_card_batches", "fertilizer_card_queue"):
                compatibility = plant.get(field_name)
                if isinstance(compatibility, list):
                    batches.extend(
                        row for row in compatibility if isinstance(row, dict)
                    )

        # A retained timed effect was the active dose. Preserve that position
        # ahead of schema-22 experimental queued batches. Previously migrated
        # v26 rows remain a stable prefix so rerunning migration is idempotent.
        migration_prefix = [
            row for row in batches
            if str(row.get("source_event_key", "")).startswith(
                "migration:v26:fertilizer:"
            )
        ]
        compatibility_suffix = [
            row for row in batches if row not in migration_prefix
        ]
        batches = [*migration_prefix, *compatibility_suffix]
        migration_insert_index = len(migration_prefix)

        seen_keys = {
            str(row.get("source_event_key"))
            for row in batches
            if isinstance(row, dict) and row.get("source_event_key")
        }
        periods: list[dict[str, Any]] = []
        current = plant.get("fertilizer")
        if isinstance(current, dict):
            periods.append(current)
        history = plant.get("fertilizer_history")
        if isinstance(history, list):
            periods.extend(row for row in history if isinstance(row, dict))
        periods.sort(key=lambda row: (
            _finite_timestamp(row.get("started_at")) or 0.0,
            _finite_timestamp(row.get("expires_at")) or 0.0,
        ))
        plant_id = str(plant.get("plant_id") or "plant")
        for index, period in enumerate(periods):
            tier = period.get("tier")
            effect_id = f"fertilizer_{tier}"
            spec = _TIMED_FERTILIZER_MIGRATION_SPECS.get(effect_id)
            interval = _timed_fertilizer_interval(period)
            if spec is None or interval is None:
                continue
            started_at, expires_at = interval
            if expires_at <= migration_time:
                continue
            _tier, growth_units, full_duration, full_cards = spec
            remaining_seconds = max(
                0.0, expires_at - max(migration_time, started_at)
            )
            remaining_cards = min(
                full_cards,
                int(math.ceil(
                    float(full_cards) * remaining_seconds / float(full_duration)
                )),
            )
            if remaining_cards <= 0:
                continue
            source_event_key = (
                "migration:v26:fertilizer:"
                f"{plant_id}:{int(started_at * 1000)}:{index}"
            )
            if source_event_key in seen_keys:
                continue
            seen_keys.add(source_event_key)
            batches.insert(migration_insert_index, {
                "effect_id": effect_id,
                "growth_per_card_units": growth_units,
                "total_cards": full_cards,
                "remaining_cards": remaining_cards,
                "activated_at": datetime.fromtimestamp(
                    started_at, tz=timezone.utc
                ).isoformat(),
                "source_event_key": source_event_key,
            })
            migration_insert_index += 1
            changed = True

        booster_remaining = queue.get("booster_remaining_cards", 0)
        if isinstance(booster_remaining, bool) or not isinstance(booster_remaining, int):
            booster_remaining = 0
        if booster_remaining <= 0:
            for field_name in ("booster_card_batches", "booster_card_queue"):
                compatibility = plant.get(field_name)
                if isinstance(compatibility, list):
                    booster_remaining += sum(
                        max(0, int(row.get("remaining_cards", 0)))
                        for row in compatibility
                        if isinstance(row, dict)
                        and isinstance(row.get("remaining_cards", 0), int)
                        and not isinstance(row.get("remaining_cards", 0), bool)
                    )
        queue["fertilizer_batches"] = batches
        queue["booster_remaining_cards"] = max(0, booster_remaining)
        plant["card_effect_queue"] = queue
        plant["fertilizer"] = None
        plant["fertilizer_history"] = []
        plant["fertilizer_card_batches"] = []
        plant["fertilizer_card_queue"] = []
        plant["booster"] = None
        plant["booster_history"] = []
        plant["booster_card_batches"] = []
        plant["booster_card_queue"] = []
    return changed


def _migrate_schema22_progression_payload(
    payload: dict[str, Any],
    *,
    migrated_at: float | None = None,
) -> None:
    """Add exact Growth, daily projection, and finite progression authorities."""

    migration_time = time.time() if migrated_at is None else max(0.0, float(migrated_at))
    payload["version"] = STATE_VERSION
    payload.setdefault("stored_growth_units", 0)
    payload.setdefault("autumn_coin_carry_units", 0)

    plants = payload.get("plants")
    plant_rows = plants if isinstance(plants, list) else []
    active_plant_id = payload.get("active_plant_id")
    active_remainder = 0
    for plant in plant_rows:
        if not isinstance(plant, dict):
            continue
        growth = min(
            GROWTH_THRESHOLDS[-1],
            _legacy_nonnegative_int(plant.get("growth_points")),
        )
        plant.setdefault("growth_remainder_units", 0)
        if plant.get("plant_id") == active_plant_id:
            active_remainder = min(
                99, _legacy_nonnegative_int(plant.get("bonus_remainder"))
            )

        checkpoint_claims: list[str] = []
        stage_reward_claims: list[str] = []
        for index, stage in enumerate(GROWTH_STAGES[1:], start=1):
            start = GROWTH_THRESHOLDS[index - 1]
            finish = GROWTH_THRESHOLDS[index]
            if growth >= finish:
                stage_reward_claims.append(stage)
            for percentage in (25, 50, 75):
                checkpoint = start + ((finish - start) * percentage // 100)
                if growth >= checkpoint:
                    checkpoint_claims.append(f"{stage}:{percentage}")
        plant.setdefault("checkpoint_claims", checkpoint_claims)
        plant.setdefault("stage_reward_claims", stage_reward_claims)

        fully_grown = growth >= GROWTH_THRESHOLDS[-1]
        completion_day: str | None = None
        if fully_grown:
            memories = plant.get("memories")
            if isinstance(memories, list):
                for memory in reversed(memories):
                    if (
                        isinstance(memory, dict)
                        and memory.get("kind") == "stage"
                        and memory.get("new_stage") == GROWTH_STAGES[-1]
                        and isinstance(memory.get("occurred_on"), str)
                    ):
                        completion_day = str(memory["occurred_on"])
                        break
            if completion_day is None:
                raw_day = payload.get("last_active_day")
                completion_day = str(raw_day) if isinstance(raw_day, str) else None
        plant.setdefault("completed_on", completion_day)
        plant.setdefault("completed_at_ms", 0)
        plant.setdefault("completion_cards", 0)
        plant.setdefault("completion_active_days", 0)
        plant.setdefault("full_bloom_reward_claimed", fully_grown)

        booster_batch = _legacy_booster_card_effect_batch(
            plant.get("booster"),
            migrated_at=migration_time,
        )
        # Fertilizer remains wall-clock timed. Preserve its current and
        # historical windows exactly; obsolete card fields remain only as a
        # compatibility bridge for experimental schema-22 saves.
        plant.setdefault("fertilizer_card_batches", [])
        plant.setdefault("fertilizer_card_queue", [])
        plant.setdefault(
            "booster_card_batches",
            [booster_batch] if booster_batch is not None else [],
        )
        plant.setdefault("booster_card_queue", [])

    payload.setdefault("streak_growth_remainder_units", active_remainder)

    stats = payload.get("daily_stats")
    if not isinstance(stats, dict):
        stats = {}
        payload["daily_stats"] = stats
    for field_name in (
        "answer_growth_units",
        "instant_growth_units",
        "applied_growth_units",
        "redirected_growth_units",
        "shared_growth_units",
        "stored_growth_units",
    ):
        stats.setdefault(field_name, 0)
    for field_name in (
        "plant_applied_growth_units",
        "plant_shared_growth_units",
        "plant_instant_growth_units",
    ):
        stats.setdefault(field_name, {})

    completed = bool(stats.get("completed_due_cards", False))
    scheduler_day = stats.get("day") if isinstance(stats.get("day"), str) else ""
    daily_completion = payload.get("daily_completion")
    if not isinstance(daily_completion, dict):
        daily_completion = {}
        payload["daily_completion"] = daily_completion
    daily_completion.setdefault("scheduler_day", scheduler_day)
    if not daily_completion.get("scheduler_day"):
        daily_completion["scheduler_day"] = scheduler_day
    daily_completion.setdefault("status", "complete" if completed else "unavailable")
    daily_completion.setdefault("obligation_projection_initialized", False)
    daily_completion.setdefault("starting_required_cards", 0)
    daily_completion.setdefault("starting_required_cards_completed", 0)
    daily_completion.setdefault("remaining_new_cards", 0)
    daily_completion.setdefault("remaining_required_reviews", 0)
    daily_completion.setdefault("remaining_learning_steps", 0)
    daily_completion.setdefault("future_learning_steps_before_cutoff", 0)
    daily_completion.setdefault("next_learning_due_at_ms", 0)
    daily_completion.setdefault("cutoff_at_ms", 0)
    daily_completion.setdefault(
        "cards_completed_today", _legacy_nonnegative_int(stats.get("reviewed"))
    )
    daily_completion.setdefault("unresolved_obligation_disappearances", 0)
    daily_completion.setdefault("reward_claimed", completed)
    daily_completion.setdefault(
        "unavailable_reason", "" if completed else "legacy_projection_unavailable"
    )
    payload.setdefault("daily_loadout", {
        "scheduler_day": "",
        "locked_at_ms": 0,
        "weather_id": "",
        "scenery_id": "",
        "queued_for_day": "",
        "queued_weather_id": "",
        "queued_scenery_id": "",
    })

    transaction_claim = any(
        isinstance(transaction, dict)
        and isinstance(transaction.get("event_key"), str)
        and str(transaction["event_key"]).startswith("all_due:")
        for transaction in (
            payload.get("currency_transactions")
            if isinstance(payload.get("currency_transactions"), list)
            else []
        )
    )
    payload.setdefault(
        "first_daily_completion_reward_claimed", completed or transaction_claim
    )
    legacy_ultra = max(
        _legacy_nonnegative_int(payload.get("garden_find_ultra_misses")),
        _legacy_nonnegative_int(payload.get("ultra_pity_misses")),
    )
    payload.setdefault("environment_pity_misses", {
        "rare": 0,
        "very_rare": 0,
        "ultra": legacy_ultra,
    })
    _migrate_schema23_garden_features_payload(payload)


def _migrate_schema23_garden_features_payload(payload: dict[str, Any]) -> None:
    """Replace persisted Weather ownership with canonical Garden Decorations.

    The transform is deliberately idempotent. It maps only known legacy item
    identities and canonical fields, so unrelated extension-owned state is
    preserved verbatim.
    """

    payload["version"] = STATE_VERSION
    inventory = payload.get("inventory")
    if not isinstance(inventory, dict):
        inventory = {}
        payload["inventory"] = inventory
    legacy_owned = inventory.pop("weather", [])
    current_owned = inventory.get("garden_features", [])
    owned = [
        DEFAULT_GARDEN_FEATURE_ID,
        *(
            legacy_owned if isinstance(legacy_owned, list) else []
        ),
        *(
            current_owned if isinstance(current_owned, list) else []
        ),
    ]
    inventory["garden_features"] = list(dict.fromkeys(
        canonical_garden_feature_id(item)
        for item in owned
        if isinstance(item, str) and item
    ))

    loadout = payload.get("loadout")
    if not isinstance(loadout, dict):
        loadout = {}
        payload["loadout"] = loadout
    raw_feature = loadout.pop(
        "weather_id",
        payload.pop("selected_weather", DEFAULT_GARDEN_FEATURE_ID),
    )
    loadout["garden_feature_id"] = canonical_garden_feature_id(
        loadout.get("garden_feature_id", raw_feature)
    ) or DEFAULT_GARDEN_FEATURE_ID
    visibility = loadout.get("visibility")
    if not isinstance(visibility, dict):
        visibility = {}
    legacy_visibility = payload.get("environment_visibility")
    legacy_visibility = (
        legacy_visibility if isinstance(legacy_visibility, dict) else {}
    )
    legacy_visible = visibility.pop(
        "weather",
        payload.pop(
            "show_garden_feature",
            payload.pop(
                "show_weather",
                legacy_visibility.get("weather", True),
            ),
        ),
    )
    visibility.setdefault("garden_feature", bool(legacy_visible))
    visibility.setdefault("scenery", True)
    loadout["visibility"] = visibility
    payload.pop("environment_visibility", None)

    schedule = payload.get("daily_loadout")
    if not isinstance(schedule, dict):
        schedule = {}
        payload["daily_loadout"] = schedule
    schedule["garden_feature_id"] = canonical_garden_feature_id(
        schedule.get("garden_feature_id", schedule.pop("weather_id", ""))
    )
    schedule["pending_garden_feature_id"] = canonical_garden_feature_id(
        schedule.get(
            "pending_garden_feature_id",
            schedule.pop("queued_weather_id", ""),
        )
    )

    equipped = payload.get("equipped")
    if isinstance(equipped, dict):
        equipped.pop("weather", None)
        equipped["garden_feature"] = loadout["garden_feature_id"]

    def migrate_item_field(records: object, *field_names: str) -> None:
        if not isinstance(records, (list, dict)):
            return
        rows = records.values() if isinstance(records, dict) else records
        for row in rows:
            if not isinstance(row, dict):
                continue
            for field_name in field_names:
                value = row.get(field_name)
                if isinstance(value, str) and value in LEGACY_WEATHER_TO_GARDEN_FEATURE:
                    row[field_name] = canonical_garden_feature_id(value)
            if row.get("environment_kind") == "weather":
                row["environment_kind"] = "garden_feature"
            if row.get("asset_category") == "weather":
                row["asset_category"] = "garden_features"

    migrate_item_field(payload.get("garden_find_outcomes"), "item_id", "reward_id")
    migrate_item_field(payload.get("recent_reward_receipts"), "item_id", "source_id")
    migrate_item_field(payload.get("completed_purchase_requests"), "item_id")
    migrate_item_field(payload.get("pending_feedback"), "item_id", "asset_key")

    claims = payload.get("daily_environment_claims")
    if isinstance(claims, dict):
        payload["daily_environment_claims"] = {
            canonical_garden_feature_id(key): value
            for key, value in claims.items()
        }
    _migrate_schema25_decoration_bonus_payload(payload)


def _migrate_schema25_decoration_bonus_payload(payload: dict[str, Any]) -> None:
    """Split the prior combined decoration choice without losing its value."""

    payload["version"] = STATE_VERSION
    loadout = payload.get("loadout")
    if not isinstance(loadout, dict):
        loadout = {}
        payload["loadout"] = loadout
    prior = canonical_garden_feature_id(
        loadout.pop("garden_feature_id", loadout.pop("weather_id", ""))
    ) or DEFAULT_GARDEN_FEATURE_ID
    loadout.setdefault("displayed_garden_feature_id", prior)
    loadout.setdefault("active_bonus_garden_feature_id", prior)
    visibility = loadout.get("visibility")
    if not isinstance(visibility, dict):
        visibility = {}
    visibility.setdefault("garden_feature", True)
    visibility.setdefault("scenery", True)
    loadout["visibility"] = visibility
    payload.setdefault("wind_chime_progress", 0)
    payload.setdefault("watering_station_progress", 0)
    payload.setdefault("firefly_lantern_progress", 0)
    payload.setdefault("prism_pending_growth_units", 0)
    payload.setdefault("prism_released_anki_day_id", "")
    schedule = payload.get("daily_loadout")
    if not isinstance(schedule, dict):
        schedule = {}
        payload["daily_loadout"] = schedule
    # Existing scenery remains locked, but the revised mechanical bonus starts
    # only with the first eligible post-update answer.
    schedule["garden_bonus_anki_day_id"] = ""
    schedule["garden_bonus_locked_at_ms"] = 0
    schedule["garden_feature_id"] = ""


_BED_MIGRATION = {
    3: (150, "first_canopy", "First Canopy", "Grow any plant to Mature."),
    4: (
        300,
        "first_full_bloom",
        "First Full Bloom",
        "Grow one unique species to Full Bloom.",
    ),
    5: (
        500,
        "growing_garden",
        "Growing Garden",
        "Grow three unique species to Full Bloom.",
    ),
    6: (
        800,
        "flourishing_garden",
        "Flourishing Garden",
        "Grow six unique species to Full Bloom.",
    ),
}


def _migrate_schema26_economy_payload(
    payload: dict[str, Any],
    *,
    migrated_at: float | None = None,
) -> None:
    """Apply the one-way schema-26 economy foundation without inventing history."""

    migration_time = time.time() if migrated_at is None else max(
        0.0, float(migrated_at)
    )
    migrated_iso = datetime.fromtimestamp(
        migration_time, tz=timezone.utc
    ).isoformat()

    loadout = payload.get("loadout")
    if not isinstance(loadout, dict):
        loadout = {}
        payload["loadout"] = loadout
    legacy_feature = canonical_garden_feature_id(
        loadout.get(
            "active_garden_bonus_id",
            loadout.get(
                "active_bonus_garden_feature_id",
                loadout.get("garden_feature_id", loadout.get("weather_id", "")),
            ),
        )
    ) or DEFAULT_GARDEN_FEATURE_ID
    display_feature = canonical_garden_feature_id(
        loadout.get(
            "display_decoration_id",
            loadout.get("displayed_garden_feature_id", legacy_feature),
        )
    ) or legacy_feature
    legacy_scenery = str(
        loadout.get(
            "display_scenery_id",
            loadout.get("scenery_id", DEFAULT_SCENERY_ID),
        )
        or DEFAULT_SCENERY_ID
    )
    loadout["display_decoration_id"] = display_feature
    loadout["active_garden_bonus_id"] = legacy_feature
    loadout["display_scenery_id"] = legacy_scenery
    loadout["active_scenery_effect_id"] = str(
        loadout.get("active_scenery_effect_id", legacy_scenery) or legacy_scenery
    )
    for retired_key in (
        "weather_id",
        "garden_feature_id",
        "displayed_garden_feature_id",
        "active_bonus_garden_feature_id",
        "scenery_id",
    ):
        loadout.pop(retired_key, None)

    inventory = payload.get("inventory")
    if not isinstance(inventory, dict):
        inventory = {}
        payload["inventory"] = inventory
    legacy_cosmetics = inventory.pop("decorations", [])
    current_cosmetics = inventory.get("cosmetics", [])
    cosmetics = list(dict.fromkeys(
        item_id
        for item_id in [
            *(legacy_cosmetics if isinstance(legacy_cosmetics, list) else []),
            *(current_cosmetics if isinstance(current_cosmetics, list) else []),
            *( [display_feature] if display_feature in COSMETIC_DISPLAY_IDS else [] ),
        ]
        if isinstance(item_id, str) and item_id in COSMETIC_DISPLAY_IDS
    ))
    inventory["cosmetics"] = cosmetics

    # The schema-26 Full Bloom threshold is lower than schema 25's. Preserve
    # every valid hundredth-Growth unit by routing only the excess to Stored
    # Growth; this is conservation, not a player-visible compensation grant.
    stored_growth_units = _legacy_nonnegative_int(
        payload.get(
            "stored_growth_units",
            payload.get("stored_growth_balance_units"),
        )
    )
    plant_rows = payload.get("plants")
    for plant in plant_rows if isinstance(plant_rows, list) else []:
        if not isinstance(plant, dict):
            continue
        growth_points = _legacy_nonnegative_int(plant.get("growth_points"))
        remainder_units = min(
            99,
            _legacy_nonnegative_int(plant.get("growth_remainder_units")),
        )
        if growth_points < GROWTH_THRESHOLDS[-1]:
            continue
        overflow_points = max(0, growth_points - GROWTH_THRESHOLDS[-1])
        stored_growth_units += overflow_points * 100 + remainder_units
        plant["growth_points"] = GROWTH_THRESHOLDS[-1]
        plant["growth_remainder_units"] = 0
    payload["stored_growth_units"] = stored_growth_units

    _migrate_timed_fertilizer_to_card_queue(
        payload, migrated_at=migration_time
    )
    consumables = payload.get("consumables")
    if not isinstance(consumables, dict):
        consumables = {}
        payload["consumables"] = consumables
    rich_compost = sum(
        _legacy_nonnegative_int(consumables.pop(key, 0))
        for key in ("rich_compost", "fertilizer_rich")
    )
    consumables["fertilizer_basic"] = (
        _legacy_nonnegative_int(consumables.get("fertilizer_basic"))
        + rich_compost
    )

    payload.setdefault("daily_economy_snapshot", None)
    payload.setdefault("garden_project", {
        "selected_project_id": "",
        "contributed_growth_units": 0,
        "ready_to_complete": False,
        "completed_project_ids": [],
        "displayed_project_id": "",
        "auto_contribute": False,
    })
    payload.setdefault("cultivation_mastery", {
        "highest_rank_by_species": {},
    })
    payload.setdefault("lifetime_economy_aggregates", {
        "coins_earned_by_source": {},
        "coins_spent_by_sink": {},
        "growth_earned_by_source": {},
        "growth_spent_on_landmarks": 0,
        "growth_spent_on_mastery": 0,
        "finds_by_outcome": {},
        "environment_discoveries": {},
        "consumables_earned": {},
        "consumables_used": {},
        "plants_completed": 0,
        "today_cards_completions": 0,
    })
    payload.setdefault("hourglass_completion_progress", 0)
    payload.setdefault("full_moon_completion_progress", 0)
    payload["prism_pending_growth_units"] = min(
        30_000,
        max(
            _legacy_nonnegative_int(payload.get("prism_pending_growth_units")),
            _legacy_nonnegative_int(payload.pop("prism_banked_growth", 0)),
        ),
    )
    payload["environment_completion_pity_misses"] = {
        "rare": 0,
        "very_rare": 0,
        "ultra": 0,
    }

    unlocked_slots = min(
        6, max(2, _legacy_nonnegative_int(payload.get("unlocked_slots"), 2))
    )
    existing_unlocks = payload.get("earned_bed_unlocks")
    earned_unlocks = {
        int(value)
        for value in existing_unlocks
        if isinstance(value, int)
        and not isinstance(value, bool)
        and 3 <= int(value) <= 6
    } if isinstance(existing_unlocks, list) else set()
    earned_unlocks.update(range(3, unlocked_slots + 1))
    payload["earned_bed_unlocks"] = sorted(earned_unlocks)

    achievements = payload.get("achievements")
    if not isinstance(achievements, dict):
        achievements = {}
        payload["achievements"] = achievements
    pending = payload.get("pending_economy_migration_grants")
    pending_rows = list(pending) if isinstance(pending, list) else []
    pending_keys = {
        str(row.get("event_key"))
        for row in pending_rows
        if isinstance(row, dict) and row.get("event_key")
    }
    for bed_number in sorted(earned_unlocks):
        price, achievement_id, name, description = _BED_MIGRATION[bed_number]
        existing_achievement = achievements.get(achievement_id)
        achievement = (
            dict(existing_achievement)
            if isinstance(existing_achievement, dict)
            else {}
        )
        achievement.setdefault("achievement_id", achievement_id)
        achievement.setdefault("name", name)
        achievement.setdefault("description", description)
        achievement["unlocked"] = True
        achievement["progress"] = 1.0
        achievement.setdefault("unlocked_at", migrated_iso)
        achievement.setdefault("category", "completion")
        achievement.setdefault("requirement", description)
        achievement.setdefault("reward_summary", f"Bed {bed_number}")
        achievement.setdefault("rewarded_at", migrated_iso)
        achievement.setdefault(
            "reward_event_key", f"migration:v26:bed_claim:{bed_number}"
        )
        achievement.setdefault("historical_backfill", True)
        achievements[achievement_id] = achievement
        event_key = f"migration:v26:bed_refund:{bed_number}"
        if event_key not in pending_keys:
            pending_rows.append({
                "event_key": event_key,
                "coins": price,
                "reason": f"Schema 26 Bed {bed_number} purchase refund",
                "source_id": "bed_refund",
            })
            pending_keys.add(event_key)

    completed_requests = payload.get("completed_purchase_requests")
    for row in completed_requests if isinstance(completed_requests, list) else []:
        if not isinstance(row, dict):
            continue
        request_id = row.get("request_id")
        outcome = row.get("outcome")
        if (
            not isinstance(request_id, str)
            or not isinstance(outcome, dict)
            or outcome.get("status") != "success"
            or outcome.get("category") != "Plant"
        ):
            continue
        amount_spent = outcome.get("amount_spent")
        if (
            isinstance(amount_spent, bool)
            or not isinstance(amount_spent, int)
            or amount_spent <= 250
        ):
            continue
        event_key = f"migration:v26:plant_refund:{request_id}"
        if event_key in pending_keys:
            continue
        pending_rows.append({
            "event_key": event_key,
            "coins": amount_spent - 250,
            "reason": "Schema 26 recorded plant-price refund",
            "source_id": "plant_price_refund",
        })
        pending_keys.add(event_key)
    payload["pending_economy_migration_grants"] = pending_rows
    payload["version"] = STATE_VERSION


def _migrate_schema27_endgame_payload(
    payload: dict[str, Any],
    *,
    source_version: int,
) -> None:
    """Install cumulative endgame authorities without spending player value."""

    old_stored = _legacy_nonnegative_int(payload.pop("stored_growth_units", 0))
    payload["stored_growth_balance_units"] = (
        old_stored
        if source_version <= 26
        else _legacy_nonnegative_int(
            payload.get("stored_growth_balance_units"), old_stored
        )
    )
    if source_version <= 26:
        payload["stored_growth_opening_balance_units"] = payload[
            "stored_growth_balance_units"
        ]
        payload["stored_growth_opening_balance_source"] = (
            "schema_27_migration_preserved_balance"
        )
        payload["stored_growth_opening_balance_identity"] = (
            STORED_GROWTH_OPENING_IDENTITY_MIGRATION
        )

    project = payload.get("garden_project")
    if not isinstance(project, dict):
        project = {}
    completed_raw = project.get("completed_project_ids", [])
    completed_candidates = (
        {item for item in completed_raw if isinstance(item, str)}
        if isinstance(completed_raw, list) else set()
    )
    completed: list[str] = []
    for project_id in GARDEN_PROJECT_IDS:
        if project_id not in completed_candidates:
            break
        completed.append(project_id)
    claimed = min(
        len(GARDEN_PROJECT_IDS),
        max(
            len(completed),
            _legacy_nonnegative_int(
                project.get("landmark_highest_claimed_tier")
            ),
        ),
    )
    claimed_floor = (
        GARDEN_PROJECT_CUMULATIVE_GROWTH_THRESHOLDS_UNITS[
            GARDEN_PROJECT_IDS[claimed - 1]
        ]
        if claimed else 0
    )
    selected = project.get("selected_project_id")
    partial = _legacy_nonnegative_int(project.get("contributed_growth_units"))
    if not isinstance(selected, str) or selected not in GARDEN_PROJECT_IDS:
        partial = 0
    existing_funded = _legacy_nonnegative_int(
        project.get("landmark_growth_units_funded")
    )
    funded = max(claimed_floor, existing_funded)
    if "landmark_growth_units_funded" not in project:
        funded += partial
    landmark_max = GARDEN_PROJECT_CUMULATIVE_GROWTH_THRESHOLDS_UNITS[
        GARDEN_PROJECT_IDS[-1]
    ]
    funded = min(landmark_max, funded)
    displayed = project.get(
        "displayed_landmark_tier_id",
        project.get("displayed_project_id", ""),
    )
    claimed_ids = list(GARDEN_PROJECT_IDS[:claimed])
    if displayed not in claimed_ids:
        displayed = ""
    project.update({
        "landmark_growth_units_funded": funded,
        "landmark_highest_claimed_tier": claimed,
        "displayed_landmark_tier_id": displayed,
        "grandfathered_funding_units": max(
            _legacy_nonnegative_int(project.get("grandfathered_funding_units")),
            funded if source_version <= 26 else 0,
        ),
        "selected_project_id": "",
        "contributed_growth_units": max(0, funded - claimed_floor),
        "ready_to_complete": False,
        "completed_project_ids": claimed_ids,
        "displayed_project_id": displayed,
        "auto_contribute": False,
    })
    payload["garden_project"] = project

    mastery = payload.get("cultivation_mastery")
    if not isinstance(mastery, dict):
        mastery = {}
    raw_claims = mastery.get(
        "highest_claimed_rank_by_species",
        mastery.get("highest_rank_by_species", {}),
    )
    claims = dict(raw_claims) if isinstance(raw_claims, dict) else {}
    raw_funding = mastery.get("growth_units_funded_by_species", {})
    funding = dict(raw_funding) if isinstance(raw_funding, dict) else {}
    raw_grandfathered = mastery.get(
        "grandfathered_funding_units_by_species", {}
    )
    grandfathered = (
        dict(raw_grandfathered) if isinstance(raw_grandfathered, dict) else {}
    )
    for species_id, rank_id in list(claims.items()):
        if rank_id not in CULTIVATION_MASTERY_RANKS:
            continue
        floor = CULTIVATION_MASTERY_CUMULATIVE_GROWTH_THRESHOLDS_UNITS[rank_id]
        funding[species_id] = max(
            floor, _legacy_nonnegative_int(funding.get(species_id))
        )
        if source_version <= 26:
            grandfathered[species_id] = max(
                floor,
                _legacy_nonnegative_int(grandfathered.get(species_id)),
            )
    for species_id in CURRENT_CATALOG_SPECIES_ORDER:
        amount = min(
            MASTERY_MAX_GROWTH_UNITS_PER_SPECIES,
            _legacy_nonnegative_int(funding.get(species_id)),
        )
        if amount:
            funding[species_id] = amount
            if source_version <= 26:
                grandfathered[species_id] = max(
                    amount,
                    _legacy_nonnegative_int(grandfathered.get(species_id)),
                )
    mastery.update({
        "growth_units_funded_by_species": funding,
        "highest_claimed_rank_by_species": claims,
        "grandfathered_funding_units_by_species": grandfathered,
        "highest_rank_by_species": claims,
    })
    payload["cultivation_mastery"] = mastery

    payload["active_growth_target_type"] = ""
    payload["active_growth_target_id"] = ""
    payload["active_growth_target_activation_identity"] = ""
    if source_version <= 26:
        payload["garden_legacy_level"] = 0
        payload["garden_legacy_progress_units"] = 0
    else:
        payload.setdefault("garden_legacy_level", 0)
        payload.setdefault("garden_legacy_progress_units", 0)

    aggregates = payload.get("lifetime_economy_aggregates")
    if not isinstance(aggregates, dict):
        aggregates = {}
    for key in (
        "growth_generated_units",
        "growth_applied_to_plants_units",
        "growth_routed_to_storage_units_lifetime",
        "growth_contributed_to_landmarks_units",
        "growth_contributed_to_mastery_units",
        "growth_contributed_to_legacy_units",
        "growth_unallocated_overflow_units",
    ):
        aggregates.setdefault(key, 0)
    if source_version <= 26:
        aggregates["history_complete"] = False
        aggregates.setdefault(
            "authoritative_from_event_identity", "migration:schema27"
        )
    payload["lifetime_economy_aggregates"] = aggregates
    payload["version"] = STATE_VERSION


def migrate_previous_state(raw: Any) -> GardenState:
    """Convert the supported schema-10 release into the current state contract.

    The migration preserves identity, stage-relative Growth, collection unlocks,
    stories, aggregate review history, slots, and the revlog cursor. Removed
    Quest, history-import, rare-variant, and the removed seven-day score systems are not
    carried into the new single-progression model.
    """
    if not isinstance(raw, dict) or raw.get("version") != PREVIOUS_STATE_VERSION:
        raise ValueError("only schema 10 can be migrated")
    legacy_stats = raw.get("daily_stats") if isinstance(raw.get("daily_stats"), dict) else {}
    reviewed_today = _legacy_nonnegative_int(legacy_stats.get("reviewed"))
    legacy_inventory = raw.get("inventory") if isinstance(raw.get("inventory"), dict) else {}
    unlocked_species = [
        item for item in legacy_inventory.get("plants", [])
        if isinstance(item, str) and item in PLANT_SPECIES
    ]
    migrated_plants: list[dict[str, Any]] = []
    for plant in raw.get("plants", []) if isinstance(raw.get("plants"), list) else []:
        if not isinstance(plant, dict):
            continue
        species = plant.get("species")
        if isinstance(species, str) and species in PLANT_SPECIES:
            unlocked_species.append(species)
        migrated_plants.append({
            "plant_id": plant.get("plant_id"),
            "species": species,
            "name": plant.get("name"),
            "slot_index": plant.get("slot_index"),
            "growth_points": _migrate_legacy_growth(plant.get("growth_points")),
            "bonus_remainder": 0,
            "personality": plant.get("personality", "balanced"),
            "planted_on": plant.get("planted_on"),
            "memories": _migrate_legacy_memories(plant.get("memories")),
            "fertilizer": None,
            # Every nonblank schema-10 name is treated as learner-owned copy.
            # There is no reliable historical marker that distinguishes an
            # accepted generated name from a manually edited one.
            "name_customized": bool(
                isinstance(plant.get("name"), str) and plant.get("name").strip()
            ),
        })
    current_inventory = {
        key: value for key, value in legacy_inventory.items()
        if key in {"pots", "backgrounds", "weather"}
    }
    payload = {
        "version": STATE_VERSION,
        "garden_name": DEFAULT_GARDEN_NAME,
        # Migrated gardens must not be interrupted by the new first-run name
        # prompt. Learners can still rename the garden in Settings.
        "garden_setup_version": 1,
        "streak_days": raw.get("streak_days"),
        "total_reviews": raw.get("total_reviews"),
        "total_correct": raw.get("total_correct"),
        "total_wrong": raw.get("total_wrong"),
        "unlocked_slots": raw.get("unlocked_slots"),
        "unlocked_species": list(dict.fromkeys(unlocked_species)),
        "starter_selection_complete": bool(migrated_plants or unlocked_species),
        "onboarding": {
            "version": 1,
            "step": "done" if (migrated_plants or unlocked_species) else "introduction",
            "pending_species": None,
            "starter_plant_id": (
                migrated_plants[0].get("plant_id") if migrated_plants else None
            ),
        },
        "selected_background": raw.get("selected_background"),
        "selected_weather": raw.get("selected_weather"),
        "plants": migrated_plants,
        "achievements": raw.get("achievements"),
        "daily_stats": {
            "day": legacy_stats.get("day"),
            "reviewed": reviewed_today,
            "correct": legacy_stats.get("correct"),
            "wrong": legacy_stats.get("wrong"),
            "new_count": legacy_stats.get("new_count"),
            "learning_count": legacy_stats.get("learning_count"),
            "review_count": legacy_stats.get("review_count"),
            "difficult_count": legacy_stats.get("difficult_count"),
            "recovered_lapses": legacy_stats.get("recovered_lapses"),
            # Legacy Growth used different rules and is already represented in
            # the proportionally migrated plant totals. Do not count it twice.
            "base_growth": 0,
            "bonus_growth": 0,
            "growth_earned": 0,
            "plant_growth": {},
            "completed_due_cards": bool(legacy_stats.get("completed_due_cards", False)),
        },
        "currency_balance": 0,
        "currency_transactions": [],
        "claimed_streak_rewards": [],
        "pending_feedback": [],
        "inventory": current_inventory,
        "equipped": raw.get("equipped"),
        "last_active_day": raw.get("last_active_day"),
        "active_plant_id": raw.get("focus_plant_id"),
        "active_plant_periods": [],
        "last_processed_revlog_id": raw.get("retrospective_last_revlog_id"),
        "processed_revlog_floor": raw.get("retrospective_last_revlog_id"),
        "processed_revlog_ids": [],
        "revlog_ledger_migration_pending": True,
        "scene_geometry_version": 0,
    }
    _migrate_loadout_payload(payload)
    _migrate_reward_state_payload(payload)
    _migrate_schema22_progression_payload(payload)
    _migrate_schema26_economy_payload(payload)
    _migrate_schema27_endgame_payload(payload, source_version=PREVIOUS_STATE_VERSION)
    return _materialize_unlocked_species(GardenState.from_dict(payload))


def _migrate_schema28_equipment_payload(payload: dict[str, Any]) -> None:
    """Keep the displayed selections and retire independent effect scheduling."""
    payload["version"] = STATE_VERSION
    payload.pop("daily_loadout", None)
    loadout = payload.get("loadout")
    if isinstance(loadout, dict):
        for key in ("active_garden_bonus_id", "active_scenery_effect_id",
                    "active_bonus_garden_feature_id"):
            loadout.pop(key, None)


def migrate_modern_state(
    raw: Any,
    *,
    migrated_at: float | None = None,
    onboarding_version: Any = 0,
) -> GardenState:
    """Add current preservation boundaries to a previous modern state.

    Those schemas already use the current progression model, so their payload
    can be validated by the current contract after changing only the schema
    version and marking the pre-existing garden as established.
    """
    if (
        not isinstance(raw, dict)
        or raw.get("version") not in MODERN_PREVIOUS_STATE_VERSIONS
    ):
        raise ValueError("only previous modern schemas can use the modern migration")
    payload = deepcopy(raw)
    source_version = int(payload.get("version", 0) or 0)
    def finish(*, materialize: bool = True) -> GardenState:
        if source_version < 26:
            _migrate_schema26_economy_payload(payload, migrated_at=migrated_at)
        if source_version < 27:
            _migrate_schema27_endgame_payload(
                payload, source_version=source_version
            )
        _migrate_schema28_equipment_payload(payload)
        state = GardenState.from_dict(payload)
        return _materialize_unlocked_species(state) if materialize else state

    if source_version in {26, 27, 28, 29}:
        return finish()
    if source_version == 25:
        payload.setdefault("pending_sync_reward_summary", None)
        return finish()
    if source_version == 24:
        _migrate_schema25_decoration_bonus_payload(payload)
        payload.setdefault("pending_sync_reward_summary", None)
        return finish()
    if source_version == 23:
        _migrate_schema25_decoration_bonus_payload(payload)
        payload.setdefault("pending_sync_reward_summary", None)
        return finish()
    if source_version == 22:
        _migrate_schema23_garden_features_payload(payload)
        payload.setdefault("pending_sync_reward_summary", None)
        return finish()
    if source_version == 21:
        _migrate_schema22_progression_payload(payload, migrated_at=migrated_at)
        return finish()
    if source_version == 20:
        payload["version"] = STATE_VERSION
        payload.setdefault("completed_purchase_requests", [])
        _migrate_reward_state_payload(payload)
        _migrate_schema22_progression_payload(payload, migrated_at=migrated_at)
        return finish(materialize=False)
    if source_version == 19:
        payload["version"] = STATE_VERSION
        payload.setdefault("completed_purchase_requests", [])
        _migrate_growth_accounting_payload(payload)
        _migrate_reward_state_payload(payload)
        _migrate_schema22_progression_payload(payload, migrated_at=migrated_at)
        return finish(materialize=False)
    if source_version in {17, 18}:
        # Schemas 17 and 18 already own every progression, onboarding, and
        # revlog field. Preserve their bounded purchase replay history while
        # collapsing only the duplicate environment mirrors.
        payload["version"] = STATE_VERSION
        payload.setdefault("completed_purchase_requests", [])
        _migrate_loadout_payload(payload)
        _migrate_growth_accounting_payload(payload)
        _migrate_reward_state_payload(payload)
        _migrate_schema22_progression_payload(payload, migrated_at=migrated_at)
        return finish(materialize=False)
    _add_legacy_fertilizer_activation_boundaries(
        payload,
        time.time() if migrated_at is None else migrated_at,
    )
    payload["version"] = STATE_VERSION
    payload.setdefault("eligible_reward_count", 0)
    payload.setdefault("ultra_pity_misses", 0)
    payload.setdefault("daily_environment_claims", {})
    payload.setdefault("environment_completion_counts", {})
    payload.setdefault("environment_visibility", {"weather": True, "scenery": True})
    payload.setdefault("garden_name", DEFAULT_GARDEN_NAME)
    payload.setdefault("completed_purchase_requests", [])
    _migrate_growth_accounting_payload(payload)
    if source_version < 16:
        payload["garden_setup_version"] = 1
    plants = payload.get("plants")
    if isinstance(plants, list):
        for plant in plants:
            if not isinstance(plant, dict):
                continue
            existing_name = plant.get("name")
            plant.setdefault(
                "name_customized",
                bool(isinstance(existing_name, str) and existing_name.strip()),
            )
    raw_unlocked = payload.get("unlocked_species")
    has_collection_evidence = bool(
        (isinstance(plants, list) and any(isinstance(plant, dict) for plant in plants))
        or (isinstance(raw_unlocked, list) and any(isinstance(value, str) for value in raw_unlocked))
    )
    if source_version < 16:
        payload["starter_selection_complete"] = has_collection_evidence
    planted = [
        plant for plant in (plants if isinstance(plants, list) else [])
        if isinstance(plant, dict) and plant.get("slot_index") is not None
    ]
    starter_id = planted[0].get("plant_id") if planted else None
    has_first_nurture = any(
        isinstance(memory, dict) and memory.get("kind") in {"first_nurture", "first_focus"}
        for plant in planted
        for memory in (
            plant.get("memories") if isinstance(plant.get("memories"), list) else []
        )
    )
    try:
        legacy_onboarding_version = max(0, int(onboarding_version or 0))
    except (TypeError, ValueError):
        legacy_onboarding_version = 0
    if not has_collection_evidence:
        onboarding_step = "introduction"
    elif (
        source_version == 16
        and bool(planted)
        and int(payload.get("garden_setup_version", 0) or 0) < 1
        and not has_first_nurture
        and not payload.get("active_plant_id")
        and legacy_onboarding_version < 3
    ):
        onboarding_step = "nurture"
    else:
        onboarding_step = "done"
    payload["onboarding"] = {
        "version": 1,
        "step": onboarding_step,
        "pending_species": None,
        "starter_plant_id": starter_id,
    }
    payload["processed_revlog_floor"] = payload.get("last_processed_revlog_id", 0)
    payload["processed_revlog_ids"] = []
    payload["revlog_ledger_migration_pending"] = True
    _migrate_loadout_payload(payload)
    _migrate_reward_state_payload(payload)
    _migrate_schema22_progression_payload(payload, migrated_at=migrated_at)
    return finish()


@dataclass(frozen=True)
class DueObligationStatus:
    review_count: int = 0
    learning_count: int = 0
    available: bool = True
    error: str = ""
    future_learning_count: int = 0
    next_learning_due_at_ms: int = 0
    cutoff_at_ms: int = 0
    new_count: int = 0
    committed_card_ids: tuple[int, ...] = ()
    card_transitions: tuple[tuple[int, str], ...] = ()
    buried_sibling_card_ids: tuple[int, ...] = ()

    @property
    def committed_card_classification_complete(self) -> bool:
        """Whether every requested card has one usable post-answer state."""

        requested = {
            max(0, int(card_id)) for card_id in self.committed_card_ids
            if max(0, int(card_id)) > 0
        }
        if not requested:
            return False
        transitions = {
            max(0, int(card_id)): str(state)
            for card_id, state in self.card_transitions
            if max(0, int(card_id)) > 0
        }
        return requested == set(transitions) and all(
            transitions[card_id] in {
                "completed", "remaining", "buried", "suspended"
            }
            for card_id in requested
        )

    @property
    def remaining(self) -> int:
        return (
            max(0, int(self.new_count))
            + max(0, int(self.learning_count))
            + max(0, int(self.review_count))
        )

    @property
    def complete(self) -> bool:
        return self.available and not self.error and self.remaining == 0

    @property
    def currently_due(self) -> int:
        return (
            max(0, int(self.new_count))
            + max(0, int(self.review_count))
            + max(
                0,
                int(self.learning_count)
                - max(0, int(self.future_learning_count)),
            )
        )


@dataclass(frozen=True)
class ReviewStreakSnapshot:
    """Consecutive Anki scheduler days derived from authoritative revlog rows."""

    days: int = 0
    latest_day: str = ""
    studied_today: bool = False


@dataclass(frozen=True)
class HistoricalReviewEntry:
    """One eligible Anki review with its original scheduler-day identity."""

    revlog_id: int
    card_id: int
    ease: int
    interval: int
    last_interval: int
    factor: int
    response_time_ms: int
    review_type: int
    answer_ms: int
    scheduler_day: str
    card_day_ordinal: int = 0
    answer_identity: str = ""

    @property
    def stable_answer_key(self) -> str:
        """Lineage key retained when undo/reanswer replaces a revlog row."""

        return self.answer_identity or _answer_lineage_key(
            self.scheduler_day,
            self.card_id,
            max(1, self.card_day_ordinal),
        )

    def as_revlog_row(self) -> tuple[int, int, int, int, int, int, int, int]:
        """Return the established row shape consumed by reviewer mapping."""

        return (
            self.revlog_id,
            self.card_id,
            self.ease,
            self.interval,
            self.last_interval,
            self.factor,
            self.response_time_ms,
            self.review_type,
        )


@dataclass(frozen=True)
class HistoricalReviewPage:
    entries: tuple[HistoricalReviewEntry, ...]
    high_water_revlog_id: int
    next_after_id: int
    has_more: bool


@dataclass(frozen=True)
class HistoricalReviewSnapshot:
    entries: tuple[HistoricalReviewEntry, ...]
    high_water_revlog_id: int
    fingerprint: str
    answer_lineage_bindings: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class IndexedHistoricalReviewSnapshot:
    entries: tuple[HistoricalReviewEntry, ...]
    high_water_revlog_id: int
    fingerprint: str
    history: Any
    closed_history: Any
    days: tuple[dict[str, Any], ...]
    day_answer_numbers: Mapping[int, int]

    def streaks(self) -> dict[str, int]:
        result: dict[str, int] = {}
        previous = None
        run = 0
        for summary in self.days:
            day = date.fromisoformat(summary["day"])
            run = run + 1 if previous is not None and day == previous + timedelta(days=1) else 1
            result[summary["day"]] = run
            previous = day
        return result

    def active_after(self, day: str, activation_ms: int) -> bool:
        return any(row["day"] == day and int(row["last"]) >= activation_ms for row in self.days)


@dataclass(frozen=True)
class LocalAnswerProof:
    """One unambiguous appended answer plus its card/day lineage context."""

    row: tuple[Any, ...]
    card_day_rows: tuple[tuple[Any, ...], ...]


class GardenStorage:
    _reward_ledger: RewardLedger | None = None
    _ledger_revision: int = 0

    def __init__(self, mw: Any, config: Any, *, deferred: bool = False,
                 data_dir: Path | None = None, addon_dir: Path | None = None) -> None:
        self.runtime_pending = bool(deferred)
        self._runtime_initialized = not deferred
        self._allow_runtime_commit = False
        self.history_index = None
        self._due_snapshot = None
        self._due_snapshot_collection = None
        self.mw = mw
        self.config = config
        self.addon_dir = addon_dir or Path(__file__).parent
        # Production supplies the uninstall-independent directory. Keep the
        # legacy default for standalone migration and development callers.
        self.user_files_dir = data_dir or self.addon_dir / "user_files"
        self.data_path = self.user_files_dir / "garden_state.json"
        self.database_path = self.user_files_dir / REWARD_DATABASE_FILENAME
        self.assets_root = self.addon_dir / "assets"
        self.metadata_dir = self.addon_dir / "user_files"
        self.cache_dir = self.metadata_dir / "cache"
        self.asset_metadata = self.metadata_dir / "asset_metadata.json"
        self._reward_ledger: RewardLedger | None = None
        self._ledger_revision = 0
        try:
            self.state = self._load_authoritative_state()
            self._initialize_activity_history()
            self._initialize_activity_drop_counts()
            if self._reward_ledger is not None and self._reward_ledger.interrupt_activity_sessions():
                committed = self._reward_ledger.commit_state(self._bounded_state_payload(self.state),
                    schema_version=STATE_VERSION, expected_revision=self._ledger_revision)
                self._ledger_revision = committed.revision
            if not deferred:
                self._ensure_defaults()
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        """Release the writer without committing unfinished transactions."""
        if self._reward_ledger is not None:
            self._reward_ledger.close()
            self._reward_ledger = None
        self.runtime_pending = True

    def reopen(self) -> None:
        """Reopen the same shared store after a profile switch."""
        if self._reward_ledger is not None:
            return
        if not self.database_path.is_file():
            raise StatePreservationError("Garden's saved database is missing; progress was not reset.")
        existing_state = self.state
        try:
            loaded = self._load_authoritative_state()
        except Exception:
            self.close()
            raise
        # Engine and open views hold this object across profile switches.
        existing_state.__dict__.clear()
        existing_state.__dict__.update(loaded.__dict__)
        self.state = existing_state
        self.history_index = None
        self._due_snapshot = None
        self._due_snapshot_collection = None

    def _initialize_activity_history(self) -> None:
        """Preserve available old receipts once; never infer review sessions."""
        from .activity import event_from_economy, event_from_transaction, transaction_event_key
        ledger = self._reward_ledger
        if ledger is None:
            return
        operation_id = "activity-history-v1"
        if ledger.idempotency_record("migration", operation_id) is not None:
            return
        checkpoint = ledger.checkpoint()
        try:
            for _rowid, record in ledger.iter_economy_events(legacy_activity_only=True):
                if record.coins_earned or record.coins_spent or (
                    record.event_kind != "answer_growth" and
                    (record.growth_generated_units or record.quantity)
                ):
                    ledger.stage_activity_event(event_from_economy(record, state=self.state, earlier=True))
            for transaction in self.state.currency_transactions:
                if ledger.activity_event(transaction_event_key(transaction)) is None:
                    ledger.stage_activity_event(event_from_transaction(transaction))
            ledger.stage_idempotency_record(IdempotencyRecord(
                "migration", operation_id, operation_id, {"status": "applied"},
                datetime.now(timezone.utc).isoformat()))
            committed = ledger.commit_state(self._bounded_state_payload(self.state),
                schema_version=STATE_VERSION, expected_revision=self._ledger_revision)
            self._ledger_revision = committed.revision
        except Exception:
            ledger.rollback(checkpoint)
            raise

    def _initialize_activity_drop_counts(self) -> None:
        """Upgrade saved display totals once without changing earned rewards."""
        ledger = self._reward_ledger
        operation_id = "activity-items-and-finds-v1"
        if ledger is None or ledger.idempotency_record("migration", operation_id) is not None:
            return
        checkpoint = ledger.checkpoint()
        try:
            ledger.stage_activity_drop_count_upgrade()
            ledger.stage_idempotency_record(IdempotencyRecord(
                "migration", operation_id, operation_id, {"status": "applied"},
                datetime.now(timezone.utc).isoformat()))
            committed = ledger.commit_state(self._bounded_state_payload(self.state),
                schema_version=STATE_VERSION, expected_revision=self._ledger_revision)
            self._ledger_revision = committed.revision
        except Exception:
            ledger.rollback(checkpoint)
            raise

    def begin_activity_session(self, session_id: str, started_at: str) -> None:
        from .activity import ActivitySession
        if self._reward_ledger is not None:
            self._reward_ledger.stage_activity_session(ActivitySession(session_id, started_at=started_at))

    def finish_activity_session(self, session_id: str, ended_at: str) -> None:
        from .activity import ActivitySession
        ledger = self._reward_ledger
        if ledger is None:
            return
        checkpoint = ledger.checkpoint()
        try:
            ledger.stage_activity_session(ActivitySession(session_id, ended_at=ended_at, status="ended"))
            if not getattr(self, "runtime_pending", False):
                self.save()
        except Exception:
            ledger.rollback(checkpoint)
            raise

    def stage_activity_economy_event(self, record: EconomyEventRecord, *, correlation_id: str = "") -> None:
        from .activity import event_from_economy
        if self._reward_ledger is not None:
            self._reward_ledger.stage_activity_event(event_from_economy(
                record, state=self.state, correlation_id=correlation_id))

    def stage_activity_answer(self, result: Any, *, answer_key: str, window_token: str = "",
                              batch_id: str = "") -> None:
        from dataclasses import replace
        from .activity import ActivityEvent, ActivitySession, iso_from_ms
        ledger = self._reward_ledger
        if ledger is None or not result.event_id:
            return
        occurred = iso_from_ms(result.occurred_at_ms)
        if window_token:
            group_id, kind = f"review-session:{window_token}", "session"
        else:
            kind = "sync" if result.origin in {"historical_sync", "sync"} else "study"
            group_id = f"{kind}:{batch_id or result.event_id}:{result.scheduler_day}"
        # Existing session metadata keeps its observed beginning and end. Recovered
        # answers can still attach after the reviewer has already closed.
        ledger.stage_activity_session(ActivitySession(group_id, kind,
            status="open" if kind == "session" else "recorded"))
        ledger.stage_activity_event(ActivityEvent(
            f"study:{answer_key}", group_id, result.scheduler_day, occurred,
            "card_answer", result.correlation_id, card_answers=result.cards_completed))
        keys = {f"answer-growth:{answer_key}",
                *(tx.event_key for tx in result.currency_transactions),
                *(receipt.event_key for receipt in result.reward_receipts)}
        keys.update(event.event_key for event in ledger.pending_activity_events()
                    if event.correlation_id == result.correlation_id
                    and event.scheduler_day == result.scheduler_day
                    and event.group_id == event.event_key)
        for key in keys:
            event = ledger.activity_event(key)
            if event is not None and not event.adjustment and event.coins >= 0:
                ledger.stage_activity_event(replace(event, group_id=group_id,
                    occurred_at=occurred, scheduler_day=result.scheduler_day))

    def activity_entries(self, **kwargs: Any) -> tuple[Any, ...]:
        return self._reward_ledger.activity_entries(**kwargs) if self._reward_ledger else ()

    def activity_details(self, group_id: str) -> tuple[Any, ...]:
        return self._reward_ledger.activity_details(group_id) if self._reward_ledger else ()

    def activity_day_totals(self, day: str) -> dict[str, int]:
        return self._reward_ledger.activity_day_totals(day) if self._reward_ledger else {}

    def _load_authoritative_state(self) -> GardenState:
        """Load the SQLite authority, or atomically import the legacy JSON."""

        self.user_files_dir.mkdir(parents=True, exist_ok=True)
        if self.database_path.exists():
            ledger: RewardLedger | None = None
            try:
                ledger = RewardLedger(self.database_path)
                snapshot = ledger.load_state_snapshot()
                if snapshot is None:
                    raise RewardLedgerSchemaError(
                        "The Garden state snapshot uses an unsupported schema."
                    )
                if snapshot.schema_version in MODERN_PREVIOUS_STATE_VERSIONS:
                    backup = self.database_path.with_suffix(
                        f".schema-{snapshot.schema_version}.legacy-{time.time_ns()}.sqlite3"
                    )
                    try:
                        ledger.backup_to(backup)
                    except Exception as backup_error:
                        raise StatePreservationError(
                            "Anki Garden could not preserve its legacy reward database."
                        ) from backup_error
                    state = migrate_modern_state(
                        dict(snapshot.payload), migrated_at=time.time()
                    )
                    if snapshot.schema_version < 27:
                        self._initialize_schema27_migration_metadata(ledger, state)
                        self._stage_legacy_economy_idempotency(ledger, state)
                        self._apply_pending_economy_migration_grants(ledger, state)
                    committed = ledger.commit_state(
                        self._bounded_state_payload(state),
                        schema_version=STATE_VERSION,
                        expected_revision=snapshot.revision,
                    )
                    ledger.integrity_check()
                    self._reward_ledger = ledger
                    self._ledger_revision = committed.revision
                    self._refresh_reanswer_hint_cache(state)
                    self._refresh_recent_find_cache(state)
                    logger.info(
                        "Anki Garden: migrated authoritative schema %s at %s to schema %s",
                        snapshot.schema_version, backup,
                        STATE_VERSION,
                    )
                    return state
                if snapshot.schema_version != STATE_VERSION:
                    raise RewardLedgerSchemaError(
                        "The Garden state snapshot uses an unsupported schema."
                    )
                self._reward_ledger = ledger
                payload = deepcopy(dict(snapshot.payload))
                state = _materialize_unlocked_species(
                    GardenState.from_dict(payload)
                )
                self._ledger_revision = snapshot.revision
                # Validate every exact endgame and Stored Growth authority at
                # the reload boundary, before any repair can save the state.
                self.state = state
                if not getattr(self, "runtime_pending", False):
                    # Direct storage users retain synchronous validation;
                    # Anki startup verifies a private copy in the background.
                    ledger.reset_economy_projections()
                    self.refresh_lifetime_economy_aggregates()
                self._refresh_reanswer_hint_cache(state)
                self._refresh_recent_find_cache(state)
                return state
            except Exception as error:
                logger.exception("Anki Garden: authoritative reward database is unreadable")
                backup = self.database_path.with_suffix(
                    f".invalid-{time.time_ns()}.sqlite3"
                )
                try:
                    if ledger is not None:
                        try:
                            ledger.backup_to(backup)
                        except Exception:
                            # A structurally damaged database may be impossible
                            # to back up through SQLite. Preserve its complete
                            # raw file family instead of silently losing WAL.
                            ledger.close()
                            ledger = None
                            _required_sqlite_family_backup(
                                self.database_path, backup
                            )
                    else:
                        _required_sqlite_family_backup(
                            self.database_path, backup
                        )
                except Exception as backup_error:
                    raise StatePreservationError(
                        "Anki Garden could not preserve its unreadable reward database."
                    ) from backup_error
                finally:
                    if ledger is not None:
                        ledger.close()
                raise StatePreservationError(
                    "Anki Garden preserved an unreadable reward database and stopped before overwriting it."
                ) from error

        state = self._load()
        self._install_reward_database(state)
        return state

    @staticmethod
    def _bounded_state_payload(state: GardenState) -> dict[str, Any]:
        # Every caller immediately passes this to commit_state(), which JSON
        # encodes and detaches it before opening the transaction. Avoid a
        # second full copy here; rollback snapshots still use to_dict().
        payload = state.to_dict(detached=False)
        for key in UNBOUNDED_STATE_AUTHORITY_KEYS:
            payload.pop(key, None)
        return payload

    @staticmethod
    def _clear_unbounded_state_authorities(state: GardenState) -> None:
        state.applied_reward_event_keys = []
        state.processed_answer_keys = []
        state.answer_lineage_bindings = {}
        state.pending_reanswer_lineages = {}
        state.finalized_day_fingerprints = {}
        state.garden_find_daily_counts = {}
        state.garden_find_reward_daily_counts = {}
        state.garden_find_outcomes = {}

    @staticmethod
    def _initialize_schema27_migration_metadata(
        ledger: RewardLedger,
        state: GardenState,
    ) -> None:
        """Record conservative, retry-safe schema-27 migration provenance."""

        operation_id = SCHEMA27_ECONOMY_AUTHORITY_OPERATION_ID
        existing = ledger.idempotency_record("migration", operation_id)
        if existing is not None:
            return
        landmark_funding = max(
            0,
            min(
                LANDMARK_MAX_GROWTH_UNITS,
                int(state.garden_project.landmark_growth_units_funded),
            ),
        )
        state.garden_project.grandfathered_funding_units = landmark_funding
        mastery_funding = {
            species_id: min(
                MASTERY_MAX_GROWTH_UNITS_PER_SPECIES,
                max(
                    0,
                    int(
                        state.cultivation_mastery
                        .growth_units_funded_by_species.get(species_id, 0)
                    ),
                ),
            )
            for species_id in CURRENT_CATALOG_SPECIES_ORDER
            if int(
                state.cultivation_mastery
                .growth_units_funded_by_species.get(species_id, 0)
            ) > 0
        }
        state.cultivation_mastery.grandfathered_funding_units_by_species = (
            dict(mastery_funding)
        )
        landmark_claimed = max(
            0,
            min(
                len(GARDEN_PROJECT_IDS),
                int(state.garden_project.landmark_highest_claimed_tier),
            ),
        )
        mastery_claims = {
            species_id: rank_id
            for species_id, rank_id in (
                state.cultivation_mastery
                .highest_claimed_rank_by_species.items()
            )
            if species_id in CURRENT_CATALOG_SPECIES_ORDER
            and rank_id in CULTIVATION_MASTERY_RANKS
        }
        legacy_total = (
            max(0, int(state.garden_legacy_level))
            * GARDEN_LEGACY_LEVEL_COST_UNITS
            + max(0, int(state.garden_legacy_progress_units))
        )
        payload = {
            "endgame_reconciliation_version": (
                SCHEMA27_ENDGAME_RECONCILIATION_VERSION
            ),
            "lifetime_growth_history_complete": bool(
                state.lifetime_economy_aggregates.history_complete
            ),
            "lifetime_growth_history_authority": str(
                state.lifetime_economy_aggregates
                .authoritative_from_event_identity
                or operation_id
            ),
            "stored_growth_opening_balance_units": (
                state.stored_growth_opening_balance_units
            ),
            "stored_growth_opening_balance_source": (
                state.stored_growth_opening_balance_source
            ),
            "stored_growth_opening_balance_identity": (
                state.stored_growth_opening_balance_identity
            ),
            "landmark_grandfathered_funding_units": (
                landmark_funding
            ),
            "landmark_highest_claimed_tier_baseline": landmark_claimed,
            "mastery_grandfathered_funding_units_by_species": dict(
                mastery_funding
            ),
            "mastery_highest_claimed_rank_baseline_by_species": mastery_claims,
            "garden_legacy_total_units_baseline": legacy_total,
        }
        fingerprint = hashlib.sha256(json.dumps(
            payload, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest()
        ledger.stage_idempotency_record(IdempotencyRecord(
            operation_kind="migration",
            operation_id=operation_id,
            request_fingerprint=fingerprint,
            outcome={"status": "applied", **payload},
            occurred_at=datetime.now(timezone.utc).isoformat(),
        ))

    @staticmethod
    def _apply_pending_economy_migration_grants(
        ledger: RewardLedger,
        state: GardenState,
    ) -> None:
        """Stage deterministic migration refunds with the state that receives them."""

        retained: list[PendingEconomyMigrationGrant] = []
        for grant in state.pending_economy_migration_grants:
            existing = ledger.idempotency_record("migration", grant.event_key)
            if existing is not None:
                continue
            fingerprint = hashlib.sha256(
                json.dumps(
                    {
                        "event_key": grant.event_key,
                        "coins": grant.coins,
                        "source_id": grant.source_id,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            occurred_at = datetime.now(timezone.utc).isoformat()
            balance = max(0, int(state.currency_balance)) + grant.coins
            transaction_id = str(uuid.uuid5(
                uuid.NAMESPACE_URL, "anki-garden:" + grant.event_key
            ))
            state.currency_balance = balance
            state.currency_transactions.append(CurrencyTransaction(
                transaction_id=transaction_id,
                event_key=grant.event_key,
                reason=grant.reason,
                delta=grant.coins,
                balance=balance,
                occurred_at=occurred_at,
                transaction_type="credit",
                source="migration",
                source_id=grant.source_id,
                correlation_id=grant.event_key,
            ))
            state.currency_transactions = state.currency_transactions[
                -MAX_TRANSACTION_HISTORY:
            ]
            current = state.lifetime_economy_aggregates.coins_earned_by_source
            current[grant.source_id] = (
                max(0, int(current.get(grant.source_id, 0))) + grant.coins
            )
            ledger.stage_idempotency_record(IdempotencyRecord(
                operation_kind="migration",
                operation_id=grant.event_key,
                request_fingerprint=fingerprint,
                outcome={
                    "status": "applied",
                    "coins": grant.coins,
                    "balance": balance,
                },
                occurred_at=occurred_at,
            ))
            ledger.stage_economy_event(EconomyEventRecord(
                event_key=grant.event_key,
                event_kind="migration_refund",
                source_id=grant.source_id,
                occurred_at=occurred_at,
                coins_earned=grant.coins,
            ))
        state.pending_economy_migration_grants = retained

    def _install_reward_database(self, state: GardenState) -> None:
        """Import one JSON state into a temporary database, then install it."""

        temporary = self.user_files_dir / (
            f".{REWARD_DATABASE_FILENAME}.{uuid.uuid4().hex}.tmp"
        )
        portable = self.user_files_dir / (
            f".{REWARD_DATABASE_FILENAME}.{uuid.uuid4().hex}.install"
        )
        ledger: RewardLedger | None = None
        try:
            ledger = RewardLedger(temporary)
            self._stage_legacy_authorities(ledger, state)
            self._initialize_schema27_migration_metadata(ledger, state)
            self._stage_legacy_economy_idempotency(ledger, state)
            self._apply_pending_economy_migration_grants(ledger, state)
            committed = ledger.commit_state(
                self._bounded_state_payload(state),
                schema_version=STATE_VERSION,
                expected_revision=0,
            )
            ledger.integrity_check()
            # The temporary writer uses WAL. Install a verified online backup
            # so the atomic replacement never depends on SQLite sidecars.
            ledger.backup_to(portable)
            ledger.close()
            ledger = None
            temporary.unlink(missing_ok=True)
            Path(str(temporary) + "-wal").unlink(missing_ok=True)
            Path(str(temporary) + "-shm").unlink(missing_ok=True)
            if self.data_path.exists():
                legacy_backup = self.data_path.with_suffix(
                    f".pre-sqlite-{time.time_ns()}.json"
                )
                _required_backup(self.data_path, legacy_backup)
            os.replace(portable, self.database_path)
            self._reward_ledger = RewardLedger(self.database_path)
            self._ledger_revision = committed.revision
            self._clear_unbounded_state_authorities(state)
            self._refresh_reanswer_hint_cache(state)
            self._refresh_recent_find_cache(state)
        except Exception:
            if ledger is not None:
                ledger.close()
            temporary.unlink(missing_ok=True)
            Path(str(temporary) + "-wal").unlink(missing_ok=True)
            Path(str(temporary) + "-shm").unlink(missing_ok=True)
            portable.unlink(missing_ok=True)
            raise

    def _stage_legacy_authorities(
        self,
        ledger: RewardLedger,
        state: GardenState,
    ) -> None:
        """One-way import of exact schema-21 replay authorities."""

        from .garden_finds import consumption_id, stable_answer_event_identity

        for event_key in dict.fromkeys(state.applied_reward_event_keys):
            ledger.stage_reward_event(RewardEventRecord(str(event_key)))

        parsed_lineages: dict[str, tuple[str, int, int]] = {}
        for lineage in [
            *state.answer_lineage_bindings.values(),
            *state.pending_reanswer_lineages.keys(),
        ]:
            parsed = _parse_answer_lineage_key(lineage)
            if parsed is not None:
                parsed_lineages[str(lineage)] = parsed
        for lineage, (scheduler_day, card_id, serial) in parsed_lineages.items():
            ledger.stage_answer_lineage(AnswerLineageRecord(
                lineage, scheduler_day, card_id, serial
            ))
        for raw_revlog_id, lineage in state.answer_lineage_bindings.items():
            if lineage in parsed_lineages:
                ledger.stage_revlog_alias(RevlogAliasRecord(
                    int(raw_revlog_id), lineage
                ))

        outcomes_by_answer: dict[str, list[Any]] = {}
        for outcome in state.garden_find_outcomes.values():
            outcomes_by_answer.setdefault(str(outcome.answer_key), []).append(outcome)
        processed_keys = set(state.processed_answer_keys)
        processed_keys.update(outcomes_by_answer)
        lineage_for_consumption: dict[str, tuple[str, int]] = {}
        if processed_keys:
            for lineage in parsed_lineages:
                answer_key = consumption_id(stable_answer_event_identity(
                    1, lineage_id=lineage
                ))
                if answer_key in processed_keys:
                    aliases = [
                        int(raw_revlog_id)
                        for raw_revlog_id, bound in state.answer_lineage_bindings.items()
                        if bound == lineage
                    ]
                    lineage_for_consumption[answer_key] = (
                        lineage,
                        min(aliases, default=0),
                    )
        for answer_key in sorted(processed_keys):
            outcomes = outcomes_by_answer.get(answer_key, [])
            first = min(
                outcomes,
                key=lambda outcome: (outcome.occurred_at, outcome.pool_id),
                default=None,
            )
            lineage, first_revlog_id = lineage_for_consumption.get(
                answer_key, ("", 0)
            )
            ledger.stage_answer_consumption(AnswerConsumptionRecord(
                answer_key=answer_key,
                scheduler_day=(str(first.scheduler_day) if first else ""),
                occurred_at=(str(first.occurred_at) if first else ""),
                lineage_key=lineage,
                first_revlog_id=first_revlog_id,
            ))
        for lineage, minimum_revlog_id in state.pending_reanswer_lineages.items():
            if ledger.lineage_record(lineage) is not None:
                ledger.stage_reanswer_hint(lineage, int(minimum_revlog_id))
        for answer_key, outcomes in outcomes_by_answer.items():
            for outcome in outcomes:
                ledger.stage_find_outcome(FindOutcomeRecord(
                    answer_key=answer_key,
                    scheduler_day=str(outcome.scheduler_day),
                    pool_id=str(outcome.pool_id),
                    pool_version=str(outcome.pool_version),
                    status=str(outcome.status),
                    occurred_at=str(outcome.occurred_at),
                    reward_id=str(outcome.reward_id),
                    hit_payload=(
                        dict(outcome.__dict__)
                        if str(outcome.status) == "hit"
                        else None
                    ),
                ))
        for scheduler_day, fingerprint in state.finalized_day_fingerprints.items():
            ledger.stage_finalized_day(FinalizedDayRecord(
                str(scheduler_day), str(fingerprint)
            ))

    @staticmethod
    def _stage_legacy_economy_idempotency(
        ledger: RewardLedger,
        state: GardenState,
    ) -> None:
        """Promote bounded v25 request receipts into permanent ledger identities."""

        records = (
            (
                "purchase",
                request.request_id,
                request.request_fingerprint,
                request.outcome.to_dict(),
                request.occurred_at,
            )
            for request in state.completed_purchase_requests
        )
        growth_records = (
            (
                "growth_charge",
                request.request_id,
                request.request_fingerprint,
                request.outcome.to_dict(),
                request.occurred_at,
            )
            for request in state.completed_growth_charge_requests
        )
        for kind, request_id, fingerprint, outcome, occurred_at in (
            *records,
            *growth_records,
        ):
            ledger.stage_idempotency_record(IdempotencyRecord(
                operation_kind=kind,
                operation_id=request_id,
                request_fingerprint=fingerprint,
                outcome=outcome,
                occurred_at=occurred_at,
            ))

    @staticmethod
    def _domain_find_outcome(record: FindOutcomeRecord) -> GardenFindOutcome:
        payload = dict(record.hit_payload or {})
        return GardenFindOutcome(
            answer_key=record.answer_key,
            scheduler_day=record.scheduler_day,
            status=record.status,
            pool_id=record.pool_id,
            pool_version=record.pool_version,
            occurred_at=record.occurred_at,
            reward_id=record.reward_id,
            reward_type=str(payload.get("reward_type", "")),
            amount=max(0, int(payload.get("amount", 0) or 0)),
            item_id=str(payload.get("item_id", "")),
            display_name=str(payload.get("display_name", "")),
            description=str(payload.get("description", "")),
            tier=str(payload.get("tier", "")),
            artwork_ref=str(payload.get("artwork_ref", "")),
            localization_key=str(payload.get("localization_key", "")),
        )

    def _refresh_recent_find_cache(self, state: GardenState | None = None) -> None:
        target = state if state is not None else getattr(self, "state", None)
        ledger = self._reward_ledger
        if target is None or ledger is None:
            return
        outcomes = [
            self._domain_find_outcome(record)
            for record in reversed(ledger.recent_hit_outcomes(
                limit=RECENT_FIND_CACHE_LIMIT
            ))
        ]
        target.garden_find_outcomes = {
            f"{outcome.pool_id}:{outcome.answer_key}": outcome
            for outcome in outcomes
        }

    def _refresh_reanswer_hint_cache(self, state: GardenState | None = None) -> None:
        target = state if state is not None else getattr(self, "state", None)
        ledger = self._reward_ledger
        if target is None or ledger is None:
            return
        target.pending_reanswer_lineages = ledger.reanswer_hints()

    def reward_ledger_checkpoint(self) -> LedgerCheckpoint | None:
        return self._reward_ledger.checkpoint() if self._reward_ledger else None

    def rollback_reward_ledger(self, checkpoint: LedgerCheckpoint | None) -> None:
        if self._reward_ledger is not None and checkpoint is not None:
            self._reward_ledger.rollback(checkpoint)

    def reward_ledger_has_staged_writes(self) -> bool:
        return bool(self._reward_ledger and self._reward_ledger.has_staged_writes)

    def reward_applied(self, event_key: str) -> bool:
        if self._reward_ledger is None:
            return str(event_key) in self.state.applied_reward_event_keys
        return self._reward_ledger.reward_applied(str(event_key))

    def stage_reward_event(
        self,
        event_key: str,
        *,
        source: str = "",
        scheduler_day: str = "",
        occurred_at: str = "",
    ) -> None:
        if self._reward_ledger is None:
            if event_key not in self.state.applied_reward_event_keys:
                self.state.applied_reward_event_keys.append(event_key)
            return
        if not self._reward_ledger.reward_applied(event_key):
            self._reward_ledger.stage_reward_event(RewardEventRecord(
                event_key,
                source,
                scheduler_day,
                occurred_at,
            ))

    def idempotency_record(
        self,
        operation_kind: str,
        operation_id: str,
    ) -> IdempotencyRecord | None:
        if self._reward_ledger is None:
            return None
        return self._reward_ledger.idempotency_record(
            operation_kind, operation_id
        )

    def stage_idempotency_record(self, record: IdempotencyRecord) -> None:
        if self._reward_ledger is None:
            return
        self._reward_ledger.stage_idempotency_record(record)

    def economy_event(self, event_key: str) -> EconomyEventRecord | None:
        if self._reward_ledger is None:
            return None
        return self._reward_ledger.economy_event(event_key)

    def first_item_acquisition_at(self, item_id: str) -> str | None:
        if self._reward_ledger is None:
            return None
        return self._reward_ledger.first_item_acquisition_at(item_id)

    def stage_economy_event(self, record: EconomyEventRecord) -> None:
        if self._reward_ledger is None:
            return
        self._reward_ledger.stage_economy_event(record)

    def _schema27_migration_outcome(self) -> Mapping[str, Any] | None:
        if self._reward_ledger is None:
            return None
        record = self._reward_ledger.idempotency_record(
            "migration", SCHEMA27_ECONOMY_AUTHORITY_OPERATION_ID
        )
        return dict(record.outcome) if record is not None else None

    def _reconcile_schema27_endgame_state(self) -> Mapping[str, Any] | None:
        """Verify cumulative project state against exact permanent events."""

        ledger = self._reward_ledger
        if ledger is None:
            return None
        migration = self._schema27_migration_outcome()
        if migration is None:
            landmark_funding = 0
            landmark_claimed = 0
            mastery_funding = {
                species_id: 0 for species_id in CURRENT_CATALOG_SPECIES_ORDER
            }
            mastery_claimed = {}
            legacy_total = 0
        else:
            if migration.get("endgame_reconciliation_version") != (
                SCHEMA27_ENDGAME_RECONCILIATION_VERSION
            ):
                raise RewardLedgerCorruptionError(
                    "The schema-27 endgame migration baseline is incomplete."
                )

            def baseline_int(
                key: str,
                *,
                maximum: int | None = None,
            ) -> int:
                value = migration.get(key)
                if (
                    isinstance(value, bool)
                    or not isinstance(value, int)
                    or value < 0
                    or (maximum is not None and value > maximum)
                ):
                    raise RewardLedgerCorruptionError(
                        "The schema-27 endgame migration baseline is invalid: "
                        + key
                    )
                return int(value)

            landmark_funding = baseline_int(
                "landmark_grandfathered_funding_units",
                maximum=LANDMARK_MAX_GROWTH_UNITS,
            )
            landmark_claimed = baseline_int(
                "landmark_highest_claimed_tier_baseline",
                maximum=len(GARDEN_PROJECT_IDS),
            )
            raw_mastery_funding = migration.get(
                "mastery_grandfathered_funding_units_by_species"
            )
            raw_mastery_claimed = migration.get(
                "mastery_highest_claimed_rank_baseline_by_species"
            )
            if not isinstance(raw_mastery_funding, Mapping) or not isinstance(
                raw_mastery_claimed, Mapping
            ):
                raise RewardLedgerCorruptionError(
                    "The schema-27 Mastery migration baseline is invalid."
                )
            if set(raw_mastery_funding).difference(
                CURRENT_CATALOG_SPECIES_ORDER
            ) or set(raw_mastery_claimed).difference(
                CURRENT_CATALOG_SPECIES_ORDER
            ):
                raise RewardLedgerCorruptionError(
                    "The schema-27 Mastery migration baseline has an unknown species."
                )
            mastery_funding = {
                species_id: 0 for species_id in CURRENT_CATALOG_SPECIES_ORDER
            }
            for species_id, value in raw_mastery_funding.items():
                if (
                    isinstance(value, bool)
                    or not isinstance(value, int)
                    or value < 0
                    or value > MASTERY_MAX_GROWTH_UNITS_PER_SPECIES
                ):
                    raise RewardLedgerCorruptionError(
                        "The schema-27 Mastery funding baseline is invalid."
                    )
                mastery_funding[str(species_id)] = int(value)
            mastery_claimed = {}
            for species_id, rank_id in raw_mastery_claimed.items():
                if rank_id not in CULTIVATION_MASTERY_RANKS:
                    raise RewardLedgerCorruptionError(
                        "The schema-27 Mastery claim baseline is invalid."
                    )
                mastery_claimed[str(species_id)] = str(rank_id)
            legacy_total = baseline_int(
                "garden_legacy_total_units_baseline"
            )

        landmark_claimed_floor = (
            GARDEN_PROJECT_CUMULATIVE_GROWTH_THRESHOLDS_UNITS[
                GARDEN_PROJECT_IDS[landmark_claimed - 1]
            ]
            if landmark_claimed else 0
        )
        if landmark_funding < landmark_claimed_floor:
            raise RewardLedgerCorruptionError(
                "Grandfathered Landmark claims exceed their funded Growth."
            )
        for species_id, rank_id in mastery_claimed.items():
            threshold = (
                CULTIVATION_MASTERY_CUMULATIVE_GROWTH_THRESHOLDS_UNITS[
                    rank_id
                ]
            )
            if mastery_funding[species_id] < threshold:
                raise RewardLedgerCorruptionError(
                    "Grandfathered Mastery claims exceed their funded Growth."
                )
        landmark_funding_baseline = landmark_funding
        mastery_funding_baseline = dict(mastery_funding)

        initial = {
            "landmark_funding": landmark_funding,
            "landmark_claimed": landmark_claimed,
            "mastery_funding": mastery_funding,
            "mastery_claimed": mastery_claimed,
            "legacy_total": legacy_total,
        }

        def accumulate(projection: dict[str, Any], event: EconomyEventRecord) -> None:
            landmark_funding = projection["landmark_funding"]
            landmark_claimed = projection["landmark_claimed"]
            mastery_funding = projection["mastery_funding"]
            mastery_claimed = projection["mastery_claimed"]
            legacy_total = projection["legacy_total"]

            def claim_landmark(event: EconomyEventRecord, claim_id: str) -> None:
                nonlocal landmark_claimed
                expected = (
                    GARDEN_PROJECT_IDS[landmark_claimed]
                    if landmark_claimed < len(GARDEN_PROJECT_IDS) else ""
                )
                if (
                    not expected
                    or claim_id != expected
                    or event.item_id != expected
                    or event.quantity != 1
                    or event.coins_spent != LANDMARK_COIN_COST_BY_ID[expected]
                    or landmark_funding
                    < GARDEN_PROJECT_CUMULATIVE_GROWTH_THRESHOLDS_UNITS[expected]
                ):
                    raise RewardLedgerCorruptionError(
                        "A Landmark claim is out of order, unfunded, or unpaid: "
                        + event.event_key
                    )
                landmark_claimed += 1

            def claim_mastery(
                event: EconomyEventRecord,
                species_id: str,
                rank_id: str,
            ) -> None:
                if species_id not in CURRENT_CATALOG_SPECIES_ORDER:
                    raise RewardLedgerCorruptionError(
                        "A Mastery claim targets an unknown species: "
                        + event.event_key
                    )
                previous = mastery_claimed.get(species_id, "")
                previous_index = (
                    CULTIVATION_MASTERY_RANKS.index(previous)
                    if previous else -1
                )
                expected_index = previous_index + 1
                expected = (
                    CULTIVATION_MASTERY_RANKS[expected_index]
                    if expected_index < len(CULTIVATION_MASTERY_RANKS) else ""
                )
                if (
                    not expected
                    or rank_id != expected
                    or event.item_id != expected
                    or event.quantity != 1
                    or event.coins_spent != MASTERY_COIN_COST_BY_ID[expected]
                    or mastery_funding[species_id]
                    < CULTIVATION_MASTERY_CUMULATIVE_GROWTH_THRESHOLDS_UNITS[
                        expected
                    ]
                ):
                    raise RewardLedgerCorruptionError(
                        "A Mastery claim is out of order, unfunded, or unpaid: "
                        + event.event_key
                    )
                mastery_claimed[species_id] = expected

            if event.growth_flow_kind == "legacy_unreconciled":
                return
            allocations = dict(
                (event.metric_deltas or {}).get("project_allocations", {})
            )
            for target_key, units in allocations.items():
                target_type, _, target_id = str(target_key).partition(":")
                amount = int(units)
                if target_type == "landmark" and target_id == "garden_landmark":
                    landmark_funding += amount
                    if landmark_funding > LANDMARK_MAX_GROWTH_UNITS:
                        raise RewardLedgerCorruptionError(
                            "Landmark Growth exceeds its maximum."
                        )
                elif target_type == "mastery" and target_id in mastery_funding:
                    mastery_funding[target_id] += amount
                    if mastery_funding[target_id] > (
                        MASTERY_MAX_GROWTH_UNITS_PER_SPECIES
                    ):
                        raise RewardLedgerCorruptionError(
                            "Mastery Growth exceeds its species maximum."
                        )
                elif target_type == "legacy" and target_id == "garden_legacy":
                    if (
                        landmark_funding < LANDMARK_MAX_GROWTH_UNITS
                        or any(
                            mastery_funding[species_id]
                            < MASTERY_MAX_GROWTH_UNITS_PER_SPECIES
                            for species_id in CURRENT_CATALOG_SPECIES_ORDER
                        )
                    ):
                        raise RewardLedgerCorruptionError(
                            "Garden Legacy received Growth before finite funding."
                        )
                    legacy_total += amount
                else:
                    raise RewardLedgerCorruptionError(
                        "A project allocation targets unknown content: "
                        + event.event_key
                    )

            if event.event_kind == "growth_project_claim":
                if event.growth_flow_kind != "claim":
                    raise RewardLedgerCorruptionError(
                        "A Growth project claim has an invalid Growth flow."
                    )
                if event.sink_id == "garden_landmark":
                    claim_landmark(event, event.item_id)
                elif event.sink_id in mastery_funding:
                    claim_mastery(event, event.sink_id, event.item_id)
                else:
                    raise RewardLedgerCorruptionError(
                        "A Growth project claim has no valid target: "
                        + event.event_key
                    )
            elif event.event_kind == "landmark_complete":
                if (
                    event.growth_flow_kind != "claim"
                    or event.sink_id != event.item_id
                ):
                    raise RewardLedgerCorruptionError(
                        "A Landmark claim target differs from its claim ID."
                    )
                claim_landmark(event, event.item_id)
            elif event.event_kind == "mastery_purchase":
                species_id, separator, rank_id = event.sink_id.partition(":")
                if (
                    event.growth_flow_kind not in {
                        "claim", "manual_contribution"
                    }
                    or not separator
                    or rank_id != event.item_id
                ):
                    raise RewardLedgerCorruptionError(
                        "A Mastery claim target differs from its claim ID."
                    )
                claim_mastery(event, species_id, rank_id)
            elif event.growth_flow_kind == "claim":
                raise RewardLedgerCorruptionError(
                    "An unknown project claim was committed: " + event.event_key
                )

            projection.update(
                landmark_funding=landmark_funding,
                landmark_claimed=landmark_claimed,
                legacy_total=legacy_total,
            )

        projection = ledger.project_economy("endgame-v1", initial, accumulate)
        landmark_funding = projection["landmark_funding"]
        landmark_claimed = projection["landmark_claimed"]
        mastery_funding = projection["mastery_funding"]
        mastery_claimed = projection["mastery_claimed"]
        legacy_total = projection["legacy_total"]

        actual_landmark_funding = max(
            0, int(self.state.garden_project.landmark_growth_units_funded)
        )
        actual_landmark_claimed = max(
            0, int(self.state.garden_project.landmark_highest_claimed_tier)
        )
        actual_mastery_funding = {
            species_id: max(
                0,
                int(
                    self.state.cultivation_mastery
                    .growth_units_funded_by_species.get(species_id, 0)
                ),
            )
            for species_id in CURRENT_CATALOG_SPECIES_ORDER
        }
        actual_mastery_claimed = dict(
            self.state.cultivation_mastery.highest_claimed_rank_by_species
        )
        actual_legacy_total = (
            max(0, int(self.state.garden_legacy_level))
            * GARDEN_LEGACY_LEVEL_COST_UNITS
            + max(0, int(self.state.garden_legacy_progress_units))
        )
        if (
            actual_landmark_funding != landmark_funding
            or actual_landmark_claimed != landmark_claimed
            or actual_mastery_funding != mastery_funding
            or actual_mastery_claimed != mastery_claimed
            or actual_legacy_total != legacy_total
        ):
            raise RewardLedgerCorruptionError(
                "Endgame funding or claims do not reconcile with the exact ledger."
            )
        if self.state.garden_project.grandfathered_funding_units != (
            landmark_funding_baseline
        ):
            raise RewardLedgerCorruptionError(
                "The Landmark migration funding baseline changed."
            )
        expected_mastery_grandfathered = {
            species_id: amount
            for species_id, amount in mastery_funding_baseline.items()
            if amount
        }
        if (
            self.state.cultivation_mastery
            .grandfathered_funding_units_by_species
            != expected_mastery_grandfathered
        ):
            raise RewardLedgerCorruptionError(
                "The Mastery migration funding baseline changed."
            )
        return migration

    def lifetime_economy_aggregates(self) -> Mapping[str, Any]:
        if self._reward_ledger is None:
            return self.state.lifetime_economy_aggregates.to_dict()
        return self._reward_ledger.lifetime_economy_aggregates()

    def refresh_lifetime_economy_aggregates(
        self,
    ) -> LifetimeEconomyAggregates:
        """Rebuild and persist the state projection from permanent events."""

        values = self.lifetime_economy_aggregates()
        if self._reward_ledger is not None:
            migration = self._reconcile_schema27_endgame_state()
            if migration is not None:
                history_complete = migration.get(
                    "lifetime_growth_history_complete"
                )
                if not isinstance(history_complete, bool):
                    raise RewardLedgerCorruptionError(
                        "The lifetime Growth migration provenance is invalid."
                    )
                if not history_complete:
                    values = {
                        **dict(values),
                        "history_complete": False,
                        "authoritative_from_event_identity": str(
                            migration.get("lifetime_growth_history_authority")
                            or SCHEMA27_ECONOMY_AUTHORITY_OPERATION_ID
                        ),
                    }
            expected_stored = (
                max(
                    0,
                    int(self.state.stored_growth_opening_balance_units),
                )
                + self._reward_ledger.stored_growth_balance_net_delta_units()
            )
            actual_stored = max(
                0, int(self.state.stored_growth_balance_units)
            )
            if expected_stored != actual_stored:
                raise RewardLedgerCorruptionError(
                    "Stored Growth balance does not reconcile with exact "
                    f"ledger deltas ({actual_stored} != {expected_stored})"
                )
        aggregate = LifetimeEconomyAggregates(
            coins_earned_by_source=dict(
                values.get("coins_earned_by_source", {})
            ),
            coins_spent_by_sink=dict(values.get("coins_spent_by_sink", {})),
            growth_earned_by_source=dict(
                values.get("growth_earned_by_source", {})
            ),
            growth_spent_on_landmarks=int(
                values.get("growth_spent_on_landmarks", 0)
            ),
            growth_spent_on_mastery=int(
                values.get("growth_spent_on_mastery", 0)
            ),
            growth_generated_units=int(
                values.get("growth_generated_units", 0)
            ),
            growth_applied_to_plants_units=int(
                values.get("growth_applied_to_plants_units", 0)
            ),
            growth_routed_to_storage_units_lifetime=int(
                values.get("growth_routed_to_storage_units_lifetime", 0)
            ),
            growth_contributed_to_landmarks_units=int(
                values.get("growth_contributed_to_landmarks_units", 0)
            ),
            growth_contributed_to_mastery_units=int(
                values.get("growth_contributed_to_mastery_units", 0)
            ),
            growth_contributed_to_legacy_units=int(
                values.get("growth_contributed_to_legacy_units", 0)
            ),
            growth_unallocated_overflow_units=int(
                values.get("growth_unallocated_overflow_units", 0)
            ),
            history_complete=bool(values.get("history_complete", False)),
            authoritative_from_event_identity=str(
                values.get("authoritative_from_event_identity", "")
            ),
            finds_by_outcome=dict(values.get("finds_by_outcome", {})),
            environment_discoveries=dict(
                values.get("environment_discoveries", {})
            ),
            consumables_earned=dict(values.get("consumables_earned", {})),
            consumables_used=dict(values.get("consumables_used", {})),
            plants_completed=int(values.get("plants_completed", 0)),
            today_cards_completions=int(
                values.get("today_cards_completions", 0)
            ),
        )
        self.state.lifetime_economy_aggregates = aggregate
        return aggregate

    def rebuild_lifetime_economy_aggregates(
        self,
    ) -> LifetimeEconomyAggregates:
        """Compatibility alias for callers that describe refresh as rebuild."""

        return self.refresh_lifetime_economy_aggregates()

    def daily_economy_snapshot(
        self,
        anki_day: str,
    ) -> DailyEconomySnapshot | None:
        if self._reward_ledger is None:
            snapshot = self.state.daily_economy_snapshot
            return (
                snapshot
                if snapshot is not None and snapshot.anki_day == anki_day
                else None
            )
        record = self._reward_ledger.daily_economy_snapshot(anki_day)
        if record is None:
            return None
        return DailyEconomySnapshot(
            anki_day=record.anki_day,
            active_garden_bonus_id=record.active_garden_bonus_id,
            active_scenery_effect_id=record.active_scenery_effect_id,
            snapshot_source=record.snapshot_source,
            snapshot_id=record.snapshot_id,
        )

    def stage_daily_economy_snapshot(
        self,
        snapshot: DailyEconomySnapshot | DailyEconomySnapshotRecord | None = None,
        *,
        anki_day: str = "",
        active_garden_bonus_id: str = "",
        active_scenery_effect_id: str = "",
        snapshot_source: str = "",
        snapshot_id: str = "",
    ) -> DailyEconomySnapshot:
        if snapshot is None:
            value = DailyEconomySnapshot(
                anki_day=anki_day,
                active_garden_bonus_id=active_garden_bonus_id,
                active_scenery_effect_id=active_scenery_effect_id,
                snapshot_source=snapshot_source,
                snapshot_id=snapshot_id,
            )
        else:
            value = DailyEconomySnapshot(
                anki_day=snapshot.anki_day,
                active_garden_bonus_id=snapshot.active_garden_bonus_id,
                active_scenery_effect_id=snapshot.active_scenery_effect_id,
                snapshot_source=snapshot.snapshot_source,
                snapshot_id=snapshot.snapshot_id,
            )
        existing = self.daily_economy_snapshot(value.anki_day)
        if existing is not None:
            if existing != value:
                raise ValueError(
                    "That Anki day already has a different economy snapshot."
                )
            return existing
        if self._reward_ledger is not None:
            self._reward_ledger.stage_daily_economy_snapshot(
                DailyEconomySnapshotRecord(
                    anki_day=value.anki_day,
                    active_garden_bonus_id=value.active_garden_bonus_id,
                    active_scenery_effect_id=value.active_scenery_effect_id,
                    snapshot_source=value.snapshot_source,
                    snapshot_id=value.snapshot_id,
                )
            )
        self.state.daily_economy_snapshot = value
        return value

    def eligible_study_days_before(
        self,
        anki_day: str,
        *,
        limit: int = 7,
    ) -> tuple[str, ...]:
        if self._reward_ledger is not None:
            return self._reward_ledger.eligible_study_days_before(
                anki_day, limit=limit
            )
        candidates: set[str] = set()
        snapshot = self.state.daily_economy_snapshot
        if snapshot is not None and snapshot.anki_day < anki_day:
            candidates.add(snapshot.anki_day)
        if self.state.daily_stats.reviewed > 0 and self.state.daily_stats.day < anki_day:
            candidates.add(self.state.daily_stats.day)
        return tuple(sorted(candidates, reverse=True)[:max(0, int(limit))])

    def verified_today_cards_completion_days_before(
        self,
        anki_day: str,
    ) -> frozenset[str]:
        if self._reward_ledger is not None:
            return self._reward_ledger.verified_today_cards_completion_days_before(
                anki_day
            )
        result: set[str] = set()
        if (
            self.state.daily_completion.status == "complete"
            and self.state.daily_completion.reward_claimed
            and self.state.daily_completion.scheduler_day < anki_day
        ):
            result.add(self.state.daily_completion.scheduler_day)
        for transaction in self.state.currency_transactions:
            if transaction.event_key.startswith("all_due:"):
                candidate = transaction.event_key.partition(":")[2]
                try:
                    parsed = date.fromisoformat(candidate).isoformat()
                except ValueError:
                    continue
                if parsed < anki_day:
                    result.add(parsed)
        return frozenset(result)

    def answer_consumed(self, answer_key: str) -> bool:
        if self._reward_ledger is None:
            return str(answer_key) in self.state.processed_answer_keys
        return self._reward_ledger.answer_consumed(str(answer_key))

    def consumed_answer_keys(self, answer_keys: Any) -> set[str]:
        values = {str(value) for value in answer_keys if str(value)}
        if self._reward_ledger is None:
            return values.intersection(self.state.processed_answer_keys)
        return self._reward_ledger.consumed_answer_keys(values)

    def stage_answer_consumption(
        self,
        answer_key: str,
        *,
        scheduler_day: str,
        lineage_key: str = "",
        first_revlog_id: int = 0,
    ) -> None:
        if self._reward_ledger is None:
            if answer_key not in self.state.processed_answer_keys:
                self.state.processed_answer_keys.append(answer_key)
            return
        if self._reward_ledger.answer_consumed(answer_key):
            return
        self._reward_ledger.stage_answer_consumption(AnswerConsumptionRecord(
            answer_key=answer_key,
            scheduler_day=scheduler_day,
            lineage_key=lineage_key,
            first_revlog_id=max(0, int(first_revlog_id)),
        ))

    def answer_lineage_bindings_for_cards(self, card_ids: Any) -> dict[str, str]:
        if self._reward_ledger is None:
            state = getattr(self, "state", None)
            return dict(
                getattr(state, "answer_lineage_bindings", {}) or {}
            )
        return {
            str(revlog_id): lineage
            for revlog_id, lineage in self._reward_ledger.bindings_for_cards(
                card_ids
            ).items()
        }

    def present_answer_lineages(self, bindings: Mapping[str, str]) -> set[str]:
        """Check alias presence beyond the review hook's current-day window.

        Exact-ID lookups retain existing historical answers without loading
        their contents or mistaking them for deleted Undo/reanswer candidates.
        Use Anki's authority so this also works without the disposable index.
        """
        aliases = {int(key): lineage for key, lineage in bindings.items()}
        if not aliases:
            return set()
        collection = getattr(self.mw, "col", None)
        if collection is None or getattr(collection, "db", None) is None:
            raise RevlogReadError("Anki review history is not available yet.")
        present: set[str] = set()
        revlog_ids = list(aliases)
        for offset in range(0, len(revlog_ids), 900):
            chunk = revlog_ids[offset:offset + 900]
            placeholders = ",".join("?" for _ in chunk)
            rows = collection.db.all(
                "SELECT id FROM revlog WHERE id IN (" + placeholders + ") "
                "AND type IN (0, 1, 2, 3)",
                *chunk,
            )
            present.update(aliases[int(row[0])] for row in rows)
        return present

    def all_answer_lineage_bindings(self) -> dict[str, str]:
        if self._reward_ledger is None:
            return dict(self.state.answer_lineage_bindings)
        return {
            str(revlog_id): lineage
            for revlog_id, lineage in self._reward_ledger.all_revlog_bindings().items()
        }

    def pending_reanswer_lineages(self) -> dict[str, int]:
        if self._reward_ledger is None:
            state = getattr(self, "state", None)
            return dict(
                getattr(state, "pending_reanswer_lineages", {}) or {}
            )
        return self._reward_ledger.reanswer_hints()

    def reanswer_floor_for_lineage(self, lineage: str) -> int | None:
        if self._reward_ledger is None:
            return self.state.pending_reanswer_lineages.get(str(lineage))
        floor = self._reward_ledger.reanswer_floor_for_lineage(str(lineage))
        return floor if floor and floor > 0 else None

    def stage_reanswer_hint(self, lineage: str, minimum_revlog_id: int) -> None:
        key = str(lineage)
        floor = max(1, int(minimum_revlog_id))
        if self._reward_ledger is not None:
            self._reward_ledger.stage_reanswer_hint(key, floor)
        self.state.pending_reanswer_lineages[key] = floor

    def clear_reanswer_hint(self, lineage: str) -> None:
        key = str(lineage)
        if self._reward_ledger is not None:
            self._reward_ledger.stage_clear_reanswer_hint(key)
        self.state.pending_reanswer_lineages.pop(key, None)

    def stage_answer_lineage_alias(self, revlog_id: int, lineage: str) -> None:
        if self._reward_ledger is None:
            state = getattr(self, "state", None)
            if state is None:
                return
            existing = state.answer_lineage_bindings.get(str(revlog_id))
            if existing not in (None, lineage):
                raise ValueError("That revlog identity has a conflicting lineage.")
            state.answer_lineage_bindings[str(revlog_id)] = lineage
            return
        existing = self._reward_ledger.binding_for_revlog(int(revlog_id))
        if existing is not None:
            if existing != lineage:
                raise ValueError("That revlog identity has a conflicting lineage.")
            return
        parsed = _parse_answer_lineage_key(lineage)
        if parsed is None:
            raise ValueError("The answer lineage is malformed.")
        if self._reward_ledger.lineage_record(lineage) is None:
            scheduler_day, card_id, serial = parsed
            self._reward_ledger.stage_answer_lineage(AnswerLineageRecord(
                lineage, scheduler_day, card_id, serial
            ))
        self._reward_ledger.stage_revlog_alias(RevlogAliasRecord(
            int(revlog_id), lineage
        ))

    def garden_find_outcome(
        self,
        answer_key: str,
        pool_id: str,
    ) -> GardenFindOutcome | None:
        if self._reward_ledger is None:
            return self.state.garden_find_outcomes.get(f"{pool_id}:{answer_key}")
        record = self._reward_ledger.find_outcome(answer_key, pool_id)
        return self._domain_find_outcome(record) if record is not None else None

    def stage_garden_find_outcome(self, outcome: GardenFindOutcome) -> None:
        if self._reward_ledger is None:
            outcome_key = f"{outcome.pool_id}:{outcome.answer_key}"
            if outcome_key in self.state.garden_find_outcomes:
                return
            self.state.garden_find_outcomes[outcome_key] = outcome
            if outcome.pool_id == "standard" and outcome.status == "hit":
                finds_today = max(0, int(
                    self.state.garden_find_daily_counts.get(
                        outcome.scheduler_day, 0
                    )
                ))
                self.state.garden_find_daily_counts[outcome.scheduler_day] = finds_today + 1
                reward_counts = (
                    self.state.garden_find_reward_daily_counts.setdefault(
                        outcome.scheduler_day, {}
                    )
                )
                reward_counts[outcome.reward_id] = max(0, int(reward_counts.get(outcome.reward_id, 0))) + 1
            return
        if self._reward_ledger.find_outcome(
            outcome.answer_key, outcome.pool_id
        ) is not None:
            return
        self._reward_ledger.stage_find_outcome(FindOutcomeRecord(
            answer_key=outcome.answer_key,
            scheduler_day=outcome.scheduler_day,
            pool_id=outcome.pool_id,
            pool_version=outcome.pool_version,
            status=outcome.status,
            occurred_at=outcome.occurred_at,
            reward_id=outcome.reward_id,
            hit_payload=(
                dict(outcome.__dict__) if outcome.status == "hit" else None
            ),
        ))

    def garden_find_counts(
        self,
        scheduler_day: str,
        *,
        pool_id: str = "standard",
    ) -> tuple[int, dict[str, int]]:
        if self._reward_ledger is None:
            return (
                max(0, int(self.state.garden_find_daily_counts.get(
                    scheduler_day, 0
                ))),
                dict(self.state.garden_find_reward_daily_counts.get(
                    scheduler_day, {}
                )),
            )
        counts = self._reward_ledger.find_counts(
            scheduler_day, pool_id=pool_id
        )
        return counts.total_hits, dict(counts.reward_counts)

    def recent_garden_find_outcomes(
        self,
        *,
        limit: int = 8,
    ) -> tuple[GardenFindOutcome, ...]:
        if self._reward_ledger is None:
            values = [
                outcome for outcome in self.state.garden_find_outcomes.values()
                if outcome.status == "hit"
            ]
            return tuple(values[-max(0, int(limit)):])
        return tuple(
            self._domain_find_outcome(record)
            for record in self._reward_ledger.recent_hit_outcomes(limit=limit)
        )

    def finalized_day_fingerprint(self, scheduler_day: str) -> str | None:
        if self._reward_ledger is None:
            return self.state.finalized_day_fingerprints.get(scheduler_day)
        return self._reward_ledger.finalized_day_fingerprint(scheduler_day)

    def stage_finalized_day(self, scheduler_day: str, fingerprint: str) -> None:
        if self._reward_ledger is None:
            self.state.finalized_day_fingerprints[scheduler_day] = fingerprint
            return
        existing = self._reward_ledger.finalized_day_fingerprint(scheduler_day)
        if existing == fingerprint:
            return
        self._reward_ledger.stage_finalized_day(
            FinalizedDayRecord(scheduler_day, fingerprint),
            replace=existing is not None,
        )

    def _load(self) -> GardenState:
        try:
            if self.data_path.exists():
                raw = json.loads(self.data_path.read_text("utf-8"))
                version = int(raw.get("version", -1)) if isinstance(raw, dict) else -1
                if version == PREVIOUS_STATE_VERSION or version in MODERN_PREVIOUS_STATE_VERSIONS:
                    backup = self.data_path.with_suffix(f".schema-{version}.legacy.json")
                    _required_backup(self.data_path, backup)
                    logger.info(
                        "Anki Garden: migrating schema %s from backup %s to schema %s",
                        version, backup, STATE_VERSION,
                    )
                    return (
                        migrate_previous_state(raw)
                        if version == PREVIOUS_STATE_VERSION
                        else migrate_modern_state(
                            raw,
                            onboarding_version=(
                                self.config.value("onboarding_version", 0)
                                if hasattr(getattr(self, "config", None), "value")
                                else 0
                            ),
                        )
                    )
                if version != STATE_VERSION:
                    backup = self.data_path.with_suffix(f".schema-{version}.legacy.json")
                    _required_backup(self.data_path, backup)
                    raise StatePreservationError(
                        f"Garden schema {version} is unsupported. The original was preserved at {backup}."
                    )
                payload = deepcopy(raw)
                return _materialize_unlocked_species(GardenState.from_dict(payload))
        except StatePreservationError:
            raise
        except Exception as load_error:
            logger.exception("Anki Garden: saved state is unreadable; preserving it and stopping")
            try:
                backup = self.data_path.with_suffix(".invalid.json")
                _required_backup(self.data_path, backup)
            except Exception as error:
                logger.exception("Anki Garden: could not preserve invalid state")
                raise StatePreservationError(
                    "Anki Garden could not preserve the saved garden; startup was stopped before any overwrite."
                ) from error
            raise StatePreservationError(
                "Garden preserved unreadable progress and stopped before overwriting it."
            ) from load_error
        return GardenState()

    def _atomic_write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path: Path | None = None
        try:
            with NamedTemporaryFile("w", delete=False, dir=path.parent, encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, ensure_ascii=False)
                handle.flush()
                temp_path = Path(handle.name)
            temp_path.replace(path)
            temp_path = None
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    @timed("storage.save")
    def save(self) -> None:
        if getattr(self, "runtime_pending", False) and not getattr(self, "_allow_runtime_commit", False):
            raise RuntimeError("Garden is still updating. Please try this change again shortly.")
        if self._reward_ledger is None:
            self._atomic_write_json(self.data_path, self.state.to_dict())
            return
        self.refresh_lifetime_economy_aggregates()
        committed = self._reward_ledger.commit_state(
            self._bounded_state_payload(self.state),
            schema_version=STATE_VERSION,
            expected_revision=self._ledger_revision,
        )
        self._ledger_revision = committed.revision
        try:
            self._refresh_recent_find_cache()
        except Exception:
            # The authoritative commit is already durable. A presentation
            # cache failure must not make the engine attempt to roll it back.
            logger.exception("Anki Garden: recent Find cache refresh deferred")

    def create_development_backup(self) -> Path:
        """Create a one-off recovery point before a development seed."""

        self.save()
        backup_dir = self.user_files_dir / "development_backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        if self._reward_ledger is None:
            destination = backup_dir / f"garden-state-{stamp}-{time.time_ns()}.json"
            _required_backup(self.data_path, destination)
            return destination
        destination = backup_dir / f"garden-state-{stamp}-{time.time_ns()}.sqlite3"
        self._reward_ledger.backup_to(destination)
        return destination

    def load_development_backup(self, path: Path) -> GardenState:
        candidate = Path(path).resolve()
        backup_root = (self.user_files_dir / "development_backups").resolve()
        if candidate.parent != backup_root or not candidate.is_file():
            raise StatePreservationError("That development backup is not available.")
        if candidate.suffix == ".sqlite3":
            ledger = RewardLedger(candidate)
            try:
                snapshot = ledger.load_state_snapshot()
                reanswer_hints = ledger.reanswer_hints()
            finally:
                ledger.close()
            if snapshot is None or snapshot.schema_version != STATE_VERSION:
                raise StatePreservationError(
                    "That development backup uses an unsupported schema."
                )
            payload = deepcopy(dict(snapshot.payload))
            state = GardenState.from_dict(payload)
            state.pending_reanswer_lineages = reanswer_hints
            return state
        raw = json.loads(candidate.read_text("utf-8"))
        if not isinstance(raw, dict) or int(raw.get("version", -1)) != STATE_VERSION:
            raise StatePreservationError("That development backup uses an unsupported schema.")
        payload = deepcopy(raw)
        return GardenState.from_dict(payload)

    def restore_development_backup(self, path: Path) -> GardenState:
        """Atomically restore both bounded state and exact reward authority."""

        candidate = Path(path).resolve()
        backup_root = (self.user_files_dir / "development_backups").resolve()
        if (
            candidate.parent != backup_root
            or not candidate.is_file()
            or candidate.suffix != ".sqlite3"
        ):
            # Legacy JSON backups contain no SQLite authority and are retained
            # only for source-compatible inspection.
            raise StatePreservationError(
                "That development backup cannot restore the current reward ledger."
            )
        if self._reward_ledger is None:
            raise StatePreservationError("The reward database is not available.")
        if self._reward_ledger.has_staged_writes:
            raise StatePreservationError(
                "Finish the current Garden transaction before restoring a backup."
            )
        source = RewardLedger(candidate)
        replacement = self.user_files_dir / (
            f".{REWARD_DATABASE_FILENAME}.{uuid.uuid4().hex}.restore"
        )
        try:
            source.backup_to(replacement)
        finally:
            source.close()
        prior = self.database_path.with_suffix(
            f".pre-restore-{time.time_ns()}.sqlite3"
        )
        self._reward_ledger.backup_to(prior)
        self._reward_ledger.close()
        try:
            os.replace(replacement, self.database_path)
            self._reward_ledger = RewardLedger(self.database_path)
            snapshot = self._reward_ledger.load_state_snapshot()
            if snapshot is None or snapshot.schema_version != STATE_VERSION:
                raise StatePreservationError(
                    "The restored database uses an unsupported schema."
                )
            payload = deepcopy(dict(snapshot.payload))
            restored = GardenState.from_dict(payload)
            self._ledger_revision = snapshot.revision
            self._refresh_reanswer_hint_cache(restored)
            self._refresh_recent_find_cache(restored)
            self.state = restored
            return restored
        except Exception:
            # The prior database is a complete online backup. Put it back if
            # reopening the selected recovery point fails.
            failed_ledger = self._reward_ledger
            if failed_ledger is not None:
                failed_ledger.close()
            self._reward_ledger = None
            os.replace(prior, self.database_path)
            self._reward_ledger = RewardLedger(self.database_path)
            snapshot = self._reward_ledger.load_state_snapshot()
            self._ledger_revision = snapshot.revision if snapshot else 0
            raise
        finally:
            replacement.unlink(missing_ok=True)

    def ensure_revlog_ledger_ready(self) -> None:
        """Atomically seed schema-14 idempotency from the legacy scalar cursor."""
        if not self.state.revlog_ledger_migration_pending:
            return
        day_start, day_end = self.current_scheduler_day_bounds_ms()
        rows = self._load_revlog_entries_between(
            day_start,
            day_end,
            MAX_PROCESSED_REVLOG_IDS,
        )
        legacy_cursor = max(0, int(self.state.processed_revlog_floor or 0))
        seeded_ids = sorted({
            int(row[0])
            for row in rows
            if day_start <= int(row[0]) < day_end
            and int(row[0]) <= legacy_cursor
        })
        previous = (
            self.state.last_processed_revlog_id,
            self.state.processed_revlog_floor,
            list(self.state.processed_revlog_ids),
            self.state.revlog_ledger_migration_pending,
        )
        self.state.processed_revlog_floor = max(0, day_start - 1)
        self.state.processed_revlog_ids = seeded_ids
        self.state.last_processed_revlog_id = max(
            self.state.last_processed_revlog_id,
            self.state.processed_revlog_floor,
        )
        self.state.revlog_ledger_migration_pending = False
        try:
            self.save()
        except Exception:
            (
                self.state.last_processed_revlog_id,
                self.state.processed_revlog_floor,
                self.state.processed_revlog_ids,
                self.state.revlog_ledger_migration_pending,
            ) = previous
            raise

    def _ensure_defaults(self) -> None:
        before = self.state.to_dict()
        self.user_files_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        _materialize_unlocked_species(self.state)
        try:
            GardenStorage.ensure_revlog_ledger_ready(self)
        except RevlogReadError:
            # Persist the pending marker without changing either cursor. Every
            # live entry point retries this seed before review reconciliation.
            logger.warning(
                "Anki Garden: review ledger migration deferred until the collection is readable"
            )
        try:
            scheduler_day = self.current_scheduler_day()
            scheduler_day_floor = max(0, int(self.current_day_start_ms()) - 1)
        except SchedulerBoundaryError:
            # Keep the saved scheduler day. Falling back to the wall calendar
            # here could persist a false rollover before Anki's collection and
            # scheduler have finished opening.
            scheduler_day = self.state.daily_stats.day
            scheduler_day_floor = self.state.processed_revlog_floor
            logger.warning(
                "Anki Garden: scheduler day unavailable during state repair; preserving %s",
                scheduler_day,
            )
        if self.state.daily_stats.reviewed == 0 and self.state.daily_stats.day != scheduler_day:
            self.state.daily_stats.day = scheduler_day
            self.state.processed_revlog_floor = scheduler_day_floor
            self.state.processed_revlog_ids = []
        repaired_invalid_reference = bool(
            getattr(self.state, "_active_plant_reference_invalid", False)
        )
        active = next((
            plant for plant in self.state.plants
            if plant.plant_id == self.state.active_plant_id
            and plant.planted
            and not plant.fully_grown
        ), None)
        if self.state.active_plant_id is not None and active is None:
            repaired_invalid_reference = not any(
                plant.plant_id == self.state.active_plant_id for plant in self.state.plants
            )
            self.state.active_plant_id = None
        if repaired_invalid_reference:
            candidate = next((
                plant for plant in sorted(
                    self.state.plants,
                    key=lambda item: (
                        item.slot_index is None,
                        item.slot_index if item.slot_index is not None else 99,
                        item.plant_id,
                    ),
                )
                if plant.planted and not plant.fully_grown
            ), None)
            self.state.active_plant_id = candidate.plant_id if candidate else None
            self.state._active_plant_reference_invalid = False
        if not self.state.active_plant_periods:
            self.state.active_plant_periods.append(ActivePlantPeriod(
                scheduler_day,
                self.state.active_plant_id if self.state.starter_selection_complete else None,
                0 if not self.state.starter_selection_complete else self.current_time_ms(),
            ))
        else:
            desired_plant_id = (
                self.state.active_plant_id
                if self.state.starter_selection_complete
                else None
            )
            latest = max(
                self.state.active_plant_periods,
                key=lambda period: (period.started_at_ms, period.day),
                default=None,
            )
            if latest is None or latest.plant_id != desired_plant_id:
                self.state.active_plant_periods.append(ActivePlantPeriod(
                    scheduler_day,
                    desired_plant_id,
                    0 if not self.state.starter_selection_complete else self.current_time_ms(),
                ))
        staged = getattr(self, "reward_ledger_has_staged_writes", None)
        if self.state.to_dict() != before or (callable(staged) and staged()):
            self.save()

    def load_asset_metadata(self) -> dict:
        if not self.asset_metadata.exists():
            return {}
        try:
            return json.loads(self.asset_metadata.read_text("utf-8"))
        except Exception:
            return {}

    def save_asset_metadata(self, data: dict) -> None:
        self._atomic_write_json(self.asset_metadata, data)

    @staticmethod
    def current_time_ms() -> int:
        return int(datetime.now().timestamp() * 1000)

    def maintenance_signature(self) -> tuple[str, int, int]:
        """Return the cheap authorities that make one reconciliation reusable.

        Sync and undo can add or remove rows below the scalar high-water, so
        their hooks explicitly invalidate the caller's session generation.
        This signature covers the remaining steady-state authorities without
        serializing the complete Garden state or rereading full history.
        """

        if self.reward_ledger_has_staged_writes():
            raise RevlogReadError(
                "Garden maintenance cannot be reused during a pending transaction."
            )
        scheduler_day = self.current_scheduler_day()
        high_water = self.eligible_review_history_high_water()
        if self.current_scheduler_day() != scheduler_day:
            raise SchedulerBoundaryError(
                "Anki's scheduler day changed while maintenance was sampled."
            )
        return scheduler_day, high_water, max(0, int(self._ledger_revision))

    def max_revlog_id(self) -> int:
        collection = getattr(self.mw, "col", None)
        if collection is None or getattr(collection, "db", None) is None:
            raise RevlogReadError("Anki review history is not available yet.")
        try:
            value = collection.db.scalar("select max(id) from revlog")
            return max(0, int(value or 0))
        except Exception as error:
            logger.exception("Anki Garden: unable to read the latest review-history id")
            raise RevlogReadError(
                "Anki Garden could not read the latest review-history id."
            ) from error

    def load_proven_local_answer(
        self,
        *,
        after_id: int,
        card_id: int,
        ease: int,
    ) -> LocalAnswerProof | None:
        """Read a locally appended answer only when its identity is unique.

        The caller may use this narrow query only after a complete session
        reconciliation and must revoke that proof on sync, undo, collection
        reload, or any error. This method rejects multiple appended rows,
        callback/card mismatches, and same-card ledger ambiguity; explicit
        invalidation handles history mutations below the processed cursor.
        Callers use the established full-day fallback whenever proof is absent.
        """

        verified_through = max(0, int(getattr(self, "_verified_history_high_water", 0)))
        normalized_card = max(0, int(card_id))
        normalized_ease = int(ease)
        if normalized_card <= 0 or normalized_ease <= 0:
            return None
        collection = getattr(self.mw, "col", None)
        if collection is None or getattr(collection, "db", None) is None:
            raise RevlogReadError("Anki review history is not available yet.")
        day_start, day_end = self.current_scheduler_day_bounds_ms()
        # A persisted scalar cursor can include future-dated imported history.
        # It cannot hide today's answers from the already verified local path.
        local_after = int(after_id)
        if local_after >= int(day_end):
            local_after = max(
                (int(value) for value in self.state.processed_revlog_ids
                 if int(value) < int(day_end)),
                default=0,
            )
        normalized_after = max(verified_through, local_after)
        lower_bound = max(max(0, int(day_start) - 1), normalized_after)
        bounded_limit = min(MAX_PROCESSED_REVLOG_IDS, 2)
        try:
            appended = collection.db.all(
                "select id, cid, ease, ivl, lastIvl, factor, time, type "
                "from revlog where id > ? and id < ? "
                "and type in (0, 1, 2, 3) order by id asc limit ?",
                lower_bound,
                int(day_end),
                bounded_limit,
            )
            if len(appended) != 1:
                return None
            row = tuple(appended[0])
            if (
                len(row) < 8
                or int(row[0]) <= normalized_after
                or int(row[1]) != normalized_card
                or int(row[2]) != normalized_ease
            ):
                return None
            card_rows = collection.db.all(
                "select id, cid, ease, ivl, lastIvl, factor, time, type "
                "from revlog where id > ? and id < ? and cid = ? "
                "and type in (0, 1, 2, 3) order by id asc limit ?",
                max(0, int(day_start) - 1),
                int(day_end),
                normalized_card,
                MAX_PROCESSED_REVLOG_IDS + 1,
            )
            if len(card_rows) > MAX_PROCESSED_REVLOG_IDS:
                return None
            normalized_card_rows = [tuple(item) for item in card_rows]
            unseen = unprocessed_revlog_entries(self.state, normalized_card_rows)
            if verified_through:
                unseen = [item for item in unseen if int(item[0]) > verified_through]
            if len(unseen) != 1 or int(unseen[0][0]) != int(row[0]):
                return None
            return LocalAnswerProof(row, tuple(normalized_card_rows))
        except (RevlogReadError, SchedulerBoundaryError):
            raise
        except Exception as error:
            logger.exception("Anki Garden: unable to prove the local review answer")
            raise RevlogReadError(
                "Anki Garden could not verify this card."
            ) from error

    def deck_ids_for_cards(self, card_ids: Any) -> dict[int, int]:
        """Resolve review deck identities in bounded SQL batches."""

        collection = getattr(self.mw, "col", None)
        if collection is None or getattr(collection, "db", None) is None:
            return {}
        normalized = sorted({
            int(card_id)
            for card_id in card_ids
            if isinstance(card_id, int)
            and not isinstance(card_id, bool)
            and int(card_id) > 0
        })
        result: dict[int, int] = {}
        chunk_size = 900
        for offset in range(0, len(normalized), chunk_size):
            chunk = normalized[offset:offset + chunk_size]
            placeholders = ",".join("?" for _item in chunk)
            rows = collection.db.all(
                "select id, did from cards where id in (" + placeholders + ")",
                *chunk,
            )
            for row in rows:
                try:
                    card_id, deck_id = int(row[0]), int(row[1])
                except (IndexError, TypeError, ValueError):
                    continue
                if card_id in chunk:
                    result[card_id] = deck_id
        return result

    def eligible_review_history_high_water(self) -> int:
        """Snapshot the newest eligible revlog identity for a consistent scan."""

        collection = getattr(self.mw, "col", None)
        if collection is None or getattr(collection, "db", None) is None:
            raise RevlogReadError("Anki review history is not available yet.")
        try:
            value = collection.db.scalar(
                "select max(id) from revlog where type in (0, 1, 2, 3)"
            )
            return max(0, int(value or 0))
        except Exception as error:
            logger.exception("Anki Garden: unable to snapshot eligible review history")
            raise RevlogReadError(
                "Anki Garden could not snapshot eligible review history."
            ) from error

    @staticmethod
    def _scheduler_day_from_wall_cutoff(
        answer_ms: int,
        cutoff_local: datetime,
    ) -> str:
        """Map an answer to an Anki day using local wall time, including DST.

        ``datetime.fromtimestamp`` applies the timezone offset in force on the
        historical answer itself. Comparing only local clock components keeps
        a fixed Anki cutoff (for example 04:00) stable across 23- and 25-hour
        local days.
        """

        answered_local = datetime.fromtimestamp(max(0, int(answer_ms)) / 1000)
        answered_clock = (
            answered_local.hour,
            answered_local.minute,
            answered_local.second,
            answered_local.microsecond,
        )
        cutoff_clock = (
            cutoff_local.hour,
            cutoff_local.minute,
            cutoff_local.second,
            cutoff_local.microsecond,
        )
        scheduler_date = answered_local.date()
        if answered_clock < cutoff_clock:
            scheduler_date -= timedelta(days=1)
        return scheduler_date.isoformat()

    def scheduler_day_for_answer_ms(self, answer_ms: int) -> str:
        """Public mapping used by reward reconciliation and focused tests."""

        _, cutoff_ms = self.current_scheduler_day_bounds_ms()
        cutoff_local = datetime.fromtimestamp(cutoff_ms / 1000)
        return self._scheduler_day_from_wall_cutoff(answer_ms, cutoff_local)

    def load_eligible_review_history_page(
        self,
        *,
        after_id: int,
        high_water_revlog_id: int,
        limit: int = DEFAULT_HISTORY_PAGE_SIZE,
    ) -> HistoricalReviewPage:
        """Read one deterministic page inside a previously snapped high-water.

        The SQL always requests ``limit + 1``. The extra row is used only to
        prove whether another page exists; callers never receive an implicitly
        truncated page.
        """

        collection = getattr(self.mw, "col", None)
        if collection is None or getattr(collection, "db", None) is None:
            raise RevlogReadError("Anki review history is not available yet.")
        lower_bound = max(0, int(after_id))
        high_water = max(0, int(high_water_revlog_id))
        if lower_bound > high_water:
            raise RevlogReadError("The review-history page bounds are invalid.")
        bounded_limit = min(
            MAX_HISTORICAL_REVLOG_ENTRIES,
            max(1, int(limit)),
        )
        try:
            _, cutoff_ms = self.current_scheduler_day_bounds_ms()
            cutoff_local = datetime.fromtimestamp(cutoff_ms / 1000)
            rows = collection.db.all(
                "select id, cid, ease, ivl, lastIvl, factor, time, type "
                "from revlog where id > ? and id <= ? "
                "and type in (0, 1, 2, 3) order by id asc limit ?",
                lower_bound,
                high_water,
                bounded_limit + 1,
            )
        except (RevlogReadError, SchedulerBoundaryError):
            raise
        except Exception as error:
            logger.exception("Anki Garden: unable to read eligible review history")
            raise RevlogReadError(
                "Anki Garden could not read eligible review history."
            ) from error

        has_more = len(rows) > bounded_limit
        visible_rows = rows[:bounded_limit]
        entries: list[HistoricalReviewEntry] = []
        for row in visible_rows:
            try:
                revlog_id = int(row[0])
                review_type = int(row[7])
                if revlog_id <= lower_bound or revlog_id > high_water:
                    raise ValueError("revlog identity outside snapped page")
                if review_type not in {0, 1, 2, 3}:
                    raise ValueError("ineligible revlog type")
                entries.append(HistoricalReviewEntry(
                    revlog_id=revlog_id,
                    card_id=int(row[1]),
                    ease=int(row[2]),
                    interval=int(row[3]),
                    last_interval=int(row[4]),
                    factor=int(row[5]),
                    response_time_ms=max(0, int(row[6])),
                    review_type=review_type,
                    answer_ms=revlog_id,
                    scheduler_day=self._scheduler_day_from_wall_cutoff(
                        revlog_id,
                        cutoff_local,
                    ),
                ))
            except (IndexError, TypeError, ValueError) as error:
                raise RevlogReadError(
                    "Anki Garden found a malformed eligible review-history row."
                ) from error
        next_after = entries[-1].revlog_id if entries else lower_bound
        if has_more and next_after <= lower_bound:
            raise RevlogReadError("Review-history pagination made no progress.")
        return HistoricalReviewPage(
            entries=tuple(entries),
            high_water_revlog_id=high_water,
            next_after_id=next_after,
            has_more=has_more,
        )

    @timed("history.load-batch")
    def load_reconciliation_history(self) -> HistoricalReviewSnapshot | IndexedHistoricalReviewSnapshot:
        """Use the verified index; compatibility adapters retain the full reader."""
        self._history_batch_has_more = False
        index = getattr(self, "history_index", None)
        if index is None or self._reward_ledger is None:
            return self.load_eligible_review_history()
        from .history_index import analyze_indexed_days

        current_day = self.current_scheduler_day()
        days = tuple(day for day in index.summaries() if str(day["day"]) <= current_day)
        history = analyze_indexed_days(days, current_open_day=current_day)
        closed = analyze_indexed_days(days, current_open_day=current_day, include_open_day=False)
        entries: list[HistoricalReviewEntry] = []
        ordinals: dict[int, int] = {}
        # The coordinator plans and commits aliases before enabling replay.
        # Loading a reward batch is now independent of each card's lifetime.
        batch_limit = getattr(self, "_history_batch_limit", None)
        for page in index.reward_pages(
            activation_ms=max(1, int(self.state.reward_activation_ms)),
            through_day=current_day, ledger_path=self.database_path,
            limit=None if batch_limit is None else batch_limit + 1,
            after_id=getattr(self, "_history_after_id", 0),
        ):
            identities = self._reward_ledger.bindings_for_revlogs(int(row[0]) for row in page)
            if len(identities) != len(page):
                raise RevlogReadError("Answer identities are still being prepared.")
            for row in page:
                revlog_id = int(row[0])
                lineage = identities[revlog_id]
                self.stage_answer_lineage_alias(revlog_id, lineage)
                entries.append(HistoricalReviewEntry(
                    revlog_id=revlog_id, card_id=int(row[1]), ease=int(row[2]), interval=int(row[3]),
                    last_interval=int(row[4]), factor=int(row[5]), response_time_ms=int(row[6]),
                    review_type=int(row[7]), answer_ms=revlog_id, scheduler_day=str(row[8]),
                    card_day_ordinal=int(lineage.rsplit("|", 1)[-1]), answer_identity=lineage,
                ))
                ordinals[revlog_id] = int(row[9])
        if batch_limit is not None and len(entries) > batch_limit:
            self._history_batch_has_more = True
            entries = entries[:batch_limit]
            ordinals = {entry.revlog_id: ordinals[entry.revlog_id] for entry in entries}
        self._history_loaded_through = max((entry.revlog_id for entry in entries), default=0)
        return IndexedHistoricalReviewSnapshot(
            tuple(entries), max((int(row["last"]) for row in days), default=0), history.fingerprint,
            history, closed, days, ordinals,
        )

    def load_eligible_review_history(
        self,
        *,
        high_water_revlog_id: int | None = None,
        max_entries: int = MAX_HISTORICAL_REVLOG_ENTRIES,
        page_size: int = DEFAULT_HISTORY_PAGE_SIZE,
    ) -> HistoricalReviewSnapshot:
        """Read a complete eligible history snapshot or fail closed.

        Persisted card-answer lineages give reward reconciliation identities
        that survive undo/reanswer replacement and later synced insertions.
        Reviews are returned chronologically by revlog identity.
        """

        high_water = (
            self.eligible_review_history_high_water()
            if high_water_revlog_id is None
            else max(0, int(high_water_revlog_id))
        )
        bounded_max = min(
            MAX_HISTORICAL_REVLOG_ENTRIES,
            max(1, int(max_entries)),
        )
        bounded_page = min(bounded_max, max(1, int(page_size)))
        entries: list[HistoricalReviewEntry] = []
        after_id = 0
        while after_id < high_water:
            remaining = bounded_max - len(entries)
            if remaining <= 0:
                raise RevlogReadError(
                    "Eligible review history exceeded Garden's safety bound."
                )
            page = self.load_eligible_review_history_page(
                after_id=after_id,
                high_water_revlog_id=high_water,
                limit=min(bounded_page, remaining),
            )
            entries.extend(page.entries)
            if len(entries) >= bounded_max and page.has_more:
                raise RevlogReadError(
                    "Eligible review history exceeded Garden's safety bound."
                )
            after_id = page.next_after_id
            if not page.has_more:
                break

        ordinals: dict[tuple[str, int], int] = {}
        normalized: list[HistoricalReviewEntry] = []
        digest = hashlib.sha256()
        for entry in entries:
            ordinal_key = (entry.scheduler_day, entry.card_id)
            ordinal = ordinals.get(ordinal_key, 0) + 1
            ordinals[ordinal_key] = ordinal
            normalized_entry = replace(entry, card_day_ordinal=ordinal)
            normalized.append(normalized_entry)
        existing_bindings = self.answer_lineage_bindings_for_cards(
            {entry.card_id for entry in normalized}
        )
        identities, bindings = assign_stable_answer_identities(
            [
                (entry.revlog_id, entry.card_id, entry.scheduler_day)
                for entry in normalized
            ],
            existing_bindings,
            self.pending_reanswer_lineages(),
        )
        normalized = [
            replace(
                entry,
                answer_identity=identities.get(entry.revlog_id, ""),
            )
            for entry in normalized
        ]
        for revlog_id, lineage in identities.items():
            self.stage_answer_lineage_alias(revlog_id, lineage)
        for normalized_entry in normalized:
            digest.update(
                (
                    f"{normalized_entry.revlog_id}|{normalized_entry.card_id}|"
                    f"{normalized_entry.ease}|{normalized_entry.interval}|"
                    f"{normalized_entry.last_interval}|{normalized_entry.factor}|"
                    f"{normalized_entry.response_time_ms}|{normalized_entry.review_type}|"
                    f"{normalized_entry.scheduler_day}|"
                    f"{normalized_entry.stable_answer_key}\n"
                ).encode("utf-8")
            )
        return HistoricalReviewSnapshot(
            entries=tuple(normalized),
            high_water_revlog_id=high_water,
            fingerprint=digest.hexdigest(),
            answer_lineage_bindings=bindings,
        )

    def review_type_for_revlog_id(self, revlog_id: int) -> int | None:
        collection = getattr(self.mw, "col", None)
        if collection is None or getattr(collection, "db", None) is None or int(revlog_id) <= 0:
            return None
        try:
            value = collection.db.scalar("select type from revlog where id = ?", int(revlog_id))
            return int(value) if value is not None else None
        except Exception:
            return None

    def load_new_revlog_entries(
        self,
        after_id: int,
        limit: int = MAX_PROCESSED_REVLOG_IDS,
    ) -> list[tuple[Any, ...]]:
        """Read the bounded current scheduler day for ledger-based reconciliation.

        ``after_id`` remains part of the compatibility API, but cannot be used
        as the SQL lower bound: synced devices may deliver an unseen row whose
        id is lower than the scalar cursor.
        """
        day_start, day_end = self.current_scheduler_day_bounds_ms()
        return self._load_revlog_entries_between(day_start, day_end, limit)

    def _load_revlog_entries_between(
        self,
        day_start: int,
        day_end: int,
        limit: int,
    ) -> list[tuple[Any, ...]]:
        collection = getattr(self.mw, "col", None)
        if collection is None or getattr(collection, "db", None) is None:
            raise RevlogReadError("Anki review history is not available yet.")
        lower_bound = max(0, int(day_start) - 1)
        upper_bound = int(day_end)
        if upper_bound <= int(day_start):
            raise SchedulerBoundaryError("Anki's scheduler-day cutoff is invalid.")
        bounded_limit = min(MAX_PROCESSED_REVLOG_IDS, max(1, int(limit)))
        try:
            rows = collection.db.all(
                "select id, cid, ease, ivl, lastIvl, factor, time, type "
                "from revlog where id > ? and id < ? "
                "and type in (0, 1, 2, 3) order by id asc limit ?",
                lower_bound,
                day_end,
                bounded_limit + 1,
            )
            if len(rows) > bounded_limit:
                raise RevlogReadError(
                    "The current scheduler day exceeded Garden's review-history safety bound."
                )
            return rows
        except RevlogReadError:
            raise
        except Exception:
            logger.exception("Anki Garden: unable to read same-day review history")
            raise RevlogReadError(
                "Anki Garden could not read same-day review history."
            )

    def current_day_start_ms(self) -> int:
        """Return the beginning of Anki's current scheduler day in milliseconds."""
        return self.current_scheduler_day_bounds_ms()[0]

    def current_scheduler_day_bounds_ms(self) -> tuple[int, int]:
        """Return one internally consistent ``[start, end)`` scheduler interval."""
        cutoff = self.current_day_end_ms()
        if cutoff <= 0:
            raise SchedulerBoundaryError("Anki's scheduler-day cutoff is unavailable.")
        try:
            cutoff_local = datetime.fromtimestamp(cutoff / 1000)
            previous_date = cutoff_local.date() - timedelta(days=1)
            previous_wall_time = datetime.combine(previous_date, cutoff_local.time())
            start = int(time.mktime(previous_wall_time.timetuple()) * 1000)
            start += previous_wall_time.microsecond // 1000
        except Exception as error:
            raise SchedulerBoundaryError(
                "Anki's scheduler-day cutoff is invalid."
            ) from error
        if start <= 0 or start >= cutoff:
            raise SchedulerBoundaryError("Anki's scheduler-day cutoff is invalid.")
        return start, cutoff

    def reviews_today(self) -> int:
        """Return the authoritative all-decks scheduler-day review count."""

        collection = getattr(self.mw, "col", None)
        if collection is None or getattr(collection, "db", None) is None:
            raise RevlogReadError("Anki review history is not available yet.")
        day_start_ms, day_end_ms = self.current_scheduler_day_bounds_ms()
        try:
            count = collection.db.scalar(
                "select count(*) from revlog where id >= ? and id < ? "
                "and type in (0, 1, 2, 3)",
                int(day_start_ms),
                int(day_end_ms),
            )
            return max(0, int(count or 0))
        except Exception as error:
            raise RevlogReadError(
                "Anki Garden could not count today's review history."
            ) from error

    def current_day_end_ms(self) -> int:
        collection = getattr(self.mw, "col", None)
        if collection is None or getattr(collection, "sched", None) is None:
            return 0
        try:
            sched = collection.sched
            cutoff = getattr(sched, "day_cutoff", None)
            if cutoff is None:
                cutoff = getattr(sched, "dayCutoff", None)
            return max(0, int(cutoff or 0) * 1000)
        except Exception:
            return 0

    def current_scheduler_day(self) -> str:
        start = self.current_day_start_ms()
        return datetime.fromtimestamp(start / 1000).date().isoformat()

    def retrospective_streak(self, *, limit_days: int = 10_000) -> ReviewStreakSnapshot:
        """Return the current consecutive-day streak from Anki review history.

        Revlog timestamps are shifted by the wall-clock time of Anki's current
        scheduler cutoff before they are grouped. This keeps reviews before the
        cutoff attached to the preceding Anki day, including across local DST
        changes, without replaying any historical Garden rewards or Growth.
        """

        collection = getattr(self.mw, "col", None)
        if collection is None or getattr(collection, "db", None) is None:
            raise RevlogReadError("Anki review history is not available yet.")
        try:
            _, cutoff_ms = self.current_scheduler_day_bounds_ms()
            cutoff_local = datetime.fromtimestamp(cutoff_ms / 1000)
            cutoff_minutes = cutoff_local.hour * 60 + cutoff_local.minute
            shift_modifier = f"-{cutoff_minutes} minutes"
            bounded_limit = min(20_000, max(2, int(limit_days)))
            rows = collection.db.all(
                "select distinct date(id / 1000, 'unixepoch', 'localtime', ?) as garden_day "
                "from revlog where id < ? and type in (0, 1, 2, 3) "
                "order by garden_day desc limit ?",
                shift_modifier,
                int(cutoff_ms),
                bounded_limit,
            )
        except (RevlogReadError, SchedulerBoundaryError):
            raise
        except Exception as error:
            logger.exception("Anki Garden: unable to derive the Anki streak")
            raise RevlogReadError(
                "Anki Garden could not read the review history needed for the streak."
            ) from error

        review_days: set[date] = set()
        for row in rows:
            raw_day = row[0] if isinstance(row, (list, tuple)) and row else row
            try:
                review_days.add(date.fromisoformat(str(raw_day)))
            except (TypeError, ValueError):
                continue
        try:
            today = date.fromisoformat(self.current_scheduler_day())
        except (TypeError, ValueError) as error:
            raise SchedulerBoundaryError("Anki's scheduler day is invalid.") from error
        review_days = {day for day in review_days if day <= today}
        studied_today = today in review_days
        cursor = today if studied_today else today - timedelta(days=1)
        latest_day = max(review_days).isoformat() if review_days else ""
        days = 0
        while cursor in review_days and days < bounded_limit:
            days += 1
            cursor -= timedelta(days=1)
        return ReviewStreakSnapshot(days, latest_day, studied_today)

    def scheduler_day_index(self) -> int:
        collection = getattr(self.mw, "col", None)
        sched = getattr(collection, "sched", None) if collection is not None else None
        try:
            return max(0, int(getattr(sched, "today")))
        except Exception:
            return 0

    @staticmethod
    def _post_answer_card_state(
        *,
        queue: int,
        due: int,
        scheduler_day_index: int,
        cutoff_seconds: int,
    ) -> str:
        """Classify one committed card against the unified Today scope.

        The classification is deliberately conservative. Buried and suspended
        cards are not completed obligations, and unknown queue kinds cannot be
        used to prove the final daily reward.
        """

        normalized_queue = int(queue)
        normalized_due = int(due)
        if normalized_queue in {-3, -2}:
            return "buried"
        if normalized_queue == -1:
            return "suspended"
        if normalized_queue == 0:
            return "remaining"
        if normalized_queue == 1:
            return (
                "remaining"
                if normalized_due < max(0, int(cutoff_seconds))
                else "completed"
            )
        if normalized_queue in {2, 3}:
            return (
                "remaining"
                if normalized_due <= max(0, int(scheduler_day_index))
                else "completed"
            )
        return "unknown"

    @classmethod
    def _committed_card_transition_snapshot(
        cls,
        collection: Any,
        card_ids: Iterable[int],
        *,
        scheduler_day_index: int,
        cutoff_seconds: int,
    ) -> tuple[tuple[tuple[int, str], ...], tuple[int, ...]]:
        """Return post-answer card states and explicitly related buried siblings."""

        requested = tuple(sorted({
            int(card_id)
            for card_id in card_ids
            if isinstance(card_id, int)
            and not isinstance(card_id, bool)
            and int(card_id) > 0
        }))
        if not requested:
            return (), ()
        rows_by_id: dict[int, tuple[int, int, int]] = {}
        for offset in range(0, len(requested), 900):
            chunk = requested[offset:offset + 900]
            placeholders = ",".join("?" for _value in chunk)
            rows = collection.db.all(
                "select id, nid, queue, due from cards where id in "
                f"({placeholders})",
                *chunk,
            )
            for raw_card_id, raw_note_id, raw_queue, raw_due in rows:
                try:
                    card_id = int(raw_card_id)
                    if card_id not in requested:
                        continue
                    rows_by_id[card_id] = (
                        int(raw_note_id), int(raw_queue), int(raw_due)
                    )
                except (TypeError, ValueError):
                    continue
        transitions = tuple(
            (
                card_id,
                cls._post_answer_card_state(
                    queue=rows_by_id[card_id][1],
                    due=rows_by_id[card_id][2],
                    scheduler_day_index=scheduler_day_index,
                    cutoff_seconds=cutoff_seconds,
                ) if card_id in rows_by_id else "unknown",
            )
            for card_id in requested
        )
        note_ids = tuple(sorted({
            note_id for note_id, _queue, _due in rows_by_id.values()
            if note_id > 0
        }))
        buried_siblings: set[int] = set()
        for offset in range(0, len(note_ids), 900):
            chunk = note_ids[offset:offset + 900]
            placeholders = ",".join("?" for _value in chunk)
            rows = collection.db.all(
                "select id from cards where nid in "
                f"({placeholders}) and queue in (-3, -2)",
                *chunk,
            )
            for row in rows:
                raw_card_id = row[0] if isinstance(row, (tuple, list)) else row
                try:
                    card_id = int(raw_card_id)
                except (TypeError, ValueError):
                    continue
                if card_id > 0 and card_id not in requested:
                    buried_siblings.add(card_id)
        return transitions, tuple(sorted(buried_siblings))

    def invalidate_due_snapshot(self) -> None:
        self._due_snapshot = None
        self._due_snapshot_collection = None
        self._due_tree_snapshot = None

    def due_tree(self) -> Any | None:
        """Share the exact scheduler tree used for the current due snapshot.

        The snapshot expires on collection changes, review operations, learning
        deadlines, and day rollover, so presentation never extends its lifetime.
        """

        status = self.due_obligations()
        if not status.available or status.error:
            return None
        return getattr(self, "_due_tree_snapshot", None)

    def due_obligations(self, *, committed_card_ids: Iterable[int] = ()) -> DueObligationStatus:
        if getattr(self, "runtime_pending", False) and not getattr(self, "_allow_runtime_commit", False):
            return DueObligationStatus(available=False, error="Garden is updating.")
        collection = getattr(self.mw, "col", None)
        requested = tuple(sorted({int(value) for value in committed_card_ids
                                  if isinstance(value, int) and not isinstance(value, bool) and value > 0}))
        cached = getattr(self, "_due_snapshot", None)
        now_ms = int(time.time() * 1000)
        if cached is not None and getattr(self, "_due_snapshot_collection", None) is collection:
            deadlines = [value for value in (cached.cutoff_at_ms, cached.next_learning_due_at_ms) if value > 0]
            if deadlines and now_ms < min(deadlines):
                if not requested:
                    return replace(cached, committed_card_ids=(), card_transitions=(), buried_sibling_card_ids=())
                if requested == cached.committed_card_ids:
                    return cached
        from .performance import RUNTIME_PERFORMANCE
        started = RUNTIME_PERFORMANCE.begin()
        try:
            result = self._read_due_obligations(committed_card_ids=requested)
            if result.available and not result.error:
                self._due_snapshot = result
                self._due_snapshot_collection = collection
            return result
        finally:
            RUNTIME_PERFORMANCE.finish("scheduler.snapshot", started)

    def _read_due_obligations(
        self,
        *,
        committed_card_ids: Iterable[int] = (),
    ) -> DueObligationStatus:
        """Return the live collection-wide Today’s Cards obligation set.

        Scheduler-available New, Learn, and Review counts come from Anki's deck
        tree, which applies active deck limits and includes filtered decks.
        Learning and relearning cards remain obligations through the scheduler-day
        cutoff even when an intraday step is not available at this exact second.
        Negative queue values (suspended/buried) are deliberately excluded.
        """
        self.invalidate_due_snapshot()
        collection = getattr(self.mw, "col", None)
        if collection is None or getattr(collection, "db", None) is None or getattr(collection, "sched", None) is None:
            return DueObligationStatus(
                available=False,
                error=(
                    "Anki Garden could not verify today’s cards. "
                    "Normal Garden Growth is unaffected."
                ),
            )
        try:
            tree = collection.sched.deck_due_tree()
            self._due_tree_snapshot = tree
            new_count, tree_learning, review_count = self._due_tree_totals(tree)
            end_ms = self.current_day_end_ms()
            today_index = self.scheduler_day_index()
            if end_ms <= 0:
                raise RuntimeError("scheduler cutoff is unavailable")
            # queue=1 uses epoch seconds; queue=3 uses scheduler-day numbers.
            intraday = collection.db.scalar(
                "select count() from cards where "
                "(queue = 1 and due < ?) or (queue = 3 and due <= ?)",
                int(end_ms / 1000),
                today_index,
            )
            learning_count = max(max(0, int(tree_learning)), max(0, int(intraday or 0)))
            future_learning = max(0, learning_count - max(0, int(tree_learning)))
            next_due_ms = 0
            if future_learning:
                now_ms = max(0, int(time.time() * 1000))
                next_due_seconds = collection.db.scalar(
                    "select min(due) from cards where queue = 1 and due > ? and due < ?",
                    int(now_ms / 1000),
                    int(end_ms / 1000),
                )
                if next_due_seconds:
                    next_due_ms = max(0, int(next_due_seconds) * 1000)
            normalized_card_ids = tuple(sorted({
                int(card_id)
                for card_id in committed_card_ids
                if isinstance(card_id, int)
                and not isinstance(card_id, bool)
                and int(card_id) > 0
            }))
            card_transitions: tuple[tuple[int, str], ...] = ()
            buried_sibling_card_ids: tuple[int, ...] = ()
            if normalized_card_ids:
                try:
                    (
                        card_transitions,
                        buried_sibling_card_ids,
                    ) = self._committed_card_transition_snapshot(
                        collection,
                        normalized_card_ids,
                        scheduler_day_index=today_index,
                        cutoff_seconds=int(end_ms / 1000),
                    )
                except Exception:
                    # Aggregate scheduler counts remain useful for progress,
                    # but a final reward must fail closed when the committed
                    # card identities cannot be classified.
                    logger.debug(
                        "Anki Garden: committed card transition classification "
                        "unavailable",
                        exc_info=True,
                    )
            return DueObligationStatus(
                review_count=max(0, int(review_count)),
                learning_count=learning_count,
                new_count=max(0, int(new_count)),
                future_learning_count=future_learning,
                next_learning_due_at_ms=next_due_ms,
                cutoff_at_ms=max(0, int(end_ms)),
                committed_card_ids=normalized_card_ids,
                card_transitions=card_transitions,
                buried_sibling_card_ids=buried_sibling_card_ids,
            )
        except Exception:
            logger.exception("Anki Garden: unable to evaluate all-due obligations")
            return DueObligationStatus(
                available=False,
                error=(
                    "Anki Garden could not verify today’s cards. "
                    "Normal Garden Growth is unaffected."
                ),
            )

    @classmethod
    def _due_tree_totals(cls, tree: Any) -> tuple[int, int, int]:
        if tree is None:
            return 0, 0, 0
        children = list(getattr(tree, "children", []) or [])
        try:
            deck_id = int(getattr(tree, "deck_id", getattr(tree, "did", 0)) or 0)
        except Exception:
            deck_id = 0
        if deck_id == 0 and children:
            totals = [cls._due_tree_totals(child) for child in children]
            return (
                sum(item[0] for item in totals),
                sum(item[1] for item in totals),
                sum(item[2] for item in totals),
            )
        new = max(
            0,
            int(getattr(tree, "new_count", getattr(tree, "new", 0)) or 0),
        )
        review = max(
            0,
            int(getattr(tree, "review_count", getattr(tree, "rev", 0)) or 0),
        )
        learning = max(
            0,
            int(getattr(tree, "learn_count", getattr(tree, "lrn", 0)) or 0),
        )
        # DeckTreeNode counts include descendants; do not sum children again.
        return new, learning, review
