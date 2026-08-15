"""Automated UI-face screenshot capture for disposable Anki runs.

Capture logic is intentionally conservative and activated only when
``ANKI_GARDEN_CAPTURE_UI_FACES`` is set. It uses only Qt-native screenshot
paths and closes transient dialogs after each face to keep the sequence stable.
"""

from __future__ import annotations

import logging
import math
import os
import platform
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from aqt import mw
from aqt.qt import (
    QAbstractButton,
    QAbstractScrollArea,
    QApplication,
    QDialog,
    QFrame,
    QGuiApplication,
    QLabel,
    QPainter,
    QTabWidget,
    QTimer,
    Qt,
    QWidget,
)


logger = logging.getLogger(__name__)


HOME_CAPTURE_BRAND_RGB = (92, 197, 139)
HOME_CAPTURE_DARK_RGB = (
    (7, 26, 21),
    (12, 38, 31),
    (13, 32, 29),
)


CAPTURE_CONTRACT_VERSION = 8
CAPTURE_FACE_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "First run",
        (
            "starter-deck-browser-home",
            "starter-overview-home",
            "starter-garden-onboarding",
            "starter-nursery-plants",
            "starter-selection-confirmation",
            "starter-action-above-footer",
        ),
    ),
    (
        "Anki home",
        (
            "deck-browser-home",
            "overview-home",
        ),
    ),
    (
        "Garden",
        (
            "full-garden",
            "hover-outline",
            "selected-plant-not-nurtured",
            "selected-plant-nurtured",
            "fertilizer-unaffordable",
            "fertilizer-affordable",
            "fertilizer-active",
            "move-mode",
            "plant-story",
        ),
    ),
    (
        "Anki home — active after Nurture",
        (
            "active-deck-browser-home-after-nurture",
            "active-overview-home-after-nurture",
        ),
    ),
    (
        "Garden Progress",
        (
            "growth-zero",
            "growth-nonzero",
            "streak-new",
            "streak-active",
            "coins-zero",
            "coins-activity",
            "progress-overview",
            "progress-achievements",
            "progress-collection",
            "collection-species-overview",
        ),
    ),
    (
        "Customize",
        (
            "customize-garden",
            "customize-effects-on",
            "customize-effects-off",
        ),
    ),
    (
        "Nursery",
        (
            "nursery-plants",
            "nursery-fertilizer-booster",
            "nursery-garden-spaces",
            "nursery-weather-scenery",
        ),
    ),
    (
        "Settings",
        (
            "settings-menu-display",
            "settings-display",
            "settings-display-advanced-open",
            "diagnostics-clean",
            "diagnostics-warning",
        ),
    ),
    (
        "Release stress — Garden",
        (
            "long-garden-name",
            "long-plant-name",
            "four-digit-coin-balance",
            "growth-near-stage-completion",
            "all-six-beds-occupied",
            "plant-at-every-stage",
            "fully-grown-plant-without-fertilize",
            "popover-plot-1",
            "popover-plot-2",
            "popover-plot-3",
            "popover-plot-4",
            "popover-plot-5",
            "popover-plot-6",
            "move-occupied-empty-destinations",
            "fertilizer-expiring-under-minute",
            "fertilizer-replacement-confirmation",
        ),
    ),
    (
        "Watering can — all six plots",
        (
            "watering-can-garden-plot-1",
            "watering-can-garden-plot-2",
            "watering-can-garden-plot-3",
            "watering-can-garden-plot-4",
            "watering-can-garden-plot-5",
            "watering-can-garden-plot-6",
            "watering-can-deck-browser-plot-1",
            "watering-can-deck-browser-plot-3",
            "watering-can-deck-browser-plot-5",
            "watering-can-overview-plot-2",
            "watering-can-overview-plot-4",
            "watering-can-overview-plot-6",
        ),
    ),
    (
        "Release stress — Progress",
        (
            "collection-several-discovered",
            "collection-no-filter-matches",
            "achievement-completed",
            "clear-recall-separate-conditions",
            "streak-at-risk",
            "streak-missed-day",
            "streak-reward-claimed-unclaimed",
        ),
    ),
    (
        "Release stress — Nursery",
        (
            "nursery-item-owned",
            "nursery-item-locked",
            "nursery-purchase-success",
            "nursery-final-row-above-footer",
            "missing-artwork-graphical-fallback",
        ),
    ),
    (
        "Release stress — Settings",
        (
            "settings-unsaved-changes",
            "settings-validation-error",
            "diagnostics-expanded",
            "production-build-controls-absent",
        ),
    ),
    (
        "Accessibility and responsive",
        (
            "reduced-motion-enabled",
            "keyboard-focus-state",
            "narrow-window-responsive",
            "display-scaling-150",
            "display-scaling-200-qt-representative",
        ),
    ),
    (
        "Responsive resize matrix",
        (
            "resize-dashboard-minimum",
            "resize-dashboard-content-699",
            "resize-dashboard-content-701",
            "resize-dashboard-content-819",
            "resize-dashboard-content-821",
            "resize-dashboard-content-899",
            "resize-dashboard-content-901",
            "resize-dashboard-content-999",
            "resize-dashboard-content-1001",
            "resize-dashboard-content-1359",
            "resize-dashboard-content-1361",
            "resize-dashboard-default",
            "resize-dashboard-large",
            "resize-settings-minimum",
            "resize-settings-content-699",
            "resize-settings-content-701",
            "resize-settings-content-759",
            "resize-settings-content-761",
            "resize-settings-default",
            "resize-settings-large",
            "resize-progress-minimum",
            "resize-progress-content-819",
            "resize-progress-content-821",
            "resize-progress-default",
            "resize-progress-large",
            "resize-customize-minimum",
            "resize-customize-content-819",
            "resize-customize-content-821",
            "resize-customize-default",
            "resize-customize-large",
            "resize-nursery-minimum",
            "resize-nursery-content-759",
            "resize-nursery-content-761",
            "resize-nursery-default",
            "resize-nursery-large",
            "resize-story-minimum",
            "resize-story-content-539",
            "resize-story-content-541",
            "resize-story-default",
            "resize-story-large",
            "resize-starter-confirmation-minimum",
            "resize-starter-confirmation-content-399",
            "resize-starter-confirmation-content-401",
            "resize-starter-confirmation-default",
            "resize-starter-confirmation-large",
            "resize-fertilizer-minimum",
            "resize-fertilizer-default",
            "resize-fertilizer-large",
            "resize-fertilizer-replacement-minimum",
            "resize-fertilizer-replacement-content-399",
            "resize-fertilizer-replacement-content-401",
            "resize-fertilizer-replacement-default",
            "resize-fertilizer-replacement-large",
            "resize-species-overview-minimum",
            "resize-species-overview-default",
            "resize-species-overview-large",
        ),
    ),
)
CAPTURE_FACE_LABELS = tuple(
    label
    for _group, labels in CAPTURE_FACE_GROUPS
    for label in labels
)

WATERING_CAN_CAPTURE_FACE_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Watering can — marker-critical interfaces",
        (
            "selected-plant-nurtured",
            "customize-garden",
            "settings-display",
            "all-six-beds-occupied",
            "watering-can-garden-plot-1",
            "watering-can-garden-plot-2",
            "watering-can-garden-plot-3",
            "watering-can-garden-plot-4",
            "watering-can-garden-plot-5",
            "watering-can-garden-plot-6",
            "watering-can-deck-browser-plot-1",
            "watering-can-deck-browser-plot-3",
            "watering-can-deck-browser-plot-5",
            "watering-can-overview-plot-2",
            "watering-can-overview-plot-4",
            "watering-can-overview-plot-6",
            "reduced-motion-enabled",
            "narrow-window-responsive",
            "display-scaling-150",
            "display-scaling-200-qt-representative",
        ),
    ),
)

WATERING_CAN_HOME_CAPTURE_FACE_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Watering can — Anki Home only",
        (
            "watering-can-deck-browser-plot-1",
            "watering-can-deck-browser-plot-3",
            "watering-can-deck-browser-plot-5",
            "watering-can-overview-plot-2",
            "watering-can-overview-plot-4",
            "watering-can-overview-plot-6",
        ),
    ),
)

NURTURED_MARKER_GEOMETRY_CAPTURE_LABELS = frozenset({
    "selected-plant-nurtured",
    "active-deck-browser-home-after-nurture",
    "active-overview-home-after-nurture",
    "customize-garden",
    "settings-display",
    "all-six-beds-occupied",
    "reduced-motion-enabled",
    "narrow-window-responsive",
    "display-scaling-150",
    "display-scaling-200-qt-representative",
    *(f"watering-can-garden-plot-{slot}" for slot in range(1, 7)),
    "watering-can-deck-browser-plot-1",
    "watering-can-deck-browser-plot-3",
    "watering-can-deck-browser-plot-5",
    "watering-can-overview-plot-2",
    "watering-can-overview-plot-4",
    "watering-can-overview-plot-6",
})


RESIZE_MATRIX_SPECS: tuple[
    tuple[str, str, str, int, int, int, int], ...
] = (
    ("resize-dashboard-minimum", "dashboard", "default-to-minimum", 620, 520, 1240, 840),
    ("resize-dashboard-content-699", "dashboard", "default-to-below-700", 723, 700, 1240, 840),
    ("resize-dashboard-content-701", "dashboard", "default-to-above-700", 725, 700, 1240, 840),
    ("resize-dashboard-content-819", "dashboard", "default-to-below-820", 843, 720, 1240, 840),
    ("resize-dashboard-content-821", "dashboard", "default-to-above-820", 845, 720, 1240, 840),
    ("resize-dashboard-content-899", "dashboard", "default-to-below-900", 923, 740, 1240, 840),
    ("resize-dashboard-content-901", "dashboard", "default-to-above-900", 925, 740, 1240, 840),
    ("resize-dashboard-content-999", "dashboard", "default-to-below-1000", 1023, 760, 1240, 840),
    ("resize-dashboard-content-1001", "dashboard", "default-to-above-1000", 1025, 760, 1240, 840),
    ("resize-dashboard-content-1359", "dashboard", "default-to-below-1360", 1383, 900, 1240, 840),
    ("resize-dashboard-content-1361", "dashboard", "default-to-above-1360", 1385, 900, 1240, 840),
    ("resize-dashboard-default", "dashboard", "minimum-to-default", 1240, 840, 620, 520),
    ("resize-dashboard-large", "dashboard", "default-to-large", 1440, 960, 1240, 840),
    ("resize-settings-minimum", "settings", "default-to-minimum", 560, 420, 980, 680),
    ("resize-settings-content-699", "settings", "default-to-below-700", 747, 620, 980, 680),
    ("resize-settings-content-701", "settings", "default-to-above-700", 749, 620, 980, 680),
    ("resize-settings-content-759", "settings", "default-to-below-760", 807, 650, 980, 680),
    ("resize-settings-content-761", "settings", "default-to-above-760", 809, 650, 980, 680),
    ("resize-settings-default", "settings", "minimum-to-default", 980, 680, 560, 420),
    ("resize-settings-large", "settings", "default-to-large", 1000, 820, 980, 680),
    ("resize-progress-minimum", "progress", "default-to-minimum", 720, 500, 940, 680),
    ("resize-progress-content-819", "progress", "default-to-below-820", 867, 620, 940, 680),
    ("resize-progress-content-821", "progress", "default-to-above-820", 869, 620, 940, 680),
    ("resize-progress-default", "progress", "minimum-to-default", 940, 680, 720, 500),
    ("resize-progress-large", "progress", "default-to-large", 1000, 820, 940, 680),
    ("resize-customize-minimum", "customize", "default-to-minimum", 680, 480, 1040, 700),
    ("resize-customize-content-819", "customize", "default-to-below-820", 867, 620, 1040, 700),
    ("resize-customize-content-821", "customize", "default-to-above-820", 869, 620, 1040, 700),
    ("resize-customize-default", "customize", "minimum-to-default", 1040, 700, 680, 480),
    ("resize-customize-large", "customize", "default-to-large", 1120, 860, 1040, 700),
    ("resize-nursery-minimum", "nursery", "default-to-minimum", 640, 460, 840, 640),
    ("resize-nursery-content-759", "nursery", "default-to-below-760", 795, 600, 840, 640),
    ("resize-nursery-content-761", "nursery", "default-to-above-760", 797, 600, 840, 640),
    ("resize-nursery-default", "nursery", "minimum-to-default", 840, 640, 640, 460),
    ("resize-nursery-large", "nursery", "default-to-large", 1050, 800, 840, 640),
    ("resize-story-minimum", "story", "default-to-minimum", 480, 400, 640, 520),
    ("resize-story-content-539", "story", "default-to-below-540", 587, 500, 640, 520),
    ("resize-story-content-541", "story", "default-to-above-540", 589, 500, 640, 520),
    ("resize-story-default", "story", "minimum-to-default", 640, 520, 480, 400),
    ("resize-story-large", "story", "default-to-large", 640, 680, 640, 520),
    ("resize-starter-confirmation-minimum", "starter-confirmation", "default-to-minimum", 360, 250, 480, 300),
    ("resize-starter-confirmation-content-399", "starter-confirmation", "default-to-below-400", 447, 280, 480, 300),
    ("resize-starter-confirmation-content-401", "starter-confirmation", "default-to-above-400", 449, 280, 480, 300),
    ("resize-starter-confirmation-default", "starter-confirmation", "minimum-to-default", 480, 300, 360, 250),
    ("resize-starter-confirmation-large", "starter-confirmation", "default-to-large", 520, 360, 480, 300),
    ("resize-fertilizer-minimum", "fertilizer", "default-to-minimum", 520, 460, 600, 580),
    ("resize-fertilizer-default", "fertilizer", "minimum-to-default", 600, 580, 520, 460),
    ("resize-fertilizer-large", "fertilizer", "default-to-large", 760, 760, 600, 580),
    ("resize-fertilizer-replacement-minimum", "fertilizer-replacement", "default-to-minimum", 420, 400, 480, 420),
    ("resize-fertilizer-replacement-content-399", "fertilizer-replacement", "default-to-below-400", 443, 420, 480, 420),
    ("resize-fertilizer-replacement-content-401", "fertilizer-replacement", "default-to-above-400", 445, 420, 480, 420),
    ("resize-fertilizer-replacement-default", "fertilizer-replacement", "minimum-to-default", 480, 420, 420, 400),
    ("resize-fertilizer-replacement-large", "fertilizer-replacement", "default-to-large", 560, 500, 480, 420),
    ("resize-species-overview-minimum", "species-overview", "default-to-minimum", 500, 420, 560, 500),
    ("resize-species-overview-default", "species-overview", "minimum-to-default", 560, 500, 500, 420),
    ("resize-species-overview-large", "species-overview", "default-to-large", 760, 700, 560, 500),
)


def start_capture(app: Any) -> None:
    """Launch the UI-face capture sequence for a running add-on instance."""
    _UiFaceCaptureRunner(app).start()


