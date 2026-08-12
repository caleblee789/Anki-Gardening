from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CAPTURE_PATH = ROOT / "ankigarden" / "capture_ui_faces.py"


def _method_source(class_name: str, method_name: str) -> str:
    source = CAPTURE_PATH.read_text("utf-8")
    module = ast.parse(source)
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == method_name:
                    segment = ast.get_source_segment(source, child)
                    assert segment is not None
                    return segment
    raise AssertionError(f"Missing {class_name}.{method_name}")


def _literal_assignment(name: str) -> object:
    module = ast.parse(CAPTURE_PATH.read_text("utf-8"))
    for node in module.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == name and node.value is not None:
                return ast.literal_eval(node.value)
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} was not found")


def test_capture_contract_covers_every_public_surface_group() -> None:
    groups = dict(_literal_assignment("CAPTURE_FACE_GROUPS"))

    assert groups["First run"] == (
            "starter-deck-browser-home",
            "starter-overview-home",
            "starter-garden-onboarding",
            "starter-nursery-plants",
        )
    assert groups["Anki home"] == ("deck-browser-home", "overview-home")
    assert groups["Garden"] == (
            "full-garden",
            "selected-plant-not-nurtured",
            "selected-plant-nurtured",
            "fertilizer-unaffordable",
            "fertilizer-affordable",
            "fertilizer-active",
            "move-mode",
            "plant-story",
        )
    assert groups["Garden Progress"] == (
            "growth-zero",
            "growth-nonzero",
            "streak-new",
            "streak-active",
            "coins-zero",
            "coins-activity",
            "progress-overview",
            "progress-achievements",
            "progress-collection",
        )
    assert groups["Customize"] == ("customize-garden",)
    assert groups["Nursery"] == (
            "nursery-plants",
            "nursery-fertilizer-booster",
            "nursery-garden-spaces",
            "nursery-weather-scenery",
        )
    assert groups["Settings"] == (
            "settings-menu-display",
            "settings-display",
            "diagnostics-clean",
            "diagnostics-warning",
        )
    assert groups["Release stress — Garden"] == (
        "long-garden-name",
        "long-plant-name",
        "four-digit-coin-balance",
        "growth-near-stage-completion",
        "all-six-beds-occupied",
        "plant-at-every-stage",
        "popover-plot-1",
        "popover-plot-2",
        "popover-plot-3",
        "popover-plot-4",
        "popover-plot-5",
        "popover-plot-6",
        "move-occupied-empty-destinations",
        "fertilizer-expiring-under-minute",
        "fertilizer-replacement-confirmation",
    )
    assert groups["Release stress — Progress"] == (
        "collection-several-discovered",
        "collection-no-filter-matches",
        "achievement-completed",
        "streak-at-risk",
        "streak-missed-day",
        "streak-reward-claimed-unclaimed",
    )
    assert groups["Release stress — Nursery"] == (
        "nursery-item-owned",
        "nursery-item-locked",
        "nursery-purchase-success",
    )
    assert groups["Release stress — Settings"] == (
        "settings-unsaved-changes",
        "settings-validation-error",
        "diagnostics-expanded",
    )
    assert groups["Accessibility and responsive"] == (
        "reduced-motion-enabled",
        "keyboard-focus-state",
        "narrow-window-responsive",
        "display-scaling-150",
    )
    labels = [label for group in groups.values() for label in group]
    assert len(labels) == 63
    assert len(labels) == len(set(labels))


def test_capture_runner_drives_every_tab_and_exports_its_contract() -> None:
    source = CAPTURE_PATH.read_text("utf-8")

    for key, label in (
        ("overview", "progress-overview"),
        ("achievements", "progress-achievements"),
        ("collection", "progress-collection"),
    ):
        assert f'self._capture_progress_page("{key}", "{label}")' in source
    for label in (
        "fertilizer-unaffordable",
        "fertilizer-affordable",
        "fertilizer-active",
        "growth-zero",
        "growth-nonzero",
        "streak-new",
        "streak-active",
        "coins-zero",
        "coins-activity",
        "diagnostics-clean",
        "diagnostics-warning",
    ):
        assert f'"{label}"' in source
    for index, label in enumerate(
        (
            "nursery-plants",
            "nursery-fertilizer-booster",
            "nursery-garden-spaces",
            "nursery-weather-scenery",
        )
    ):
        assert f'self._capture_nursery_tab({index}, "{label}")' in source

    assert '"capture_contract_version": CAPTURE_CONTRACT_VERSION' in source
    assert '"capture_groups": [' in source
    assert '"expected_faces": expected_labels' in source
    assert "captured_labels == expected_labels" in source


def test_capture_state_variants_use_writable_sources_and_clear_stale_toasts() -> None:
    growth_zero = _method_source("_UiFaceCaptureRunner", "_capture_growth_zero")
    growth_nonzero = _method_source("_UiFaceCaptureRunner", "_capture_growth_nonzero")
    with_dashboard = _method_source("_UiFaceCaptureRunner", "_with_dashboard")

    assert "plant.growth_points = 0" in growth_zero
    assert "plant.growth_points = 1_250" in growth_nonzero
    assert "plant.growth_stage =" not in growth_zero
    assert "plant.growth_stage =" not in growth_nonzero
    assert 'getattr(dashboard, "toast_region", None)' in with_dashboard
    assert "clear_toast()" in with_dashboard


def test_starter_nursery_capture_does_not_depend_on_a_nested_modal_loop() -> None:
    source = _method_source("_UiFaceCaptureRunner", "_capture_starter_nursery_after")

    assert "NurseryDialog" in source
    assert "setModal(False)" in source
    assert "_open_starter_nursery" not in source
