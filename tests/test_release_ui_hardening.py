from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Any


DASHBOARD_PATH = (
    Path(__file__).resolve().parents[1] / "ankigarden" / "ui" / "dashboard.py"
)


def _compiled_method(
    class_name: str,
    method_name: str,
    namespace: dict[str, Any] | None = None,
) -> Any:
    source = DASHBOARD_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(DASHBOARD_PATH))
    owner = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    method = next(
        node
        for node in owner.body
        if isinstance(node, ast.FunctionDef) and node.name == method_name
    )
    method.decorator_list = []
    module = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
    scope = dict(namespace or {})
    exec(compile(module, str(DASHBOARD_PATH), "exec"), scope)
    return scope[method_name]


def _dialog_shell_node() -> ast.ClassDef:
    source = DASHBOARD_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(DASHBOARD_PATH))
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "DialogShell"
    )


def _method_node(class_name: str, method_name: str) -> ast.FunctionDef:
    source = DASHBOARD_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(DASHBOARD_PATH))
    owner = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )
    return next(
        node
        for node in owner.body
        if isinstance(node, ast.FunctionDef) and node.name == method_name
    )


def _assigned_call(
    class_name: str,
    method_name: str,
    target_source: str,
) -> ast.Call:
    method = _method_node(class_name, method_name)
    for node in ast.walk(method):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        if any(ast.unparse(target) == target_source for target in node.targets):
            return node.value
    raise AssertionError(f"missing assignment for {class_name}.{method_name}: {target_source}")


def test_dialog_shell_uses_the_native_parented_qdialog_contract() -> None:
    source = DASHBOARD_PATH.read_text(encoding="utf-8")
    shell = _dialog_shell_node()
    shell_source = ast.get_source_segment(source, shell) or ""

    assert [ast.unparse(base) for base in shell.bases] == ["QDialog"]
    assert "super().__init__(parent)" in shell_source
    for forbidden in (
        "Qt.WindowType.Tool",
        "WA_ShowWithoutActivating",
        "ctypes",
        "winId",
        "windowHandle",
        "setTransientParent",
        "setScreen",
        "collectionBehavior",
        "QEventLoop",
        "activateWindow",
        "raise_(",
        "_recenter_over_parent",
        "_position_over_parent_once",
    ):
        assert forbidden not in shell_source

    methods = {
        node.name
        for node in shell.body
        if isinstance(node, ast.FunctionDef)
    }
    assert "exec" not in methods
    assert "done" not in methods
    assert "setModal" not in methods
    assert "isModal" not in methods


def test_every_garden_window_route_uses_the_shared_dialog_contract() -> None:
    source = DASHBOARD_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(DASHBOARD_PATH))
    bases = {
        node.name: {ast.unparse(base) for base in node.bases}
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    }

    def derives_from_dialog_shell(class_name: str) -> bool:
        pending = [class_name]
        seen: set[str] = set()
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            seen.add(current)
            direct = bases.get(current, set())
            if "DialogShell" in direct:
                return True
            pending.extend(base for base in direct if base in bases)
        return False

    for class_name in (
        "GardenDashboard",
        "GardenSettingsDialog",
        "NurseryDialog",
        "GardenProgressDialog",
        "GardenDetailsDialog",
        "CollectibleDetailDialog",
        "PlantStoryDialog",
        "StarterConfirmationDialog",
        "GrowthChargeConfirmationDialog",
        "PurchaseConfirmationDialog",
        "FertilizerReplacementDialog",
    ):
        assert derives_from_dialog_shell(class_name), class_name


def test_visibility_sensitive_children_have_parents_at_construction() -> None:
    expected_parent_args = (
        ("GardenDialog", "__init__", "self.dialog_subtitle", 1, "self.header"),
        (
            "GardenStatsStrip",
            "__init__",
            "self.growth_kicker",
            1,
            "self.cells['growth']",
        ),
        ("NurseryDialog", "_available_card", "affordability_label", 1, "card"),
        ("NurseryDialog", "_space_card", "self.bed_affordability", 1, "card"),
        ("CollectibleDetailDialog", "_option_tile", "state", 1, "tile"),
        (
            "GardenDashboard",
            "_collectible_registry_card",
            "status",
            1,
            "card",
        ),
        (
            "GardenDashboard",
            "_collectible_registry_card",
            "facts",
            1,
            "card",
        ),
        (
            "GardenDashboard",
            "_open_fertilizer_menu",
            "current_status",
            0,
            "dialog",
        ),
        (
            "GardenDashboard",
            "_open_fertilizer_menu",
            "options_heading",
            1,
            "dialog",
        ),
        ("NurseryDialog", "__init__", "self._status_hide_timer", 0, "self"),
        ("PlantInfoCard", "__init__", "self.nurture", 1, "self"),
        ("PlantInfoCard", "__init__", "self.fertilize", 1, "self"),
        ("PlantInfoCard", "__init__", "self.growth_charge", 1, "self"),
        ("PlantInfoCard", "__init__", "self.move", 1, "self"),
        ("PlantInfoCard", "__init__", "self.story", 1, "self"),
        ("PlantInfoCard", "__init__", "self.choose_another", 1, "self"),
    )

    for class_name, method_name, target, argument_index, expected_parent in expected_parent_args:
        call = _assigned_call(class_name, method_name, target)
        assert len(call.args) > argument_index, (class_name, method_name, target)
        assert ast.unparse(call.args[argument_index]) == expected_parent


