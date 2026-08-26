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


def test_dialog_exec_scopes_modality_and_rejects_reentrant_loops() -> None:
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
            "QDialog": SimpleNamespace(DialogCode=SimpleNamespace(Rejected=0)),
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
