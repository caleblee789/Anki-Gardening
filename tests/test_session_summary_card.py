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
    source = SOURCE_PATH.read_text(encoding="utf-8")
    return source.split(f"def {name}", 1)[1].split(f"def {following}", 1)[0]


def test_session_summary_geometry_uses_380_preferred_width_and_32px_narrow_allowance():
    assert SESSION_SUMMARY_DEFAULT_WIDTH == 380
    assert SESSION_SUMMARY_MAX_WIDTH == 380
    assert SESSION_SUMMARY_EDGE_MARGIN == 20
    assert SESSION_SUMMARY_PREFERRED_TOP_MARGIN == 48
    assert SESSION_SUMMARY_MIN_VERTICAL_MARGIN == 16
    assert SESSION_SUMMARY_MAX_HEIGHT is None
    assert session_summary_geometry(1_200, 900, 900) == (800, 16, 380, 868)
    assert session_summary_geometry(1_200, 954, 865) == (800, 48, 380, 865)
    assert SESSION_SUMMARY_HEADER_HEIGHT == 52
    assert SESSION_SUMMARY_FOOTER_HEIGHT == 60
    assert SESSION_SUMMARY_FRAME_BORDER_WIDTH == 1


def test_session_summary_geometry_contracts_inside_small_viewports():
    assert session_summary_geometry(340, 300, 500) == (12, 16, 308, 268)
    assert session_summary_geometry(900, 800, 212) == (500, 48, 380, 212)
    assert session_summary_geometry(28, 30, 500) == (7, 16, 1, 1)
    assert session_summary_geometry(
        1_200,
        900,
        900,
        reserved_top=124,
    ) == (800, 140, 380, 744)


def test_session_summary_compact_density_covers_measured_macos_host_heights():
    assert SESSION_SUMMARY_COMPACT_HOST_HEIGHT == 903
    assert session_summary_uses_compact_density(633) is True
    assert session_summary_uses_compact_density(813) is True
    assert session_summary_uses_compact_density(873) is True
    assert session_summary_uses_compact_density(903) is False
    assert session_summary_uses_compact_density(954) is False


def test_session_summary_palette_has_semantic_reward_tokens_and_light_adaptation():
    dark = session_summary_palette(None)
    light = session_summary_palette(230)
    assert dark["elevated_surface"] == GARDEN_THEME["session_summary_panel_bg"]
    for key in (
        "growth_accent",
        "coin_accent",
        "find_accent",
        "milestone_accent",
        "progress_track",
        "highlight_surface",
        "action_pressed",
    ):
        assert dark[key]
        assert light[key]
    assert dark["find_accent"] == GARDEN_THEME["session_summary_find"]
    assert dark["milestone_accent"] == GARDEN_THEME["session_summary_milestone"]
    assert light["elevated_surface"] != dark["elevated_surface"]


def test_session_summary_typography_keeps_the_approved_title_and_hero_scale():
    source = SOURCE_PATH.read_text(encoding="utf-8")
    assert "font-size:13px" in source
    assert "summaryTitle='true'] {font-size:18px" in source
    assert "summaryHero='true'] {font-size:34px" in source
    assert "summaryHeroLabel='true']" in source
    assert "font-size:14px;font-weight:520" in source
    assert "hero_layout.setSpacing(2)" in source
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
    source = SOURCE_PATH.read_text(encoding="utf-8")
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


def test_main_body_hierarchy_matches_the_approved_summary_order():
    method = _method_source("_rebuild_page", "_add_pager")
    calls = [
        "self._add_hero",
        "self._add_today_cards",
        "self._add_highlights",
        "self._add_rewards_earned",
        "self._add_active_boosts",
    ]
    positions = [method.index(call) for call in calls]
    assert positions == sorted(positions)
    assert 'setObjectName("ankiGardenSessionBody")' in method


def test_today_progress_is_native_semantic_and_animation_ready():
    source = SOURCE_PATH.read_text(encoding="utf-8")
    method = _method_source("_add_today_cards", "_section_heading")
    assert 'setObjectName("ankiGardenSessionToday")' in method
    assert "QProgressBar" in method
    assert 'setObjectName("ankiGardenSessionTodayProgress")' in method
    assert 'setProperty("progressFraction"' in method
    assert "completed this session" in source
    assert 'QPropertyAnimation(progress, b"value"' in source
    assert "setDuration(320)" in source
    assert "setStartValue(progress_start)" in source
    assert 'getattr(today, "start_progress_value"' in method
    assert 'end.status not in {"not_eligible", "unavailable"}' in method
    assert "if show_progress:" in method


def test_highlight_cards_are_static_prioritized_and_two_line_safe():
    source = SOURCE_PATH.read_text(encoding="utf-8")
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
    assert "candidates[2:]" in highlights
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


