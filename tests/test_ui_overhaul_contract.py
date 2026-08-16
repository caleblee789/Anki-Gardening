import ast
from math import isfinite
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _source(relative: str) -> str:
    return (ROOT / relative).read_text("utf-8")


def _method_source(relative: str, class_name: str, method_name: str) -> str:
    """Return one exact method body without importing Anki's Qt runtime."""

    source = _source(relative)
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == method_name:
                    segment = ast.get_source_segment(source, child)
                    assert segment is not None
                    return segment
    raise AssertionError(f"Missing {class_name}.{method_name} in {relative}")


def _class_source(relative: str, class_name: str) -> str:
    source = _source(relative)
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            segment = ast.get_source_segment(source, node)
            assert segment is not None
            return segment
    raise AssertionError(f"Missing {class_name} in {relative}")


def _function_source(relative: str, function_name: str) -> str:
    source = _source(relative)
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            segment = ast.get_source_segment(source, node)
            assert segment is not None
            return segment
    raise AssertionError(f"Missing {function_name} in {relative}")


def test_nursery_uses_ready_catalog_and_the_same_flow_for_the_free_starter() -> None:
    dashboard = _source("ankigarden/ui/dashboard.py")
    nursery = dashboard.split("class NurseryDialog", 1)[1].split("class PlantInfoCard", 1)[0]

    assert "self.engine.catalog_summary()" in nursery
    assert "self.engine.choose_starter(species)" in nursery
    assert "self._currently_growing_strip(active)" in nursery
    assert '"Your collection"' in nursery
    assert '"Botanical catalog"' in nursery
    assert "self._plant_stage_strip(species)" in nursery
    assert "self._plant_artwork(species, GROWTH_STAGES[0], 112)" in nursery
    assert "starter_selection_complete" in nursery


def test_nursery_previews_crop_manifest_artwork_into_a_grounded_tile() -> None:
    scope: dict[str, object] = {"Any": object, "isfinite": isfinite}
    exec(_function_source("ankigarden/ui/dashboard.py", "_padded_preview_bounds"), scope)
    crop = scope["_padded_preview_bounds"]

    assert tuple(round(value, 3) for value in crop((0.4, 0.6, 0.2, 0.2))) == (
        0.38,
        0.58,
        0.24,
        0.24,
    )
    assert crop(None) == (0.0, 0.0, 1.0, 1.0)

    preview = _method_source(
        "ankigarden/ui/dashboard.py", "NurseryDialog", "_plant_artwork"
    )
    assert "size: int = 96" in preview
    assert "_asset_preview_label(" in preview
    assert 'property_name="nurseryArtwork"' in preview
    helper = _function_source("ankigarden/ui/dashboard.py", "_asset_preview_label")
    assert 'getattr(engine, "resolve_plant_asset", None)' in helper
    assert '"visible_bounds", placement.get("art_bounds")' in helper
    assert "_padded_preview_bounds(bounds)" in helper
    assert "pixmap.copy(crop_x, crop_y, crop_width, crop_height)" in helper
    assert '"seed": 0.92' in helper
    assert '"rare": 0.86' in helper
    assert "Qt.AlignmentFlag.AlignCenter" in helper
    assert "Qt.TransformationMode.SmoothTransformation" in helper
    available_card = _method_source(
        "ankigarden/ui/dashboard.py", "NurseryDialog", "_available_card"
    )
    assert "item_name = seed_title(species_name)" in available_card
    assert "title = QLabel(item_name)" in available_card
    assert 'ownership = QLabel("Not collected")' in available_card
    assert "COST_FREE" not in available_card
    assert "Cost: {amount} Garden Coins" in _source("ankigarden/ui/copy.py")
    assert '"Starts as Seed"' not in available_card
    assert "_compact_affordability_status(" in available_card


def test_rare_stage_preview_stays_hidden_everywhere_until_it_is_discovered() -> None:
    scope: dict[str, object] = {
        "Any": object,
        "GROWTH_THRESHOLDS": [0, 500, 2_500, 8_000, 20_000, 50_000],
    }
    exec(_function_source("ankigarden/ui/dashboard.py", "_rare_stage_unlocked"), scope)
    rare_stage_unlocked = scope["_rare_stage_unlocked"]

    class Engine:
        state: object

    engine = Engine()
    engine.state = {"plants": []}
    assert not rare_stage_unlocked(engine, "rose")
    engine.state = {
        "plants": [
            {"species": "rose", "stage": "flowering", "growth_points": 49_999},
            {"species": "bonsai", "stage": "rare", "growth_points": 50_000},
        ]
    }
    assert not rare_stage_unlocked(engine, "rose")
    engine.state["plants"][0]["growth_points"] = 50_000
    assert rare_stage_unlocked(engine, "rose")

    preview = _function_source("ankigarden/ui/dashboard.py", "_asset_preview_label")
    assert preview.index('if stage_key == "rare"') < preview.index(
        'getattr(engine, "resolve_plant_asset", None)'
    )
    assert "_rare_stage_unlocked(engine, species)" in preview
    assert "undiscovered=True" in preview
    assert "Rare-stage artwork remains hidden until this species reaches Rare." in preview

    populate = _function_source("ankigarden/ui/dashboard.py", "_populate_asset_preview")
    assert "rare_unlocked=rare_unlocked" in populate
    assert "target.setAccessibleDescription(preview.accessibleDescription())" in populate

    story = _method_source(
        "ankigarden/ui/dashboard.py", "PlantStoryDialog", "refresh"
    )
    growth = _method_source(
        "ankigarden/ui/dashboard.py", "GardenDetailsDialog", "_add_growth_stage_path"
    )
    assert 'rare_unlocked=stage_state != "upcoming"' in story
    assert 'rare_unlocked=state != "upcoming"' in growth

    nursery_artwork = _method_source(
        "ankigarden/ui/dashboard.py", "NurseryDialog", "_plant_artwork"
    )
    stage_strip = _method_source(
        "ankigarden/ui/dashboard.py", "NurseryDialog", "_plant_stage_strip"
    )
    stage_carousel = _method_source(
        "ankigarden/ui/dashboard.py", "NurseryDialog", "_plant_stage_carousel"
    )
    assert "_asset_preview_label(" in nursery_artwork
    assert "self._plant_artwork(species, stage, 48)" in stage_strip
    assert "self._plant_artwork(species, stage, 132)" in stage_carousel


def test_nursery_stage_carousel_uses_clear_bounded_navigation() -> None:
    carousel = _method_source(
        "ankigarden/ui/dashboard.py", "NurseryDialog", "_plant_stage_carousel"
    )

    assert 'QPushButton("← Previous")' in carousel
    assert 'QPushButton("Next →")' in carousel
    assert 'stage_count.setText(f"Stage {index + 1} of {len(GROWTH_STAGES)}")' in carousel
    assert carousel.count("set_control_enabled(") >= 2
    assert "index > 0" in carousel
    assert "index < len(GROWTH_STAGES) - 1" in carousel
    assert "This is the first growth stage." in carousel
    assert "This is the final growth stage." in carousel
    assert "state[\"index\"] = max(" in carousel
    assert "% len(GROWTH_STAGES)" not in carousel
    assert "preview.setToolTip(replacement.toolTip())" in carousel
    assert "preview.setAccessibleDescription(replacement.accessibleDescription())" in carousel
    assert "layout = QHBoxLayout(widget)" in carousel
    assert "stage_details = QVBoxLayout()" in carousel
    assert "widget.setMaximumWidth(330)" in carousel
    assert "button.setFixedSize(84, BUTTON_MIN_HEIGHT)" in carousel


