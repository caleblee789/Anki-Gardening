"""A virtualized native reward feed with stable history and finite motion."""
from __future__ import annotations

from aqt.qt import (
    QAbstractListModel, QAbstractItemView, QColor, QEasingCurve, QEvent,
    QFont, QFontMetrics, QListView, QModelIndex, QPainter,
    QPen, QPointF, QRect, QRectF, QSize, QStyledItemDelegate, QTimer,
    QVariantAnimation, QVBoxLayout, QWidget, Qt,
)

from ..reward_presentation import RewardFeedHistory, RewardHero, project_reward_detail_rows
from .reviewer_hud import format_growth_units
from .icons import garden_icon, garden_icon_pixmap
from .growth_count_up import GrowthCountUp
from .reward_rarity import reward_treatment
from .theme import GARDEN_THEME


class _FeedModel(QAbstractListModel):
    PAGE_SIZE = 64

    def __init__(self, parent):
        super().__init__(parent)
        self.history = RewardFeedHistory()
        self.entries = []
        self._visible_count = 0

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else self._visible_count

    def canFetchMore(self, parent=QModelIndex()):
        return not parent.isValid() and self._visible_count < len(self.entries)

    def fetchMore(self, parent=QModelIndex()):
        if not self.canFetchMore(parent):
            return
        count = min(self.PAGE_SIZE, len(self.entries) - self._visible_count)
        self.beginInsertRows(QModelIndex(), self._visible_count, self._visible_count + count - 1)
        self._visible_count += count
        self.endInsertRows()

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < self._visible_count:
            return None
        entry = self.entries[-1 - index.row()]
        if role == Qt.ItemDataRole.UserRole:
            return entry
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.AccessibleTextRole):
            row = project_reward_detail_rows((entry.item,))[0]
            return " · ".join(filter(None, (row.name, row.value)))
        return None

    def append(self, bundle):
        before = len(self.entries)
        added, changed = self.history.append(bundle)
        if added or changed:
            # New answers return the feed to its newest rewards. Keep the
            # entire history, but let Qt measure only one page until the user
            # scrolls into older rewards. Painting was virtualized already;
            # QListView's variable-height layout was still measuring every row.
            inserted = min(added, self.PAGE_SIZE)
            retained = min(self._visible_count, self.PAGE_SIZE - inserted)
            if retained < self._visible_count:
                self.beginRemoveRows(QModelIndex(), retained, self._visible_count - 1)
                self._visible_count = retained
                self.endRemoveRows()
        if added:
            self.beginInsertRows(QModelIndex(), 0, inserted - 1)
            self.entries.extend(self.history.entries[-added:])
            self._visible_count += inserted
            self.endInsertRows()
        if changed and before:
            self.entries[before - 1] = self.history.entries[before - 1]
            if added < self._visible_count:
                self.dataChanged.emit(self.index(added), self.index(added))
        return added, changed