class _UiFaceCaptureRunner:
    def __init__(self, app: Any) -> None:
        self.app = app
        self.capture_root = Path(
            os.environ.get(
                "ANKI_GARDEN_UI_CAPTURE_DIR",
                os.environ.get(
                    "ANKI_GARDEN_CAPTURE_DIR",
                    str(Path(__file__).resolve().parent / ".." / "build" / "ui-face-captures"),
                ),
            )
        ).expanduser()
        self.session_dir = self.capture_root / datetime.now().strftime("%Y%m%d-%H%M%S")
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self._screenshots: list[str] = []
        self._capture_records: list[dict[str, Any]] = []
        self._capture_annotations: dict[str, dict[str, Any]] = {}
        self._text_layout_warnings: list[dict[str, Any]] = []
        self._failures: list[dict[str, str]] = []
        self._step_index = 0
        self._capture_index = 1
        self._starter_seed_attempts = 0
        self._capture_display = "primary"
        self._capture_force_primary = False
        self._requested_scale_factor = os.environ.get("QT_SCALE_FACTOR", "system")
        self._active_geometry_request: dict[str, Any] | None = None
        self._phase = "starter"
        self._starter_steps = [
            self._capture_starter_deck_browser,
            self._capture_starter_overview,
            self._capture_starter_garden,
            self._capture_starter_nursery,
            self._capture_starter_confirmation,
            self._capture_starter_action_above_footer,
        ]
        self._release_steps = [
            self._capture_deck_browser,
            self._capture_overview,
            self._capture_full_garden,
            self._capture_hover_outline,
            self._capture_selected_card,
            self._capture_nurture,
            self._capture_fertilize,
            self._capture_fertilize_affordable,
            self._capture_fertilize_active,
            self._capture_move,
            self._capture_story,
            self._capture_active_deck_browser_after_nurture,
            self._capture_active_overview_after_nurture,
            self._capture_growth_zero,
            self._capture_growth_nonzero,
            self._capture_streak_new,
            self._capture_streak_active,
            self._capture_coins_zero,
            self._capture_coins_activity,
            self._capture_progress_today,
            self._capture_progress_achievements,
            self._capture_progress_collection,
            self._capture_species_overview,
            self._capture_customize_garden,
            self._capture_customize_effects_on,
            self._capture_customize_effects_off,
            self._capture_nursery_plants,
            self._capture_nursery_fertilizer_booster,
            self._capture_nursery_garden_spaces,
            self._capture_nursery_weather_scenery,
            self._capture_addon_settings_menu,
            self._capture_settings_display,
            self._capture_settings_display_advanced,
            self._capture_settings_troubleshooting,
            self._capture_settings_warning,
            self._capture_long_garden_name,
            self._capture_long_plant_name,
            self._capture_four_digit_coin_balance,
            self._capture_growth_near_stage_completion,
            self._capture_all_six_beds,
            self._capture_all_six_stages,
            self._capture_fully_grown_without_fertilize,
            *(lambda slot=slot: self._capture_popover_slot(slot) for slot in range(6)),
            self._capture_move_mixed_destinations,
            self._capture_fertilizer_expiring,
            self._capture_fertilizer_replacement_confirmation,
            *(
                lambda slot=slot: self._capture_watering_can_garden_plot(slot)
                for slot in range(6)
            ),
            *(
                lambda slot=slot: self._capture_watering_can_home_plot(
                    slot,
                    "deckBrowser",
                )
                for slot in (0, 2, 4)
            ),
            *(
                lambda slot=slot: self._capture_watering_can_home_plot(
                    slot,
                    "overview",
                )
                for slot in (1, 3, 5)
            ),
            self._capture_collection_several,
            self._capture_collection_no_matches,
            self._capture_achievement_completed,
            self._capture_clear_recall_conditions,
            self._capture_streak_at_risk,
            self._capture_streak_missed_day,
            self._capture_streak_reward_states,
            self._capture_nursery_owned_item,
            self._capture_nursery_locked_item,
            self._capture_nursery_purchase_success,
            self._capture_nursery_final_row,
            self._capture_missing_artwork_fallback,
            self._capture_settings_unsaved,
            self._capture_settings_validation_error,
            self._capture_diagnostics_expanded,
            self._capture_production_controls_absent,
            self._capture_reduced_motion,
            self._capture_keyboard_focus,
            self._capture_narrow_window,
            self._capture_display_scaling,
            self._capture_display_scaling_200_representative,
            *(
                lambda spec=spec: self._capture_resize_matrix_face(spec)
                for spec in RESIZE_MATRIX_SPECS
            ),
        ]
        self._capture_profile = str(
            os.environ.get("ANKI_GARDEN_CAPTURE_PROFILE", "full") or "full"
        ).strip().lower()
        self._capture_face_groups = CAPTURE_FACE_GROUPS
        if self._capture_profile == "watering-can":
            # The targeted regression profile still seeds through the real
            # first-run transaction, but does not spend time screenshotting
            # unrelated interfaces. The full v8 release contract remains the
            # default and is unchanged.
            self._capture_face_groups = WATERING_CAN_CAPTURE_FACE_GROUPS
            self._starter_steps = []
            self._release_steps = [
                self._capture_nurture,
                self._capture_customize_garden,
                self._capture_settings_display,
                self._capture_all_six_beds,
                *(
                    lambda slot=slot: self._capture_watering_can_garden_plot(slot)
                    for slot in range(6)
                ),
                *(
                    lambda slot=slot: self._capture_watering_can_home_plot(
                        slot,
                        "deckBrowser",
                    )
                    for slot in (0, 2, 4)
                ),
                *(
                    lambda slot=slot: self._capture_watering_can_home_plot(
                        slot,
                        "overview",
                    )
                    for slot in (1, 3, 5)
                ),
                self._capture_reduced_motion,
                self._capture_narrow_window,
                self._capture_display_scaling,
                self._capture_display_scaling_200_representative,
            ]
        elif self._capture_profile == "watering-can-home":
            self._capture_face_groups = WATERING_CAN_HOME_CAPTURE_FACE_GROUPS
            self._starter_steps = []
            self._release_steps = [
                *(
                    lambda slot=slot: self._capture_watering_can_home_plot(
                        slot,
                        "deckBrowser",
                    )
                    for slot in (0, 2, 4)
                ),
                *(
                    lambda slot=slot: self._capture_watering_can_home_plot(
                        slot,
                        "overview",
                    )
                    for slot in (1, 3, 5)
                ),
            ]
        elif self._capture_profile != "full":
            self._failures.append({
                "label": "capture-profile",
                "reason": f"Unsupported capture profile: {self._capture_profile}",
            })
        self._capture_face_labels = tuple(
            label
            for _group, labels in self._capture_face_groups
            for label in labels
        )
        self._steps = self._starter_steps

    def start(self) -> None:
        """Kick off capture after collection load and dashboard prerequisites."""
        self._wait_for_collection(self._prepare_capture_window, tries=120)

    def _prepare_capture_window(self) -> None:
        self._move_to_capture_display(mw)
        QTimer.singleShot(300, self._prepare_starter_phase)

    def _prepare_starter_phase(self, *, tries: int = 80) -> None:
        """Require the disposable profile's untouched first-run state."""
        state = getattr(self.app.storage, "state", None)
        if state is None:
            if tries <= 0:
                self._failures.append({
                    "label": "starter-state",
                    "reason": "Garden state was unavailable before first-run capture",
                })
                self._next_step()
                return
            QTimer.singleShot(
                120,
                lambda: self._prepare_starter_phase(tries=tries - 1),
            )
            return
        if bool(getattr(state, "starter_selection_complete", False)) or list(
            getattr(state, "plants", []) or []
        ):
            self._failures.append({
                "label": "starter-state",
                "reason": "Disposable profile was not in untouched first-run state",
            })
        self._next_step()

    def _move_to_capture_display(self, widget: Any | None) -> None:
        """Move capture windows fully onto the selected display."""
        if widget is None:
            return
        try:
            screens = list(QGuiApplication.screens())
        except Exception:
            screens = []
        if not screens:
            return
        use_secondary = (
            os.environ.get("ANKI_GARDEN_CAPTURE_SECOND_MONITOR", "1").lower()
            not in {"0", "false", "no"}
            and len(screens) >= 2
            and not self._capture_force_primary
        )
        screen = screens[1] if use_secondary else QGuiApplication.primaryScreen()
        screen = screen or screens[0]
        try:
            handle = widget.windowHandle()
            if handle is not None:
                handle.setScreen(screen)
            geometry = screen.availableGeometry()
            frame = widget.frameGeometry()
            frame_width = max(int(frame.width()), int(widget.width()))
            frame_height = max(int(frame.height()), int(widget.height()))
            inset_x = max(0, min(24, int(geometry.width()) - frame_width))
            inset_y = max(0, min(24, int(geometry.height()) - frame_height))
            widget.move(geometry.x() + inset_x, geometry.y() + inset_y)
            self._capture_display = "secondary" if use_secondary else "primary"
        except Exception:
            logger.debug("Anki Garden capture: could not move to selected display", exc_info=True)

    def _prepare_capture_state(self) -> None:
        if self._ensure_capture_state():
            reset = getattr(mw, "reset", None)
            if callable(reset):
                try:
                    reset()
                except Exception:
                    logger.debug("Anki Garden capture: seeded Home refresh failed", exc_info=True)
            self._phase = "release"
            self._steps = self._release_steps
            self._step_index = 0
            QTimer.singleShot(800, self._next_step)
            return
        if self._starter_seed_attempts >= 80:
            self._next_step()
            return
        self._starter_seed_attempts += 1
        QTimer.singleShot(250, self._prepare_capture_state)

    def _ensure_capture_state(self) -> bool:
        """Make capture deterministic with a planted, not-yet-nurtured starter.

        The release sequence captures the consequential boundary on both sides:
        ``choose_starter`` persists the planted starter and its no-active-plant
        sentinel, then the later Nurture face uses the normal dashboard action
        to make the active assignment. Capture setup must not skip that boundary.
        """
        state = getattr(self.app.storage, "state", None)
        if state is None:
            return False
        plants = list(getattr(state, "plants", []) or [])
        if bool(getattr(state, "starter_selection_complete", False)) and plants:
            return True
        ready = getattr(self.app.engine, "release_ready_species", None)
        choose_starter = getattr(self.app.engine, "choose_starter", None)
        if ready is None or choose_starter is None:
            return False
        try:
            candidates = list(ready())
        except Exception:
            return False
        if not candidates:
            return False
        species = str(candidates[0]).lower()
        try:
            ok, _message, plant = choose_starter(species)
            if ok and plant is not None:
                return True
        except Exception:
            logger.debug("Anki Garden capture: starter bootstrap waiting for scheduler", exc_info=True)
        return False

    def _next_step(self) -> None:
        if self._step_index >= len(self._steps):
            if self._phase == "starter":
                self._phase = "seeding"
                self._close_top_level_dialogs()
                self._close_dashboard()
                QTimer.singleShot(350, self._prepare_capture_state)
                return
            self._finish()
            return
        current = self._steps[self._step_index]
        self._step_index += 1
        try:
            current()
        except Exception:
            logger.exception("Anki Garden capture: step failed, moving on")
            self._next_after(300)

    def _next_after(self, delay_ms: int) -> None:
        QTimer.singleShot(max(80, int(delay_ms)), self._next_step)

    def _wait_for_collection(self, ready: Callable[[], None], *, tries: int = 40) -> None:
        collection = getattr(mw, "col", None)
        if collection is not None and getattr(collection, "db", None) is not None:
            ready()
            return
        if tries <= 0:
            ready()
            return
        QTimer.singleShot(120, lambda: self._wait_for_collection(ready, tries=tries - 1))

    def _wait_for_dashboard(self, ready: Callable[[], None], *, tries: int = 80) -> None:
        dashboard = getattr(self.app, "dashboard", None)
        visible = False
        if dashboard is not None:
            try:
                visible = bool(dashboard.isVisible())
            except Exception:
                visible = True
        if visible:
            ready()
            return
        if tries <= 0:
            ready()
            return
        QTimer.singleShot(120, lambda: self._wait_for_dashboard(ready, tries=tries - 1))

    def _wait_for(
        self,
        predicate: Callable[[], bool],
        on_ready: Callable[[], None],
        *,
        tries: int = 80,
        failure_label: str = "",
        failure_reason: str = "",
    ) -> None:
        try:
            if predicate():
                on_ready()
                return
        except Exception:
            pass
        if tries <= 0:
            if failure_label:
                self._failures.append({
                    "label": failure_label,
                    "reason": failure_reason or "Timed out waiting for the requested UI surface",
                })
                self._next_after(120)
                return
            on_ready()
            return
        QTimer.singleShot(
            120,
            lambda: self._wait_for(
                predicate,
                on_ready,
                tries=tries - 1,
                failure_label=failure_label,
                failure_reason=failure_reason,
            ),
        )

    def _wait_for_home_surface(
        self,
        state: str,
        on_ready: Callable[[], None],
        *,
        tries: int = 100,
    ) -> None:
        if str(getattr(mw, "state", "")) != state:
            if tries <= 0:
                self._failures.append({"label": state, "reason": "Anki surface did not become active"})
                self._next_after(120)
                return
            QTimer.singleShot(
                120,
                lambda: self._wait_for_home_surface(state, on_ready, tries=tries - 1),
            )
            return
        web = getattr(mw, "web", None)
        evaluate = getattr(web, "evalWithCallback", None)
        if not callable(evaluate):
            on_ready()
            return
        script = """
            (() => {
              const root = document.querySelector('#ag-home-root');
              if (!root || !['success', 'partial'].includes(root.dataset.state)) return false;
              const rect = root.getBoundingClientRect();
              if (rect.width < 100 || rect.height < 100) return false;
              return [...root.querySelectorAll('img')].every(img => img.complete);
            })()
        """

        settled = False

        def retry_or_fail() -> None:
            if tries <= 0:
                self._failures.append({"label": state, "reason": "Home widget never reached painted success or partial state"})
                self._next_after(120)
            else:
                QTimer.singleShot(
                    120,
                    lambda: self._wait_for_home_surface(state, on_ready, tries=tries - 1),
                )

        def resolved(ready: Any) -> None:
            nonlocal settled
            if settled:
                return
            settled = True
            if bool(ready):
                QTimer.singleShot(32, on_ready)
            else:
                retry_or_fail()

        def callback_watchdog() -> None:
            """Retry if a page transition discards WebEngine's JS callback."""

            nonlocal settled
            if settled:
                return
            settled = True
            retry_or_fail()

        try:
            evaluate(script, resolved)
            QTimer.singleShot(750, callback_watchdog)
        except Exception:
            settled = True
            retry_or_fail()

    def _with_dashboard(self, on_ready: Callable[[], None]) -> None:
        def prepare_dashboard() -> None:
            dashboard = getattr(self.app, "dashboard", None)
            toast = getattr(dashboard, "toast_region", None)
            clear_toast = getattr(toast, "clear", None)
            if callable(clear_toast):
                clear_toast()
            self._move_to_capture_display(dashboard)
            on_ready()

        dashboard = getattr(self.app, "dashboard", None)
        try:
            if dashboard is not None and bool(dashboard.isVisible()):
                prepare_dashboard()
                return
        except Exception:
            pass
        self.app.open_dashboard()
        self._wait_for_dashboard(prepare_dashboard)

    def _record_nurtured_marker_audit(
        self,
        label: str,
        audit: dict[str, Any],
        issues: list[str],
    ) -> None:
        """Attach one fail-closed marker audit to the capture manifest."""

        passed = not issues
        audit["passed"] = passed
        if issues:
            audit["issues"] = list(dict.fromkeys(issues))
        annotation = self._capture_annotations.setdefault(label, {})
        annotation["nurtured_marker"] = audit
        annotation["passed"] = bool(annotation.get("passed", True)) and passed
        if issues:
            self._failures.append({
                "label": label,
                "reason": "Watering-can geometry audit failed: " + "; ".join(
                    dict.fromkeys(issues)
                ),
            })

    def _audit_home_nurtured_marker(self, label: str) -> None:
        """Validate the shared marker result embedded in Home HTML."""

        from .ui.plant_display import (
            NURTURED_MARKER_MAX_GROUND_DELTA_RATIO,
            NURTURED_MARKER_MAX_PLANT_DISTANCE_RATIO,
        )

        issues: list[str] = []
        html_builder = getattr(self.app, "_home_garden_html_for_injection", None)
        html = html_builder() if callable(html_builder) else ""
        markers = re.findall(
            r'<img[^>]*data-testid="home-nurturing-marker"[^>]*>',
            str(html),
        )
        marker = markers[0] if markers else ""
        state = getattr(self.app.storage, "state", None)
        active_id = str(getattr(state, "active_plant_id", "") or "")
        active = next((
            plant for plant in list(getattr(state, "plants", ()) or ())
            if str(getattr(plant, "plant_id", "") or "") == active_id
        ), None)
        expected_slot = int(getattr(active, "slot_index", -1) or 0) if active is not None else -1
        expected_side = "left" if expected_slot % 2 == 0 else "right"
        expected_orientation = (
            "spout-right" if expected_side == "left" else "spout-left"
        )
        if active is None:
            issues.append("active nurtured plant was unavailable")
        if len(markers) != 1:
            issues.append(f"expected one rendered marker, found {len(markers)}")
        for attribute, expected in (
            ("data-marker-slot", str(expected_slot)),
            ("data-marker-side", expected_side),
            ("data-marker-orientation", expected_orientation),
        ):
            if f'{attribute}="{expected}"' not in marker:
                issues.append(f"{attribute} did not equal {expected}")

        rect_match = re.search(r'data-marker-rect="([^"]+)"', marker)
        pulse_match = re.search(r'data-marker-pulse="([^"]+)"', marker)
        target_match = re.search(
            r'data-marker-target-ground="([^"]+)"', marker
        )
        planter_match = re.search(
            r'data-marker-planter-rect="([^"]+)"', marker
        )

        def parse_values(
            match: re.Match[str] | None,
            name: str,
            count: int,
        ) -> list[float]:
            if match is None:
                issues.append(f"{name} metadata was missing")
                return []
            try:
                values = [float(value) for value in match.group(1).split(",")]
            except (TypeError, ValueError):
                values = []
            if len(values) != count:
                issues.append(f"{name} metadata was invalid")
            return values

        rect = parse_values(rect_match, "marker rectangle", 4)
        pulse = parse_values(pulse_match, "pulse envelope", 4)
        target_ground = parse_values(target_match, "target ground", 2)
        planter = parse_values(planter_match, "planter rectangle", 4)
        if len(rect) == 4 and not (44.0 <= rect[2] <= 88.0 and rect[2] == rect[3]):
            issues.append("marker rectangle did not preserve its 44-88 pixel square")
        if len(pulse) == 4 and not (
            pulse[0] >= 0.0
            and pulse[1] >= 0.0
            and pulse[0] + pulse[2] <= 1000.0
            and pulse[1] + pulse[3] <= 420.0
        ):
            issues.append("pulse envelope extended outside the Home scene")
        plant_distance: float | None = None
        ground_delta: float | None = None
        if len(rect) == 4 and len(target_ground) == 2 and len(planter) == 4:
            marker_center_x = rect[0] + rect[2] / 2
            marker_ground_y = rect[1] + rect[3] * 0.916
            plant_distance = math.hypot(
                marker_center_x - target_ground[0],
                marker_ground_y - target_ground[1],
            )
            ground_delta = abs(marker_ground_y - target_ground[1])
            if plant_distance > planter[2] * NURTURED_MARKER_MAX_PLANT_DISTANCE_RATIO:
                issues.append("marker was too far from the nurtured plant")
            if ground_delta > rect[2] * NURTURED_MARKER_MAX_GROUND_DELTA_RATIO:
                issues.append("marker ground contact was detached from the plant")
            if expected_side == "left" and marker_center_x >= target_ground[0]:
                issues.append("left marker crossed the nurtured plant center")
            if expected_side == "right" and marker_center_x <= target_ground[0]:
                issues.append("right marker crossed the nurtured plant center")
        self._record_nurtured_marker_audit(
            label,
            {
                "renderer": "home-html",
                "expected_slot": expected_slot,
                "marker_count": len(markers),
                "side": expected_side,
                "orientation": expected_orientation,
                "rect": rect,
                "pulse_bounds": pulse,
                "target_ground": target_ground,
                "planter_rect": planter,
                "plant_distance": plant_distance,
                "ground_contact_delta": ground_delta,
            },
            issues,
        )

    def _audit_qt_nurtured_marker(self, label: str, widget: QWidget) -> None:
        """Validate every visible native scene's marker and reserved envelope."""

        from .ui.plant_display import (
            NURTURED_MARKER_MAX_GROUND_DELTA_RATIO,
            NURTURED_MARKER_MAX_PLANT_DISTANCE_RATIO,
            PlantPlacement,
            Rect,
            planter_draw_rect,
        )

        candidates = [widget, *widget.findChildren(QWidget)]
        scenes: list[Any] = []
        for candidate in candidates:
            geometry = getattr(candidate, "nurtured_marker_geometry", None)
            if not callable(geometry):
                continue
            try:
                if candidate is not widget and not candidate.isVisibleTo(widget):
                    continue
            except RuntimeError:
                continue
            scenes.append(candidate)
        issues: list[str] = []
        scene_audits: list[dict[str, Any]] = []
        if not scenes:
            issues.append("no visible native Garden scene was available")

        qt_app = QApplication.instance()
        for scene in scenes:
            scene.repaint()
            if qt_app is not None:
                qt_app.processEvents()
            # QWidget.repaint() may remain deferred for a child canvas on
            # macOS. A local grab forces the exact paint path synchronously so
            # the diagnostic below cannot describe the preceding capture.
            probe = scene.grab()
            if probe is None or probe.isNull():
                issues.append(f"{type(scene).__name__} marker probe was null")
                continue
            payload = getattr(scene, "scene", {})
            plants = [
                plant for plant in list(payload.get("plants", ()) or ())
                if isinstance(plant, dict)
            ] if isinstance(payload, dict) else []
            active = [plant for plant in plants if bool(plant.get("is_active"))]
            if len(active) != 1:
                issues.append(
                    f"{type(scene).__name__} contained {len(active)} active plants"
                )
            expected_slot = int(active[0].get("slot_index", -1)) if active else -1
            expected_side = "left" if expected_slot % 2 == 0 else "right"
            expected_orientation = (
                "spout-right" if expected_side == "left" else "spout-left"
            )
            expected_asset = (
                "nurtured_marker_spout_right"
                if expected_orientation == "spout-right"
                else "nurtured_marker"
            )
            diagnostic = scene.nurtured_marker_geometry()
            if not isinstance(diagnostic, dict):
                issues.append(f"{type(scene).__name__} did not resolve a marker")
                continue
            if int(diagnostic.get("slot_index", -1)) != expected_slot:
                issues.append(f"{type(scene).__name__} marker targeted the wrong plot")
            if str(diagnostic.get("side", "")) != expected_side:
                issues.append(f"{type(scene).__name__} marker used the wrong outer side")
            if str(diagnostic.get("orientation", "")) != expected_orientation:
                issues.append(f"{type(scene).__name__} marker spout did not point inward")
            if str(diagnostic.get("asset_key", "")) != expected_asset:
                issues.append(f"{type(scene).__name__} marker used the wrong asset")
            if bool(diagnostic.get("used_fallback", True)):
                issues.append(f"{type(scene).__name__} required degraded placement")
            try:
                rect_values = [float(value) for value in diagnostic["rect"]]
                pulse_values = [float(value) for value in diagnostic["pulse_bounds"]]
                marker_rect = Rect(*rect_values)
                pulse_rect = Rect(*pulse_values)
            except (KeyError, TypeError, ValueError):
                issues.append(f"{type(scene).__name__} exposed invalid marker geometry")
                continue
            if not (44.0 <= marker_rect.width <= 88.0 and marker_rect.width == marker_rect.height):
                issues.append(f"{type(scene).__name__} marker size was outside 44-88 pixels")
            if not (
                pulse_rect.x >= 0.0
                and pulse_rect.y >= 0.0
                and pulse_rect.right <= float(scene.width())
                and pulse_rect.bottom <= float(scene.height())
            ):
                issues.append(f"{type(scene).__name__} pulse envelope left the canvas")

            layout_builder = getattr(scene, "_layout_plants", None)
            rows = (
                layout_builder(scene.width(), scene.height())
                if callable(layout_builder) else []
            )
            occupied_layouts = [
                row[1] for row in rows
                if isinstance(row, tuple)
                and len(row) >= 2
                and isinstance(row[1], PlantPlacement)
            ]
            family_builder = getattr(scene, "_planter_family_record", None)
            family = family_builder() if callable(family_builder) else {}
            target_layout = next(
                (
                    layout for layout in occupied_layouts
                    if layout.slot_index == expected_slot
                ),
                None,
            )
            plant_distance: float | None = None
            ground_delta: float | None = None
            if target_layout is None:
                issues.append(f"{type(scene).__name__} target layout was unavailable")
            else:
                target_planter = planter_draw_rect(target_layout, family)
                marker_center_x = marker_rect.x + marker_rect.width / 2
                marker_ground_y = marker_rect.y + marker_rect.height * 0.916
                plant_distance = math.hypot(
                    marker_center_x - target_layout.ground_anchor[0],
                    marker_ground_y - target_layout.ground_anchor[1],
                )
                ground_delta = abs(
                    marker_ground_y - target_layout.ground_anchor[1]
                )
                if (
                    plant_distance
                    > target_planter.width
                    * NURTURED_MARKER_MAX_PLANT_DISTANCE_RATIO
                ):
                    issues.append(
                        f"{type(scene).__name__} marker was too far from the nurtured plant"
                    )
                if (
                    ground_delta
                    > marker_rect.width * NURTURED_MARKER_MAX_GROUND_DELTA_RATIO
                ):
                    issues.append(
                        f"{type(scene).__name__} marker ground contact was detached"
                    )
                if expected_side == "left" and marker_center_x >= target_layout.ground_anchor[0]:
                    issues.append(f"{type(scene).__name__} left marker crossed the plant center")
                if expected_side == "right" and marker_center_x <= target_layout.ground_anchor[0]:
                    issues.append(f"{type(scene).__name__} right marker crossed the plant center")
            blockers = [layout.visible.expanded(4.0, 4.0) for layout in occupied_layouts]
            for qt_rect in (
                getattr(scene, "_card_connector_rect", None),
                getattr(scene, "_status_rect", None),
            ):
                if qt_rect is not None:
                    blockers.append(Rect(
                        qt_rect.x(),
                        qt_rect.y(),
                        qt_rect.width(),
                        qt_rect.height(),
                    ).expanded(4.0, 4.0))
            if any(pulse_rect.intersects(blocker) for blocker in blockers):
                issues.append(
                    f"{type(scene).__name__} pulse envelope overlapped protected geometry"
                )
            scene_audits.append({
                "widget": type(scene).__name__,
                "expected_slot": expected_slot,
                "side": str(diagnostic.get("side", "")),
                "orientation": str(diagnostic.get("orientation", "")),
                "asset_key": str(diagnostic.get("asset_key", "")),
                "rect": rect_values,
                "pulse_bounds": pulse_values,
                "plant_distance": plant_distance,
                "ground_contact_delta": ground_delta,
                "used_fallback": bool(diagnostic.get("used_fallback", True)),
            })
        self._record_nurtured_marker_audit(
            label,
            {
                "renderer": "qt",
                "scene_count": len(scenes),
                "scenes": scene_audits,
            },
            issues,
        )

    def _audit_nurtured_marker_capture(self, label: str, widget: QWidget) -> None:
        if label not in NURTURED_MARKER_GEOMETRY_CAPTURE_LABELS:
            return
        if widget is mw:
            self._audit_home_nurtured_marker(label)
        else:
            self._audit_qt_nurtured_marker(label, widget)

    @staticmethod
    def _home_pixmap_metrics(
        pixmap: Any,
        *,
        expected_width: int,
        expected_height: int,
    ) -> dict[str, Any]:
        """Measure both generic image content and Garden-specific evidence."""

        image = pixmap.toImage()
        width = int(image.width())
        height = int(image.height())
        colors: dict[int, int] = {}
        saturated_samples = 0
        if width > 0 and height > 0:
            x_step = max(1, width // 31)
            y_step = max(1, height // 23)
            for y in range(y_step // 2, height, y_step):
                for x in range(x_step // 2, width, x_step):
                    color = image.pixelColor(x, y)
                    rgba = int(color.rgba())
                    colors[rgba] = colors.get(rgba, 0) + 1
                    if int(color.saturation()) >= 28:
                        saturated_samples += 1
        sample_count = sum(colors.values())
        dominant_ratio = (
            max(colors.values()) / sample_count
            if colors and sample_count else 1.0
        )
        saturated_ratio = (
            saturated_samples / sample_count if sample_count else 0.0
        )

        # Every release Home state has the same mint primary action and dark
        # Garden shell. Sampling both is a semantic identity gate: a colorful
        # desktop wallpaper, a transparent WebEngine layer, or the wrong native
        # window can no longer satisfy the capture contract merely by being
        # non-uniform.
        semantic_step = max(1, min(width, height) // 120)
        semantic_samples = 0
        brand_samples = 0
        dark_samples = 0
        for y in range(semantic_step // 2, height, semantic_step):
            for x in range(semantic_step // 2, width, semantic_step):
                color = image.pixelColor(x, y)
                rgb = (int(color.red()), int(color.green()), int(color.blue()))
                semantic_samples += 1
                if max(
                    abs(channel - expected)
                    for channel, expected in zip(rgb, HOME_CAPTURE_BRAND_RGB)
                ) <= 22:
                    brand_samples += 1
                if any(
                    max(
                        abs(channel - expected)
                        for channel, expected in zip(rgb, dark_rgb)
                    ) <= 22
                    for dark_rgb in HOME_CAPTURE_DARK_RGB
                ):
                    dark_samples += 1
        brand_ratio = (
            brand_samples / semantic_samples if semantic_samples else 0.0
        )
        dark_ratio = (
            dark_samples / semantic_samples if semantic_samples else 0.0
        )
        actual_aspect = width / height if width > 0 and height > 0 else 0.0
        expected_aspect = (
            max(1, int(expected_width)) / max(1, int(expected_height))
        )
        aspect_ratio_error = (
            abs(actual_aspect / expected_aspect - 1.0)
            if actual_aspect > 0 and expected_aspect > 0 else 1.0
        )
        generic_passed = (
            len(colors) >= 8
            and dominant_ratio < 0.92
            and saturated_ratio >= 0.04
            and aspect_ratio_error <= 0.12
        )
        semantic_passed = brand_ratio >= 0.001 and dark_ratio >= 0.003
        return {
            "sample_count": sample_count,
            "unique_sampled_colors": len(colors),
            "dominant_color_ratio": round(dominant_ratio, 4),
            "saturated_sample_ratio": round(saturated_ratio, 4),
            "semantic_sample_count": semantic_samples,
            "brand_sample_ratio": round(brand_ratio, 4),
            "dark_shell_sample_ratio": round(dark_ratio, 4),
            "actual_aspect_ratio": round(actual_aspect, 4),
            "expected_aspect_ratio": round(expected_aspect, 4),
            "aspect_ratio_error": round(aspect_ratio_error, 4),
            "generic_content_passed": generic_passed,
            "semantic_identity_passed": semantic_passed,
            "passed": generic_passed and semantic_passed,
        }

    def _capture_home_pixmap(self, widget: QWidget) -> tuple[Any | None, str]:
        """Choose the Home image that proves the foreground Garden UI painted."""

        if not self._activate_current_process_window(widget):
            logger.warning(
                "Anki Garden capture: exact Anki Home window did not become foreground"
            )
            return None, "foreground-window-not-ready"

        def capture_candidates() -> list[tuple[str, Any, dict[str, Any]]]:
            candidates: list[tuple[str, Any]] = []
            handle = widget.windowHandle()
            screen = handle.screen() if handle is not None else None
            screen = screen or QGuiApplication.primaryScreen()
            origin = widget.mapToGlobal(widget.rect().topLeft())
            screen_geometry = screen.geometry() if screen is not None else None
            if screen is not None and screen_geometry is not None:
                try:
                    candidates.append((
                        "foreground-screen-region",
                        screen.grabWindow(
                            0,
                            int(origin.x() - screen_geometry.x()),
                            int(origin.y() - screen_geometry.y()),
                            int(widget.width()),
                            int(widget.height()),
                        ),
                    ))
                except Exception:
                    logger.debug(
                        "Anki Garden capture: foreground screen-region capture failed",
                        exc_info=True,
                    )

            # A direct QWidget grab is the reliable fallback when macOS window
            # capture returns the desktop beneath a GPU-composited WebEngine view.
            # Grabbing the WebEngine child separately and painting it into the Qt
            # shell preserves the actual Anki context instead of substituting a
            # synthetic Home mockup.
            try:
                shell_pixmap = widget.grab()
                web = getattr(mw, "web", None)
                if (
                    shell_pixmap is not None
                    and not shell_pixmap.isNull()
                    and web is not None
                    and bool(web.isVisible())
                ):
                    web_pixmap = web.grab()
                    if web_pixmap is not None and not web_pixmap.isNull():
                        painter = QPainter(shell_pixmap)
                        painter.drawPixmap(
                            web.mapTo(widget, web.rect().topLeft()),
                            web_pixmap,
                        )
                        painter.end()
                        candidates.append(("qt-shell-with-webview", shell_pixmap))
                    else:
                        candidates.append(("qt-widget", shell_pixmap))
                elif shell_pixmap is not None:
                    candidates.append(("qt-widget", shell_pixmap))
            except Exception:
                logger.debug(
                    "Anki Garden capture: Qt Home fallback capture failed",
                    exc_info=True,
                )

            if screen is not None:
                try:
                    candidates.append((
                        "native-window",
                        screen.grabWindow(
                            int(widget.winId()),
                            0,
                            0,
                            int(widget.width()),
                            int(widget.height()),
                        ),
                    ))
                except Exception:
                    logger.debug(
                        "Anki Garden capture: native Home window capture failed",
                        exc_info=True,
                    )

            viable: list[tuple[str, Any, dict[str, Any]]] = []
            for method, candidate in candidates:
                if candidate is None or candidate.isNull():
                    continue
                metrics = self._home_pixmap_metrics(
                    candidate,
                    expected_width=int(widget.width()),
                    expected_height=int(widget.height()),
                )
                viable.append((method, candidate, metrics))
            return viable

        for capture_attempt in range(3):
            if capture_attempt and not self._activate_current_process_window(widget):
                continue
            viable = capture_candidates()
            ready = [
                row for row in viable
                if row[2]["passed"]
            ]
            if ready:
                method, pixmap, _metrics = max(
                    ready,
                    key=lambda row: (
                        float(row[2]["brand_sample_ratio"]),
                        float(row[2]["dark_shell_sample_ratio"]),
                    ),
                )
                return pixmap, method

            diagnostic = [
                {
                    "method": method,
                    "pixel_size": [
                        int(candidate.toImage().width()),
                        int(candidate.toImage().height()),
                    ],
                    "generic": bool(metrics["generic_content_passed"]),
                    "semantic": bool(metrics["semantic_identity_passed"]),
                    "brand_ratio": float(metrics["brand_sample_ratio"]),
                }
                for method, candidate, metrics in viable
            ]
            logger.warning(
                "Anki Garden capture: Home candidates on %s display were not "
                "Garden-ready: %s",
                self._capture_display,
                diagnostic,
            )
            if self._capture_display == "secondary" and not self._capture_force_primary:
                # Qt/macOS can report a secondary mixed-DPI QScreen while
                # grabWindow(0, ...) returns that display's entire desktop. The
                # semantic gate is the reliable compatibility test; retry the
                # same real window on primary and keep later captures there.
                self._capture_force_primary = True
                self._move_to_capture_display(widget)
            if capture_attempt < 2:
                time.sleep(0.06)
                app = QApplication.instance()
                if app is not None:
                    app.processEvents()
        return None, "semantic-window-not-ready"

    def _activate_current_process_window(self, widget: QWidget) -> bool:
        """Foreground this Anki process and its exact Home window on macOS."""

        app = QApplication.instance()
        if app is None:
            return False
        try:
            widget.show()
            handle = widget.windowHandle()
            request_activate = getattr(handle, "requestActivate", None)
            if callable(request_activate):
                request_activate()
            widget.raise_()
            widget.activateWindow()
            app.setActiveWindow(widget)
            widget.update()
            web = getattr(mw, "web", None)
            update_web = getattr(web, "update", None)
            if callable(update_web):
                update_web()
            app.processEvents()
        except Exception:
            logger.debug(
                "Anki Garden capture: Qt Home activation failed",
                exc_info=True,
            )
            return False

        try:
            visible = bool(widget.isVisible())
        except RuntimeError:
            return False
        if not visible or platform.system() != "Darwin":
            return visible

        try:
            import ctypes

            objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
            objc_get_class = objc.objc_getClass
            objc_get_class.argtypes = [ctypes.c_char_p]
            objc_get_class.restype = ctypes.c_void_p
            sel_register_name = objc.sel_registerName
            sel_register_name.argtypes = [ctypes.c_char_p]
            sel_register_name.restype = ctypes.c_void_p
            send_pointer = ctypes.CFUNCTYPE(
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_void_p,
            )(("objc_msgSend", objc))
            send_bool = ctypes.CFUNCTYPE(
                ctypes.c_bool,
                ctypes.c_void_p,
                ctypes.c_void_p,
            )(("objc_msgSend", objc))
            send_bool_options = ctypes.CFUNCTYPE(
                ctypes.c_bool,
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_ulong,
            )(("objc_msgSend", objc))
            send_void_pointer = ctypes.CFUNCTYPE(
                None,
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_void_p,
            )(("objc_msgSend", objc))

            running_application_class = objc_get_class(b"NSRunningApplication")
            current_application = send_pointer(
                running_application_class,
                sel_register_name(b"currentApplication"),
            )
            native_view = ctypes.c_void_p(int(widget.winId()))
            native_window = send_pointer(
                native_view,
                sel_register_name(b"window"),
            )
            if not current_application or not native_window:
                return False

            activate_options = (1 << 0) | (1 << 1)
            for _attempt in range(5):
                send_bool_options(
                    current_application,
                    sel_register_name(b"activateWithOptions:"),
                    activate_options,
                )
                send_void_pointer(
                    native_window,
                    sel_register_name(b"makeKeyAndOrderFront:"),
                    None,
                )
                if callable(request_activate):
                    request_activate()
                widget.raise_()
                widget.activateWindow()
                app.setActiveWindow(widget)
                widget.update()
                if callable(update_web):
                    update_web()
                app.processEvents()
                process_active = bool(send_bool(
                    current_application,
                    sel_register_name(b"isActive"),
                ))
                window_is_key = bool(send_bool(
                    native_window,
                    sel_register_name(b"isKeyWindow"),
                ))
                if process_active and window_is_key:
                    # Give the system compositor one bounded frame to publish
                    # the GPU-backed WebEngine surface before screen capture.
                    time.sleep(0.04)
                    app.processEvents()
                    return bool(widget.isVisible())
                time.sleep(0.04)
            return False
        except Exception:
            logger.debug(
                "Anki Garden capture: native current-process activation failed",
                exc_info=True,
            )
            return False

    def _audit_home_pixmap(
        self,
        label: str,
        pixmap: Any,
        *,
        expected_width: int,
        expected_height: int,
    ) -> None:
        """Reject blank, wrong-window, and non-Garden Home captures."""

        metrics = self._home_pixmap_metrics(
            pixmap,
            expected_width=expected_width,
            expected_height=expected_height,
        )
        passed = bool(metrics["passed"])
        annotation = self._capture_annotations.setdefault(label, {})
        annotation["home_pixmap"] = metrics
        annotation["passed"] = bool(annotation.get("passed", True)) and passed
        if not passed:
            self._failures.append({
                "label": label,
                "reason": (
                    "Anki Home capture did not contain the branded Garden "
                    "surface at the expected window geometry "
                    f"(brand ratio {metrics['brand_sample_ratio']:.4f}; "
                    f"dark shell ratio {metrics['dark_shell_sample_ratio']:.4f}; "
                    f"dominant ratio {metrics['dominant_color_ratio']:.4f}; "
                    f"aspect error {metrics['aspect_ratio_error']:.4f})"
                ),
            })

    def _capture_now(self, label: str, widget: Any | None = None) -> None:
        path = self.session_dir / f"{self._capture_index:02d}-{label}.png"
        self._capture_index += 1
        app = QApplication.instance()
        if app is None:
            self._failures.append({"label": label, "reason": "Qt application unavailable"})
            return
        app.processEvents()
        if widget is None:
            self._failures.append({"label": label, "reason": "Expected capture widget was not provided"})
            return
        try:
            if not bool(widget.isVisible()) or widget.width() <= 0 or widget.height() <= 0:
                self._failures.append({"label": label, "reason": "Expected capture widget was not visible with nonzero geometry"})
                return
            self._move_to_capture_display(widget)
            app.processEvents()
            geometry_request = (
                dict(self._active_geometry_request)
                if self._active_geometry_request is not None
                and self._active_geometry_request.get("label") == label
                else None
            )
            family = str(widget.property("windowFamily") or type(widget).__name__)
            requested_size = (
                list(geometry_request["requested_client_size"])
                if geometry_request is not None else
                [int(widget.width()), int(widget.height())]
            )
            if geometry_request is not None:
                requested = geometry_request["requested_client_size"]
                actual = [int(widget.width()), int(widget.height())]
                geometry_request["actual_client_size"] = actual
                exact = actual == requested
                geometry_request["exact_size_reached"] = exact
                if not exact:
                    self._failures.append({
                        "label": label,
                        "reason": (
                            "Window manager or widget constraints clamped the requested "
                            f"client size {requested[0]} by {requested[1]} to "
                            f"{actual[0]} by {actual[1]}"
                        ),
                    })
            if label == "display-scaling-150":
                dashboard = getattr(self.app, "dashboard", None)
                if widget is dashboard:
                    top_bar = dashboard.top_bar
                    scene = dashboard.scene
                    header_bottom = int(
                        top_bar.mapTo(widget, top_bar.rect().bottomLeft()).y()
                    )
                    scene_top = int(
                        scene.mapTo(widget, scene.rect().topLeft()).y()
                    )
                    scene_top_gap = max(0, scene_top - header_bottom - 1)
                    title_stack_extra_height = max(
                        0,
                        int(dashboard.title_stack_widget.height())
                        - int(dashboard.title_stack_widget.sizeHint().height()),
                    )
                    spacing_passed = (
                        scene_top_gap <= 24
                        and title_stack_extra_height <= 16
                    )
                    self._capture_annotations[label] = {
                        "scene_top_gap": scene_top_gap,
                        "maximum_allowed_gap": 24,
                        "title_stack_extra_height": title_stack_extra_height,
                        "maximum_title_stack_extra_height": 16,
                        "header_height": int(top_bar.height()),
                        "feedback_panel_height": int(dashboard.feedback_panel.height()),
                        "feedback_panel_visible": bool(dashboard.feedback_panel.isVisible()),
                        "scene_height": int(scene.height()),
                        "passed": spacing_passed,
                    }
                    if not spacing_passed:
                        self._failures.append({
                            "label": label,
                            "reason": (
                                "Responsive header geometry was over-expanded "
                                f"(scene gap {scene_top_gap}px; title excess "
                                f"{title_stack_extra_height}px)"
                            ),
                        })
            self._audit_nurtured_marker_capture(label, widget)
            if widget is mw:
                pixmap, capture_method = self._capture_home_pixmap(widget)
                annotation = self._capture_annotations.setdefault(label, {})
                annotation["home_capture_method"] = capture_method
            else:
                pixmap = widget.grab()
            if pixmap is None:
                self._failures.append({"label": label, "reason": "Qt returned no pixmap"})
                return
            if pixmap.isNull():
                screen = QGuiApplication.primaryScreen()
                if screen is None:
                    self._failures.append({"label": label, "reason": "No screen available for fallback capture"})
                    return
                try:
                    pixmap = screen.grabWindow(int(widget.winId()))
                except Exception:
                    self._failures.append({"label": label, "reason": "Window fallback capture failed"})
                    return
                if pixmap.isNull():
                    self._failures.append({"label": label, "reason": "Captured pixmap was null"})
                    return
            if widget is mw:
                self._audit_home_pixmap(
                    label,
                    pixmap,
                    expected_width=int(widget.width()),
                    expected_height=int(widget.height()),
                )
            if pixmap.save(str(path), "png"):
                self._screenshots.append(str(path))
                text_layout_warnings = self._find_text_layout_warnings(widget)
                geometry_layout_warnings = self._find_geometry_layout_warnings(widget)
                for warning in text_layout_warnings:
                    warning["capture"] = label
                for warning in geometry_layout_warnings:
                    warning["capture"] = label
                self._text_layout_warnings.extend(text_layout_warnings)
                self._text_layout_warnings.extend(geometry_layout_warnings)
                if text_layout_warnings or geometry_layout_warnings:
                    self._failures.append({
                        "label": label,
                        "reason": (
                            f"Geometry audit found {len(text_layout_warnings)} text "
                            f"warning(s) and {len(geometry_layout_warnings)} layout warning(s)"
                        ),
                    })
                frame = widget.frameGeometry()
                dpr_reader = getattr(widget, "devicePixelRatioF", None)
                device_pixel_ratio = (
                    float(dpr_reader()) if callable(dpr_reader) else
                    float(widget.devicePixelRatio())
                )
                record = {
                    "label": label,
                    "path": str(path),
                    "widget": type(widget).__name__,
                    "window_family": family,
                    "width": int(widget.width()),
                    "height": int(widget.height()),
                    "requested_client_size": (
                        requested_size
                    ),
                    "declared_client_size": (
                        list(geometry_request.get("declared_client_size", requested_size))
                        if geometry_request is not None else requested_size
                    ),
                    "available_screen_size": (
                        geometry_request.get("available_screen_size")
                        if geometry_request is not None else None
                    ),
                    "screen_limited": bool(
                        geometry_request.get("screen_limited", False)
                        if geometry_request is not None else False
                    ),
                    "constraint_limited": bool(
                        geometry_request.get("constraint_limited", False)
                        if geometry_request is not None else False
                    ),
                    "native_normalized": bool(
                        geometry_request.get("native_normalized", False)
                        if geometry_request is not None else False
                    ),
                    "normalization_reason": (
                        str(geometry_request.get("normalization_reason", ""))
                        if geometry_request is not None else ""
                    ),
                    "frame_overhead": (
                        list(geometry_request.get("frame_overhead", [0, 0]))
                        if geometry_request is not None else [0, 0]
                    ),
                    "actual_client_size": [int(widget.width()), int(widget.height())],
                    "frame_size": [int(frame.width()), int(frame.height())],
                    "device_pixel_ratio": device_pixel_ratio,
                    "capture_display": self._capture_display,
                    "layout_mode": str(widget.property("layoutMode") or "default"),
                    "transition_path": (
                        str(geometry_request["transition_path"])
                        if geometry_request is not None else
                        "canonical-open"
                    ),
                    "text_layout_warnings": text_layout_warnings,
                    "geometry_layout_warnings": geometry_layout_warnings,
                }
                annotation = self._capture_annotations.get(label)
                if annotation:
                    record["audit"] = dict(annotation)
                self._capture_records.append(record)
            else:
                self._failures.append({"label": label, "reason": "PNG save failed"})
        except Exception:
            self._failures.append({"label": label, "reason": "Unexpected capture exception"})
            logger.debug("Anki Garden capture: screenshot failed for %s", label, exc_info=True)
        finally:
            if (
                self._active_geometry_request is not None
                and self._active_geometry_request.get("label") == label
            ):
                self._active_geometry_request = None

    @staticmethod
    def _find_geometry_layout_warnings(root: QWidget) -> list[dict[str, Any]]:
        """Report painted children outside their root and forbidden horizontal scroll."""

        warnings: list[dict[str, Any]] = []
        for scroll in root.findChildren(QAbstractScrollArea):
            try:
                if not scroll.isVisibleTo(root):
                    continue
                # QScrollArea reports the visible vertical scrollbar's width as
                # horizontal range until its viewport completes a relayout.
                # Validate real content width against the viewport instead of
                # treating that native scrollbar extent as clipped content.
                content = scroll.widget() if isinstance(scroll, QScrollArea) else None
                content_overflow = (
                    max(0, int(content.width()) - int(scroll.viewport().width()))
                    if content is not None else
                    int(scroll.horizontalScrollBar().maximum())
                )
                if (
                    scroll.horizontalScrollBarPolicy()
                    == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
                    and content_overflow > 0
                ):
                    warnings.append({
                        "kind": "forbidden-horizontal-overflow",
                        "widget": type(scroll).__name__,
                        "object_name": str(scroll.objectName() or ""),
                        "overflow": content_overflow,
                    })
            except Exception:
                logger.debug(
                    "Anki Garden capture: horizontal overflow audit failed",
                    exc_info=True,
                )
        for frame in root.findChildren(QFrame):
            try:
                if not frame.isVisibleTo(root) or frame is root:
                    continue
                # Only immediate painted regions belong to the top-level
                # window boundary audit. Descendants are already constrained
                # by their own frame/scroll viewport, and mapping them to the
                # root misclassifies intentionally scrolled content.
                if frame.parentWidget() is not root:
                    continue
                position = frame.mapTo(root, frame.rect().topLeft())
                left = int(position.x())
                top = int(position.y())
                right = left + int(frame.width())
                bottom = top + int(frame.height())
                if (
                    left < -2
                    or top < -2
                    or right > int(root.width()) + 2
                    or bottom > int(root.height()) + 2
                ):
                    warnings.append({
                        "kind": "painted-frame-outside-root",
                        "widget": type(frame).__name__,
                        "object_name": str(frame.objectName() or ""),
                        "geometry": [left, top, int(frame.width()), int(frame.height())],
                        "root_size": [int(root.width()), int(root.height())],
                    })
            except Exception:
                logger.debug(
                    "Anki Garden capture: painted-frame audit failed",
                    exc_info=True,
                )
        return warnings

    def _capture_requested_size(
        self,
        label: str,
        widget: QWidget,
        *,
        width: int,
        height: int,
        start_width: int,
        start_height: int,
        transition_path: str,
        close_callback: Callable[[], None] | None = None,
    ) -> None:
        """Exercise a real resize transition and capture only once it settles."""

        self._move_to_capture_display(widget)
        declared_width = int(width)
        declared_height = int(height)
        initial_width = int(start_width)
        initial_height = int(start_height)
        capture_screen = widget.screen()
        available = (
            capture_screen.availableGeometry()
            if capture_screen is not None else None
        )
        if available is not None:
            initial_width = min(initial_width, int(available.width()))
            initial_height = min(initial_height, int(available.height()))
        widget.resize(initial_width, initial_height)
        widget.show()
        widget.raise_()
        QApplication.processEvents()

        # A macOS top-level window's available geometry includes the native
        # title-bar footprint while QWidget.resize() addresses only the client
        # area.  Establish that footprint after the window is shown, then cap
        # the requested client size against both the screen and any deliberate
        # per-dialog maximum.  The first geometry reached is the normalized
        # request; the delayed capture still fails if it subsequently drifts.
        frame = widget.frameGeometry()
        frame_overhead_width = max(0, int(frame.width()) - int(widget.width()))
        frame_overhead_height = max(0, int(frame.height()) - int(widget.height()))
        screen_maximum_width = (
            max(1, int(available.width()) - frame_overhead_width)
            if available is not None else 16777215
        )
        screen_maximum_height = (
            max(1, int(available.height()) - frame_overhead_height)
            if available is not None else 16777215
        )
        widget_maximum_width = int(widget.maximumWidth())
        widget_maximum_height = int(widget.maximumHeight())
        target_width = max(
            int(widget.minimumWidth()),
            min(declared_width, screen_maximum_width, widget_maximum_width),
        )
        target_height = max(
            int(widget.minimumHeight()),
            min(declared_height, screen_maximum_height, widget_maximum_height),
        )
        widget.resize(target_width, target_height)
        QApplication.processEvents()
        normalized_width = int(widget.width())
        normalized_height = int(widget.height())
        screen_limited = (
            declared_width > screen_maximum_width
            or declared_height > screen_maximum_height
        )
        constraint_limited = (
            declared_width > widget_maximum_width
            or declared_height > widget_maximum_height
            or declared_width < int(widget.minimumWidth())
            or declared_height < int(widget.minimumHeight())
        )
        native_normalized = (
            normalized_width != target_width
            or normalized_height != target_height
        )
        normalization_reasons: list[str] = []
        if screen_limited:
            normalization_reasons.append("available-screen")
        if constraint_limited:
            normalization_reasons.append("widget-constraint")
        if native_normalized:
            normalization_reasons.append("native-frame-or-scale")
        self._active_geometry_request = {
            "label": label,
            "declared_client_size": [declared_width, declared_height],
            "requested_client_size": [normalized_width, normalized_height],
            "available_screen_size": (
                [int(available.width()), int(available.height())]
                if available is not None else None
            ),
            "screen_limited": screen_limited,
            "constraint_limited": constraint_limited,
            "native_normalized": native_normalized,
            "normalization_reason": ",".join(normalization_reasons),
            "frame_overhead": [frame_overhead_width, frame_overhead_height],
            "transition_path": str(transition_path),
        }
        self._capture_and_advance(
            label,
            widget,
            capture_delay_ms=360,
            close_callback=close_callback,
            close_ms=620 if close_callback is not None else None,
            next_ms=820,
        )

    @staticmethod
    def _find_text_layout_warnings(root: QWidget) -> list[dict[str, Any]]:
        """Report visible native text whose widget geometry cannot contain it.

        This supplements image review with a deterministic guard against the
        failure mode where Qt compresses a label inside a fixed-height card.
        Scroll-view content is safe: the check compares text with its own
        widget, not with the currently visible part of the viewport.
        """

        warnings: list[dict[str, Any]] = []
        candidates = [root, *root.findChildren(QWidget)]
        for candidate in candidates:
            if not isinstance(candidate, (QLabel, QAbstractButton)):
                continue
            try:
                if not candidate.isVisibleTo(root):
                    continue
                # QScrollArea intentionally clips off-screen content and makes
                # it reachable through the allowed scroll axis. Auditing the
                # candidate's own glyph box is sufficient there; walking to
                # the top-level root would report normal scrolled content as
                # a malformed window.
                inside_scroll = False
                ancestor = candidate.parentWidget()
                while ancestor is not None and ancestor is not root:
                    if isinstance(ancestor, QAbstractScrollArea):
                        inside_scroll = True
                        break
                    ancestor = ancestor.parentWidget()
                text = str(candidate.text() or "").strip()
                if not text or "<" in text:
                    continue
                metrics = candidate.fontMetrics()
                contents = candidate.contentsRect()
                available_width = max(1, int(contents.width()))
                # Qt style-sheet padding can shrink ``contentsRect()`` even
                # though the label paints and clips against its full widget
                # bounds.  Audit the actual paint boundary vertically, and use
                # tight glyph bounds so ascender/descender leading does not
                # turn compact chips and metric values into false positives.
                available_height = max(1, int(candidate.height()))
                lines = text.splitlines() or [text]
                required_height = 0
                for line in lines:
                    line_height = max(1, int(metrics.tightBoundingRect(line or " ").height()))
                    if isinstance(candidate, QLabel) and candidate.wordWrap():
                        advance = max(1, int(metrics.horizontalAdvance(line or " ")))
                        wrapped_lines = max(1, (advance + available_width - 1) // available_width)
                    else:
                        wrapped_lines = 1
                    required_height += line_height * wrapped_lines

                vertical_clip = required_height > available_height + 2
                horizontal_clip = False
                if isinstance(candidate, QLabel) and not candidate.wordWrap() and "\n" not in text:
                    horizontal_clip = metrics.horizontalAdvance(text) > available_width + 1
                elif isinstance(candidate, QAbstractButton) and len(text) > 2:
                    horizontal_clip = metrics.horizontalAdvance(text) > max(
                        1,
                        available_width - 12,
                    )
                # A label can contain its own glyphs but still be cut off by a
                # fixed-height parent. Walk native ancestors to catch that
                # failure. Content that is intentionally reachable through a
                # scroll bar is exempt only on the scrollable axis.
                ancestor_clip_horizontal = False
                ancestor_clip_vertical = False
                allow_scroll_horizontal = False
                allow_scroll_vertical = False
                scroll_ancestor = candidate.parentWidget()
                while scroll_ancestor is not None:
                    if isinstance(scroll_ancestor, QAbstractScrollArea):
                        allow_scroll_horizontal = allow_scroll_horizontal or (
                            scroll_ancestor.horizontalScrollBarPolicy()
                            != Qt.ScrollBarPolicy.ScrollBarAlwaysOff
                        )
                        allow_scroll_vertical = allow_scroll_vertical or (
                            scroll_ancestor.verticalScrollBarPolicy()
                            != Qt.ScrollBarPolicy.ScrollBarAlwaysOff
                        )
                    if scroll_ancestor is root:
                        break
                    scroll_ancestor = scroll_ancestor.parentWidget()
                ancestor = candidate.parentWidget()
                while ancestor is not None and not inside_scroll:
                    # A layout container is an implementation detail, not a
                    # paint boundary. Qt can legitimately let a child extend
                    # through that container while the enclosing styled frame
                    # owns the visible surface. Audit native paint boundaries
                    # and the capture root, which catches real card/frame
                    # clipping without treating layout negotiation as damage.
                    checks_paint_boundary = (
                        isinstance(ancestor, (QFrame, QAbstractButton, QAbstractScrollArea))
                        or ancestor is root
                    )
                    if not checks_paint_boundary:
                        ancestor = ancestor.parentWidget()
                        continue
                    position = candidate.mapTo(
                        ancestor,
                        candidate.rect().topLeft(),
                    )
                    left = int(position.x())
                    top = int(position.y())
                    right = left + int(candidate.width())
                    bottom = top + int(candidate.height())
                    if not allow_scroll_horizontal and (
                        left < -2 or right > int(ancestor.width()) + 2
                    ):
                        ancestor_clip_horizontal = True
                    if not allow_scroll_vertical and (
                        top < -2 or bottom > int(ancestor.height()) + 2
                    ):
                        ancestor_clip_vertical = True
                    if ancestor_clip_horizontal or ancestor_clip_vertical or ancestor is root:
                        break
                    ancestor = ancestor.parentWidget()
                horizontal_clip = horizontal_clip or ancestor_clip_horizontal
                vertical_clip = vertical_clip or ancestor_clip_vertical
                if not vertical_clip and not horizontal_clip:
                    continue
                warnings.append({
                    "widget": type(candidate).__name__,
                    "object_name": str(candidate.objectName() or ""),
                    "text": text[:120],
                    "width": int(candidate.width()),
                    "height": int(candidate.height()),
                    "required_height": int(required_height),
                    "horizontal_clip": horizontal_clip,
                    "vertical_clip": vertical_clip,
                    "ancestor_clip_horizontal": ancestor_clip_horizontal,
                    "ancestor_clip_vertical": ancestor_clip_vertical,
                })
            except Exception:
                logger.debug("Anki Garden capture: text geometry audit failed", exc_info=True)
        return warnings

    def _capture_and_advance(
        self,
        label: str,
        widget: Any | None = None,
        *,
        capture_delay_ms: int = 260,
        close_ms: int | None = None,
        close_callback: Callable[[], None] | None = None,
        next_ms: int = 900,
    ) -> None:
        if widget is mw:
            if not self._activate_current_process_window(widget):
                logger.debug(
                    "Anki Garden capture: foreground request is still settling"
                )
        QTimer.singleShot(
            max(20, int(capture_delay_ms)),
            lambda: self._capture_now(label, widget),
        )
        if close_callback is not None:
            if close_ms is None:
                close_ms = max(220, int(capture_delay_ms) + 180)
            QTimer.singleShot(max(60, int(close_ms)), close_callback)
        self._next_after(next_ms)

    def _close_widget(self, widget: Any | None) -> None:
        if widget is None:
            return
        try:
            done = getattr(widget, "done", None)
            if callable(done):
                # Native QDialogs and the macOS embedded DialogShell both
                # expose done(). It exits a nested exec() loop directly and
                # avoids first-run prompts reopening before capture advances.
                done(int(QDialog.DialogCode.Rejected))
            else:
                widget.close()
        except Exception:
            pass

    def _close_top_level_dialogs(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        from .ui.dashboard import DialogShell

        # On macOS Garden dialogs intentionally remain child widgets so that
        # opening one cannot move a full-screen Anki window to another Space.
        # allWidgets() therefore replaces a topLevelWidgets()-only cleanup.
        for widget in tuple(app.allWidgets()):
            if widget is mw or not widget.isVisible():
                continue
            if not isinstance(widget, (QDialog, DialogShell)):
                continue
            self._close_widget(widget)

    def _close_dashboard(self) -> None:
        dashboard = getattr(self.app, "dashboard", None)
        self._close_widget(dashboard)

    def _audit_nursery_action_above_footer(
        self,
        dialog: Any,
        scroll: Any,
        label: str,
        *,
        row: str,
        button_prefix: str = "",
    ) -> bool:
        """Verify one catalog action row is reachable inside the body viewport."""

        content = scroll.widget() if scroll is not None else None
        footer = getattr(dialog, "nursery_footer", None)
        viewport = scroll.viewport() if scroll is not None else None
        if content is None or footer is None or viewport is None:
            self._failures.append({
                "label": label,
                "reason": "Nursery body, viewport, or footer was unavailable for clearance audit",
            })
            return False
        candidates = [
            button
            for button in content.findChildren(QAbstractButton)
            if button.isVisible()
            and (not button_prefix or str(button.text()).startswith(button_prefix))
        ]
        if not candidates:
            self._failures.append({
                "label": label,
                "reason": f"No {button_prefix or 'catalog'} action was available for clearance audit",
            })
            return False

        positions = {
            button: int(button.mapTo(content, button.rect().topLeft()).y())
            for button in candidates
        }
        target_y = (
            min(positions.values()) if row == "first" else max(positions.values())
        )
        target_row = [
            button for button, position in positions.items()
            if abs(position - target_y) <= 4
        ]
        bar = scroll.verticalScrollBar()
        issues: list[str] = []
        if row == "last" and int(bar.value()) != int(bar.maximum()):
            issues.append(
                f"scroll value {bar.value()} did not reach last edge {bar.maximum()}"
            )
        footer_top = int(footer.mapTo(dialog, footer.rect().topLeft()).y())
        for button in target_row:
            viewport_top = int(button.mapTo(viewport, button.rect().topLeft()).y())
            viewport_bottom = viewport_top + int(button.height())
            dialog_top = int(button.mapTo(dialog, button.rect().topLeft()).y())
            dialog_bottom = dialog_top + int(button.height())
            if viewport_top < 0 or viewport_bottom > int(viewport.height()):
                issues.append(f"{button.text()!r} was not fully inside the scroll viewport")
            if dialog_bottom > footer_top:
                issues.append(f"{button.text()!r} extended beneath the Nursery footer")
        passed = not issues
        self._capture_annotations[label] = {
            "nursery_footer_clearance_audited": True,
            "catalog_row": row,
            "action_count": len(target_row),
            "passed": passed,
        }
        if issues:
            self._failures.append({
                "label": label,
                "reason": "; ".join(issues),
            })
        return passed

    def _select_plant(self, *, activate: bool = True) -> str:
        state = getattr(self.app.storage, "state", None)
        plants = list(getattr(state, "plants", []) or []) if state is not None else []
        if not plants:
            return ""
        active_id = getattr(state, "active_plant_id", "")
        if active_id:
            return str(active_id)
        for plant in plants:
            if getattr(plant, "plant_id", ""):
                first = str(plant.plant_id)
                if activate:
                    try:
                        self.app.engine.set_active_plant(first)
                    except Exception:
                        pass
                return first
        return ""

    def _switch_surface(self, state: str) -> None:
        if getattr(mw, "state", None) == state:
            return
        move_to_state = getattr(mw, "moveToState", None)
        if callable(move_to_state):
            try:
                move_to_state(state)
                return
            except Exception:
                logger.debug("Anki Garden capture: moveToState failed for %s", state, exc_info=True)
        for method_name in (
            f"on{state[0].upper() + state[1:]}",
            f"show{state[0].upper() + state[1:]}",
            f"show_{state}",
            state,
        ):
            method = getattr(mw, method_name, None)
            if callable(method):
                try:
                    method()
                except TypeError:
                    method(state)
                except Exception:
                    logger.debug("Anki Garden capture: surface switch failed for %s", method_name, exc_info=True)
                return
        set_state = getattr(mw, "setState", None)
        if callable(set_state):
            try:
                set_state(state)
                return
            except Exception:
                pass
        set_state_old = getattr(mw, "set_state", None)
        if callable(set_state_old):
            try:
                set_state_old(state)
            except Exception:
                pass

    def _find_settings_dialog(self) -> QWidget | None:
        dashboard = getattr(self.app, "dashboard", None)
        dialog = getattr(dashboard, "settings_dialog", None)
        if dialog is not None:
            return dialog
        app = QApplication.instance()
        if app is None:
            return None
        for widget in app.allWidgets():
            if (
                isinstance(widget, QWidget)
                and "setting" in widget.windowTitle().lower()
            ):
                return widget
        return None

    def _set_settings_tab(self, settings_dialog: QWidget | None, index: int) -> None:
        if settings_dialog is None:
            return
        for widget in settings_dialog.findChildren(QTabWidget):
            if widget.count() > index:
                widget.setCurrentIndex(index)
                return

    def _capture_metric(self, metric: str, label: str) -> None:
        dashboard = getattr(self.app, "dashboard", None)
        if dashboard is None:
            self._next_after(200)
            return
        dialog = getattr(dashboard, "progress_dialog", None)
        if dialog is None:
            self._failures.append({
                "label": label,
                "reason": "Garden metric dialog was unavailable",
            })
            self._next_after(200)
            return
        refresh = getattr(dialog, "refresh", None)
        if callable(refresh):
            refresh()
        navigation = getattr(dialog, "navigation", None)
        if navigation is None or metric not in getattr(navigation, "keys", []):
            self._failures.append({
                "label": label,
                "reason": f"Garden Progress page {metric!r} was unavailable",
            })
            self._next_after(200)
            return
        navigation.set_current(metric)
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        dialog.setModal(False)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

        def _dialog_ready() -> None:
            self._capture_and_advance(
                label,
                dialog,
                capture_delay_ms=260,
                close_callback=lambda: self._close_widget(dialog),
                close_ms=620,
                next_ms=1000,
            )
            if dialog is not None:
                QTimer.singleShot(650, lambda: self._close_widget(dialog))
            else:
                # keep moving if dialog creation failed
                QTimer.singleShot(0, self._close_dashboard)

        self._wait_for(
            lambda: bool(
                dialog.isVisible()
                and navigation.stack.currentIndex() == navigation.keys.index(metric)
            ),
            _dialog_ready,
            tries=50,
            failure_label=label,
            failure_reason=f"{metric} metric dialog did not become ready",
        )

    def _capture_starter_deck_browser(self) -> None:
        self._switch_surface("overview")

        def enter_fresh_deck_browser() -> None:
            self._switch_surface("deckBrowser")
            QTimer.singleShot(
                500,
                lambda: self._wait_for_home_surface(
                    "deckBrowser",
                    lambda: self._capture_and_advance(
                        "starter-deck-browser-home",
                        mw,
                        capture_delay_ms=650,
                        next_ms=1200,
                    ),
                ),
            )

        QTimer.singleShot(500, enter_fresh_deck_browser)

    def _capture_starter_overview(self) -> None:
        self._switch_surface("overview")
        QTimer.singleShot(
            350,
            lambda: self._wait_for_home_surface(
                "overview",
                lambda: self._capture_and_advance(
                    "starter-overview-home",
                    mw,
                    capture_delay_ms=650,
                    next_ms=1200,
                ),
            ),
        )

    def _capture_starter_garden(self) -> None:
        def dashboard_ready() -> None:
            dashboard = getattr(self.app, "dashboard", None)

            def onboarding_ready() -> None:
                self._capture_and_advance(
                    "starter-garden-onboarding",
                    dashboard,
                    capture_delay_ms=420,
                    next_ms=1000,
                )

            self._wait_for(
                lambda: bool(
                    dashboard is not None
                    and dashboard.isVisible()
                    and getattr(dashboard, "onboarding_panel", None)
                    and dashboard.onboarding_panel.isVisible()
                ),
                onboarding_ready,
                tries=80,
                failure_label="starter-garden-onboarding",
                failure_reason="First-run Garden guidance did not become visible",
            )

        self._with_dashboard(dashboard_ready)

    def _capture_starter_nursery(self) -> None:
        self._with_dashboard(self._capture_starter_nursery_after)

    def _capture_starter_action_above_footer(self) -> None:
        self._with_dashboard(
            lambda: self._capture_starter_nursery_after(
                label="starter-action-above-footer",
                audit_action=True,
            )
        )

    def _capture_starter_confirmation(self) -> None:
        from .ui.dashboard import StarterConfirmationDialog

        dashboard = getattr(self.app, "dashboard", None)
        ready_species = getattr(self.app.engine, "release_ready_species", None)
        species = ""
        if callable(ready_species):
            try:
                species = str(next(iter(ready_species()), ""))
            except Exception:
                species = ""
        if dashboard is None or not species:
            self._failures.append({
                "label": "starter-selection-confirmation",
                "reason": "Starter confirmation prerequisites were unavailable",
            })
            self._next_after(200)
            return
        dialog = StarterConfirmationDialog(dashboard, self.app.engine, species)
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        dialog.setModal(False)
        dialog.show()
        self._capture_and_advance(
            "starter-selection-confirmation",
            dialog,
            capture_delay_ms=360,
            close_callback=lambda: self._close_widget(dialog),
            close_ms=700,
            next_ms=1000,
        )

    def _capture_starter_nursery_after(
        self,
        *,
        label: str = "starter-nursery-plants",
        audit_action: bool = False,
    ) -> None:
        from .ui.dashboard import NurseryDialog

        dashboard = getattr(self.app, "dashboard", None)
        if dashboard is None:
            self._failures.append({
                "label": label,
                "reason": "Starter Nursery parent was unavailable",
            })
            self._next_after(250)
            return

        # The product route intentionally uses QDialog.exec(). Capture this
        # surface non-modally so teardown cannot become trapped in that nested
        # event loop while the first-run prompt is still eligible to reopen.
        dialog = NurseryDialog(dashboard, self.app.engine, self.app.storage)
        dashboard.nursery_dialog = dialog
        dialog.catalog_tabs.setCurrentIndex(0)
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        dialog.setModal(False)
        self._move_to_capture_display(dialog)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

        def capture_ready() -> None:
            if audit_action:
                self._audit_nursery_action_above_footer(
                    dialog,
                    dialog.scroll,
                    label,
                    row="first",
                    button_prefix="Choose",
                )
            self._capture_and_advance(
                label,
                dialog,
                capture_delay_ms=420,
                close_callback=lambda: self._close_widget(dialog),
                close_ms=780,
                next_ms=1200,
            )

        def ready() -> None:
            if audit_action:
                content = dialog.scroll.widget()
                actions = [
                    button
                    for button in content.findChildren(QAbstractButton)
                    if button.isVisible() and button.text().startswith("Choose")
                ] if content is not None else []
                if actions:
                    first_action = min(
                        actions,
                        key=lambda button: int(
                            button.mapTo(content, button.rect().topLeft()).y()
                        ),
                    )
                    dialog.scroll.ensureWidgetVisible(first_action, 0, 28)
                QTimer.singleShot(180, capture_ready)
                return
            capture_ready()

        QTimer.singleShot(
            0,
            lambda: self._wait_for(
                lambda: bool(
                    getattr(dashboard, "nursery_dialog", None)
                    is dialog
                    and dialog.isVisible()
                    and dialog.catalog_tabs.currentIndex() == 0
                    and bool(getattr(dialog, "_starter_mode", False))
                ),
                ready,
                tries=80,
                failure_label=label,
                failure_reason="Starter Nursery Plants tab did not become ready",
            ),
        )

    def _capture_deck_browser(self) -> None:
        # A disposable profile starts on Deck Browser before deterministic
        # Garden seeding. Force a real state transition so Anki replaces that
        # pre-seed DOM instead of letting its old successful root satisfy the
        # readiness predicate during the page fade.
        self._switch_surface("overview")

        def enter_fresh_deck_browser() -> None:
            self._switch_surface("deckBrowser")
            QTimer.singleShot(
                500,
                lambda: self._wait_for_home_surface(
                    "deckBrowser",
                    lambda: self._capture_and_advance(
                        "deck-browser-home",
                        mw,
                        capture_delay_ms=650,
                        next_ms=1200,
                    ),
                ),
            )

        QTimer.singleShot(500, enter_fresh_deck_browser)

    def _capture_overview(self) -> None:
        self._switch_surface("overview")
        QTimer.singleShot(
            350,
            lambda: self._wait_for_home_surface(
                "overview",
                lambda: self._capture_and_advance(
                    "overview-home",
                    mw,
                    capture_delay_ms=650,
                    next_ms=1200,
                ),
            ),
        )

    def _capture_addon_settings_menu(self) -> None:
        action = getattr(self.app, "_settings_action", None)
        if action is not None and hasattr(action, "trigger"):
            action.trigger()
        else:
            self.app.open_settings()

        def _ready() -> None:
            dialog = self._find_settings_dialog()
            self._capture_and_advance(
                "settings-menu-display",
                dialog,
                capture_delay_ms=400,
                close_callback=lambda: self._close_widget(dialog),
                close_ms=700,
                next_ms=1200,
            )
        self._wait_for(
            lambda: bool(
                self._find_settings_dialog() is not None
                and self._find_settings_dialog().isVisible()
            ),
            _ready,
            tries=80,
            failure_label="settings-menu-display",
            failure_reason="Settings dialog did not open from the Anki menu action",
        )

    def _capture_full_garden(self) -> None:
        self._with_dashboard(lambda: self._capture_and_advance(
            "full-garden",
            self.app.dashboard,
            capture_delay_ms=500,
            next_ms=900,
        ))

    def _capture_hover_outline(self) -> None:
        self._with_dashboard(self._capture_hover_outline_after)

    def _capture_hover_outline_after(self) -> None:
        plant_id = self._select_plant(activate=False)
        dashboard = getattr(self.app, "dashboard", None)
        scene = getattr(dashboard, "scene", None) if dashboard is not None else None
        if not plant_id or scene is None:
            self._failures.append({
                "label": "hover-outline",
                "reason": "Garden scene or representative plant was unavailable",
            })
            self._close_dashboard()
            self._next_after(250)
            return
        scene._interaction.dismiss()
        scene._interaction.hover(plant_id)
        scene._hover_opacity = {plant_id: 1.0}
        scene.update()
        self._capture_and_advance(
            "hover-outline",
            dashboard,
            capture_delay_ms=320,
            next_ms=850,
        )

    def _capture_selected_card(self) -> None:
        self._with_dashboard(self._capture_selected_card_after)

    def _capture_selected_card_after(self) -> None:
        from .ui.state_contracts import OnboardingState, onboarding_state_display

        plant_id = self._select_plant(activate=False)
        dashboard = getattr(self.app, "dashboard", None)
        if not plant_id or dashboard is None:
            self._close_dashboard()
            self._next_after(250)
            return
        config = getattr(self.app, "config", None)
        onboarding_version = (
            config.value("onboarding_version", 0)
            if config is not None and hasattr(config, "value") else 0
        )
        onboarding = onboarding_state_display(
            self.app.storage.state,
            onboarding_version,
        )
        if onboarding.state != OnboardingState.STARTER_PLANTED_NOT_NURTURED:
            self._failures.append({
                "label": "selected-plant-not-nurtured",
                "reason": (
                    "Starter capture was not in the persisted planted-before-Nurture state "
                    f"({onboarding.state.value})"
                ),
            })
        refresh = getattr(dashboard, "refresh_all", None)
        if callable(refresh):
            refresh()
        selector = getattr(dashboard, "_on_scene_selection", None)
        keep_open = getattr(getattr(dashboard, "scene", None), "keep_card_open", None)
        if callable(keep_open):
            keep_open(plant_id)
        if callable(selector):
            selector(plant_id)
        self._capture_and_advance(
            "selected-plant-not-nurtured",
            dashboard,
            capture_delay_ms=400,
            next_ms=900,
        )

    def _capture_nurture(self) -> None:
        self._with_dashboard(self._capture_nurture_after)

    def _capture_nurture_after(self) -> None:
        plant_id = self._select_plant(activate=False)
        dashboard = getattr(self.app, "dashboard", None)
        if not plant_id or dashboard is None:
            self._close_dashboard()
            self._next_after(250)
            return
        nurture = getattr(dashboard, "_nurture_plant", None)
        if callable(nurture):
            nurture(plant_id)
        state = self.app.storage.state
        plant = self.app.engine.plant_story(plant_id)
        first_nurture_committed = bool(
            plant is not None
            and any(
                str(getattr(memory, "kind", "") or "") == "first_nurture"
                or str(getattr(memory, "memory_id", "") or "") == "nurture:first"
                for memory in tuple(getattr(plant, "memories", ()) or ())
            )
        )
        if str(getattr(state, "active_plant_id", "") or "") != plant_id or not first_nurture_committed:
            self._failures.append({
                "label": "selected-plant-nurtured",
                "reason": "Nurture did not atomically persist the active plant and first-Nurture memory",
            })
        self._capture_and_advance(
            "selected-plant-nurtured",
            dashboard,
            capture_delay_ms=260,
            next_ms=850,
        )

    def _capture_fertilize(self) -> None:
        self._with_dashboard(
            lambda: self._capture_fertilize_after("fertilizer-unaffordable", "unaffordable")
        )

    def _capture_fertilize_affordable(self) -> None:
        self._with_dashboard(
            lambda: self._capture_fertilize_after("fertilizer-affordable", "affordable")
        )

    def _capture_fertilize_active(self) -> None:
        self._with_dashboard(
            lambda: self._capture_fertilize_after("fertilizer-active", "active")
        )

    def _capture_fertilize_after(self, label: str, state_variant: str) -> None:
        plant_id = self._select_plant()
        dashboard = getattr(self.app, "dashboard", None)
        if not plant_id or dashboard is None:
            self._close_dashboard()
            self._next_after(250)
            return
        state = self.app.storage.state
        plant = self.app.engine.plant_story(plant_id)
        if plant is not None and state_variant in {"unaffordable", "affordable", "active"}:
            plant.fertilizer = None
        state.currency_balance = 0 if state_variant == "unaffordable" else 500
        if state_variant == "active":
            purchase = getattr(self.app.engine, "purchase_fertilizer", None)
            if callable(purchase):
                purchase(plant_id, "basic")
        refresh = getattr(dashboard, "refresh_all", None)
        if callable(refresh):
            refresh()
        fertilize = getattr(dashboard, "_open_fertilizer_menu", None)
        if not callable(fertilize):
            self._close_dashboard()
            self._next_after(250)
            return
        def ready() -> None:
            dialog = getattr(dashboard, "fertilizer_dialog", None)
            self._capture_and_advance(
                label,
                dialog,
                capture_delay_ms=220,
                close_callback=lambda: self._close_widget(dialog),
                close_ms=620,
                next_ms=1000,
            )

        QTimer.singleShot(
            0,
            lambda: self._wait_for(
                lambda: bool(
                    getattr(dashboard, "fertilizer_dialog", None)
                    and dashboard.fertilizer_dialog.isVisible()
                ),
                ready,
                tries=80,
                failure_label=label,
                failure_reason="Fertilizer dialog did not become ready",
            ),
        )
        fertilize(plant_id)

    def _capture_move(self) -> None:
        self._with_dashboard(self._capture_move_after)

    def _capture_move_after(self) -> None:
        plant_id = self._select_plant()
        dashboard = getattr(self.app, "dashboard", None)
        if not plant_id or dashboard is None:
            self._close_dashboard()
            self._next_after(250)
            return
        begin_move = getattr(dashboard, "_begin_move", None)
        if callable(begin_move):
            begin_move(plant_id)
        cancel_move = getattr(dashboard, "_cancel_move", None)
        self._capture_and_advance(
            "move-mode",
            dashboard,
            capture_delay_ms=500,
            close_callback=lambda: (cancel_move() if callable(cancel_move) else self._close_dashboard()),
            close_ms=800,
            next_ms=1200,
        )

    def _capture_story(self) -> None:
        self._with_dashboard(self._capture_story_after)

    def _capture_story_after(self) -> None:
        from .ui.dashboard import PlantStoryDialog

        plant_id = self._select_plant()
        dashboard = getattr(self.app, "dashboard", None)
        if not plant_id or dashboard is None:
            self._close_dashboard()
            self._next_after(250)
            return

        # The product route intentionally uses QDialog.exec(). Capture the
        # identical dialog non-modally so teardown cannot remain trapped in its
        # nested event loop after the screenshot has already been written.
        dialog = PlantStoryDialog(dashboard, self.app.engine, plant_id)
        dashboard.story_dialog = dialog
        dialog.remember_invoker(dashboard.plant_card.story)
        dialog.chooseAnother.connect(dashboard._choose_another_plant)
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        dialog.setModal(False)
        self._move_to_capture_display(dialog)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

        def close_story() -> None:
            self._close_widget(dialog)
            if getattr(dashboard, "story_dialog", None) is dialog:
                dashboard.story_dialog = None

        def ready() -> None:
            self._capture_and_advance(
                "plant-story",
                dialog,
                capture_delay_ms=220,
                close_callback=close_story,
                close_ms=650,
                next_ms=1000,
            )

        QTimer.singleShot(
            0,
            lambda: self._wait_for(
                lambda: bool(
                    getattr(dashboard, "story_dialog", None)
                    and dashboard.story_dialog.isVisible()
                ),
                ready,
                tries=80,
                failure_label="plant-story",
                failure_reason="Plant Story dialog did not become ready",
            ),
        )

    def _nurtured_capture_plant_id(self, label: str) -> str:
        state = getattr(self.app.storage, "state", None)
        active_id = str(getattr(state, "active_plant_id", "") or "")
        plant = self.app.engine.plant_story(active_id) if active_id else None
        first_nurture_committed = bool(
            plant is not None
            and any(
                str(getattr(memory, "kind", "") or "") == "first_nurture"
                or str(getattr(memory, "memory_id", "") or "") == "nurture:first"
                for memory in tuple(getattr(plant, "memories", ()) or ())
            )
        )
        if not active_id or not first_nurture_committed:
            self._failures.append({
                "label": label,
                "reason": "Active Home capture was attempted before the real Nurture transaction completed",
            })
            return ""
        return active_id

    def _capture_active_deck_browser_after_nurture(self) -> None:
        label = "active-deck-browser-home-after-nurture"
        if not self._nurtured_capture_plant_id(label):
            self._next_after(200)
            return
        self._close_top_level_dialogs()
        self._close_dashboard()
        reset = getattr(mw, "reset", None)
        if callable(reset):
            reset()
        self._switch_surface("overview")

        def enter_deck_browser() -> None:
            self._switch_surface("deckBrowser")
            self._wait_for_home_surface(
                "deckBrowser",
                lambda: self._capture_and_advance(
                    label,
                    mw,
                    capture_delay_ms=650,
                    next_ms=1200,
                ),
            )

        QTimer.singleShot(500, enter_deck_browser)

    def _capture_active_overview_after_nurture(self) -> None:
        label = "active-overview-home-after-nurture"
        if not self._nurtured_capture_plant_id(label):
            self._next_after(200)
            return
        self._close_top_level_dialogs()
        self._close_dashboard()
        reset = getattr(mw, "reset", None)
        if callable(reset):
            reset()
        self._switch_surface("overview")
        QTimer.singleShot(
            350,
            lambda: self._wait_for_home_surface(
                "overview",
                lambda: self._capture_and_advance(
                    label,
                    mw,
                    capture_delay_ms=650,
                    next_ms=1200,
                ),
            ),
        )

    def _refresh_capture_dashboard(self) -> None:
        dashboard = getattr(self.app, "dashboard", None)
        refresh = getattr(dashboard, "refresh_all", None)
        if callable(refresh):
            refresh()

    def _capture_growth_zero(self) -> None:
        def ready() -> None:
            state = self.app.storage.state
            plant = self.app.engine.active_plant()
            if plant is not None:
                plant.growth_points = 0
            stats = state.daily_stats
            for field in (
                "growth_earned", "base_growth", "streak_bonus_growth",
                "fertilizer_growth", "booster_growth", "weather_growth",
                "scenery_growth", "charge_growth",
            ):
                setattr(stats, field, 0)
            self._refresh_capture_dashboard()
            self._capture_metric("growth", "growth-zero")

        self._with_dashboard(ready)

    def _capture_growth_nonzero(self) -> None:
        def ready() -> None:
            state = self.app.storage.state
            plant = self.app.engine.active_plant()
            if plant is not None:
                plant.growth_points = 1_250
            stats = state.daily_stats
            stats.growth_earned = 37
            stats.base_growth = 30
            stats.streak_bonus_growth = 3
            stats.fertilizer_growth = 4
            stats.booster_growth = 0
            stats.weather_growth = 0
            stats.scenery_growth = 0
            stats.charge_growth = 0
            self._refresh_capture_dashboard()
            self._capture_metric("growth", "growth-nonzero")

        self._with_dashboard(ready)

    def _capture_streak_new(self) -> None:
        def ready() -> None:
            state = self.app.storage.state
            state.streak_days = 0
            state.daily_stats.reviewed = 0
            self._refresh_capture_dashboard()
            self._capture_metric("streak", "streak-new")

        self._with_dashboard(ready)

    def _capture_streak_active(self) -> None:
        def ready() -> None:
            state = self.app.storage.state
            state.streak_days = 7
            state.daily_stats.reviewed = 12
            state.daily_stats.correct = 10
            state.daily_stats.wrong = 2
            state.last_active_day = str(state.daily_stats.day)
            streak_achievement = state.achievements.get("streak_7")
            if streak_achievement is not None:
                streak_achievement.unlocked = True
                streak_achievement.progress = 1.0
                streak_achievement.unlocked_at = str(state.daily_stats.day)
            self._refresh_capture_dashboard()
            self._capture_metric("streak", "streak-active")

        self._with_dashboard(ready)

    def _capture_coins_zero(self) -> None:
        def ready() -> None:
            state = self.app.storage.state
            state.currency_balance = 0
            state.currency_transactions.clear()
            self._refresh_capture_dashboard()
            self._capture_metric("currency", "coins-zero")

        self._with_dashboard(ready)

    def _capture_coins_activity(self) -> None:
        def ready() -> None:
            state = self.app.storage.state
            state.currency_balance = 0
            state.currency_transactions.clear()
            credit = getattr(self.app.engine, "_credit_currency", None)
            if callable(credit):
                credit("capture:stage", "Reached Sprout", 5)
                credit("capture:streak", "7-day Anki streak", 25)
            self._refresh_capture_dashboard()
            self._capture_metric("currency", "coins-activity")

        self._with_dashboard(ready)

    def _capture_progress_page(self, key: str, label: str) -> None:
        self._with_dashboard(
            lambda: self._capture_progress_page_after(key, label)
        )

    def _capture_collection_filter(self, selected: str, label: str) -> None:
        """Open Collection, then apply its filter after the dialog refresh."""
        def after() -> None:
            dashboard = getattr(self.app, "dashboard", None)
            dialog = getattr(dashboard, "progress_dialog", None)
            navigation = getattr(dialog, "navigation", None) if dialog is not None else None
            if dashboard is None or dialog is None or navigation is None:
                self._failures.append({
                    "label": label,
                    "reason": "Garden Progress Collection was unavailable",
                })
                self._next_after(250)
                return
            refresh = getattr(dialog, "refresh", None)
            if callable(refresh):
                refresh()
            navigation.set_current("collection")
            dashboard._set_collection_filter(selected)
            dialog.setWindowModality(Qt.WindowModality.NonModal)
            dialog.setModal(False)
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()

            def ready() -> None:
                self._capture_and_advance(
                    label,
                    dialog,
                    capture_delay_ms=420,
                    close_callback=lambda: self._close_widget(dialog),
                    close_ms=820,
                    next_ms=1160,
                )

            self._wait_for(
                lambda: bool(
                    dialog.isVisible()
                    and navigation.stack.currentIndex()
                    == navigation.keys.index("collection")
                    and dashboard._collection_filter == selected
                ),
                ready,
                tries=80,
                failure_label=label,
                failure_reason=f"Collection filter {selected!r} did not become ready",
            )

        self._with_dashboard(after)

    def _capture_progress_page_after(self, key: str, label: str) -> None:
        dashboard = getattr(self.app, "dashboard", None)
        if dashboard is None:
            self._next_after(250)
            return
        dialog = getattr(dashboard, "progress_dialog", None)
        navigation = getattr(dialog, "navigation", None) if dialog is not None else None
        if dialog is None or navigation is None or key not in getattr(navigation, "keys", []):
            self._failures.append({
                "label": label,
                "reason": "Garden Progress dialog or requested page was unavailable",
            })
            self._next_after(250)
            return
        refresh = getattr(dialog, "refresh", None)
        if callable(refresh):
            refresh()
        navigation.set_current(key)
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        dialog.setModal(False)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

        def ready() -> None:
            self._capture_and_advance(
                label,
                dialog,
                capture_delay_ms=360,
                close_callback=lambda: self._close_widget(dialog),
                close_ms=760,
                next_ms=1100,
            )

        self._wait_for(
            lambda: bool(
                dialog.isVisible()
                and navigation.stack.currentIndex() == navigation.keys.index(key)
            ),
            ready,
            tries=80,
            failure_label=label,
            failure_reason=f"Garden Progress page {key!r} did not become ready",
        )

    def _capture_progress_today(self) -> None:
        self._capture_progress_page("overview", "progress-overview")

    def _capture_progress_achievements(self) -> None:
        self._capture_progress_page("achievements", "progress-achievements")

    def _capture_progress_collection(self) -> None:
        self._capture_progress_page("collection", "progress-collection")

    def _capture_species_overview(self) -> None:
        def dashboard_ready() -> None:
            dashboard = getattr(self.app, "dashboard", None)
            instances = list(getattr(self.app.storage.state, "plants", ()) or ())
            species = str(getattr(instances[0], "species", "") or "") if instances else ""
            builder = getattr(dashboard, "_build_species_overview_dialog", None)
            dialog = builder(species) if callable(builder) and species else None
            if dialog is None:
                self._failures.append({
                    "label": "collection-species-overview",
                    "reason": "Species overview prerequisites were unavailable",
                })
                self._next_after(200)
                return
            dialog.setWindowModality(Qt.WindowModality.NonModal)
            dialog.setModal(False)
            dialog.show()
            self._capture_and_advance(
                "collection-species-overview",
                dialog,
                capture_delay_ms=360,
                close_callback=lambda: self._close_widget(dialog),
                close_ms=720,
                next_ms=1050,
            )

        self._with_dashboard(dashboard_ready)

    def _capture_customize_garden(self) -> None:
        self._with_dashboard(self._capture_customize_garden_after)

    def _capture_customize_garden_after(self) -> None:
        dashboard = getattr(self.app, "dashboard", None)
        opener = getattr(dashboard, "_open_customize", None)
        if dashboard is None or not callable(opener):
            self._failures.append({
                "label": "customize-garden",
                "reason": "Customize Garden opener was unavailable",
            })
            self._next_after(250)
            return
        opener()
        dialog = getattr(dashboard, "customize_dialog", None)
        self._wait_for(
            lambda: bool(dialog is not None and dialog.isVisible()),
            lambda: self._capture_and_advance(
                "customize-garden",
                dialog,
                capture_delay_ms=420,
                close_callback=lambda: self._close_widget(dialog),
                close_ms=780,
                next_ms=1200,
            ),
            tries=80,
            failure_label="customize-garden",
            failure_reason="Customize Garden did not become ready",
        )

    def _capture_customize_effects_on(self) -> None:
        self._capture_customize_effects("customize-effects-on", True)

    def _capture_customize_effects_off(self) -> None:
        self._capture_customize_effects("customize-effects-off", False)

    def _capture_customize_effects(self, label: str, enabled: bool) -> None:
        self._with_dashboard(
            lambda: self._capture_customize_effects_after(label, enabled)
        )

    def _capture_customize_effects_after(self, label: str, enabled: bool) -> None:
        dashboard = getattr(self.app, "dashboard", None)
        opener = getattr(dashboard, "_open_customize", None)
        if dashboard is None or not callable(opener):
            self._failures.append({
                "label": label,
                "reason": "Customize Garden opener was unavailable",
            })
            self._next_after(250)
            return
        opener()
        dialog = getattr(dashboard, "customize_dialog", None)

        def ready() -> None:
            dialog.option_tabs.setCurrentIndex(2)
            dialog.show_weather.setChecked(enabled)
            dialog.show_scenery.setChecked(enabled)

            def state_ready() -> bool:
                return bool(
                    dialog.isVisible()
                    and dialog.option_tabs.currentIndex() == 2
                    and dialog.show_weather.isChecked() is enabled
                    and dialog.show_scenery.isChecked() is enabled
                )

            self._wait_for(
                state_ready,
                lambda: self._capture_and_advance(
                    label,
                    dialog,
                    capture_delay_ms=420,
                    close_callback=lambda: self._close_widget(dialog),
                    close_ms=780,
                    next_ms=1200,
                ),
                tries=80,
                failure_label=label,
                failure_reason=f"Customize Effects {label!r} did not become ready",
            )

        self._wait_for(
            lambda: bool(dialog is not None and dialog.isVisible()),
            ready,
            tries=80,
            failure_label=label,
            failure_reason="Customize Garden did not become ready",
        )

    def _capture_nursery_tab(self, index: int, label: str) -> None:
        self._with_dashboard(
            lambda: self._capture_nursery_tab_after(index, label)
        )

    def _capture_nursery_tab_after(self, index: int, label: str) -> None:
        dashboard = getattr(self.app, "dashboard", None)
        open_nursery = getattr(dashboard, "_open_nursery", None)
        if dashboard is None or not callable(open_nursery):
            self._failures.append({
                "label": label,
                "reason": "Nursery opener was unavailable",
            })
            self._next_after(250)
            return

        def ready() -> None:
            dialog = getattr(dashboard, "nursery_dialog", None)
            self._capture_and_advance(
                label,
                dialog,
                capture_delay_ms=420,
                close_callback=lambda: self._close_widget(dialog),
                close_ms=780,
                next_ms=1200,
            )

        QTimer.singleShot(
            0,
            lambda: self._wait_for(
                lambda: bool(
                    getattr(dashboard, "nursery_dialog", None)
                    and dashboard.nursery_dialog.isVisible()
                    and dashboard.nursery_dialog.catalog_tabs.count() > index
                    and dashboard.nursery_dialog.catalog_tabs.currentIndex() == index
                ),
                ready,
                tries=80,
                failure_label=label,
                failure_reason=f"Nursery tab {index + 1} did not become ready",
            ),
        )
        open_nursery(index)

    def _capture_nursery_plants(self) -> None:
        self._capture_nursery_tab(0, "nursery-plants")

    def _capture_nursery_fertilizer_booster(self) -> None:
        self._capture_nursery_tab(1, "nursery-fertilizer-booster")

    def _capture_nursery_garden_spaces(self) -> None:
        self._capture_nursery_tab(2, "nursery-garden-spaces")

    def _capture_nursery_weather_scenery(self) -> None:
        self._capture_nursery_tab(3, "nursery-weather-scenery")

    def _capture_settings_display(self) -> None:
        self._with_dashboard(self._capture_settings_display_after)

    def _capture_settings_display_after(self) -> None:
        dashboard = getattr(self.app, "dashboard", None)
        if dashboard is None:
            self._next_after(250)
            return
        open_settings = getattr(dashboard, "_open_settings", None)
        if callable(open_settings):
            open_settings()
        self._wait_for(
            lambda: bool(
                self._find_settings_dialog() is not None
                and self._find_settings_dialog().isVisible()
            ),
            self._capture_settings_display_ready,
            tries=80,
            failure_label="settings-display",
            failure_reason="Settings Display tab did not become ready",
        )

    def _capture_settings_display_ready(self) -> None:
        settings_dialog = self._find_settings_dialog()
        if settings_dialog is None:
            self._close_dashboard()
            self._next_after(300)
            return
        self._set_settings_tab(settings_dialog, 0)
        self._capture_and_advance(
            "settings-display",
            settings_dialog,
            capture_delay_ms=450,
            close_callback=lambda: self._close_widget(settings_dialog),
            close_ms=900,
            next_ms=1400,
        )

    def _capture_settings_display_advanced(self) -> None:
        self._with_dashboard(self._capture_settings_display_advanced_after)

    def _capture_settings_display_advanced_after(self) -> None:
        dashboard = getattr(self.app, "dashboard", None)
        if dashboard is None:
            self._next_after(250)
            return
        open_settings = getattr(dashboard, "_open_settings", None)
        if callable(open_settings):
            open_settings()
        self._wait_for(
            lambda: bool(
                self._find_settings_dialog() is not None
                and self._find_settings_dialog().isVisible()
            ),
            self._capture_settings_display_advanced_ready,
            tries=80,
            failure_label="settings-display-advanced-open",
            failure_reason="Settings Display Advanced state did not become ready",
        )

    def _capture_settings_display_advanced_ready(self) -> None:
        settings_dialog = self._find_settings_dialog()
        if settings_dialog is None:
            self._close_dashboard()
            self._next_after(300)
            return
        self._set_settings_tab(settings_dialog, 0)
        settings_dialog.behavior.advanced_toggle.setChecked(True)
        self._wait_for(
            lambda: bool(
                settings_dialog.isVisible()
                and settings_dialog.behavior.advanced_panel.isVisible()
                and settings_dialog.behavior.advanced_toggle.isChecked()
            ),
            lambda: self._capture_and_advance(
                "settings-display-advanced-open",
                settings_dialog,
                capture_delay_ms=500,
                close_callback=lambda: self._close_widget(settings_dialog),
                close_ms=900,
                next_ms=1400,
            ),
            tries=80,
            failure_label="settings-display-advanced-open",
            failure_reason="Settings Display Advanced panel did not expand",
        )

    def _capture_settings_troubleshooting(self) -> None:
        self._with_dashboard(self._capture_settings_troubleshooting_after)

    def _capture_settings_troubleshooting_after(self) -> None:
        dashboard = getattr(self.app, "dashboard", None)
        if dashboard is None:
            self._next_after(250)
            return
        open_settings = getattr(dashboard, "_open_settings", None)
        if callable(open_settings):
            open_settings()
        self._wait_for(
            lambda: bool(
                self._find_settings_dialog() is not None
                and self._find_settings_dialog().isVisible()
            ),
            self._capture_settings_troubleshooting_ready,
            tries=80,
            failure_label="diagnostics-clean",
            failure_reason="Settings Troubleshooting tab did not become ready",
        )

    def _capture_settings_troubleshooting_ready(self) -> None:
        settings_dialog = self._find_settings_dialog()
        if settings_dialog is None:
            self._close_dashboard()
            self._next_after(300)
            return
        self._set_settings_tab(settings_dialog, 1)
        self._capture_and_advance(
            "diagnostics-clean",
            settings_dialog,
            capture_delay_ms=500,
            close_callback=lambda: self._close_widget(settings_dialog),
            close_ms=900,
            next_ms=1400,
        )

    def _capture_settings_warning(self) -> None:
        self._with_dashboard(self._capture_settings_warning_after)

    def _capture_settings_warning_after(self) -> None:
        from .display_telemetry import DISPLAY_TELEMETRY

        DISPLAY_TELEMETRY.record_missing_or_invalid_field(
            route="capture",
            field="preview_artwork",
            reason="Intentional screenshot-regression warning state",
            required=True,
        )
        dashboard = getattr(self.app, "dashboard", None)
        open_settings = getattr(dashboard, "_open_settings", None)
        if callable(open_settings):
            open_settings()
        self._wait_for(
            lambda: bool(
                self._find_settings_dialog() is not None
                and self._find_settings_dialog().isVisible()
            ),
            self._capture_settings_warning_ready,
            tries=80,
            failure_label="diagnostics-warning",
            failure_reason="Diagnostics warning state did not become ready",
        )

    def _capture_settings_warning_ready(self) -> None:
        settings_dialog = self._find_settings_dialog()
        if settings_dialog is None:
            self._next_after(300)
            return
        self._set_settings_tab(settings_dialog, 1)
        refresh = getattr(settings_dialog, "_refresh_debug_report", None)
        if callable(refresh):
            refresh()
        self._capture_and_advance(
            "diagnostics-warning",
            settings_dialog,
            capture_delay_ms=500,
            close_callback=lambda: self._close_widget(settings_dialog),
            close_ms=900,
            next_ms=1400,
        )

    def _capture_dashboard_stress(
        self,
        label: str,
        mutate: Callable[[], None] | None = None,
        *,
        delay_ms: int = 480,
    ) -> None:
        def ready() -> None:
            if mutate is not None:
                mutate()
            self._refresh_capture_dashboard()
            self._capture_and_advance(
                label,
                self.app.dashboard,
                capture_delay_ms=delay_ms,
                next_ms=980,
            )

        self._with_dashboard(ready)

    def _capture_long_garden_name(self) -> None:
        self._capture_dashboard_stress(
            "long-garden-name",
            lambda: setattr(
                self.app.storage.state,
                "garden_name",
                "The Moonlit Conservatory at Willow Ridge"[:40],
            ),
        )

    def _capture_long_plant_name(self) -> None:
        def mutate() -> None:
            plant = self.app.engine.active_plant() or self.app.storage.state.plants[0]
            plant.name = "Bonsai of the Everlasting Twilight Grove"[:40]
            plant.name_customized = True

        self._capture_dashboard_stress("long-plant-name", mutate)

    def _capture_four_digit_coin_balance(self) -> None:
        self._capture_dashboard_stress(
            "four-digit-coin-balance",
            lambda: setattr(self.app.storage.state, "currency_balance", 9_999),
        )

    def _capture_growth_near_stage_completion(self) -> None:
        from .models.state import GROWTH_THRESHOLDS

        def mutate() -> None:
            plant = self.app.engine.active_plant() or self.app.storage.state.plants[0]
            plant.growth_points = GROWTH_THRESHOLDS[-1] - 25
            self.app.storage.state.active_plant_id = plant.plant_id
            dashboard = self.app.dashboard
            dashboard.scene.keep_card_open(plant.plant_id)
            dashboard._on_scene_selection(plant.plant_id)

        self._capture_dashboard_stress(
            "growth-near-stage-completion",
            mutate,
            delay_ms=560,
        )

    def _ensure_development_stress_state(self) -> bool:
        if bool(getattr(self, "_development_stress_ready", False)):
            return True
        from .models.state import GROWTH_THRESHOLDS, MAX_GARDEN_SLOTS

        ok, message = self.app.engine.development_populate()
        if not ok:
            self._failures.append({
                "label": "development-stress-state",
                "reason": str(message),
            })
            return False
        plants = list(self.app.storage.state.plants)
        if len(plants) < MAX_GARDEN_SLOTS:
            self._failures.append({
                "label": "development-stress-state",
                "reason": "Development population did not create six plants",
            })
            return False
        for index, plant in enumerate(plants):
            plant.slot_index = index if index < MAX_GARDEN_SLOTS else None
            if index < MAX_GARDEN_SLOTS:
                plant.growth_points = GROWTH_THRESHOLDS[index]
        state = self.app.storage.state
        state.unlocked_slots = MAX_GARDEN_SLOTS
        state.currency_balance = 9_999
        state.active_plant_id = plants[0].plant_id
        self._development_stress_ready = True
        self._refresh_capture_dashboard()
        return True

    def _capture_all_six_beds(self) -> None:
        def mutate() -> None:
            self._ensure_development_stress_state()
            self.app.dashboard.scene.dismiss_selection()

        self._capture_dashboard_stress("all-six-beds-occupied", mutate, delay_ms=620)

    def _capture_all_six_stages(self) -> None:
        self._capture_dashboard_stress(
            "plant-at-every-stage",
            self._ensure_development_stress_state,
            delay_ms=620,
        )

    def _capture_fully_grown_without_fertilize(self) -> None:
        def mutate() -> None:
            if not self._ensure_development_stress_state():
                return
            fully_grown = next(
                (
                    plant for plant in self.app.storage.state.plants
                    if bool(getattr(plant, "fully_grown", False))
                ),
                None,
            )
            dashboard = self.app.dashboard
            if fully_grown is None:
                self._failures.append({
                    "label": "fully-grown-plant-without-fertilize",
                    "reason": "No fully grown plant was available",
                })
                return
            dashboard.scene.keep_card_open(fully_grown.plant_id)
            dashboard._on_scene_selection(fully_grown.plant_id)
            fertilize_visible = bool(dashboard.plant_card.fertilize.isVisible())
            choose_visible = bool(dashboard.plant_card.choose_another.isVisible())
            passed = not fertilize_visible and choose_visible
            self._capture_annotations["fully-grown-plant-without-fertilize"] = {
                "fertilize_visible": fertilize_visible,
                "choose_another_visible": choose_visible,
                "passed": passed,
            }
            if not passed:
                self._failures.append({
                    "label": "fully-grown-plant-without-fertilize",
                    "reason": "Fully grown plant still exposed Fertilize or hid Choose another plant",
                })

        self._capture_dashboard_stress(
            "fully-grown-plant-without-fertilize",
            mutate,
            delay_ms=560,
        )

    def _capture_popover_slot(self, slot: int) -> None:
        label = f"popover-plot-{slot + 1}"

        def mutate() -> None:
            if not self._ensure_development_stress_state():
                return
            plant = next(
                row for row in self.app.storage.state.plants
                if row.slot_index == slot
            )
            dashboard = self.app.dashboard
            dashboard.scene.keep_card_open(plant.plant_id)
            dashboard._on_scene_selection(plant.plant_id)
            if not bool(dashboard.plant_card.isVisible()):
                self._failures.append({
                    "label": label,
                    "reason": "Selected plant details were not visible for this plot",
                })

        self._capture_dashboard_stress(label, mutate, delay_ms=520)

    def _capture_move_mixed_destinations(self) -> None:
        def ready() -> None:
            if not self._ensure_development_stress_state():
                self._next_after(200)
                return
            plants = list(self.app.storage.state.plants)
            for plant in plants[:4]:
                plant.slot_index = plants.index(plant)
            for plant in plants[4:]:
                plant.slot_index = None
            active = plants[0]
            self.app.storage.state.active_plant_id = active.plant_id
            dashboard = self.app.dashboard
            dashboard.refresh_all()
            dashboard._begin_move(active.plant_id)
            self._capture_and_advance(
                "move-occupied-empty-destinations",
                dashboard,
                capture_delay_ms=560,
                close_callback=dashboard._cancel_move,
                close_ms=820,
                next_ms=1150,
            )

        self._with_dashboard(ready)

    def _prepare_expiring_fertilizer(self) -> str:
        if not self._ensure_development_stress_state():
            return ""
        plant = self.app.storage.state.plants[0]
        plant.slot_index = 0
        self.app.storage.state.active_plant_id = plant.plant_id
        current = getattr(plant, "fertilizer", None)
        if current is None or not current.active(time.time()) or current.tier != "basic":
            self.app.engine.purchase_fertilizer(
                plant.plant_id,
                "basic",
                replace_active=bool(current and current.active(time.time())),
            )
            current = plant.fertilizer
        if current is not None:
            current.expires_at = time.time() + 45
        self._refresh_capture_dashboard()
        return plant.plant_id

    def _capture_fertilizer_expiring(self) -> None:
        def ready() -> None:
            plant_id = self._prepare_expiring_fertilizer()
            dashboard = self.app.dashboard
            if not plant_id:
                self._next_after(200)
                return

            def dialog_ready() -> None:
                dialog = getattr(dashboard, "fertilizer_dialog", None)
                self._capture_and_advance(
                    "fertilizer-expiring-under-minute",
                    dialog,
                    capture_delay_ms=420,
                    close_callback=lambda: self._close_widget(dialog),
                    close_ms=760,
                    next_ms=1100,
                )

            QTimer.singleShot(
                0,
                lambda: self._wait_for(
                    lambda: bool(
                        getattr(dashboard, "fertilizer_dialog", None)
                        and dashboard.fertilizer_dialog.isVisible()
                    ),
                    dialog_ready,
                    failure_label="fertilizer-expiring-under-minute",
                    failure_reason="Expiring Fertilizer dialog did not become ready",
                ),
            )
            dashboard._open_fertilizer_menu(plant_id)

        self._with_dashboard(ready)

    def _visible_fertilizer_replacement_dialog(self) -> QWidget | None:
        from .ui.dashboard import FertilizerReplacementDialog

        app = QApplication.instance()
        if app is None:
            return None
        return next(
            (
                widget for widget in app.allWidgets()
                if isinstance(widget, FertilizerReplacementDialog)
                and widget.isVisible()
            ),
            None,
        )

    def _capture_fertilizer_replacement_confirmation(self) -> None:
        def ready() -> None:
            plant_id = self._prepare_expiring_fertilizer()
            dashboard = self.app.dashboard
            if not plant_id:
                self._next_after(200)
                return

            def fertilizer_ready() -> None:
                dialog = getattr(dashboard, "fertilizer_dialog", None)
                replace = next(
                    (
                        button for button in dialog.findChildren(QAbstractButton)
                        if button.text() == "Replace" and button.isEnabled()
                    ),
                    None,
                )
                if replace is None:
                    self._failures.append({
                        "label": "fertilizer-replacement-confirmation",
                        "reason": "No enabled replacement action was available",
                    })
                    self._close_widget(dialog)
                    self._next_after(200)
                    return

                def confirmation_ready() -> None:
                    replacement_dialog = self._visible_fertilizer_replacement_dialog()

                    def close_confirmation() -> None:
                        self._close_widget(replacement_dialog)
                        self._close_widget(dialog)

                    self._capture_and_advance(
                        "fertilizer-replacement-confirmation",
                        replacement_dialog,
                        capture_delay_ms=320,
                        close_callback=close_confirmation,
                        close_ms=700,
                        next_ms=1100,
                    )

                self._wait_for(
                    lambda: self._visible_fertilizer_replacement_dialog() is not None,
                    confirmation_ready,
                    tries=80,
                    failure_label="fertilizer-replacement-confirmation",
                    failure_reason="Replacement confirmation did not become visible",
                )
                QTimer.singleShot(80, replace.click)

            QTimer.singleShot(
                0,
                lambda: self._wait_for(
                    lambda: bool(
                        getattr(dashboard, "fertilizer_dialog", None)
                        and dashboard.fertilizer_dialog.isVisible()
                    ),
                    fertilizer_ready,
                    failure_label="fertilizer-replacement-confirmation",
                    failure_reason="Fertilizer dialog did not become ready",
                ),
            )
            dashboard._open_fertilizer_menu(plant_id)

        self._with_dashboard(ready)

    def _set_nurtured_capture_slot(self, slot: int, label: str) -> bool:
        """Commit a valid nurtured plant in one of the six disposable plots."""

        if not self._ensure_development_stress_state():
            return False
        from .models.state import GROWTH_THRESHOLDS

        plants = list(self.app.storage.state.plants)
        # Earlier release faces deliberately exercise an occupied/empty move
        # matrix. Re-seat the canonical first six before each marker face so
        # every plot remains independently capturable regardless of that prior
        # transient mutation.
        for index, item in enumerate(plants):
            item.slot_index = index if index < 6 else None
        plant = plants[slot] if 0 <= int(slot) < min(6, len(plants)) else None
        if plant is None:
            self._failures.append({
                "label": label,
                "reason": f"Plot {slot + 1} did not contain a plant",
            })
            return False
        # A fully grown plant cannot be nurtured by the product contract. The
        # disposable visual fixture keeps the same species and plot while
        # returning only that representative to the last unfinished stage.
        if bool(getattr(plant, "fully_grown", False)):
            plant.growth_points = GROWTH_THRESHOLDS[-2]
        ok, message = self.app.engine.set_active_plant(plant.plant_id)
        if not ok:
            self._failures.append({"label": label, "reason": str(message)})
            return False
        coordinator = getattr(self.app, "state_events", None)
        notify = getattr(coordinator, "notify", None)
        if callable(notify):
            notify(f"Capture watering can in plot {slot + 1}")
        self._refresh_capture_dashboard()
        return True

    def _capture_watering_can_garden_plot(self, slot: int) -> None:
        label = f"watering-can-garden-plot-{slot + 1}"

        def ready() -> None:
            if not self._set_nurtured_capture_slot(slot, label):
                self._next_after(200)
                return
            dashboard = self.app.dashboard
            dashboard.scene.dismiss_selection()
            dashboard.refresh_all()
            self._capture_and_advance(
                label,
                dashboard,
                capture_delay_ms=620,
                next_ms=1050,
            )

        self._with_dashboard(ready)

    def _capture_watering_can_home_plot(self, slot: int, surface: str) -> None:
        surface_slug = "deck-browser" if surface == "deckBrowser" else "overview"
        label = f"watering-can-{surface_slug}-plot-{slot + 1}"
        if surface not in {"deckBrowser", "overview"}:
            self._failures.append({
                "label": label,
                "reason": f"Unsupported Anki Home surface {surface}",
            })
            self._next_after(200)
            return
        if not self._set_nurtured_capture_slot(slot, label):
            self._next_after(200)
            return
        self._close_top_level_dialogs()
        self._close_dashboard()
        reset = getattr(mw, "reset", None)
        if callable(reset):
            reset()
        opposite = "overview" if surface == "deckBrowser" else "deckBrowser"
        self._switch_surface(opposite)

        def enter_surface() -> None:
            self._switch_surface(surface)
            self._wait_for_home_surface(
                surface,
                lambda: self._capture_and_advance(
                    label,
                    mw,
                    capture_delay_ms=650,
                    next_ms=1200,
                ),
            )

        QTimer.singleShot(500, enter_surface)

    def _capture_collection_several(self) -> None:
        self._ensure_development_stress_state()
        self._capture_collection_filter("all", "collection-several-discovered")

    def _capture_collection_no_matches(self) -> None:
        self._ensure_development_stress_state()
        self._capture_collection_filter("locked", "collection-no-filter-matches")

    def _capture_achievement_completed(self) -> None:
        if not self._ensure_development_stress_state():
            self._next_after(200)
            return
        state = self.app.storage.state
        stats = state.daily_stats
        # Keep every completed card coherent even if a renderer still consults
        # today's counters. The product projection treats completion thresholds
        # as immutable, but a release fixture should never depend on stale,
        # contradictory values to demonstrate that behavior.
        stats.reviewed = 100
        stats.correct = 100
        stats.wrong = 0
        stats.new_count = 0
        stats.learning_count = 0
        stats.review_count = 100
        stats.completed_due_cards = True
        state.total_reviews = max(1_000, int(getattr(state, "total_reviews", 0) or 0))
        state.streak_days = max(30, int(getattr(state, "streak_days", 0) or 0))
        state.last_active_day = str(stats.day)
        state.claimed_streak_rewards = sorted(
            set(getattr(state, "claimed_streak_rewards", []) or []) | {7, 14, 30}
        )
        self._refresh_capture_dashboard()
        self._capture_progress_page("achievements", "achievement-completed")

    def _capture_clear_recall_conditions(self) -> None:
        from .ui.state_contracts import achievement_progress_display

        if not self._ensure_development_stress_state():
            self._next_after(200)
            return
        state = self.app.storage.state
        stats = state.daily_stats
        stats.reviewed = 12
        stats.correct = 10
        stats.wrong = 2
        achievement = state.achievements.get("retention_90")
        if achievement is None:
            self._failures.append({
                "label": "clear-recall-separate-conditions",
                "reason": "Clear Recall achievement was unavailable",
            })
            self._next_after(200)
            return
        achievement.unlocked = False
        achievement.unlocked_at = None
        achievement.progress = 0.0
        display = achievement_progress_display(achievement, state)
        condition_rows = tuple(
            (condition.label, condition.value_text)
            for condition in display.conditions
        )
        expected_rows = (
            ("Accuracy", "83% / 90%"),
            ("Anki card answers", "12 / 20"),
        )
        if condition_rows != expected_rows:
            self._failures.append({
                "label": "clear-recall-separate-conditions",
                "reason": f"Clear Recall conditions were not separate and coherent: {condition_rows!r}",
            })
        self._capture_annotations["clear-recall-separate-conditions"] = {
            "condition_rows": [list(row) for row in condition_rows],
            "passed": condition_rows == expected_rows,
        }
        self._refresh_capture_dashboard()
        self._capture_progress_page(
            "achievements",
            "clear-recall-separate-conditions",
        )

    def _set_streak_capture_state(
        self,
        *,
        days: int,
        reviewed: int,
        last_active_offset: int,
        claimed: list[int] | None = None,
    ) -> None:
        state = self.app.storage.state
        try:
            current_day = date.fromisoformat(str(state.daily_stats.day)[:10])
        except (TypeError, ValueError):
            current_day = date.today()
            state.daily_stats.day = current_day.isoformat()
        state.streak_days = days
        state.daily_stats.reviewed = reviewed
        state.last_active_day = (current_day + timedelta(days=last_active_offset)).isoformat()
        if claimed is not None:
            state.claimed_streak_rewards = list(claimed)
        self._refresh_capture_dashboard()

    def _capture_streak_at_risk(self) -> None:
        self._set_streak_capture_state(days=7, reviewed=0, last_active_offset=-1)
        self._capture_metric("streak", "streak-at-risk")

    def _capture_streak_missed_day(self) -> None:
        from .ui.state_contracts import StreakPresentationState, streak_presentation

        self._set_streak_capture_state(days=3, reviewed=0, last_active_offset=-2)
        state = self.app.storage.state
        presentation = streak_presentation(
            state.streak_days,
            state.last_active_day,
            state.daily_stats.reviewed,
            today=date.fromisoformat(str(state.daily_stats.day)[:10]),
        )
        if not (
            presentation.state == StreakPresentationState.ENDED
            and presentation.current_days == 0
            and presentation.previous_days == 3
        ):
            self._failures.append({
                "label": "streak-missed-day",
                "reason": "Missed-day fixture did not project an ended 0-day streak with its previous context",
            })
        self._capture_metric("streak", "streak-missed-day")

    def _capture_streak_reward_states(self) -> None:
        self._set_streak_capture_state(
            days=14,
            reviewed=12,
            last_active_offset=0,
            claimed=[7, 14],
        )
        self._capture_metric("streak", "streak-reward-claimed-unclaimed")

    def _capture_nursery_owned_item(self) -> None:
        self._ensure_development_stress_state()
        self._capture_nursery_tab(0, "nursery-item-owned")

    def _capture_custom_nursery(
        self,
        index: int,
        label: str,
        on_ready: Callable[[Any], None],
    ) -> None:
        def dashboard_ready() -> None:
            dashboard = self.app.dashboard

            def dialog_ready() -> None:
                dialog = dashboard.nursery_dialog
                on_ready(dialog)

            QTimer.singleShot(
                0,
                lambda: self._wait_for(
                    lambda: bool(
                        getattr(dashboard, "nursery_dialog", None)
                        and dashboard.nursery_dialog.isVisible()
                        and dashboard.nursery_dialog.catalog_tabs.currentIndex() == index
                    ),
                    dialog_ready,
                    failure_label=label,
                    failure_reason=f"Nursery stress state {label!r} did not become ready",
                ),
            )
            dashboard._open_nursery(index)

        self._with_dashboard(dashboard_ready)

    def _capture_nursery_locked_item(self) -> None:
        self.app.storage.state.currency_balance = 0
        for key in list(self.app.storage.state.consumables):
            self.app.storage.state.consumables[key] = 0

        def ready(dialog: Any) -> None:
            scrollbar = dialog.supplements_scroll.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
            self._capture_and_advance(
                "nursery-item-locked",
                dialog,
                capture_delay_ms=520,
                close_callback=lambda: self._close_widget(dialog),
                close_ms=850,
                next_ms=1200,
            )

        self._capture_custom_nursery(1, "nursery-item-locked", ready)

    def _capture_nursery_purchase_success(self) -> None:
        from .environment import SCENERY_CATALOG, WEATHER_CATALOG

        state = self.app.storage.state
        state.currency_balance = 100_000
        item = next(
            entry for entry in [*WEATHER_CATALOG.values(), *SCENERY_CATALOG.values()]
            if entry.acquisition == "purchase"
        )
        inventory_key = "weather" if item.kind == "weather" else "scenery"
        state.inventory[inventory_key] = [
            key for key in state.inventory.get(inventory_key, [])
            if key != item.item_id
        ]
        if item.kind == "scenery":
            state.inventory["backgrounds"] = [
                key for key in state.inventory.get("backgrounds", [])
                if key != item.item_id
            ]

        def ready(dialog: Any) -> None:
            # Preview and purchase the same catalog object through the normal UI
            # action, then restore that preview after its successful refresh.
            # This keeps the receipt, artwork, name, price, and Owned action
            # product-bound instead of falling back to the first catalog tile.
            dialog._preview_environment_item(item)
            dialog._purchase_environment(item.kind, item.item_id)
            dialog._preview_environment_item(item)
            if not self.app.engine.owns_environment(item.kind, item.item_id):
                self._failures.append({
                    "label": "nursery-purchase-success",
                    "reason": f"Purchase fixture did not own {item.name} after the transaction",
                })
            if str(dialog.environment_feature_title.text()) != item.name:
                self._failures.append({
                    "label": "nursery-purchase-success",
                    "reason": "Purchase success preview no longer matched the purchased catalog item",
                })
            self._capture_and_advance(
                "nursery-purchase-success",
                dialog,
                capture_delay_ms=520,
                close_callback=lambda: self._close_widget(dialog),
                close_ms=900,
                next_ms=1250,
            )

        self._capture_custom_nursery(3, "nursery-purchase-success", ready)

    def _capture_nursery_final_row(self) -> None:
        label = "nursery-final-row-above-footer"
        if not self._ensure_development_stress_state():
            self._next_after(200)
            return

        def ready(dialog: Any) -> None:
            scrollbar = dialog.scroll.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

            def capture_ready() -> None:
                self._audit_nursery_action_above_footer(
                    dialog,
                    dialog.scroll,
                    label,
                    row="last",
                )
                self._capture_and_advance(
                    label,
                    dialog,
                    capture_delay_ms=420,
                    close_callback=lambda: self._close_widget(dialog),
                    close_ms=780,
                    next_ms=1200,
                )

            QTimer.singleShot(140, capture_ready)

        self._capture_custom_nursery(0, label, ready)

    def _capture_missing_artwork_fallback(self) -> None:
        from .environment import SCENERY_CATALOG
        from .ui.dashboard import _asset_preview_label, _item_preview_label

        label = "missing-artwork-graphical-fallback"
        item = next(iter(SCENERY_CATALOG.values()), None)
        if item is None:
            self._failures.append({
                "label": label,
                "reason": "No Scenery product was available for fallback capture",
            })
            self._next_after(200)
            return

        def ready(dialog: Any) -> None:
            engine = self.app.engine
            resolver_names = (
                "resolve_scenery_preview_asset",
                "resolve_plant_asset",
                "resolve_plant_image",
                "resolve_item_asset",
            )
            original_resolvers = {
                name: getattr(engine, name, None) for name in resolver_names
            }
            if not all(callable(original_resolvers[name]) for name in resolver_names):
                self._failures.append({
                    "label": label,
                    "reason": "One or more artwork resolvers were unavailable",
                })
                self._close_widget(dialog)
                self._next_after(200)
                return

            restored = False

            def restore_resolver() -> None:
                nonlocal restored
                if restored:
                    return
                restored = True
                for name, resolver in original_resolvers.items():
                    setattr(engine, name, resolver)

            try:
                setattr(engine, "resolve_scenery_preview_asset", lambda _item_id: None)
                setattr(engine, "resolve_plant_asset", lambda _species, _stage: None)
                setattr(engine, "resolve_plant_image", lambda _species, _stage: None)
                setattr(engine, "resolve_item_asset", lambda _item_key: None)
                dialog._preview_environment_item(item)
                pixmap = dialog.environment_feature_art.pixmap()
                graphical = bool(pixmap is not None and not pixmap.isNull())
                text_free = not bool(str(dialog.environment_feature_art.text() or "").strip())
                plant_preview = _asset_preview_label(
                    engine, "bonsai", "seed", size=84
                )
                plant_pixmap = plant_preview.pixmap()
                plant_graphical = bool(
                    plant_pixmap is not None and not plant_pixmap.isNull()
                )
                plant_text_free = not bool(str(plant_preview.text() or "").strip())
                plant_geometry_stable = (
                    int(plant_preview.width()) == 84
                    and int(plant_preview.height()) == 84
                )
                item_preview = _item_preview_label(
                    engine, "booster_potion", "Booster Potion", size=76
                )
                item_pixmap = item_preview.pixmap()
                item_graphical = bool(
                    item_pixmap is not None and not item_pixmap.isNull()
                )
                item_text_free = not bool(str(item_preview.text() or "").strip())
                item_geometry_stable = (
                    int(item_preview.width()) == 76
                    and int(item_preview.height()) == 76
                )
                passed = all((
                    graphical,
                    text_free,
                    plant_graphical,
                    plant_text_free,
                    plant_geometry_stable,
                    item_graphical,
                    item_text_free,
                    item_geometry_stable,
                ))
                self._capture_annotations[label] = {
                    "resolvers_forced_missing": list(resolver_names),
                    "environment_graphical_pixmap_present": graphical,
                    "environment_text_placeholder_absent": text_free,
                    "plant_graphical_pixmap_present": plant_graphical,
                    "plant_text_placeholder_absent": plant_text_free,
                    "plant_geometry_stable": plant_geometry_stable,
                    "item_graphical_pixmap_present": item_graphical,
                    "item_text_placeholder_absent": item_text_free,
                    "item_geometry_stable": item_geometry_stable,
                    "passed": passed,
                }
                if not passed:
                    self._failures.append({
                        "label": label,
                        "reason": (
                            "Missing environment, plant, or item artwork did not "
                            "render a geometry-stable graphical fallback"
                        ),
                    })
            except Exception:
                restore_resolver()
                self._failures.append({
                    "label": label,
                    "reason": "Missing-artwork fallback fixture could not be prepared",
                })
                self._close_widget(dialog)
                self._next_after(200)
                return

            def close_capture() -> None:
                restore_resolver()
                self._close_widget(dialog)

            self._capture_and_advance(
                label,
                dialog,
                capture_delay_ms=520,
                close_callback=close_capture,
                close_ms=850,
                next_ms=1200,
            )
            QTimer.singleShot(1000, restore_resolver)

        self._capture_custom_nursery(3, label, ready)

    def _capture_custom_settings(
        self,
        label: str,
        tab: int,
        prepare: Callable[[Any], None],
    ) -> None:
        def dashboard_ready() -> None:
            dashboard = self.app.dashboard
            dashboard._open_settings()

            def settings_ready() -> None:
                dialog = self._find_settings_dialog()
                self._set_settings_tab(dialog, tab)
                prepare(dialog)
                self._capture_and_advance(
                    label,
                    dialog,
                    capture_delay_ms=480,
                    close_callback=lambda: self._close_settings_capture(dialog),
                    close_ms=880,
                    next_ms=1250,
                )

            self._wait_for(
                lambda: bool(
                    self._find_settings_dialog() is not None
                    and self._find_settings_dialog().isVisible()
                ),
                settings_ready,
                failure_label=label,
                failure_reason=f"Settings stress state {label!r} did not become ready",
            )

        self._with_dashboard(dashboard_ready)

    @staticmethod
    def _close_settings_capture(dialog: Any) -> None:
        """Restore the saved draft so stress captures never open a discard prompt."""
        try:
            dialog.behavior.apply_persistent_payload(dialog._persisted_payload)
            dialog.garden_name_edit.setText(dialog._persisted_name)
            dialog.done(int(QDialog.DialogCode.Rejected))
        except Exception:
            dialog.close()

    def _capture_settings_unsaved(self) -> None:
        self._capture_custom_settings(
            "settings-unsaved-changes",
            0,
            lambda dialog: dialog.garden_name_edit.setText("Unsaved Moonlit Garden"),
        )

    def _capture_settings_validation_error(self) -> None:
        self._capture_custom_settings(
            "settings-validation-error",
            0,
            lambda dialog: dialog.garden_name_edit.setText("   "),
        )

    def _capture_diagnostics_expanded(self) -> None:
        def prepare(dialog: Any) -> None:
            dialog._refresh_debug_report()
            dialog.report_details_toggle.setChecked(True)

        self._capture_custom_settings("diagnostics-expanded", 1, prepare)

    def _capture_production_controls_absent(self) -> None:
        """Render and audit the Settings branch used by production packages."""

        from . import build_capabilities
        from .ui import dashboard as dashboard_ui

        label = "production-build-controls-absent"

        def dashboard_ready() -> None:
            dashboard = getattr(self.app, "dashboard", None)
            if dashboard is None:
                self._failures.append({
                    "label": label,
                    "reason": "Dashboard was unavailable for production Settings audit",
                })
                self._next_after(200)
                return
            original_capability = dashboard_ui.DEVELOPMENT_MUTATION_ENABLED
            dashboard_ui.DEVELOPMENT_MUTATION_ENABLED = False
            try:
                dialog = dashboard_ui.GardenSettingsDialog(
                    dashboard,
                    self.app.engine,
                    dashboard.config,
                )
            finally:
                dashboard_ui.DEVELOPMENT_MUTATION_ENABLED = original_capability
            dialog.prepare_to_show()
            self._set_settings_tab(dialog, 1)
            dialog.setWindowModality(Qt.WindowModality.NonModal)
            dialog.setModal(False)
            self._move_to_capture_display(dialog)
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()

            forbidden_attributes = (
                "unlock_development",
                "development_panel",
                "populate_development",
                "restore_development",
            )
            forbidden_labels = {
                "Unlock development tools",
                "Populate test garden",
                "Restore backup",
            }
            present_attributes = [
                name for name in forbidden_attributes if hasattr(dialog, name)
            ]
            present_labels = sorted(
                str(button.text())
                for button in dialog.findChildren(QAbstractButton)
                if str(button.text()) in forbidden_labels
            )
            passed = not present_attributes and not present_labels
            self._capture_annotations[label] = {
                "capture_harness_build_mode": str(build_capabilities.BUILD_MODE),
                "production_capability_branch_forced": True,
                "forbidden_attributes_present": present_attributes,
                "forbidden_controls_present": present_labels,
                "passed": passed,
            }
            if not passed:
                self._failures.append({
                    "label": label,
                    "reason": "Production Settings branch exposed development mutation controls",
                })
            self._capture_and_advance(
                label,
                dialog,
                capture_delay_ms=500,
                close_callback=lambda: self._close_widget(dialog),
                close_ms=900,
                next_ms=1250,
            )

        self._with_dashboard(dashboard_ready)

    def _capture_reduced_motion(self) -> None:
        try:
            self.app.dashboard.config.update({"reduced_motion": True})
        except Exception:
            logger.debug("Anki Garden capture: could not persist reduced motion", exc_info=True)
        self._capture_custom_settings(
            "reduced-motion-enabled",
            0,
            lambda dialog: dialog.behavior.reduced_motion.setChecked(True),
        )

    def _capture_keyboard_focus(self) -> None:
        def ready() -> None:
            dashboard = self.app.dashboard
            dashboard.progress_btn.setFocus(Qt.FocusReason.TabFocusReason)
            self._capture_and_advance(
                "keyboard-focus-state",
                dashboard,
                capture_delay_ms=420,
                next_ms=900,
            )

        self._with_dashboard(ready)

    def _capture_narrow_window(self) -> None:
        def ready() -> None:
            dashboard = self.app.dashboard
            previous = dashboard.size()
            dashboard.resize(760, 620)

            def restore() -> None:
                dashboard.resize(previous)

            self._capture_and_advance(
                "narrow-window-responsive",
                dashboard,
                capture_delay_ms=620,
                close_callback=restore,
                close_ms=900,
                next_ms=1200,
            )

        self._with_dashboard(ready)

    def _capture_display_scaling(self) -> None:
        if self._requested_scale_factor not in {"1.5", "1.50", "1.500"}:
            self._failures.append({
                "label": "display-scaling-150",
                "reason": (
                    "The release capture must be launched with QT_SCALE_FACTOR=1.5 "
                    "to verify the 150 percent display state"
                ),
            })
        self._capture_dashboard_stress("display-scaling-150", delay_ms=620)

    def _capture_display_scaling_200_representative(self) -> None:
        """Capture a deterministic Qt logical-viewport proxy for 200% scaling.

        Qt cannot safely change the process display scale after QApplication is
        constructed. The required capture run remains at 150%; this face uses
        the dashboard's minimum logical viewport to exercise the responsive
        geometry a 200% desktop scale would expose, without mutating OS state.
        """

        label = "display-scaling-200-qt-representative"

        def ready() -> None:
            dashboard = self.app.dashboard
            previous_size = dashboard.size()
            logical_width = int(dashboard.MIN_WINDOW_WIDTH)
            logical_height = int(dashboard.MIN_WINDOW_HEIGHT)
            dashboard.resize(logical_width, logical_height)

            def capture_ready() -> None:
                actual_width = int(dashboard.width())
                actual_height = int(dashboard.height())
                passed = (
                    actual_width == logical_width
                    and actual_height == logical_height
                )
                self._capture_annotations[label] = {
                    "representative_kind": "deterministic-qt-logical-viewport",
                    "effective_scale_percent": 200,
                    "os_display_scaling_changed": False,
                    "capture_process_scale_factor": self._requested_scale_factor,
                    "logical_width": actual_width,
                    "logical_height": actual_height,
                    "passed": passed,
                }
                if not passed:
                    self._failures.append({
                        "label": label,
                        "reason": (
                            "Qt 200 percent representative did not reach the "
                            f"required {logical_width} by {logical_height} logical viewport"
                        ),
                    })

                def restore() -> None:
                    dashboard.resize(previous_size)

                self._capture_and_advance(
                    label,
                    dashboard,
                    capture_delay_ms=620,
                    close_callback=restore,
                    close_ms=900,
                    next_ms=1200,
                )

            QTimer.singleShot(180, capture_ready)

        self._with_dashboard(ready)

    def _capture_resize_matrix_face(
        self,
        spec: tuple[str, str, str, int, int, int, int],
    ) -> None:
        """Capture one declared window family after an explicit resize path."""

        label, family, transition, width, height, start_width, start_height = spec
        dashboard = getattr(self.app, "dashboard", None)
        if dashboard is None:
            self._failures.append({
                "label": label,
                "reason": "Dashboard was unavailable for the resize matrix",
            })
            self._next_after(200)
            return

        def capture_widget(widget: QWidget | None, *, close: bool) -> None:
            if widget is None:
                self._failures.append({
                    "label": label,
                    "reason": f"{family} window was unavailable for the resize matrix",
                })
                self._next_after(200)
                return
            widget.setWindowModality(Qt.WindowModality.NonModal)
            set_modal = getattr(widget, "setModal", None)
            if callable(set_modal):
                set_modal(False)
            self._capture_requested_size(
                label,
                widget,
                width=width,
                height=height,
                start_width=start_width,
                start_height=start_height,
                transition_path=transition,
                close_callback=(lambda: self._close_widget(widget)) if close else None,
            )

        if family == "dashboard":
            self._with_dashboard(lambda: capture_widget(self.app.dashboard, close=False))
            return
        if family == "settings":
            from .ui.dashboard import GardenSettingsDialog

            capture_widget(
                GardenSettingsDialog(dashboard, self.app.engine, self.app.config),
                close=True,
            )
            return
        if family == "progress":
            progress = getattr(dashboard, "progress_dialog", None)
            refresh = getattr(progress, "refresh", None)
            if callable(refresh):
                refresh()
            capture_widget(progress, close=True)
            return
        if family == "customize":
            customize = getattr(dashboard, "customize_dialog", None)
            prepare = getattr(customize, "prepare_to_show", None)
            if callable(prepare):
                prepare()
            capture_widget(customize, close=True)
            return
        if family == "nursery":
            from .ui.dashboard import NurseryDialog

            capture_widget(
                NurseryDialog(dashboard, self.app.engine, self.app.storage),
                close=True,
            )
            return
        plant_id = self._select_plant()
        if family == "story":
            from .ui.dashboard import PlantStoryDialog

            capture_widget(
                PlantStoryDialog(dashboard, self.app.engine, plant_id),
                close=True,
            )
            return
        if family == "starter-confirmation":
            from .ui.dashboard import StarterConfirmationDialog

            plant = self.app.engine.plant_story(plant_id)
            species = str(getattr(plant, "species", "bonsai") or "bonsai")
            capture_widget(
                StarterConfirmationDialog(dashboard, self.app.engine, species),
                close=True,
            )
            return
        if family == "fertilizer":
            opener = getattr(dashboard, "_open_fertilizer_menu", None)
            if not callable(opener) or not plant_id:
                capture_widget(None, close=True)
                return
            # The production route uses exec(). Scheduling it lets the nested
            # loop run while capture waits for the identical visible shell.
            QTimer.singleShot(0, lambda: opener(plant_id))
            self._wait_for(
                lambda: bool(
                    getattr(dashboard, "fertilizer_dialog", None)
                    and dashboard.fertilizer_dialog.isVisible()
                ),
                lambda: capture_widget(dashboard.fertilizer_dialog, close=True),
                tries=80,
                failure_label=label,
                failure_reason="Fertilizer window did not become ready for resizing",
            )
            return
        if family == "fertilizer-replacement":
            from .ui.dashboard import FertilizerReplacementDialog

            capture_widget(
                FertilizerReplacementDialog(
                    dashboard,
                    current_name="Basic Fertilizer",
                    current_effect="+1 Growth per Anki card answer",
                    remaining_time="45 seconds",
                    new_name="Premium Fertilizer",
                    new_effect="+3 Growth per Anki card answer",
                    cost=120,
                ),
                close=True,
            )
            return
        if family == "species-overview":
            plant = self.app.engine.plant_story(plant_id)
            species = str(getattr(plant, "species", "") or "")
            builder = getattr(dashboard, "_build_species_overview_dialog", None)
            capture_widget(
                builder(species) if callable(builder) and species else None,
                close=True,
            )
            return
        capture_widget(None, close=True)

    def _finish(self) -> None:
        captured_labels = [
            str(record.get("label", ""))
            for record in self._capture_records
        ]
        expected_labels = list(self._capture_face_labels)
        capture_displays = list(dict.fromkeys(
            str(record.get("capture_display", ""))
            for record in self._capture_records
            if str(record.get("capture_display", "")) in {"primary", "secondary"}
        ))
        capture_display = (
            capture_displays[0]
            if len(capture_displays) == 1 else
            "mixed"
            if capture_displays else
            self._capture_display
        )
        manifest = {
            "captured_at": datetime.now().isoformat(timespec="seconds"),
            "capture_contract_version": CAPTURE_CONTRACT_VERSION,
            "capture_profile": self._capture_profile,
            "capture_display": capture_display,
            "capture_displays": capture_displays,
            "requested_scale_factor": self._requested_scale_factor,
            "capture_groups": [
                {"name": group, "labels": list(labels)}
                for group, labels in self._capture_face_groups
            ],
            "expected_faces": expected_labels,
            "screenshots": self._screenshots,
            "captures": self._capture_records,
            "text_layout_warnings": self._text_layout_warnings,
            "failures": self._failures,
            "expected_count": len(expected_labels),
            "complete": (
                captured_labels == expected_labels
                and len(self._screenshots) == len(expected_labels)
                and not self._failures
                and not self._text_layout_warnings
            ),
        }
        try:
            self._close_top_level_dialogs()
            self._close_dashboard()
        except Exception:
            pass
        try:
            manifest_path = self.session_dir / "manifest.json"
            manifest_path.write_text(
                __import__("json").dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        except Exception:
            logger.debug("Anki Garden capture: could not write manifest", exc_info=True)
        if os.environ.get("ANKI_GARDEN_CAPTURE_QUIT_WHEN_DONE") == "1":
            app = QApplication.instance()
            if app is not None:
                QTimer.singleShot(350, app.quit)
