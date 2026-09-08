"""Renderer-neutral product-language and state projections.

These contracts retain durable engine identifiers while giving every renderer
the same names and count semantics.  They intentionally contain no Qt, HTML,
or capture dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping
from .feature_availability import landmarks_enabled

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


@dataclass(frozen=True)
class GardenSetupItem:
    kind: str
    appearance_id: str
    appearance_name: str
    visible: bool
    bonus_id: str = ""
    bonus_name: str = ""
    effect: str = "No bonus"


@dataclass(frozen=True)
class GardenSupplyEffect:
    name: str
    effect: str
    plant_id: str = ""
    plant_name: str = ""
    remaining_cards: int = 0
    pending: bool = False


@dataclass(frozen=True)
class GardenSetupProjection:
    items: tuple[GardenSetupItem, ...]
    effects: tuple[GardenSupplyEffect, ...]


def project_garden_setup(engine: Any, storage: Any) -> GardenSetupProjection:
    """Read committed appearance and engine-resolved effects without transactions.

    In particular, previewing this projection must never start a review session,
    quote an item, or roll the day.
    """
    from .balance_catalog import COSMETIC_BY_ID
    from .ui.copy import garden_bonus_effect_copy
    from .ui.economy_presenters import growth_points

    state = storage.state
    items = []
    for kind, appearance_id, catalog in (
        ("scenery", str(state.selected_background), SCENERY_CATALOG),
        ("garden_feature", str(state.displayed_garden_feature), GARDEN_FEATURE_CATALOG),
    ):
        item = catalog.get(appearance_id)
        name = (COSMETIC_BY_ID[appearance_id].display_name
                if appearance_id in COSMETIC_BY_ID else _catalog_name(catalog, appearance_id))
        effect = (garden_bonus_effect_copy(item.item_id, item.effect).strip()
                  if item is not None else "Appearance only")
        items.append(GardenSetupItem(
            kind, appearance_id, name,
            True,
            appearance_id, name, effect,
        ))
    if landmarks_enabled():
        landmarks = engine.landmark_catalog_summary().get("items", ())
        displayed = next((row for row in landmarks if row.get("displayed")), None)
        items.append(GardenSetupItem(
            "landmark", str(displayed["landmark_id"]) if displayed else "",
            str(displayed["display_name"]) if displayed else "No landmark displayed",
            bool(displayed), effect="Cosmetic · No bonus",
        ))
    effects = []
    for plant in state.plants:
        identity = plant_identity(plant)
        for field, pending in (("fertilizer_card_batches", False),
                               ("booster_card_batches", False),
                               ("fertilizer_card_queue", True),
                               ("booster_card_queue", True)):
            grouped: dict[tuple[str, int], int] = {}
            for batch in _read(plant, field, ()) or ():
                if batch.remaining_cards > 0:
                    key = (batch.effect_id, batch.growth_per_card_units)
                    grouped[key] = grouped.get(key, 0) + batch.remaining_cards
            for (effect_id, units), cards in grouped.items():
                tier = effect_id.removeprefix("fertilizer_")
                spec = getattr(engine, "FERTILIZERS", {}).get(tier)
                name = "Booster Potion" if effect_id == "booster_potion" else str(
                    getattr(spec, "name", "") or _identifier_display_name(effect_id))
                effects.append(GardenSupplyEffect(
                    name, f"+{growth_points(units)} Growth per card",
                    identity.plant_id, identity.display_name, cards, pending,
                ))
    bonus = engine.current_streak_bonus_percent()
    if bonus:
        # Achievement unlocks retain this percentage after the streak ends.
        effects.append(GardenSupplyEffect("Permanent Growth bonus", f"+{bonus}% Growth"))
    return GardenSetupProjection(tuple(items), tuple(effects))


def _identifier_display_name(value: Any) -> str:
    return str(value or "").replace("_", " ").strip().title()


def plant_species_name(plant: Any) -> str:
    """Resolve a species independently of the retired custom plant name."""
    from .balance_catalog import SPECIES_BY_ID

    species = str(plant if isinstance(plant, str) else _read(plant, "species", "") or "")
    definition = SPECIES_BY_ID.get(species)
    if definition is not None:
        return definition.display_name
    return (
        _identifier_display_name(species)
        or str(_read(plant, "species_name", "") or _read(plant, "plant_class", "")).strip()
        or "Plant"
    )


def plant_stage_title(species: Any, stage: Any) -> str:
    """Put Seed/Sprout after the species and later stage modifiers before it."""
    from .growth import stage_presentation

    name = plant_species_name(species)
    resolved = stage_presentation(stage)
    if resolved is None:
        return name
    if resolved.stage_id in {"seed", "sprout"}:
        return f"{name} {resolved.display_name}"
    return f"{resolved.display_name} {name}"


def plant_stage_event(species: Any, stage: Any, *, checkpoint_percent: int = 0) -> str:
    """Describe the recorded milestone, never the plant's later live stage."""
    from .growth import stage_presentation

    name = plant_species_name(species)
    resolved = stage_presentation(stage)
    destination = resolved.display_name if resolved is not None else "a new stage"
    if checkpoint_percent:
        return f"{name} reached {checkpoint_percent}% toward {destination}"
    return f"{name} reached {destination}"


