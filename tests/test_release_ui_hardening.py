from __future__ import annotations

from ankigarden.presentation import plant_species_name, plant_stage_event

import ast

import pytest
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any


DASHBOARD_PATH = (
    Path(__file__).resolve().parents[1] / "ankigarden" / "ui" / "dashboard.py"
)


@lru_cache(maxsize=1)
def _dashboard_source() -> str:
    return DASHBOARD_PATH.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _dashboard_tree() -> ast.Module:
    return ast.parse(_dashboard_source(), filename=str(DASHBOARD_PATH))


def _compiled_method(
    class_name: str,
    method_name: str,
    namespace: dict[str, Any] | None = None,
) -> Any:
    tree = _dashboard_tree()
    method = deepcopy(_method_node(class_name, method_name))
    method.decorator_list = []
    module = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
    scope = dict(namespace or {})
    exec(compile(module, str(DASHBOARD_PATH), "exec"), scope)
    return scope[method_name]


def _dialog_shell_node() -> ast.ClassDef:
    return next(
        node
        for node in _dashboard_tree().body
        if isinstance(node, ast.ClassDef) and node.name == "_ShellBehavior"
    )


def _method_node(class_name: str, method_name: str) -> ast.FunctionDef:
    classes = {n.name: n for n in _dashboard_tree().body if isinstance(n, ast.ClassDef)}
    pending = [class_name]
    seen = set()
    while pending:
        name = pending.pop(0)
        if name in seen or name not in classes:
            continue
        seen.add(name)
        owner = classes[name]
        for node in owner.body:
            if isinstance(node, ast.FunctionDef) and node.name == method_name:
                return node
        pending.extend(ast.unparse(base) for base in owner.bases)
    raise AssertionError(f"missing method: {class_name}.{method_name}")


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
    source = _dashboard_source()
    shell = _dialog_shell_node()
    shell_source = ast.get_source_segment(source, shell) or ""

    assert "class DialogShell(_ShellBehavior, QDialog):" in source
    assert "class PageShell(_ShellBehavior, QWidget):" in source
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
    tree = _dashboard_tree()
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
            if "DialogShell" in direct or "PageShell" in direct:
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
        "GrowthChargeConfirmationDialog",
        "PurchaseConfirmationDialog",
        "FertilizerReplacementDialog",
    ):
        assert derives_from_dialog_shell(class_name), class_name


def test_growth_charge_preview_and_success_share_one_markup_tree() -> None:
    source = _dashboard_source()
    owner = next(
        node
        for node in _dashboard_tree().body
        if isinstance(node, ast.ClassDef)
        and node.name == "GrowthChargeConfirmationDialog"
    )
    owner_source = ast.get_source_segment(source, owner) or ""
    refresh_source = ast.get_source_segment(
        source,
        _method_node("GrowthChargeConfirmationDialog", "_refresh_quote"),
    ) or ""
    success_source = ast.get_source_segment(
        source,
        _method_node("GrowthChargeConfirmationDialog", "_show_receipt"),
    ) or ""
    confirmed_data_source = ast.get_source_segment(
        source,
        _method_node("GrowthChargeConfirmationDialog", "_data_from_outcome"),
    ) or ""

    assert "self.summary_panel = QFrame" in owner_source
    assert owner_source.count("self.summary_panel = QFrame") == 1
    assert "self._render_shared_summary(self._data_from_quote(quote))" not in refresh_source
    assert "self._render_shared_summary(data)" in refresh_source
    assert "data = self._data_from_quote(quote)" in refresh_source
    assert "data = self._data_from_outcome(outcome)" in success_source
    assert "self._render_shared_summary(data)" in success_source
    assert "QFrame(" not in success_source
    assert "self.quote" not in confirmed_data_source
    for confirmed_field in (
        "outcome.previous_growth",
        "outcome.resulting_growth",
        "outcome.previous_stage",
        "outcome.resulting_stage",
        "outcome.growth_granted",
        "outcome.inventory_remaining",
        "outcome.rewards",
        "request.expected_inventory",
    ):
        assert confirmed_field in confirmed_data_source
    assert "GrowthChargeDialog = GrowthChargeConfirmationDialog" in source
    assert "GrowthChargeProgressBar(self.summary_panel)" in owner_source
    progress_owner = next(
        node
        for node in _dashboard_tree().body
        if isinstance(node, ast.ClassDef)
        and node.name == "GrowthChargeProgressBar"
    )
    progress_source = ast.get_source_segment(source, progress_owner) or ""
    assert "_MINIMUM_NONZERO_FILL = 2.0" in progress_source
    assert "max(self._MINIMUM_NONZERO_FILL, exact_width)" in progress_source

    for required_copy in (
        '"Use 1 charge"',
        '"View plant"',
        '"Charges remaining"',
        '"Next-stage progress"',
        'format_status_label(data.before_stage_name)',
        'format_status_label(data.after_stage_name)',
    ):
        assert required_copy in owner_source
    for obsolete_copy in (
        '"Reaches Sprout"',
        '"Use Small Growth Charge"',
        '"Small Growth Charges remaining"',
    ):
        assert obsolete_copy not in owner_source


