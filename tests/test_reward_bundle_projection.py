from __future__ import annotations

import pytest

from ankigarden.models.state import RewardReceipt
from ankigarden.reward_presentation import (
    RewardBundleProjection,
    RewardCompactProjection,
    RewardCompactSummary,
    RewardDetailRow,
    RewardHero,
    RewardItemProjection,
    project_committed_reward_bundle,
    project_reward_detail_rows,
    project_reward_session_history,
)
from ankigarden.ui.session_summary import (
    CoinAward,
    CommittedSessionEvent,
    EnvironmentDiscovery,
    PlantGrowthDelta,
    PlantMilestone,
    StandardFind,
)


def _event(**changes: object) -> CommittedSessionEvent:
    values: dict[str, object] = {
        "event_id": "answer:stable-1",
        "anki_day_id": "2026-08-28",
        "occurred_at": "2026-08-28T10:00:00Z",
    }
    values.update(changes)
    return CommittedSessionEvent(**values)  # type: ignore[arg-type]


def test_bundle_uses_exact_priority_bounds_secondary_items_and_preserves_all_data():
    event = _event(
        plant_growth=(PlantGrowthDelta("rose", "Rose", 5_000),),
        shared_growth=(PlantGrowthDelta("juniper", "Juniper", 200),),
        stored_growth_delta_units=300,
        coin_awards=(
            CoinAward("coin:bloom", "stage", "Full Bloom", 5),
            CoinAward("coin:stage", "stage", "Mature", 3),
            CoinAward("coin:checkpoint", "checkpoint", "Checkpoint", 2),
            CoinAward("coin:daily", "daily_activity", "First card today", 4),
        ),
        standard_finds=(StandardFind(
            "find:common",
            "morning_dew",
            "Morning Dew",
            "common",
            "growth",
            "+40 Growth",
            40,
            "morning_dew.webp",
        ),),
        milestones=(
            PlantMilestone(
                "stage:rose:mature",
                "rose",
                "Rose",
                "stage_change",
                "2026-08-28T10:00:00Z",
                new_stage="mature",
                stage_path=("sprout", "young", "mature"),
                coin_reward=3,
                coin_award_event_ids=("coin:stage",),
                coin_included_in_total=True,
            ),
            PlantMilestone(
                "checkpoint:rose:75",
                "rose",
                "Rose",
                "checkpoint",
                "2026-08-28T10:00:00Z",
                checkpoint_percent=75,
                new_stage="flowering",
                plant_class="Bonsai",
                coin_reward=2,
                coin_award_event_ids=("coin:checkpoint",),
                coin_included_in_total=True,
            ),
            PlantMilestone(
                "bloom:rose",
                "rose",
                "Rose",
                "full_bloom",
                "2026-08-28T10:00:00Z",
                plant_art_asset="rose-rare.webp",
                plant_class="Bonsai",
                new_stage="rare",
                coin_reward=5,
                coin_award_event_ids=("coin:bloom",),
                coin_included_in_total=True,
            ),
        ),
        environment_discoveries=(EnvironmentDiscovery(
            "environment:twilight",
            "twilight",
            "Verdant Twilight",
            "scenery",
            "rare",
            "twilight.webp",
            "Cosmetic environment",
        ),),
    )

    bundle = project_committed_reward_bundle(event)

    assert bundle is not None
    assert bundle.bundle_id == event.event_id
    assert bundle.correlation_id == event.event_id
    assert bundle.hero.kind is RewardHero.FULL_BLOOM
    assert bundle.hero.artwork_ref == "rose-rare.webp"
    assert bundle.hero.plant_id == "rose"
    assert bundle.hero.plant_name == "Rose"
    assert bundle.hero.plant_class == "Bonsai"
    assert bundle.hero.new_stage == "rare"
    assert bundle.hero.sequence == 2
    assert bundle.hero.garden_coins == 5
    assert bundle.displayed_coin_delta == 14
    assert [item.kind for item in bundle.secondary_items] == [
        RewardHero.STAGE_CHANGE,
        RewardHero.ENVIRONMENT_DISCOVERY,
        RewardHero.GARDEN_FIND,
    ]
    assert bundle.secondary_items[-1].title == "Morning Dew"
    assert bundle.secondary_items[-1].rarity == "common"
    checkpoint = next(
        item for item in bundle.all_items if item.kind is RewardHero.CHECKPOINT
    )
    assert checkpoint.checkpoint_percent == 75
    assert checkpoint.plant_class == "Bonsai"
    assert checkpoint.sequence == 1
    assert bundle.compact.eyebrow == "MILESTONE REACHED"
    assert bundle.compact.hero_title == "Full Bloom achieved"
    assert bundle.compact.hero_subtitle == "Rose"
    assert [summary.label for summary in bundle.visible_summaries] == [
        "1 Standard Find",
        "Verdant Twilight",
    ]
    assert [summary.reward_type for summary in bundle.visible_summaries] == [
        "garden_find",
        "environment_discovery",
    ]
    assert bundle.visible_summaries[0].artwork_ref == "morning_dew.webp"
    assert bundle.visible_summaries[0].rarity == "common"
    assert bundle.visible_summaries[1].artwork_ref == "twilight.webp"
    assert bundle.visible_summaries[1].rarity == "rare"
    assert bundle.remaining_count == 5
    assert bundle.more_label == "Details ›"
    assert bundle.compact == project_committed_reward_bundle(event).compact
    assert bundle.routine_only is False
    assert sum(item.garden_coins for item in bundle.all_items) == 14
    assert sum(item.growth_units for item in bundle.all_items) == 5_500


