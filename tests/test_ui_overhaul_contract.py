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
    assert "self._plant_stage_carousel(species)" in nursery
    assert 'self._plant_artwork(species, "seed", 132)' in nursery
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
    assert '"seed": 0.46' in helper
    assert '"rare": 0.86' in helper
    assert "Qt.AlignmentFlag.AlignCenter" in helper
    assert "Qt.TransformationMode.SmoothTransformation" in helper
    available_card = _method_source(
        "ankigarden/ui/dashboard.py", "NurseryDialog", "_available_card"
    )
    assert "title = QLabel(species_name)" in available_card
    assert 'ownership = QLabel("NOT COLLECTED")' in available_card
    assert '"Free starter"' in available_card
    assert '"Starts as Seed"' not in available_card
    assert "_compact_affordability_status(" in available_card


def test_nursery_stage_carousel_uses_clear_bounded_navigation() -> None:
    carousel = _method_source(
        "ankigarden/ui/dashboard.py", "NurseryDialog", "_plant_stage_carousel"
    )

    assert 'QPushButton("← Previous")' in carousel
    assert 'QPushButton("Next →")' in carousel
    assert 'stage_count.setText(f"Stage {index + 1} of {len(GROWTH_STAGES)}")' in carousel
    assert "previous.setEnabled(index > 0)" in carousel
    assert "next_button.setEnabled(index < len(GROWTH_STAGES) - 1)" in carousel
    assert "state[\"index\"] = max(" in carousel
    assert "% len(GROWTH_STAGES)" not in carousel
    assert "preview.setToolTip(replacement.toolTip())" in carousel
    assert "preview.setAccessibleDescription(replacement.accessibleDescription())" in carousel
    assert "layout = QHBoxLayout(widget)" in carousel
    assert "stage_details = QVBoxLayout()" in carousel
    assert "widget.setMaximumWidth(330)" in carousel
    assert "button.setFixedSize(84, 32)" in carousel


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
    assert "button.setFixedSize(84, 32)" in nursery
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
    assert "identity = QHBoxLayout()" in available_card
    assert "footer = QHBoxLayout()" in available_card
    assert "Qt.AlignmentFlag.AlignHCenter" in available_card
    assert "available_grid = QGridLayout(available_grid_host)" in refresh
    assert "index // 2" in refresh
    assert "index % 2" in refresh
    assert "available_grid.setColumnStretch(0, 1)" in refresh
    assert "available_grid.setColumnStretch(1, 1)" in refresh


def test_nursery_is_full_garden_only_and_first_open_is_automatic() -> None:
    dashboard = _source("ankigarden/ui/dashboard.py")
    home = _source("ankigarden/ui/home_widget.py")
    scene = _source("ankigarden/ui/scene.py")
    prompt_starter = _method_source(
        "ankigarden/ui/dashboard.py", "GardenDashboard", "prompt_starter_if_needed"
    )
    open_dashboard = _method_source(
        "ankigarden/addon.py", "AnkiGardenApp", "_open_dashboard_when_ready"
    )
    activate_landmark = _method_source(
        "ankigarden/ui/scene.py", "GardenSceneWidget", "_activate_landmark"
    )

    assert '"garden.nursery.open": self._open_nursery' in dashboard
    assert '"garden.progress.open": self._open_progress' in dashboard
    assert "self._starter_prompt_scheduled = False" in dashboard
    assert "not self._starter_prompt_scheduled" in prompt_starter
    assert 'getattr(self.storage.state, "starter_selection_complete", True)' in prompt_starter
    assert prompt_starter.count("QTimer.singleShot(0, self._open_nursery)") == 1
    assert prompt_starter.index("self._starter_prompt_scheduled = True") < prompt_starter.index(
        "QTimer.singleShot(0, self._open_nursery)"
    )
    assert "if opening_settings:" in open_dashboard
    assert "prompt_starter_if_needed" in open_dashboard
    assert open_dashboard.index("if opening_settings:") < open_dashboard.index(
        "prompt_starter_if_needed"
    )
    assert 'self.onboarding_action = QPushButton("Show me")' in dashboard
    assert 'self.scene.focus_landmark("garden.nursery.open")' in dashboard
    assert "garden.nursery.open" not in home
    assert "not self.interactive" in activate_landmark
    assert "self._interaction.placing" in activate_landmark
    assert "normalized_id not in self._landmark_actions" in activate_landmark
    assert "self.landmarkActivated.emit(normalized_id)" in activate_landmark
    assert "self.scene = GardenSceneWidget()" in dashboard
    assert "GardenSceneWidget(interactive=False)" in _source("ankigarden/ui/garden_studio.py")


