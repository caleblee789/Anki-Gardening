from __future__ import annotations

from dataclasses import replace

import pytest

from ankigarden.models.state import RewardReceipt

from ankigarden.ui.session_summary import (
    AuthoritativeEventReversal,
    BoosterSnapshot,
    CoinAward,
    CommittedSessionEvent,
    EffectsSnapshot,
    EnvironmentDiscovery,
    FertilizerSnapshot,
    FindItemQuantity,
    LiveSessionSnapshot,
    PlantGrowthDelta,
    PlantMilestone,
    ReviewContinuationTarget,
    RewardComponent,
    SessionEndSnapshot,
    SessionProjectGrowthAllocation,
    SessionStartSnapshot,
    SessionSummaryAccumulator,
    StandardFind,
    TodayCardsSnapshot,
    format_growth_units,
    project_session_day,
    project_today_cards,
    unlock_category_copy,
)


DAY_ONE = "2026-08-28"
DAY_TWO = "2026-08-29"


def _today(
    status: str = "in_progress",
    *,
    remaining: int | None = 18,
    complete: int = 0,
    waiting: int = 0,
    due_in: int = 0,
    reward_coins: int = 0,
    currently_due: int | None = None,
    total: int | None = None,
    kind: str = "reviewable",
    scope: str = "all_decks",
    scope_label: str = "",
    contributing_decks: int = 1,
    can_continue: bool | None = None,
    continuation_target: ReviewContinuationTarget | None = None,
) -> TodayCardsSnapshot:
    normalized_due = currently_due
    if normalized_due is None and status == "in_progress":
        normalized_due = max(0, int(remaining or 0))
    if can_continue is None:
        can_continue = bool(
            status == "in_progress"
            and kind == "reviewable"
            and int(normalized_due or 0) > 0
        )
    if can_continue and continuation_target is None:
        continuation_target = ReviewContinuationTarget("deck", 1, "Default")
    if total is None and remaining is not None:
        total = complete + remaining
    return TodayCardsSnapshot(
        status=status,  # type: ignore[arg-type]
        cards_remaining=remaining,
        cards_completed=complete,
        waiting_cards=waiting,
        currently_due_cards=normalized_due,
        next_due_in_seconds=due_in,
        reward_coins=reward_coins,
        cards_total=total,
        kind=kind,  # type: ignore[arg-type]
        scope=scope,  # type: ignore[arg-type]
        scope_label=scope_label,
        contributing_deck_count=contributing_decks,
        can_continue_reviews=can_continue,
        continuation_target=continuation_target,
    )


def _start(
    *,
    today: TodayCardsSnapshot | None = None,
    effects: EffectsSnapshot | None = None,
    known: frozenset[str] = frozenset(),
    owned: frozenset[str] = frozenset(),
) -> SessionStartSnapshot:
    return SessionStartSnapshot(
        today_cards=today or _today(remaining=160, total=160),
        effects=effects or EffectsSnapshot(),
        existing_event_ids=known,
        owned_environment_ids=owned,
    )


def _accumulator(
    *,
    start: SessionStartSnapshot | None = None,
) -> SessionSummaryAccumulator:
    return SessionSummaryAccumulator(
        session_id="session-local-1",
        started_at="2026-08-28T10:00:00Z",
        anki_day_id=DAY_ONE,
        start_snapshot=start or _start(),
    )


def _event(
    event_id: str,
    *,
    day: str = DAY_ONE,
    cards: int = 1,
    plant_growth: tuple[PlantGrowthDelta, ...] = (),
    shared_growth: tuple[PlantGrowthDelta, ...] = (),
    stored: int = 0,
    landmark: int = 0,
    projects: tuple[SessionProjectGrowthAllocation, ...] = (),
    coins: tuple[CoinAward, ...] = (),
    finds: tuple[StandardFind, ...] = (),
    milestones: tuple[PlantMilestone, ...] = (),
    discoveries: tuple[EnvironmentDiscovery, ...] = (),
    receipts: tuple[RewardReceipt, ...] = (),
    total_finds: int | None = None,
) -> CommittedSessionEvent:
    return CommittedSessionEvent(
        event_id=event_id,
        anki_day_id=day,
        occurred_at="2026-08-28T10:01:00Z",
        cards_completed=cards,
        plant_growth=plant_growth,
        shared_growth=shared_growth,
        stored_growth_delta_units=stored,
        project_allocations=projects,
        landmark_growth_delta_units=landmark,
        coin_awards=coins,
        standard_finds=finds,
        milestones=milestones,
        environment_discoveries=discoveries,
        reward_receipts=receipts,
        total_finds=(
            sum(find.quantity for find in finds)
            if total_finds is None else total_finds
        ),
    )


def _finish(
    accumulator: SessionSummaryAccumulator,
    *,
    end: SessionEndSnapshot | None = None,
):
    return accumulator.finalize(
        ended_at="2026-08-28T11:00:00Z",
        end_snapshot=end or SessionEndSnapshot(
            _today(remaining=18, complete=142, total=160)
        ),
    )


def test_plant_milestone_supports_defaulted_plant_class_metadata() -> None:
    legacy = PlantMilestone(
        "milestone:legacy",
        "plant:rose",
        "Rose",
        "checkpoint",
        "2026-08-28T10:00:00Z",
    )
    typed = PlantMilestone(
        "milestone:typed",
        "plant:juniper",
        "Juniper",
        "full_bloom",
        "2026-08-28T10:00:01Z",
        plant_class="  Bonsai  ",
    )

    assert legacy.plant_class == ""
    assert typed.plant_class == "Bonsai"


