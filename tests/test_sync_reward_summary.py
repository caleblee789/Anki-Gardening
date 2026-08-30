from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from ankigarden.models.state import STATE_VERSION, GardenState
from ankigarden.models.sync_reward import (
    MAX_SYNC_SUMMARY_DAYS,
    MAX_SYNC_SUMMARY_ROWS,
    MAX_SYNC_SUMMARY_TEXT,
    SYNC_REWARD_MODEL_VERSION,
    SyncRewardSummary,
)
from ankigarden.ui.sync_reward_summary import (
    SyncRewardSummaryCard,
    _effect_lines,
    sync_reward_metric_plan,
    sync_reward_summary_geometry,
    sync_reward_visibility_plan,
)


def _summary(**changes) -> SyncRewardSummary:
    payload = {
        "batch_id": "batch-a",
        "anki_days": ("2026-08-29",),
        "eligible_answer_count": 42,
        "growth_total_units": 52_000,
        "plant_growth": ({
            "plant_id": "bluebell",
            "plant_name": "Bluebell",
            "plant_image": "bluebell",
            "growth_delta_units": 42_000,
            "stage_before": "mature",
            "stage_after": "flowering",
            "stage_progress_before": 55,
            "stage_progress_after": 68,
            "next_stage": "rare",
            "active": True,
        },),
        "shared_growth_delta_units": 8_000,
        "stored_growth_delta_units": 2_000,
        "garden_coin_delta": 12,
        "source_batch_ids": ("batch-a",),
    }
    payload.update(changes)
    return SyncRewardSummary(**payload)


def test_geometry_is_upper_right_and_viewport_bounded() -> None:
    assert sync_reward_summary_geometry(900, 700, 300) == (420, 24, 456, 300)
    assert sync_reward_summary_geometry(900, 700, 900) == (420, 24, 456, 640)

    x, y, width, height = sync_reward_summary_geometry(420, 260, 500)
    assert (x, y, width, height) == (24, 24, 372, 212)
    assert x + width <= 420
    assert y + height <= 260


def test_metric_plan_keeps_standard_finds_and_discoveries_separate() -> None:
    assert sync_reward_metric_plan(_summary()) == (
        ("42", "Card answers", "sync_review_cards"),
        ("+520", "Growth", "growth_resource"),
        ("+12", "Garden Coins", "garden_coin"),
    )
    assert len(sync_reward_metric_plan(_summary(garden_coin_delta=0))) == 2
    find_rows = ({
        "reward_id": "small_charge",
        "event_id": "standard-find:event-1",
        "display_name": "Small Charge",
        "quantity": 3,
    },)
    discovery_rows = (
        {
            "environment_id": "firefly_lantern",
            "event_id": "garden-discovery:event-1",
            "display_name": "Firefly Lantern",
        },
        {
            "environment_id": "moon_gate",
            "event_id": "garden-discovery:event-2",
            "display_name": "Moon Gate",
        },
    )
    reward_summary = _summary(
        garden_coin_delta=12,
        finds=find_rows,
        environment_discoveries=discovery_rows,
    )

    assert sync_reward_metric_plan(reward_summary) == (
        ("42", "Card answers", "sync_review_cards"),
        ("+520", "Growth", "growth_resource"),
        ("+12", "Garden Coins", "garden_coin"),
        ("+3", "Standard Finds", "standard_find"),
        ("+2", "Garden discoveries", "garden_discovery"),
    )
    restored = SyncRewardSummary.from_dict(reward_summary.to_dict())

    assert restored is not None
    assert restored.finds[0]["reward_id"] == "small_charge"
    assert restored.finds[0]["event_id"] == "standard-find:event-1"
    assert tuple(
        row["event_id"] for row in restored.environment_discoveries
    ) == ("garden-discovery:event-1", "garden-discovery:event-2")


def test_visibility_uses_one_disclosure_and_keeps_full_bloom_visible() -> None:
    plants = tuple({
        "plant_id": f"plant-{index}",
        "plant_name": f"Plant {index}",
        "growth_delta_units": 100,
    } for index in range(5))
    environments = tuple({
        "environment_id": f"env-{index}",
        "display_name": f"Environment {index}",
    } for index in range(3))
    finds = tuple({
        "reward_id": f"find-{index}",
        "display_name": f"Find {index}",
    } for index in range(5))
    events = (
        {"event_id": "stage-1", "plant_id": "plant-0", "event_type": "stage"},
        {"event_id": "stage-2", "plant_id": "plant-1", "event_type": "stage"},
        {"event_id": "bloom", "plant_id": "plant-4", "event_type": "full_bloom"},
        {"event_id": "stage-3", "plant_id": "plant-2", "event_type": "stage"},
    )
    summary = _summary(
        plant_growth=plants,
        environment_discoveries=environments,
        finds=finds,
        progression_events=events,
    )

    collapsed = sync_reward_visibility_plan(summary)
    assert len(collapsed.plant_growth) == 3
    assert len(collapsed.environment_discoveries) == 2
    assert len(collapsed.finds) == 3
    assert any(row.get("full_bloom") for row in collapsed.plant_growth)
    assert collapsed.progression_events == ()
    assert collapsed.hidden_count == 5

    expanded = sync_reward_visibility_plan(summary, expanded=True)
    assert expanded.hidden_count == 0
    assert len(expanded.plant_growth) == 5
    assert len(expanded.environment_discoveries) == 3
    assert len(expanded.finds) == 5
    assert expanded.progression_events == ()