def test_full_bloom_coin_history_reconciles_the_canonical_footer_total() -> None:
    event = _event(
        coin_awards=(
            CoinAward("coin:bloom", "stage", "Full Bloom", 5),
            CoinAward("coin:checkpoint", "checkpoint", "Checkpoint", 2),
            CoinAward("coin:daily", "daily_activity", "First card today", 7),
            CoinAward(
                "coin:external",
                "external",
                "Unrelated external reward",
                50,
                included_in_total=False,
            ),
        ),
        milestones=(PlantMilestone(
            "stage:rose:rare",
            "rose",
            "Rose",
            "full_bloom",
            "2026-08-28T10:00:00Z",
            new_stage="rare",
            coin_reward=5,
            coin_award_event_ids=("coin:bloom",),
            coin_included_in_total=True,
        ),),
    )

    bundle = project_committed_reward_bundle(event)

    assert bundle is not None
    assert bundle.hero.kind is RewardHero.FULL_BLOOM
    assert bundle.hero.garden_coins == 5
    assert bundle.displayed_coin_delta == 64
    assert sum(item.garden_coins for item in bundle.all_items) == 64
    assert [
        (item.event_id, item.garden_coins)
        for item in bundle.all_items
    ] == [
        ("stage:rose:rare", 5),
        ("answer:stable-1:coins", 59),
    ]


def test_find_history_reconciles_missing_details_without_duplicate_payouts() -> None:
    event = _event(
        standard_finds=(StandardFind(
            "find:known",
            "morning_dew",
            "Morning Dew",
            "common",
            "growth",
            "+40 Growth",
            40,
            "morning_dew.webp",
            quantity=2,
        ),),
        total_finds=3,
    )

    bundle = project_committed_reward_bundle(event)

    assert bundle is not None
    find_items = tuple(
        item for item in bundle.all_items if item.kind is RewardHero.GARDEN_FIND
    )
    assert [item.event_id for item in find_items] == [
        "find:known",
        "find:known:occurrence:2",
        "answer:stable-1:find:unitemized:1",
    ]
    assert sum(item.growth_units for item in find_items) == 4_000
    assert sum(item.garden_coins for item in find_items) == 0
    assert tuple(item.inventory_items for item in find_items) == ((), (), ())
    assert bundle.visible_summaries[0].label == "2 Standard Finds"
    assert project_committed_reward_bundle(event) == bundle


def test_additional_coin_awards_are_locatable_once_in_reward_history() -> None:
    event = _event(coin_awards=(
        CoinAward("coin:base", "daily", "Daily reward", 3),
        CoinAward(
            "coin:additional",
            "external",
            "Additional reward",
            7,
            included_in_total=False,
        ),
    ))

    bundle = project_committed_reward_bundle(event)

    assert bundle is not None
    assert bundle.hero.event_id == "answer:stable-1:coins"
    assert bundle.hero.garden_coins == 10
    assert sum(item.garden_coins for item in bundle.all_items) == 10
    assert project_committed_reward_bundle(event) == bundle


