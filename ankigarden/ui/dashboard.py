from __future__ import annotations

from typing import Any

from aqt.qt import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTimer,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    Qt,
    QColor,
    QFontMetrics,
    QListWidgetItem,
    QSizePolicy,
    QGuiApplication,
)
from .formatters import format_integer, format_percent, format_status_label, pluralize
from .garden_studio import GardenStudioWidget
from .plant_display import growth_display
from .scene import GardenSceneWidget
from ..display_telemetry import DISPLAY_TELEMETRY

UI_TEXT = {
    "settings_window_title": "Anki Garden Settings",
    "advanced_hint": "Use advanced and debug controls here to keep the dashboard focused.",
    "tab_advanced": "Advanced",
    "app_title": "Anki Garden",
    "title_banner": "🌿 Anki Garden",
    "open_settings": "⚙ Open Settings",
    "hero_growth_format": "Daily growth %p%",
    "quest_progress_title": "Quest Progress",
    "no_quests": "No quest progress yet today. Review a card to start progress.",
    "no_achievements": "Achievement progress will appear as you keep studying.",
    "no_boosts": "No active inventory boosts yet.",
}

BUTTON_VARIANT_PRIMARY = "primary"
BUTTON_VARIANT_SECONDARY = "secondary"


def _set_button_variant(button: QPushButton, variant: str) -> None:
    button.setProperty("variant", variant)
    style = button.style()
    if style is not None:
        style.unpolish(button)
        style.polish(button)


def _button_stylesheet() -> str:
    return """
            QPushButton { border-radius: 10px; padding: 7px 12px; font-weight: 600; }
            QPushButton[variant='primary'] { background: #2f6f48; border: 1px solid #4f9a67; color: #f2fff6; }
            QPushButton[variant='primary']:hover { background: #3d8559; }
            QPushButton[variant='secondary'] { background: #264456; border: 1px solid #3d6174; color: #e6f0ea; }
            QPushButton[variant='secondary']:hover { background: #2f5468; }
            QPushButton[variant='destructive'] { background: #6d2d2d; border: 1px solid #a44a4a; color: #ffecec; }
            QPushButton[variant='destructive']:hover { background: #823636; }
            QPushButton:disabled { background: #1c2a32; border: 1px solid #2c3b44; color: #7a8a92; }
    """


class GardenSettingsDialog(QDialog):
    def __init__(self, parent: QWidget, engine: Any, config: Any) -> None:
        super().__init__(parent)
        self.engine = engine
        self.config = config
        self.setWindowTitle(UI_TEXT["settings_window_title"])
        self.setMinimumSize(640, 460)
        self.resize(*self._recommended_window_size(920, 640, width_ratio=0.72, height_ratio=0.72))
        self.setStyleSheet(_button_stylesheet())
        root = QHBoxLayout(self)
        tabs = QTabWidget()
        root.addWidget(tabs)

        self.behavior = GardenStudioWidget(config, asset_resolver=engine.resolve_preview_assets)
        save_visuals = QPushButton("Save Garden Appearance")
        _set_button_variant(save_visuals, BUTTON_VARIANT_PRIMARY)
        save_visuals.clicked.connect(self._save_visual_settings)
        behavior = QWidget()
        behavior_layout = QVBoxLayout(behavior)
        behavior_layout.addWidget(self.behavior)
        behavior_layout.addWidget(save_visuals)

        advanced = QWidget()
        a_layout = QVBoxLayout(advanced)
        a_layout.addWidget(QLabel(UI_TEXT["advanced_hint"]))
        self.debug_report = QTextEdit()
        self.debug_report.setReadOnly(True)
        self.debug_report.setPlaceholderText("Display telemetry report appears here.")
        refresh_debug = QPushButton("Refresh Debug Report")
        _set_button_variant(refresh_debug, BUTTON_VARIANT_SECONDARY)
        refresh_debug.clicked.connect(self._refresh_debug_report)
        a_layout.addWidget(refresh_debug)
        a_layout.addWidget(self.debug_report)
        self._refresh_debug_report()
        a_layout.addStretch(1)

        tabs.addTab(behavior, "Garden Appearance")
        tabs.addTab(advanced, UI_TEXT["tab_advanced"])

    def _save_visual_settings(self) -> None:
        self.config.update(self.behavior.build_theme_payload())
        self.engine.assets.metadata.clear()
        parent = self.parent()
        if parent is not None and hasattr(parent, "refresh_all"):
            parent.refresh_all()
        QMessageBox.information(self, UI_TEXT["app_title"], "Garden appearance saved.")

    def _refresh_debug_report(self) -> None:
        self.debug_report.setPlainText("\\n".join(DISPLAY_TELEMETRY.report_lines()))

    def _recommended_window_size(
        self, default_width: int, default_height: int, *, width_ratio: float, height_ratio: float
    ) -> tuple[int, int]:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return default_width, default_height
        available = screen.availableGeometry()
        width = min(default_width, max(self.minimumWidth(), int(available.width() * width_ratio)))
        height = min(default_height, max(self.minimumHeight(), int(available.height() * height_ratio)))
        return width, height

