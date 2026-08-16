from __future__ import annotations

import ast
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_PATH = ROOT / "ankigarden/ui/dashboard.py"
STATE_PATH = ROOT / "ankigarden/models/state.py"


def _source() -> str:
    return DASHBOARD_PATH.read_text("utf-8")


def _class_node(class_name: str) -> ast.ClassDef:
    return next(
        node
        for node in ast.parse(_source()).body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )


def _function_node(function_name: str) -> ast.FunctionDef:
    return next(
        node
        for node in ast.parse(_source()).body
        if isinstance(node, ast.FunctionDef) and node.name == function_name
    )


def _method_node(class_name: str, method_name: str) -> ast.FunctionDef:
    class_node = _class_node(class_name)
    return next(
        node
        for node in class_node.body
        if isinstance(node, ast.FunctionDef) and node.name == method_name
    )


def _segment(node: ast.AST) -> str:
    source = _source()
    segment = ast.get_source_segment(source, node)
    assert segment is not None
    return segment


def _compiled_method(
    class_name: str,
    method_name: str,
    namespace: dict[str, Any] | None = None,
) -> Any:
    method = _method_node(class_name, method_name)
    method.decorator_list = []
    module = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
    scope = dict(namespace or {})
    exec(compile(module, str(DASHBOARD_PATH), "exec"), scope)
    return scope[method_name]


def _call_path(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_path(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _calls(node: ast.AST, path: str) -> list[ast.Call]:
    return [
        child
        for child in ast.walk(node)
        if isinstance(child, ast.Call) and _call_path(child.func) == path
    ]


def _strings(node: ast.AST) -> set[str]:
    return {
        child.value
        for child in ast.walk(node)
        if isinstance(child, ast.Constant) and isinstance(child.value, str)
    }


def _module_constant(path: Path, name: str) -> object:
    for node in ast.parse(path.read_text("utf-8")).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == name
            and node.value is not None
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"Missing module constant: {name}")


def test_dashboard_is_a_fixed_root_shell_without_focus_driven_self_scrolling() -> None:
    dashboard = _segment(_class_node("GardenDashboard"))
    build = _method_node("GardenDashboard", "_build_ui")

    assert "self.page_scroll" not in dashboard
    assert "ensureWidgetVisible" not in dashboard

    outer_adds = _calls(build, "outer.addWidget")
    assert any(
        call.args and isinstance(call.args[0], ast.Name) and call.args[0].id == "page"
        for call in outer_adds
    )
    root_adds = _calls(build, "root.addWidget")
    assert any(
        len(call.args) >= 2
        and isinstance(call.args[0], ast.Name)
        and call.args[0].id == "hero_card"
        and isinstance(call.args[1], ast.Constant)
        and call.args[1].value == 1
        for call in root_adds
    )


def test_content_measured_narrow_header_stacks_regions_on_distinct_rows() -> None:
    method = _method_node("GardenDashboard", "_apply_responsive_layout")
    source = _segment(method)
    narrow_assignment = next(
        node
        for node in method.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "header_narrow"
            for target in node.targets
        )
    )
    assert isinstance(narrow_assignment.value, ast.BoolOp)
    assert "header_compact and title_actions.mode == COMPACT_MODE" in source
    assert "<= 820" not in source

    narrow_branch = next(
        node
        for node in method.body
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Name)
        and node.test.id == "header_narrow"
    )
    placements: dict[str, tuple[int, ...]] = {}
    for statement in narrow_branch.body:
        for call in _calls(statement, "self.header_grid.addWidget"):
            widget = call.args[0]
            if not isinstance(widget, ast.Attribute):
                continue
            placements[widget.attr] = tuple(
                int(ast.literal_eval(argument)) for argument in call.args[1:]
            )

    assert placements == {
        "title_stack_widget": (0, 0, 1, 2),
        "header_actions_widget": (1, 0, 1, 2),
        "garden_stats_bar": (2, 0, 1, 2),
    }