def test_nursery_cards_use_larger_readable_type() -> None:
    dashboard = _source("ankigarden/ui/dashboard.py")
    nursery = dashboard.split("class NurseryDialog", 1)[1].split(
        "class PlantInfoCard", 1
    )[0]

    assert "QLabel[nurseryTitle='true'] { font-size:30px" in nursery
    assert "QLabel[nurseryPlantName='true'] { color:#fff3da; font-size:19px" in nursery
    assert "QLabel[nurseryMeta='true'] { color:#d6c4ac; font-size:14px" in nursery
    assert 'title.setProperty("nurseryPlantName", True)' in nursery


def test_nursery_tabs_use_available_width_without_cutting_off_labels() -> None:
    dashboard = _source("ankigarden/ui/dashboard.py")
    nursery = dashboard.split("class NurseryDialog", 1)[1].split(
        "class PlantInfoCard", 1
    )[0]

    assert "self.catalog_tabs.tabBar().setExpanding(True)" in nursery
    assert "self.catalog_tabs.tabBar().setElideMode(Qt.TextElideMode.ElideNone)" in nursery
    assert "button.setFixedSize(84, BUTTON_MIN_HEIGHT)" in nursery
    assert "navigation = QHBoxLayout()" in nursery
    assert "navigation.setSpacing(8)" in nursery


def test_available_plants_fill_space_with_a_two_column_catalog() -> None:
    available_card = _method_source(
        "ankigarden/ui/dashboard.py", "NurseryDialog", "_available_card"
    )
    refresh = _method_source(
        "ankigarden/ui/dashboard.py", "NurseryDialog", "refresh"
    )

    assert "card_layout = QVBoxLayout(card)" in available_card
    assert "self._plant_description(species)" in available_card
    assert 'details = QPushButton("Details")' in available_card
    assert "footer = QHBoxLayout()" in available_card
    assert "Qt.AlignmentFlag.AlignHCenter" in available_card
    assert "available_grid_host = ResponsiveTileGrid(breakpoint=600)" in refresh
    assert "available_grid_host.add_tile(" in refresh


def test_nursery_is_directly_reachable_from_each_starter_entry_point() -> None:
    dashboard = _source("ankigarden/ui/dashboard.py")
    home = _source("ankigarden/ui/home_widget.py")
    scene = _source("ankigarden/ui/scene.py")
    starter_setup = _method_source(
        "ankigarden/ui/dashboard.py", "GardenDashboard", "_present_starter_setup_if_needed"
    )
    open_dashboard = _method_source(
        "ankigarden/addon.py", "AnkiGardenApp", "_open_dashboard_when_ready"
    )
    activate_landmark = _method_source(
        "ankigarden/ui/scene.py", "GardenSceneWidget", "_activate_landmark"
    )

    assert '"garden.nursery.open": self._open_nursery' in dashboard
    assert '"garden.progress.open": self._open_progress' in dashboard
    assert "starter_selection_complete" in starter_setup
    assert "QInputDialog" not in dashboard
    assert "def _open_starter_nursery" in dashboard
    assert "self.starter_header_btn.clicked.connect(self._open_starter_nursery)" in dashboard
    assert "self.onboarding_action.clicked.connect(self._activate_onboarding_action)" in dashboard
    assert "STEP 1 OF 2" in dashboard
    assert "STEP 2 OF 2" in dashboard
    assert "if opening_settings:" in open_dashboard
    assert "opening_starter" in open_dashboard
    assert "_open_starter_nursery" in open_dashboard
    assert 'self.onboarding_action = QPushButton(CHOOSE_STARTER_ACTION)' in dashboard
    assert 'self.dismiss_onboarding = QPushButton(GARDEN_SETUP_SECONDARY_ACTION)' in dashboard
    assert 'self.scene.focus_landmark("garden.nursery.open")' in dashboard
    assert 'anki-garden:choose-starter' in home
    assert "CHOOSE_STARTER_ACTION" in home
    assert 'CHOOSE_STARTER_ACTION = "Choose plant"' in _source("ankigarden/ui/copy.py")
    assert "_open_starter_nursery()" in dashboard
    assert "not self.interactive" in activate_landmark
    assert "self._interaction.placing" in activate_landmark
    assert "normalized_id not in self._landmark_actions" in activate_landmark
    assert "self.landmarkActivated.emit(normalized_id)" in activate_landmark
    assert "self.scene = GardenSceneWidget()" in dashboard
    assert "GardenSceneWidget(interactive=False)" in _source("ankigarden/ui/garden_studio.py")


def test_garden_chrome_uses_one_unified_progress_dialog() -> None:
    dashboard = _source("ankigarden/ui/dashboard.py")
    capture = _source("ankigarden/capture_ui_faces.py")
    progress_source = _class_source(
        "ankigarden/ui/dashboard.py", "GardenProgressDialog"
    )
    open_progress = _method_source(
        "ankigarden/ui/dashboard.py", "GardenDashboard", "_open_progress"
    )
    open_details = _method_source(
        "ankigarden/ui/dashboard.py", "GardenDashboard", "_open_metric_details"
    )
    open_nursery = _method_source(
        "ankigarden/ui/dashboard.py", "GardenDashboard", "_open_nursery"
    )

    assert '("growth", "Plant Growth", GROWTH_EXPLANATION)' in dashboard
    assert '("streak", "Anki Streak", ANKI_STREAK_EXPLANATION)' in dashboard
    assert '("currency", "Garden Coins", GARDEN_CURRENCY_EXPLANATION)' in dashboard
    assert '("reviews", "Card answers"' not in dashboard
    assert 'self.progress_btn = QPushButton("Garden Progress")' in dashboard
    assert "class GardenDialog(DialogShell):" in dashboard
    assert "class GardenProgressDialog(GardenDetailsDialog):" in dashboard
    assert "class GardenDetailsDialog(GardenDialog):" in dashboard
    assert "class MetricDetailDialog(QDialog):" not in dashboard
    assert '("growth", "Plant Growth")' in dashboard
    assert '("streak", "Anki Streak")' in dashboard
    assert '("currency", "Garden Coins")' in dashboard
    assert "self.progress_dialog = GardenProgressDialog(" in dashboard
    assert "DialogSizeClass.CATALOG" in progress_source
    assert "self.apply_size_policy(" in progress_source
    assert "self.navigation = GardenSideNavigation()" in dashboard
    assert "self.set_body_widget(self.navigation)" in dashboard
    assert "self.details_dialog = self.progress_dialog" in dashboard
    assert "self.metric_dialogs" not in dashboard
    assert 'self.progress_dialog.open_page("overview")' in open_progress
    assert "self.garden_stats_bar.metricActivated.connect(self._open_metric_details)" in dashboard
    assert "self.progress_dialog.open_page(key)" in open_details
    assert "self.details_dialog.isVisible()" in open_nursery
    assert "self.details_dialog.close()" in open_nursery
    assert "WA_TransparentForMouseEvents" in dashboard
    assert "self.progress_dialog.finished.connect(self._restore_progress_focus)" in dashboard
    assert "self.details_dialog.finished.connect(self._restore_metric_focus)" in dashboard
    assert "self._metric_return_focus = self.garden_stats_bar.cells.get(key)" in open_details
    assert "self.details_tabs" not in dashboard
    assert "self.milestone_card.hide()" in dashboard
    assert "self.streak_ticks" not in dashboard
    assert 'getattr(dashboard, "progress_dialog", None)' in capture
    assert "metric_dialogs" not in capture
    assert "navigation.stack.currentIndex() == navigation.keys.index(metric)" in capture