def test_accumulator_uses_exact_committed_deltas_and_deduplicates_transactions():
    accumulator = _accumulator()
    event = _event(
        "card:1",
        plant_growth=(
            PlantGrowthDelta("juniper", "Juniper", 84_250, "bonsai", "juniper.webp"),
            PlantGrowthDelta("rose", "Rose", 12_000),
        ),
        shared_growth=(PlantGrowthDelta("rose", "Rose", 16_200),),
        stored=1_850,
        coins=(CoinAward("coin:1", "today_cards", "Today’s Cards", 10),),
        finds=(StandardFind(
            "find:1",
            "morning_dew",
            "Morning Dew",
            "common",
            "growth",
            "+40 Plant Growth",
            40,
        ),),
    )

    assert accumulator.accept_committed(event) is True
    assert accumulator.accept_committed(event) is False
    assert accumulator.accept_committed(_event("card:2")) is True

    payload = _finish(accumulator)
    assert payload is not None
    assert payload.cards_completed == 2
    summary = payload.segments[0]
    assert summary.plant_growth_total_units == 96_250
    assert [(row.plant_id, row.growth_units) for row in summary.plant_growth_by_plant] == [
        ("juniper", 84_250),
        ("rose", 12_000),
    ]
    assert summary.shared_growth_total_units == 16_200
    assert summary.stored_growth.delta_units == 1_850
    assert summary.garden_coins_earned == 10
    assert [item.find_id for item in summary.standard_finds] == ["morning_dew"]
    assert summary.growth_applied_total_units == 112_450


def test_landmark_progress_flows_through_live_final_and_projection_surfaces():
    accumulator = _accumulator()
    assert accumulator.accept_committed(_event(
        "card:landmark-1",
        plant_growth=(PlantGrowthDelta("rose", "Rose", 1_000),),
        shared_growth=(PlantGrowthDelta("bonsai", "Bonsai", 200),),
        stored=50,
        landmark=250,
    ))
    assert accumulator.accept_committed(_event(
        "card:landmark-2",
        landmark=50,
    ))

    end = SessionEndSnapshot(_today(remaining=18, complete=142, total=160))
    live = accumulator.live_snapshot(
        ended_at="2026-08-28T10:30:00Z",
        end_snapshot=end,
    )
    assert live.landmark_growth_delta_units == 300
    assert live.footer_growth_units == 1_550

    payload = _finish(accumulator, end=end)
    assert payload is not None
    summary = payload.segments[0]
    projection = project_session_day(summary)
    assert summary.landmark_growth_delta_units == 300
    assert summary.growth_applied_total_units == 1_200
    assert projection.landmark_growth_delta_units == 300
    assert (
        "landmark_progress",
        "Landmark progress",
        "+3",
    ) in [
        (row.key, row.label, row.value) for row in projection.result_rows
    ]


def test_committed_project_allocations_flow_without_mutable_state_inference():
    accumulator = _accumulator()
    assert accumulator.accept_committed(_event(
        "card:projects-1",
        plant_growth=(PlantGrowthDelta("rose", "Rose", 1_000),),
        landmark=250,
        projects=(
            SessionProjectGrowthAllocation("landmark", "garden_landmark", 250),
            SessionProjectGrowthAllocation("mastery", "bonsai", 100),
        ),
    ))
    assert accumulator.accept_committed(_event(
        "card:projects-2",
        projects=(
            SessionProjectGrowthAllocation("mastery", "bonsai", 50),
            SessionProjectGrowthAllocation("legacy", "garden_legacy", 25),
        ),
    ))

    end = SessionEndSnapshot(_today(remaining=18, complete=142, total=160))
    live = accumulator.live_snapshot(
        ended_at="2026-08-28T10:30:00Z",
        end_snapshot=end,
    )
    expected = [
        ("landmark", "garden_landmark", 250),
        ("mastery", "bonsai", 150),
        ("legacy", "garden_legacy", 25),
    ]
    assert [(row.target_type, row.target_id, row.units) for row in live.project_allocations] == expected
    assert live.project_growth_total_units == 425
    assert live.footer_growth_units == 1_425

    payload = _finish(accumulator, end=end)
    assert payload is not None
    summary = payload.segments[0]
    projection = project_session_day(summary)
    assert [(row.target_type, row.target_id, row.units) for row in summary.project_allocations] == expected
    assert [(row.target_type, row.target_id, row.units) for row in payload.project_allocations] == expected
    assert [(row.target_type, row.target_id, row.units) for row in projection.project_allocations] == expected


def test_reward_strip_uses_applied_growth_and_signed_non_additive_totals():
    accumulator = _accumulator()
    accumulator.accept_committed(_event(
        "card:accounting",
        plant_growth=(PlantGrowthDelta("wisteria", "Wisteria", 148_600),),
        shared_growth=(PlantGrowthDelta("juniper", "Juniper", 59_400),),
        stored=1_250,
        coins=(CoinAward("coin:total", "session", "Session rewards", 67),),
        finds=tuple(
            StandardFind(
                f"find:{index}", f"find-{index}", f"Find {index}",
                "common", "growth", "+10 Growth", 10,
            )
            for index in range(3)
        ),
    ))

    payload = _finish(accumulator)
    assert payload is not None
    summary = payload.segments[0]
    projection = project_session_day(summary)

    assert summary.growth_applied_total_units == 208_000
    assert summary.stored_growth.delta_units == 1_250
    assert [(row.key, row.label, row.value) for row in projection.reward_metrics] == [
        ("growth_applied", "Growth applied", "+2,080"),
        ("garden_coins", "Coins", "+67"),
        ("standard_finds", "Standard Finds", "+3"),
    ]
    assert not any(row.key == "shared_growth" for row in projection.result_rows)
    assert not any(row.key == "stored_growth" for row in projection.result_rows)


def test_coin_total_keeps_session_subtotal_and_explicit_additional_rewards():
    accumulator = _accumulator()
    accumulator.accept_committed(_event(
        "card:coin-inclusion",
        coins=(
            CoinAward(
                "coin:included",
                "review",
                "Review rewards",
                17,
                included_in_total=True,
            ),
            CoinAward(
                "coin:additional",
                "external",
                "Additional reward",
                50,
                included_in_total=False,
            ),
        ),
    ))

    payload = _finish(accumulator)
    assert payload is not None
    summary = payload.segments[0]
    assert summary.garden_coins_earned == 17
    assert summary.additional_coins_earned == 50
    assert summary.garden_coins_total == 67
    assert summary.coin_sources_reconciled is True
    assert [award.event_id for award in summary.coin_sources] == [
        "coin:included",
        "coin:additional",
    ]
    assert [
        (row.key, row.value)
        for row in project_session_day(summary).reward_metrics
    ] == [("garden_coins", "+67")]