def test_garden_chrome_uses_one_tabbed_details_dialog_plus_progress_window() -> None:
    dashboard = _source("ankigarden/ui/dashboard.py")
    capture = _source("ankigarden/capture_ui_faces.py")
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
    assert 'self.progress_btn = QPushButton("Progress")' in dashboard
    assert "class GardenProgressDialog(QDialog):" in dashboard
    assert "class GardenDetailsDialog(QDialog):" in dashboard
    assert "class MetricDetailDialog(QDialog):" not in dashboard
    assert '("growth", "Plant Growth")' in dashboard
    assert '("streak", "Anki Streak")' in dashboard
    assert '("currency", "Garden Coins")' in dashboard
    assert "self.progress_dialog = GardenProgressDialog(self, self.details_tabs)" in dashboard
    assert "self.details_dialog = GardenDetailsDialog(" in dashboard
    assert "self.metric_dialogs" not in dashboard
    assert "self.progress_dialog.show()" in open_progress
    assert "self.progress_dialog.raise_()" in open_progress
    assert "self.garden_stats_bar.metricActivated.connect(self._open_metric_details)" in dashboard
    assert "self.details_dialog.open_metric(key)" in open_details
    assert "self.details_dialog.isVisible()" in open_nursery
    assert "self.details_dialog.close()" in open_nursery
    assert "WA_TransparentForMouseEvents" in dashboard
    assert "self.progress_dialog.finished.connect(self._restore_progress_focus)" in dashboard
    assert "self.details_dialog.finished.connect(self._restore_metric_focus)" in dashboard
    assert "self._metric_return_focus = self.garden_stats_bar.cells.get(key)" in open_details
    assert "self.details_tabs.hide()" not in dashboard
    assert "self.milestone_card.hide()" in dashboard
    assert "self.streak_ticks" not in dashboard
    assert 'getattr(dashboard, "details_dialog", None)' in capture
    assert "metric_dialogs" not in capture
    assert "dashboard.details_dialog.tabs.currentIndex() == expected_index" in capture


def test_garden_details_shell_is_stable_centered_and_keyboard_native() -> None:
    dashboard = _source("ankigarden/ui/dashboard.py")
    details = dashboard.split("class GardenDetailsDialog", 1)[1].split(
        "class GardenDashboard", 1
    )[0]

    assert 'self.setWindowTitle("Garden Details")' in details
    assert "self.setModal(False)" in details
    assert "self.setWindowModality(Qt.WindowModality.NonModal)" in details
    assert "self.setMinimumSize(680, 500)" in details
    assert "self.setMaximumWidth(780)" in details
    assert "self.resize(740, min(570, maximum_height))" in details
    assert "self.tabs = QTabWidget()" in details
    assert 'self.tabs.setAccessibleName("Garden detail sections")' in details
    assert "parent.mapToGlobal(parent.rect().center())" in details
    assert "frame.moveCenter(center)" in details
    assert "self.show()" in details
    assert "self.raise_()" in details
    assert "self.activateWindow()" in details
    assert "self.tabs.tabBar().setFocus()" in details
    assert 'body.setProperty("detailBodyPanel", True)' in details
    assert "widget.hide()" in details
    assert 'self.close_button = QPushButton("Close")' not in details


