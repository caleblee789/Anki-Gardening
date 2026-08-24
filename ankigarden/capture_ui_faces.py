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
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from aqt import mw
from aqt.qt import (
    QAbstractButton,
    QAbstractScrollArea,
    QApplication,
    QComboBox,
    QCoreApplication,
    QDialog,
    QEvent,
    QFrame,
    QFont,
    QFontMetricsF,
    QGuiApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPainter,
    QScrollArea,
    QTabWidget,
    QTimer,
    Qt,
    QVBoxLayout,
    QWidget,
)


logger = logging.getLogger(__name__)


def _displayed_button_text(button: QAbstractButton) -> str:
    """Return learner-visible copy after Qt mnemonic escaping."""

    return str(button.text()).replace("&&", "&")


HOME_CAPTURE_BRAND_RGB = (92, 197, 139)
HOME_CAPTURE_DARK_RGB = (
    (7, 26, 21),
    (12, 38, 31),
    (13, 32, 29),
)


CAPTURE_CONTRACT_VERSION = 21
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
            "progress-overview-redirect-growth",
            "progress-achievements",
            "progress-collection",
            "collection-species-overview",
        ),
    ),
    (
        "Collection loadout details",
        (
            "collection-loadout-detail",
            "collection-preview-active",
            "collection-preview-restored",
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
            "settings-home-preview-disabled",
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
            "clear-recall-canonical-projection",
            "streak-at-risk",
            "streak-missed-day",
            "streak-achievement-earned-next",
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
        "Release stress — Settings and reviewer rewards",
        (
            "settings-unsaved-changes",
            "settings-validation-error",
            "diagnostics-expanded",
            "production-build-controls-absent",
            "reviewer-find-common-reduced-motion",
            "reviewer-find-environment",
            "reviewer-find-stacked-sync",
        ),
    ),
    (
        "Accessibility",
        (
            "reduced-motion-enabled",
            "keyboard-focus-state",
        ),
    ),
    (
        "Release overhaul — resumable and resilient states",
        (
            "starter-placement",
            "starter-completion",
            "home-preview-loading",
            "home-preview-error",
            "home-preview-stale",
            "onboarding-persistence-error",
            "move-persistence-error",
            "collection-known-not-collected-overview",
        ),
    ),
    (
        "Release overhaul — purchase confirmations and outcomes",
        (
            "purchase-confirmation-species",
            "purchase-confirmation-growth-charge",
            "purchase-confirmation-environment",
            "purchase-confirmation-fertilizer-application",
            "purchase-confirmation-fertilizer-extension",
            "purchase-confirmation-garden-bed",
            "purchase-confirmation-loading-disabled",
            "purchase-error-insufficient-coins",
            "purchase-error-persistence-failure",
            "purchase-error-item-unavailable",
            "purchase-error-already-owned",
            "purchase-error-invalid-target",
            "purchase-error-stale-price",
            "purchase-error-stale-balance",
            "purchase-success-inventory-collection",
            "purchase-success-fertilizer-applied",
            "purchase-success-garden-bed-unlocked",
            "nursery-empty-state",
            "collection-environment-mechanics",
        ),
    ),
    (
        "Collection consolidation — transactional states",
        (
            "collection-loadout-persistence-error",
            "collection-origin-plant-placement",
        ),
    ),
    (
        "Growth overhaul — Charge confirmation states",
        (
            "growth-charge-use-ready",
            "growth-charge-empty-inventory",
            "growth-charge-loading-disabled",
            "growth-charge-stale-inventory",
            "growth-charge-invalid-target",
            "growth-charge-persistence-failure",
            "growth-charge-success-stage-reward",
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
            "collection-loadout-detail",
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
    "collection-loadout-detail",
    "settings-display",
    "all-six-beds-occupied",
    "reduced-motion-enabled",
    *(f"watering-can-garden-plot-{slot}" for slot in range(1, 7)),
    "watering-can-deck-browser-plot-1",
    "watering-can-deck-browser-plot-3",
    "watering-can-deck-browser-plot-5",
    "watering-can-overview-plot-2",
    "watering-can-overview-plot-4",
    "watering-can-overview-plot-6",
})

WATERING_CAPTURE_GARDEN_NAME = "My Garden"
WATERING_CAPTURE_CURRENCY_BALANCE = 30
WATERING_CAPTURE_GROWTH_POINTS = 500

# ``development_populate()`` intentionally randomizes its broad developer
# fixture. Release evidence needs the same ten source-owned instances in the
# same order on every run, so the capture harness verifies this literal against
# both the current catalog and the release-ready asset projection before using
# it. Keeping the expected order literal also lets offline manifest validators
# bind the live postcondition without importing Anki or Qt.
DEVELOPMENT_STRESS_SPECIES_ORDER: tuple[str, ...] = (
    "bonsai",
    "rose",
    "sunflower",
    "lavender",
    "hydrangea",
    "peony",
    "foxglove",
    "japanese_maple",
    "wisteria",
    "dahlia",
)


# Automated geometry inputs only. These labels are intentionally absent from
# ``CAPTURE_FACE_GROUPS``: canonical release evidence captures each distinct UI
# state once at 100%, while the non-GUI responsive gate evaluates these sizes.
RESIZE_MATRIX_SPECS: tuple[
    tuple[str, str, str, int, int, int, int], ...
] = (
    ("resize-dashboard-minimum", "dashboard", "default-to-minimum", 620, 520, 1240, 840),
    ("resize-dashboard-content-699", "dashboard", "historical-edge-low-stability-probe", 723, 700, 1240, 840),
    ("resize-dashboard-content-701", "dashboard", "historical-edge-high-stability-probe", 725, 700, 1240, 840),
    ("resize-dashboard-content-819", "dashboard", "historical-edge-low-stability-probe", 843, 720, 1240, 840),
    ("resize-dashboard-content-821", "dashboard", "historical-edge-high-stability-probe", 845, 720, 1240, 840),
    ("resize-dashboard-content-899", "dashboard", "historical-edge-low-stability-probe", 923, 740, 1240, 840),
    ("resize-dashboard-content-901", "dashboard", "historical-edge-high-stability-probe", 925, 740, 1240, 840),
    ("resize-dashboard-content-999", "dashboard", "historical-edge-low-stability-probe", 1023, 760, 1240, 840),
    ("resize-dashboard-content-1001", "dashboard", "historical-edge-high-stability-probe", 1025, 760, 1240, 840),
    ("resize-dashboard-content-1359", "dashboard", "historical-edge-low-stability-probe", 1383, 900, 1240, 840),
    ("resize-dashboard-content-1361", "dashboard", "historical-edge-high-stability-probe", 1385, 900, 1240, 840),
    ("resize-dashboard-default", "dashboard", "minimum-to-default", 1240, 840, 620, 520),
    ("resize-dashboard-large", "dashboard", "default-to-large", 1440, 960, 1240, 840),
    ("resize-settings-minimum", "settings", "default-to-minimum", 560, 420, 1020, 690),
    ("resize-settings-content-699", "settings", "historical-edge-low-stability-probe", 747, 620, 1020, 690),
    ("resize-settings-content-701", "settings", "historical-edge-high-stability-probe", 749, 620, 1020, 690),
    ("resize-settings-content-759", "settings", "historical-edge-low-stability-probe", 807, 650, 1020, 690),
    ("resize-settings-content-761", "settings", "historical-edge-high-stability-probe", 809, 650, 1020, 690),
    ("resize-settings-default", "settings", "minimum-to-default", 1020, 690, 560, 420),
    ("resize-settings-large", "settings", "default-to-large", 1180, 880, 1020, 690),
    ("resize-progress-minimum", "progress", "default-to-minimum", 720, 500, 1120, 800),
    ("resize-progress-content-819", "progress", "historical-edge-low-stability-probe", 867, 620, 1120, 800),
    ("resize-progress-content-821", "progress", "historical-edge-high-stability-probe", 869, 620, 1120, 800),
    ("resize-progress-default", "progress", "minimum-to-default", 1120, 800, 720, 500),
    ("resize-progress-large", "progress", "default-to-large", 1180, 880, 1120, 800),
    ("resize-collectible-detail-minimum", "collectible-detail", "default-to-minimum", 680, 480, 1160, 810),
    ("resize-collectible-detail-content-819", "collectible-detail", "historical-edge-low-stability-probe", 867, 620, 1160, 810),
    ("resize-collectible-detail-content-821", "collectible-detail", "historical-edge-high-stability-probe", 869, 620, 1160, 810),
    ("resize-collectible-detail-default", "collectible-detail", "minimum-to-default", 1160, 810, 680, 480),
    ("resize-collectible-detail-large", "collectible-detail", "default-to-large", 1180, 880, 1160, 810),
    ("resize-nursery-minimum", "nursery", "default-to-minimum", 640, 460, 1100, 720),
    ("resize-nursery-content-759", "nursery", "historical-edge-low-stability-probe", 795, 600, 1100, 720),
    ("resize-nursery-content-761", "nursery", "historical-edge-high-stability-probe", 797, 600, 1100, 720),
    ("resize-nursery-default", "nursery", "minimum-to-default", 1100, 720, 640, 460),
    ("resize-nursery-large", "nursery", "default-to-large", 1180, 880, 1100, 720),
    ("resize-story-minimum", "story", "default-to-minimum", 480, 400, 840, 640),
    ("resize-story-content-539", "story", "historical-edge-low-stability-probe", 587, 500, 840, 640),
    ("resize-story-content-541", "story", "historical-edge-high-stability-probe", 589, 500, 840, 640),
    ("resize-story-default", "story", "minimum-to-default", 840, 640, 480, 400),
    ("resize-story-large", "story", "default-to-large", 940, 800, 840, 640),
    ("resize-starter-confirmation-minimum", "starter-confirmation", "default-to-minimum", 360, 280, 560, 320),
    ("resize-starter-confirmation-content-399", "starter-confirmation", "historical-edge-low-stability-probe", 447, 280, 560, 320),
    ("resize-starter-confirmation-content-401", "starter-confirmation", "historical-edge-high-stability-probe", 449, 280, 560, 320),
    ("resize-starter-confirmation-default", "starter-confirmation", "minimum-to-default", 560, 320, 360, 280),
    ("resize-starter-confirmation-large", "starter-confirmation", "default-to-large", 600, 380, 560, 320),
    ("resize-fertilizer-minimum", "fertilizer", "default-to-minimum", 520, 460, 760, 520),
    ("resize-fertilizer-default", "fertilizer", "minimum-to-default", 760, 520, 520, 460),
    ("resize-fertilizer-large", "fertilizer", "default-to-large", 940, 800, 760, 520),
    ("resize-fertilizer-replacement-minimum", "fertilizer-replacement", "default-to-minimum", 420, 400, 680, 460),
    ("resize-fertilizer-replacement-content-399", "fertilizer-replacement", "historical-edge-low-stability-probe", 443, 420, 680, 460),
    ("resize-fertilizer-replacement-content-401", "fertilizer-replacement", "historical-edge-high-stability-probe", 445, 420, 680, 460),
    ("resize-fertilizer-replacement-default", "fertilizer-replacement", "minimum-to-default", 680, 460, 420, 400),
    ("resize-fertilizer-replacement-large", "fertilizer-replacement", "default-to-large", 820, 535, 680, 460),
    ("resize-species-overview-minimum", "species-overview", "default-to-minimum", 500, 420, 920, 720),
    ("resize-species-overview-default", "species-overview", "minimum-to-default", 920, 720, 500, 420),
    ("resize-species-overview-large", "species-overview", "default-to-large", 940, 800, 920, 720),
    ("resize-collection-minimum", "collection", "default-to-minimum", 720, 500, 1120, 800),
    ("resize-collection-default", "collection", "minimum-to-default", 1120, 800, 720, 500),
    ("resize-collection-large", "collection", "default-to-large", 1180, 880, 1120, 800),
)

# Automated purchase-confirmation geometry. The comparison threshold is
# derived from two 220 px cards, 10 px spacing, the shared 24 px responsive
# reserve, and the shell's 44 px outer margins: 518 px. The stability probes
# are exactly one logical pixel below and above that complete threshold.
PURCHASE_CONFIRMATION_RESIZE_SPECS: tuple[
    tuple[str, str, str, int, int, int, int], ...
] = (
    ("purchase-confirmation-minimum", "purchase-confirmation", "default-to-minimum", 420, 400, 680, 460),
    ("purchase-confirmation-breakpoint-low", "purchase-confirmation", "measured-threshold-minus-one", 517, 520, 680, 460),
    ("purchase-confirmation-breakpoint-high", "purchase-confirmation", "measured-threshold-plus-one", 519, 520, 680, 460),
    ("purchase-confirmation-default", "purchase-confirmation", "minimum-to-default", 680, 460, 420, 400),
    ("purchase-confirmation-large", "purchase-confirmation", "default-to-large", 820, 535, 680, 460),
)

# Automated Growth Charge minimum-size geometry. It is not a release capture
# face; the seven distinct Growth Charge states are captured at canonical 100%.
GROWTH_CHARGE_RESIZE_SPECS: tuple[
    tuple[str, str, str, int, int, int, int], ...
] = (
    (
        "geometry-growth-charge-minimum",
        "growth-charge",
        "default-to-minimum",
        420,
        400,
        680,
        500,
    ),
)

# Each resize face owns a semantic layout state in addition to its requested
# geometry.  Native window managers may trim a client surface to the available
# screen, so exact pixels alone are not sufficient to prove that the two sides
# of a breakpoint remained distinct.
RESIZE_MATRIX_LAYOUT_MODES: dict[str, str] = {
    "resize-dashboard-minimum": "narrow",
    "resize-dashboard-content-699": "compact",
    "resize-dashboard-content-701": "compact",
    "resize-dashboard-content-819": "compact",
    "resize-dashboard-content-821": "compact",
    "resize-dashboard-content-899": "compact",
    "resize-dashboard-content-901": "compact",
    "resize-dashboard-content-999": "compact",
    "resize-dashboard-content-1001": "compact",
    "resize-dashboard-content-1359": "compact",
    "resize-dashboard-content-1361": "compact",
    "resize-dashboard-default": "compact",
    "resize-dashboard-large": "compact",
    "resize-settings-minimum": "display",
    "resize-settings-content-699": "display",
    "resize-settings-content-701": "display",
    "resize-settings-content-759": "display",
    "resize-settings-content-761": "display",
    "resize-settings-default": "display",
    "resize-settings-large": "display",
    "resize-progress-minimum": "compact",
    "resize-progress-content-819": "wide",
    "resize-progress-content-821": "wide",
    "resize-progress-default": "wide",
    "resize-progress-large": "wide",
    "resize-collectible-detail-minimum": "compact",
    "resize-collectible-detail-content-819": "compact",
    "resize-collectible-detail-content-821": "compact",
    "resize-collectible-detail-default": "wide",
    "resize-collectible-detail-large": "wide",
    "resize-nursery-minimum": "compact",
    "resize-nursery-content-759": "wide",
    "resize-nursery-content-761": "wide",
    "resize-nursery-default": "wide",
    "resize-nursery-large": "wide",
    "resize-story-minimum": "compact",
    "resize-story-content-539": "wide",
    "resize-story-content-541": "wide",
    "resize-story-default": "wide",
    "resize-story-large": "wide",
    "resize-starter-confirmation-minimum": "compact",
    "resize-starter-confirmation-content-399": "wide",
    "resize-starter-confirmation-content-401": "wide",
    "resize-starter-confirmation-default": "wide",
    "resize-starter-confirmation-large": "wide",
    "resize-fertilizer-minimum": "default",
    "resize-fertilizer-default": "default",
    "resize-fertilizer-large": "default",
    "resize-fertilizer-replacement-minimum": "compact",
    "resize-fertilizer-replacement-content-399": "compact",
    "resize-fertilizer-replacement-content-401": "compact",
    "resize-fertilizer-replacement-default": "compact",
    "resize-fertilizer-replacement-large": "wide",
    "resize-species-overview-minimum": "default",
    "resize-species-overview-default": "default",
    "resize-species-overview-large": "default",
    "resize-collection-minimum": "compact",
    "resize-collection-default": "wide",
    "resize-collection-large": "wide",
    "purchase-confirmation-minimum": "compact",
    "purchase-confirmation-breakpoint-low": "compact",
    "purchase-confirmation-breakpoint-high": "wide",
    "purchase-confirmation-default": "wide",
    "purchase-confirmation-large": "wide",
    "geometry-growth-charge-minimum": "compact",
}


# Canonical 100% evidence that exercises the shared one-scroll/footer contract.
# Breakpoint and resize geometry remain covered by the non-GUI responsive tests.
DIALOG_SCROLL_CAPTURE_COVERAGE: dict[str, tuple[str, ...]] = {
    "Purchase confirmation": (
        "purchase-confirmation-species",
        "purchase-confirmation-growth-charge",
        "purchase-confirmation-environment",
        "purchase-confirmation-fertilizer-application",
        "purchase-confirmation-fertilizer-extension",
        "purchase-confirmation-garden-bed",
        "purchase-confirmation-loading-disabled",
        "purchase-error-insufficient-coins",
        "purchase-error-persistence-failure",
        "purchase-error-item-unavailable",
        "purchase-error-already-owned",
        "purchase-error-invalid-target",
        "purchase-error-stale-price",
        "purchase-error-stale-balance",
    ),
    "Nursery": (
        "nursery-plants",
        "nursery-final-row-above-footer",
    ),
    "Fertilizer selection": (
        "fertilizer-unaffordable",
        "fertilizer-affordable",
        "fertilizer-active",
    ),
    "Fertilizer replacement": (
        "fertilizer-replacement-confirmation",
    ),
    "Plant Story": (
        "plant-story",
    ),
    "Species overview": (
        "collection-species-overview",
        "collection-known-not-collected-overview",
    ),
    "Settings": (
        "settings-display",
        "settings-display-advanced-open",
    ),
    "Garden Progress": (
        "progress-overview-redirect-growth",
        "progress-achievements",
    ),
    "Growth Charge confirmation": (
        "growth-charge-use-ready",
        "growth-charge-empty-inventory",
        "growth-charge-loading-disabled",
        "growth-charge-stale-inventory",
        "growth-charge-invalid-target",
        "growth-charge-persistence-failure",
        "growth-charge-success-stage-reward",
    ),
    "Collection": (
        "progress-collection",
        "collection-several-discovered",
        "collection-no-filter-matches",
    ),
    "Collection loadout details": (
        "collection-loadout-detail",
        "collection-preview-active",
        "collection-preview-restored",
    ),
}


# Expected live renderer/page identity for every scroll-coverage record. The
# geometry audit records the independently observed value so a valid Progress
# shell cannot be misrepresented as Collection (or vice versa).
DIALOG_SCROLL_CAPTURE_SEMANTICS: dict[str, str] = {
    "purchase-confirmation-species": "PurchaseConfirmationDialog",
    "purchase-confirmation-growth-charge": "PurchaseConfirmationDialog",
    "purchase-confirmation-environment": "PurchaseConfirmationDialog",
    "purchase-confirmation-fertilizer-application": "PurchaseConfirmationDialog",
    "purchase-confirmation-fertilizer-extension": "PurchaseConfirmationDialog",
    "purchase-confirmation-garden-bed": "PurchaseConfirmationDialog",
    "purchase-confirmation-loading-disabled": "PurchaseConfirmationDialog",
    "purchase-error-insufficient-coins": "PurchaseConfirmationDialog",
    "purchase-error-persistence-failure": "PurchaseConfirmationDialog",
    "purchase-error-item-unavailable": "PurchaseConfirmationDialog",
    "purchase-error-already-owned": "PurchaseConfirmationDialog",
    "purchase-error-invalid-target": "PurchaseConfirmationDialog",
    "purchase-error-stale-price": "PurchaseConfirmationDialog",
    "purchase-error-stale-balance": "PurchaseConfirmationDialog",
    "nursery-plants": "NurseryDialog:plants",
    "nursery-final-row-above-footer": "NurseryDialog:plants",
    "fertilizer-unaffordable": "FertilizerDialog",
    "fertilizer-affordable": "FertilizerDialog",
    "fertilizer-active": "FertilizerDialog",
    "fertilizer-replacement-confirmation": "FertilizerReplacementDialog",
    "plant-story": "PlantStoryDialog",
    "collection-species-overview": "SpeciesOverviewDialog",
    "collection-known-not-collected-overview": "SpeciesOverviewDialog",
    "settings-display": "GardenSettingsDialog:display",
    "settings-display-advanced-open": "GardenSettingsDialog:display",
    "progress-overview-redirect-growth": "GardenProgressDialog:growth",
    "progress-achievements": "GardenProgressDialog:achievements",
    "progress-collection": "GardenProgressDialog:collection",
    "collection-several-discovered": "GardenProgressDialog:collection",
    "collection-no-filter-matches": "GardenProgressDialog:collection",
    "collection-loadout-detail": "CollectibleDetailDialog:loadout",
    "collection-preview-active": "CollectibleDetailDialog:preview",
    "collection-preview-restored": "CollectibleDetailDialog:preview",
    "growth-charge-use-ready": "GrowthChargeConfirmationDialog",
    "growth-charge-empty-inventory": "GrowthChargeConfirmationDialog",
    "growth-charge-loading-disabled": "GrowthChargeConfirmationDialog",
    "growth-charge-stale-inventory": "GrowthChargeConfirmationDialog",
    "growth-charge-invalid-target": "GrowthChargeConfirmationDialog",
    "growth-charge-persistence-failure": "GrowthChargeConfirmationDialog",
    "growth-charge-success-stage-reward": "GrowthChargeConfirmationDialog",
}


RESPONSIVE_STABILITY_PAIRS: tuple[tuple[str, str], ...] = (
    ("resize-dashboard-content-699", "resize-dashboard-content-701"),
    ("resize-dashboard-content-819", "resize-dashboard-content-821"),
    ("resize-dashboard-content-899", "resize-dashboard-content-901"),
    ("resize-dashboard-content-999", "resize-dashboard-content-1001"),
    ("resize-dashboard-content-1359", "resize-dashboard-content-1361"),
    ("resize-settings-content-699", "resize-settings-content-701"),
    ("resize-settings-content-759", "resize-settings-content-761"),
    ("resize-progress-content-819", "resize-progress-content-821"),
    ("resize-collectible-detail-content-819", "resize-collectible-detail-content-821"),
    ("resize-nursery-content-759", "resize-nursery-content-761"),
    ("resize-story-content-539", "resize-story-content-541"),
    (
        "resize-starter-confirmation-content-399",
        "resize-starter-confirmation-content-401",
    ),
    (
        "resize-fertilizer-replacement-content-399",
        "resize-fertilizer-replacement-content-401",
    ),
)


def dialog_scroll_geometry_issue_codes(
    *,
    registered_count: int,
    active_count: int,
    footer_visible: bool,
    footer_height: int,
    footer_top: int,
    viewport_top: int,
    viewport_height: int,
    declared_clearance: int,
    layout_clearance: int,
    content_height: int,
    content_size_hint_height: int,
    content_minimum_size_hint_height: int,
    scroll_minimum: int,
    scroll_maximum: int,
    last_body_child_bottom: int,
    last_body_child_bottom_at_scroll_end: int,
    require_no_scroll: bool,
) -> tuple[str, ...]:
    """Return fail-closed issue codes for one dialog's vertical scroll owner."""

    registered = int(registered_count)
    active = int(active_count)
    issues: list[str] = []
    if registered and active != 1:
        issues.append("active-scroll-count")
    if active != 1:
        return tuple(issues)

    metrics = {
        "footer_height": int(footer_height),
        "footer_top": int(footer_top),
        "viewport_top": int(viewport_top),
        "declared_clearance": int(declared_clearance),
        "layout_clearance": int(layout_clearance),
        "content_height": int(content_height),
        "content_size_hint_height": int(content_size_hint_height),
        "content_minimum_size_hint_height": int(
            content_minimum_size_hint_height
        ),
        "scroll_minimum": int(scroll_minimum),
        "scroll_maximum": int(scroll_maximum),
        "last_body_child_bottom": int(last_body_child_bottom),
        "last_body_child_bottom_at_scroll_end": int(
            last_body_child_bottom_at_scroll_end
        ),
    }
    if registered < 1:
        issues.append("registered-scroll-count")
    for field, value in metrics.items():
        if value < 0:
            issues.append(f"negative-scroll-metric:{field}")
    if int(viewport_height) <= 0:
        issues.append("invalid-scroll-metric:viewport_height")
    if int(content_height) <= 0:
        issues.append("invalid-scroll-metric:content_height")
    if int(scroll_maximum) < int(scroll_minimum):
        issues.append("invalid-scroll-range")
    scroll_span = max(0, int(scroll_maximum) - int(scroll_minimum))
    expected_body_end = int(viewport_top) + max(
        0,
        int(last_body_child_bottom) - scroll_span,
    )
    if int(last_body_child_bottom_at_scroll_end) != expected_body_end:
        issues.append("last-body-child-position-mismatch")
    body_limit = (
        int(footer_top)
        if bool(footer_visible)
        else int(viewport_top) + int(viewport_height)
    )
    if int(last_body_child_bottom_at_scroll_end) > body_limit:
        issues.append("last-body-child-under-footer")
    if bool(require_no_scroll) and scroll_span != 0:
        issues.append("compact-transaction-scroll-range")

    if bool(footer_visible) and int(footer_height) <= 0:
        issues.append("visible-footer-height")
    if not bool(footer_visible) and int(footer_height) != 0:
        issues.append("hidden-footer-height")
    # DialogShell pins the footer as a normal sibling below the scroll owner.
    # Its content margin therefore stays at the layout's original value
    # (normally zero); adding the footer height would manufacture a blank tail.
    if int(declared_clearance) != int(layout_clearance):
        issues.append("footer-clearance-mismatch")
    viewport_bottom = int(viewport_top) + int(viewport_height)
    if bool(footer_visible) and viewport_bottom > int(footer_top):
        issues.append("footer-viewport-overlap")

    # ``sizeHint`` is a preferred height and may legitimately exceed the
    # widgetResizable QScrollArea's laid-out height. Reachability is governed
    # by the actual content/descendant geometry and its minimum size hint.
    # Treating the preferred hint as mandatory rejects fully reachable Qt
    # layouts by their ordinary style spacing delta.
    required_content_height = max(
        0,
        int(content_height),
        int(content_minimum_size_hint_height),
    )
    reachable_content_height = int(viewport_height) + scroll_span
    if reachable_content_height < required_content_height:
        issues.append("unreachable-scroll-content")
    return tuple(issues)


def responsive_semantic_maps(
    entries: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> tuple[
    dict[str, tuple[str, int, int, tuple[str, ...]]],
    dict[str, tuple[str, int, tuple[str, ...]]],
    tuple[str, ...],
]:
    """Return exact and pair-stability maps plus conflicting duplicate IDs."""

    exact: dict[str, tuple[str, int, int, tuple[str, ...]]] = {}
    stable: dict[str, tuple[str, int, tuple[str, ...]]] = {}
    conflicts: list[str] = []
    for entry in entries:
        semantic_id = str(entry.get("semantic_id", "")).strip()
        if not semantic_id:
            continue
        order = tuple(str(item) for item in entry.get("region_order", ()))
        exact_state = (
            str(entry.get("mode", "")),
            int(entry.get("available_width", -1)),
            int(entry.get("threshold_width", -1)),
            order,
        )
        stable_state = (exact_state[0], exact_state[2], exact_state[3])
        if semantic_id in exact and exact[semantic_id] != exact_state:
            conflicts.append(semantic_id)
            continue
        exact[semantic_id] = exact_state
        stable[semantic_id] = stable_state
    return exact, stable, tuple(dict.fromkeys(conflicts))


def responsive_stability_pair_issue_codes(
    low_entries: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    high_entries: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> tuple[str, ...]:
    """Compare nested responsive state while ignoring the expected 2 px delta."""

    _low_exact, low, low_conflicts = responsive_semantic_maps(low_entries)
    _high_exact, high, high_conflicts = responsive_semantic_maps(high_entries)
    issues: list[str] = []
    if not low:
        issues.append("missing-low-semantic-telemetry")
    if not high:
        issues.append("missing-high-semantic-telemetry")
    for semantic_id in low_conflicts:
        issues.append(f"conflicting-low-semantic-id:{semantic_id}")
    for semantic_id in high_conflicts:
        issues.append(f"conflicting-high-semantic-id:{semantic_id}")
    if set(low) != set(high):
        issues.append("semantic-id-set-mismatch")
    for semantic_id in sorted(set(low) & set(high)):
        if low[semantic_id] != high[semantic_id]:
            issues.append(f"semantic-state-mismatch:{semantic_id}")
    return tuple(issues)


_HOME_CAPTURE_LABELS = frozenset({
    "starter-deck-browser-home",
    "starter-overview-home",
    "deck-browser-home",
    "overview-home",
    "active-deck-browser-home-after-nurture",
    "active-overview-home-after-nurture",
    "watering-can-deck-browser-plot-1",
    "watering-can-deck-browser-plot-3",
    "watering-can-deck-browser-plot-5",
    "watering-can-overview-plot-2",
    "watering-can-overview-plot-4",
    "watering-can-overview-plot-6",
    "home-preview-loading",
    "home-preview-error",
    "home-preview-stale",
})

_DASHBOARD_CAPTURE_LABELS = frozenset({
    "starter-garden-onboarding",
    "full-garden",
    "hover-outline",
    "selected-plant-not-nurtured",
    "selected-plant-nurtured",
    "move-mode",
    "long-garden-name",
    "long-plant-name",
    "four-digit-coin-balance",
    "growth-near-stage-completion",
    "all-six-beds-occupied",
    "plant-at-every-stage",
    "fully-grown-plant-without-fertilize",
    "move-occupied-empty-destinations",
    "keyboard-focus-state",
    *(f"popover-plot-{slot}" for slot in range(1, 7)),
    *(f"watering-can-garden-plot-{slot}" for slot in range(1, 7)),
    "starter-placement",
    "starter-completion",
    "onboarding-persistence-error",
    "move-persistence-error",
    "collection-origin-plant-placement",
})

_PROGRESS_CAPTURE_LABELS = frozenset({
    "growth-zero",
    "growth-nonzero",
    "streak-new",
    "streak-active",
    "coins-zero",
    "coins-activity",
    "progress-overview-redirect-growth",
    "progress-achievements",
    "progress-collection",
    "collection-several-discovered",
    "collection-no-filter-matches",
    "achievement-completed",
    "clear-recall-canonical-projection",
    "streak-at-risk",
    "streak-missed-day",
    "streak-achievement-earned-next",
    "collection-environment-mechanics",
})

_GROWTH_CHARGE_CAPTURE_LABELS = frozenset({
    "growth-charge-use-ready",
    "growth-charge-empty-inventory",
    "growth-charge-loading-disabled",
    "growth-charge-stale-inventory",
    "growth-charge-invalid-target",
    "growth-charge-persistence-failure",
    "growth-charge-success-stage-reward",
})

_NURSERY_CAPTURE_LABELS = frozenset({
    "starter-nursery-plants",
    "starter-action-above-footer",
    "nursery-plants",
    "nursery-fertilizer-booster",
    "nursery-garden-spaces",
    "nursery-weather-scenery",
    "nursery-item-owned",
    "nursery-item-locked",
    "nursery-purchase-success",
    "nursery-final-row-above-footer",
    "missing-artwork-graphical-fallback",
    "purchase-success-inventory-collection",
    "purchase-success-fertilizer-applied",
    "purchase-success-garden-bed-unlocked",
    "nursery-empty-state",
})

_SETTINGS_CAPTURE_LABELS = frozenset({
    "settings-home-preview-disabled",
    "settings-display",
    "settings-display-advanced-open",
    "diagnostics-clean",
    "diagnostics-warning",
    "settings-unsaved-changes",
    "settings-validation-error",
    "diagnostics-expanded",
    "production-build-controls-absent",
    "reduced-motion-enabled",
})

_REVIEWER_CAPTURE_LABELS = frozenset({
    "reviewer-find-common-reduced-motion",
    "reviewer-find-environment",
    "reviewer-find-stacked-sync",
})

COMPACT_HOME_BANNED_COPY: tuple[str, ...] = (
    "today",
    "streak",
    "garden coins",
    "coins",
    "closest",
    "planted starter",
)

# Native Qt layout evidence is produced by ``DialogShell`` and consumed by the
# existing manifest/validator stream. Keep the thresholds source-owned so the
# runner and offline validator cannot silently drift apart.
CAPTURE_LAYOUT_LIMITS: dict[str, float | int] = {
    "maximum_client_gutter_px": 16,
    "maximum_content_footer_gap_px": 48,
    "maximum_nursery_root_offset_px": 16,
    "maximum_action_width_ratio": 0.50,
    "minimum_rendered_text_px": 12.0,
    "maximum_overflow_owner_count": 1,
}

CAPTURE_BUTTON_HEIGHTS: dict[str, int] = {
    "compact-row": 30,
    "secondary": 34,
    "primary": 36,
    "onboarding": 38,
    "icon": 30,
}

TABULAR_NUMERAL_CAPTURE_LABELS = frozenset({
    "growth-zero",
    "growth-nonzero",
    "streak-new",
    "streak-active",
    "coins-zero",
    "coins-activity",
    "progress-overview-redirect-growth",
    "streak-at-risk",
    "streak-missed-day",
    "streak-achievement-earned-next",
    "purchase-error-stale-price",
    "purchase-error-stale-balance",
    "growth-charge-use-ready",
    "growth-charge-stale-inventory",
    "growth-charge-success-stage-reward",
})

MISSING_ARTWORK_CAPTURE_TYPES: tuple[str, ...] = (
    "plant",
    "fertilizer",
    "weather",
    "scenery",
    "growth-charge",
)

RENDERED_PIXEL_EVIDENCE_KEYS: dict[str, tuple[str, ...]] = {
    "full-garden": ("full-garden-scene",),
    "progress-overview-redirect-growth": (
        "direct-growth-label",
        "direct-growth-value",
    ),
    "collection-preview-restored": ("restored-preview-banner",),
    "nursery-item-owned": ("owned-item-card",),
    "missing-artwork-graphical-fallback": ("missing-art-weather",),
    "collection-environment-mechanics": (
        "environment-toolbar",
        "environment-summary-title",
        "environment-summary-selection",
        "environment-edit-appearance",
        "environment-item-title",
        "environment-item-status",
        "environment-effect",
        "environment-mechanics",
    ),
    "collection-loadout-persistence-error": (
        "loadout-preview-scene",
        "loadout-persistence-error",
    ),
}


def expected_capture_window_family(label: str) -> str:
    """Return the exact renderer family required for one manifest fixture."""

    if label in _HOME_CAPTURE_LABELS:
        return "AnkiQt"
    if label in _DASHBOARD_CAPTURE_LABELS:
        return "GardenDashboard"
    if label in _PROGRESS_CAPTURE_LABELS:
        return "GardenProgressDialog"
    if label in _NURSERY_CAPTURE_LABELS:
        return "NurseryDialog"
    if label in _SETTINGS_CAPTURE_LABELS:
        return "GardenSettingsDialog"
    if label in _REVIEWER_CAPTURE_LABELS:
        return "AnkiQt"
    if label in _GROWTH_CHARGE_CAPTURE_LABELS:
        return "GrowthChargeConfirmationDialog"
    if label in {
        "starter-selection-confirmation",
    }:
        return "StarterConfirmationDialog"
    if label in {
        "purchase-confirmation-species",
        "purchase-confirmation-growth-charge",
        "purchase-confirmation-environment",
        "purchase-confirmation-fertilizer-application",
        "purchase-confirmation-fertilizer-extension",
        "purchase-confirmation-garden-bed",
        "purchase-confirmation-loading-disabled",
        "purchase-error-insufficient-coins",
        "purchase-error-persistence-failure",
        "purchase-error-item-unavailable",
        "purchase-error-already-owned",
        "purchase-error-invalid-target",
        "purchase-error-stale-price",
        "purchase-error-stale-balance",
    }:
        return "PurchaseConfirmationDialog"
    if label in {
        "fertilizer-unaffordable",
        "fertilizer-affordable",
        "fertilizer-active",
        "fertilizer-expiring-under-minute",
    }:
        return "FertilizerDialog"
    if label == "fertilizer-replacement-confirmation":
        return "FertilizerReplacementDialog"
    if label == "plant-story":
        return "PlantStoryDialog"
    if label in {
        "collection-species-overview",
        "collection-known-not-collected-overview",
    }:
        return "SpeciesOverviewDialog"
    if label in {
        "collection-loadout-detail",
        "collection-preview-active",
        "collection-preview-restored",
        "collection-loadout-persistence-error",
    }:
        return "CollectibleDetailDialog"
    return ""


def expected_capture_state_profile(label: str) -> dict[str, Any]:
    """Return the state-specific fixture profile required by one capture label.

    Renderer identity alone cannot distinguish two states rendered by the same
    dialog.  Every manifest label therefore receives an exact profile which is
    checked against live widget and storage state immediately before pixels are
    saved.
    """

    family = expected_capture_window_family(label)
    if not family:
        return {}
    profile: dict[str, Any] = {
        "profile_id": label,
        "window_family": family,
    }
    if label in _HOME_CAPTURE_LABELS:
        if label == "home-preview-error":
            surface = "overview"
        elif label.startswith("home-preview-"):
            surface = "deckBrowser"
        else:
            surface = "deckBrowser" if "deck-browser" in label else "overview"
        if label == "home-preview-loading":
            fixture_state = "preview-loading"
        elif label == "home-preview-error":
            fixture_state = "preview-error"
        elif label == "home-preview-stale":
            fixture_state = "preview-stale"
        elif label.startswith("starter-"):
            fixture_state = "starter-not-selected"
        elif label in {"deck-browser-home", "overview-home"}:
            fixture_state = "starter-planted-not-nurtured"
        else:
            fixture_state = "nurtured-active"
        profile.update({
            "kind": "home",
            "surface": surface,
            "fixture_state": fixture_state,
        })
        match = re.search(r"-plot-(\d+)$", label)
        if match:
            profile["active_slot"] = int(match.group(1)) - 1
        return profile
    if label == "collection-known-not-collected-overview":
        profile.update({
            "kind": "dialog",
            "state": "known-not-collected-rare-mystery",
        })
        return profile
    if label in _REVIEWER_CAPTURE_LABELS:
        profile.update({
            "kind": "reviewer",
            "state": label,
            "toast_tier": (
                "Common" if label == "reviewer-find-common-reduced-motion" else
                "Rare" if label == "reviewer-find-environment" else
                ""
            ),
            "stacked_sync": label == "reviewer-find-stacked-sync",
            "reduced_motion": label == "reviewer-find-common-reduced-motion",
        })
        return profile
    if label in _DASHBOARD_CAPTURE_LABELS:
        profile.update({"kind": "dashboard", "state": label})
        return profile
    if label in _PROGRESS_CAPTURE_LABELS:
        page = (
            "growth" if label.startswith("growth-") else
            "streak" if label.startswith("streak-") else
            "currency" if label.startswith("coins-") else
            "growth" if label == "progress-overview-redirect-growth" else
            "collection" if label in {
                "progress-collection",
                "collection-several-discovered",
            "collection-no-filter-matches",
            "collection-known-not-collected-overview",
            "collection-environment-mechanics",
            } else
            "achievements"
        )
        profile.update({"kind": "progress", "page": page, "state": label})
        return profile
    growth_charge_status_by_label = {
        "growth-charge-use-ready": "ready",
        "growth-charge-empty-inventory": "empty_inventory",
        "growth-charge-loading-disabled": "loading",
        "growth-charge-stale-inventory": "stale_inventory",
        "growth-charge-invalid-target": "target_invalid",
        "growth-charge-persistence-failure": "persistence_failure",
        "growth-charge-success-stage-reward": "success",
    }
    if label in growth_charge_status_by_label:
        profile.update({
            "kind": "dialog",
            "state": label,
            "growth_charge_status": growth_charge_status_by_label[label],
        })
        if label == "growth-charge-stale-inventory":
            profile["growth_charge_fixture_semantics"] = (
                "ready_with_stale_inventory_warning"
            )
        return profile
    if label in _NURSERY_CAPTURE_LABELS:
        tab_by_label = {
            "starter-nursery-plants": 0,
            "starter-action-above-footer": 0,
            "nursery-plants": 0,
            "nursery-fertilizer-booster": 1,
            "nursery-garden-spaces": 2,
            "nursery-weather-scenery": 3,
            "nursery-item-owned": 0,
            "nursery-item-locked": 1,
            "nursery-purchase-success": 3,
            "nursery-final-row-above-footer": 0,
            "missing-artwork-graphical-fallback": 3,
            "purchase-success-inventory-collection": 0,
            "purchase-success-fertilizer-applied": 1,
            "purchase-success-garden-bed-unlocked": 2,
            "nursery-empty-state": 0,
        }
        profile.update({
            "kind": "nursery",
            "tab": tab_by_label[label],
            "state": label,
            "starter_mode": label.startswith("starter-"),
        })
        return profile
    if label in _SETTINGS_CAPTURE_LABELS:
        diagnostics_labels = {
            "diagnostics-clean",
            "diagnostics-warning",
            "diagnostics-expanded",
            "production-build-controls-absent",
        }
        profile.update({
            "kind": "settings",
            "tab": 1 if label in diagnostics_labels else 0,
            "state": label,
        })
        return profile
    if label in {
        "collection-loadout-detail",
        "collection-preview-active",
        "collection-preview-restored",
        "collection-loadout-persistence-error",
    }:
        profile.update({"kind": "collectible-detail", "state": label})
        return profile
    purchase_status_by_label = {
        "purchase-confirmation-species": "ready",
        "purchase-confirmation-growth-charge": "ready",
        "purchase-confirmation-environment": "ready",
        "purchase-confirmation-fertilizer-application": "ready",
        "purchase-confirmation-fertilizer-extension": "ready",
        "purchase-confirmation-garden-bed": "ready",
        "purchase-confirmation-loading-disabled": "loading",
        "purchase-error-insufficient-coins": "insufficient_coins",
        "purchase-error-persistence-failure": "persistence_failure",
        "purchase-error-item-unavailable": "item_unavailable",
        "purchase-error-already-owned": "already_owned",
        "purchase-error-invalid-target": "target_invalid",
        "purchase-error-stale-price": "stale_price",
        "purchase-error-stale-balance": "stale_balance",
    }
    if label in purchase_status_by_label:
        profile.update({
            "kind": "dialog",
            "state": label,
            "purchase_status": purchase_status_by_label[label],
        })
        if label == "purchase-error-stale-balance":
            profile["purchase_fixture_semantics"] = (
                "ready_with_balance_update"
            )
        return profile
    profile.update({"kind": "dialog", "state": label})
    return profile


def resize_geometry_acceptance(
    *,
    label: str,
    declared_size: list[int] | tuple[int, int],
    actual_size: list[int] | tuple[int, int],
    minimum_size: list[int] | tuple[int, int],
    maximum_size: list[int] | tuple[int, int],
    screen_limited: bool,
    constraint_limited: bool,
    native_normalized: bool,
    normalization_reason: str,
) -> dict[str, Any]:
    """Classify requested-to-actual drift without hiding unsafe clamps.

    Breakpoint probes keep their declared width within one logical pixel so a
    native resize cannot cross or collapse the audited boundary.  Height may be
    reduced by the window manager, but it must remain inside the widget's
    declared constraints and may never grow unexpectedly beyond the request.
    """

    declared_width, declared_height = (int(value) for value in declared_size)
    actual_width, actual_height = (int(value) for value in actual_size)
    minimum_width, minimum_height = (int(value) for value in minimum_size)
    maximum_width, maximum_height = (int(value) for value in maximum_size)
    exact = [actual_width, actual_height] == [declared_width, declared_height]
    breakpoint_fixture = (
        "-content-" in str(label)
        or "-breakpoint-" in str(label)
    )
    reasons = {
        token.strip()
        for token in str(normalization_reason or "").split(",")
        if token.strip()
    }
    provenance_flags = {
        "screen_limited": bool(screen_limited),
        "constraint_limited": bool(constraint_limited),
        "native_normalized": bool(native_normalized),
    }
    provenance_tokens_match = (
        (not screen_limited or "extends-beyond-available-screen" in reasons)
        and (not constraint_limited or "widget-constraint" in reasons)
        and (not native_normalized or "native-frame-or-scale" in reasons)
    )
    provenance_explains_drift = bool(any(provenance_flags.values())) and bool(
        reasons
    ) and provenance_tokens_match
    breakpoint_width_within_one = (
        not breakpoint_fixture
        or abs(actual_width - declared_width) <= 1
    )
    safe_bounded_width = (
        max(1, minimum_width) <= actual_width <= max(1, maximum_width)
        and actual_width <= max(declared_width + 1, minimum_width)
    )
    safe_bounded_height = (
        max(1, minimum_height) <= actual_height <= max(1, maximum_height)
        and actual_height <= max(declared_height + 1, minimum_height)
    )
    accepted = exact or (
        provenance_explains_drift
        and breakpoint_width_within_one
        and safe_bounded_width
        and safe_bounded_height
    )
    return {
        "exact": exact,
        "drifted": not exact,
        "accepted": accepted,
        "breakpoint_fixture": breakpoint_fixture,
        "breakpoint_width_within_one": breakpoint_width_within_one,
        "safe_bounded_width": safe_bounded_width,
        "safe_bounded_height": safe_bounded_height,
        "provenance_explains_drift": provenance_explains_drift,
        "provenance_flags": provenance_flags,
        "normalization_reasons": sorted(reasons),
        "declared_client_size": [declared_width, declared_height],
        "actual_client_size": [actual_width, actual_height],
        "minimum_client_size": [minimum_width, minimum_height],
        "maximum_client_size": [maximum_width, maximum_height],
    }


def intentional_scroll_viewport_exemption(
    *,
    candidate_rect: list[int] | tuple[int, int, int, int],
    viewport_rect: list[int] | tuple[int, int, int, int],
    horizontal_scrollable: bool,
    vertical_scrollable: bool,
) -> bool:
    """Return whether a widget is wholly outside an intentional scroll viewport.

    An empty QWidget visible region is normally evidence of clipping or
    occlusion.  The sole safe exemption is content beyond a scroll viewport on
    axes that are actually reachable through a nonzero scrollbar range.
    """

    left, top, width, height = (int(value) for value in candidate_rect)
    view_left, view_top, view_width, view_height = (
        int(value) for value in viewport_rect
    )
    if width <= 0 or height <= 0 or view_width <= 0 or view_height <= 0:
        return False
    right = left + width
    bottom = top + height
    view_right = view_left + view_width
    view_bottom = view_top + view_height
    outside_horizontal = right <= view_left or left >= view_right
    outside_vertical = bottom <= view_top or top >= view_bottom
    if not outside_horizontal and not outside_vertical:
        return False
    return (
        (not outside_horizontal or bool(horizontal_scrollable))
        and (not outside_vertical or bool(vertical_scrollable))
    )


def canonicalize_development_stress_plants(
    plants: list[Any],
    species_order: list[str] | tuple[str, ...],
    generated_name: Callable[[str], str],
) -> list[Any]:
    """Return every development plant in deterministic source-catalog order."""

    order = tuple(str(species) for species in species_order)
    rank = {species: index for index, species in enumerate(order)}
    canonical = sorted(
        list(plants),
        key=lambda plant: (
            rank.get(str(getattr(plant, "species", "") or ""), len(rank)),
            str(getattr(plant, "species", "") or ""),
            str(getattr(plant, "plant_id", "") or ""),
        ),
    )
    for plant in canonical:
        species = str(getattr(plant, "species", "") or "")
        plant.name = str(generated_name(species))
        plant.name_customized = False
    return canonical


def restore_capture_plant_order(
    plants: list[Any],
    plant_id_order: list[str] | tuple[str, ...],
) -> list[Any]:
    """Restore exact runtime order after a state serialization round trip."""

    expected = tuple(str(plant_id) for plant_id in plant_id_order)
    by_id: dict[str, Any] = {}
    for plant in plants:
        plant_id = str(getattr(plant, "plant_id", "") or "")
        if not plant_id or plant_id in by_id:
            raise ValueError("Capture fixture plants require unique non-empty IDs")
        by_id[plant_id] = plant
    if len(expected) != len(set(expected)) or set(expected) != set(by_id):
        raise ValueError("Capture fixture plant IDs changed across restoration")
    return [by_id[plant_id] for plant_id in expected]


def start_capture(app: Any) -> None:
    """Launch the UI-face capture sequence for a running add-on instance."""
    _UiFaceCaptureRunner(app).start()


class _UiFaceCaptureRunner:
    def __init__(self, app: Any) -> None:
        self.app = app
        self._capture_started_at = datetime.now().isoformat(timespec="milliseconds")
        self._capture_started_monotonic = time.perf_counter()
        self._capture_requested_monotonic: dict[str, float] = {}
        self._performance_samples: dict[str, list[float]] = {
            "garden_open_ms": [],
        }
        self._dialog_memory_probe: dict[str, Any] = {
            "status": "not-run",
            "cycles": 0,
        }
        self._dialog_memory_probe_attempted = False
        self._finished = False
        self._fatal_fixture_restore_failure = False
        self._active_fixture_source = "capture-runner-initialization"
        self._active_fixture_expected_label = ""
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
        self._active_home_fixture_state = ""
        self._active_home_dom_audit: dict[str, Any] = {}
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
            self._capture_collection_loadout_detail,
            self._capture_collection_preview_active,
            self._capture_collection_preview_restored,
            self._capture_nursery_plants,
            self._capture_nursery_fertilizer_booster,
            self._capture_nursery_garden_spaces,
            self._capture_nursery_weather_scenery,
            self._capture_settings_home_preview_disabled,
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
            self._capture_clear_recall_projection,
            self._capture_streak_at_risk,
            self._capture_streak_missed_day,
            self._capture_streak_achievement_states,
            self._capture_nursery_owned_item,
            self._capture_nursery_locked_item,
            self._capture_nursery_purchase_success,
            self._capture_nursery_final_row,
            self._capture_missing_artwork_fallback,
            self._capture_settings_unsaved,
            self._capture_settings_validation_error,
            self._capture_diagnostics_expanded,
            self._capture_production_controls_absent,
            self._capture_reviewer_find_common,
            self._capture_reviewer_find_environment,
            self._capture_reviewer_find_stacked_sync,
            self._capture_reduced_motion,
            self._capture_keyboard_focus,
            self._capture_starter_placement,
            self._capture_starter_completion,
            lambda: self._capture_home_preview_phase(
                "home-preview-loading", "deckBrowser", "loading"
            ),
            lambda: self._capture_home_preview_phase(
                "home-preview-error", "overview", "error"
            ),
            lambda: self._capture_home_preview_phase(
                "home-preview-stale", "deckBrowser", "stale"
            ),
            self._capture_onboarding_persistence_error,
            self._capture_move_persistence_error,
            self._capture_known_uncollected_species_overview,
            self._capture_purchase_confirmation_species,
            self._capture_purchase_confirmation_growth_charge,
            self._capture_purchase_confirmation_environment,
            self._capture_purchase_confirmation_fertilizer_application,
            self._capture_purchase_confirmation_fertilizer_extension,
            self._capture_purchase_confirmation_bed,
            self._capture_purchase_confirmation_loading,
            self._capture_purchase_error_insufficient,
            self._capture_purchase_error_persistence,
            self._capture_purchase_error_unavailable,
            self._capture_purchase_error_already_owned,
            self._capture_purchase_error_invalid_target,
            self._capture_purchase_error_stale_price,
            self._capture_purchase_error_stale_balance,
            self._capture_purchase_success_collection,
            self._capture_purchase_success_fertilizer,
            self._capture_purchase_success_bed,
            self._capture_nursery_empty_state,
            self._capture_collection_environment_mechanics,
            self._capture_collection_loadout_persistence_error,
            self._capture_collection_origin_plant_placement,
            self._capture_growth_charge_ready,
            self._capture_growth_charge_empty_inventory,
            self._capture_growth_charge_loading,
            self._capture_growth_charge_stale_inventory,
            self._capture_growth_charge_invalid_target,
            self._capture_growth_charge_persistence_failure,
            self._capture_growth_charge_success_reward,
        ]
        self._capture_profile = str(
            os.environ.get("ANKI_GARDEN_CAPTURE_PROFILE", "full") or "full"
        ).strip().lower()
        self._capture_face_groups = CAPTURE_FACE_GROUPS
        if self._capture_profile == "watering-can":
            # The targeted regression profile still seeds through the real
            # first-run transaction, but does not spend time screenshotting
            # unrelated interfaces. The full canonical release contract remains the
            # default.
            self._capture_face_groups = WATERING_CAN_CAPTURE_FACE_GROUPS
            self._starter_steps = []
            self._release_steps = [
                self._capture_nurture,
                self._capture_collection_loadout_detail,
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
        try:
            screens = list(QGuiApplication.screens())
            secondary_requested = (
                os.environ.get("ANKI_GARDEN_CAPTURE_SECOND_MONITOR", "1").lower()
                not in {"0", "false", "no"}
                and len(screens) >= 2
            )
            if secondary_requested:
                primary_ratio = float(screens[0].devicePixelRatio())
                secondary_ratio = float(screens[1].devicePixelRatio())
                if abs(primary_ratio - secondary_ratio) > 0.01:
                    # Moving a live QWebEngineView between mixed-DPI screens can
                    # leave its compositor blank until control returns to Qt.
                    # Select the stable display before the async settle delay.
                    self._capture_force_primary = True
                    logger.info(
                        "Anki Garden capture: mixed display pixel ratios %.2f/%.2f; "
                        "pinning capture windows to the primary display",
                        primary_ratio,
                        secondary_ratio,
                    )
        except Exception:
            logger.debug(
                "Anki Garden capture: could not compare display pixel ratios",
                exc_info=True,
            )
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
            current_screen = None
            if handle is not None:
                current_screen_getter = getattr(handle, "screen", None)
                if callable(current_screen_getter):
                    current_screen = current_screen_getter()
            if current_screen is None:
                current_screen_getter = getattr(widget, "screen", None)
                if callable(current_screen_getter):
                    current_screen = current_screen_getter()
            already_on_target_screen = (
                current_screen is screen or current_screen == screen
            )
            if handle is not None and not already_on_target_screen:
                handle.setScreen(screen)
            geometry = screen.availableGeometry()
            frame = widget.frameGeometry()
            frame_width = max(int(frame.width()), int(widget.width()))
            frame_height = max(int(frame.height()), int(widget.height()))
            inset_x = max(0, min(24, int(geometry.width()) - frame_width))
            inset_y = max(0, min(24, int(geometry.height()) - frame_height))
            frame_fully_inside_target = (
                int(frame.x()) >= int(geometry.x())
                and int(frame.y()) >= int(geometry.y())
                and int(frame.x()) + frame_width
                <= int(geometry.x()) + int(geometry.width())
                and int(frame.y()) + frame_height
                <= int(geometry.y()) + int(geometry.height())
            )
            if not (
                already_on_target_screen and frame_fully_inside_target
            ):
                widget.move(geometry.x() + inset_x, geometry.y() + inset_y)
            self._capture_display = "secondary" if use_secondary else "primary"
        except Exception:
            logger.debug("Anki Garden capture: could not move to selected display", exc_info=True)

    def _prepare_capture_state(self) -> None:
        if self._ensure_capture_state():
            coordinator = getattr(self.app, "state_events", None)
            notify = getattr(coordinator, "notify", None)
            if callable(notify):
                notify("Capture starter fixture committed")
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
            self._failures.append({
                "label": "release-fixture-seed",
                "reason": (
                    "Starter fixture did not reach the planted, not-yet-nurtured "
                    "release boundary"
                ),
            })
            self._finish()
            return
        self._starter_seed_attempts += 1
        QTimer.singleShot(250, self._prepare_capture_state)

    def _ensure_capture_state(self) -> bool:
        """Make capture deterministic with a planted, not-yet-nurtured starter.

        The release sequence captures the consequential boundary on both sides:
        the real select, confirm, and placement transitions persist the starter
        and its no-active-plant sentinel, then the later Nurture face uses the
        normal dashboard action to make the active assignment. Capture setup
        must not skip that boundary.
        """
        from .models.state import OnboardingStep

        state = getattr(self.app.storage, "state", None)
        if state is None:
            return False
        plants = list(getattr(state, "plants", []) or [])
        if (
            bool(getattr(state, "starter_selection_complete", False))
            and plants
            and not getattr(state, "active_plant_id", None)
            and state.onboarding.step == OnboardingStep.NURTURE
        ):
            return True
        ready = getattr(self.app.engine, "release_ready_species", None)
        if ready is None:
            return False
        try:
            candidates = list(ready())
        except Exception:
            return False
        if not candidates:
            return False
        species = str(candidates[0]).lower()
        try:
            step = state.onboarding.step
            if step == OnboardingStep.INTRODUCTION:
                self.app.engine.enter_starter_nursery()
                return False
            if step == OnboardingStep.NURSERY:
                self.app.engine.select_starter_species(species)
                return False
            if step == OnboardingStep.CONFIRMATION:
                self.app.engine.confirm_starter_species()
                return False
            if step == OnboardingStep.PLACEMENT:
                ok, _message, plant = self.app.engine.place_starter(0)
                return bool(ok and plant is not None)
        except Exception:
            logger.debug("Anki Garden capture: starter bootstrap waiting for scheduler", exc_info=True)
        return False

    def _next_step(self) -> None:
        if self._fatal_fixture_restore_failure:
            self._finish()
            return
        if self._step_index >= len(self._steps):
            if self._phase == "starter":
                self._phase = "seeding"
                self._close_top_level_dialogs()
                self._close_dashboard()
                QTimer.singleShot(350, self._prepare_capture_state)
                return
            if (
                self._capture_profile == "full"
                and not self._dialog_memory_probe_attempted
            ):
                self._dialog_memory_probe_attempted = True
                self._run_dialog_memory_probe()
                return
            self._finish()
            return
        current = self._steps[self._step_index]
        self._step_index += 1
        expected_index = max(0, self._capture_index - 1)
        expected_label = (
            self._capture_face_labels[expected_index]
            if expected_index < len(self._capture_face_labels) else
            f"capture-step-{self._step_index}"
        )
        self._active_fixture_source = (
            f"ordered-step-{self._step_index:03d}:"
            f"{getattr(current, '__name__', type(current).__name__)}"
        )
        self._active_fixture_expected_label = expected_label
        trace = getattr(globals().get("logger"), "info", None)
        if callable(trace):
            trace(
                "Anki Garden capture step %d/%d: expected=%s source=%s capture_index=%d",
                self._step_index,
                len(self._steps),
                expected_label,
                self._active_fixture_source,
                self._capture_index,
            )
        try:
            current()
        except Exception as exc:
            self._failures.append({
                "label": expected_label,
                "reason": (
                    f"Capture step {self._active_fixture_source!r} raised "
                    f"{type(exc).__name__}"
                ),
            })
            logger.exception("Anki Garden capture: step failed, moving on")
            self._next_after(300)

    def _next_after(self, delay_ms: int) -> None:
        QTimer.singleShot(max(80, int(delay_ms)), self._next_step)

    def _one_shot_async_callback(
        self,
        label: str,
        callback: Callable[..., Any],
        *,
        on_error: Callable[[], None] | None = None,
        advance_on_error: bool = True,
    ) -> Callable[..., Any]:
        """Guard a Qt callback so it runs once and exceptions fail closed.

        WebEngine, timers, and nested dialog loops may deliver a callback late
        or more than once.  A raised callback must never be mistaken for a
        predicate miss and retried against a later fixture.
        """

        if bool(getattr(callback, "_anki_garden_capture_one_shot", False)):
            return callback
        called = False

        def guarded(*args: Any, **kwargs: Any) -> Any:
            nonlocal called
            if called:
                return None
            called = True
            try:
                return callback(*args, **kwargs)
            except Exception as exc:
                self._failures.append({
                    "label": label,
                    "reason": (
                        "Capture readiness callback raised "
                        f"{type(exc).__name__}"
                    ),
                })
                logger.exception(
                    "Anki Garden capture: asynchronous callback failed for %s",
                    label,
                )
                if on_error is not None:
                    try:
                        on_error()
                    except Exception as cleanup_exc:
                        self._failures.append({
                            "label": label,
                            "reason": (
                                "Capture failure cleanup raised "
                                f"{type(cleanup_exc).__name__}"
                            ),
                        })
                        logger.exception(
                            "Anki Garden capture: callback cleanup failed for %s",
                            label,
                        )
                if advance_on_error:
                    self._next_after(120)
                return None

        setattr(guarded, "_anki_garden_capture_one_shot", True)
        setattr(guarded, "_anki_garden_capture_label", str(label))
        return guarded

    def _run_dialog_memory_probe(self, *, cycles: int = 12) -> None:
        """Measure retained Qt widgets after repeated real Nursery open/close cycles."""

        dashboard = getattr(self.app, "dashboard", None)
        app = QApplication.instance()
        opener = getattr(dashboard, "_open_nursery", None)
        if app is None or dashboard is None or not callable(opener):
            self._dialog_memory_probe = {
                "status": "unavailable",
                "cycles": 0,
                "visible_cycles": 0,
                "closed_cycles": 0,
                "passed": False,
                "reason": "Dashboard or Nursery opener was unavailable",
            }
            self._failures.append({
                "label": "dialog-memory-probe",
                "reason": "Dashboard or Nursery opener was unavailable",
            })
            QTimer.singleShot(80, self._finish)
            return

        def class_counts() -> dict[str, int]:
            counts: dict[str, int] = {}
            for widget in tuple(app.allWidgets()):
                name = type(widget).__name__
                counts[name] = counts.get(name, 0) + 1
            return counts

        def max_rss_kib() -> int | None:
            try:
                usage = __import__("resource").getrusage(
                    __import__("resource").RUSAGE_SELF
                )
                raw = int(getattr(usage, "ru_maxrss", 0) or 0)
                # macOS reports bytes; Linux reports KiB.
                return raw // 1024 if platform.system() == "Darwin" else raw
            except Exception:
                return None

        before = class_counts()
        before_total = len(tuple(app.allWidgets()))
        before_rss = max_rss_kib()
        completed = 0
        visible_cycles = 0
        closed_cycles = 0
        cycle_observations: list[dict[str, Any]] = []
        try:
            for index in range(max(1, int(cycles))):
                observation: dict[str, Any] = {
                    "cycle": index + 1,
                    "visible": False,
                    "closed": False,
                }

                def close_current() -> None:
                    dialog = getattr(dashboard, "nursery_dialog", None)
                    observation["dialog_class"] = (
                        type(dialog).__name__ if dialog is not None else ""
                    )
                    try:
                        is_nursery = bool(
                            dialog is not None
                            and str(
                                dialog.property("windowFamily")
                                or type(dialog).__name__
                            ) == "NurseryDialog"
                        )
                        observation["visible"] = bool(
                            is_nursery and dialog.isVisible()
                        )
                        if dialog is not None:
                            self._close_widget(dialog)
                        app.processEvents()
                        observation["closed"] = bool(
                            dialog is not None and not dialog.isVisible()
                        )
                    except RuntimeError:
                        # A Qt object deleted immediately after close still
                        # proves closure if it was visibly observed first.
                        observation["closed"] = bool(observation["visible"])
                    except Exception as exc:
                        observation["close_error"] = type(exc).__name__
                        if dialog is not None:
                            self._close_widget(dialog)

                QTimer.singleShot(80, close_current)
                opener(0)
                app.processEvents()
                cycle_observations.append(dict(observation))
                if not bool(observation["visible"]):
                    raise RuntimeError(
                        f"Nursery cycle {index + 1} never became visible"
                    )
                visible_cycles += 1
                if not bool(observation["closed"]):
                    raise RuntimeError(
                        f"Nursery cycle {index + 1} did not close"
                    )
                closed_cycles += 1
                completed += 1
        except Exception as exc:
            logger.exception("Anki Garden capture: dialog memory probe failed")
            self._dialog_memory_probe = {
                "status": "error",
                "cycles": completed,
                "visible_cycles": visible_cycles,
                "closed_cycles": closed_cycles,
                "cycle_observations": cycle_observations,
                "passed": False,
                "reason": f"{type(exc).__name__}: {exc}",
            }
            self._failures.append({
                "label": "dialog-memory-probe",
                "reason": f"Nursery visibility/closure probe failed: {exc}",
            })
            QTimer.singleShot(80, self._finish)
            return

        try:
            # ``processEvents()`` alone does not guarantee delivery of
            # DeferredDelete events while this probe is itself running inside
            # a capture callback. Drain them explicitly so the after-count
            # measures retained widgets rather than queued Qt cleanup.
            app.processEvents()
            QCoreApplication.sendPostedEvents(
                None,
                QEvent.Type.DeferredDelete,
            )
            app.processEvents()
        except Exception as exc:
            logger.exception(
                "Anki Garden capture: dialog memory cleanup drain failed"
            )
            self._dialog_memory_probe = {
                "status": "error",
                "cycles": completed,
                "visible_cycles": visible_cycles,
                "closed_cycles": closed_cycles,
                "cycle_observations": cycle_observations,
                "passed": False,
                "reason": f"DeferredDelete drain failed: {type(exc).__name__}: {exc}",
            }
            self._failures.append({
                "label": "dialog-memory-probe",
                "reason": f"Nursery retention cleanup could not be measured: {exc}",
            })
            QTimer.singleShot(80, self._finish)
            return

        after = class_counts()
        after_rss = max_rss_kib()
        watched = (
            "NurseryDialog",
            "DialogShell",
            "PlantStoryDialog",
            "GardenDialog",
        )
        watched_delta = {
            name: after.get(name, 0) - before.get(name, 0)
            for name in watched
        }
        passed = (
            int(cycles) == 12
            and completed == 12
            and visible_cycles == 12
            and closed_cycles == 12
            and watched_delta["NurseryDialog"] == 0
        )
        self._dialog_memory_probe = {
            "status": "measured",
            "cycles": completed,
            "visible_cycles": visible_cycles,
            "closed_cycles": closed_cycles,
            "cycle_observations": cycle_observations,
            "passed": passed,
            "measurement": "QApplication.allWidgets plus process peak RSS",
            "current_rss_available": False,
            "peak_rss_before_kib": before_rss,
            "peak_rss_after_kib": after_rss,
            "widget_count_before": before_total,
            "widget_count_after": len(tuple(app.allWidgets())),
            "watched_class_counts_before": {
                name: before.get(name, 0) for name in watched
            },
            "watched_class_counts_after": {
                name: after.get(name, 0) for name in watched
            },
            "watched_class_delta": watched_delta,
        }
        if not passed:
            self._failures.append({
                "label": "dialog-memory-probe",
                "reason": (
                    "Release memory probe required 12 visible and closed Nursery "
                    "cycles with exactly zero retained NurseryDialog widgets; "
                    f"observed {visible_cycles} visible, {closed_cycles} closed, "
                    f"and a NurseryDialog delta of {watched_delta['NurseryDialog']}"
                ),
            })
        QTimer.singleShot(120, self._finish)

    def _wait_for_collection(
        self,
        ready: Callable[[], None],
        *,
        tries: int = 40,
        failure_label: str = "collection-ready",
        on_error: Callable[[], None] | None = None,
    ) -> None:
        ready = self._one_shot_async_callback(
            failure_label,
            ready,
            on_error=on_error or self._finish,
            advance_on_error=False,
        )
        collection = getattr(mw, "col", None)
        if collection is not None and getattr(collection, "db", None) is not None:
            ready()
            return
        if tries <= 0:
            self._failures.append({
                "label": failure_label,
                "reason": "Anki collection did not become ready before capture",
            })
            if on_error is not None:
                on_error()
            else:
                self._finish()
            return
        QTimer.singleShot(
            120,
            lambda: self._wait_for_collection(
                ready,
                tries=tries - 1,
                failure_label=failure_label,
                on_error=on_error,
            ),
        )

    def _wait_for_dashboard(
        self,
        ready: Callable[[], None],
        *,
        tries: int = 80,
        failure_label: str = "dashboard-ready",
        on_error: Callable[[], None] | None = None,
    ) -> None:
        ready = self._one_shot_async_callback(
            failure_label,
            ready,
            on_error=on_error,
        )
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
            self._failures.append({
                "label": failure_label,
                "reason": "Garden Dashboard did not become visible before capture",
            })
            if on_error is not None:
                on_error()
            self._next_after(120)
            return
        QTimer.singleShot(
            120,
            lambda: self._wait_for_dashboard(
                ready,
                tries=tries - 1,
                failure_label=failure_label,
                on_error=on_error,
            ),
        )

    def _wait_for(
        self,
        predicate: Callable[[], bool],
        on_ready: Callable[[], None],
        *,
        tries: int = 80,
        failure_label: str,
        failure_reason: str = "",
        started_monotonic: float | None = None,
        on_error: Callable[[], None] | None = None,
    ) -> None:
        on_ready = self._one_shot_async_callback(
            failure_label,
            on_ready,
            on_error=on_error,
        )
        if started_monotonic is None:
            started_monotonic = time.perf_counter()
        is_ready = False
        try:
            is_ready = bool(predicate())
        except Exception:
            pass
        if is_ready:
            elapsed_ms = max(
                0.0,
                (time.perf_counter() - started_monotonic) * 1000.0,
            )
            self._performance_samples.setdefault(
                f"surface_ready:{failure_label}",
                [],
            ).append(round(elapsed_ms, 3))
            on_ready()
            return
        if tries <= 0:
            self._failures.append({
                "label": failure_label,
                "reason": failure_reason or "Timed out waiting for the requested UI surface",
            })
            if on_error is not None:
                on_error()
            self._next_after(120)
            return
        QTimer.singleShot(
            120,
            lambda: self._wait_for(
                predicate,
                on_ready,
                tries=tries - 1,
                failure_label=failure_label,
                failure_reason=failure_reason,
                started_monotonic=started_monotonic,
                on_error=on_error,
            ),
        )

    def _wait_for_home_surface(
        self,
        state: str,
        capture_label: str,
        on_ready: Callable[[], None],
        *,
        tries: int = 100,
    ) -> None:
        on_ready = self._one_shot_async_callback(capture_label, on_ready)
        if str(getattr(mw, "state", "")) != state:
            if tries <= 0:
                self._failures.append({
                    "label": capture_label,
                    "reason": f"Anki surface {state!r} did not become active",
                })
                self._next_after(120)
                return
            QTimer.singleShot(
                120,
                lambda: self._wait_for_home_surface(
                    state,
                    capture_label,
                    on_ready,
                    tries=tries - 1,
                ),
            )
            return
        web = getattr(mw, "web", None)
        overview_root_script = ""
        if state == "overview" and tries in {100, 75, 50, 25}:
            # Anki keeps its external Congratulations document alive while
            # repeated Overview fixtures change underneath it.  That means
            # ``webview_did_inject_style_into_page`` is not guaranteed to fire
            # again even though the source-backed Garden HTML has advanced.
            # Prefix the DOM audit with the production replacement script so
            # both operations run in one current-frame WebEngine transaction.
            # A navigation can discard a separate asynchronous eval between
            # these operations during a full 126-face run.
            build_overview_root_script = getattr(
                self.app,
                "_home_garden_root_replacement_script",
                None,
            )
            if callable(build_overview_root_script):
                try:
                    overview_root_script = str(
                        build_overview_root_script() or ""
                    )
                except Exception:
                    logger.debug(
                        "Anki Garden capture: Overview root refresh failed for %s",
                        capture_label,
                        exc_info=True,
                    )
        page_getter = getattr(web, "page", None)
        page = page_getter() if callable(page_getter) else None
        run_javascript = getattr(page, "runJavaScript", None)
        evaluate = getattr(web, "evalWithCallback", None)
        if not callable(run_javascript) and not callable(evaluate):
            self._failures.append({
                "label": capture_label,
                "reason": "Home fixture identity could not be verified without WebEngine",
            })
            self._next_after(120)
            return

        special_fixture_state = {
            "home-preview-loading": "preview-loading",
            "home-preview-error": "preview-error",
            "home-preview-stale": "preview-stale",
        }.get(capture_label, "")
        garden_state = getattr(self.app.storage, "state", None)
        starter_complete = bool(
            getattr(garden_state, "starter_selection_complete", False)
        )
        active_plant_id = str(
            getattr(garden_state, "active_plant_id", "") or ""
        )
        plants = list(getattr(garden_state, "plants", ()) or ())
        active_plant = next((
            plant for plant in plants
            if str(getattr(plant, "plant_id", "") or "") == active_plant_id
        ), None)
        active_slot_value = (
            getattr(active_plant, "slot_index", None)
            if active_plant is not None else None
        )
        expected_active_slot = (
            int(active_slot_value)
            if active_slot_value is not None else -1
        )
        if special_fixture_state:
            fixture_state = special_fixture_state
        elif not starter_complete:
            fixture_state = "starter-not-selected"
        elif active_plant_id:
            fixture_state = "nurtured-active"
        elif plants:
            fixture_state = "starter-planted-not-nurtured"
        else:
            fixture_state = "starter-complete-without-plant"
        self._active_home_fixture_state = fixture_state
        script = """
            (() => {
              const roots = [...document.querySelectorAll('#ag-home-root')];
              const visibleRoots = roots.filter(candidate => {
                const bounds = candidate.getBoundingClientRect();
                const style = window.getComputedStyle(candidate);
                return bounds.width >= 100 && bounds.height >= 100
                  && style.display !== 'none' && style.visibility !== 'hidden';
              });
              const root = visibleRoots.length
                ? visibleRoots[visibleRoots.length - 1]
                : null;
              if (!root) {
                return {
                  ready: false,
                  reason: 'no-visible-root',
                  rootCount: roots.length,
                  visibleRootCount: visibleRoots.length,
                };
              }
              const rect = root.getBoundingClientRect();
              const images = [...root.querySelectorAll('img')];
              const imagesComplete = images.every(img => img.complete);
              const failedImageCount = images.filter(
                img => img.complete && img.naturalWidth <= 0
              ).length;
              const homeAction = root.querySelector('[data-testid="home-open"]');
              const command = homeAction
                ? homeAction.dataset.ankiGardenCommand || ''
                : root.dataset.ankiGardenCommand || '';
              const growth = root.querySelector('[data-testid="home-growth"]');
              const growthText = growth ? growth.textContent || '' : '';
              const activeSlot = Number(root.dataset.activeSlot || '-1');
              const marker = root.querySelector(
                '[data-testid="home-nurturing-marker"], '
                + '[data-testid="home-nurturing-marker-fallback"]'
              );
              const sceneFrame = root.querySelector('.ag-home__scene-frame');
              const weatherLayer = root.querySelector('[data-testid="home-weather-layer"]');
              const sunLayer = root.querySelector(
                '[data-testid="home-sun-layer"], .ag-home__sun-layer, .ag-home__sun'
              );
              const sceneryLayer = root.querySelector('[data-testid="home-scenery-layer"]');
              const previewStatus = root.querySelector(
                '[data-testid="home-preview-status"]'
              );
              const previewStatusPresent = !!previewStatus;
              const previewStatusRect = previewStatus
                ? previewStatus.getBoundingClientRect()
                : null;
              const homeActionRect = homeAction
                ? homeAction.getBoundingClientRect()
                : null;
              const previewStatusActionOverlap = !!(
                previewStatusRect && homeActionRect
                && previewStatusRect.left < homeActionRect.right
                && previewStatusRect.right > homeActionRect.left
                && previewStatusRect.top < homeActionRect.bottom
                && previewStatusRect.bottom > homeActionRect.top
              );
              const loadingPresent = !!root.querySelector(
                '[data-testid="home-loading"]'
              );
              const accessibilityCopy = [
                root.getAttribute('aria-label') || '',
                ...[...root.querySelectorAll('[aria-label]')].map(
                  candidate => candidate.getAttribute('aria-label') || ''
                ),
                ...[...root.querySelectorAll('.ag-home__sr-only')].map(
                  candidate => candidate.textContent || ''
                ),
              ].join(' ');
              const renderedCopy = `${root.innerText || ''} ${accessibilityCopy}`
                .replace(/\\s+/g, ' ')
                .trim();
              const normalizedCopy = renderedCopy.toLocaleLowerCase('en-US');
              const bannedTerms = [
                'today',
                'streak',
                'garden coins',
                'coins',
                'closest',
                'planted starter',
              ].filter(term => normalizedCopy.includes(term));
              const compactFieldsPresent = !!(
                root.querySelector('[data-testid="home-title"]')
                && root.querySelector('[data-testid="home-support"]')
                && homeAction
              );
              const fixtureState = __FIXTURE_STATE__;
              const expectedActiveSlot = __EXPECTED_ACTIVE_SLOT__;
              const support = root.querySelector('[data-testid="home-support"]');
              const supportText = (support ? support.textContent || '' : '').trim();
              const homeActionText = (homeAction ? homeAction.textContent || '' : '').trim();
              const homeActionGeometryPassed = !homeAction
                || homeActionText !== 'Open Garden'
                || (
                  Math.round(homeActionRect.width) >= 104
                  && Math.round(homeActionRect.width) <= 120
                  && Math.round(homeActionRect.height) === 36
                );
              const conciseInformationModelPassed = (
                fixtureState === 'preview-loading'
                  ? normalizedCopy.includes('loading garden')
                  : fixtureState === 'preview-error'
                    ? normalizedCopy.includes('garden preview unavailable')
                      && homeActionText === 'Open Garden'
                    : fixtureState === 'starter-not-selected'
                      ? homeActionText.length > 0
                      : supportText.includes('Growth')
                        && homeActionText === 'Open Garden'
              );
              let fixtureMatches = false;
              if (fixtureState === 'starter-not-selected') {
                fixtureMatches = command.endsWith(':choose-starter')
                  && activeSlot < 0
                  && !marker;
              } else if (fixtureState === 'starter-planted-not-nurtured') {
                fixtureMatches = command.endsWith(':open')
                  && activeSlot < 0
                  && !marker;
              } else if (fixtureState === 'nurtured-active') {
                fixtureMatches = command.endsWith(':open')
                  && activeSlot === expectedActiveSlot
                  && !!marker;
              } else if (fixtureState === 'preview-loading') {
                fixtureMatches = root.dataset.state === 'loading'
                  && !!root.querySelector('[data-testid="home-loading"]');
              } else if (fixtureState === 'preview-error') {
                fixtureMatches = root.dataset.state === 'error'
                  && !!root.querySelector('[data-testid="home-error"]');
              } else if (fixtureState === 'preview-stale') {
                fixtureMatches = root.dataset.state === 'stale'
                  && command.endsWith(':open')
                  && !!previewStatus
                  && !!homeAction
                  && !homeAction.disabled
                  && !previewStatusActionOverlap;
              }
              const paintedState = fixtureState.startsWith('preview-')
                ? root.dataset.state === fixtureState.replace('preview-', '')
                : ['success', 'partial'].includes(root.dataset.state);
              const canonicalSettled = fixtureState.startsWith('preview-') || (
                root.dataset.state === 'success'
                && !previewStatusPresent
                && !loadingPresent
                && failedImageCount === 0
              );
              return {
                ready: paintedState && imagesComplete && canonicalSettled
                  && fixtureMatches && bannedTerms.length === 0
                  && homeActionGeometryPassed && conciseInformationModelPassed,
                reason: !paintedState ? 'unpainted-state'
                  : !imagesComplete ? 'images-pending'
                  : !canonicalSettled ? 'canonical-preview-unsettled'
                  : !fixtureMatches ? 'fixture-mismatch'
                  : 'ready',
                rootCount: roots.length,
                visibleRootCount: visibleRoots.length,
                state: root.dataset.state || '',
                command,
                activeSlot,
                markerPresent: !!marker,
                weatherLayerPresent: !!weatherLayer,
                sunLayerPresent: !!sunLayer,
                sceneryLayerPresent: !!sceneryLayer,
                sceneOpacity: sceneFrame
                  ? Number.parseFloat(window.getComputedStyle(sceneFrame).opacity || '1')
                  : null,
                imagesComplete,
                failedImageCount,
                previewStatusPresent,
                previewStatusActionOverlap,
                previewStatusBounds: previewStatusRect ? {
                  left: Math.round(previewStatusRect.left - rect.left),
                  top: Math.round(previewStatusRect.top - rect.top),
                  right: Math.round(previewStatusRect.right - rect.left),
                  bottom: Math.round(previewStatusRect.bottom - rect.top),
                } : null,
                homeActionBounds: homeActionRect ? {
                  left: Math.round(homeActionRect.left - rect.left),
                  top: Math.round(homeActionRect.top - rect.top),
                  right: Math.round(homeActionRect.right - rect.left),
                  bottom: Math.round(homeActionRect.bottom - rect.top),
                } : null,
                homeActionEnabled: !!homeAction && !homeAction.disabled,
                homeActionText,
                homeActionWidth: homeActionRect
                  ? Math.round(homeActionRect.width) : null,
                homeActionHeight: homeActionRect
                  ? Math.round(homeActionRect.height) : null,
                homeActionGeometryPassed,
                supportText,
                conciseInformationModelPassed,
                loadingPresent,
                renderedCopy,
                bannedTerms,
                compactFieldsPresent,
                plantedSummaryPresent: !!root.querySelector('.planted-starter-summary'),
                nurturedSummaryPresent: !!root.querySelector('.nurtured-plant-summary'),
                growthText,
                fixtureState,
                expectedActiveSlot,
                width: Math.round(rect.width),
                height: Math.round(rect.height),
              };
            })()
        """.replace(
            "__FIXTURE_STATE__",
            repr(fixture_state),
        ).replace(
            "__EXPECTED_ACTIVE_SLOT__",
            str(expected_active_slot),
        )
        if overview_root_script:
            script = f"{overview_root_script}\n{script}"

        settled = False

        def retry_or_fail() -> None:
            if tries in {100, 75, 50, 25, 0}:
                trace = getattr(globals().get("logger"), "info", None)
                if callable(trace):
                    trace(
                        "Anki Garden Home readiness: label=%s tries=%d observation=%r",
                        capture_label,
                        tries,
                        dict(getattr(self, "_active_home_dom_audit", {}) or {}),
                    )
            if tries <= 0:
                observed = dict(getattr(self, "_active_home_dom_audit", {}) or {})
                self._failures.append({
                    "label": capture_label,
                    "reason": (
                        "Home widget never reached the source-backed fixture state "
                        f"{fixture_state!r}; last DOM observation: {observed!r}"
                    ),
                })
                self._next_after(120)
            else:
                observed = dict(getattr(self, "_active_home_dom_audit", {}) or {})
                stale_nurtured_slot = bool(
                    fixture_state == "nurtured-active"
                    and int(observed.get("activeSlot", -1))
                    != expected_active_slot
                )
                if tries in {75, 50, 25} or (tries == 100 and stale_nurtured_slot):
                    invalidate = getattr(self.app, "_invalidate_home_cache", None)
                    if callable(invalidate):
                        invalidate(f"capture readiness retry for {capture_label}")
                    reset = getattr(mw, "reset", None)
                    if callable(reset):
                        try:
                            reset()
                        except Exception:
                            logger.debug(
                                "Anki Garden capture: Home retry refresh failed",
                                exc_info=True,
                            )
                    surface_controller = getattr(mw, state, None)
                    refresh_surface = getattr(
                        surface_controller,
                        "refresh",
                        None,
                    )
                    if callable(refresh_surface):
                        try:
                            refresh_surface()
                        except Exception:
                            logger.debug(
                                "Anki Garden capture: %s controller refresh failed",
                                state,
                                exc_info=True,
                            )
                QTimer.singleShot(
                    120,
                    lambda: self._wait_for_home_surface(
                        state,
                        capture_label,
                        on_ready,
                        tries=tries - 1,
                    ),
                )

        def resolved(result: Any) -> None:
            nonlocal settled
            if settled:
                return
            settled = True
            observation = dict(result) if isinstance(result, dict) else {
                "ready": bool(result),
                "reason": "legacy-boolean-result",
            }
            observation.update({
                "capture_label": capture_label,
                "surface": state,
                "expected_fixture_state": fixture_state,
            })
            self._active_home_dom_audit = observation
            if bool(observation.get("ready", False)):
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

        resolved_once = self._one_shot_async_callback(
            capture_label,
            resolved,
        )
        try:
            if callable(run_javascript):
                # Call the live QWebEnginePage directly. Anki's convenience
                # wrapper can retain a callback queue across repeated main-page
                # navigations; late in a full release run that queue may stop
                # delivering results even though the page remains painted.
                # The page API binds this audit to the current renderer frame.
                try:
                    run_javascript(script, 0, resolved_once)
                except TypeError:
                    run_javascript(script, resolved_once)
            else:
                evaluate(script, resolved_once)
            # A busy WebEngine compositor can legitimately take longer than
            # one frame budget to return runJavaScript results while native
            # capture windows are being moved and grabbed.  The old 750 ms
            # watchdog repeatedly invalidated callbacks that arrived shortly
            # afterward, so a healthy painted Home face could never settle.
            QTimer.singleShot(2500, callback_watchdog)
        except Exception:
            settled = True
            retry_or_fail()

    def _with_dashboard(
        self,
        on_ready: Callable[[], None],
        *,
        failure_label: str | None = None,
        on_error: Callable[[], None] | None = None,
    ) -> None:
        callback_label = str(
            failure_label
            or getattr(self, "_active_fixture_expected_label", "")
            or "dashboard-ready"
        )
        on_ready = self._one_shot_async_callback(
            callback_label,
            on_ready,
            on_error=on_error,
        )
        opened_at: float | None = None

        def prepare_dashboard() -> None:
            if opened_at is not None:
                elapsed_ms = max(0.0, (time.perf_counter() - opened_at) * 1000.0)
                self._performance_samples.setdefault("garden_open_ms", []).append(
                    round(elapsed_ms, 3)
                )
            dashboard = getattr(self.app, "dashboard", None)
            toast = getattr(dashboard, "toast_region", None)
            clear_toast = getattr(toast, "clear", None)
            if callable(clear_toast):
                clear_toast()
            self._move_to_capture_display(dashboard)
            on_ready()

        prepare_dashboard_once = self._one_shot_async_callback(
            callback_label,
            prepare_dashboard,
            on_error=on_error,
        )

        dashboard = getattr(self.app, "dashboard", None)
        try:
            if dashboard is not None and bool(dashboard.isVisible()):
                prepare_dashboard_once()
                return
        except Exception:
            pass
        opened_at = time.perf_counter()
        try:
            self.app.open_dashboard()
        except Exception as exc:
            self._failures.append({
                "label": callback_label,
                "reason": f"Garden Dashboard opener raised {type(exc).__name__}",
            })
            if on_error is not None:
                on_error()
            self._next_after(120)
            return
        self._wait_for_dashboard(
            prepare_dashboard_once,
            failure_label=callback_label,
            on_error=on_error,
        )

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
        preferred_side = "left" if expected_slot % 2 == 0 else "right"
        side_match = re.search(r'data-marker-side="([^"]+)"', marker)
        orientation_match = re.search(
            r'data-marker-orientation="([^"]+)"', marker
        )
        resolved_side = side_match.group(1) if side_match is not None else ""
        resolved_orientation = (
            orientation_match.group(1) if orientation_match is not None else ""
        )
        expected_orientation = (
            "spout-right" if resolved_side == "left" else "spout-left"
        )
        if active is None:
            issues.append("active nurtured plant was unavailable")
        if len(markers) != 1:
            issues.append(f"expected one rendered marker, found {len(markers)}")
        if f'data-marker-slot="{expected_slot}"' not in marker:
            issues.append(f"data-marker-slot did not equal {expected_slot}")
        if resolved_side not in {"left", "right"}:
            issues.append("data-marker-side was not left or right")
        if resolved_orientation != expected_orientation:
            issues.append("data-marker-orientation did not point inward")

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
            if resolved_side == "left" and marker_center_x >= target_ground[0]:
                issues.append("left marker crossed the nurtured plant center")
            if resolved_side == "right" and marker_center_x <= target_ground[0]:
                issues.append("right marker crossed the nurtured plant center")
        self._record_nurtured_marker_audit(
            label,
            {
                "renderer": "home-html",
                "expected_slot": expected_slot,
                "marker_count": len(markers),
                "preferred_side": preferred_side,
                "side": resolved_side,
                "orientation": resolved_orientation,
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
            preferred_side = "left" if expected_slot % 2 == 0 else "right"
            diagnostic = scene.nurtured_marker_geometry()
            if not isinstance(diagnostic, dict):
                issues.append(f"{type(scene).__name__} did not resolve a marker")
                continue
            resolved_side = str(diagnostic.get("side", ""))
            expected_orientation = (
                "spout-right" if resolved_side == "left" else "spout-left"
            )
            expected_asset = (
                "nurtured_marker_spout_right"
                if expected_orientation == "spout-right"
                else "nurtured_marker"
            )
            if int(diagnostic.get("slot_index", -1)) != expected_slot:
                issues.append(f"{type(scene).__name__} marker targeted the wrong plot")
            if resolved_side not in {"left", "right"}:
                issues.append(f"{type(scene).__name__} marker did not use a side lane")
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
                if resolved_side == "left" and marker_center_x >= target_layout.ground_anchor[0]:
                    issues.append(f"{type(scene).__name__} left marker crossed the plant center")
                if resolved_side == "right" and marker_center_x <= target_layout.ground_anchor[0]:
                    issues.append(f"{type(scene).__name__} right marker crossed the plant center")
            blockers = [layout.visible.expanded(4.0, 4.0) for layout in occupied_layouts]
            protected_reader = getattr(
                scene,
                "nurtured_marker_protected_regions",
                None,
            )
            protected_regions = (
                protected_reader()
                if callable(protected_reader)
                else tuple(
                    region for region in (
                        getattr(scene, "_card_connector_rect", None),
                        getattr(scene, "_status_rect", None),
                    )
                    if region is not None
                )
            )
            for qt_rect in protected_regions:
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
                "preferred_side": preferred_side,
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

    @staticmethod
    def _pixmap_contains_overlay(
        pixmap: Any,
        root: QWidget,
        overlay: QWidget,
    ) -> bool:
        """Confirm sampled overlay pixels survived the selected capture path."""

        try:
            if not overlay.isVisibleTo(root):
                return False
            overlay_pixmap = overlay.grab()
            if overlay_pixmap is None or overlay_pixmap.isNull():
                return False
            target_image = pixmap.toImage()
            overlay_image = overlay_pixmap.toImage()
            if target_image.isNull() or overlay_image.isNull():
                return False
            origin = overlay.mapTo(root, overlay.rect().topLeft())
            if (
                int(origin.x()) < 0
                or int(origin.y()) < 0
                or int(origin.x()) + int(overlay.width()) > int(root.width())
                or int(origin.y()) + int(overlay.height()) > int(root.height())
            ):
                return False
            scale_x = target_image.width() / max(1, int(root.width()))
            scale_y = target_image.height() / max(1, int(root.height()))
            matches = 0
            compared = 0
            for x_fraction in (0.08, 0.23, 0.41, 0.59, 0.77, 0.92):
                for y_fraction in (0.12, 0.31, 0.50, 0.69, 0.88):
                    source_x = min(
                        overlay_image.width() - 1,
                        max(0, round(x_fraction * (overlay_image.width() - 1))),
                    )
                    source_y = min(
                        overlay_image.height() - 1,
                        max(0, round(y_fraction * (overlay_image.height() - 1))),
                    )
                    source_color = overlay_image.pixelColor(source_x, source_y)
                    if source_color.alpha() < 192:
                        continue
                    target_x = round(
                        (int(origin.x()) + x_fraction * int(overlay.width()))
                        * scale_x
                    )
                    target_y = round(
                        (int(origin.y()) + y_fraction * int(overlay.height()))
                        * scale_y
                    )
                    if not (
                        0 <= target_x < target_image.width()
                        and 0 <= target_y < target_image.height()
                    ):
                        continue
                    target_color = target_image.pixelColor(target_x, target_y)
                    compared += 1
                    if max(
                        abs(source_color.red() - target_color.red()),
                        abs(source_color.green() - target_color.green()),
                        abs(source_color.blue() - target_color.blue()),
                    ) <= 48:
                        matches += 1
            if compared >= 8 and matches / compared >= 0.45:
                return True

            # Text, SVG strokes, and transparent icon buttons can have too few
            # opaque pixels at the coarse grid points above. Inspect their
            # actual painted pixels densely while keeping work bounded.
            dense_compared = 0
            dense_matches = 0
            dense_step = max(
                1,
                min(4, min(overlay_image.width(), overlay_image.height()) // 28),
            )
            for source_y in range(0, overlay_image.height(), dense_step):
                for source_x in range(0, overlay_image.width(), dense_step):
                    source_color = overlay_image.pixelColor(source_x, source_y)
                    if source_color.alpha() < 96:
                        continue
                    logical_x = (
                        source_x
                        * int(overlay.width())
                        / max(1, overlay_image.width())
                    )
                    logical_y = (
                        source_y
                        * int(overlay.height())
                        / max(1, overlay_image.height())
                    )
                    target_x = round(
                        (int(origin.x()) + logical_x) * scale_x
                    )
                    target_y = round(
                        (int(origin.y()) + logical_y) * scale_y
                    )
                    if not (
                        0 <= target_x < target_image.width()
                        and 0 <= target_y < target_image.height()
                    ):
                        continue
                    target_color = target_image.pixelColor(target_x, target_y)
                    dense_compared += 1
                    if max(
                        abs(source_color.red() - target_color.red()),
                        abs(source_color.green() - target_color.green()),
                        abs(source_color.blue() - target_color.blue()),
                    ) <= 64:
                        dense_matches += 1
            return bool(
                dense_compared >= 3
                and dense_matches / dense_compared >= 0.50
            )
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return False

    @staticmethod
    def _pixmap_icon_region_has_detail(
        pixmap: Any,
        root: QWidget,
        button: QAbstractButton,
    ) -> bool:
        """Prove a compact icon left visible contrast in the final PNG."""

        try:
            target = pixmap.toImage()
            if target.isNull() or not button.isVisibleTo(root):
                return False
            origin = button.mapTo(root, button.rect().topLeft())
            icon_size = button.iconSize()
            logical_width = max(1, int(icon_size.width()))
            logical_height = max(1, int(icon_size.height()))
            logical_left = int(origin.x()) + max(
                0,
                (int(button.width()) - logical_width) // 2,
            )
            logical_top = int(origin.y()) + max(
                0,
                (int(button.height()) - logical_height) // 2,
            )
            scale_x = target.width() / max(1, int(root.width()))
            scale_y = target.height() / max(1, int(root.height()))
            left = max(0, round(logical_left * scale_x))
            top = max(0, round(logical_top * scale_y))
            right = min(
                target.width(),
                round((logical_left + logical_width) * scale_x),
            )
            bottom = min(
                target.height(),
                round((logical_top + logical_height) * scale_y),
            )
            if right - left < 3 or bottom - top < 3:
                return False
            luminance: list[int] = []
            quantized: set[tuple[int, int, int]] = set()
            for y in range(top, bottom):
                for x in range(left, right):
                    color = target.pixelColor(x, y)
                    if color.alpha() < 64:
                        continue
                    red, green, blue = color.red(), color.green(), color.blue()
                    luminance.append((red * 3 + green * 6 + blue) // 10)
                    quantized.add((red // 8, green // 8, blue // 8))
            return bool(
                len(luminance) >= 12
                and len(quantized) >= 3
                and max(luminance) - min(luminance) >= 16
            )
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return False

    @staticmethod
    def _widget_bounds_evidence(
        widget: Any,
        container: Any,
    ) -> dict[str, Any]:
        """Return fail-closed logical bounds for one painted child."""

        if widget is None or container is None:
            return {
                "bounds": [],
                "container_size": [],
                "visible": False,
                "intersects": False,
                "contained": False,
            }
        try:
            origin = widget.mapTo(container, widget.rect().topLeft())
            bounds = [
                int(origin.x()),
                int(origin.y()),
                int(widget.width()),
                int(widget.height()),
            ]
            container_size = [int(container.width()), int(container.height())]
            left, top, width, height = bounds
            intersects = bool(
                width > 0
                and height > 0
                and left < container_size[0]
                and top < container_size[1]
                and left + width > 0
                and top + height > 0
            )
            contained = bool(
                intersects
                and left >= 0
                and top >= 0
                and left + width <= container_size[0]
                and top + height <= container_size[1]
            )
            return {
                "bounds": bounds,
                "container_size": container_size,
                "visible": bool(widget.isVisibleTo(container)),
                "intersects": intersects,
                "contained": contained,
            }
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return {
                "bounds": [],
                "container_size": [],
                "visible": False,
                "intersects": False,
                "contained": False,
            }

    @staticmethod
    def _rectangle_clearance(
        first: list[int],
        second: list[int],
    ) -> int:
        """Return the minimum axis clearance, or zero for overlapping rects."""

        if len(first) != 4 or len(second) != 4:
            return 0
        first_left, first_top, first_width, first_height = first
        second_left, second_top, second_width, second_height = second
        first_right = first_left + first_width
        first_bottom = first_top + first_height
        second_right = second_left + second_width
        second_bottom = second_top + second_height
        horizontal_overlap = first_left < second_right and second_left < first_right
        vertical_overlap = first_top < second_bottom and second_top < first_bottom
        if horizontal_overlap and vertical_overlap:
            return 0
        horizontal_gap = max(
            0,
            second_left - first_right,
            first_left - second_right,
        )
        vertical_gap = max(
            0,
            second_top - first_bottom,
            first_top - second_bottom,
        )
        if horizontal_overlap:
            return vertical_gap
        if vertical_overlap:
            return horizontal_gap
        return min(horizontal_gap, vertical_gap)

    def _reviewer_overlay_geometry_audit(
        self,
        label: str,
        toast: Any,
    ) -> dict[str, Any]:
        """Prove Reviewer feedback is bounded and clear of answer controls."""

        reviewer = getattr(mw, "reviewer", None)
        expected_parent = (
            getattr(reviewer, "web", None)
            or getattr(mw, "web", None)
        )
        parent = toast.parentWidget() if toast is not None else None
        evidence = self._widget_bounds_evidence(toast, parent)
        bounds = list(evidence.get("bounds", ()) or ())
        viewport_size = list(evidence.get("container_size", ()) or ())
        width = bounds[2] if len(bounds) == 4 else 0
        height = bounds[3] if len(bounds) == 4 else 0
        size_in_range = bool(
            340 <= width <= 370
            and 66 <= height <= 78
        )

        # Reviewer answer buttons live inside WebEngine and are not QWidgets.
        # Reserve the complete lower control band in logical viewport pixels;
        # any discovered Qt-owned reviewer controls are added as stricter bounds.
        control_rects: list[dict[str, Any]] = []
        if len(viewport_size) == 2:
            reserved_height = min(128, max(88, viewport_size[1] // 5))
            control_rects.append({
                "name": "reviewer-answer-and-toolbar-reserved-band",
                "bounds": [
                    0,
                    max(0, viewport_size[1] - reserved_height),
                    viewport_size[0],
                    reserved_height,
                ],
                "source": "reviewer-viewport-contract",
            })
        if parent is not None:
            for control in mw.findChildren(QAbstractButton):
                try:
                    copy = " ".join((
                        _displayed_button_text(control),
                        str(control.accessibleName() or ""),
                        str(control.objectName() or ""),
                    )).casefold()
                    if not any(
                        marker in copy
                        for marker in (
                            "show answer", "again", "hard", "good", "easy",
                            "edit", "more",
                        )
                    ):
                        continue
                    control_evidence = self._widget_bounds_evidence(control, parent)
                    if not (
                        control_evidence.get("visible", False)
                        and control_evidence.get("intersects", False)
                    ):
                        continue
                    control_rects.append({
                        "name": copy.strip(),
                        "bounds": list(control_evidence["bounds"]),
                        "source": "qt-control",
                    })
                except (AttributeError, RuntimeError, TypeError, ValueError):
                    continue
        clearances = [
            self._rectangle_clearance(bounds, list(control["bounds"]))
            for control in control_rects
        ]
        minimum_clearance = min(clearances) if clearances else 0
        parent_is_reviewer_webview = bool(
            parent is not None and parent is expected_parent
        )
        passed = bool(
            toast is not None
            and toast.isVisible()
            and parent_is_reviewer_webview
            and evidence.get("contained", False)
            and size_in_range
            and control_rects
            and minimum_clearance >= 16
        )
        return {
            "parent_is_reviewer_webview": parent_is_reviewer_webview,
            "overlay_bounds": bounds,
            "viewport_size": viewport_size,
            "viewport_contained": bool(evidence.get("contained", False)),
            "width": width,
            "height": height,
            "size_in_range": size_in_range,
            "control_rects": control_rects,
            "minimum_control_clearance": minimum_clearance,
            "passed": passed,
        }

    @staticmethod
    def _icon_has_visible_pixels(button: Any) -> bool:
        try:
            icon = button.icon()
            icon_size = button.iconSize()
            if icon is None or icon.isNull():
                return False
            pixmap = icon.pixmap(
                max(1, int(icon_size.width())),
                max(1, int(icon_size.height())),
            )
            if pixmap.isNull():
                return False
            image = pixmap.toImage()
            visible = 0
            for y in range(int(image.height())):
                for x in range(int(image.width())):
                    if image.pixelColor(x, y).alpha() >= 64:
                        visible += 1
                        if visible >= 3:
                            return True
            return False
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return False

    def _native_layout_telemetry_audit(
        self,
        root: QWidget,
        label: str,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Consume the shell-owned telemetry and bind it to release limits."""

        reader = getattr(root, "capture_layout_telemetry", None)
        if not callable(reader):
            return ({
                "applicable": False,
                "source": "",
                "issues": [],
                "passed": True,
            }, [])
        issue_codes: list[str] = []
        try:
            raw = dict(reader())
        except Exception as exc:
            issue = f"native-layout-telemetry-error:{type(exc).__name__}"
            return ({
                "applicable": True,
                "source": "DialogShell.capture_layout_telemetry",
                "issues": [issue],
                "passed": False,
            }, [{"kind": issue, "native_layout_telemetry": True}])

        client_width = max(1, int(root.contentsRect().width()))
        fill = raw.get("clientSurfaceFill")
        fill_number = (
            float(fill)
            if isinstance(fill, (int, float)) and not isinstance(fill, bool)
            else -1.0
        )
        client_gutter = (
            max(0, client_width - round(client_width * fill_number))
            if 0.0 <= fill_number <= 1.0 else -1
        )
        if not 0.0 <= fill_number <= 1.0:
            issue_codes.append("invalid-client-surface-fill")
        elif client_gutter > int(
            CAPTURE_LAYOUT_LIMITS["maximum_client_gutter_px"]
        ):
            issue_codes.append("client-surface-gutter")

        footer_gap = raw.get("contentToFooterGap")
        if footer_gap is not None and (
            type(footer_gap) is not int
            or footer_gap < 0
            or footer_gap > int(
                CAPTURE_LAYOUT_LIMITS["maximum_content_footer_gap_px"]
            )
        ):
            issue_codes.append("content-footer-gap")

        nursery_offset = raw.get("nurseryRootOffset")
        nursery_expected = expected_capture_window_family(label) == "NurseryDialog"
        if nursery_expected and (
            type(nursery_offset) is not int
            or nursery_offset < 0
            or nursery_offset > int(
                CAPTURE_LAYOUT_LIMITS["maximum_nursery_root_offset_px"]
            )
        ):
            issue_codes.append("nursery-root-offset")
        elif not nursery_expected and nursery_offset is not None and (
            type(nursery_offset) is not int or nursery_offset < 0
        ):
            issue_codes.append("invalid-nursery-root-offset")

        action_ratio = raw.get("maximumActionWidthRatio")
        action_ratio_number = (
            float(action_ratio)
            if isinstance(action_ratio, (int, float))
            and not isinstance(action_ratio, bool)
            else -1.0
        )
        if not 0.0 <= action_ratio_number <= 1.0:
            issue_codes.append("invalid-action-width-ratio")
        elif action_ratio_number > float(
            CAPTURE_LAYOUT_LIMITS["maximum_action_width_ratio"]
        ):
            issue_codes.append("stretched-action")

        minimum_text = raw.get("minimumRenderedTextSize")
        minimum_text_number = (
            float(minimum_text)
            if isinstance(minimum_text, (int, float))
            and not isinstance(minimum_text, bool)
            else -1.0
        )
        if minimum_text_number < float(
            CAPTURE_LAYOUT_LIMITS["minimum_rendered_text_px"]
        ):
            issue_codes.append("rendered-text-below-floor")
        if raw.get("elisionWithoutTooltipCount") != 0:
            issue_codes.append("elision-without-tooltip")

        scrollbars = raw.get("scrollbars")
        if not isinstance(scrollbars, list):
            scrollbars = []
            issue_codes.append("invalid-scrollbar-telemetry")
        overflow_owner_count = raw.get("overflowOwnerCount")
        if (
            type(overflow_owner_count) is not int
            or overflow_owner_count < 0
            or overflow_owner_count > int(
                CAPTURE_LAYOUT_LIMITS["maximum_overflow_owner_count"]
            )
        ):
            issue_codes.append("overflow-owner-count")
        elif scrollbars and overflow_owner_count != 1:
            issue_codes.append("missing-overflow-owner")
        owner_rows = 0
        for row in scrollbars:
            if not isinstance(row, dict):
                issue_codes.append("invalid-scrollbar-record")
                continue
            minimum = row.get("minimum")
            maximum = row.get("maximum")
            value = row.get("value")
            visible = row.get("visible")
            owner = row.get("overflowOwner")
            if (
                type(minimum) is not int
                or type(maximum) is not int
                or type(value) is not int
                or type(visible) is not bool
                or type(owner) is not bool
                or maximum < minimum
                or not minimum <= value <= maximum
            ):
                issue_codes.append("invalid-scrollbar-record")
                continue
            owner_rows += int(owner)
            if owner and visible is not (maximum > minimum):
                issue_codes.append("scrollbar-range-visibility")
            if not owner and visible:
                issue_codes.append("non-owner-scrollbar-visible")
        if type(overflow_owner_count) is int and owner_rows != overflow_owner_count:
            issue_codes.append("overflow-owner-record-mismatch")

        buttons: list[dict[str, Any]] = []
        for button in root.findChildren(QPushButton):
            try:
                if (
                    button.window() is not root
                    or not button.isVisibleTo(root)
                    or bool(button.property("catalogCard"))
                    or bool(button.property("environmentTile"))
                ):
                    continue
                size_name = str(button.property("buttonSize") or "")
                height = int(button.height())
                text = _displayed_button_text(button).strip()
                measured_text_size = button.property("renderedTextSizePx")
                if (
                    isinstance(measured_text_size, (int, float))
                    and not isinstance(measured_text_size, bool)
                ):
                    text_size = round(float(measured_text_size), 2)
                else:
                    font = button.font()
                    pixel_size = int(font.pixelSize())
                    if pixel_size > 0:
                        text_size = float(pixel_size)
                    else:
                        point_size = float(font.pointSizeF())
                        screen = root.screen()
                        dpi = (
                            float(screen.logicalDotsPerInchY())
                            if screen is not None else 96.0
                        )
                        text_size = round(point_size * dpi / 72.0, 2)
                expected_height = CAPTURE_BUTTON_HEIGHTS.get(size_name)
                passed = bool(
                    expected_height is not None
                    and height == expected_height
                    and (
                        not text
                        or text_size >= float(
                            CAPTURE_LAYOUT_LIMITS["minimum_rendered_text_px"]
                        )
                    )
                    and (
                        size_name != "icon"
                        or int(button.width()) == expected_height
                    )
                )
                buttons.append({
                    "text": text,
                    "buttonSize": size_name,
                    "height": height,
                    "width": int(button.width()),
                    "expectedHeight": expected_height,
                    "renderedTextSize": text_size,
                    "passed": passed,
                })
                if not passed:
                    issue_codes.append("button-geometry-or-text-size")
            except (AttributeError, RuntimeError, TypeError, ValueError):
                issue_codes.append("button-telemetry-error")

        tabular_widgets: list[dict[str, Any]] = []
        for candidate in root.findChildren(QWidget):
            try:
                if candidate.window() is not root or not candidate.isVisibleTo(root):
                    continue
                text_getter = getattr(candidate, "text", None)
                text = str(text_getter()).strip() if callable(text_getter) else ""
                if not text or not any(character.isdigit() for character in text):
                    continue
                if bool(candidate.property("tabularNumerals")):
                    tabular_widgets.append({
                        "widget": type(candidate).__name__,
                        "objectName": str(candidate.objectName() or ""),
                        "text": text[:120],
                    })
            except (AttributeError, RuntimeError, TypeError, ValueError):
                continue
        if label in TABULAR_NUMERAL_CAPTURE_LABELS and not tabular_widgets:
            issue_codes.append("missing-tabular-numeral-evidence")

        unique_issues = list(dict.fromkeys(issue_codes))
        audit = {
            "applicable": True,
            "source": "DialogShell.capture_layout_telemetry",
            **raw,
            "clientWidth": client_width,
            "clientGutterPx": client_gutter,
            "buttonRecords": buttons,
            "tabularNumeralWidgets": tabular_widgets,
            "tabularNumeralWidgetCount": len(tabular_widgets),
            "tabularNumeralsRequired": label in TABULAR_NUMERAL_CAPTURE_LABELS,
            "limits": dict(CAPTURE_LAYOUT_LIMITS),
            "buttonHeights": dict(CAPTURE_BUTTON_HEIGHTS),
            "issues": unique_issues,
            "passed": not unique_issues,
        }
        warnings = [
            {"kind": issue, "native_layout_telemetry": True}
            for issue in unique_issues
        ]
        return audit, warnings

    def _visual_contract_audit(
        self,
        root: QWidget,
        label: str,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Measure release geometry that warning lists alone cannot prove."""

        if root is mw:
            return ({
                "applicable": False,
                "controls": [],
                "close_icons": [],
                "primary_action_count": 0,
                "visible_horizontal_scrollbars": [],
                "largest_unexplained_gap": 0,
                "screen_contained": True,
                "popover": {"applicable": False, "passed": True},
                "issues": [],
                "passed": True,
            }, [])

        issue_codes: list[str] = []
        controls: list[dict[str, Any]] = []
        close_icons: list[dict[str, Any]] = []
        primary_actions: list[str] = []
        primary_scope_widgets: list[QWidget] = []
        primary_action_groups: list[dict[str, Any]] = []
        footer_actions: list[dict[str, Any]] = []
        pinned_footer = getattr(root, "_pinned_footer", None)

        def primary_scope(button: QAbstractButton) -> QWidget:
            current = button.parentWidget()
            while current is not None and current is not root:
                if any(
                    bool(current.property(marker))
                    for marker in (
                        "decisionGroup",
                        "actionFooter",
                        "dialogFooter",
                        "toastRegion",
                        "emptyState",
                        "nurseryCatalogCard",
                        "catalogCard",
                        "environmentTile",
                        "sectionCard",
                    )
                ):
                    return current
                current = current.parentWidget()
            return root

        def record_primary(button: QAbstractButton, action_name: str) -> None:
            scope = primary_scope(button)
            index = next(
                (
                    item_index
                    for item_index, candidate in enumerate(primary_scope_widgets)
                    if candidate is scope
                ),
                -1,
            )
            if index < 0:
                primary_scope_widgets.append(scope)
                marker = next(
                    (
                        name
                        for name in (
                            "decisionGroup",
                            "actionFooter",
                            "dialogFooter",
                            "toastRegion",
                            "emptyState",
                            "nurseryCatalogCard",
                            "catalogCard",
                            "environmentTile",
                            "sectionCard",
                        )
                        if bool(scope.property(name))
                    ),
                    "window",
                )
                primary_action_groups.append({
                    "scope": (
                        str(scope.objectName())
                        or f"{marker}-{len(primary_scope_widgets)}"
                    ),
                    "actions": [],
                })
                index = len(primary_action_groups) - 1
            primary_action_groups[index]["actions"].append(action_name)

        for button in root.findChildren(QAbstractButton):
            if button.window() is not root or not button.isVisibleTo(root):
                continue
            if (
                isinstance(button.parentWidget(), QLineEdit)
                and not str(button.property("gardenComponent") or "")
                and not button.property("iconButton")
            ):
                # Qt owns the embedded clear affordance and sizes it to the
                # line edit's contents rect. It is not an app icon control.
                continue
            painted = self._widget_bounds_evidence(button, root)
            if not painted.get("intersects", False):
                continue
            text = _displayed_button_text(button).strip()
            component = str(button.property("gardenComponent") or "")
            composite_button = bool(
                button.property("catalogCard")
                or button.property("environmentTile")
            )
            icon_only = bool(
                component == "icon-button"
                or button.property("iconButton")
                or (not text and not button.icon().isNull())
            ) and not composite_button
            visual_size = int(
                button.property("visualControlSize")
                or max(int(button.width()), int(button.height()))
            )
            icon_size = [
                int(button.iconSize().width()),
                int(button.iconSize().height()),
            ]
            standard_button = bool(
                component == "button"
                or str(button.property("variant") or "")
            )
            icon_width = (
                max(0, int(button.iconSize().width())) + 6
                if not button.icon().isNull()
                else 0
            )
            text_width = int(button.fontMetrics().horizontalAdvance(text))
            horizontal_padding = (
                20
                if button.property("compactRowAction")
                else 16
                if button.property("disclosureRow")
                else 28
            )
            available_text_width = max(
                0,
                int(button.contentsRect().width())
                - horizontal_padding
                - icon_width,
            )
            text_fit_clearance = max(
                0,
                int(button.property("textFitClearance") or 0),
            )
            text_fit_passed = bool(
                not text
                or text_width + text_fit_clearance <= available_text_width
            )
            footer_action = bool(
                pinned_footer is not None
                and (
                    button is pinned_footer
                    or pinned_footer.isAncestorOf(button)
                )
            )
            size_passed = bool(
                28 <= visual_size <= 30
                and 14 <= icon_size[0] <= 16
                and 14 <= icon_size[1] <= 16
                if icon_only else
                int(button.height()) <= 40
                if standard_button else
                True
            )
            controls.append({
                "text": text,
                "accessible_name": str(button.accessibleName() or ""),
                "bounds": list(painted.get("bounds", ()) or ()),
                "icon_only": icon_only,
                "visual_size": visual_size,
                "icon_size": icon_size,
                "standard_button": standard_button,
                "size_passed": size_passed,
                "contained": bool(painted.get("contained", False)),
                "footer_action": footer_action,
                "text_width": text_width,
                "horizontal_padding": horizontal_padding,
                "text_fit_clearance": text_fit_clearance,
                "available_text_width": available_text_width,
                "text_fit_passed": text_fit_passed,
            })
            if not size_passed:
                issue_codes.append(
                    "icon-control-size" if icon_only else "standard-button-height"
                )
            if not text_fit_passed:
                issue_codes.append("action-label-overflow")
            if footer_action:
                footer_actions.append(controls[-1])
                if not painted.get("contained", False):
                    issue_codes.append("footer-action-outside-dialog")
            if str(button.property("variant") or "") == "primary":
                action_name = (
                    text or str(button.accessibleName() or type(button).__name__)
                )
                primary_actions.append(action_name)
                record_primary(button, action_name)
            accessible_name = str(button.accessibleName() or "").casefold()
            if icon_only and "close" in accessible_name:
                glyph_present = self._icon_has_visible_pixels(button)
                close_passed = bool(size_passed and glyph_present)
                close_icons.append({
                    "accessible_name": str(button.accessibleName() or ""),
                    "bounds": list(painted.get("bounds", ()) or ()),
                    "glyph_pixels_present": glyph_present,
                    "passed": close_passed,
                })
                if not close_passed:
                    issue_codes.append("close-icon-glyph-or-size")

        requires_inline_close = bool(
            expected_capture_window_family(label) != "GardenDashboard"
        )
        if requires_inline_close and not close_icons:
            issue_codes.append("missing-inline-close-icon")

        for group in primary_action_groups:
            group["count"] = len(group["actions"])
            group["passed"] = group["count"] <= 1
        max_primary_actions_per_group = max(
            (int(group["count"]) for group in primary_action_groups),
            default=0,
        )
        if max_primary_actions_per_group > 1:
            issue_codes.append("multiple-filled-primary-actions")

        horizontal_scrollbars: list[str] = []
        for scroll in root.findChildren(QAbstractScrollArea):
            try:
                bar = scroll.horizontalScrollBar()
                if (
                    scroll.window() is root
                    and scroll.isVisibleTo(root)
                    and bar is not None
                    and bar.maximum() > bar.minimum()
                    and bar.isVisibleTo(root)
                ):
                    horizontal_scrollbars.append(
                        str(scroll.accessibleName() or scroll.objectName() or type(scroll).__name__)
                    )
            except (AttributeError, RuntimeError):
                continue
        if horizontal_scrollbars:
            issue_codes.append("visible-horizontal-scrollbar")

        direct_children: list[list[int]] = []
        for child in root.findChildren(QWidget):
            try:
                if child.parentWidget() is not root or not child.isVisibleTo(root):
                    continue
                evidence = self._widget_bounds_evidence(child, root)
                if evidence.get("intersects", False):
                    direct_children.append(list(evidence["bounds"]))
            except (AttributeError, RuntimeError, TypeError, ValueError):
                continue
        direct_children.sort(key=lambda bounds: (bounds[1], bounds[0]))
        vertical_gaps = [
            max(0, following[1] - (current[1] + current[3]))
            for current, following in zip(direct_children, direct_children[1:])
            if current[0] < following[0] + following[2]
            and following[0] < current[0] + current[2]
        ]
        largest_gap = max(vertical_gaps, default=0)
        if largest_gap > max(64, round(int(root.height()) * 0.20)):
            issue_codes.append("unexplained-large-vertical-gap")

        screen_contained = True
        try:
            screen = root.screen()
            available = screen.availableGeometry() if screen is not None else None
            frame = root.frameGeometry()
            screen_contained = bool(
                available is not None and available.contains(frame)
            )
        except (AttributeError, RuntimeError, TypeError):
            screen_contained = False
        if not screen_contained:
            issue_codes.append("window-outside-available-screen")

        popover: dict[str, Any] = {"applicable": False, "passed": True}
        if label.startswith("popover-plot-"):
            scene = getattr(root, "scene", None)
            card = getattr(root, "plant_card", None)
            evidence = self._widget_bounds_evidence(card, scene)
            page_scroll = getattr(root, "dashboard_scroll", None)
            page_scroll_value = (
                int(page_scroll.verticalScrollBar().value())
                if page_scroll is not None else -1
            )
            popover = {
                "applicable": True,
                "bounds": list(evidence.get("bounds", ()) or ()),
                "scene_size": list(evidence.get("container_size", ()) or ()),
                "contained_in_scene": bool(evidence.get("contained", False)),
                "page_scroll_value": page_scroll_value,
                "passed": bool(
                    evidence.get("contained", False) and page_scroll_value == 0
                ),
            }
            if not popover["passed"]:
                issue_codes.append("popover-outside-scene-or-page-scrolled")

        unique_issues = list(dict.fromkeys(issue_codes))
        audit = {
            "applicable": True,
            "controls": controls,
            "control_sizes_passed": not any(
                issue in unique_issues
                for issue in ("icon-control-size", "standard-button-height")
            ),
            "close_icons": close_icons,
            "requires_inline_close": requires_inline_close,
            "close_icons_passed": bool(
                (close_icons or not requires_inline_close)
                and all(bool(item.get("passed", False)) for item in close_icons)
            ),
            "primary_actions": primary_actions,
            "primary_action_count": len(primary_actions),
            "primary_action_groups": primary_action_groups,
            "max_primary_actions_per_group": max_primary_actions_per_group,
            "footer_actions": footer_actions,
            "footer_actions_contained": all(
                bool(item.get("contained", False))
                for item in footer_actions
            ),
            "action_text_fits": all(
                bool(item.get("text_fit_passed", False))
                for item in controls
            ),
            "visible_horizontal_scrollbars": horizontal_scrollbars,
            "largest_unexplained_gap": largest_gap,
            "screen_contained": screen_contained,
            "popover": popover,
            "issues": unique_issues,
            "passed": not unique_issues,
        }
        warnings = [
            {"kind": issue, "visual_contract": True}
            for issue in unique_issues
        ]
        return audit, warnings

    def _audit_capture_pixel_contracts(
        self,
        label: str,
        root: QWidget,
        pixmap: Any,
        visual_contract: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Bind measured controls and high-risk fixture widgets to PNG pixels."""

        warnings: list[dict[str, Any]] = []
        annotation = self._capture_annotations.setdefault(label, {})
        if visual_contract.get("applicable") is True:
            close_buttons = [
                button
                for button in root.findChildren(QAbstractButton)
                if button.window() is root
                and button.isVisibleTo(root)
                and "close" in str(button.accessibleName() or "").casefold()
            ]
            close_rows = list(visual_contract.get("close_icons", ()) or ())
            for row in close_rows:
                accessible_name = str(row.get("accessible_name", ""))
                button = next(
                    (
                        candidate for candidate in close_buttons
                        if str(candidate.accessibleName() or "") == accessible_name
                    ),
                    None,
                )
                pixels_present = bool(
                    button is not None
                    and (
                        self._pixmap_contains_overlay(pixmap, root, button)
                        or self._pixmap_icon_region_has_detail(
                            pixmap,
                            root,
                            button,
                        )
                    )
                )
                row["capture_pixels_present"] = pixels_present
                row["passed"] = bool(row.get("passed", False) and pixels_present)
            requires_inline_close = bool(
                visual_contract.get("requires_inline_close", True)
            )
            close_pixels_passed = bool(
                (close_rows or not requires_inline_close)
                and all(
                    row.get("capture_pixels_present") is True
                    for row in close_rows
                )
            )
            visual_contract["close_icons_passed"] = bool(
                visual_contract.get("close_icons_passed", False)
                and close_pixels_passed
            )
            if not close_pixels_passed:
                issues = list(visual_contract.get("issues", ()) or ())
                issues.append("close-icon-absent-from-captured-pixels")
                visual_contract["issues"] = list(dict.fromkeys(issues))
                visual_contract["passed"] = False
                warnings.append({
                    "kind": "close-icon-absent-from-captured-pixels",
                    "visual_contract": True,
                })
            annotation["visual_contract"] = dict(visual_contract)
            annotation["passed"] = bool(
                annotation.get("passed", True)
                and visual_contract.get("passed", False)
            )

        required_keys = RENDERED_PIXEL_EVIDENCE_KEYS.get(label, ())
        if not required_keys:
            return warnings
        candidates = (root, *tuple(root.findChildren(QWidget)))
        results: list[dict[str, Any]] = []
        for key in required_keys:
            target = next(
                (
                    candidate for candidate in candidates
                    if str(candidate.property("captureEvidenceKey") or "") == key
                    and (
                        candidate is root
                        or candidate.isVisibleTo(root)
                    )
                ),
                None,
            )
            bounds = self._widget_bounds_evidence(target, root)
            pixels_present = bool(
                target is not None
                and bounds.get("contained", False)
                and self._pixmap_contains_overlay(pixmap, root, target)
            )
            results.append({
                "key": key,
                "bounds": list(bounds.get("bounds", ()) or ()),
                "visible": bool(bounds.get("visible", False)),
                "contained": bool(bounds.get("contained", False)),
                "capture_pixels_present": pixels_present,
                "passed": bool(
                    bounds.get("visible", False)
                    and bounds.get("contained", False)
                    and pixels_present
                ),
            })
        rendered = {
            "required_keys": list(required_keys),
            "results": results,
            "passed": bool(
                [row["key"] for row in results] == list(required_keys)
                and all(row["passed"] for row in results)
            ),
        }
        annotation["rendered_pixel_evidence"] = rendered
        annotation["passed"] = bool(
            annotation.get("passed", True) and rendered["passed"]
        )
        if not rendered["passed"]:
            warnings.append({
                "kind": "required-rendered-pixels-absent",
                "visual_contract": True,
                "required_keys": list(required_keys),
            })
        return warnings

    def _capture_home_pixmap(
        self,
        widget: QWidget,
        *,
        require_garden_identity: bool = True,
        required_overlays: tuple[QWidget, ...] = (),
    ) -> tuple[Any | None, str, bool]:
        """Capture the real Anki main window without trusting an obscured desktop."""

        foreground_confirmed = bool(self._activate_current_process_window(widget))
        if not foreground_confirmed:
            logger.warning(
                "Anki Garden capture: exact Anki Home window did not become "
                "foreground; limiting capture to the app-owned Qt surface"
            )

        def capture_candidates(
            *,
            allow_screen_capture: bool,
        ) -> list[tuple[str, Any, dict[str, Any]]]:
            candidates: list[tuple[str, Any]] = []
            screen = None
            if allow_screen_capture:
                handle = widget.windowHandle()
                screen = handle.screen() if handle is not None else None
                screen = screen or QGuiApplication.primaryScreen()
                origin = widget.mapToGlobal(widget.rect().topLeft())
                screen_geometry = screen.geometry() if screen is not None else None
            else:
                origin = None
                screen_geometry = None
            if (
                allow_screen_capture
                and screen is not None
                and screen_geometry is not None
                and origin is not None
            ):
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
                method = "qt-widget"
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
                        for overlay in required_overlays:
                            if overlay is None or not overlay.isVisibleTo(widget):
                                continue
                            overlay_pixmap = overlay.grab()
                            if overlay_pixmap is None or overlay_pixmap.isNull():
                                continue
                            painter.drawPixmap(
                                overlay.mapTo(widget, overlay.rect().topLeft()),
                                overlay_pixmap,
                            )
                        painter.end()
                        method = "qt-shell-with-webview"
                if shell_pixmap is not None:
                    if required_overlays:
                        method += "-with-overlays"
                    candidates.append((method, shell_pixmap))
            except Exception:
                logger.debug(
                    "Anki Garden capture: Qt Home fallback capture failed",
                    exc_info=True,
                )

            if allow_screen_capture and screen is not None:
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
                metrics["required_overlays_present"] = all(
                    self._pixmap_contains_overlay(candidate, widget, overlay)
                    for overlay in required_overlays
                )
                viable.append((method, candidate, metrics))
            return viable

        # WebEngine can briefly expose an app-owned but unpainted surface after
        # a Deck Browser/Overview transition, especially when the window moves
        # between mixed-DPI displays. Poll the semantic pixels for a bounded
        # interval instead of treating the first 180 ms as authoritative.
        attempt_count = max(
            3,
            int(getattr(self, "_home_capture_ready_attempts", 20)),
        )
        for capture_attempt in range(attempt_count):
            if capture_attempt:
                foreground_confirmed = bool(
                    self._activate_current_process_window(widget)
                )
            viable = capture_candidates(
                allow_screen_capture=foreground_confirmed,
            )
            ready = [
                row for row in viable
                if bool(row[2]["required_overlays_present"])
                and (
                    row[2]["passed"] or (
                        not require_garden_identity
                        and row[2]["generic_content_passed"]
                    )
                )
            ]
            if ready:
                method, pixmap, _metrics = max(
                    ready,
                    key=(
                        lambda row: (
                            float(row[2]["brand_sample_ratio"]),
                            float(row[2]["dark_shell_sample_ratio"]),
                        )
                    ) if require_garden_identity else (
                        lambda row: (
                            float(row[2]["saturated_sample_ratio"]),
                            int(row[2]["unique_sampled_colors"]),
                        )
                    ),
                )
                self._last_required_overlay_pixels_present = bool(
                    _metrics["required_overlays_present"]
                )
                return pixmap, method, foreground_confirmed

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
                    "required_overlays_present": bool(
                        metrics["required_overlays_present"]
                    ),
                }
                for method, candidate, metrics in viable
            ]
            logger.warning(
                "Anki Garden capture: main-window candidates on %s display were not "
                "ready: %s",
                self._capture_display,
                diagnostic,
            )
            if self._capture_display == "secondary" and not self._capture_force_primary:
                # Never relocate a live WebEngine window inside this synchronous
                # polling callback. Keep the current face fail-closed and pin
                # later async captures to primary if the secondary is unusable.
                self._capture_force_primary = True
            if capture_attempt < attempt_count - 1:
                app = QApplication.instance()
                if app is not None:
                    app.processEvents()
                for render_target in (getattr(mw, "web", None), widget):
                    update = getattr(render_target, "update", None)
                    if callable(update):
                        update()
                time.sleep(0.12)
                if app is not None:
                    app.processEvents()
        failure_kind = (
            "semantic-window-not-ready"
            if foreground_confirmed else
            "app-owned-home-surface-not-ready"
        )
        self._last_required_overlay_pixels_present = not bool(required_overlays)
        return None, failure_kind, foreground_confirmed

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

    @staticmethod
    def _onboarding_copy_geometry(dashboard: Any) -> dict[str, Any]:
        panel = getattr(dashboard, "onboarding_panel", None)
        ordinary_message = getattr(dashboard, "onboarding_message", None)
        error_banner = getattr(dashboard, "onboarding_error_banner", None)
        message = ordinary_message
        if error_banner is not None and error_banner.isVisible():
            message = getattr(error_banner, "message", error_banner)
        actions = [
            getattr(dashboard, "onboarding_action", None),
            getattr(dashboard, "dismiss_onboarding", None),
        ]
        action_tops: list[int] = []
        message_bounds: list[int] = []
        panel_size: list[int] = []
        if panel is not None and message is not None:
            origin = message.mapTo(panel, message.rect().topLeft())
            message_bounds = [
                int(origin.x()),
                int(origin.y()),
                int(message.width()),
                int(message.height()),
            ]
            panel_size = [int(panel.width()), int(panel.height())]
            for action in actions:
                if action is None or not action.isVisible():
                    continue
                action_origin = action.mapTo(
                    panel,
                    action.rect().topLeft(),
                )
                action_tops.append(int(action_origin.y()))
        message_bottom = (
            message_bounds[1] + message_bounds[3]
            if len(message_bounds) == 4 else -1
        )
        required_message_height = -1
        message_height_sufficient = False
        if message is not None and int(message.width()) > 0:
            wrapped_height = int(message.heightForWidth(int(message.width())))
            required_message_height = (
                wrapped_height
                if wrapped_height > 0 else int(message.sizeHint().height())
            )
            message_height_sufficient = bool(
                int(message.height()) >= required_message_height
            )
        passed = bool(
            panel is not None
            and message is not None
            and not message.isHidden()
            and len(action_tops) == 2
            and message_bottom >= 0
            and message_bottom <= min(action_tops)
            and message_bottom <= int(panel.height())
            and message_height_sufficient
        )
        return {
            "passed": passed,
            "message_bounds": message_bounds,
            "required_message_height": required_message_height,
            "message_height_sufficient": message_height_sufficient,
            "action_tops": action_tops,
            "panel_size": panel_size,
        }

    def _capture_fixture_postcondition(
        self,
        label: str,
        widget: Any,
        *,
        expected_fixture_label: str,
        actual_family: str,
        geometry_request: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Validate the exact live state represented by a manifest fixture."""

        expectation = expected_capture_state_profile(label)
        facts: dict[str, Any] = {}
        issues: list[str] = []

        def require(name: str, condition: bool, value: Any) -> None:
            facts[name] = value
            if not bool(condition):
                issues.append(name)

        def scroll_child_bounds(
            child: Any,
            scroll: Any,
        ) -> tuple[list[int], bool]:
            if child is None or scroll is None:
                return [], False
            viewport = scroll.viewport()
            origin = child.mapTo(viewport, child.rect().topLeft())
            bounds = [
                int(origin.x()),
                int(origin.y()),
                int(child.width()),
                int(child.height()),
            ]
            return bounds, bool(
                bounds[0] >= 0
                and bounds[1] >= 0
                and bounds[0] + bounds[2] <= int(viewport.width())
                and bounds[1] + bounds[3] <= int(viewport.height())
            )

        require(
            "ordered_fixture_label",
            str(expected_fixture_label) == label,
            str(expected_fixture_label),
        )
        require(
            "state_profile_declared",
            bool(expectation),
            str(expectation.get("profile_id", "")),
        )
        require(
            "window_family",
            str(expectation.get("window_family", "")) == actual_family,
            actual_family,
        )
        if not expectation:
            return {
                "profile_id": "",
                "kind": "unmapped",
                "facts": facts,
                "issues": issues,
                "passed": False,
            }

        kind = str(expectation.get("kind", ""))
        state_name = str(expectation.get("state", label))
        garden_state = getattr(getattr(self.app, "storage", None), "state", None)
        plants = list(getattr(garden_state, "plants", ()) or ())
        active_id = str(getattr(garden_state, "active_plant_id", "") or "")
        active_plant = next(
            (
                plant for plant in plants
                if str(getattr(plant, "plant_id", "") or "") == active_id
            ),
            None,
        )
        annotation = dict(self._capture_annotations.get(label, {}) or {})

        if state_name == "starter-selection-confirmation":
            progress = getattr(garden_state, "onboarding", None)
            step = getattr(progress, "step", "")
            require(
                "persisted_confirmation_step",
                str(getattr(step, "value", step)) == "confirmation"
                and bool(getattr(progress, "pending_species", "")),
                str(getattr(step, "value", step)),
            )

        if state_name in {
            "starter-placement",
            "starter-completion",
            "onboarding-persistence-error",
            "move-persistence-error",
        }:
            dashboard = getattr(self.app, "dashboard", None)
            progress = getattr(garden_state, "onboarding", None)
            step = getattr(progress, "step", "")
            step_value = str(getattr(step, "value", step))
            if state_name == "starter-placement":
                require("onboarding_step", step_value == "placement", step_value)
                require(
                    "starter_not_created_before_placement",
                    not plants and not bool(getattr(garden_state, "starter_selection_complete", False)),
                    len(plants),
                )
                require(
                    "starter_placement_mode",
                    bool(
                        dashboard is not None
                        and getattr(dashboard, "_starter_placement_active", False)
                        and dashboard.scene._interaction.placing
                    ),
                    bool(dashboard is not None and dashboard.scene._interaction.placing),
                )
            elif state_name == "starter-completion":
                require("onboarding_step", step_value == "completion", step_value)
                require(
                    "completion_has_nurtured_starter",
                    bool(active_id and plants and active_id == str(getattr(progress, "starter_plant_id", "") or "")),
                    active_id,
                )
                require(
                    "completion_not_done_before_destination",
                    int(getattr(garden_state, "garden_setup_version", -1)) == 0,
                    int(getattr(garden_state, "garden_setup_version", -1)),
                )
            else:
                if state_name == "onboarding-persistence-error":
                    require(
                        "onboarding_step",
                        step_value == "introduction",
                        step_value,
                    )
                require(
                    "rollback_fixture_audit",
                    bool(annotation.get("passed", False)),
                    annotation,
                )
            if state_name in {
                "starter-completion",
                "onboarding-persistence-error",
            }:
                onboarding_geometry = self._onboarding_copy_geometry(dashboard)
                require(
                    "onboarding_copy_clear_of_actions",
                    bool(onboarding_geometry.get("passed", False)),
                    onboarding_geometry,
                )

        if state_name == "keyboard-focus-state":
            dashboard = getattr(self.app, "dashboard", None)
            capture_config = getattr(dashboard, "config", None)
            config_value = getattr(capture_config, "value", None)
            reduced_motion = (
                bool(config_value("reduced_motion", False))
                if callable(config_value) else None
            )
            require(
                "reduced_motion_baseline_restored",
                reduced_motion is False,
                reduced_motion,
            )

        if (
            state_name in {
                "all-six-beds-occupied",
                "plant-at-every-stage",
                "fully-grown-plant-without-fertilize",
                "move-occupied-empty-destinations",
                "fertilizer-expiring-under-minute",
                "fertilizer-replacement-confirmation",
                "collection-no-filter-matches",
                "achievement-completed",
                "clear-recall-canonical-projection",
                "streak-at-risk",
                "streak-missed-day",
                "streak-achievement-earned-next",
                "nursery-item-owned",
                "nursery-item-locked",
                "nursery-purchase-success",
                "nursery-final-row-above-footer",
                "missing-artwork-graphical-fallback",
                "settings-unsaved-changes",
                "settings-validation-error",
                "diagnostics-expanded",
                "production-build-controls-absent",
                "reduced-motion-enabled",
                "keyboard-focus-state",
            }
            or state_name.startswith("popover-plot-")
            or state_name.startswith("watering-can-")
        ):
            development_species = [
                str(getattr(plant, "species", "") or "") for plant in plants
            ]
            development_ids = [
                str(getattr(plant, "plant_id", "") or "") for plant in plants
            ]
            development_names = [
                str(getattr(plant, "name", "") or "") for plant in plants
            ]
            expected_species = list(
                DEVELOPMENT_STRESS_SPECIES_ORDER[:6]
                if state_name == "nursery-item-owned" else
                DEVELOPMENT_STRESS_SPECIES_ORDER
            )
            expected_ids = [f"dev_{species}" for species in expected_species]
            expected_names = [
                f"{species.replace('_', ' ').title()} Plant"[:40]
                for species in expected_species
            ]
            require(
                "canonical_development_species_order",
                development_species == expected_species,
                development_species,
            )
            require(
                "canonical_development_plant_ids",
                development_ids == expected_ids,
                development_ids,
            )
            require(
                "canonical_development_generated_names",
                development_names == expected_names
                and all(
                    not bool(getattr(plant, "name_customized", False))
                    for plant in plants
                ),
                development_names,
            )

        if label.startswith("watering-can-"):
            planted = sorted(
                (
                    plant for plant in plants
                    if getattr(plant, "slot_index", None) is not None
                ),
                key=lambda plant: int(getattr(plant, "slot_index", -1)),
            )[:6]
            canonical_names = {
                str(getattr(plant, "name", "") or "")
                == (
                    f"{str(getattr(plant, 'species', '') or '').replace('_', ' ').title()} Plant"
                )[:40]
                for plant in planted
            }
            require(
                "canonical_watering_garden_name",
                str(getattr(garden_state, "garden_name", "") or "")
                == WATERING_CAPTURE_GARDEN_NAME,
                str(getattr(garden_state, "garden_name", "") or ""),
            )
            require(
                "canonical_watering_currency_balance",
                int(getattr(garden_state, "currency_balance", -1) or 0)
                == WATERING_CAPTURE_CURRENCY_BALANCE,
                int(getattr(garden_state, "currency_balance", -1) or 0),
            )
            require(
                "canonical_watering_plant_names",
                len(planted) == 6 and canonical_names == {True},
                [str(getattr(plant, "name", "") or "") for plant in planted],
            )
            require(
                "canonical_watering_growth",
                len(planted) == 6
                and all(
                    int(getattr(plant, "growth_points", -1) or 0)
                    == WATERING_CAPTURE_GROWTH_POINTS
                    for plant in planted
                ),
                [
                    int(getattr(plant, "growth_points", -1) or 0)
                    for plant in planted
                ],
            )

        if kind == "reviewer":
            handler = getattr(self.app, "reviewer_hooks", None)
            toast = getattr(handler, "_reward_toast", None)
            labels = {
                str(label_widget.objectName()): str(label_widget.text())
                for label_widget in (
                    toast.findChildren(QLabel) if toast is not None else ()
                )
                if str(label_widget.objectName())
            }
            expected_title = str(
                annotation.get("canonical_feedback_title", "")
            )
            expected_message = str(
                annotation.get("canonical_feedback_message", "")
            )
            require(
                "reviewer_surface",
                str(getattr(mw, "state", "")) == "review",
                str(getattr(mw, "state", "")),
            )
            require(
                "reward_toast_visible",
                bool(toast is not None and toast.isVisible()),
                bool(toast is not None and toast.isVisible()),
            )
            require(
                "reward_toast_title",
                bool(expected_title)
                and labels.get("ankiGardenRewardTitle") == expected_title,
                labels.get("ankiGardenRewardTitle", ""),
            )
            require(
                "reward_toast_message",
                bool(expected_message)
                and labels.get("ankiGardenRewardMessage") == expected_message
                and not labels.get("ankiGardenRewardDetail", ""),
                {
                    "message": labels.get("ankiGardenRewardMessage", ""),
                    "detail": labels.get("ankiGardenRewardDetail", ""),
                },
            )
            require(
                "canonical_reviewer_reward_projection",
                bool(annotation.get("canonical_projection_passed", False))
                and bool(
                    annotation.get(
                        "all_receipt_groups_share_correlation",
                        False,
                    )
                ),
                annotation,
            )
            expected_tier = str(expectation.get("toast_tier", ""))
            require(
                "reward_toast_tier",
                labels.get("ankiGardenRewardTier", "") == expected_tier,
                labels.get("ankiGardenRewardTier", ""),
            )
            require(
                "reward_toast_focus_safe",
                bool(
                    toast is not None
                    and toast.focusPolicy() == Qt.FocusPolicy.NoFocus
                    and toast.testAttribute(
                        Qt.WidgetAttribute.WA_ShowWithoutActivating
                    )
                    and toast.testAttribute(
                        Qt.WidgetAttribute.WA_TransparentForMouseEvents
                    )
                    and annotation.get("focus_preserved", False)
                ),
                {
                    "focus_preserved": bool(annotation.get("focus_preserved", False)),
                    "no_focus": bool(
                        toast is not None
                        and toast.focusPolicy() == Qt.FocusPolicy.NoFocus
                    ),
                    "show_without_activating": bool(
                        toast is not None
                        and toast.testAttribute(
                            Qt.WidgetAttribute.WA_ShowWithoutActivating
                        )
                    ),
                },
            )
            reviewer_geometry = dict(
                annotation.get("reviewer_overlay_geometry", {}) or {}
            )
            require(
                "reviewer_overlay_geometry",
                bool(
                    reviewer_geometry.get("passed", False)
                    and reviewer_geometry.get(
                        "parent_is_reviewer_webview",
                        False,
                    )
                    and reviewer_geometry.get("viewport_contained", False)
                    and reviewer_geometry.get("size_in_range", False)
                    and reviewer_geometry.get("control_rects")
                    and int(
                        reviewer_geometry.get(
                            "minimum_control_clearance",
                            0,
                        )
                        or 0
                    ) >= 16
                ),
                reviewer_geometry,
            )
            if state_name == "reviewer-find-stacked-sync":
                expected_message = str(
                    annotation.get("expected_feedback_message", "")
                )
                require(
                    "stacked_sync_summary",
                    bool(
                        annotation.get("canonical_projection_passed", False)
                        and annotation.get("stacked_find_count", 0) > 1
                        and annotation.get("sync_correlation")
                        and expected_message
                        and annotation.get("canonical_feedback_message")
                        == expected_message
                        and labels.get("ankiGardenRewardMessage", "")
                        == expected_message
                    ),
                    {
                        "stacked_find_count": annotation.get("stacked_find_count"),
                        "message": labels.get("ankiGardenRewardMessage", ""),
                    },
                )
            if state_name == "reviewer-find-common-reduced-motion":
                require(
                    "reviewer_reduced_motion",
                    bool(annotation.get("reduced_motion_config_enabled", False)),
                    bool(annotation.get("reduced_motion_config_enabled", False)),
                )
        elif kind == "home":
            dom = dict(getattr(self, "_active_home_dom_audit", {}) or {})
            expected_fixture = str(expectation.get("fixture_state", ""))
            require(
                "anki_surface",
                str(getattr(mw, "state", "")) == expectation.get("surface"),
                str(getattr(mw, "state", "")),
            )
            require(
                "source_fixture_state",
                self._active_home_fixture_state == expected_fixture,
                self._active_home_fixture_state,
            )
            require(
                "dom_capture_label",
                str(dom.get("capture_label", "")) == label,
                str(dom.get("capture_label", "")),
            )
            require("dom_fixture_ready", bool(dom.get("ready", False)), dom)
            require(
                "home_weather_and_sun_absent",
                not bool(dom.get("weatherLayerPresent", False))
                and not bool(dom.get("sunLayerPresent", False)),
                {
                    "weather_layer_present": bool(
                        dom.get("weatherLayerPresent", False)
                    ),
                    "sun_layer_present": bool(dom.get("sunLayerPresent", False)),
                },
            )
            banned_terms = [
                str(term) for term in list(dom.get("bannedTerms", ()) or ())
            ]
            compact_fields_required = expected_fixture in {
                "starter-planted-not-nurtured",
                "nurtured-active",
                "starter-complete-without-plant",
            }
            require(
                "compact_home_copy",
                not banned_terms
                and (
                    not compact_fields_required
                    or bool(dom.get("compactFieldsPresent", False))
                ),
                {
                    "rendered_text": str(dom.get("renderedCopy", "")),
                    "banned_terms": banned_terms,
                    "compact_fields_present": bool(
                        dom.get("compactFieldsPresent", False)
                    ),
                    "passed": bool(
                        not banned_terms
                        and (
                            not compact_fields_required
                            or bool(dom.get("compactFieldsPresent", False))
                        )
                    ),
                },
            )
            require(
                "home_preview_information_model",
                bool(
                    dom.get("conciseInformationModelPassed", False)
                    and dom.get("homeActionGeometryPassed", False)
                ),
                {
                    "support_text": str(dom.get("supportText", "")),
                    "action_text": str(dom.get("homeActionText", "")),
                    "action_width": dom.get("homeActionWidth"),
                    "action_height": dom.get("homeActionHeight"),
                    "information_model_passed": bool(
                        dom.get("conciseInformationModelPassed", False)
                    ),
                    "geometry_passed": bool(
                        dom.get("homeActionGeometryPassed", False)
                    ),
                },
            )
            if state_name == "home-preview-stale":
                stale_geometry = {
                    "status_bounds": dom.get("previewStatusBounds"),
                    "action_bounds": dom.get("homeActionBounds"),
                    "status_action_overlap": bool(
                        dom.get("previewStatusActionOverlap", True)
                    ),
                    "action_enabled": bool(dom.get("homeActionEnabled", False)),
                }
                stale_geometry["passed"] = bool(
                    dom.get("previewStatusPresent", False)
                    and not stale_geometry["status_action_overlap"]
                    and stale_geometry["action_enabled"]
                )
                require(
                    "stale_preview_action_clearance",
                    bool(stale_geometry["passed"]),
                    stale_geometry,
                )
            if "active_slot" in expectation:
                expected_slot = int(expectation["active_slot"])
                actual_slot = int(getattr(active_plant, "slot_index", -1) or 0)
                require("active_plant_slot", actual_slot == expected_slot, actual_slot)
                require(
                    "dom_active_slot",
                    int(dom.get("activeSlot", -1)) == expected_slot,
                    int(dom.get("activeSlot", -1)),
                )
        elif kind == "dashboard":
            scene = getattr(widget, "scene", None)
            scene_payload = dict(getattr(scene, "scene", {}) or {})
            plant_card = getattr(widget, "plant_card", None)
            selected_id = str(getattr(plant_card, "plant_id", "") or "")
            selected_plant = next(
                (
                    plant for plant in plants
                    if str(getattr(plant, "plant_id", "") or "") == selected_id
                ),
                None,
            )
            occupied_slots = sorted(
                int(getattr(plant, "slot_index"))
                for plant in plants
                if getattr(plant, "slot_index", None) is not None
            )
            require("garden_scene_present", scene is not None, bool(scene))
            if state_name == "starter-garden-onboarding":
                panel = getattr(widget, "onboarding_panel", None)
                require(
                    "starter_incomplete",
                    not bool(getattr(garden_state, "starter_selection_complete", False)),
                    bool(getattr(garden_state, "starter_selection_complete", False)),
                )
                require(
                    "onboarding_visible",
                    bool(panel is not None and panel.isVisible()),
                    bool(panel is not None and panel.isVisible()),
                )
            elif state_name == "full-garden":
                require("planted_garden", bool(plants), len(plants))
                require(
                    "starter_complete",
                    bool(getattr(garden_state, "starter_selection_complete", False)),
                    bool(getattr(garden_state, "starter_selection_complete", False)),
                )
                steady_state = dict(
                    annotation.get("steady_state_visual", {}) or {}
                )
                require(
                    "steady_state_visual",
                    bool(
                        steady_state.get("passed", False)
                        and steady_state.get("overlay_free", False)
                        and steady_state.get("scene_contained", False)
                        and steady_state.get("onboarding_step") == "done"
                        and steady_state.get("page_scroll_value") == 0
                    ),
                    steady_state,
                )
            elif state_name == "hover-outline":
                require(
                    "hover_outline_active",
                    bool(getattr(scene, "_hover_opacity", {})),
                    dict(getattr(scene, "_hover_opacity", {}) or {}),
                )
            elif state_name in {
                "selected-plant-not-nurtured",
                "selected-plant-nurtured",
            }:
                card_visible = bool(plant_card is not None and plant_card.isVisible())
                require("plant_card_visible", card_visible, card_visible)
                require("selected_plant", selected_plant is not None, selected_id)
                expects_active = state_name == "selected-plant-nurtured"
                require(
                    "nurture_boundary",
                    bool(active_id) is expects_active
                    and (not expects_active or selected_id == active_id),
                    {"active_plant_id": active_id, "selected_plant_id": selected_id},
                )
            elif state_name in {"move-mode", "move-occupied-empty-destinations"}:
                placing = bool(getattr(getattr(scene, "_interaction", None), "placing", False))
                require("move_mode_active", placing, placing)
                if state_name == "move-occupied-empty-destinations":
                    require("four_occupied_slots", len(occupied_slots) == 4, occupied_slots)
                    require(
                        "empty_destinations",
                        sum(
                            getattr(plant, "slot_index", None) is None
                            for plant in plants
                        ) >= 2,
                        sum(
                            getattr(plant, "slot_index", None) is None
                            for plant in plants
                        ),
                    )
                    scene_bounds, scene_contained = scroll_child_bounds(
                        scene,
                        getattr(widget, "dashboard_scroll", None),
                    )
                    require(
                        "move_scene_fully_visible",
                        scene_contained,
                        scene_bounds,
                    )
            elif state_name == "collection-origin-plant-placement":
                require(
                    "placement_scene_fully_visible",
                    bool(annotation.get("scene_fully_visible", False)),
                    annotation.get("scene_viewport_bounds"),
                )
            elif state_name == "long-garden-name":
                name = str(getattr(garden_state, "garden_name", "") or "")
                require("long_garden_name", len(name) >= 35, name)
            elif state_name == "long-plant-name":
                longest = max(
                    (str(getattr(plant, "name", "") or "") for plant in plants),
                    key=len,
                    default="",
                )
                require("long_plant_name", len(longest) >= 35, longest)
            elif state_name == "four-digit-coin-balance":
                balance = int(getattr(garden_state, "currency_balance", 0) or 0)
                require("four_digit_balance", balance == 9_999, balance)
            elif state_name == "growth-near-stage-completion":
                from .models.state import GROWTH_THRESHOLDS

                points = int(getattr(selected_plant, "growth_points", -1) or 0)
                require(
                    "near_stage_completion",
                    points == int(GROWTH_THRESHOLDS[-1]) - 25,
                    points,
                )
            elif state_name == "all-six-beds-occupied":
                require("six_occupied_slots", occupied_slots == list(range(6)), occupied_slots)
            elif state_name == "plant-at-every-stage":
                stages = {
                    str(getattr(plant, "growth_stage", "") or "")
                    for plant in plants[:6]
                }
                require("six_growth_stages", len(stages) == 6, sorted(stages))
            elif state_name == "fully-grown-plant-without-fertilize":
                require(
                    "fully_grown_selected",
                    bool(getattr(selected_plant, "fully_grown", False)),
                    selected_id,
                )
                require("fixture_audit", bool(annotation.get("passed", False)), annotation)
                card_bounds, card_contained = scroll_child_bounds(
                    plant_card,
                    getattr(widget, "dashboard_scroll", None),
                )
                require(
                    "plant_card_fully_visible",
                    card_contained
                    and bool(annotation.get("plant_card_fully_visible", False)),
                    {
                        "bounds": card_bounds,
                        "annotation": annotation,
                    },
                )
            elif state_name.startswith("popover-plot-"):
                expected_slot = int(state_name.rsplit("-", 1)[1]) - 1
                actual_slot = getattr(selected_plant, "slot_index", None)
                require(
                    "selected_popover_slot",
                    actual_slot == expected_slot
                    and bool(plant_card is not None and plant_card.isVisible()),
                    actual_slot,
                )
                card_bounds, card_contained = scroll_child_bounds(
                    plant_card,
                    getattr(widget, "dashboard_scroll", None),
                )
                require(
                    "plant_card_fully_visible",
                    card_contained,
                    {
                        "bounds": card_bounds,
                        "annotation": annotation,
                    },
                )
            elif state_name.startswith("watering-can-garden-plot-"):
                expected_slot = int(state_name.rsplit("-", 1)[1]) - 1
                actual_slot = getattr(active_plant, "slot_index", None)
                require("active_plant_slot", actual_slot == expected_slot, actual_slot)
            elif state_name == "keyboard-focus-state":
                button = getattr(widget, "progress_btn", None)
                try:
                    focus_owner = QApplication.focusWidget()
                except Exception:
                    focus_owner = None
                require(
                    "keyboard_focus_visible",
                    bool(button is not None and button.hasFocus()),
                    bool(button is not None and button.hasFocus()),
                )
                require(
                    "keyboard_focus_owner",
                    button is not None
                    and focus_owner is button
                    and bool(button.hasFocus()),
                    "progress_btn" if focus_owner is button else (
                        type(focus_owner).__name__ if focus_owner is not None else ""
                    ),
                )
        elif kind == "progress":
            navigation = getattr(widget, "navigation", None)
            keys = list(getattr(navigation, "keys", ()) or ())
            current_index = int(
                navigation.stack.currentIndex()
                if navigation is not None and getattr(navigation, "stack", None) is not None
                else -1
            )
            current_page = keys[current_index] if 0 <= current_index < len(keys) else ""
            require(
                "progress_page",
                current_page == expectation.get("page"),
                current_page,
            )
            stats = getattr(garden_state, "daily_stats", None)
            visible_label_texts = [
                str(label_widget.text())
                for label_widget in widget.findChildren(QLabel)
                if label_widget.isVisible()
            ]
            if state_name == "growth-zero":
                require(
                    "zero_growth",
                    active_plant is not None
                    and int(getattr(active_plant, "growth_points", -1) or 0) == 0
                    and int(getattr(stats, "growth_earned", -1) or 0) == 0
                    and len([plant for plant in plants if getattr(plant, "planted", False)]) == 3
                    and not dict(getattr(stats, "plant_nurtured_growth", {}) or {})
                    and not dict(getattr(stats, "plant_passive_growth_fifths", {}) or {}),
                    {
                        "plant": int(getattr(active_plant, "growth_points", -1) or 0),
                        "today": int(getattr(stats, "growth_earned", -1) or 0),
                        "planted_count": len([
                            plant for plant in plants
                            if getattr(plant, "planted", False)
                        ]),
                    },
                )
            elif state_name == "growth-nonzero":
                source_values = [
                    int(getattr(stats, field, 0) or 0)
                    for field in (
                        "base_growth",
                        "streak_bonus_growth",
                        "fertilizer_growth",
                        "weather_growth",
                        "scenery_growth",
                        "booster_growth",
                    )
                ]
                passive_fifths = dict(
                    getattr(stats, "plant_passive_growth_fifths", {}) or {}
                )
                require(
                    "nonzero_growth",
                    int(getattr(active_plant, "growth_points", 0) or 0) == 1_250
                    and int(getattr(stats, "study_growth_generated", 0) or 0) == 53
                    and int(getattr(stats, "growth_earned", 0) or 0) == 105
                    and source_values == [31, 5, 4, 3, 6, 4]
                    and sorted(passive_fifths.values()) == [17, 36, 53]
                    and sorted(
                        int(getattr(plant, "passive_growth_remainder_fifths", 0) or 0)
                        for plant in plants
                    ) == [1, 2, 3],
                    {
                        "plant": int(getattr(active_plant, "growth_points", 0) or 0),
                        "today": int(getattr(stats, "growth_earned", 0) or 0),
                        "study": int(
                            getattr(stats, "study_growth_generated", 0) or 0
                        ),
                        "sources": source_values,
                        "passive_fifths": passive_fifths,
                    },
                )
            elif state_name == "streak-new":
                require(
                    "new_streak",
                    int(getattr(garden_state, "streak_days", -1) or 0) == 0
                    and int(getattr(stats, "reviewed", -1) or 0) == 0,
                    [getattr(garden_state, "streak_days", None), getattr(stats, "reviewed", None)],
                )
            elif state_name == "streak-active":
                from .reward_presentation import achievement_presentation

                streak_projection = achievement_presentation(
                    "streak_7",
                    garden_state,
                )
                require(
                    "active_streak",
                    streak_projection is not None
                    and int(getattr(garden_state, "streak_days", 0) or 0)
                    == streak_projection.progress_target
                    and int(getattr(stats, "reviewed", 0) or 0)
                    == int(annotation.get("daily_answers", -1)),
                    [getattr(garden_state, "streak_days", None), getattr(stats, "reviewed", None)],
                )
                require(
                    "canonical_active_streak_achievement",
                    streak_projection is not None
                    and streak_projection.completed
                    and annotation.get("achievement_reward")
                    == streak_projection.reward_summary
                    and bool(annotation.get("passed", False)),
                    annotation,
                )
            elif state_name == "coins-zero":
                transactions = list(getattr(garden_state, "currency_transactions", ()) or ())
                receipts = list(
                    getattr(garden_state, "recent_reward_receipts", ()) or ()
                )
                outcomes = dict(
                    getattr(garden_state, "garden_find_outcomes", {}) or {}
                )
                require(
                    "zero_coins",
                    int(getattr(garden_state, "currency_balance", -1) or 0) == 0
                    and not transactions,
                    [getattr(garden_state, "currency_balance", None), len(transactions)],
                )
                require(
                    "empty_coin_activity",
                    not receipts
                    and not outcomes
                    and bool(annotation.get("passed", False))
                    and any(
                        "Earn Garden Coins from daily rewards" in text
                        or (
                            "Earn Garden Coins" in text
                            and "Garden Finds" in text
                        )
                        for text in visible_label_texts
                    ),
                    {
                        "receipt_count": len(receipts),
                        "find_count": len(outcomes),
                        "labels": visible_label_texts,
                    },
                )
            elif state_name == "coins-activity":
                from .reward_presentation import (
                    recent_garden_finds,
                    recent_reward_summaries,
                )

                transactions = list(getattr(garden_state, "currency_transactions", ()) or ())
                summaries = recent_reward_summaries(garden_state)
                findings = recent_garden_finds(garden_state)
                stacked_correlation = str(
                    annotation.get("stacked_correlation_id", "")
                )
                stacked = next(
                    (
                        summary for summary in summaries
                        if summary.correlation_id == stacked_correlation
                    ),
                    None,
                )
                direct_growth = next(
                    (
                        item for item in findings
                        if item.reward_id == "find_morning_dew"
                    ),
                    None,
                )
                compost = next(
                    (
                        item for item in findings
                        if item.reward_id == "find_fertilizer"
                    ),
                    None,
                )
                require(
                    "canonical_reward_activity",
                    len(transactions) >= 2
                    and stacked is not None
                    and len(stacked.receipts) == 2
                    and all(
                        receipt.correlation_id == stacked_correlation
                        for receipt in stacked.receipts
                    )
                    and direct_growth is not None
                    and direct_growth.reward_type == "growth"
                    and compost is not None
                    and compost.display_name == "Rich Compost"
                    and compost.item_id == "fertilizer_basic"
                    and bool(annotation.get("passed", False)),
                    annotation,
                )
                require(
                    "coin_activity_ledger_copy",
                    "Recent activity" in visible_label_texts
                    and all(
                        heading in visible_label_texts
                        for heading in (
                            "Source",
                            "Change",
                            "Balance",
                        )
                    )
                    and "Garden Find" in visible_label_texts
                    and any(
                        text.startswith("Achievement · ")
                        for text in visible_label_texts
                    ),
                    visible_label_texts,
                )
            elif state_name == "progress-overview-redirect-growth":
                require(
                    "overview_redirected_to_growth",
                    bool(annotation.get("passed", False))
                    and annotation.get("requested_route") == "overview"
                    and annotation.get("normalized_page") == "growth"
                    and not bool(annotation.get("overview_registered", True)),
                    annotation,
                )
                direct_growth = dict(
                    annotation.get("direct_growth_visual", {}) or {}
                )
                require(
                    "direct_growth_visual",
                    bool(
                        direct_growth.get("passed", False)
                        and int(direct_growth.get("amount", 0) or 0) > 0
                        and bool(str(direct_growth.get("label", "")).strip())
                        and direct_growth.get("label_contained", False)
                        and direct_growth.get("value_contained", False)
                    ),
                    direct_growth,
                )
            elif state_name == "collection-several-discovered":
                require(
                    "several_collected_audit",
                    bool(annotation.get("passed", False))
                    and int(annotation.get("collected_count", 0)) == 4,
                    annotation,
                )
            elif state_name == "collection-no-filter-matches":
                dashboard = getattr(self.app, "dashboard", None)
                no_results = getattr(dashboard, "collection_no_results", None)
                empty_text = str(annotation.get("empty_state_text", ""))
                require(
                    "not_collected_filter",
                    str(getattr(dashboard, "_collection_filter", "")) == "not_collected",
                    str(getattr(dashboard, "_collection_filter", "")),
                )
                require(
                    "collection_no_results_visible",
                    bool(
                        no_results is not None
                        and no_results.isVisible()
                        and "No matches" in empty_text
                        and annotation.get("empty_state_actions") == []
                        and bool(annotation.get("filter_clear_visible", False))
                        and bool(annotation.get("passed", False))
                    ),
                    annotation,
                )
            elif state_name == "collection-environment-mechanics":
                mechanics_visual = dict(
                    annotation.get("environment_mechanics_visual", {}) or {}
                )
                require(
                    "environment_mechanics_and_collection_loadout",
                    bool(annotation.get("passed", False))
                    and bool(annotation.get("complete_effects_visible", False))
                    and bool(annotation.get("loadout_summary_visible", False))
                    and bool(annotation.get("equipment_state_visible", False))
                    and bool(annotation.get("loadout_route_visible", False))
                    and bool(annotation.get("loadout_routes_enabled", False))
                    and bool(annotation.get("action_buttons_fully_visible", False))
                    and bool(annotation.get("compact_environment_actions", False))
                    and bool(annotation.get("mechanics_always_visible", False))
                    and bool(annotation.get("filter_toolbar_visible", False))
                    and bool(annotation.get("scroll_at_top", False))
                    and not bool(annotation.get("direct_mutation_controls", True)),
                    annotation,
                )
                require(
                    "environment_mechanics_visual",
                    bool(
                        mechanics_visual.get("passed", False)
                        and set(mechanics_visual.get("required_keys", ()))
                        == {
                            "toolbar",
                            "summary_title",
                            "summary_selection",
                            "edit_appearance",
                            "item_title",
                            "item_status",
                            "effect",
                            "mechanics",
                        }
                        and all(
                            bool(dict(row).get("contained", False))
                            for row in list(
                                mechanics_visual.get("required_bounds", ()) or ()
                            )
                        )
                    ),
                    mechanics_visual,
                )
            elif state_name == "achievement-completed":
                from .achievements import ACHIEVEMENT_DEFINITIONS
                from .reward_presentation import achievement_presentations

                projections = achievement_presentations(garden_state)
                require(
                    "completed_canonical_achievements",
                    int(getattr(stats, "reviewed", 0) or 0)
                    == int(annotation.get("daily_answers", -1))
                    and len(projections) == len(ACHIEVEMENT_DEFINITIONS)
                    and all(item.completed for item in projections)
                    and all(bool(item.reward_summary) for item in projections)
                    and bool(annotation.get("passed", False))
                    and annotation.get("achievement_filter") == "completed"
                    and any(
                        projection.reward_summary in visible_label_texts
                        for projection in projections
                    ),
                    {
                        "reviewed": getattr(stats, "reviewed", None),
                        "projection_count": len(projections),
                        "completed": sum(item.completed for item in projections),
                        "annotation": annotation,
                    },
                )
            elif state_name == "clear-recall-canonical-projection":
                from .reward_presentation import achievement_presentation

                projection = achievement_presentation(
                    "retention_90",
                    garden_state,
                )
                require(
                    "canonical_clear_recall",
                    bool(annotation.get("passed", False))
                    and projection is not None
                    and tuple(annotation.get("condition_lines", ()))
                    == projection.condition_lines
                    and len(projection.condition_lines) >= 1
                    and all(
                        condition in visible_label_texts
                        for condition in projection.condition_lines
                    )
                    and annotation.get("value_text") == projection.value_text
                    and annotation.get("reward_summary")
                    == projection.reward_summary
                    and not projection.completed
                    and projection.name in visible_label_texts
                    and projection.criteria_text in visible_label_texts
                    and projection.reward_summary in visible_label_texts
                    and bool(annotation.get("target_card_fully_visible", False))
                    and annotation.get("achievement_filter") == "in_progress"
                    and int(annotation.get("achievement_grid_columns", 0)) == 2
                    and bool(annotation.get("singleton_spans_passed", False))
                    and len(annotation.get("singleton_span_cards", ())) == 2,
                    annotation,
                )
            elif state_name == "streak-at-risk":
                require(
                    "at_risk_streak",
                    bool(annotation.get("passed", False))
                    and int(getattr(garden_state, "streak_days", 0) or 0)
                    == int(annotation.get("streak_days", -1))
                    and int(getattr(stats, "reviewed", -1) or 0)
                    == int(annotation.get("daily_answers", -1)),
                    annotation,
                )
            elif state_name == "streak-missed-day":
                from .reward_presentation import recurring_reward_presentations

                projected_streak_days = int(
                    annotation.get("projected_streak_days", -1)
                )
                weekly_reward = next(
                    rule
                    for rule in recurring_reward_presentations(
                        garden_state,
                        self.app.engine,
                        current_streak_days=projected_streak_days,
                    )
                    if rule.rule_id == "weekly_streak"
                )
                require(
                    "missed_day_streak",
                    bool(annotation.get("passed", False))
                    and int(getattr(garden_state, "streak_days", 0) or 0)
                    == int(annotation.get("previous_streak_days", -1))
                    and int(getattr(stats, "reviewed", -1) or 0)
                    == int(annotation.get("daily_answers", -1)),
                    annotation,
                )
                require(
                    "missed_day_weekly_reward_projection",
                    projected_streak_days == 0
                    and annotation.get("weekly_reward_status")
                    == weekly_reward.status
                    and "Streak ended at 3 days" in visible_label_texts
                    and "Answer a card to start again." in visible_label_texts
                    and not any(
                        text.startswith(("Previous streak", "Next Growth bonus"))
                        for text in visible_label_texts
                    ),
                    {
                        "projected_streak_days": projected_streak_days,
                        "expected_status": weekly_reward.status,
                        "annotation": annotation,
                    },
                )
            elif state_name == "streak-achievement-earned-next":
                from .reward_presentation import achievement_presentation

                completed = achievement_presentation(
                    "streak_7",
                    garden_state,
                )
                next_achievement = achievement_presentation(
                    "streak_30",
                    garden_state,
                )
                require(
                    "earned_streak_achievement_and_next_growth_bonus",
                    int(getattr(garden_state, "streak_days", 0) or 0)
                    == int(annotation.get("current_streak_days", -1))
                    and completed is not None
                    and completed.completed
                    and annotation.get("completed_achievement_reward")
                    == completed.reward_summary
                    and next_achievement is not None
                    and not next_achievement.completed
                    and annotation.get("next_achievement_value")
                    == next_achievement.value_text
                    and bool(annotation.get("passed", False)),
                    annotation,
                )
                require(
                    "streak_achievement_and_growth_bonus_copy",
                    any(
                        (
                            "Next bonus at "
                            f"{int(annotation.get('next_growth_bonus_days', 0)):,} days"
                        ) in text
                        for text in visible_label_texts
                    )
                    and "Growth bonuses" in visible_label_texts
                    and "One-time streak achievements" in visible_label_texts
                    and completed is not None
                    and completed.name in visible_label_texts
                    and completed.reward_summary in visible_label_texts,
                    visible_label_texts,
                )
        elif kind == "nursery":
            tabs = getattr(widget, "catalog_tabs", None)
            tab = int(tabs.currentIndex()) if tabs is not None else -1
            starter_mode = bool(getattr(widget, "_starter_mode", False))
            require("nursery_tab", tab == int(expectation.get("tab", -1)), tab)
            require(
                "starter_mode",
                starter_mode is bool(expectation.get("starter_mode", False)),
                starter_mode,
            )
            visible_buttons = [
                _displayed_button_text(button)
                for button in widget.findChildren(QAbstractButton)
                if button.isVisible()
            ]
            if state_name == "nursery-fertilizer-booster":
                action_text = str(annotation.get("action_text", ""))
                action = next(
                    (
                        button
                        for button in widget.findChildren(QAbstractButton)
                        if _displayed_button_text(button) == action_text
                    ),
                    None,
                )
                item_id = str(annotation.get("item_id", ""))
                require(
                    "stored_find_fertilizer_usable",
                    bool(annotation.get("passed", False))
                    and bool(action_text)
                    and action is not None
                    and action.isVisible()
                    and action.isEnabled()
                    and int(garden_state.consumables.get(item_id, 0) or 0) >= 1
                    and str(getattr(garden_state, "active_plant_id", "") or "")
                    == str(annotation.get("target_plant_id", "")),
                    {
                        "annotation": annotation,
                        "visible_buttons": visible_buttons,
                    },
                )
            elif state_name == "nursery-item-owned":
                unlocked = set(
                    str(item)
                    for item in list(getattr(garden_state, "unlocked_species", ()) or ())
                )
                owned_species = {
                    str(getattr(plant, "species", "") or "") for plant in plants
                }
                require(
                    "owned_catalog_action",
                    len(plants) >= 6
                    and bool(owned_species)
                    and owned_species.issubset(unlocked)
                    and bool(
                        set(visible_buttons)
                        & {"Store plant", "Place in Garden", "View Garden"}
                    )
                    and bool(
                        self.app.engine.catalog_summary().get(
                            "available_species",
                            [],
                        )
                    ),
                    {
                        "buttons": visible_buttons,
                        "owned_species": sorted(owned_species),
                        "unlocked_species": sorted(unlocked),
                    },
                )
                owned_visual = dict(
                    annotation.get("owned_item_visual", {}) or {}
                )
                require(
                    "owned_item_visual",
                    bool(
                        annotation.get("passed", False)
                        and owned_visual.get("passed", False)
                        and owned_visual.get("item_id")
                        and owned_visual.get("item_name")
                        and all(
                            bool(
                                dict(owned_visual.get(key, {}) or {}).get(
                                    "contained",
                                    False,
                                )
                            )
                            for key in (
                                "card",
                                "title",
                                "action_bounds",
                            )
                        )
                    ),
                    owned_visual,
                )
            elif state_name == "nursery-item-locked":
                disabled_catalog_actions = [
                    _displayed_button_text(button)
                    for button in widget.findChildren(QAbstractButton)
                    if button.isVisible()
                    and not button.isEnabled()
                    and _displayed_button_text(button) in {
                        "Buy",
                        "Buy and apply",
                        "Buy and replace",
                        "Extend",
                        "Use",
                    }
                ]
                helper_text = [
                    str(label_widget.text())
                    for label_widget in widget.findChildren(QLabel)
                    if label_widget.isVisible()
                    and (
                        "more needed" in str(label_widget.text()).lower()
                        or "owned" in str(label_widget.text()).lower()
                    )
                ]
                require(
                    "locked_catalog_state",
                    int(getattr(garden_state, "currency_balance", -1) or 0) == 0
                    and bool(disabled_catalog_actions)
                    and bool(helper_text),
                    {
                        "currency_balance": int(
                            getattr(garden_state, "currency_balance", -1) or 0
                        ),
                        "disabled_catalog_actions": disabled_catalog_actions,
                        "helper_text": helper_text,
                    },
                )
                locked_geometry = dict(
                    annotation.get("locked_catalog_geometry", {}) or {}
                )
                require(
                    "locked_catalog_rows_unclipped",
                    bool(
                        annotation.get("passed", False)
                        and locked_geometry.get("passed", False)
                        and locked_geometry.get("visible_cards")
                        and not locked_geometry.get("partial_cards")
                        and dict(locked_geometry.get("heading", {}) or {}).get(
                            "contained",
                            False,
                        )
                    ),
                    locked_geometry,
                )
            elif state_name == "nursery-purchase-success":
                title = str(
                    getattr(getattr(widget, "environment_feature_title", None), "text", lambda: "")()
                )
                toast = getattr(widget, "nursery_toast", None)
                toast_text = str(
                    getattr(getattr(toast, "message", None), "text", lambda: "")()
                )
                primary = str(
                    getattr(getattr(toast, "action", None), "text", lambda: "")()
                )
                secondary = str(
                    getattr(getattr(toast, "dismiss", None), "text", lambda: "")()
                )
                require(
                    "purchased_item_preview",
                    bool(title)
                    and bool(toast is not None and toast.isVisible())
                    and toast_text == "Soft Breeze added to your collection."
                    and primary == "View Collection"
                    and secondary == "Keep browsing",
                    {
                        "title": title,
                        "toast": toast_text,
                        "primary": primary,
                        "secondary": secondary,
                        "buttons": visible_buttons,
                    },
                )
            elif state_name in {
                "purchase-success-inventory-collection",
                "purchase-success-fertilizer-applied",
                "purchase-success-garden-bed-unlocked",
            }:
                toast = getattr(widget, "nursery_toast", None)
                toast_text = str(
                    getattr(getattr(toast, "message", None), "text", lambda: "")()
                )
                expected_action = {
                    "purchase-success-inventory-collection": "Place in Garden",
                    "purchase-success-fertilizer-applied": "View plant",
                    "purchase-success-garden-bed-unlocked": "View Garden",
                }[state_name]
                expected_outcome = {
                    "purchase-success-inventory-collection": "Sunflower added.",
                    "purchase-success-fertilizer-applied": "Basic Fertilizer applied.",
                    "purchase-success-garden-bed-unlocked": "Bed 3 unlocked.",
                }[state_name]
                require(
                    "typed_purchase_receipt",
                    bool(toast is not None and toast.isVisible())
                    and toast_text == expected_outcome
                    and getattr(toast, "action", None) is not None
                    and toast.action.text() == expected_action
                    and toast.dismiss.text() == (
                        "View Collection"
                        if state_name == "purchase-success-inventory-collection"
                        else "Keep browsing"
                    )
                    and bool(
                        dict(
                            annotation.get("nursery_feedback_flow", {}) or {}
                        ).get("passed", False)
                    )
                    and bool(annotation.get("passed", False)),
                    {
                        "toast": toast_text,
                        "buttons": visible_buttons,
                        "annotation": annotation,
                    },
                )
                require(
                    "normal_flow_transaction_feedback",
                    bool(
                        dict(
                            annotation.get("nursery_feedback_flow", {}) or {}
                        ).get("passed", False)
                    ),
                    annotation.get("nursery_feedback_flow", {}),
                )
            elif state_name == "nursery-empty-state":
                require(
                    "intentional_nursery_empty_state",
                    bool(annotation.get("passed", False))
                    and bool(annotation.get("empty_state_visible", False)),
                    annotation,
                )
            elif state_name == "nursery-weather-scenery":
                require(
                    "distinct_weather_preview_art",
                    bool(annotation.get("passed", False))
                    and bool(annotation.get("clear_skies_preview_present", False))
                    and bool(annotation.get("soft_breeze_preview_present", False))
                    and not bool(annotation.get("missing_art_previews", ()))
                    and bool(annotation.get("preview_signatures_distinct", False)),
                    annotation,
                )
            elif state_name == "missing-artwork-graphical-fallback":
                missing_matrix = dict(
                    annotation.get("missing_artwork_matrix", {}) or {}
                )
                require(
                    "missing_artwork_matrix",
                    bool(
                        annotation.get("passed", False)
                        and missing_matrix.get("passed", False)
                        and list(missing_matrix.get("types", ()))
                        == list(MISSING_ARTWORK_CAPTURE_TYPES)
                        and len(list(missing_matrix.get("entries", ()) or ()))
                        == len(MISSING_ARTWORK_CAPTURE_TYPES)
                        and len(
                            list(
                                missing_matrix.get(
                                    "diagnostic_log_fingerprints",
                                    (),
                                )
                                or ()
                            )
                        ) == len(MISSING_ARTWORK_CAPTURE_TYPES)
                        and all(
                            bool(dict(entry).get("passed", False))
                            and bool(dict(entry).get("graphic_present", False))
                            and bool(
                                dict(entry).get(
                                    "aspect_ratio_preserved",
                                    False,
                                )
                            )
                            and bool(
                                dict(entry).get(
                                    "diagnostic_path_logged",
                                    False,
                                )
                            )
                            for entry in list(
                                missing_matrix.get("entries", ()) or ()
                            )
                        )
                    ),
                    missing_matrix,
                )
            elif state_name in {
                "starter-action-above-footer",
                "nursery-final-row-above-footer",
            }:
                require("fixture_audit", bool(annotation.get("passed", False)), annotation)
        elif kind == "settings":
            tabs = getattr(widget, "tabs", None)
            tab = int(tabs.currentIndex()) if tabs is not None else -1
            require("settings_tab", tab == int(expectation.get("tab", -1)), tab)
            if state_name == "settings-home-preview-disabled":
                enabled = bool(widget.behavior.show_home_widget.isChecked())
                dirty = bool(widget._draft_is_dirty())
                require(
                    "home_preview_disabled_draft",
                    not enabled and dirty,
                    {"home_preview_enabled": enabled, "draft_dirty": dirty},
                )
            elif state_name == "settings-display-advanced-open":
                require(
                    "advanced_display_open",
                    bool(widget.behavior.advanced_toggle.isChecked())
                    and bool(widget.behavior.advanced_panel.isVisible()),
                    bool(widget.behavior.advanced_panel.isVisible()),
                )
            elif state_name == "diagnostics-clean":
                value = str(widget.diagnostics_card.property("diagnosticState") or "")
                require("clean_diagnostics", value == "clean", value)
            elif state_name == "diagnostics-warning":
                value = str(widget.diagnostics_card.property("diagnosticState") or "")
                require("warning_diagnostics", value == "warning", value)
            elif state_name == "settings-unsaved-changes":
                value = str(widget.garden_name_edit.text())
                require("unsaved_name", value == "Unsaved Moonlit Garden", value)
            elif state_name == "settings-validation-error":
                value = str(widget.garden_name_edit.text())
                require(
                    "validation_error",
                    not value.strip() and bool(widget.garden_name_error.isVisible()),
                    {"value": value, "error_visible": widget.garden_name_error.isVisible()},
                )
            elif state_name == "diagnostics-expanded":
                require(
                    "diagnostics_details_expanded",
                    bool(widget.report_details_toggle.isChecked()),
                    bool(widget.report_details_toggle.isChecked()),
                )
            elif state_name == "production-build-controls-absent":
                require("production_controls_audit", bool(annotation.get("passed", False)), annotation)
            elif state_name == "reduced-motion-enabled":
                dashboard = getattr(self.app, "dashboard", None)
                capture_config = getattr(dashboard, "config", None)
                config_value = getattr(capture_config, "value", None)
                reduced_motion = (
                    bool(config_value("reduced_motion", False))
                    if callable(config_value) else None
                )
                require(
                    "reduced_motion_checked",
                    bool(widget.behavior.reduced_motion.isChecked()),
                    bool(widget.behavior.reduced_motion.isChecked()),
                )
                require(
                    "reduced_motion_config_enabled",
                    reduced_motion is True,
                    reduced_motion,
                )
        elif kind == "collectible-detail":
            tabs = getattr(widget, "option_tabs", None)
            tab = int(tabs.currentIndex()) if tabs is not None else -1
            if state_name == "collection-loadout-detail":
                require("collection_loadout_tab", tab == 0, tab)
            elif state_name == "collection-loadout-persistence-error":
                rendered_state = dict(
                    annotation.get("rendered_state", {}) or {}
                )
                require(
                    "loadout_rollback",
                    bool(annotation.get("passed", False))
                    and bool(annotation.get("error_visible", False))
                    and bool(annotation.get("single_banner", False))
                    and bool(annotation.get("normal_width_actions", False))
                    and bool(annotation.get("actions_right_aligned", False))
                    and bool(rendered_state.get("passed", False)),
                    annotation,
                )
            else:
                persisted_visibility = tuple(
                    bool(value)
                    for value in list(annotation.get("persisted_visibility", ()))[:2]
                )
                expected_visibility = (
                    persisted_visibility
                    if state_name == "collection-preview-restored"
                    and len(persisted_visibility) == 2
                    else (False, False)
                )
                require("collection_effects_tab", tab == 3, tab)
                require(
                    "effect_visibility",
                    (
                        bool(widget.show_weather.isChecked()),
                        bool(widget.show_scenery.isChecked()),
                    ) == expected_visibility,
                    [widget.show_weather.isChecked(), widget.show_scenery.isChecked()],
                )
                if state_name == "collection-preview-restored":
                    require(
                        "restored_preview_transition",
                        bool(
                            annotation.get("dirty_preview_created", False)
                            and annotation.get("reset_path_invoked", False)
                            and annotation.get("draft_restored", False)
                            and annotation.get("committed_state_unchanged", False)
                        ),
                        annotation,
                    )
                    restored_visual = dict(
                        annotation.get("restored_preview_visual", {}) or {}
                    )
                    require(
                        "restored_preview_dirty_cleared",
                        bool(
                            annotation.get("restored_preview_dirty_cleared", False)
                            and widget.unsaved.isHidden()
                            and not str(widget.unsaved.text()).strip()
                        ),
                        {
                            "hidden": widget.unsaved.isHidden(),
                            "text": str(widget.unsaved.text()),
                        },
                    )
                    require(
                        "restored_preview_visual",
                        bool(
                            restored_visual.get("passed", False)
                            and restored_visual.get("visible", False)
                            and restored_visual.get("contained", False)
                            and restored_visual.get("text") == "Preview reset."
                        ),
                        restored_visual,
                    )
        elif kind == "dialog":
            title = str(widget.windowTitle() or "")
            require("dialog_title", bool(title), title)
            if state_name == "starter-selection-confirmation":
                buttons = [
                    str(button.text()) for button in widget.findChildren(QAbstractButton)
                ]
                require(
                    "starter_confirmation",
                    title.startswith("Choose ")
                    and title.endswith("?")
                    and "Back" in buttons
                    and any(button.startswith("Choose ") for button in buttons),
                    {"title": title, "buttons": buttons},
                )
            elif state_name == "plant-story":
                require(
                    "plant_story_target",
                    title == "Plant Story" and bool(getattr(widget, "plant_id", "")),
                    getattr(widget, "plant_id", ""),
                )
            elif state_name == "collection-species-overview":
                require(
                    "species_overview",
                    actual_family == "SpeciesOverviewDialog",
                    actual_family,
                )
            elif state_name == "known-not-collected-rare-mystery":
                require(
                    "known_not_collected_rare_mystery",
                    actual_family == "SpeciesOverviewDialog"
                    and bool(annotation.get("passed", False))
                    and int(annotation.get("collected_instances", -1)) == 0
                    and bool(annotation.get("rare_mystery", False)),
                    annotation,
                )
            elif state_name == "fertilizer-replacement-confirmation":
                buttons = [
                    _displayed_button_text(button)
                    for button in widget.findChildren(QAbstractButton)
                ]
                require(
                    "fertilizer_replacement",
                    title.startswith("Replace ")
                    and title.endswith("?")
                    and any(button.startswith("Keep ") for button in buttons)
                    and any(button.startswith("Buy ") for button in buttons),
                    {"title": title, "buttons": buttons},
                )
            elif state_name in _GROWTH_CHARGE_CAPTURE_LABELS:
                from .ui.formatters import format_status_label

                expected_status = str(
                    expectation.get("growth_charge_status", "")
                )
                actual_status = str(widget.property("growthChargeState") or "")
                buttons = [
                    _displayed_button_text(button)
                    for button in widget.findChildren(QAbstractButton)
                    if not button.isHidden()
                ]
                active_scrolls = tuple(widget.active_vertical_scroll_regions())
                quote = getattr(widget, "quote", None)
                outcome = getattr(widget, "outcome", None)
                visible_label_text = {
                    str(label_widget.text()).strip()
                    for label_widget in widget.findChildren(QLabel)
                    if label_widget.isVisible()
                    and str(label_widget.text()).strip()
                }
                compact_result = str(widget.compact_summary.text()).strip()
                compact_result_visible = bool(
                    widget.compact_summary_card.isVisible()
                    and compact_result
                )
                plant_details_visible = bool(
                    widget.hero.isVisible()
                    and widget.target_name.isVisible()
                    and str(widget.target_name.text()).strip()
                )
                charge_details_visible = bool(
                    widget.selector_card.isVisible()
                    and (
                        widget.charge_selector.isVisible()
                        or widget.static_charge_row.isVisible()
                    )
                )
                quantity_text = " ".join(filter(None, (
                    str(widget.static_charge_quantity.text()).strip(),
                    str(widget.charge_selector.currentText()).strip(),
                )))
                result_matches_quote = bool(
                    quote is not None
                    and compact_result_visible
                    and f"{max(0, int(quote.current_growth)):,}" in compact_result
                    and f"{max(0, int(quote.projected_growth)):,}" in compact_result
                )
                target_state_value = str(
                    getattr(
                        getattr(quote, "target_state", ""),
                        "value",
                        getattr(quote, "target_state", ""),
                    )
                )
                target_state_label = format_status_label(target_state_value)
                target_state_visible = bool(
                    target_state_label
                    and any(
                        target_state_label.casefold() in text.casefold()
                        for text in visible_label_text
                    )
                )
                footer = getattr(widget, "_pinned_footer", None)
                nursery_action_in_footer = bool(
                    footer is not None
                    and footer.isAncestorOf(widget.nursery_action)
                )
                state_visible = True
                if state_name == "growth-charge-empty-inventory":
                    state_visible = (
                        widget.empty_inventory.isVisible()
                        and widget.nursery_action.isVisible()
                        and nursery_action_in_footer
                        and widget.use_action.isHidden()
                    )
                elif state_name == "growth-charge-loading-disabled":
                    state_visible = (
                        bool(widget._submitting)
                        and bool(widget.dialog_in_flight)
                        and not widget.use_action.isEnabled()
                        and not widget.cancel_action.isEnabled()
                        and (
                            not widget.charge_selector.isVisible()
                            or not widget.charge_selector.isEnabled()
                        )
                        and bool(widget.use_action.property("busy"))
                        and plant_details_visible
                        and charge_details_visible
                        and result_matches_quote
                    )
                elif state_name == "growth-charge-invalid-target":
                    alert_copy = str(widget.alert.text()).strip()
                    state_visible = (
                        widget.alert.isVisible()
                        and "This plant can’t use a Growth Charge." in alert_copy
                        and "Your charge was not used." in alert_copy
                        and not plant_details_visible
                        and not charge_details_visible
                        and not compact_result_visible
                        and not target_state_visible
                        and widget._primary_route == "choose_plant"
                        and widget.use_action.isEnabled()
                        and widget.cancel_action.isVisible()
                        and widget.cancel_action.isEnabled()
                    )
                elif state_name == "growth-charge-stale-inventory":
                    state_visible = (
                        outcome is not None
                        and str(
                            getattr(
                                getattr(outcome, "status", ""),
                                "value",
                                getattr(outcome, "status", ""),
                            )
                        ) == "stale_inventory"
                        and quote is not None
                        and bool(quote.ready)
                        and not bool(widget._submitting)
                        and widget.use_action.isEnabled()
                        and plant_details_visible
                        and charge_details_visible
                        and result_matches_quote
                        and f"{max(0, int(quote.inventory_before)):,}" in quantity_text
                    )
                elif state_name == "growth-charge-persistence-failure":
                    state_visible = (
                        widget.alert.isVisible()
                        and bool(widget.alert.text().strip())
                        and bool(quantity_text)
                        and widget.use_action.isEnabled()
                    )
                elif state_name == "growth-charge-success-stage-reward":
                    rewards = tuple(getattr(outcome, "rewards", ()) or ())
                    reward_total = sum(
                        max(0, int(getattr(reward, "garden_coins", 0) or 0))
                        for reward in rewards
                    )
                    result_title = (
                        f"{str(getattr(outcome, 'target_name', ''))} reached "
                        f"{format_status_label(str(getattr(outcome, 'resulting_stage', '')))}"
                    )
                    reward_copy = f"+{reward_total:,} Garden Coins"
                    state_visible = (
                        outcome is not None
                        and widget.receipt.isVisible()
                        and result_title in visible_label_text
                        and reward_copy in visible_label_text
                        and widget.receipt_copy.isVisible()
                        and f"+{max(0, int(getattr(outcome, 'growth_granted', 0))):,} Growth"
                        in str(widget.receipt_copy.text())
                        and f"{max(0, int(getattr(outcome, 'inventory_remaining', 0))):,}"
                        in str(widget.receipt_copy.text())
                        and not compact_result_visible
                        and widget.use_action.isEnabled()
                        and widget.cancel_action.isVisible()
                        and widget.cancel_action.isEnabled()
                    )
                declared_size = list(
                    expectation.get("declared_client_size", ()) or ()
                )
                geometry_matches = (
                    not declared_size
                    or [int(widget.width()), int(widget.height())] == declared_size
                )
                require(
                    "growth_charge_confirmation_state",
                    bool(title)
                    and actual_status == expected_status
                    and bool(annotation.get("passed", False))
                    and len(active_scrolls) == 1
                    and state_visible
                    and geometry_matches
                    and not bool(widget.content_scroll.verticalScrollBar().isVisible()),
                    {
                        "expected_status": expected_status,
                        "actual_status": actual_status,
                        "buttons": buttons,
                        "active_scroll_count": len(active_scrolls),
                        "compact_result_visible": compact_result_visible,
                        "plant_details_visible": plant_details_visible,
                        "charge_details_visible": charge_details_visible,
                        "target_state_visible": target_state_visible,
                        "state_visible": state_visible,
                        "declared_size": declared_size,
                        "actual_size": [int(widget.width()), int(widget.height())],
                        "annotation": annotation,
                    },
                )
                if state_name == "growth-charge-stale-inventory":
                    require(
                        "growth_charge_ready_with_stale_inventory_warning",
                        bool(
                            expectation.get("growth_charge_fixture_semantics")
                            == "ready_with_stale_inventory_warning"
                            and annotation.get(
                                "ready_with_stale_inventory_warning",
                                False,
                            )
                            and widget.alert.isVisible()
                            and "Availability updated"
                            in str(widget.alert.text())
                        ),
                        {
                            "semantics": expectation.get(
                                "growth_charge_fixture_semantics",
                                "",
                            ),
                            "alert": str(widget.alert.text()),
                            "annotation": annotation,
                        },
                    )
                elif state_name == "growth-charge-success-stage-reward":
                    require(
                        "growth_charge_seed_to_sprout_receipt",
                        bool(
                            annotation.get("seed_to_sprout_receipt", False)
                            and "Seed → Sprout"
                            in str(widget.receipt_copy.text())
                        ),
                        {
                            "receipt": str(widget.receipt_copy.text()),
                            "annotation": annotation,
                        },
                    )
            elif state_name.startswith("purchase-confirmation-") or state_name.startswith("purchase-error-"):
                buttons = [
                    _displayed_button_text(button)
                    for button in widget.findChildren(QAbstractButton)
                ]
                expected_status = str(expectation.get("purchase_status", ""))
                actual_status = str(widget.property("purchaseState") or "")
                status_widget = getattr(widget, "status", None)
                status_visible = bool(
                    status_widget is not None and status_widget.isVisible()
                )
                is_error = state_name.startswith("purchase-error-")
                visible_text = "\n".join(
                    str(candidate.text())
                    for candidate in (
                        list(widget.findChildren(QLabel))
                        + list(widget.findChildren(QAbstractButton))
                    )
                    if candidate.isVisible() and str(candidate.text()).strip()
                )
                banned_noise = (
                    "Not applicable",
                    "Replaces nothing",
                    "Quantity: 1",
                    "Are you sure you want to purchase",
                ) + (
                    ()
                    if state_name in {
                        "purchase-error-stale-price",
                        "purchase-error-stale-balance",
                    }
                    else ("Balance after purchase",)
                )
                scroll = getattr(widget, "content_scroll", None)
                scroll_maximum = (
                    int(scroll.verticalScrollBar().maximum())
                    if scroll is not None else 0
                )
                require(
                    "purchase_confirmation_state",
                    actual_status == expected_status
                    and bool(annotation.get("passed", False))
                    and (
                        not bool(annotation.get("error_banner_required", False))
                        or status_visible
                    )
                    and not any(value in visible_text for value in banned_noise),
                    {
                        "expected_status": expected_status,
                        "actual_status": actual_status,
                        "status_visible": status_visible,
                        "buttons": buttons,
                        "scroll_maximum": scroll_maximum,
                        "annotation": annotation,
                    },
                )
                if state_name in {
                    "purchase-error-stale-price",
                    "purchase-error-stale-balance",
                }:
                    require(
                        "stale_purchase_updated_terms",
                        bool(
                            "Preview" not in visible_text
                            and "Proposed" not in visible_text
                            and widget.price_label.text()
                            == f"{widget.presentation.price:,} Garden Coins"
                            and f"{max(0, int(widget.quote.balance_after)):,}"
                            in widget.balance_label.text()
                            and bool(annotation.get("stale_terms_visible", False))
                            and bool(
                                annotation.get("refreshed_request_matches_live_terms", False)
                            )
                            and bool(annotation.get("canonical_primary_action", False))
                        ),
                        {
                            "proposal": widget.proposal_notice.text(),
                            "price": widget.price_label.text(),
                            "balance": widget.balance_label.text(),
                            "annotation": annotation,
                        },
                    )
                if state_name == "purchase-error-stale-price":
                    require(
                        "stale_price_item_identity",
                        bool(
                            annotation.get("stale_price_item_identity", False)
                            and str(widget.windowTitle()) == "Price changed"
                            and widget.item_name.text().strip()
                            == widget.quote.item_name
                        ),
                        {
                            "title": str(widget.windowTitle()),
                            "item_name": widget.item_name.text().strip(),
                            "annotation": annotation,
                        },
                    )
                elif state_name == "purchase-error-stale-balance":
                    proposal_message = getattr(
                        widget.proposal_notice,
                        "message",
                        None,
                    )
                    proposal_text = str(
                        proposal_message.text()
                        if proposal_message is not None else ""
                    ).strip()
                    require(
                        "ready_with_balance_update",
                        bool(
                            expectation.get("purchase_fixture_semantics")
                            == "ready_with_balance_update"
                            and annotation.get("ready_balance_update", False)
                            and bool(widget.quote.ready)
                            and widget.purchase_action.isEnabled()
                            and widget.status.isHidden()
                            and not widget.proposal_notice.isHidden()
                            and proposal_text == "Balance updated"
                            and str(
                                widget.property("transactionPresentation")
                                or ""
                            ) == "inline-balance-update"
                        ),
                        {
                            "semantics": expectation.get(
                                "purchase_fixture_semantics",
                                "",
                            ),
                            "proposal": proposal_text,
                            "quote_ready": bool(widget.quote.ready),
                            "annotation": annotation,
                        },
                    )
            elif state_name in {
                "fertilizer-unaffordable",
                "fertilizer-affordable",
                "fertilizer-active",
                "fertilizer-expiring-under-minute",
            }:
                balance = int(getattr(garden_state, "currency_balance", 0) or 0)
                fertilizer = getattr(active_plant, "fertilizer", None)
                active = bool(
                    fertilizer is not None
                    and getattr(fertilizer, "active", lambda _now: False)(time.time())
                )
                if state_name == "fertilizer-unaffordable":
                    require("unaffordable_fertilizer", balance == 0 and not active, [balance, active])
                elif state_name == "fertilizer-affordable":
                    require("affordable_fertilizer", balance == 500 and not active, [balance, active])
                elif state_name == "fertilizer-active":
                    require("active_fertilizer", active, active)
                else:
                    remaining = (
                        float(getattr(fertilizer, "expires_at", 0.0) or 0.0)
                        - time.time()
                    )
                    require("expiring_fertilizer", active and 0 < remaining < 60, remaining)

        if state_name == "collection-origin-plant-placement":
            require(
                "collection_placement_active",
                bool(
                    annotation.get("placement_active", False)
                    and annotation.get("occupied_badges_legible", False)
                    and annotation.get("badge_text_fits", False)
                    and annotation.get("badges_contained", False)
                    and annotation.get("badges_pairwise_non_overlapping", False)
                    and annotation.get("badges_clear_plant_artwork", False)
                    and annotation.get("placement_labels_correct", False)
                    and bool(annotation.get("passed", False))
                ),
                annotation,
            )

        return {
            "profile_id": str(expectation.get("profile_id", "")),
            "kind": kind,
            "facts": facts,
            "issues": list(dict.fromkeys(issues)),
            "passed": not issues,
        }

    def _capture_now(
        self,
        label: str,
        widget: Any | None = None,
        *,
        capture_identity: tuple[int, str, str, str] | None = None,
    ) -> None:
        capture_started_monotonic = time.perf_counter()
        trace = getattr(globals().get("logger"), "info", None)
        if callable(trace):
            trace(
                "Anki Garden capture attempt: label=%s identity=%r widget=%s",
                label,
                capture_identity,
                type(widget).__name__ if widget is not None else "None",
            )
        if not isinstance(capture_identity, tuple) or len(capture_identity) != 4:
            self._failures.append({
                "label": label,
                "reason": "Scheduled capture identity snapshot was missing or malformed",
            })
            return
        capture_id, scheduled_label, fixture_source, expected_fixture_label = (
            capture_identity
        )
        identity_issues: list[str] = []
        if type(capture_id) is not int or capture_id < 1:
            identity_issues.append("capture_id")
        if not isinstance(scheduled_label, str) or scheduled_label != label:
            identity_issues.append("scheduled_label")
        if (
            not isinstance(fixture_source, str)
            or not fixture_source.startswith("ordered-step-")
        ):
            identity_issues.append("fixture_source")
        if (
            not isinstance(expected_fixture_label, str)
            or expected_fixture_label != label
        ):
            identity_issues.append("expected_fixture_label")
        if identity_issues:
            self._failures.append({
                "label": label,
                "reason": (
                    "Scheduled capture identity did not match the requested fixture: "
                    + ", ".join(identity_issues)
                ),
            })
            return
        path = self.session_dir / f"{capture_id:02d}-{label}.png"
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
            if widget is not mw:
                self._move_to_capture_display(widget)
            app.processEvents()
            geometry_request = (
                dict(self._active_geometry_request)
                if self._active_geometry_request is not None
                and self._active_geometry_request.get("label") == label
                else None
            )
            family = str(widget.property("windowFamily") or type(widget).__name__)
            expected_family = expected_capture_window_family(label)
            if label in _HOME_CAPTURE_LABELS:
                dom_audit = dict(
                    getattr(self, "_active_home_dom_audit", {}) or {}
                )
                banned_terms = [
                    str(term)
                    for term in list(dom_audit.get("bannedTerms", ()) or ())
                ]
                compact_copy = {
                    "rendered_text": str(dom_audit.get("renderedCopy", "")),
                    "banned_terms": banned_terms,
                    "compact_fields_present": bool(
                        dom_audit.get("compactFieldsPresent", False)
                    ),
                    "support_text": str(dom_audit.get("supportText", "")),
                    "action_text": str(dom_audit.get("homeActionText", "")),
                    "action_width": dom_audit.get("homeActionWidth"),
                    "action_height": dom_audit.get("homeActionHeight"),
                    "information_model_passed": bool(
                        dom_audit.get("conciseInformationModelPassed", False)
                    ),
                    "geometry_passed": bool(
                        dom_audit.get("homeActionGeometryPassed", False)
                    ),
                    "passed": bool(
                        not banned_terms
                        and dom_audit.get(
                            "conciseInformationModelPassed",
                            False,
                        )
                        and dom_audit.get("homeActionGeometryPassed", False)
                    ),
                }
                home_annotation = self._capture_annotations.setdefault(label, {})
                home_annotation["compact_home_copy"] = compact_copy
                home_annotation["passed"] = bool(
                    home_annotation.get("passed", True)
                ) and bool(compact_copy["passed"])
            try:
                postcondition = self._capture_fixture_postcondition(
                    label,
                    widget,
                    expected_fixture_label=expected_fixture_label,
                    actual_family=family,
                    geometry_request=geometry_request,
                )
            except Exception as exc:
                logger.exception(
                    "Anki Garden capture: fixture postcondition failed for %s",
                    label,
                )
                postcondition = {
                    "profile_id": label,
                    "kind": "validation-error",
                    "facts": {"exception": type(exc).__name__},
                    "issues": ["postcondition_exception"],
                    "passed": False,
                }
            fixture_validation = {
                "capture_id": capture_id,
                "fixture_id": label,
                "fixture_source": fixture_source,
                "expected_window_family": expected_family,
                "actual_window_family": family,
                "state_profile": str(postcondition.get("profile_id", "")),
                "postcondition": postcondition,
                "passed": bool(
                    expected_family
                    and family == expected_family
                    and postcondition.get("passed", False)
                ),
            }
            annotation = self._capture_annotations.setdefault(label, {})
            annotation["fixture_identity"] = fixture_validation
            annotation["passed"] = (
                bool(annotation.get("passed", True))
                and bool(fixture_validation["passed"])
            )
            if not expected_family:
                self._failures.append({
                    "label": label,
                    "reason": "Capture fixture is not mapped to a renderer family",
                })
                return
            if family != expected_family:
                self._failures.append({
                    "label": label,
                    "reason": (
                        f"Capture fixture required {expected_family}, but "
                        f"{family} was visible"
                    ),
                })
                return
            if not bool(postcondition.get("passed", False)):
                self._failures.append({
                    "label": label,
                    "reason": (
                        "Capture fixture postcondition failed: "
                        + ", ".join(
                            str(issue)
                            for issue in list(postcondition.get("issues", ()))
                        )
                    ),
                })
            requested_size = (
                list(geometry_request["requested_client_size"])
                if geometry_request is not None else
                [int(widget.width()), int(widget.height())]
            )
            if geometry_request is not None:
                requested = geometry_request["requested_client_size"]
                actual = [int(widget.width()), int(widget.height())]
                geometry_request["actual_client_size"] = actual
                geometry_acceptance = dict(
                    dict(postcondition.get("facts", {}) or {}).get(
                        "geometry_acceptance",
                        {},
                    ) or {}
                )
                exact = bool(geometry_acceptance.get("exact", actual == requested))
                accepted = bool(geometry_acceptance.get("accepted", False))
                geometry_request["exact_size_reached"] = exact
                geometry_request["geometry_drift_accepted"] = bool(
                    accepted and not exact
                )
                geometry_request["geometry_acceptance"] = geometry_acceptance
                if not accepted:
                    self._failures.append({
                        "label": label,
                        "reason": (
                            "Unexplained or unsafe geometry drift from requested "
                            f"client size {requested[0]} by {requested[1]} to "
                            f"{actual[0]} by {actual[1]}: {geometry_acceptance!r}"
                        ),
                    })
            # Capture the exact semantic/layout state that is about to be
            # painted. These readers are non-mutating and fail closed through
            # structured warnings rather than silently accepting partial data.
            responsive_semantics, responsive_warnings = (
                self._responsive_semantic_telemetry(widget)
            )
            geometry_layout_warnings = self._find_geometry_layout_warnings(
                widget,
                capture_label=label,
            )
            dialog_scroll_audit = dict(
                getattr(self, "_last_dialog_scroll_audit", {}) or {}
            )
            geometry_layout_warnings.extend(responsive_warnings)
            self._audit_nurtured_marker_capture(label, widget)
            native_layout_telemetry, native_layout_warnings = (
                self._native_layout_telemetry_audit(widget, label)
            )
            geometry_layout_warnings.extend(native_layout_warnings)
            visual_contract_audit, visual_contract_warnings = (
                self._visual_contract_audit(widget, label)
            )
            geometry_layout_warnings.extend(visual_contract_warnings)
            annotation = self._capture_annotations.setdefault(label, {})
            annotation["native_layout_telemetry"] = dict(
                native_layout_telemetry
            )
            annotation["visual_contract"] = dict(visual_contract_audit)
            annotation["passed"] = bool(
                annotation.get("passed", True)
            ) and bool(
                native_layout_telemetry.get("passed", False)
            ) and bool(visual_contract_audit.get("passed", False))
            if widget is mw:
                reward_toast = None
                if label in _REVIEWER_CAPTURE_LABELS:
                    reviewer_handler = getattr(self.app, "reviewer_hooks", None)
                    reward_toast = getattr(reviewer_handler, "_reward_toast", None)
                    pixmap, capture_method, foreground_confirmed = (
                        self._capture_home_pixmap(
                            widget,
                            require_garden_identity=False,
                            required_overlays=(
                                (reward_toast,)
                                if reward_toast is not None else
                                ()
                            ),
                        )
                    )
                else:
                    pixmap, capture_method, foreground_confirmed = (
                        self._capture_home_pixmap(widget)
                    )
                annotation = self._capture_annotations.setdefault(label, {})
                annotation["home_capture_method"] = capture_method
                annotation["home_foreground_confirmed"] = foreground_confirmed
                annotation["required_overlay_pixels_present"] = bool(
                    (
                        label not in _REVIEWER_CAPTURE_LABELS
                        or reward_toast is not None
                    )
                    and getattr(
                        self,
                        "_last_required_overlay_pixels_present",
                        label not in _REVIEWER_CAPTURE_LABELS,
                    )
                )
                annotation["home_fixture_state"] = self._active_home_fixture_state
                annotation["home_capture_scope"] = (
                    "foreground-window"
                    if capture_method in {
                        "foreground-screen-region",
                        "native-window",
                    } else
                    "app-owned-qt-surface"
                )
                if (
                    label in _REVIEWER_CAPTURE_LABELS
                    and not annotation["required_overlay_pixels_present"]
                ):
                    annotation["passed"] = False
                    self._failures.append({
                        "label": label,
                        "reason": (
                            "Reviewer reward toast was not present in the captured pixels"
                        ),
                    })
            else:
                pixmap = widget.grab()
            if pixmap is None:
                self._failures.append({
                    "label": label,
                    "reason": (
                        f"Anki Home capture failed: {capture_method}"
                        if widget is mw else
                        "Qt returned no pixmap"
                    ),
                })
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
            geometry_layout_warnings.extend(
                self._audit_capture_pixel_contracts(
                    label,
                    widget,
                    pixmap,
                    visual_contract_audit,
                )
            )
            if widget is mw and label in _HOME_CAPTURE_LABELS:
                self._audit_home_pixmap(
                    label,
                    pixmap,
                    expected_width=int(widget.width()),
                    expected_height=int(widget.height()),
                )
            if pixmap.save(str(path), "png"):
                self._screenshots.append(str(path))
                trace = getattr(globals().get("logger"), "info", None)
                if callable(trace):
                    trace(
                        "Anki Garden capture saved: id=%d label=%s path=%s",
                        capture_id,
                        label,
                        path,
                    )
                text_layout_warnings = self._find_text_layout_warnings(widget)
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
                    "capture_id": capture_id,
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
                    "exact_size_reached": bool(
                        geometry_request.get("exact_size_reached", True)
                        if geometry_request is not None else True
                    ),
                    "geometry_drift_accepted": bool(
                        geometry_request.get("geometry_drift_accepted", False)
                        if geometry_request is not None else False
                    ),
                    "geometry_acceptance": (
                        dict(geometry_request.get("geometry_acceptance", {}) or {})
                        if geometry_request is not None else {}
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
                    "responsive_semantics": responsive_semantics,
                    "dialog_scroll_audit": dialog_scroll_audit,
                    "native_layout_telemetry": dict(
                        native_layout_telemetry
                    ),
                    "visual_contract_audit": dict(visual_contract_audit),
                    "text_layout_warnings": text_layout_warnings,
                    "geometry_layout_warnings": geometry_layout_warnings,
                    "fixture_source": fixture_source,
                    "fixture_validation": dict(fixture_validation),
                    "ready_to_capture_ms": round(
                        max(
                            0.0,
                            (
                                capture_started_monotonic
                                - self._capture_requested_monotonic.pop(
                                    label,
                                    capture_started_monotonic,
                                )
                            ) * 1000.0,
                        ),
                        3,
                    ),
                    "capture_duration_ms": round(
                        max(
                            0.0,
                            (time.perf_counter() - capture_started_monotonic)
                            * 1000.0,
                        ),
                        3,
                    ),
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
    def _responsive_semantic_telemetry(
        root: QWidget,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Record visible content-aware decisions and reject ambiguous IDs."""

        entries: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        try:
            candidates = (root, *tuple(root.findChildren(QWidget)))
        except Exception as exc:
            return [], [{
                "kind": "responsive-telemetry-audit-error",
                "exception": type(exc).__name__,
            }]
        for candidate in candidates:
            try:
                if candidate.window() is not root:
                    continue
                if candidate is not root and not candidate.isVisibleTo(root):
                    continue
                semantic_id = str(
                    candidate.property("responsiveRegion") or ""
                ).strip()
                mode = str(candidate.property("responsiveMode") or "").strip()
                available = candidate.property("responsiveAvailableWidth")
                threshold = candidate.property("responsiveThreshold")
                raw_order = str(
                    candidate.property("responsiveRegionOrder") or ""
                ).strip()
                # AdaptiveRegion targets intentionally publish only their
                # region ID. An owner publishes the complete telemetry tuple.
                owner_signal = bool(
                    mode
                    or available is not None
                    or threshold is not None
                    or raw_order
                )
                if not owner_signal:
                    continue
                missing = [
                    name
                    for name, present in (
                        ("responsiveRegion", bool(semantic_id)),
                        ("responsiveMode", bool(mode)),
                        ("responsiveAvailableWidth", available is not None),
                        ("responsiveThreshold", threshold is not None),
                        ("responsiveRegionOrder", bool(raw_order)),
                    )
                    if not present
                ]
                if missing:
                    warnings.append({
                        "kind": "incomplete-responsive-semantic-telemetry",
                        "widget": type(candidate).__name__,
                        "object_name": str(candidate.objectName() or ""),
                        "missing": missing,
                    })
                    continue
                entries.append({
                    "semantic_id": semantic_id,
                    "mode": mode,
                    "available_width": int(available),
                    "threshold_width": int(threshold),
                    "region_order": raw_order.split("|"),
                    "widget": type(candidate).__name__,
                    "object_name": str(candidate.objectName() or ""),
                })
            except Exception as exc:
                warnings.append({
                    "kind": "responsive-telemetry-audit-error",
                    "widget": type(candidate).__name__,
                    "exception": type(exc).__name__,
                })
        _exact, _stable, conflicts = responsive_semantic_maps(entries)
        for semantic_id in conflicts:
            warnings.append({
                "kind": "conflicting-responsive-semantic-id",
                "semantic_id": semantic_id,
            })
        return entries, warnings

    @staticmethod
    def _dialog_surface_page_semantic(root: QWidget) -> str:
        """Return the visible dialog family plus its selected page/tab."""

        family = str(root.property("windowFamily") or type(root).__name__)
        if family == "GardenProgressDialog":
            navigation = getattr(root, "navigation", None)
            keys = list(getattr(navigation, "keys", ()) or ())
            stack = getattr(navigation, "stack", None)
            index = int(stack.currentIndex()) if stack is not None else -1
            page = str(keys[index]) if 0 <= index < len(keys) else "unknown"
            return f"{family}:{page}"
        if family == "GardenSettingsDialog":
            tabs = getattr(root, "tabs", None)
            index = int(tabs.currentIndex()) if tabs is not None else -1
            page = {0: "display", 1: "diagnostics"}.get(index, f"tab-{index}")
            return f"{family}:{page}"
        if family == "NurseryDialog":
            tabs = getattr(root, "catalog_tabs", None)
            index = int(tabs.currentIndex()) if tabs is not None else -1
            page = {
                0: "plants",
                1: "fertilizer",
                2: "garden-spaces",
                3: "weather-scenery",
            }.get(index, f"tab-{index}")
            return f"{family}:{page}"
        if family == "CollectibleDetailDialog":
            tabs = getattr(root, "option_tabs", None)
            index = int(tabs.currentIndex()) if tabs is not None else -1
            page = {0: "loadout", 1: "loadout", 2: "loadout", 3: "preview"}.get(
                index,
                f"tab-{index}",
            )
            return f"{family}:{page}"
        return family

    def _find_geometry_layout_warnings(
        self,
        root: QWidget,
        *,
        capture_label: str = "",
    ) -> list[dict[str, Any]]:
        """Report painted children outside their root and unsafe scrolling."""

        warnings: list[dict[str, Any]] = []
        dialog_scroll_audit: dict[str, Any] = {
            "applicable": False,
            "registered_count": 0,
            "active_count": 0,
            "issues": [],
            "passed": True,
        }
        coverage_surface = ""
        for surface, labels in DIALOG_SCROLL_CAPTURE_COVERAGE.items():
            if capture_label in labels:
                coverage_surface = surface
                break
        expected_page_semantic = DIALOG_SCROLL_CAPTURE_SEMANTICS.get(
            capture_label,
            "",
        )
        actual_page_semantic = ""
        try:
            actual_page_semantic = self._dialog_surface_page_semantic(root)
            registered = tuple(
                getattr(root, "_registered_scroll_regions", ()) or ()
            )
            registered_ids = {id(scroll) for scroll in registered}
            discovered = tuple(root.findChildren(QScrollArea))
            deliberate: list[QScrollArea] = []
            seen_ids: set[int] = set()
            for scroll in (*registered, *discovered):
                scroll_id = id(scroll)
                if scroll_id in seen_ids:
                    continue
                if scroll.window() is not root:
                    continue
                is_deliberate = (
                    scroll_id in registered_ids
                    or bool(scroll.property("dialogScrollRegion"))
                )
                if not is_deliberate:
                    continue
                seen_ids.add(scroll_id)
                deliberate.append(scroll)
            active_scrolls = tuple(
                scroll
                for scroll in deliberate
                if scroll.window() is root
                and scroll.isVisibleTo(root)
                and scroll.verticalScrollBarPolicy()
                != Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
            dialog_scroll_audit.update({
                "applicable": bool(deliberate),
                "registered_count": len(deliberate),
                "active_count": len(active_scrolls),
                "issues": (
                    ["active-scroll-count"]
                    if deliberate and len(active_scrolls) != 1 else []
                ),
                "passed": not deliberate or len(active_scrolls) == 1,
            })
            if deliberate and len(active_scrolls) != 1:
                warnings.append({
                    "kind": (
                        "multiple-active-vertical-scroll-regions"
                        if len(active_scrolls) > 1
                        else "missing-active-vertical-scroll-region"
                    ),
                    "count": len(active_scrolls),
                    "registered_count": len(deliberate),
                    "scrolls": [
                        str(
                            scroll.accessibleName()
                            or scroll.objectName()
                            or type(scroll).__name__
                        )
                        for scroll in active_scrolls
                    ],
                })
            if len(active_scrolls) == 1:
                scroll = active_scrolls[0]
                content = scroll.widget()
                viewport = scroll.viewport()
                footer = getattr(root, "_pinned_footer", None)
                footer_visible = bool(
                    footer is not None and footer.isVisibleTo(root)
                )
                footer_height = (
                    max(0, int(footer.height())) if footer_visible else 0
                )
                footer_top = (
                    int(footer.mapTo(root, footer.rect().topLeft()).y())
                    if footer_visible else 0
                )
                viewport_top = int(
                    viewport.mapTo(root, viewport.rect().topLeft()).y()
                )
                content_layout = content.layout() if content is not None else None
                base_margins = getattr(root, "_scroll_base_margins", {}) or {}
                base = base_margins.get(id(scroll))
                layout_clearance = -1
                if content_layout is not None and base is not None:
                    layout_clearance = (
                        int(content_layout.contentsMargins().bottom())
                        - int(base[3])
                    )
                declared = scroll.property("footerClearance")
                declared_clearance = -1 if declared is None else int(declared)
                size_hint_height = (
                    int(content.sizeHint().height()) if content is not None else 0
                )
                minimum_hint_height = (
                    int(content.minimumSizeHint().height())
                    if content is not None else 0
                )
                visible_content_bottom = 0
                if content is not None:
                    for descendant in content.findChildren(QWidget):
                        if (
                            descendant.window() is not root
                            or not descendant.isVisibleTo(content)
                        ):
                            continue
                        descendant_top = descendant.mapTo(
                            content,
                            descendant.rect().topLeft(),
                        )
                        visible_content_bottom = max(
                            visible_content_bottom,
                            int(descendant_top.y()) + int(descendant.height()),
                        )
                content_height = (
                    max(
                        int(content.height()),
                        int(content.minimumHeight()),
                        visible_content_bottom,
                    )
                    if content is not None else 0
                )
                vertical = scroll.verticalScrollBar()
                scroll_span = max(
                    0,
                    int(vertical.maximum()) - int(vertical.minimum()),
                )
                last_body_child_bottom_at_scroll_end = (
                    viewport_top
                    + max(0, visible_content_bottom - scroll_span)
                )
                require_no_scroll = bool(
                    capture_label.startswith("purchase-confirmation-")
                    or capture_label.startswith("purchase-error-")
                    or capture_label.startswith("growth-charge-")
                )
                metrics = {
                    "registered_count": len(deliberate),
                    "active_count": len(active_scrolls),
                    "footer_visible": footer_visible,
                    "footer_height": footer_height,
                    "footer_top": footer_top,
                    "viewport_top": viewport_top,
                    "viewport_height": int(viewport.height()),
                    "declared_clearance": declared_clearance,
                    "layout_clearance": layout_clearance,
                    "content_height": content_height,
                    "content_size_hint_height": size_hint_height,
                    "content_minimum_size_hint_height": minimum_hint_height,
                    "scroll_minimum": int(vertical.minimum()),
                    "scroll_maximum": int(vertical.maximum()),
                    "last_body_child_bottom": visible_content_bottom,
                    "last_body_child_bottom_at_scroll_end": (
                        last_body_child_bottom_at_scroll_end
                    ),
                    "require_no_scroll": require_no_scroll,
                }
                issue_codes = dialog_scroll_geometry_issue_codes(**metrics)
                required_content_height = max(
                    content_height,
                    minimum_hint_height,
                )
                reachable_content_height = (
                    int(viewport.height())
                    + scroll_span
                )
                dialog_scroll_audit = {
                    "applicable": True,
                    "scroll_name": str(
                        scroll.accessibleName()
                        or scroll.objectName()
                        or type(scroll).__name__
                    ),
                    **metrics,
                    "viewport_bottom": viewport_top + int(viewport.height()),
                    "required_content_height": required_content_height,
                    "reachable_content_height": reachable_content_height,
                    "issues": list(issue_codes),
                    "passed": not issue_codes,
                }
                for issue_code in issue_codes:
                    if issue_code == "active-scroll-count":
                        continue
                    if issue_code == "footer-clearance-mismatch":
                        issue_kind = (
                            "insufficient-footer-scroll-clearance"
                            if declared_clearance < footer_height
                            else "excess-footer-scroll-clearance"
                        )
                    else:
                        issue_kind = {
                            "footer-layout-clearance-mismatch": (
                                "footer-layout-clearance-mismatch"
                            ),
                            "footer-viewport-overlap": (
                                "footer-overlaps-scroll-viewport"
                            ),
                            "unreachable-scroll-content": (
                                "unreachable-scroll-content"
                            ),
                        }.get(issue_code, issue_code)
                    warnings.append({
                        "kind": issue_kind,
                        "widget": type(scroll).__name__,
                        "object_name": str(scroll.objectName() or ""),
                        **metrics,
                    })
        except Exception as exc:
            dialog_scroll_audit = {
                "applicable": True,
                "registered_count": int(
                    dialog_scroll_audit.get("registered_count", 0) or 0
                ),
                "active_count": int(
                    dialog_scroll_audit.get("active_count", 0) or 0
                ),
                "issues": ["dialog-scroll-contract-audit-error"],
                "exception": type(exc).__name__,
                "passed": False,
            }
            warnings.append({
                "kind": "dialog-scroll-contract-audit-error",
                "exception": type(exc).__name__,
            })
        if coverage_surface or expected_page_semantic:
            identity_issues: list[str] = []
            if not coverage_surface:
                identity_issues.append("missing-scroll-coverage-surface")
            if not expected_page_semantic:
                identity_issues.append("missing-scroll-page-semantic")
            elif actual_page_semantic != expected_page_semantic:
                identity_issues.append("scroll-surface-page-mismatch")
            dialog_scroll_audit.update({
                "surface": coverage_surface,
                "expected_page_semantic": expected_page_semantic,
                "actual_page_semantic": actual_page_semantic,
                "issues": list(dict.fromkeys([
                    *list(dialog_scroll_audit.get("issues", ()) or ()),
                    *identity_issues,
                ])),
            })
            dialog_scroll_audit["passed"] = bool(
                dialog_scroll_audit.get("passed", False)
                and not identity_issues
            )
            for issue in identity_issues:
                warnings.append({
                    "kind": issue,
                    "surface": coverage_surface,
                    "expected_page_semantic": expected_page_semantic,
                    "actual_page_semantic": actual_page_semantic,
                })
        self._last_dialog_scroll_audit = dialog_scroll_audit
        for scroll in root.findChildren(QAbstractScrollArea):
            try:
                if scroll.window() is not root or not scroll.isVisibleTo(root):
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

    @staticmethod
    def _text_candidate_is_intentionally_scrolled_out(
        candidate: QWidget,
        root: QWidget,
    ) -> bool:
        """Narrowly exempt content wholly outside a reachable scroll viewport."""

        ancestor = candidate.parentWidget()
        while ancestor is not None:
            if isinstance(ancestor, QAbstractScrollArea):
                viewport = ancestor.viewport()
                if viewport is not None:
                    origin = candidate.mapTo(
                        viewport,
                        candidate.rect().topLeft(),
                    )
                    horizontal = ancestor.horizontalScrollBar()
                    vertical = ancestor.verticalScrollBar()
                    horizontal_scrollable = bool(
                        ancestor.horizontalScrollBarPolicy()
                        != Qt.ScrollBarPolicy.ScrollBarAlwaysOff
                        and int(horizontal.maximum()) > int(horizontal.minimum())
                    )
                    vertical_scrollable = bool(
                        ancestor.verticalScrollBarPolicy()
                        != Qt.ScrollBarPolicy.ScrollBarAlwaysOff
                        and int(vertical.maximum()) > int(vertical.minimum())
                    )
                    if intentional_scroll_viewport_exemption(
                        candidate_rect=[
                            int(origin.x()),
                            int(origin.y()),
                            int(candidate.width()),
                            int(candidate.height()),
                        ],
                        viewport_rect=[
                            int(viewport.rect().x()),
                            int(viewport.rect().y()),
                            int(viewport.width()),
                            int(viewport.height()),
                        ],
                        horizontal_scrollable=horizontal_scrollable,
                        vertical_scrollable=vertical_scrollable,
                    ):
                        return True
            if ancestor is root:
                break
            ancestor = ancestor.parentWidget()
        return False

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
                # A child-owned dialog can remain in QObject ancestry while
                # painting in a separate native window. It is not part of a
                # grab of ``root`` and must be audited with its own surface.
                if candidate.window() is not root.window():
                    continue
                if not candidate.isVisibleTo(root):
                    continue
                if int(candidate.width()) <= 0 or int(candidate.height()) <= 0:
                    continue
                text = str(candidate.text() or "").strip()
                visible_region = candidate.visibleRegion()
                if visible_region is None or visible_region.isEmpty():
                    if _UiFaceCaptureRunner._text_candidate_is_intentionally_scrolled_out(
                        candidate,
                        root,
                    ):
                        continue
                    warnings.append({
                        "kind": "empty-visible-region",
                        "widget": type(candidate).__name__,
                        "object_name": str(candidate.objectName() or ""),
                        "text": text[:120],
                        "width": int(candidate.width()),
                        "height": int(candidate.height()),
                        "required_height": 0,
                        "horizontal_clip": False,
                        "vertical_clip": False,
                        "ancestor_clip_horizontal": False,
                        "ancestor_clip_vertical": False,
                        "empty_visible_region": True,
                    })
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
                    # QLabel clips painted glyphs, not the cursor advance after
                    # the final glyph.  At fractional/high-DPI scaling the
                    # advance can round several pixels wider than fully visible
                    # ink (especially in padded badges and tabular values).
                    # Tight ink bounds retain real truncation failures without
                    # rejecting complete text at the style boundary.
                    ink_width = int(metrics.tightBoundingRect(text).width())
                    horizontal_clip = ink_width > available_width + 2
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

    def _reserve_capture_identity(
        self,
        label: str,
    ) -> tuple[int, str, str, str]:
        """Reserve immutable identity before any delayed or re-entrant Qt work."""

        capture_id = int(self._capture_index)
        identity = (
            capture_id,
            str(label),
            str(getattr(self, "_active_fixture_source", "")),
            str(getattr(self, "_active_fixture_expected_label", "")),
        )
        self._capture_index = capture_id + 1
        return identity

    def _capture_and_advance(
        self,
        label: str,
        widget: Any | None = None,
        *,
        capture_delay_ms: int = 260,
        before_capture: Callable[[], None] | None = None,
        close_ms: int | None = None,
        close_callback: Callable[[], None] | None = None,
        next_ms: int = 900,
    ) -> None:
        capture_identity = self._reserve_capture_identity(label)
        trace = getattr(globals().get("logger"), "info", None)
        if callable(trace):
            trace(
                "Anki Garden capture scheduled: label=%s identity=%r",
                label,
                capture_identity,
            )
        scheduled_label = capture_identity[1]
        self._capture_requested_monotonic[scheduled_label] = time.perf_counter()
        capture_delay = max(20, int(capture_delay_ms))
        requested_next = max(80, int(next_ms))
        requested_close = (
            max(60, int(close_ms))
            if close_callback is not None and close_ms is not None
            else capture_delay + 180
        )
        if widget is mw:
            # Position the live WebEngine window before the existing async
            # settle delay. Moving it again in the screenshot callback can
            # yield an unpainted compositor frame on macOS.
            self._move_to_capture_display(widget)
            if not self._activate_current_process_window(widget):
                logger.debug(
                    "Anki Garden capture: foreground request is still settling"
                )

        def advance_after_capture() -> None:
            if close_callback is None:
                self._next_after(max(80, requested_next - capture_delay))
                return

            def close_then_advance() -> None:
                try:
                    close_callback()
                except Exception as exc:
                    self._failures.append({
                        "label": scheduled_label,
                        "reason": (
                            "Capture cleanup callback raised "
                            f"{type(exc).__name__}"
                        ),
                    })
                    logger.exception(
                        "Anki Garden capture: cleanup failed for %s",
                        scheduled_label,
                    )
                finally:
                    self._next_after(
                        max(80, requested_next - requested_close)
                    )

            QTimer.singleShot(
                max(20, requested_close - capture_delay),
                close_then_advance,
            )

        def capture_ready(identity: tuple[int, str, str, str]) -> None:
            try:
                if before_capture is not None:
                    before_capture()
                self._capture_now(
                    identity[1],
                    widget,
                    capture_identity=identity,
                )
            except Exception as exc:
                self._failures.append({
                    "label": identity[1],
                    "reason": (
                        "Scheduled capture callback raised "
                        f"{type(exc).__name__}"
                    ),
                })
                logger.exception(
                    "Anki Garden capture: scheduled capture failed for %s",
                    identity[1],
                )
            finally:
                # Capture, cleanup, and fixture advancement must be strictly
                # ordered. Independent timers can all become due while Qt is
                # busy; _capture_now() pumps events and would otherwise close
                # the surface or replace resize provenance before grabbing it.
                advance_after_capture()

        QTimer.singleShot(
            capture_delay,
            lambda identity=capture_identity: capture_ready(identity),
        )

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
        footer_visible = bool(footer.isVisibleTo(dialog))
        footer_top = (
            int(footer.mapTo(dialog, footer.rect().topLeft()).y())
            if footer_visible else 0
        )
        for button in target_row:
            viewport_top = int(button.mapTo(viewport, button.rect().topLeft()).y())
            viewport_bottom = viewport_top + int(button.height())
            dialog_top = int(button.mapTo(dialog, button.rect().topLeft()).y())
            dialog_bottom = dialog_top + int(button.height())
            if viewport_top < 0 or viewport_bottom > int(viewport.height()):
                issues.append(f"{button.text()!r} was not fully inside the scroll viewport")
            if footer_visible and dialog_bottom > footer_top:
                issues.append(f"{button.text()!r} extended beneath the Nursery footer")
        passed = not issues
        self._capture_annotations[label] = {
            "nursery_footer_clearance_audited": True,
            "catalog_row": row,
            "action_count": len(target_row),
            "footer_visible": footer_visible,
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
                break
        for scroll in settings_dialog.findChildren(QAbstractScrollArea):
            try:
                scroll.verticalScrollBar().setValue(0)
                scroll.horizontalScrollBar().setValue(0)
            except Exception:
                logger.debug(
                    "Anki Garden capture: could not reset Settings scroll state",
                    exc_info=True,
                )

    @staticmethod
    def _show_reduced_motion_fixture(dialog: Any) -> None:
        control = dialog.behavior.reduced_motion
        control.setChecked(True)
        controls_scroll = getattr(dialog.behavior, "controls_scroll", None)
        ensure_controls = getattr(controls_scroll, "ensureWidgetVisible", None)
        if callable(ensure_controls):
            ensure_controls(control, 0, 28)
        for scroll in dialog.findChildren(QAbstractScrollArea):
            if str(scroll.accessibleName() or "") == "Display settings":
                scroll.ensureWidgetVisible(control, 0, 20)
                break

    def _capture_metric(
        self,
        metric: str,
        label: str,
        *,
        restore_callback: Callable[[], None] | None = None,
    ) -> None:
        dashboard = getattr(self.app, "dashboard", None)
        if dashboard is None:
            if restore_callback is not None:
                restore_callback()
            self._next_after(200)
            return
        dialog = getattr(dashboard, "progress_dialog", None)
        if dialog is None:
            self._failures.append({
                "label": label,
                "reason": "Garden metric dialog was unavailable",
            })
            if restore_callback is not None:
                restore_callback()
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
            if restore_callback is not None:
                restore_callback()
            self._next_after(200)
            return
        navigation.set_current(metric)
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        dialog.setModal(False)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

        def _dialog_ready() -> None:
            def close_metric() -> None:
                try:
                    self._close_widget(dialog)
                finally:
                    if restore_callback is not None:
                        restore_callback()

            self._capture_and_advance(
                label,
                dialog,
                capture_delay_ms=260,
                close_callback=close_metric,
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
            on_error=restore_callback,
        )

    def _capture_starter_deck_browser(self) -> None:
        self._switch_surface("overview")

        def enter_fresh_deck_browser() -> None:
            self._switch_surface("deckBrowser")
            QTimer.singleShot(
                500,
                lambda: self._wait_for_home_surface(
                    "deckBrowser",
                    "starter-deck-browser-home",
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
                "starter-overview-home",
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
        from .models.state import OnboardingStep
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
        progress = self.app.storage.state.onboarding
        if progress.step == OnboardingStep.INTRODUCTION:
            self.app.engine.enter_starter_nursery()
            progress = self.app.storage.state.onboarding
        if progress.step == OnboardingStep.NURSERY:
            self.app.engine.select_starter_species(species)
            progress = self.app.storage.state.onboarding
        if (
            progress.step != OnboardingStep.CONFIRMATION
            or progress.pending_species != species
        ):
            self._failures.append({
                "label": "starter-selection-confirmation",
                "reason": "Starter confirmation did not reach its persisted source state",
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

    def _replace_capture_state(self, state: Any) -> Callable[[], None]:
        """Install one in-memory fixture and return an idempotent restoration."""

        storage = self.app.storage
        engine = self.app.engine
        original_storage_state = storage.state
        original_engine_state = engine.state
        restored = False
        storage.state = state
        engine.state = state

        def restore() -> None:
            nonlocal restored
            if restored:
                return
            restored = True
            dashboard = getattr(self.app, "dashboard", None)
            if dashboard is not None:
                dashboard._starter_placement_active = False
                dashboard._placement_draft = None
                dashboard.scene.finish_move("Capture fixture restored.")
                dashboard.rearrange_bar.hide()
                dashboard.rearrange_bar.cancel.setText("Cancel")
                dashboard.toast_region.clear()
            storage.state = original_storage_state
            engine.state = original_engine_state
            if dashboard is not None:
                dashboard.refresh_all()

        return restore

    def _capture_starter_placement(self) -> None:
        from .models.state import GardenState, OnboardingProgress, OnboardingStep

        def ready() -> None:
            dashboard = getattr(self.app, "dashboard", None)
            if dashboard is None:
                self._next_after(200)
                return
            fixture = GardenState()
            fixture.onboarding = OnboardingProgress(
                step=OnboardingStep.PLACEMENT,
                pending_species="rose",
            )
            restore = self._replace_capture_state(fixture)
            dashboard._starter_placement_active = False
            dashboard._placement_draft = None
            dashboard.scene.finish_move("Preparing starter placement capture.")
            dashboard.rearrange_bar.hide()
            dashboard._starter_setup_dismissed = False
            dashboard.refresh_all()
            dashboard._begin_starter_placement()

            def stabilize_placement() -> None:
                # A queued dashboard refresh may reconcile the transient
                # ``__starter__`` interaction before the grab. Reassert the
                # manifest-owned placement state at the capture boundary.
                if not (
                    dashboard._starter_placement_active
                    and dashboard.scene._interaction.placing
                ):
                    dashboard._begin_starter_placement()

            self._capture_annotations["starter-placement"] = {
                "passed": bool(
                    fixture.onboarding.step == OnboardingStep.PLACEMENT
                    and not fixture.plants
                    and dashboard.scene._interaction.placing
                ),
                "pending_species": fixture.onboarding.pending_species,
            }
            self._capture_and_advance(
                "starter-placement",
                dashboard,
                capture_delay_ms=420,
                before_capture=stabilize_placement,
                close_callback=restore,
                # High-DPI dashboard grabs can spend more than one second in
                # screenshot and geometry audits. Keep the placement fixture
                # authoritative until those synchronous checks finish; an
                # early restore makes the manifest disagree with the pixels.
                close_ms=2300,
                next_ms=2600,
            )

        self._with_dashboard(ready, failure_label="starter-placement")

    @staticmethod
    def _settle_onboarding_capture_geometry(dashboard: Any) -> None:
        """Reflow coachmark copy after its final font and width are live."""

        app = QApplication.instance()
        for _pass in range(2):
            dashboard._position_onboarding_coachmark()
            dashboard._sync_dashboard_content_minimum_height()
            if app is not None:
                app.processEvents()

    def _capture_starter_completion(self) -> None:
        from .models.state import (
            GardenState,
            OnboardingProgress,
            OnboardingStep,
            Plant,
            PlantMemory,
        )

        def ready() -> None:
            dashboard = getattr(self.app, "dashboard", None)
            if dashboard is None:
                self._next_after(200)
                return
            fixture = GardenState()
            plant = Plant(
                "capture_starter",
                "rose",
                "Briar",
                0,
                memories=[
                    PlantMemory("planted", "planted", fixture.daily_stats.day),
                    PlantMemory("nurture:first", "first_nurture", fixture.daily_stats.day),
                ],
            )
            fixture.plants = [plant]
            fixture.unlocked_species = [plant.species]
            fixture.starter_selection_complete = True
            fixture.active_plant_id = plant.plant_id
            fixture.onboarding = OnboardingProgress(
                step=OnboardingStep.COMPLETION,
                starter_plant_id=plant.plant_id,
            )
            restore = self._replace_capture_state(fixture)
            dashboard._starter_setup_dismissed = False
            dashboard.refresh_all()
            completion_message = str(
                dashboard.onboarding_message.text() or ""
            ).strip()
            self._capture_annotations["starter-completion"] = {
                "passed": bool(
                    fixture.onboarding.step == OnboardingStep.COMPLETION
                    and fixture.active_plant_id == plant.plant_id
                    and fixture.garden_setup_version == 0
                    and bool(completion_message)
                    and bool(dashboard.onboarding_action.text().strip())
                    and dashboard.onboarding_action.isVisibleTo(dashboard)
                    and dashboard.onboarding_action.isEnabled()
                    and bool(dashboard.dismiss_onboarding.text().strip())
                    and dashboard.dismiss_onboarding.isVisibleTo(dashboard)
                    and dashboard.dismiss_onboarding.isEnabled()
                ),
                "starter_plant_id": plant.plant_id,
                "garden_bed": 1,
            }
            self._capture_and_advance(
                "starter-completion",
                dashboard,
                capture_delay_ms=420,
                before_capture=lambda: self._settle_onboarding_capture_geometry(
                    dashboard
                ),
                close_callback=restore,
                close_ms=700,
                next_ms=980,
            )

        self._with_dashboard(ready, failure_label="starter-completion")

    def _capture_home_preview_phase(
        self,
        label: str,
        surface: str,
        phase: str,
    ) -> None:
        from .ui.home_widget import HomeWidgetSnapshot, render_home_widget

        self._close_top_level_dialogs()
        self._close_dashboard()
        controller = self.app._home_widget_controller
        if phase == "stale" and controller.snapshot.data is None:
            self.app._build_home_garden_html()
        original_snapshot = controller.snapshot
        original_cache = getattr(self.app, "_home_html_cache", None)
        original_revision = int(getattr(self.app, "_home_html_revision", -1))
        state_events = getattr(self.app, "state_events", None)
        current_revision = int(getattr(state_events, "revision", 0))
        error_message = {
            "error": "Garden preview unavailable",
            "stale": "Updating…",
        }.get(phase)
        fixture_snapshot = HomeWidgetSnapshot(
            request_id=original_snapshot.request_id + 1,
            phase=phase,
            data=original_snapshot.data if phase == "stale" else None,
            error_message=error_message,
            enable_animations=original_snapshot.enable_animations,
            reduced_motion=original_snapshot.reduced_motion,
        )
        controller.snapshot = fixture_snapshot
        self.app._home_html_cache = render_home_widget(fixture_snapshot)
        self.app._home_html_revision = current_revision
        restored = False

        def restore() -> None:
            nonlocal restored
            if restored:
                return
            restored = True
            controller.snapshot = original_snapshot
            self.app._home_html_cache = original_cache
            self.app._home_html_revision = original_revision

        alternate = "overview" if surface == "deckBrowser" else "deckBrowser"
        self._switch_surface(alternate)

        def enter_surface() -> None:
            self._switch_surface(surface)
            self._wait_for_home_surface(
                surface,
                label,
                lambda: self._capture_and_advance(
                    label,
                    mw,
                    capture_delay_ms=650,
                    close_callback=restore,
                    close_ms=720,
                    next_ms=980,
                ),
            )

        QTimer.singleShot(420, enter_surface)

    def _capture_onboarding_persistence_error(self) -> None:
        from .models.state import GardenState, OnboardingStep

        def ready() -> None:
            dashboard = getattr(self.app, "dashboard", None)
            if dashboard is None:
                self._next_after(200)
                return
            fixture = GardenState()
            restore_state = self._replace_capture_state(fixture)

            def restore() -> None:
                dashboard._onboarding_save_error = ""
                dashboard._last_onboarding_error_announcement = ""
                dashboard.toast_region.clear()
                restore_state()

            dashboard._starter_setup_dismissed = False
            dashboard.refresh_all()
            original_save = self.app.storage.save

            def fail_save() -> None:
                raise OSError("capture persistence failure")

            self.app.storage.save = fail_save
            try:
                dashboard._open_starter_nursery()
            finally:
                self.app.storage.save = original_save
            current = self.app.storage.state
            error_banner = dashboard.onboarding_error_banner
            error_copy = str(error_banner.message.text())
            self._capture_annotations["onboarding-persistence-error"] = {
                "passed": bool(
                    current.onboarding.step == OnboardingStep.INTRODUCTION
                    and not current.plants
                    and dashboard.onboarding_panel.isVisible()
                    and error_banner.isVisible()
                    and bool(dashboard.onboarding_title.text().strip())
                    and bool(error_copy.strip())
                    and dashboard.onboarding_action.isVisible()
                    and dashboard.onboarding_action.isEnabled()
                    and dashboard.dismiss_onboarding.isVisible()
                    and dashboard.dismiss_onboarding.isEnabled()
                    and bool(dashboard._onboarding_save_error)
                    and not dashboard.toast_region.isVisible()
                ),
                "onboarding_step": current.onboarding.step.value,
                "committed_plants": len(current.plants),
                "error_copy": error_copy,
            }
            self._capture_and_advance(
                "onboarding-persistence-error",
                dashboard,
                capture_delay_ms=420,
                before_capture=lambda: self._settle_onboarding_capture_geometry(
                    dashboard
                ),
                close_callback=restore,
                close_ms=700,
                next_ms=980,
            )

        self._with_dashboard(ready, failure_label="onboarding-persistence-error")

    def _capture_move_persistence_error(self) -> None:
        from .models.state import GardenState, Plant

        def ready() -> None:
            dashboard = getattr(self.app, "dashboard", None)
            if dashboard is None:
                self._next_after(200)
                return
            plant_id = "capture_move_rose"
            fixture = GardenState(
                unlocked_slots=3,
                plants=[
                    Plant(plant_id, "rose", "Briar", 0, growth_points=500),
                    Plant(
                        "capture_move_bonsai",
                        "bonsai",
                        "Juniper",
                        1,
                        growth_points=500,
                    ),
                ],
                active_plant_id=plant_id,
            )
            restore = self._replace_capture_state(fixture)
            dashboard.refresh_all()
            dashboard._begin_move(plant_id)
            draft = dashboard._placement_draft
            destinations = (
                self.app.engine.valid_destination_slots(draft)
                if draft is not None else
                []
            )
            origin = draft.current.get(plant_id) if draft is not None else None
            occupied_slots = {
                int(plant.slot_index)
                for plant in fixture.plants
                if plant.slot_index is not None
            }
            destination = next(
                (
                    slot
                    for slot in destinations
                    if slot != origin and int(slot) not in occupied_slots
                ),
                None,
            )
            if destination is None:
                self._failures.append({
                    "label": "move-persistence-error",
                    "reason": "No valid destination was available for the rollback fixture",
                })
                dashboard._cancel_move()
                restore()
                self._next_after(200)
                return
            before = deepcopy(self.app.storage.state.to_dict())
            original_save = self.app.storage.save

            def fail_save() -> None:
                raise OSError("capture persistence failure")

            self.app.storage.save = fail_save
            try:
                dashboard._place_plant(
                    plant_id,
                    int(destination),
                    dashboard._active_placement_token,
                )
            finally:
                self.app.storage.save = original_save
            after = self.app.storage.state.to_dict()
            retry_active = bool(dashboard.scene._interaction.placing)
            retry_selected = (
                dashboard.scene._interaction.dragged_id == plant_id
            )
            error_visible = bool(
                dashboard.rearrange_bar.isVisible()
                and dashboard.rearrange_bar.property("error")
                and bool(dashboard.rearrange_bar.title.text().strip())
                and dashboard.rearrange_bar.retry.isVisible()
                and dashboard.rearrange_bar.retry.isEnabled()
                and dashboard.rearrange_bar.cancel.isVisible()
                and dashboard.rearrange_bar.cancel.isEnabled()
            )
            self._capture_annotations["move-persistence-error"] = {
                "passed": bool(
                    before == after
                    and int(destination) not in occupied_slots
                    and retry_active
                    and retry_selected
                    and error_visible
                ),
                "selected_plant_id": plant_id,
                "destination_slot": int(destination),
                "destination_was_empty": int(destination) not in occupied_slots,
                "state_restored": before == after,
                "retry_active": retry_active,
                "retry_selected": retry_selected,
                "error_visible": error_visible,
            }

            def cleanup() -> None:
                dashboard._cancel_move()
                restore()

            self._capture_and_advance(
                "move-persistence-error",
                dashboard,
                capture_delay_ms=480,
                close_callback=cleanup,
                close_ms=720,
                next_ms=980,
            )

        self._with_dashboard(ready, failure_label="move-persistence-error")

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
                    "deck-browser-home",
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
                "overview-home",
                lambda: self._capture_and_advance(
                    "overview-home",
                    mw,
                    capture_delay_ms=650,
                    next_ms=1200,
                ),
            ),
        )

    def _capture_settings_home_preview_disabled(self) -> None:
        """Exercise the menu route with a visibly distinct, unsaved display state."""

        action = getattr(self.app, "_settings_action", None)
        if action is not None and hasattr(action, "trigger"):
            action.trigger()
        else:
            self.app.open_settings()

        def _ready() -> None:
            dialog = self._find_settings_dialog()
            toggle = getattr(getattr(dialog, "behavior", None), "show_home_widget", None)
            if dialog is None or toggle is None:
                self._failures.append({
                    "label": "settings-home-preview-disabled",
                    "reason": "Settings Home preview control was unavailable",
                })
                self._close_widget(dialog)
                self._next_after(300)
                return
            original = bool(toggle.isChecked())
            toggle.setChecked(False)

            def close_and_restore() -> None:
                toggle.setChecked(original)
                self._close_widget(dialog)

            self._wait_for(
                lambda: bool(
                    dialog.isVisible()
                    and not toggle.isChecked()
                    and dialog._draft_is_dirty()
                ),
                lambda: self._capture_and_advance(
                    "settings-home-preview-disabled",
                    dialog,
                    capture_delay_ms=400,
                    close_callback=close_and_restore,
                    close_ms=700,
                    next_ms=1200,
                ),
                tries=40,
                failure_label="settings-home-preview-disabled",
                failure_reason="Settings Home preview disabled draft did not become ready",
            )
        self._wait_for(
            lambda: bool(
                self._find_settings_dialog() is not None
                and self._find_settings_dialog().isVisible()
            ),
            _ready,
            tries=80,
            failure_label="settings-home-preview-disabled",
            failure_reason="Settings dialog did not open from the Anki menu action",
        )

    def _capture_full_garden(self) -> None:
        label = "full-garden"

        def ready() -> None:
            from .models.state import OnboardingStep

            dashboard = self.app.dashboard
            state = self.app.storage.state
            state.starter_selection_complete = True
            state.onboarding.step = OnboardingStep.DONE
            state.onboarding.pending_species = None
            if not state.onboarding.starter_plant_id and state.plants:
                state.onboarding.starter_plant_id = state.plants[0].plant_id
            page_scroll = getattr(dashboard, "dashboard_scroll", None)
            if page_scroll is not None:
                page_scroll.verticalScrollBar().setValue(0)
            scene = getattr(dashboard, "scene", None)
            if scene is not None:
                scene.setProperty("captureEvidenceKey", "full-garden-scene")
                dismiss = getattr(scene, "dismiss_selection", None)
                if callable(dismiss):
                    dismiss()
            toast = getattr(dashboard, "toast_region", None)
            clear_toast = getattr(toast, "clear", None)
            if callable(clear_toast):
                clear_toast()
            dashboard.refresh_all()
            refresh_onboarding = getattr(dashboard, "_refresh_onboarding", None)
            if callable(refresh_onboarding):
                refresh_onboarding()
            QApplication.processEvents()

            overlays = {
                name: getattr(dashboard, name, None)
                for name in (
                    "onboarding_panel",
                    "onboarding_error_banner",
                    "plant_card",
                    "plant_card_dock",
                    "rearrange_bar",
                    "toast_region",
                )
            }
            visible_overlays = [
                name
                for name, overlay in overlays.items()
                if overlay is not None and overlay.isVisibleTo(dashboard)
            ]
            scene_container = (
                page_scroll.viewport() if page_scroll is not None else dashboard
            )
            scene_evidence = self._widget_bounds_evidence(
                scene,
                scene_container,
            )
            page_scroll_value = (
                int(page_scroll.verticalScrollBar().value())
                if page_scroll is not None else 0
            )
            audit = {
                "onboarding_step": str(state.onboarding.step.value),
                "visible_overlays": visible_overlays,
                "overlay_free": not visible_overlays,
                "scene_bounds": list(scene_evidence.get("bounds", ()) or ()),
                "scene_contained": bool(scene_evidence.get("contained", False)),
                "page_scroll_value": page_scroll_value,
            }
            audit["passed"] = bool(
                audit["onboarding_step"] == "done"
                and audit["overlay_free"]
                and audit["scene_contained"]
                and page_scroll_value == 0
            )
            self._capture_annotations[label] = {
                "steady_state_visual": audit,
                "passed": bool(audit["passed"]),
            }
            self._capture_and_advance(
                label,
                dashboard,
                capture_delay_ms=500,
                next_ms=900,
            )

        self._with_dashboard(ready, failure_label=label)

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
        from .models.state import OnboardingStep
        from .ui.state_contracts import OnboardingState, onboarding_state_display

        plant_id = self._select_plant(activate=False)
        dashboard = getattr(self.app, "dashboard", None)
        if not plant_id or dashboard is None:
            self._close_dashboard()
            self._next_after(250)
            return
        state = self.app.storage.state
        state.starter_selection_complete = True
        state.onboarding.step = OnboardingStep.NURTURE
        state.onboarding.starter_plant_id = plant_id
        state.onboarding.pending_species = None
        config = getattr(self.app, "config", None)
        onboarding_version = (
            config.value("onboarding_version", 0)
            if config is not None and hasattr(config, "value") else 0
        )
        onboarding = onboarding_state_display(
            state,
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

        # ID 151 owns the resumable completion surface. This selection face
        # proves the normal post-onboarding scene, so choose the capture
        # harness destination before showing the anchored plant panel.
        ok, message = self.app.engine.finish_onboarding()
        if not ok:
            self._failures.append({
                "label": "selected-plant-nurtured",
                "reason": f"Completion could not be persisted before capture: {message}",
            })
        refresh = getattr(dashboard, "refresh_all", None)
        if callable(refresh):
            refresh()
        dashboard.scene.keep_card_open(plant_id)
        dashboard._on_scene_selection(plant_id)

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
        from .models.state import Fertilizer

        plant_id = self._select_plant()
        dashboard = getattr(self.app, "dashboard", None)
        if not plant_id or dashboard is None:
            self._close_dashboard()
            self._next_after(250)
            return
        snapshot = self._capture_fixture_state_snapshot(label)

        def cleanup() -> None:
            self._restore_capture_fixture_state(snapshot)

        state = self.app.storage.state
        plant = self.app.engine.plant_story(plant_id)
        try:
            if plant is not None:
                plant.fertilizer = None
            state.currency_balance = (
                0 if state_variant == "unaffordable" else 500
            )
            state.currency_transactions.clear()
            if state_variant == "active" and plant is not None:
                now = self.app.engine._now_seconds()
                plant.fertilizer = Fertilizer(
                    "basic",
                    1,
                    now + 3_600,
                    now,
                )
            refresh = getattr(dashboard, "refresh_all", None)
            if callable(refresh):
                refresh()
            fertilize = getattr(dashboard, "_open_fertilizer_menu", None)
            if not callable(fertilize):
                cleanup()
                self._close_dashboard()
                self._next_after(250)
                return
        except Exception:
            cleanup()
            raise

        def ready() -> None:
            dialog = getattr(dashboard, "fertilizer_dialog", None)

            def close_dialog() -> None:
                self._close_widget(dialog)
                cleanup()

            self._capture_and_advance(
                label,
                dialog,
                capture_delay_ms=220,
                close_callback=close_dialog,
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
                on_error=cleanup,
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
                label,
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
                label,
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

    def _capture_fixture_state_snapshot(
        self,
        label: str,
        *,
        exact_ledger_restore: bool = False,
    ) -> dict[str, Any]:
        """Take a capture-owned state boundary before a reversible fixture.

        A normal engine snapshot can roll back only within the current staged
        reward-ledger generation. Committing fixtures use a verified full
        SQLite backup instead, so cleanup restores both bounded state and all
        exact idempotency rows without relaxing production checkpoint rules.
        """

        engine = self.app.engine
        storage = self.app.storage
        plant_id_order = tuple(
            str(getattr(plant, "plant_id", "") or "")
            for plant in list(getattr(engine.state, "plants", ()) or ())
        )
        if not exact_ledger_restore:
            snapshot = engine._state_snapshot()
            setattr(snapshot, "capture_fixture_label", str(label))
            setattr(snapshot, "capture_plant_id_order", plant_id_order)
            return snapshot
        if os.environ.get("ANKI_GARDEN_CAPTURE_UI_FACES") != "1":
            raise RuntimeError(
                "Exact fixture backup is available only in capture mode"
            )
        if getattr(storage, "_reward_ledger", None) is None:
            raise RuntimeError(
                f"Capture fixture {label!r} requires an exact SQLite ledger"
            )
        has_staged = getattr(storage, "reward_ledger_has_staged_writes", None)
        if not callable(has_staged):
            raise RuntimeError("The capture ledger staging guard was unavailable")
        if has_staged():
            raise RuntimeError(
                f"Capture fixture {label!r} started with staged reward-ledger writes"
            )
        backup_path = Path(storage.create_development_backup())
        if backup_path.suffix != ".sqlite3":
            backup_path.unlink(missing_ok=True)
            raise RuntimeError(
                f"Capture fixture {label!r} could not create an exact ledger backup"
            )
        try:
            snapshot = engine._state_snapshot()
            setattr(snapshot, "capture_fixture_label", str(label))
            setattr(snapshot, "capture_plant_id_order", plant_id_order)
            setattr(snapshot, "capture_ledger_backup", backup_path)
            setattr(snapshot, "capture_restore_complete", False)
            return snapshot
        except Exception:
            backup_path.unlink(missing_ok=True)
            raise

    def _restore_capture_fixture_state(self, snapshot: dict[str, Any]) -> None:
        """Restore one capture boundary, including committed exact ledger rows."""

        if bool(getattr(snapshot, "capture_restore_complete", False)):
            return
        label = str(getattr(snapshot, "capture_fixture_label", "capture-fixture"))
        backup_value = getattr(snapshot, "capture_ledger_backup", None)
        plant_id_order = tuple(
            getattr(snapshot, "capture_plant_id_order", ()) or ()
        )
        try:
            if backup_value is None:
                self.app.engine._restore_state(snapshot)
            else:
                if os.environ.get("ANKI_GARDEN_CAPTURE_UI_FACES") != "1":
                    raise RuntimeError(
                        "Exact fixture restore is available only in capture mode"
                    )
                storage = self.app.storage
                ledger = getattr(storage, "_reward_ledger", None)
                if ledger is None:
                    raise RuntimeError("The capture reward ledger was unavailable")
                # The boundary required a clean ledger. Any staged rows now
                # belong to this disposable fixture and must not cross into
                # the restored database.
                if bool(getattr(ledger, "has_staged_writes", False)):
                    ledger.rollback_all()
                restored = storage.restore_development_backup(Path(backup_value))
                # Preserve the engine's long-lived state identity so existing
                # dialogs and controllers cannot retain a detached fixture.
                self.app.engine.state.__dict__.clear()
                self.app.engine.state.__dict__.update(restored.__dict__)
                storage.state = self.app.engine.state
            restored_state = self.app.engine.state
            restored_state.plants = restore_capture_plant_order(
                list(restored_state.plants),
                plant_id_order,
            )
            if backup_value is None:
                self.app.storage.save()
            else:
                # The exact database and in-memory state are authoritative at
                # this point. Mark completion before fallible UI refresh or
                # temporary-file cleanup so the consumed backup is never used
                # for a second restore attempt.
                setattr(snapshot, "capture_restore_complete", True)
                try:
                    Path(backup_value).unlink(missing_ok=True)
                except OSError:
                    logger.debug(
                        "Anki Garden capture: exact fixture backup cleanup deferred",
                        exc_info=True,
                    )
            if backup_value is None:
                setattr(snapshot, "capture_restore_complete", True)
            self._refresh_capture_dashboard()
        except Exception as exc:
            self._fatal_fixture_restore_failure = True
            self._failures.append({
                "label": label,
                "reason": (
                    "Capture fixture state restoration raised "
                    f"{type(exc).__name__}"
                ),
            })
            logger.exception(
                "Anki Garden capture: exact state restoration failed for %s",
                label,
            )
            raise

    def _prepare_growth_capture_fixture(
        self,
        *,
        populated: bool,
    ) -> tuple[dict[str, Any], str]:
        """Install one reversible, exact multi-plant Growth accounting fixture."""

        from .models.state import Plant, PlantMemory

        snapshot = self._capture_fixture_state_snapshot(
            "growth-populated" if populated else "growth-zero"
        )
        state = self.app.storage.state
        today = str(state.daily_stats.day)
        points = (1_250, 2_450, 7_950) if populated else (0, 700, 2_700)
        species = ("bonsai", "rose", "sunflower")
        plants = [
            Plant(
                plant_id=f"capture_growth_{plant_species}",
                species=plant_species,
                name=self.app.engine._generated_name(plant_species),
                slot_index=index,
                growth_points=points[index],
                planted_on=today,
                memories=[PlantMemory(
                    memory_id=f"capture-growth-planted-{index}",
                    kind="planted",
                    occurred_on=today,
                )],
                passive_growth_remainder_fifths=(
                    (2, 1, 3)[index] if populated else 0
                ),
            )
            for index, plant_species in enumerate(species)
        ]
        state.plants = plants
        state.unlocked_species = list(dict.fromkeys([
            *state.unlocked_species,
            *species,
        ]))
        state.unlocked_slots = max(3, int(state.unlocked_slots))
        state.active_plant_id = plants[0].plant_id
        state.starter_selection_complete = True
        state.onboarding.starter_plant_id = plants[0].plant_id
        stats = state.daily_stats
        stats.reviewed = 8 if populated else 0
        stats.correct = 7 if populated else 0
        stats.wrong = 1 if populated else 0
        stats.base_growth = 31 if populated else 0
        stats.streak_bonus_growth = 5 if populated else 0
        stats.fertilizer_growth = 4 if populated else 0
        stats.weather_growth = 3 if populated else 0
        stats.scenery_growth = 6 if populated else 0
        stats.booster_growth = 4 if populated else 0
        stats.plant_nurtured_growth = (
            {plants[0].plant_id: 36, plants[1].plant_id: 17}
            if populated else {}
        )
        stats.plant_passive_growth_fifths = (
            {
                plants[0].plant_id: 17,
                plants[1].plant_id: 36,
                plants[2].plant_id: 53,
            }
            if populated else {}
        )
        stats.plant_passive_growth_credited = (
            {
                plants[0].plant_id: 3,
                plants[1].plant_id: 7,
                plants[2].plant_id: 10,
            }
            if populated else {}
        )
        stats.plant_charge_growth = (
            {plants[1].plant_id: 25} if populated else {}
        )
        stats.plant_direct_reward_growth = (
            {plants[2].plant_id: 7} if populated else {}
        )
        stats.legacy_unattributed_growth = 0
        stats.legacy_plant_growth = {}
        stats.growth_accounting_stale = False
        stats.reconcile_growth_totals()
        return snapshot, plants[0].plant_id

    def _restore_growth_capture_fixture(self, snapshot: dict[str, Any]) -> None:
        self._restore_capture_fixture_state(snapshot)

    def _restore_reward_capture_fixture(self, snapshot: dict[str, Any]) -> None:
        """Restore reward fixtures without leaving presentation history behind."""

        self._restore_capture_fixture_state(snapshot)

    def _prepare_canonical_achievement_capture_fixture(
        self,
        *,
        streak_days: int = 0,
        daily_answers: int = 0,
        again_answers: int = 0,
        lifetime_answers: int = 0,
        non_again_run: int = 0,
        completed_ids: tuple[str, ...] = (),
    ) -> tuple[dict[str, Any], tuple[Any, ...]]:
        """Build saved achievement rows, then read only canonical projections."""

        from .achievements import ACHIEVEMENTS_BY_ID
        from .reward_presentation import achievement_presentations

        snapshot = self._capture_fixture_state_snapshot(
            "achievement-projection"
        )
        state = self.app.storage.state
        stats = state.daily_stats
        day_value = str(stats.day)
        completed_at = f"{day_value}T12:00:00+00:00"
        state.streak_days = max(0, int(streak_days))
        state.last_active_day = day_value if state.streak_days else ""
        state.lifetime_eligible_answers = max(0, int(lifetime_answers))
        state.total_reviews = state.lifetime_eligible_answers
        state.current_non_again_run = max(0, int(non_again_run))
        stats.reviewed = max(0, int(daily_answers))
        stats.wrong = min(stats.reviewed, max(0, int(again_answers)))
        stats.correct = max(0, stats.reviewed - stats.wrong)
        stats.completed_due_cards = False

        self.app.engine._ensure_achievements()
        for achievement in state.achievements.values():
            achievement.unlocked = False
            achievement.progress = 0.0
            achievement.unlocked_at = None
            achievement.rewarded_at = None
            achievement.reward_event_key = ""
            achievement.historical_backfill = False
        self.app.engine._refresh_achievement_progress()
        for achievement_id in completed_ids:
            if achievement_id not in ACHIEVEMENTS_BY_ID:
                raise ValueError(
                    f"unknown canonical capture achievement: {achievement_id}"
                )
            achievement = state.achievements[achievement_id]
            achievement.unlocked = True
            achievement.progress = 1.0
            achievement.unlocked_at = completed_at
            achievement.rewarded_at = completed_at
            achievement.reward_event_key = f"achievement:{achievement_id}"

        projections = achievement_presentations(state)
        if {item.achievement_id for item in projections} != set(ACHIEVEMENTS_BY_ID):
            raise RuntimeError(
                "canonical achievement registry did not project every capture row"
            )
        return snapshot, projections

    def _append_canonical_streak_reward_receipts(
        self,
        *,
        streak_days: int,
    ) -> tuple[str, ...]:
        """Record the exact current-day receipts shown by streak captures."""

        from .models.state import RewardReceipt

        state = self.app.storage.state
        day_value = str(state.daily_stats.day)
        correlation_id = f"answer:capture-streak-day-{max(0, int(streak_days))}"
        occurred_at = f"{day_value}T12:00:00+00:00"
        state.recent_reward_receipts = [
            receipt
            for receipt in state.recent_reward_receipts
            if not (
                receipt.scheduler_day == day_value
                and (
                    receipt.source in {"daily_activity", "weekly_streak"}
                    or (
                        receipt.source in {"achievement", "achievement_backfill"}
                        and receipt.source_id == "streak_7"
                    )
                )
            )
        ]
        receipts = [RewardReceipt(
            event_key=f"daily_activity:{day_value}",
            reward_type="coins",
            source="daily_activity",
            source_id=day_value,
            scheduler_day=day_value,
            correlation_id=correlation_id,
            occurred_at=occurred_at,
            amount=int(self.app.engine.DAILY_ACTIVITY_COINS),
            title="Daily activity reward",
        )]
        days = max(0, int(streak_days))
        if days > 0 and days % 7 == 0:
            first_cycle = bool(
                days == 7
                and state.achievements.get("streak_7") is not None
                and state.achievements["streak_7"].unlocked
            )
            receipts.append(RewardReceipt(
                event_key=(
                    "achievement:streak_7"
                    if first_cycle else
                    f"weekly_streak:{day_value}"
                ),
                reward_type="coins",
                source="achievement" if first_cycle else "weekly_streak",
                source_id="streak_7" if first_cycle else f"day_{days}",
                scheduler_day=day_value,
                correlation_id=correlation_id,
                occurred_at=occurred_at,
                amount=int(self.app.engine.WEEKLY_STREAK_COINS),
                title=(
                    "7-Day Anki Streak"
                    if first_cycle else
                    "Seven-day streak reward"
                ),
            ))
        state.recent_reward_receipts.extend(receipts)
        return tuple(receipt.source for receipt in receipts)

    def _prepare_reward_history_capture_fixture(
        self,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Create one canonical stacked reward plus three persisted Finds."""

        from .achievements import ACHIEVEMENTS_BY_ID
        from .garden_finds import (
            STANDARD_FIND_REGISTRY,
            STANDARD_POOL_ID,
            STANDARD_POOL_VERSION,
        )
        from .models.state import CurrencyTransaction, GardenFindOutcome, RewardReceipt
        from .reward_presentation import recent_garden_finds, recent_reward_summaries

        snapshot = self._capture_fixture_state_snapshot("reward-history")
        state = self.app.storage.state
        active = self.app.engine.active_plant() or next(
            (
                plant for plant in state.plants
                if bool(getattr(plant, "planted", False))
                and not bool(getattr(plant, "fully_grown", False))
            ),
            None,
        )
        if active is None:
            raise RuntimeError("reward capture requires one unfinished nurtured plant")

        day_value = "2026-08-21"
        state.recent_reward_receipts = []
        state.garden_find_outcomes = {}
        state.garden_find_daily_counts = {day_value: 3}
        state.garden_find_reward_daily_counts = {day_value: {}}
        state.currency_transactions = []
        state.currency_balance = 0

        self.app.engine._ensure_achievements()
        achievement_definition = ACHIEVEMENTS_BY_ID["streak_30"]
        achievement = state.achievements[achievement_definition.achievement_id]
        achievement.unlocked = True
        achievement.progress = 1.0
        achievement.unlocked_at = f"{day_value}T09:00:00+00:00"
        achievement.rewarded_at = achievement.unlocked_at
        achievement.reward_event_key = "achievement:streak_30"
        achievement.historical_backfill = False

        stacked_correlation = "capture-review:stacked-achievement"
        stacked_event_key = "achievement:streak_30"
        stacked_at = f"{day_value}T09:00:00+00:00"
        stack_receipts = [
            RewardReceipt(
                event_key=stacked_event_key,
                reward_type="coins",
                source="achievement",
                source_id=achievement_definition.achievement_id,
                scheduler_day=day_value,
                correlation_id=stacked_correlation,
                occurred_at=stacked_at,
                amount=achievement_definition.reward.coins,
                title=achievement_definition.name,
                description=achievement_definition.description,
            ),
            RewardReceipt(
                event_key=stacked_event_key,
                reward_type="inventory_item",
                source="achievement",
                source_id=achievement_definition.achievement_id,
                scheduler_day=day_value,
                correlation_id=stacked_correlation,
                occurred_at=stacked_at,
                amount=achievement_definition.reward.small_growth_charges,
                item_id="growth_charge_small",
                title=achievement_definition.name,
                description=achievement_definition.description,
            ),
        ]
        state.recent_reward_receipts.extend(stack_receipts)
        state.currency_balance = achievement_definition.reward.coins
        state.consumables["growth_charge_small"] = max(
            1,
            int(state.consumables.get("growth_charge_small", 0) or 0),
        )
        state.currency_transactions.append(CurrencyTransaction(
            transaction_id="capture-tx-achievement",
            event_key=stacked_event_key,
            reason=achievement_definition.name,
            delta=achievement_definition.reward.coins,
            balance=state.currency_balance,
            occurred_at=stacked_at,
            transaction_type="credit",
            source="achievement",
            source_id=achievement_definition.achievement_id,
            scheduler_day=day_value,
            correlation_id=stacked_correlation,
        ))

        reward_by_id = {
            reward.reward_id: reward for reward in STANDARD_FIND_REGISTRY
        }
        find_specs = (
            ("capture-find-growth", "find_morning_dew", "10:00:00"),
            ("capture-find-compost", "find_fertilizer", "10:05:00"),
            ("capture-find-coins", "find_coin_sprout", "10:10:00"),
        )
        for answer_key, reward_id, clock in find_specs:
            reward = reward_by_id[reward_id]
            occurred_at = f"{day_value}T{clock}+00:00"
            event_key = f"garden_find:{answer_key}:{STANDARD_POOL_ID}"
            correlation_id = f"capture-review:{answer_key}"
            item_id = reward.inventory_item_id or ""
            outcome = GardenFindOutcome(
                answer_key=answer_key,
                scheduler_day=day_value,
                status="hit",
                pool_id=STANDARD_POOL_ID,
                pool_version=STANDARD_POOL_VERSION,
                occurred_at=occurred_at,
                reward_id=reward.reward_id,
                reward_type=reward.reward_kind,
                amount=reward.amount,
                item_id=item_id,
                display_name=reward.display_name,
                description=reward.description,
                tier=reward.tier,
                artwork_ref=reward.artwork_ref,
                localization_key=reward.localization_key,
            )
            state.garden_find_outcomes[outcome.outcome_key] = outcome
            state.recent_reward_receipts.append(RewardReceipt(
                event_key=event_key,
                reward_type=reward.reward_kind,
                source="garden_find",
                source_id=reward.reward_id,
                scheduler_day=day_value,
                correlation_id=correlation_id,
                occurred_at=occurred_at,
                amount=reward.amount,
                item_id=item_id,
                plant_id=(active.plant_id if reward.reward_kind == "growth" else ""),
                title=reward.display_name,
                description=reward.description,
            ))
            state.garden_find_reward_daily_counts[day_value][reward.reward_id] = 1
            if event_key not in state.applied_reward_event_keys:
                state.applied_reward_event_keys.append(event_key)
            if answer_key not in state.processed_answer_keys:
                state.processed_answer_keys.append(answer_key)
            if reward.reward_kind == "coins":
                state.currency_balance += reward.amount
                state.currency_transactions.append(CurrencyTransaction(
                    transaction_id=f"capture-tx-{reward.reward_id}",
                    event_key=event_key,
                    reason=f"Garden Find: {reward.display_name}",
                    delta=reward.amount,
                    balance=state.currency_balance,
                    occurred_at=occurred_at,
                    transaction_type="credit",
                    source="garden_find",
                    source_id=reward.reward_id,
                    scheduler_day=day_value,
                    correlation_id=correlation_id,
                ))
            elif reward.reward_kind == "growth":
                active.growth_points += reward.amount
                state.daily_stats.plant_direct_reward_growth[active.plant_id] = (
                    int(state.daily_stats.plant_direct_reward_growth.get(
                        active.plant_id,
                        0,
                    ) or 0)
                    + reward.amount
                )
            elif reward.reward_kind == "inventory_item" and item_id:
                state.consumables[item_id] = max(
                    reward.amount,
                    int(state.consumables.get(item_id, 0) or 0),
                )

        if stacked_event_key not in state.applied_reward_event_keys:
            state.applied_reward_event_keys.append(stacked_event_key)
        summaries = recent_reward_summaries(state)
        findings = recent_garden_finds(state)
        stacked = next(
            summary for summary in summaries
            if summary.correlation_id == stacked_correlation
        )
        direct_growth = next(
            item for item in findings if item.reward_id == "find_morning_dew"
        )
        compost = next(
            item for item in findings if item.reward_id == "find_fertilizer"
        )
        annotation = {
            "stacked_correlation_id": stacked_correlation,
            "stacked_reward_types": [line.reward_type for line in stacked.lines],
            "stacked_receipt_count": len(stacked.receipts),
            "all_stacked_receipts_share_correlation": all(
                receipt.correlation_id == stacked_correlation
                for receipt in stacked.receipts
            ),
            "recent_find_ids": [item.reward_id for item in findings],
            "direct_growth_result": direct_growth.description,
            "direct_growth_has_passive_wording": (
                "passive" in direct_growth.description.lower()
            ),
            "rich_compost_item_id": compost.item_id,
            "rich_compost_result": compost.description,
        }
        annotation["passed"] = bool(
            annotation["stacked_receipt_count"] == 2
            and annotation["all_stacked_receipts_share_correlation"]
            and annotation["stacked_reward_types"] == [
                "coins",
                "inventory_item",
            ]
            and annotation["recent_find_ids"] == [
                "find_morning_dew",
                "find_fertilizer",
                "find_coin_sprout",
            ]
            and not annotation["direct_growth_has_passive_wording"]
            and annotation["rich_compost_item_id"]
            == reward_by_id["find_fertilizer"].inventory_item_id
        )
        return snapshot, annotation

    def _capture_growth_zero(self) -> None:
        def ready() -> None:
            snapshot, _plant_id = self._prepare_growth_capture_fixture(
                populated=False,
            )
            self._refresh_capture_dashboard()
            self._capture_progress_page_after(
                "growth",
                "growth-zero",
                restore_callback=lambda: self._restore_growth_capture_fixture(snapshot),
            )

        self._with_dashboard(ready)

    def _capture_growth_nonzero(self) -> None:
        def ready() -> None:
            snapshot, _plant_id = self._prepare_growth_capture_fixture(
                populated=True,
            )
            self._refresh_capture_dashboard()
            self._capture_progress_page_after(
                "growth",
                "growth-nonzero",
                restore_callback=lambda: self._restore_growth_capture_fixture(snapshot),
            )

        self._with_dashboard(ready)

    def _capture_streak_new(self) -> None:
        def ready() -> None:
            snapshot, _projections = (
                self._prepare_canonical_achievement_capture_fixture()
            )
            self._refresh_capture_dashboard()
            self._capture_metric(
                "streak",
                "streak-new",
                restore_callback=lambda: self._restore_reward_capture_fixture(
                    snapshot
                ),
            )

        self._with_dashboard(ready)

    def _capture_streak_active(self) -> None:
        def ready() -> None:
            from .achievements import ACHIEVEMENTS_BY_ID

            definition = ACHIEVEMENTS_BY_ID["streak_7"]
            streak_days = int(definition.progress_target)
            daily_answers = streak_days + 5
            snapshot, projections = (
                self._prepare_canonical_achievement_capture_fixture(
                    streak_days=streak_days,
                    daily_answers=daily_answers,
                    again_answers=2,
                    completed_ids=("streak_7",),
                )
            )
            receipt_sources = self._append_canonical_streak_reward_receipts(
                streak_days=streak_days,
            )
            from .reward_presentation import recurring_reward_presentations

            reward_rules = {
                rule.rule_id: rule
                for rule in recurring_reward_presentations(
                    self.app.storage.state,
                    self.app.engine,
                )
            }
            streak_projection = next(
                item for item in projections
                if item.achievement_id == "streak_7"
            )
            self._capture_annotations["streak-active"] = {
                "achievement_id": streak_projection.achievement_id,
                "achievement_name": streak_projection.name,
                "achievement_reward": streak_projection.reward_summary,
                "achievement_completed": streak_projection.completed,
                "achievement_target": streak_days,
                "daily_answers": daily_answers,
                "recurring_receipt_sources": list(receipt_sources),
                "daily_reward_earned": reward_rules["daily_activity"].awarded_today,
                "weekly_reward_earned": reward_rules["weekly_streak"].awarded_today,
                "passed": bool(
                    streak_projection.completed
                    and streak_projection.reward_coins == definition.reward.coins
                    and streak_projection.reward_small_growth_charges
                    == definition.reward.small_growth_charges
                    and streak_projection.reward_standard_growth_charges
                    == definition.reward.standard_growth_charges
                    and reward_rules["daily_activity"].awarded_today
                    and reward_rules["weekly_streak"].awarded_today
                ),
            }
            self._refresh_capture_dashboard()
            self._capture_metric(
                "streak",
                "streak-active",
                restore_callback=lambda: self._restore_reward_capture_fixture(
                    snapshot
                ),
            )

        self._with_dashboard(ready)

    def _capture_coins_zero(self) -> None:
        def ready() -> None:
            snapshot = self._capture_fixture_state_snapshot("coins-zero")
            state = self.app.storage.state
            state.currency_balance = 0
            state.currency_transactions.clear()
            state.recent_reward_receipts.clear()
            state.garden_find_outcomes.clear()
            state.garden_find_daily_counts.clear()
            state.garden_find_reward_daily_counts.clear()
            self._capture_annotations["coins-zero"] = {
                "recent_reward_count": 0,
                "recent_find_count": 0,
                "passed": True,
            }
            self._refresh_capture_dashboard()
            self._capture_metric(
                "currency",
                "coins-zero",
                restore_callback=lambda: self._restore_reward_capture_fixture(
                    snapshot
                ),
            )

        self._with_dashboard(ready)

    def _capture_coins_activity(self) -> None:
        def ready() -> None:
            snapshot, annotation = self._prepare_reward_history_capture_fixture()
            self._capture_annotations["coins-activity"] = annotation
            self._refresh_capture_dashboard()
            self._capture_metric(
                "currency",
                "coins-activity",
                restore_callback=lambda: self._restore_reward_capture_fixture(
                    snapshot
                ),
            )

        self._with_dashboard(ready)

    def _capture_progress_page(
        self,
        key: str,
        label: str,
        *,
        restore_callback: Callable[[], None] | None = None,
    ) -> None:
        restored = False

        def restore_once() -> None:
            nonlocal restored
            if restored:
                return
            restored = True
            if restore_callback is not None:
                restore_callback()

        self._with_dashboard(
            lambda: self._capture_progress_page_after(
                key,
                label,
                restore_callback=restore_once,
            ),
            failure_label=label,
            on_error=restore_once,
        )

    def _capture_collection_filter(
        self,
        selected: str,
        label: str,
        *,
        restore_callback: Callable[[], None] | None = None,
    ) -> None:
        """Open Collection, then apply its filter after the dialog refresh."""
        restored = False

        def restore_fixture() -> None:
            nonlocal restored
            if restored:
                return
            restored = True
            if restore_callback is not None:
                restore_callback()

        def after() -> None:
            dashboard = getattr(self.app, "dashboard", None)
            dialog = getattr(dashboard, "progress_dialog", None)
            navigation = getattr(dialog, "navigation", None) if dialog is not None else None
            if dashboard is None or dialog is None or navigation is None:
                self._failures.append({
                    "label": label,
                    "reason": "Garden Progress Collection was unavailable",
                })
                restore_fixture()
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
                if label == "collection-no-filter-matches":
                    no_results = getattr(dashboard, "collection_no_results", None)
                    collection_grid = getattr(dashboard, "collection_list", None)
                    scroll = getattr(collection_grid, "scroll", None)
                    if no_results is not None and scroll is not None:
                        scroll.ensureWidgetVisible(no_results, 0, 80)
                        QApplication.processEvents()
                        # Collection refreshes can replace the empty-state
                        # instance during that event turn. Audit the live
                        # instance that will actually be captured.
                        no_results = getattr(
                            dashboard,
                            "collection_no_results",
                            None,
                        )
                        collection_grid = getattr(
                            dashboard,
                            "collection_list",
                            None,
                        )
                        scroll = getattr(collection_grid, "scroll", None)
                    if no_results is not None and scroll is not None:
                        scroll.ensureWidgetVisible(no_results, 0, 80)
                        QApplication.processEvents()
                        no_results = getattr(
                            dashboard,
                            "collection_no_results",
                            no_results,
                        )
                        viewport = scroll.viewport()
                        origin = no_results.mapTo(
                            viewport,
                            no_results.rect().topLeft(),
                        )
                        bounds = [
                            int(origin.x()),
                            int(origin.y()),
                            int(no_results.width()),
                            int(no_results.height()),
                        ]
                        contained = bool(
                            no_results.isVisible()
                            and bounds[0] >= 0
                            and bounds[1] >= 0
                            and bounds[0] + bounds[2] <= int(viewport.width())
                            and bounds[1] + bounds[3] <= int(viewport.height())
                        )
                        self._capture_annotations[label] = {
                            "empty_state_visible": no_results.isVisible(),
                            "empty_state_text": "\n".join(
                                str(candidate.text())
                                for candidate in no_results.findChildren(QLabel)
                                if str(candidate.text()).strip()
                            ),
                            "empty_state_actions": sorted(
                                _displayed_button_text(candidate)
                                for candidate in no_results.findChildren(QAbstractButton)
                                if candidate.isVisible()
                                and _displayed_button_text(candidate)
                            ),
                            "filter_clear_visible": bool(
                                getattr(
                                    getattr(
                                        dashboard,
                                        "collection_filter_controls",
                                        None,
                                    ),
                                    "clear",
                                    None,
                                ) is not None
                                and dashboard.collection_filter_controls.clear.isVisible()
                                and dashboard.collection_filter_controls.clear.isEnabled()
                            ),
                            "empty_state_viewport_bounds": bounds,
                            "empty_state_viewport_size": [
                                int(viewport.width()),
                                int(viewport.height()),
                            ],
                            "passed": contained,
                        }

                def close_collection() -> None:
                    try:
                        self._close_widget(dialog)
                    finally:
                        restore_fixture()

                close_collection_once = self._one_shot_async_callback(
                    label,
                    close_collection,
                    on_error=restore_fixture,
                    advance_on_error=False,
                )

                self._capture_and_advance(
                    label,
                    dialog,
                    capture_delay_ms=420,
                    close_callback=close_collection_once,
                    close_ms=820,
                    next_ms=1160,
                )

            def collection_ready() -> bool:
                ready_state = bool(
                    dialog.isVisible()
                    and navigation.stack.currentIndex()
                    == navigation.keys.index("collection")
                    and dashboard._collection_filter == selected
                )
                if not ready_state or label != "collection-no-filter-matches":
                    return ready_state
                no_results = getattr(dashboard, "collection_no_results", None)
                return bool(no_results is not None and no_results.isVisible())

            self._wait_for(
                collection_ready,
                ready,
                tries=80,
                failure_label=label,
                failure_reason=f"Collection filter {selected!r} did not become ready",
                on_error=restore_fixture,
            )

        self._with_dashboard(
            after,
            failure_label=label,
            on_error=restore_fixture,
        )

    def _capture_progress_page_after(
        self,
        key: str,
        label: str,
        *,
        restore_callback: Callable[[], None] | None = None,
    ) -> None:
        dashboard = getattr(self.app, "dashboard", None)
        if dashboard is None:
            if restore_callback is not None:
                restore_callback()
            self._next_after(250)
            return
        dialog = getattr(dashboard, "progress_dialog", None)
        navigation = getattr(dialog, "navigation", None) if dialog is not None else None
        if dialog is None or navigation is None or key not in getattr(navigation, "keys", []):
            self._failures.append({
                "label": label,
                "reason": "Garden Progress dialog or requested page was unavailable",
            })
            if restore_callback is not None:
                restore_callback()
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
            if label in {
                "achievement-completed",
                "clear-recall-canonical-projection",
            }:
                annotation = dict(
                    self._capture_annotations.get(label, {}) or {}
                )
                annotation["achievement_filter"] = str(
                    getattr(dashboard, "_achievement_filter", "") or ""
                )
                self._capture_annotations[label] = annotation
            if label == "clear-recall-canonical-projection":
                achievement_grid = getattr(
                    dashboard,
                    "achievement_list",
                    None,
                )
                entries = list(
                    getattr(achievement_grid, "_entries", ()) or ()
                )
                target = next(
                    (
                        candidate
                        for candidate, _full_width in entries
                        if str(candidate.property("achievementId") or "")
                        == "retention_90"
                    ),
                    None,
                )
                scroll = getattr(achievement_grid, "scroll", None)
                annotation = dict(
                    self._capture_annotations.get(label, {}) or {}
                )
                layout = getattr(achievement_grid, "grid", None)
                singleton_cards: list[dict[str, Any]] = []
                if layout is not None:
                    for candidate, full_width in entries:
                        if (
                            full_width
                            or bool(candidate.property("excludedFromProgressGrid"))
                            or not bool(candidate.property("spansSingletonRow"))
                        ):
                            continue
                        layout_index = layout.indexOf(candidate)
                        if layout_index < 0:
                            continue
                        grid_row, grid_column, row_span, column_span = (
                            layout.getItemPosition(layout_index)
                        )
                        singleton_cards.append({
                            "achievement_id": str(
                                candidate.property("achievementId") or ""
                            ),
                            "grid_position": [
                                int(grid_row),
                                int(grid_column),
                            ],
                            "grid_span": [
                                int(row_span),
                                int(column_span),
                            ],
                        })
                annotation.update({
                    "achievement_grid_columns": int(
                        getattr(achievement_grid, "_columns", 0) or 0
                    ),
                    "singleton_span_cards": singleton_cards,
                    "singleton_spans_passed": bool(
                        len(singleton_cards) == 2
                        and all(
                            card["grid_position"][1] == 0
                            and card["grid_span"] == [1, 2]
                            for card in singleton_cards
                        )
                    ),
                })
                if target is not None and scroll is not None:
                    container = getattr(achievement_grid, "container", None)
                    if container is not None:
                        target_origin = target.mapTo(
                            container,
                            target.rect().topLeft(),
                        )
                        bar = scroll.verticalScrollBar()
                        bar.setValue(max(0, int(target_origin.y()) - 24))
                    scroll.ensureWidgetVisible(target, 0, 24)
                    QApplication.processEvents()
                    viewport = scroll.viewport()
                    origin = target.mapTo(
                        viewport,
                        target.rect().topLeft(),
                    )
                    bounds = [
                        int(origin.x()),
                        int(origin.y()),
                        int(target.width()),
                        int(target.height()),
                    ]
                    contained = bool(
                        not target.isHidden()
                        and bounds[0] >= 0
                        and bounds[1] >= 0
                        and bounds[0] + bounds[2] <= int(viewport.width())
                        and bounds[1] + bounds[3] <= int(viewport.height())
                    )
                    annotation.update({
                        "target_card_fully_visible": contained,
                        "target_card_viewport_bounds": bounds,
                        "target_card_viewport_size": [
                            int(viewport.width()),
                            int(viewport.height()),
                        ],
                    })
                else:
                    annotation.update({
                        "target_card_fully_visible": False,
                        "target_card_viewport_bounds": [],
                        "target_card_viewport_size": [],
                    })
                self._capture_annotations[label] = annotation

            def close_progress() -> None:
                try:
                    self._close_widget(dialog)
                finally:
                    if restore_callback is not None:
                        restore_callback()

            self._capture_and_advance(
                label,
                dialog,
                capture_delay_ms=360,
                close_callback=close_progress,
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
            on_error=restore_callback,
        )

    def _capture_progress_today(self) -> None:
        label = "progress-overview-redirect-growth"
        cleanup_holder: dict[str, Callable[[], None]] = {
            "callback": lambda: None,
        }

        def cleanup() -> None:
            cleanup_holder["callback"]()

        def after() -> None:
            snapshot, _plant_id = self._prepare_growth_capture_fixture(
                populated=True,
            )
            restored = False

            def restore_once() -> None:
                nonlocal restored
                if restored:
                    return
                restored = True
                self._restore_growth_capture_fixture(snapshot)

            cleanup_holder["callback"] = restore_once
            self._refresh_capture_dashboard()
            dashboard = getattr(self.app, "dashboard", None)
            dialog = getattr(dashboard, "progress_dialog", None)
            navigation = getattr(dialog, "navigation", None)
            if dialog is None or navigation is None:
                self._failures.append({
                    "label": label,
                    "reason": "Garden Progress was unavailable for the stale Overview redirect",
                })
                restore_once()
                self._next_after(200)
                return
            dialog.setWindowModality(Qt.WindowModality.NonModal)
            dialog.setModal(False)
            dialog.open_page("overview")

            def ready() -> None:
                def prepare_capture() -> None:
                    keys = list(getattr(navigation, "keys", ()) or ())
                    current_index = int(navigation.stack.currentIndex())
                    current_page = (
                        keys[current_index]
                        if 0 <= current_index < len(keys) else ""
                    )
                    growth_scroll = navigation.stack.currentWidget()
                    viewport = (
                        growth_scroll.viewport()
                        if isinstance(growth_scroll, QAbstractScrollArea) else
                        growth_scroll
                    )
                    QCoreApplication.sendPostedEvents(
                        None,
                        QEvent.Type.DeferredDelete,
                    )
                    QApplication.processEvents()
                    breakdowns = [
                        button
                        for button in growth_scroll.findChildren(QAbstractButton)
                        if button.isVisibleTo(growth_scroll)
                        and str(button.accessibleName()).strip()
                        == "Growth breakdown"
                    ]
                    breakdown = breakdowns[-1] if breakdowns else None
                    if breakdown is not None and not breakdown.isChecked():
                        breakdown.setChecked(True)
                        QApplication.processEvents()
                    direct_label = next(
                        (
                            candidate
                            for candidate in growth_scroll.findChildren(QLabel)
                            if candidate.isVisibleTo(growth_scroll)
                            and "Rewards and charges" in str(candidate.text())
                        ),
                        None,
                    )
                    if (
                        direct_label is not None
                        and isinstance(growth_scroll, QScrollArea)
                    ):
                        growth_scroll.ensureWidgetVisible(direct_label, 0, 24)
                        QApplication.processEvents()
                    visible_labels = [
                        candidate
                        for candidate in growth_scroll.findChildren(QLabel)
                        if candidate.isVisibleTo(growth_scroll)
                        and self._widget_bounds_evidence(
                            candidate,
                            viewport,
                        ).get("intersects", False)
                    ]
                    direct_label = next(
                        (
                            candidate for candidate in visible_labels
                            if "Rewards and charges" in str(candidate.text())
                        ),
                        None,
                    )
                    stats = self.app.storage.state.daily_stats
                    direct_amount = sum(
                        int(value or 0)
                        for mapping in (
                            stats.plant_charge_growth,
                            stats.plant_direct_reward_growth,
                        )
                        for value in dict(mapping or {}).values()
                    )
                    direct_value = next(
                        (
                            candidate for candidate in visible_labels
                            if str(candidate.text()).strip().replace(",", "")
                            == str(direct_amount)
                        ),
                        None,
                    )
                    if direct_label is not None:
                        direct_label.setProperty(
                            "captureEvidenceKey",
                            "direct-growth-label",
                        )
                    if direct_value is not None:
                        direct_value.setProperty(
                            "captureEvidenceKey",
                            "direct-growth-value",
                        )
                    label_evidence = self._widget_bounds_evidence(
                        direct_label,
                        viewport,
                    )
                    value_evidence = self._widget_bounds_evidence(
                        direct_value,
                        viewport,
                    )
                    direct_visual = {
                        "label": str(direct_label.text()) if direct_label is not None else "",
                        "amount": direct_amount,
                        "label_bounds": list(label_evidence.get("bounds", ()) or ()),
                        "value_bounds": list(value_evidence.get("bounds", ()) or ()),
                        "label_contained": bool(label_evidence.get("contained", False)),
                        "value_contained": bool(value_evidence.get("contained", False)),
                    }
                    direct_visual["passed"] = bool(
                        direct_amount > 0
                        and bool(direct_visual["label"].strip())
                        and direct_visual["label_contained"]
                        and direct_visual["value_contained"]
                    )
                    passed = bool(
                        current_page == "growth"
                        and "overview" not in keys
                        and direct_visual["passed"]
                    )
                    self._capture_annotations[label] = {
                        "requested_route": "overview",
                        "normalized_page": current_page,
                        "overview_registered": "overview" in keys,
                        "direct_growth_visual": direct_visual,
                        "passed": passed,
                    }
                    if not passed:
                        self._failures.append({
                            "label": label,
                            "reason": "The stale Overview route did not normalize to Plant Growth",
                        })

                self._capture_and_advance(
                    label,
                    dialog,
                    capture_delay_ms=360,
                    before_capture=prepare_capture,
                    close_callback=lambda: (
                        self._close_widget(dialog),
                        restore_once(),
                    ),
                    close_ms=760,
                    next_ms=1100,
                )

            self._wait_for(
                lambda: bool(
                    dialog.isVisible()
                    and navigation.stack.currentIndex()
                    == navigation.keys.index("growth")
                ),
                ready,
                tries=80,
                failure_label=label,
                failure_reason="The stale Overview route did not render Plant Growth",
                on_error=restore_once,
            )

        self._with_dashboard(
            after,
            failure_label=label,
            on_error=cleanup,
        )

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

    def _capture_known_uncollected_species_overview(self) -> None:
        """Prove known catalog identity, zero instances, and Rare mystery together."""

        label = "collection-known-not-collected-overview"
        if not self._ensure_development_stress_state():
            self._next_after(200)
            return
        dashboard = getattr(self.app, "dashboard", None)
        state = self.app.storage.state
        release_ready = list(self.app.engine.release_ready_species())
        if dashboard is None or not release_ready:
            self._failures.append({
                "label": label,
                "reason": "Known uncollected species fixture prerequisites were unavailable",
            })
            self._next_after(200)
            return
        species = str(release_ready[-1])
        original_plants = list(state.plants)
        original_unlocked = list(state.unlocked_species)
        original_active = state.active_plant_id
        restored = False

        def restore() -> None:
            nonlocal restored
            if restored:
                return
            restored = True
            state.plants = original_plants
            state.unlocked_species = original_unlocked
            state.active_plant_id = original_active
            self._refresh_capture_dashboard()

        state.plants = [plant for plant in state.plants if str(plant.species) != species]
        state.unlocked_species = [
            value for value in state.unlocked_species if str(value) != species
        ]
        if str(state.active_plant_id or "") not in {
            str(plant.plant_id) for plant in state.plants
        }:
            state.active_plant_id = ""
        builder = getattr(dashboard, "_build_species_overview_dialog", None)
        dialog = builder(species) if callable(builder) else None
        if dialog is None:
            restore()
            self._failures.append({
                "label": label,
                "reason": "Known uncollected species overview could not be built",
            })
            self._next_after(200)
            return
        rare_hidden = any(
            "Undiscovered Rare stage silhouette" in str(widget.accessibleName())
            for widget in dialog.findChildren(QLabel)
        )
        passed = bool(
            str(dialog.property("collectionState") or "") == "not-collected"
            and not any(str(plant.species) == species for plant in state.plants)
            and rare_hidden
        )
        self._capture_annotations[label] = {
            "species": species,
            "known_catalog_identity": True,
            "collected_instances": 0,
            "rare_mystery": rare_hidden,
            "passed": passed,
        }
        if not passed:
            self._failures.append({
                "label": label,
                "reason": "Known species, zero-instance, and Rare mystery contract did not agree",
            })
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        dialog.setModal(False)
        dialog.show()
        self._capture_and_advance(
            label,
            dialog,
            capture_delay_ms=420,
            close_callback=lambda: (self._close_widget(dialog), restore()),
            close_ms=820,
            next_ms=1160,
        )

    def _purchase_capture_snapshot(
        self,
        label: str,
        *,
        exact_ledger_restore: bool = False,
    ) -> tuple[dict[str, Any], Any] | None:
        """Return a reversible, canonical purchase fixture and active plant."""

        if not self._ensure_development_stress_state():
            self._failures.append({
                "label": label,
                "reason": "The canonical purchase fixture could not be prepared",
            })
            return None
        state = self.app.storage.state
        plant = state.plants[0] if state.plants else None
        if plant is None:
            self._failures.append({
                "label": label,
                "reason": "The purchase fixture had no target plant",
            })
            return None
        snapshot = self._capture_fixture_state_snapshot(
            label,
            exact_ledger_restore=exact_ledger_restore,
        )
        state.currency_balance = 5_000
        state.currency_transactions.clear()
        state.completed_purchase_requests.clear()
        plant.slot_index = 0
        plant.growth_points = 0
        plant.fertilizer = None
        plant.fertilizer_history.clear()
        state.active_plant_id = plant.plant_id
        state.starter_selection_complete = True
        return snapshot, plant

    def _restore_purchase_capture(self, snapshot: dict[str, Any]) -> None:
        self._restore_capture_fixture_state(snapshot)

    def _capture_purchase_dialog_fixture(self, label: str, variant: str) -> None:
        cleanup_holder: dict[str, Callable[[], None]] = {
            "callback": lambda: None,
        }

        def registered_cleanup() -> None:
            cleanup_holder["callback"]()

        def dashboard_ready() -> None:
            prepared = self._purchase_capture_snapshot(label)
            if prepared is None:
                self._next_after(200)
                return
            snapshot, plant = prepared
            cleanup_complete = False
            restore_catalog_override: Callable[[], None] = lambda: None

            def cleanup_fixture() -> None:
                nonlocal cleanup_complete
                if cleanup_complete:
                    return
                cleanup_complete = True
                restore_catalog_override()
                self._restore_purchase_capture(snapshot)

            cleanup_holder["callback"] = cleanup_fixture
            from dataclasses import replace
            from .environment import GROWTH_CHARGES
            from .models.state import Fertilizer
            from .purchases import PurchaseKind
            from .ui.dashboard import PurchaseConfirmationDialog

            state = self.app.storage.state
            engine = self.app.engine
            kind = PurchaseKind.GROWTH_CHARGE
            item_id = "growth_charge_small"
            target_id: str | None = None

            if variant in {"species", "loading"}:
                kind = PurchaseKind.SPECIES
                item_id = "sunflower"
                state.plants = [
                    item for item in state.plants if item.species != item_id
                ]
                state.unlocked_species = [
                    item for item in state.unlocked_species if item != item_id
                ]
            elif variant == "environment":
                kind = PurchaseKind.WEATHER
                item_id = "breeze"
                state.inventory["weather"] = [
                    value for value in state.inventory.get("weather", [])
                    if value != item_id
                ]
                if state.selected_weather == item_id:
                    state.selected_weather = "sunny"
            elif variant in {"fertilizer-application", "fertilizer-extension", "invalid-target"}:
                kind = PurchaseKind.FERTILIZER
                item_id = "basic"
                target_id = plant.plant_id
                if variant == "fertilizer-extension":
                    now = engine._now_seconds()
                    plant.fertilizer = Fertilizer("basic", 1, now + 2_700, now)
                elif variant == "invalid-target":
                    target_id = "missing-plant"
            elif variant == "bed":
                kind = PurchaseKind.BED
                item_id = "next"
                state.unlocked_slots = 2
            elif variant == "insufficient":
                state.currency_balance = 0
            elif variant == "unavailable":
                item_id = "missing-growth-charge"
            elif variant == "already-owned":
                kind = PurchaseKind.WEATHER
                item_id = "sunny"

            quote = engine.quote_purchase(
                kind,
                item_id,
                target_id=target_id,
            )
            dialog = PurchaseConfirmationDialog(
                self.app.dashboard,
                engine,
                quote,
            )
            original_confirmation = {
                "title": str(dialog.windowTitle()),
                "primary_label": _displayed_button_text(dialog.purchase_action),
                "price": int(dialog.quote.total_price),
                "ready": bool(dialog.quote.ready),
            }

            if variant == "loading":
                dialog._progress_motion_enabled = False
                dialog._set_submitting(True)
            elif variant == "persistence":
                original_save = self.app.storage.save

                def fail_save() -> None:
                    raise OSError("deterministic capture persistence failure")

                self.app.storage.save = fail_save
                try:
                    dialog._set_submitting(True)
                    dialog._commit()
                finally:
                    self.app.storage.save = original_save
            elif variant == "stale-price":
                original_spec = GROWTH_CHARGES[item_id]
                catalog_override_restored = False

                def restore_stale_price_catalog() -> None:
                    nonlocal catalog_override_restored
                    if catalog_override_restored:
                        return
                    catalog_override_restored = True
                    GROWTH_CHARGES[item_id] = original_spec

                restore_catalog_override = restore_stale_price_catalog
                GROWTH_CHARGES[item_id] = replace(
                    original_spec,
                    price=int(original_spec.price or 0) + 1,
                )
                try:
                    dialog._set_submitting(True)
                    dialog._commit()
                except Exception:
                    restore_stale_price_catalog()
                    raise
            elif variant == "stale-balance":
                state.currency_balance += 1
                dialog._set_submitting(True)
                dialog._commit()

            expected_status = str(
                expected_capture_state_profile(label).get("purchase_status", "")
            )
            actual_status = str(dialog.property("purchaseState") or "")
            error_variant = variant in {
                "insufficient",
                "persistence",
                "unavailable",
                "already-owned",
                "invalid-target",
                "stale-price",
                "stale-balance",
            }
            error_banner_visible = bool(
                dialog.status.text().strip()
                and not dialog.status.isHidden()
            )
            expected_disposition = {
                "fertilizer-application": "applied",
                "fertilizer-extension": "extended",
            }.get(variant, "")
            actual_disposition = quote.disposition.value
            visible_copy = "\n".join(
                (
                    _displayed_button_text(widget)
                    if isinstance(widget, QAbstractButton)
                    else str(widget.text())
                )
                for widget in (
                    list(dialog.findChildren(QLabel))
                    + list(dialog.findChildren(QAbstractButton))
                )
                if not widget.isHidden() and str(widget.text()).strip()
            )
            stale_variant = variant in {"stale-price", "stale-balance"}
            banned_noise = (
                "Not applicable",
                "Replaces nothing",
                "Quantity: 1",
                "Are you sure you want to purchase",
            ) + (() if stale_variant else ("Balance after purchase",))
            stale_terms_visible = bool(
                not stale_variant
                or (
                    "Preview" not in visible_copy
                    and "Proposed" not in visible_copy
                    and dialog.price_label.text()
                    == f"{dialog.presentation.price:,} Garden Coins"
                    and f"{max(0, int(dialog.quote.balance_after)):,}"
                    in dialog.balance_label.text()
                )
            )
            expected_primary = (
                str(dialog.presentation.processing_label)
                if variant == "loading" else
                "Choose another plant"
                if variant == "invalid-target" else
                str(dialog.presentation.primary_label)
            )
            primary_action = _displayed_button_text(dialog.purchase_action)
            canonical_primary_action = bool(
                primary_action
                and (
                    primary_action == expected_primary
                    if variant != "invalid-target" else
                    str(dialog._primary_route_override) == "garden"
                )
            )
            request_price_matches_quote = bool(
                int(dialog.request.expected_price) == int(dialog.quote.total_price)
            )
            request_balance_matches_state = bool(
                int(dialog.request.expected_balance)
                == int(state.currency_balance)
            )
            request_price_matches_registry = bool(
                variant != "stale-price"
                or int(dialog.request.expected_price)
                == int(GROWTH_CHARGES[item_id].price or 0)
                * max(1, int(dialog.request.quantity))
            )
            refreshed_request_matches_live_terms = bool(
                not stale_variant
                or (
                    request_price_matches_quote
                    and request_balance_matches_state
                    and request_price_matches_registry
                )
            )
            applicable_copy = bool(
                dialog.item_name.text().strip()
                and dialog.category.text().strip()
            )
            unavailable_terminal = variant == "unavailable"
            error_banner_required = variant in {
                "persistence",
                "invalid-target",
                "stale-price",
            }
            proposal_update_message = getattr(
                dialog.proposal_notice,
                "message",
                None,
            )
            proposal_update_text = str(
                proposal_update_message.text()
                if proposal_update_message is not None else ""
            ).strip()
            ready_balance_update = bool(
                variant != "stale-balance"
                or (
                    original_confirmation["ready"]
                    and bool(dialog.quote.ready)
                    and str(dialog.property("transactionPresentation") or "")
                    == "inline-balance-update"
                    and proposal_update_text == "Balance updated"
                    and not dialog.proposal_notice.isHidden()
                    and dialog.status.isHidden()
                    and dialog.purchase_action.isEnabled()
                    and not dialog.cost_summary.isHidden()
                    and str(dialog.windowTitle()) == original_confirmation["title"]
                    and _displayed_button_text(dialog.purchase_action)
                    == original_confirmation["primary_label"]
                    and actual_status != "insufficient_coins"
                )
            )
            stale_price_item_identity = bool(
                variant != "stale-price"
                or (
                    str(dialog.windowTitle()) == "Price changed"
                    and bool(dialog.item_name.text().strip())
                    and dialog.item_name.text().strip() == dialog.quote.item_name
                    and dialog.category.text().strip()
                )
            )
            self._capture_annotations[label] = {
                "purchase_kind": kind.value,
                "item_id": item_id,
                "expected_status": expected_status,
                "actual_status": actual_status,
                "expected_disposition": expected_disposition,
                "actual_disposition": actual_disposition,
                "applicable_copy": applicable_copy,
                "banned_noise_absent": not any(
                    value in visible_copy for value in banned_noise
                ),
                "primary_action": primary_action,
                "expected_primary_action": expected_primary,
                "expected_primary_source": (
                    "processing-presentation"
                    if variant == "loading" else
                    "target-route-override"
                    if variant == "invalid-target" else
                    "purchase-presentation"
                ),
                "canonical_primary_action": canonical_primary_action,
                "cost_summary_visible": not dialog.cost_summary.isHidden(),
                "unavailable_terminal": bool(
                    not unavailable_terminal
                    or (
                        dialog.cost_summary.isHidden()
                        and dialog.presentation.terminal
                        and _displayed_button_text(dialog.purchase_action)
                        == "Return to Nursery"
                    )
                ),
                "quantity": quote.quantity,
                "target_id": target_id or "",
                "error_banner_visible": error_banner_visible,
                "error_banner_required": error_banner_required,
                "stale_terms_visible": stale_terms_visible,
                "request_expected_price": int(dialog.request.expected_price),
                "live_quote_price": int(dialog.quote.total_price),
                "request_expected_balance": int(dialog.request.expected_balance),
                "live_committed_balance": int(state.currency_balance),
                "request_price_matches_registry": request_price_matches_registry,
                "refreshed_request_matches_live_terms": (
                    refreshed_request_matches_live_terms
                ),
                "original_confirmation": original_confirmation,
                "proposal_update_text": proposal_update_text,
                "ready_balance_update": ready_balance_update,
                "stale_price_item_identity": stale_price_item_identity,
                "passed": bool(
                    actual_status == expected_status
                    and (
                        not expected_disposition
                        or actual_disposition == expected_disposition
                    )
                    and applicable_copy
                    and not any(value in visible_copy for value in banned_noise)
                    and canonical_primary_action
                    and (
                        not unavailable_terminal
                        or (
                            dialog.cost_summary.isHidden()
                            and dialog.presentation.terminal
                        )
                    )
                    and quote.quantity == 1
                    and (
                        not error_variant
                        or not error_banner_required
                        or error_banner_visible
                    )
                    and stale_terms_visible
                    and refreshed_request_matches_live_terms
                    and ready_balance_update
                    and stale_price_item_identity
                ),
            }
            if not self._capture_annotations[label]["passed"]:
                self._failures.append({
                    "label": label,
                    "reason": "Purchase confirmation fixture state did not match its declared status",
                })

            dialog.setWindowModality(Qt.WindowModality.NonModal)
            dialog.setModal(False)
            self._move_to_capture_display(dialog)
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()

            def close_dialog() -> None:
                if dialog._submitting:
                    dialog._set_submitting(False)
                try:
                    self._close_widget(dialog)
                finally:
                    cleanup_fixture()

            self._capture_and_advance(
                label,
                dialog,
                capture_delay_ms=420,
                close_callback=close_dialog,
                close_ms=820,
                next_ms=1160,
            )

        self._with_dashboard(
            dashboard_ready,
            failure_label=label,
            on_error=registered_cleanup,
        )

    def _capture_purchase_confirmation_species(self) -> None:
        self._capture_purchase_dialog_fixture("purchase-confirmation-species", "species")

    def _capture_purchase_confirmation_growth_charge(self) -> None:
        self._capture_purchase_dialog_fixture("purchase-confirmation-growth-charge", "growth-charge")

    def _capture_purchase_confirmation_environment(self) -> None:
        self._capture_purchase_dialog_fixture("purchase-confirmation-environment", "environment")

    def _capture_purchase_confirmation_fertilizer_application(self) -> None:
        self._capture_purchase_dialog_fixture(
            "purchase-confirmation-fertilizer-application",
            "fertilizer-application",
        )

    def _capture_purchase_confirmation_fertilizer_extension(self) -> None:
        self._capture_purchase_dialog_fixture(
            "purchase-confirmation-fertilizer-extension",
            "fertilizer-extension",
        )

    def _capture_purchase_confirmation_bed(self) -> None:
        self._capture_purchase_dialog_fixture("purchase-confirmation-garden-bed", "bed")

    def _capture_purchase_confirmation_loading(self) -> None:
        self._capture_purchase_dialog_fixture("purchase-confirmation-loading-disabled", "loading")

    def _capture_purchase_error_insufficient(self) -> None:
        self._capture_purchase_dialog_fixture("purchase-error-insufficient-coins", "insufficient")

    def _capture_purchase_error_persistence(self) -> None:
        self._capture_purchase_dialog_fixture("purchase-error-persistence-failure", "persistence")

    def _capture_purchase_error_unavailable(self) -> None:
        self._capture_purchase_dialog_fixture("purchase-error-item-unavailable", "unavailable")

    def _capture_purchase_error_already_owned(self) -> None:
        self._capture_purchase_dialog_fixture("purchase-error-already-owned", "already-owned")

    def _capture_purchase_error_invalid_target(self) -> None:
        self._capture_purchase_dialog_fixture("purchase-error-invalid-target", "invalid-target")

    def _capture_purchase_error_stale_price(self) -> None:
        self._capture_purchase_dialog_fixture("purchase-error-stale-price", "stale-price")

    def _capture_purchase_error_stale_balance(self) -> None:
        self._capture_purchase_dialog_fixture("purchase-error-stale-balance", "stale-balance")

    def _capture_purchase_success_fixture(
        self,
        label: str,
        variant: str,
        tab_index: int,
    ) -> None:
        cleanup_holder: dict[str, Callable[[], None]] = {
            "callback": lambda: None,
        }

        def registered_cleanup() -> None:
            cleanup_holder["callback"]()

        def dashboard_ready() -> None:
            prepared = self._purchase_capture_snapshot(
                label,
                exact_ledger_restore=True,
            )
            if prepared is None:
                self._next_after(200)
                return
            snapshot, plant = prepared
            def cleanup() -> None:
                self._restore_purchase_capture(snapshot)

            # Register exact restoration before any purchase can commit.
            cleanup_holder["callback"] = cleanup
            from .purchases import (
                PurchaseKind,
                PurchaseRequest,
                purchase_presentation,
            )
            from .ui.dashboard import NurseryDialog

            state = self.app.storage.state
            if variant == "collection":
                kind = PurchaseKind.SPECIES
                item_id = "sunflower"
                target_id = None
                state.plants = [item for item in state.plants if item.species != item_id]
                state.unlocked_species = [
                    item for item in state.unlocked_species if item != item_id
                ]
            elif variant == "fertilizer":
                kind = PurchaseKind.FERTILIZER
                item_id = "basic"
                target_id = plant.plant_id
            else:
                kind = PurchaseKind.BED
                item_id = "next"
                target_id = None
                state.unlocked_slots = 2
                for candidate in state.plants:
                    if candidate.slot_index is not None and candidate.slot_index >= 2:
                        candidate.slot_index = None

            quote = self.app.engine.quote_purchase(
                kind,
                item_id,
                target_id=target_id,
            )
            outcome = self.app.engine.confirm_purchase(
                PurchaseRequest.from_quote(quote)
            )
            dialog = NurseryDialog(
                self.app.dashboard,
                self.app.engine,
                self.app.storage,
            )
            dialog.catalog_tabs.setCurrentIndex(tab_index)
            if variant == "bed" and outcome.success:
                dialog._recently_unlocked_bed = int(outcome.result_id)
                dialog.refresh()
                dialog.catalog_tabs.setCurrentIndex(tab_index)
            if outcome.success:
                dialog._show_purchase_receipt(
                    outcome,
                    purchase_presentation(quote, ignore_status=True),
                )
            self._capture_annotations[label] = {
                "status": outcome.status.value,
                "disposition": outcome.disposition.value,
                "amount_spent": outcome.amount_spent,
                "new_balance": outcome.new_balance,
                "result_id": outcome.result_id,
                "passed": bool(outcome.success),
            }
            if not outcome.success:
                self._failures.append({
                    "label": label,
                    "reason": f"Success fixture failed with {outcome.status.value}",
                })
            dialog.setWindowModality(Qt.WindowModality.NonModal)
            dialog.setModal(False)
            self._move_to_capture_display(dialog)
            dialog.show()

            def audit_success_flow() -> None:
                QApplication.processEvents()
                host = dialog.nursery_feedback_host
                page = dialog.catalog_pages[tab_index]
                page_layout = dialog.catalog_page_layouts[tab_index]
                scroll = (
                    dialog.scroll,
                    dialog.supplements_scroll,
                    dialog.upgrades_scroll,
                    dialog.environment_scroll,
                )[tab_index]
                host_bounds = self._widget_bounds_evidence(host, dialog)
                scroll_bounds = self._widget_bounds_evidence(scroll, dialog)
                tab_bar_bounds = self._widget_bounds_evidence(
                    dialog.catalog_tabs.tabBar(),
                    dialog,
                )
                host_box = list(host_bounds.get("bounds", ()) or ())
                scroll_box = list(scroll_bounds.get("bounds", ()) or ())
                tab_box = list(tab_bar_bounds.get("bounds", ()) or ())
                normal_flow = bool(
                    host.parentWidget() is page
                    and page_layout.indexOf(host) == 0
                    and page_layout.indexOf(scroll) > page_layout.indexOf(host)
                    and not host.isHidden()
                    and not dialog.nursery_toast.isHidden()
                    and len(host_box) == 4
                    and len(scroll_box) == 4
                    and len(tab_box) == 4
                    and int(host_box[1])
                    >= int(tab_box[1]) + int(tab_box[3])
                    and int(host_box[1]) + int(host_box[3])
                    <= int(scroll_box[1])
                )
                annotation = self._capture_annotations[label]
                annotation["nursery_feedback_flow"] = {
                    "host_bounds": host_bounds,
                    "scroll_bounds": scroll_bounds,
                    "tab_bar_bounds": tab_bar_bounds,
                    "host_layout_index": page_layout.indexOf(host),
                    "scroll_layout_index": page_layout.indexOf(scroll),
                    "passed": normal_flow,
                }
                annotation["passed"] = bool(
                    annotation.get("passed", False) and normal_flow
                )

            def close_dialog() -> None:
                self._close_widget(dialog)
                cleanup()

            self._capture_and_advance(
                label,
                dialog,
                capture_delay_ms=520,
                before_capture=audit_success_flow,
                close_callback=close_dialog,
                close_ms=920,
                next_ms=1260,
            )

        self._with_dashboard(
            dashboard_ready,
            failure_label=label,
            on_error=registered_cleanup,
        )

    def _capture_purchase_success_collection(self) -> None:
        self._capture_purchase_success_fixture(
            "purchase-success-inventory-collection", "collection", 0
        )

    def _capture_purchase_success_fertilizer(self) -> None:
        self._capture_purchase_success_fixture(
            "purchase-success-fertilizer-applied", "fertilizer", 1
        )

    def _capture_purchase_success_bed(self) -> None:
        self._capture_purchase_success_fixture(
            "purchase-success-garden-bed-unlocked", "bed", 2
        )

    def _prepare_growth_charge_capture(
        self,
        label: str,
        *,
        inventory: int = 2,
        growth_points: int = 1_250,
        planted: bool = True,
        exact_ledger_restore: bool = False,
    ) -> tuple[dict[str, Any], list[Any], Any]:
        """Install one exact, reversible target for a Charge dialog fixture."""

        from .environment import GROWTH_CHARGES
        from .models.state import Plant, PlantMemory

        snapshot = self._capture_fixture_state_snapshot(
            label,
            exact_ledger_restore=exact_ledger_restore,
        )
        transition_snapshot = list(self.app.engine._pending_stage_transitions)
        state = self.app.storage.state
        today = str(state.daily_stats.day)
        plant = Plant(
            plant_id="capture_growth_charge_bonsai",
            species="bonsai",
            name="Bonsai Plant",
            slot_index=0 if planted else None,
            growth_points=max(0, int(growth_points)),
            planted_on=today,
            memories=[PlantMemory(
                memory_id="capture-growth-charge-planted",
                kind="planted",
                occurred_on=today,
            )],
        )
        state.plants = [plant]
        state.unlocked_species = list(dict.fromkeys([
            *state.unlocked_species,
            "bonsai",
        ]))
        state.unlocked_slots = max(1, int(state.unlocked_slots))
        state.active_plant_id = plant.plant_id if planted else None
        state.starter_selection_complete = True
        state.onboarding.starter_plant_id = plant.plant_id
        state.completed_growth_charge_requests.clear()
        for charge_id in GROWTH_CHARGES:
            state.consumables[charge_id] = 0
        state.consumables["growth_charge_small"] = max(0, int(inventory))
        state.selected_background = "default"
        stats = state.daily_stats
        stats.plant_charge_growth = {}
        stats.plant_direct_reward_growth = {}
        stats.reconcile_growth_totals()
        self._capture_annotations[label] = {
            "target_id": plant.plant_id,
            "initial_growth": plant.growth_points,
            "initial_inventory": max(0, int(inventory)),
            "passed": True,
        }
        return snapshot, transition_snapshot, plant

    def _restore_growth_charge_capture(
        self,
        snapshot: dict[str, Any],
        transition_snapshot: list[Any],
    ) -> None:
        self.app.engine._pending_stage_transitions = list(transition_snapshot)
        self._restore_capture_fixture_state(snapshot)

    def _growth_charge_capture_annotation(
        self,
        label: str,
        variant: str,
        dialog: Any,
        plant: Any,
    ) -> None:
        expected_status = str(
            expected_capture_state_profile(label).get("growth_charge_status", "")
        )
        actual_status = str(dialog.property("growthChargeState") or "")
        state = self.app.storage.state
        target = self.app.engine.plant_story(
            str(getattr(plant, "plant_id", "") or "")
        )
        inventory = max(
            0,
            int(state.consumables.get("growth_charge_small", 0) or 0),
        )
        ledger_count = len(state.completed_growth_charge_requests)
        alert_visible = not dialog.alert.isHidden()
        receipt_visible = not dialog.receipt.isHidden()
        quote = getattr(dialog, "quote", None)
        outcome = getattr(dialog, "outcome", None)
        visible_label_text = {
            str(label_widget.text()).strip()
            for label_widget in dialog.findChildren(QLabel)
            if label_widget.isVisible()
            and str(label_widget.text()).strip()
        }
        compact_result = str(dialog.compact_summary.text()).strip()
        compact_result_visible = bool(
            dialog.compact_summary_card.isVisible()
            and compact_result
        )
        result_matches_quote = bool(
            quote is not None
            and compact_result_visible
            and f"{max(0, int(quote.current_growth)):,}" in compact_result
            and f"{max(0, int(quote.projected_growth)):,}" in compact_result
        )
        plant_details_visible = bool(
            dialog.hero.isVisible()
            and dialog.target_name.isVisible()
            and str(dialog.target_name.text()).strip()
        )
        charge_details_visible = bool(
            dialog.selector_card.isVisible()
            and (
                dialog.charge_selector.isVisible()
                or dialog.static_charge_row.isVisible()
            )
        )
        quantity_text = " ".join(filter(None, (
            str(dialog.static_charge_quantity.text()).strip(),
            str(dialog.charge_selector.currentText()).strip(),
        )))
        alert_copy = str(dialog.alert.text()).strip()
        receipt_copy = str(dialog.receipt_copy.text()).strip()
        conditions = [actual_status == expected_status]
        if variant == "ready":
            conditions.extend([
                bool(quote is not None and quote.ready),
                dialog.use_action.isEnabled(),
                plant_details_visible,
                charge_details_visible,
                result_matches_quote,
                inventory == 2,
            ])
        elif variant == "empty":
            footer = getattr(dialog, "_pinned_footer", None)
            conditions.extend([
                dialog.empty_inventory.isVisible(),
                dialog.nursery_action.isVisible(),
                bool(
                    footer is not None
                    and footer.isAncestorOf(dialog.nursery_action)
                ),
                dialog.use_action.isHidden(),
                inventory == 0,
            ])
        elif variant == "loading":
            conditions.extend([
                dialog._submitting,
                dialog.dialog_in_flight,
                not dialog.use_action.isEnabled(),
                not dialog.cancel_action.isEnabled(),
                not dialog.charge_selector.isEnabled(),
                bool(dialog.use_action.property("busy")),
                plant_details_visible,
                charge_details_visible,
                result_matches_quote,
                inventory == 2,
            ])
        elif variant == "stale":
            conditions.extend([
                outcome is not None,
                str(
                    getattr(
                        getattr(outcome, "status", ""),
                        "value",
                        getattr(outcome, "status", ""),
                    )
                ) == "stale_inventory",
                bool(quote is not None and quote.ready),
                not dialog._submitting,
                dialog.use_action.isEnabled(),
                plant_details_visible,
                charge_details_visible,
                result_matches_quote,
                f"{inventory:,}" in quantity_text,
                alert_visible,
                "Availability updated" in alert_copy,
                inventory == 1,
                int(getattr(target, "growth_points", -1)) == 1_250,
                ledger_count == 0,
            ])
        elif variant == "invalid":
            target_state = str(
                getattr(
                    getattr(quote, "target_state", ""),
                    "value",
                    getattr(quote, "target_state", ""),
                )
            )
            alert_copy = str(dialog.alert.text()).strip()
            conditions.extend([
                alert_visible,
                not plant_details_visible,
                not charge_details_visible,
                not compact_result_visible,
                target_state == "stored",
                str(dialog.windowTitle()) == "Choose another plant",
                "This plant can’t use a Growth Charge." in alert_copy,
                "Your charge was not used." in alert_copy,
                dialog.use_action.isEnabled(),
                dialog.cancel_action.isVisible(),
                dialog.cancel_action.isEnabled(),
                dialog._primary_route == "choose_plant",
                not bool(getattr(target, "planted", False)),
                ledger_count == 0,
            ])
        elif variant == "persistence":
            conditions.extend([
                alert_visible,
                bool(dialog.alert.text().strip()),
                bool(quantity_text),
                dialog.use_action.isEnabled(),
                inventory == 2,
                int(getattr(target, "growth_points", -1)) == 1_250,
                ledger_count == 0,
            ])
        elif variant == "success":
            from .ui.formatters import format_status_label

            result_title = (
                f"{str(getattr(outcome, 'target_name', ''))} reached "
                f"{format_status_label(str(getattr(outcome, 'resulting_stage', '')))}"
            )
            reward_total = sum(
                int(reward.garden_coins)
                for reward in getattr(outcome, "rewards", ())
            )
            conditions.extend([
                receipt_visible,
                bool(outcome is not None and outcome.success),
                tuple(getattr(outcome, "completed_stages", ())) == ("sprout",),
                reward_total == 5,
                result_title in visible_label_text,
                f"+{reward_total:,} Garden Coins" in visible_label_text,
                "Seed → Sprout" in receipt_copy,
                not compact_result_visible,
                inventory == 1,
                int(getattr(target, "growth_points", -1)) == 550,
                ledger_count == 1,
                dialog.use_action.isEnabled(),
                dialog.cancel_action.isVisible(),
                dialog.cancel_action.isEnabled(),
            ])
        single_scroll_region = len(dialog.active_vertical_scroll_regions()) == 1
        conditions.append(single_scroll_region)
        passed = all(conditions)
        self._capture_annotations[label].update({
            "variant": variant,
            "expected_status": expected_status,
            "actual_status": actual_status,
            "inventory": inventory,
            "target_growth": int(getattr(target, "growth_points", -1)),
            "request_ledger_count": ledger_count,
            "alert_visible": alert_visible,
            "receipt_visible": receipt_visible,
            "compact_result_visible": compact_result_visible,
            "result_matches_quote": result_matches_quote,
            "plant_details_visible": plant_details_visible,
            "charge_details_visible": charge_details_visible,
            "alert_copy": alert_copy,
            "receipt_copy": receipt_copy,
            "ready_with_stale_inventory_warning": bool(
                variant != "stale"
                or (
                    alert_visible
                    and "Availability updated" in alert_copy
                    and quote is not None
                    and bool(quote.ready)
                    and dialog.use_action.isEnabled()
                )
            ),
            "seed_to_sprout_receipt": bool(
                variant != "success"
                or (
                    receipt_visible
                    and "Seed → Sprout" in receipt_copy
                )
            ),
            "single_scroll_region": single_scroll_region,
            "passed": passed,
        })
        if not passed:
            self._failures.append({
                "label": label,
                "reason": (
                    "Growth Charge fixture did not match its declared state "
                    f"({actual_status!r} != {expected_status!r})"
                ),
            })

    def _capture_growth_charge_dialog_fixture(
        self,
        label: str,
        variant: str,
    ) -> None:
        cleanup_holder: dict[str, Callable[[], None]] = {
            "callback": lambda: None,
        }

        def registered_cleanup() -> None:
            cleanup_holder["callback"]()

        def dashboard_ready() -> None:
            inventory = 0 if variant == "empty" else 2
            growth_points = 450 if variant == "success" else 1_250
            planted = variant != "invalid"
            snapshot, transition_snapshot, plant = self._prepare_growth_charge_capture(
                label,
                inventory=inventory,
                growth_points=growth_points,
                planted=planted,
                exact_ledger_restore=variant == "success",
            )
            def cleanup() -> None:
                self._restore_growth_charge_capture(
                    snapshot,
                    transition_snapshot,
                )

            # Register cleanup before the dialog's synchronous commit path.
            cleanup_holder["callback"] = cleanup
            from .ui.dashboard import GrowthChargeConfirmationDialog

            dialog = GrowthChargeConfirmationDialog(
                self.app.dashboard,
                self.app.engine,
                plant.plant_id,
                open_nursery=lambda: None,
            )
            if variant == "loading":
                dialog._commit = lambda: None
                dialog._activate_primary()
            elif variant == "stale":
                self.app.storage.state.consumables["growth_charge_small"] = 1
                dialog._submitting = True
                dialog._commit()
            elif variant == "persistence":
                original_save = self.app.storage.save

                def fail_save() -> None:
                    raise OSError("deterministic Growth Charge persistence failure")

                self.app.storage.save = fail_save
                try:
                    dialog._submitting = True
                    dialog._commit()
                finally:
                    self.app.storage.save = original_save
            elif variant == "success":
                dialog._submitting = True
                dialog._commit()

            dialog.setWindowModality(Qt.WindowModality.NonModal)
            dialog.setModal(False)
            self._move_to_capture_display(dialog)

            def close_dialog() -> None:
                dialog._submitting = False
                self._close_widget(dialog)
                cleanup()

            dialog.show()
            dialog.raise_()
            dialog.activateWindow()
            QApplication.processEvents()
            self._growth_charge_capture_annotation(label, variant, dialog, plant)
            self._capture_and_advance(
                label,
                dialog,
                capture_delay_ms=440,
                close_callback=close_dialog,
                close_ms=840,
                next_ms=1180,
            )

        self._with_dashboard(
            dashboard_ready,
            failure_label=label,
            on_error=registered_cleanup,
        )

    def _capture_growth_charge_ready(self) -> None:
        self._capture_growth_charge_dialog_fixture(
            "growth-charge-use-ready",
            "ready",
        )

    def _capture_growth_charge_empty_inventory(self) -> None:
        self._capture_growth_charge_dialog_fixture(
            "growth-charge-empty-inventory",
            "empty",
        )

    def _capture_growth_charge_loading(self) -> None:
        self._capture_growth_charge_dialog_fixture(
            "growth-charge-loading-disabled",
            "loading",
        )

    def _capture_growth_charge_stale_inventory(self) -> None:
        self._capture_growth_charge_dialog_fixture(
            "growth-charge-stale-inventory",
            "stale",
        )

    def _capture_growth_charge_invalid_target(self) -> None:
        self._capture_growth_charge_dialog_fixture(
            "growth-charge-invalid-target",
            "invalid",
        )

    def _capture_growth_charge_persistence_failure(self) -> None:
        self._capture_growth_charge_dialog_fixture(
            "growth-charge-persistence-failure",
            "persistence",
        )

    def _capture_growth_charge_success_reward(self) -> None:
        self._capture_growth_charge_dialog_fixture(
            "growth-charge-success-stage-reward",
            "success",
        )

    def _capture_nursery_empty_state(self) -> None:
        label = "nursery-empty-state"

        def dashboard_ready() -> None:
            prepared = self._purchase_capture_snapshot(label)
            if prepared is None:
                self._next_after(200)
                return
            snapshot, _plant = prepared
            from .ui.dashboard import NurseryDialog

            state = self.app.storage.state
            state.unlocked_species = list(self.app.engine.release_ready_species())
            dialog = NurseryDialog(
                self.app.dashboard,
                self.app.engine,
                self.app.storage,
            )
            dialog.catalog_tabs.setCurrentIndex(0)
            dialog.setWindowModality(Qt.WindowModality.NonModal)
            dialog.setModal(False)
            self._move_to_capture_display(dialog)
            dialog.show()
            scrollbar = dialog.scroll.verticalScrollBar()
            QTimer.singleShot(120, lambda: scrollbar.setValue(0))

            def audit_empty_state() -> None:
                QApplication.processEvents()
                visible_labels = {
                    str(label_widget.text())
                    for label_widget in dialog.findChildren(QLabel)
                    if not label_widget.isHidden()
                }
                visible_buttons = {
                    _displayed_button_text(button)
                    for button in dialog.findChildren(QAbstractButton)
                    if not button.isHidden()
                }
                available_count = len(
                    self.app.engine.catalog_summary().get(
                        "available_species",
                        [],
                    )
                )
                empty_visible = bool(
                    "All plants collected" in visible_labels
                    and any(
                        re.fullmatch(
                            r"\d[\d,]* of \d[\d,]* species collected",
                            copy.strip(),
                        )
                        for copy in visible_labels
                    )
                    and "View Collection" in visible_buttons
                    and scrollbar.value() == 0
                )
                self._capture_annotations[label] = {
                    "empty_state_visible": empty_visible,
                    "available_count": available_count,
                    "actions": sorted(visible_buttons),
                    "passed": bool(empty_visible and available_count == 0),
                }

            def close_dialog() -> None:
                self._close_widget(dialog)
                self._restore_purchase_capture(snapshot)

            self._capture_and_advance(
                label,
                dialog,
                capture_delay_ms=520,
                before_capture=audit_empty_state,
                close_callback=close_dialog,
                close_ms=900,
                next_ms=1240,
            )

        self._with_dashboard(dashboard_ready, failure_label=label)

    def _capture_collection_environment_mechanics(self) -> None:
        label = "collection-environment-mechanics"
        cleanup_holder: dict[str, Callable[[], None]] = {}

        def registered_cleanup() -> None:
            callback = cleanup_holder.pop("callback", None)
            if callback is not None:
                callback()

        def dashboard_ready() -> None:
            prepared = self._purchase_capture_snapshot(label)
            if prepared is None:
                self._next_after(200)
                return
            snapshot, _plant = prepared
            from .environment import WEATHER_CATALOG

            dashboard = self.app.dashboard
            state = self.app.storage.state
            previous_collection_preferences = (
                str(dashboard._collection_filter),
                str(dashboard._collection_category),
                str(dashboard._collection_query),
                str(dashboard._collection_sort),
            )
            restored = False

            def restore() -> None:
                nonlocal restored
                if restored:
                    return
                restored = True
                cleanup_holder.pop("callback", None)
                self._restore_purchase_capture(snapshot)
                (
                    dashboard._collection_filter,
                    dashboard._collection_category,
                    dashboard._collection_query,
                    dashboard._collection_sort,
                ) = previous_collection_preferences
                dashboard._refresh_collection_list()

            cleanup_holder["callback"] = restore
            for item_id in ("sunny", "breeze"):
                if item_id not in state.inventory.setdefault("weather", []):
                    state.inventory["weather"].append(item_id)
            for item_id in ("default", "spring"):
                if item_id not in state.inventory.setdefault("scenery", []):
                    state.inventory["scenery"].append(item_id)
            state.selected_weather = "breeze"
            state.selected_background = "spring"
            dashboard._collection_filter = "all"
            dashboard._collection_category = "weather"
            dashboard._collection_query = WEATHER_CATALOG["breeze"].name
            dashboard._collection_sort = "catalog"
            dashboard._refresh_collection_list()
            dialog = dashboard.progress_dialog
            dialog.refresh()
            dialog.navigation.set_current("collection")
            dialog.setWindowModality(Qt.WindowModality.NonModal)
            dialog.setModal(False)
            self._move_to_capture_display(dialog)
            dialog.show()
            dialog.raise_()

            def finalize_fixture() -> None:
                app = QApplication.instance()
                QCoreApplication.sendPostedEvents(
                    None,
                    QEvent.Type.DeferredDelete,
                )
                if app is not None:
                    app.processEvents()
                button_widgets = dashboard.collection_list.findChildren(QAbstractButton)
                scroll = dashboard.collection_list.scroll
                scrollbar = scroll.verticalScrollBar()
                scrollbar.setValue(0)
                if app is not None:
                    app.processEvents()

                viewport = scroll.viewport()
                filter_controls = getattr(
                    dashboard,
                    "collection_filter_controls",
                    None,
                )
                edit_appearance = next((
                    button for button in button_widgets
                    if button.isVisible()
                    and str(button.text()) == "Edit appearance"
                ), None)
                visible_label_widgets = [
                    label_widget
                    for label_widget in dashboard.collection_list.findChildren(QLabel)
                    if label_widget.isVisible()
                ]
                summary_title = next((
                    item for item in visible_label_widgets
                    if bool(item.property("appearanceSummaryTitle"))
                ), None)
                appearance_summary = next((
                    item
                    for item in dashboard.collection_list.findChildren(QWidget)
                    if bool(item.property("collectionAppearanceSummary"))
                ), None)
                summary_selection = next((
                    item for item in (
                        appearance_summary.findChildren(QLabel)
                        if appearance_summary is not None else ()
                    )
                    if bool(item.property("rowCriteria"))
                ), None)
                environment_title = next((
                    item for item in visible_label_widgets
                    if bool(item.property("rowTitle"))
                    and str(item.text()).strip() == WEATHER_CATALOG["breeze"].name
                ), None)
                environment_status = next((
                    item for item in visible_label_widgets
                    if bool(item.property("catalogStatus"))
                    and "Weather" in str(item.text())
                ), None)
                environment_effect = next((
                    item for item in visible_label_widgets
                    if bool(item.property("rowCriteria"))
                    and "Growth" in str(item.text())
                    and item is not summary_selection
                ), None)
                mechanics_details = next((
                    item for item in visible_label_widgets
                    if bool(item.property("collectionEnvironmentMetadata"))
                ), None)
                preview_action = next((
                    button for button in button_widgets
                    if button.isVisible()
                    and _displayed_button_text(button) == "Preview"
                ), None)
                unequip_action = next((
                    button for button in button_widgets
                    if button.isVisible()
                    and _displayed_button_text(button) == "Unequip"
                ), None)
                required_widgets: dict[str, Any] = {
                    "toolbar": filter_controls,
                    "summary_title": summary_title,
                    "summary_selection": summary_selection,
                    "edit_appearance": edit_appearance,
                    "item_title": environment_title,
                    "item_status": environment_status,
                    "effect": environment_effect,
                    "mechanics": mechanics_details,
                }

                def evidence_text(key: str, widget: Any) -> str:
                    if widget is None:
                        return ""
                    if isinstance(widget, QAbstractButton):
                        return _displayed_button_text(widget)
                    if isinstance(widget, QLabel):
                        return str(widget.text()).strip()
                    if key == "toolbar":
                        return str(widget.accessibleName() or "Collection filters")
                    return str(widget.accessibleName() or "").strip()

                required_bounds: list[dict[str, Any]] = []
                for key, required_widget in required_widgets.items():
                    if required_widget is not None:
                        required_widget.setProperty(
                            "captureEvidenceKey",
                            f"environment-{key.replace('_', '-')}",
                        )
                    evidence = self._widget_bounds_evidence(required_widget, viewport)
                    evidence.update({
                        "key": key,
                        "text": evidence_text(key, required_widget),
                    })
                    required_bounds.append(evidence)

                toolbar_controls: list[tuple[str, Any]] = []
                if filter_controls is not None:
                    toolbar_controls = [
                        ("count", getattr(filter_controls, "count", None)),
                        ("search", getattr(filter_controls, "search", None)),
                        ("status", getattr(filter_controls, "status_combo", None)),
                        ("category", getattr(filter_controls, "category_combo", None)),
                        ("sort", getattr(filter_controls, "sort_combo", None)),
                        ("clear", getattr(filter_controls, "clear", None)),
                    ]
                toolbar_bounds: list[dict[str, Any]] = []
                for key, control in toolbar_controls:
                    evidence = self._widget_bounds_evidence(control, viewport)
                    if isinstance(control, QComboBox):
                        copy = str(control.currentText()).strip()
                    elif isinstance(control, QLineEdit):
                        copy = str(control.text()).strip()
                    elif isinstance(control, QAbstractButton):
                        copy = _displayed_button_text(control)
                    elif isinstance(control, QLabel):
                        copy = str(control.text()).strip()
                    else:
                        copy = ""
                    evidence.update({"key": key, "text": copy})
                    toolbar_bounds.append(evidence)
                toolbar_mode = str(
                    filter_controls.property("layoutMode")
                    if filter_controls is not None else ""
                )
                toolbar_visual = {
                    "layout_mode": toolbar_mode,
                    "row_count": 1 if toolbar_mode == "wide" else 2,
                    "controls": toolbar_bounds,
                    "toolbar": self._widget_bounds_evidence(
                        filter_controls,
                        viewport,
                    ),
                }
                toolbar_box = list(
                    toolbar_visual["toolbar"].get("bounds", ()) or ()
                )
                toolbar_visual["passed"] = bool(
                    toolbar_mode in {"wide", "compact"}
                    and toolbar_visual["row_count"] <= 2
                    and len(toolbar_bounds) == 6
                    and all(
                        bool(row.get("visible", False))
                        and bool(row.get("contained", False))
                        and bool(str(row.get("text", "")).strip())
                        for row in toolbar_bounds
                    )
                    and bool(toolbar_visual["toolbar"].get("contained", False))
                    and len(toolbar_box) == 4
                    and int(toolbar_box[3]) <= 150
                )
                environment_mechanics_visual = {
                    "required_keys": list(required_widgets),
                    "required_bounds": required_bounds,
                    "viewport_size": [
                        int(viewport.width()),
                        int(viewport.height()),
                    ],
                    "toolbar_visual": toolbar_visual,
                }
                environment_mechanics_visual["passed"] = bool(
                    len(required_bounds) == len(required_widgets)
                    and all(
                        bool(row.get("visible", False))
                        and bool(row.get("contained", False))
                        and bool(str(row.get("text", "")).strip())
                        for row in required_bounds
                    )
                    and toolbar_visual["passed"]
                )
                mechanics_text = evidence_text("mechanics", mechanics_details)
                edit_evidence = next(
                    row for row in required_bounds
                    if row.get("key") == "edit_appearance"
                )
                annotation = {
                    "collection_category": str(dashboard._collection_category),
                    "collection_query": str(dashboard._collection_query),
                    "mechanics_expanded": bool(
                        mechanics_details is not None
                        and mechanics_details.isVisible()
                    ),
                    "mechanics_always_visible": bool(
                        mechanics_details is not None
                        and mechanics_details.isVisible()
                        and "Available every day" in mechanics_text
                        and "Only one weather can be equipped" in mechanics_text
                    ),
                    "selected_environment_visible": (
                        evidence_text("item_title", environment_title)
                        == WEATHER_CATALOG["breeze"].name
                    ),
                    "complete_effects_visible": (
                        "Growth" in evidence_text(
                            "effect",
                            environment_effect,
                        )
                        and "Available every day" in mechanics_text
                        and "Only one weather can be equipped" in mechanics_text
                    ),
                    "loadout_summary_visible": (
                        evidence_text("summary_title", summary_title)
                        == "Garden appearance"
                        and WEATHER_CATALOG["breeze"].name
                        in evidence_text("summary_selection", summary_selection)
                    ),
                    "equipment_state_visible": bool(
                        environment_status is not None
                        and "Equipped" in str(environment_status.text())
                    ),
                    "loadout_route_visible": bool(
                        edit_appearance is not None
                        and edit_appearance.isVisible()
                    ),
                    "loadout_routes_enabled": bool(
                        edit_appearance is not None
                        and edit_appearance.isEnabled()
                    ),
                    "action_buttons_fully_visible": bool(
                        edit_evidence.get("contained", False)
                        and 34 <= int(edit_appearance.height()) <= 38
                    ),
                    "compact_environment_actions": bool(
                        preview_action is not None
                        and unequip_action is not None
                        and preview_action.isVisible()
                        and unequip_action.isVisible()
                        and preview_action.height() == 34
                        and unequip_action.height() == 34
                        and preview_action.width() <= int(dialog.width() * 0.50)
                        and unequip_action.width() <= int(dialog.width() * 0.50)
                    ),
                    "route_button_bounds": [edit_evidence],
                    "filter_toolbar_visible": toolbar_visual["passed"],
                    "scroll_at_top": bool(scrollbar.value() == 0),
                    "direct_mutation_controls": any(
                        button.isCheckable()
                        and str(button.text()) in {"Show Weather", "Show Scenery"}
                        for button in button_widgets
                    ),
                    "environment_mechanics_visual": (
                        environment_mechanics_visual
                    ),
                }
                annotation["passed"] = bool(
                    annotation["collection_category"] == "weather"
                    and annotation["mechanics_expanded"]
                    and annotation["mechanics_always_visible"]
                    and annotation["selected_environment_visible"]
                    and annotation["complete_effects_visible"]
                    and annotation["loadout_summary_visible"]
                    and annotation["equipment_state_visible"]
                    and annotation["loadout_route_visible"]
                    and annotation["loadout_routes_enabled"]
                    and annotation["action_buttons_fully_visible"]
                    and annotation["compact_environment_actions"]
                    and annotation["filter_toolbar_visible"]
                    and environment_mechanics_visual["passed"]
                    and annotation["scroll_at_top"]
                    and not annotation["direct_mutation_controls"]
                )
                self._capture_annotations[label] = annotation

                def bind_final_pixel_evidence() -> None:
                    QCoreApplication.sendPostedEvents(
                        None,
                        QEvent.Type.DeferredDelete,
                    )
                    if app is not None:
                        app.processEvents()
                    current_buttons = dashboard.collection_list.findChildren(
                        QAbstractButton
                    )
                    scrollbar.setValue(0)
                    if app is not None:
                        app.processEvents()
                    current_labels = [
                        label_widget
                        for label_widget in dashboard.collection_list.findChildren(QLabel)
                        if label_widget.isVisible()
                    ]
                    current_summary = next((
                        item
                        for item in dashboard.collection_list.findChildren(QWidget)
                        if bool(item.property("collectionAppearanceSummary"))
                    ), None)
                    current_summary_selection = next((
                        item
                        for item in (
                            current_summary.findChildren(QLabel)
                            if current_summary is not None else ()
                        )
                        if bool(item.property("rowCriteria"))
                    ), None)
                    current_widgets: dict[str, Any] = {
                        "toolbar": getattr(
                            dashboard,
                            "collection_filter_controls",
                            None,
                        ),
                        "summary_title": next((
                            item for item in current_labels
                            if bool(item.property("appearanceSummaryTitle"))
                        ), None),
                        "summary_selection": current_summary_selection,
                        "edit_appearance": next((
                            button for button in current_buttons
                            if button.isVisible()
                            and str(button.text()) == "Edit appearance"
                        ), None),
                        "item_title": next((
                            item for item in current_labels
                            if bool(item.property("rowTitle"))
                            and str(item.text()).strip()
                            == WEATHER_CATALOG["breeze"].name
                        ), None),
                        "item_status": next((
                            item for item in current_labels
                            if bool(item.property("catalogStatus"))
                            and "Weather" in str(item.text())
                        ), None),
                        "effect": next((
                            item for item in current_labels
                            if bool(item.property("rowCriteria"))
                            and "Growth" in str(item.text())
                            and item is not current_summary_selection
                        ), None),
                        "mechanics": next((
                            item for item in current_labels
                            if bool(item.property("collectionEnvironmentMetadata"))
                        ), None),
                    }
                    for key, current_widget in current_widgets.items():
                        if current_widget is not None:
                            current_widget.setProperty(
                                "captureEvidenceKey",
                                f"environment-{key.replace('_', '-')}",
                            )

                def close_dialog() -> None:
                    self._close_widget(dialog)
                    restore()

                self._capture_and_advance(
                    label,
                    dialog,
                    capture_delay_ms=560,
                    before_capture=bind_final_pixel_evidence,
                    close_callback=close_dialog,
                    close_ms=940,
                    next_ms=1280,
                )

            QTimer.singleShot(180, finalize_fixture)

        self._with_dashboard(
            dashboard_ready,
            failure_label=label,
            on_error=registered_cleanup,
        )

    def _capture_collection_loadout_persistence_error(self) -> None:
        label = "collection-loadout-persistence-error"

        def ready() -> None:
            dashboard = self.app.dashboard
            prepared = self._purchase_capture_snapshot(label)
            if prepared is None:
                self._next_after(200)
                return
            snapshot, _plant = prepared
            state = self.app.storage.state
            if "breeze" not in state.inventory.setdefault("weather", []):
                state.inventory["weather"].append("breeze")
            state.selected_weather = "sunny"
            dialog = dashboard.collectible_detail_dialog
            dialog.prepare_to_show()
            dialog._select_option("weather", "breeze")
            before = deepcopy(self.app.engine.state.loadout.to_dict())
            original_save = self.app.storage.save

            def fail_save() -> None:
                raise OSError("deterministic Collection loadout persistence failure")

            self.app.storage.save = fail_save
            try:
                dialog._apply_draft()
            finally:
                self.app.storage.save = original_save
            after = self.app.engine.state.loadout.to_dict()
            self._move_to_capture_display(dialog)
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()
            QApplication.processEvents()
            error_copy = str(dialog.preview_feedback.message.text())
            error_visible = bool(
                dialog.preview_feedback.isVisible()
                and dialog.preview_panel.isAncestorOf(dialog.preview_feedback)
                and not dialog.preview_scene.isAncestorOf(dialog.preview_feedback)
                and "Could not save changes" in error_copy
                and "unchanged" in error_copy
            )
            actions = {
                _displayed_button_text(dialog.cancel_preview),
                _displayed_button_text(dialog.apply_changes),
            }
            normal_width_actions = bool(
                dialog.property("footerMode") == "wide"
                and max(
                    dialog.cancel_preview.width(),
                    dialog.apply_changes.width(),
                )
                <= max(220, int(dialog.footer.width() * 0.35))
            )
            apply_origin = dialog.apply_changes.mapTo(
                dialog.footer,
                dialog.apply_changes.rect().topLeft(),
            )
            footer_margins = dialog.footer_layout.contentsMargins()
            actions_right_aligned = bool(
                apply_origin.x() + dialog.apply_changes.width()
                >= dialog.footer.width() - footer_margins.right() - 2
            )
            single_banner = bool(
                error_visible
                and dialog.unsaved.isHidden()
                and not str(dialog.unsaved.text()).strip()
            )
            self._capture_annotations[label] = {
                "passed": bool(
                    before == after
                    and error_visible
                    and actions == {"Try again", "Discard changes"}
                    and single_banner
                    and normal_width_actions
                    and actions_right_aligned
                ),
                "state_restored": before == after,
                "error_visible": error_visible,
                "error_copy": error_copy,
                "actions": sorted(actions),
                "single_banner": single_banner,
                "normal_width_actions": normal_width_actions,
                "actions_right_aligned": actions_right_aligned,
            }

            def bind_final_pixel_evidence() -> None:
                """Prove the settled rollback state is painted, not just owned."""

                QCoreApplication.sendPostedEvents(
                    None,
                    QEvent.Type.DeferredDelete,
                )
                app = QApplication.instance()
                if app is not None:
                    app.processEvents()
                dialog._refresh_preview()
                dialog._sync_option_page_geometry(
                    dialog.option_tabs.currentIndex()
                )
                dialog._sync_preview_scene_geometry()
                body = dialog.body_scroll.widget()
                for layout in (
                    dialog.main_grid,
                    dialog.library.layout(),
                    dialog.preview_panel.layout(),
                    body.layout() if body is not None else None,
                ):
                    if layout is None:
                        continue
                    layout.invalidate()
                    layout.activate()
                if body is not None:
                    body.setMinimumHeight(0)
                    body.updateGeometry()
                dialog.body_scroll.verticalScrollBar().setValue(0)
                dialog.preview_scene.setProperty(
                    "captureEvidenceKey",
                    "loadout-preview-scene",
                )
                dialog.preview_feedback.setProperty(
                    "captureEvidenceKey",
                    "loadout-persistence-error",
                )
                dialog.preview_scene.update()
                dialog._position_preview_feedback()
                dialog.preview_feedback.raise_()
                if app is not None:
                    app.processEvents()
                dialog.preview_scene.repaint()
                if app is not None:
                    app.processEvents()

                scene_bounds = self._widget_bounds_evidence(
                    dialog.preview_scene,
                    dialog,
                )
                feedback_bounds = self._widget_bounds_evidence(
                    dialog.preview_feedback,
                    dialog,
                )
                scene_metrics = self._home_pixmap_metrics(
                    dialog.preview_scene.grab(),
                    expected_width=dialog.preview_scene.width(),
                    expected_height=dialog.preview_scene.height(),
                )
                scene_box = list(scene_bounds.get("bounds", ()) or ())
                feedback_box = list(feedback_bounds.get("bounds", ()) or ())
                feedback_outside_artwork = bool(
                    len(scene_box) == 4
                    and len(feedback_box) == 4
                    and int(feedback_box[1]) + int(feedback_box[3])
                    <= int(scene_box[1])
                )
                rendered_state = {
                    "scene_bounds": scene_bounds,
                    "scene_metrics": scene_metrics,
                    "feedback_bounds": feedback_bounds,
                    "feedback_text": str(dialog.preview_feedback.message.text()),
                    "feedback_outside_artwork": feedback_outside_artwork,
                    "scroll_maximum": int(
                        dialog.body_scroll.verticalScrollBar().maximum()
                    ),
                    "passed": bool(
                        scene_bounds.get("visible", False)
                        and scene_bounds.get("contained", False)
                        and scene_metrics.get("generic_content_passed", False)
                        and feedback_bounds.get("visible", False)
                        and feedback_bounds.get("contained", False)
                        and feedback_outside_artwork
                        and "Could not save changes"
                        in str(dialog.preview_feedback.message.text())
                    ),
                }
                annotation = self._capture_annotations[label]
                annotation["rendered_state"] = rendered_state
                annotation["passed"] = bool(
                    annotation.get("passed", False)
                    and rendered_state["passed"]
                )

            def close_dialog() -> None:
                self._close_widget(dialog)
                self._restore_purchase_capture(snapshot)

            self._capture_and_advance(
                label,
                dialog,
                capture_delay_ms=460,
                before_capture=bind_final_pixel_evidence,
                close_callback=close_dialog,
                close_ms=800,
                next_ms=1120,
            )

        self._with_dashboard(ready, failure_label=label)

    def _capture_collection_origin_plant_placement(self) -> None:
        label = "collection-origin-plant-placement"

        def ready() -> None:
            dashboard = self.app.dashboard
            prepared = self._purchase_capture_snapshot(label)
            if prepared is None:
                self._next_after(200)
                return
            snapshot, plant = prepared
            plant.slot_index = None
            dashboard.refresh_all()
            dashboard._begin_collection_placement(plant.plant_id)
            QApplication.processEvents()
            dashboard_scroll = dashboard.dashboard_scroll
            dashboard_scrollbar = dashboard_scroll.verticalScrollBar()
            dashboard_scrollbar.setValue(dashboard_scrollbar.maximum())
            QApplication.processEvents()
            active = bool(
                dashboard._collection_placement_plant_id == plant.plant_id
                and dashboard.scene._interaction.placing
            )
            from .ui.plant_display import (
                bed_badge_rect,
                move_badge_label,
                move_target_state,
            )

            scene = dashboard.scene
            viewport = dashboard_scroll.viewport()
            scene_origin = scene.mapTo(viewport, scene.rect().topLeft())
            scene_viewport_bounds = [
                int(scene_origin.x()),
                int(scene_origin.y()),
                int(scene.width()),
                int(scene.height()),
            ]
            scene_fully_visible = bool(
                scene_origin.x() >= 0
                and scene_origin.y() >= 0
                and scene_origin.x() + scene.width() <= viewport.width()
                and scene_origin.y() + scene.height() <= viewport.height()
            )
            scene_plants = list(scene.scene.get("plants", ()))
            occupied_slots = {
                int(candidate.get("slot_index", -1))
                for candidate in scene_plants
            }
            occupant_names = {
                int(candidate.get("slot_index", -1)): str(
                    candidate.get("name")
                    or candidate.get("species")
                    or "plant"
                )
                for candidate in scene_plants
            }
            unlocked_slots = max(
                0,
                min(
                    6,
                    int(scene.scene.get("unlocked_slots", len(occupied_slots))),
                ),
            )
            valid_destinations = set(scene._destination_slots())
            origin_slot = scene._interaction.drag_origin_slot
            unplaced_placement = bool(
                origin_slot is None or int(origin_slot) < 0
            )
            destination_slot = scene._interaction.destination_slot
            hovered_slot = scene._hovered_move_slot
            plant_obstacles = [
                layout.visible.expanded(4.0, 3.0)
                for _candidate, layout in scene._layout_plants(
                    scene.width(),
                    scene.height(),
                )
            ]
            badge_font = QFont(scene.font())
            badge_font.setPointSizeF(11.0)
            badge_font.setBold(True)
            badge_metrics = QFontMetricsF(badge_font)
            placed_badges = []
            badge_audits: list[dict[str, Any]] = []

            for slot, row in scene._slot_placements.items():
                target_state = move_target_state(
                    slot,
                    origin_slot=origin_slot,
                    valid_destination_slots=valid_destinations,
                    unlocked_slots=unlocked_slots,
                )
                semantic_label, semantic_state = move_badge_label(
                    slot,
                    origin_slot=origin_slot,
                    destination_slot=(
                        slot
                        if slot == hovered_slot and target_state == "valid"
                        else destination_slot
                    ),
                    unlocked_slots=unlocked_slots,
                    occupied_slots=occupied_slots,
                    occupant_names=occupant_names,
                )
                current = target_state == "current"
                occupied_target = slot in occupied_slots and not current
                visual_label = (
                    "Current"
                    if current else
                    "Occupied"
                    if target_state == "unavailable" and occupied_target else
                    "Invalid"
                    if target_state == "unavailable" else
                    "Locked"
                    if target_state == "locked" else
                    "Place here"
                    if (
                        unplaced_placement
                        and semantic_state in {"active", "available"}
                    ) else
                    "Move here"
                    if semantic_state in {"active", "available"} else
                    semantic_label
                )
                badge = bed_badge_rect(
                    row,
                    visual_label,
                    scene.width(),
                    scene.height(),
                    [*plant_obstacles, *placed_badges],
                )
                text_width = float(badge_metrics.horizontalAdvance(visual_label))
                text_height = float(badge_metrics.height())
                contained = bool(
                    badge.x >= 4.0
                    and badge.y >= 4.0
                    and badge.right <= float(scene.width()) - 4.0
                    and badge.bottom <= float(scene.height()) - 4.0
                )
                clear_previous_badges = not any(
                    badge.intersects(previous) for previous in placed_badges
                )
                clear_plant_artwork = not any(
                    badge.intersects(obstacle) for obstacle in plant_obstacles
                )
                text_fits = bool(
                    text_width <= badge.width - 12.0
                    and text_height <= badge.height - 8.0
                )
                badge_audits.append({
                    "slot": int(slot),
                    "label": visual_label,
                    "semantic_state": semantic_state,
                    "rect": [
                        round(float(badge.x), 3),
                        round(float(badge.y), 3),
                        round(float(badge.width), 3),
                        round(float(badge.height), 3),
                    ],
                    "text_size": [
                        round(text_width, 3),
                        round(text_height, 3),
                    ],
                    "contained": contained,
                    "clear_previous_badges": clear_previous_badges,
                    "clear_plant_artwork": clear_plant_artwork,
                    "text_fits": text_fits,
                })
                placed_badges.append(badge)

            occupied_badge_widths = [
                float(audit["rect"][2])
                for audit in badge_audits
                if audit["label"] == "Occupied"
            ]
            occupied_badges_legible = bool(
                occupied_badge_widths
                and all(width >= 80.0 for width in occupied_badge_widths)
            )
            badge_text_fits = bool(
                badge_audits
                and all(audit["text_fits"] for audit in badge_audits)
            )
            badges_contained = bool(
                badge_audits
                and all(audit["contained"] for audit in badge_audits)
            )
            badges_pairwise_non_overlapping = bool(
                badge_audits
                and all(
                    audit["clear_previous_badges"] for audit in badge_audits
                )
            )
            badges_clear_plant_artwork = bool(
                badge_audits
                and all(audit["clear_plant_artwork"] for audit in badge_audits)
            )
            placement_badges = [
                audit
                for audit in badge_audits
                if audit["semantic_state"] in {"active", "available"}
            ]
            painted_move_labels = {
                int(slot): str(painted_label)
                for slot, painted_label in dict(
                    getattr(scene, "_painted_move_labels", {})
                ).items()
            }
            placement_labels_correct = bool(
                unplaced_placement
                and placement_badges
                and painted_move_labels
                and "Place here" in painted_move_labels.values()
                and "Move here" not in painted_move_labels.values()
            )
            self._capture_annotations[label] = {
                "passed": bool(
                    active
                    and occupied_badges_legible
                    and badge_text_fits
                    and badges_contained
                    and badges_pairwise_non_overlapping
                    and badges_clear_plant_artwork
                    and placement_labels_correct
                    and scene_fully_visible
                ),
                "plant_id": plant.plant_id,
                "placement_active": active,
                "badge_font_point_size": 11.0,
                "badge_font_bold": True,
                "badge_audits": badge_audits,
                "occupied_badge_widths": occupied_badge_widths,
                "occupied_badges_legible": occupied_badges_legible,
                "badge_text_fits": badge_text_fits,
                "badges_contained": badges_contained,
                "badges_pairwise_non_overlapping": (
                    badges_pairwise_non_overlapping
                ),
                "badges_clear_plant_artwork": badges_clear_plant_artwork,
                "painted_move_labels": painted_move_labels,
                "placement_labels_correct": placement_labels_correct,
                "scene_viewport_bounds": scene_viewport_bounds,
                "scene_fully_visible": scene_fully_visible,
            }

            def cleanup() -> None:
                if dashboard.scene._interaction.placing:
                    dashboard.scene.finish_move("Capture complete.")
                dashboard._collection_placement_plant_id = ""
                dashboard.rearrange_bar.hide()
                dashboard_scrollbar.setValue(0)
                QApplication.processEvents()
                self._restore_purchase_capture(snapshot)

            self._capture_and_advance(
                label,
                dashboard,
                capture_delay_ms=460,
                close_callback=cleanup,
                close_ms=800,
                next_ms=1120,
            )

        self._with_dashboard(ready, failure_label=label)

    def _capture_collection_loadout_detail(self) -> None:
        self._with_dashboard(self._capture_collection_loadout_detail_after)

    def _capture_collection_loadout_detail_after(self) -> None:
        dashboard = getattr(self.app, "dashboard", None)
        opener = getattr(dashboard, "_open_loadout_detail", None)
        if dashboard is None or not callable(opener):
            self._failures.append({
                "label": "collection-loadout-detail",
                "reason": "Collection loadout detail opener was unavailable",
            })
            self._next_after(250)
            return
        opener()
        dialog = getattr(dashboard, "collectible_detail_dialog", None)
        self._wait_for(
            lambda: bool(dialog is not None and dialog.isVisible()),
            lambda: self._capture_and_advance(
                "collection-loadout-detail",
                dialog,
                capture_delay_ms=420,
                close_callback=lambda: self._close_widget(dialog),
                close_ms=780,
                next_ms=1200,
            ),
            tries=80,
            failure_label="collection-loadout-detail",
            failure_reason="Collection loadout detail did not become ready",
        )

    def _capture_collection_preview_active(self) -> None:
        self._capture_collection_preview("collection-preview-active", False)

    def _capture_collection_preview_restored(self) -> None:
        self._capture_collection_preview("collection-preview-restored", True)

    def _capture_collection_preview(self, label: str, enabled: bool) -> None:
        self._with_dashboard(
            lambda: self._capture_collection_preview_after(label, enabled)
        )

    def _capture_collection_preview_after(self, label: str, enabled: bool) -> None:
        dashboard = getattr(self.app, "dashboard", None)
        opener = getattr(dashboard, "_open_loadout_detail", None)
        if dashboard is None or not callable(opener):
            self._failures.append({
                "label": label,
                "reason": "Collection loadout detail opener was unavailable",
            })
            self._next_after(250)
            return
        opener()
        dialog = getattr(dashboard, "collectible_detail_dialog", None)

        def ready() -> None:
            dialog.option_tabs.setCurrentWidget(dialog.effects_page)
            persisted_draft = tuple(dialog._persisted_draft)
            persisted_weather_visible = bool(persisted_draft[3])
            persisted_scenery_visible = bool(persisted_draft[4])
            expected_weather_visible = bool(enabled)
            expected_scenery_visible = bool(enabled)
            committed_before = {
                "weather": str(self.app.storage.state.selected_weather),
                "scenery": str(self.app.storage.state.selected_background),
                "visibility": deepcopy(
                    self.app.storage.state.environment_visibility
                ),
                "loadout": deepcopy(self.app.storage.state.loadout.to_dict()),
            }
            dirty_preview_created = False
            reset_path_invoked = False

            if label == "collection-preview-restored":
                expected_weather_visible = persisted_weather_visible
                expected_scenery_visible = persisted_scenery_visible
                dialog.show_weather.setChecked(not persisted_weather_visible)
                dialog.show_scenery.setChecked(not persisted_scenery_visible)
                QApplication.processEvents()
                dirty_preview_created = bool(
                    dialog._draft_key() != persisted_draft
                    and dialog.dialog_dirty
                    and str(dialog.property("transactionPresentation") or "")
                    == "preview"
                )
                # Exercise the real Restore saved appearance control path, not
                # a direct toggle assignment that merely resembles its result.
                dialog._reset_preview()
                reset_path_invoked = True
                QApplication.processEvents()
            else:
                dialog.show_weather.setChecked(expected_weather_visible)
                dialog.show_scenery.setChecked(expected_scenery_visible)

            committed_after = {
                "weather": str(self.app.storage.state.selected_weather),
                "scenery": str(self.app.storage.state.selected_background),
                "visibility": deepcopy(
                    self.app.storage.state.environment_visibility
                ),
                "loadout": deepcopy(self.app.storage.state.loadout.to_dict()),
            }
            draft_restored = bool(
                dialog._draft_key() == persisted_draft
                and bool(dialog.show_weather.isChecked()) == persisted_weather_visible
                and bool(dialog.show_scenery.isChecked()) == persisted_scenery_visible
                and str(dialog.property("transactionPresentation") or "")
                == "committed-state"
            )
            committed_state_unchanged = committed_after == committed_before
            preview_feedback = getattr(dialog, "preview_feedback", None)
            if (
                label == "collection-preview-restored"
                and preview_feedback is not None
            ):
                preview_feedback.setProperty(
                    "captureEvidenceKey",
                    "restored-preview-banner",
                )
            preview_feedback_text = str(
                getattr(getattr(preview_feedback, "message", None), "text", lambda: "")()
                if preview_feedback is not None else ""
            ).strip()
            preview_feedback_bounds = self._widget_bounds_evidence(
                preview_feedback,
                dialog.body_scroll.viewport(),
            )
            restored_preview_visual = {
                "text": preview_feedback_text,
                "visible": bool(
                    preview_feedback is not None
                    and preview_feedback.isVisible()
                ),
                "bounds": preview_feedback_bounds.get("bounds", []),
                "contained": bool(preview_feedback_bounds.get("contained", False)),
            }
            restored_preview_visual["passed"] = bool(
                label != "collection-preview-restored"
                or (
                    restored_preview_visual["text"] == "Preview reset."
                    and restored_preview_visual["visible"]
                    and restored_preview_visual["contained"]
                )
            )
            transition_passed = bool(
                label != "collection-preview-restored"
                or (
                    dirty_preview_created
                    and reset_path_invoked
                    and draft_restored
                    and committed_state_unchanged
                    and restored_preview_visual["passed"]
                )
            )
            self._capture_annotations[label] = {
                "dirty_preview_created": dirty_preview_created,
                "reset_path_invoked": reset_path_invoked,
                "draft_restored": draft_restored,
                "committed_state_unchanged": committed_state_unchanged,
                "persisted_visibility": [
                    persisted_weather_visible,
                    persisted_scenery_visible,
                ],
                "restored_preview_visual": restored_preview_visual,
                "restored_preview_dirty_cleared": bool(
                    not dialog.dialog_dirty
                    and dialog.unsaved.isHidden()
                    and not str(dialog.unsaved.text()).strip()
                ),
                "passed": transition_passed,
            }

            def state_ready() -> bool:
                return bool(
                    dialog.isVisible()
                    and dialog.option_tabs.currentIndex()
                    == dialog.option_tabs.indexOf(dialog.effects_page)
                    and bool(dialog.show_weather.isChecked()) == expected_weather_visible
                    and bool(dialog.show_scenery.isChecked()) == expected_scenery_visible
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
                failure_reason=f"Collection preview {label!r} did not become ready",
            )

        self._wait_for(
            lambda: bool(dialog is not None and dialog.isVisible()),
            ready,
            tries=80,
            failure_label=label,
            failure_reason="Collection loadout detail did not become ready",
        )

    def _capture_nursery_tab(
        self,
        index: int,
        label: str,
        *,
        fixture_setup: Callable[[Any], Callable[[], None]] | None = None,
        ready_audit: Callable[[Any], None] | None = None,
    ) -> None:
        self._with_dashboard(
            lambda: self._capture_nursery_tab_after(
                index,
                label,
                fixture_setup=fixture_setup,
                ready_audit=ready_audit,
            ),
            failure_label=label,
        )

    def _capture_nursery_tab_after(
        self,
        index: int,
        label: str,
        *,
        fixture_setup: Callable[[Any], Callable[[], None]] | None = None,
        ready_audit: Callable[[Any], None] | None = None,
    ) -> None:
        dashboard = getattr(self.app, "dashboard", None)
        open_nursery = getattr(dashboard, "_open_nursery", None)
        if dashboard is None or not callable(open_nursery):
            self._failures.append({
                "label": label,
                "reason": "Nursery opener was unavailable",
            })
            self._next_after(250)
            return
        cleanup: Callable[[], None] = lambda: None
        try:
            if fixture_setup is not None:
                cleanup = fixture_setup(dashboard)
        except Exception as exc:
            cleanup()
            self._failures.append({
                "label": label,
                "reason": (
                    "Nursery fixture setup raised "
                    f"{type(exc).__name__}"
                ),
            })
            self._close_dashboard()
            self._next_after(250)
            return

        def ready() -> None:
            dialog = getattr(dashboard, "nursery_dialog", None)

            if ready_audit is not None:
                ready_audit(dialog)

            def close_and_restore() -> None:
                self._close_widget(dialog)
                cleanup()

            self._capture_and_advance(
                label,
                dialog,
                capture_delay_ms=420,
                close_callback=close_and_restore,
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
                on_error=cleanup,
            ),
        )
        try:
            open_nursery(index)
        except Exception:
            cleanup()
            raise

    def _capture_nursery_plants(self) -> None:
        self._capture_nursery_tab(0, "nursery-plants")

    def _capture_nursery_fertilizer_booster(self) -> None:
        label = "nursery-fertilizer-booster"
        fixture: dict[str, Any] = {}

        def setup(dashboard: Any) -> Callable[[], None]:
            from .collectibles import collectible_registry

            snapshot = self._capture_fixture_state_snapshot(label)
            try:
                state = self.app.storage.state
                item = next(
                    definition
                    for definition in collectible_registry()
                    if definition.item_id == "growth_items:fertilizer_basic"
                )
                target = next(
                    (
                        plant
                        for plant in list(getattr(state, "plants", ()) or ())
                        if bool(getattr(plant, "planted", False))
                        and not bool(getattr(plant, "fully_grown", False))
                    ),
                    None,
                )
                if target is None:
                    raise RuntimeError(
                        "Rich Compost capture requires an unfinished planted plant"
                    )
                target.fertilizer = None
                state.active_plant_id = str(target.plant_id)
                state.consumables["fertilizer_basic"] = max(
                    1,
                    int(state.consumables.get("fertilizer_basic", 0) or 0),
                )
                fixture.update({
                    "item_display_name": str(item.name),
                    "item_id": str(item.source_id),
                    "target_plant_id": str(target.plant_id),
                })
                dashboard.refresh_all()
            except Exception:
                self._restore_capture_fixture_state(snapshot)
                raise
            return lambda: self._restore_capture_fixture_state(snapshot)

        def audit(dialog: Any) -> None:
            item_id = str(fixture.get("item_id", ""))
            card = next(
                (
                    candidate
                    for candidate in dialog.findChildren(QFrame)
                    if str(candidate.property("catalogItemId") or "") == item_id
                ),
                None,
            )
            action = next(
                iter(card.findChildren(QAbstractButton)),
                None,
            ) if card is not None else None
            action_text = (
                _displayed_button_text(action) if action is not None else ""
            )
            state = self.app.storage.state
            owned_count = int(state.consumables.get(item_id, 0) or 0)
            passed = bool(
                action is not None
                and action.isVisible()
                and action.isEnabled()
                and owned_count >= 1
                and str(getattr(state, "active_plant_id", "") or "")
                == fixture.get("target_plant_id")
            )
            self._capture_annotations[label] = {
                **fixture,
                "action_text": action_text,
                "action_visible": bool(action is not None and action.isVisible()),
                "action_enabled": bool(action is not None and action.isEnabled()),
                "owned_count": owned_count,
                "passed": passed,
            }

        self._capture_nursery_tab(
            1,
            label,
            fixture_setup=setup,
            ready_audit=audit,
        )

    def _capture_nursery_garden_spaces(self) -> None:
        self._capture_nursery_tab(2, "nursery-garden-spaces")

    def _capture_nursery_weather_scenery(self) -> None:
        label = "nursery-weather-scenery"
        preview_names = ("Clear Skies preview", "Soft Breeze preview")

        def pixmap_signature(pixmap: Any) -> list[int]:
            image = pixmap.toImage()
            width = max(1, int(image.width()))
            height = max(1, int(image.height()))
            return [
                int(image.pixel(
                    min(width - 1, width * column // 7),
                    min(height - 1, height * row // 5),
                ))
                for row in range(1, 5)
                for column in range(1, 7)
            ]

        def audit(dialog: Any) -> None:
            previews: dict[str, list[tuple[int, QLabel, list[int]]]] = {
                name: [] for name in preview_names
            }
            missing_art_previews: list[str] = []
            for preview in dialog.findChildren(QLabel):
                name = str(preview.accessibleName())
                if name not in previews or not preview.isVisible():
                    continue
                pixmap = preview.pixmap()
                if (
                    pixmap is None
                    or pixmap.isNull()
                    or str(preview.property("gardenRole") or "") == "missing-art"
                ):
                    missing_art_previews.append(name)
                    continue
                previews[name].append((
                    int(pixmap.width()) * int(pixmap.height()),
                    preview,
                    pixmap_signature(pixmap),
                ))

            selected_signatures: dict[str, list[int]] = {}
            selected_sizes: dict[str, list[int]] = {}
            for name, matches in previews.items():
                if not matches:
                    continue
                _area, preview, signature = min(matches, key=lambda row: row[0])
                pixmap = preview.pixmap()
                selected_signatures[name] = signature
                selected_sizes[name] = [
                    int(pixmap.width()),
                    int(pixmap.height()),
                ]

            clear_signature = selected_signatures.get(preview_names[0])
            breeze_signature = selected_signatures.get(preview_names[1])
            distinct = bool(
                clear_signature
                and breeze_signature
                and clear_signature != breeze_signature
            )
            passed = bool(
                clear_signature
                and breeze_signature
                and not missing_art_previews
                and distinct
            )
            self._capture_annotations[label] = {
                "clear_skies_preview_present": bool(clear_signature),
                "soft_breeze_preview_present": bool(breeze_signature),
                "missing_art_previews": missing_art_previews,
                "preview_match_counts": {
                    name: len(matches) for name, matches in previews.items()
                },
                "preview_sizes": selected_sizes,
                "preview_signatures_distinct": distinct,
                "passed": passed,
            }
            if not passed:
                self._failures.append({
                    "label": label,
                    "reason": (
                        "Clear Skies and Soft Breeze did not expose distinct "
                        "packaged preview artwork"
                    ),
                })

        self._capture_nursery_tab(
            3,
            label,
            ready_audit=audit,
        )

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
        reveal_plant_card: bool = False,
    ) -> None:
        def ready() -> None:
            if mutate is not None:
                mutate()
            self._refresh_capture_dashboard()
            if reveal_plant_card:
                self._reveal_capture_plant_card(label)
            toast = getattr(self.app.dashboard, "toast_region", None)
            clear_toast = getattr(toast, "clear", None)
            if callable(clear_toast):
                clear_toast()
            self._capture_and_advance(
                label,
                self.app.dashboard,
                capture_delay_ms=delay_ms,
                next_ms=980,
            )

        self._with_dashboard(ready)

    def _reveal_capture_plant_card(self, label: str) -> None:
        """Reveal the complete selected card inside the intentional Dashboard scroll."""

        dashboard = getattr(self.app, "dashboard", None)
        card = getattr(dashboard, "plant_card", None)
        scroll = getattr(dashboard, "dashboard_scroll", None)
        annotation = self._capture_annotations.setdefault(label, {})
        if card is None or scroll is None or not card.isVisible():
            annotation.update({
                "plant_card_viewport_bounds": [],
                "plant_card_fully_visible": False,
                "passed": False,
            })
            self._failures.append({
                "label": label,
                "reason": "Selected plant details were unavailable for viewport reveal",
            })
            return
        QApplication.processEvents()
        scroll.ensureWidgetVisible(card, 0, 24)
        QApplication.processEvents()
        viewport = scroll.viewport()
        origin = card.mapTo(viewport, card.rect().topLeft())
        bounds = [
            int(origin.x()),
            int(origin.y()),
            int(card.width()),
            int(card.height()),
        ]
        contained = bool(
            bounds[0] >= 0
            and bounds[1] >= 0
            and bounds[0] + bounds[2] <= int(viewport.width())
            and bounds[1] + bounds[3] <= int(viewport.height())
        )
        annotation.update({
            "plant_card_viewport_bounds": bounds,
            "plant_card_viewport_size": [
                int(viewport.width()),
                int(viewport.height()),
            ],
            "plant_card_fully_visible": contained,
            "passed": bool(annotation.get("passed", True)) and contained,
        })
        if not contained:
            self._failures.append({
                "label": label,
                "reason": "Selected plant details did not fit the Dashboard capture viewport",
            })

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
        from .models.state import (
            CURRENT_CATALOG_SPECIES_ORDER,
            GROWTH_THRESHOLDS,
            MAX_GARDEN_SLOTS,
        )

        ok, message = self.app.engine.development_populate()
        if not ok:
            self._failures.append({
                "label": "development-stress-state",
                "reason": str(message),
            })
            return False
        state = self.app.storage.state
        catalog_order = tuple(str(species) for species in CURRENT_CATALOG_SPECIES_ORDER)
        release_ready_order = tuple(
            str(species) for species in self.app.engine.release_ready_species()
        )
        declared_order = tuple(DEVELOPMENT_STRESS_SPECIES_ORDER)
        if catalog_order != declared_order or release_ready_order != declared_order:
            self._failures.append({
                "label": "development-stress-state",
                "reason": (
                    "Development capture species order disagreed with the current "
                    "catalog or release-ready asset projection "
                    f"(catalog={catalog_order!r}, release_ready={release_ready_order!r})"
                ),
            })
            return False
        original_plants = list(state.plants)
        original_ids = sorted(
            str(getattr(plant, "plant_id", "") or "")
            for plant in original_plants
        )
        plants = canonicalize_development_stress_plants(
            original_plants,
            catalog_order,
            self.app.engine._generated_name,
        )
        canonical_species = tuple(
            str(getattr(plant, "species", "") or "") for plant in plants
        )
        canonical_ids = [
            str(getattr(plant, "plant_id", "") or "") for plant in plants
        ]
        if (
            len(plants) != len(declared_order)
            or canonical_species != declared_order
            or len(set(canonical_ids)) != len(declared_order)
            or sorted(canonical_ids) != original_ids
        ):
            self._failures.append({
                "label": "development-stress-state",
                "reason": (
                    "Development population did not preserve one canonical "
                    f"instance for all ten species ({canonical_species!r})"
                ),
            })
            return False
        state.plants = plants
        for index, plant in enumerate(plants):
            plant.slot_index = index if index < MAX_GARDEN_SLOTS else None
            plant.growth_points = GROWTH_THRESHOLDS[index % len(GROWTH_THRESHOLDS)]
        state.unlocked_species = list(declared_order)
        state.unlocked_slots = MAX_GARDEN_SLOTS
        state.currency_balance = 9_999
        state.currency_transactions.clear()
        state.active_plant_id = plants[0].plant_id
        state.onboarding.starter_plant_id = plants[0].plant_id
        try:
            # development_populate() commits its shuffled seed. Persist the
            # canonical capture ordering and its matching bounded ledgers
            # before later fixtures take rollback checkpoints.
            self.app.storage.save()
        except Exception as exc:
            self._failures.append({
                "label": "development-stress-state",
                "reason": (
                    "Canonical development capture state could not be saved: "
                    f"{type(exc).__name__}"
                ),
            })
            return False
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
            reveal_plant_card=True,
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
            # Opening an in-scene card must not move the page-level Dashboard
            # scroll owner or clip the header. The card is clamped by the
            # scene itself, so surface evidence is captured from scroll zero.
            dashboard.dashboard_scroll.verticalScrollBar().setValue(0)
            QApplication.processEvents()
            if not bool(dashboard.plant_card.isVisible()):
                self._failures.append({
                    "label": label,
                    "reason": "Selected plant details were not visible for this plot",
                })

        self._capture_dashboard_stress(
            label,
            mutate,
            delay_ms=520,
            reveal_plant_card=False,
        )

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
            QApplication.processEvents()
            scrollbar = dashboard.dashboard_scroll.verticalScrollBar()
            scrollbar.setValue(0)
            QApplication.processEvents()

            def cleanup() -> None:
                dashboard._cancel_move()
                scrollbar.setValue(0)
                QApplication.processEvents()

            self._capture_and_advance(
                "move-occupied-empty-destinations",
                dashboard,
                capture_delay_ms=560,
                close_callback=cleanup,
                close_ms=820,
                next_ms=1150,
            )

        self._with_dashboard(ready)

    def _prepare_expiring_fertilizer(self) -> str:
        from .models.state import Fertilizer

        if not self._ensure_development_stress_state():
            return ""
        plant = self.app.storage.state.plants[0]
        plant.slot_index = 0
        self.app.storage.state.active_plant_id = plant.plant_id
        now = self.app.engine._now_seconds()
        plant.fertilizer = Fertilizer("basic", 1, now + 45, now)
        self._refresh_capture_dashboard()
        return plant.plant_id

    def _capture_fertilizer_expiring(self) -> None:
        label = "fertilizer-expiring-under-minute"
        cleanup_holder: dict[str, Callable[[], None]] = {
            "callback": lambda: None,
        }

        def registered_cleanup() -> None:
            cleanup_holder["callback"]()

        def ready() -> None:
            if not self._ensure_development_stress_state():
                self._next_after(200)
                return
            snapshot = self._capture_fixture_state_snapshot(label)

            def cleanup() -> None:
                self._restore_capture_fixture_state(snapshot)

            cleanup_holder["callback"] = cleanup
            plant_id = self._prepare_expiring_fertilizer()
            dashboard = self.app.dashboard
            if not plant_id:
                cleanup()
                self._next_after(200)
                return

            def dialog_ready() -> None:
                dialog = getattr(dashboard, "fertilizer_dialog", None)

                def close_dialog() -> None:
                    self._close_widget(dialog)
                    cleanup()

                self._capture_and_advance(
                    label,
                    dialog,
                    capture_delay_ms=420,
                    close_callback=close_dialog,
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
                    failure_label=label,
                    failure_reason="Expiring Fertilizer dialog did not become ready",
                    on_error=cleanup,
                ),
            )
            dashboard._open_fertilizer_menu(plant_id)

        self._with_dashboard(
            ready,
            failure_label=label,
            on_error=registered_cleanup,
        )

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
        label = "fertilizer-replacement-confirmation"
        cleanup_holder: dict[str, Callable[[], None]] = {
            "callback": lambda: None,
        }

        def registered_cleanup() -> None:
            cleanup_holder["callback"]()

        def ready() -> None:
            if not self._ensure_development_stress_state():
                self._next_after(200)
                return
            snapshot = self._capture_fixture_state_snapshot(label)

            def cleanup() -> None:
                self._restore_capture_fixture_state(snapshot)

            cleanup_holder["callback"] = cleanup
            plant_id = self._prepare_expiring_fertilizer()
            dashboard = self.app.dashboard
            if not plant_id:
                cleanup()
                self._next_after(200)
                return

            def fertilizer_ready() -> None:
                dialog = getattr(dashboard, "fertilizer_dialog", None)
                replace = next(
                    (
                        button for button in dialog.findChildren(QAbstractButton)
                        if _displayed_button_text(button) == "Buy and replace"
                        and button.isEnabled()
                    ),
                    None,
                )
                if replace is None:
                    self._failures.append({
                        "label": label,
                        "reason": "No enabled replacement action was available",
                    })
                    self._close_widget(dialog)
                    cleanup()
                    self._next_after(200)
                    return

                def confirmation_ready() -> None:
                    replacement_dialog = self._visible_fertilizer_replacement_dialog()

                    def close_confirmation() -> None:
                        self._close_widget(replacement_dialog)
                        self._close_widget(dialog)
                        cleanup()

                    self._capture_and_advance(
                        label,
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
                    failure_label=label,
                    failure_reason="Replacement confirmation did not become visible",
                    on_error=cleanup,
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
                    failure_label=label,
                    failure_reason="Fertilizer dialog did not become ready",
                    on_error=cleanup,
                ),
            )
            dashboard._open_fertilizer_menu(plant_id)

        self._with_dashboard(
            ready,
            failure_label=label,
            on_error=registered_cleanup,
        )

    def _set_nurtured_capture_slot(self, slot: int, label: str) -> bool:
        """Commit a valid nurtured plant in one of the six disposable plots."""

        if not self._ensure_development_stress_state():
            return False
        from .models.state import CURRENT_CATALOG_SPECIES_ORDER

        state = self.app.storage.state
        catalog_order = {
            species: index
            for index, species in enumerate(CURRENT_CATALOG_SPECIES_ORDER)
        }
        plants = sorted(
            list(state.plants),
            key=lambda item: (
                catalog_order.get(str(getattr(item, "species", "") or ""), 10_000),
                str(getattr(item, "plant_id", "") or ""),
            ),
        )
        # Earlier release faces deliberately exercise an occupied/empty move
        # matrix, long names, large balances, and stage extremes. Re-seat a
        # canonical, deterministic six-plant scene before every marker face so
        # watering position is the only variable under audit.
        state.garden_name = WATERING_CAPTURE_GARDEN_NAME
        state.currency_balance = WATERING_CAPTURE_CURRENCY_BALANCE
        for index, item in enumerate(plants):
            item.slot_index = index if index < 6 else None
            item.name = (
                f"{str(item.species).replace('_', ' ').title()} Plant"
            )[:40]
            item.name_customized = False
            if index < 6:
                item.growth_points = WATERING_CAPTURE_GROWTH_POINTS
                item.fertilizer = None
        plant = plants[slot] if 0 <= int(slot) < min(6, len(plants)) else None
        if plant is None:
            self._failures.append({
                "label": label,
                "reason": f"Plot {slot + 1} did not contain a plant",
            })
            return False
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
        restore_fixture: Callable[[], None] | None = None
        opposite = "overview" if surface == "deckBrowser" else "deckBrowser"
        self._switch_surface(opposite)

        def enter_surface() -> None:
            invalidate = getattr(self.app, "_invalidate_home_cache", None)
            if callable(invalidate):
                invalidate(f"capture transition for {label}")
            self._switch_surface(surface)
            QTimer.singleShot(
                420,
                lambda: self._wait_for_home_surface(
                    surface,
                    label,
                    lambda: self._capture_and_advance(
                        label,
                        mw,
                        capture_delay_ms=650,
                        close_callback=restore_fixture,
                        close_ms=760 if restore_fixture is not None else 0,
                        next_ms=1200,
                    ),
                ),
            )

        def opposite_surface_settled() -> None:
            # ``mw.state`` changes before WebEngine finishes the corresponding
            # navigation. Let that real page load settle before requesting the
            # target state, otherwise repeated Home fixtures can strand the
            # renderer with every subsequent JavaScript callback discarded.
            QTimer.singleShot(420, enter_surface)

        # Consecutive Home fixtures alternate through the opposite Anki state
        # so WebEngine must construct a new source-backed root. A fixed delay
        # alone can race moveToState() under capture load, leaving the old
        # active-slot DOM in place even though the model has advanced. Wait for
        # the state transition, then give the matching WebEngine navigation one
        # bounded settle interval before returning to the requested surface.
        self._wait_for(
            lambda: str(getattr(mw, "state", "")) == opposite,
            opposite_surface_settled,
            tries=80,
            failure_label=label,
            failure_reason=(
                f"Anki Home did not reach the intermediate {opposite} state"
            ),
        )

    def _capture_collection_several(self) -> None:
        label = "collection-several-discovered"
        state = self.app.storage.state
        original_plants = list(state.plants)
        original_unlocked = list(state.unlocked_species)
        original_active = state.active_plant_id
        dashboard = getattr(self.app, "dashboard", None)
        original_filter = str(
            getattr(dashboard, "_collection_filter", "all") or "all"
        )
        restored = False

        def restore() -> None:
            nonlocal restored
            if restored:
                return
            restored = True
            state.plants = original_plants
            state.unlocked_species = original_unlocked
            state.active_plant_id = original_active
            if dashboard is not None:
                dashboard._collection_filter = original_filter
            self._refresh_capture_dashboard()

        if not self._ensure_development_stress_state():
            restore()
            self._next_after(200)
            return

        release_ready = list(self.app.engine.release_ready_species())
        plants_by_species = {
            str(plant.species): plant for plant in original_plants
        }
        discovered_species = [
            species for species in release_ready
            if species in plants_by_species
        ][:4]
        if len(discovered_species) != 4 or len(release_ready) <= 4:
            self._failures.append({
                "label": label,
                "reason": "Several-discovered fixture could not retain four of a larger catalog",
            })
            restore()
            self._next_after(200)
            return
        try:
            state.plants = [plants_by_species[species] for species in discovered_species]
            state.unlocked_species = list(discovered_species)
            state.active_plant_id = state.plants[0].plant_id
            summary = self.app.engine.catalog_summary()
            discovered_count = len(summary.get("owned_species", ()))
            total_count = len(summary.get("release_ready_species", ()))
            passed = discovered_count == 4 and total_count > discovered_count
            self._capture_annotations[label] = {
                "collected_species": list(discovered_species),
                "collected_count": discovered_count,
                "catalog_count": total_count,
                "passed": passed,
            }
            if not passed:
                self._failures.append({
                    "label": label,
                    "reason": (
                        "Several-discovered fixture did not project four discovered "
                        f"species in a larger catalog ({discovered_count}/{total_count})"
                    ),
                })

            self._refresh_capture_dashboard()
            self._capture_collection_filter(
                "all",
                label,
                restore_callback=restore,
            )
        except Exception:
            restore()
            raise

    def _capture_collection_no_matches(self) -> None:
        if not self._ensure_development_stress_state():
            self._next_after(200)
            return
        from .collectibles import collectible_views

        label = "collection-no-filter-matches"
        snapshot = self._capture_fixture_state_snapshot(label)
        state = self.app.storage.state

        def restore() -> None:
            self._restore_capture_fixture_state(snapshot)

        try:
            locked = [view for view in collectible_views(state) if not view.owned]
            unsupported = [
                view.definition.item_id
                for view in locked
                if view.definition.category != "growth_items"
            ]
            if unsupported:
                self._failures.append({
                    "label": label,
                    "reason": (
                        "No-matches fixture found non-growth collectibles that "
                        "the development stress state did not own: "
                        + ", ".join(unsupported)
                    ),
                })
                restore()
                self._next_after(200)
                return
            for view in locked:
                item_id = str(view.definition.source_id)
                state.consumables[item_id] = max(
                    1,
                    int(state.consumables.get(item_id, 0) or 0),
                )
            remaining = [
                view.definition.item_id
                for view in collectible_views(state)
                if not view.owned
            ]
            if remaining:
                self._failures.append({
                    "label": label,
                    "reason": (
                        "No-matches fixture could not derive complete ownership "
                        "from the Collection registry: " + ", ".join(remaining)
                    ),
                })
                restore()
                self._next_after(200)
                return
            self._refresh_capture_dashboard()
            self._capture_collection_filter(
                "not_collected",
                label,
                restore_callback=restore,
            )
        except Exception:
            restore()
            raise

    def _capture_achievement_completed(self) -> None:
        from .achievements import (
            ACHIEVEMENT_DEFINITIONS,
            AchievementProgressMetric,
        )

        if not self._ensure_development_stress_state():
            self._next_after(200)
            return
        completed_ids = tuple(
            definition.achievement_id
            for definition in ACHIEVEMENT_DEFINITIONS
        )
        def metric_target(metric: AchievementProgressMetric) -> int:
            return max(
                (
                    max(
                        int(definition.progress_target),
                        int(definition.minimum_answers),
                    )
                    for definition in ACHIEVEMENT_DEFINITIONS
                    if definition.progress_metric is metric
                ),
                default=0,
            )

        streak_days = metric_target(AchievementProgressMetric.STREAK_DAYS)
        daily_answers = metric_target(AchievementProgressMetric.DAILY_ANSWERS)
        lifetime_answers = metric_target(
            AchievementProgressMetric.LIFETIME_ANSWERS
        )
        non_again_run = metric_target(
            AchievementProgressMetric.CONSECUTIVE_NON_AGAIN
        )
        snapshot, projections = self._prepare_canonical_achievement_capture_fixture(
            streak_days=streak_days,
            daily_answers=daily_answers,
            lifetime_answers=lifetime_answers,
            non_again_run=non_again_run,
            completed_ids=completed_ids,
        )
        self._capture_annotations["achievement-completed"] = {
            "projection_ids": [item.achievement_id for item in projections],
            "completed_projection_ids": [
                item.achievement_id for item in projections if item.completed
            ],
            "reward_summaries": {
                item.achievement_id: item.reward_summary
                for item in projections
            },
            "canonical_projection_count": len(projections),
            "streak_days": streak_days,
            "daily_answers": daily_answers,
            "lifetime_answers": lifetime_answers,
            "non_again_run": non_again_run,
            "passed": bool(
                len(projections) == len(ACHIEVEMENT_DEFINITIONS)
                and all(item.completed for item in projections)
                and all(bool(item.reward_summary) for item in projections)
            ),
        }
        dashboard = getattr(self.app, "dashboard", None)
        previous_filter = str(
            getattr(dashboard, "_achievement_filter", "all") or "all"
        )
        if dashboard is not None:
            dashboard._achievement_filter = "completed"

        def restore() -> None:
            if dashboard is not None:
                dashboard._achievement_filter = previous_filter
            self._restore_reward_capture_fixture(snapshot)

        self._refresh_capture_dashboard()
        self._capture_progress_page(
            "achievements",
            "achievement-completed",
            restore_callback=restore,
        )

    def _capture_clear_recall_projection(self) -> None:
        from .achievements import ACHIEVEMENTS_BY_ID
        from .reward_presentation import achievement_presentation

        if not self._ensure_development_stress_state():
            self._next_after(200)
            return
        definition = ACHIEVEMENTS_BY_ID["retention_90"]
        daily_answers = max(1, int(definition.minimum_answers) * 3 // 5)
        again_answers = max(1, daily_answers // 6)
        snapshot, projections = self._prepare_canonical_achievement_capture_fixture(
            daily_answers=daily_answers,
            again_answers=again_answers,
            non_again_run=max(
                1,
                int(ACHIEVEMENTS_BY_ID["retention_100"].progress_target) // 3,
            ),
        )
        projection = achievement_presentation(
            "retention_90",
            self.app.storage.state,
        )
        if projection is None:
            self._failures.append({
                "label": "clear-recall-canonical-projection",
                "reason": "Clear Recall canonical projection was unavailable",
            })
            self._restore_reward_capture_fixture(snapshot)
            self._next_after(200)
            return
        unlocked_ids = [
            item.achievement_id for item in projections if item.unlocked
        ]
        passed = bool(
            len(projection.condition_lines) >= 1
            and projection.current == daily_answers
            and projection.progress_target == definition.progress_target
            and projection.reward_coins == definition.reward.coins
            and projection.reward_small_growth_charges
            == definition.reward.small_growth_charges
            and projection.reward_standard_growth_charges
            == definition.reward.standard_growth_charges
            and not projection.completed
            and not unlocked_ids
        )
        if not passed:
            self._failures.append({
                "label": "clear-recall-canonical-projection",
                "reason": "Clear Recall did not match its canonical projection",
            })
        self._capture_annotations["clear-recall-canonical-projection"] = {
            "achievement_id": projection.achievement_id,
            "condition_lines": list(projection.condition_lines),
            "value_text": projection.value_text,
            "reward_summary": projection.reward_summary,
            "current": projection.current,
            "target": projection.progress_target,
            "daily_answers": daily_answers,
            "again_answers": again_answers,
            "unlocked_achievement_ids": unlocked_ids,
            "canonical_projection": True,
            "passed": passed,
        }
        dashboard = getattr(self.app, "dashboard", None)
        previous_filter = str(
            getattr(dashboard, "_achievement_filter", "all") or "all"
        )
        if dashboard is not None:
            dashboard._achievement_filter = "in_progress"

        def restore() -> None:
            if dashboard is not None:
                dashboard._achievement_filter = previous_filter
            self._restore_reward_capture_fixture(snapshot)

        self._refresh_capture_dashboard()
        self._capture_progress_page(
            "achievements",
            "clear-recall-canonical-projection",
            restore_callback=restore,
        )

    def _set_streak_capture_state(
        self,
        *,
        days: int,
        reviewed: int,
        last_active_offset: int,
        completed_ids: tuple[str, ...] = (),
    ) -> tuple[dict[str, Any], tuple[Any, ...]]:
        snapshot, projections = self._prepare_canonical_achievement_capture_fixture(
            streak_days=days,
            daily_answers=reviewed,
            completed_ids=completed_ids,
        )
        state = self.app.storage.state
        try:
            current_day = date.fromisoformat(str(state.daily_stats.day)[:10])
        except (TypeError, ValueError):
            current_day = date.today()
            state.daily_stats.day = current_day.isoformat()
        state.last_active_day = (current_day + timedelta(days=last_active_offset)).isoformat()
        if reviewed > 0:
            self._append_canonical_streak_reward_receipts(streak_days=days)
        self._refresh_capture_dashboard()
        return snapshot, projections

    def _capture_streak_at_risk(self) -> None:
        from .achievements import ACHIEVEMENTS_BY_ID

        definition = ACHIEVEMENTS_BY_ID["streak_7"]
        streak_days = int(definition.progress_target)
        snapshot, _projections = self._set_streak_capture_state(
            days=streak_days,
            reviewed=0,
            last_active_offset=-1,
            completed_ids=(definition.achievement_id,),
        )
        self._capture_annotations["streak-at-risk"] = {
            "achievement_id": definition.achievement_id,
            "streak_days": streak_days,
            "daily_answers": 0,
            "passed": bool(
                self.app.storage.state.streak_days == streak_days
                and self.app.storage.state.daily_stats.reviewed == 0
            ),
        }
        self._capture_metric(
            "streak",
            "streak-at-risk",
            restore_callback=lambda: self._restore_reward_capture_fixture(snapshot),
        )

    def _capture_streak_missed_day(self) -> None:
        from .achievements import ACHIEVEMENTS_BY_ID
        from .ui.state_contracts import StreakPresentationState, streak_presentation

        previous_days = max(
            1,
            int(ACHIEVEMENTS_BY_ID["streak_7"].progress_target) // 2,
        )
        snapshot, _projections = self._set_streak_capture_state(
            days=previous_days,
            reviewed=0,
            last_active_offset=-2,
        )
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
            and presentation.previous_days == previous_days
        ):
            self._failures.append({
                "label": "streak-missed-day",
                "reason": "Missed-day fixture did not project an ended 0-day streak with its previous context",
            })
        from .reward_presentation import recurring_reward_presentations

        weekly_reward = next(
            rule
            for rule in recurring_reward_presentations(
                state,
                self.app.engine,
                current_streak_days=presentation.current_days,
            )
            if rule.rule_id == "weekly_streak"
        )
        self._capture_annotations["streak-missed-day"] = {
            "previous_streak_days": previous_days,
            "daily_answers": 0,
            "presentation_state": presentation.state.value,
            "projected_streak_days": presentation.current_days,
            "weekly_reward_status": weekly_reward.status,
            "passed": bool(
                presentation.state == StreakPresentationState.ENDED
                and presentation.current_days == 0
                and presentation.previous_days == previous_days
            ),
        }
        self._capture_metric(
            "streak",
            "streak-missed-day",
            restore_callback=lambda: self._restore_reward_capture_fixture(snapshot),
        )

    def _capture_streak_achievement_states(self) -> None:
        from .achievements import ACHIEVEMENTS_BY_ID
        from .models.state import STREAK_BONUS_TIERS
        from .reward_presentation import recurring_reward_presentations

        completed_definition = ACHIEVEMENTS_BY_ID["streak_7"]
        next_definition = ACHIEVEMENTS_BY_ID["streak_30"]
        current_days = min(
            int(next_definition.progress_target) - 1,
            int(completed_definition.progress_target) * 2,
        )
        daily_answers = max(1, current_days - 2)
        snapshot, projections = self._set_streak_capture_state(
            days=current_days,
            reviewed=daily_answers,
            last_active_offset=0,
            completed_ids=("streak_7",),
        )
        completed = next(
            item for item in projections if item.achievement_id == "streak_7"
        )
        next_achievement = next(
            item for item in projections if item.achievement_id == "streak_30"
        )
        next_bonus_day = next(
            day for day, _percent in STREAK_BONUS_TIERS if day > current_days
        )
        reward_rules = {
            rule.rule_id: rule
            for rule in recurring_reward_presentations(
                self.app.storage.state,
                self.app.engine,
            )
        }
        self._capture_annotations["streak-achievement-earned-next"] = {
            "current_streak_days": current_days,
            "daily_answers": daily_answers,
            "completed_achievement_id": completed.achievement_id,
            "completed_achievement_reward": completed.reward_summary,
            "next_achievement_id": next_achievement.achievement_id,
            "next_achievement_value": next_achievement.value_text,
            "next_growth_bonus_days": next_bonus_day,
            "daily_reward_earned": reward_rules["daily_activity"].awarded_today,
            "weekly_reward_earned": reward_rules["weekly_streak"].awarded_today,
            "canonical_projection": True,
            "passed": bool(
                completed.completed
                and completed.reward_coins
                == completed_definition.reward.coins
                and completed.reward_small_growth_charges
                == completed_definition.reward.small_growth_charges
                and completed.reward_standard_growth_charges
                == completed_definition.reward.standard_growth_charges
                and not next_achievement.completed
                and next_achievement.current == current_days
                and next_achievement.progress_target
                == next_definition.progress_target
                and reward_rules["daily_activity"].awarded_today
                and reward_rules["weekly_streak"].awarded_today
            ),
        }
        self._capture_metric(
            "streak",
            "streak-achievement-earned-next",
            restore_callback=lambda: self._restore_reward_capture_fixture(snapshot),
        )

    def _capture_nursery_owned_item(self) -> None:
        label = "nursery-item-owned"
        fixture: dict[str, str] = {}

        def setup(_dashboard: Any) -> Callable[[], None]:
            if not self._ensure_development_stress_state():
                raise RuntimeError("development stress state was unavailable")
            snapshot = self._capture_fixture_state_snapshot(label)
            state = self.app.storage.state
            state.plants = list(state.plants[:6])
            state.unlocked_species = [
                str(plant.species) for plant in state.plants
            ]
            state.active_plant_id = state.plants[0].plant_id
            state.onboarding.starter_plant_id = state.active_plant_id
            # The active plant lives in the dedicated "Currently growing"
            # strip. Target another owned plant so this fixture visibly proves
            # the reusable owned catalog-card state.
            owned_catalog_plant = state.plants[1]
            fixture["plant_id"] = str(owned_catalog_plant.plant_id)
            fixture["plant_name"] = str(owned_catalog_plant.name)
            self._refresh_capture_dashboard()
            return lambda: self._restore_capture_fixture_state(snapshot)

        def reveal_owned_item(dialog: Any) -> None:
            target_id = fixture.get("plant_id", "")
            target_name = fixture.get("plant_name", "")
            cards = dialog.scroll.findChildren(QFrame)
            card = next(
                (
                    candidate for candidate in cards
                    if str(candidate.property("catalogItemId") or "") == target_id
                ),
                None,
            )
            if card is not None:
                card.setProperty("captureEvidenceKey", "owned-item-card")
                dialog.scroll.ensureWidgetVisible(card, 0, 24)
            QApplication.processEvents()
            labels = card.findChildren(QLabel) if card is not None else []
            buttons = (
                card.findChildren(QAbstractButton) if card is not None else []
            )
            title_label = next(
                (
                    item for item in labels
                    if bool(item.property("nurseryPlantName"))
                    and str(item.text()).strip().startswith(f"{target_name} ·")
                ),
                None,
            )
            action = next(
                (
                    button for button in buttons
                    if _displayed_button_text(button)
                    in {"Store", "Place", "View in garden"}
                ),
                None,
            )
            viewport = dialog.scroll.viewport()
            card_bounds = self._widget_bounds_evidence(card, viewport)
            title_bounds = self._widget_bounds_evidence(title_label, viewport)
            action_bounds = self._widget_bounds_evidence(action, viewport)
            visual = {
                "item_id": target_id,
                "item_name": target_name,
                "action": (
                    _displayed_button_text(action) if action is not None else ""
                ),
                "card": card_bounds,
                "title": title_bounds,
                "action_bounds": action_bounds,
            }
            visual["passed"] = bool(
                target_id
                and target_name
                and str(getattr(title_label, "text", lambda: "")()).startswith(
                    f"{target_name} ·"
                )
                and visual["action"]
                in {"Store", "Place", "View in garden"}
                and all(
                    bool(evidence.get("contained", False))
                    for evidence in (
                        card_bounds,
                        title_bounds,
                        action_bounds,
                    )
                )
            )
            self._capture_annotations[label] = {
                "owned_item_visual": visual,
                "passed": bool(visual["passed"]),
            }

        self._capture_nursery_tab(
            0,
            label,
            fixture_setup=setup,
            ready_audit=reveal_owned_item,
        )

    def _capture_custom_nursery(
        self,
        index: int,
        label: str,
        on_ready: Callable[[Any], None],
        *,
        on_error: Callable[[], None] | None = None,
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
                    on_error=on_error,
                ),
            )
            dashboard._open_nursery(index)

        self._with_dashboard(
            dashboard_ready,
            failure_label=label,
            on_error=on_error,
        )

    def _capture_nursery_locked_item(self) -> None:
        label = "nursery-item-locked"
        snapshot = self._capture_fixture_state_snapshot(label)

        def cleanup() -> None:
            self._restore_capture_fixture_state(snapshot)

        self.app.storage.state.currency_balance = 0
        for key in list(self.app.storage.state.consumables):
            self.app.storage.state.consumables[key] = 0

        def ready(dialog: Any) -> None:
            growth_heading = next(
                (
                    candidate
                    for candidate in dialog.supplements_catalog.findChildren(QLabel)
                    if str(candidate.text()).strip() == "Growth Charges"
                ),
                None,
            )
            # A short, real layout item gives the final section enough native
            # scroll range to align as a complete group. Unlike a forged bottom
            # margin, it remains visible to the shared reachability audit.
            capture_tail = QWidget(dialog.supplements_catalog)
            capture_tail.setProperty("captureScrollTail", True)
            capture_tail.setFixedHeight(48)
            dialog.supplements_layout.insertWidget(
                max(0, dialog.supplements_layout.count() - 1),
                capture_tail,
            )

            def align_and_audit() -> None:
                dialog.supplements_layout.activate()
                QApplication.processEvents()
                scrollbar = dialog.supplements_scroll.verticalScrollBar()
                if growth_heading is not None:
                    scrollbar.setValue(max(
                        int(scrollbar.minimum()),
                        min(
                            int(scrollbar.maximum()),
                            int(growth_heading.y()) - 8,
                        ),
                    ))
                QApplication.processEvents()

                viewport = dialog.supplements_scroll.viewport()
                viewport_height = int(viewport.height())
                visible_cards: list[dict[str, Any]] = []
                partial_cards: list[dict[str, Any]] = []
                for card in dialog.supplements_catalog.findChildren(QFrame):
                    if not bool(card.property("nurseryCatalogCard")):
                        continue
                    bounds = self._widget_bounds_evidence(card, viewport)
                    left, top, width, height = list(
                        bounds.get("bounds", ()) or (0, 0, 0, 0)
                    )
                    bottom = int(top) + int(height)
                    if bottom <= 0 or int(top) >= viewport_height:
                        continue
                    row = {
                        "item_id": str(card.property("catalogItemId") or ""),
                        "bounds": [int(left), int(top), int(width), int(height)],
                    }
                    visible_cards.append(row)
                    if int(top) < 0 or bottom > viewport_height:
                        partial_cards.append(row)
                heading_bounds = self._widget_bounds_evidence(
                    growth_heading,
                    viewport,
                )
                geometry = {
                    "scroll_value": int(scrollbar.value()),
                    "scroll_maximum": int(scrollbar.maximum()),
                    "heading": heading_bounds,
                    "visible_cards": visible_cards,
                    "partial_cards": partial_cards,
                }
                geometry["passed"] = bool(
                    heading_bounds.get("contained", False)
                    and visible_cards
                    and not partial_cards
                )
                self._capture_annotations[label] = {
                    "locked_catalog_geometry": geometry,
                    "passed": bool(geometry["passed"]),
                }

            def close_dialog() -> None:
                self._close_widget(dialog)
                cleanup()

            self._capture_and_advance(
                label,
                dialog,
                capture_delay_ms=520,
                before_capture=align_and_audit,
                close_callback=close_dialog,
                close_ms=850,
                next_ms=1200,
            )

        try:
            self._capture_custom_nursery(
                1,
                label,
                ready,
                on_error=cleanup,
            )
        except Exception:
            cleanup()
            raise

    def _capture_nursery_purchase_success(self) -> None:
        from .environment import SCENERY_CATALOG, WEATHER_CATALOG
        from .purchases import PurchaseKind, PurchaseRequest, purchase_presentation

        label = "nursery-purchase-success"
        snapshot = self._capture_fixture_state_snapshot(
            label,
            exact_ledger_restore=True,
        )

        def cleanup() -> None:
            self._restore_capture_fixture_state(snapshot)

        state = self.app.storage.state
        state.currency_balance = 100_000
        state.currency_transactions.clear()
        state.completed_purchase_requests.clear()
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
            if state.selected_background == item.item_id:
                state.selected_background = "default"
        elif state.selected_weather == item.item_id:
            state.selected_weather = "sunny"

        def ready(dialog: Any) -> None:
            purchase_kind = PurchaseKind(item.kind)
            quote = self.app.engine.quote_purchase(purchase_kind, item.item_id)
            outcome = self.app.engine.confirm_purchase(
                PurchaseRequest.from_quote(quote)
            )
            dialog.refresh()
            dialog.catalog_tabs.setCurrentIndex(3)
            dialog._preview_environment_item(item)
            if outcome.success:
                dialog._show_purchase_receipt(
                    outcome,
                    purchase_presentation(quote, ignore_status=True),
                )
            if not self.app.engine.owns_environment(item.kind, item.item_id):
                self._failures.append({
                    "label": label,
                    "reason": f"Purchase fixture did not own {item.name} after the transaction",
                })
            if str(dialog.environment_feature_title.text()) != item.name:
                self._failures.append({
                    "label": label,
                    "reason": "Purchase success preview no longer matched the purchased catalog item",
                })

            def close_dialog() -> None:
                self._close_widget(dialog)
                cleanup()

            self._capture_and_advance(
                label,
                dialog,
                capture_delay_ms=520,
                close_callback=close_dialog,
                close_ms=900,
                next_ms=1250,
            )

        try:
            self._capture_custom_nursery(
                3,
                label,
                ready,
                on_error=cleanup,
            )
        except Exception:
            cleanup()
            raise

    def _capture_nursery_final_row(self) -> None:
        label = "nursery-final-row-above-footer"
        if not self._ensure_development_stress_state():
            self._next_after(200)
            return

        def ready(dialog: Any) -> None:
            scrollbar = dialog.scroll.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

            def capture_ready() -> None:
                # Catalog rows can finish their deferred geometry after the
                # dialog first becomes visible, which can increase the range
                # after the initial scroll. Re-anchor to the settled edge
                # immediately before the reachability audit.
                scrollbar.setValue(scrollbar.maximum())
                QApplication.processEvents()
                scrollbar.setValue(scrollbar.maximum())
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
        from .environment import (
            GROWTH_CHARGES,
            SCENERY_CATALOG,
            WEATHER_CATALOG,
        )
        from .purchases import PurchaseKind
        from .ui.dashboard import (
            _LOGGED_MISSING_ARTWORK,
            _asset_preview_label,
            _item_preview_label,
        )

        label = "missing-artwork-graphical-fallback"
        weather_item = WEATHER_CATALOG.get("sunny")
        scenery_item = SCENERY_CATALOG.get("spring")
        growth_charge = GROWTH_CHARGES.get("growth_charge_small")
        if weather_item is None or scenery_item is None or growth_charge is None:
            self._failures.append({
                "label": label,
                "reason": "The complete missing-artwork catalog matrix was unavailable",
            })
            self._next_after(200)
            return

        def ready(dialog: Any) -> None:
            engine = self.app.engine
            resolver_names = (
                "resolve_weather_preview_asset",
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

            class MissingCaptureAsset:
                def __init__(self, path: str) -> None:
                    self.path = path
                    self.placement: dict[str, Any] = {}

            missing_paths = {
                "plant": "/capture-missing/plant-bonsai-seed.webp",
                "fertilizer": "/capture-missing/fertilizer-basic.webp",
                "growth-charge": "/capture-missing/growth-charge-small.webp",
                "weather": "/capture-missing/weather-breeze.svg",
                "scenery": "/capture-missing/scenery-spring.webp",
            }

            def restore_resolver() -> None:
                nonlocal restored
                if restored:
                    return
                restored = True
                for name, resolver in original_resolvers.items():
                    setattr(engine, name, resolver)

            try:
                original_scenery_resolver = original_resolvers[
                    "resolve_scenery_preview_asset"
                ]
                setattr(
                    engine,
                    "resolve_weather_preview_asset",
                    lambda _item_id: MissingCaptureAsset(missing_paths["weather"]),
                )

                def scenery_resolver(item_id: str) -> Any:
                    if str(item_id) == scenery_item.item_id:
                        return MissingCaptureAsset(missing_paths["scenery"])
                    return original_scenery_resolver(item_id)

                setattr(engine, "resolve_scenery_preview_asset", scenery_resolver)
                setattr(
                    engine,
                    "resolve_plant_asset",
                    lambda _species, _stage: MissingCaptureAsset(
                        missing_paths["plant"]
                    ),
                )
                setattr(
                    engine,
                    "resolve_plant_image",
                    lambda _species, _stage: missing_paths["plant"],
                )

                def item_resolver(item_key: str) -> MissingCaptureAsset:
                    path_key = (
                        "fertilizer"
                        if "fertilizer" in str(item_key)
                        else "growth-charge"
                    )
                    return MissingCaptureAsset(missing_paths[path_key])

                setattr(engine, "resolve_item_asset", item_resolver)

                # Exercise every fallback renderer without injecting a
                # cross-category diagnostics strip into the product UI.
                previews = {
                    "plant": _asset_preview_label(
                        engine,
                        "bonsai",
                        "seed",
                        size=84,
                    ),
                    "fertilizer": _item_preview_label(
                        engine,
                        "fertilizer_basic",
                        "Rich Compost preview",
                        size=76,
                        placeholder_kind=PurchaseKind.FERTILIZER,
                    ),
                    "growth-charge": _item_preview_label(
                        engine,
                        growth_charge.charge_id,
                        f"{growth_charge.name} preview",
                        size=76,
                        placeholder_kind=PurchaseKind.GROWTH_CHARGE,
                    ),
                    "weather": dialog._environment_artwork(
                        weather_item,
                        width=124,
                        height=72,
                    ),
                    "scenery": dialog._environment_artwork(
                        scenery_item,
                        width=124,
                        height=72,
                    ),
                }
                expected_aspects = {
                    "plant": 1.0,
                    "fertilizer": 1.0,
                    "growth-charge": 1.0,
                    "weather": 114 / 62,
                    "scenery": 114 / 62,
                }
                original_weather_resolver = original_resolvers[
                    "resolve_weather_preview_asset"
                ]
                original_scenery_resolver = original_resolvers[
                    "resolve_scenery_preview_asset"
                ]
                setattr(
                    engine,
                    "resolve_weather_preview_asset",
                    lambda item_id: (
                        MissingCaptureAsset(missing_paths["weather"])
                        if str(item_id) == weather_item.item_id
                        else original_weather_resolver(item_id)
                    ),
                )
                setattr(
                    engine,
                    "resolve_scenery_preview_asset",
                    original_scenery_resolver,
                )
                dialog.refresh()
                dialog.catalog_tabs.setCurrentIndex(3)
                dialog.environment_scroll.verticalScrollBar().setValue(0)
                QApplication.processEvents()

                normal_card = next((
                    card
                    for card in dialog.environment_catalog.findChildren(QFrame)
                    if str(card.property("catalogItemId") or "")
                    == weather_item.item_id
                ), None)
                visible_preview = (
                    next((
                        child
                        for child in normal_card.findChildren(QLabel)
                        if bool(child.property("nurseryArtwork"))
                    ), None)
                    if normal_card is not None else None
                )
                if visible_preview is not None:
                    visible_preview.setProperty(
                        "captureEvidenceKey",
                        "missing-art-weather",
                    )
                if normal_card is not None:
                    dialog.environment_scroll.ensureWidgetVisible(
                        normal_card,
                        0,
                        24,
                    )
                    QApplication.processEvents()

                expected_fingerprints = {
                    (
                        "plant",
                        "bonsai:seed",
                        missing_paths["plant"],
                    ),
                    (
                        "fertilizer",
                        "fertilizer_basic",
                        missing_paths["fertilizer"],
                    ),
                    (
                        "growth_charge",
                        growth_charge.charge_id,
                        missing_paths["growth-charge"],
                    ),
                    (
                        "weather",
                        weather_item.item_id,
                        missing_paths["weather"],
                    ),
                    (
                        "scenery",
                        scenery_item.item_id,
                        missing_paths["scenery"],
                    ),
                }
                matrix_entries: list[dict[str, Any]] = []
                for artwork_type in MISSING_ARTWORK_CAPTURE_TYPES:
                    preview = previews[artwork_type]
                    pixmap = preview.pixmap()
                    pixmap_width = int(pixmap.width()) if pixmap is not None else 0
                    pixmap_height = int(pixmap.height()) if pixmap is not None else 0
                    actual_aspect = (
                        pixmap_width / pixmap_height if pixmap_height > 0 else 0.0
                    )
                    expected_aspect = expected_aspects[artwork_type]
                    entry = {
                        "type": artwork_type,
                        "source_path": missing_paths[artwork_type],
                        "accessible_name": str(preview.accessibleName() or ""),
                        "accessible_description": str(
                            preview.accessibleDescription() or ""
                        ),
                        "semantic_role": str(
                            preview.property("gardenRole") or ""
                        ),
                        "pixmap_size": [pixmap_width, pixmap_height],
                        "graphic_present": bool(
                            pixmap is not None and not pixmap.isNull()
                        ),
                        "expected_aspect_ratio": round(expected_aspect, 4),
                        "actual_aspect_ratio": round(actual_aspect, 4),
                        "aspect_ratio_preserved": bool(
                            actual_aspect > 0
                            and abs(actual_aspect / expected_aspect - 1.0) <= 0.03
                        ),
                        "diagnostic_path_logged": any(
                            fingerprint[2] == missing_paths[artwork_type]
                            for fingerprint in _LOGGED_MISSING_ARTWORK
                        ),
                    }
                    entry["passed"] = bool(
                        entry["semantic_role"] == "missing-art"
                        and entry["graphic_present"]
                        and entry["aspect_ratio_preserved"]
                        and str(entry["accessible_name"]).strip()
                        and str(entry["accessible_description"]).startswith(
                            "Artwork unavailable"
                        )
                        and entry["diagnostic_path_logged"]
                    )
                    matrix_entries.append(entry)
                logged_fingerprints = sorted(
                    [
                        list(fingerprint)
                        for fingerprint in expected_fingerprints
                        if fingerprint in _LOGGED_MISSING_ARTWORK
                    ]
                )

                def prepare_capture() -> None:
                    current_card = next((
                        card
                        for card in dialog.environment_catalog.findChildren(QFrame)
                        if str(card.property("catalogItemId") or "")
                        == weather_item.item_id
                    ), None)
                    current_preview = (
                        next((
                            child
                            for child in current_card.findChildren(QLabel)
                            if bool(child.property("nurseryArtwork"))
                        ), None)
                        if current_card is not None else None
                    )
                    if current_preview is not None:
                        current_preview.setProperty(
                            "captureEvidenceKey",
                            "missing-art-weather",
                        )
                    if current_card is not None:
                        dialog.environment_scroll.ensureWidgetVisible(
                            current_card,
                            0,
                            24,
                        )
                        QApplication.processEvents()
                    viewport = dialog.environment_scroll.viewport()
                    visible_card_evidence = self._widget_bounds_evidence(
                        current_card,
                        viewport,
                    )
                    visible_preview_evidence = self._widget_bounds_evidence(
                        current_preview,
                        viewport,
                    )
                    visible_missing_previews = [
                        child
                        for child in dialog.environment_catalog.findChildren(QLabel)
                        if str(child.property("gardenRole") or "") == "missing-art"
                        and bool(
                            self._widget_bounds_evidence(child, viewport).get(
                                "visible",
                                False,
                            )
                        )
                        and bool(
                            self._widget_bounds_evidence(child, viewport).get(
                                "contained",
                                False,
                            )
                        )
                    ]
                    matrix_passed = bool(
                        [entry["type"] for entry in matrix_entries]
                        == list(MISSING_ARTWORK_CAPTURE_TYPES)
                        and expected_fingerprints.issubset(_LOGGED_MISSING_ARTWORK)
                        and all(entry["passed"] for entry in matrix_entries)
                        and visible_card_evidence.get("visible", False)
                        and visible_card_evidence.get("contained", False)
                        and visible_preview_evidence.get("visible", False)
                        and visible_preview_evidence.get("contained", False)
                        and len(visible_missing_previews) == 1
                    )
                    self._capture_annotations[label] = {
                        "resolvers_forced_missing": list(resolver_names),
                        "missing_artwork_matrix": {
                            "types": list(MISSING_ARTWORK_CAPTURE_TYPES),
                            "entries": matrix_entries,
                            "missing_source_paths": dict(missing_paths),
                            "diagnostic_log_fingerprints": logged_fingerprints,
                            "visible_card": visible_card_evidence,
                            "visible_preview": visible_preview_evidence,
                            "visible_missing_preview_count": len(
                                visible_missing_previews
                            ),
                            "passed": matrix_passed,
                        },
                        "passed": matrix_passed,
                    }
                    if not matrix_passed:
                        self._failures.append({
                            "label": label,
                            "reason": (
                                "The normal Nursery card or offscreen fallback contract "
                                "was incomplete"
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
                before_capture=prepare_capture,
                close_callback=close_capture,
                close_ms=850,
                next_ms=1200,
            )

        self._capture_custom_nursery(3, label, ready)

    def _capture_custom_settings(
        self,
        label: str,
        tab: int,
        prepare: Callable[[Any], None],
        *,
        restore_callback: Callable[[], None] | None = None,
    ) -> None:
        dialog_for_cleanup: Any | None = None
        cleanup_complete = False

        def cleanup_once() -> None:
            nonlocal cleanup_complete
            if cleanup_complete:
                return
            cleanup_complete = True
            dialog = dialog_for_cleanup
            if dialog is None:
                try:
                    dialog = self._find_settings_dialog()
                except Exception as exc:
                    self._failures.append({
                        "label": label,
                        "reason": (
                            "Settings fixture cleanup could not inspect the dialog: "
                            f"{type(exc).__name__}"
                        ),
                    })
            if dialog is not None:
                try:
                    self._close_settings_capture(dialog)
                except Exception as exc:
                    self._failures.append({
                        "label": label,
                        "reason": (
                            "Settings fixture cleanup could not close the dialog: "
                            f"{type(exc).__name__}"
                        ),
                    })
            if restore_callback is not None:
                try:
                    restore_callback()
                except Exception as exc:
                    self._failures.append({
                        "label": label,
                        "reason": (
                            "Settings fixture state restoration failed: "
                            f"{type(exc).__name__}"
                        ),
                    })

        def dashboard_ready() -> None:
            dashboard = self.app.dashboard
            dashboard._open_settings()

            def settings_ready() -> None:
                nonlocal dialog_for_cleanup
                dialog = self._find_settings_dialog()
                dialog_for_cleanup = dialog
                self._set_settings_tab(dialog, tab)
                prepare(dialog)
                self._capture_and_advance(
                    label,
                    dialog,
                    capture_delay_ms=480,
                    close_callback=cleanup_once,
                    close_ms=700,
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
                on_error=cleanup_once,
            )

        self._with_dashboard(
            dashboard_ready,
            failure_label=label,
            on_error=cleanup_once,
        )

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

    def _prepare_reviewer_capture_card(self) -> bool:
        """Create one disposable Basic note so reward captures use real Reviewer UI."""

        if bool(getattr(self, "_reviewer_capture_card_ready", False)):
            return True
        collection = getattr(mw, "col", None)
        if collection is None:
            return False
        try:
            decks = collection.decks
            # ``id_for_name()`` is lookup-only in current Anki releases.  The
            # legacy-named ``id()`` API remains the supported create-or-reuse
            # path across the full 25.07-26.08 release target.
            deck_id = decks.id("Anki Garden Capture")
            if deck_id is None:
                return False
            models = collection.models
            note_type = models.by_name("Basic") or models.current()
            if note_type is None:
                return False
            note = collection.new_note(note_type)
            field_names = list(note.keys())
            if not field_names:
                return False
            note[field_names[0]] = "What did this review uncover?"
            if len(field_names) > 1:
                note[field_names[1]] = "A Garden Find."
            add_note = getattr(collection, "add_note", None)
            if callable(add_note):
                add_note(note, int(deck_id))
            else:
                note_type = note.note_type()
                note_type["did"] = int(deck_id)
                collection.addNote(note)
            select_deck = getattr(decks, "select", None)
            if callable(select_deck):
                select_deck(int(deck_id))
            reset = getattr(collection, "reset", None)
            if callable(reset):
                reset()
            self._reviewer_capture_card_ready = True
            return True
        except Exception:
            logger.exception("Anki Garden capture: could not prepare Reviewer card")
            return False

    def _prepare_canonical_reviewer_feedback_fixture(
        self,
        *,
        find_reward_ids: tuple[str, ...],
        environment_item_ids: tuple[str, ...] = (),
        include_daily_activity: bool = False,
        achievement_ids: tuple[str, ...] = (),
    ) -> tuple[dict[str, Any], Any, dict[str, Any]]:
        """Project a real Reviewer event from committed, registry-owned facts."""

        from .achievements import ACHIEVEMENTS_BY_ID
        from .garden_finds import (
            ENVIRONMENT_POOL_ID,
            ENVIRONMENT_POOL_VERSION,
            SPECIAL_ENVIRONMENT_POOL,
            STANDARD_FIND_REGISTRY,
            STANDARD_POOL_ID,
            STANDARD_POOL_VERSION,
        )
        from .models.state import (
            CurrencyTransaction,
            GardenFindOutcome,
            RewardReceipt,
        )
        from .reward_presentation import (
            recent_garden_finds,
            recent_reward_summaries,
        )

        snapshot = self._capture_fixture_state_snapshot("reviewer-feedback")
        try:
            handler = getattr(self.app, "reviewer_hooks", None)
            if handler is None:
                raise RuntimeError("Reviewer reward handler was unavailable")
            state = self.app.storage.state
            active = self.app.engine.active_plant() or next(
                (
                    plant for plant in state.plants
                    if bool(getattr(plant, "planted", False))
                    and not bool(getattr(plant, "fully_grown", False))
                ),
                None,
            )
            if active is None:
                raise RuntimeError(
                    "canonical Reviewer reward capture requires an unfinished plant"
                )

            reward_by_id = {
                reward.reward_id: reward for reward in STANDARD_FIND_REGISTRY
            }
            environment_by_id = {
                item.item_id: item for item in SPECIAL_ENVIRONMENT_POOL
            }
            unknown_find_ids = set(find_reward_ids) - set(reward_by_id)
            if unknown_find_ids:
                raise ValueError(
                    "unknown canonical Reviewer Find IDs: "
                    + ", ".join(sorted(unknown_find_ids))
                )
            unknown_environment_ids = (
                set(environment_item_ids) - set(environment_by_id)
            )
            if unknown_environment_ids:
                raise ValueError(
                    "unknown canonical Reviewer environment Find IDs: "
                    + ", ".join(sorted(unknown_environment_ids))
                )
            unknown_achievement_ids = set(achievement_ids) - set(
                ACHIEVEMENTS_BY_ID
            )
            if unknown_achievement_ids:
                raise ValueError(
                    "unknown canonical Reviewer achievement IDs: "
                    + ", ".join(sorted(unknown_achievement_ids))
                )

            day_value = "2026-08-21"
            state.daily_stats.day = day_value
            state.recent_reward_receipts = []
            state.garden_find_outcomes = {}
            state.garden_find_daily_counts = {day_value: len(find_reward_ids)}
            state.garden_find_reward_daily_counts = {day_value: {}}
            state.currency_transactions = []
            state.pending_feedback = []
            state.applied_reward_event_keys = []
            state.processed_answer_keys = []
            self.app.engine._ensure_achievements()

            sync_correlation = f"sync:capture-reviewer:{day_value}"
            all_receipt_groups: list[tuple[RewardReceipt, ...]] = []
            for index, reward_id in enumerate(find_reward_ids, start=1):
                reward = reward_by_id[reward_id]
                answer_key = f"capture-reviewer-{index}"
                correlation_id = sync_correlation
                occurred_at = f"{day_value}T09:{index:02d}:00+00:00"
                find_event_key = (
                    f"garden_find:{answer_key}:{STANDARD_POOL_ID}"
                )
                item_id = reward.inventory_item_id or ""
                outcome = GardenFindOutcome(
                    answer_key=answer_key,
                    scheduler_day=day_value,
                    status="hit",
                    pool_id=STANDARD_POOL_ID,
                    pool_version=STANDARD_POOL_VERSION,
                    occurred_at=occurred_at,
                    reward_id=reward.reward_id,
                    reward_type=reward.reward_kind,
                    amount=reward.amount,
                    item_id=item_id,
                    display_name=reward.display_name,
                    description=reward.description,
                    tier=reward.tier,
                    artwork_ref=reward.artwork_ref,
                    localization_key=reward.localization_key,
                )
                state.garden_find_outcomes[outcome.outcome_key] = outcome
                receipts: list[RewardReceipt] = []
                if include_daily_activity and index == 1:
                    receipts.append(RewardReceipt(
                        event_key=f"daily_activity:{day_value}",
                        reward_type="coins",
                        source="daily_activity",
                        source_id=day_value,
                        scheduler_day=day_value,
                        correlation_id=correlation_id,
                        occurred_at=occurred_at,
                        amount=int(self.app.engine.DAILY_ACTIVITY_COINS),
                        title="Daily activity reward",
                    ))
                receipts.append(RewardReceipt(
                    event_key=find_event_key,
                    reward_type=reward.reward_kind,
                    source="garden_find",
                    source_id=reward.reward_id,
                    scheduler_day=day_value,
                    correlation_id=correlation_id,
                    occurred_at=occurred_at,
                    amount=reward.amount,
                    item_id=item_id,
                    plant_id=(
                        active.plant_id if reward.reward_kind == "growth" else ""
                    ),
                    title=reward.display_name,
                    description=reward.description,
                ))

                if index == len(find_reward_ids):
                    for achievement_id in achievement_ids:
                        definition = ACHIEVEMENTS_BY_ID[achievement_id]
                        event_key = f"achievement:{achievement_id}"
                        if definition.reward.coins:
                            receipts.append(RewardReceipt(
                                event_key=event_key,
                                reward_type="coins",
                                source="achievement",
                                source_id=achievement_id,
                                scheduler_day=day_value,
                                correlation_id=correlation_id,
                                occurred_at=occurred_at,
                                amount=definition.reward.coins,
                                title=definition.name,
                                description=definition.description,
                            ))
                        for charge_id, amount in (
                            (
                                "growth_charge_small",
                                definition.reward.small_growth_charges,
                            ),
                            (
                                "growth_charge_standard",
                                definition.reward.standard_growth_charges,
                            ),
                        ):
                            if amount:
                                receipts.append(RewardReceipt(
                                    event_key=event_key,
                                    reward_type="inventory_item",
                                    source="achievement",
                                    source_id=achievement_id,
                                    scheduler_day=day_value,
                                    correlation_id=correlation_id,
                                    occurred_at=occurred_at,
                                    amount=amount,
                                    item_id=charge_id,
                                    title=definition.name,
                                    description=definition.description,
                                ))
                        achievement = state.achievements[achievement_id]
                        achievement.unlocked = True
                        achievement.progress = 1.0
                        achievement.unlocked_at = occurred_at
                        achievement.rewarded_at = occurred_at
                        achievement.reward_event_key = event_key
                        achievement.historical_backfill = False

                for receipt_index, receipt in enumerate(receipts, start=1):
                    state.recent_reward_receipts.append(receipt)
                    if receipt.event_key not in state.applied_reward_event_keys:
                        state.applied_reward_event_keys.append(receipt.event_key)
                    if receipt.reward_type == "coins":
                        state.currency_balance += receipt.amount
                        state.currency_transactions.append(CurrencyTransaction(
                            transaction_id=(
                                f"capture-reviewer-tx-{index}-{receipt_index}"
                            ),
                            event_key=receipt.event_key,
                            reason=receipt.title,
                            delta=receipt.amount,
                            balance=state.currency_balance,
                            occurred_at=receipt.occurred_at,
                            transaction_type="credit",
                            source=receipt.source,
                            source_id=receipt.source_id,
                            scheduler_day=receipt.scheduler_day,
                            correlation_id=receipt.correlation_id,
                        ))
                    elif receipt.reward_type == "growth":
                        active.growth_points += receipt.amount
                        direct_growth = (
                            state.daily_stats.plant_direct_reward_growth
                        )
                        direct_growth[active.plant_id] = (
                            int(direct_growth.get(active.plant_id, 0) or 0)
                            + receipt.amount
                        )
                    elif receipt.reward_type == "inventory_item" and receipt.item_id:
                        state.consumables[receipt.item_id] = (
                            int(state.consumables.get(receipt.item_id, 0) or 0)
                            + receipt.amount
                        )
                state.processed_answer_keys.append(answer_key)
                state.garden_find_reward_daily_counts[day_value][reward_id] = (
                    int(state.garden_find_reward_daily_counts[day_value].get(
                        reward_id,
                        0,
                    ) or 0)
                    + 1
                )
                receipt_group = tuple(receipts)
                all_receipt_groups.append(receipt_group)

            for offset, item_id in enumerate(environment_item_ids, start=1):
                item = environment_by_id[item_id]
                answer_key = f"capture-reviewer-environment-{offset}"
                correlation_id = sync_correlation
                minute = len(find_reward_ids) + offset
                occurred_at = f"{day_value}T09:{minute:02d}:30+00:00"
                find_event_key = (
                    f"garden_find:{answer_key}:{ENVIRONMENT_POOL_ID}"
                )
                outcome = GardenFindOutcome(
                    answer_key=answer_key,
                    scheduler_day=day_value,
                    status="hit",
                    pool_id=ENVIRONMENT_POOL_ID,
                    pool_version=ENVIRONMENT_POOL_VERSION,
                    occurred_at=occurred_at,
                    reward_id=item.item_id,
                    reward_type="environment_item",
                    amount=1,
                    item_id=item.item_id,
                    display_name=item.display_name,
                    description="Added to Weather and Scenery",
                    tier=item.tier,
                    artwork_ref=item.item_id,
                    localization_key=f"garden_find.environment.{item.item_id}",
                )
                state.garden_find_outcomes[outcome.outcome_key] = outcome
                receipt = RewardReceipt(
                    event_key=find_event_key,
                    reward_type="environment_item",
                    source="garden_find_environment",
                    source_id=item.item_id,
                    scheduler_day=day_value,
                    correlation_id=correlation_id,
                    occurred_at=occurred_at,
                    amount=1,
                    item_id=item.item_id,
                    title=item.display_name,
                    description=outcome.description,
                )
                state.recent_reward_receipts.append(receipt)
                if receipt.event_key not in state.applied_reward_event_keys:
                    state.applied_reward_event_keys.append(receipt.event_key)
                owned_items = state.inventory.setdefault(
                    item.environment_kind,
                    [],
                )
                if item.item_id not in owned_items:
                    owned_items.append(item.item_id)
                state.processed_answer_keys.append(answer_key)
                all_receipt_groups.append((receipt,))

            all_receipts = tuple(
                receipt
                for group in all_receipt_groups
                for receipt in group
            )
            if not self.app.engine._queue_reward_feedback(
                sync_correlation,
                all_receipts,
                achievement_ids=achievement_ids,
                plant_id=active.plant_id,
                title="Garden rewards added",
            ):
                raise RuntimeError(
                    "canonical Reviewer sync reward feedback was not queued"
                )
            state.pending_feedback[-1].occurred_at = (
                all_receipts[-1].occurred_at if all_receipts else f"{day_value}T09:00:00+00:00"
            )

            presentations = recent_garden_finds(state, limit=8)
            feedback = handler._consolidated_reward_feedback(
                list(state.pending_feedback)
            )
            if feedback is None:
                raise RuntimeError(
                    "canonical Reviewer reward feedback could not be projected"
                )
            expected_title = (
                presentations[0].display_name
                if len(presentations) == 1
                else f"{len(presentations):,} Garden rewards added"
            )
            receipt_correlations = {
                receipt.correlation_id for receipt in all_receipts
            }
            all_groups_share_correlation = bool(
                all_receipt_groups
                and all(all_receipt_groups)
                and receipt_correlations == {sync_correlation}
            )
            matching_summaries = tuple(
                summary
                for summary in recent_reward_summaries(state)
                if summary.correlation_id == sync_correlation
            )
            if len(matching_summaries) != 1:
                raise RuntimeError(
                    "canonical Reviewer fixture did not produce one typed summary"
                )
            expected_coins = sum(
                max(0, int(receipt.amount))
                for receipt in all_receipts
                if receipt.reward_type == "coins"
            )
            expected_growth = sum(
                max(0, int(receipt.amount))
                for receipt in all_receipts
                if receipt.reward_type == "growth"
            )
            expected_environments = sum(
                max(0, int(receipt.amount))
                for receipt in all_receipts
                if receipt.reward_type == "environment_item"
            )
            expected_parts = []
            if expected_coins:
                expected_parts.append(f"+{expected_coins:,} Garden Coins")
            if expected_growth:
                expected_parts.append(f"+{expected_growth:,} Growth")
            if (
                len(presentations) == 1
                and presentations[0].pool_id == ENVIRONMENT_POOL_ID
                and expected_environments
            ):
                expected_message = "Added to Weather and Scenery"
            elif expected_parts:
                expected_message = " · ".join(expected_parts)
            elif len(presentations) == 1:
                expected_message = str(presentations[0].description)
            else:
                expected_message = "Garden rewards added"
            annotation = {
                "canonical_find_ids": [
                    presentation.reward_id for presentation in presentations
                ],
                "canonical_find_pools": [
                    presentation.pool_id for presentation in presentations
                ],
                "canonical_feedback_title": feedback.title,
                "canonical_feedback_detail": feedback.reward_detail,
                "canonical_feedback_message": feedback.message,
                "expected_feedback_message": expected_message,
                "expected_feedback_amount": 0,
                "stacked_find_count": len(presentations),
                "sync_correlation": sync_correlation,
                "all_receipt_groups_share_correlation": (
                    all_groups_share_correlation
                ),
                "canonical_projection_passed": bool(
                    feedback.title == expected_title
                    and feedback.reward_detail == ""
                    and feedback.message == expected_message
                    and feedback.amount == 0
                    and all_groups_share_correlation
                    and len(presentations)
                    == len(find_reward_ids) + len(environment_item_ids)
                ),
            }
            return snapshot, feedback, annotation
        except Exception:
            self._restore_reward_capture_fixture(snapshot)
            raise

    def _with_capture_reviewer(
        self,
        label: str,
        ready: Callable[[], None],
        *,
        on_error: Callable[[], None] | None = None,
    ) -> None:
        if not self._prepare_reviewer_capture_card():
            self._failures.append({
                "label": label,
                "reason": "A disposable Reviewer card could not be prepared",
            })
            self._next_after(180)
            return
        try:
            mw.moveToState("review")
        except Exception as exc:
            self._failures.append({
                "label": label,
                "reason": f"Reviewer state could not open: {type(exc).__name__}",
            })
            self._next_after(180)
            return
        self._wait_for(
            lambda: bool(
                str(getattr(mw, "state", "")) == "review"
                and getattr(mw, "web", None) is not None
                and mw.web.isVisible()
            ),
            ready,
            tries=100,
            failure_label=label,
            failure_reason="The real Anki Reviewer did not become ready",
            on_error=on_error,
        )

    def _capture_reviewer_find_feedback(
        self,
        label: str,
        prepare_feedback: Callable[
            [],
            tuple[dict[str, Any], Any, dict[str, Any]],
        ],
        *,
        reduced_motion: bool = False,
    ) -> None:
        cleanup_holder: dict[str, Callable[[], None]] = {
            "callback": lambda: None,
        }

        def registered_cleanup() -> None:
            cleanup_holder["callback"]()

        def ready() -> None:
            handler = getattr(self.app, "reviewer_hooks", None)
            if handler is None:
                self._failures.append({
                    "label": label,
                    "reason": "Reviewer reward handler was unavailable",
                })
                self._next_after(180)
                return
            try:
                snapshot, event, fixture_annotation = prepare_feedback()
            except Exception as exc:
                logger.exception(
                    "Anki Garden capture: canonical Reviewer fixture failed"
                )
                self._failures.append({
                    "label": label,
                    "reason": (
                        "Canonical Reviewer reward fixture failed: "
                        f"{type(exc).__name__}"
                    ),
                })
                self._next_after(180)
                return
            cleaned_up = False
            config_value: Callable[..., Any] | None = None
            config_update: Callable[..., Any] | None = None
            baseline_reduced_motion = False

            def cleanup() -> None:
                nonlocal cleaned_up
                if cleaned_up:
                    return
                cleaned_up = True
                current = getattr(handler, "_reward_toast", None)
                if current is not None:
                    try:
                        current.hide()
                    except RuntimeError:
                        pass
                    finally:
                        handler._reward_toast = None
                if reduced_motion and callable(config_update):
                    try:
                        config_update({"reduced_motion": baseline_reduced_motion})
                    except Exception:
                        logger.exception(
                            "Anki Garden capture: reduced-motion fixture restoration failed"
                        )
                self._restore_reward_capture_fixture(snapshot)

            # Install cleanup immediately after the fixture mutates state. The
            # outer readiness guard can now restore it for every later failure.
            cleanup_holder["callback"] = cleanup

            try:
                config = getattr(self.app, "config", None)
                config_value = getattr(config, "value", None)
                config_update = getattr(config, "update", None)
                baseline_reduced_motion = (
                    bool(config_value("reduced_motion", False))
                    if callable(config_value) else False
                )
                if reduced_motion and callable(config_update):
                    config_update({"reduced_motion": True})
                app = QApplication.instance()
                focus_target = getattr(mw, "web", None)
                if focus_target is not None:
                    focus_target.setFocus(Qt.FocusReason.TabFocusReason)
                if app is not None:
                    app.processEvents()
                focus_before = QApplication.focusWidget()
                rendered = bool(handler._show_reward_toast(event))
                if app is not None:
                    app.processEvents()
                focus_after = QApplication.focusWidget()
                toast = getattr(handler, "_reward_toast", None)
            except Exception:
                cleanup()
                raise
            overlay_geometry = self._reviewer_overlay_geometry_audit(
                label,
                toast,
            )
            passed = bool(
                rendered
                and toast is not None
                and toast.isVisible()
                and focus_after is focus_before
                and focus_after is not toast
                and overlay_geometry.get("passed", False)
                and fixture_annotation.get(
                    "canonical_projection_passed",
                    False,
                )
            )
            self._capture_annotations[label] = {
                **fixture_annotation,
                "focus_preserved": focus_after is focus_before,
                "focus_owner": (
                    type(focus_after).__name__ if focus_after is not None else ""
                ),
                "reduced_motion_config_enabled": bool(
                    reduced_motion
                    and callable(config_value)
                    and config_value("reduced_motion", False)
                ),
                "toast_visible": bool(toast is not None and toast.isVisible()),
                "reviewer_overlay_geometry": overlay_geometry,
                "passed": passed,
            }
            if not passed:
                self._failures.append({
                    "label": label,
                    "reason": "Reviewer Find notification did not match its focus-safe projection",
                })

            try:
                self._capture_and_advance(
                    label,
                    mw,
                    capture_delay_ms=520,
                    close_callback=cleanup,
                    close_ms=760,
                    next_ms=1120,
                )
            except Exception:
                cleanup()
                raise

        self._with_capture_reviewer(
            label,
            ready,
            on_error=registered_cleanup,
        )

    def _capture_reviewer_find_common(self) -> None:
        self._capture_reviewer_find_feedback(
            "reviewer-find-common-reduced-motion",
            lambda: self._prepare_canonical_reviewer_feedback_fixture(
                find_reward_ids=("find_morning_dew",),
                include_daily_activity=True,
            ),
            reduced_motion=True,
        )

    def _capture_reviewer_find_environment(self) -> None:
        self._capture_reviewer_find_feedback(
            "reviewer-find-environment",
            lambda: self._prepare_canonical_reviewer_feedback_fixture(
                find_reward_ids=(),
                environment_item_ids=("fireflies",),
            ),
        )

    def _capture_reviewer_find_stacked_sync(self) -> None:
        self._capture_reviewer_find_feedback(
            "reviewer-find-stacked-sync",
            lambda: self._prepare_canonical_reviewer_feedback_fixture(
                find_reward_ids=(
                    "find_morning_dew",
                    "find_morning_dew",
                    "find_coin_pouch",
                ),
                include_daily_activity=True,
                achievement_ids=("retention_100",),
            ),
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
        """Render and audit Settings after removing mutation controls from source."""

        from . import build_capabilities
        from .ui.dashboard import GardenSettingsDialog

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
            dialog = GardenSettingsDialog(
                dashboard,
                self.app.engine,
                dashboard.config,
            )
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
                "development_controls_implemented": False,
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
        label = "reduced-motion-enabled"
        dashboard = getattr(self.app, "dashboard", None)
        config = getattr(dashboard, "config", None)
        config_value = getattr(config, "value", None)
        config_update = getattr(config, "update", None)
        if not callable(config_value) or not callable(config_update):
            self._failures.append({
                "label": label,
                "reason": "Reduced-motion capture configuration was unavailable",
            })
            self._next_after(120)
            return
        baseline_reduced_motion = bool(config_value("reduced_motion", False))

        def restore_reduced_motion() -> None:
            config_update({"reduced_motion": baseline_reduced_motion})
            self._refresh_capture_dashboard()

        try:
            config_update({"reduced_motion": True})
        except Exception as exc:
            self._failures.append({
                "label": label,
                "reason": (
                    "Reduced-motion fixture could not enable its configuration: "
                    f"{type(exc).__name__}"
                ),
            })
            self._next_after(120)
            return
        try:
            self._capture_custom_settings(
                label,
                0,
                self._show_reduced_motion_fixture,
                restore_callback=restore_reduced_motion,
            )
        except Exception:
            try:
                restore_reduced_motion()
            except Exception as cleanup_exc:
                self._failures.append({
                    "label": label,
                    "reason": (
                        "Reduced-motion synchronous cleanup failed: "
                        f"{type(cleanup_exc).__name__}"
                    ),
                })
            raise

    def _capture_keyboard_focus(self) -> None:
        label = "keyboard-focus-state"
        cleanup_complete = False

        def clear_focus_once() -> None:
            nonlocal cleanup_complete
            if cleanup_complete:
                return
            cleanup_complete = True
            dashboard = getattr(self.app, "dashboard", None)
            button = getattr(dashboard, "progress_btn", None)
            if button is None:
                return
            try:
                button.clearFocus()
                app = QApplication.instance()
                if app is not None:
                    app.processEvents()
                focus_owner = QApplication.focusWidget()
                if focus_owner is button or bool(button.hasFocus()):
                    self._failures.append({
                        "label": label,
                        "reason": "Keyboard-focus fixture retained Garden Progress focus",
                    })
            except Exception as exc:
                self._failures.append({
                    "label": label,
                    "reason": (
                        "Keyboard-focus fixture cleanup failed: "
                        f"{type(exc).__name__}"
                    ),
                })

        def ready() -> None:
            dashboard = self.app.dashboard

            def focus_before_capture() -> None:
                activate = getattr(self, "_activate_current_process_window", None)
                if callable(activate):
                    activate(dashboard)
                raise_window = getattr(dashboard, "raise_", None)
                if callable(raise_window):
                    raise_window()
                activate_window = getattr(dashboard, "activateWindow", None)
                if callable(activate_window):
                    activate_window()
                app = QApplication.instance()
                set_active_window = (
                    getattr(app, "setActiveWindow", None)
                    if app is not None else None
                )
                if callable(set_active_window):
                    top_level = getattr(dashboard, "window", lambda: dashboard)()
                    set_active_window(top_level)
                if app is not None:
                    app.processEvents()
                dashboard.progress_btn.setFocus(Qt.FocusReason.TabFocusReason)
                if app is not None:
                    app.processEvents()
                # A native activation event can briefly retarget focus while
                # Qt settles. Reassert the same real keyboard target after the
                # event pump; the capture postcondition still verifies both
                # hasFocus() and QApplication.focusWidget().
                dashboard.progress_btn.setFocus(Qt.FocusReason.TabFocusReason)

            self._capture_and_advance(
                label,
                dashboard,
                capture_delay_ms=420,
                before_capture=focus_before_capture,
                close_callback=clear_focus_once,
                close_ms=620,
                next_ms=900,
            )

        self._with_dashboard(
            ready,
            failure_label=label,
            on_error=clear_focus_once,
        )

    def _dialog_scroll_coverage_report(self) -> dict[str, Any]:
        """Require positive scroll/footer facts for every named dialog face."""

        if self._capture_profile != "full":
            return {
                "required": False,
                "required_count": 0,
                "records": [],
                "passed": True,
            }
        coverage_by_label: dict[str, tuple[str, str]] = {}
        duplicate_labels: list[str] = []
        for surface, labels in DIALOG_SCROLL_CAPTURE_COVERAGE.items():
            for label in labels:
                if label not in self._capture_face_labels:
                    continue
                if label in coverage_by_label:
                    duplicate_labels.append(label)
                    continue
                coverage_by_label[label] = (
                    surface,
                    DIALOG_SCROLL_CAPTURE_SEMANTICS.get(label, ""),
                )
        records = {
            str(record.get("label", "")): record
            for record in self._capture_records
        }
        results: list[dict[str, Any]] = []
        for duplicate in dict.fromkeys(duplicate_labels):
            self._failures.append({
                "label": duplicate,
                "reason": "Dialog scroll coverage label belongs to multiple surfaces",
            })
        integer_fields = (
            "registered_count",
            "active_count",
            "footer_height",
            "footer_top",
            "viewport_top",
            "viewport_height",
            "viewport_bottom",
            "declared_clearance",
            "layout_clearance",
            "content_height",
            "content_size_hint_height",
            "content_minimum_size_hint_height",
            "scroll_minimum",
            "scroll_maximum",
            "last_body_child_bottom",
            "last_body_child_bottom_at_scroll_end",
            "required_content_height",
            "reachable_content_height",
        )
        geometry_fields = (
            "registered_count",
            "active_count",
            "footer_height",
            "footer_top",
            "viewport_top",
            "viewport_height",
            "declared_clearance",
            "layout_clearance",
            "content_height",
            "content_size_hint_height",
            "content_minimum_size_hint_height",
            "scroll_minimum",
            "scroll_maximum",
            "last_body_child_bottom",
            "last_body_child_bottom_at_scroll_end",
        )
        for label, (surface, expected_semantic) in coverage_by_label.items():
            record = records.get(label, {})
            audit = record.get("dialog_scroll_audit")
            issues: list[str] = []
            if not isinstance(audit, dict):
                issues.append("missing-dialog-scroll-audit")
                audit = {}
            fixture = record.get("fixture_validation")
            if (
                not isinstance(fixture, dict)
                or fixture.get("passed") is not True
                or fixture.get("state_profile") != label
            ):
                issues.append("scroll-fixture-identity-not-proven")
            if audit.get("applicable") is not True:
                issues.append("dialog-scroll-audit-not-applicable")
            if audit.get("passed") is not True:
                issues.append("dialog-scroll-audit-did-not-pass")
            if audit.get("surface") != surface:
                issues.append("scroll-coverage-surface-mismatch")
            if not expected_semantic:
                issues.append("missing-scroll-page-semantic")
            if audit.get("expected_page_semantic") != expected_semantic:
                issues.append("expected-scroll-page-semantic-mismatch")
            if audit.get("actual_page_semantic") != expected_semantic:
                issues.append("actual-scroll-page-semantic-mismatch")
            if (
                not isinstance(audit.get("scroll_name"), str)
                or not str(audit.get("scroll_name", "")).strip()
            ):
                issues.append("missing-scroll-name")
            if type(audit.get("footer_visible")) is not bool:
                issues.append("invalid-footer-visibility")
            if type(audit.get("require_no_scroll")) is not bool:
                issues.append("invalid-require-no-scroll")
            for field in integer_fields:
                if type(audit.get(field)) is not int:
                    issues.append(f"invalid-scroll-metric:{field}")
            if (
                type(audit.get("registered_count")) is int
                and int(audit.get("registered_count", 0)) < 1
            ):
                issues.append("registered-scroll-count")
            if audit.get("active_count") != 1:
                issues.append("active-scroll-count")
            if (
                audit.get("footer_visible") is True
                and type(audit.get("footer_height")) is int
                and int(audit.get("footer_height", 0)) <= 0
            ):
                issues.append("visible-footer-height")
            if not isinstance(audit.get("issues"), list) or audit.get("issues"):
                issues.append("dialog-scroll-audit-reported-issues")
            if not any(issue.startswith("invalid-scroll-metric:") for issue in issues):
                metrics = {
                    field: int(audit[field])
                    for field in geometry_fields
                }
                metrics["footer_visible"] = bool(audit.get("footer_visible"))
                metrics["require_no_scroll"] = bool(
                    audit.get("require_no_scroll")
                )
                issues.extend(dialog_scroll_geometry_issue_codes(**metrics))
                required = max(
                    0,
                    int(audit["content_height"]),
                    int(audit["content_minimum_size_hint_height"]),
                )
                reachable = int(audit["viewport_height"]) + max(
                    0,
                    int(audit["scroll_maximum"])
                    - int(audit["scroll_minimum"]),
                )
                if int(audit["viewport_bottom"]) != (
                    int(audit["viewport_top"])
                    + int(audit["viewport_height"])
                ):
                    issues.append("viewport-bottom-mismatch")
                if int(audit["required_content_height"]) != required:
                    issues.append("required-content-height-mismatch")
                if int(audit["reachable_content_height"]) != reachable:
                    issues.append("reachable-content-height-mismatch")
            passed = not issues
            results.append({
                "label": label,
                "surface": surface,
                "expected_page_semantic": expected_semantic,
                "actual_page_semantic": audit.get("actual_page_semantic", ""),
                "registered_count": audit.get("registered_count"),
                "active_count": audit.get("active_count"),
                "footer_height": audit.get("footer_height"),
                "viewport_height": audit.get("viewport_height"),
                "declared_clearance": audit.get("declared_clearance"),
                "layout_clearance": audit.get("layout_clearance"),
                "required_content_height": audit.get("required_content_height"),
                "reachable_content_height": audit.get("reachable_content_height"),
                "last_body_child_bottom": audit.get("last_body_child_bottom"),
                "last_body_child_bottom_at_scroll_end": audit.get(
                    "last_body_child_bottom_at_scroll_end"
                ),
                "issues": list(dict.fromkeys(issues)),
                "passed": passed,
            })
            if not passed:
                self._failures.append({
                    "label": label,
                    "reason": (
                        "Dialog scroll coverage failed: "
                        + ", ".join(dict.fromkeys(issues))
                    ),
                })
        return {
            "required": True,
            "required_count": len(coverage_by_label),
            "records": results,
            "passed": (
                not duplicate_labels
                and len(results) == len(coverage_by_label)
                and all(result["passed"] for result in results)
            ),
        }

    def _responsive_stability_report(self) -> dict[str, Any]:
        """Record that responsive geometry is enforced by the non-GUI gate."""

        return {
            "required": False,
            "pair_count": 0,
            "pairs": [],
            "coverage": "automated-responsive-geometry",
            "passed": True,
        }

    def _finish(self) -> None:
        if bool(getattr(self, "_finished", False)):
            return
        self._finished = True
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
        fixture_validations_complete = (
            len(self._capture_records) == len(expected_labels)
            and all(
                int(record.get("capture_id", -1)) == index
                and str(record.get("label", "")) == expected_labels[index - 1]
                and bool(
                    dict(record.get("fixture_validation", {})).get("passed", False)
                )
                for index, record in enumerate(self._capture_records, start=1)
            )
        )
        finished_at = datetime.now().isoformat(timespec="milliseconds")
        capture_duration_ms = round(
            max(
                0.0,
                (
                    __import__("time").perf_counter()
                    - float(getattr(self, "_capture_started_monotonic", 0.0))
                ) * 1000.0,
            ),
            3,
        )
        performance: dict[str, Any] = {}
        for name, raw_values in dict(
            getattr(self, "_performance_samples", {})
        ).items():
            values = [float(value) for value in list(raw_values or ())]
            performance[str(name)] = {
                "samples": [round(value, 3) for value in values],
                "count": len(values),
                "minimum_ms": round(min(values), 3) if values else None,
                "maximum_ms": round(max(values), 3) if values else None,
                "mean_ms": (
                    round(sum(values) / len(values), 3) if values else None
                ),
            }
        memory_probe = dict(
            getattr(self, "_dialog_memory_probe", {"status": "not-run"})
        )
        memory_probe_complete = (
            self._capture_profile != "full"
            or (
                str(memory_probe.get("status", "")) == "measured"
                and int(memory_probe.get("cycles", 0) or 0) == 12
                and int(memory_probe.get("visible_cycles", 0) or 0) == 12
                and int(memory_probe.get("closed_cycles", 0) or 0) == 12
                and bool(memory_probe.get("passed", False))
            )
        )
        dialog_scroll_reporter = getattr(
            self,
            "_dialog_scroll_coverage_report",
            None,
        )
        if callable(dialog_scroll_reporter):
            dialog_scroll_audits = dialog_scroll_reporter()
        elif self._capture_profile == "full":
            dialog_scroll_audits = {
                "required": True,
                "required_count": 0,
                "records": [],
                "passed": False,
            }
            self._failures.append({
                "label": "dialog-scroll-audits",
                "reason": "Dialog scroll coverage reporter was unavailable",
            })
        else:
            dialog_scroll_audits = {
                "required": False,
                "required_count": 0,
                "records": [],
                "passed": True,
            }
        dialog_scroll_audits_complete = bool(
            dialog_scroll_audits.get("passed", False)
        )
        responsive_reporter = getattr(
            self,
            "_responsive_stability_report",
            None,
        )
        if callable(responsive_reporter):
            responsive_stability = responsive_reporter()
        elif self._capture_profile == "full":
            responsive_stability = {
                "required": True,
                "pair_count": 0,
                "pairs": [],
                "passed": False,
            }
            self._failures.append({
                "label": "responsive-stability",
                "reason": "Responsive stability reporter was unavailable",
            })
        else:
            responsive_stability = {
                "required": False,
                "pair_count": 0,
                "pairs": [],
                "passed": True,
            }
        responsive_stability_complete = bool(
            responsive_stability.get("passed", False)
        )
        complete = (
            captured_labels == expected_labels
            and len(self._screenshots) == len(expected_labels)
            and fixture_validations_complete
            and memory_probe_complete
            and dialog_scroll_audits_complete
            and responsive_stability_complete
            and not self._fatal_fixture_restore_failure
            and not self._failures
            and not self._text_layout_warnings
        )
        manifest = {
            "captured_at": finished_at,
            "started_at": str(
                getattr(self, "_capture_started_at", finished_at)
            ),
            "finished_at": finished_at,
            "duration_ms": capture_duration_ms,
            "performance": performance,
            "dialog_memory_probe": memory_probe,
            "dialog_memory_probe_complete": memory_probe_complete,
            "dialog_scroll_audits": dialog_scroll_audits,
            "dialog_scroll_audits_complete": dialog_scroll_audits_complete,
            "responsive_stability": responsive_stability,
            "responsive_stability_complete": responsive_stability_complete,
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
            "fixture_validations_complete": fixture_validations_complete,
            "complete": complete,
            "manifest_write_succeeded": True,
        }
        try:
            self._close_top_level_dialogs()
            self._close_dashboard()
        except Exception:
            pass
        manifest_write_succeeded = False
        try:
            manifest_path = self.session_dir / "manifest.json"
            manifest_path.write_text(
                __import__("json").dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            manifest_write_succeeded = True
        except Exception:
            logger.error("Anki Garden capture: could not write manifest", exc_info=True)
        if (
            os.environ.get("ANKI_GARDEN_CAPTURE_QUIT_WHEN_DONE") == "1"
            or not manifest_write_succeeded
        ):
            app = QApplication.instance()
            if app is not None:
                exit_code = 0 if complete and manifest_write_succeeded else 1
                QTimer.singleShot(350, lambda: app.exit(exit_code))
