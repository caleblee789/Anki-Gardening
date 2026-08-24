from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

VISIBLE_STRING_PATHS = (
    ROOT / "ankigarden" / "ui" / "dashboard.py",
    ROOT / "ankigarden" / "ui" / "home_widget.py",
    ROOT / "ankigarden" / "ui" / "garden_studio.py",
    ROOT / "ankigarden" / "ui" / "plant_display.py",
    ROOT / "ankigarden" / "ui" / "scene.py",
    ROOT / "ankigarden" / "hooks" / "reviewer.py",
)

VISIBLE_CALLS = {
    "EmptyState",
    "GardenBadge",
    "QCheckBox",
    "QLabel",
    "QPushButton",
    "announce",
    "critical",
    "information",
    "setAccessibleDescription",
    "setAccessibleName",
    "setText",
    "setToolTip",
    "setWindowTitle",
    "show_message",
    "warning",
}

FORBIDDEN_TERMINOLOGY = re.compile(
    r"\b(?:persistence|stale|target|eligible|allocation|passive|canonical|"
    r"projection|transactional|origin|authoritative|credited|generated|loadout)\b|"
    r"active window|inventory changed|resulting balance|owned quantity|"
    r"planted instances",
    re.IGNORECASE,
)

REMOVED_VISIBLE_COPY = (
    "No gameplay bonus",
    "No growth recorded today",
    "Streak bonus +0%",
    "Stage remains",
    "Purchase and apply",
    "Purchase and replace",
    "Confirm purchase",
    "Purchasing…",
    "Apply Growth Charge",
    "Growth Charge applied",
    "Use potion",
    "Manage loadout",
    "Refresh diagnostics",
    "No new plants available",
    "Every currently available species is already in your collection",
    "Botanical catalog",
    "Choose a fertilizer",
    "Temporarily increase Growth earned per card",
    "Browse fertilizers",
    "Not now",
    "Preview paused",
    "Outcome preview",
    "More details",
    "Garden Spaces",
)

OFFSCREEN_STRING_PATHS = (
    ROOT / "ankigarden" / "addon.py",
    ROOT / "ankigarden" / "game.py",
    ROOT / "ankigarden" / "reward_presentation.py",
    ROOT / "ankigarden" / "terminology.py",
    ROOT / "ankigarden" / "purchases.py",
    ROOT / "ankigarden" / "hooks" / "reviewer.py",
    ROOT / "ankigarden" / "ui" / "copy.py",
    ROOT / "ankigarden" / "ui" / "state.py",
    ROOT / "ankigarden" / "ui" / "plant_presenters.py",
    *VISIBLE_STRING_PATHS,
)

OFFSCREEN_REMOVED_COPY = (
    "The reward for finishing all due cards could not be saved.",
    "The purchase could not be saved; no Garden Coins were spent.",
    "The Booster Potion could not be applied",
    "The move could not be saved",
    "The collection change could not be saved.",
    "The plant you chose to nurture could not be saved.",
    "The new name could not be saved.",
    "The garden name could not be saved.",
    "The new arrangement could not be saved.",
    "The previous arrangement could not be restored.",
    "Anki card answer Garden can count",
    "Anki card answers Garden can count",
    "Growth per Anki card answer",
    "Finalized after the qualifying Anki day",
    "Garden progress could not refresh.",
    "stored in Collection and remains owned",
    "Storing the plant could not be saved.",
    "Planting could not be saved.",
    "Nurtured + passive",
    "cards left to",
    "direct Growth to the nurtured plant",
    "Added to the Weather and Scenery collection",
    "unfinished planted plant",
    "Move or swap here",
    "Swap with plant",
    "Showing the last available garden preview",
    "Garden progress could not be loaded",
)

PROCESS_BUTTON_LABELS = {
    "Purchase",
    "Confirm purchase",
    "Purchase and apply",
    "Purchase and replace",
    "Apply Growth Charge",
    "Manage loadout",
    "Refresh diagnostics",
}


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def _literal_text(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            value.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str)
            else "{}"
            for value in node.values
        )
    return None


