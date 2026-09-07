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

from ..activity import source_name
from ..reward_presentation import recurring_reward_presentations, reward_content_visible
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
    label.setAccessibleName({"reviews": "Card answers", "coin": "Coins",
        "growth": "Growth", "find": "Garden Finds", "streak": "Anki streak"}.get(name, ""))
    return label


def _growth(units: int, *, signed: bool = False) -> str:
    return format_growth(Decimal(int(units)) / 100, include_unit=signed, signed=signed)


def _coins(amount: int | None, *, earned: bool = False, signed: bool = True) -> str:
    # Keep each amount and its unit together; the earned state can wrap separately.
    if amount is None:
        return "Earned · Amount unavailable" if earned else "Amount unavailable"
    return format_garden_coins(amount, signed=signed).replace(" ", "\u00a0") + (" · Earned" if earned else "")


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
            ("reviews", "Card answers", f"{state.daily_stats.reviewed:,}"),
            ("growth", "Growth earned", _growth(totals["growth_units"]) if totals is not None else "—"),
            ("coin", "Coins earned", f"{totals['coins']:,}" if totals is not None else "—"),
            ("find", "Garden Finds", f"{projection.finds_count:,}" if projection.finds_count is not None else "—"),
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
        self.completion_card = self._completion_card(projection)
        self.streak_card = self._streak_card()
        sidebar = ResponsiveTileGrid(minimum_tile_width=320, maximum_columns=2)
        sidebar.grid.setHorizontalSpacing(16)
        sidebar.grid.setVerticalSpacing(16)
        for card in (self.completion_card, self.streak_card):
            host = QWidget()
            column = QVBoxLayout(host)
            column.setContentsMargins(0, 0, 0, 0)
            column.setAlignment(Qt.AlignmentFlag.AlignTop)
            column.addWidget(card)
            sidebar.add_tile(host)
        self.history_card = self._build_history()
        self.columns = ResponsiveSplit(self.history_card, sidebar, stretches=(7, 3),
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

    def _completion_card(self, projection):
        from .dashboard import DisclosureRow
        status = projection.status
        reward = self.engine.today_cards_reward_summary()
        earned = bool(reward["earned"])
        card, box = self._card("Today’s cards", "progress.today-cards-status")
        card.setProperty("todayCardsStatus", status.status)
        card.setProperty("completionRewardState", "earned" if earned else projection.claim_state)
        amount = int(reward["completion_coins"])
        cycle_coins = int(reward["cycle_coins"])
        if earned:
            amount, cycle_coins = self._completion_coins(cycle_coins, reward["cycle_earned"])
        # Reward receipt and current workload are independent: new due work must
        # never remove an already earned label, even if verification is unavailable.
        if earned or status.status not in {"not_eligible", "unavailable"}:
            _line(box, "Finish all due cards", _coins(amount, earned=earned), "coin")
        if status.status == "unavailable":
            box.addWidget(_label("Status unavailable", "secondary"))
            retry = QPushButton("Try again")
            retry.clicked.connect(lambda: self.owner._refresh_metric_page("today"))
            box.addWidget(retry, 0, Qt.AlignmentFlag.AlignLeft)
        elif status.status == "not_eligible" and not earned:
            box.addWidget(_label("No cards due today", "secondary"))
        elif projection.remaining_cards:
            # This is the same exact obligation count and copy used by the engine.
            box.addWidget(_label(self.engine._cards_remaining_copy(projection.remaining_cards), "secondary"))
            if status.status == "waiting_for_learning":
                box.addWidget(_label(status.primary, "secondary"))
        if reward["growth"]:
            _line(box, "Prism Trellis", format_growth(reward["growth"], signed=True), "growth")
        box.addSpacing(4)
        progress, goal = int(reward["cycle_progress"]), int(reward["cycle_goal"])
        _line(box, "Completed days", f"{progress:,} / {goal:,}").setToolTip("A completed day means finishing all due cards. These days do not need to be consecutive.")
        segments = QWidget()
        segments.setAccessibleName(f"{progress} of {goal} completed days")
        track = QHBoxLayout(segments)
        track.setContentsMargins(0, 0, 0, 0)
        track.setSpacing(4)
        for index in range(goal):
            segment = QFrame()
            segment.setProperty("activitySegment", True)
            segment.setProperty("filled", index < progress)
            track.addWidget(segment, 1)
        box.addWidget(segments)
        _line(box, f"Every {goal:,} completed days", _coins(cycle_coins, earned=reward["cycle_earned"]), "coin")
        disclosure = DisclosureRow("View details", [], semantic_id="progress.today-details")
        details = disclosure.panel.layout()
        details.addWidget(_label("Finish the cards due across your collection, including learning steps due later today.", "secondary"))
        details.addWidget(_label("A completed day means finishing all due cards. These days do not need to be consecutive.", "secondary"))
        details.addWidget(_label("Burying or suspending cards does not count as finishing them. An empty day does not earn this reward.", "secondary"))
        if projection.cutoff_at_ms:
            cutoff = datetime.fromtimestamp(projection.cutoff_at_ms / 1000).astimezone()
            _line(details, "New Anki day", cutoff.strftime("%I:%M %p").lstrip("0"))
        _line(details, "Garden Rhythm", f"+{reward['rhythm_percent']}% review Growth", "growth")
        details.addWidget(_label("Garden Rhythm follows your recent completed days.", "secondary"))
        box.addWidget(disclosure)
        return card

    def _completion_coins(self, cycle_fallback, cycle_earned):
        """Keep historical amounts exact, even after equipment or catalog changes."""
        keys = (f"all_due:{self.day}", f"achievement-trophy:garden_journal:{self.day}",
                f"harvest-bell:{self.day}", f"autumn-hearth:{self.day}")
        cycle_key = f"completion_cycle_5:{self.day}"
        recorded = {tx.event_key: tx.delta for tx in self.storage.state.currency_transactions
                    if tx.event_key in (*keys, cycle_key)}
        ledger = getattr(self.storage, "_reward_ledger", None)
        if ledger is not None:
            try:
                for key in (*keys, cycle_key):
                    event = ledger.activity_event(key)
                    if event is not None:
                        recorded[key] = event.coins
            except Exception:
                logger.exception("Anki Garden: completion receipts unavailable")
        required = [key for key in keys if key == keys[0] or self.engine._reward_applied(key)]
        amount = sum(recorded[key] for key in required) if all(key in recorded for key in required) else None
        return amount, recorded.get(cycle_key) if cycle_earned else cycle_fallback

    def _streak_card(self):
        from .dashboard import DisclosureRow
        from .state_contracts import streak_presentation
        state = self.storage.state
        presentation = streak_presentation(state.streak_days, state.last_active_day,
            state.daily_stats.reviewed, today=date.fromisoformat(self.day))
        rules = {rule.rule_id: rule for rule in recurring_reward_presentations(
            state, self.engine, current_streak_days=presentation.current_days)}
        card, box = self._card("Daily & streak rewards", "progress.streak-hero")
        card.setProperty("streakSemantic", presentation.semantic)
        _line(box, "Anki streak", format_streak(presentation.current_days)).setToolTip(
            "Answer at least one card each Anki day to continue your streak.")
        try:
            earned = self.storage.activity_streak_rewards(self.day) or None
        except Exception:
            earned = None
        if earned is None:
            _line(box, "First card today", "Status unavailable")
        else:
            daily = int(earned["daily"])
            _line(box, "First card today", _coins(daily or rules["daily_activity"].reward_coins, earned=bool(daily)), "coin")
        box.addSpacing(4)
        streak = rules["weekly_streak"]
        _line(box, f"{streak.next_streak_day:,}-day streak reward", _coins(streak.reward_coins), "coin")
        box.addWidget(_label(f"{streak.streak_days_remaining:,} more consecutive study {'day' if streak.streak_days_remaining == 1 else 'days'}", "secondary"))
        details = DisclosureRow("Reward details", [], semantic_id="progress.streak-rewards")
        try:
            all_rewards = self.storage.activity_streak_rewards() or None
        except Exception:
            all_rewards = None
        if all_rewards is None:
            details.panel.layout().addWidget(_label("Reward history is unavailable. Try refreshing Activity.", "secondary"))
        else:
            if earned and earned["streak"]:
                _line(details.panel.layout(), "Streak reward today", _coins(earned["streak"], earned=True), "coin")
            for key, name in (("daily", "First-card rewards"), ("streak", "Streak milestones"),
                              ("achievements", "Other streak achievements")):
                _line(details.panel.layout(), name, _coins(all_rewards[key], signed=False), "coin")
            details.panel.layout().addWidget(_label("Totals from your available reward history. The first streak milestone and its achievement share one Coin reward.", "secondary"))
        box.addWidget(details)
        return card

    def _build_history(self):
        card, body = self._card("Recent activity", "progress.activity-history")
        self.history_heading = body.takeAt(0).widget()
        heading = QWidget()
        header = GardenFlowLayout(heading, spacing=16, row_spacing=8, justify=True)
        header.addWidget(self.history_heading)
        segmented = QFrame()
        segmented.setProperty("activityFilters", True)
        filters = QHBoxLayout(segmented)
        filters.setContentsMargins(2, 2, 2, 2)
        filters.setSpacing(0)
        self.filters = {}
        self.filter_key = getattr(self.owner, "_transaction_filter", "all")
        if self.filter_key not in {"all", "study", "earned", "spent"}:
            self.filter_key = "all"
        for key, name in (("all", "All"), ("study", "Study"), ("earned", "Earned"), ("spent", "Spent")):
            button = QPushButton(name)
            button.setCheckable(True)
            button.setProperty("activityFilter", True)
            button.setFixedHeight(28)
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
            scroll.ensureWidgetVisible(self.streak_card, 0, 16)
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
                       "study": "No study sessions yet", "earned": "No rewards yet", "spent": "No spending yet"}[self.filter_key]
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
        title = {"session": "Study session", "sync": "Synced study", "study": "Study activity"}.get(entry.kind)
        if title is None:
            title = source_name(first.source, str(first.payload.get("source_id", "")),
                                str(first.payload.get("reason", ""))) if first else "Garden reward"
        if entry.kind == "purchase":
            if title == "Purchase":
                title = self._stat_details("items", saved_events()).removesuffix(" ×1") or "garden item"
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
            metrics = [("reviews", format_quantity(entry.card_answers, "card answer"))]
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
            box.addWidget(_label(self.dates._local_datetime(timestamp).strftime("%I:%M %p").lstrip("0"), "secondary"))
            details = self._stat_details("items", saved_events())
            if entry.growth_units:
                _line(box, "Growth earned", _growth(entry.growth_units, signed=True), "growth")
            if details and not entry.spent:
                box.addWidget(_label(details, "secondary"))
        return card
    def _stat_details(self, kind, events):
        if kind == "reviews":
            return "Each completed answer counts, including repeat study of the same card."
        coin_rows, destinations, items = defaultdict(int), defaultdict(int), defaultdict(int)
        for event in events:
            if event.coins:
                name = source_name(event.source, str(event.payload.get("source_id", "")), str(event.payload.get("reason", "")))
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
                ("plants", "Plants"), ("storage", "Stored Growth"), ("projects", "Growth projects"))
                if destinations[key]) or "No Growth earned in this session."
        from ..reward_presentation import _inventory_item_name, _environment_item_name
        names = []
        for item_id, amount in items.items():
            name = _inventory_item_name(item_id)
            if name == item_id.replace("_", " ").title():
                name = _environment_item_name(item_id)
            names.append(f"{name} ×{amount:,}")
        if kind == "items":
            return " · ".join(names)
        finds = [source_name(event.source, reason=str(event.payload.get("reason", "")))
                 for event in events if event.finds]
        return "\n".join(dict.fromkeys(finds + names)) or "No Garden Finds in this session."