class GardenDashboard(QDialog):
    ROOT_MARGINS = (18, 18, 18, 18)
    ROOT_SPACING = 12
    CARD_SPACING = 10
    CARD_PADDING = (12, 12, 12, 12)
    CARD_BORDER_RADIUS = 14
    CHIP_BORDER_RADIUS = 12
    CHIP_PADDING = (5, 10)
    CHIP_SPACING = 8
    MID_ROW_SPACING = 12
    CARD_BG = "#18252e"
    CARD_BORDER = "#2f4652"
    APP_BG = "#101820"
    TEXT_PRIMARY = "#e6f0ea"
    TEXT_MUTED = "#b2c4c8"
    CHIP_BG = "#213847"
    LIST_ELIDE_WIDTH = 340
    LIST_MAX_LENGTH = 170
    MIN_WINDOW_WIDTH = 760
    MIN_WINDOW_HEIGHT = 560
    DEFAULT_WINDOW_WIDTH = 1240
    DEFAULT_WINDOW_HEIGHT = 840

    def __init__(self, mw_window: Any, engine: Any, storage: Any, config: Any) -> None:
        super().__init__(mw_window)
        self.engine = engine
        self.storage = storage
        self.config = config
        self.settings_dialog: GardenSettingsDialog | None = None
        self.setWindowTitle(UI_TEXT["app_title"])
        self.setMinimumSize(self.MIN_WINDOW_WIDTH, self.MIN_WINDOW_HEIGHT)
        self.resize(*self._recommended_window_size())
        self._build_ui()

    def _recommended_window_size(self) -> tuple[int, int]:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return self.DEFAULT_WINDOW_WIDTH, self.DEFAULT_WINDOW_HEIGHT
        available = screen.availableGeometry()
        width = min(self.DEFAULT_WINDOW_WIDTH, max(self.MIN_WINDOW_WIDTH, int(available.width() * 0.92)))
        height = min(self.DEFAULT_WINDOW_HEIGHT, max(self.MIN_WINDOW_HEIGHT, int(available.height() * 0.9)))
        return width, height

    def _build_ui(self) -> None:
        self.setStyleSheet(
            f"""
            QDialog {{ background: {self.APP_BG}; color: {self.TEXT_PRIMARY}; }}
            QFrame[card='true'] {{ background: {self.CARD_BG}; border: 1px solid {self.CARD_BORDER}; border-radius: {self.CARD_BORDER_RADIUS}px; }}
            QLabel[typography='title'] {{ font-size: 20px; font-weight: 800; letter-spacing: 0.3px; }}
            QLabel[typography='section-title'] {{ font-size: 15px; font-weight: 700; letter-spacing: 0.2px; }}
            QLabel[typography='muted-body'] {{ font-size: 13px; color: {self.TEXT_MUTED}; }}
            QLabel[typography='status-chip'] {{ font-size: 12px; font-weight: 600; letter-spacing: 0.1px; }}
            QLabel[chip='true'] {{ padding: {self.CHIP_PADDING[0]}px {self.CHIP_PADDING[1]}px; background:{self.CHIP_BG}; border-radius:{self.CHIP_BORDER_RADIUS}px; }}
            {_button_stylesheet()}
            QProgressBar {{ border-radius: 7px; border: 1px solid {self.CARD_BORDER}; background: #132029; }}
            QProgressBar::chunk {{ background: #56ba7f; border-radius: 6px; }}
            QListWidget {{ background: #12202a; border-radius: 10px; border: 1px solid #2a404d; padding: 4px; }}
            """
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(*self.ROOT_MARGINS)
        root.setSpacing(self.ROOT_SPACING)
        page_scroll = QScrollArea()
        page_scroll.setWidgetResizable(True)
        page_scroll.setFrameShape(QFrame.Shape.NoFrame)
        page_scroll.setWidget(page)
        outer.addWidget(page_scroll)

        top = self._card_frame()
        t_layout = QHBoxLayout(top)
        t_layout.setContentsMargins(*self.CARD_PADDING)
        t_layout.setSpacing(self.CHIP_SPACING)
        self.title_label = QLabel(UI_TEXT["title_banner"])
        self._apply_typography(self.title_label, "title")
        self.streak_chip = QLabel()
        self.progress_chip = QLabel()
        self.health_chip = QLabel()
        self.settings_btn = QPushButton(UI_TEXT["open_settings"])
        _set_button_variant(self.settings_btn, BUTTON_VARIANT_SECONDARY)
        self.settings_btn.clicked.connect(self._open_settings)
        t_layout.addWidget(self.title_label)
        t_layout.addStretch(1)
        for chip in (self.streak_chip, self.progress_chip, self.health_chip):
            chip.setProperty("chip", True)
            self._apply_typography(chip, "status-chip")
            t_layout.addWidget(chip)
        t_layout.addWidget(self.settings_btn)
        root.addWidget(top)

        hero_card = self._card_frame()
        h_layout = QVBoxLayout(hero_card)
        h_layout.setContentsMargins(*self.CARD_PADDING)
        h_layout.setSpacing(self.CARD_SPACING)
        self.scene = GardenSceneWidget()
        self.stage_transition_note = QLabel("")
        self.stage_transition_note.setWordWrap(True)
        self.stage_transition_note.setMinimumHeight(24)
        self._apply_typography(self.stage_transition_note, "muted-body")
        self.stage_transition_note.setStyleSheet("color:#f4d58a; font-size:14px; font-weight:700;")
        self.hero_summary = QLabel()
        self.hero_summary.setWordWrap(True)
        self.hero_summary.setMinimumHeight(48)
        self.hero_summary.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)
        self._apply_typography(self.hero_summary, "muted-body")
        self.hero_summary.setStyleSheet("line-height: 1.35;")
        self.hero_growth = QProgressBar()
        self.hero_growth.setMaximum(100)
        self.hero_growth.setFormat(UI_TEXT["hero_growth_format"])
        self.hero_growth.setStyleSheet(
            "QProgressBar{height:18px;font-weight:700;} QProgressBar::chunk{background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #5fd484, stop:1 #d7ff8f);}"
        )
        self.retrospective_note = QLabel("")
        self.retrospective_note.setWordWrap(True)
        self.retrospective_note.setMinimumHeight(24)
        self.retrospective_note.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)
        self._apply_typography(self.retrospective_note, "muted-body")
        self.retrospective_note.setStyleSheet("color:#9ef3b0; font-size:13px;")
        h_layout.addWidget(self.scene)
        h_layout.addWidget(self.stage_transition_note)
        h_layout.addWidget(self.hero_summary)
        h_layout.addWidget(self.hero_growth)
        h_layout.addWidget(self.retrospective_note)
        root.addWidget(hero_card, 2)

        mid_row = QHBoxLayout()
        mid_row.setSpacing(self.MID_ROW_SPACING)
        self.quest_list = QListWidget()
        self.quest_list.setAlternatingRowColors(True)
        self.quest_list.setMinimumHeight(180)
        self.achievement_list = QListWidget()
        self.achievement_list.setAlternatingRowColors(True)
        self.achievement_list.setMinimumHeight(180)
        self.inventory_list = QListWidget()
        self.inventory_list.setAlternatingRowColors(True)
        self.inventory_list.setMinimumHeight(180)
        mid_row.addWidget(self._simple_card(UI_TEXT["quest_progress_title"], self.quest_list), 1)
        mid_row.addWidget(self._simple_card("Milestones", self.achievement_list), 1)
        mid_row.addWidget(self._simple_card("Garden Collection", self.inventory_list), 1)
        root.addLayout(mid_row, 1)

    def _card_frame(self) -> QFrame:
        frame = QFrame()
        frame.setProperty("card", True)
        return frame

    def _apply_typography(self, label: QLabel, level: str) -> None:
        label.setProperty("typography", level)

    def _simple_card(self, title: str, body: QWidget) -> QFrame:
        f = self._card_frame()
        f.setMinimumWidth(240)
        f.setMinimumHeight(240)
        l = QVBoxLayout(f)
        l.setContentsMargins(*self.CARD_PADDING)
        l.setSpacing(self.CARD_SPACING)
        label = QLabel(title)
        self._apply_typography(label, "section-title")
        l.addWidget(label)
        l.addWidget(body)
        return f

    def _add_list_entry(self, widget: QListWidget, text: str, *, empty_state: bool = False) -> None:
        item = QListWidgetItem()
        full_text = text if len(text) <= self.LIST_MAX_LENGTH else f"{text[: self.LIST_MAX_LENGTH - 1]}…"
        max_width = max(140, widget.viewport().width() - 24, self.LIST_ELIDE_WIDTH)
        metrics = QFontMetrics(widget.font())
        display_text = metrics.elidedText(full_text, Qt.TextElideMode.ElideRight, max_width)
        item.setText(display_text)
        if display_text != full_text:
            item.setToolTip(full_text)
        if empty_state:
            item.setFlags(Qt.ItemFlag.NoItemFlags)
        widget.addItem(item)

    def refresh_all(self) -> None:
        DISPLAY_TELEMETRY.track_render("dashboard")
        state = self.storage.state
        stats = state.daily_stats
        health = self.engine.garden_health_index()
        streak_unit = pluralize(state.streak_days, "day")
        self.streak_chip.setText(f"Streak {format_integer(state.streak_days)} {streak_unit}")
        self.progress_chip.setText(f"Today {format_integer(stats.reviewed)} • {format_percent(stats.accuracy)}")
        self.health_chip.setText(f"Health {format_percent(health)}")
        self.hero_summary.setText(
            f"Weather: {format_status_label(state.selected_weather)}\n"
            "Every review helps your plants grow. Daily quests add a little extra progress without taking anything away."
        )
        daily_goal = max(1, int(self.config.value("daily_goal", 140)))
        growth_pct = int(min(100, (stats.growth_earned / daily_goal) * 100))
        self.hero_growth.setValue(growth_pct)

        transitions = self.engine.consume_stage_transitions()
        transition_message = self.engine.stage_transition_message(transitions)
        self.stage_transition_note.setText(transition_message)
        if transition_message:
            QTimer.singleShot(4200, lambda: self.stage_transition_note.setText(""))

        self.scene.set_scene(
            {
                "weather": state.selected_weather,
                "health": health,
                "growth": min(1.0, stats.growth_earned / daily_goal),
                "motion_enabled": bool(
                    self.config.value("enable_animations", True)
                    and not self.config.value("reduced_motion", False)
                ),
                "animation_intensity": self.config.nested("theme_overrides", "animation_intensity", default=0.7),
                "weather_particle_density": self.config.nested("theme_overrides", "weather_particle_density", default=1.0),
                "asset_paths": {
                    "background": self.engine.resolve_background_image(),
                    "weather": self.engine.resolve_weather_overlay(),
                    "decoration": self.engine.resolve_decoration_image(state.equipped.get("decoration", "lantern")),
                },
                "stage_transitions": [transition.to_dict() for transition in transitions],
                "plants": [self._plant_scene_payload(plant) for plant in state.plants],
            }
        )

        self.quest_list.clear()
        for quest in state.daily_quests:
            marker = "✅" if quest.completed else "🌱"
            self._add_list_entry(
                self.quest_list,
                f"{marker} {quest.description}  {quest.progress}/{quest.target}",
            )
        if self.quest_list.count() == 0:
            DISPLAY_TELEMETRY.track_empty_state(route="dashboard", view="quest_list", expected_non_empty=bool(state.daily_quests))
            self._add_list_entry(self.quest_list, UI_TEXT["no_quests"], empty_state=True)

        self.achievement_list.clear()
        for ach in state.achievements.values():
            marker = "🏅" if ach.unlocked else "🔒"
            self._add_list_entry(self.achievement_list, f"{marker} {ach.name}")
        if self.achievement_list.count() == 0:
            DISPLAY_TELEMETRY.track_empty_state(route="dashboard", view="achievement_list", expected_non_empty=bool(state.achievements))
            self._add_list_entry(self.achievement_list, UI_TEXT["no_achievements"], empty_state=True)

        self.inventory_list.clear()
        for category, items in state.inventory.items():
            if items:
                label = format_status_label(category)
                item_labels = ", ".join(format_status_label(item) for item in items[:3])
                self._add_list_entry(self.inventory_list, f"{label}: {item_labels}")
        if self.inventory_list.count() == 0:
            expected_non_empty_inventory = any(items for items in state.inventory.values())
            DISPLAY_TELEMETRY.track_empty_state(
                route="dashboard", view="inventory_list", expected_non_empty=expected_non_empty_inventory
            )
            self._add_list_entry(self.inventory_list, UI_TEXT["no_boosts"], empty_state=True)

    def show_retrospective_feedback(self, review_count: int, growth_gain: int) -> None:
        if review_count <= 0:
            self.retrospective_note.setText("")
            return
        self.retrospective_note.setText(
            f"✨ Applied catch-up from synced reviews: +{growth_gain} growth from {review_count} reviews."
        )

    def _plant_scene_payload(self, plant: Any) -> dict[str, Any]:
        display = growth_display(plant.growth_points, plant.rare_variant)
        return {
            "plant_id": plant.plant_id,
            "name": plant.name,
            "species": plant.species,
            "stage": display.stage,
            "vitality": plant.vitality,
            "growth_points": plant.growth_points,
            "rare_variant": plant.rare_variant,
            "next_stage": display.next_stage,
            "next_threshold": display.next_threshold,
            "points_remaining": display.points_remaining,
            "stage_progress": display.progress,
            "fully_grown": display.fully_grown,
            "image_path": self.engine.resolve_plant_image(plant.species, plant.growth_stage, plant.rare_variant),
        }

    def _open_settings(self) -> None:
        if self.settings_dialog is None:
            self.settings_dialog = GardenSettingsDialog(self, self.engine, self.config)
        self.settings_dialog.show()
        self.settings_dialog.raise_()
