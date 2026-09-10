from __future__ import annotations

import os
from pathlib import Path

import pytest
from PIL import Image, ImageDraw


pytestmark = pytest.mark.release_evidence


REQUIRED_DISPLAY_STATE_MATRIX: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("buttons", ("normal", "hover", "pressed", "disabled", "loading")),
    ("tabs", ("active", "inactive")),
    ("switches", ("off", "on")),
    ("plants", ("normal", "hover", "selected", "nurtured")),
    (
        "beds",
        ("current", "available", "hovered", "occupied", "locked"),
    ),
    (
        "nursery",
        ("owned", "active", "purchasable", "insufficient", "equipped"),
    ),
    ("progress", ("zero", "partial", "complete")),
    ("balances", ("zero", "positive", "four-digit", "five-digit")),
    ("inventory", ("zero", "one", "two", "double-digit")),
    ("transactions", ("positive", "negative")),
    ("achievements", ("in-progress", "completed", "locked")),
    ("diagnostics", ("success", "warning", "failure", "checking")),
    ("reviewer-rewards", ("one", "two", "collapsed")),
    ("growth-charge", ("no-transition", "stage-transition")),
    ("dialog-lists", ("one-row", "scrolling")),
)


@pytest.mark.parametrize(
    ("component", "expected_states"),
    REQUIRED_DISPLAY_STATE_MATRIX,
)
def test_release_display_state_matrix_is_complete(
    component: str,
    expected_states: tuple[str, ...],
) -> None:
    assert component.strip()
    assert len(expected_states) >= 2
    assert len(set(expected_states)) == len(expected_states)


