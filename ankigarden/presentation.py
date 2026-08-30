"""Renderer-neutral product-language and state projections.

These contracts retain durable engine identifiers while giving every renderer
the same names and count semantics.  They intentionally contain no Qt, HTML,
or capture dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from .environment import (
    DEFAULT_GARDEN_FEATURE_ID,
    DEFAULT_SCENERY_ID,
    GARDEN_FEATURE_CATALOG,
    SCENERY_CATALOG,
)


def _read(source: Any, key: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)


def _identifier_display_name(value: Any) -> str:
    return str(value or "").replace("_", " ").strip().title()


@dataclass(frozen=True)
class PlantIdentity:
    """Stable instance, display, and species identities for one plant."""

    plant_id: str
    display_name: str
    species_name: str

    @classmethod
    def from_plant(cls, plant: Any) -> "PlantIdentity":
        plant_id = str(_read(plant, "plant_id", "") or "")
        species_id = str(_read(plant, "species", "") or "")
        species_name = str(
            _read(plant, "species_name", "")
            or _identifier_display_name(species_id)
            or "Plant"
        )
        display_name = str(
            _read(plant, "display_name", "")
            or _read(plant, "name", "")
            or f"{species_name} Plant"
        )
        return cls(plant_id, display_name, species_name)


def plant_identity(plant: Any) -> PlantIdentity:
    return PlantIdentity.from_plant(plant)


@dataclass(frozen=True)
class CollectionProjection:
    """Unambiguous species, instance, and whole-registry collection counts."""

    species_discovered: int
    species_total: int
    plants_owned: int
    collection_entries_discovered: int
    collection_entries_total: int
    collection_complete: bool

    @property
    def species_text(self) -> str:
        return (
            f"{self.species_discovered:,} of {self.species_total:,} "
            "species discovered"
        )

    @property
    def plants_text(self) -> str:
        noun = "plant" if self.plants_owned == 1 else "plants"
        return f"{self.plants_owned:,} {noun} owned"

    @property
    def collection_entries_text(self) -> str:
        return (
            f"{self.collection_entries_discovered:,} of "
            f"{self.collection_entries_total:,} collection entries discovered"
        )


def project_collection(state: Any) -> CollectionProjection:
    """Project collection counts from the existing registry authority."""

    # Import lazily: the registry resolves engine-owned item definitions, while
    # this module must remain safe for engine and non-Qt presentation imports.
    from .collectibles import collection_summary

    summary = collection_summary(state)
    species_discovered = max(0, int(summary.plant_species_owned))
    species_total = max(0, int(summary.plant_species_total))
    plants = _read(state, "plants", ())
    plants_owned = len(plants) if isinstance(plants, (list, tuple)) else 0
    return CollectionProjection(
        species_discovered=species_discovered,
        species_total=species_total,
        plants_owned=plants_owned,
        collection_entries_discovered=max(0, int(summary.collectibles_owned)),
        collection_entries_total=max(0, int(summary.collectibles_total)),
        collection_complete=bool(
            species_total > 0 and species_discovered == species_total
        ),
    )


def _catalog_name(catalog: Mapping[str, Any], item_id: str) -> str:
    item = catalog.get(item_id)
    return str(
        getattr(item, "name", "")
        or _identifier_display_name(item_id)
        or "None"
    )


@dataclass(frozen=True)
class GardenAppearanceProjection:
    """The four independent facts shown in Garden appearance summaries."""

    scenery_id: str
    scenery_name: str
    displayed_decoration_id: str
    displayed_decoration_name: str
    active_bonus_decoration_id: str
    active_bonus_name: str
    visual_effects_enabled: bool

    @property
    def visual_effects_text(self) -> str:
        return "On" if self.visual_effects_enabled else "Off"

    @property
    def summary_rows(self) -> tuple[tuple[str, str], ...]:
        return (
            ("Scenery", self.scenery_name),
            ("Displayed decoration", self.displayed_decoration_name),
            ("Active garden bonus", self.active_bonus_name),
            ("Visual effects", self.visual_effects_text),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenery_id": self.scenery_id,
            "displayed_decoration_id": self.displayed_decoration_id,
            "active_bonus_decoration_id": self.active_bonus_decoration_id,
            "visual_effects_enabled": self.visual_effects_enabled,
        }


def project_garden_appearance(
    state: Any,
    *,
    visual_effects_enabled: bool | None = None,
) -> GardenAppearanceProjection:
    """Resolve displayed, active, and day-locked appearance state separately."""

    loadout = _read(state, "loadout")
    schedule = _read(state, "daily_loadout")
    daily_stats = _read(state, "daily_stats")
    scheduler_day = str(_read(daily_stats, "day", "") or "")

    scenery_id = str(
        _read(loadout, "scenery_id", DEFAULT_SCENERY_ID)
        or DEFAULT_SCENERY_ID
    )
    if (
        schedule is not None
        and str(_read(schedule, "scheduler_day", "") or "") == scheduler_day
        and int(_read(schedule, "locked_at_ms", 0) or 0) > 0
        and _read(schedule, "scenery_id", "")
    ):
        scenery_id = str(_read(schedule, "scenery_id"))

    displayed_id = str(
        _read(
            loadout,
            "displayed_garden_feature_id",
            DEFAULT_GARDEN_FEATURE_ID,
        )
        or DEFAULT_GARDEN_FEATURE_ID
    )
    active_bonus_id = str(
        _read(
            loadout,
            "active_bonus_garden_feature_id",
            _read(loadout, "garden_feature_id", DEFAULT_GARDEN_FEATURE_ID),
        )
        or DEFAULT_GARDEN_FEATURE_ID
    )
    if (
        schedule is not None
        and str(_read(schedule, "garden_bonus_anki_day_id", "") or "")
        == scheduler_day
        and int(_read(schedule, "garden_bonus_locked_at_ms", 0) or 0) > 0
        and _read(schedule, "garden_feature_id", "")
    ):
        active_bonus_id = str(_read(schedule, "garden_feature_id"))

    visibility = _read(loadout, "visibility", {})
    if visual_effects_enabled is None:
        visual_effects_enabled = bool(
            not isinstance(visibility, Mapping)
            or visibility.get("garden_feature", visibility.get("weather", True))
            or visibility.get("scenery", True)
        )
    return GardenAppearanceProjection(
        scenery_id=scenery_id,
        scenery_name=_catalog_name(SCENERY_CATALOG, scenery_id),
        displayed_decoration_id=displayed_id,
        displayed_decoration_name=_catalog_name(
            GARDEN_FEATURE_CATALOG,
            displayed_id,
        ),
        active_bonus_decoration_id=active_bonus_id,
        active_bonus_name=_catalog_name(GARDEN_FEATURE_CATALOG, active_bonus_id),
        visual_effects_enabled=bool(visual_effects_enabled),
    )


STANDARD_FIND_INTERNAL_ID = "standard_find"
GARDEN_DISCOVERY_INTERNAL_ID = "garden_discovery"


@dataclass(frozen=True)
class VisibleRewardTerm:
    """Player vocabulary paired with the unchanged internal category ID."""

    internal_id: str
    singular: str
    plural: str

    def label(self, quantity: int = 1, *, include_quantity: bool = False) -> str:
        count = max(0, int(quantity))
        value = self.singular if count == 1 else self.plural
        return f"{count:,} {value}" if include_quantity else value


_STANDARD_FIND_IDS = frozenset({
    STANDARD_FIND_INTERNAL_ID,
    "standard",
    "standard_find_reward",
})
_GARDEN_DISCOVERY_IDS = frozenset({
    GARDEN_DISCOVERY_INTERNAL_ID,
    "environment_discovery",
    "garden_environment_discovery",
})


def visible_reward_term(internal_id: Any) -> VisibleRewardTerm:
    raw_id = str(internal_id or "").strip()
    normalized = raw_id.casefold()
    if normalized in _STANDARD_FIND_IDS:
        return VisibleRewardTerm(raw_id, "Standard Find", "Standard Finds")
    if normalized in _GARDEN_DISCOVERY_IDS:
        return VisibleRewardTerm(
            raw_id,
            "Garden discovery",
            "Garden discoveries",
        )
    fallback = _identifier_display_name(normalized) or "Reward"
    return VisibleRewardTerm(raw_id, fallback, f"{fallback}s")


class DiagnosticsUiState(str, Enum):
    """Visible Diagnostics result and interaction states."""

    SUCCESS = "success"
    WARNING = "warning"
    FAILURE = "failure"
    CHECKING = "checking"
    COPY_CONFIRMATION = "copy-confirmation"


@dataclass(frozen=True)
class DiagnosticsProjection:
    """Renderer-neutral copy, tone, and control state for Diagnostics."""

    state: DiagnosticsUiState
    result_state: DiagnosticsUiState
    title: str
    summary: str
    icon_name: str
    accent_role: str
    check_label: str
    check_enabled: bool
    copy_confirmation: str = ""

    @property
    def copy_confirmation_visible(self) -> bool:
        return bool(self.copy_confirmation)


def project_diagnostics(
    *,
    missing_artwork_count: int = 0,
    contract_failure_count: int = 0,
    parsing_exception_count: int = 0,
    failure_message: str = "",
    checking: bool = False,
    copy_confirmed: bool = False,
) -> DiagnosticsProjection:
    """Project one exact Diagnostics state without Qt or capture knowledge."""

    missing = max(0, int(missing_artwork_count))
    contract_failures = max(0, int(contract_failure_count))
    parsing_exceptions = max(0, int(parsing_exception_count))
    failure = str(failure_message or "").strip()
    if failure or contract_failures or parsing_exceptions:
        result_state = DiagnosticsUiState.FAILURE
        title = "Display issues detected"
        summary = failure or (
            "Check again. Copy the current report if the issue continues."
        )
        icon_name = "warning"
        accent_role = "error"
    elif missing:
        result_state = DiagnosticsUiState.WARNING
        title = (
            f"{missing:,} artwork file is missing"
            if missing == 1 else
            f"{missing:,} artwork files are missing"
        )
        summary = "Some plants, decorations, or scenery may not appear."
        icon_name = "warning"
        accent_role = "warning"
    else:
        result_state = DiagnosticsUiState.SUCCESS
        title = "All artwork is available"
        summary = ""
        icon_name = "check"
        accent_role = "success"

    if checking:
        return DiagnosticsProjection(
            state=DiagnosticsUiState.CHECKING,
            result_state=result_state,
            title="Checking display diagnostics",
            summary="Scanning artwork and display telemetry.",
            icon_name="refresh",
            accent_role="checking",
            check_label="Checking…",
            check_enabled=False,
        )
    if copy_confirmed:
        return DiagnosticsProjection(
            state=DiagnosticsUiState.COPY_CONFIRMATION,
            result_state=result_state,
            title=title,
            summary=summary,
            icon_name=icon_name,
            accent_role=accent_role,
            check_label="Check again",
            check_enabled=True,
            copy_confirmation="Report copied to clipboard",
        )
    return DiagnosticsProjection(
        state=result_state,
        result_state=result_state,
        title=title,
        summary=summary,
        icon_name=icon_name,
        accent_role=accent_role,
        check_label="Check again",
        check_enabled=True,
    )