def test_routine_growth_bundle_is_typed_and_nonduplicating():
    event = _event(
        plant_growth=(PlantGrowthDelta("rose", "Rose", 1_000),),
        shared_growth=(PlantGrowthDelta("juniper", "Juniper", 200),),
        stored_growth_delta_units=500,
    )

    first = project_committed_reward_bundle(event)
    second = project_committed_reward_bundle(event)

    assert first == second
    assert first is not None
    assert first.routine_only is True
    assert first.has_major_reward is False
    assert [item.event_id for item in first.all_items] == [
        "answer:stable-1:growth:plant",
        "answer:stable-1:growth:shared",
        "answer:stable-1:growth:stored",
    ]
    assert [item.growth_units for item in first.all_items] == [1_000, 200, 500]
    assert first.remaining_count == 0
    assert first.more_label == "Details ›"
    assert first.detail_expansion_available is True


def test_typed_booster_receipt_is_major_and_must_share_answer_correlation():
    event_id = "answer:stable-1"
    booster = RewardReceipt(
        "booster:answer:1",
        "inventory_item",
        "achievement",
        "streak_7",
        "2026-08-28",
        event_id,
        "2026-08-28T10:00:00Z",
        amount=1,
        item_id="booster_potion",
        title="Booster Potion",
    )
    event = _event(
        plant_growth=(PlantGrowthDelta("rose", "Rose", 1_000),),
        reward_receipts=(booster,),
    )

    bundle = project_committed_reward_bundle(event)

    assert bundle is not None
    assert bundle.hero.kind is RewardHero.COIN_OR_BOOSTER
    assert bundle.compact.eyebrow == "REWARD EARNED"
    assert bundle.hero.inventory_items == (("booster_potion", 1),)
    assert bundle.routine_only is False
    assert bundle.secondary_items[0].kind is RewardHero.ROUTINE_GROWTH

    with pytest.raises(ValueError, match="share the committed event correlation"):
        project_committed_reward_bundle(
            event,
            receipts=(
                RewardReceipt(
                    "booster:other",
                    "inventory_item",
                    "achievement",
                    "streak_7",
                    "2026-08-28",
                    "answer:other",
                    event.occurred_at,
                    amount=1,
                    item_id="booster_potion",
                ),
            ),
        )


def test_full_bloom_inventory_receipt_names_the_growth_charge_not_the_event():
    event_id = "answer:full-bloom-charge"
    event = CommittedSessionEvent(
        event_id=event_id,
        anki_day_id="2026-08-28",
        occurred_at="2026-08-28T10:00:00Z",
        milestones=(PlantMilestone(
            "stage:rose:rare",
            "rose",
            "Rose",
            "full_bloom",
            "2026-08-28T10:00:00Z",
            new_stage="rare",
        ),),
        reward_receipts=(RewardReceipt(
            event_key="full_bloom:rose",
            reward_type="inventory_item",
            source="full_bloom",
            source_id="rose",
            scheduler_day="2026-08-28",
            correlation_id=event_id,
            occurred_at="2026-08-28T10:00:00Z",
            amount=1,
            item_id="growth_charge_small",
            title="Full Bloom",
        ),),
    )

    bundle = project_committed_reward_bundle(event)

    assert bundle is not None
    assert bundle.displayed_coin_delta == 0
    assert [summary.label for summary in bundle.visible_summaries] == [
        "Small Growth Charge +1"
    ]


def test_standard_find_inventory_keeps_its_engine_item_identity():
    event = _event(
        standard_finds=(StandardFind(
            "find:booster",
            "find_booster",
            "Bottled Rain",
            "uncommon",
            "inventory_item",
            "+1 Booster Potion",
            1,
            "bottled_rain.webp",
            item_id="booster_potion",
        ),),
    )

    bundle = project_committed_reward_bundle(event)

    assert bundle is not None
    assert bundle.hero.inventory_items == (("booster_potion", 1),)
    assert bundle.hero.learner_inventory_labels == ("+1 Booster Potion",)


def test_answer_without_reward_facts_has_no_bundle():
    assert project_committed_reward_bundle(_event()) is None