def test_exact_generalized_subtitle_copy() -> None:
    assert _summary(eligible_answer_count=1).subtitle == (
        "Reward from 1 card answer on another device."
    )
    assert _summary().subtitle == (
        "Rewards from 42 card answers on another device."
    )


def test_current_boost_projection_keeps_names_and_art_references_aligned() -> None:
    summary = _summary(
        fertilizer_remaining_seconds=1_080,
        fertilizer_state_changed=True,
        fertilizer_item_id="fertilizer_quality",
        fertilizer_art_asset="/art/fertilizer_quality.webp",
        booster_cards_remaining=1,
        booster_state_changed=True,
        booster_item_id="booster_potion",
        booster_art_asset="/art/booster_potion.webp",
    )

    assert _effect_lines(summary) == (
        (
            "fertilizer",
            "fertilizer_quality",
            "Quality Fertilizer active · 18 min remaining",
            "/art/fertilizer_quality.webp",
        ),
        (
            "booster",
            "booster_potion",
            "Booster Potion active · 1 card remaining",
            "/art/booster_potion.webp",
        ),
    )


def test_native_card_shell_when_qt_is_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))
    try:
        from aqt.qt import QApplication, QLabel, QPushButton, QScrollArea, QWidget, Qt
    except (ImportError, ModuleNotFoundError):
        pytest.skip("Anki's Qt runtime is unavailable")

    application = QApplication.instance() or QApplication([])
    parent = QWidget()
    parent.resize(900, 700)
    parent.show()
    application.processEvents()

    dismissed: list[str] = []
    opened: list[str] = []
    card = SyncRewardSummaryCard(
        parent,
        _summary(),
        on_dismiss=lambda: dismissed.append("dismissed"),
        on_open_garden=lambda: opened.append("opened"),
        animations_enabled=False,
    )
    card.show()
    application.processEvents()
    application.processEvents()

    assert card.parentWidget() is parent
    assert card.property("summaryNonmodal") is True
    assert card.property("summaryCentered") is False
    assert card.property("summaryDock") == "upper-right"
    assert card.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    assert len(card.findChildren(QScrollArea)) == 1
    assert card.findChildren(QScrollArea)[0].property("syncBodyScrollOwner") is True
    assert card.x() == parent.width() - card.width() - 24
    assert 400 <= card.width() <= 480
    assert card.height() <= 640
    assert (card.x(), card.y(), card.width(), card.height()) == (
        sync_reward_summary_geometry(
            parent.width(),
            parent.height(),
            card._natural_height(),
        )
    )

    texts = {label.text() for label in card.findChildren(QLabel)}
    assert "SYNC REWARDS" in texts
    assert "Your garden caught up" in texts
    assert "Rewards from 42 card answers on another device." in texts
    assert "Rewards already applied." in texts
    buttons = {button.text(): button for button in card.findChildren(QPushButton)}
    assert {"Close", "Open Garden"} <= set(buttons)

    buttons["Close"].click()
    application.processEvents()
    assert dismissed == ["dismissed"]
    assert opened == []
    parent.close()
    parent.deleteLater()
    application.processEvents()


def test_presentation_model_round_trip_is_normalized_and_bounded() -> None:
    start = date(2025, 1, 1)
    raw = _summary().to_dict()
    raw["anki_days"] = [
        (start + timedelta(days=index)).isoformat()
        for index in range(MAX_SYNC_SUMMARY_DAYS + 20)
    ]
    raw["plant_growth"] = [
        {
            "plant_id": f"plant-{index}",
            "plant_name": "P" * (MAX_SYNC_SUMMARY_TEXT + 40),
            "growth_delta_units": index,
        }
        for index in range(MAX_SYNC_SUMMARY_ROWS + 20)
    ]
    raw["source_batch_ids"] = [
        f"batch-{index}" for index in range(MAX_SYNC_SUMMARY_ROWS + 20)
    ]

    restored = SyncRewardSummary.from_dict(raw)

    assert restored is not None
    assert len(restored.anki_days) == MAX_SYNC_SUMMARY_DAYS
    assert len(restored.plant_growth) == MAX_SYNC_SUMMARY_ROWS
    assert len(restored.source_batch_ids) == MAX_SYNC_SUMMARY_ROWS
    assert len(restored.plant_growth[0]["plant_name"]) == MAX_SYNC_SUMMARY_TEXT
    assert SyncRewardSummary.from_dict(restored.to_dict()) == restored


