from __future__ import annotations

import os
from types import SimpleNamespace

import pytest


pytestmark = pytest.mark.release_evidence


def test_live_qt_small_screen_content_keeps_one_safety_scroll_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANKI_GARDEN_SKIP_STARTUP", "1")
    monkeypatch.setenv(
        "QT_QPA_PLATFORM",
        os.environ.get("QT_QPA_PLATFORM", "offscreen"),
    )
    try:
        from aqt.qt import (
            QApplication,
            QLabel,
            QScrollArea,
            QRect,
            QVBoxLayout,
            QWidget,
            Qt,
        )
        from ankigarden.ui.dashboard import GardenDialog
        from ankigarden.ui.dialog_foundations import DialogSizeClass
    except (ImportError, ModuleNotFoundError):
        pytest.skip("Anki's Qt runtime is not installed in the unit-test environment")

    application = QApplication.instance() or QApplication([])
    owner = QWidget()
    owner.resize(1_000, 800)
    owner.show()
    monkeypatch.setattr(owner, "screen", lambda: SimpleNamespace(
        availableGeometry=lambda: QRect(0, 0, 420, 300),
    ))

    dialog = GardenDialog(owner, "Narrow content fit", show_close=False)
    scroll = QScrollArea(dialog)
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    content = QWidget()
    content.setMinimumWidth(620)
    content_layout = QVBoxLayout(content)
    copy = QLabel("A width-clamped content dialog must expose one safety viewport.")
    copy.setWordWrap(True)
    copy.setMinimumHeight(420)
    content_layout.addWidget(copy)
    scroll.setWidget(content)
    dialog.set_body_widget(scroll)
    dialog.register_scroll_region(scroll)
    dialog.apply_size_policy(DialogSizeClass.TRANSACTION)
    dialog.apply_view_size_profile("simple")
    dialog.show()
    application.processEvents()

    dialog.fit_content_to_family(preserve_transition=False)
    application.processEvents()

    assert dialog.width() < content.minimumWidth()
    assert dialog.property("contentScreenLimited") is True
    assert dialog.property("safetyScrollActive") is True
    assert dialog.active_vertical_scroll_regions() == (scroll,)
    assert scroll.property("dialogOverflowOwner") is True

    previous_range = scroll.verticalScrollBar().maximum()

    # Catalogs add and remove whole groups before the event loop settles.
    # Their surviving descendants must still participate in content fitting.
    for index in range(20):
        transient = QLabel(f"Temporary row {index}", content)
        transient.setParent(None)
        transient.deleteLater()
    added = QLabel("New catalog content", content)
    content_layout.addWidget(added)
    application.processEvents()
    added.setMinimumHeight(800)
    application.processEvents()
    dialog.fit_content_to_family(preserve_transition=False)
    application.processEvents()
    assert dialog.active_vertical_scroll_regions() == (scroll,)
    assert scroll.verticalScrollBar().maximum() > previous_range

    dialog.close()
    owner.close()
    dialog.deleteLater()
    owner.deleteLater()
    application.processEvents()