class _FeedDelegate(QStyledItemDelegate):
    def __init__(self, view, artwork):
        super().__init__(view)
        self.view = view
        self.artwork = artwork
        self.new_ids = set()
        self.progress = 1.0
        self.growth_counts = {}
        self.title_font = QFont(view.font())
        self.title_font.setPixelSize(14)
        self.title_font.setWeight(QFont.Weight.DemiBold)
        self.small_font = QFont(view.font())
        self.small_font.setPixelSize(13)
        self.value_font = QFont(self.title_font)
        self.body_font = QFont(self.title_font)
        self.body_font.setWeight(QFont.Weight.Normal)
        self.icons = {key: garden_icon(key).pixmap(14, 14) for key in ("coin", "growth")}

    def artwork_for(self, item, size=40):
        pixmap = self.artwork(item, size)
        if pixmap is not None and not pixmap.isNull():
            return pixmap
        identity = {
            RewardHero.FULL_BLOOM: "plant",
            RewardHero.STAGE_CHANGE: "stage",
            RewardHero.CHECKPOINT: "checkpoint",
            RewardHero.ENVIRONMENT_DISCOVERY: "environment-discovery",
            RewardHero.GARDEN_FIND: "garden-reward",
            RewardHero.COIN_OR_BOOSTER: "garden-reward",
            RewardHero.ROUTINE_GROWTH: "stored_growth" if item.artwork_ref == "stored_growth" else "reviews",
        }.get(item.kind, "find")
        return garden_icon_pixmap(identity, size, color=reward_treatment(item).color,
                                  device_pixel_ratio=self.view.devicePixelRatioF())

    def _parts(self, entry, width):
        item = entry.item
        tone = reward_treatment(item)
        title = project_reward_detail_rows((item,))[0].name
        if item.kind == RewardHero.ROUTINE_GROWTH and item.artwork_ref != "stored_growth":
            title = "Card Growth"
        category = ""
        detail = " · ".join(item.learner_inventory_labels)
        if not detail and item.kind not in {RewardHero.ROUTINE_GROWTH, RewardHero.FULL_BLOOM, RewardHero.STAGE_CHANGE, RewardHero.CHECKPOINT}:
            detail = item.detail if item.detail.casefold() != title.casefold() else ""
        if item.kind == RewardHero.GARDEN_FIND and (item.growth_units or item.garden_coins):
            detail = ""
        badge_width = QFontMetrics(self.small_font).horizontalAdvance(tone.label) + 20 if tone.label and tone.label.casefold() not in title.casefold() else 0
        text_width = max(60, width - 76 - badge_width)
        title_height = QFontMetrics(self.title_font).boundingRect(QRect(0, 0, text_width, 1000), Qt.TextFlag.TextWordWrap, title).height()
        detail_height = QFontMetrics(self.small_font).boundingRect(QRect(0, 0, text_width, 1000), Qt.TextFlag.TextWordWrap, detail).height() if detail else 0
        heading_height = 0
        values_height = 20 if item.growth_units or item.garden_coins else 0
        height = 20 + heading_height + max(40, title_height + (4 + detail_height if detail else 0) + values_height)
        return item, tone, title, category, detail, title_height, detail_height, heading_height, height

    def sizeHint(self, option, index):
        entry = index.data(Qt.ItemDataRole.UserRole)
        width = max(120, self.view.viewport().width())
        return QSize(width, self._parts(entry, width)[-1] + 6)

    def paint(self, painter: QPainter, option, index):
        entry = index.data(Qt.ItemDataRole.UserRole)
        width = option.rect.width()
        item, tone, title, category, detail, title_h, detail_h, heading_h, height = self._parts(entry, width)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if item.event_id in self.new_ids:
            painter.setOpacity(self.progress)
            painter.translate(0, -10 * (1 - self.progress))
        card = QRectF(option.rect.x() + 1, option.rect.y() + 1, width - 3, height - 1)
        painter.setPen(Qt.PenStyle.NoPen)
        bg = QColor(tone.color) if tone.notable else QColor(GARDEN_THEME['raised_surface'])
        if tone.notable:
            bg.setAlpha(20)
        painter.setBrush(bg)
        painter.drawRoundedRect(card, 8, 8)
        if tone.notable:
            painter.setPen(QPen(QColor(tone.color), 2))
            painter.drawLine(card.topLeft() + QPointF(1, 8), card.bottomLeft() - QPointF(-1, 8))
        left, top = int(card.left()) + 10, int(card.top()) + 8
        painter.setFont(self.title_font)
        painter.setPen(QColor(GARDEN_THEME['text_primary']))
        if category:
            painter.drawText(QRect(left, top, width - 24, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, category)
        if tone.label and tone.label.casefold() not in title.casefold():
            painter.setFont(self.small_font)
            badge_w = QFontMetrics(self.small_font).horizontalAdvance(tone.label) + 14
            badge = QRectF(card.right() - badge_w - 8, top, badge_w, 18)
            badge_bg = QColor(tone.color)
            badge_bg.setAlpha(28)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(badge_bg)
            painter.drawRoundedRect(badge, 5, 5)
            painter.setPen(QColor(tone.color))
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, tone.label)
        top += heading_h
        pixmap = self.artwork_for(item)
        if pixmap is not None and not pixmap.isNull():
            size = pixmap.size().scaled(40, 40, Qt.AspectRatioMode.KeepAspectRatio)
            painter.drawPixmap(QRect(left + (40 - size.width()) // 2,
                                     top + (40 - size.height()) // 2,
                                     size.width(), size.height()), pixmap)
        text_left, text_width = left + 48, max(60, width - 76 - (QFontMetrics(self.small_font).horizontalAdvance(tone.label) + 20 if tone.label and tone.label.casefold() not in title.casefold() else 0))
        milestone = item.kind in {RewardHero.FULL_BLOOM, RewardHero.STAGE_CHANGE, RewardHero.CHECKPOINT}
        painter.setFont(self.title_font)
        painter.setPen(QColor(tone.color if tone.notable else GARDEN_THEME['text_primary']))
        painter.drawText(QRect(text_left, top, text_width, title_h), Qt.TextFlag.TextWordWrap, title)
        value_top = top + title_h + 4
        if detail:
            painter.setFont(self.small_font)
            painter.setPen(QColor(GARDEN_THEME['text_secondary']))
            painter.drawText(QRect(text_left, value_top, text_width, detail_h), Qt.TextFlag.TextWordWrap, detail)
            value_top += detail_h + 3
        painter.setFont(self.value_font)
        value_left = text_left
        counter = self.growth_counts.get(item.event_id)
        growth_units = counter.value if counter is not None else item.growth_units
        for key, amount in (("coin", f"+{item.garden_coins:,}" if item.garden_coins else ""),
                            ("growth", format_growth_units(growth_units, signed=True) if item.growth_units else "")):
            if not amount:
                continue
            painter.drawPixmap(QRect(value_left, value_top, 14, 14), self.icons[key])
            painter.setPen(QColor(GARDEN_THEME['coin_accent' if key == 'coin' else 'growth_accent']))
            amount_w = QFontMetrics(self.value_font).horizontalAdvance(amount)
            painter.drawText(QRect(value_left + 18, value_top - 1, amount_w + 2, 18), Qt.AlignmentFlag.AlignVCenter, amount)
            value_left += amount_w + 28
        painter.restore()