def test_visibility_audit_is_opt_in_and_never_creates_native_handles() -> None:
    source = DASHBOARD_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(DASHBOARD_PATH))
    audit = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "_ParentlessShowAudit"
    )
    installer = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_install_parentless_show_audit"
    )
    audit_source = ast.get_source_segment(source, audit) or ""
    installer_source = ast.get_source_segment(source, installer) or ""

    assert "parentWidget() is None" in audit_source
    assert "isWindow()" in audit_source
    assert "winId" not in audit_source
    assert "ANKI_GARDEN_VISIBILITY_AUDIT" in installer_source


def test_dialog_presentation_uses_show_without_native_window_manipulation() -> None:
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
        def __init__(self, *, visible: bool, visible_after_show: bool = True) -> None:
            self.visible = visible
            self.visible_after_show = visible_after_show
            self.calls: list[str] = []

        def isVisible(self) -> bool:
            return self.visible

        def show(self) -> None:
            self.calls.append("show")
            self.visible = self.visible_after_show

    already_visible = Shell(visible=True)
    assert present(already_visible) is True
    assert already_visible.calls == []

    visible_after_show = Shell(visible=False)
    assert present(visible_after_show) is True
    assert visible_after_show.calls == ["show"]

    invisible_after_show = Shell(visible=False, visible_after_show=False)
    assert present(invisible_after_show) is False
    assert invisible_after_show.calls == ["show"]
    assert log_calls == ["error"]


def test_view_profile_and_disposal_never_move_or_detach_dialogs() -> None:
    source = DASHBOARD_PATH.read_text(encoding="utf-8")
    shell = _dialog_shell_node()
    apply_profile = next(
        node
        for node in shell.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "apply_view_size_profile"
    )
    apply_source = ast.get_source_segment(source, apply_profile) or ""
    assert "self.move(" not in apply_source
    assert "_recenter_over_parent" not in apply_source

    tree = ast.parse(source, filename=str(DASHBOARD_PATH))
    dispose = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_dispose_owned_dialog"
    )
    dispose_source = ast.get_source_segment(source, dispose) or ""
    assert "setParent(" not in dispose_source


def test_settings_name_failure_reports_split_commit_when_rollback_fails() -> None:
    class RollbackFailure(Exception):
        pass

    old_payload = {"show_home_widget": True, "reduced_motion": False}
    new_payload = {"show_home_widget": False, "reduced_motion": True}

    class Config:
        def __init__(self) -> None:
            self.calls: list[dict[str, bool]] = []
            self.committed = dict(old_payload)

        def update(self, payload: dict[str, bool]) -> None:
            self.calls.append(dict(payload))
            if len(self.calls) == 2:
                raise RollbackFailure("rollback write failed")
            self.committed = dict(payload)

    class Dialog:
        def __init__(self) -> None:
            self._persisted_payload = dict(old_payload)
            self._persisted_name = "Old Garden"
            self.behavior = SimpleNamespace(
                build_theme_payload=lambda: dict(new_payload)
            )
            self.garden_name_edit = SimpleNamespace(text=lambda: "New Garden")
            self.config = Config()
            self.engine = SimpleNamespace(
                rename_garden=lambda _name: (False, "Garden name was not saved.")
            )
            self.dirty_baselines: list[tuple[dict[str, bool], str]] = []
            self.errors: list[str] = []

        def _update_dirty_state(self) -> None:
            self.dirty_baselines.append(
                (dict(self._persisted_payload), self._persisted_name)
            )

        def _show_save_error(self, message: str) -> None:
            self.errors.append(message)

    save = _compiled_method(
        "GardenSettingsDialog",
        "_save_visual_settings_once",
        {
            "deepcopy": lambda value: dict(value),
            "MAX_GARDEN_NAME_LENGTH": 40,
            "ConfigError": RollbackFailure,
            "_learner_text": str,
            "logger": SimpleNamespace(exception=lambda *_args, **_kwargs: None),
        },
    )
    dialog = Dialog()

    save(dialog)

    assert dialog.config.calls == [new_payload, old_payload]
    assert dialog.config.committed == new_payload
    assert dialog._persisted_payload == new_payload
    assert dialog._persisted_name == "Old Garden"
    assert dialog.dirty_baselines == [(new_payload, "Old Garden")]
    assert len(dialog.errors) == 1
    assert "Display settings were saved" in dialog.errors[0]
    assert "the garden name wasn’t" in dialog.errors[0]
    assert "Try saving the name again" in dialog.errors[0]
    assert "no Settings changes were applied" not in dialog.errors[0]