def test_coin_source_mismatch_keeps_authoritative_total_and_omits_details(caplog):
    accumulator = _accumulator()
    accumulator.accept_committed(_event(
        "card:coin-mismatch",
        coins=(CoinAward("coin:source", "review", "Review rewards", 17),),
    ))
    payload = _finish(accumulator)
    assert payload is not None

    with caplog.at_level("WARNING"):
        summary = replace(
            payload.segments[0],
            garden_coins_earned=23,
        )

    projection = project_session_day(summary)
    assert summary.garden_coins_earned == 23
    assert summary.coin_sources_reconciled is False
    assert summary.coin_sources == ()
    assert [(row.key, row.value) for row in projection.reward_metrics] == [
        ("garden_coins", "+23"),
    ]
    assert projection.coin_details.visible == ()
    assert "Coin details omitted" in caplog.text


def test_coin_detail_mismatch_preserves_authoritative_extra_awards(caplog):
    accumulator = _accumulator()
    accumulator.accept_committed(_event(
        "card:coin-extra-mismatch",
        coins=(
            CoinAward("coin:source", "review", "Review rewards", 17),
            CoinAward(
                "coin:bonus",
                "external",
                "Milestone bonus",
                50,
                included_in_total=False,
            ),
        ),
    ))
    payload = _finish(accumulator)
    assert payload is not None

    with caplog.at_level("WARNING"):
        summary = replace(payload.segments[0], garden_coins_earned=23)

    assert summary.coin_sources_reconciled is False
    assert summary.coin_sources == ()
    assert summary.additional_coins_earned == 50
    assert summary.garden_coins_total == 73
    assert [(row.key, row.value) for row in project_session_day(summary).reward_metrics] == [
        ("garden_coins", "+73"),
    ]


def test_exact_typed_reward_receipts_survive_grouping_without_double_counting():
    receipts = (
        RewardReceipt(
            event_key="full-bloom:p1",
            reward_type="coins",
            source="plant_stage",
            source_id="p1",
            scheduler_day=DAY_ONE,
            correlation_id="card:receipt",
            occurred_at="2026-08-28T10:01:00Z",
            amount=20,
            title="Full Bloom",
        ),
        RewardReceipt(
            event_key="full-bloom:p1",
            reward_type="inventory_item",
            source="plant_stage",
            source_id="p1",
            scheduler_day=DAY_ONE,
            correlation_id="card:receipt",
            occurred_at="2026-08-28T10:01:00Z",
            amount=1,
            item_id="growth_charge_small",
            title="Full Bloom",
        ),
    )
    accumulator = _accumulator()
    accumulator.accept_committed(_event("card:receipt", receipts=receipts))
    accumulator.accept_committed(_event("card:receipt:replay", receipts=receipts))

    payload = _finish(accumulator)
    assert payload is not None
    assert payload.cards_completed == 2
    assert payload.segments[0].reward_receipts == receipts


def test_milestone_coin_component_has_an_explicit_total_inclusion_link():
    coin = CoinAward(
        "coin:bloom",
        "full_bloom_bonus",
        "Full Bloom",
        20,
        event_key="stage:p1:rare",
        transaction_id="coin:bloom",
        correlation_id="card:bloom",
    )
    milestone = PlantMilestone(
        "stage:p1:rare",
        "p1",
        "Wisteria",
        "full_bloom",
        "2026-08-28T10:01:00Z",
        coin_reward=20,
        coin_award_event_ids=(coin.event_id,),
        coin_included_in_total=True,
    )
    accumulator = _accumulator()
    accumulator.accept_committed(_event(
        "card:bloom", coins=(coin,), milestones=(milestone,),
    ))

    payload = _finish(accumulator)
    assert payload is not None
    projection = project_session_day(payload.segments[0])
    highlight = projection.highlights.featured[0]
    assert payload.segments[0].garden_coins_earned == 20
    assert highlight.coin_award_event_ids == ("coin:bloom",)
    assert highlight.coin_included_in_total is True
    assert highlight.reward_text == "+20 coin bonus included"
    assert payload.segments[0].milestones[0].reward is not None
    assert (
        payload.segments[0].milestones[0].reward.component_type
        == "full_bloom_bonus"
    )

    with pytest.raises(ValueError, match="must link"):
        PlantMilestone(
            "stage:p2:rare", "p2", "Rose", "full_bloom",
            "2026-08-28T10:02:00Z", coin_reward=20,
            coin_included_in_total=True,
        )

    with pytest.raises(ValueError, match="must link"):
        PlantMilestone(
            "stage:p3:rare", "p3", "Dahlia", "full_bloom",
            "2026-08-28T10:03:00Z", coin_reward=50,
            coin_included_in_total=False,
        )


def test_additional_milestone_coin_component_names_the_displayed_total():
    included = CoinAward(
        "coin:review",
        "review",
        "Review rewards",
        17,
    )
    additional = CoinAward(
        "coin:bloom-bonus",
        "full_bloom_bonus",
        "Full Bloom bonus",
        50,
        included_in_total=False,
    )
    milestone = PlantMilestone(
        "stage:p1:rare-bonus",
        "p1",
        "Wisteria",
        "full_bloom",
        "2026-08-28T10:01:00Z",
        coin_reward=50,
        coin_award_event_ids=(additional.event_id,),
        coin_included_in_total=False,
    )
    accumulator = _accumulator()
    accumulator.accept_committed(_event(
        "card:bloom-bonus",
        coins=(included, additional),
        milestones=(milestone,),
    ))

    payload = _finish(accumulator)
    assert payload is not None
    summary = payload.segments[0]
    highlight = project_session_day(summary).highlights.featured[0]
    assert summary.garden_coins_earned == 17
    assert summary.additional_coins_earned == 50
    assert summary.garden_coins_total == 67
    assert highlight.reward_text == (
        "+50 coin bonus · included in +67 total"
    )