def test_garden_details_shell_preserves_user_position_and_keyboard_focus() -> None:
    dashboard = _source("ankigarden/ui/dashboard.py")
    details = dashboard.split("class GardenDetailsDialog", 1)[1].split(
        "class GardenDashboard", 1
    )[0]

    assert 'super().__init__(parent, "Plant Growth")' in details
    assert "self.apply_size_policy(" in details
    assert "DialogSizeClass.STANDARD_TEXT" in details
    assert "preferred_width=740" in details
    assert "preferred_height=570" in details
    assert "self.setMinimumSize(620, 460)" not in details
    assert 'self.tabs = GardenTabs("Garden detail sections")' in details
    assert "def _position_over_parent_once" in dashboard
    assert "parent.window().frameGeometry()" in dashboard
    assert "frame.moveCenter(parent_frame.center())" in dashboard
    assert "self.present_over_parent()" in details
    assert "self.activateWindow()" not in details
    assert "QTimer.singleShot(0, self._center_on_parent)" not in details
    assert "self.tabs.tabBar().setFocus()" in details
    assert 'body.setProperty("detailBodyPanel", True)' in details
    assert "widget.hide()" in details
    assert 'self.close_button = QPushButton("Close")' not in details


def test_garden_details_growth_is_nonzero_first_and_uses_engine_stage_sources() -> None:
    growth = _method_source(
        "ankigarden/ui/dashboard.py", "GardenDetailsDialog", "_refresh_growth"
    )

    assert "growth_display(plant.growth_points)" in growth
    stage_path = _method_source(
        "ankigarden/ui/dashboard.py", "GardenDetailsDialog", "_add_growth_stage_path"
    )
    assert "GROWTH_STAGES" in stage_path
    assert "GROWTH_THRESHOLDS[index]" not in stage_path
    assert "ScrollBarAsNeeded" in stage_path
    assert '"✓ Completed"' in stage_path
    assert "display.stage_index" in stage_path
    assert '"completed" if index < display.stage_index' in stage_path
    assert '"current" if index == display.stage_index' in stage_path
    assert "active_rows" in growth
    assert '"Growth breakdown"' in growth
    assert "recorded != answer_growth" in growth
    assert '("Total Growth",' in growth
    assert 'if int(stats.growth_earned) == 0:' in growth
    assert '[(label, f"{value:,}") for label, value in active_rows]' in growth
    assert 'self._label("Growth Charges", "detailSection")' in growth
    assert 'f"{int(stats.growth_earned):,}"' in growth
    assert "stage_scroll" not in growth
    assert "stage_card.setMinimumWidth(98)" in stage_path
    assert " base + " not in growth


def test_garden_details_streak_uses_config_and_omits_maximum_progress_bar() -> None:
    dashboard = _source("ankigarden/ui/dashboard.py")
    streak = _method_source(
        "ankigarden/ui/dashboard.py", "GardenDetailsDialog", "_refresh_streak"
    )
    reward = _method_source(
        "ankigarden/ui/dashboard.py", "GardenDetailsDialog", "_streak_reward_text"
    )

    assert "STREAK_BONUS_TIERS" in streak
    assert "self.engine.STREAK_CURRENCY" in reward
    assert "_day_count(day)" in streak
    assert '"Next milestone: Day {next_day:,}"' in streak
    assert 'ProgressBar("Progress to the next Anki streak milestone")' in streak
    assert '"How the streak works".lower()' not in dashboard
    assert '"How the streak works"' in streak
    assert "The milestone layout leaves room" not in dashboard
    assert '"1 days"' not in dashboard


def test_garden_details_currency_renders_the_persisted_ledger_newest_first() -> None:
    currency = _method_source(
        "ankigarden/ui/dashboard.py", "GardenDetailsDialog", "_refresh_currency"
    )
    details = _source("ankigarden/ui/dashboard.py").split(
        "class GardenDetailsDialog", 1
    )[1].split("class GardenDashboard", 1)[0]

    assert "self.storage.state.currency_transactions" in currency
    assert "reverse=True" in currency
    assert "transaction.occurred_at" in currency
    assert "transaction.reason" in currency
    assert "transaction.delta" in currency
    assert "transaction.balance" in currency
    assert "transactions[:8]" in currency
    assert 'QPushButton("View all activity")' in currency
    assert "len(transactions) > 8" in currency
    assert "self.engine.STAGE_CURRENCY.items()" in currency
    assert "self.engine.STREAK_CURRENCY.items()" in currency
    assert "self.engine.COIN_DROP_AMOUNT" in currency
    assert "_credit_currency" not in details
    assert "_debit_currency" not in details


def test_dashboard_metric_cards_have_uniform_interaction_affordances() -> None:
    dashboard = _source("ankigarden/ui/dashboard.py")
    assert "class ElidingLabel(QLabel):" in dashboard
    assert 'self.growth_name = ElidingLabel("Choose a plant")' in dashboard
    stats = dashboard.split("class GardenStatsStrip", 1)[1].split(
        "class RearrangeBar", 1
    )[0]

    assert "cell.setMinimumHeight(96)" in stats
    assert "growth_layout.setContentsMargins(16, 10, 16, 11)" in stats
    assert "growth_layout.setSpacing(5)" in stats
    assert "growth_bar.setFixedHeight(10)" in stats
    assert 'cell.setProperty("separator", key != "currency")' in stats
    assert "QLabel(METRIC_AFFORDANCE)" not in stats
    assert 'METRIC_AFFORDANCE = "Open details"' in _source("ankigarden/ui/copy.py")
    assert "cell.setCursor(Qt.CursorShape.PointingHandCursor)" in stats
    assert "cell.setFocusPolicy(Qt.FocusPolicy.StrongFocus)" in stats
    assert "QPushButton[gardenStatCell='true']:hover" in dashboard
    assert "QPushButton[gardenStatCell='true']:pressed" in dashboard
    assert "QPushButton[gardenStatCell='true']:focus" in dashboard
    assert 'self.currency_support = QLabel("Spend in the Nursery")' in stats


def test_environment_catalog_previews_composite_weather_over_real_scenery() -> None:
    dashboard = _source("ankigarden/ui/dashboard.py")
    preview = dashboard.split("def _environment_preview_pixmap", 1)[1].split(
        "class ArtworkThumbnail", 1
    )[0]

    assert "engine.resolve_scenery_preview_asset(scenery_id)" in preview
    assert "engine.resolve_weather_preview_asset(item.item_id)" in preview
    assert "painter.drawPixmap(0, 0, overlay)" in preview
    assert "_environment_placeholder_pixmap" in preview
    assert "name.setWordWrap(True)" in dashboard
    assert "self.option_tabs.tabBar().setUsesScrollButtons(False)" in dashboard


def test_growth_metric_uses_compact_high_dpi_numeric_copy() -> None:
    dashboard = _source("ankigarden/ui/dashboard.py")
    stats = dashboard.split("class GardenStatsStrip", 1)[1].split(
        "class RearrangeBar", 1
    )[0]

    assert 'self._growth_value_full_text = "0 / 0 Growth"' in stats
    assert 'full_text.removesuffix(" Growth")' in stats
    assert "self.growth_value.setAccessibleName(full_text)" in stats
    assert "growth_layout.addWidget(growth_bar)" in stats
    assert stats.index("growth_layout.addWidget(growth_bar)") < stats.index(
        'self.progress = {"growth": growth_bar}'
    )