def test_garden_details_growth_is_nonzero_first_and_uses_engine_stage_sources() -> None:
    growth = _method_source(
        "ankigarden/ui/dashboard.py", "GardenDetailsDialog", "_refresh_growth"
    )

    assert "growth_display(plant.growth_points)" in growth
    assert "GROWTH_STAGES" in growth
    assert "GROWTH_THRESHOLDS[index]" in growth
    assert "display.stage_index" in growth
    assert '"completed" if index < display.stage_index' in growth
    assert '"current" if index == display.stage_index' in growth
    assert "active_rows" in growth and "inactive_rows" in growth
    assert 'self._disclosure(\n                today_layout,\n                "inactive modifiers"' in growth
    assert "recorded != int(stats.growth_earned)" in growth
    assert 'f"{stats.growth_earned:,}"' in growth
    assert "setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)" in growth
    assert "stage_card.setMinimumWidth(102)" in growth
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
    assert 'if next_tier is None:' in streak
    maximum_branch = streak.split("if next_tier is None:", 1)[1].split("else:", 1)[0]
    assert "QProgressBar" not in maximum_branch
    assert '"All Growth bonus milestones completed"' in maximum_branch
    assert '"How the streak works".lower()' not in dashboard
    assert '"how the streak works"' in streak
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
    stats = dashboard.split("class GardenStatsStrip", 1)[1].split(
        "class RearrangeBar", 1
    )[0]

    assert "cell.setMinimumHeight(132)" in stats
    assert stats.count('QLabel("View details ›")') == 3
    assert "cell.setCursor(Qt.CursorShape.PointingHandCursor)" in stats
    assert "cell.setFocusPolicy(Qt.FocusPolicy.StrongFocus)" in stats
    assert "QPushButton[gardenStatCell='true']:hover" in dashboard
    assert "QPushButton[gardenStatCell='true']:pressed" in dashboard
    assert "QPushButton[gardenStatCell='true']:focus" in dashboard
    assert 'self.currency_support = QLabel("Spend in the Nursery")' in stats


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
    assert "actions.addWidget(self.nurture, 0, 0, 1, 2)" in card
    assert "actions.addWidget(self.fertilize, 1, 0, 1, 2)" in card
    assert "actions.addWidget(self.story, 2, 0)" in card
    assert "actions.addWidget(self.move, 2, 1)" in card
    assert 'self.nurture.setText("Nurturing" if active else "Nurture")' in card
    assert 'self.fertilize.setText("Replace Fertilizer" if fertilizer_growth else "Fertilize")' in card
    assert "self.action_hint.setText(action_hint)" in card
    assert "nurture_reason" in card
    assert "fertilizer_reason" in card
    assert "Nurture this plant before using Fertilizer." in card
    plant_section_style = dashboard.split("QLabel[plantCardSection='true']", 1)[1].split("}", 1)[0]
    assert "font-size:11px" in plant_section_style
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
        'self.placement_note.setText(result)'
    )
    assert "self.engine.restore_placement(self._undo_placement)" in undo
    assert 'self.placement_note.setText("Move undone.")' in undo


def test_story_is_chronological_compact_and_has_an_up_next_card() -> None:
    dashboard = _source("ankigarden/ui/dashboard.py")
    story = dashboard.split("class PlantStoryDialog", 1)[1].split("class NurseryDialog", 1)[0]
    refresh = _method_source("ankigarden/ui/dashboard.py", "PlantStoryDialog", "refresh")

    assert 'self.edit_name_btn = QPushButton("✎")' in story
    assert 'self.edit_name_btn.setAccessibleName("Rename plant")' in story
    assert "self.edit_name_btn.setFixedSize(36, 36)" in story
    assert 'up_next_title = QLabel("Up next")' in story
    assert "memories = chronological_memories(plant.memories)" in refresh
    assert "reverse=True" not in refresh
    assert 'timeline_label = QLabel("Memories")' in dashboard
    assert "New memories will appear as this plant grows." in dashboard
    assert "about {_card_answer_count(answers)} before bonuses" in refresh
    assert "This plant has reached its rare form" in refresh