@pytest.mark.parametrize(
    ("award", "reward_amount", "reward_included"),
    (
        (
            CoinAward("coin:wrong-inclusion", "review", "Review", 50),
            50,
            False,
        ),
        (
            CoinAward(
                "coin:wrong-amount",
                "full_bloom_bonus",
                "Full Bloom bonus",
                49,
                included_in_total=False,
            ),
            50,
            False,
        ),
    ),
)
def test_milestone_coin_component_fails_closed_when_engine_link_disagrees(
    award,
    reward_amount,
    reward_included,
):
    milestone = PlantMilestone(
        f"stage:{award.event_id}",
        "p1",
        "Wisteria",
        "full_bloom",
        "2026-08-28T10:01:00Z",
        coin_reward=reward_amount,
        coin_award_event_ids=(award.event_id,),
        coin_included_in_total=reward_included,
    )
    accumulator = _accumulator()
    accumulator.accept_committed(_event(
        f"card:{award.event_id}",
        coins=(award,),
        milestones=(milestone,),
    ))

    payload = _finish(accumulator)
    assert payload is not None
    retained = payload.segments[0].milestones[0]
    assert retained.event_id == milestone.event_id
    assert retained.reward is None
    assert retained.coin_reward == 0
    assert (
        project_session_day(payload.segments[0])
        .highlights.featured[0]
        .reward_text
    ) == ""


def test_live_snapshot_is_exact_once_non_finalizing_and_matches_final_reducer():
    accumulator = _accumulator()
    event = _event(
        "card:live:1",
        plant_growth=(PlantGrowthDelta("juniper", "Juniper", 1_250),),
        shared_growth=(PlantGrowthDelta("rose", "Rose", 400),),
        stored=500,
        coins=(CoinAward("coin:live:1", "find", "Standard Find", 4),),
        finds=(StandardFind(
            "find:live:1",
            "morning_dew",
            "Morning Dew",
            "common",
            "growth",
            "+40 Growth",
            40,
        ),),
    )
    assert accumulator.accept_committed(event) is True
    assert accumulator.accept_committed(event) is False
    accumulator.accept_committed(_event("card:live:2", stored=-300))
    end = SessionEndSnapshot(_today(remaining=16))

    first = accumulator.live_snapshot(
        ended_at="2026-08-28T11:00:00Z",
        end_snapshot=end,
    )
    second = accumulator.live_snapshot(
        ended_at="2026-08-28T11:00:00Z",
        end_snapshot=end,
    )

    assert isinstance(first, LiveSessionSnapshot)
    assert first == second
    assert accumulator.finalized is False
    assert first.cards_completed == 2
    assert first.plant_growth_total_units == 1_250
    assert first.shared_growth_total_units == 400
    assert first.stored_growth == first.segments[0].stored_growth
    assert (
        first.stored_growth.delta_units,
        first.stored_growth.added_units,
        first.stored_growth.used_units,
    ) == (200, 500, 300)
    assert first.footer_growth_units == 2_150
    assert first.garden_coins_earned == 4
    assert first.footer_find_count == 1

    payload = accumulator.finalize(
        ended_at="2026-08-28T11:00:00Z",
        end_snapshot=end,
    )
    assert payload is not None
    assert first.segments == payload.segments


def test_same_card_can_count_twice_when_authoritative_event_ids_differ():
    accumulator = _accumulator()
    assert accumulator.accept_committed(_event("review:learning:1"))
    assert accumulator.accept_committed(_event("review:learning:2"))

    payload = _finish(accumulator)
    assert payload is not None
    assert payload.cards_completed == 2


def test_starting_event_ids_block_preexisting_or_reconstructed_rewards():
    accumulator = _accumulator(start=_start(known=frozenset({"old:card", "old:coin"})))
    assert accumulator.accept_committed(_event("old:card")) is False
    assert accumulator.accept_committed(_event(
        "new:card",
        coins=(
            CoinAward("old:coin", "sync", "Older reward", 500),
            CoinAward("new:coin", "first_card", "First card", 2),
        ),
    ))

    payload = _finish(accumulator)
    assert payload is not None
    assert payload.cards_completed == 1
    assert payload.segments[0].garden_coins_earned == 2
    assert [item.event_id for item in payload.segments[0].coin_sources] == ["new:coin"]


def test_authoritative_reversal_removes_whole_card_or_selected_reward_once():
    accumulator = _accumulator()
    accumulator.accept_committed(_event(
        "card:1",
        plant_growth=(PlantGrowthDelta("rose", "Rose", 1_000),),
        coins=(CoinAward("coin:1", "stage", "Mature stage", 10),),
        finds=(StandardFind(
            "find:1", "dew", "Morning Dew", "common", "coins", "+4 Garden Coins", 4
        ),),
    ))
    accumulator.accept_committed(_event(
        "card:2",
        plant_growth=(PlantGrowthDelta("rose", "Rose", 2_000),),
        coins=(CoinAward("coin:2", "find", "Standard Find", 4),),
    ))

    selective = AuthoritativeEventReversal("undo:reward", ("coin:1", "find:1"))
    assert accumulator.apply_reversal(selective) is True
    assert accumulator.apply_reversal(selective) is False
    assert accumulator.apply_reversal(
        AuthoritativeEventReversal("undo:card", ("card:2",))
    ) is True

    payload = _finish(accumulator)
    assert payload is not None
    summary = payload.segments[0]
    assert summary.cards_completed == 1
    assert summary.plant_growth_total_units == 1_000
    assert summary.garden_coins_earned == 0
    assert summary.standard_finds == ()


def test_reversal_can_supply_an_authoritative_corrected_event():
    accumulator = _accumulator()
    accumulator.accept_committed(_event(
        "card:1",
        plant_growth=(PlantGrowthDelta("rose", "Rose", 1_000),),
    ))
    corrected = _event(
        "card:1",
        plant_growth=(PlantGrowthDelta("rose", "Rose", 750),),
    )
    assert accumulator.apply_reversal(AuthoritativeEventReversal(
        "correction:1",
        ("card:1",),
        (corrected,),
    ))

    payload = _finish(accumulator)
    assert payload is not None
    assert payload.cards_completed == 1
    assert payload.segments[0].plant_growth_total_units == 750


def test_empty_or_fully_reversed_session_has_no_payload():
    empty = _accumulator()
    assert _finish(empty) is None
    assert empty.take_finalized_payload() is None
    assert empty.take_finalized_payload() is None

    reversed_session = _accumulator()
    reversed_session.accept_committed(_event("card:1"))
    reversed_session.apply_reversal(
        AuthoritativeEventReversal("undo:1", ("card:1",))
    )
    assert _finish(reversed_session) is None


def test_finalize_is_idempotent_and_payload_can_only_be_taken_once():
    accumulator = _accumulator()
    accumulator.accept_committed(_event("card:1"))
    first = _finish(accumulator)
    second = _finish(accumulator)
    assert first is second
    assert accumulator.take_finalized_payload() is first
    assert accumulator.take_finalized_payload() is None