def test_plant_popover_uses_one_slash_progress_value_and_hides_fully_grown_fertilizer() -> None:
    selected = _method_node("PlantInfoCard", "set_selected")
    selected_source = _segment(selected)
    layout_actions = _method_node("PlantInfoCard", "_layout_actions")

    fertilizer_visibility = _calls(selected, "self.fertilize.setVisible")
    assert any(
        call.args
        and isinstance(call.args[0], ast.UnaryOp)
        and isinstance(call.args[0].op, ast.Not)
        and isinstance(call.args[0].operand, ast.Name)
        and call.args[0].operand.id == "fully_grown"
        for call in fertilizer_visibility
    )

    fully_grown_branch = next(
        node
        for node in layout_actions.body
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Name)
        and node.test.id == "fully_grown"
    )
    grown_actions = {
        call.args[0].attr
        for call in _calls(fully_grown_branch, "self.actions.addWidget")
        if call.args and isinstance(call.args[0], ast.Attribute)
    }
    assert grown_actions == {"choose_another", "move", "story"}
    assert 'value_text=f"{stage_points:,} / {stage_goal:,} Growth"' in selected_source
    assert 'value_text=f"{growth_points:,} Growth"' in selected_source
    assert '"Plant Growth"' in selected_source
    assert _calls(selected, "self.growth_summary.hide")
    assert _calls(selected, "self.growth_remaining.hide")
    assert not _calls(selected, "self.growth_remaining.show")
    assert not _calls(selected, "self.growth_remaining.setText")
    assert not any(
        call.args
        and isinstance(call.args[0], ast.Constant)
        and call.args[0].value is True
        for call in _calls(selected, "self.growth_remaining.setVisible")
    )


def test_fully_grown_action_hint_is_owned_by_the_plant_card_layout() -> None:
    constructor = _method_node("PlantInfoCard", "__init__")
    placements = [
        call
        for call in _calls(constructor, "layout.addWidget")
        if call.args
        and isinstance(call.args[0], ast.Attribute)
        and isinstance(call.args[0].value, ast.Name)
        and call.args[0].value.id == "self"
        and call.args[0].attr == "action_hint"
    ]
    assert len(placements) == 1

    actions_layout = next(
        call
        for call in _calls(constructor, "layout.addLayout")
        if call.args
        and isinstance(call.args[0], ast.Attribute)
        and isinstance(call.args[0].value, ast.Name)
        and call.args[0].value.id == "self"
        and call.args[0].attr == "actions"
    )
    assert placements[0].lineno < actions_layout.lineno


def test_collection_filter_empty_state_has_exact_recovery_copy_and_clear_hook() -> None:
    refresh = _method_node("GardenDashboard", "_refresh_collection_list")
    refresh_strings = _strings(refresh)
    expected_copy = {
        "No plants match these filters",
        "Choose another filter or show the complete collection.",
        "Clear filters",
    }
    missing = expected_copy - refresh_strings
    assert not missing, f"Collection empty-state contract is missing: {sorted(missing)}"

    clear_buttons = [
        call
        for call in ast.walk(refresh)
        if isinstance(call, ast.Call)
        and _call_path(call.func).endswith("QPushButton")
        and call.args
        and isinstance(call.args[0], ast.Constant)
        and call.args[0].value == "Clear filters"
    ]
    assert clear_buttons, "Clear filters must be a real keyboard-operable button."

    direct_resets = [
        call
        for call in _calls(refresh, "self._set_collection_filter")
        if any(
            isinstance(argument, ast.Constant) and argument.value == "all"
            for argument in call.args
        )
    ]
    clear_methods = {
        node.name
        for node in _class_node("GardenDashboard").body
        if isinstance(node, ast.FunctionDef)
        and "clear" in node.name
        and "collection" in node.name
        and "filter" in node.name
    }
    refresh_source = _segment(refresh)
    named_reset_is_connected = any(
        f"self.{method_name}" in refresh_source for method_name in clear_methods
    )
    assert direct_resets or named_reset_is_connected, (
        "Clear filters must reset the collection filter to All."
    )