def test_growth_charge_transition_copy_keeps_stage_up_and_same_stage_layouts() -> None:
    transition_copy = _compiled_method(
        "GrowthChargeConfirmationDialog",
        "_transition_copy",
        {
            "GrowthChargeDialogData": object,
            "plant_species_name": plant_species_name,
            "plant_stage_event": plant_stage_event,
            "format_status_label": lambda value: str(value).title(),
        },
    )
    stage_change = SimpleNamespace(
        plant_name="Bonsai Sprout",
        plant_species="bonsai",
        stage_changed=True,
        after_stage_name="sprout",
        growth_amount=100,
    )
    same_stage = SimpleNamespace(
        plant_name="Bonsai Sprout",
        plant_species="bonsai",
        stage_changed=False,
        after_stage_name="sprout",
        growth_amount=100,
    )

    stage_change.variant = "confirmation"
    assert transition_copy(stage_change) == "Bonsai will reach sprout"
    stage_change.variant = "success"
    assert transition_copy(stage_change) == "Bonsai reached Sprout"
    same_stage.variant = "confirmation"
    assert transition_copy(same_stage) == "Bonsai Sprout will gain 100 Growth"
    same_stage.variant = "success"
    assert transition_copy(same_stage) == "Bonsai Sprout gained 100 Growth"


def test_growth_charge_view_plant_returns_to_the_committed_target() -> None:
    source = _dashboard_source()
    activate = _compiled_method("GrowthChargeConfirmationDialog", "_activate_primary")
    owner_source = ast.get_source_segment(
        source,
        _method_node("GardenDashboard", "_open_growth_charges_for_plant"),
    ) or ""

    for destination, opens_plant in (("plant", True), ("garden", False)):
        accepted = []
        dialog = SimpleNamespace(_completed=True, quote=SimpleNamespace(destination_kind=destination),
                                 setProperty=lambda *_: None, accept=lambda: accepted.append(True))
        activate(dialog)
        assert dialog.view_plant_requested is opens_plant
        assert accepted == [True]
    assert "view_plant_requested = bool(dialog.view_plant_requested)" in owner_source
    assert "self.scene.keep_card_open(target_id)" in owner_source
    assert "self._refresh_selected_plant_card()" in owner_source




def test_visibility_audit_is_opt_in_and_never_creates_native_handles() -> None:
    source = _dashboard_source()
    tree = _dashboard_tree()
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
    source = _dashboard_source()
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

    tree = _dashboard_tree()
    dispose = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_dispose_owned_dialog"
    )
    dispose_source = ast.get_source_segment(source, dispose) or ""
    assert "setParent(" not in dispose_source




@pytest.mark.parametrize("rename_raises", [False, True])
def test_settings_name_failure_reports_split_commit_when_rollback_fails(rename_raises: bool) -> None:
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
            def rename(_name: str) -> tuple[bool, str]:
                if rename_raises:
                    raise RuntimeError("Name could not be written")
                return False, "Garden name was not saved."
            self.engine = SimpleNamespace(rename_garden=rename)
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