def test_full_bloom_compact_projection_groups_and_counts_hidden_event_ids() -> None:
    bundle = RewardBundleProjection(
        "answer:full-bloom",
        "2026-08-28T10:00:00Z",
        (
            RewardItemProjection(
                "bloom:rose",
                RewardHero.FULL_BLOOM,
                "Rose",
                "Full Bloom",
                garden_coins=14,
                plant_id="rose",
                plant_name="Rose",
                plant_class="Bonsai",
            ),
            RewardItemProjection(
                "stage:rose:mature",
                RewardHero.STAGE_CHANGE,
                "Rose",
                "Stage change",
                detail="Reached Mature",
                plant_id="rose",
                plant_name="Rose",
            ),
            RewardItemProjection(
                "find:morning-dew",
                RewardHero.GARDEN_FIND,
                "Morning Dew",
                "Standard Find",
                growth_units=4_000,
            ),
            RewardItemProjection(
                "discovery:rain",
                RewardHero.ENVIRONMENT_DISCOVERY,
                "Gentle Rain",
                "Environment discovery",
            ),
            RewardItemProjection(
                "discovery:twilight",
                RewardHero.ENVIRONMENT_DISCOVERY,
                "Verdant Twilight",
                "Environment discovery",
            ),
            RewardItemProjection(
                "checkpoint:rose:75",
                RewardHero.CHECKPOINT,
                "Rose",
                "Checkpoint reached",
                checkpoint_percent=75,
                plant_id="rose",
            ),
            RewardItemProjection(
                "booster:answer",
                RewardHero.COIN_OR_BOOSTER,
                "Booster extended",
                "Garden reward",
                inventory_items=(("booster_potion", 10),),
                detail="+10 cards",
            ),
        ),
    )

    compact = bundle.compact

    assert compact == RewardCompactProjection(
        eyebrow="MILESTONE REACHED",
        hero_title="Full Bloom achieved",
        hero_subtitle="Rose",
        visible_summaries=(
            RewardCompactSummary(
                "garden_finds",
                "1 Standard Find",
                ("find:morning-dew",),
                reward_type="garden_find",
            ),
            RewardCompactSummary(
                "discoveries",
                "2 Garden discoveries",
                ("discovery:rain", "discovery:twilight"),
                reward_type="environment_discovery",
            ),
        ),
        hidden_summaries=(
            RewardCompactSummary(
                "checkpoint:checkpoint:rose:75",
                "Checkpoint reached",
                ("checkpoint:rose:75",),
                reward_type="checkpoint",
            ),
            RewardCompactSummary(
                "inventory:booster:answer",
                "Booster Potion +10 cards",
                ("booster:answer",),
                "booster_potion",
                reward_type="booster",
            ),
        ),
        more_label="Details ›",
    )
    assert compact.hidden_event_ids == (
        "checkpoint:rose:75",
        "booster:answer",
    )
    assert "stage:rose:mature" not in {
        event_id
        for summary in (*compact.visible_summaries, *compact.hidden_summaries)
        for event_id in summary.event_ids
    }
    assert "stage:rose:mature" in {item.event_id for item in bundle.all_items}
    assert len(compact.visible_summaries) == 2
    assert bundle.remaining_count == 2