@dataclass(frozen=True)
class PlantIdentity:
    """Stable instance, display, and species identities for one plant."""

    plant_id: str
    display_name: str
    species_name: str

    @classmethod
    def from_plant(cls, plant: Any) -> "PlantIdentity":
        plant_id = str(_read(plant, "plant_id", "") or "")
        species_name = plant_species_name(plant)
        stage = _read(plant, "growth_stage", "") or _read(plant, "stage", "") or _read(plant, "stage_after", "")
        if not stage and _read(plant, "growth_points", None) is not None:
            from .growth import stage_progress

            stage = stage_progress(_read(plant, "growth_points")).stage
        display_name = plant_stage_title(species_name, stage)
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


@dataclass(frozen=True)
class AppearanceCollectionProjection:
    category: str
    owned: int
    total: int

    @property
    def text(self) -> str:
        label = "Scenery" if self.category == "scenery" else "Decorations"
        return f"{label} collected: {self.owned:,} of {self.total:,}"


def project_appearance_collection(state: Any, kind: str) -> AppearanceCollectionProjection:
    """Count distinct player-facing collectible IDs, including owned defaults."""
    from .collectibles import collection_entry_views

    category = "scenery" if kind == "scenery" else "garden_features"
    views = {
        view.definition.item_id: view
        for view in collection_entry_views(state)
        if view.definition.category == category
    }
    return AppearanceCollectionProjection(category, sum(view.owned for view in views.values()), len(views))


def _catalog_name(catalog: Mapping[str, Any], item_id: str) -> str:
    item = catalog.get(item_id)
    return str(
        getattr(item, "name", "")
        or _identifier_display_name(item_id)
        or "None"
    )


def _catalog_effect(catalog: Mapping[str, Any], item_id: str) -> str:
    item = catalog.get(item_id)
    return str(getattr(item, "effect", "") or "").strip().rstrip(".")


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
    active_bonus_effect: str = ""

    @property
    def visual_effects_text(self) -> str:
        return "Enabled" if self.visual_effects_enabled else "Disabled"

    @property
    def summary_rows(self) -> tuple[tuple[str, str], ...]:
        return (
            ("Scenery", self.scenery_name),
            ("Displayed decoration", self.displayed_decoration_name),
            (
                "Active garden bonus",
                " · ".join(
                    part
                    for part in (
                        self.active_bonus_name,
                        self.active_bonus_effect,
                    )
                    if part
                ),
            ),
            ("Visual effects", self.visual_effects_text),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenery_id": self.scenery_id,
            "displayed_decoration_id": self.displayed_decoration_id,
            "active_bonus_decoration_id": self.active_bonus_decoration_id,
            "active_bonus_effect": self.active_bonus_effect,
            "visual_effects_enabled": self.visual_effects_enabled,
        }


def project_garden_appearance(
    state: Any,
    *,
    visual_effects_enabled: bool | None = None,
) -> GardenAppearanceProjection:
    """Project equipped artwork and the effect belonging to that same item."""

    # Keep engine/catalog effect language stable while projecting the exact
    # learner-facing card cadence shared by every Garden surface.
    from .ui.copy import garden_bonus_effect_copy

    loadout = _read(state, "loadout")
    scenery_id = str(_read(loadout, "display_scenery_id", _read(loadout, "scenery_id", DEFAULT_SCENERY_ID)) or DEFAULT_SCENERY_ID)
    displayed_id = str(_read(loadout, "display_decoration_id", _read(loadout, "displayed_garden_feature_id", DEFAULT_GARDEN_FEATURE_ID)) or DEFAULT_GARDEN_FEATURE_ID)
    active_bonus_id = displayed_id
    # Retain the optional parameter for older renderers; equipped artwork
    # always displays, independently of retired visibility preferences.
    visual_effects_enabled = True
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
        active_bonus_effect=(garden_bonus_effect_copy(
            active_bonus_id,
            _catalog_effect(GARDEN_FEATURE_CATALOG, active_bonus_id),
        ) if active_bonus_id in GARDEN_FEATURE_CATALOG else "No bonus"),
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
        return VisibleRewardTerm(raw_id, "Garden Find", "Garden Finds")
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

    NOT_CHECKED = "not-checked"
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
    checked: bool = True,
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
    if not checked:
        result_state = DiagnosticsUiState.NOT_CHECKED
        title = "Check garden artwork"
        summary = "Check that the artwork included with Anki Garden is available."
        icon_name = "refresh"
        accent_role = "neutral"
    elif failure or contract_failures or parsing_exceptions:
        result_state = DiagnosticsUiState.FAILURE
        title = "Couldn’t check artwork" if failure else "Display issues detected"
        summary = failure or (
            "Check again. Copy the current report if the issue continues."
        )
        icon_name = "warning"
        accent_role = "error"
    elif missing:
        result_state = DiagnosticsUiState.WARNING
        title = "Some artwork is missing"
        summary = "Some plants, decorations, or scenery may not appear. Check again or copy the support report."
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
            title="Checking artwork…",
            summary="Checking the artwork included with Anki Garden.",
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
            copy_confirmation="Report copied",
        )
    return DiagnosticsProjection(
        state=result_state,
        result_state=result_state,
        title=title,
        summary=summary,
        icon_name=icon_name,
        accent_role=accent_role,
        check_label="Check again" if checked else "Check artwork",
        check_enabled=True,
    )
