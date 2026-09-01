from __future__ import annotations

from ankigarden.reward_presentation import (
    RewardBundleProjection,
    RewardHero,
    RewardItemProjection,
)
from ankigarden.ui.event_presentation import (
    EventPresentationKind,
    EventPresentationUnit,
    EventRowPresentation,
    SourceQuantityContribution,
    committed_reward_event_rows,
    event_amount_total,
)


def test_committed_reward_rows_keep_explicit_kinds_units_and_totals() -> None:
    bundle = RewardBundleProjection(
        bundle_id="full-bloom:plant-1",
        occurred_at="2026-09-01T12:00:00Z",
        all_items=(
            RewardItemProjection(
                "full-bloom:event",
                RewardHero.FULL_BLOOM,
                "Wisteria reached Full Bloom",
                "Full Bloom",
                garden_coins=14,
                artwork_ref="wisteria_rare",
            ),
            RewardItemProjection(
                "find:event",
                RewardHero.GARDEN_FIND,
                "Small Growth Charge",
                "Standard Find",
                artwork_ref="growth_charge_small",
            ),
            RewardItemProjection(
                "discovery:one",
                RewardHero.ENVIRONMENT_DISCOVERY,
                "Firefly Lantern",
                "Discovery",
                artwork_ref="garden_feature_firefly_lantern",
            ),
            RewardItemProjection(
                "discovery:two",
                RewardHero.ENVIRONMENT_DISCOVERY,
                "Morning Dew",
                "Discovery",
                artwork_ref="weather_morning_dew",
            ),
        ),
    )

    rows = committed_reward_event_rows(bundle)

    assert tuple(row.tone for row in rows) == (
        "violet",
        "aqua",
        "aqua",
        "aqua",
    )
    assert event_amount_total(
        rows,
        kind=EventPresentationKind.FULL_BLOOM,
        unit=EventPresentationUnit.GARDEN_COINS,
    ) == 14
    assert event_amount_total(
        rows,
        kind=EventPresentationKind.STANDARD_FIND,
        unit=EventPresentationUnit.STANDARD_FINDS,
    ) == 1
    assert event_amount_total(
        rows,
        kind=EventPresentationKind.DISCOVERY,
        unit=EventPresentationUnit.DISCOVERIES,
    ) == 2


def test_effect_and_source_records_do_not_encode_units_in_copy() -> None:
    effect = EventRowPresentation(
        EventPresentationKind.EFFECT_REMAINING,
        "Quality Fertilizer",
        38,
        EventPresentationUnit.CARDS,
        "Active effect",
        "fertilizer_quality",
        None,
    )
    source = SourceQuantityContribution("Full Bloom", 1, ("event:one",))

    assert (effect.amount, effect.unit.value, effect.tone) == (38, "cards", "sage")
    assert (source.label, source.quantity, source.event_ids) == (
        "Full Bloom",
        1,
        ("event:one",),
    )
