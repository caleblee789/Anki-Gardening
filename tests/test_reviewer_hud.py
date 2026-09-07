from __future__ import annotations

import inspect
from collections import deque
from pathlib import Path
from types import SimpleNamespace

import pytest

from ankigarden.config import DEFAULT_CONFIG
from ankigarden.economy_progression import (
    GrowthTargetRef,
    GrowthTargetType,
    build_growth_projects_snapshot,
)
from ankigarden.reward_presentation import (
    RewardBundleProjection,
    RewardHero,
    RewardItemProjection,
)
from ankigarden.ui.plant_art import padded_preview_bounds
from ankigarden.ui.reviewer_hud import (
    HUD_COLLAPSED_HEIGHT,
    HUD_COLLAPSED_WIDTH,
    NurtureProjection,
    project_plant_choices,
    project_reviewer_hud,
    project_today_cards,
    reviewer_hud_geometry,
    reviewer_hud_safe_bottom,
    reviewer_hud_width,
)
from ankigarden.ui.reviewer_hud_widget import (
    ReviewGardenHud,
    _COMPACT_REWARD_MAX_HEIGHT,
    _COMPACT_REWARD_MIN_HEIGHT,
    _TODAY_INCOMPLETE_VISUAL_MAX,
    _TODAY_PROGRESS_SCALE,
    _all_secondary_items,
    _bundle_has_kind,
    _bundle_growth_units,
    _checkpoint_marker_states,
    _checkpoint_sequence_is_chronological,
    _compact_summary_label,
    _effect_display_text,
    _effect_overflow_label,
    _format_coin_balance,
    _ground_shadow_metrics,
    _hero_amounts,
    _hero_inventory_labels,
    _hero_kind,
    _secondary_label,
    _session_coin_count,
    _session_find_count,
    _session_metric_increases,
    _session_metric_labels,
)


DAY = "2026-08-28"
WIDGET_SOURCE = Path(
    "ankigarden/ui/reviewer_hud_widget.py"
).read_text(encoding="utf-8")
DASHBOARD_SOURCE = Path("ankigarden/ui/dashboard.py").read_text(encoding="utf-8")
REVIEWER_HOOK_SOURCE = Path("ankigarden/hooks/reviewer.py").read_text(encoding="utf-8")