def test_secondary_reward_priority_is_semantic_stable_and_metadata_rich() -> None:
    hero = RewardItemProjection(
        "bloom:rose",
        RewardHero.FULL_BLOOM,
        "Rose",
        "Full Bloom",
        plant_id="rose",
        plant_name="Rose",
    )
    candidates = (
        RewardItemProjection(
            "growth:routine",
            RewardHero.ROUTINE_GROWTH,
            "Growth earned",
            "Routine Growth",
            growth_units=1_800,
            sequence=17,
        ),
        RewardItemProjection(
            "coins:daily",
            RewardHero.COIN_OR_BOOSTER,
            "Garden Coins",
            "Garden Coin reward",
            garden_coins=10,
            sequence=16,
        ),
        RewardItemProjection(
            "fertilizer:quality",
            RewardHero.COIN_OR_BOOSTER,
            "Fertilizer extended",
            "Garden reward",
            inventory_items=(("fertilizer_quality", 1),),
            sequence=15,
        ),
        RewardItemProjection(
            "booster:answer",
            RewardHero.COIN_OR_BOOSTER,
            "Booster extended",
            "Garden reward",
            inventory_items=(("booster_potion", 1),),
            sequence=14,
        ),
        RewardItemProjection(
            "checkpoint:rose:75",
            RewardHero.CHECKPOINT,
            "Rose",
            "Checkpoint reached",
            checkpoint_percent=75,
            sequence=13,
        ),
        RewardItemProjection(
            "discovery:firefly-evening",
            RewardHero.ENVIRONMENT_DISCOVERY,
            "Firefly Evening",
            "Environment discovery",
            rarity="rare",
            artwork_ref="firefly-evening.webp",
            sequence=12,
        ),
        RewardItemProjection(
            "customization:moonlit-planter",
            RewardHero.COIN_OR_BOOSTER,
            "Moonlit Planter",
            "Customization reward",
            inventory_items=(("moonlit_planter", 1),),
            artwork_ref="moonlit-planter.webp",
            sequence=11,
        ),
        RewardItemProjection(
            "find:morning-dew",
            RewardHero.GARDEN_FIND,
            "Morning Dew",
            "Standard Find",
            growth_units=4_000,
            rarity="common",
            artwork_ref="morning-dew.webp",
            sequence=10,
        ),
    )
    bundle = RewardBundleProjection(
        "answer:priority",
        "2026-08-28T10:00:00Z",
        (hero, *candidates),
    )

    summaries = (*bundle.visible_summaries, *bundle.hidden_summaries)
    assert tuple(summary.reward_type for summary in summaries) == (
        "garden_find",
        "customization_unlock",
        "environment_discovery",
        "checkpoint",
        "booster",
        "fertilizer",
        "coins",
        "growth",
    )
    assert tuple(summary.label for summary in bundle.visible_summaries) == (
        "1 Standard Find",
        "Moonlit Planter +1",
    )
    assert summaries[0].event_ids == ("find:morning-dew",)
    assert summaries[0].artwork_ref == "morning-dew.webp"
    assert summaries[0].artwork_refs == ("morning-dew.webp",)
    assert summaries[0].art_assets == ("morning-dew.webp",)
    assert summaries[0].rarity == "common"
    assert summaries[0].semantic_type == "garden_find"
    growth = summaries[-1]
    assert growth.event_ids == ("growth:routine",)
    assert "find:morning-dew" not in growth.event_ids


def test_secondary_ties_use_event_sequence_then_event_id() -> None:
    hero = RewardItemProjection(
        "bloom:rose",
        RewardHero.FULL_BLOOM,
        "Rose",
        "Full Bloom",
    )
    later_id = RewardItemProjection(
        "customization:zeta",
        RewardHero.COIN_OR_BOOSTER,
        "Zeta Planter",
        "Customization reward",
        inventory_items=(("zeta_planter", 1),),
        sequence=4,
    )
    earlier_id = RewardItemProjection(
        "customization:alpha",
        RewardHero.COIN_OR_BOOSTER,
        "Alpha Planter",
        "Customization reward",
        inventory_items=(("alpha_planter", 1),),
        sequence=4,
    )
    first = RewardBundleProjection(
        "answer:stable-tie",
        "2026-08-28T10:00:00Z",
        (hero, later_id, earlier_id),
    )
    second = RewardBundleProjection(
        "answer:stable-tie",
        "2026-08-28T10:00:00Z",
        (hero, earlier_id, later_id),
    )

    expected = ("customization:alpha", "customization:zeta")
    assert tuple(summary.event_ids[0] for summary in first.visible_summaries) == expected
    assert tuple(summary.event_ids[0] for summary in second.visible_summaries) == expected


