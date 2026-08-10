import ast
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
    assert 'self._section_label("Your plants")' in nursery
    assert 'self._section_label("Available now")' in nursery
    assert 'self._plant_artwork(species, "seed")' in nursery
    assert "starter_selection_complete" in nursery


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

    assert 'handlers = {"garden.nursery.open": self._open_nursery}' in dashboard
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


def test_garden_chrome_is_three_metrics_plus_a_collapsed_progress_drawer() -> None:
    dashboard = _source("ankigarden/ui/dashboard.py")
    progress_toggle = _method_source(
        "ankigarden/ui/dashboard.py", "GardenDashboard", "_set_progress_expanded"
    )

    assert '("growth", "Plant Growth", GROWTH_EXPLANATION)' in dashboard
    assert '("streak", "Anki streak", ANKI_STREAK_EXPLANATION)' in dashboard
    assert '("currency", "Garden Coins", GARDEN_CURRENCY_EXPLANATION)' in dashboard
    assert '("reviews", "Card answers"' not in dashboard
    assert 'self.progress_toggle = QPushButton("Progress")' in dashboard
    assert "self.progress_toggle.setCheckable(True)" in dashboard
    assert "self.details_tabs.hide()" in dashboard
    assert "self.details_tabs.setVisible(bool(expanded))" in progress_toggle
    assert "self.page_scroll.ensureWidgetVisible(self.details_tabs, 12, 12)" in progress_toggle
    assert '"Hide progress" if expanded else "Progress"' in progress_toggle
    assert '"Hide garden progress" if expanded else "Show garden progress"' in progress_toggle
    assert "self.milestone_card.hide()" in dashboard
    assert "self.streak_ticks" not in dashboard


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
    assert 'self.nurture.setText("Nurturing" if active else "Nurture")' in card
    assert 'self.fertilize.setText("Replace Fertilizer" if fertilizer_growth else "Fertilize")' in card
    assert "self.action_hint.setText(action_hint)" in card
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
    assert "This story is just beginning" in dashboard
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
    assert 'QPushButton("Save settings")' in settings
    assert 'QPushButton("Cancel")' in settings
    assert 'QPushButton("Restore defaults")' in settings
    assert "self.config.update(payload)" in save
    assert 'self.save_status.setText("Saved")' in save
    assert "self._save_status_generation += 1" in save
    assert "generation = self._save_status_generation" in save
    assert "QTimer.singleShot(2400, lambda: self._hide_saved_status(generation))" in save
    assert "generation != self._save_status_generation" in hide_saved
    assert 'self.save_status.text() == "Saved"' in hide_saved
    assert "self.save_status.hide()" in hide_saved
    assert 'tabs.addTab(advanced, UI_TEXT["tab_advanced"])' in settings


def test_settings_preview_and_actions_have_clear_responsive_regions() -> None:
    studio = _source("ankigarden/ui/garden_studio.py")
    dashboard = _source("ankigarden/ui/dashboard.py")
    settings = dashboard.split("class GardenSettingsDialog", 1)[1].split(
        "class MemoryTimeline", 1
    )[0]

    assert 'self.preview_panel.setProperty("previewPanel", True)' in studio
    assert 'preview_title = QLabel("Your garden preview")' in studio
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

    assert "Growth to {next_stage}\\n" in plant_card
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
    assert '"Finish today’s available review and learning cards."' in dashboard
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
    assert "_plant_count(owned_count)" in nursery_refresh
    assert "self.intro.setAccessibleDescription(intro_text)" in nursery_refresh
    assert "_plant_count(len(state.plants))" in collection_refresh
    assert "_card_answer_count(review_count)" in catchup
    assert "_card_answer_count(reviews_remaining)" in dashboard


def test_nursery_and_fertilizer_show_affordability_before_activation() -> None:
    scope: dict[str, object] = {}
    exec(_function_source("ankigarden/ui/dashboard.py", "_affordability_status"), scope)
    exec(_function_source("ankigarden/ui/dashboard.py", "_fertilizer_action_label"), scope)
    affordability = scope["_affordability_status"]
    fertilizer_action = scope["_fertilizer_action_label"]

    assert affordability(25, 25) == (True, "Affordable now.")
    assert affordability(25, 24) == (False, "Need 1 more Garden Coin.")
    assert affordability(150, 25) == (False, "Need 125 more Garden Coins.")
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
    fertilizer = _method_source(
        "ankigarden/ui/dashboard.py", "GardenDashboard", "_open_fertilizer_menu"
    )

    assert "_affordability_status(price, balance)" in available_card
    assert "action.setEnabled(affordable)" in available_card
    assert "card.setFocusPolicy(Qt.FocusPolicy.StrongFocus)" in available_card
    assert "apply_explanatory_tooltip(" in available_card
    assert "self.bed_affordability" in nursery
    assert "bed_status" in nursery_refresh
    assert "and bed_affordable" in nursery_refresh
    assert "current_status" in fertilizer
    assert "self._fertilizer_text(plant)" in fertilizer
    assert "choose.setEnabled(affordable)" in fertilizer
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
