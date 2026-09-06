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


@pytest.mark.parametrize("font_pixels", (13, 20, 26))
def test_shared_actions_fit_enlarged_text_and_release_unused_width(monkeypatch, font_pixels):
    """Ordinary and stretched actions keep their complete label readable."""
    monkeypatch.setenv("ANKI_GARDEN_SKIP_STARTUP", "1")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    try:
        from aqt.qt import QApplication, QPushButton, QVBoxLayout, QWidget
        from ankigarden.ui.dashboard import set_button_size
        from ankigarden.ui.theme import ButtonSize, foundation_stylesheet
    except (ImportError, ModuleNotFoundError):
        pytest.skip("Anki's Qt runtime is not installed")
    app = QApplication.instance() or QApplication([])
    owner = QWidget()
    owner.setStyleSheet(foundation_stylesheet())
    layout = QVBoxLayout(owner)
    buttons = []
    for stretch in (False, True):
        button = QPushButton("Buy and use next", owner)
        set_button_size(button, ButtonSize.PRIMARY, allow_horizontal_stretch=stretch)
        button.setStyleSheet(f"font-size: {font_pixels}px;")
        layout.addWidget(button)
        buttons.append(button)
    owner.show()
    try:
        for _ in range(6):
            app.processEvents()
        for button in buttons:
            assert button.font().pixelSize() == font_pixels
            assert button.height() >= button.fontMetrics().lineSpacing() + 8
            assert button.width() >= button.fontMetrics().horizontalAdvance(button.text()) + 32
        initial = buttons[0].minimumWidth()
        buttons[0].setText("Buy")
        buttons[0].setStyleSheet(f"font-size: {font_pixels}px; font-weight: 600;")
        for _ in range(6):
            app.processEvents()
        assert buttons[0].minimumWidth() < initial
    finally:
        owner.close()
        owner.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("font_pixels", (14, 21, 28))
def test_today_totals_reflow_without_clipping_at_larger_text(monkeypatch, font_pixels):
    monkeypatch.setenv("ANKI_GARDEN_SKIP_STARTUP", "1")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    try:
        from aqt.qt import QApplication, QLabel
        from ankigarden.ui.dashboard import StatSummary
    except (ImportError, ModuleNotFoundError):
        pytest.skip("Anki's Qt runtime is not installed")
    app = QApplication.instance() or QApplication([])
    summary = StatSummary([("Cards studied", "120"), ("Growth earned", "6,840", "growth"), ("Garden Finds", "5")])
    summary.setStyleSheet(f"QLabel {{ font-size: {font_pixels}px; }}")
    summary.resize(340, 480)
    summary.show()
    try:
        for _ in range(6):
            app.processEvents()
        for label in summary.findChildren(QLabel):
            if label.text():
                assert label.width() >= label.fontMetrics().horizontalAdvance(label.text())
                assert label.height() >= label.fontMetrics().tightBoundingRect(label.text()).height()
                assert summary.rect().contains(label.rect().translated(label.mapTo(summary, label.rect().topLeft())))
    finally:
        summary.close()
        summary.deleteLater()
        app.processEvents()