def completion(status: str, **overrides):
    values = {
        "scheduler_day": DAY,
        "status": status,
        "starting_required_cards": 194,
        "starting_required_cards_completed": 176,
        "remaining_new_cards": 0,
        "remaining_required_reviews": 16,
        "remaining_learning_steps": 2,
        "future_learning_steps_before_cutoff": 0,
        "next_learning_due_at_ms": 0,
        "cards_completed_today": 176,
        "reward_claimed": status == "complete",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def state_for(status: str, **completion_overrides):
    return SimpleNamespace(
        daily_completion=completion(status, **completion_overrides),
        daily_stats=SimpleNamespace(day=DAY, reviewed=176),
        garden_find_daily_counts={DAY: 3},
        garden_find_drought_count=74,
        currency_balance=10_013,
        starter_selection_complete=True,
        stored_growth_units=0,
        active_plant_id="plant-1",
        plants=[],
        selected_weather="gentle_rain",
        selected_background="spring",
        daily_loadout=SimpleNamespace(
            weather_id="gentle_rain",
            scenery_id="spring",
        ),
    )


def test_today_cards_is_global_compact_and_has_no_find_cap_copy() -> None:
    in_progress = project_today_cards(state_for("in_progress"))
    assert in_progress.heading == "Today’s cards"
    assert in_progress.primary == "176 / 194"
    assert in_progress.secondary == ("18 cards left",)
    assert (in_progress.progress_value, in_progress.progress_maximum) == (176, 194)
    assert in_progress.remaining_count == 18
    assert in_progress.finds_line == ""
    assert in_progress.finds_detail == ""

    complete = project_today_cards(state_for("complete"))
    assert complete.heading == "Today’s cards complete"
    assert complete.primary == "+10 Coins"
    assert complete.secondary == ("176 cards studied today",)
    assert complete.progress_percent == 100

    visible = " ".join((
        in_progress.heading,
        in_progress.primary,
        *in_progress.secondary,
        complete.heading,
        complete.primary,
        *complete.secondary,
    )).casefold()
    for forbidden in ("garden find", "daily limit", "all decks", "reward cap"):
        assert forbidden not in visible


def test_today_cards_counts_new_only_obligations_once() -> None:
    projection = project_today_cards(state_for(
        "in_progress",
        starting_required_cards=20,
        starting_required_cards_completed=0,
        remaining_new_cards=20,
        remaining_required_reviews=0,
        remaining_learning_steps=0,
        future_learning_steps_before_cutoff=0,
        cards_completed_today=0,
    ))

    assert projection.primary == "0 / 20"
    assert projection.secondary == ("20 cards left",)
    assert (projection.progress_value, projection.progress_maximum) == (0, 20)
    assert projection.remaining_count == 20


def test_today_cards_reconciles_mixed_new_review_and_learning_obligations() -> None:
    projection = project_today_cards(state_for(
        "in_progress",
        remaining_new_cards=4,
        remaining_required_reviews=10,
        remaining_learning_steps=2,
        future_learning_steps_before_cutoff=2,
    ))

    assert projection.primary == "176 / 194"
    assert projection.secondary == ("18 cards left",)
    assert (projection.progress_value, projection.progress_maximum) == (176, 194)
    assert projection.remaining_count == 18


def test_complete_today_card_uses_engine_confirmed_coin_reward() -> None:
    projection = project_reviewer_hud(
        SimpleNamespace(
            active_plant=lambda: None,
            all_due_rewards=lambda: (15, 0),
            ALL_DUE_BASE_COINS=10,
        ),
        state_for("complete"),
    )

    assert projection.today.primary == "+15 Coins"
    assert projection.today.completion_reward_coins == 15
    singular = project_today_cards(
        state_for("complete"),
        completion_reward_coins=1,
    )
    assert singular.primary == "+1 Coin"
    unawarded = state_for("complete", reward_claimed=False)
    unawarded.daily_stats.completed_due_cards = False
    pending = project_today_cards(unawarded)
    assert pending.completion_reward_coins == 0
    assert "Coin" not in pending.primary



def test_incomplete_today_progress_retains_an_end_gap_at_175_of_176() -> None:
    projection = project_today_cards(state_for(
        "in_progress",
        starting_required_cards=176,
        starting_required_cards_completed=175,
        remaining_required_reviews=1,
        remaining_learning_steps=0,
        future_learning_steps_before_cutoff=0,
    ))

    assert projection.primary == "175 / 176"
    assert projection.secondary == ("1 card left",)
    assert projection.progress_percent == 99
    assert (_TODAY_PROGRESS_SCALE, _TODAY_INCOMPLETE_VISUAL_MAX) == (1_000, 985)

    today_copy = WIDGET_SOURCE.split("def _apply_today_copy", 1)[1].split(
        "def _settle_today_completion",
        1,
    )[0]
    assert "round(actual_percent * 10.0)" in today_copy
    assert "_TODAY_INCOMPLETE_VISUAL_MAX" in today_copy
    assert '"minimumUnfilledLogicalPixels"' in today_copy


def test_waiting_and_unavailable_states_remain_concise() -> None:
    waiting = project_today_cards(
        state_for(
            "waiting_for_learning",
            remaining_required_reviews=0,
            remaining_learning_steps=0,
            future_learning_steps_before_cutoff=2,
            next_learning_due_at_ms=1_360_000,
        ),
        now_ms=1_000_000,
    )
    assert waiting.primary == "176 / 194"
    assert waiting.secondary == ("2 cards due in 6 minutes",)

    ineligible = project_today_cards(state_for("not_eligible"))
    assert (ineligible.heading, ineligible.primary) == (
        "Today’s cards",
        "No cards due",
    )
    unavailable = project_today_cards(state_for("unavailable"))
    assert unavailable.primary == "Card status unavailable"
    assert unavailable.secondary == ("Garden growth is unaffected.",)


def test_nurture_projection_keeps_only_the_outcomes_needed_during_review() -> None:
    placement = SimpleNamespace(
        thumbnail_bounds=(0.38, 0.18, 0.24, 0.62),
        thumbnail_safe_padding=0.10,
    )
    plant = SimpleNamespace(
        plant_id="plant-1",
        species="bonsai",
        name="Juniper of the Moonlit Terrace",
        slot_index=0,
        growth_points=6_020,
        growth_remainder_units=0,
        planted=True,
        fully_grown=False,
        fertilizer_card_batches=(SimpleNamespace(
            effect_id="fertilizer_quality",
            remaining_cards=42,
        ),),
        booster_card_batches=(SimpleNamespace(remaining_cards=38),),
    )
    state = state_for("in_progress")
    state.plants = [plant]
    award = SimpleNamespace(
        total_growth_units=1_350,
        streak_growth_units=100,
        weather_growth_units=50,
        scenery_growth_units=25,
        allocations=(
            SimpleNamespace(role="nurtured", applied_units=1_350),
            SimpleNamespace(role="passive", plant_id="plant-2", applied_units=270),
        ),
    )
    engine = SimpleNamespace(
        active_plant=lambda: plant,
        project_review_growth=lambda _plant: award,
        resolve_plant_asset=lambda species, stage: SimpleNamespace(
            path=f"/art/{species}-{stage}.webp",
            placement=placement,
        ),
        STAGE_REWARD_SPLITS={"mature": (4, 4, 4, 8)},
    )

    nurture = project_reviewer_hud(engine, state, now_ms=1_000_000).nurture

    assert nurture.plant_name == "Mature Bonsai"
    assert nurture.stage_label == "Mature · Stage 4 of 6"
    assert nurture.species_name == "Bonsai"
    assert nurture.next_answer_value == "+13.5 Growth"
    assert nurture.next_card_line == "Next card: +13.5 Growth"
    assert nurture.checkpoint_line == "2,230 Growth to next checkpoint"
    assert nurture.estimate_line == "~166 cards to the next checkpoint"
    assert nurture.checkpoint_growth_remaining == 2_230
    assert nurture.estimated_cards_to_checkpoint == 166
    assert nurture.next_checkpoint_percent == 25
    assert nurture.next_checkpoint_reward_coins == 0
    assert nurture.checkpoint_percents == (25, 50, 75, 100)
    assert nurture.next_stage_line == ""
    assert nurture.art_path == "/art/bonsai-mature.webp"
    assert nurture.art_placement is placement
    assert nurture.visible_effect_chips == (
        "Quality Fertilizer · 42 cards remaining",
        "Booster Potion · 38 cards remaining",
    )
    assert nurture.effect_chips == (
        "Quality Fertilizer · 42 cards remaining",
        "Booster Potion · 38 cards remaining",
        "Garden decoration · +0.5 Growth",
        "Scenery · +0.25 Growth",
        "Garden Rhythm · +1 Growth",
    )
    assert nurture.visible_effect_art_refs == (
        "fertilizer_quality",
        "booster_potion",
    )
    assert nurture.effect_art_refs == (
        "fertilizer_quality",
        "booster_potion",
        "",
        "",
        "",
    )
    assert nurture.effect_overflow_count == 3
    assert nurture.shared_line == ""
    assert nurture.environment_line == ""
    assert nurture.queued_line == ""
    assert nurture.stored_growth_line == ""


def test_plant_choices_are_engine_confirmed_planted_unfinished_alternatives() -> None:
    active = SimpleNamespace(
        plant_id="active",
        species="bonsai",
        name="Active Plant",
        slot_index=0,
        planted=True,
        fully_grown=True,
        growth_stage="rare",
    )
    second = SimpleNamespace(
        plant_id="second",
        species="ivy",
        name="Quiet Ivy",
        slot_index=2,
        planted=True,
        fully_grown=False,
        growth_stage="young",
    )
    first = SimpleNamespace(
        plant_id="first",
        species="rose",
        name="Amber Rose",
        slot_index=1,
        planted=True,
        fully_grown=False,
        growth_stage="sprout",
    )
    unplanted = SimpleNamespace(
        plant_id="stored",
        species="fern",
        name="Stored Fern",
        slot_index=None,
        planted=False,
        fully_grown=False,
        growth_stage="seed",
    )
    complete = SimpleNamespace(
        plant_id="complete",
        species="oak",
        name="Finished Oak",
        slot_index=3,
        planted=True,
        fully_grown=True,
        growth_stage="rare",
    )
    stale = SimpleNamespace(
        plant_id="stale",
        species="moss",
        name="Stale Moss",
        slot_index=4,
        planted=True,
        fully_grown=False,
        growth_stage="seed",
    )
    state = SimpleNamespace(
        active_plant_id="active",
        plants=[second, stale, active, complete, first, unplanted],
    )
    by_id = {
        plant.plant_id: plant
        for plant in (active, second, first, unplanted, complete)
    }
    placement = object()
    engine = SimpleNamespace(
        state=state,
        plant_story=lambda plant_id: by_id.get(plant_id),
        resolve_plant_asset=lambda species, stage: SimpleNamespace(
            path=f"/art/{species}-{stage}.webp",
            placement=placement,
        ),
    )

    choices = project_plant_choices(engine, state)

    assert tuple(choice.plant_id for choice in choices) == ("first", "second")
    assert choices[0].plant_name == "Rose Sprout"
    assert choices[0].species_name == "Rose"
    assert choices[0].stage_label == "Sprout"
    assert choices[0].art_path == "/art/rose-sprout.webp"
    assert choices[0].art_placement is placement
    # A caller holding an older snapshot still gets engine-confirmed choices.
    snapshot = SimpleNamespace(active_plant_id=state.active_plant_id, plants=[
        SimpleNamespace(**{**vars(plant), "planted": False, "slot_index": None})
        for plant in state.plants
    ])
    assert project_plant_choices(engine, snapshot) == choices


def test_no_plant_and_full_bloom_use_contextual_copy() -> None:
    no_target = state_for("in_progress")
    no_target.active_plant_id = ""
    no_target.stored_growth_units = 1_250
    empty = project_reviewer_hud(SimpleNamespace(active_plant=lambda: None), no_target).nurture
    assert empty.empty_heading == "No plant selected"
    assert empty.empty_message == "Growth earned during review will be stored."
    assert not empty.stored_growth_line
    assert empty.growth_destination.detail == "12.5 Growth in reserve"
    assert empty.growth_destination.artwork_id == "stored_growth"

    full = SimpleNamespace(
        plant_id="plant-1",
        species="rose",
        name="Rose",
        slot_index=1,
        growth_points=100_000,
        planted=True,
        fully_grown=True,
        booster_card_batches=(),
    )
    full_state = state_for("complete")
    full_state.plants = [full]
    projection = project_reviewer_hud(
        SimpleNamespace(active_plant=lambda: full),
        full_state,
    ).nurture
    assert projection.fully_grown is True
    assert projection.stage_label == "Full Bloom · Stage 6 of 6"
    assert projection.next_checkpoint_percent == 0
    assert projection.next_answer_value == ""
    assert projection.species_name == "Rose"
    assert projection.empty_message == (
        "All planted plants are at Full Bloom. Future Growth will be stored."
    )
    assert projection.all_plants_full_bloom is True
    assert projection.growth_destination is not None
    assert projection.growth_destination.kind == "stored_growth"

    mastery_target = GrowthTargetRef(GrowthTargetType.MASTERY, "rose")
    active_snapshot = build_growth_projects_snapshot(
        state_revision=1,
        stored_balance_units=1_250,
        wallet_balance_coins=0,
        full_bloom_species=("rose",),
        active_target=mastery_target,
    )
    projection = project_reviewer_hud(
        SimpleNamespace(
            active_plant=lambda: full,
            growth_projects_snapshot=lambda: active_snapshot,
        ),
        full_state,
    ).nurture
    destination = projection.growth_destination
    assert destination is not None
    assert (
        destination.kind,
        destination.target_type,
        destination.project_id,
    ) == ("stored_growth", "", "")
    assert destination.heading == "Stored Growth"
    assert destination.artwork_id == "stored_growth"
    assert destination.stored_growth_units == 1_250

    choose_snapshot = build_growth_projects_snapshot(
        state_revision=2,
        stored_balance_units=1_250,
        wallet_balance_coins=0,
        full_bloom_species=("rose",),
    )
    projection = project_reviewer_hud(
        SimpleNamespace(
            active_plant=lambda: full,
            growth_projects_snapshot=lambda: choose_snapshot,
        ),
        full_state,
    ).nurture
    assert projection.growth_destination is not None
    assert projection.growth_destination.kind == "stored_growth"
    assert projection.growth_destination.stored_growth_units == 1_250


def test_geometry_is_responsive_content_hugging_and_answer_bar_safe() -> None:
    assert reviewer_hud_width(1_280) == 296
    assert reviewer_hud_width(1_600) == 296
    assert reviewer_hud_width(2_000) == 296

    expanded = reviewer_hud_geometry(
        1_600,
        1_000,
        collapsed=False,
        dock="right",
        content_height=590,
    )
    assert expanded == (1_288, 44, 296, 590)

    short = reviewer_hud_geometry(
        1_280,
        500,
        collapsed=False,
        dock="right",
        content_height=700,
    )
    assert short == (968, 44, 296, 384)
    assert reviewer_hud_safe_bottom(509) == 437
    short_reviewer = reviewer_hud_geometry(
        1_280,
        509,
        collapsed=False,
        dock="right",
        content_height=700,
    )
    assert short_reviewer == (968, 44, 296, 393)
    assert short_reviewer[1] + short_reviewer[3] == (
        reviewer_hud_safe_bottom(509)
    )
    actual_controls = reviewer_hud_geometry(
        1_600,
        1_000,
        collapsed=False,
        dock="right",
        content_height=900,
        answer_controls_top=850,
    )
    assert actual_controls == (1_288, 44, 296, 806)
    assert reviewer_hud_safe_bottom(1_000, 850) == 850
    collapsed = reviewer_hud_geometry(1_200, 800, collapsed=True, dock="left")
    assert collapsed == (16, 44, HUD_COLLAPSED_WIDTH, HUD_COLLAPSED_HEIGHT)
    assert reviewer_hud_geometry(
        1_200, 800, collapsed=True, dock="left", content_height=88,
    ) == (16, 44, HUD_COLLAPSED_WIDTH, 88)
    assert DEFAULT_CONFIG["show_reviewer_hud"] is True
    assert DEFAULT_CONFIG["reviewer_hud_dock"] == "right"
    assert "content_height = 46 + body_height + reward_height" in WIDGET_SOURCE
    assert 'setProperty("hudRewardDockNaturalHeight", reward_height)' in WIDGET_SOURCE
    assert "self._body_contents.setMinimumWidth(0)" in WIDGET_SOURCE
    assert "QSizePolicy.Policy.Ignored" in WIDGET_SOURCE
    assert "chip.setMinimumWidth(0)" in WIDGET_SOURCE
    assert "effects_layout = QGridLayout(self._effects)" in WIDGET_SOURCE
    assert "effects_layout.addWidget(chip, 0, len(self._effect_chips))" in WIDGET_SOURCE
    assert "effects_layout.addWidget(\n            self._effects_overflow,\n            1," in WIDGET_SOURCE
    effect_chip_block = WIDGET_SOURCE.split(
        "for _index in range(2):",
        1,
    )[1].split("self._effects_overflow", 1)[0]
    assert "QSizePolicy.Policy.Ignored" in effect_chip_block
    assert "chip.setMaximumWidth" not in effect_chip_block
    assert "QSizePolicy.Policy.Expanding" in effect_chip_block
    assert "chip_layout.setContentsMargins(1, 0, 1, 0)" in effect_chip_block
    assert "chip_layout.setSpacing(1)" in effect_chip_block
    assert 'label.setProperty("hudEffectLabel", True)' in effect_chip_block
    clear_celebration = WIDGET_SOURCE.split(
        "def _clear_celebration",
        1,
    )[1].split("def update_session_totals", 1)[0]
    assert "if self._disposed" in clear_celebration


def test_widget_consumes_versioned_answer_control_rect_and_rejects_stale_viewport() -> None:
    class Host:
        def __init__(self, properties):
            self.properties = dict(properties)

        def property(self, name):
            return self.properties.get(name)

        def findChildren(self, _kind):
            return []

    measured = Host({
        "reviewerAnswerControlsSchemaVersion": 1,
        "reviewerAnswerControlsRect": [80, 648, 1_040, 88],
        "reviewerAnswerControlsTop": 648,
        "reviewerAnswerControlsClearance": 152,
        "reviewerAnswerControlsViewport": [1_200, 800],
        "reviewerAnswerControlsSource": "webengine-dom",
        "reviewerAnswerControlsMeasured": True,
    })
    receiver = SimpleNamespace()

    assert ReviewGardenHud._host_answer_controls_geometry(
        receiver,
        measured,
        1_200,
        800,
    ) == (648, (80, 648, 1_040, 88), 152, "webengine-dom")

    measured.properties["reviewerAnswerControlsViewport"] = [1_200, 700]
    assert ReviewGardenHud._host_answer_controls_geometry(
        receiver,
        measured,
        1_200,
        800,
    ) == (None, None, 72, "fallback")


def test_plant_art_bounds_remove_empty_canvas_without_mutating_source() -> None:
    assert padded_preview_bounds(
        (0.40, 0.20, 0.20, 0.60),
        padding=0.10,
    ) == pytest.approx((0.38, 0.14, 0.24, 0.72))
    assert padded_preview_bounds(None) == (0.0, 0.0, 1.0, 1.0)


def test_release_copy_helpers_cover_balance_markers_effects_and_zero_free_session() -> None:
    assert _compact_summary_label(SimpleNamespace(label="+13.5 growth")) == "+13.5 Growth"
    assert _compact_summary_label(SimpleNamespace(label="Booster +2")) == "Booster Potion +2"
    for value in (248, 9_999, 10_013, 999_999, 1_000_000):
        assert _format_coin_balance(value, exact_fits=False) == f"{value:,}"
    assert _format_coin_balance(1_200_000, exact_fits=False) == "1.2M"

    assert _checkpoint_marker_states(38, 50) == (
        "completed",
        "next",
        "future",
        "future",
    )
    assert _checkpoint_marker_states(38, 50, (20, 50, 80, 100)) == (
        "completed",
        "next",
        "future",
        "future",
    )
    assert _effect_display_text("Fertilizer 1h 24m") == "Fertilizer · 1h 24m"
    assert _effect_display_text("Booster · 38 cards") == (
        "Booster Potion · 38 cards"
    )
    assert _effect_display_text("Unrelated effect") == "Unrelated effect"
    assert _effect_overflow_label(1) == "1 more effect ›"
    assert _effect_overflow_label(3) == "3 more effects ›"
    assert _session_metric_labels(0, 0, 0) == ()
    assert _session_metric_labels(1_800, 0, 0) == ("+18 Growth",)
    assert _session_metric_labels(1_800, 2, 1) == (
        "+18 Growth",
        "+2 Coins",
        "1 Garden Find",
    )
    # A rapid answer may arrive while the prior Coin count-up is still showing
    # an intermediate value. Change detection must use the last committed
    # totals so the unchanged Coin category settles without animating again.
    assert _session_metric_increases(
        (1_800, 2, 0),
        (2_000, 2, 0),
    ) == (True, False, False)
    assert _session_coin_count(SimpleNamespace(
        footer_coin_count=0,
        garden_coins_earned=23,
    )) == 0
    assert _session_coin_count(SimpleNamespace(garden_coins_earned=23)) == 23
    assert _session_find_count(SimpleNamespace(
        footer_find_count=0,
        standard_finds=(SimpleNamespace(event_id="find-raw"),),
    )) == 0
    assert _session_find_count(SimpleNamespace(
        standard_finds=(SimpleNamespace(event_id="find-raw"),),
    )) == 1

    two_effects = NurtureProjection(
        True,
        effect_chips=("Fertilizer · 1h", "Booster · 38 cards"),
        effect_art_refs=("fertilizer_quality", "booster_potion"),
    )
    assert two_effects.visible_effect_chips == two_effects.effect_chips
    assert two_effects.visible_effect_art_refs == two_effects.effect_art_refs
    assert two_effects.effect_overflow_count == 0
    three_effects = NurtureProjection(
        True,
        effect_chips=(
            "Fertilizer · 1h",
            "Booster · 38 cards",
            "Garden decoration +1 growth",
        ),
    )
    assert three_effects.visible_effect_chips == three_effects.effect_chips[:2]
    assert three_effects.effect_overflow_count == 1


def test_ground_shadow_tracks_visible_stage_bounds_without_floating() -> None:
    seed = _ground_shadow_metrics("seed", 50, 120, 146)
    sprout = _ground_shadow_metrics("sprout", 60, 123, 146)
    young = _ground_shadow_metrics("young", 100, 126, 146)
    mature = _ground_shadow_metrics("mature", 130, 130, 146)

    assert seed == pytest.approx((70, 121, 7))
    assert sprout == pytest.approx((85, 124, 7))
    assert young == pytest.approx((135, 127, 7))
    assert mature == pytest.approx((175.5, 131, 7))
    assert seed[0] < sprout[0] < young[0] < mature[0]
    assert _ground_shadow_metrics("seed", 50, 145, 146)[1] == 142


def test_checkpoint_crossings_are_chronological_and_include_multiple_markers() -> None:
    previous = SimpleNamespace(
        progress_percent=10,
        next_checkpoint_percent=25,
        next_checkpoint_reward_coins=2,
        fully_grown=False,
    )
    final = SimpleNamespace(
        progress_percent=55,
        next_checkpoint_percent=75,
        fully_grown=False,
    )
    assert ReviewGardenHud._crossed_checkpoints(final, previous) == (25, 50)

    stage_boundary_previous = SimpleNamespace(
        progress_percent=82,
        next_checkpoint_percent=100,
        fully_grown=False,
    )
    next_stage = SimpleNamespace(
        progress_percent=8,
        next_checkpoint_percent=25,
        fully_grown=False,
    )
    assert ReviewGardenHud._crossed_checkpoints(
        next_stage,
        stage_boundary_previous,
    ) == (100,)

    redirected_later_stage = SimpleNamespace(
        progress_percent=55,
        next_checkpoint_percent=75,
        fully_grown=False,
    )
    assert ReviewGardenHud._crossed_checkpoints(
        redirected_later_stage,
        stage_boundary_previous,
    ) == (100, 25, 50)
    assert _checkpoint_sequence_is_chronological((100, 25, 50))
    assert _checkpoint_sequence_is_chronological((75, 100, 25, 50))
    assert not _checkpoint_sequence_is_chronological((75, 25))


def test_widget_consumes_the_canonical_reward_bundle_shape() -> None:
    hero = RewardItemProjection(
        event_id="find-1",
        kind=RewardHero.GARDEN_FIND,
        title="Moonlit Sprout",
        category_label="Standard Find",
        growth_units=4_000,
        garden_coins=4,
        rarity="common",
        artwork_ref="/art/moonlit-sprout.webp",
    )
    bundle = RewardBundleProjection("answer-1", "2026-08-28T12:00:00Z", (hero,))
    assert _hero_kind(bundle) == "garden_find"
    assert _hero_amounts(bundle) == (4_000, 4)
    assert _bundle_growth_units(bundle) == 4_000
    assert ReviewGardenHud._collapsed_coin_delta(bundle) == 4
    additional = RewardItemProjection(event_id="coin-2", kind=RewardHero.COIN_OR_BOOSTER,
                                      title="Checkpoint reward", category_label="Coins", garden_coins=3)
    mixed = RewardBundleProjection("answer-mixed", bundle.occurred_at, (hero, additional))
    assert ReviewGardenHud._collapsed_coin_delta(mixed) == 7

    signature = inspect.signature(ReviewGardenHud.present_reward)
    assert "reveal" in signature.parameters
    assert signature.parameters["reveal"].default is True
    committed = inspect.signature(ReviewGardenHud.present_committed_result)
    assert committed.parameters["applied_growth_units"].default == 0
    assert committed.parameters["reveal"].default is True
    assert hasattr(ReviewGardenHud, "update_session_totals")
    assert hasattr(ReviewGardenHud, "update_projection")


def test_named_find_art_uses_the_shared_item_resolver_in_reviewer_ui() -> None:
    assert 'getattr(hero, "artwork_ref", "")' in REVIEWER_HOOK_SOURCE
    assert 'resolver_names = (' in REVIEWER_HOOK_SOURCE
    assert '"resolve_item_asset", "resolve_garden_feature_preview_asset", "resolve_scenery_preview_asset"' in REVIEWER_HOOK_SOURCE
    assert 'asset_category == "ui" and asset_key' in REVIEWER_HOOK_SOURCE
    assert 'hero, "reward_type", ""' in REVIEWER_HOOK_SOURCE
    assert '"garden_pouch": "Garden Pouch artwork"' in REVIEWER_HOOK_SOURCE
    assert '"morning_dew": "Morning Dew artwork"' in REVIEWER_HOOK_SOURCE
    assert "self._reward_art.setFixedSize(52, 52)" in WIDGET_SOURCE
    assert "if isinstance(hero, str)" in REVIEWER_HOOK_SOURCE
    assert 'icon.setProperty("hudEffectArtwork", True)' in WIDGET_SOURCE
    assert "icon.setFixedSize(18, 18)" in WIDGET_SOURCE
    assert "icon.setAlignment(Qt.AlignmentFlag.AlignCenter)" in WIDGET_SOURCE
    assert '"hudEffectUsesItemArt"' in WIDGET_SOURCE
    assert "self._effect_art_pixmap(artwork_ref)" in WIDGET_SOURCE
    assert '"hudRewardSummaryArtworkRef"' in WIDGET_SOURCE
    assert '"hudRewardSummaryUsesItemArt"' in WIDGET_SOURCE
    assert "summary if summary is not None else artwork_ref" in WIDGET_SOURCE
    alpha_crop = WIDGET_SOURCE.split("def _alpha_cropped_pixmap", 1)[1].split(
        "def _session_metric_labels", 1
    )[0]
    assert "pixmap.mask().boundingRect()" in alpha_crop
    assert "pixelColor" not in alpha_crop


def test_reward_amounts_stay_on_the_hero_and_overflow_remains_inspectable() -> None:
    stage = RewardItemProjection(
        event_id="stage-1",
        kind=RewardHero.STAGE_CHANGE,
        title="Rose",
        category_label="Stage change",
    )
    secondary = (
        RewardItemProjection(
            event_id="growth-1",
            kind=RewardHero.ROUTINE_GROWTH,
            title="Growth earned",
            category_label="Routine Growth",
            growth_units=400,
        ),
        RewardItemProjection(
            event_id="find-1",
            kind=RewardHero.GARDEN_FIND,
            title="Moonlit Sprout",
            category_label="Standard Find",
        ),
        RewardItemProjection(
            event_id="booster-1",
            kind=RewardHero.COIN_OR_BOOSTER,
            title="Booster Potion",
            category_label="Garden reward",
            inventory_items=(("booster_potion", 1),),
        ),
        RewardItemProjection(
            event_id="checkpoint-1",
            kind=RewardHero.CHECKPOINT,
            title="Rose",
            category_label="Checkpoint reached",
        ),
    )
    bundle = RewardBundleProjection(
        "answer-overflow",
        "2026-08-28T12:00:00Z",
        (stage, *secondary),
    )

    assert _hero_amounts(bundle) == (0, 0)
    assert len(_all_secondary_items(bundle)) == 4
    assert len(bundle.visible_summaries) == 2
    assert tuple(summary.label for summary in bundle.visible_summaries) == (
        "1 Garden Find",
        "Checkpoint reached",
    )
    booster_summary = next(
        summary
        for summary in bundle.hidden_summaries
        if summary.key.startswith("inventory:")
    )
    assert booster_summary.artwork_ref == "booster_potion"
    assert bundle.more_label == "Details ›"


def test_inventory_quantities_are_visible_for_hero_secondary_and_plural_copy() -> None:
    booster = RewardItemProjection(
        event_id="booster-1",
        kind=RewardHero.COIN_OR_BOOSTER,
        title="Booster Potion",
        category_label="Garden reward",
        inventory_items=(("booster_potion", 2),),
    )
    bundle = RewardBundleProjection(
        "answer-inventory",
        "2026-08-28T12:00:00Z",
        (booster,),
    )

    assert booster.learner_inventory_labels == ("+2 Booster Potions",)
    assert _hero_inventory_labels(bundle) == ("+2 Booster Potions",)
    assert _secondary_label(booster) == "Booster Potion · +2 Booster Potions"


def test_full_bloom_compact_projection_suppresses_only_same_plant_stage_copy() -> None:
    hero = RewardItemProjection(
        event_id="bloom-1",
        kind=RewardHero.FULL_BLOOM,
        title="Rose",
        category_label="Full Bloom",
        garden_coins=14,
        plant_id="plant-1",
        plant_name="Rose",
        plant_class="Heritage Rose",
    )
    mature = RewardItemProjection(
        event_id="stage-mature",
        kind=RewardHero.STAGE_CHANGE,
        title="Rose",
        category_label="Stage change",
        detail="Reached Mature",
        plant_id="plant-1",
        plant_name="Rose",
    )
    items = (
        mature,
        RewardItemProjection(
            event_id="growth-1",
            kind=RewardHero.ROUTINE_GROWTH,
            title="Growth earned",
            category_label="Routine Growth",
            growth_units=4_000,
        ),
        RewardItemProjection(
            event_id="discovery-1",
            kind=RewardHero.ENVIRONMENT_DISCOVERY,
            title="Clear Skies",
            category_label="Discovery",
        ),
        RewardItemProjection(
            event_id="discovery-2",
            kind=RewardHero.ENVIRONMENT_DISCOVERY,
            title="Verdant Twilight",
            category_label="Discovery",
        ),
        RewardItemProjection(
            event_id="find-1",
            kind=RewardHero.GARDEN_FIND,
            title="Moonlit Sprout",
            category_label="Standard Find",
        ),
        RewardItemProjection(
            event_id="booster-1",
            kind=RewardHero.COIN_OR_BOOSTER,
            title="Booster Potion",
            category_label="Garden reward",
            inventory_items=(("booster_potion", 1),),
        ),
    )
    bundle = RewardBundleProjection(
        "answer-full-bloom",
        "2026-08-28T12:00:00Z",
        (hero, *items),
    )

    assert bundle.compact.eyebrow == "MILESTONE REACHED"
    assert bundle.compact.hero_title == "Heritage Rose reached full bloom"
    assert bundle.compact.hero_subtitle == ""
    assert tuple(summary.label for summary in bundle.visible_summaries) == (
        "1 Garden Find",
        "2 Garden discoveries",
    )
    assert bundle.more_label == "Details ›"
    compact_event_ids = {
        event_id
        for summary in (*bundle.visible_summaries, *bundle.hidden_summaries)
        for event_id in summary.event_ids
    }
    assert "stage-mature" not in compact_event_ids
    assert any(item.event_id == "stage-mature" for item in bundle.all_items)

    reconciled = RewardBundleProjection(
        "answer-full-bloom-coins",
        "2026-08-28T12:00:00Z",
        (hero, *items),
        displayed_coin_delta=23,
    )
    assert _hero_amounts(reconciled) == (0, 23)
    assert ReviewGardenHud._collapsed_coin_delta(reconciled) == 23
    reconciled_zero = RewardBundleProjection(
        "answer-full-bloom-zero-coins",
        "2026-08-28T12:00:00Z",
        (hero, *items),
        displayed_coin_delta=0,
    )
    assert _hero_amounts(reconciled_zero) == (0, 0)
    assert ReviewGardenHud._collapsed_coin_delta(reconciled_zero) == 0


def test_committed_entrypoint_respects_an_explicit_zero_applied_growth() -> None:
    animated: list[int] = []
    fake = SimpleNamespace(
        _seen_bundle_ids=set(),
        _reward_history=deque(),
        _reward_history_page=0,
        _collapsed=False,
        _unseen_major=0,
        _current_reward=None,
        _reward_minimum_hold_elapsed=False,
        _reward_details_expanded=False,
        setProperty=lambda *_args: None,
        _sync_history_rows=lambda: None,
        _sync_unseen_badge=lambda: None,
        animate_growth_delta=animated.append,
    )
    find = RewardBundleProjection(
        "answer-find",
        "2026-08-28T12:00:00Z",
        (RewardItemProjection(
            event_id="find-1",
            kind=RewardHero.GARDEN_FIND,
            title="Moonlit Sprout",
            category_label="Standard Find",
            growth_units=4_000,
        ),),
    )

    assert ReviewGardenHud.present_committed_result(
        fake,
        find,
        applied_growth_units=0,
        reveal=False,
    )
    assert animated == []
    assert tuple(fake._reward_history) == (find,)


def test_routine_session_feedback_releases_only_for_the_current_projection() -> None:
    properties: dict[str, object] = {}
    flushes: list[str] = []
    fake = SimpleNamespace(
        _disposed=False,
        _revision=7,
        _routine_projection_feedback_active=True,
        setProperty=properties.__setitem__,
        _flush_deferred_checkpoint_feedback=lambda: flushes.append("released"),
    )

    ReviewGardenHud._finish_routine_projection_feedback(fake, 6)
    assert flushes == []
    assert fake._routine_projection_feedback_active is True

    ReviewGardenHud._finish_routine_projection_feedback(fake, 7)
    assert flushes == ["released"]
    assert fake._routine_projection_feedback_active is False
    assert properties == {
        "hudRoutineProjectionFeedbackActive": False,
        "hudRoutineSessionReleasedAfterProgress": True,
    }


def test_routine_answers_remain_reconciled_with_an_early_major_reward() -> None:
    major = RewardBundleProjection(
        "answer-major",
        "2026-08-28T12:00:00Z",
        (RewardItemProjection(
            event_id="find-1",
            kind=RewardHero.GARDEN_FIND,
            title="Moonlit Sprout",
            category_label="Standard Find",
        ),),
    )
    fake = SimpleNamespace(
        _seen_bundle_ids=set(),
        _reward_history=deque(),
        _reward_history_page=0,
        _collapsed=False,
        _unseen_major=0,
        _current_reward=None,
        _reward_minimum_hold_elapsed=False,
        _reward_details_expanded=False,
        setProperty=lambda *_args: None,
        _sync_history_rows=lambda: None,
        _sync_unseen_badge=lambda: None,
        animate_growth_delta=lambda _units: None,
    )

    assert ReviewGardenHud.present_reward(fake, major, reveal=False)
    for index in range(25):
        routine = RewardBundleProjection(
            f"answer-routine-{index}",
            "2026-08-28T12:00:00Z",
            (RewardItemProjection(
                event_id=f"growth-{index}",
                kind=RewardHero.ROUTINE_GROWTH,
                title="Growth earned",
                category_label="Routine Growth",
            ),),
        )
        assert ReviewGardenHud.present_reward(fake, routine, reveal=False)

    assert len(fake._reward_history) == 26
    assert fake._reward_history[0] is major
    assert tuple(bundle.bundle_id for bundle in tuple(fake._reward_history)[-2:]) == (
        "answer-routine-23",
        "answer-routine-24",
    )


def test_committed_major_reward_is_idempotent_and_presented_while_collapsed() -> None:
    presented = []
    bundle = RewardBundleProjection(
        "answer-major-collapsed",
        "2026-08-28T12:00:00Z",
        (RewardItemProjection(
            event_id="find-collapsed",
            kind=RewardHero.GARDEN_FIND,
            title="Moonlit Sprout",
            category_label="Standard Find",
        ),),
    )
    fake = SimpleNamespace(
        _seen_bundle_ids=set(),
        _reward_history=deque(),
        _reward_history_page=0,
        _collapsed=True,
        _unseen_major=0,
        _current_reward=None,
        _reward_minimum_hold_elapsed=False,
        _reward_details_expanded=False,
        _reward_queue=deque(),
        _enqueue_reward_reveal=presented.append,
        setProperty=lambda *_args: None,
        _sync_history_rows=lambda: None,
        _sync_unseen_badge=lambda: None,
        animate_growth_delta=lambda _units: None,
    )

    assert ReviewGardenHud.present_committed_result(fake, bundle)
    assert ReviewGardenHud.present_committed_result(fake, bundle)
    assert tuple(fake._reward_history) == (bundle,)
    assert not fake._reward_queue
    assert presented == [bundle]
    assert fake._unseen_major == 1


def test_reward_archives_only_after_minimum_hold_and_next_distinct_commit() -> None:
    reveal_properties: dict[str, object] = {}
    hud_properties: dict[str, object] = {}
    archives: list[str] = []
    current = object()
    readable = SimpleNamespace(
        _current_reward=current,
        _collapsed=True,
        _collapsed_feedback=SimpleNamespace(major_pending=True),
        _reward_minimum_hold_elapsed=False,
        _reward_next_commit_seen=False,
        _reward_details_expanded=False,
        _history_reward_inspection=None,
        _reward_reveal_state="celebrating",
        _reward_reveal=SimpleNamespace(setProperty=reveal_properties.__setitem__),
        setProperty=hud_properties.__setitem__,
        _archive_current_reward=lambda: archives.append("archived"),
    )

    ReviewGardenHud._mark_reward_hold_elapsed(readable)

    assert readable._current_reward is current
    assert readable._reward_minimum_hold_elapsed is True
    assert readable._reward_reveal_state == "settled"
    assert hud_properties == {
        "hudRewardMinimumHoldElapsed": True,
        "hudRewardRevealState": "settled",
    }
    assert reveal_properties == {"rewardRevealState": "settled"}
    assert archives == []

    readable._reward_next_commit_seen = True
    assert ReviewGardenHud._maybe_archive_current_reward(readable) is False
    readable._collapsed_feedback.major_pending = False
    assert ReviewGardenHud._maybe_archive_current_reward(readable) is True
    assert archives == ["archived"]


def test_zero_reward_commit_advances_reveal_once_by_stable_event_id() -> None:
    archives: list[str] = []
    properties: dict[str, object] = {}
    fake = SimpleNamespace(
        _seen_commit_ids=set(),
        _collapsed=False,
        _current_reward=object(),
        _reward_minimum_hold_elapsed=True,
        _reward_next_commit_seen=False,
        _reward_details_expanded=False,
        _history_reward_inspection=None,
        setProperty=properties.__setitem__,
        _archive_current_reward=lambda: archives.append("archived"),
    )

    assert ReviewGardenHud.notify_committed_card(fake, "answer:no-reward") is True
    assert fake._reward_next_commit_seen is True
    assert properties["hudRewardNextCommitSeen"] is True
    assert archives == ["archived"]

    fake._current_reward = object()
    fake._reward_next_commit_seen = False
    assert ReviewGardenHud.notify_committed_card(fake, "answer:no-reward") is True
    assert fake._reward_next_commit_seen is False
    assert archives == ["archived"]


def test_early_next_commit_waits_for_hold_and_details_pause_archiving() -> None:
    current = object()
    archives: list[str] = []

    new_bundle = RewardBundleProjection(
        "answer-after-readable-reward",
        "2026-08-28T12:00:01Z",
        (RewardItemProjection(
            event_id="growth-after-readable-reward",
            kind=RewardHero.ROUTINE_GROWTH,
            title="Growth earned",
            category_label="Routine Growth",
        ),),
    )
    committed = SimpleNamespace(
        _seen_bundle_ids=set(),
        _current_reward=current,
        _reward_minimum_hold_elapsed=False,
        _reward_next_commit_seen=False,
        _reward_details_expanded=True,
        _history_reward_inspection=None,
        _reward_reveal_state="details_open",
        _reward_reveal=SimpleNamespace(setProperty=lambda *_args: None),
        _archive_current_reward=lambda: archives.append("archived"),
        _reward_history=deque(),
        _reward_history_page=0,
        _collapsed=False,
        _unseen_major=0,
        setProperty=lambda *_args: None,
        _sync_history_rows=lambda: None,
        animate_growth_delta=lambda _units: None,
    )

    assert ReviewGardenHud.present_committed_result(
        committed,
        new_bundle,
        reveal=False,
    )
    assert committed._reward_next_commit_seen is True
    assert archives == []
    assert tuple(committed._reward_history) == (new_bundle,)

    ReviewGardenHud._mark_reward_hold_elapsed(committed)
    assert archives == []
    committed._reward_details_expanded = False
    assert ReviewGardenHud._maybe_archive_current_reward(committed) is True
    assert archives == ["archived"]

    # A replay of the same stable bundle returns before it can satisfy or
    # repeat any lifecycle transition.
    assert ReviewGardenHud.present_committed_result(
        committed,
        new_bundle,
        reveal=False,
    )
    assert archives == ["archived"]


def test_collapsing_preserves_the_mounted_reward_and_running_hold() -> None:
    current = object()
    visibility: list[tuple[str, bool]] = []
    timer_stops: list[str] = []
    fake = SimpleNamespace(
        _collapsed=False,
        _current_reward=current,
        _reward_queue=deque(),
        _expanded=SimpleNamespace(
            setVisible=lambda visible: visibility.append(("expanded", visible))
        ),
        _collapsed_tab=SimpleNamespace(
            setVisible=lambda visible: visibility.append(("tab", visible))
        ),
        _reward_timer=SimpleNamespace(
            stop=lambda: timer_stops.append("stopped")
        ),
        setProperty=lambda *_args: None,
        _sync_reward_dock_visibility=lambda: None,
        reposition=lambda: None,
    )

    ReviewGardenHud.set_collapsed(fake, True)
    ReviewGardenHud.set_collapsed(fake, False)

    assert fake._current_reward is current
    assert tuple(fake._reward_queue) == ()
    assert timer_stops == []
    assert visibility == [
        ("expanded", False),
        ("tab", True),
        ("expanded", True),
        ("tab", False),
    ]


def test_reward_remount_restores_the_readable_event_without_representing_it() -> None:
    current = RewardBundleProjection(
        "answer-readable-remount",
        "2026-08-28T12:00:00Z",
        (RewardItemProjection(
            event_id="find-readable-remount",
            kind=RewardHero.GARDEN_FIND,
            title="Moonlit Sprout",
            category_label="Standard Find",
        ),),
    )
    queued = RewardBundleProjection(
        "answer-queued-remount",
        "2026-08-28T12:00:01Z",
        (RewardItemProjection(
            event_id="checkpoint-queued-remount",
            kind=RewardHero.CHECKPOINT,
            title="50% checkpoint",
            category_label="Checkpoint",
        ),),
    )
    inline_state = {"major_id": current.bundle_id, "current": {"caption": "Stored"}, "remaining_ms": 450}
    restored_inline = []
    exported = SimpleNamespace(
        _collapsed_feedback=SimpleNamespace(export_state=lambda: inline_state),
        _history_reward_inspection=None,
        _current_reward=current,
        _reward_minimum_hold_elapsed=True,
        _reward_details_expanded=False,
        _reward_next_commit_seen=False,
        _reward_reveal_state="settled",
        _reward_timer=SimpleNamespace(remainingTime=lambda: -1),
        _checkpoint_pending_bundles=[],
        _reward_queue=deque((current, queued)),
        _seen_bundle_ids={current.bundle_id, queued.bundle_id},
        _reward_history=deque((current, queued)),
        _unseen_major=1,
    )

    snapshot = ReviewGardenHud.export_reward_state(exported)
    assert snapshot["current"] == {
        "bundle": current,
        "minimum_hold_elapsed": True,
        "details_expanded": False,
        "next_commit_seen": False,
        "reveal_state": "settled",
        "hold_remaining_ms": 0,
    }
    assert tuple(snapshot["pending"]) == (queued,)

    presentations: list[tuple[object, dict[str, object]]] = []
    restored = SimpleNamespace(
        _collapsed_feedback=SimpleNamespace(restore_state=restored_inline.append, resume=lambda: None),
        _seen_bundle_ids=set(),
        _reward_history=deque(),
        _reward_history_page=0,
        _checkpoint_pending_bundles=[],
        _reward_queue=deque(),
        _unseen_major=0,
        _collapsed=False,
        _current_reward=None,
        _history_reward_inspection=None,
        setProperty=lambda *_args: None,
        _sync_history_rows=lambda: None,
        _sync_unseen_badge=lambda: None,
        _sync_reward_dock_visibility=lambda: None,
        _show_reward=lambda bundle, **options: presentations.append(
            (bundle, options)
        ),
    )

    ReviewGardenHud.restore_reward_state(restored, snapshot)

    assert snapshot["collapsed_feedback"] == inline_state
    assert restored_inline == [inline_state]
    assert presentations == [(
        current,
        {
            "expanded": False,
            "presentation": "restored",
            "minimum_hold_elapsed": True,
            "next_commit_seen": False,
            "reveal_state": "settled",
            "hold_remaining_ms": 0,
        },
    )]
    assert tuple(restored._reward_queue) == (queued,)


def test_history_reward_inspection_suspends_and_restores_the_live_event() -> None:
    live = RewardBundleProjection(
        "answer-live-readable",
        "2026-08-28T12:00:01Z",
        (RewardItemProjection(
            event_id="find-live-readable",
            kind=RewardHero.GARDEN_FIND,
            title="Current Find",
            category_label="Standard Find",
        ),),
    )
    historical = RewardBundleProjection(
        "answer-historical-details",
        "2026-08-28T11:59:59Z",
        (RewardItemProjection(
            event_id="bloom-historical-details",
            kind=RewardHero.FULL_BLOOM,
            title="Full Bloom achieved",
            category_label="Full Bloom",
        ),),
    )
    presentations: list[tuple[object, dict[str, object]]] = []
    timer_stops: list[str] = []
    fake = SimpleNamespace(
        _visible_history_bundles=(historical,),
        _reward_history_panel=SimpleNamespace(hide=lambda: None),
        _session_footer=SimpleNamespace(setProperty=lambda *_args: None),
        _set_session_history_chevron=lambda _expanded: None,
        _current_reward=live,
        _reward_minimum_hold_elapsed=True,
        _reward_details_expanded=False,
        _reward_next_commit_seen=False,
        _reward_reveal_state="settled",
        _history_reward_inspection=None,
        _reward_timer=SimpleNamespace(
            remainingTime=lambda: -1,
            stop=lambda: timer_stops.append("stopped"),
        ),
        _reward_queue=deque(),
        _collapsed=False,
        setProperty=lambda *_args: None,
        _show_reward=lambda bundle, **options: presentations.append(
            (bundle, options)
        ),
    )

    ReviewGardenHud._reopen_history_reward(fake, 0)

    assert fake._history_reward_inspection == {
        "bundle": live,
        "minimum_hold_elapsed": True,
        "details_expanded": False,
        "next_commit_seen": False,
        "reveal_state": "settled",
        "hold_remaining_ms": 0,
    }
    assert tuple(fake._reward_queue) == ()
    assert presentations[-1] == (
        historical,
        {
            "expanded": True,
            "presentation": "history",
            "minimum_hold_elapsed": True,
        },
    )

    ReviewGardenHud._close_history_reward_inspection(fake)

    assert fake._history_reward_inspection is None
    assert presentations[-1] == (
        live,
        {
            "expanded": False,
            "presentation": "restored",
            "minimum_hold_elapsed": True,
            "next_commit_seen": False,
            "reveal_state": "settled",
            "hold_remaining_ms": 0,
        },
    )
    assert timer_stops == ["stopped"]


def test_duplicate_commit_does_not_disturb_history_inspection() -> None:
    bundle = RewardBundleProjection(
        "answer-already-seen-during-history",
        "2026-08-28T12:00:00Z",
        (RewardItemProjection(
            event_id="find-already-seen-during-history",
            kind=RewardHero.GARDEN_FIND,
            title="Moonlit Sprout",
            category_label="Standard Find",
        ),),
    )
    closes: list[str] = []
    fake = SimpleNamespace(
        _seen_bundle_ids={bundle.bundle_id},
        _history_reward_inspection={"bundle": object()},
        _close_history_reward_inspection=lambda: closes.append("closed"),
    )

    assert ReviewGardenHud.present_committed_result(fake, bundle)
    assert closes == []


def test_mixed_reward_bundle_delays_for_its_checkpoint_item() -> None:
    find = RewardItemProjection(
        event_id="find-1",
        kind=RewardHero.GARDEN_FIND,
        title="Moonlit Sprout",
        category_label="Standard Find",
    )
    checkpoint = RewardItemProjection(
        event_id="checkpoint-1",
        kind=RewardHero.CHECKPOINT,
        title="Rose",
        category_label="Checkpoint reached",
    )
    bundle = RewardBundleProjection(
        "answer-mixed",
        "2026-08-28T12:00:00Z",
        (find, checkpoint),
    )

    assert _hero_kind(bundle) == "garden_find"
    assert _bundle_has_kind(bundle, "checkpoint") is True


def test_native_component_has_stable_audit_targets_and_no_toast_stack() -> None:
    for object_name in (
        "ankiGardenReviewerHud",
        "reviewerHudHeader",
        "reviewerHudBodyScroll",
        "reviewerHudTodayCard",
        "reviewerHudPlantCard",
        "reviewerHudPlantClass",
        "reviewerHudPlantName",
        "reviewerHudCheckpointTrack",
        "reviewerHudCheckpointDistanceRow",
        "reviewerHudNextAnswerLabel",
        "reviewerHudRewardDock",
        "reviewerHudRewardDockSurface",
        "reviewerHudRewardScroll",
        "reviewerHudRewardReveal",
        "reviewerHudRewardAccent",
        "reviewerHudRewardHeading",
        "reviewerHudRewardDetailsToggle",
        "reviewerHudRewardEyebrow",
        "reviewerHudRewardSubtitle",
        "reviewerHudRewardSummaryChip0",
        "reviewerHudRewardSummaryChip1",
        "reviewerHudRewardDetails",
        "reviewerHudRewardDivider",
        "reviewerHudSessionFooter",
        "reviewerHudRewardHistory",
        "reviewerHudCollapsedTab",
    ):
        assert object_name in WIDGET_SOURCE
    assert "ankiGardenRewardToast" not in WIDGET_SOURCE
    assert "HUD_TOP_MARGIN," in WIDGET_SOURCE.split(
        "from .reviewer_hud import (", 1
    )[1].split(")", 1)[0]
    assert "reward close" not in WIDGET_SOURCE.casefold()
    assert "body.addStretch" not in WIDGET_SOURCE
    assert "deque(maxlen=_REWARD_QUEUE_LIMIT)" not in WIDGET_SOURCE
    art_update = WIDGET_SOURCE.split("def _update_plant_art", 1)[1].split(
        "def _fade_art_in",
        1,
    )[0]
    assert art_update.index("_collapsed_ring.set_progress") < art_update.index(
        "if key == self._art_key"
    )
    assert "animate_checkpoint_crossing" in WIDGET_SOURCE
    assert "animate_checkpoint_sequence" in WIDGET_SOURCE
    assert "when_checkpoint_reached" in WIDGET_SOURCE
    assert 'self.setProperty("markerShape", "diamond-tick")' in WIDGET_SOURCE
    assert 'self.setProperty("interactive", False)' in WIDGET_SOURCE
    assert 'self.setProperty("currentPositionHandleVisible", False)' in WIDGET_SOURCE
    checkpoint_paint = WIDGET_SOURCE.split(
        "class CheckpointTrack",
        1,
    )[1].split("class _MiniProgressRing", 1)[0]
    assert "painter.rotate(45.0)" in checkpoint_paint
    assert "painter.drawRoundedRect" in checkpoint_paint
    assert "painter.drawEllipse" in checkpoint_paint
    assert "_reopen_history_reward" in WIDGET_SOURCE
    assert 'setObjectName("reviewerHudRewardMore")' not in WIDGET_SOURCE
    assert "reviewerHudRewardDisclosureChevron" not in WIDGET_SOURCE
    assert (_COMPACT_REWARD_MIN_HEIGHT, _COMPACT_REWARD_MAX_HEIGHT) == (130, 150)
    assert "self._reward_summary_chips: list[_ElidedLabel]" in WIDGET_SOURCE
    assert "visible_summaries[:2]" in WIDGET_SOURCE
    assert "self._reward_details_toggle.setMinimumWidth(" in WIDGET_SOURCE
    assert "self._reward_details_toggle.setMinimumHeight(28)" in WIDGET_SOURCE
    assert 'self._reward_details_toggle.setText("Reward details ›")' in WIDGET_SOURCE
    assert 'details_text = "Hide details"' in WIDGET_SOURCE
    assert 'self._reward_reveal.setProperty("rewardDetailEventIds", detail_event_ids)' in WIDGET_SOURCE
    assert "self._reward_timer.timeout.connect(self._mark_reward_hold_elapsed)" in WIDGET_SOURCE
    hold_elapsed = WIDGET_SOURCE.split(
        "def _mark_reward_hold_elapsed",
        1,
    )[1].split("def _current_reward_reveal_state", 1)[0]
    assert "_maybe_archive_current_reward" in hold_elapsed
    assert "class _PreferredHeightScrollArea" in WIDGET_SOURCE
    assert "self._reward_scroll.set_preferred_height(target)" in WIDGET_SOURCE
    assert "layout.heightForWidth(natural_width)" in WIDGET_SOURCE
    assert "self._build_reward_dock(expanded_layout)" in WIDGET_SOURCE
    assert "_apply_full_bloom_override" in WIDGET_SOURCE
    assert "_apply_stage_change_override" in WIDGET_SOURCE
    assert 'setProperty("titleAnchorStable", True)' in WIDGET_SOURCE
    assert 'setProperty("fullBloomSettled", False)' in WIDGET_SOURCE
    assert "self._reward_dock.hide()" in WIDGET_SOURCE
    assert "divider_visible = scroll_visible and footer_visible" in WIDGET_SOURCE
    assert "animate = bool(animate and self._animations_enabled)" in WIDGET_SOURCE
    assert "delta = target - committed_before" in WIDGET_SOURCE
    assert "revision != self._coin_feedback_revision" in WIDGET_SOURCE
    assert "revision != self._growth_feedback_revision" in WIDGET_SOURCE
    assert "revision != self._today_feedback_revision" in WIDGET_SOURCE
    assert "_PROJECTION_APPLY_DELAY_MS = 220" in WIDGET_SOURCE
    assert "_ROUTINE_SESSION_RELEASE_MS = _PROJECTION_APPLY_DELAY_MS + _PROGRESS_FILL_MS" in WIDGET_SOURCE
    assert '"hudRoutineSessionReleaseDelayMs", _ROUTINE_SESSION_RELEASE_MS' in WIDGET_SOURCE
    assert "def _finish_routine_projection_feedback" in WIDGET_SOURCE
    assert '"hudRoutineSessionUpdateDeferred"' in WIDGET_SOURCE
    assert "_NEXT_PROJECTION_RESTORE_MS = 850" in WIDGET_SOURCE
    assert "revision != self._revision" in WIDGET_SOURCE
    assert "def present_committed_result" in WIDGET_SOURCE
    assert "def _flush_deferred_checkpoint_feedback" in WIDGET_SOURCE
    assert "def export_reward_state" in WIDGET_SOURCE
    assert "def restore_reward_state" in WIDGET_SOURCE
    assert WIDGET_SOURCE.count("self._build_shell()") == 1

    plant_builder = WIDGET_SOURCE.split("def _build_plant", 1)[1].split(
        "def _build_reward_dock",
        1,
    )[0]
    assert "layout.addWidget(self._checkpoint_reward_row)" in plant_builder
    assert "layout.addWidget(self._next_answer)" not in plant_builder
    assert "self._next_answer.hide()" in plant_builder
    assert "metadata.addWidget(self._bed)" not in plant_builder


def test_release_revision_feedback_and_numeric_roles_are_wired() -> None:
    assert '.setProperty("tabularNumerals", True)' not in WIDGET_SOURCE
    for widget_name in (
        "self._coin_balance",
        "self._coin_delta",
        "self._today_value",
        "self._today_detail",
        "self._percent",
        "self._checkpoint",
        "self._checkpoint_estimate",
        "self._next_answer_value",
        "self._checkpoint_reward",
        "self._effects_overflow",
        "self._effect_details",
        "self._reward_growth",
        "self._reward_coins",
    ):
        assert f"apply_tabular_numerals({widget_name})" in WIDGET_SOURCE

    receipt_source = Path(__file__).parents[1].joinpath("ankigarden/ui/reward_receipt.py").read_text()
    assert "apply_tabular_numerals(amount)" in receipt_source
    assert "surface.insertWidget(0, self._session_footer)" in WIDGET_SOURCE

    effect_overflow = WIDGET_SOURCE.split(
        "def _effect_overflow_label",
        1,
    )[1].split("def _session_metric_labels", 1)[0]
    assert "format_quantity(normalized, 'more effect', 'more effects')" in effect_overflow
    footer_builder = WIDGET_SOURCE.split("def _build_reward_dock", 1)[1].split(
        "def _build_collapsed",
        1,
    )[0]
    assert 'setObjectName("reviewerHudSessionChevron")' in footer_builder
    assert "self._session_history_chevron.hide()" in footer_builder
    history_sync = WIDGET_SOURCE.split("def _sync_history_rows", 1)[1].split(
        "def _advance_reward_history_page",
        1,
    )[0]
    assert "self._session_history_chevron.setVisible(available)" in history_sync

    full_bloom_override = WIDGET_SOURCE.split(
        "def _apply_full_bloom_override",
        1,
    )[1].split("def _apply_projected_full_bloom_settled", 1)[0]
    assert "self._select_plant.show()" not in full_bloom_override
    projected_full_bloom = WIDGET_SOURCE.split(
        "def _apply_projected_full_bloom_settled",
        1,
    )[1].split("def _apply_stage_change_override", 1)[0]
    assert "self._effects.hide()" in projected_full_bloom
    assert "elif nurture.fully_grown:" in WIDGET_SOURCE
    assert "self._select_plant.clicked.connect(self._select_another_plant)" in WIDGET_SOURCE
    select_action = WIDGET_SOURCE.split(
        "def _select_another_plant",
        1,
    )[1].split("def _open_current_reward", 1)[0]
    assert "_call(self._on_select_plant)" in select_action
    assert "_on_open_garden" not in select_action
    assert REVIEWER_HOOK_SOURCE.count(
        "on_select_plant=self._select_another_plant_from_reviewer_hud"
    ) == 2
    assert REVIEWER_HOOK_SOURCE.count(
        "on_choose_plant=self._choose_plant_from_reviewer_hud"
    ) == 2
    assert 'QMenu(self._select_plant)' in select_action
    assert 'menu.popup(' in select_action
    assert 'normalized_plant_pixmap(' in select_action
    identity_sync = WIDGET_SOURCE.split(
        "def _sync_reward_identity_visibility",
        1,
    )[1].split("def _sync_current_reward_secondary", 1)[0]
    assert "event_plant_id == displayed_plant_id" in identity_sync
    plant_update = WIDGET_SOURCE.split(
        "def _update_plant",
        1,
    )[1].split("def _update_plant_art", 1)[0]
    assert "self._sync_reward_identity_visibility()" in plant_update
    assert "self._settled_full_bloom_bundle = None" in plant_update
    public_selection = DASHBOARD_SOURCE.split(
        "def open_plant_selection",
        1,
    )[1].split("def _release_collection_activation", 1)[0]
    assert "self._open_collection()" in public_selection
    select_style = WIDGET_SOURCE.split(
        '"QToolButton#reviewerHudSelectPlant',
        1,
    )[1].split('"QScrollArea#reviewerHudBodyScroll', 1)[0]
    assert 't["action_accent"]' in select_style
    assert "reviewer_hud_coin" not in select_style

    routine_feedback = WIDGET_SOURCE.split("def animate_growth_delta", 1)[1].split(
        "def _swap_next_answer_row",
        1,
    )[0]
    assert "self._start_plant_motion()" in routine_feedback
    milestone_feedback = WIDGET_SOURCE.split("def celebrate_milestone", 1)[1].split(
        "def _apply_full_bloom_override",
        1,
    )[0]
    assert "self._start_plant_motion(full_bloom=True)" in milestone_feedback
    bounded_motion = WIDGET_SOURCE.split("def _start_plant_motion", 1)[1].split(
        "def _sync_effects",
        1,
    )[0]
    assert "animation.setDuration(" in bounded_motion
    assert 'setProperty("fullBloomParticlesActive", True)' in bounded_motion
    assert "self._settle_plant_motion()" in bounded_motion

    session_feedback = WIDGET_SOURCE.split(
        "def _highlight_session_changes",
        1,
    )[1].split("def _clear_session_highlight", 1)[0]
    assert "QVariantAnimation(self)" in session_feedback
    assert "self._set_session_metric_values(displayed)" in session_feedback
    assert "widget.setMinimumWidth" not in session_feedback
    assert "changed = changed_metrics[index]" in session_feedback
    assert "changed_metrics=changed_metrics" in WIDGET_SOURCE
    assert "receipt_metric(self._session_footer" in WIDGET_SOURCE


def test_custom_hud_position_preserves_anchor_and_stays_clear_of_answer_controls():
    expanded = reviewer_hud_geometry(1200, 900, collapsed=False, dock="right", content_height=360, answer_controls_top=820, position=(.7, .2))
    compact = reviewer_hud_geometry(1200, 900, collapsed=True, dock="right", answer_controls_top=820, position=(.7, .2))
    assert expanded[0] + expanded[2] == compact[0] + compact[2]
    assert expanded[1] == compact[1]
    for width, height, controls in ((800, 600, 520), (1600, 960, 850)):
        x, y, w, h = reviewer_hud_geometry(width, height, collapsed=False, dock="right", content_height=360, answer_controls_top=controls, position=(1., 1.))
        assert 0 <= x <= width - w
        assert 0 <= y <= reviewer_hud_safe_bottom(height, controls) - h