def test_toggle_switch_text_tracks_signal_blocked_checked_state() -> None:
    dashboard = _source("ankigarden/ui/dashboard.py")
    toggle = dashboard.split("class ToggleSwitch", 1)[1].split(
        "class ProgressRow", 1
    )[0]

    assert "def setChecked(self, checked: bool)" in toggle
    assert "super().setChecked(bool(checked))" in toggle
    assert "self._sync_accessible_state(bool(checked))" in toggle
    assert "self.setText(self.accessibleName())" in toggle
    assert "self.setIcon(_toggle_state_icon(bool(checked)))" in toggle
    assert "✓  On" not in toggle
    assert "○  Off" not in toggle


def test_header_settings_action_uses_a_centered_vector_painted_gear() -> None:
    dashboard = _source("ankigarden/ui/dashboard.py")
    build_ui = _method_source("ankigarden/ui/dashboard.py", "GardenDashboard", "_build_ui")

    assert "def _settings_gear_icon(" in dashboard
    assert "path.setFillRule(Qt.FillRule.OddEvenFill)" in dashboard
    assert "self.settings_btn = QPushButton()" in build_ui
    assert "self.settings_btn.setIcon(_settings_gear_icon(22))" in build_ui
    assert "self.settings_btn.setIconSize(QSize(22, 22))" in build_ui


def test_plant_card_and_move_flow_have_stable_direct_actions() -> None:
    dashboard = _source("ankigarden/ui/dashboard.py")
    card = dashboard.split("class PlantInfoCard", 1)[1].split("class GardenStatsStrip", 1)[0]
    rearrange = dashboard.split("class RearrangeBar", 1)[1].split("class GardenDashboard", 1)[0]
    build_ui = _method_source("ankigarden/ui/dashboard.py", "GardenDashboard", "_build_ui")
    movement = _method_source("ankigarden/ui/dashboard.py", "GardenDashboard", "_place_plant")
    undo = _method_source("ankigarden/ui/dashboard.py", "GardenDashboard", "_undo_move")

    positions: list[int] = []
    for label in ("Nurture", "Fertilize", "Move", "Story"):
        assert f'QPushButton("{label}")' in card
        positions.append(card.index(f'QPushButton("{label}")'))
    assert positions == sorted(positions)
    assert "actions.addWidget(self.nurture, 0, 0)" in card
    assert "actions.addWidget(self.fertilize, 0, 1)" in card
    assert "actions.addWidget(self.move, 1, 0)" in card
    assert "actions.addWidget(self.story, 1, 1)" in card
    assert 'self.nurture.setText("Nurture")' in card
    assert 'self.fertilize.setText("Fertilize")' in card
    assert "self.nurture.setChecked(False)" in card
    assert "self.nurture.setVisible(not active and not fully_grown)" in card
    assert "self.nurtured_badge.setVisible(active or fully_grown)" in card
    assert "nurture_reason" in card
    assert "fertilizer_reason" in card
    assert "Nurture this plant before using Fertilizer." in card
    plant_section_style = dashboard.split("QLabel[plantCardSection='true']", 1)[1].split("}", 1)[0]
    assert "font-size:12px" in plant_section_style
    assert "self.plant_card.nurture.clicked.connect" in build_ui
    assert "self.plant_card.fertilize.clicked.connect" in build_ui
    assert "self.plant_card.move.clicked.connect" in build_ui
    assert "self.plant_card.story.clicked.connect" in build_ui
    assert not any(control in rearrange + movement for control in ("QComboBox", "QMenu"))
    assert "destination_selector" not in rearrange + movement
    assert 'QPushButton("Done")' not in rearrange
    assert "self.engine.stage_placement(draft, destination_slot)" in movement
    assert "self.engine.commit_placement_draft(draft)" in movement
    assert "self._undo_placement = committed" in movement
    assert movement.index("self.engine.commit_placement_draft(draft)") < movement.index(
        "self.toast_region.show_message("
    )
    assert "self.engine.restore_placement(self._undo_placement)" in undo
    assert 'self.toast_region.show_message("Move undone.")' in undo


def test_story_is_chronological_compact_and_has_an_up_next_card() -> None:
    dashboard = _source("ankigarden/ui/dashboard.py")
    story = dashboard.split("class PlantStoryDialog", 1)[1].split("class NurseryDialog", 1)[0]
    refresh = _method_source("ankigarden/ui/dashboard.py", "PlantStoryDialog", "refresh")

    assert 'self.edit_name_btn = QPushButton("Rename")' in story
    assert 'self.edit_name_btn.setAccessibleName("Rename plant")' in story
    assert "self.edit_name_btn.setMinimumHeight(BUTTON_MIN_HEIGHT)" in story
    assert 'up_next_title = QLabel("Up next")' in story
    assert "memories = chronological_memories(plant.memories)" in refresh
    assert "reverse=True" not in refresh
    assert 'timeline_label = QLabel("Memories")' in dashboard
    assert "New memories will appear as this plant grows." in dashboard
    assert "Anki card {'answer' if answers == 1 else 'answers'}" in refresh
    assert "self.stage_nodes" in story
    assert "stage_preview = ArtworkThumbnail()" in story
    assert 'stage_preview.setProperty("storyStagePreview", True)' in story
    assert refresh.count("_populate_asset_preview(") == 2
    assert "plant.species" in refresh
    assert "stage_key" in refresh
    assert "storyStageMark" not in story
    assert "FULLY_GROWN_MESSAGE" in refresh
    assert "FULLY_GROWN_ACTION" in story


def test_story_reuses_the_nurtured_badge_and_shows_one_growth_counter() -> None:
    dashboard = _source("ankigarden/ui/dashboard.py")
    story = dashboard.split("class PlantStoryDialog", 1)[1].split("class NurseryDialog", 1)[0]
    story_refresh = _method_source(
        "ankigarden/ui/dashboard.py", "PlantStoryDialog", "refresh"
    )
    card_refresh = _method_source(
        "ankigarden/ui/dashboard.py", "PlantInfoCard", "set_selected"
    )

    assert 'self.nurturing_status.setProperty("nurturedBadge", True)' in story
    assert 'self.nurturing_status.setProperty("detailStatus", True)' not in story
    assert dashboard.count(
        "QLabel[nurturedBadge='true'] {{ {_nurtured_badge_declarations()} }}"
    ) == 2
    assert 'self.stage_progress.set_progress(\n                "Growth",' in story_refresh
    assert story_refresh.count(
        'value_text=f"{progress.stage_points:,} / {progress.stage_goal:,} Growth"'
    ) == 1
    assert 'f"{progress.points_remaining:,} Growth remaining' not in story_refresh
    assert 'f"Progress to {next_stage}"' in card_refresh
    assert card_refresh.count(
        'value_text=f"{stage_points:,} / {stage_goal:,} Growth"'
    ) == 1
    assert "self.growth_remaining.setText(" not in card_refresh
    assert card_refresh.count("self.growth_remaining.hide()") == 2