def _visible_literals() -> tuple[tuple[Path, int, str], ...]:
    records: list[tuple[Path, int, str]] = []
    for path in VISIBLE_STRING_PATHS:
        tree = ast.parse(path.read_text("utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or _call_name(node) not in VISIBLE_CALLS:
                continue
            for argument in (*node.args, *(keyword.value for keyword in node.keywords)):
                text = _literal_text(argument)
                if text:
                    records.append((path, node.lineno, text))
    return tuple(records)


def test_ordinary_ui_literals_do_not_expose_implementation_terminology() -> None:
    violations = [
        f"{path.relative_to(ROOT)}:{line}: {text!r}"
        for path, line, text in _visible_literals()
        if FORBIDDEN_TERMINOLOGY.search(text)
    ]
    assert not violations, "Implementation terminology reached ordinary UI:\n" + "\n".join(
        violations
    )


def test_deleted_copy_is_not_reintroduced_on_visible_surfaces() -> None:
    violations = [
        f"{path.relative_to(ROOT)}:{line}: {text!r}"
        for path, line, text in _visible_literals()
        if any(removed.casefold() in text.casefold() for removed in REMOVED_VISIBLE_COPY)
    ]
    assert not violations, "Superseded copy remains visible:\n" + "\n".join(violations)


def test_only_metric_labels_use_the_required_all_caps_copy() -> None:
    allowed_metric_labels = {"CURRENT PLANT", "ANKI STREAK", "GARDEN COINS"}
    violations = [
        f"{path.relative_to(ROOT)}:{line}: {text!r}"
        for path, line, text in _visible_literals()
        if text in allowed_metric_labels and path.name != "dashboard.py"
    ]
    assert not violations, "Metric-label copy escaped the Garden header:\n" + "\n".join(
        violations
    )
    visible = {text for _path, _line, text in _visible_literals()}
    assert allowed_metric_labels <= visible


def test_offscreen_learner_copy_does_not_restore_superseded_phrasing() -> None:
    violations: list[str] = []
    for path in OFFSCREEN_STRING_PATHS:
        source = path.read_text("utf-8")
        for removed in OFFSCREEN_REMOVED_COPY:
            if removed.casefold() in source.casefold():
                violations.append(f"{path.relative_to(ROOT)}: {removed!r}")
    assert not violations, "Superseded off-screen copy remains:\n" + "\n".join(
        violations
    )


def test_buttons_use_direct_action_labels() -> None:
    violations: list[str] = []
    for path in VISIBLE_STRING_PATHS:
        tree = ast.parse(path.read_text("utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or _call_name(node) != "QPushButton":
                continue
            if not node.args:
                continue
            label = _literal_text(node.args[0])
            if label in PROCESS_BUTTON_LABELS:
                violations.append(
                    f"{path.relative_to(ROOT)}:{node.lineno}: {label!r}"
                )
    assert not violations, "Process-oriented button labels remain:\n" + "\n".join(
        violations
    )


def test_occupied_bed_swap_is_confirmed_only_after_selection() -> None:
    dashboard = (ROOT / "ankigarden" / "ui" / "dashboard.py").read_text("utf-8")

    assert 'box.setText(f"Swap {moving.name} with {occupant.name}?")' in dashboard
    assert 'box.addButton("Swap", QMessageBox.ButtonRole.AcceptRole)' in dashboard
    assert 'box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)' in dashboard
    assert 'self.rearrange_bar.instructions.setText("Choose a bed.")' in dashboard
    assert '"Choose an empty bed or a plant to swap with."' in dashboard
    assert 'failure_title = "Move not saved"' in dashboard
    assert 'failure_body = "Your plant remains in its original bed."' in dashboard


def test_shared_copy_surfaces_keep_the_canonical_action_vocabulary() -> None:
    dashboard = (ROOT / "ankigarden" / "ui" / "dashboard.py").read_text("utf-8")
    purchases = (ROOT / "ankigarden" / "purchases.py").read_text("utf-8")
    home = (ROOT / "ankigarden" / "ui" / "home_widget.py").read_text("utf-8")

    for copy in (
        "Choose a starter",
        "Open Garden",
        "Use charge",
        "Growth breakdown",
        "Garden appearance",
        "Technical details",
        "Couldn’t save your garden",
        "Move not saved",
    ):
        assert copy in dashboard or copy in home

    for copy in (
        "Price changed",
        "Balance updated",
        "Purchase failed",
        "No Garden Coins were spent.",
    ):
        assert copy in purchases


def test_final_visual_audit_states_do_not_repeat_copy() -> None:
    dashboard = (ROOT / "ankigarden" / "ui" / "dashboard.py").read_text("utf-8")
    scene = (ROOT / "ankigarden" / "ui" / "scene.py").read_text("utf-8")
    collectibles = (ROOT / "ankigarden" / "collectibles.py").read_text("utf-8")

    assert 'duration=basic_duration' in collectibles
    assert '"Image unavailable"' in dashboard
    assert 'self.empty_inventory = EmptyState(\n            "",' in dashboard
    assert 'self.compact_summary_card.hide()' in dashboard
    assert 'title=failure_title' in dashboard
    assert 'or self._interaction.drag_origin_slot is None' in scene