def test_session_history_names_meaningful_events_and_aggregates_routine_growth() -> None:
    bloom = RewardBundleProjection(
        "answer:bloom",
        "2026-08-28T10:00:00Z",
        (
            RewardItemProjection(
                "bloom:rose",
                RewardHero.FULL_BLOOM,
                "Rose",
                "Full Bloom",
                garden_coins=14,
                plant_name="Rose",
                artwork_ref="rose-rare.webp",
            ),
            RewardItemProjection(
                "growth:plant",
                RewardHero.ROUTINE_GROWTH,
                "Growth earned",
                "Routine Growth",
                growth_units=1_000,
            ),
        ),
    )
    collectibles = RewardBundleProjection(
        "answer:collectibles",
        "2026-08-28T10:01:00Z",
        (
            RewardItemProjection(
                "find:morning-dew",
                RewardHero.GARDEN_FIND,
                "Morning Dew",
                "Standard Find",
                growth_units=4_000,
                rarity="common",
                artwork_ref="morning-dew.webp",
                detail="+40 Growth",
            ),
            RewardItemProjection(
                "discovery:firefly-evening",
                RewardHero.ENVIRONMENT_DISCOVERY,
                "Firefly Evening",
                "Environment discovery",
                artwork_ref="firefly-evening.webp",
                detail="Cosmetic environment",
            ),
            RewardItemProjection(
                "growth:shared",
                RewardHero.ROUTINE_GROWTH,
                "Shared Growth",
                "Routine Growth",
                growth_units=800,
            ),
        ),
    )
    original_items = (bloom.all_items, collectibles.all_items)

    rows = project_reward_session_history((bloom, collectibles, bloom))

    assert tuple(row.name for row in rows) == (
        "Full Bloom achieved",
        "Morning Dew",
        "Firefly Evening",
        "Growth applied",
    )
    assert rows[0].value == "Rose · +14 Garden Coins"
    assert rows[1].category_label == "Standard Find"
    assert rows[1].value == "+40 Growth"
    assert rows[2].category_label == "Discovery"
    assert rows[2].artwork_ref == "firefly-evening.webp"
    assert rows[-1] == RewardDetailRow(
        category_label="Routine Growth",
        name="Growth applied",
        value="+18 Growth",
        event_ids=("growth:plant", "growth:shared"),
    )
    assert (bloom.all_items, collectibles.all_items) == original_items


def test_detail_action_tracks_structured_rows_instead_of_hidden_count() -> None:
    full_bloom = RewardBundleProjection(
        "answer:full-bloom-only",
        "2026-08-28T10:00:00Z",
        (RewardItemProjection(
            "bloom:rose",
            RewardHero.FULL_BLOOM,
            "Rose",
            "Full Bloom",
            plant_id="rose",
            plant_name="Rose",
        ),),
    )
    coin_only = RewardBundleProjection(
        "answer:coin-only",
        "2026-08-28T10:00:00Z",
        (RewardItemProjection(
            "coins:daily",
            RewardHero.COIN_OR_BOOSTER,
            "Garden Coins",
            "Garden Coin reward",
            garden_coins=3,
        ),),
    )

    assert full_bloom.remaining_count == 0
    assert full_bloom.detail_expansion_available is True
    assert full_bloom.has_detail_expansion is True
    assert full_bloom.more_label == "Details ›"
    assert coin_only.detail_expansion_available is False
    assert coin_only.more_label == ""


def test_detail_rows_are_pure_structured_projections_of_atomic_bundle_items() -> None:
    items = (
        RewardItemProjection(
            "bloom:rose",
            RewardHero.FULL_BLOOM,
            "Rose",
            "Full Bloom",
            garden_coins=14,
            artwork_ref="rose-rare.webp",
            plant_id="rose",
            plant_name="Rose",
            new_stage="rare",
        ),
        RewardItemProjection(
            "find:morning-dew",
            RewardHero.GARDEN_FIND,
            "Morning Dew",
            "Standard Find",
            growth_units=4_000,
            artwork_ref="morning-dew.webp",
        ),
        RewardItemProjection(
            "discovery:twilight",
            RewardHero.ENVIRONMENT_DISCOVERY,
            "Verdant Twilight",
            "Environment discovery",
            artwork_ref="twilight.webp",
        ),
        RewardItemProjection(
            "booster:answer",
            RewardHero.COIN_OR_BOOSTER,
            "Booster extended",
            "Garden reward",
            inventory_items=(("booster_potion", 2),),
            detail="+10 cards",
        ),
        RewardItemProjection(
            "checkpoint:rose:75",
            RewardHero.CHECKPOINT,
            "Rose",
            "Checkpoint reached",
            garden_coins=2,
            checkpoint_percent=75,
            new_stage="flowering",
        ),
    )
    bundle = RewardBundleProjection(
        "answer:detail-rows",
        "2026-08-28T10:00:00Z",
        items,
    )

    expected = (
        RewardDetailRow(
            category_label="Full Bloom",
            name="Rose",
            value="Reached Full Bloom · +14 Garden Coins",
            event_ids=("bloom:rose",),
            artwork_ref="rose-rare.webp",
        ),
        RewardDetailRow(
            category_label="Standard Find",
            name="Morning Dew",
            value="+40 Growth",
            event_ids=("find:morning-dew",),
            artwork_ref="morning-dew.webp",
        ),
        RewardDetailRow(
            category_label="Environment discovery",
            name="Verdant Twilight",
            value="New discovery",
            event_ids=("discovery:twilight",),
            artwork_ref="twilight.webp",
        ),
        RewardDetailRow(
            category_label="Garden reward",
            name="Booster extended",
            value="+10 cards · +2 Booster Potions",
            event_ids=("booster:answer",),
        ),
        RewardDetailRow(
            category_label="Checkpoint reached",
            name="Rose",
            value="75% toward Flowering · +2 Garden Coins",
            event_ids=("checkpoint:rose:75",),
        ),
    )
    assert project_reward_detail_rows(items) == expected
    assert bundle.detail_rows == expected
    assert expected[0].category == "Full Bloom"
    assert expected[0].art_asset == "rose-rare.webp"


