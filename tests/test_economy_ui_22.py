from types import SimpleNamespace

from ankigarden.models.state import CardEffectBatch, GardenState
from ankigarden.ui.economy_presenters import (
    bed_unlock_rows,
    cosmetic_rows,
    landmark_summary,
    mastery_summary,
)
from ankigarden.ui.plant_presenters import fertilizer_status
from ankigarden.ui.reviewer_hud import _active_effect_rows
from ankigarden.ui.session_summary import EffectRow
from ankigarden.ui.session_summary_card import session_effect_remaining_text


def batch(effect_id: str, remaining: int, total: int) -> CardEffectBatch:
    return CardEffectBatch(effect_id, 100, total, remaining)


def test_fertilizer_status_is_card_counted_fifo_and_time_invariant() -> None:
    engine = SimpleNamespace(FERTILIZERS={
        "basic": SimpleNamespace(name="Basic Fertilizer"),
        "quality": SimpleNamespace(name="Quality Fertilizer"),
    })
    plant = SimpleNamespace(
        fertilizer_card_batches=(
            batch("fertilizer_basic", 17, 100),
            batch("fertilizer_basic", 80, 100),
        ),
        fertilizer_card_queue=(batch("fertilizer_quality", 200, 200),),
    )

    early = fertilizer_status(engine, plant, now=1)
    late = fertilizer_status(engine, plant, now=9_999_999_999)

    assert early == late
    assert early.duration == "97 cards remaining"
    assert early.cards_remaining == 97
    assert early.total_cards == 200
    assert early.queued_cards == 200
    assert early.seconds_remaining == 0
    assert "cards queued after this dose" in early.accessible_text


def test_reviewer_effect_rows_use_cards_and_garden_rhythm() -> None:
    plant = SimpleNamespace(
        fertilizer_card_batches=(batch("fertilizer_basic", 23, 100),),
        booster_card_batches=(),
    )
    engine = SimpleNamespace(
        state=SimpleNamespace(wind_chime_progress=4),
        active_garden_feature_id=lambda: "wind_chime",
    )
    award = SimpleNamespace(
        weather_growth_units=0,
        scenery_growth_units=0,
        streak_growth_units=20,
    )

    rows = _active_effect_rows(engine, plant, award, now_ms=1)

    assert (
        "Basic Fertilizer · 23 cards remaining",
        "fertilizer_basic",
    ) in rows
    assert ("Garden Rhythm · +0.2 Growth", "") in rows
    assert not any(" h" in label or " min" in label for label, _asset in rows)


def test_session_effect_copy_never_uses_wall_clock() -> None:
    effect = EffectRow(
        "fertilizer",
        "fertilizer:plant:basic",
        "Basic Fertilizer",
        "",
        remaining_seconds=3_600,
        remaining_cards=1,
        expires_at_epoch_seconds=99_999_999_999,
    )

    assert session_effect_remaining_text(effect, now_epoch_seconds=0) == "1 card remaining"
    assert session_effect_remaining_text(effect, now_epoch_seconds=99_999_999_999) == "1 card remaining"


def test_beds_are_presented_as_earned_milestones() -> None:
    state = SimpleNamespace(unlocked_slots=3)
    rows = bed_unlock_rows(state)

    assert [row.unlocked for row in rows] == [True, True, True, False, False, False]
    assert rows[3].requirement == "First unique species reaches Full Bloom"
    assert rows[5].requirement == "6 unique species reach Full Bloom"
    assert rows[2].action_text == "Unlock Bed 3"
    assert rows[2].artwork_id == "bg_verdant_twilight_any_soil_master_v6"
    assert rows[2].unlock_policy == "automatic_achievement"
    assert rows[2].price_coins is None
    assert rows[2].can_commit is False


def test_trophy_rows_exclude_retired_purchases_and_never_equip() -> None:
    state = GardenState()
    state.inventory["cosmetics"] = ["garden_bench", "golden_trowel"]
    state.loadout.display_decoration_id = "golden_trowel"
    rows = {row.item_id: row for row in cosmetic_rows(state)}
    assert set(rows) == {"botanists_plaque", "garden_journal", "golden_trowel"}
    assert rows["golden_trowel"].owned
    assert all(not row.displayed and row.price is None for row in rows.values())


def test_endgame_presenters_consume_engine_catalog_summaries() -> None:
    engine = SimpleNamespace(
        landmark_catalog_summary=lambda: {
            "unlocked": True,
            "stored_growth_units": 12_500,
            "auto_contribute": False,
            "selected_landmark_id": "mossy_stone_path",
            "next_landmark_id": "mossy_stone_path",
            "displayed_landmark_id": "",
            "completed_landmark_ids": [],
            "contributed_growth_units": 2_500,
            "required_growth_units": 2_500_000,
            "ready_to_complete": False,
            "items": ({
                "landmark_id": "mossy_stone_path",
                "display_name": "Mossy Stone Path",
                "growth_cost_units": 2_500_000,
                "coin_cost": 250,
                "completed": False,
                "selected": True,
                "displayed": False,
            },),
        },
        mastery_catalog_summary=lambda: {
            "stored_growth_units": 12_500,
            "species": ({
                "species_id": "bonsai",
                "eligible": True,
                "current_rank_id": "bronze",
                "next_rank_id": "silver",
            },),
        },
    )

    landmark = landmark_summary(engine)
    mastery = mastery_summary(engine)

    assert landmark.rows[0].name == "Mossy Stone Path"
    assert landmark.contributed_growth_units == 2_500
    assert mastery.rows[0].next_rank_id == "silver"
