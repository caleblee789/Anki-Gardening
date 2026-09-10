"""Shared, focus-safe shell and rows for already-applied Garden rewards."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from .icons import garden_icon
from .reward_rarity import apply_reward_treatment, reward_treatment, rarity_badge_style
from .theme import GARDEN_THEME, apply_tabular_numerals


def receipt_progress_card(parent: Any, artwork: Any, title: str, text: str, *,
                          progress_percent: int | None, coins: int, palette: dict[str, str],
                          full_bloom: bool = False, growth_gain: str = "", stage_change: str = "") -> Any:
    """One illustrated journey and its committed progression reward."""
    from aqt.qt import QFrame, QHBoxLayout, QLabel, QProgressBar, Qt, QVBoxLayout
    frame = QFrame(parent)
    frame.setProperty("receiptProgressCard", True)
    frame.setStyleSheet(
        f"QFrame[receiptProgressCard='true'] {{background:{palette['receipt_secondary_surface']};"
        f"border:1px solid {palette['receipt_border_strong']};border-radius:10px;}}"
    )
    row = QHBoxLayout(frame)
    row.setContentsMargins(10, 9, 10, 9)
    row.setSpacing(10)
    row.addWidget(artwork, 0, Qt.AlignmentFlag.AlignTop)
    copy = QVBoxLayout()
    copy.setSpacing(4)
    heading = QHBoxLayout()
    name = QLabel(title, frame)
    name.setWordWrap(True)
    name.setStyleSheet(f"color:{palette['text_primary']};font-size:14px;font-weight:600;background:transparent;border:0;")
    heading.addWidget(name, 1)
    if growth_gain:
        gain = QLabel(growth_gain, frame)
        gain.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        gain.setStyleSheet(f"color:{palette['growth_accent']};font-size:14px;font-weight:600;background:transparent;border:0;")
        apply_tabular_numerals(gain)
        heading.addWidget(gain, 0, Qt.AlignmentFlag.AlignTop)
    if full_bloom:
        treatment = reward_treatment(full_bloom=True)
        apply_reward_treatment(frame, treatment, artwork=artwork)
        if treatment.label.casefold() not in title.casefold():
            badge = QLabel(treatment.label, frame)
            badge.setProperty("receiptRarityBadge", True)
            badge.setStyleSheet(rarity_badge_style(treatment))
            heading.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
    if coins > 0 and not growth_gain:
        reward = receipt_resource_values(frame, coins=coins, compact=True)
        reward.setProperty("receiptProgressCoins", coins)
        heading.addWidget(reward, 0, Qt.AlignmentFlag.AlignTop)
    copy.addLayout(heading)
    description = QLabel(text, frame)
    description.setWordWrap(True)
    description.setTextFormat(Qt.TextFormat.PlainText)
    description.setStyleSheet(f"color:{palette['text_secondary']};font-size:13px;font-weight:400;background:transparent;border:0;")
    if growth_gain:
        description.setVisible(bool(text))
    copy.addWidget(description)
    progress = QProgressBar(frame)
    progress.setRange(0, 100)
    progress.setValue(max(0, min(100, int(progress_percent or 0))))
    progress.setTextVisible(False)
    progress.setFixedHeight(5)
    progress.setStyleSheet(f"QProgressBar {{background:{palette['divider']};border:0;border-radius:2px;}} "
                          f"QProgressBar::chunk {{background:{palette['receipt_primary_mint']};border-radius:2px;}}")
    progress.setVisible(progress_percent is not None and not full_bloom)
    copy.addWidget(progress)
    if stage_change:
        stage = QLabel(stage_change, frame)
        stage.setWordWrap(True)
        stage.setTextFormat(Qt.TextFormat.PlainText)
        stage.setStyleSheet(description.styleSheet())
        copy.addWidget(stage)
    if coins > 0 and growth_gain:
        reward = receipt_resource_values(frame, coins=coins, compact=True)
        reward.setProperty("receiptProgressCoins", coins)
        copy.addWidget(reward, 0, Qt.AlignmentFlag.AlignRight)
    row.addLayout(copy, 1)
    return SimpleNamespace(widget=frame, progress=progress, title=name, description=description)


def receipt_resource_values(parent: Any, *, coins: int = 0, growth_units: int = 0, compact: bool = False) -> Any:
    """One icon-adjacent amount per resource, shared by both summary menus."""
    from aqt.qt import QFrame, QHBoxLayout, QLabel, Qt
    from .session_summary import format_growth_units
    frame = QFrame(parent)
    frame.setStyleSheet("QFrame {background:transparent;border:0;}")
    row = QHBoxLayout(frame)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(4)
    for kind, text in (("coin", (f"+{coins:,}" if compact else f"+{coins:,} Coins") if coins else ""),
                       ("growth", (format_growth_units(growth_units, signed=True) + ("" if compact else " Growth")) if growth_units else "")):
        if not text:
            continue
        icon = QLabel(frame)
        icon.setFixedSize(14, 14)
        icon.setPixmap(garden_icon(kind).pixmap(14, 14))
        row.addWidget(icon, 0, Qt.AlignmentFlag.AlignVCenter)
        value = QLabel(text, frame)
        value.setStyleSheet(f"color:{GARDEN_THEME['coin_accent' if kind == 'coin' else 'growth_accent']};font-size:14px;font-weight:600;")
        apply_tabular_numerals(value)
        row.addWidget(value)
    row.addStretch(1)
    return frame


def build_receipt_shell(owner: Any, title: str, close: Any, palette: dict[str, str], *, prefix: str) -> Any:
    from aqt.qt import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSize, Qt, QVBoxLayout

    owner.setProperty("rewardReceipt", True)
    root = QVBoxLayout(owner)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)
    header = QFrame(owner)
    header.setObjectName(f"{prefix}Header")
    header.setProperty("receiptHeader", True)
    header.setMinimumHeight(44)
    row = QHBoxLayout(header)
    row.setContentsMargins(16, 6, 16, 6)
    row.setSpacing(8)
    label = QLabel(title, header)
    label.setProperty("receiptTitle", True)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setMinimumWidth(0)
    row.addWidget(label, 1)
    close_button = QPushButton("", header)
    close_button.setObjectName(f"{prefix}Close")
    close_button.setProperty("receiptClose", True)
    close_button.setFixedSize(32, 32)
    close_button.setIcon(garden_icon("close", color=palette["text_secondary"]))
    close_button.setIconSize(QSize(16, 16))
    close_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    close_button.setAccessibleName(f"Close {title.lower()}")
    close_button.clicked.connect(close)
    row.addWidget(close_button)
    root.addWidget(header)
    scroll = QScrollArea(owner)
    scroll.setObjectName(f"{prefix}Scroll")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    root.addWidget(scroll, 1)
    footer = QFrame(owner)
    footer.setObjectName(f"{prefix}Footer")
    footer.setProperty("receiptFooter", True)
    footer.setMinimumHeight(48)
    actions = QHBoxLayout(footer)
    actions.setContentsMargins(16, 8, 16, 8)
    actions.setSpacing(8)
    root.addWidget(footer)
    return SimpleNamespace(root=root, header=header, title=label, close=close_button,
                           scroll=scroll, footer=footer, actions=actions)


def receipt_button(parent: Any, text: str, callback: Any, *, primary: bool) -> Any:
    from aqt.qt import QPushButton, Qt
    button = QPushButton(text, parent)
    button.setProperty("receiptPrimary" if primary else "receiptSecondary", True)
    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    button.setMinimumHeight(32)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.clicked.connect(callback)
    return button


def reward_discovery_count(source: Any) -> int:
    """Compatibility entrypoint for the shared Items & finds counter."""
    from ..reward_counts import reward_drop_count
    return reward_drop_count(source)


def receipt_growth_breakdown(parent: Any, *, total_units: int, plant_units: int,
                             shared_units: int = 0, stored_units: int = 0,
                             project_units: int = 0, transferred_units: int = 0) -> Any:
    """One non-overlapping view of recorded Growth, shared by both receipts."""
    from aqt.qt import QFrame, QHBoxLayout, QLabel, QVBoxLayout, Qt
    from .session_summary import format_growth_units
    frame = QFrame(parent)
    box = QVBoxLayout(frame)
    box.setContentsMargins(0, 0, 0, 0)
    box.setSpacing(4)
    box.addWidget(receipt_section_heading(frame, "Growth breakdown"))
    allocated = sum(max(0, int(n)) for n in (plant_units, stored_units, project_units))
    rows = [("To plants", plant_units), ("Stored Growth", stored_units), ("Growth projects", project_units)]
    if total_units > allocated:
        rows.append(("Other recorded Growth", total_units - allocated))
    for name, units in rows:
        if units <= 0:
            continue
        row = QHBoxLayout()
        label = QLabel(name, frame)
        label.setProperty("receiptEventDetail", True)
        row.addWidget(label, 1)
        amount = QLabel(format_growth_units(units, signed=True), frame)
        amount.setProperty("receiptEventDetail", True)
        apply_tabular_numerals(amount)
        row.addWidget(amount, 0, Qt.AlignmentFlag.AlignRight)
        box.addLayout(row)
        if name == "To plants" and shared_units:
            detail = QLabel(f"Includes {format_growth_units(shared_units)} Shared Growth", frame)
            detail.setProperty("receiptEventDetail", True)
            detail.setWordWrap(True)
            detail.setContentsMargins(16, 0, 0, 2)
            box.addWidget(detail)
    if transferred_units:
        detail = QLabel(f"{format_growth_units(transferred_units)} Stored Growth applied from reserve", frame)
        detail.setProperty("receiptEventDetail", True)
        detail.setWordWrap(True)
        box.addWidget(detail)
    frame.setProperty("growthBreakdownEarnedUnits", int(total_units))
    frame.setProperty("growthBreakdownAllocatedUnits", allocated)
    return frame


def receipt_metric(parent: Any, label: str, value: str, icon_name: str,
                   palette: dict[str, str], *, compact: bool = False) -> Any:
    from decimal import Decimal, InvalidOperation
    from aqt.qt import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, Qt

    class AmountLabel(QLabel):
        """Fit compact HUD totals while preserving their exact accessible value."""
        def setText(self, text: str) -> None:
            self._full_text = str(text)
            self.setAccessibleName(self._full_text)
            self._fit_text()

        def _fit_text(self) -> None:
            full = getattr(self, "_full_text", "")
            fitted = full
            available = max(1, self.contentsRect().width())
            if compact and self.fontMetrics().horizontalAdvance(full) > available:
                try:
                    number = Decimal(full.replace(",", ""))
                    sign = "+" if full.startswith("+") else "-" if number < 0 else ""
                    for scale, suffix in ((10**12, "T"), (10**9, "B"), (10**6, "M"), (10**3, "K")):
                        if abs(number) < scale:
                            continue
                        for places in (2, 1, 0):
                            digits = f"{abs(number) / scale:.{places}f}"
                            if places:
                                digits = digits.rstrip("0").rstrip(".")
                            candidate = sign + digits + suffix
                            if self.fontMetrics().horizontalAdvance(candidate) <= available:
                                fitted = candidate
                                break
                        break
                except InvalidOperation:
                    pass
                fitted = self.fontMetrics().elidedText(fitted, Qt.TextElideMode.ElideRight, available)
            super().setText(fitted)
            self.setToolTip(full if fitted != full else "")
            if compact:
                # HUD labels pass mouse events through to their tile, so the
                # exact amount must also be available on that hover target.
                tile.setAccessibleName(f"{label}: {full}")
                tooltip = f"{label}: {full}" if fitted != full else ""
                if label == "Items & finds":
                    tooltip = "\n".join(filter(None, (tooltip, "Find events and item or unlock awards")))
                tile.setToolTip(tooltip)

        def resizeEvent(self, event: Any) -> None:
            super().resizeEvent(event)
            self._fit_text()

        def changeEvent(self, event: Any) -> None:
            super().changeEvent(event)
            self._fit_text()

    color = (palette["coin_accent"] if icon_name == "coin" else
             palette["growth_accent"] if icon_name == "growth" else
             palette.get("find_accent", palette["text_secondary"]))
    tile = QFrame(parent)
    tile.setProperty("receiptMetric", True)
    tile.setProperty("receiptMetricCompact", compact)
    tile.setMinimumWidth(0)
    tile.setSizePolicy(QSizePolicy.Policy.Ignored,
                       QSizePolicy.Policy.Fixed if compact else QSizePolicy.Policy.Preferred)
    tile.setAccessibleName(f"{label}: {value}")
    if label == "Items & finds":
        tile.setToolTip("Find events and item or unlock awards")
    tile.setStyleSheet(
        f"QFrame[receiptMetric='true'] {{background:{palette['raised_surface']};"
        f"border:1px solid {palette['subtle_border']};border-radius:8px;}}"
    )
    layout = QVBoxLayout(tile)
    layout.setContentsMargins(6 if compact else 8, 6, 6 if compact else 8, 6)
    layout.setSpacing(4)
    caption = QLabel(label, tile)
    caption.setProperty("receiptMetricLabel", True)
    caption.setMinimumWidth(0)
    caption.setWordWrap(True)
    caption.setTextFormat(Qt.TextFormat.PlainText)
    caption.setStyleSheet(f"color:{palette['text_secondary']};font-size:13px;font-weight:500;background:transparent;border:0;")
    if compact:
        caption.setMinimumHeight(caption.fontMetrics().lineSpacing() * 2)
        caption.setAlignment(Qt.AlignmentFlag.AlignTop)
    layout.addWidget(caption)
    number_row = QHBoxLayout()
    number_row.setContentsMargins(0, 0, 0, 0)
    number_row.setSpacing(4)
    icon = QLabel(tile)
    icon.setFixedSize(12 if compact else 14, 12 if compact else 14)
    icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
    icon.setPixmap(garden_icon(icon_name, color=color).pixmap(icon.width(), icon.height()))
    icon.setStyleSheet("background:transparent;border:0;")
    number_row.addWidget(icon, 0, Qt.AlignmentFlag.AlignVCenter)
    amount = AmountLabel(tile)
    amount.setTextFormat(Qt.TextFormat.PlainText)
    amount.setMinimumWidth(0)
    amount.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    amount.setProperty("receiptMetricValue", True)
    amount.setStyleSheet(f"color:{color};font-size:{13 if compact else 18}px;font-weight:600;background:transparent;border:0;")
    apply_tabular_numerals(amount)
    amount.setText(value)
    number_row.addWidget(amount, 1)
    layout.addLayout(number_row)
    return SimpleNamespace(widget=tile, value=amount, caption=caption, icon=icon)



def receipt_metrics_layout(parent: Any = None) -> Any:
    """Keep reward totals in a row, stacking them when larger text needs space."""
    from aqt.qt import QBoxLayout, QHBoxLayout, QLabel

    class MetricsLayout(QHBoxLayout):
        def setGeometry(self, rect: Any) -> None:
            minimum_widths = []
            for index in range(self.count()):
                tile = self.itemAt(index).widget()
                if tile is None:
                    continue
                labels = tile.findChildren(QLabel)
                caption = next((label for label in labels if label.property("receiptMetricLabel")), None)
                amount = next((label for label in labels if label.property("receiptMetricValue")), None)
                if caption is None or amount is None:
                    continue
                margins = tile.layout().contentsMargins()
                caption_parts = (caption.text().split() if tile.property("receiptMetricCompact")
                                 else [caption.text()])
                caption_width = max((caption.fontMetrics().horizontalAdvance(part)
                                     for part in caption_parts), default=0)
                number_row = tile.layout().itemAt(1).layout()
                icon = number_row.itemAt(0).widget()
                # Compact captions can wrap; exact amounts determine when the
                # three-column group needs to stack.
                amount_width = (amount.fontMetrics().horizontalAdvance(amount.text())
                                + icon.width() + number_row.spacing())
                minimum_widths.append(max(caption_width, amount_width) + margins.left() + margins.right())
            margins = self.contentsMargins()
            needed = (max(minimum_widths, default=0) * len(minimum_widths)
                      + max(0, len(minimum_widths) - 1) * self.spacing()
                      + margins.left() + margins.right())
            direction = (QBoxLayout.Direction.TopToBottom if needed > rect.width()
                         else QBoxLayout.Direction.LeftToRight)
            if self.direction() != direction:
                self.setDirection(direction)
            super().setGeometry(rect)

    return MetricsLayout(parent) if parent is not None else MetricsLayout()

def reward_section_heading_style() -> str:
    """One small heading treatment for receipt and reviewer reward sections."""
    return f"color:{GARDEN_THEME['text_primary']};font-size:14px;font-weight:600;background:transparent;border:0;"


def receipt_section_heading(parent: Any, text: str) -> Any:
    from aqt.qt import QLabel, Qt
    label = QLabel(text, parent)
    label.setProperty("receiptSection", True)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setStyleSheet(reward_section_heading_style())
    return label


def receipt_event_row(parent: Any, artwork: Any, title: str, *, detail: str = "", milestone: bool = False, reward: Any = None, eyebrow: str = "", rarity_badge: bool = False) -> Any:
    """Lead with the recorded item/event; category headings belong to the list."""
    from aqt.qt import QFrame, QHBoxLayout, QLabel, QVBoxLayout, Qt
    frame = QFrame(parent)
    frame.setProperty("receiptEvent", True)
    frame.setProperty("receiptMilestone", milestone)
    treatment = reward_treatment(reward, full_bloom=milestone)
    row = QHBoxLayout(frame)
    row.setContentsMargins(8, 6, 8, 6)
    row.setSpacing(8)
    row.addWidget(artwork, 0, Qt.AlignmentFlag.AlignVCenter)
    copy = QVBoxLayout()
    copy.setContentsMargins(0, 0, 0, 0)
    copy.setSpacing(3)
    heading = QHBoxLayout()
    heading.setSpacing(6)
    name = QLabel(title, frame)
    name.setProperty("receiptEventTitle", True)
    name.setWordWrap(True)
    name.setMinimumWidth(0)
    name.setTextFormat(Qt.TextFormat.PlainText)
    heading.addWidget(name, 1)
    if ((rarity_badge or milestone or treatment.notable) and treatment.label
            and treatment.label.casefold() not in title.casefold()):
        badge = QLabel(treatment.label, frame)
        badge.setProperty("receiptRarityBadge", True)
        badge.setStyleSheet(rarity_badge_style(treatment))
        heading.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
    copy.addLayout(heading)
    if detail:
        secondary = QLabel(detail, frame)
        secondary.setProperty("receiptEventDetail", True)
        secondary.setWordWrap(True)
        secondary.setMinimumWidth(0)
        secondary.setTextFormat(Qt.TextFormat.PlainText)
        copy.addWidget(secondary)
    row.addLayout(copy, 1)
    apply_reward_treatment(frame, treatment, title=name, artwork=artwork)
    if not treatment.notable:
        frame.setStyleSheet(
            f"QFrame[receiptEvent='true'] {{background:{GARDEN_THEME['raised_surface']};"
            "border:0;border-radius:10px;}"
        )
    return SimpleNamespace(widget=frame, layout=row, copy=copy, title=name)


def receipt_style(p: dict[str, str]) -> str:
    """Use existing Garden tokens; all rules stay inside the add-on receipt."""
    return f"""
    QFrame[rewardReceipt='true'] {{ background:{p['receipt_panel']}; border:1px solid {p['receipt_border']}; border-radius:16px; }}
    QFrame[receiptHeader='true'], QFrame[receiptFooter='true'] {{ background:transparent; border:0; }}
    QFrame[receiptFooter='true'] {{ border-top:1px solid {p['divider']}; }}
    QLabel[receiptTitle='true'] {{ color:{p['text_primary']}; font-size:20px; font-weight:600; }}
    QPushButton[receiptClose='true'] {{ padding:0; border:0; background:transparent; }}
    QPushButton[receiptPrimary='true'] {{ color:{p['action_text']}; background:{p['action_accent']}; border:0; border-radius:9px; padding:0 12px; font-size:13px; font-weight:600; }}
    QPushButton[receiptPrimary='true']:hover {{ background:{p['action_hover']}; }}
    QPushButton[receiptPrimary='true']:pressed {{ background:{p['action_pressed']}; }}
    QPushButton[receiptSecondary='true'] {{ color:{p['text_primary']}; background:transparent; border:1px solid {p['subtle_border']}; border-radius:9px; padding:0 12px; font-size:13px; font-weight:600; }}
    QPushButton[receiptSecondary='true']:hover {{ background:{p['selected_surface']}; }}
    QPushButton[receiptSecondary='true']:pressed {{ background:{p['strong_border']}; }}
    QFrame[receiptMetric='true'], QFrame[receiptEvent='true'] {{ background:transparent; border:0; }}
    QLabel[receiptMetricLabel='true'] {{ color:{p['text_secondary']}; font-size:12px; font-weight:500; }}
    QLabel[receiptMetricValue='true'] {{ font-size:18px; font-weight:600; }}
    QLabel[receiptEventTitle='true'] {{ color:{p['text_primary']}; font-size:14px; font-weight:600; }}
    QLabel[receiptEventDetail='true'] {{ color:{p['text_secondary']}; font-size:13px; }}
    """


def receipt_body_height(body: Any, width: int) -> int:
    """Measure wrapped content at its final width, excluding old scroll height."""
    layout = body.layout()
    if layout is None:
        return 0
    layout.invalidate()
    layout.activate()
    wrapped = layout.totalHeightForWidth(max(1, int(width)))
    return max(1, wrapped if wrapped >= 0 else layout.sizeHint().height())


def fit_receipt_chrome(header: Any, footer: Any, width: int) -> None:
    """Keep receipt titles and actions visible at narrow widths and larger text."""
    from aqt.qt import QBoxLayout

    actions = footer.layout()
    margins = actions.contentsMargins()
    controls = [actions.itemAt(index).widget() for index in range(actions.count())]
    controls = [control for control in controls if control is not None and not control.isHidden()]
    required = (sum(control.sizeHint().width() for control in controls)
                + max(0, len(controls) - 1) * actions.spacing()
                + margins.left() + margins.right())
    actions.setDirection(QBoxLayout.Direction.TopToBottom if required > width
                         else QBoxLayout.Direction.LeftToRight)
    for frame, minimum in ((header, 44), (footer, 48)):
        layout = frame.layout()
        layout.invalidate()
        measured = layout.totalHeightForWidth(max(1, int(width)))
        frame.setFixedHeight(max(minimum, measured if measured >= 0 else layout.sizeHint().height()))