def test_anki_day_cutoff_creates_separate_reportable_segments():
    accumulator = _accumulator()
    accumulator.accept_committed(_event("day-one:card"))
    accumulator.split_anki_day(
        ended_at="2026-08-29T04:00:00Z",
        end_snapshot=SessionEndSnapshot(_today(remaining=2)),
        next_anki_day_id=DAY_TWO,
        next_started_at="2026-08-29T04:00:00Z",
        next_start_snapshot=_start(today=_today(remaining=40)),
    )
    accumulator.accept_committed(_event("day-two:card", day=DAY_TWO))

    payload = accumulator.finalize(
        ended_at="2026-08-29T04:20:00Z",
        end_snapshot=SessionEndSnapshot(_today(remaining=39)),
    )
    assert payload is not None
    assert payload.page_count == 2
    assert [segment.anki_day_id for segment in payload.segments] == [DAY_ONE, DAY_TWO]
    assert [segment.cards_completed for segment in payload.segments] == [1, 1]
    assert payload.segments[0].today_cards_end.cards_remaining == 2
    assert payload.segments[1].today_cards_start.cards_remaining == 40


def test_today_cards_projection_uses_approved_cards_language_only():
    completed = TodayCardsSnapshot(
        "complete",
        cards_completed=176,
        cards_total=176,
        reward_coins=10,
    )
    assert completed.player_lines == ("All of today’s cards complete",)
    waiting = TodayCardsSnapshot(
        "waiting_for_learning",
        waiting_cards=2,
        next_due_in_seconds=6 * 60,
    )
    assert waiting.player_lines == ("2 remaining", "Next card in 6 minutes")
    progress = project_today_cards(
        _today(remaining=160, complete=0, total=160),
        _today(remaining=18, complete=142, total=160),
    )
    assert progress.lines == ("18 remaining", "142 of 160 completed")
    assert (progress.progress_value, progress.progress_max) == (142, 160)
    assert progress.progress_fraction == pytest.approx(0.8875)
    assert progress.start_progress_fraction == 0.0
    assert progress.animate_progress is True
    assert progress.can_continue_reviews is True
    completed_during_session = project_today_cards(
        _today(remaining=82, complete=94, total=176),
        completed,
    )
    assert completed_during_session.lines == (
        "All of today’s cards complete",
        "176 of 176 completed",
    )
    assert completed_during_session.progress_fraction == 1.0
    assert completed_during_session.can_continue_reviews is False
    complete_at_both = project_today_cards(completed, completed)
    assert complete_at_both.lines == (
        "All of today’s cards complete",
        "176 of 176 completed",
    )

    all_copy = " ".join((
        *completed.player_lines,
        *waiting.player_lines,
        *progress.lines,
        *completed_during_session.lines,
        *complete_at_both.lines,
    ))
    forbidden = ("all clear", "daily care", "required", "drought", "answer")
    assert not any(term in all_copy.casefold() for term in forbidden)


def test_today_cards_progress_is_semantic_across_exit_states():
    waiting = project_today_cards(
        _today(remaining=20, complete=0, total=20),
        _today(
            "waiting_for_learning",
            remaining=2,
            complete=18,
            total=20,
            waiting=2,
            due_in=360,
            currently_due=0,
        ),
    )
    assert waiting.status_text == "2 remaining"
    assert waiting.supporting_text == "18 of 20 completed · Next card in 6 minutes"
    assert (waiting.progress_value, waiting.progress_max) == (18, 20)
    assert waiting.can_continue_reviews is False

    complete = project_today_cards(
        _today(remaining=144, complete=0, total=144),
        _today("complete", remaining=None, complete=144, total=144),
    )
    assert complete.status_text == "All of today’s cards complete"
    assert complete.supporting_text == "144 of 144 completed"
    assert complete.progress_fraction == 1.0

    increased = project_today_cards(
        _today(remaining=2, complete=0, total=2),
        _today(remaining=4, complete=0, total=4, currently_due=4),
    )
    assert increased.status_text == "4 remaining"
    assert increased.supporting_text == "0 of 4 completed"
    assert increased.progress_fraction == 0.0
    assert increased.animate_progress is False

    unavailable = project_today_cards(
        _today(remaining=None),
        _today("unavailable", remaining=None),
    )
    assert unavailable.progress_max == 0
    assert unavailable.can_continue_reviews is False


def test_second_session_keeps_session_work_separate_from_today_progress():
    start = _today(
        remaining=60,
        complete=84,
        total=144,
        currently_due=60,
    )
    accumulator = _accumulator(start=_start(today=start))
    accumulator.accept_committed(_event("later-session", cards=42))
    payload = _finish(
        accumulator,
        end=SessionEndSnapshot(_today(
            remaining=18,
            complete=126,
            total=144,
            currently_due=18,
        )),
    )

    assert payload is not None
    summary = payload.segments[0]
    projection = project_session_day(summary)
    assert summary.cards_completed == 42
    assert projection.cards_completed_value == "42"
    assert projection.today_cards.lines == (
        "18 remaining",
        "126 of 144 completed",
    )
    assert projection.today_cards.start_progress_value == 84
    assert projection.today_cards.progress_value == 126
    assert projection.today_cards.progress_max == 144
    assert projection.today_cards.animate_progress is True


def test_today_kind_scope_and_continuation_are_explicit():
    daily_target = project_today_cards(
        _today(
            remaining=60,
            complete=84,
            total=144,
            kind="daily_target",
            can_continue=False,
        ),
        _today(
            remaining=18,
            complete=126,
            total=144,
            kind="daily_target",
            can_continue=False,
        ),
    )
    assert daily_target.heading == "Daily target"
    assert daily_target.status_text == "18 to goal"
    assert daily_target.can_continue_reviews is False

    multi_deck = project_today_cards(
        _today(remaining=60, complete=84, total=144, contributing_decks=3),
        _today(remaining=18, complete=126, total=144, contributing_decks=3),
    )
    assert multi_deck.status_text == "18 remaining across all decks"
    assert multi_deck.continuation_target == ReviewContinuationTarget(
        "deck", 1, "Default"
    )

    with pytest.raises(ValueError, match="routable deck"):
        ReviewContinuationTarget("all_decks")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="continuation_target"):
        TodayCardsSnapshot(
            "in_progress",
            cards_remaining=18,
            cards_completed=126,
            currently_due_cards=18,
            cards_total=144,
            can_continue_reviews=True,
        )