def test_all_scroll_layers_use_explicit_garden_surfaces() -> None:
    module = ast.parse(_source())
    scroll_constructors = _calls(module, "QScrollArea")
    surface_calls = _calls(module, "_set_scroll_surface")
    helper = _segment(_function_node("_set_scroll_surface"))

    assert len(scroll_constructors) == 16
    assert len(surface_calls) == len(scroll_constructors)
    assert "scroll.viewport()" in helper
    assert "for widget in (scroll, scroll.viewport(), content)" in helper
    assert 'widget.setProperty("gardenScrollSurface", True)' in helper
    assert "widget.setAutoFillBackground(True)" in helper


def test_shared_tabs_and_empty_state_action_never_fall_back_to_platform_gray() -> None:
    stylesheet = _segment(_function_node("_garden_dialog_stylesheet"))
    empty_state = _segment(_method_node("EmptyState", "__init__"))
    collection = _segment(
        _method_node("GardenDashboard", "_refresh_collection_list")
    )

    assert "QTabWidget::pane {{ border:0; background:{t['dialog_surface']}" in stylesheet
    assert "QTabBar::tab {{" in stylesheet
    assert "background:{t['dialog_surface']}" in stylesheet
    assert "QPushButton[emptyStateAction='true'][variant='primary']" in stylesheet
    assert 'action.setProperty("emptyStateAction", True)' in empty_state
    assert "_pin_empty_state_action_style(" in empty_state
    assert "self.collection_list.add_full_width(EmptyState(" in collection

    local_style = _segment(_function_node("_pin_empty_state_action_style"))
    assert "button.setStyleSheet(" in local_style
    assert "background-color:{t['action_accent']}" in local_style


def test_garden_uses_a_movable_native_window_in_the_anki_fullscreen_space() -> None:
    dialog_shell = _segment(_class_node("DialogShell"))
    attach = _segment(
        _method_node("DialogShell", "_attach_native_parent_before_show")
    )
    auxiliary = _segment(
        _method_node("DialogShell", "_configure_macos_auxiliary_window")
    )
    present = _segment(_method_node("DialogShell", "present_over_parent"))
    position = _segment(
        _method_node("DialogShell", "_position_over_parent_once")
    )
    synchronous = _segment(_method_node("DialogShell", "exec"))
    dashboard = _class_node("GardenDashboard")
    nursery = _class_node("NurseryDialog")
    opener_source = (
        ROOT / "ankigarden" / "addon.py"
    ).read_text(encoding="utf-8")

    assert isinstance(dashboard.bases[0], ast.Name)
    assert dashboard.bases[0].id == "DialogShell"
    assert isinstance(nursery.bases[0], ast.Name)
    assert nursery.bases[0].id == "DialogShell"
    assert "class DialogShell(QWidget)" in dialog_shell
    assert "Qt.WindowModality.WindowModal" in dialog_shell
    assert "def present_over_parent" in dialog_shell
    assert 'platform.system() == "Darwin"' in dialog_shell
    assert "Qt.WindowType.Tool" in dialog_shell
    assert "Qt.WindowType.WindowTitleHint" in dialog_shell
    assert "Qt.WindowType.WindowMinimizeButtonHint" in dialog_shell
    assert "Qt.WindowType.WindowMaximizeButtonHint" in dialog_shell
    assert 'self.setProperty("movableNativeWindow", True)' in dialog_shell
    assert "self._native_position_initialized = False" in dialog_shell
    assert "child_handle.setTransientParent(parent_handle)" in attach
    assert "child_handle.setScreen(parent_handle.screen())" in attach
    assert "Qt.WidgetAttribute.WA_ShowWithoutActivating" in dialog_shell
    assert 'ctypes.CDLL("/usr/lib/libobjc.A.dylib")' in auxiliary
    assert "move_to_active_space = 1 << 1" in auxiliary
    assert "full_screen_auxiliary = 1 << 8" in auxiliary
    assert "auxiliary = 1 << 17" in auxiliary
    assert 'sel_register_name(b"setCollectionBehavior:")' in auxiliary
    assert 'self.setProperty("macosMoveToActiveSpace"' in auxiliary
    assert 'self.setProperty("macosFullScreenAuxiliary"' in auxiliary
    assert present.index("self._attach_native_parent_before_show()") < present.index(
        "self.show()"
    )
    assert "self._native_auxiliary_on_macos and not attached" in present
    assert present.index("self._position_over_parent_once()") < present.index(
        "self.show()"
    )
    assert "if self._native_position_initialized" in position
    assert "self._native_position_initialized = True" in position
    assert "activateWindow" not in present
    assert "self.present_over_parent()" in synchronous
    assert "QEventLoop(self)" in synchronous
    assert "event_loop.exec()" in synchronous
    assert 'getattr(self.dashboard, "present_over_parent", None)' in opener_source
    assert "activateWindow" not in opener_source


