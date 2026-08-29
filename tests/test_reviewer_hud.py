from __future__ import annotations

import inspect
from collections import deque
from pathlib import Path
from types import SimpleNamespace

import pytest

from ankigarden.config import DEFAULT_CONFIG
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
    project_reviewer_hud,
    project_today_cards,
    reviewer_hud_geometry,
    reviewer_hud_width,
)
from ankigarden.ui.reviewer_hud_widget import (
    ReviewGardenHud,
    _all_secondary_items,
    _bundle_has_kind,
    _bundle_growth_units,
    _checkpoint_marker_states,
    _checkpoint_sequence_is_chronological,
    _effect_overflow_label,
    _format_coin_balance,
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


def completion(status: str, **overrides):
    values = {
        "scheduler_day": DAY,
        "status": status,
        "starting_required_cards": 194,
        "starting_required_cards_completed": 176,
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
    assert complete.heading == "All cards complete"
    assert complete.primary == "+10 coins"
    assert complete.secondary == ("176 reviewed today",)
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


def test_complete_today_card_uses_engine_confirmed_coin_reward() -> None:
    projection = project_reviewer_hud(
        SimpleNamespace(
            active_plant=lambda: None,
            all_due_rewards=lambda: (15, 0),
            ALL_DUE_BASE_COINS=10,
        ),
        state_for("complete"),
    )

    assert projection.today.primary == "+15 coins"
    assert projection.today.completion_reward_coins == 15
    singular = project_today_cards(
        state_for("complete"),
        completion_reward_coins=1,
    )
    assert singular.primary == "+1 coin"


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
        "No cards due today",
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
        fertilizer=SimpleNamespace(expires_at=4_600),
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

    assert nurture.plant_name == "Juniper of the Moonlit Terrace"
    assert nurture.stage_label == "Young · Stage 2 of 5"
    assert nurture.species_name == "Bonsai"
    assert nurture.next_answer_value == "+13.5 growth"
    assert nurture.next_card_line == "Next answer · +13.5 growth"
    assert nurture.checkpoint_line == "605 growth to next checkpoint"
    assert nurture.estimate_line == "~45 cards"
    assert nurture.checkpoint_growth_remaining == 605
    assert nurture.estimated_cards_to_checkpoint == 45
    assert nurture.next_checkpoint_percent == 75
    assert nurture.next_checkpoint_reward_coins == 4
    assert nurture.next_stage_line == "+4 coins at next checkpoint"
    assert nurture.art_path == "/art/bonsai-young.webp"
    assert nurture.art_placement is placement
    assert nurture.visible_effect_chips == (
        "Fertilizer 1h",
        "Booster 38 cards",
    )
    assert nurture.effect_chips == (
        "Fertilizer 1h",
        "Booster 38 cards",
        "Weather +0.5 growth",
        "Scenery +0.25 growth",
        "Streak bonus +1 growth",
    )
    assert nurture.effect_overflow_count == 3
    assert nurture.shared_line == ""
    assert nurture.environment_line == ""
    assert nurture.queued_line == ""
    assert nurture.stored_growth_line == ""


def test_no_plant_and_full_bloom_use_contextual_copy() -> None:
    no_target = state_for("in_progress")
    no_target.active_plant_id = ""
    no_target.stored_growth_units = 1_250
    empty = project_reviewer_hud(SimpleNamespace(active_plant=lambda: None), no_target).nurture
    assert empty.empty_heading == "No plant selected"
    assert empty.empty_message == "Growth earned during review will be stored."
    assert empty.stored_growth_line == (
        "12.5 growth stored until a plant is selected"
    )

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
    assert projection.stage_label == "Full Bloom"
    assert projection.next_checkpoint_percent == 0
    assert projection.next_answer_value == ""
    assert projection.species_name == "Rose"
    assert projection.empty_message == (
        "Future growth will be shared or stored until you select another plant."
    )


def test_geometry_is_responsive_content_hugging_and_answer_bar_safe() -> None:
    assert reviewer_hud_width(1_280) == 312
    assert reviewer_hud_width(1_600) == 320
    assert reviewer_hud_width(2_000) == 328

    expanded = reviewer_hud_geometry(
        1_600,
        1_000,
        collapsed=False,
        dock="right",
        content_height=590,
    )
    assert expanded == (1_268, 16, 320, 590)

    short = reviewer_hud_geometry(
        1_280,
        500,
        collapsed=False,
        dock="right",
        content_height=700,
    )
    assert short == (956, 16, 312, 372)
    collapsed = reviewer_hud_geometry(1_200, 800, collapsed=True, dock="left")
    assert collapsed == (12, 16, HUD_COLLAPSED_WIDTH, HUD_COLLAPSED_HEIGHT)
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
    assert "chip_layout.setContentsMargins(3, 0, 3, 0)" in effect_chip_block
    assert "chip_layout.setSpacing(2)" in effect_chip_block
    assert 'label.setProperty("hudEffectLabel", True)' in effect_chip_block
    clear_celebration = WIDGET_SOURCE.split(
        "def _clear_celebration",
        1,
    )[1].split("def update_session_totals", 1)[0]
    assert "if self._disposed" in clear_celebration


def test_plant_art_bounds_remove_empty_canvas_without_mutating_source() -> None:
    assert padded_preview_bounds(
        (0.40, 0.20, 0.20, 0.60),
        padding=0.10,
    ) == pytest.approx((0.38, 0.14, 0.24, 0.72))
    assert padded_preview_bounds(None) == (0.0, 0.0, 1.0, 1.0)


def test_release_copy_helpers_cover_balance_markers_effects_and_zero_free_session() -> None:
    for value in (248, 9_999, 10_013, 999_999, 1_000_000):
        assert _format_coin_balance(value, exact_fits=False) == f"{value:,}"
    assert _format_coin_balance(1_200_000, exact_fits=False) == "1.2M"

    assert _checkpoint_marker_states(38, 50) == (
        "completed",
        "next",
        "future",
        "future",
    )
    assert _effect_overflow_label(1) == "1 more effect ›"
    assert _effect_overflow_label(3) == "3 more effects ›"
    assert _session_metric_labels(0, 0, 0) == ()
    assert _session_metric_labels(1_800, 0, 0) == ("+18 growth",)
    assert _session_metric_labels(1_800, 2, 1) == (
        "+18 growth",
        "+2 coins",
        "1 find",
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
        effect_chips=("Fertilizer 1h", "Booster 38 cards"),
    )
    assert two_effects.visible_effect_chips == two_effects.effect_chips
    assert two_effects.effect_overflow_count == 0
    three_effects = NurtureProjection(
        True,
        effect_chips=("Fertilizer 1h", "Booster 38 cards", "Weather +1 growth"),
    )
    assert three_effects.visible_effect_chips == three_effects.effect_chips[:2]
    assert three_effects.effect_overflow_count == 1


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
        category_label="Garden Find",
        growth_units=4_000,
        garden_coins=4,
        rarity="common",
        artwork_ref="/art/moonlit-sprout.webp",
    )
    bundle = RewardBundleProjection("answer-1", "2026-08-28T12:00:00Z", (hero,))
    assert _hero_kind(bundle) == "garden_find"
    assert _hero_amounts(bundle) == (4_000, 4)
    assert _bundle_growth_units(bundle) == 4_000

    signature = inspect.signature(ReviewGardenHud.present_reward)
    assert "reveal" in signature.parameters
    assert signature.parameters["reveal"].default is True
    committed = inspect.signature(ReviewGardenHud.present_committed_result)
    assert committed.parameters["applied_growth_units"].default == 0
    assert committed.parameters["reveal"].default is True
    assert hasattr(ReviewGardenHud, "update_session_totals")
    assert hasattr(ReviewGardenHud, "update_projection")


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
            category_label="Garden Find",
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
        "+4 growth",
        "1 Garden Find",
    )
    assert bundle.more_label == "2 more rewards ›"


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
            category_label="Garden Find",
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
    assert bundle.compact.hero_title == "Full Bloom achieved"
    assert bundle.compact.hero_subtitle == "Rose"
    assert tuple(summary.label for summary in bundle.visible_summaries) == (
        "+40 growth",
        "2 discoveries",
    )
    assert bundle.more_label == "2 more rewards ›"
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
    reconciled_zero = RewardBundleProjection(
        "answer-full-bloom-zero-coins",
        "2026-08-28T12:00:00Z",
        (hero, *items),
        displayed_coin_delta=0,
    )
    assert _hero_amounts(reconciled_zero) == (0, 0)


