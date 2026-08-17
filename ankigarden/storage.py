from __future__ import annotations

import json
import logging
import math
import shutil
import time
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict

from .environment import DEFAULT_SCENERY_ID, DEFAULT_WEATHER_ID
from .models.state import (
    ActivePlantPeriod,
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


logger = logging.getLogger(__name__)

PREVIOUS_STATE_VERSION = 10
MODERN_PREVIOUS_STATE_VERSIONS = frozenset({11, 12, 13, 14, 15, 16, 17, 18, 19})
LEGACY_GROWTH_THRESHOLDS = [0, 80, 220, 480, 900, 1_400]


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


def _required_backup(source: Path, destination: Path) -> None:
    try:
        shutil.copy2(source, destination)
    except Exception as error:
        raise StatePreservationError(
            "Anki Garden could not preserve the saved garden; startup was stopped before any overwrite."
        ) from error


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
    return _materialize_unlocked_species(GardenState.from_dict(payload))


def migrate_modern_state(
    raw: Any,
    *,
    migrated_at: float | None = None,
    onboarding_version: Any = 0,
) -> GardenState:
    """Add current preservation boundaries to a schema 11-19 state.

    Those schemas already use the current progression model, so their payload
    can be validated by the current contract after changing only the schema
    version and marking the pre-existing garden as established.
    """
    if (
        not isinstance(raw, dict)
        or raw.get("version") not in MODERN_PREVIOUS_STATE_VERSIONS
    ):
        raise ValueError("only schema 11 through 19 can use the modern migration")
    payload = deepcopy(raw)
    source_version = int(payload.get("version", 0) or 0)
    if source_version == 19:
        payload["version"] = STATE_VERSION
        payload.setdefault("completed_purchase_requests", [])
        _migrate_growth_accounting_payload(payload)
        return GardenState.from_dict(payload)
    if source_version in {17, 18}:
        # Schemas 17 and 18 already own every progression, onboarding, and
        # revlog field. Preserve their bounded purchase replay history while
        # collapsing only the duplicate environment mirrors.
        payload["version"] = STATE_VERSION
        payload.setdefault("completed_purchase_requests", [])
        _migrate_loadout_payload(payload)
        _migrate_growth_accounting_payload(payload)
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


class GardenStorage:
    def __init__(self, mw: Any, config: Any) -> None:
        self.mw = mw
        self.config = config
        self.addon_dir = Path(__file__).parent
        # Anki keeps user_files/ across add-on upgrades. All mutable state stays here.
        self.user_files_dir = self.addon_dir / "user_files"
        self.data_path = self.user_files_dir / "garden_state.json"
        self.assets_root = self.addon_dir / "assets"
        self.metadata_dir = self.user_files_dir
        self.cache_dir = self.user_files_dir / "cache"
        self.asset_metadata = self.user_files_dir / "asset_metadata.json"
        self.state = self._load()
        self._ensure_defaults()

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
        self._atomic_write_json(self.data_path, self.state.to_dict())

    def create_development_backup(self) -> Path:
        """Create a one-off recovery point before a development seed."""

        self.save()
        backup_dir = self.user_files_dir / "development_backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        destination = backup_dir / f"garden-state-{stamp}-{time.time_ns()}.json"
        _required_backup(self.data_path, destination)
        return destination

    def load_development_backup(self, path: Path) -> GardenState:
        candidate = Path(path).resolve()
        backup_root = (self.user_files_dir / "development_backups").resolve()
        if candidate.parent != backup_root or not candidate.is_file():
            raise StatePreservationError("That development backup is not available.")
        raw = json.loads(candidate.read_text("utf-8"))
        if not isinstance(raw, dict) or int(raw.get("version", -1)) != STATE_VERSION:
            raise StatePreservationError("That development backup uses an unsupported schema.")
        return GardenState.from_dict(raw)

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
            today_periods = [
                period for period in self.state.active_plant_periods
                if period.day == scheduler_day
            ]
            latest = max(
                today_periods,
                key=lambda period: period.started_at_ms,
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