def test_story_layout_keeps_short_timelines_attached_to_their_heading() -> None:
    dashboard = _source("ankigarden/ui/dashboard.py")
    story = dashboard.split("class PlantStoryDialog", 1)[1].split("class NurseryDialog", 1)[0]
    timeline_refresh = _method_source(
        "ankigarden/ui/dashboard.py", "MemoryTimeline", "set_memories"
    )

    assert "QSizePolicy.Policy.Preferred" in dashboard.split(
        "class MemoryTimeline", 1
    )[1].split("class PlantStoryDialog", 1)[0]
    assert "self.updateGeometry()" in timeline_refresh
    assert "QScrollArea" not in dashboard.split("class MemoryTimeline", 1)[1].split("class PlantStoryDialog", 1)[0]
    assert "self.layout.addStretch" not in timeline_refresh
    assert 'story_panel.setProperty("storyTimeline", True)' in story
    assert "story_layout.addWidget(self.timeline)" in story
    assert "root.addWidget(self.timeline, 1)" not in story
    assert "identity_text.addLayout(self.rename_row)" in story
    assert "root.addLayout(self.rename_row)" not in story
    assert 'story_body.setProperty("storyBody", True)' in story
    assert 'self.story_scroll.viewport().setProperty("storyViewport", True)' in story
    assert 'story_body.setStyleSheet("background:#071a15;")' not in story


def test_settings_expose_one_real_theme_and_stage_changes_until_save() -> None:
    studio = _source("ankigarden/ui/garden_studio.py")
    dashboard = _source("ankigarden/ui/dashboard.py")
    settings = dashboard.split("class GardenSettingsDialog", 1)[1].split("class MemoryTimeline", 1)[0]
    theme_card = studio.split("self.theme_card = QFrame()", 1)[1].split(
        "self.animations_enabled = QCheckBox()", 1
    )[0]
    apply_preview = _method_source("ankigarden/ui/garden_studio.py", "GardenStudioWidget", "_apply_preview")
    save = _method_source("ankigarden/ui/dashboard.py", "GardenSettingsDialog", "_save_visual_settings")
    hide_saved = _method_source("ankigarden/ui/dashboard.py", "GardenSettingsDialog", "_hide_saved_status")

    assert "self.theme_combo" not in studio
    assert 'theme_title = QLabel("Current scenery")' in theme_card
    assert "self.theme_thumbnail = QLabel()" in theme_card
    assert 'self.theme_thumbnail.setAccessibleName("Verdant Twilight preview")' in theme_card
    assert "QComboBox" not in theme_card
    assert 'self.manage_environment = QToolButton()' in theme_card
    assert 'background_asset = asset_paths.get("background")' in apply_preview
    assert "self.theme_thumbnail.setPixmap(background_pixmap.scaled(" in apply_preview
    assert 'self.fine_tune_toggle.setText("Fine tune")' in studio
    assert "self.fine_tune_section.hide()" in studio
    assert 'QPushButton("Save changes")' in settings
    assert 'QPushButton("Cancel")' in settings
    assert 'QPushButton("Restore display defaults")' in settings
    assert "self.garden_name_edit = QLineEdit()" in settings
    assert "self.garden_name_edit.setMaxLength(MAX_GARDEN_NAME_LENGTH + 80)" in settings
    assert 'f"Garden name must be 1 to {MAX_GARDEN_NAME_LENGTH} characters."' in settings
    assert 'self.garden_name_error.setProperty("fieldError", True)' in settings
    assert "self.garden_name_error.setVisible(not valid)" in settings
    assert 'self.save_status.setText("Fix 1 error before saving.")' in save
    assert "self.garden_name_edit.setFocus()" in save
    assert "self.garden_name_edit.selectAll()" in save
    assert "self.engine.rename_garden" in settings
    garden = dashboard.split("class GardenDashboard", 1)[1]
    assert 'QPushButton("Rename")' not in garden
    assert "self.config.update(payload)" in save
    assert 'self.save_status.setText("Saved")' in save
    assert "self._save_status_generation += 1" in save
    assert "generation = self._save_status_generation" in save
    assert "QTimer.singleShot(2400, lambda: self._hide_saved_status(generation))" in save
    assert "generation != self._save_status_generation" in hide_saved
    assert 'self.save_status.text() == "Saved"' in hide_saved
    assert "self.save_status.hide()" in hide_saved
    assert 'self.tabs.addTab(advanced, UI_TEXT["tab_advanced"])' in settings
    assert "from ..build_capabilities import DEVELOPMENT_MUTATION_ENABLED" in dashboard
    assert "if DEVELOPMENT_MUTATION_ENABLED:" in settings
    assert "ANKI_GARDEN_DEV_TOOLS" not in settings
    capabilities = _source("ankigarden/build_capabilities.py")
    assert 'BUILD_MODE = "production"' in capabilities
    assert "CAPTURE_HARNESS_ENABLED = False" in capabilities
    assert "DEVELOPMENT_MUTATION_ENABLED = False" in capabilities


def test_settings_preview_debounces_expensive_asset_resolution() -> None:
    studio = _source("ankigarden/ui/garden_studio.py")
    slider = _method_source("ankigarden/ui/garden_studio.py", "GardenStudioWidget", "_on_slider_changed")
    schedule = _method_source("ankigarden/ui/garden_studio.py", "GardenStudioWidget", "_schedule_preview")

    assert "self._preview_timer.setSingleShot(True)" in studio
    assert "self._preview_timer.setInterval(120)" in studio
    assert "self._schedule_preview()" in slider
    assert "self._apply_preview()" not in slider
    assert "self._preview_timer.start()" in schedule


def test_reduced_motion_control_is_visible_and_owns_animation_behavior() -> None:
    studio = _source("ankigarden/ui/garden_studio.py")
    assert "self.motion_row = ToggleSettingRow(" in studio
    assert "REDUCED_MOTION_LABEL" in studio
    assert "REDUCED_MOTION_DESCRIPTION" in studio
    assert "controls_layout.addWidget(self.motion_row)" in studio
    assert "self.motion_row.hide()" not in studio


def test_settings_preview_and_actions_have_clear_responsive_regions() -> None:
    studio = _source("ankigarden/ui/garden_studio.py")
    dashboard = _source("ankigarden/ui/dashboard.py")
    settings = dashboard.split("class GardenSettingsDialog", 1)[1].split(
        "class MemoryTimeline", 1
    )[0]

    assert 'self.preview_panel.setProperty("previewPanel", True)' in studio
    assert 'preview_title = QLabel("Home preview")' in studio
    assert 'self.home_preview = HomeGardenPreview(self.scene)' in studio
    assert "preview_layout.addWidget(self.home_preview)" in studio
    assert "self.root_layout.addWidget(self.preview_panel, 1)" in studio
    assert "self.controls.setMaximumWidth(16777215 if compact else 380)" in studio
    assert "self.advanced_panel.setSizePolicy(" in studio
    assert "self.advanced_actions_layout.setAlignment(Qt.AlignmentFlag.AlignTop)" in studio
    assert "controls_layout.setAlignment(Qt.AlignmentFlag.AlignTop)" in studio
    assert "controls_layout.addStretch(1)" not in studio
    assert "self.root_layout.setAlignment(" in studio
    assert "self.controls_scroll," in studio
    assert "def _finish_advanced_layout_update(" in studio
    assert "parent.ensureWidgetVisible(target, 12, 12)" in studio
    toggle_row = studio.split("class ToggleSettingRow", 1)[1].split(
        "class HomeGardenPreview", 1
    )[0]
    assert "QSizePolicy.Policy.Maximum" in toggle_row
    assert "self.footer_layout.addWidget(self.save_status, 1)" in settings
    assert "def _apply_settings_footer_layout" in settings
    assert "self.behavior.advanced_actions_layout.addWidget(self.restore_defaults)" in settings
    assert "self.settings_footer_grid.addWidget(self.cancel_settings, 0, 0)" in settings