def test_v1_rows_are_grouped_and_superseded_checkpoints_are_removed() -> None:
    raw = _summary(
        progression_events=(
            {
                "event_id": "checkpoint:bluebell:75",
                "plant_id": "bluebell",
                "event_type": "checkpoint",
                "checkpoint_name": "75% toward Flowering",
                "stage_name": "Flowering",
                "display_text": "Bluebell reached the 75% checkpoint",
            },
            {
                "event_id": "stage:wisteria:rare",
                "plant_id": "wisteria",
                "plant_name": "Wisteria",
                "event_type": "full_bloom",
                "display_text": "Wisteria reached Full Bloom",
            },
        ),
    ).to_dict()
    raw.pop("plant_results", None)
    raw["model_version"] = 1

    restored = SyncRewardSummary.from_dict(raw)

    assert restored is not None
    assert restored.model_version == SYNC_REWARD_MODEL_VERSION
    grouped = {row.plant_id: row for row in restored.grouped_plant_results}
    assert grouped["bluebell"].checkpoints == ()
    assert grouped["bluebell"].primary_milestone.kind == "stage_change"
    assert grouped["wisteria"].full_bloom
    assert restored.to_dict()["model_version"] == SYNC_REWARD_MODEL_VERSION
    assert len(restored.to_dict()["plant_results"]) == 2


def test_active_boost_art_fields_round_trip_bounded() -> None:
    raw = _summary(
        fertilizer_item_id="fertilizer_quality",
        fertilizer_art_asset="/art/fertilizer_quality.webp",
        booster_item_id="booster_potion",
        booster_art_asset="/art/booster_potion.webp",
    ).to_dict()
    raw["fertilizer_art_asset"] = "a" * (MAX_SYNC_SUMMARY_TEXT + 20)

    restored = SyncRewardSummary.from_dict(raw)

    assert restored is not None
    assert restored.fertilizer_item_id == "fertilizer_quality"
    assert len(restored.fertilizer_art_asset) == MAX_SYNC_SUMMARY_TEXT
    assert restored.booster_item_id == "booster_potion"
    assert restored.booster_art_asset == "/art/booster_potion.webp"


@pytest.mark.parametrize(
    "payload",
    (
        None,
        {},
        {"batch_id": "", "eligible_answer_count": 1},
        {"batch_id": "batch-a", "eligible_answer_count": 0},
    ),
)
def test_presentation_model_rejects_missing_identity_or_answer_count(payload) -> None:
    assert SyncRewardSummary.from_dict(payload) is None


def test_merge_aggregates_batches_while_preserving_progress_boundaries() -> None:
    older = _summary(
        batch_id="batch-a",
        anki_days=("2026-08-27",),
        eligible_answer_count=2,
        growth_total_units=1_000,
        garden_coin_delta=1,
        plant_growth=({
            "plant_id": "bluebell",
            "plant_name": "Bluebell",
            "growth_delta_units": 1_000,
            "stage_before": "young",
            "stage_after": "mature",
            "stage_progress_before": 80,
            "stage_progress_after": 5,
        },),
        finds=({"reward_id": "small_charge", "quantity": 1},),
        fertilizer_remaining_seconds=900,
        fertilizer_state_changed=True,
        fertilizer_item_id="fertilizer_quality",
        fertilizer_art_asset="/art/fertilizer_quality.webp",
        booster_cards_remaining=12,
        booster_state_changed=True,
        booster_item_id="booster_potion",
        booster_art_asset="/art/booster_potion.webp",
        source_batch_ids=("batch-a",),
    )
    newer = _summary(
        batch_id="batch-b",
        anki_days=("2026-08-29",),
        eligible_answer_count=3,
        growth_total_units=2_000,
        garden_coin_delta=10,
        plant_growth=({
            "plant_id": "bluebell",
            "plant_name": "Bluebell",
            "growth_delta_units": 2_000,
            "stage_before": "mature",
            "stage_after": "flowering",
            "stage_progress_before": 5,
            "stage_progress_after": 40,
        },),
        finds=({"reward_id": "small_charge", "quantity": 2},),
        all_clear_earned=True,
        all_clear_coin_reward=10,
        source_batch_ids=("batch-b",),
    )

    merged = older.merge(newer)

    assert merged.batch_id == "batch-a"
    assert merged.source_batch_ids == ("batch-a", "batch-b")
    assert merged.anki_days == ("2026-08-27", "2026-08-29")
    assert merged.eligible_answer_count == 5
    assert merged.additional_answer_count == 3
    assert merged.growth_total_units == 3_000
    assert merged.garden_coin_delta == 11
    assert merged.finds[0]["quantity"] == 3
    assert merged.plant_growth[0]["growth_delta_units"] == 3_000
    assert merged.plant_growth[0]["stage_before"] == "young"
    assert merged.plant_growth[0]["stage_after"] == "flowering"
    assert merged.all_clear_earned
    assert merged.all_clear_coin_reward == 10
    assert merged.fertilizer_remaining_seconds == 900
    assert merged.fertilizer_state_changed
    assert merged.fertilizer_item_id == "fertilizer_quality"
    assert merged.fertilizer_art_asset == "/art/fertilizer_quality.webp"
    assert merged.booster_cards_remaining == 12
    assert merged.booster_state_changed
    assert merged.booster_item_id == "booster_potion"
    assert merged.booster_art_asset == "/art/booster_potion.webp"