def test_dialog_presentation_reports_attachment_and_visibility_failures() -> None:
    log_calls: list[str] = []
    present = _compiled_method(
        "DialogShell",
        "present_over_parent",
        {
            "logger": SimpleNamespace(
                error=lambda *_args, **_kwargs: log_calls.append("error"),
                exception=lambda *_args, **_kwargs: log_calls.append("exception"),
            )
        },
    )

    class Shell:
        def __init__(self, *, visible: bool, native: bool, attached: bool) -> None:
            self.visible = visible
            self._native_auxiliary_on_macos = native
            self.attached = attached
            self.calls: list[str] = []

        def isVisible(self) -> bool:
            return self.visible

        def raise_(self) -> None:
            self.calls.append("raise")

        def _attach_native_parent_before_show(self) -> bool:
            self.calls.append("attach")
            return self.attached

        def _position_over_parent_once(self) -> None:
            self.calls.append("position")

        def show(self) -> None:
            self.calls.append("show")

    already_visible = Shell(visible=True, native=True, attached=True)
    assert present(already_visible) is True
    assert already_visible.calls == ["raise"]

    unattached = Shell(visible=False, native=True, attached=False)
    assert present(unattached) is False
    assert unattached.calls == ["attach"]

    invisible_after_show = Shell(visible=False, native=False, attached=False)
    assert present(invisible_after_show) is False
    assert invisible_after_show.calls == ["attach", "position", "show"]
    assert log_calls.count("error") == 2


def test_dialog_exec_scopes_window_modality_and_rejects_reentrant_loops() -> None:
    non_modal = object()
    window_modal = object()
    loops: list[Any] = []

    class EventLoop:
        def __init__(self, owner: Any) -> None:
            self.owner = owner
            loops.append(self)

        def exec(self) -> None:
            assert self.owner.modality is window_modal
            assert self.owner._modal_requested is True
            self.owner._dialog_result = 1

    execute = _compiled_method(
        "DialogShell",
        "exec",
        {
            "QDialog": SimpleNamespace(
                DialogCode=SimpleNamespace(Rejected=0)
            ),
            "QEventLoop": EventLoop,
            "Qt": SimpleNamespace(
                WindowModality=SimpleNamespace(WindowModal=window_modal)
            ),
            "logger": SimpleNamespace(
                warning=lambda *_args, **_kwargs: None,
                debug=lambda *_args, **_kwargs: None,
            ),
        },
    )

    class Shell:
        def __init__(self, *, presented: bool = True) -> None:
            self._dialog_result = 0
            self._dialog_event_loop = None
            self._dialog_exec_active = False
            self._modal_requested = False
            self.modality = non_modal
            self.presented = presented
            self.present_calls = 0
            self.modality_changes: list[Any] = []

        def windowModality(self) -> Any:
            return self.modality

        def setWindowModality(self, modality: Any) -> None:
            self.modality = modality
            self.modality_changes.append(modality)

        def present_over_parent(self) -> bool:
            self.present_calls += 1
            return self.presented

    shell = Shell()
    assert execute(shell) == 1
    assert shell.modality_changes == [window_modal, non_modal]
    assert shell.modality is non_modal
    assert shell._dialog_event_loop is None
    assert shell._dialog_exec_active is False
    assert shell._modal_requested is False
    assert shell.present_calls == 1
    assert len(loops) == 1

    refused = Shell(presented=False)
    assert execute(refused) == 0
    assert refused.modality_changes == [window_modal, non_modal]
    assert refused._dialog_exec_active is False
    assert refused._modal_requested is False
    assert len(loops) == 1

    reentrant = Shell()
    reentrant._dialog_exec_active = True
    reentrant._dialog_result = 7
    assert execute(reentrant) == 0
    assert reentrant.present_calls == 0
    assert reentrant.modality_changes == []
    assert len(loops) == 1