def test_multi_stage_bundle_uses_highest_stage_as_hero_and_keeps_each_event():
    event = _event(milestones=(
        PlantMilestone(
            "stage:rose:young",
            "rose",
            "Rose",
            "stage_change",
            "2026-08-28T10:00:00Z",
            previous_stage="sprout",
            new_stage="young",
        ),
        PlantMilestone(
            "stage:rose:mature",
            "rose",
            "Rose",
            "stage_change",
            "2026-08-28T10:00:01Z",
            previous_stage="young",
            new_stage="mature",
        ),
    ))

    bundle = project_committed_reward_bundle(event)

    assert bundle is not None
    assert bundle.hero.event_id == "stage:rose:mature"
    assert bundle.hero.detail == "Reached Mature"
    assert bundle.compact.eyebrow == "NEW GROWTH STAGE"
    assert bundle.compact.hero_title == "Mature reached"
    assert bundle.compact.hero_subtitle == "Advanced 2 stages"
    assert bundle.compact.visible_summaries == ()
    assert {item.event_id for item in bundle.all_items} == {
        "stage:rose:young",
        "stage:rose:mature",
    }
    assert {item.sequence for item in bundle.all_items} == {0, 1}


@pytest.mark.parametrize(
    ("kind", "eyebrow", "more_label"),
    (
        (
            RewardHero.FULL_BLOOM,
            "MILESTONE REACHED",
            "Details ›",
        ),
        (RewardHero.GARDEN_FIND, "STANDARD FIND", ""),
        (RewardHero.CHECKPOINT, "CHECKPOINT REACHED", ""),
        (RewardHero.ENVIRONMENT_DISCOVERY, "NEW DISCOVERY", ""),
    ),
)
def test_compact_projection_uses_event_specific_eyebrows(
    kind: RewardHero,
    eyebrow: str,
    more_label: str,
) -> None:
    item = RewardItemProjection(
        f"event:{kind.value}",
        kind,
        "Rose",
        "Garden reward",
        plant_name="Rose",
    )
    bundle = RewardBundleProjection(
        f"answer:{kind.value}",
        "2026-08-28T10:00:00Z",
        (item,),
    )

    assert bundle.compact.eyebrow == eyebrow
    assert bundle.compact.visible_summaries == ()
    assert bundle.more_label == more_label


def test_checkpoint_compact_copy_names_progress_and_next_target() -> None:
    event = _event(
        coin_awards=(CoinAward(
            "coin:checkpoint",
            "checkpoint",
            "50% checkpoint",
            2,
        ),),
        milestones=(PlantMilestone(
            "checkpoint:rose:50",
            "rose",
            "Rose",
            "checkpoint",
            "2026-08-28T10:00:00Z",
            plant_art_asset="rose-young.webp",
            checkpoint_percent=50,
            new_stage="mature",
            coin_reward=2,
            coin_award_event_ids=("coin:checkpoint",),
            coin_included_in_total=True,
        ),),
    )

    bundle = project_committed_reward_bundle(event)

    assert bundle is not None
    assert bundle.hero.kind is RewardHero.CHECKPOINT
    assert bundle.hero.artwork_ref == "rose-young.webp"
    assert bundle.hero.garden_coins == 2
    assert bundle.compact.eyebrow == "CHECKPOINT REACHED"
    assert bundle.compact.hero_title == "50% checkpoint"
    assert bundle.compact.hero_subtitle == "Next checkpoint at 75%"


