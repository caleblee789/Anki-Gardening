"""Stable, renderer-neutral projections for the Reviewer Garden HUD.

The reviewer hook owns engine commits and session lifetime. This module turns
the already-committed Garden state into compact display facts. The native Qt
component lives in :mod:`ankigarden.ui.reviewer_hud_widget` and stays mounted
while these immutable projections are replaced.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any

from ..growth import GROWTH_UNITS_PER_POINT, stage_presentation, stage_progress
from ..presentation import PlantIdentity
from ..environment import GARDEN_FEATURE_CATALOG
from ..garden_features import FEATURE_EFFECT_KEYS
from .formatters import format_approximate_cards, format_quantity


# The reviewer brief uses one fixed safe-area width. A fixed value also keeps
# two-line plant-name and checkpoint geometry stable across desktop widths.
HUD_EXPANDED_WIDTH = 296
HUD_MIN_WIDTH = 296
HUD_MAX_WIDTH = 296
HUD_COLLAPSED_WIDTH = 56
HUD_COLLAPSED_HEIGHT = 112
HUD_DEFAULT_CONTENT_HEIGHT = 558
HUD_TOP_MARGIN = 44
HUD_EDGE_MARGIN = 16
HUD_CONTROLS_CLEARANCE = 72
HUD_ANSWER_CONTROLS_SCHEMA_VERSION = 1
HUD_NARROW_VIEWPORT = 620
HUD_HEADER_LEFT_INSET = 14
HUD_HEADER_RIGHT_INSET = 6
HUD_HEADER_ACTIONS_PREFERRED_WIDTH = 170

# Full Bloom does not discard later review value: primary Growth routes to the
# next planted unfinished plant, Shared Growth is distributed among unfinished
# planted beds, and only a remainder with no available capacity is stored.
# Keep one renderer-neutral learner-facing contract so the projection and the
# native HUD cannot drift.
FULL_BLOOM_GROWTH_ROUTE_COPY = (
    "Future Growth will go to other planted plants. Any remainder will be stored."
)


STAGE_NAMES = {
    "seed": "Seed",
    "sprout": "Sprout",
    "young": "Young",
    "mature": "Mature",
    "flowering": "Flowering",
    "rare": "Full Bloom",
}


@dataclass(frozen=True)
class TodayCardsProjection:
    """Global all-decks completion, with legacy fields kept source-compatible."""

    status: str
    heading: str
    primary: str
    secondary: tuple[str, ...] = ()
    progress_value: int = 0
    progress_maximum: int = 0
    # These fields remain for the detailed Garden page, but the reviewer HUD
    # never populates or renders Find limits.
    finds_line: str = ""
    finds_detail: str = ""
    reviewed_count: int = 0
    remaining_count: int = 0
    completion_reward_coins: int = 0

    @property
    def complete(self) -> bool:
        return self.status == "complete"

    @property
    def progress_percent(self) -> int:
        if self.complete:
            return 100
        if self.progress_maximum <= 0:
            return 0
        # Preserve an unmistakable end gap until the scheduler confirms that
        # every due card and learning step is complete. In particular,
        # 175/176 must not render as visually complete due to rounding.
        return max(
            0,
            min(99, round(self.progress_value * 100 / self.progress_maximum)),
        )


@dataclass(frozen=True)
class NurtureProjection:
    """One visually focused active-plant projection.

    Legacy calculation-line fields remain present so an older detailed-view
    caller cannot fail during a rolling upgrade. They intentionally remain
    empty in the persistent reviewer HUD projection.
    """

    has_target: bool
    plant_id: str = ""
    plant_name: str = ""
    species_name: str = ""
    bed_label: str = ""
    stage_label: str = ""
    progress_percent: int = 0
    checkpoint_line: str = ""
    next_stage_line: str = ""
    estimate_line: str = ""
    next_card_line: str = ""
    shared_line: str = ""
    effect_chips: tuple[str, ...] = ()
    effect_art_refs: tuple[str, ...] = ()
    environment_line: str = ""
    queued_line: str = ""
    stored_growth_line: str = ""
    empty_heading: str = ""
    empty_message: str = ""
    stage_key: str = ""
    next_stage_key: str = ""
    checkpoint_percents: tuple[int, ...] = (25, 50, 75, 100)
    next_checkpoint_percent: int = 0
    next_checkpoint_reward_coins: int = 0
    checkpoint_growth_remaining: int = 0
    estimated_cards_to_checkpoint: int = 0
    next_answer_growth_units: int = 0
    art_path: str = ""
    art_placement: Any = None
    environment_tone: str = ""
    fully_grown: bool = False

    @property
    def next_answer_value(self) -> str:
        if self.next_answer_growth_units <= 0:
            return ""
        return f"{format_growth_units(self.next_answer_growth_units, signed=True)} growth"

    @property
    def visible_effect_chips(self) -> tuple[str, ...]:
        return self.effect_chips[:2]

    @property
    def visible_effect_art_refs(self) -> tuple[str, ...]:
        return self.effect_art_refs[:2]

    @property
    def effect_overflow_count(self) -> int:
        return max(0, len(self.effect_chips) - 2)


@dataclass(frozen=True)
class PlantChoiceProjection:
    """One engine-confirmed alternative for the reviewer plant selector."""

    plant_id: str
    plant_name: str
    species_name: str
    stage_key: str
    stage_label: str
    art_path: str = ""
    art_placement: Any = None


@dataclass(frozen=True)
class ReviewerHudProjection:
    coins: int
    today: TodayCardsProjection
    nurture: NurtureProjection
    collapsed: bool
    dock: str
    plant_choices: tuple[PlantChoiceProjection, ...] = ()


def format_growth_units(units: Any, *, signed: bool = False) -> str:
    """Format hundredth Growth units without unnecessary zeroes."""

    try:
        normalized = max(0, int(units))
    except (TypeError, ValueError):
        normalized = 0
    whole, remainder = divmod(normalized, GROWTH_UNITS_PER_POINT)
    if remainder == 0:
        value = f"{whole:,}"
    else:
        value = f"{whole:,}.{remainder:02d}".rstrip("0")
    return f"+{value}" if signed else value


def plural_cards(count: Any, *, suffix: str = "") -> str:
    try:
        normalized = max(0, int(count))
    except (TypeError, ValueError):
        normalized = 0
    return f"{format_quantity(normalized, 'card')}{suffix}"


def _relative_due_time(next_due_at_ms: Any, now_ms: int) -> str:
    try:
        seconds = max(0, math.ceil((int(next_due_at_ms) - int(now_ms)) / 1000))
    except (TypeError, ValueError):
        seconds = 0
    if seconds < 60:
        return "less than a minute"
    minutes = math.ceil(seconds / 60)
    if minutes < 60:
        return f"{minutes} {'minute' if minutes == 1 else 'minutes'}"
    hours = math.ceil(minutes / 60)
    return f"{hours} {'hour' if hours == 1 else 'hours'}"


def _completion_counts(completion: Any, stats: Any) -> tuple[int, int, int]:
    reviewed = max(
        0,
        int(
            getattr(
                completion,
                "cards_completed_today",
                getattr(stats, "reviewed", 0),
            )
            or 0
        ),
    )
    remaining = sum(
        max(0, int(getattr(completion, field, 0) or 0))
        for field in (
            "remaining_new_cards",
            "remaining_required_reviews",
            "remaining_learning_steps",
            "future_learning_steps_before_cutoff",
        )
    )
    maximum = max(0, int(getattr(completion, "starting_required_cards", 0) or 0))
    cleared = max(
        0,
        int(getattr(completion, "starting_required_cards_completed", 0) or 0),
    )
    if maximum <= 0 and cleared + remaining:
        maximum = cleared + remaining
    cleared = min(maximum, cleared) if maximum else 0
    return reviewed, remaining, cleared


def project_today_cards(
    state: Any,
    *,
    now_ms: int | None = None,
    completion_reward_coins: int = 10,
) -> TodayCardsProjection:
    """Project the global daily goal without exposing reward-cap mechanics."""

    completion = getattr(state, "daily_completion", None)
    stats = getattr(state, "daily_stats", None)
    status = str(getattr(completion, "status", "unavailable") or "unavailable")
    reviewed, remaining, cleared = _completion_counts(completion, stats)
    reward_coins = max(0, int(completion_reward_coins or 0))
    maximum = max(0, int(getattr(completion, "starting_required_cards", 0) or 0))
    if maximum <= 0 and cleared + remaining:
        maximum = cleared + remaining

    if status == "complete":
        return TodayCardsProjection(
            status="complete",
            heading="All cards complete",
            primary=f"+{format_quantity(reward_coins, 'coin')}",
            secondary=(f"{reviewed:,} reviewed today",),
            progress_value=max(maximum, cleared),
            progress_maximum=max(maximum, cleared),
            reviewed_count=reviewed,
            remaining_count=0,
            completion_reward_coins=reward_coins,
        )
    if status == "not_eligible":
        return TodayCardsProjection(
            status="not_eligible",
            heading="Today’s cards",
            primary="No cards due today",
            reviewed_count=reviewed,
        )
    if status == "unavailable":
        return TodayCardsProjection(
            status="unavailable",
            heading="Today’s cards",
            primary="Card status unavailable",
            secondary=("Garden growth is unaffected.",),
            reviewed_count=reviewed,
        )

    primary = (
        f"{cleared:,} / {maximum:,}"
        if maximum > 0
        else plural_cards(remaining, suffix=" left")
    )
    secondary: tuple[str, ...] = (plural_cards(remaining, suffix=" left"),)
    if status == "waiting_for_learning":
        current_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)
        secondary = (
            f"{plural_cards(remaining)} due in "
            f"{_relative_due_time(getattr(completion, 'next_learning_due_at_ms', 0), current_ms)}",
        )
    return TodayCardsProjection(
        status="waiting_for_learning" if status == "waiting_for_learning" else "in_progress",
        heading="Today’s cards",
        primary=primary,
        secondary=secondary,
        progress_value=cleared,
        progress_maximum=maximum,
        reviewed_count=reviewed,
        remaining_count=remaining,
        completion_reward_coins=reward_coins,
    )


def _active_target(engine: Any, state: Any) -> Any | None:
    resolver = getattr(engine, "active_plant", None)
    try:
        target = resolver() if callable(resolver) else None
    except Exception:
        target = None
    if target is not None:
        return target
    target_id = str(getattr(state, "active_plant_id", "") or "")
    return next(
        (
            plant
            for plant in getattr(state, "plants", ())
            if str(getattr(plant, "plant_id", "")) == target_id
            and bool(
                getattr(
                    plant,
                    "planted",
                    getattr(plant, "slot_index", None) is not None,
                )
            )
        ),
        None,
    )


def _reviewer_checkpoint_percents(engine: Any) -> tuple[int, ...]:
    values: list[int] = []
    for raw in tuple(
        getattr(engine, "reviewer_checkpoint_percents", (25, 50, 75, 100))
        or (25, 50, 75, 100)
    ):
        try:
            percent = int(raw)
        except (TypeError, ValueError):
            continue
        if 0 < percent <= 100 and percent not in values:
            values.append(percent)
    return tuple(sorted(values)) or (25, 50, 75, 100)


def _next_checkpoint(
    total_growth: int,
    checkpoint_percents: tuple[int, ...] = (25, 50, 75, 100),
) -> tuple[int, int, int] | None:
    progress = stage_progress(total_growth)
    if progress.fully_grown or progress.next_threshold is None:
        return None
    for percent in checkpoint_percents:
        point = progress.stage_start + math.ceil(progress.stage_goal * percent / 100)
        if total_growth < point:
            return percent, point - total_growth, point
    return None


def _remaining_time_label(seconds: Any) -> str:
    try:
        remaining = max(0, int(math.ceil(float(seconds))))
    except (TypeError, ValueError):
        remaining = 0
    if remaining < 60:
        return "<1m"
    minutes = math.ceil(remaining / 60)
    if minutes < 60:
        return f"{minutes}m"
    hours, extra_minutes = divmod(minutes, 60)
    return f"{hours}h" if extra_minutes == 0 else f"{hours}h {extra_minutes}m"


def _active_effect_rows(
    engine: Any,
    plant: Any,
    award: Any,
    *,
    now_ms: int | None = None,
) -> tuple[tuple[str, str], ...]:
    """Return compact effect copy paired with canonical item artwork refs."""

    rows: list[tuple[str, str]] = []
    state = getattr(engine, "state", None)
    active_feature_resolver = getattr(engine, "active_garden_feature_id", None)
    try:
        active_id = str(
            active_feature_resolver()
            if callable(active_feature_resolver)
            else ""
        )
    except Exception:
        active_id = ""
    active_item = GARDEN_FEATURE_CATALOG.get(active_id)
    effect = FEATURE_EFFECT_KEYS.get(active_id, "none")
    progress_copy = {
        "growth_every_10_plus_1": (
            f"{max(0, int(getattr(state, 'wind_chime_progress', 0) or 0))} / 10 cards to next +1 Growth"
        ),
        "growth_every_5_plus_1": (
            f"{max(0, int(getattr(state, 'watering_station_progress', 0) or 0))} / 5 cards to next +1 Growth"
        ),
        "growth_every_4_plus_3": (
            f"{max(0, int(getattr(state, 'firefly_lantern_progress', 0) or 0))} / 4 cards to next +3 Growth"
        ),
        "completion_coins_plus_5": "+5 Coins when Today’s Cards are complete",
        "booster_cards_multiplier_1_25": "Booster Potions add 25% more cards",
        "none": "No mechanical bonus",
    }.get(effect, "")
    if effect == "prism_bank_per_answer_1_5":
        day = str(getattr(getattr(state, "daily_stats", None), "day", "") or "")
        released = str(getattr(state, "prism_released_anki_day_id", "") or "") == day
        progress_copy = (
            "+1.5 direct Growth per eligible card · Today’s Prism Harvest released"
            if released else
            f"{format_growth_units(getattr(state, 'prism_pending_growth_units', 0))} Growth banked"
        )
    feature_row = (
        (
            f"{active_item.name} · {progress_copy}",
            f"garden_feature_{active_id}",
        )
        if active_item is not None and progress_copy
        else None
    )
    current_seconds = (
        float(time.time())
        if now_ms is None
        else max(0, int(now_ms)) / 1_000
    )
    fertilizer = None
    queued_fertilizer: tuple[Any, ...] = ()
    scheduler = getattr(engine, "fertilizer_schedule", None)
    if callable(scheduler):
        try:
            fertilizer, queued_fertilizer = scheduler(plant, now=current_seconds)
        except Exception:
            fertilizer, queued_fertilizer = None, ()
    else:
        candidate = getattr(plant, "fertilizer", None)
        if candidate is not None and float(getattr(candidate, "expires_at", 0) or 0) > current_seconds:
            fertilizer = candidate
    if fertilizer is not None:
        tier = str(getattr(fertilizer, "tier", "") or "")
        effective_end = float(getattr(fertilizer, "expires_at", 0) or 0)
        for period in queued_fertilizer:
            if (
                str(getattr(period, "tier", "") or "") == tier
                and float(getattr(period, "started_at", 0) or 0) <= effective_end
            ):
                effective_end = max(
                    effective_end,
                    float(getattr(period, "expires_at", 0) or 0),
                )
            else:
                break
        rows.append((
            f"Fertilizer · {_remaining_time_label(effective_end - current_seconds)}",
            f"fertilizer_{tier}" if tier in {"basic", "quality", "premium"} else "",
        ))

    booster_batches = list(getattr(plant, "booster_card_batches", ()) or ())
    if booster_batches:
        booster_cards = sum(
            max(0, int(getattr(batch, "remaining_cards", 0) or 0))
            for batch in booster_batches
        )
        rows.append((
            f"Booster · {plural_cards(booster_cards)}",
            "booster_potion",
        ))

    # Garden Decoration and Scenery contributions are active per-card modifiers,
    # so they precede the derived streak bonus while remaining behind timed
    # Fertilizer and card-limited Booster effects.
    for label, units in (
        ("Garden decoration", getattr(award, "weather_growth_units", 0)),
        ("Scenery", getattr(award, "scenery_growth_units", 0)),
    ):
        normalized_units = max(0, int(units or 0))
        if normalized_units:
            rows.append((
                f"{label} · {format_growth_units(normalized_units, signed=True)} growth",
                "",
            ))

    # Named mechanical features remain useful when they affect a later card or
    # completion rather than this answer. Avoid duplicating the active feature
    # when its direct Growth is already represented above.
    if feature_row is not None and (
        effect != "none"
        and max(0, int(getattr(award, "weather_growth_units", 0) or 0)) == 0
    ):
        rows.append(feature_row)

    streak_units = max(0, int(getattr(award, "streak_growth_units", 0) or 0))
    if streak_units:
        rows.append((
            f"Streak bonus · {format_growth_units(streak_units, signed=True)} growth",
            "",
        ))
    if feature_row is not None and effect == "none":
        rows.append(feature_row)
    return tuple(rows)


def _active_effect_chips(
    engine: Any,
    plant: Any,
    award: Any,
    *,
    now_ms: int | None = None,
) -> tuple[str, ...]:
    """Compatibility projection for callers that only consume effect copy."""

    return tuple(
        copy
        for copy, _artwork_ref in _active_effect_rows(
            engine,
            plant,
            award,
            now_ms=now_ms,
        )
    )


def _checkpoint_reward(engine: Any, next_stage: str, percent: int) -> int:
    resolver = getattr(engine, "project_checkpoint_reward", None)
    if callable(resolver) and percent:
        try:
            return max(0, int(resolver(next_stage, percent)))
        except Exception:
            pass
    splits = getattr(engine, "STAGE_REWARD_SPLITS", {}) or {}
    if next_stage in splits and percent in (25, 50, 75, 100):
        try:
            return max(0, int(tuple(splits[next_stage])[(25, 50, 75, 100).index(percent)]))
        except (TypeError, ValueError, IndexError):
            pass
    return 0


def _resolved_plant_art(engine: Any, species: str, stage: str) -> tuple[str, Any]:
    asset = None
    resolver = getattr(engine, "resolve_plant_asset", None)
    if callable(resolver):
        try:
            asset = resolver(species, stage)
        except Exception:
            asset = None
    path = getattr(asset, "path", None) if asset is not None else None
    placement = getattr(asset, "placement", None) if asset is not None else None
    if not path:
        legacy = getattr(engine, "resolve_plant_image", None)
        if callable(legacy):
            try:
                path = legacy(species, stage)
            except Exception:
                path = None
    return (str(path) if path else "", placement)


def project_plant_choices(
    engine: Any,
    state: Any,
) -> tuple[PlantChoiceProjection, ...]:
    """Project planted, unfinished alternatives without mutating Garden state."""

    active_id = str(getattr(state, "active_plant_id", "") or "")
    story = getattr(engine, "plant_story", None)
    choices: list[tuple[tuple[Any, ...], PlantChoiceProjection]] = []
    for candidate in tuple(getattr(state, "plants", ()) or ()):
        plant_id = str(getattr(candidate, "plant_id", "") or "")
        if not plant_id or plant_id == active_id:
            continue
        plant = candidate
        if callable(story):
            try:
                plant = story(plant_id)
            except Exception:
                plant = None
            if plant is None:
                continue
        planted = bool(
            getattr(
                plant,
                "planted",
                getattr(plant, "slot_index", None) is not None,
            )
        )
        if not planted or bool(getattr(plant, "fully_grown", False)):
            continue
        species_key = str(getattr(plant, "species", "") or "")
        species_name = species_key.replace("_", " ").title()
        plant_name = str(getattr(plant, "name", "") or species_name or "Plant")
        stage_key = str(getattr(plant, "growth_stage", "") or "seed")
        stage_label = STAGE_NAMES.get(
            stage_key,
            stage_key.replace("_", " ").title(),
        )
        art_path, art_placement = _resolved_plant_art(
            engine,
            species_key,
            stage_key,
        )
        choice = PlantChoiceProjection(
            plant_id=plant_id,
            plant_name=plant_name,
            species_name=species_name,
            stage_key=stage_key,
            stage_label=stage_label,
            art_path=art_path,
            art_placement=art_placement,
        )
        try:
            slot_order = int(getattr(plant, "slot_index", 0) or 0)
        except (TypeError, ValueError):
            slot_order = 0
        choices.append((
            (slot_order, plant_name.casefold(), plant_id),
            choice,
        ))
    choices.sort(key=lambda item: item[0])
    return tuple(choice for _sort_key, choice in choices)


def project_nurture(
    engine: Any,
    state: Any,
    *,
    now_ms: int | None = None,
) -> NurtureProjection:
    stored_units = max(0, int(getattr(state, "stored_growth_units", 0) or 0))
    target = _active_target(engine, state)
    if target is None:
        stored_line = (
            f"{format_growth_units(stored_units)} growth stored until a plant is selected"
            if stored_units
            else ""
        )
        return NurtureProjection(
            False,
            stored_growth_line=stored_line,
            empty_heading="No plant selected",
            empty_message="Growth earned during review will be stored.",
        )

    total_growth = max(0, int(getattr(target, "growth_points", 0) or 0))
    progress = stage_progress(total_growth)
    fully_grown = bool(getattr(target, "fully_grown", False) or progress.fully_grown)
    stage_key = "rare" if fully_grown else str(
        getattr(target, "growth_stage", "") or progress.stage or "seed"
    )
    next_stage = str(progress.next_stage or "")
    checkpoint_percents = _reviewer_checkpoint_percents(engine)
    checkpoint = (
        None
        if fully_grown
        else _next_checkpoint(total_growth, checkpoint_percents)
    )

    award = None
    projector = getattr(engine, "project_review_growth", None)
    if callable(projector) and not fully_grown:
        try:
            award = projector(target)
        except Exception:
            award = None
    total_units = max(
        0,
        int(
            getattr(
                award,
                "total_growth_units",
                max(0, int(getattr(award, "total_growth", 0) or 0))
                * GROWTH_UNITS_PER_POINT,
            )
            or 0
        ),
    )

    checkpoint_percent = 0
    checkpoint_line = ""
    estimate_line = ""
    checkpoint_reward = 0
    growth_remaining = 0
    estimated_cards = 0
    if checkpoint is not None:
        checkpoint_percent, growth_remaining, _point = checkpoint
        estimated_cards = (
            math.ceil(growth_remaining * GROWTH_UNITS_PER_POINT / total_units)
            if total_units > 0
            else 0
        )
        estimate_line = format_approximate_cards(estimated_cards) if estimated_cards else ""
        checkpoint_line = f"{growth_remaining:,} growth to next checkpoint"
        checkpoint_reward = _checkpoint_reward(engine, next_stage, checkpoint_percent)

    canonical_stage = stage_presentation(stage_key)
    stage_name = (
        canonical_stage.display_name
        if canonical_stage is not None else
        STAGE_NAMES.get(stage_key, stage_key.replace("_", " ").title())
    )
    stage_label = (
        f"{stage_name} · {canonical_stage.display_ordinal} of "
        f"{canonical_stage.display_total} stages"
        if canonical_stage is not None else
        stage_name
    )

    species_key = str(getattr(target, "species", "") or "")
    identity = PlantIdentity.from_plant(target)
    species_name = identity.species_name
    plant_name = identity.display_name
    art_path, art_placement = _resolved_plant_art(engine, species_key, stage_key)
    effect_rows = _active_effect_rows(engine, target, award, now_ms=now_ms)
    schedule = getattr(state, "daily_loadout", None)
    weather_id = str(
        getattr(schedule, "weather_id", "")
        or getattr(state, "selected_weather", "")
    )
    scenery_id = str(
        getattr(schedule, "scenery_id", "")
        or getattr(state, "selected_background", "")
    )
    next_answer_line = (
        f"Next answer · {format_growth_units(total_units, signed=True)} growth"
        if total_units
        else ""
    )
    return NurtureProjection(
        True,
        plant_id=str(getattr(target, "plant_id", "") or ""),
        plant_name=plant_name,
        species_name=species_name,
        bed_label=(
            f"Bed {int(getattr(target, 'slot_index', 0)) + 1}"
            if getattr(target, "slot_index", None) is not None
            else ""
        ),
        stage_label=stage_label,
        progress_percent=100 if fully_grown else max(0, min(100, round(progress.progress * 100))),
        checkpoint_line=checkpoint_line,
        next_stage_line=(
            f"Checkpoint reward · +{format_quantity(checkpoint_reward, 'coin')}"
            if checkpoint_reward
            else ""
        ),
        estimate_line=estimate_line,
        next_card_line=next_answer_line,
        effect_chips=tuple(copy for copy, _artwork_ref in effect_rows),
        effect_art_refs=tuple(artwork_ref for _copy, artwork_ref in effect_rows),
        stored_growth_line="",
        empty_message=(
            FULL_BLOOM_GROWTH_ROUTE_COPY
            if fully_grown
            else ""
        ),
        stage_key=stage_key,
        next_stage_key=next_stage,
        checkpoint_percents=checkpoint_percents,
        next_checkpoint_percent=checkpoint_percent,
        next_checkpoint_reward_coins=checkpoint_reward,
        checkpoint_growth_remaining=growth_remaining,
        estimated_cards_to_checkpoint=estimated_cards,
        next_answer_growth_units=total_units,
        art_path=art_path,
        art_placement=art_placement,
        environment_tone=" ".join(value for value in (weather_id, scenery_id) if value),
        fully_grown=fully_grown,
    )


def project_reviewer_hud(
    engine: Any,
    state: Any,
    *,
    collapsed: bool = False,
    dock: str = "right",
    now_ms: int | None = None,
) -> ReviewerHudProjection:
    reward_coins = max(0, int(getattr(engine, "ALL_DUE_BASE_COINS", 10) or 0))
    reward_resolver = getattr(engine, "all_due_rewards", None)
    if callable(reward_resolver):
        try:
            resolved_coins, _resolved_growth = reward_resolver()
            reward_coins = max(0, int(resolved_coins or 0))
        except Exception:
            pass
    return ReviewerHudProjection(
        coins=max(0, int(getattr(state, "currency_balance", 0) or 0)),
        today=project_today_cards(
            state,
            now_ms=now_ms,
            completion_reward_coins=reward_coins,
        ),
        nurture=project_nurture(engine, state, now_ms=now_ms),
        collapsed=bool(collapsed),
        dock="left" if str(dock) == "left" else "right",
        plant_choices=project_plant_choices(engine, state),
    )


def reviewer_hud_width(viewport_width: int) -> int:
    """Return the responsive expanded width for one reviewer viewport."""

    viewport = max(1, int(viewport_width))
    available = max(1, viewport - HUD_EDGE_MARGIN * 2)
    responsive = round(viewport * 0.20)
    return min(available, max(HUD_MIN_WIDTH, min(HUD_MAX_WIDTH, responsive)))


def reviewer_hud_header_actions_width(title_width: int) -> int:
    """Return the largest action reserve that keeps the header contained.

    The title is content-sized while the balance and collapse control share a
    right-aligned reserve.  Deriving that reserve from the fixed Reviewer safe
    area prevents either group from crossing the header boundary when native
    font metrics make the title wider than its former nominal allocation.
    """

    available = (
        HUD_EXPANDED_WIDTH
        - HUD_HEADER_LEFT_INSET
        - HUD_HEADER_RIGHT_INSET
        - max(0, int(title_width))
    )
    return max(0, min(HUD_HEADER_ACTIONS_PREFERRED_WIDTH, available))


def reviewer_hud_safe_bottom(
    viewport_height: int,
    answer_controls_top: int | None = None,
) -> int:
    """Return the shared lower boundary for the Reviewer HUD safe area."""

    viewport = max(1, int(viewport_height))
    if answer_controls_top is None:
        return max(
            HUD_TOP_MARGIN + 1,
            viewport - HUD_CONTROLS_CLEARANCE,
        )
    return max(
        HUD_TOP_MARGIN + 1,
        min(viewport, int(answer_controls_top)),
    )


def reviewer_hud_geometry(
    viewport_width: int,
    viewport_height: int,
    *,
    collapsed: bool,
    dock: str,
    content_height: int | None = None,
    answer_controls_top: int | None = None,
) -> tuple[int, int, int, int]:
    """Return content-hugging, answer-bar-safe ``(x, y, width, height)``.

    ``content_height`` is the mounted native widget's current size hint. The
    default represents the normal no-reveal composition and intentionally does
    not consume all available vertical space.
    """

    viewport_width = max(1, int(viewport_width))
    viewport_height = max(1, int(viewport_height))
    width_limit = max(1, viewport_width - HUD_EDGE_MARGIN * 2)
    width = (
        min(HUD_COLLAPSED_WIDTH, width_limit)
        if collapsed
        else reviewer_hud_width(viewport_width)
    )
    safe_bottom = reviewer_hud_safe_bottom(
        viewport_height,
        answer_controls_top,
    )
    available_height = max(1, safe_bottom - HUD_TOP_MARGIN)
    if collapsed:
        height = min(HUD_COLLAPSED_HEIGHT, available_height)
    else:
        desired = max(1, int(
            HUD_DEFAULT_CONTENT_HEIGHT if content_height is None else content_height
        ))
        height = min(desired, available_height)
    x = (
        HUD_EDGE_MARGIN
        if str(dock) == "left"
        else max(0, viewport_width - width - HUD_EDGE_MARGIN)
    )
    return x, HUD_TOP_MARGIN, width, height


def should_start_collapsed(viewport_width: int, saved_collapsed: bool) -> bool:
    return bool(saved_collapsed) or int(viewport_width) < HUD_NARROW_VIEWPORT


def create_reviewer_hud(parent: Any, **callbacks: Any) -> Any:
    """Construct the native mounted component without importing Qt here."""

    from .reviewer_hud_widget import ReviewGardenHud

    return ReviewGardenHud(parent, **callbacks)


__all__ = [
    "HUD_COLLAPSED_HEIGHT",
    "HUD_COLLAPSED_WIDTH",
    "HUD_ANSWER_CONTROLS_SCHEMA_VERSION",
    "HUD_CONTROLS_CLEARANCE",
    "HUD_DEFAULT_CONTENT_HEIGHT",
    "HUD_EDGE_MARGIN",
    "HUD_EXPANDED_WIDTH",
    "HUD_HEADER_ACTIONS_PREFERRED_WIDTH",
    "HUD_HEADER_LEFT_INSET",
    "HUD_HEADER_RIGHT_INSET",
    "HUD_MAX_WIDTH",
    "HUD_MIN_WIDTH",
    "HUD_NARROW_VIEWPORT",
    "HUD_TOP_MARGIN",
    "NurtureProjection",
    "PlantChoiceProjection",
    "ReviewerHudProjection",
    "TodayCardsProjection",
    "create_reviewer_hud",
    "format_growth_units",
    "plural_cards",
    "project_plant_choices",
    "project_nurture",
    "project_reviewer_hud",
    "project_today_cards",
    "reviewer_hud_geometry",
    "reviewer_hud_header_actions_width",
    "reviewer_hud_safe_bottom",
    "reviewer_hud_width",
    "should_start_collapsed",
]