def test_today_scope_or_denominator_change_disables_progress_animation():
    projection = project_today_cards(
        _today(
            remaining=60,
            complete=84,
            total=144,
            scope="deck",
            continuation_target=ReviewContinuationTarget("deck", 11),
        ),
        _today(
            remaining=18,
            complete=126,
            total=144,
            scope="all_decks",
        ),
    )
    assert projection.start_progress_value == 126
    assert projection.progress_value == 126
    assert projection.animate_progress is False


def test_find_quantities_reconcile_to_explicit_total_and_limit_by_occurrence():
    accumulator = _accumulator()
    accumulator.accept_committed(_event(
        "card:finds",
        finds=(
            StandardFind(
                "find:charge:1", "small_charge", "Small Growth Charge",
                "common", "inventory_item", "Small Growth Charge", 1,
                item_id="growth_charge_small", quantity=3,
            ),
        ),
        total_finds=3,
    ))
    payload = _finish(accumulator)
    assert payload is not None
    summary = payload.segments[0]
    projection = project_session_day(summary)
    assert summary.total_finds == 3
    assert summary.find_items == (
        FindItemQuantity(
            "small_charge",
            "Small Growth Charge",
            3,
            "common",
            "inventory_item",
            "Small Growth Charge",
            "",
            "growth_charge_small",
            "",
        ),
    )
    assert projection.reward_metrics[-1].value == "+3"
    assert projection.find_details.visible[0].quantity == 3

    multiple = _accumulator()
    multiple.accept_committed(_event(
        "card:mixed-finds",
        finds=(
            StandardFind(
                "find:charge", "charge", "Small Growth Charge", "common",
                "inventory_item", "Small Growth Charge", item_id="charge",
            ),
            StandardFind(
                "find:coins", "coins", "Garden Coin Cache", "common",
                "coins", "Garden Coins",
            ),
            StandardFind(
                "find:stored", "stored", "Stored Growth Charge", "common",
                "stored_growth", "Stored Growth",
            ),
        ),
        total_finds=3,
    ))
    multiple_payload = _finish(multiple)
    assert multiple_payload is not None
    details = project_session_day(multiple_payload.segments[0]).find_details
    assert [item.find_name for item in details.visible] == [
        "Small Growth Charge",
        "Garden Coin Cache",
    ]
    assert details.remaining_count == 1
    assert details.more_label == "1 more Standard Find"

    plural = _accumulator()
    plural.accept_committed(_event(
        "card:four-mixed-finds",
        finds=tuple(
            StandardFind(
                f"find:plural:{index}",
                f"plural-{index}",
                f"Find reward {index}",
                "common",
                "inventory_item",
                f"Find reward {index}",
                item_id=f"plural-{index}",
            )
            for index in range(4)
        ),
        total_finds=4,
    ))
    plural_payload = _finish(plural)
    assert plural_payload is not None
    plural_details = project_session_day(
        plural_payload.segments[0]
    ).find_details
    assert plural_details.remaining_count == 2
    assert plural_details.more_label == "2 more Standard Finds"


def test_inventory_find_names_the_granted_item_not_internal_flavor_copy():
    accumulator = _accumulator()
    finds = tuple(
        StandardFind(
            f"find:charge:{index}",
            "find_small_charge",
            "Charged Seed",
            "Uncommon",
            "inventory_item",
            "+1 Small Growth Charge",
            1,
            "ui_growth_charge_small",
            item_id="growth_charge_small",
        )
        for index in range(3)
    )
    accumulator.accept_committed(_event(
        "card:concrete-find",
        finds=finds,
        total_finds=3,
    ))

    payload = _finish(accumulator)
    assert payload is not None
    summary = payload.segments[0]
    assert summary.standard_finds[0].find_name == "Charged Seed"
    assert summary.find_items[0].find_name == "Small Growth Charge"
    assert summary.find_items[0].quantity == 3
    assert project_session_day(summary).find_details.visible[0].find_name == (
        "Small Growth Charge"
    )


def test_incomplete_find_items_keep_authoritative_total_and_omit_details(caplog):
    accumulator = _accumulator()
    accumulator.accept_committed(_event(
        "card:incomplete-find",
        finds=(StandardFind(
            "find:known", "known", "Known Find", "common",
            "growth", "Growth", quantity=1,
        ),),
        total_finds=3,
    ))
    with caplog.at_level("WARNING"):
        payload = _finish(accumulator)

    assert payload is not None
    summary = payload.segments[0]
    projection = project_session_day(summary)
    assert summary.total_finds == 3
    assert summary.find_items == ()
    assert summary.find_items_reconciled is False
    assert [(row.key, row.value) for row in projection.reward_metrics] == [
        ("standard_finds", "+3"),
    ]
    assert projection.find_details.visible == ()
    assert "Find details omitted" in caplog.text


def test_projection_omits_zero_rows_and_uses_cards_complete_hero_copy():
    accumulator = _accumulator()
    accumulator.accept_committed(_event("card:1"))
    payload = _finish(accumulator)
    assert payload is not None

    projection = project_session_day(payload.segments[0])
    assert projection.cards_completed_value == "1"
    assert projection.cards_completed_label == "card completed this session"
    assert projection.result_rows == ()
    assert not hasattr(projection, "no_rewards_copy")
    assert projection.open_garden_available is True
    assert projection.continue_reviews_available is True


def test_growth_format_has_separators_and_at_most_one_decimal():
    assert format_growth_units(128_400, signed=True) == "+1,284"
    assert format_growth_units(128_450, signed=True) == "+1,284.5"
    assert format_growth_units(1_855, signed=True) == "+18.6"
    assert format_growth_units(-3_200) == "-32"


