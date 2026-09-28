from __future__ import annotations

from types import SimpleNamespace

import pytest

from ankigarden.game import GardenGameEngine
from ankigarden.models.state import RewardReceipt
from ankigarden.ui.session_summary_card import (
    SESSION_SUMMARY_COMPACT_HOST_HEIGHT,
    SessionSummaryCard,
    session_earned_item_plan,
    session_effect_remaining_text,
    session_inventory_reward_lines,
    session_plant_progress,
    session_summary_geometry,
    session_summary_uses_compact_density,
)


@pytest.mark.parametrize(
    "species,before,gain,name,amount,description,transition,current,required",
    (
        ("bonsai", 601_200, 3_100, "Mature Bonsai", "+31 Growth",
         "43 / 9,000 Growth to Flowering", "", 4_300, 900_000),
        ("wisteria", 56_280, 465, "Wisteria Sprout", "+4 Growth",
         "167 / 1,600 Growth to Young", "", 16_745, 160_000),
        ("bonsai", 39_950, 100, "Bonsai Sprout", "+1 Growth",
         "0 / 1,600 Growth to Young", "Reached Sprout", 50, 160_000),
        ("bonsai", 0, 200_050, "Young Bonsai", "+2,000 Growth",
         "0 / 4,000 Growth to Mature", "Advanced 2 stages to Young", 50, 400_000),
        ("bonsai", 3_499_999, 1, "Full Bloom Bonsai", "+0 Growth",
         "Fully grown", "Reached Full Bloom", None, None),
        ("bonsai", 3_500_000, 100, "Full Bloom Bonsai", "+1 Growth",
         "Fully grown", "", None, None),
        ("bonsai", None, 10_050, "Bonsai", "+100 Growth", "", "", None, None),
    ),
)
def test_session_plant_progress_keeps_recorded_gain_across_stage_boundaries(
    species, before, gain, name, amount, description, transition, current, required,
):
    progress = session_plant_progress(species, before, gain)
    assert (progress.name, progress.gain) == (name, amount)
    assert (progress.description, progress.stage_change) == (description, transition)
    assert (progress.current_units, progress.required_units) == (current, required)
    assert progress.fully_grown == (description == "Fully grown")


def test_session_summary_geometry_contracts_inside_small_viewports():
    assert session_summary_geometry(340, 300, 500) == (12, 16, 308, 268)
    assert session_summary_geometry(900, 800, 212) == (480, 48, 400, 212)
    assert session_summary_geometry(28, 30, 500) == (7, 16, 1, 1)
    assert session_summary_geometry(
        1_200,
        900,
        900,
        reserved_top=124,
    ) == (780, 140, 400, 520)


def test_session_summary_density_changes_at_its_boundary():
    threshold = SESSION_SUMMARY_COMPACT_HOST_HEIGHT
    assert session_summary_uses_compact_density(threshold - 1)
    assert not session_summary_uses_compact_density(threshold)
    assert not session_summary_uses_compact_density(threshold + 1)


def test_session_receipt_metrics_use_reconciled_totals():
    summary = SimpleNamespace(
        garden_coins_total=14, plant_growth_total_units=4000,
        shared_growth_total_units=0, stored_growth=SimpleNamespace(added_units=0),
        total_finds=2, environment_discoveries=(object(),),
    )
    metrics = SessionSummaryCard._reward_metrics(
        summary, SimpleNamespace(growth_applied_total_units=4000),
    )
    assert [(row[1], row[2]) for row in metrics] == [
        ("Coins", "+14"), ("Growth", "+40"), ("Items & finds", "3"),
    ]


def test_active_boost_art_maps_every_fertilizer_tier_and_booster() -> None:
    renderer = SimpleNamespace(
        _effect_kind=lambda effect: str(effect.kind),
    )

    assert SessionSummaryCard._effect_art_reference(
        renderer,
        SimpleNamespace(
            kind="fertilizer",
            effect_id="fertilizer:plant-a:basic:1:2",
            label="Basic Fertilizer",
        ),
    ) == "fertilizer_basic"
    assert SessionSummaryCard._effect_art_reference(
        renderer,
        SimpleNamespace(
            kind="fertilizer",
            effect_id="fertilizer:plant-a:quality:1:2",
            label="Quality Fertilizer",
        ),
    ) == "fertilizer_quality"
    assert SessionSummaryCard._effect_art_reference(
        renderer,
        SimpleNamespace(
            kind="fertilizer",
            effect_id="fertilizer:plant-a:premium:1:2",
            label="Magical Fertilizer",
        ),
    ) == "fertilizer_premium"
    assert SessionSummaryCard._effect_art_reference(
        renderer,
        SimpleNamespace(
            kind="booster",
            effect_id="booster:plant-a",
            label="Booster Potion",
        ),
    ) == "booster_potion"


