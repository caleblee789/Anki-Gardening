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
from datetime import date, datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, Mapping

from .environment import DEFAULT_SCENERY_ID, DEFAULT_WEATHER_ID
from .models.state import (
    ActivePlantPeriod,
    GardenFindOutcome,
    GardenState,
    GROWTH_THRESHOLDS,
    MAX_PROCESSED_REVLOG_IDS,
    OnboardingProgress,
    OnboardingStep,
    Plant,
    PlantMemory,
    PLANT_MEMORY_KINDS,
    PLANT_SPECIES,
    STATE_VERSION,
)
from .reward_ledger import (
    AnswerConsumptionRecord,
    AnswerLineageRecord,
    FinalizedDayRecord,
    FindOutcomeRecord,
    LedgerCheckpoint,
    RevlogAliasRecord,
    RewardEventRecord,
    RewardLedger,
    RewardLedgerSchemaError,
    UNBOUNDED_STATE_AUTHORITY_KEYS,
)


logger = logging.getLogger(__name__)

PREVIOUS_STATE_VERSION = 10
MODERN_PREVIOUS_STATE_VERSIONS = frozenset({11, 12, 13, 14, 15, 16, 17, 18, 19, 20})
LEGACY_GROWTH_THRESHOLDS = [0, 80, 220, 480, 900, 1_400]
MAX_HISTORICAL_REVLOG_ENTRIES = 1_000_000
DEFAULT_HISTORY_PAGE_SIZE = 5_000
REWARD_DATABASE_FILENAME = "garden_state.sqlite3"
RECENT_FIND_CACHE_LIMIT = 32


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
) -> tuple[dict[int, str], dict[str, str]]:
    """Bind revlog rows to insertion-stable, undo-resistant answer lineages.

    Exact revlog IDs retain their prior lineage. If an old row disappeared and
    a new row for the same card and Anki day appeared, the orphaned lineage is
    reused (the normal undo/reanswer shape). A late synced row added alongside
    all existing rows receives a new monotonically allocated lineage, so it
    cannot shift or reroll any earlier answer.
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
    assigned_lineages = set(identities.values())
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
    decoration = equipped.get("decoration")
    payload["loadout"] = {
        "weather_id": payload.get(
            "selected_weather", equipped.get("weather", DEFAULT_WEATHER_ID)
        ),
        "scenery_id": payload.get(
            "selected_background", equipped.get("background", DEFAULT_SCENERY_ID)
        ),
        "decoration_id": None if decoration in (None, "", "none") else decoration,
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
        if key in {"pots", "backgrounds", "decorations", "weather"}
    }
    payload = {
        "version": STATE_VERSION,
        "garden_name": "My Garden",
        # Migrated gardens must not be interrupted by the new first-run name
        # prompt. Learners can still rename the garden from its header.
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
    return _materialize_unlocked_species(GardenState.from_dict(payload))


def migrate_modern_state(
    raw: Any,
    *,
    migrated_at: float | None = None,
    onboarding_version: Any = 0,
) -> GardenState:
    """Add current preservation boundaries to a schema 11-20 state.

    Those schemas already use the current progression model, so their payload
    can be validated by the current contract after changing only the schema
    version and marking the pre-existing garden as established.
    """
    if (
        not isinstance(raw, dict)
        or raw.get("version") not in MODERN_PREVIOUS_STATE_VERSIONS
    ):
        raise ValueError("only schema 11 through 20 can use the modern migration")
    payload = deepcopy(raw)
    source_version = int(payload.get("version", 0) or 0)
    if source_version == 20:
        payload["version"] = STATE_VERSION
        payload.setdefault("completed_purchase_requests", [])
        _migrate_reward_state_payload(payload)
        return GardenState.from_dict(payload)
    if source_version == 19:
        payload["version"] = STATE_VERSION
        payload.setdefault("completed_purchase_requests", [])
        _migrate_growth_accounting_payload(payload)
        _migrate_reward_state_payload(payload)
        return GardenState.from_dict(payload)
    if source_version in {17, 18}:
        # Schemas 17 and 18 already own every progression, onboarding, and
        # revlog field. Preserve their bounded purchase replay history while
        # collapsing only the duplicate environment mirrors.
        payload["version"] = STATE_VERSION
        payload.setdefault("completed_purchase_requests", [])
        _migrate_loadout_payload(payload)
        _migrate_growth_accounting_payload(payload)
        _migrate_reward_state_payload(payload)
        return GardenState.from_dict(payload)
    _add_legacy_fertilizer_activation_boundaries(
        payload,
        time.time() if migrated_at is None else migrated_at,
    )
    payload["version"] = STATE_VERSION
    payload.setdefault("eligible_reward_count", 0)
    payload.setdefault("ultra_pity_misses", 0)
    payload.setdefault("daily_environment_claims", {})
    payload.setdefault("environment_visibility", {"weather": True, "scenery": True})
    payload.setdefault("garden_name", "My Garden")
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
    return _materialize_unlocked_species(GardenState.from_dict(payload))


@dataclass(frozen=True)
class DueObligationStatus:
    review_count: int = 0
    learning_count: int = 0
    available: bool = True
    error: str = ""

    @property
    def remaining(self) -> int:
        return max(0, int(self.review_count)) + max(0, int(self.learning_count))

    @property
    def complete(self) -> bool:
        return self.available and not self.error and self.remaining == 0


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


class GardenStorage:
    _reward_ledger: RewardLedger | None = None
    _ledger_revision: int = 0

    def __init__(self, mw: Any, config: Any) -> None:
        self.mw = mw
        self.config = config
        self.addon_dir = Path(__file__).parent
        # Anki keeps user_files/ across add-on upgrades. All mutable state stays here.
        self.user_files_dir = self.addon_dir / "user_files"
        self.data_path = self.user_files_dir / "garden_state.json"
        self.database_path = self.user_files_dir / REWARD_DATABASE_FILENAME
        self.assets_root = self.addon_dir / "assets"
        self.metadata_dir = self.user_files_dir
        self.cache_dir = self.user_files_dir / "cache"
        self.asset_metadata = self.user_files_dir / "asset_metadata.json"
        self._reward_ledger: RewardLedger | None = None
        self._ledger_revision = 0
        self.state = self._load_authoritative_state()
        self._ensure_defaults()

    def _load_authoritative_state(self) -> GardenState:
        """Load the SQLite authority, or atomically import the legacy JSON."""

        self.user_files_dir.mkdir(parents=True, exist_ok=True)
        if self.database_path.exists():
            ledger: RewardLedger | None = None
            try:
                ledger = RewardLedger(self.database_path)
                snapshot = ledger.load_state_snapshot()
                if snapshot is None or snapshot.schema_version != STATE_VERSION:
                    raise RewardLedgerSchemaError(
                        "The Garden state snapshot uses an unsupported schema."
                    )
                self._reward_ledger = ledger
                self._ledger_revision = snapshot.revision
                state = _materialize_unlocked_species(
                    GardenState.from_dict(dict(snapshot.payload))
                )
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
        payload = state.to_dict()
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

    def stage_reward_event(self, event_key: str) -> None:
        if self._reward_ledger is None:
            if event_key not in self.state.applied_reward_event_keys:
                self.state.applied_reward_event_keys.append(event_key)
            return
        if not self._reward_ledger.reward_applied(event_key):
            self._reward_ledger.stage_reward_event(RewardEventRecord(event_key))

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
                self.state.garden_find_daily_counts[outcome.scheduler_day] = min(
                    3, finds_today + 1
                )
                reward_counts = (
                    self.state.garden_find_reward_daily_counts.setdefault(
                        outcome.scheduler_day, {}
                    )
                )
                reward_counts[outcome.reward_id] = min(
                    3,
                    max(0, int(reward_counts.get(outcome.reward_id, 0))) + 1,
                )
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
                    logger.warning(
                        "Anki Garden: unsupported schema %s preserved at %s; starting schema %s",
                        version, backup, STATE_VERSION,
                    )
                    return GardenState()
                return _materialize_unlocked_species(GardenState.from_dict(raw))
        except StatePreservationError:
            raise
        except Exception:
            logger.exception("Anki Garden: saved state is unreadable; preserving it and starting fresh")
            try:
                backup = self.data_path.with_suffix(".invalid.json")
                _required_backup(self.data_path, backup)
            except Exception as error:
                logger.exception("Anki Garden: could not preserve invalid state")
                raise StatePreservationError(
                    "Anki Garden could not preserve the saved garden; startup was stopped before any overwrite."
                ) from error
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

    def save(self) -> None:
        if self._reward_ledger is None:
            self._atomic_write_json(self.data_path, self.state.to_dict())
            return
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
            state = GardenState.from_dict(dict(snapshot.payload))
            state.pending_reanswer_lineages = reanswer_hints
            return state
        raw = json.loads(candidate.read_text("utf-8"))
        if not isinstance(raw, dict) or int(raw.get("version", -1)) != STATE_VERSION:
            raise StatePreservationError("That development backup uses an unsupported schema.")
        return GardenState.from_dict(raw)

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
            self._ledger_revision = snapshot.revision
            restored = GardenState.from_dict(dict(snapshot.payload))
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

    def due_obligations(self) -> DueObligationStatus:
        """Return the live collection-wide all-due obligation set.

        Unseen new cards are excluded. Review counts come from Anki's deck tree,
        which applies active deck limits and includes filtered decks. Learning and
        relearning cards remain obligations through the scheduler-day cutoff even
        when an intraday step is not available at this exact second. Negative queue
        values (suspended/buried) are deliberately excluded.
        """
        collection = getattr(self.mw, "col", None)
        if collection is None or getattr(collection, "db", None) is None or getattr(collection, "sched", None) is None:
            return DueObligationStatus(available=False, error="Open an Anki collection to check due reviews.")
        try:
            tree = collection.sched.deck_due_tree()
            review_count, tree_learning = self._due_tree_totals(tree)
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
            return DueObligationStatus(max(0, int(review_count)), learning_count)
        except Exception:
            logger.exception("Anki Garden: unable to evaluate all-due obligations")
            return DueObligationStatus(available=False, error="Anki could not evaluate all due reviews.")

    @classmethod
    def _due_tree_totals(cls, tree: Any) -> tuple[int, int]:
        if tree is None:
            return 0, 0
        children = list(getattr(tree, "children", []) or [])
        try:
            deck_id = int(getattr(tree, "deck_id", getattr(tree, "did", 0)) or 0)
        except Exception:
            deck_id = 0
        if deck_id == 0 and children:
            totals = [cls._due_tree_totals(child) for child in children]
            return sum(item[0] for item in totals), sum(item[1] for item in totals)
        review = max(0, int(getattr(tree, "review_count", getattr(tree, "rev", 0)) or 0))
        learning = max(0, int(getattr(tree, "learn_count", getattr(tree, "lrn", 0)) or 0))
        # DeckTreeNode counts include descendants; do not sum children again.
        return review, learning
