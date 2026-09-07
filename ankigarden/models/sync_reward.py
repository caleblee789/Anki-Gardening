from __future__ import annotations

from ..presentation import plant_stage_title, plant_stage_event

"""Bounded presentation contract for rewards introduced by collection sync."""

from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any, Iterable, Mapping
import uuid

from ..growth import GROWTH_STAGES, stage_presentation


MAX_SYNC_SUMMARY_ROWS = 256
MAX_SYNC_SUMMARY_DAYS = 366
MAX_SYNC_SUMMARY_TEXT = 240
SYNC_REWARD_MODEL_VERSION = 4


def _text(value: Any, *, limit: int = MAX_SYNC_SUMMARY_TEXT) -> str:
    return str(value or "").strip()[:limit]


def _nonnegative(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _day(value: Any) -> str:
    text = _text(value, limit=10)
    try:
        return date.fromisoformat(text).isoformat()
    except (TypeError, ValueError):
        return ""


def _records(value: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    result: list[dict[str, Any]] = []
    for raw in value[:MAX_SYNC_SUMMARY_ROWS]:
        if not isinstance(raw, Mapping):
            continue
        clean: dict[str, Any] = {}
        for raw_key, raw_value in raw.items():
            key = _text(raw_key, limit=64)
            if not key:
                continue
            if isinstance(raw_value, bool):
                clean[key] = raw_value
            elif isinstance(raw_value, int) and not isinstance(raw_value, bool):
                clean[key] = max(-1_000_000_000, min(1_000_000_000, raw_value))
            elif raw_value is None:
                clean[key] = None
            else:
                clean[key] = _text(raw_value)
        result.append(clean)
    return tuple(result)


@dataclass(frozen=True)
class SyncProjectGrowthAllocation:
    """Exact project Growth committed by the production engine during sync."""

    target_type: str
    target_id: str
    units: int

    def __post_init__(self) -> None:
        target_type = _text(self.target_type, limit=32).casefold()
        target_id = _text(self.target_id, limit=96)
        units = _nonnegative(self.units)
        if target_type not in {"landmark", "mastery", "legacy"}:
            raise ValueError("Unknown Growth project target type")
        if not target_id:
            raise ValueError("Growth project target id is required")
        if units <= 0:
            raise ValueError("Growth project allocation must be positive")
        object.__setattr__(self, "target_type", target_type)
        object.__setattr__(self, "target_id", target_id)
        object.__setattr__(self, "units", units)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_type": self.target_type,
            "target_id": self.target_id,
            "units": self.units,
        }

    @classmethod
    def from_dict(cls, raw: Any) -> SyncProjectGrowthAllocation | None:
        if not isinstance(raw, Mapping):
            return None
        try:
            return cls(
                target_type=_text(raw.get("target_type"), limit=32),
                target_id=_text(raw.get("target_id"), limit=96),
                units=_nonnegative(raw.get("units")),
            )
        except ValueError:
            return None


def _merge_project_allocations(
    *groups: Iterable[SyncProjectGrowthAllocation],
) -> tuple[SyncProjectGrowthAllocation, ...]:
    totals: dict[tuple[str, str], int] = {}
    for group in groups:
        for allocation in group:
            key = (allocation.target_type, allocation.target_id)
            totals[key] = totals.get(key, 0) + allocation.units
    return tuple(
        SyncProjectGrowthAllocation(target_type, target_id, units)
        for (target_type, target_id), units in tuple(totals.items())[
            :MAX_SYNC_SUMMARY_ROWS
        ]
    )


@dataclass(frozen=True)
class SyncPlantCheckpoint:
    event_id: str
    percent: int
    stage_name: str
    display_text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": _text(self.event_id, limit=96),
            "percent": max(0, min(100, int(self.percent))),
            "stage_name": _text(self.stage_name),
            "display_text": _text(self.display_text),
        }

    @classmethod
    def from_dict(cls, raw: Any) -> SyncPlantCheckpoint | None:
        if not isinstance(raw, Mapping):
            return None
        event_id = _text(raw.get("event_id"), limit=96)
        if not event_id:
            return None
        return cls(
            event_id=event_id,
            percent=max(0, min(100, _nonnegative(raw.get("percent")))),
            stage_name=_text(raw.get("stage_name")),
            display_text=_text(raw.get("display_text")),
        )