def test_exec_backed_nursery_story_species_and_fertilizer_share_modal_shell() -> None:
    assert _class_node("GardenDialog").bases[0].id == "DialogShell"
    assert _class_node("NurseryDialog").bases[0].id == "DialogShell"
    assert _class_node("StarterConfirmationDialog").bases[0].id == "DialogShell"
    assert _class_node("FertilizerReplacementDialog").bases[0].id == "DialogShell"
    assert _class_node("PlantStoryDialog").bases[0].id == "GardenDialog"

    exec_callers = {
        "Nursery": _segment(_method_node("GardenDashboard", "_open_nursery")),
        "Plant Story": _segment(_method_node("GardenDashboard", "_open_plant_story")),
        "species overview": _segment(
            _method_node("GardenDashboard", "_open_species_overview")
        ),
        "Fertilizer": _segment(
            _method_node("GardenDashboard", "_open_fertilizer_menu")
        ),
    }
    assert all(".exec()" in source for source in exec_callers.values())

    synchronous = _segment(_method_node("DialogShell", "exec"))
    assert synchronous.index("Qt.WindowModality.WindowModal") < synchronous.index(
        "self.present_over_parent()"
    )
    assert "if self._dialog_exec_active:" in synchronous
    assert "finally:" in synchronous
    assert "self.setWindowModality(previous_modality)" in synchronous

    opener = (ROOT / "ankigarden" / "addon.py").read_text("utf-8")
    open_method = ast.get_source_segment(
        opener,
        next(
            child
            for node in ast.parse(opener).body
            if isinstance(node, ast.ClassDef) and node.name == "AnkiGardenApp"
            for child in node.body
            if isinstance(child, ast.FunctionDef)
            and child.name == "_open_dashboard_when_ready"
        ),
    )
    assert open_method is not None
    assert "presentation_result" in open_method
    assert "if not bool(self.dashboard.isVisible()):" in open_method
    assert open_method.index("if not bool(self.dashboard.isVisible()):") < open_method.index(
        'getattr(self.dashboard, "acknowledge_rendered_feedback", None)'
    )


def test_dialog_shell_construction_never_shows_parentless_widgets_on_macos() -> None:
    """A parentless setVisible(True) creates a transient NSWindow and changes Spaces."""

    shell_init = _segment(_method_node("DialogShell", "__init__"))
    garden_dialog_init = _method_node("GardenDialog", "__init__")
    garden_dialog_source = _segment(garden_dialog_init)

    assert "self.hide()" in shell_init
    assert 'QLabel(subtitle, self.header)' in garden_dialog_source
    assert 'QPushButton("×", self.header)' in garden_dialog_source

    assigned_parents: dict[str, str] = {}
    for statement in garden_dialog_init.body:
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
            continue
        target = statement.targets[0]
        value = statement.value
        if (
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
            and isinstance(value, ast.Call)
            and value.args
            and isinstance(value.args[-1], ast.Attribute)
            and isinstance(value.args[-1].value, ast.Name)
            and value.args[-1].value.id == "self"
        ):
            assigned_parents[target.attr] = value.args[-1].attr

    visible_targets = {
        call.func.value.attr
        for call in ast.walk(garden_dialog_init)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr == "setVisible"
        and isinstance(call.func.value, ast.Attribute)
        and isinstance(call.func.value.value, ast.Name)
        and call.func.value.value.id == "self"
    }
    assert visible_targets == {"dialog_subtitle", "top_close"}
    assert all(assigned_parents.get(name) == "header" for name in visible_targets)


