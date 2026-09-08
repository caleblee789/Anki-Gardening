from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

from ankigarden.game import GardenGameEngine
from ankigarden.models.state import RewardReceipt
from ankigarden.ui.icons import GARDEN_ICON_PATHS
from ankigarden.ui.session_summary_card import (
    SESSION_SUMMARY_DEFAULT_WIDTH,
    SESSION_SUMMARY_EDGE_MARGIN,
    SESSION_SUMMARY_COMPACT_HOST_HEIGHT,
    SESSION_SUMMARY_FOOTER_HEIGHT,
    SESSION_SUMMARY_FRAME_BORDER_WIDTH,
    SESSION_SUMMARY_HEADER_HEIGHT,
    SESSION_SUMMARY_MAX_HEIGHT,
    SESSION_SUMMARY_MAX_WIDTH,
    SESSION_SUMMARY_MIN_VERTICAL_MARGIN,
    SESSION_SUMMARY_PREFERRED_TOP_MARGIN,
    SessionSummaryCard,
    session_earned_item_plan,
    session_effect_remaining_text,
    session_find_summary_plan,
    session_inventory_reward_lines,
    session_summary_geometry,
    session_summary_palette,
    session_summary_uses_compact_density,
)
from ankigarden.ui.theme import GARDEN_THEME


SOURCE_PATH = Path(__file__).parents[1] / "ankigarden" / "ui" / "session_summary_card.py"


def _method_source(name: str, following: str) -> str:
    source = SOURCE_PATH.read_text(encoding="utf-8") + SOURCE_PATH.with_name("reward_receipt.py").read_text(encoding="utf-8")
    return source.split(f"def {name}", 1)[1].split(f"def {following}", 1)[0]


def test_session_summary_geometry_uses_400_preferred_width_and_32px_narrow_allowance():
    assert SESSION_SUMMARY_DEFAULT_WIDTH == 400
    assert SESSION_SUMMARY_MAX_WIDTH == 400
    assert SESSION_SUMMARY_EDGE_MARGIN == 20
    assert SESSION_SUMMARY_PREFERRED_TOP_MARGIN == 48
    assert SESSION_SUMMARY_MIN_VERTICAL_MARGIN == 16
    assert SESSION_SUMMARY_MAX_HEIGHT == 520
    assert session_summary_geometry(1_200, 900, 900) == (780, 16, 400, 520)
    assert session_summary_geometry(1_200, 954, 865) == (780, 48, 400, 520)
    assert SESSION_SUMMARY_HEADER_HEIGHT == 44
    assert SESSION_SUMMARY_FOOTER_HEIGHT == 48
    assert SESSION_SUMMARY_FRAME_BORDER_WIDTH == 1


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


def test_session_summary_compact_density_covers_measured_macos_host_heights():
    assert SESSION_SUMMARY_COMPACT_HOST_HEIGHT == 903
    assert session_summary_uses_compact_density(633) is True
    assert session_summary_uses_compact_density(813) is True
    assert session_summary_uses_compact_density(873) is True
    assert session_summary_uses_compact_density(903) is False
    assert session_summary_uses_compact_density(954) is False




def test_session_summary_typography_keeps_the_approved_title_and_hero_scale():
    source = SOURCE_PATH.read_text(encoding="utf-8") + SOURCE_PATH.with_name("reward_receipt.py").read_text(encoding="utf-8")
    assert "font-size:13px" in source
    assert "summaryTitle='true'] {font-size:20px" in source
    assert "summaryHero='true'] {font-size:40px" in source
    assert "summaryHeroLabel='true']" in source
    assert "font-size:14px;font-weight:520" in source
    assert "font-size:20px;font-weight:700" in source
    assert "summaryLongMetric='true'] {font-size:17px;}" in source
    assert "QPushButton:pressed, QToolButton:pressed" in source
    assert "QPushButton[summaryPrimary='true']:pressed" in source
    assert "QPushButton[summarySecondary='true']:pressed" in source


