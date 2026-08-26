from __future__ import annotations

import os

import pytest


pytestmark = pytest.mark.release_evidence


def test_live_qt_narrow_content_activates_one_safety_scroll_when_available(
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

    dialog = GardenDialog(owner, "Narrow content fit", show_close=False)
    scroll = QScrollArea(dialog)
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    content = QWidget()
    content.setMinimumSize(620, 420)
    content_layout = QVBoxLayout(content)
    copy = QLabel("A width-clamped content dialog must expose one safety viewport.")
    copy.setWordWrap(True)
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

    assert dialog.width() == 500
    assert dialog.property("contentScreenLimited") is True
    assert dialog.property("safetyScrollActive") is True
    assert dialog.active_vertical_scroll_regions() == (scroll,)
    assert scroll.property("dialogOverflowOwner") is True

    dialog.close()
    owner.close()
    dialog.deleteLater()
    owner.deleteLater()
    application.processEvents()
