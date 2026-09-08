"""Study activity and committed rewards inside Garden Progress."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
import logging

from aqt.qt import (
    QEvent, QFrame, QHBoxLayout, QLabel, QPushButton,
    QSizePolicy, Qt, QVBoxLayout, QWidget,
)

from ..reward_presentation import reward_content_visible, recorded_event_presentation
from .copy import STUDY_COUNT_LABEL, DAILY_COMPLETION_CONDITION, cards_studied_text
from .controls import GardenFlowLayout, GardenWrappingLabel
from .formatters import (
    format_garden_coins, format_growth, format_quantity, format_streak, GardenDateService,
)
from .icons import garden_icon
from .theme import GARDEN_THEME, TEXT_ROLE_TOKENS, TextRole, apply_tabular_numerals

logger = logging.getLogger(__name__)


def _label(text: str, role: str = "body") -> QLabel:
    label = GardenWrappingLabel(text)
    label.setProperty("activityRole", role)
    label.setWordWrap(True)
    label.setMinimumWidth(0)
    label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
    return label


def _icon(name: str, size: int = 16, *, gold: bool = False) -> QLabel:
    label = QLabel()
    label.setFixedSize(size, size)
    label.setPixmap(garden_icon(name, color=GARDEN_THEME[
        "coin_accent" if gold else "growth_accent"]).pixmap(size, size))
    label.setAccessibleName({"reviews": STUDY_COUNT_LABEL, "coin": "Coins",
        "growth": "Growth", "find": "Garden Finds", "streak": "Anki streak"}.get(name, ""))
    return label


def _growth(units: int, *, signed: bool = False) -> str:
    return format_growth(Decimal(int(units)) / 100, include_unit=signed, signed=signed)


def _coins(amount: int | None, *, earned: bool = False, signed: bool = True) -> str:
    # Keep each amount and its unit together; the earned state can wrap separately.
    if amount is None:
        return "Earned\nAmount unavailable" if earned else "Amount unavailable"
    return format_garden_coins(amount, signed=signed).replace(" ", "\u00a0") + ("\nEarned" if earned else "")


def _line(layout, name: str, value: str = "", icon: str = ""):
    row = QHBoxLayout()
    row.setSpacing(8)
    label = _label(name)
    row.addWidget(label, 1)
    if value:
        if icon:
            row.addWidget(_icon(icon, 14, gold=icon == "coin"))
        amount = _label(value, "value")
        amount.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        apply_tabular_numerals(amount)
        row.addWidget(amount)
    layout.addLayout(row)
    return label


class ActivityStat(QFrame):
    """An intact inline total with its recorded source breakdown on hover."""

    def __init__(self, icon, text, details):
        super().__init__()
        self.setProperty("activityStat", True)
        self._details = details
        self.setToolTip(text)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(5)
        row.addWidget(_icon(icon, 14, gold=icon == "coin"))
        value = _label(text, "stat")
        value.setWordWrap(False)
        apply_tabular_numerals(value)
        row.addWidget(value)

    def event(self, event):
        if event.type() == QEvent.Type.ToolTip and self._details is not None:
            try:
                self.setToolTip(self._details())
                self._details = None
            except Exception:
                logger.exception("Anki Garden: activity source details unavailable")
        return super().event(event)


class ActivityPage(QWidget):
    def __init__(self, owner):
        super().__init__()
        from .dashboard import SectionCard, ResponsiveSplit, ResponsiveTileGrid, _today_cards_page_projection

        self.owner, self.storage, self.engine = owner, owner.storage, owner.engine
        self.dates = GardenDateService(self.storage)
        self.setObjectName("agActivity")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setProperty("semanticId", "progress.activity")
        self.setMaximumWidth(1400)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        colors = GARDEN_THEME
        rules = [f"""
            QWidget#agActivity {{background:{colors['garden_background']};}}
            QWidget#agActivity QFrame[sectionCard='true'] {{background:{colors['raised_surface']}; border:0; border-radius:12px;}}
            QWidget#agActivity QFrame[activityEntry='true'], QWidget#agActivity QFrame[activityStat='true'] {{background:transparent; border:0;}}
            QWidget#agActivity QFrame[activityDivider='true'] {{background:{colors['subtle_border']}; border:0; min-height:1px; max-height:1px;}}
            QWidget#agActivity QFrame[activitySegment='true'] {{background:{colors['selected_surface']}; border:0; border-radius:3px; min-height:6px; max-height:6px;}}
            QWidget#agActivity QFrame[activitySegment='true'][filled='true'] {{background:{colors['action_accent']};}}
            QWidget#agActivity QFrame[activityFilters='true'] {{background:{colors['dialog_surface']}; border:0; border-radius:8px;}}
            QWidget#agActivity QPushButton[activityFilter='true'] {{background:transparent; color:{colors['text_secondary']}; border:1px solid transparent; border-radius:6px; padding:3px 8px; min-width:0; font-size:13px; font-weight:500;}}
            QWidget#agActivity QPushButton[activityFilter='true']:checked {{background:{colors['selected_surface']}; color:{colors['action_accent']};}}
            QWidget#agActivity QPushButton[activityFilter='true']:hover {{color:{colors['text_primary']};}}
            QWidget#agActivity QPushButton[activityFilter='true']:focus {{border-color:{colors['action_accent']};}}
            QWidget#agActivity QPushButton[disclosureRow='true'] {{background:transparent; border:0; border-radius:6px; color:{colors['text_secondary']}; padding:5px 0; text-align:left; font-size:13px;}}
            QWidget#agActivity QPushButton[disclosureRow='true']:hover {{color:{colors['text_primary']};}}
            QWidget#agActivity QPushButton[disclosureRow='true']:focus {{background:{colors['raised_surface']};}}
        """]
        for name, role in (("heading", TextRole.SCREEN_TITLE), ("title", TextRole.SECTION_HEADING),
                           ("body", TextRole.BODY), ("value", TextRole.BODY),
                           ("secondary", TextRole.SECONDARY), ("stat", TextRole.SECONDARY),
                           ("metric", TextRole.NUMERIC_DISPLAY)):
            token = TEXT_ROLE_TOKENS[role]
            color = colors["text_secondary" if name in {"secondary", "body"} else "text_primary"]
            rules.append(f"QWidget#agActivity QLabel[activityRole='{name}'] {{font-size:{token.font_size_px}px; font-weight:{token.font_weight}; color:{color};}}")
        rules.append("""
            QWidget#agActivity QFrame[studyRewards='true'] QLabel[activityRole='title'] {font-size:14px; font-weight:600;}
            QWidget#agActivity QFrame[studyRewards='true'] QLabel[activityRole='body'],
            QWidget#agActivity QFrame[studyRewards='true'] QLabel[activityRole='value'] {font-size:13px;}
            QWidget#agActivity QFrame[studyRewards='true'] QLabel[activityRole='secondary'] {font-size:12px;}
        """)
        self.setStyleSheet("\n".join(rules))
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(16)
        state = getattr(self.storage, "state", None)
        if state is None or (getattr(self.storage, "runtime_pending", False)
                             and not getattr(self.storage, "_allow_runtime_commit", False)):
            self.body.addWidget(_label("Loading your activity…", "secondary"))
            return
        failed = False
        try:
            self.engine.today_cards_status()
        except Exception:
            failed = True
        projection = _today_cards_page_projection(self.engine, self.storage, verification_failed=failed)
        self.day = str(state.daily_stats.day)
        try:
            totals = self.storage.activity_day_totals(self.day) or None
        except Exception:
            logger.exception("Anki Garden: Activity totals unavailable")
            totals = None
        self.body.addWidget(_label("Today", "heading"))
        metrics = ResponsiveTileGrid(minimum_tile_width=205, maximum_columns=4,
                                    allowed_columns=(1, 2, 4))
        metrics.grid.setHorizontalSpacing(16)
        for icon, title, value in (
            ("reviews", STUDY_COUNT_LABEL, f"{state.daily_stats.reviewed:,}"),
            ("growth", "Growth earned", _growth(totals["growth_units"]) if totals is not None else "—"),
            ("coin", "Coins earned", f"{totals['coins']:,}" if totals is not None else "—"),
            ("find", "Garden Finds", f"{totals['finds']:,}" if totals is not None else "—"),
        ):
            tile = SectionCard()
            tile.setMinimumHeight(80)
            box = QVBoxLayout(tile)
            box.setContentsMargins(16, 12, 16, 12)
            box.setSpacing(6)
            heading = QHBoxLayout()
            heading.setSpacing(7)
            heading.addWidget(_icon(icon, gold=icon == "coin"))
            heading.addWidget(_label(title, "secondary"), 1)
            box.addLayout(heading)
            number = _label(value, "metric")
            apply_tabular_numerals(number)
            box.addWidget(number)
            if icon == "reviews":
                tile.setToolTip("Includes repeat answers to the same card.")
                tile.setAccessibleDescription(tile.toolTip())
            elif icon == "growth":
                tile.setToolTip("Includes Growth earned by your plants and Growth added to storage or projects.")
            elif icon == "coin":
                tile.setToolTip("Coins received today, before spending.")
            metrics.add_tile(tile)
        self.body.addWidget(metrics)
        self.study_rewards_card = self._study_rewards_panel(projection)
        sidebar = QWidget()
        column = QVBoxLayout(sidebar)
        column.setContentsMargins(0, 0, 0, 0)
        column.setAlignment(Qt.AlignmentFlag.AlignTop)
        column.addWidget(self.study_rewards_card)
        self.history_card = self._build_history()
        self.columns = ResponsiveSplit(self.history_card, sidebar, stretches=(13, 6),
                                       minimum_widths=(480, 320), stack_right_first=True)
        self.body.addWidget(self.columns)

    def _card(self, title: str, semantic: str = ""):
        from .dashboard import SectionCard
        card = SectionCard()
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        if semantic:
            card.setProperty("semanticId", semantic)
        box = QVBoxLayout(card)
        box.setContentsMargins(16, 16, 16, 16)
        box.setSpacing(10)
        box.setAlignment(Qt.AlignmentFlag.AlignTop)
        box.addWidget(_label(title, "title"))
        return card, box

    def _study_rewards_panel(self, projection):
        from .state_contracts import streak_presentation

        reward = self.engine.study_rewards_summary()
        completion = reward["completion"]
        earned = bool(completion["earned"])
        status = projection.status
        state = self.storage.state
        streak = streak_presentation(state.streak_days, state.last_active_day,
            state.daily_stats.reviewed, today=date.fromisoformat(self.day))
        card, box = self._card("Study rewards", "progress.study-rewards")
        card.setProperty("studyRewards", True)
        card.setProperty("streakSemantic", streak.semantic)
        card.setProperty("completionRewardState", "earned" if earned else projection.claim_state)
        card.setProperty("todayCardsStatus", status.status)
        box.setContentsMargins(12, 12, 12, 12)
        box.setSpacing(8)
        box.addWidget(_label("Today", "secondary"))

        def amount_text(amount, received):
            if amount is None:
                return "Earned · amount unavailable" if received else "Amount unavailable"
            text = format_garden_coins(amount, signed=not received)
            return f"{text} earned" if received else text

        _line(box, "Study 1 card",
              amount_text(reward["first_coins"], reward["first_earned"]), "coin")
        due_box = QVBoxLayout()
        due_box.setSpacing(4)
        box.addLayout(due_box)
        if status.status == "not_eligible" and not earned:
            _line(due_box, DAILY_COMPLETION_CONDITION)
            due_box.addWidget(_label("No cards due today", "secondary"))
        else:
            _line(due_box, DAILY_COMPLETION_CONDITION,
                  amount_text(completion["coins"], earned), "coin")
            if status.status == "unavailable":
                due_box.addWidget(_label("Status unavailable", "secondary"))
                retry = QPushButton("Try again")
                retry.clicked.connect(lambda: self.owner._refresh_metric_page("today"))
                due_box.addWidget(retry, 0, Qt.AlignmentFlag.AlignLeft)
            elif not earned and projection.remaining_cards:
                due_box.addWidget(_label(self.engine._cards_remaining_copy(
                    projection.remaining_cards), "secondary"))
                if status.status == "waiting_for_learning":
                    due_box.addWidget(_label(status.primary, "secondary"))

        box.addSpacing(6)
        percent = reward["growth_percent"]
        _line(box, "Permanent Growth bonus" if percent else "Growth bonus",
              f"+{percent}%", "growth")
        _line(box, "Current streak", format_streak(streak.current_days))
        if reward["next_tier_days"] is None:
            box.addWidget(_label("All Growth tiers unlocked", "secondary"))
        else:
            _line(box, "Next tier",
                  f"+{reward['next_tier_percent']}% at {reward['next_tier_days']:,} days")
        achievements = QPushButton("View achievements")
        achievements.setProperty("semanticId", "progress.study-rewards-achievements")
        achievements.setEnabled(callable(self.owner.open_achievement))
        achievements.clicked.connect(lambda: self.owner.open_achievement(reward["achievement_id"]))
        box.addWidget(achievements, 0, Qt.AlignmentFlag.AlignLeft)
        return card
    def _build_history(self):
        card, body = self._card("Recent activity", "progress.activity-history")
        self.history_heading = body.takeAt(0).widget()
        heading = QWidget()
        header = GardenFlowLayout(heading, spacing=16, row_spacing=8, justify=True)
        header.addWidget(self.history_heading)
        segmented = QFrame()
        segmented.setProperty("activityFilters", True)
        # Keep the segmented control intact when the outer header wraps. A
        # nested flow advertises only its smallest button's minimum width.
        segmented.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        filters = QHBoxLayout(segmented)
        filters.setSpacing(0)
        filters.setContentsMargins(2, 2, 2, 2)
        self.filters = {}
        self.filter_key = getattr(self.owner, "_transaction_filter", "all")
        if self.filter_key not in {"all", "study", "earned", "spent"}:
            self.filter_key = "all"
        for key, name in (("all", "All"), ("study", "Study"), ("earned", "Earned"), ("spent", "Spent")):
            button = QPushButton(name)
            button.setCheckable(True)
            button.setProperty("activityFilter", True)
            button.setFixedHeight(28)
            button.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            button.setChecked(key == self.filter_key)
            button.setAccessibleName(f"{name} activity")
            button.clicked.connect(lambda _checked=False, key=key: self._change_filter(key))
            filters.addWidget(button)
            self.filters[key] = button
        header.addWidget(segmented)
        body.addWidget(heading)
        content = QWidget()
        self.history = QVBoxLayout(content)
        self.history.setContentsMargins(0, 0, 0, 0)
        self.history.setSpacing(8)
        self.history.setAlignment(Qt.AlignmentFlag.AlignTop)
        body.addWidget(content)
        self.more = QPushButton("Show more")
        self.more.clicked.connect(self._load_more)
        body.addWidget(self.more, 0, Qt.AlignmentFlag.AlignLeft)
        self.cursor, self.last_day, self.history_message = None, None, None
        self._load_more()
        return card

    def focus_section(self, section):
        scroll = self.owner.body_scrolls.get("today")
        if scroll is None:
            return
        if section in {"currency", "coins"}:
            scroll.ensureWidgetVisible(self.history_heading, 0, 16)
        elif section == "streak":
            scroll.ensureWidgetVisible(self.study_rewards_card, 0, 16)
        elif section in {"today", "activity", "overview"}:
            scroll.verticalScrollBar().setValue(0)

    def _change_filter(self, key):
        self.filter_key = self.owner._transaction_filter = key
        for candidate, button in self.filters.items():
            button.setChecked(candidate == key)
        self.owner._clear_layout(self.history)
        self.cursor, self.last_day, self.history_message = None, None, None
        self._load_more()

    def _load_more(self):
        if self.history_message is not None:
            self.history.removeWidget(self.history_message)
            self.history_message.hide()
            self.history_message.deleteLater()
            self.history_message = None
        try:
            entries = self.storage.activity_entries(filter_key=self.filter_key, limit=21, before=self.cursor)
        except Exception:
            logger.exception("Anki Garden: Activity could not be loaded")
            self.history_message = _label("Activity couldn’t be loaded.", "secondary")
            self.history.addWidget(self.history_message)
            self.more.setText("Try again")
            self.more.setVisible(True)
            return
        for entry in entries[:20]:
            row = self._entry(entry)
            self.cursor = (entry.sort_ms, entry.group_id)
            if row is None:
                continue
            if self.last_day is not None:
                divider = QFrame()
                divider.setProperty("activityDivider", True)
                self.history.addWidget(divider)
            if entry.scheduler_day != self.last_day:
                timestamp = datetime.fromtimestamp(entry.sort_ms / 1000).astimezone().isoformat()
                self.history.addWidget(_label(self.dates.format_activity_day(entry.scheduler_day, timestamp), "secondary"))
                self.last_day = entry.scheduler_day
            self.history.addWidget(row)
        if not self.history.count():
            message = {"all": "No activity yet\nStudy cards to start earning Growth and rewards.",
                       "study": "No study activity recorded yet", "earned": "No rewards recorded yet", "spent": "No spending recorded yet"}[self.filter_key]
            self.history_message = _label(message, "secondary")
            self.history.addWidget(self.history_message)
        self.more.setText("Show more")
        self.more.setVisible(len(entries) > 20)

    def _entry(self, entry):
        from .dashboard import SectionCard
        study = entry.kind in {"session", "sync", "study"}
        def visible_events():
            return tuple(event for event in self.storage.activity_details(entry.group_id)
                         if reward_content_visible(event) and reward_content_visible(event.payload))
        events = None if study else visible_events()
        if not study and not events:
            return None
        def saved_events():
            nonlocal events
            if events is None:
                events = visible_events()
            return events
        first = events[0] if events else None
        event_presentation = recorded_event_presentation(first) if first else None
        title = {"session": "Study session", "sync": "Synced study", "study": "Study activity"}.get(entry.kind)
        if title is None:
            title = event_presentation.title if event_presentation else "Garden reward"
        if entry.kind == "purchase":
            if title == "Purchase":
                title = self._stat_details("items", saved_events()).removesuffix(" ×1") or "garden item"
            if not title.startswith("Bought "):
                title = "Bought " + title
        card = SectionCard()
        card.setProperty("activityEntry", True)
        box = QVBoxLayout(card)
        box.setContentsMargins(0, 6, 0, 6)
        box.setSpacing(6)
        timestamp = datetime.fromtimestamp(entry.sort_ms / 1000).astimezone().isoformat()
        delta = entry.earned + entry.adjustments - entry.spent
        if study:
            heading = QWidget()
            top = GardenFlowLayout(heading, spacing=12, row_spacing=4, justify=True)
            top.addWidget(_label(title, "value"))
            time_text = (self.dates.format_session_range(entry.started_at, entry.ended_at, status=entry.status)
                         if entry.kind == "session" else self.dates.format_timestamp(timestamp, scheduler_day=entry.scheduler_day))
            clock = _label(time_text, "secondary")
            clock.setToolTip(self.dates.format_timestamp(timestamp, scheduler_day=entry.scheduler_day))
            top.addWidget(clock)
            box.addWidget(heading)
            facts = QWidget()
            inline = GardenFlowLayout(facts, spacing=16)
            metrics = [("reviews", cards_studied_text(entry.card_answers))]
            if entry.growth_units:
                metrics.append(("growth", _growth(entry.growth_units, signed=True)))
            if delta:
                metrics.append(("coin", _coins(delta)))
            if entry.finds:
                metrics.append(("find", format_quantity(entry.finds, "Find")))
            for icon, text in metrics:
                inline.addWidget(ActivityStat(icon, text, lambda icon=icon: self._stat_details(icon, saved_events())))
            box.addWidget(facts)
        else:
            top = QHBoxLayout()
            top.setSpacing(8)
            top.addWidget(_label(title, "body"), 1)
            if delta:
                top.addWidget(_icon("coin", 14, gold=True), 0, Qt.AlignmentFlag.AlignTop)
                money = _label(_coins(delta), "value")
                money.setWordWrap(False)
                apply_tabular_numerals(money)
                top.addWidget(money, 0, Qt.AlignmentFlag.AlignTop)
            box.addLayout(top)
            source_detail = str(getattr(event_presentation, "detail", "") or "")
            if source_detail and source_detail != title:
                box.addWidget(_label(source_detail, "secondary"))
            box.addWidget(_label(self.dates._local_datetime(timestamp).strftime("%I:%M %p").lstrip("0"), "secondary"))
            details = self._stat_details("items", saved_events())
            if entry.growth_units:
                _line(box, "Growth earned", _growth(entry.growth_units, signed=True), "growth")
            if details and details != source_detail and not entry.spent:
                box.addWidget(_label(details, "secondary"))
        return card
    def _stat_details(self, kind, events):
        if kind == "reviews":
            return "Each completed answer counts, including repeat study of the same card."
        coin_rows, destinations, items = defaultdict(int), defaultdict(int), defaultdict(int)
        for event in events:
            if event.coins:
                name = recorded_event_presentation(event).title
                coin_rows[name] += event.coins
            for key, value in dict(event.payload.get("destinations", {})).items():
                destinations[key] += int(value)
            for item in event.payload.get("items", ()):
                item_id = str(item.get("item_id", ""))
                if item_id:
                    items[item_id] += int(item.get("amount", 0))
        if kind == "coin":
            return "\n".join(f"{name}: {format_garden_coins(amount, signed=True)}" for name, amount in coin_rows.items()) or "No Coins earned in this session."
        if kind == "growth":
            return "\n".join(f"{name}: +{_growth(destinations[key])} Growth" for key, name in (
                ("plants", "To plants (includes Shared Growth)"), ("storage", "Stored Growth"), ("projects", "Growth projects"))
                if destinations[key]) or "No Growth earned in this session."
        from ..reward_presentation import _inventory_item_name, _environment_item_name
        names = []
        for item_id, amount in items.items():
            name = _inventory_item_name(item_id)
            if name == item_id.replace("_", " ").title():
                name = _environment_item_name(item_id)
            names.append(f"{name} ×{amount:,}")
        if kind == "items":
            return "\n".join(names)
        finds = [recorded_event_presentation(event).title
                 for event in events if event.finds]
        return "\n".join(dict.fromkeys(finds + names)) or "No Garden Finds in this session."
