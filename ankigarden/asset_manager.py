from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class BedAnchor:
    """One permanent planting bed in normalized scene coordinates."""

    x: float
    y: float
    depth: float
    plant_scale: float
    footprint: tuple[float, float]
    label_anchor: tuple[float, float]
    physical_width_ratio: float = 0.125
    surface_id: str = ""
    contact_plane: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
    shadow_depth: str = "front"
    shadow_opacity: float = 0.34
    occlusion_id: str = ""

    @classmethod
    def from_manifest(cls, value: Any, default: "BedAnchor") -> "BedAnchor":
        row = value if isinstance(value, dict) else {}

        def number(key: str, fallback: float, low: float = 0.0, high: float = 1.0) -> float:
            try:
                return max(low, min(high, float(row.get(key, fallback))))
            except (TypeError, ValueError):
                return fallback

        def pair(key: str, fallback: tuple[float, float]) -> tuple[float, float]:
            raw = row.get(key, fallback)
            if not isinstance(raw, (list, tuple)) or len(raw) != 2:
                return fallback
            result: list[float] = []
            for item, default_item in zip(raw, fallback):
                try:
                    result.append(max(0.0, min(1.0, float(item))))
                except (TypeError, ValueError):
                    result.append(default_item)
            return result[0], result[1]

        def quad(
            key: str, fallback: tuple[float, float, float, float]
        ) -> tuple[float, float, float, float]:
            raw = row.get(key, fallback)
            if not isinstance(raw, (list, tuple)) or len(raw) != 4:
                return fallback
            result: list[float] = []
            for item, default_item in zip(raw, fallback):
                try:
                    result.append(max(0.0, min(1.0, float(item))))
                except (TypeError, ValueError):
                    result.append(default_item)
            return result[0], result[1], result[2], result[3]

        shadow_depth = str(row.get("shadow_depth", default.shadow_depth))
        if shadow_depth not in {"rear", "front"}:
            shadow_depth = default.shadow_depth

        return cls(
            x=number("x", default.x),
            y=number("y", default.y),
            depth=number("depth", default.depth),
            plant_scale=number("plant_scale", default.plant_scale, 0.35, 1.4),
            footprint=pair("footprint", default.footprint),
            label_anchor=pair("label_anchor", default.label_anchor),
            physical_width_ratio=number(
                "physical_width_ratio", default.physical_width_ratio, 0.04, 0.30
            ),
            surface_id=str(row.get("surface_id", default.surface_id)),
            contact_plane=quad("contact_plane", default.contact_plane),
            shadow_depth=shadow_depth,
            shadow_opacity=number("shadow_opacity", default.shadow_opacity, 0.0, 1.0),
            occlusion_id=str(row.get("occlusion_id", default.occlusion_id)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "x": self.x,
            "y": self.y,
            "depth": self.depth,
            "plant_scale": self.plant_scale,
            "footprint": list(self.footprint),
            "label_anchor": list(self.label_anchor),
            "physical_width_ratio": self.physical_width_ratio,
            "surface_id": self.surface_id,
            "contact_plane": list(self.contact_plane),
            "shadow_depth": self.shadow_depth,
            "shadow_opacity": self.shadow_opacity,
            "occlusion_id": self.occlusion_id,
        }


@dataclass(frozen=True)
class SceneSurfaceProfile:
    """Registered background variants and the physical surfaces painted into them."""

    profile_id: str
    geometry_version: int
    theme: str
    light_direction: tuple[float, float]
    variant_breakpoints: dict[str, float]
    variants: dict[str, dict[str, Any]]

    @classmethod
    def from_manifest(cls, value: Any) -> Optional["SceneSurfaceProfile"]:
        row = value if isinstance(value, dict) else {}
        profile_id = str(row.get("profile_id", "")).strip()
        raw_variants = row.get("variants")
        if not profile_id or not isinstance(raw_variants, dict):
            return None

        def number(raw: Any, default: float, low: float = 0.0, high: float = 4.0) -> float:
            try:
                return max(low, min(high, float(raw)))
            except (TypeError, ValueError):
                return default

        direction = row.get("light_direction", [-0.22, 0.18])
        light_direction = (
            number(direction[0], -0.22, -1.0, 1.0),
            number(direction[1], 0.18, -1.0, 1.0),
        ) if isinstance(direction, (list, tuple)) and len(direction) == 2 else (-0.22, 0.18)
        breakpoints = row.get("variant_breakpoints", {})
        normalized_breakpoints = {
            "four_three_max": number(
                breakpoints.get("four_three_max") if isinstance(breakpoints, dict) else None,
                1.42, 1.0, 2.0,
            ),
            "ultrawide_min": number(
                breakpoints.get("ultrawide_min") if isinstance(breakpoints, dict) else None,
                2.05, 1.4, 4.0,
            ),
        }
        variants: dict[str, dict[str, Any]] = {}
        for name in ("4:3", "16:9", "home"):
            raw = raw_variants.get(name)
            if not isinstance(raw, dict):
                continue
            asset_file = str(raw.get("file", ""))
            occlusion_file = str(raw.get("occlusion_file", ""))
            if not asset_file.startswith("assets/") or ".." in Path(asset_file).parts:
                continue
            if occlusion_file and (
                not occlusion_file.startswith("assets/") or ".." in Path(occlusion_file).parts
            ):
                continue
            surfaces = raw.get("surfaces")
            if not isinstance(surfaces, list) or len(surfaces) != 6:
                continue
            variants[name] = {
                "file": asset_file,
                "occlusion_file": occlusion_file,
                "width": max(1, int(number(raw.get("width"), 1, 1, 10000))),
                "height": max(1, int(number(raw.get("height"), 1, 1, 10000))),
                "focal_point": list(raw.get("focal_point", [0.5, 0.5])),
                "planting_zone": dict(raw.get("planting_zone", {})),
                "surfaces": [dict(surface) for surface in surfaces if isinstance(surface, dict)],
            }
        if set(variants) != {"4:3", "16:9", "home"}:
            return None
        return cls(
            profile_id=profile_id,
            geometry_version=max(1, int(number(row.get("geometry_version"), 1, 1, 99))),
            theme=str(row.get("theme", "verdant_dusk")),
            light_direction=light_direction,
            variant_breakpoints=normalized_breakpoints,
            variants=variants,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "geometry_version": self.geometry_version,
            "theme": self.theme,
            "light_direction": list(self.light_direction),
            "variant_breakpoints": dict(self.variant_breakpoints),
            "variants": {name: dict(value) for name, value in self.variants.items()},
        }


DEFAULT_BED_ANCHORS: tuple[BedAnchor, ...] = (
    BedAnchor(0.27, 0.58, 0.58, 1.0, (0.125, 0.040), (0.27, 0.635), 0.125),
    BedAnchor(0.47, 0.55, 0.55, 1.0, (0.130, 0.040), (0.47, 0.605), 0.130),
    BedAnchor(0.75, 0.58, 0.58, 1.0, (0.125, 0.040), (0.75, 0.635), 0.125),
    BedAnchor(0.31, 0.80, 0.80, 1.0, (0.155, 0.050), (0.31, 0.845), 0.155),
    BedAnchor(0.53, 0.85, 0.85, 1.0, (0.170, 0.050), (0.53, 0.895), 0.170),
    BedAnchor(0.69, 0.80, 0.80, 1.0, (0.155, 0.050), (0.69, 0.845), 0.155),
)


@dataclass(frozen=True)
class AssetPlacement:
    anchor_x: float = 0.5
    baseline_y: float = 0.86
    scale: float = 1.0
    crop: str = "contain"
    layer: str = "content"
    visible_bounds: tuple[float, float, float, float] = (0.08, 0.04, 0.84, 0.92)
    ground_anchor: tuple[float, float] = (0.5, 0.96)
    art_bounds: tuple[float, float, float, float] = (0.08, 0.04, 0.84, 0.92)
    base_bounds: tuple[float, float, float, float] = (0.30, 0.72, 0.40, 0.24)
    support_bounds: tuple[float, float, float, float] = (0.32, 0.86, 0.36, 0.10)
    foliage_bounds: tuple[float, float, float, float] = (0.08, 0.04, 0.84, 0.72)
    plant_above_rim_bounds: tuple[float, float, float, float] = (0.08, 0.04, 0.84, 0.68)
    soil_contact: tuple[float, float] = (0.5, 0.96)
    interaction_bounds: tuple[float, float, float, float] = (0.06, 0.02, 0.88, 0.96)
    display_scale: float = 1.0
    base_type: str = "legacy"
    contact_shadow: tuple[float, float] = (0.56, 0.055)
    geometry_version: int = 0
    review_provenance: str = ""
    vessel_class: str = "legacy"
    vessel_class_multiplier: float = 1.0
    scene_scale_correction: float = 1.0
    focal_point: tuple[float, float] = (0.5, 0.5)
    planting_zone: tuple[float, float, float, float] = (0.08, 0.92, 0.62, 0.91)
    scene_anchor: tuple[float, float] = (0.82, 0.86)
    bed_anchors: tuple[BedAnchor, ...] = DEFAULT_BED_ANCHORS
    layout_profiles: dict[str, Any] = field(default_factory=dict)
    surface_profile: Optional[SceneSurfaceProfile] = None

    @classmethod
    def from_manifest(cls, value: Any, *, category: str) -> "AssetPlacement":
        row = value if isinstance(value, dict) else {}
        defaults = {
            "backgrounds": cls(0.5, 0.5, 1.0, "cover", "background", focal_point=(0.5, 0.43)),
            "weather": cls(0.5, 0.5, 1.0, "cover", "weather"),
            "decorations": cls(0.82, 0.86, 0.72, "contain", "decoration"),
            "plants": cls(0.5, 0.9, 1.0, "contain", "plants"),
            "ui": cls(),
        }.get(category, cls())

        def number(key: str, default: float, low: float, high: float) -> float:
            try:
                return max(low, min(high, float(row.get(key, default))))
            except (TypeError, ValueError):
                return default

        crop = str(row.get("crop", defaults.crop))
        if crop not in {"contain", "cover"}:
            crop = defaults.crop
        def pair(key: str, default: tuple[float, float]) -> tuple[float, float]:
            value = row.get(key, default)
            return pair_from(value, default)

        def pair_from(value: Any, default: tuple[float, float]) -> tuple[float, float]:
            if not isinstance(value, (list, tuple)) or len(value) != 2:
                return default
            return (number_from(value[0], default[0]), number_from(value[1], default[1]))

        def quad(key: str, default: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
            value = row.get(key, default)
            if key == "planting_zone" and isinstance(value, dict):
                value = [value.get("left"), value.get("right"), value.get("far_y"), value.get("near_y")]
            if not isinstance(value, (list, tuple)) or len(value) != 4:
                return default
            return tuple(number_from(v, d) for v, d in zip(value, default))  # type: ignore[return-value]

        def number_from(value: Any, default: float) -> float:
            try:
                return max(0.0, min(1.0, float(value)))
            except (TypeError, ValueError):
                return default

        base_type = str(row.get("base_type", defaults.base_type))
        if base_type not in {"pot", "dirt_mound", "legacy"}:
            base_type = defaults.base_type
        vessel_class = str(row.get("vessel_class", defaults.vessel_class))
        if vessel_class not in {
            "standard_upright", "wide_planter", "bonsai_tray", "bowl_low",
            "soil_only", "legacy",
        }:
            vessel_class = defaults.vessel_class
        contact_default = {
            "pot": (0.52, 0.045),
            "dirt_mound": (0.68, 0.04),
            "legacy": defaults.contact_shadow,
        }[base_type]
        raw_beds = row.get("bed_anchors")
        if isinstance(raw_beds, list) and len(raw_beds) == len(DEFAULT_BED_ANCHORS):
            bed_anchors = tuple(
                BedAnchor.from_manifest(item, DEFAULT_BED_ANCHORS[index])
                for index, item in enumerate(raw_beds)
            )
        else:
            bed_anchors = DEFAULT_BED_ANCHORS
        layout_profiles: dict[str, Any] = {}
        raw_profiles = row.get("layout_profiles")
        if isinstance(raw_profiles, dict):
            for profile_name in ("4:3", "3:2", "16:9", "home"):
                raw_profile = raw_profiles.get(profile_name)
                if not isinstance(raw_profile, dict):
                    continue
                profile: dict[str, Any] = {}
                profile["focal_point"] = list(pair_from(raw_profile.get("focal_point"), defaults.focal_point))
                coordinate_space = str(raw_profile.get("coordinate_space", "viewport"))
                profile["coordinate_space"] = (
                    coordinate_space
                    if coordinate_space in {"viewport", "source_4_3", "source"}
                    else "viewport"
                )
                if raw_profile.get("surface_variant") in {"4:3", "16:9", "home"}:
                    profile["surface_variant"] = str(raw_profile["surface_variant"])
                try:
                    profile["source_aspect_ratio"] = max(
                        0.5, min(4.0, float(raw_profile.get("source_aspect_ratio", 4 / 3)))
                    )
                except (TypeError, ValueError):
                    profile["source_aspect_ratio"] = 4 / 3
                raw_zone = raw_profile.get("planting_zone")
                if isinstance(raw_zone, dict):
                    profile["planting_zone"] = {
                        "left": number_from(raw_zone.get("left"), defaults.planting_zone[0]),
                        "right": number_from(raw_zone.get("right"), defaults.planting_zone[1]),
                        "far_y": number_from(raw_zone.get("far_y"), defaults.planting_zone[2]),
                        "near_y": number_from(raw_zone.get("near_y"), defaults.planting_zone[3]),
                    }
                compositions: dict[str, list[dict[str, Any]]] = {}
                raw_compositions = raw_profile.get("compositions")
                if isinstance(raw_compositions, dict):
                    for count in range(1, 7):
                        raw_composition = raw_compositions.get(str(count))
                        if not isinstance(raw_composition, list) or len(raw_composition) != 6:
                            continue
                        compositions[str(count)] = [
                            BedAnchor.from_manifest(item, DEFAULT_BED_ANCHORS[index]).to_dict()
                            for index, item in enumerate(raw_composition)
                        ]
                if compositions:
                    profile["compositions"] = compositions
                layout_profiles[profile_name] = profile
        return cls(
            anchor_x=number("anchor_x", defaults.anchor_x, 0.0, 1.0),
            baseline_y=number("baseline_y", defaults.baseline_y, 0.0, 1.0),
            scale=number("scale", defaults.scale, 0.1, 2.5),
            crop=crop,
            layer=str(row.get("layer", defaults.layer)),
            visible_bounds=quad("visible_bounds", defaults.visible_bounds),
            ground_anchor=pair("ground_anchor", defaults.ground_anchor),
            art_bounds=quad("art_bounds", quad("visible_bounds", defaults.art_bounds)),
            base_bounds=quad("base_bounds", defaults.base_bounds),
            support_bounds=quad("support_bounds", quad("base_bounds", defaults.support_bounds)),
            foliage_bounds=quad("foliage_bounds", quad("visible_bounds", defaults.foliage_bounds)),
            plant_above_rim_bounds=quad(
                "plant_above_rim_bounds", quad("foliage_bounds", defaults.plant_above_rim_bounds)
            ),
            soil_contact=pair("soil_contact", pair("ground_anchor", defaults.soil_contact)),
            interaction_bounds=quad("interaction_bounds", quad("visible_bounds", defaults.interaction_bounds)),
            display_scale=number("display_scale", number("scale", defaults.display_scale, 0.1, 2.5), 0.1, 2.5),
            base_type=base_type,
            contact_shadow=pair("contact_shadow", contact_default),
            geometry_version=int(number("geometry_version", defaults.geometry_version, 0, 99)),
            review_provenance=str(row.get("review_provenance", defaults.review_provenance)),
            vessel_class=vessel_class,
            vessel_class_multiplier=number(
                "vessel_class_multiplier", defaults.vessel_class_multiplier, 0.5, 1.5
            ),
            scene_scale_correction=number(
                "scene_scale_correction", defaults.scene_scale_correction, 0.5, 1.5
            ),
            focal_point=pair("focal_point", defaults.focal_point),
            planting_zone=quad("planting_zone", defaults.planting_zone),
            scene_anchor=pair("scene_anchor", (number("anchor_x", defaults.anchor_x, 0, 1), number("baseline_y", defaults.baseline_y, 0, 1))),
            bed_anchors=bed_anchors,
            layout_profiles=layout_profiles,
            surface_profile=SceneSurfaceProfile.from_manifest(row.get("surface_profile")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "anchor_x": self.anchor_x,
            "baseline_y": self.baseline_y,
            "scale": self.scale,
            "crop": self.crop,
            "layer": self.layer,
            "visible_bounds": list(self.visible_bounds),
            "ground_anchor": list(self.ground_anchor),
            "art_bounds": list(self.art_bounds),
            "base_bounds": list(self.base_bounds),
            "support_bounds": list(self.support_bounds),
            "foliage_bounds": list(self.foliage_bounds),
            "plant_above_rim_bounds": list(self.plant_above_rim_bounds),
            "soil_contact": list(self.soil_contact),
            "interaction_bounds": list(self.interaction_bounds),
            "display_scale": self.display_scale,
            "base_type": self.base_type,
            "contact_shadow": list(self.contact_shadow),
            "geometry_version": self.geometry_version,
            "review_provenance": self.review_provenance,
            "vessel_class": self.vessel_class,
            "vessel_class_multiplier": self.vessel_class_multiplier,
            "scene_scale_correction": self.scene_scale_correction,
            "focal_point": list(self.focal_point),
            "planting_zone": {
                "left": self.planting_zone[0], "right": self.planting_zone[1],
                "far_y": self.planting_zone[2], "near_y": self.planting_zone[3],
            },
            "scene_anchor": list(self.scene_anchor),
            "bed_anchors": [anchor.to_dict() for anchor in self.bed_anchors],
            "layout_profiles": self.layout_profiles,
            "surface_profile": self.surface_profile.to_dict() if self.surface_profile is not None else {},
        }


@dataclass(frozen=True)
class ResolvedAsset:
    path: Path
    asset_id: str
    category: str
    placement: AssetPlacement
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        rel = Path(str(self.metadata.get("file", "")))
        asset_root = self.path
        if rel.parts:
            for _part in rel.parts:
                asset_root = asset_root.parent
        else:
            asset_root = self.path.parent
        return {
            "path": str(self.path),
            "asset_root": str(asset_root),
            "asset_id": self.asset_id,
            "category": self.category,
            "placement": self.placement.to_dict(),
            "metadata": dict(self.metadata),
        }


class AssetManager:
    SUPPORTED_FORMATS = {".svg", ".png", ".webp"}
    MIN_DIMENSIONS = {
        "plants": (128, 128),
        "backgrounds": (512, 384),
        "decorations": (128, 128),
        "weather": (256, 192),
        "overlays": (512, 384),
        "ui": (128, 96),
    }

    QUALITY_ORDER = {"performance": 0, "balanced": 1, "ultra": 2}
    THEME_ALIASES = {"morning_bloom": "verdant_dawn"}

    def __init__(self, config: Any, storage: Any) -> None:
        self.config = config
        self.storage = storage
        self.metadata = self.storage.load_asset_metadata()
        self._catalog = self._load_catalog()
        self._migrate_legacy_metadata()

    def get_or_fetch(
        self,
        category: str,
        key: str,
        query: str,
        provider_hint: Optional[str] = None,
        theme: Optional[str] = None,
        reroll: bool = False,
        quality_preference: Optional[str] = None,
    ) -> Optional[Path]:
        resolved = self.resolve(
            category,
            key,
            query,
            provider_hint=provider_hint,
            theme=theme,
            reroll=reroll,
            quality_preference=quality_preference,
        )
        return resolved.path if resolved else None

    def resolve(
        self,
        category: str,
        key: str,
        query: str,
        provider_hint: Optional[str] = None,
        theme: Optional[str] = None,
        reroll: bool = False,
        quality_preference: Optional[str] = None,
    ) -> Optional[ResolvedAsset]:
        del query, provider_hint
        cache_key = f"{category}:{key}"
        slot = self._slot_for(category, key, theme)
        quality_pref = str(
            quality_preference
            or self.config.nested("assets", "quality_preference", default="balanced")
            or "balanced"
        )

        candidates = self._select_candidates(category, slot, quality_pref)
        if not candidates:
            if self.config.nested("assets", "allow_fallback_placeholder", default=True):
                candidates = self._placeholder_candidates()
            else:
                return None

        valid_candidates = [
            entry for entry in candidates
            if self._valid_local_asset(self.storage.addon_dir / entry["file"], category)
        ]
        if not valid_candidates:
            if not self.config.nested("assets", "allow_fallback_placeholder", default=True):
                return None
            placeholder = self._ensure_placeholder_asset()
            valid_candidates = [{
                "asset_id": "fallback_placeholder",
                "category": category,
                "file": str(placeholder.relative_to(self.storage.addon_dir)),
                "width": 1200,
                "height": 675,
                "quality_score": 0.5,
            }]

        idx = self._pick_index(cache_key, key, [self.storage.addon_dir / row["file"] for row in valid_candidates], reroll)
        picked_entry = valid_candidates[idx]
        picked = self.storage.addon_dir / picked_entry["file"]
        rel = str(picked.relative_to(self.storage.addon_dir))
        raw_placement = dict(picked_entry.get("placement", {})) if isinstance(picked_entry.get("placement"), dict) else {}
        if category == "plants" and "base_type" not in raw_placement:
            growth_base = str(picked_entry.get("growth_base", ""))
            species = str((picked_entry.get("slot", {}) or {}).get("species", ""))
            if growth_base == "bonsai_pot" or "pot" in picked_entry.get("variants", []) or (
                species == "rose" and picked_entry.get("style_family") == "storybook_gouache"
            ):
                raw_placement["base_type"] = "pot"
            elif growth_base == "dirt_mound" or "dirt_mound" in picked_entry.get("variants", []):
                raw_placement["base_type"] = "dirt_mound"
        self.metadata[cache_key] = {
            "provider": "local_catalog",
            "source_kind": "local_catalog",
            "source_url": "local://manifest",
            "query": "",
            "downloaded_at": int(time.time()),
            "local_path": rel,
            "quality_score": self._quality_score_for(rel),
            "dimensions": self._manifest_dimensions_for(rel),
            "derivatives": {"thumbnail": rel, "preview": rel, "full": rel},
            "catalog_slot": slot,
            "catalog_cycle_index": idx,
            "asset_id": str(picked_entry.get("asset_id", "")),
            "placement": AssetPlacement.from_manifest(raw_placement, category=category).to_dict(),
            "legacy_remote_preserved": bool(self.metadata.get(cache_key, {}).get("legacy_remote_preserved", False)),
        }
        self.storage.save_asset_metadata(self.metadata)
        placement = AssetPlacement.from_manifest(raw_placement, category=category)
        return ResolvedAsset(
            path=picked,
            asset_id=str(picked_entry.get("asset_id", "")),
            category=category,
            placement=placement,
            metadata=dict(picked_entry),
        )

    def _load_catalog(self) -> dict[str, list[dict[str, Any]]]:
        manifest = self.storage.assets_root / "manifest.json"
        if not manifest.exists():
            return {}
        try:
            payload = json.loads(manifest.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        entries = payload.get("assets", [])
        by_category: dict[str, list[dict[str, Any]]] = {}
        for row in entries:
            if not isinstance(row, dict):
                continue
            category = str(row.get("category", ""))
            if not category:
                continue
            by_category.setdefault(category, []).append(row)
        return by_category

    def _migrate_legacy_metadata(self) -> None:
        changed = False
        for _, row in list(self.metadata.items()):
            if not isinstance(row, dict):
                continue
            if row.get("source_kind") in {"remote", "starter_pack"}:
                row["legacy_remote_preserved"] = True
                changed = True
        if changed:
            self.storage.save_asset_metadata(self.metadata)

    def _slot_for(self, category: str, key: str, theme: Optional[str]) -> dict[str, str]:
        if category == "plants":
            species, stage = (key.split("_", 1) + ["mature"])[:2]
            return {"species": species, "stage": stage}
        if category == "backgrounds":
            _, season, weather = (key.split("_", 2) + ["default", "breeze"])[0:3]
            configured_theme = theme or str(self.config.value("visual_theme", "verdant_dusk"))
            return {"season": season, "weather": weather, "theme": self.normalize_theme(configured_theme)}
        if category == "weather":
            weather = key.replace("weather_", "", 1)
            return {"weather": weather}
        if category == "decorations":
            return {"decoration_id": key.replace("decor_", "", 1)}
        if category == "overlays":
            configured_theme = theme or str(self.config.value("visual_theme", "verdant_dusk"))
            return {
                "overlay_id": key.replace("overlay_", "", 1),
                "theme": self.normalize_theme(configured_theme),
            }
        if category == "ui":
            return {"ui_id": key.replace("ui_", "", 1)}
        return {"key": key}

    def normalize_theme(self, theme: str) -> str:
        return self.THEME_ALIASES.get(str(theme), str(theme))

    def _select_candidates(self, category: str, slot: dict[str, str], quality_pref: str) -> list[dict[str, Any]]:
        entries = self._catalog.get(category, [])
        preferred: list[dict[str, Any]] = []
        for entry in entries:
            entry_slot = entry.get("slot", {})
            if all(str(entry_slot.get(k)) == str(v) for k, v in slot.items() if v):
                preferred.append(entry)

        if category == "backgrounds":
            preferred.extend(
                e
                for e in entries
                if e not in preferred
                and (e.get("slot", {}) or {}).get("season") == slot.get("season")
                and (e.get("slot", {}) or {}).get("weather") == "any"
                and (e.get("slot", {}) or {}).get("theme") == slot.get("theme")
            )

        if not preferred and category == "backgrounds":
            preferred = [
                e
                for e in entries
                if (e.get("slot", {}) or {}).get("season") == slot.get("season")
                and (e.get("slot", {}) or {}).get("weather") == "any"
                and (e.get("slot", {}) or {}).get("theme") == slot.get("theme")
            ]
        if not preferred and category == "backgrounds":
            preferred = [e for e in entries if (e.get("slot", {}) or {}).get("season") == slot.get("season") and (e.get("slot", {}) or {}).get("weather") == slot.get("weather")]
        if not preferred and category in {"plants", "weather", "decorations", "overlays", "ui"}:
            k = next(iter(slot.keys()))
            preferred = [e for e in entries if (e.get("slot", {}) or {}).get(k) == slot.get(k)]

        target_rank = self.QUALITY_ORDER.get(quality_pref, self.QUALITY_ORDER["balanced"])

        def quality_distance(entry: dict[str, Any]) -> tuple[int, int]:
            rank = self.QUALITY_ORDER.get(str(entry.get("quality_tier", "balanced")), self.QUALITY_ORDER["balanced"])
            if rank <= target_rank:
                return (0, target_rank - rank)
            return (1, rank - target_rank)

        preferred.sort(
            key=lambda e: (
                0 if e.get("style_family") == "storybook_gouache" else 1,
                (
                    0 if category == "plants" and "continuity_v4" in e.get("variants", [])
                    else 1 if category == "plants" and "continuity_v3" in e.get("variants", [])
                    else 2
                ),
                quality_distance(e),
                -float(e.get("quality_score", 0.0)),
                str(e.get("file", "")),
            )
        )
        return preferred

    def _pick_index(self, cache_key: str, key: str, candidates: list[Path], reroll: bool) -> int:
        if len(candidates) == 1:
            return 0
        existing = self.metadata.get(cache_key, {})
        if reroll:
            previous = int(existing.get("catalog_cycle_index", -1))
            return (previous + 1) % len(candidates)
        del key
        return 0

    def _manifest_dimensions_for(self, rel_path: str) -> dict[str, int]:
        for rows in self._catalog.values():
            for row in rows:
                if row.get("file") == rel_path:
                    return {"width": int(row.get("width", 0)), "height": int(row.get("height", 0))}
        return {"width": 0, "height": 0}

    def _quality_score_for(self, rel_path: str) -> float:
        for rows in self._catalog.values():
            for row in rows:
                if row.get("file") == rel_path:
                    return round(float(row.get("quality_score", 0.75)), 4)
        return 0.75

    def _valid_local_asset(self, path: Path, category: str) -> bool:
        try:
            resolved = path.resolve()
            addon_root = self.storage.addon_dir.resolve()
            resolved.relative_to(addon_root)
        except (OSError, ValueError):
            return False
        if not resolved.exists() or not resolved.is_file():
            return False
        suffix = resolved.suffix.lower()
        if suffix not in self.SUPPORTED_FORMATS:
            return False
        try:
            rel_path = str(resolved.relative_to(self.storage.addon_dir.resolve()))
        except ValueError:
            return False
        expected_format = self._manifest_format_for(rel_path)
        if expected_format and expected_format != suffix.lstrip("."):
            return False
        dims = self._manifest_dimensions_for(rel_path)
        min_w, min_h = self.MIN_DIMENSIONS.get(category, (1, 1))
        return int(dims.get("width", 0)) >= min_w and int(dims.get("height", 0)) >= min_h

    def _manifest_format_for(self, rel_path: str) -> str:
        for rows in self._catalog.values():
            for row in rows:
                if row.get("file") == rel_path:
                    return str(row.get("format", "")).lower()
        return ""

    def _placeholder_candidates(self) -> list[dict[str, Any]]:
        rel = str(self._ensure_placeholder_asset().relative_to(self.storage.addon_dir))
        return [{"file": rel, "width": 1200, "height": 675, "quality_tier": "performance", "quality_score": 0.5, "slot": {"fallback": "placeholder"}}]

    def _ensure_placeholder_asset(self) -> Path:
        bundled = self.storage.assets_root / "ui" / "fallback_placeholder.svg"
        if bundled.exists():
            return bundled
        placeholder = self.storage.cache_dir / "fallback_placeholder.svg"
        placeholder.parent.mkdir(parents=True, exist_ok=True)
        if not placeholder.exists():
            placeholder.write_text(
                "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1200 675'><rect width='1200' height='675' fill='#1a2733'/><text x='50%' y='50%' text-anchor='middle' fill='#e6f0ea' font-size='46'>Anki Garden</text></svg>",
                encoding="utf-8",
            )
        return placeholder

    def export_metadata_json(self) -> str:
        return json.dumps(self.metadata, indent=2)