def test_grouped_rewards_details_and_active_boosts_have_stable_semantics():
    source = SOURCE_PATH.read_text(encoding="utf-8")
    for object_name in (
        "ankiGardenSessionRewards",
        "ankiGardenSessionRewardCard",
        "ankiGardenSessionBreakdownToggle",
        "ankiGardenSessionBreakdown",
        "ankiGardenSessionActiveBoosts",
        "ankiGardenSessionBoostCard",
    ):
        assert object_name in source
    for key in (
        "total_growth",
        "plant_growth",
        "garden_coins",
        "standard_finds",
        "shared_growth",
        "stored_growth",
        "summaryProjectGrowthUnits",
        "summaryProjectTargetType",
        "garden_coins_total",
    ):
        assert key in source
    assert "Direct plant growth" in source
    assert "Shared Growth distributed" in source
    assert "Total applied" in source
    assert "project_growth_total_units" in source
    assert "project_growth_allocations" in source
    assert "Reward breakdown" in source
    assert "Additional to the session subtotal; included in " in source
    assert "Total earned." in source
    assert 'self._section_heading("Progress details")' in source
    assert "Rewards Earned" in source
    assert 'self._section_heading("Items added")' in source
    assert '"Total Growth"' in source
    assert '"Plant Growth"' in source
    assert '"Standard Finds"' in source
    assert "logical_size=14" in _method_source(
        "_add_reward_strip", "_add_find_summary"
    )
    assert 'toggle.setFixedHeight(40)' in source
    assert 'setProperty("summaryBoostKind", kind)' in source
    assert 'setProperty("summaryMetricDivider", True)' in source
    assert 'setProperty("summaryBoostRow", True)' in source
    boost_rows = _method_source("_add_active_boosts", "_refresh_active_effects")
    assert "row_widget.setMinimumHeight(36)" in boost_rows
    assert "row_widget.setFixedHeight(36)" not in boost_rows
    assert 'semantic_kind="active boost"' in boost_rows
    assert 'fallback_icon=kind if kind in {"fertilizer", "booster"} else "find"' in boost_rows
    assert 'setProperty("summaryBoostArt", True)' in boost_rows
    assert 'setProperty("summaryBoostArtReference", art_reference)' in boost_rows
    effect_art = _method_source("_effect_art_reference", "_effect_value")
    assert 'return "booster_potion"' in effect_art
    assert 'return f"fertilizer_{tier}"' in effect_art
    assert 'tier in {"basic", "quality", "premium"}' in effect_art
    reward_art = _method_source("_reward_art_label", "_rebuild_footer")
    assert 'fallback_icon: str = "find"' in reward_art
    assert "fallback_icon=fallback_icon" in reward_art
    assert "row_widget.setVisible(visible)" in source
    assert "×{max(1, int(quantity)):,}" in source


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


def test_find_summary_keeps_three_aggregated_groups_visible_and_accounts_for_more():
    items = (
        ("charge", "Small Growth Charge", "charge.webp", 2),
        ("cache", "Garden Coin Cache", "cache.webp", 1),
        ("stored", "Stored Growth Charge", "stored.webp", 1),
        ("booster", "Booster Potion", "booster.webp", 3),
    )

    visible, hidden_quantity = session_find_summary_plan(items[:3])
    assert visible == items[:3]
    assert hidden_quantity == 0

    visible, hidden_quantity = session_find_summary_plan(items)
    assert visible == items[:3]
    assert hidden_quantity == 3

    source = SOURCE_PATH.read_text(encoding="utf-8")
    method = _method_source("_add_find_summary", "_find_row_widget")
    assert "QHBoxLayout" not in method
    assert "for index, item in enumerate(visible)" in method
    assert 'more.clicked.connect(self._expand_find_breakdown)' in method
    row = _method_source("_find_row_widget", "_add_find_row")
    assert "row_widget.setFixedHeight(36)" in row
    assert "self._reward_art_label(art, 26)" in row


def test_semantic_art_records_real_provenance_and_uses_shared_compositors():
    source = SOURCE_PATH.read_text(encoding="utf-8")
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
    assert '"garden_coin": "coin"' in reward_art
    assert '"growth": "growth"' in reward_art
    assert '"ui_growth_charge_small": "growth_charge_small"' in reward_art
    assert 'getattr(self._engine, "resolve_item_asset", None)' in reward_art
    assert "self._reward_art_label(art, 26)" in source


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


def test_earned_garden_feature_art_can_ignore_current_loadout_visibility():
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
    ) is None
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
                event_key=find_event_id,
                reward_type="inventory_item",
                source="garden_find",
                source_id="small_charge",
                scheduler_day="2026-08-28",
                correlation_id=find_event_id,
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
    assert plan[0].source_labels == ("Standard Find", "Full Bloom")
    assert tuple(
        (contribution.label, contribution.quantity)
        for contribution in plan[0].source_contributions
    ) == (("Standard Find", 1), ("Full Bloom", 1))

    receipt_only = session_earned_item_plan(SimpleNamespace(
        find_items_reconciled=False,
        standard_finds=(),
        find_items=(),
        reward_receipts=(RewardReceipt(
            event_key=find_event_id,
            reward_type="inventory_item",
            source="garden_find",
            source_id="small_charge",
            scheduler_day="2026-08-28",
            correlation_id=find_event_id,
            occurred_at="2026-08-28T10:00:00Z",
            amount=1,
            item_id="growth_charge_small",
        ),),
    ))
    assert tuple((item.quantity, item.source_labels) for item in receipt_only) == (
        (1, ("Standard Find",)),
    )


def test_footer_has_contextual_actions_no_dismiss_button_and_failure_stays_open():
    source = SOURCE_PATH.read_text(encoding="utf-8")
    rebuild = _method_source("_rebuild_page", "_add_pager")
    footer = _method_source("_rebuild_footer", "_open_garden")
    continue_method = _method_source("_continue_reviews", "_natural_height")
    assert 'QPushButton("Open garden"' in footer
    assert 'QPushButton("Continue reviewing"' in footer
    assert 'QPushButton("Close"' in footer
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
    assert 'QPropertyAnimation(self, b"pos"' in method
    assert "QPoint(6, 0)" in method
    assert "setDuration(200)" in method
    highlight_motion = _method_source("_start_highlight_animation", "close")
    assert "QPoint(0, 4)" in highlight_motion
    assert "summaryRevealAfterHighlights" in SOURCE_PATH.read_text(encoding="utf-8")
    assert "index * 60" in highlight_motion
    assert "420" in highlight_motion
    assert "else 200" in highlight_motion
    assert "QVariantAnimation" in highlight_motion
    assert "setStartValue(0.96)" in highlight_motion
    assert 'b"blurRadius"' in highlight_motion


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