def test_dense_detail_surfaces_do_not_repeat_the_same_growth_totals() -> None:
    dashboard = _source("ankigarden/ui/dashboard.py")
    plant_card = dashboard.split("class PlantInfoCard", 1)[1].split(
        "class GardenStatsStrip", 1
    )[0]
    refresh = _method_source("ankigarden/ui/dashboard.py", "GardenDashboard", "refresh_all")
    fertilizer = _method_source(
        "ankigarden/ui/dashboard.py", "GardenDashboard", "_open_fertilizer_menu"
    )

    assert plant_card.count(
        'value_text=f"{stage_points:,} / {stage_goal:,} Growth"'
    ) == 1
    assert "self.growth_summary.setText(" in plant_card
    assert ".replace('card answer', 'eligible answer')" not in plant_card
    assert "_card_answer_count(reviews_remaining)" in plant_card
    assert "self.growth_remaining.setText(" not in plant_card
    assert plant_card.count("self.growth_remaining.hide()") == 2
    assert 'f"{remaining:,} Growth remaining. "' in plant_card
    assert "% to {next_stage}" not in plant_card
    overview = _method_source(
        "ankigarden/ui/dashboard.py", "GardenDashboard", "_refresh_progress_overview"
    )
    assert '("Growth", f"{int(stats.growth_earned):,}")' in overview
    assert "total Growth · {completed_events}" not in refresh
    assert 'title = QLabel(f"Fertilize {plant.name}")' in fertilizer
    assert 'dialog.setWindowTitle(f"Fertilize {plant.name}")' in fertilizer
    assert 'card.setProperty("fertilizerCard", True)' in fertilizer
    assert 'duration = f"{hours} hour" if hours == 1 else f"{hours} hours"' in fertilizer
    assert '"Active fertilizer · None"' in fertilizer
    assert "_fertilizer_action_label(" in fertilizer
    assert '_affordability_status(spec.price, balance_value)' in fertilizer


def test_move_guidance_uses_only_the_scene_popup_after_commit() -> None:
    build = _method_source("ankigarden/ui/dashboard.py", "GardenDashboard", "_build_ui")
    begin_move = _method_source("ankigarden/ui/dashboard.py", "GardenDashboard", "_begin_move")
    place = _method_source("ankigarden/ui/dashboard.py", "GardenDashboard", "_place_plant")

    assert "self.rearrange_bar = RearrangeBar(self.scene)" in build
    assert "placement_row" not in build
    assert "self.placement_note" not in build
    assert "self.undo_move_btn" not in build
    assert "self.toast_region = ToastRegion(self.scene)" in build
    assert build.index("h_layout.addWidget(self.feedback_panel)") < build.index(
        "h_layout.addWidget(self.scene, 1)"
    )
    assert "self.scene.setFocus()" in begin_move
    assert "QTimer.singleShot(0, self._position_scene_overlays)" in begin_move
    assert 'action_text="Undo Move"' in place
    assert "self.scene.setFocus()" in place


def test_compact_identity_copy_uses_middle_dots_but_runtime_notices_are_normalized() -> None:
    dashboard = _source("ankigarden/ui/dashboard.py")
    studio = _source("ankigarden/ui/garden_studio.py")
    assert " · " in dashboard
    assert " · " in studio
    assert "chr(0xB7)" in dashboard
    assert "_learner_text(event.message)" in dashboard
    scope = {"Any": object}
    exec(_function_source("ankigarden/ui/dashboard.py", "_learner_text"), scope)
    separator = chr(0xB7)
    for legacy_message in (
        f"Milestone reached {separator} +10 Garden Coins",
        f"Milestone reached{separator}+10 Garden Coins",
        f"Milestone reached  {separator}  +10 Garden Coins",
    ):
        assert scope["_learner_text"](legacy_message) == "Milestone reached\n+10 Garden Coins"
    assert scope["_learner_text"](
        f"One{separator}{separator}Two"
    ) == "One\nTwo"


def test_progress_rows_use_text_and_state_borders_without_an_emoji_column() -> None:
    dashboard = _source("ankigarden/ui/dashboard.py")
    progress = dashboard.split("class ProgressRow", 1)[1].split("class ProgressList", 1)[0]
    overview = _method_source(
        "ankigarden/ui/dashboard.py", "GardenDashboard", "_refresh_progress_overview"
    )

    assert "self.marker" not in progress
    assert "achievementState" in progress
    assert "icons =" not in progress
    assert "progress_state = daily_progress_display(" in overview
    assert "reward_complete=bool(stats.completed_due_cards)" in overview
    assert "reviewed_today=int(stats.reviewed)" in overview
    assert "custom_study_supported=False" in overview
    assert "DailyProgressState.IN_PROGRESS" in overview
    assert "DailyProgressState.COMPLETE" in overview
    assert "DailyProgressState.NO_DUE" in overview
    assert '"Finish today’s due cards"' in overview
    assert 'reward_text = f"Earned automatically: {progress_state.reward_outcome}"' in overview
    assert '"No Daily Progress reward action is available."' not in overview
    assert "daily_layout.addWidget(explanation)" in overview
    assert 'progress_state.action_enabled and progress_state.action_kind == "review"' in overview
    assert 'QPushButton(progress_state.action_label or "Continue studying")' in overview
    assert 'daily_explanation = due_error or "Refresh after Anki finishes loading the scheduler."' in overview
    assert "due_available" in overview


def test_settings_fine_tune_controls_share_one_visible_control_style() -> None:
    studio = _source("ankigarden/ui/garden_studio.py")
    theme = _source("ankigarden/ui/theme.py")

    assert "tool_button_stylesheet()" in studio
    for selector in (
        "QToolButton {{",
        "QToolButton:checked {{",
    ):
        assert selector in theme
    for selector in (
        "QComboBox {{",
        "QSlider::groove:horizontal {{",
        "QSlider::handle:horizontal {{",
        "QCheckBox::indicator {{",
        "QCheckBox::indicator:checked {{",
    ):
        assert selector in studio
    assert 'self.anim_value.setProperty("settingValue", True)' in studio
    assert 'self.particle_value.setProperty("settingValue", True)' in studio
    for control in (
        "self.asset_quality_combo",
        "self.anim_slider",
        "self.particle_slider",
        "self.show_home_widget",
        "self.show_progress_notifications",
    ):
        assert f"_describe_control(\n            {control}," in studio
    assert "Performance favors speed" in studio
    assert "Ultra uses the most detailed artwork" in studio


def test_reviewer_reward_notices_default_on_across_settings_and_runtime() -> None:
    dashboard = _source("ankigarden/ui/dashboard.py")
    studio = _source("ankigarden/ui/garden_studio.py")
    reviewer = _source("ankigarden/hooks/reviewer.py")
    restore_defaults = _method_source(
        "ankigarden/ui/dashboard.py", "GardenSettingsDialog", "_restore_defaults"
    )

    assert "progress notifications on" in restore_defaults
    assert 'DEFAULT_CONFIG["show_progress_notifications"]' in restore_defaults
    assert 'DEFAULT_CONFIG["show_progress_notifications"]' in studio
    assert 'DEFAULT_CONFIG["show_progress_notifications"]' in reviewer
    assert "show_progress_notifications" in dashboard