def test_story_layout_keeps_short_timelines_attached_to_their_heading() -> None:
    dashboard = _source("ankigarden/ui/dashboard.py")
    story = dashboard.split("class PlantStoryDialog", 1)[1].split("class NurseryDialog", 1)[0]
    timeline_refresh = _method_source(
        "ankigarden/ui/dashboard.py", "MemoryTimeline", "set_memories"
    )

    assert "QSizePolicy.Policy.Preferred" in dashboard.split(
        "class MemoryTimeline", 1
    )[1].split("class PlantStoryDialog", 1)[0]
    assert "target_height = max(96, min(200, hint))" in timeline_refresh
    assert "self.layout.addStretch" not in timeline_refresh
    assert 'story_panel.setProperty("storyTimeline", True)' in story
    assert "story_layout.addWidget(self.timeline)" in story
    assert "root.addWidget(self.timeline, 1)" not in story
    assert "identity_text.addLayout(self.rename_row)" in story
    assert "root.addLayout(self.rename_row)" not in story


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
    assert 'theme_title = QLabel("Verdant Twilight")' in theme_card
    assert "self.theme_thumbnail = QLabel()" in theme_card
    assert 'self.theme_thumbnail.setAccessibleName("Verdant Twilight preview")' in theme_card
    assert not any(
        control in theme_card
        for control in ("QComboBox", "QPushButton", "QToolButton", "QCheckBox", "QSlider")
    )
    assert 'background_asset = asset_paths.get("background")' in apply_preview
    assert "self.theme_thumbnail.setPixmap(background_pixmap.scaled(" in apply_preview
    assert 'self.fine_tune_toggle.setText("Fine tune")' in studio
    assert "self.fine_tune_section.hide()" in studio
    assert 'QPushButton("Save changes")' in settings
    assert 'QPushButton("Cancel")' in settings
    assert 'QPushButton("Restore defaults")' in settings
    assert 'QPushButton("Rename garden")' in settings
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
    assert 'tabs.addTab(advanced, UI_TEXT["tab_advanced"])' in settings


def test_hidden_motion_controls_remain_owned_for_settings_preview() -> None:
    studio = _source("ankigarden/ui/garden_studio.py")
    motion_setup = studio.split(
        'motion, motion_form = self._section(', 1
    )[1].split("self.show_home_widget = QCheckBox()", 1)[0]

    assert "motion.setParent(self.controls)" in motion_setup
    assert motion_setup.index("motion.setParent(self.controls)") < motion_setup.index(
        "motion.hide()"
    )


def test_settings_preview_and_actions_have_clear_responsive_regions() -> None:
    studio = _source("ankigarden/ui/garden_studio.py")
    dashboard = _source("ankigarden/ui/dashboard.py")
    settings = dashboard.split("class GardenSettingsDialog", 1)[1].split(
        "class MemoryTimeline", 1
    )[0]

    assert 'self.preview_panel.setProperty("previewPanel", True)' in studio
    assert 'preview_title = QLabel("Preview")' in studio
    assert "look before you save" in studio
    assert "preview_layout.addWidget(self.scene, 1)" in studio
    assert "self.root_layout.addWidget(self.preview_panel, 1)" in studio
    assert "self.controls.setMaximumWidth(16777215 if compact else 360)" in studio
    assert settings.index("behavior_layout.addWidget(self.save_status)") < settings.index(
        "settings_actions = QHBoxLayout()"
    )


def test_dense_detail_surfaces_do_not_repeat_the_same_growth_totals() -> None:
    dashboard = _source("ankigarden/ui/dashboard.py")
    plant_card = dashboard.split("class PlantInfoCard", 1)[1].split(
        "class GardenStatsStrip", 1
    )[0]
    refresh = _method_source("ankigarden/ui/dashboard.py", "GardenDashboard", "refresh_all")
    fertilizer = _method_source(
        "ankigarden/ui/dashboard.py", "GardenDashboard", "_open_fertilizer_menu"
    )

    assert 'self.growth_summary.setText(f"{remaining:,} Growth remaining")' in plant_card
    assert "About {_card_answer_count(reviews_remaining)} before bonuses" in plant_card
    assert "% to {next_stage}" not in plant_card
    assert "{stats.growth_earned:,} Growth today" in refresh
    assert "total Growth · {completed_events}" not in refresh
    assert 'title = QLabel(f"Fertilize {plant.name}")' in fertilizer
    assert 'card.setProperty("fertilizerCard", True)' in fertilizer
    assert 'duration = f"{hours} hour" if hours == 1 else f"{hours} hours"' in fertilizer
    assert '"Current Fertilizer\\nNone active"' in fertilizer
    assert "_fertilizer_action_label(" in fertilizer
    assert '_affordability_status(spec.price, balance_value)' in fertilizer