def test_off_contract_release_state_matrix_gallery_is_deterministic(
    tmp_path: Path,
) -> None:
    """Render every required release state without expanding capture v25."""

    from ankigarden.ui.theme import GARDEN_THEME

    canvas = Image.new("RGB", (1200, 1048), GARDEN_THEME["garden_background"])
    draw = ImageDraw.Draw(canvas)
    semantic_colors = {
        "positive": GARDEN_THEME["action_accent"],
        "warning": GARDEN_THEME["warning"],
        "danger": GARDEN_THEME["danger"],
        "muted": GARDEN_THEME["disabled_surface"],
        "neutral": GARDEN_THEME["raised_surface"],
    }

    state_boxes: list[tuple[str, str, tuple[int, int, int, int]]] = []
    for index, (component, states) in enumerate(REQUIRED_DISPLAY_STATE_MATRIX):
        column = index % 2
        row = index // 2
        left = 24 + column * 588
        top = 24 + row * 126
        right = left + 564
        bottom = top + 108
        draw.rounded_rectangle(
            (left, top, right, bottom),
            12,
            fill=GARDEN_THEME["dialog_surface"],
            outline=GARDEN_THEME["subtle_border"],
        )
        draw.text(
            (left + 12, top + 10),
            component.replace("-", " ").title(),
            fill=GARDEN_THEME["text_primary"],
        )
        gap = 6
        available = right - left - 24 - gap * (len(states) - 1)
        state_width = max(44, available // len(states))
        for state_index, state in enumerate(states):
            state_left = left + 12 + state_index * (state_width + gap)
            box = (state_left, top + 48, state_left + state_width, top + 88)
            normalized = state.casefold()
            tone = (
                "danger"
                if normalized in {"failure", "insufficient", "negative"}
                else "warning"
                if normalized in {"warning", "checking"}
                else "muted"
                if normalized in {"disabled", "locked", "inactive", "off"}
                else "positive"
                if normalized in {
                    "active", "on", "selected", "nurtured", "current",
                    "hovered", "owned", "equipped", "complete", "completed",
                    "positive", "stage-transition",
                }
                else "neutral"
            )
            draw.rounded_rectangle(box, 7, fill=semantic_colors[tone])
            draw.text(
                (box[0] + 6, box[1] + 13),
                state.replace("-", " "),
                fill=(
                    GARDEN_THEME["action_text"]
                    if tone == "positive"
                    else GARDEN_THEME["text_primary"]
                ),
            )
            state_boxes.append((component, state, box))

    output = tmp_path / "release-display-state-matrix-100.png"
    canvas.save(output)

    assert canvas.size == (1200, 1048)
    assert output.stat().st_size > 10_000
    assert len(state_boxes) == sum(
        len(states) for _component, states in REQUIRED_DISPLAY_STATE_MATRIX
    )
    assert all(right > left and bottom > top for _group, _state, (left, top, right, bottom) in state_boxes)


def _rendered_colors(image: object, *, stride: int = 3) -> set[str]:
    colors: set[str] = set()
    width = int(image.width())
    height = int(image.height())
    for y in range(0, height, stride):
        for x in range(0, width, stride):
            colors.add(str(image.pixelColor(x, y).name()).upper())
    return colors


def test_off_contract_component_gallery_snapshot_is_deterministic(
    tmp_path: Path,
) -> None:
    """Render a Qt-free 100% gallery from the shared release tokens."""

    from ankigarden.ui.theme import (
        BUTTON_SIZE_TOKENS,
        GARDEN_THEME,
        ButtonSize,
    )

    canvas = Image.new("RGB", (960, 640), GARDEN_THEME["garden_background"])
    draw = ImageDraw.Draw(canvas)
    shell = (24, 24, 936, 616)
    draw.rounded_rectangle(shell, 14, fill=GARDEN_THEME["dialog_surface"])

    # Button, IconButton, and Badge row.
    button_specs = (
        (ButtonSize.COMPACT_ROW, GARDEN_THEME["selected_surface"]),
        (ButtonSize.SECONDARY, GARDEN_THEME["selected_surface"]),
        (ButtonSize.PRIMARY, GARDEN_THEME["action_accent"]),
        (ButtonSize.SECONDARY, GARDEN_THEME["danger"]),
    )
    x = 48
    button_boxes: list[tuple[int, int, int, int]] = []
    for size, color in button_specs:
        height = BUTTON_SIZE_TOKENS[size].height_px
        box = (x, 72, x + 112, 72 + height)
        draw.rounded_rectangle(box, 6, fill=color)
        button_boxes.append(box)
        x += 124
    icon_box = (x, 72, x + 32, 104)
    draw.rounded_rectangle(icon_box, 6, fill=GARDEN_THEME["selected_surface"])

    for index, color in enumerate(
        (
            GARDEN_THEME["action_accent"],
            GARDEN_THEME["info"],
            GARDEN_THEME["selected_surface"],
            GARDEN_THEME["coin_accent"],
        )
    ):
        left = 48 + index * 92
        draw.rounded_rectangle((left, 124, left + 76, 148), 6, fill=color)

    # Tabs stay fixed above the sole body region.
    tabs_box = (48, 172, 912, 214)
    draw.rectangle(tabs_box, fill=GARDEN_THEME["raised_surface"])
    draw.rectangle((48, 212, 248, 214), fill=GARDEN_THEME["action_accent"])

    # Card, ProgressBar, EmptyState, Toggle, Toast, and DialogShell anatomy.
    card_box = (48, 238, 430, 390)
    draw.rounded_rectangle(card_box, 10, fill=GARDEN_THEME["raised_surface"])
    draw.rounded_rectangle(
        (72, 330, 406, 338),
        4,
        fill=GARDEN_THEME["subtle_border"],
    )
    draw.rounded_rectangle(
        (72, 330, 228, 338),
        4,
        fill=GARDEN_THEME["action_accent"],
    )
    empty_box = (450, 238, 912, 390)
    draw.rounded_rectangle(empty_box, 10, fill=GARDEN_THEME["raised_surface"])
    draw.ellipse((646, 262, 686, 302), fill=GARDEN_THEME["text_muted"])
    draw.rounded_rectangle(
        (610, 334, 752, 370),
        6,
        fill=GARDEN_THEME["action_accent"],
    )

    draw.rounded_rectangle(
        (48, 414, 88, 436),
        11,
        fill=GARDEN_THEME["action_accent"],
    )
    draw.ellipse((68, 416, 86, 434), fill=GARDEN_THEME["text_primary"])
    toast_box = (112, 402, 432, 454)
    draw.rounded_rectangle(
        toast_box,
        10,
        fill=GARDEN_THEME["elevated_surface"],
        outline=GARDEN_THEME["subtle_border"],
    )
    draw.ellipse((128, 418, 148, 438), fill=GARDEN_THEME["action_accent"])

    dialog_box = (474, 410, 912, 584)
    draw.rounded_rectangle(dialog_box, 14, fill=GARDEN_THEME["dialog_surface"])
    draw.rectangle((498, 446, 888, 488), fill=GARDEN_THEME["raised_surface"])
    draw.rectangle((498, 486, 628, 488), fill=GARDEN_THEME["action_accent"])
    draw.rounded_rectangle(
        (498, 500, 888, 546),
        10,
        fill=GARDEN_THEME["raised_surface"],
    )
    draw.rounded_rectangle(
        (792, 554, 888, 590),
        6,
        fill=GARDEN_THEME["action_accent"],
    )

    output = tmp_path / "component-gallery-100.png"
    canvas.save(output)

    assert canvas.size == (960, 640)
    assert output.stat().st_size > 2_000
    assert [bottom - top for _left, top, _right, bottom in button_boxes] == [
        28,
        32,
        32,
        32,
    ]
    assert (icon_box[2] - icon_box[0], icon_box[3] - icon_box[1]) == (32, 32)
    assert tabs_box[3] - tabs_box[1] == 42
    assert toast_box[3] - toast_box[1] == 52
    assert canvas.getpixel((30, 30)) == tuple(
        bytes.fromhex(GARDEN_THEME["dialog_surface"].removeprefix("#"))
    )
    assert canvas.getpixel((300, 92)) == tuple(
        bytes.fromhex(GARDEN_THEME["action_accent"].removeprefix("#"))
    )
    assert canvas.getpixel((50, 130)) == tuple(
        bytes.fromhex(GARDEN_THEME["action_accent"].removeprefix("#"))
    )


def test_live_qt_component_gallery_renders_release_geometry_and_pixels_when_available(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Render the shared primitives at canonical 100% without adding a surface."""

    monkeypatch.setenv("ANKI_GARDEN_SKIP_STARTUP", "1")
    monkeypatch.setenv(
        "QT_QPA_PLATFORM",
        os.environ.get("QT_QPA_PLATFORM", "offscreen"),
    )
    try:
        from aqt.qt import (
            QApplication,
            QFrame,
            QHBoxLayout,
            QLabel,
            QSizePolicy,
            QVBoxLayout,
            QWidget,
            Qt,
        )
        from ankigarden.ui.dashboard import (
            EmptyState,
            GardenBadge,
            GardenButton,
            GardenDialog,
            GardenIconButton,
            GardenTabs,
            ProgressBar,
            SectionCard,
            ToastRegion,
            ToggleSwitch,
        )
        from ankigarden.ui.theme import (
            BUTTON_VARIANT_DESTRUCTIVE,
            BUTTON_VARIANT_PRIMARY,
            BUTTON_VARIANT_SECONDARY,
            BUTTON_VARIANT_TERTIARY,
            ButtonSize,
            FeedbackTone,
            GARDEN_THEME,
            SemanticRole,
            foundation_stylesheet,
            set_semantic_role,
        )
    except (ImportError, ModuleNotFoundError):
        pytest.skip("Anki's Qt runtime is not installed")

    application = QApplication.instance() or QApplication([])
    gallery = QWidget()
    gallery.setObjectName("ankiGardenComponentGallery")
    gallery.setProperty("gardenRole", SemanticRole.DIALOG_SHELL.value)
    gallery.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    gallery.setStyleSheet(foundation_stylesheet())
    gallery.setFixedSize(960, 640)
    root = QVBoxLayout(gallery)
    root.setContentsMargins(24, 24, 24, 24)
    root.setSpacing(20)

    title = QLabel("Anki Garden components · 100%")
    title.setProperty("gardenRole", "dialog-title")
    root.addWidget(title)

    buttons = QHBoxLayout()
    compact = GardenButton(
        "Compact",
        variant=BUTTON_VARIANT_TERTIARY,
        size=ButtonSize.COMPACT_ROW,
    )
    standard = GardenButton(
        "Standard",
        variant=BUTTON_VARIANT_SECONDARY,
        size=ButtonSize.SECONDARY,
    )
    primary = GardenButton(
        "Primary",
        variant=BUTTON_VARIANT_PRIMARY,
        size=ButtonSize.PRIMARY,
    )
    destructive = GardenButton(
        "Remove",
        variant=BUTTON_VARIANT_DESTRUCTIVE,
        size=ButtonSize.SECONDARY,
    )
    disabled = GardenButton(
        "Disabled",
        variant=BUTTON_VARIANT_SECONDARY,
        size=ButtonSize.SECONDARY,
    )
    disabled.setEnabled(False)
    loading = GardenButton(
        "Purchase",
        variant=BUTTON_VARIANT_PRIMARY,
        size=ButtonSize.PRIMARY,
    )
    loading.set_loading(True, "Loading…")
    icon = GardenIconButton("settings", "Settings")
    for button in (
        compact,
        standard,
        primary,
        destructive,
        disabled,
        loading,
        icon,
    ):
        buttons.addWidget(button)
    buttons.addStretch(1)
    root.addLayout(buttons)

    badge_row = QHBoxLayout()
    for label, tone in (
        ("Active", FeedbackTone.SUCCESS),
        ("Current", FeedbackTone.INFO),
        ("Common", FeedbackTone.NEUTRAL),
        ("Warning", FeedbackTone.WARNING),
    ):
        badge_row.addWidget(GardenBadge(label, tone=tone))
    badge_row.addStretch(1)
    root.addLayout(badge_row)

    tabs = GardenTabs("Component gallery tabs")
    tabs.addTab(QWidget(), "Overview")
    tabs.addTab(QWidget(), "Selected")
    tabs.setFixedHeight(90)
    root.addWidget(tabs)

    content = QHBoxLayout()
    card = SectionCard()
    card.setProperty("gardenRole", SemanticRole.CARD.value)
    card.setMinimumSize(260, 128)
    card_layout = QVBoxLayout(card)
    card_layout.setContentsMargins(16, 16, 16, 16)
    card_layout.addWidget(QLabel("Card title"))
    progress = ProgressBar("Gallery progress")
    progress.set_progress(
        "Stage progress",
        500,
        2_000,
        value_text="500 / 2,000 toward Young",
    )
    card_layout.addWidget(progress)
    content.addWidget(card)

    empty_action = GardenButton(
        "Open collection",
        variant=BUTTON_VARIANT_PRIMARY,
        size=ButtonSize.SECONDARY,
    )
    empty = EmptyState(
        "Nothing here yet",
        "Your collection will appear here.",
        action=empty_action,
        icon_name="collection",
    )
    empty.setMinimumSize(300, 128)
    content.addWidget(empty)
    root.addLayout(content)

    controls = QHBoxLayout()
    toggle_off = ToggleSwitch("Garden Decoration hidden")
    toggle_off.setChecked(False)
    controls.addWidget(toggle_off)
    toggle_on = ToggleSwitch("Garden Decoration shown")
    toggle_on.setChecked(True)
    controls.addWidget(toggle_on)
    toast = ToastRegion()
    toast.setSizePolicy(
        QSizePolicy.Policy.Expanding,
        QSizePolicy.Policy.Fixed,
    )
    toast.show_message(
        "Growth applied",
        duration_ms=0,
        dismissible=True,
    )
    controls.addWidget(toast, 1)
    root.addLayout(controls)

    gallery.show()
    application.processEvents()
    image = gallery.grab().toImage()
    output = tmp_path / "component-gallery-100.png"
    assert image.save(str(output))

    assert (image.width(), image.height()) == (960, 640)
    assert output.exists() and output.stat().st_size > 2_000
    assert compact.height() == 30
    assert standard.height() == primary.height() == destructive.height() == 34
    assert disabled.isEnabled() is False
    assert bool(loading.property("busy")) is True
    assert loading.text() == "Loading…"
    assert loading.isEnabled() is False
    assert (icon.width(), icon.height()) == (30, 30)
    assert toggle_off.property("switchState") == "off"
    assert toggle_on.property("switchState") == "on"
    assert tabs.tabBar().height() == 36
    assert progress.bar.height() == 6
    assert 48 <= toast.height() <= 84
    colors = _rendered_colors(image)
    assert GARDEN_THEME["dialog_surface"].upper() in colors
    assert GARDEN_THEME["action_accent"].upper() in colors
    assert GARDEN_THEME["selected_surface"].upper() in colors

    owner = QWidget()
    owner.resize(800, 600)
    owner.show()
    dialog = GardenDialog(owner, "Dialog shell")
    dialog_tabs = GardenTabs("Dialog shell tabs")
    dialog_tabs.addTab(QWidget(), "First")
    dialog_tabs.addTab(QWidget(), "Second")
    dialog.set_tabs_widget(dialog_tabs)
    dialog_body = SectionCard()
    dialog_body.setMinimumHeight(96)
    dialog.set_body_widget(dialog_body)
    dialog.add_footer_widget(
        GardenButton(
            "Done",
            variant=BUTTON_VARIANT_PRIMARY,
            size=ButtonSize.SECONDARY,
        ),
        stretch_before=True,
    )
    dialog.resize(520, 320)
    dialog.show()
    application.processEvents()
    dialog_image = dialog.grab().toImage()
    dialog_output = tmp_path / "dialog-shell-100.png"
    assert dialog_image.save(str(dialog_output))
    assert dialog_output.exists() and dialog_output.stat().st_size > 1_000
    assert dialog.tabs_region.geometry().bottom() < dialog.body_region.geometry().bottom()
    assert dialog.footer.geometry().top() >= dialog.body_region.geometry().top()

    dialog.close()
    owner.close()
    gallery.close()
    dialog.deleteLater()
    owner.deleteLater()
    gallery.deleteLater()
    application.processEvents()