def test_stored_growth_reports_added_used_and_net_without_double_counting():
    accumulator = _accumulator()
    accumulator.accept_committed(_event("card:1", stored=5_000))
    accumulator.accept_committed(_event("card:2", stored=-3_200))
    payload = _finish(accumulator)
    assert payload is not None
    stored = payload.segments[0].stored_growth
    assert (stored.delta_units, stored.added_units, stored.used_units) == (1_800, 5_000, 3_200)

    projection = project_session_day(payload.segments[0])
    assert not any(
        item.key.startswith("stored_growth") for item in projection.result_rows
    )
    assert projection.growth_applied_total_units == 0


def test_only_positive_coin_awards_can_enter_the_session_contract():
    with pytest.raises(ValueError, match="positive"):
        CoinAward("purchase:1", "purchase", "Nursery purchase", -100)
    with pytest.raises(ValueError, match="positive"):
        CoinAward("empty:1", "other", "Other", 0)


def test_milestones_sort_by_importance_then_chronology():
    accumulator = _accumulator()
    accumulator.accept_committed(_event(
        "card:1",
        milestones=(
            PlantMilestone(
                "checkpoint:late", "rose", "Rose", "checkpoint",
                "2026-08-28T10:03:00Z", checkpoint_percent=75,
            ),
            PlantMilestone(
                "stage:late", "rose", "Rose", "stage_change",
                "2026-08-28T10:02:00Z", previous_stage="young", new_stage="mature",
            ),
            PlantMilestone(
                "bloom:1", "wisteria", "Wisteria", "full_bloom",
                "2026-08-28T10:04:00Z", previous_stage="flowering", new_stage="rare",
            ),
            PlantMilestone(
                "stage:early", "juniper", "Juniper", "stage_change",
                "2026-08-28T10:01:00Z", previous_stage="sprout", new_stage="young",
            ),
        ),
    ))
    payload = _finish(accumulator)
    assert payload is not None
    assert [item.event_id for item in payload.segments[0].milestones] == [
        "bloom:1",
        "stage:early",
        "stage:late",
        "checkpoint:late",
    ]


def test_owned_environment_is_not_reported_as_a_new_discovery():
    accumulator = _accumulator(start=_start(owned=frozenset({"firefly"})))
    accumulator.accept_committed(_event(
        "card:1",
        discoveries=(
            EnvironmentDiscovery(
                "environment:old", "firefly", "Firefly Evening", "weather",
                "rare", "firefly.webp", "+3 Growth every 4 eligible cards",
            ),
            EnvironmentDiscovery(
                "environment:new", "horizon", "Rainbow Horizon", "scenery",
                "ultra", "horizon.webp", "+1 Growth on the first 100 cards",
            ),
        ),
    ))
    payload = _finish(accumulator)
    assert payload is not None
    assert [item.environment_id for item in payload.segments[0].environment_discoveries] == [
        "horizon"
    ]
    discovery = payload.segments[0].environment_discoveries[0]
    assert discovery.environment_kind == "scenery"
    assert discovery.unlock_category == "environment"
    highlight = project_session_day(payload.segments[0]).highlights.featured[0]
    assert highlight.unlock_category == "environment"
    assert highlight.eyebrow == "ENVIRONMENT UNLOCKED"
    assert highlight.supporting_text == "Now available in the Garden"


@pytest.mark.parametrize(
    ("category", "label"),
    (
        ("garden_item", "GARDEN DISCOVERY UNLOCKED"),
        ("environment", "ENVIRONMENT UNLOCKED"),
        ("plant", "PLANT UNLOCKED"),
        ("planter", "PLANTER UNLOCKED"),
        ("background", "BACKGROUND UNLOCKED"),
    ),
)
def test_unlock_categories_have_specific_public_labels(category, label):
    assert unlock_category_copy(category)[0] == label


def test_legacy_and_canonical_garden_feature_discoveries_share_one_identity():
    accumulator = _accumulator(start=_start())
    accumulator.accept_committed(_event(
        "card:1",
        discoveries=(EnvironmentDiscovery(
            "environment:legacy",
            "fireflies",
            "Firefly Lantern",
            "weather",
            "rare",
            "fireflies.svg",
            "+3 Growth every 4 eligible cards",
        ),),
    ))
    accumulator.accept_committed(_event(
        "card:2",
        discoveries=(EnvironmentDiscovery(
            "environment:canonical",
            "firefly_lantern",
            "Firefly Lantern",
            "garden_feature",
            "rare",
            "fireflies.svg",
            "+3 Growth every 4 eligible cards",
        ),),
    ))

    payload = _finish(accumulator)

    assert payload is not None
    discoveries = payload.segments[0].environment_discoveries
    assert len(discoveries) == 1
    assert discoveries[0].environment_id == "firefly_lantern"
    assert discoveries[0].environment_kind == "garden_feature"
    assert discoveries[0].unlock_category == "garden_item"


def test_legacy_owned_weather_alias_filters_canonical_garden_feature_discovery():
    accumulator = _accumulator(start=_start(owned=frozenset({"fireflies"})))
    accumulator.accept_committed(_event(
        "card:1",
        discoveries=(EnvironmentDiscovery(
            "environment:new",
            "firefly_lantern",
            "Firefly Lantern",
            "garden_feature",
            "rare",
            "fireflies.svg",
            "+3 Growth every 4 eligible cards",
        ),),
    ))

    payload = _finish(accumulator)

    assert payload is not None
    assert payload.segments[0].environment_discoveries == ()


def test_effect_rows_are_frozen_exit_snapshots_and_exclude_external_new_effects():
    start_effects = EffectsSnapshot(
        fertilizers=(
            FertilizerSnapshot(
                "fert:quality", "Quality Fertilizer", remaining_cards=30
            ),
            FertilizerSnapshot(
                "fert:ended", "Basic Fertilizer", remaining_cards=1
            ),
        ),
        boosters=(BoosterSnapshot("boost:1", 60),),
    )
    accumulator = _accumulator(start=_start(effects=start_effects))
    accumulator.accept_committed(_event("card:1"))
    end_effects = EffectsSnapshot(
        fertilizers=(
            FertilizerSnapshot(
                "fert:quality", "Quality Fertilizer", remaining_cards=25
            ),
            FertilizerSnapshot(
                "fert:manual", "Magical Fertilizer",
                remaining_cards=72,
                source_event_id="manual:inventory",
            ),
            FertilizerSnapshot(
                "fert:earned", "Magical Fertilizer",
                remaining_cards=72,
                source_event_id="card:1",
            ),
        ),
        boosters=(BoosterSnapshot("boost:1", 31),),
    )
    payload = _finish(
        accumulator,
        end=SessionEndSnapshot(_today(remaining=18), end_effects),
    )
    assert payload is not None
    rows = payload.segments[0].effects_remaining
    assert [(row.effect_id, row.value, row.secondary) for row in rows] == [
        ("fert:earned", "72 cards remaining", ""),
        ("fert:quality", "25 cards remaining", ""),
        ("boost:1", "31 cards remaining", ""),
    ]
    assert all(not row.ended_during_session for row in rows)
    assert "fert:manual" not in {row.effect_id for row in rows}