class RewardFeed(QWidget):
    def __init__(self, parent, artwork, *, animations_enabled=True):
        super().__init__(parent)
        self.setObjectName("reviewerHudLiveRewardFeed")
        self.animations_enabled = animations_enabled
        self._animation = None
        self._revision = 0
        self._layout_pending = False
        self._maximum_height = 216
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)
        self.view = QListView(self)
        self.view.setObjectName("reviewerHudRewardFeedList")
        self.view.setAccessibleName("Recent rewards, newest first")
        self.view.setFrameShape(QListView.Shape.NoFrame)
        self.view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.view.setResizeMode(QListView.ResizeMode.Adjust)
        self.view.setStyleSheet("QListView {background:transparent;border:0;padding:0;} QScrollBar:vertical {background:transparent;width:6px;} QScrollBar::handle:vertical {background:#315247;border-radius:3px;min-height:24px;} QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {height:0;}")
        self.model = _FeedModel(self)
        self.view.setModel(self.model)
        self.delegate = _FeedDelegate(self.view, artwork)
        self.view.setItemDelegate(self.delegate)
        self.view.viewport().installEventFilter(self)
        self.view.verticalScrollBar().sliderPressed.connect(self._stop_motion)
        root.addWidget(self.view)
        self.setFixedHeight(1)

    def _stop_motion(self):
        self._revision += 1
        if self._animation is not None:
            self._animation.stop()
            self._animation.deleteLater()
            self._animation = None
        self.delegate.progress = 1.0
        self.delegate.new_ids.clear()
        self.view.viewport().update()

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.Wheel, QEvent.Type.MouseButtonPress):
            self._stop_motion()
        elif event.type() == QEvent.Type.Resize and not self._layout_pending:
            self._layout_pending = True
            QTimer.singleShot(0, self._relayout)
        return False

    def _relayout(self):
        self._layout_pending = False
        if not self.isVisible():
            return
        self.view.doItemsLayout()
        self.set_available_height()

    def showEvent(self, event):
        super().showEvent(event)
        self._relayout()

    def latest(self):
        self._stop_motion()
        self.view.scrollToTop()

    def set_available_height(self, maximum=None):
        if maximum is not None:
            self._maximum_height = max(24, int(maximum))
        visible_count = min(4, self.model.rowCount())
        natural = sum(self.view.sizeHintForRow(i) for i in range(visible_count))
        self.setFixedHeight(max(1, min(self._maximum_height, natural + 2)))

    def _count_growth(self, entry, position, previous, *, animate):
        identity = entry.item.event_id
        counter = self.delegate.growth_counts.get(identity)
        if not animate:
            if counter is not None:
                counter.stop()
                self.delegate.growth_counts.pop(identity)
                counter.deleteLater()
            return
        if counter is None:
            def repaint(_value):
                row = len(self.model.entries) - 1 - position
                if self.isVisible() and 0 <= row < self.model.rowCount():
                    self.view.viewport().update(self.view.visualRect(self.model.index(row)))
            counter = GrowthCountUp(self, repaint)
            self.delegate.growth_counts[identity] = counter
            counter.retarget(previous, animate=False)
            def finished():
                if self.delegate.growth_counts.get(identity) is counter:
                    self.delegate.growth_counts.pop(identity)
                    counter.deleteLater()
            counter.finished.connect(finished)
        counter.retarget(entry.item.growth_units, animate=animate)

    def export_count_state(self):
        return {identity: counter.snapshot() for identity, counter in self.delegate.growth_counts.items()}

    def restore_count_state(self, states):
        if not isinstance(states, dict):
            return
        # Only the exposed page can own live numeric animations.
        start = max(0, len(self.model.entries) - self.model.rowCount())
        for position in range(start, len(self.model.entries)):
            entry = self.model.entries[position]
            state = states.get(entry.item.event_id)
            if state is not None and self.animations_enabled:
                self._count_growth(entry, position, int(state.get('value', 0)), animate=True)
                self.delegate.growth_counts[entry.item.event_id].restore(state)

    def settle_counts(self):
        for counter in self.delegate.growth_counts.values():
            counter.settle()
            counter.deleteLater()
        self.delegate.growth_counts.clear()

    def append(self, bundle, *, animate=True, count_growth=False):
        bar = self.view.verticalScrollBar()
        before = bar.value()
        previous = self.model.entries[-1] if self.model.entries else None
        added, changed = self.model.append(bundle)
        if not added and not changed:
            return
        self._stop_motion()
        first = max(0, len(self.model.entries) - added - int(changed))
        for position in range(first, len(self.model.entries)):
            entry = self.model.entries[position]
            if entry.item.kind == RewardHero.ROUTINE_GROWTH and entry.item.growth_units:
                old_units = previous.item.growth_units if previous is not None and previous.item.event_id == entry.item.event_id else 0
                self._count_growth(entry, position, old_units,
                    animate=count_growth and self.animations_enabled)
        visible_ids = {entry.item.event_id for entry in self.model.entries[-self.model.rowCount():]}
        for identity in tuple(self.delegate.growth_counts):
            if identity not in visible_ids:
                counter = self.delegate.growth_counts.pop(identity)
                counter.stop()
                counter.deleteLater()
        if not self.isVisible():
            # Compact HUDs still record every reward, without laying out an
            # invisible list on the critical path to their Growth pulse.
            return
        self.view.doItemsLayout()
        self.set_available_height()
        visible_added = min(added, self.model.rowCount())
        inserted_height = sum(self.view.sizeHintForRow(i) for i in range(visible_added))
        if not added or not animate or not self.animations_enabled or not self.isVisible():
            bar.setValue(0)
            return
        self.delegate.new_ids = {self.model.data(self.model.index(i), Qt.ItemDataRole.UserRole).item.event_id for i in range(visible_added)}
        self.delegate.progress = 0.0
        start = min(bar.maximum(), before + inserted_height)
        bar.setValue(start)
        animation = QVariantAnimation(self)
        self._animation = animation
        animation.setDuration(300)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        def tick(progress):
            self.delegate.progress = float(progress)
            bar.setValue(round(start * (1 - float(progress))))
            self.view.viewport().update()

        animation.valueChanged.connect(tick)
        animation.finished.connect(self._stop_motion)
        animation.start()
