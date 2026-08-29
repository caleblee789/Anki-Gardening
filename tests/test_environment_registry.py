from __future__ import annotations

from ankigarden.environment import GARDEN_FEATURE_CATALOG, SCENERY_CATALOG


def _effect_rows(item):
    return tuple(
        (
            effect.effect_id,
            effect.trigger,
            effect.value_kind,
            effect.amount,
            effect.first_cards,
            effect.every_nth_card,
            effect.every_nth_completion,
            effect.inventory_item_id,
            tuple(
                (reward.item_id, reward.weight_percent)
                for reward in effect.weighted_rewards
            ),
        )
        for effect in item.effects
    )


def test_normalized_garden_feature_effects_are_structured_and_player_copy_is_plain():
    assert GARDEN_FEATURE_CATALOG["harvest_bell"].effect == (
        "+5 Coins when today’s cards are complete."
    )
    assert _effect_rows(GARDEN_FEATURE_CATALOG["harvest_bell"]) == ((
        "completion_coins_plus_5",
        "today_cards_complete",
        "coins",
        5,
        None,
        None,
        None,
        None,
        (),
    ),)
    assert _effect_rows(GARDEN_FEATURE_CATALOG["firefly_lantern"]) == ((
        "growth_first_15_plus_5",
        "eligible_card",
        "growth",
        5,
        15,
        None,
        None,
        None,
        (),
    ),)
    assert _effect_rows(GARDEN_FEATURE_CATALOG["prism_trellis"]) == ((
        "completion_direct_growth_plus_100",
        "today_cards_complete",
        "instant_growth",
        100,
        None,
        None,
        None,
        None,
        (),
    ),)


def test_normalized_scenery_effects_are_structured_and_bounded():
    summer = _effect_rows(SCENERY_CATALOG["summer"])[0]
    assert summer[2:6] == ("growth", 1, 100, 2)

    autumn = SCENERY_CATALOG["autumn"]
    assert autumn.price == 500
    assert _effect_rows(autumn)[0][2:4] == ("milestone_coin_percent", 50)

    snowy = _effect_rows(SCENERY_CATALOG["snowy"])[0]
    assert snowy[1:4] == ("today_cards_complete", "inventory_item", 1)
    assert snowy[7] == "growth_charge_small"

    rainbow = _effect_rows(SCENERY_CATALOG["rainbow_horizon"])[0]
    assert rainbow[2:5] == ("growth", 1, 100)

    halloween = _effect_rows(SCENERY_CATALOG["halloween"])[0]
    assert halloween[1] == "today_cards_complete"
    assert halloween[8] == (
        ("growth_charge_small", 85),
        ("growth_charge_standard", 10),
        ("booster_potion", 5),
    )

    full_moon = _effect_rows(SCENERY_CATALOG["full_moon"])
    assert full_moon[0][1:4] == (
        "today_cards_complete", "inventory_item", 1
    )
    assert full_moon[0][6:8] == (4, "booster_potion")
    assert full_moon[1][1:4] == (
        "booster_activation", "booster_cards", 25
    )

    eclipse = _effect_rows(SCENERY_CATALOG["eclipse"])[0]
    assert eclipse[2:5] == ("growth", 2, 100)


def test_environment_copy_avoids_deprecated_completion_and_answer_terms():
    player_copy = "\n".join(
        item.effect
        for catalog in (GARDEN_FEATURE_CATALOG, SCENERY_CATALOG)
        for item in catalog.values()
    ).lower()
    assert "all clear" not in player_copy
    assert "all due" not in player_copy
    assert "required card" not in player_copy
    assert "card answer" not in player_copy