def test_session_summary_card_exposes_new_footer_art_and_motion_api():
    signature = inspect.signature(SessionSummaryCard.__init__)
    assert tuple(signature.parameters)[:8] == (
        "self",
        "parent",
        "payload",
        "on_dismiss",
        "on_open_garden",
        "on_continue_reviews",
        "engine",
        "animations_enabled",
    )
    assert isinstance(SessionSummaryCard.widget, property)
    for method in ("show", "close", "reposition", "_continue_reviews"):
        assert callable(getattr(SessionSummaryCard, method))


def test_card_keeps_header_footer_fixed_and_only_body_scrollable():
    source = SOURCE_PATH.read_text(encoding="utf-8") + SOURCE_PATH.with_name("reward_receipt.py").read_text(encoding="utf-8")
    assert "class SessionSummaryCard(QFrame)" in source
    assert "WA_ShowWithoutActivating" in source
    assert "Qt.FocusPolicy.NoFocus" in source
    assert 'self._header.setFixedHeight(SESSION_SUMMARY_HEADER_HEIGHT)' in source
    assert 'self._footer.setFixedHeight(SESSION_SUMMARY_FOOTER_HEIGHT)' in source
    assert 'self._scroll.setWidget(body)' in source
    assert "ScrollBarAsNeeded" in source
    assert "ScrollBarAlwaysOff" in source
    assert "stable_body_width = max(1, provisional[2] - 8)" in source
    assert "self._body.setFixedWidth(stable_body_width)" in source
    assert "parent.installEventFilter(self)" in source
    assert "parent.removeEventFilter(self)" in source
    for property_name in (
        "summaryHomeClearanceTracking",
        "summaryHomeClearanceMeasured",
        "summaryHomeClearanceHorizontalOverlap",
        "summaryHomeClearanceTelemetry",
    ):
        assert property_name in source
    assert "QDialog" not in source
    assert "setModal" not in source
    assert "activateWindow" not in source




def test_session_receipt_keeps_totals_above_progress_and_optional_details():
    source = SOURCE_PATH.read_text(encoding="utf-8")
    page = _method_source("_rebuild_page", "_add_pager")
    assert "_add_today_cards" not in source
    assert "ankiGardenSessionBreakdownToggle" not in source
    assert "ankiGardenSessionPlantsAffectedToggle" not in source
    assert 'self._details_expanded = False' not in source
    assert page.index("self._add_reward_strip") < page.index("self._add_highlights")
    assert page.index("self._add_plant_progress") < page.index("self._add_breakdown")
    assert 'self._progress_details_expanded = False' in source
    assert '"summaryDetailsAlwaysVisible", False' in page
    summary = SimpleNamespace(garden_coins_total=14, plant_growth_total_units=4000,
                              shared_growth_total_units=0, stored_growth=SimpleNamespace(added_units=0),
                              total_finds=2, environment_discoveries=(object(),))
    metrics = SessionSummaryCard._reward_metrics(summary, SimpleNamespace(growth_applied_total_units=4000))
    assert [(row[1], row[2]) for row in metrics] == [("Coins", "+14"), ("Growth", "+40"), ("Items & finds", "3")]


def test_highlight_cards_are_static_prioritized_and_two_line_safe():
    source = SOURCE_PATH.read_text(encoding="utf-8") + SOURCE_PATH.with_name("reward_receipt.py").read_text(encoding="utf-8")
    projection_source = SOURCE_PATH.with_name("session_summary.py").read_text(
        encoding="utf-8"
    )
    method = _method_source("_add_highlight_card", "_reward_metrics")
    assert 'setProperty("summaryHighlightKind", kind)' in method
    assert 'setProperty("summaryStatic", True)' in method
    assert "setCursor" not in method
    assert "setWordWrap(True)" in source
    assert 'setProperty("summaryTwoLineName", True)' in source
    assert "elidedText" not in source
    assert "Final growth stage reached" in projection_source
    assert "unlock_category_copy" in source
    assert "Completed during this session" not in source
    highlights = _method_source("_add_highlights", "_add_highlight_card")
    assert "candidates[:2]" in highlights
    assert "candidates = (*featured, *overflow)" in highlights
    compact = _method_source("_add_compact_highlight_row", "_add_highlight_card")
    assert 'setProperty("summaryHighlightCompact", True)' in compact
    assert 'setProperty("summaryStatic", True)' in compact
    assert "setCursor" not in compact
    assert 'setFixedWidth(88)' in method
    assert "chip_layout.addStretch" not in method
    assert "compact_reward_chip" in method
    assert "len(reward_text) <= 24" in method
    assert method.index("eyebrow_row.addWidget") < method.index("copy.addWidget(title)")
    assert method.index("copy.addWidget(title)") < method.index(
        "copy.addWidget(reward_chip(), 0, Qt.AlignmentFlag.AlignLeft)"
    )




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