def test_minor_checkpoints_remain_available_in_reward_details():
    minor = SimpleNamespace(milestone_type="checkpoint", checkpoint_percent=50)
    major = SimpleNamespace(milestone_type="checkpoint", checkpoint_percent=75)
    stage = SimpleNamespace(milestone_type="stage_change", checkpoint_percent=0)

    assert SessionSummaryCard._minor_checkpoints(
        SimpleNamespace(milestones=(minor, major, stage))
    ) == (minor,)


def test_find_rows_use_explicit_reconciled_quantities_only():
    summary = SimpleNamespace(
        total_finds=3,
        find_items_reconciled=True,
        find_items=(
            SimpleNamespace(
                find_id="small_charge",
                find_name="Small Growth Charge",
                art_asset="ui_growth_charge_small",
                item_id="growth_charge_small",
                quantity=3,
            ),
        ),
    )
    assert SessionSummaryCard._find_items(summary) == (
        (
            "small_charge",
            "Small Growth Charge",
            "ui_growth_charge_small",
            3,
        ),
    )
    summary.total_finds = 4
    assert SessionSummaryCard._find_items(summary) == ()
    summary.find_items_reconciled = False
    assert SessionSummaryCard._find_items(summary) == ()


def test_canonical_garden_feature_art_uses_the_dedicated_asset_catalog():
    resolved = object()

    class _Assets:
        def __init__(self):
            self.calls = []

        def resolve(self, category, key, query, **kwargs):
            self.calls.append((category, key, query, kwargs))
            return resolved if category == "garden_features" else None

    assets = _Assets()
    engine = SimpleNamespace(
        state=SimpleNamespace(
            loadout=SimpleNamespace(visibility={"garden_feature": True}),
            selected_garden_feature="seedling_sign",
        ),
        config=SimpleNamespace(value=lambda _key, default=None: default),
        assets=assets,
    )

    result = GardenGameEngine.resolve_garden_feature_asset(
        engine,
        "firefly_lantern",
        preview=True,
    )

    assert result is resolved
    assert [(category, key) for category, key, _query, _kwargs in assets.calls] == [
        ("garden_features", "garden_feature_firefly_lantern"),
    ]


def test_earned_garden_feature_art_ignores_retired_loadout_visibility():
    resolved = object()

    class _Assets:
        def resolve(self, *_args, **_kwargs):
            return resolved

    engine = SimpleNamespace(
        state=SimpleNamespace(
            loadout=SimpleNamespace(visibility={"garden_feature": False}),
            selected_garden_feature="seedling_sign",
        ),
        config=SimpleNamespace(value=lambda _key, default=None: default),
        assets=_Assets(),
    )

    assert GardenGameEngine.resolve_garden_feature_asset(
        engine,
        "firefly_lantern",
        preview=True,
    ) is resolved
    assert GardenGameEngine.resolve_garden_feature_asset(
        engine,
        "firefly_lantern",
        preview=True,
        respect_visibility=False,
    ) is resolved