def test_troubleshooting_copy_reports_visible_keyboard_feedback() -> None:
    dashboard = _source("ankigarden/ui/dashboard.py")
    settings = dashboard.split("class GardenSettingsDialog", 1)[1].split(
        "class MemoryTimeline", 1
    )[0]
    copy_report = _method_source(
        "ankigarden/ui/dashboard.py", "GardenSettingsDialog", "_copy_debug_report"
    )
    refresh_report = _method_source(
        "ankigarden/ui/dashboard.py", "GardenSettingsDialog", "_refresh_debug_report"
    )

    assert "copy_debug.clicked.connect(self._copy_debug_report)" in settings
    assert "self.troubleshooting_status.setFocusPolicy(Qt.FocusPolicy.StrongFocus)" in settings
    assert 'self.diagnostics_checked.setText("Report copied to clipboard")' in copy_report
    assert "self.diagnostics_card.setFocus()" in copy_report
    assert 'status = "Garden display may be incomplete"' in refresh_report
    assert 'self.diagnostics_card.setProperty("diagnosticState", "warning")' in refresh_report
    assert 'status = "No display issues detected"' in refresh_report


def test_dashboard_count_copy_is_grammatical_at_one_and_many() -> None:
    scope: dict[str, object] = {}
    exec(_function_source("ankigarden/ui/dashboard.py", "_plant_count"), scope)
    exec(_function_source("ankigarden/ui/dashboard.py", "_card_answer_count"), scope)
    exec(_function_source("ankigarden/ui/dashboard.py", "_minute_count"), scope)

    assert scope["_plant_count"](1) == "1 plant"
    assert scope["_plant_count"](2) == "2 plants"
    assert scope["_card_answer_count"](1) == "1 Anki card answer"
    assert scope["_card_answer_count"](2) == "2 Anki card answers"
    assert scope["_minute_count"](1) == "1 minute"
    assert scope["_minute_count"](2) == "2 minutes"

    dashboard = _source("ankigarden/ui/dashboard.py")
    assert dashboard.count("_minute_count(minutes)") == 2
    nursery_refresh = _method_source(
        "ankigarden/ui/dashboard.py", "NurseryDialog", "refresh"
    )
    collection_refresh = _method_source(
        "ankigarden/ui/dashboard.py", "GardenDashboard", "_refresh_collection_list"
    )
    catchup = _method_source(
        "ankigarden/ui/dashboard.py", "GardenDashboard", "show_same_day_catchup_feedback"
    )
    assert "owned_count + available_count" in nursery_refresh
    assert "'plant' if max(owned_count, owned_count + available_count) == 1 else 'plants'" in nursery_refresh
    assert "self.intro.setAccessibleDescription(intro_text)" in nursery_refresh
    assert 'f"{discovered} of {len(species_catalog)} species discovered"' in collection_refresh
    assert '"Undiscovered species"' in collection_refresh
    assert "_card_answer_count(review_count)" in catchup
    assert "_card_answer_count(reviews_remaining)" in dashboard


def test_nursery_and_fertilizer_show_affordability_before_activation() -> None:
    scope: dict[str, object] = {}
    exec(_function_source("ankigarden/ui/dashboard.py", "_affordability_status"), scope)
    exec(_function_source("ankigarden/ui/dashboard.py", "_compact_affordability_status"), scope)
    exec(_function_source("ankigarden/ui/dashboard.py", "_fertilizer_action_label"), scope)
    affordability = scope["_affordability_status"]
    compact_affordability = scope["_compact_affordability_status"]
    fertilizer_action = scope["_fertilizer_action_label"]

    assert affordability(25, 25) == (True, "Affordable now.")
    assert affordability(25, 24) == (False, "Need 1 more Garden Coin.")
    assert affordability(150, 25) == (False, "Need 125 more Garden Coins.")
    assert compact_affordability(25, 25, ready_text="Ready to unlock") == "Ready to unlock"
    assert compact_affordability(150, 25, ready_text="Ready to unlock") == "125 more needed"
    assert fertilizer_action("", "basic", "Basic Fertilizer") == "Use Basic Fertilizer"
    assert fertilizer_action("basic", "basic", "Basic Fertilizer") == "Extend Basic Fertilizer"
    assert fertilizer_action("basic", "quality", "Quality Fertilizer") == "Replace with Quality Fertilizer"

    nursery = _source("ankigarden/ui/dashboard.py").split(
        "class NurseryDialog", 1
    )[1].split("class PlantInfoCard", 1)[0]
    available_card = _method_source(
        "ankigarden/ui/dashboard.py", "NurseryDialog", "_available_card"
    )
    nursery_refresh = _method_source(
        "ankigarden/ui/dashboard.py", "NurseryDialog", "refresh"
    )
    space_card = _method_source(
        "ankigarden/ui/dashboard.py", "NurseryDialog", "_space_card"
    )
    fertilizer = _method_source(
        "ankigarden/ui/dashboard.py", "GardenDashboard", "_open_fertilizer_menu"
    )

    assert "_affordability_status(price, balance)" in available_card
    assert "set_control_enabled(" in available_card
    assert "affordable," in available_card
    assert "is not affordable yet" in available_card
    assert "card.setFocusPolicy(Qt.FocusPolicy.StrongFocus)" in available_card
    assert "apply_explanatory_tooltip(" in available_card
    assert "self.bed_affordability" in nursery
    assert "state.currency_balance >= price" in space_card
    assert 'self.bed_button = QPushButton("Unlock")' in space_card
    assert "affordable and not self._bed_purchase_pending" in space_card
    assert "more needed" in space_card
    assert "current_status" in fertilizer
    assert "self._fertilizer_text(plant)" in fertilizer
    assert "set_control_enabled(" in fertilizer
    assert "affordable and active" in fertilizer
    assert "Nurture this plant before purchasing Fertilizer." in fertilizer
    assert 'action_label = "Apply"' in fertilizer
    assert 'action_label = "Replace"' in fertilizer
    assert 'f"{semantic_action} for {spec.price:,} Garden Coins"' in fertilizer
    assert "shortfall_label = QLabel(" in fertilizer
    assert 'f"Need {shortfall:,} more {' in fertilizer
    assert 'shortfall_label.setProperty("fertilizerShortfall", True)' in fertilizer
    assert 'action_label = f"Need ' not in fertilizer
    assert "_fertilizer_action_label(" in fertilizer


def test_purchase_decisions_keep_one_visible_cost_and_concise_actions() -> None:
    available = _method_source(
        "ankigarden/ui/dashboard.py", "NurseryDialog", "_available_card"
    )
    starter = _method_source(
        "ankigarden/ui/dashboard.py", "NurseryDialog", "_starter_card"
    )
    supplement = _method_source(
        "ankigarden/ui/dashboard.py", "NurseryDialog", "_supplement_card"
    )
    charge = _method_source(
        "ankigarden/ui/dashboard.py", "NurseryDialog", "_growth_charge_card"
    )
    environment = _method_source(
        "ankigarden/ui/dashboard.py", "NurseryDialog", "_environment_shop_card"
    )
    spaces = _method_source(
        "ankigarden/ui/dashboard.py", "NurseryDialog", "_space_progression"
    )
    replacement = _class_source(
        "ankigarden/ui/dashboard.py", "FertilizerReplacementDialog"
    )

    assert 'QPushButton("Buy")' in available
    assert 'QPushButton("Choose")' in starter
    assert 'QPushButton("Apply")' in supplement
    assert 'QPushButton("Buy")' in charge
    assert '"Customize" if owned else "Buy"' in environment
    assert 'QPushButton("Unlock")' in spaces
    assert 'QPushButton("Replace")' in replacement
    assert "DialogSizeClass.COMPARISON" in replacement
    assert "self.register_scroll_region(self.content_scroll)" in replacement
    assert "self.register_pinned_footer(self.action_footer)" in replacement
    for source in (available, supplement, charge, environment, spaces, replacement):
        assert "Buy for" not in source
        assert "Apply for" not in source
        assert "Replace for" not in source

    assert "cost_label(price)" in available
    assert "COST_FREE" in starter
    assert "cost_label(spec.price)" in supplement
    assert "cost_label(spec.price)" in charge
    assert "cost_label(item.price)" in environment
    assert "price_label = QLabel(cost_label(price))" in spaces
    assert 'summary("New", new_name, new_effect, cost_label(cost))' in replacement
    for source in (available, supplement, charge, environment, spaces, replacement):
        assert "Garden Coins" in source, "accessible purchase copy must retain the full unit"