def test_move_guidance_and_undo_precede_the_full_height_scene() -> None:
    build = _method_source("ankigarden/ui/dashboard.py", "GardenDashboard", "_build_ui")
    begin_move = _method_source("ankigarden/ui/dashboard.py", "GardenDashboard", "_begin_move")
    place = _method_source("ankigarden/ui/dashboard.py", "GardenDashboard", "_place_plant")

    assert build.index("h_layout.addWidget(self.rearrange_bar)") < build.index(
        "h_layout.addWidget(self.scene)"
    )
    assert "feedback_layout.addLayout(placement_row)" in build
    assert build.index("h_layout.addWidget(self.feedback_panel)") < build.index(
        "h_layout.addWidget(self.scene)"
    )
    assert "QTimer.singleShot(0, self._ensure_move_controls_visible)" in begin_move
    assert "QTimer.singleShot(0, self._ensure_move_controls_visible)" in place


def test_dashboard_and_settings_have_no_literal_middle_dot_separators() -> None:
    for relative in ("ankigarden/ui/dashboard.py", "ankigarden/ui/garden_studio.py"):
        source = _source(relative)
        tree = ast.parse(source)
        offenders = [
            (node.lineno, node.value)
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and "·" in node.value
        ]
        assert offenders == []

    dashboard = _source("ankigarden/ui/dashboard.py")
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

    assert "self.marker" not in progress
    assert "achievementState" in progress
    assert "icons =" not in progress
    assert '"Today’s available review and learning cards."' in dashboard
    assert "explanation=(" in dashboard


def test_settings_fine_tune_controls_share_one_visible_control_style() -> None:
    studio = _source("ankigarden/ui/garden_studio.py")

    for selector in (
        "QToolButton {",
        "QToolButton:checked",
        "QComboBox {",
        "QSlider::groove:horizontal",
        "QSlider::handle:horizontal",
        "QCheckBox::indicator",
        "QCheckBox::indicator:checked",
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
    assert 'self.troubleshooting_status.setText("Report copied.")' in copy_report
    assert "self.troubleshooting_status.setFocus()" in copy_report
    assert "Display diagnostics need attention:" in refresh_report
    assert "No display contract or parsing issues are currently recorded." in refresh_report


def test_dashboard_count_copy_is_grammatical_at_one_and_many() -> None:
    scope: dict[str, object] = {}
    exec(_function_source("ankigarden/ui/dashboard.py", "_plant_count"), scope)
    exec(_function_source("ankigarden/ui/dashboard.py", "_card_answer_count"), scope)

    assert scope["_plant_count"](1) == "1 plant"
    assert scope["_plant_count"](2) == "2 plants"
    assert scope["_card_answer_count"](1) == "1 card answer"
    assert scope["_card_answer_count"](2) == "2 card answers"

    dashboard = _source("ankigarden/ui/dashboard.py")
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
    assert "_plant_count(len(state.plants))" in collection_refresh
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
    assert "action.setEnabled(affordable)" in available_card
    assert "card.setFocusPolicy(Qt.FocusPolicy.StrongFocus)" in available_card
    assert "apply_explanatory_tooltip(" in available_card
    assert "self.bed_affordability" in nursery
    assert "state.currency_balance >= price" in space_card
    assert 'self.bed_button = QPushButton("Unlock")' in space_card
    assert "affordable and not self._bed_purchase_pending" in space_card
    assert "more needed" in space_card
    assert "current_status" in fertilizer
    assert "self._fertilizer_text(plant)" in fertilizer
    assert "choose.setEnabled(affordable)" in fertilizer
    assert 'ready_text="Ready to use"' in fertilizer
    assert "_fertilizer_action_label(" in fertilizer


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