def test_window_content_reflows_without_overwriting_user_geometry() -> None:
    settings = _segment(_class_node("GardenSettingsDialog"))
    settings_tab = _segment(
        _method_node("GardenSettingsDialog", "_sync_settings_tab")
    )
    settings_details = _segment(
        _method_node("GardenSettingsDialog", "_toggle_debug_report")
    )
    dashboard_scene = _segment(
        _method_node("GardenDashboard", "_update_scene_height")
    )
    customize = _segment(
        _method_node("CustomizeGardenDialog", "resizeEvent")
    )
    customize_mode = _segment(
        _method_node("CustomizeGardenDialog", "_apply_customize_layout_mode")
    )
    nursery = _segment(_method_node("NurseryDialog", "resizeEvent"))

    assert "advanced = QScrollArea()" in settings
    assert "self.resize(" not in settings_tab
    assert "_fit_dialog_to_screen" not in settings_tab
    assert "self.resize(" not in settings_details
    assert "self.scene.setMaximumHeight(16777215)" in dashboard_scene
    assert "self.scene.setMaximumHeight(target)" not in dashboard_scene
    assert "margins = self._shell_layout.contentsMargins()" in customize
    assert "self.customize_responsive.evaluate(content_width)" in customize
    assert "self.main_grid.setColumnStretch(column, 0)" in customize_mode
    assert "self.main_grid.setRowStretch(row, 0)" in customize_mode
    assert "margins = self.layout().contentsMargins()" in nursery
    assert "self.hero_responsive.evaluate(available)" in nursery
    assert 'self.setProperty("heroMode", hero.mode)' in nursery


def test_compact_stats_preserve_the_anki_streak_accessible_name() -> None:
    stats = _segment(_class_node("GardenStatsStrip"))
    compact = _segment(_method_node("GardenStatsStrip", "set_compact"))
    assert 'self.streak_label.setText("ANKI STREAK")' in compact
    assert 'self.streak_label.setAccessibleName("ANKI STREAK")' in compact
    assert "self.streak_heading.removeWidget(self.streak_bonus)" in compact
    assert "self.streak_value_row.insertWidget(" in compact
    assert "self.streak_bonus.setMinimumWidth(48)" in stats


def test_first_run_header_compacts_and_resynchronizes_with_onboarding_state() -> None:
    stats = _segment(_method_node("GardenStatsStrip", "set_onboarding_mode"))
    refresh = _segment(_method_node("GardenDashboard", "_refresh_onboarding"))
    heights = _segment(
        _method_node("GardenDashboard", "_sync_header_minimum_heights")
    )

    assert "cell.setMinimumHeight(96)" in stats
    assert "self.garden_stats_bar.set_onboarding_mode(guided)" in refresh
    assert refresh.index("self.garden_stats_bar.set_onboarding_mode(guided)") < refresh.index(
        "self._sync_header_minimum_heights()"
    )
    assert "96 if guided else (192 if metrics_compact else 104)" in heights
    assert "186 if self._header_narrow_layout else" in heights
    assert "160 if self._header_compact_layout else" in heights
    assert "self.top_bar.setMinimumHeight(minimum)" in heights


def test_customize_effects_advanced_action_has_readable_copy_at_compact_widths() -> None:
    constructor = _segment(_method_node("CustomizeGardenDialog", "__init__"))
    responsive = _segment(_method_node("CustomizeGardenDialog", "resizeEvent"))

    assert "self.effects_advanced_layout = QVBoxLayout(self.effects_advanced)" in constructor
    assert 'QLabel("Included appearance")' in constructor
    assert (
        '"Preview Clear Skies with Verdant Twilight. Apply changes to save."'
        in constructor
    )
    assert 'QPushButton("Preview included appearance")' in constructor
    assert "The appearance is not saved until Apply changes is selected." in constructor
    assert "_set_button_variant(restore, BUTTON_VARIANT_SECONDARY)" in constructor
    assert "effects_advanced_layout.setDirection" not in responsive


