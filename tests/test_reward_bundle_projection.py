from __future__ import annotations

import pytest

from ankigarden.models.state import RewardReceipt
from ankigarden.reward_presentation import (
    RewardBundleProjection,
    RewardCompactProjection,
    RewardCompactSummary,
    RewardHero,
    RewardItemProjection,
    project_committed_reward_bundle,
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
        "+55 growth",
        "1 discovery",
    ]
    assert bundle.remaining_count == 2
    assert bundle.more_label == "2 more rewards ›"
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
    assert bundle.visible_summaries[0].label == "2 Garden Finds"
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
    assert first.more_label == ""


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
                "Garden Find",
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
                "growth",
                "+40 growth",
                ("find:morning-dew",),
            ),
            RewardCompactSummary(
                "discoveries",
                "2 discoveries",
                ("discovery:rain", "discovery:twilight"),
            ),
        ),
        hidden_summaries=(
            RewardCompactSummary(
                "inventory:booster:answer",
                "Booster +10 cards",
                ("booster:answer",),
            ),
            RewardCompactSummary(
                "checkpoint:checkpoint:rose:75",
                "Checkpoint reached",
                ("checkpoint:rose:75",),
            ),
        ),
        more_label="2 more rewards ›",
    )
    assert compact.hidden_event_ids == (
        "booster:answer",
        "checkpoint:rose:75",
    )
    assert "stage:rose:mature" not in {
        event_id
        for summary in (*compact.visible_summaries, *compact.hidden_summaries)
        for event_id in summary.event_ids
    }
    assert "stage:rose:mature" in {item.event_id for item in bundle.all_items}
    assert len(compact.visible_summaries) == 2
    assert bundle.remaining_count == 2


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
    assert {item.event_id for item in bundle.all_items} == {
        "stage:rose:young",
        "stage:rose:mature",
    }
    assert {item.sequence for item in bundle.all_items} == {0, 1}


@pytest.mark.parametrize(
    ("kind", "eyebrow"),
    (
        (RewardHero.FULL_BLOOM, "MILESTONE REACHED"),
        (RewardHero.GARDEN_FIND, "GARDEN FIND"),
        (RewardHero.CHECKPOINT, "CHECKPOINT REACHED"),
        (RewardHero.ENVIRONMENT_DISCOVERY, "DISCOVERY"),
    ),
)
def test_compact_projection_uses_event_specific_eyebrows(
    kind: RewardHero,
    eyebrow: str,
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
    assert bundle.more_label == ""