def test_inventory_receipts_use_the_shared_typed_reward_copy():
    receipts = (
        RewardReceipt(
            event_key="full-bloom:item",
            reward_type="inventory_item",
            source="full_bloom",
            source_id="plant-1",
            scheduler_day="2026-08-28",
            correlation_id="full-bloom",
            occurred_at="2026-08-28T10:00:00Z",
            amount=1,
            item_id="growth_charge_small",
        ),
        RewardReceipt(
            event_key="full-bloom:coins",
            reward_type="coins",
            source="full_bloom",
            source_id="plant-1",
            scheduler_day="2026-08-28",
            correlation_id="full-bloom",
            occurred_at="2026-08-28T10:00:00Z",
            amount=20,
        ),
    )

    assert session_inventory_reward_lines(receipts) == (
        ("growth_charge_small", 1, "+1 Small Growth Charge"),
    )

    find_event_id = "find:small-charge"
    receipt_event_id = "garden_find:small-charge:standard"
    plan = session_earned_item_plan(SimpleNamespace(
        find_items_reconciled=True,
        standard_finds=(SimpleNamespace(
            find_id="small_charge",
            event_id=find_event_id,
        ),),
        find_items=(SimpleNamespace(
            find_id="small_charge",
            find_name="Small Growth Charge",
            art_asset="ui_growth_charge_small",
            reward_type="inventory_item",
            item_id="growth_charge_small",
            quantity=1,
        ),),
        reward_receipts=(
            RewardReceipt(
                event_key=receipt_event_id,
                reward_type="inventory_item",
                source="standard_find",
                source_id="small_charge",
                scheduler_day="2026-08-28",
                correlation_id="answer:small-charge",
                occurred_at="2026-08-28T10:00:00Z",
                amount=1,
                item_id="growth_charge_small",
            ),
            receipts[0],
            receipts[0],
        ),
    ))

    assert len(plan) == 1
    assert plan[0].item_id == "growth_charge_small"
    assert plan[0].quantity == 2
    assert plan[0].source_labels == ("Garden Find", "Full Bloom")

    receipt_only = session_earned_item_plan(SimpleNamespace(
        find_items_reconciled=False,
        standard_finds=(),
        find_items=(),
        reward_receipts=(RewardReceipt(
            event_key=receipt_event_id,
            reward_type="inventory_item",
            source="standard_find",
            source_id="small_charge",
            scheduler_day="2026-08-28",
            correlation_id="answer:small-charge",
            occurred_at="2026-08-28T10:00:00Z",
            amount=1,
            item_id="growth_charge_small",
        ),),
    ))
    assert tuple((item.quantity, item.source_labels) for item in receipt_only) == (
        (1, ("Garden Find",)),
    )


def test_continue_reviews_closes_only_after_success():
    closed, properties = [], {}
    card = SimpleNamespace(
        close=lambda: closed.append(True),
        setProperty=lambda key, value: properties.update({key: value}),
    )
    for callback in (None, lambda: False, lambda: 1 / 0):
        card._on_continue_reviews = callback
        SessionSummaryCard._continue_reviews(card)
        assert closed == []
    assert properties["summaryContinueFailed"] is True
    card._on_continue_reviews = lambda: True
    SessionSummaryCard._continue_reviews(card)
    assert closed == [True]


def test_effect_remaining_copy_is_live_concise_and_pluralized():
    fertilizer = SimpleNamespace(
        kind="fertilizer",
        expires_at_epoch_seconds=10_000,
        remaining_seconds=999,
        remaining_cards=32,
    )
    assert session_effect_remaining_text(
        fertilizer,
        now_epoch_seconds=8_080,
    ) == "32 cards remaining"
    assert session_effect_remaining_text(
        SimpleNamespace(
            kind="fertilizer",
            expires_at_epoch_seconds=10_000,
            remaining_seconds=999,
            remaining_cards=0,
        ),
        now_epoch_seconds=8_080,
    ) == ""
    assert session_effect_remaining_text(
        SimpleNamespace(kind="booster", remaining_cards=1)
    ) == "1 card remaining"
    assert session_effect_remaining_text(
        SimpleNamespace(kind="booster", remaining_cards=38)
    ) == "38 cards remaining"


def test_items_and_finds_counts_the_same_awards_across_summary_formats():
    from ankigarden.reward_counts import activity_drop_count, reward_drop_count
    charge = {"event_key": "achievement:one", "source": "achievement",
              "reward_type": "inventory_item", "item_id": "growth_charge_small", "amount": 2}
    find_item = {"event_key": "find:one", "source": "standard_find",
                 "reward_type": "inventory_item", "item_id": "bonsai", "amount": 1}
    unlock = {"event_key": "unlock:one", "source": "garden_find_environment",
              "reward_type": "environment_item", "item_id": "spring_bloom", "amount": 1}
    environments = ({"event_id": "unlock:one", "environment_id": "spring_bloom"},)
    session = {"total_finds": 1, "standard_finds": ({"event_id": "find:one"},),
               "environment_discoveries": environments,
               "reward_receipts": (find_item, charge, charge, unlock,
                   {**charge, "event_key": "purchase:one", "source": "purchase"})}
    sync = {"finds": ({"event_id": "find:one", "quantity": 1},
                     {"event_id": "achievement:one", "quantity": 2}),
            "environment_discoveries": environments}
    assert reward_drop_count(session) == reward_drop_count(sync) == 4
    assert sum(activity_drop_count(finds, row["source"],
               ({**row, "kind": row["reward_type"]},))
               for finds, row in ((1, find_item), (0, charge), (0, unlock))) == 4
    assert activity_drop_count(0, "purchase", ({"kind": "inventory_item", "amount": 2},)) == 0