def test_large_result_projection_limits_details_without_hiding_full_bloom():
    accumulator = _accumulator()
    growth = tuple(
        PlantGrowthDelta(f"plant:{index}", f"Plant {index}", 10_000 - index)
        for index in range(7)
    )
    milestones = tuple(
        PlantMilestone(
            f"bloom:{index}", f"bloom-plant:{index}", f"Bloom {index}",
            "full_bloom", f"2026-08-28T10:0{index}:00Z",
        )
        for index in range(2)
    ) + tuple(
        PlantMilestone(
            f"stage:{index}", f"stage-plant:{index}", f"Stage {index}",
            "stage_change", f"2026-08-28T10:1{index}:00Z",
        )
        for index in range(5)
    )
    discoveries = tuple(
        EnvironmentDiscovery(
            f"environment:{index}", f"environment-{index}", f"Environment {index}",
            "weather", "rare", f"environment-{index}.webp", "Cosmetic effect",
        )
        for index in range(4)
    )
    accumulator.accept_committed(_event(
        "card:1",
        plant_growth=growth,
        milestones=milestones,
        discoveries=discoveries,
    ))
    payload = _finish(accumulator)
    assert payload is not None
    projection = project_session_day(payload.segments[0])

    assert len(projection.plant_growth_details.visible) == 3
    assert projection.plant_growth_details.remaining_count == 4
    assert projection.plant_growth_details.more_label == "View 4 more plants"
    assert len(projection.milestones.visible) == 5
    assert [item.milestone_type for item in projection.milestones.visible[:2]] == [
        "full_bloom", "full_bloom"
    ]
    assert projection.milestones.remaining_count == 2
    assert len(projection.environment_discoveries.visible) == 2
    assert projection.environment_discoveries.remaining_count == 2
    assert (
        projection.environment_discoveries.more_label
            == "View 2 more Garden discoveries"
    )
    assert [item.kind for item in projection.highlights.featured] == [
        "full_bloom", "full_bloom"
    ]
    assert len(projection.highlights.featured) == 2
    assert len(projection.highlights.overflow) == 9
    assert projection.highlights.more_label == "View 6 more progress items"


def test_unified_highlights_follow_product_priority_before_chronology():
    accumulator = _accumulator()
    accumulator.accept_committed(_event(
        "card:highlights",
        finds=(StandardFind(
            "find:rare", "moonlit_seed", "Moonlit Seed", "rare",
            "inventory_item", "+1 Moonlit Seed", 1, occurred_at="2026-08-28T10:00:01Z",
            notable=True,
        ),),
        discoveries=(EnvironmentDiscovery(
            "environment:fireflies", "fireflies", "Firefly Evening", "weather",
            "rare", "fireflies", "Cosmetic", "2026-08-28T10:00:05Z",
        ),),
        milestones=(
            PlantMilestone(
                "checkpoint:minor", "p1", "Wisteria", "checkpoint",
                "2026-08-28T10:00:00Z", checkpoint_percent=25,
            ),
            PlantMilestone(
                "checkpoint:major", "p1", "Wisteria", "checkpoint",
                "2026-08-28T10:00:02Z", checkpoint_percent=75,
            ),
            PlantMilestone(
                "stage:mature", "p1", "Wisteria", "stage_change",
                "2026-08-28T10:00:03Z", new_stage="mature",
            ),
            PlantMilestone(
                "stage:rare", "p1", "Wisteria", "full_bloom",
                "2026-08-28T10:00:04Z", new_stage="rare",
            ),
        ),
    ))
    payload = _finish(accumulator)
    assert payload is not None
    highlights = project_session_day(payload.segments[0]).highlights
    assert [item.kind for item in highlights.featured] == [
        "full_bloom", "environment"
    ]
    assert [item.unlock_category for item in highlights.featured] == [
        "plant", "garden_item"
    ]
    assert highlights.featured[1].eyebrow == "GARDEN DISCOVERY UNLOCKED"
    assert (
        highlights.featured[1].supporting_text
        == "Added to your Garden collection"
    )
    assert [item.kind for item in highlights.overflow] == [
        "stage_change", "major_checkpoint", "rare_reward"
    ]
    assert highlights.more_label == ""


def test_effect_snapshots_follow_full_bloom_transfer_without_false_end():
    accumulator = SessionSummaryAccumulator(
        session_id="transfer-session",
        started_at="2026-08-28T10:00:00Z",
        anki_day_id=DAY_ONE,
        start_snapshot=SessionStartSnapshot(
            _today(remaining=2),
            EffectsSnapshot(
                fertilizers=(FertilizerSnapshot(
                    "fert:plant-a", "Quality Fertilizer",
                    plant_id="plant-a",
                    remaining_cards=40,
                ),),
                boosters=(BoosterSnapshot(
                    "boost:plant-a", 40,
                    plant_id="plant-a",
                ),),
            ),
        ),
    )
    accumulator.accept_committed(_event("card:full-bloom"))
    payload = _finish(
        accumulator,
        end=SessionEndSnapshot(
            _today(remaining=1),
            EffectsSnapshot(
                fertilizers=(FertilizerSnapshot(
                    "fert:plant-b", "Quality Fertilizer",
                    plant_id="plant-b",
                    remaining_cards=39,
                ),),
                boosters=(BoosterSnapshot(
                    "boost:plant-b", 39,
                    plant_id="plant-b",
                ),),
            ),
        ),
    )
    assert payload is not None
    assert [
        (row.effect_id, row.value, row.ended_during_session)
        for row in payload.segments[0].effects_remaining
    ] == [
        ("fert:plant-b", "39 cards remaining", False),
        ("boost:plant-b", "39 cards remaining", False),
    ]