def test_merge_backfills_art_for_a_legacy_pending_boost_receipt() -> None:
    older = _summary(
        fertilizer_remaining_seconds=900,
        fertilizer_state_changed=True,
        booster_cards_remaining=12,
        booster_state_changed=True,
    )
    newer = _summary(
        fertilizer_item_id="fertilizer_quality",
        fertilizer_art_asset="/art/fertilizer_quality.webp",
        booster_item_id="booster_potion",
        booster_art_asset="/art/booster_potion.webp",
    )

    merged = older.merge(newer)

    assert merged.fertilizer_remaining_seconds == 900
    assert merged.fertilizer_item_id == "fertilizer_quality"
    assert merged.fertilizer_art_asset == "/art/fertilizer_quality.webp"
    assert merged.booster_cards_remaining == 12
    assert merged.booster_item_id == "booster_potion"
    assert merged.booster_art_asset == "/art/booster_potion.webp"


def test_current_boost_rows_use_named_item_art_when_qt_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))
    try:
        from aqt.qt import QApplication, QLabel, QWidget
    except (ImportError, ModuleNotFoundError):
        pytest.skip("Anki's Qt runtime is unavailable")

    root = Path(__file__).parents[1]
    art_root = root / "ankigarden" / "assets" / "v6_storybook_gouache" / "ui"
    engine = SimpleNamespace(
        resolve_item_asset=lambda key: SimpleNamespace(path=art_root / f"{key}.webp")
    )
    application = QApplication.instance() or QApplication([])
    parent = QWidget()
    parent.resize(900, 700)
    card = SyncRewardSummaryCard(
        parent,
        _summary(
            fertilizer_remaining_seconds=1_080,
            fertilizer_state_changed=True,
            fertilizer_item_id="fertilizer_quality",
            booster_cards_remaining=12,
            booster_state_changed=True,
            booster_item_id="booster_potion",
        ),
        engine=engine,
        animations_enabled=False,
    )
    card.show()
    application.processEvents()

    copy = {label.text() for label in card.findChildren(QLabel)}
    art = [
        label for label in card.findChildren(QLabel)
        if label.property("syncBoostArtwork") is True
    ]
    assert "Quality Fertilizer active · 18 min remaining" in copy
    assert "Booster Potion active · 12 cards remaining" in copy
    assert {label.property("syncBoostArtworkReference") for label in art} == {
        "fertilizer_quality",
        "booster_potion",
    }
    assert all(label.width() == label.height() == 26 for label in art)
    assert all(label.pixmap() is not None and not label.pixmap().isNull() for label in art)

    parent.close()
    parent.deleteLater()
    application.processEvents()


def test_schema24_round_trips_pending_summary_and_fails_closed_when_malformed() -> None:
    summary = _summary()
    state = GardenState(pending_sync_reward_summary=summary.to_dict())

    restored = GardenState.from_dict(state.to_dict())

    assert restored.version == STATE_VERSION == 25
    assert SyncRewardSummary.from_dict(restored.pending_sync_reward_summary) == summary

    malformed = state.to_dict()
    malformed["pending_sync_reward_summary"] = {
        "batch_id": "",
        "eligible_answer_count": 42,
    }
    repaired = GardenState.from_dict(malformed)
    assert repaired.pending_sync_reward_summary is None