def test_semantic_art_records_real_provenance_and_uses_shared_compositors():
    source = SOURCE_PATH.read_text(encoding="utf-8") + SOURCE_PATH.with_name("reward_receipt.py").read_text(encoding="utf-8")
    for property_name in (
        "summaryArtKind",
        "summaryArtSource",
        "summaryArtFallback",
        "summaryArtSourceWidth",
        "summaryArtSourceHeight",
        "summaryArtLogicalWidth",
        "summaryArtLogicalHeight",
        "summaryArtVector",
    ):
        assert property_name in source
    assert "normalized_plant_pixmap" in source
    assert "environment_preview_pixmap" in source
    assert "from .dashboard import" not in source
    assert '60 if kind == "full_bloom"' in source
    assert "58 if garden_item else 88" in source
    assert 'kind="garden_item" if is_feature else "environment"' in source
    assert 'setProperty("summaryGardenItemArt", is_feature)' in source
    assert "collection" not in _method_source(
        "_environment_art_label", "_reward_art_label"
    )
    reward_art = _method_source("_reward_art_label", "_rebuild_footer")
    assert '"garden_coins": "garden_coin"' in reward_art
    assert '"growth": "growth_resource"' in reward_art
    assert 'bundled_ui_asset_path(item_key)' in reward_art
    assert 'getattr(self._engine, "resolve_item_asset", None)' in reward_art


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


def test_footer_has_contextual_actions_no_dismiss_button_and_failure_stays_open():
    source = SOURCE_PATH.read_text(encoding="utf-8") + SOURCE_PATH.with_name("reward_receipt.py").read_text(encoding="utf-8")
    rebuild = _method_source("_rebuild_page", "_add_pager")
    footer = _method_source("_rebuild_footer", "_open_garden")
    continue_method = _method_source("_continue_reviews", "_natural_height")
    assert '"Open garden", self._open_garden' in footer
    assert '"Continue studying", self._continue_reviews' in footer
    assert '"Close", self.close' in footer
    assert 'QPushButton("Dismiss"' not in source
    assert 'setObjectName("ankiGardenSessionOpenGarden")' in footer
    assert 'setObjectName("ankiGardenSessionContinueReviews")' in footer
    assert "and callable(self._on_continue_reviews)" in rebuild
    assert "if succeeded:" in continue_method
    assert "self.close()" in continue_method
    assert 'setProperty("summaryContinueFailed", True)' in continue_method
    assert "Reviews could not be resumed" in continue_method
    open_method = _method_source("_open_garden", "_continue_reviews")
    assert open_method.index("self.close()") < open_method.index("callback()")


def test_utility_icons_cover_all_new_native_semantics():
    assert {
        "storage",
        "find",
        "environment",
        "fertilizer",
        "booster",
        "reviews",
    }.issubset(GARDEN_ICON_PATHS)


def test_motion_is_one_shot_and_honors_the_resolved_reduced_motion_policy():
    method = _method_source("_start_entry_animation", "close")
    assert "if self._animation_started" in method
    assert "if not self._animations_enabled" in method
    assert "QGraphicsOpacityEffect" in method
    assert "setDuration(200)" in method
    assert 'b"pos"' not in method
    assert "self._body.setGraphicsEffect(None)" in method
    assert "fade.finished.connect(finish_fade)" in method


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