@dataclass(frozen=True)
class SyncPlantMilestone:
    """The single highest-priority milestone for one synced plant result."""

    kind: str
    priority: int
    event_id: str
    display_text: str
    checkpoint_percent: int = 0


def _stage_id(value: Any) -> str:
    normalized = str(value or "").replace("_", " ").strip().casefold()
    return "rare" if normalized == "full bloom" else normalized


def _stage_display_name(value: Any) -> str:
    resolved = stage_presentation(value)
    return (
        resolved.display_name
        if resolved is not None
        else _text(value, limit=64).replace("_", " ").title()
    )


def _stage_rank(value: Any) -> int:
    try:
        return GROWTH_STAGES.index(_stage_id(value))
    except ValueError:
        return -1


@dataclass(frozen=True)
class SyncPlantResult:
    plant_id: str
    display_name: str
    species: str = ""
    artwork_asset: str = ""
    growth_delta_units: int = 0
    stage_before: str = ""
    stage_after: str = ""
    stage_progress_before: int = 0
    stage_progress_after: int = 0
    next_stage: str = ""
    fully_grown: bool = False
    active: bool = False
    checkpoints: tuple[SyncPlantCheckpoint, ...] = ()
    stage_event_id: str = ""
    stage_event_text: str = ""
    full_bloom: bool = False
    transition_source: str = ""

    growth_after_units: int | None = None
    progression_coins: int = 0

    @property
    def stage_changed(self) -> bool:
        before = _stage_id(self.stage_before)
        after = _stage_id(self.stage_after)
        return bool(
            self.stage_event_id
            or (before and after and before != after)
        )

    @property
    def reached_full_bloom(self) -> bool:
        return bool(
            self.full_bloom
            or (self.fully_grown and _stage_id(self.stage_after) == "rare")
        )

    @property
    def canonical_checkpoints(self) -> tuple[SyncPlantCheckpoint, ...]:
        """Keep only the highest reached checkpoint in the current stage.

        Full Bloom and stage changes supersede checkpoint copy. Checkpoints
        aimed at a prior stage or beyond the committed progress are stale.
        """

        if self.reached_full_bloom or self.stage_changed:
            return ()
        expected_stage = _stage_id(self.next_stage)
        after_rank = _stage_rank(self.stage_after)
        candidates: dict[str, SyncPlantCheckpoint] = {}
        for checkpoint in self.checkpoints:
            target_stage = _stage_id(checkpoint.stage_name)
            target_rank = _stage_rank(target_stage)
            if expected_stage and target_stage != expected_stage:
                continue
            if (
                not expected_stage
                and self.stage_before
                and after_rank >= 0
                and 0 <= target_rank <= after_rank
            ):
                continue
            if checkpoint.percent > max(0, int(self.stage_progress_after)):
                continue
            candidates[checkpoint.event_id] = checkpoint
        if not candidates:
            return ()
        highest = sorted(
            candidates.values(),
            key=lambda item: (-int(item.percent), item.event_id),
        )[0]
        return (highest,)

    @property
    def primary_milestone(self) -> SyncPlantMilestone:
        """Resolve Full Bloom, stage, checkpoint, then ordinary Growth."""

        if self.reached_full_bloom:
            return SyncPlantMilestone(
                "full_bloom",
                0,
                self.stage_event_id or f"plant:{self.plant_id}:full_bloom",
                plant_stage_event(self.species, "rare"),
            )
        if self.stage_changed:
            return SyncPlantMilestone(
                "stage_change",
                1,
                self.stage_event_id or (
                    f"plant:{self.plant_id}:stage:{_stage_id(self.stage_after)}"
                ),
                plant_stage_event(self.species, self.stage_after),
            )
        checkpoints = self.canonical_checkpoints
        if checkpoints:
            checkpoint = checkpoints[0]
            return SyncPlantMilestone(
                "checkpoint",
                2,
                checkpoint.event_id,
                plant_stage_event(self.species, checkpoint.stage_name, checkpoint_percent=checkpoint.percent),
                checkpoint.percent,
            )
        return SyncPlantMilestone(
            "growth",
            3,
            f"plant:{self.plant_id}:growth",
            "Growth added",
        )

    def canonicalized(self) -> "SyncPlantResult":
        checkpoints = self.canonical_checkpoints
        full_bloom = self.reached_full_bloom
        return (
            self
            if checkpoints == self.checkpoints and full_bloom == self.full_bloom
            else replace(
                self,
                checkpoints=checkpoints,
                full_bloom=full_bloom,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "plant_id": _text(self.plant_id, limit=96),
            "display_name": plant_stage_title(self.species, self.stage_after),
            "species": _text(self.species, limit=96),
            "artwork_asset": _text(self.artwork_asset),
            "growth_delta_units": _nonnegative(self.growth_delta_units),
            "stage_before": _text(self.stage_before, limit=64),
            "stage_after": _text(self.stage_after, limit=64),
            "stage_progress_before": max(0, min(100, _nonnegative(self.stage_progress_before))),
            "stage_progress_after": max(0, min(100, _nonnegative(self.stage_progress_after))),
            "growth_after_units": _nonnegative(self.growth_after_units) if self.growth_after_units is not None else None,
            "progression_coins": _nonnegative(self.progression_coins),
            "next_stage": _text(self.next_stage, limit=64),
            "fully_grown": bool(self.fully_grown),
            "active": bool(self.active),
            "checkpoints": [
                checkpoint.to_dict()
                for checkpoint in self.canonical_checkpoints
            ],
            "stage_event_id": _text(self.stage_event_id, limit=96),
            "stage_event_text": _text(self.stage_event_text),
            "transition_source": _text(self.transition_source, limit=64),
            "stage_transition_source": _text(
                self.transition_source, limit=64
            ),
            "full_bloom": self.reached_full_bloom,
        }

    @classmethod
    def from_dict(cls, raw: Any) -> SyncPlantResult | None:
        if not isinstance(raw, Mapping):
            return None
        plant_id = _text(raw.get("plant_id"), limit=96)
        if not plant_id:
            return None
        raw_checkpoints = raw.get("checkpoints")
        checkpoints = tuple(
            checkpoint
            for value in (
                raw_checkpoints
                if isinstance(raw_checkpoints, (list, tuple))
                else ()
            )[:MAX_SYNC_SUMMARY_ROWS]
            if (checkpoint := SyncPlantCheckpoint.from_dict(value)) is not None
        )
        return cls(
            plant_id=plant_id,
            display_name=_text(
                raw.get("display_name") or raw.get("plant_name") or "Plant"
            ),
            species=_text(raw.get("species"), limit=96),
            artwork_asset=_text(raw.get("artwork_asset") or raw.get("plant_image")),
            growth_delta_units=_nonnegative(raw.get("growth_delta_units")),
            stage_before=_text(raw.get("stage_before"), limit=64),
            stage_after=_text(raw.get("stage_after"), limit=64),
            stage_progress_before=max(
                0, min(100, _nonnegative(raw.get("stage_progress_before")))
            ),
            stage_progress_after=max(
                0, min(100, _nonnegative(raw.get("stage_progress_after")))
            ),
            growth_after_units=_nonnegative(raw.get("growth_after_units")) if raw.get("growth_after_units") is not None else None,
            progression_coins=_nonnegative(raw.get("progression_coins")),
            next_stage=_text(raw.get("next_stage"), limit=64),
            fully_grown=bool(raw.get("fully_grown", False)),
            active=bool(raw.get("active", False)),
            checkpoints=checkpoints,
            stage_event_id=_text(raw.get("stage_event_id"), limit=96),
            stage_event_text=_text(raw.get("stage_event_text")),
            transition_source=_text(
                raw.get("transition_source")
                or raw.get("stage_transition_source"),
                limit=64,
            ),
            full_bloom=bool(raw.get("full_bloom", False)),
        ).canonicalized()


def prioritized_sync_plant_results(
    results: Iterable[SyncPlantResult],
) -> tuple[SyncPlantResult, ...]:
    """Return a deterministic cross-plant milestone presentation order."""

    canonical = tuple(result.canonicalized() for result in results)
    return tuple(sorted(
        canonical,
        key=lambda result: (
            result.primary_milestone.priority,
            0 if result.active else 1,
            result.display_name.casefold(),
            result.plant_id,
        ),
    ))


@dataclass(frozen=True)
class SyncRewardSummary:
    batch_id: str
    anki_days: tuple[str, ...]
    eligible_answer_count: int
    growth_total_units: int
    model_version: int = field(default=SYNC_REWARD_MODEL_VERSION, compare=False)
    plant_results: tuple[SyncPlantResult, ...] = field(default=(), compare=False)
    plant_growth: tuple[dict[str, Any], ...] = ()
    shared_growth_delta_units: int = 0
    stored_growth_delta_units: int = 0
    garden_coin_delta: int = 0
    finds: tuple[dict[str, Any], ...] = ()
    environment_discoveries: tuple[dict[str, Any], ...] = ()
    progression_events: tuple[dict[str, Any], ...] = ()
    all_clear_earned: bool = False
    all_clear_coin_reward: int = 0
    fertilizer_cards_remaining: int = 0
    # Compatibility-only projection for pre-2.2.0 retained receipts. New
    # summaries always commit card-counted Fertilizer value above.
    fertilizer_remaining_seconds: int = 0
    fertilizer_state_changed: bool = False
    fertilizer_item_id: str = ""
    fertilizer_art_asset: str = ""
    booster_cards_remaining: int = 0
    booster_state_changed: bool = False
    booster_item_id: str = ""
    booster_art_asset: str = ""
    source_batch_ids: tuple[str, ...] = ()
    additional_answer_count: int = 0
    # Appended for positional compatibility with retained v1/v2 callers.
    # Older persisted receipts omit this field and load it as zero.
    landmark_growth_delta_units: int = 0
    # Schema-27 project funding is emitted from committed engine results. The
    # Landmark scalar remains above as a retained compatibility field.
    mastery_growth_delta_units: int = 0
    legacy_growth_delta_units: int = 0
    project_allocations: tuple[SyncProjectGrowthAllocation, ...] = ()

    @property
    def first_anki_day(self) -> str:
        return self.anki_days[0] if self.anki_days else ""

    @property
    def last_anki_day(self) -> str:
        return self.anki_days[-1] if self.anki_days else ""

    @property
    def meaningful(self) -> bool:
        return bool(
            self.eligible_answer_count > 0
            and (
                self.growth_total_units > 0
                or self.landmark_growth_delta_units > 0
                or self.mastery_growth_delta_units > 0
                or self.legacy_growth_delta_units > 0
                or self.project_allocations
                or self.garden_coin_delta > 0
                or self.finds
                or self.environment_discoveries
                or self.grouped_plant_results
                or self.all_clear_earned
                or self.fertilizer_state_changed
                or self.booster_state_changed
            )
        )

    @property
    def subtitle(self) -> str:
        if self.eligible_answer_count == 1:
            return "Reward from 1 card answer on another device."
        return (
            f"Rewards from {self.eligible_answer_count:,} card answers "
            "on another device."
        )

    @property
    def grouped_plant_results(self) -> tuple[SyncPlantResult, ...]:
        """Return canonical plant-grouped presentation data for retained receipts."""

        results = self.plant_results or _group_legacy_plant_results(
            self.plant_growth,
            self.progression_events,
        )
        return prioritized_sync_plant_results(results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_version": SYNC_REWARD_MODEL_VERSION,
            "batch_id": self.batch_id,
            "anki_days": list(self.anki_days),
            "first_anki_day": self.first_anki_day,
            "last_anki_day": self.last_anki_day,
            "eligible_answer_count": self.eligible_answer_count,
            "growth_total_units": self.growth_total_units,
            "plant_results": [
                result.to_dict() for result in self.grouped_plant_results
            ],
            "plant_growth": [dict(item) for item in self.plant_growth],
            "shared_growth_delta_units": self.shared_growth_delta_units,
            "stored_growth_delta_units": self.stored_growth_delta_units,
            "landmark_growth_delta_units": self.landmark_growth_delta_units,
            "mastery_growth_delta_units": self.mastery_growth_delta_units,
            "legacy_growth_delta_units": self.legacy_growth_delta_units,
            "project_allocations": [
                allocation.to_dict() for allocation in self.project_allocations
            ],
            "garden_coin_delta": self.garden_coin_delta,
            "finds": [dict(item) for item in self.finds],
            "environment_discoveries": [
                dict(item) for item in self.environment_discoveries
            ],
            "progression_events": [dict(item) for item in self.progression_events],
            "all_clear_earned": self.all_clear_earned,
            "all_clear_coin_reward": self.all_clear_coin_reward,
            "fertilizer_cards_remaining": self.fertilizer_cards_remaining,
            "fertilizer_remaining_seconds": self.fertilizer_remaining_seconds,
            "fertilizer_state_changed": self.fertilizer_state_changed,
            "fertilizer_item_id": self.fertilizer_item_id,
            "fertilizer_art_asset": self.fertilizer_art_asset,
            "booster_cards_remaining": self.booster_cards_remaining,
            "booster_state_changed": self.booster_state_changed,
            "booster_item_id": self.booster_item_id,
            "booster_art_asset": self.booster_art_asset,
            "source_batch_ids": list(self.source_batch_ids),
            "additional_answer_count": self.additional_answer_count,
        }

    @classmethod
    def from_dict(cls, raw: Any) -> SyncRewardSummary | None:
        if not isinstance(raw, Mapping):
            return None
        batch_id = _text(raw.get("batch_id"), limit=96)
        if not batch_id:
            return None
        raw_days = raw.get("anki_days")
        days = sorted({
            normalized
            for value in (raw_days if isinstance(raw_days, (list, tuple)) else ())
            if (normalized := _day(value))
        })[:MAX_SYNC_SUMMARY_DAYS]
        answer_count = _nonnegative(raw.get("eligible_answer_count"))
        if answer_count <= 0:
            return None
        source_ids = tuple(dict.fromkeys(
            value
            for raw_value in (
                raw.get("source_batch_ids")
                if isinstance(raw.get("source_batch_ids"), (list, tuple))
                else ()
            )
            if (value := _text(raw_value, limit=96))
        ))[:MAX_SYNC_SUMMARY_ROWS]
        raw_plant_results = raw.get("plant_results")
        plant_results = tuple(
            result
            for value in (
                raw_plant_results
                if isinstance(raw_plant_results, (list, tuple))
                else ()
            )[:MAX_SYNC_SUMMARY_ROWS]
            if (result := SyncPlantResult.from_dict(value)) is not None
        )
        raw_project_allocations = raw.get("project_allocations")
        project_allocations = tuple(
            allocation
            for value in (
                raw_project_allocations
                if isinstance(raw_project_allocations, (list, tuple))
                else ()
            )[:MAX_SYNC_SUMMARY_ROWS]
            if (
                allocation := SyncProjectGrowthAllocation.from_dict(value)
            ) is not None
        )
        return cls(
            batch_id=batch_id,
            anki_days=tuple(days),
            eligible_answer_count=answer_count,
            growth_total_units=_nonnegative(raw.get("growth_total_units")),
            model_version=SYNC_REWARD_MODEL_VERSION,
            plant_results=plant_results,
            plant_growth=_records(raw.get("plant_growth")),
            shared_growth_delta_units=_nonnegative(
                raw.get("shared_growth_delta_units")
            ),
            stored_growth_delta_units=_nonnegative(
                raw.get("stored_growth_delta_units")
            ),
            landmark_growth_delta_units=_nonnegative(
                raw.get("landmark_growth_delta_units")
            ),
            mastery_growth_delta_units=_nonnegative(
                raw.get("mastery_growth_delta_units")
            ),
            legacy_growth_delta_units=_nonnegative(
                raw.get("legacy_growth_delta_units")
            ),
            project_allocations=project_allocations,
            garden_coin_delta=_nonnegative(raw.get("garden_coin_delta")),
            finds=_records(raw.get("finds")),
            environment_discoveries=_records(raw.get("environment_discoveries")),
            progression_events=_records(raw.get("progression_events")),
            all_clear_earned=bool(raw.get("all_clear_earned", False)),
            all_clear_coin_reward=_nonnegative(raw.get("all_clear_coin_reward")),
            fertilizer_cards_remaining=_nonnegative(
                raw.get("fertilizer_cards_remaining")
            ),
            fertilizer_remaining_seconds=_nonnegative(
                raw.get("fertilizer_remaining_seconds")
            ),
            fertilizer_state_changed=bool(
                raw.get("fertilizer_state_changed", False)
            ),
            fertilizer_item_id=_text(raw.get("fertilizer_item_id"), limit=96),
            fertilizer_art_asset=_text(raw.get("fertilizer_art_asset")),
            booster_cards_remaining=_nonnegative(raw.get("booster_cards_remaining")),
            booster_state_changed=bool(raw.get("booster_state_changed", False)),
            booster_item_id=_text(raw.get("booster_item_id"), limit=96),
            booster_art_asset=_text(raw.get("booster_art_asset")),
            source_batch_ids=source_ids or (batch_id,),
            additional_answer_count=_nonnegative(raw.get("additional_answer_count")),
        )

    def merge(self, newer: SyncRewardSummary) -> SyncRewardSummary:
        """Merge consecutive receipts while retaining one presentation identity."""

        if not isinstance(newer, SyncRewardSummary):
            raise TypeError("newer must be a SyncRewardSummary")
        plants = _merge_growth_rows(self.plant_growth, newer.plant_growth)
        plant_results = _merge_plant_results(
            self.grouped_plant_results,
            newer.grouped_plant_results,
        )
        finds = _merge_quantity_rows(self.finds, newer.finds, "reward_id")
        environments = _unique_rows(
            (*self.environment_discoveries, *newer.environment_discoveries),
            "environment_id",
        )
        events = _unique_rows(
            (*self.progression_events, *newer.progression_events),
            "event_id",
        )
        added = newer.eligible_answer_count
        return replace(
            self,
            anki_days=tuple(sorted(set(self.anki_days).union(newer.anki_days))),
            eligible_answer_count=self.eligible_answer_count + added,
            growth_total_units=self.growth_total_units + newer.growth_total_units,
            model_version=SYNC_REWARD_MODEL_VERSION,
            plant_results=plant_results,
            plant_growth=plants,
            shared_growth_delta_units=(
                self.shared_growth_delta_units + newer.shared_growth_delta_units
            ),
            stored_growth_delta_units=(
                self.stored_growth_delta_units + newer.stored_growth_delta_units
            ),
            landmark_growth_delta_units=(
                self.landmark_growth_delta_units
                + newer.landmark_growth_delta_units
            ),
            mastery_growth_delta_units=(
                self.mastery_growth_delta_units
                + newer.mastery_growth_delta_units
            ),
            legacy_growth_delta_units=(
                self.legacy_growth_delta_units
                + newer.legacy_growth_delta_units
            ),
            project_allocations=_merge_project_allocations(
                self.project_allocations,
                newer.project_allocations,
            ),
            garden_coin_delta=self.garden_coin_delta + newer.garden_coin_delta,
            finds=finds,
            environment_discoveries=environments,
            progression_events=events,
            all_clear_earned=self.all_clear_earned or newer.all_clear_earned,
            all_clear_coin_reward=(
                self.all_clear_coin_reward + newer.all_clear_coin_reward
            ),
            fertilizer_cards_remaining=(
                newer.fertilizer_cards_remaining
                if newer.fertilizer_state_changed
                else self.fertilizer_cards_remaining
            ),
            fertilizer_remaining_seconds=(
                newer.fertilizer_remaining_seconds
                if newer.fertilizer_state_changed
                else self.fertilizer_remaining_seconds
            ),
            fertilizer_state_changed=(
                self.fertilizer_state_changed or newer.fertilizer_state_changed
            ),
            fertilizer_item_id=(
                newer.fertilizer_item_id
                if newer.fertilizer_state_changed or not self.fertilizer_item_id
                else self.fertilizer_item_id
            ),
            fertilizer_art_asset=(
                newer.fertilizer_art_asset
                if newer.fertilizer_state_changed or not self.fertilizer_art_asset
                else self.fertilizer_art_asset
            ),
            booster_cards_remaining=(
                newer.booster_cards_remaining
                if newer.booster_state_changed
                else self.booster_cards_remaining
            ),
            booster_state_changed=(
                self.booster_state_changed or newer.booster_state_changed
            ),
            booster_item_id=(
                newer.booster_item_id
                if newer.booster_state_changed or not self.booster_item_id
                else self.booster_item_id
            ),
            booster_art_asset=(
                newer.booster_art_asset
                if newer.booster_state_changed or not self.booster_art_asset
                else self.booster_art_asset
            ),
            source_batch_ids=tuple(dict.fromkeys((
                *self.source_batch_ids,
                *newer.source_batch_ids,
            )))[:MAX_SYNC_SUMMARY_ROWS],
            additional_answer_count=added,
        )

    @classmethod
    def empty_batch(cls, *, batch_id: str | None = None) -> SyncRewardSummary:
        return cls(
            batch_id=_text(batch_id, limit=96) or uuid.uuid4().hex,
            anki_days=(),
            eligible_answer_count=0,
            growth_total_units=0,
        )


def _event_plant_name(row: Mapping[str, Any]) -> str:
    explicit = _text(row.get("plant_name") or row.get("display_name"))
    if explicit:
        return explicit
    text = _text(row.get("display_text"))
    for marker in (" advanced ", " reached "):
        if marker in text:
            return text.partition(marker)[0].strip() or "Plant"
    return "Plant"


def _group_legacy_plant_results(
    plant_growth: Iterable[Mapping[str, Any]],
    progression_events: Iterable[Mapping[str, Any]],
) -> tuple[SyncPlantResult, ...]:
    rows: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for raw in plant_growth:
        item = dict(raw)
        plant_id = _text(item.get("plant_id"), limit=96)
        if not plant_id:
            continue
        order.append(plant_id)
        rows[plant_id] = {
            "plant_id": plant_id,
            "display_name": _text(item.get("plant_name") or "Plant"),
            "species": _text(item.get("species"), limit=96),
            "artwork_asset": _text(item.get("plant_image")),
            "growth_delta_units": _nonnegative(item.get("growth_delta_units")),
            "stage_before": _text(item.get("stage_before"), limit=64),
            "stage_after": _text(item.get("stage_after"), limit=64),
            "stage_progress_before": max(
                0, min(100, _nonnegative(item.get("stage_progress_before")))
            ),
            "stage_progress_after": max(
                0, min(100, _nonnegative(item.get("stage_progress_after")))
            ),
            "growth_after_units": _nonnegative(item.get("growth_after_units")) if item.get("growth_after_units") is not None else None,
            "progression_coins": _nonnegative(item.get("progression_coins")),
            "next_stage": _text(item.get("next_stage"), limit=64),
            "fully_grown": bool(item.get("fully_grown", False)),
            "active": bool(item.get("active", False)),
            "checkpoints": [],
            "stage_event_id": "",
            "stage_event_text": "",
            "full_bloom": False,
            "transition_source": "",
        }
    for raw in progression_events:
        item = dict(raw)
        plant_id = _text(item.get("plant_id"), limit=96)
        if not plant_id:
            continue
        if plant_id not in rows:
            order.append(plant_id)
            rows[plant_id] = {
                "plant_id": plant_id,
                "display_name": _event_plant_name(item),
                "species": _text(item.get("species"), limit=96),
                "artwork_asset": _text(item.get("plant_image")),
                "growth_delta_units": 0,
                "stage_before": "",
                "stage_after": _text(item.get("stage_name"), limit=64),
                "stage_progress_before": 0,
                "stage_progress_after": 100,
                "next_stage": "",
                "fully_grown": False,
                "active": False,
                "checkpoints": [],
                "stage_event_id": "",
                "stage_event_text": "",
                "full_bloom": False,
                "transition_source": "",
            }
        target = rows[plant_id]
        event_type = _text(item.get("event_type"), limit=32).casefold()
        if event_type == "checkpoint":
            percent_text = _text(item.get("checkpoint_name")).partition("%")[0]
            try:
                percent = max(0, min(100, int(percent_text)))
            except (TypeError, ValueError):
                percent = 0
            checkpoint = SyncPlantCheckpoint(
                event_id=_text(item.get("event_id"), limit=96),
                percent=percent,
                stage_name=_text(item.get("stage_name")),
                display_text=(
                    f"{percent}% toward {_text(item.get('stage_name'))} reached"
                    if percent and _text(item.get("stage_name"))
                    else _text(item.get("display_text"))
                ),
            )
            target["checkpoints"].append(checkpoint)
        else:
            target["stage_event_id"] = _text(item.get("event_id"), limit=96)
            target["stage_event_text"] = _text(item.get("display_text"))
            target["transition_source"] = _text(
                item.get("transition_source")
                or item.get("stage_transition_source"),
                limit=64,
            )
            if event_type == "full_bloom":
                target["full_bloom"] = True
                target["fully_grown"] = True
                target["stage_after"] = "rare"
                target["stage_progress_after"] = 100
    return tuple(
        SyncPlantResult(
            **{
                **rows[plant_id],
                "checkpoints": tuple(rows[plant_id]["checkpoints"]),
            }
        )
        for plant_id in order[:MAX_SYNC_SUMMARY_ROWS]
    )


def _merge_plant_results(
    older: Iterable[SyncPlantResult],
    newer: Iterable[SyncPlantResult],
) -> tuple[SyncPlantResult, ...]:
    result: dict[str, SyncPlantResult] = {}
    order: list[str] = []
    for item in (*tuple(older), *tuple(newer)):
        if item.plant_id not in result:
            order.append(item.plant_id)
            result[item.plant_id] = item
            continue
        current = result[item.plant_id]
        checkpoints = {
            checkpoint.event_id: checkpoint
            for checkpoint in (*current.checkpoints, *item.checkpoints)
        }
        result[item.plant_id] = replace(
            current,
            display_name=item.display_name or current.display_name,
            species=item.species or current.species,
            artwork_asset=item.artwork_asset or current.artwork_asset,
            growth_delta_units=(
                current.growth_delta_units + item.growth_delta_units
            ),
            progression_coins=current.progression_coins + item.progression_coins,
            stage_after=item.stage_after or current.stage_after,
            stage_progress_after=item.stage_progress_after,
            growth_after_units=item.growth_after_units,
            next_stage=item.next_stage,
            fully_grown=current.fully_grown or item.fully_grown,
            active=item.active,
            checkpoints=tuple(checkpoints.values())[:MAX_SYNC_SUMMARY_ROWS],
            stage_event_id=item.stage_event_id or current.stage_event_id,
            stage_event_text=item.stage_event_text or current.stage_event_text,
            full_bloom=current.full_bloom or item.full_bloom,
            transition_source=(
                item.transition_source or current.transition_source
            ),
        ).canonicalized()
    return tuple(
        result[key].canonicalized()
        for key in order[:MAX_SYNC_SUMMARY_ROWS]
    )


def _unique_rows(
    rows: Iterable[Mapping[str, Any]],
    identity_key: str,
) -> tuple[dict[str, Any], ...]:
    result: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for raw in rows:
        item = dict(raw)
        identity = _text(item.get(identity_key), limit=96) or repr(sorted(item.items()))
        if identity not in result:
            order.append(identity)
        result[identity] = item
    return tuple(result[key] for key in order[:MAX_SYNC_SUMMARY_ROWS])


def _merge_quantity_rows(
    older: Iterable[Mapping[str, Any]],
    newer: Iterable[Mapping[str, Any]],
    identity_key: str,
) -> tuple[dict[str, Any], ...]:
    result: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for raw in (*tuple(older), *tuple(newer)):
        item = dict(raw)
        identity = _text(item.get(identity_key), limit=96) or repr(sorted(item.items()))
        if identity not in result:
            order.append(identity)
            result[identity] = item
            result[identity]["quantity"] = _nonnegative(item.get("quantity")) or 1
        else:
            result[identity]["quantity"] = _nonnegative(
                result[identity].get("quantity")
            ) + (_nonnegative(item.get("quantity")) or 1)
            if "reward_amount_total" in result[identity] and "reward_amount_total" in item:
                result[identity]["reward_amount_total"] = _nonnegative(result[identity]["reward_amount_total"]) + _nonnegative(item["reward_amount_total"])
            else:
                result[identity].pop("reward_amount_total", None)
    return tuple(result[key] for key in order[:MAX_SYNC_SUMMARY_ROWS])


def _merge_growth_rows(
    older: Iterable[Mapping[str, Any]],
    newer: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    result: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for raw in (*tuple(older), *tuple(newer)):
        item = dict(raw)
        identity = _text(item.get("plant_id"), limit=96)
        if not identity:
            continue
        if identity not in result:
            order.append(identity)
            result[identity] = item
        else:
            current = result[identity]
            current["growth_delta_units"] = _nonnegative(
                current.get("growth_delta_units")
            ) + _nonnegative(item.get("growth_delta_units"))
            for key in (
                "plant_name",
                "plant_image",
                "stage_after",
                "stage_progress_after",
                "growth_after_units",
            ):
                if item.get(key) not in (None, ""):
                    current[key] = item[key]
    return tuple(result[key] for key in order[:MAX_SYNC_SUMMARY_ROWS])