def test_progress_surfaces_show_one_growth_value_plus_a_card_answer_forecast() -> None:
    growth = _method_source(
        "ankigarden/ui/dashboard.py", "GardenDetailsDialog", "_refresh_growth"
    )
    story = _method_source(
        "ankigarden/ui/dashboard.py", "PlantStoryDialog", "refresh"
    )

    assert 'progress.set_progress(\n                "Growth",' in growth
    assert 'value_text=f"{display.stage_points:,} / {display.stage_goal:,} Growth"' in growth
    assert 'f"About {answers:,} Anki card' in growth
    assert 'f"{display.points_remaining:,} Growth remaining' not in growth
    assert 'self.stage_progress.set_progress(\n                "Growth",' in story
    assert 'f"About {answers:,} Anki card' in story


def test_compact_dashboard_keeps_words_for_progress_and_anki_streak() -> None:
    responsive = _method_source(
        "ankigarden/ui/dashboard.py", "GardenDashboard", "_apply_responsive_layout"
    )
    compact_stats = _method_source(
        "ankigarden/ui/dashboard.py", "GardenStatsStrip", "set_compact"
    )

    assert 'self.progress_btn.setText("Garden Progress")' in responsive
    assert '"Progress" if smallest else "Garden Progress"' not in responsive
    assert 'self.progress_btn.setText("↗"' not in responsive
    assert 'self.streak_label.setText("ANKI STREAK")' in compact_stats
    assert "self.streak_heading.removeWidget(self.streak_bonus)" in compact_stats
    assert "self.streak_value_row.insertWidget(" in compact_stats


def test_diagnostics_has_one_copy_action_and_one_details_toggle() -> None:
    settings = _class_source(
        "ankigarden/ui/dashboard.py", "GardenSettingsDialog"
    )
    toggle = _method_source(
        "ankigarden/ui/dashboard.py", "GardenSettingsDialog", "_toggle_debug_report"
    )

    assert settings.count('QPushButton("Copy report")') == 1
    assert "Copy details" not in settings
    assert 'QPushButton("View technical details")' in settings
    assert "self.debug_report.setVisible(bool(expanded))" in toggle


def test_visible_navigation_uses_garden_coins_and_nurture_language() -> None:
    dashboard = _source("ankigarden/ui/dashboard.py")
    home = _source("ankigarden/ui/home_widget.py")
    terminology = _source("ankigarden/terminology.py")
    sources = "\n".join((dashboard, home, _source("ankigarden/ui/scene.py"), terminology))

    assert "Garden Coins" in dashboard and "Garden Coins" in home and "Garden Coins" in terminology
    assert "Nurture" in dashboard and "nurture" in terminology.lower()
    assert "Make active" not in sources
    assert "Unlock species" not in sources
    assert "Move here" not in dashboard


def test_shared_ui_snapshot_and_post_commit_event_are_the_refresh_boundary() -> None:
    state_module = _source("ankigarden/ui/state.py")
    dashboard = _source("ankigarden/ui/dashboard.py")
    addon = _source("ankigarden/addon.py")
    reviewer = _source("ankigarden/hooks/reviewer.py")

    assert "@dataclass(frozen=True)\nclass GardenUiSnapshot" in state_module
    assert "def select_garden_ui(engine: Any, storage: Any)" in state_module
    assert "class GardenUiCoordinator" in state_module
    assert "snapshot = select_garden_ui(self.engine, self.storage)" in dashboard
    assert "self.state_events.notify(context)" in dashboard
    assert "self.state_events.stateChanged.connect(self._on_state_changed)" in dashboard
    assert "self.state_events = GardenUiCoordinator(mw)" in addon
    assert 'self.state_changed("Card answer counted")' in reviewer


def test_progress_rebuild_detaches_old_rows_before_nested_dialog_paints() -> None:
    clear = _method_source(
        "ankigarden/ui/dashboard.py", "ProgressList", "clear"
    )

    assert clear.index("widget.hide()") < clear.index("widget.setParent(None)")
    assert clear.index("widget.setParent(None)") < clear.index("widget.deleteLater()")
    assert "self.container.updateGeometry()" in clear


def test_capture_harness_requires_painted_surfaces_and_exact_dialog_instances() -> None:
    capture = _source("ankigarden/capture_ui_faces.py")
    capture_now = _method_source(
        "ankigarden/capture_ui_faces.py", "_UiFaceCaptureRunner", "_capture_now"
    )
    home_ready = _method_source(
        "ankigarden/capture_ui_faces.py", "_UiFaceCaptureRunner", "_wait_for_home_surface"
    )

    assert "QApplication.activeWindow" not in capture_now
    assert "Expected capture widget was not provided" in capture_now
    assert "widget.isVisible()" in capture_now
    assert "#ag-home-root" in home_ready
    assert "root.dataset.state" in home_ready
    assert "img.complete" in home_ready
    assert 'getattr(dashboard, "fertilizer_dialog", None)' in capture
    assert 'getattr(dashboard, "story_dialog", None)' in capture
    assert 'getattr(dashboard, "progress_dialog", None)' in capture
    assert 'dashboard is not None and bool(dashboard.isVisible())' in capture
    assert "keep_open(plant_id)" in capture
    prepare_state = _method_source(
        "ankigarden/capture_ui_faces.py", "_UiFaceCaptureRunner", "_prepare_capture_state"
    )
    assert "reset()" in prepare_state
    assert "QTimer.singleShot(800, self._next_step)" in prepare_state
    deck_capture = _method_source(
        "ankigarden/capture_ui_faces.py", "_UiFaceCaptureRunner", "_capture_deck_browser"
    )
    assert "QTimer.singleShot(" in deck_capture
    assert "capture_delay_ms=650" in deck_capture
    assert 'self._switch_surface("overview")' in deck_capture
    assert 'self._switch_surface("deckBrowser")' in deck_capture
    full_garden = _method_source(
        "ankigarden/capture_ui_faces.py", "_UiFaceCaptureRunner", "_capture_full_garden"
    )
    assert "close_callback" not in full_garden
    assert "and not self._text_layout_warnings" in capture


def test_progress_reward_badges_and_fertilizer_countdown_are_runtime_safe() -> None:
    overview = _method_source(
        "ankigarden/ui/dashboard.py", "GardenDashboard", "_refresh_progress_overview"
    )
    fertilizer = _method_source(
        "ankigarden/ui/dashboard.py", "GardenDashboard", "_open_fertilizer_menu"
    )
    fertilizer_text = _method_source(
        "ankigarden/ui/dashboard.py", "GardenDashboard", "_fertilizer_text"
    )

    assert '"detailPositive" if int(transaction.delta) >= 0 else "detailNegative",\n                True,' in overview
    assert "countdown_timer.setInterval(1_000)" in fertilizer
    assert "countdown_timer.timeout.connect(refresh_fertilizer_countdown)" in fertilizer
    assert '"Less than 1 minute remaining"' in fertilizer_text
