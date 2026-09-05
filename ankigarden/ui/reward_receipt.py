"""Shared, focus-safe shell and rows for already-applied Garden rewards."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from .icons import garden_icon
from .theme import apply_tabular_numerals


def build_receipt_shell(owner: Any, title: str, close: Any, palette: dict[str, str], *, prefix: str) -> Any:
    from aqt.qt import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSize, Qt, QVBoxLayout

    owner.setProperty("rewardReceipt", True)
    root = QVBoxLayout(owner)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)
    header = QFrame(owner)
    header.setObjectName(f"{prefix}Header")
    header.setProperty("receiptHeader", True)
    header.setFixedHeight(44)
    row = QHBoxLayout(header)
    row.setContentsMargins(16, 6, 16, 6)
    row.setSpacing(8)
    art = QLabel(header)
    art.setFixedSize(20, 20)
    art.setPixmap(garden_icon("growth", color=palette["growth_accent"]).pixmap(20, 20))
    row.addWidget(art)
    label = QLabel(title, header)
    label.setProperty("receiptTitle", True)
    label.setTextFormat(Qt.TextFormat.PlainText)
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
    footer.setFixedHeight(48)
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
    button.setFixedHeight(32)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.clicked.connect(callback)
    return button


def receipt_metric(parent: Any, label: str, value: str, icon_name: str, palette: dict[str, str]) -> Any:
    from aqt.qt import QFrame, QHBoxLayout, QLabel, QVBoxLayout, Qt
    tile = QFrame(parent)
    tile.setProperty("receiptMetric", True)
    tile.setMinimumWidth(0)
    tile.setAccessibleName(f"{label}: {value}")
    layout = QVBoxLayout(tile)
    layout.setContentsMargins(8, 6, 8, 6)
    layout.setSpacing(4)
    heading = QHBoxLayout()
    heading.setSpacing(4)
    color = palette["coin_accent"] if icon_name == "coin" else palette["growth_accent"] if icon_name == "growth" else palette["text_secondary"]
    icon = QLabel(tile)
    icon.setFixedSize(14, 14)
    icon.setPixmap(garden_icon(icon_name, color=color).pixmap(14, 14))
    heading.addWidget(icon)
    caption = QLabel(label, tile)
    caption.setProperty("receiptMetricLabel", True)
    caption.setMinimumWidth(0)
    caption.setWordWrap(True)
    heading.addWidget(caption, 1)
    layout.addLayout(heading)
    amount = QLabel(value, tile)
    amount.setTextFormat(Qt.TextFormat.PlainText)
    amount.setProperty("receiptMetricValue", True)
    amount.setStyleSheet(f"color:{color};")
    apply_tabular_numerals(amount)
    layout.addWidget(amount)
    return SimpleNamespace(widget=tile, value=amount, caption=caption)


def receipt_event_row(parent: Any, artwork: Any, title: str, *, detail: str = "", milestone: bool = False) -> Any:
    from aqt.qt import QFrame, QHBoxLayout, QLabel, QVBoxLayout, Qt
    frame = QFrame(parent)
    frame.setProperty("receiptEvent", True)
    frame.setProperty("receiptMilestone", milestone)
    row = QHBoxLayout(frame)
    row.setContentsMargins(8, 6, 8, 6)
    row.setSpacing(8)
    row.addWidget(artwork, 0, Qt.AlignmentFlag.AlignVCenter)
    copy = QVBoxLayout()
    copy.setContentsMargins(0, 0, 0, 0)
    copy.setSpacing(3)
    name = QLabel(title, frame)
    name.setProperty("receiptEventTitle", True)
    name.setWordWrap(True)
    name.setTextFormat(Qt.TextFormat.PlainText)
    copy.addWidget(name)
    if detail:
        secondary = QLabel(detail, frame)
        secondary.setProperty("receiptEventDetail", True)
        secondary.setWordWrap(True)
        secondary.setTextFormat(Qt.TextFormat.PlainText)
        copy.addWidget(secondary)
    row.addLayout(copy, 1)
    return SimpleNamespace(widget=frame, layout=row, copy=copy, title=name)


def receipt_style(p: dict[str, str]) -> str:
    """Use existing Garden tokens; all rules stay inside the add-on receipt."""
    return f"""
    QFrame[rewardReceipt='true'] {{ background:{p['receipt_panel']}; border:1px solid {p['receipt_border']}; border-radius:16px; }}
    QFrame[receiptHeader='true'], QFrame[receiptFooter='true'] {{ background:transparent; border:0; }}
    QFrame[receiptFooter='true'] {{ border-top:1px solid {p['divider']}; }}
    QLabel[receiptTitle='true'] {{ color:{p['text_primary']}; font-size:16px; font-weight:600; }}
    QPushButton[receiptClose='true'] {{ padding:0; border:0; background:transparent; }}
    QPushButton[receiptPrimary='true'] {{ color:{p['action_text']}; background:{p['action_accent']}; border:0; border-radius:9px; padding:0 12px; font-size:13px; font-weight:600; }}
    QPushButton[receiptPrimary='true']:hover {{ background:{p['action_hover']}; }}
    QPushButton[receiptPrimary='true']:pressed {{ background:{p['action_pressed']}; }}
    QPushButton[receiptSecondary='true'] {{ color:{p['text_primary']}; background:transparent; border:1px solid {p['subtle_border']}; border-radius:9px; padding:0 12px; font-size:13px; font-weight:600; }}
    QPushButton[receiptSecondary='true']:hover {{ background:{p['selected_surface']}; }}
    QPushButton[receiptSecondary='true']:pressed {{ background:{p['strong_border']}; }}
    QFrame[receiptMetric='true'], QFrame[receiptEvent='true'] {{ background:transparent; border:0; }}
    QFrame[receiptMilestone='true'] {{ border-left:3px solid {p['coin_accent']}; }}
    QLabel[receiptMetricLabel='true'] {{ color:{p['text_secondary']}; font-size:11px; font-weight:500; }}
    QLabel[receiptMetricValue='true'] {{ font-size:18px; font-weight:600; }}
    QLabel[receiptEventTitle='true'] {{ color:{p['text_primary']}; font-size:13px; font-weight:600; }}
    QLabel[receiptEventDetail='true'] {{ color:{p['text_secondary']}; font-size:12px; }}
    """