def test_single_stage_compact_copy_names_only_the_final_stage() -> None:
    event = _event(milestones=(PlantMilestone(
        "stage:rose:young",
        "rose",
        "Rose",
        "stage_change",
        "2026-08-28T10:00:00Z",
        new_stage="young",
    ),))

    bundle = project_committed_reward_bundle(event)

    assert bundle is not None
    assert bundle.compact.eyebrow == "NEW GROWTH STAGE"
    assert bundle.compact.hero_title == "Young reached"
    assert bundle.compact.hero_subtitle == ""


def test_environment_discovery_uses_named_discovery_contract() -> None:
    event = _event(environment_discoveries=(EnvironmentDiscovery(
        "environment:firefly-evening",
        "firefly_evening",
        "Firefly Evening",
        "scenery",
        "rare",
        "firefly-evening.webp",
        "Cosmetic environment",
    ),))

    bundle = project_committed_reward_bundle(event)

    assert bundle is not None
    assert bundle.hero.kind is RewardHero.ENVIRONMENT_DISCOVERY
    assert bundle.compact.eyebrow == "NEW DISCOVERY"
    assert bundle.compact.hero_title == "Firefly Evening"
    assert bundle.compact.hero_subtitle == "Cosmetic environment"


@pytest.mark.parametrize(
    ("source_type", "source_label", "amount", "routine_only"),
    (
        ("daily_activity", "First card today", 2, True),
        ("review", "Review reward", 4, True),
        ("review", "Review reward", 5, False),
        ("all_due", "Today’s Cards", 2, False),
        ("achievement", "Seven-day streak", 2, False),
        ("checkpoint", "25% checkpoint", 2, False),
    ),
)
def test_small_ordinary_coin_only_bundle_does_not_become_a_major_reveal(
    source_type: str,
    source_label: str,
    amount: int,
    routine_only: bool,
) -> None:
    event = _event(coin_awards=(CoinAward(
        f"coin:{source_type}",
        source_type,
        source_label,
        amount,
        event_key=f"{source_type}:stable",
    ),))

    bundle = project_committed_reward_bundle(event)

    assert bundle is not None
    assert bundle.hero.garden_coins == amount
    assert bundle.routine_only is routine_only
    assert bundle.has_major_reward is (not routine_only)


def test_small_receipt_only_coin_reward_is_routine_but_inventory_is_major() -> None:
    event_id = "answer:receipt-routine"
    coin_receipt = RewardReceipt(
        "daily_activity:2026-08-28",
        "coins",
        "daily_activity",
        "2026-08-28",
        "2026-08-28",
        event_id,
        "2026-08-28T10:00:00Z",
        amount=2,
        title="First card today",
    )
    booster_receipt = RewardReceipt(
        "booster:2026-08-28",
        "inventory_item",
        "daily_activity",
        "2026-08-28",
        "2026-08-28",
        event_id,
        "2026-08-28T10:00:00Z",
        amount=1,
        item_id="booster_potion",
        title="Booster Potion",
    )
    cycle_receipt = RewardReceipt(
        "completion_cycle_5:2026-08-28",
        "coins",
        "completion_cycle_5",
        "completion_cycle_5",
        "2026-08-28",
        event_id,
        "2026-08-28T10:00:00Z",
        amount=30,
    )

    routine_bundle = project_committed_reward_bundle(
        _event(event_id=event_id, reward_receipts=(coin_receipt,)),
    )
    major_bundle = project_committed_reward_bundle(
        _event(event_id=event_id, reward_receipts=(booster_receipt,)),
    )
    cycle_bundle = project_committed_reward_bundle(
        _event(event_id=event_id, reward_receipts=(cycle_receipt,)),
    )
    stacked_bundle = project_committed_reward_bundle(
        _event(
            event_id=event_id,
            reward_receipts=(cycle_receipt, booster_receipt),
        ),
    )

    assert routine_bundle is not None
    assert routine_bundle.routine_only is True
    assert major_bundle is not None
    assert major_bundle.routine_only is False
    assert cycle_bundle is not None
    assert (
        cycle_bundle.hero.title,
        cycle_bundle.hero.detail,
        cycle_bundle.hero.artwork_ref,
        cycle_bundle.hero.garden_coins,
    ) == (
        "Garden Cycle complete",
        "5 completed review days",
        "ui_garden_coin",
        30,
    )
    assert cycle_bundle.routine_only is False
    assert stacked_bundle is not None
    assert stacked_bundle.hero.title == "Booster Potion"
    assert next(
        item for item in stacked_bundle.all_items
        if item.event_id == cycle_receipt.event_key
    ).routine is True