def test_settings_garden_name_validation_is_inline_accessible_and_focuses_the_field() -> None:
    settings = _class_node("GardenSettingsDialog")
    settings_source = _segment(settings)
    update = _method_node("GardenSettingsDialog", "_update_dirty_state")
    save = _method_node("GardenSettingsDialog", "_save_visual_settings")

    assert _module_constant(STATE_PATH, "MAX_GARDEN_NAME_LENGTH") == 40
    assert (
        'f"Garden name must be 1 to {MAX_GARDEN_NAME_LENGTH} characters."'
        in settings_source
    ), "Garden name validation must resolve to the exact 1-to-40 message."
    assert "Fix 1 error before saving." in _strings(settings)

    assert re.search(
        r"addWidget\(self\.[A-Za-z_]*(?:error|validation)[A-Za-z_]*\)",
        settings_source,
    ), "The Garden name error must be an inline widget below the field."
    assert re.search(
        r"garden_name_edit\.setProperty\(\s*['\"](?:invalid|validationState)['\"]",
        settings_source,
    ), "The field needs an explicit invalid state for styling and automation."
    invalid_border = re.search(
        r"QLineEdit\[invalid=['\"]?true['\"]?\].*?border",
        settings_source,
        re.DOTALL,
    )
    validation_state_border = re.search(
        r"QLineEdit\[validationState=['\"]error['\"]\].*?border",
        settings_source,
        re.DOTALL,
    )
    assert invalid_border or validation_state_border, (
        "The invalid state needs a visible field border."
    )
    assert settings_source.count(
        "self.garden_name_edit.setAccessibleDescription("
    ) >= 2, "The inline validation message must also reach assistive technology."

    update_source = _segment(update)
    assert "set_control_enabled(" in update_source
    assert "dirty and valid" in update_source
    assert "Fix the Garden name error before saving." in update_source
    assert (
        "invalid" in update_source
        or "validation" in update_source
        or "garden_name_error" in update_source
    ), "Text changes must update and clear field-level validation immediately."
    assert "self.garden_name_edit.setFocus()" in _segment(save), (
        "An attempted invalid save must focus the Garden name field."
    )


def test_missing_artwork_uses_graphical_code_native_fallbacks_without_text_substitution() -> None:
    placeholder = _segment(_function_node("_botanical_placeholder_pixmap"))
    environment_placeholder = _segment(
        _function_node("_environment_placeholder_pixmap")
    )
    weather_placeholder = _segment(_function_node("_weather_placeholder_overlay"))
    environment_preview = _segment(_function_node("_environment_preview_pixmap"))
    plant_preview = _segment(_function_node("_asset_preview_label"))
    populated_preview = _segment(_function_node("_populate_asset_preview"))
    item_preview = _segment(_function_node("_item_preview_label"))
    nursery_item = _segment(_method_node("NurseryDialog", "_item_artwork"))
    plant_card = _segment(_method_node("PlantInfoCard", "set_selected"))
    story = _segment(_method_node("PlantStoryDialog", "refresh"))

    assert "QPixmap(" in placeholder
    assert "QPainter(" in placeholder
    assert "drawEllipse(" in placeholder
    assert "drawRect(" in placeholder
    assert "QPainter(" in environment_placeholder
    assert "QPainter(" in weather_placeholder
    assert "drawEllipse(" in weather_placeholder
    assert "drawLine(" in weather_placeholder
    assert "_environment_placeholder_pixmap(" in environment_preview
    assert "_weather_placeholder_overlay(" in environment_preview

    for source in (
        plant_preview,
        populated_preview,
        item_preview,
        nursery_item,
        plant_card,
        story,
    ):
        assert "_botanical_placeholder_pixmap(" in source

    assert "label.setText(stage_name)" not in plant_preview
    assert "target.setText(fallback_text)" not in populated_preview
    assert 'label.setText("◇")' not in item_preview
    assert "label.setText(accessible_name)" not in nursery_item
    assert 'self.artwork.setText("◇")' not in plant_card
    assert 'stage_preview.setText("?")' not in story