def test_committed_entrypoint_respects_an_explicit_zero_applied_growth() -> None:
    animated: list[int] = []
    fake = SimpleNamespace(
        _seen_bundle_ids=set(),
        _reward_history=deque(),
        _reward_history_page=0,
        _collapsed=False,
        _unseen_major=0,
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
            category_label="Garden Find",
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
            category_label="Garden Find",
        ),),
    )
    fake = SimpleNamespace(
        _seen_bundle_ids=set(),
        _reward_history=deque(),
        _reward_history_page=0,
        _collapsed=False,
        _unseen_major=0,
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


def test_committed_major_reward_is_idempotent_and_queues_while_collapsed() -> None:
    bundle = RewardBundleProjection(
        "answer-major-collapsed",
        "2026-08-28T12:00:00Z",
        (RewardItemProjection(
            event_id="find-collapsed",
            kind=RewardHero.GARDEN_FIND,
            title="Moonlit Sprout",
            category_label="Garden Find",
        ),),
    )
    fake = SimpleNamespace(
        _seen_bundle_ids=set(),
        _reward_history=deque(),
        _reward_history_page=0,
        _collapsed=True,
        _unseen_major=0,
        _reward_queue=deque(),
        setProperty=lambda *_args: None,
        _sync_history_rows=lambda: None,
        _sync_unseen_badge=lambda: None,
        animate_growth_delta=lambda _units: None,
    )

    assert ReviewGardenHud.present_committed_result(fake, bundle)
    assert ReviewGardenHud.present_committed_result(fake, bundle)
    assert tuple(fake._reward_history) == (bundle,)
    assert tuple(fake._reward_queue) == (bundle,)
    assert fake._unseen_major == 1


def test_mixed_reward_bundle_delays_for_its_checkpoint_item() -> None:
    find = RewardItemProjection(
        event_id="find-1",
        kind=RewardHero.GARDEN_FIND,
        title="Moonlit Sprout",
        category_label="Garden Find",
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
        "reviewerHudRewardEyebrow",
        "reviewerHudRewardSubtitle",
        "reviewerHudRewardSummaryChip0",
        "reviewerHudRewardSummaryChip1",
        "reviewerHudRewardDivider",
        "reviewerHudSessionFooter",
        "reviewerHudRewardHistory",
        "reviewerHudCollapsedTab",
    ):
        assert object_name in WIDGET_SOURCE
    assert "ankiGardenRewardToast" not in WIDGET_SOURCE
    assert "reward close" not in WIDGET_SOURCE.casefold()
    assert "body.addStretch" not in WIDGET_SOURCE
    assert "deque(maxlen=_REWARD_QUEUE_LIMIT)" not in WIDGET_SOURCE
    assert '"Choose a plant" if not nurture.has_target' in WIDGET_SOURCE
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
    assert "_reopen_history_reward" in WIDGET_SOURCE
    assert 'setObjectName("reviewerHudRewardMore")' in WIDGET_SOURCE
    assert "_COMPACT_REWARD_MAX_HEIGHT = 188" in WIDGET_SOURCE
    assert "if self._reward_details_expanded\n            else _COMPACT_REWARD_MAX_HEIGHT" in WIDGET_SOURCE
    assert "self._reward_summary_chips: list[_ElidedLabel]" in WIDGET_SOURCE
    assert "visible_summaries[:2]" in WIDGET_SOURCE
    assert "self._reward_more.setMinimumWidth(" in WIDGET_SOURCE
    assert "self._reward_more.setMinimumHeight(32)" in WIDGET_SOURCE
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
    assert 'self.setMinimumHeight(metrics.lineSpacing() * 2 + 3)' in WIDGET_SOURCE
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
    assert plant_builder.index("layout.addWidget(self._next_answer)") < plant_builder.index(
        "layout.addWidget(self._checkpoint_reward_row)"
    )
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
        "self._session_growth",
        "self._session_coins",
        "self._session_finds",
    ):
        assert f"apply_tabular_numerals({widget_name})" in WIDGET_SOURCE

    effect_overflow = WIDGET_SOURCE.split(
        "def _effect_overflow_label",
        1,
    )[1].split("def _session_metric_labels", 1)[0]
    assert "format_quantity(normalized, 'more effect', 'more effects')" in effect_overflow
    plant_update = WIDGET_SOURCE.split("def _update_plant", 1)[1].split(
        "def _update_plant_art",
        1,
    )[0]
    assert "format_quantity(nurture.next_checkpoint_reward_coins, 'coin')" in plant_update

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
    )[1].split("def _apply_stage_change_override", 1)[0]
    assert "self._select_plant.setVisible(bool(settled))" in full_bloom_override
    assert "self._select_plant.show()" not in full_bloom_override

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
    assert "widget.setMinimumWidth" in session_feedback
    assert "changed = changed_metrics[index]" in session_feedback
    assert "changed_metrics=changed_metrics" in WIDGET_SOURCE
    assert "self._session_footer.setFixedHeight(54)" in WIDGET_SOURCE
