from __future__ import annotations

import json
import math
import time
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


def _surface_contract_is_valid(
    variants: dict[str, dict[str, Any]], geometry_version: int
) -> bool:
    """Fail closed when a registered surface no longer matches its artwork."""

    expected_bands = ("far", "far", "middle", "middle", "near", "near")
    expected_scales = (
        (0.84, 0.84, 0.92, 0.92, 1.0, 1.0)
        if geometry_version >= 6
        else (0.86, 0.86, 0.93, 0.93, 1.0, 1.0)
    )
    for variant in variants.values():
        surfaces = variant.get("surfaces", [])
        if not isinstance(surfaces, list) or len(surfaces) != 6:
            return False
        try:
            ordered = sorted(surfaces, key=lambda surface: int(surface["slot"]))
            if [int(surface["slot"]) for surface in ordered] != list(range(6)):
                return False
            anchors = [tuple(float(value) for value in surface["anchor"]) for surface in ordered]
            if any(len(anchor) != 2 for anchor in anchors):
                return False
            if any(not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0) for x, y in anchors):
                return False
            xs = sorted(x for x, _y in anchors)
            minimum_gap = 0.050 if geometry_version >= 6 else 0.099
            if min(right - left for left, right in zip(xs, xs[1:])) < minimum_gap:
                return False
            bands = tuple(str(surface["depth_band"]) for surface in ordered)
            if bands != expected_bands:
                return False
            scales = tuple(float(surface["depth_scale"]) for surface in ordered)
            if any(abs(actual - expected) > 0.015 for actual, expected in zip(scales, expected_scales)):
                return False
            if any(right + 1e-6 < left for left, right in zip(scales, scales[1:])):
                return False
            ys = [anchor[1] for anchor in anchors]
            if any(right + 1e-6 < left for left, right in zip(ys, ys[1:])):
                return False
            if not (ys[1] < ys[2] and ys[3] < ys[4]):
                return False
            surface_ids = [str(surface["surface_id"]) for surface in ordered]
            if any(not surface_id for surface_id in surface_ids) or len(set(surface_ids)) != 6:
                return False
            for index, (surface, (anchor_x, anchor_y)) in enumerate(zip(ordered, anchors)):
                allowed = set(str(value) for value in surface["allowed_base_types"])
                expected_allowed = (
                    {"direct_soil"}
                    if geometry_version >= 6
                    else {"pot", "dirt_mound"} if index < 2 else {"pot"}
                )
                expected_kind = "soil" if geometry_version >= 6 or index < 2 else "stone"
                if allowed != expected_allowed or surface.get("surface_kind") != expected_kind:
                    return False
                plane = tuple(float(value) for value in surface["contact_plane"])
                if len(plane) != 4:
                    return False
                plane_x, plane_y, plane_width, plane_height = plane
                if plane_width <= 0 or plane_height <= 0:
                    return False
                if not (
                    plane_x <= anchor_x <= plane_x + plane_width
                    and plane_y <= anchor_y <= plane_y + plane_height
                ):
                    return False
                support = [tuple(float(value) for value in point) for point in surface["support_line"]]
                if len(support) < 2 or any(len(point) != 2 for point in support):
                    return False
                support_x = (support[0][0] + support[-1][0]) / 2
                support_y = (support[0][1] + support[-1][1]) / 2
                tolerance = max(0.001, plane_width * 0.01)
                if abs(anchor_x - support_x) > tolerance or abs(anchor_y - support_y) > tolerance:
                    return False
        except (KeyError, TypeError, ValueError):
            return False
    return True


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
    shadow_plane: tuple[tuple[float, float], ...] = ()
    support_line: tuple[tuple[float, float], ...] = ()
    shadow_depth: str = "front"
    shadow_opacity: float = 0.34
    occlusion_id: str = ""
    surface_kind: str = "soil"
    allowed_base_types: tuple[str, ...] = ("direct_soil",)
    seating_depth: float = 0.0
    depth_band: str = "near"
    shadow_color: str = ""
    light_direction: tuple[float, float] = (-0.22, 0.18)

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

        def polygon(key: str, *, minimum: int = 3) -> tuple[tuple[float, float], ...]:
            raw = row.get(key)
            fallback = default.support_line if key == "support_line" else default.shadow_plane
            if not isinstance(raw, (list, tuple)) or len(raw) < minimum:
                return fallback
            points: list[tuple[float, float]] = []
            for raw_point in raw:
                if not isinstance(raw_point, (list, tuple)) or len(raw_point) != 2:
                    return fallback
                try:
                    points.append((
                        max(0.0, min(1.0, float(raw_point[0]))),
                        max(0.0, min(1.0, float(raw_point[1]))),
                    ))
                except (TypeError, ValueError):
                    return fallback
            return tuple(points)

        shadow_depth = str(row.get("shadow_depth", default.shadow_depth))
        if shadow_depth not in {"rear", "front"}:
            shadow_depth = default.shadow_depth
        depth_band = str(row.get("depth_band", default.depth_band))
        if depth_band not in {"far", "middle", "near"}:
            depth_band = default.depth_band
        surface_kind = str(row.get("surface_kind", default.surface_kind))
        if surface_kind not in {"stone", "soil"}:
            surface_kind = default.surface_kind
        raw_allowed = row.get("allowed_base_types", default.allowed_base_types)
        allowed = tuple(
            value for value in raw_allowed
            if value in {"pot", "dirt_mound", "direct_soil"}
        ) if isinstance(raw_allowed, (list, tuple)) else default.allowed_base_types
        if not allowed:
            allowed = default.allowed_base_types
        raw_direction = row.get("light_direction", default.light_direction)
        light_direction = default.light_direction
        if isinstance(raw_direction, (list, tuple)) and len(raw_direction) == 2:
            try:
                light_direction = (
                    max(-1.0, min(1.0, float(raw_direction[0]))),
                    max(-1.0, min(1.0, float(raw_direction[1]))),
                )
            except (TypeError, ValueError):
                light_direction = default.light_direction

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
            shadow_plane=polygon("shadow_plane"),
            support_line=polygon("support_line", minimum=2),
            shadow_depth=shadow_depth,
            shadow_opacity=number("shadow_opacity", default.shadow_opacity, 0.0, 1.0),
            occlusion_id=str(row.get("occlusion_id", default.occlusion_id)),
            surface_kind=surface_kind,
            allowed_base_types=allowed,
            seating_depth=number("seating_depth", default.seating_depth, 0.0, 0.02),
            depth_band=depth_band,
            shadow_color=str(row.get("shadow_color", default.shadow_color)),
            light_direction=light_direction,
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
            "shadow_plane": [list(point) for point in self.shadow_plane],
            "support_line": [list(point) for point in self.support_line],
            "shadow_depth": self.shadow_depth,
            "shadow_opacity": self.shadow_opacity,
            "occlusion_id": self.occlusion_id,
            "surface_kind": self.surface_kind,
            "allowed_base_types": list(self.allowed_base_types),
            "seating_depth": self.seating_depth,
            "depth_band": self.depth_band,
            "shadow_color": self.shadow_color,
            "light_direction": list(self.light_direction),
        }


@dataclass(frozen=True)
class SceneSurfaceProfile:
    """Registered background variants and the physical surfaces painted into them."""

    profile_id: str
    geometry_version: int
    theme: str
    light_direction: tuple[float, float]
    key_light_origins: dict[str, tuple[float, float]]
    appearance: dict[str, Any]
    variant_contract: dict[str, Any]
    variant_breakpoints: dict[str, float]
    variants: dict[str, dict[str, Any]]
    layer_contract: dict[str, Any]
    landmarks: tuple[dict[str, Any], ...]

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
            raw_layers = raw.get("occlusion_layers", {})
            occlusion_layers: dict[str, str] = {}
            if isinstance(raw_layers, dict):
                for layer_name in ("rear", "front"):
                    layer_file = str(raw_layers.get(layer_name, ""))
                    if layer_file and (
                        not layer_file.startswith("assets/") or ".." in Path(layer_file).parts
                    ):
                        layer_file = ""
                    if layer_file:
                        occlusion_layers[layer_name] = layer_file
            raw_masks = raw.get("surface_masks", {})
            surface_masks: dict[str, str] = {}
            if isinstance(raw_masks, dict):
                for surface_id, mask_file_value in raw_masks.items():
                    mask_file = str(mask_file_value)
                    if (
                        mask_file.startswith("assets/")
                        and ".." not in Path(mask_file).parts
                    ):
                        surface_masks[str(surface_id)] = mask_file
            raw_layer_masks = raw.get("layer_masks", {})
            layer_masks: dict[str, str] = {}
            if isinstance(raw_layer_masks, dict):
                for layer_name, mask_file_value in raw_layer_masks.items():
                    mask_file = str(mask_file_value)
                    if (
                        mask_file.startswith("assets/")
                        and ".." not in Path(mask_file).parts
                    ):
                        layer_masks[str(layer_name)] = mask_file
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
                "occlusion_layers": occlusion_layers,
                "surface_masks": surface_masks,
                "layer_masks": layer_masks,
                "width": max(1, int(number(raw.get("width"), 1, 1, 10000))),
                "height": max(1, int(number(raw.get("height"), 1, 1, 10000))),
                "focal_point": list(raw.get("focal_point", [0.5, 0.5])),
                "planting_zone": dict(raw.get("planting_zone", {})),
                "surfaces": [dict(surface) for surface in surfaces if isinstance(surface, dict)],
            }
        if set(variants) != {"4:3", "16:9", "home"}:
            return None
        geometry_version = max(1, int(number(row.get("geometry_version"), 1, 1, 99)))
        if geometry_version >= 5 and not _surface_contract_is_valid(variants, geometry_version):
            return None
        raw_origins = row.get("key_light_origins", {})
        key_light_origins: dict[str, tuple[float, float]] = {}
        for name, fallback in {"4:3": (0.86, 0.20), "16:9": (0.91, 0.18), "home": (0.91, 0.18)}.items():
            raw_origin = raw_origins.get(name) if isinstance(raw_origins, dict) else None
            if isinstance(raw_origin, (list, tuple)) and len(raw_origin) == 2:
                key_light_origins[name] = (
                    number(raw_origin[0], fallback[0], 0.0, 1.0),
                    number(raw_origin[1], fallback[1], 0.0, 1.0),
                )
            else:
                key_light_origins[name] = fallback
        raw_landmarks = row.get("landmarks", [])
        landmarks = tuple(
            dict(landmark)
            for landmark in raw_landmarks
            if isinstance(landmark, dict)
            and isinstance(landmark.get("action_id"), str)
            and landmark.get("action_id")
        ) if isinstance(raw_landmarks, list) else ()
        return cls(
            profile_id=profile_id,
            geometry_version=geometry_version,
            theme=str(row.get("theme", "verdant_twilight")),
            light_direction=light_direction,
            key_light_origins=key_light_origins,
            appearance=(
                dict(row.get("appearance", {}))
                if isinstance(row.get("appearance"), dict)
                else {}
            ),
            variant_contract=(
                dict(row.get("variant_contract", {}))
                if isinstance(row.get("variant_contract"), dict)
                else {}
            ),
            variant_breakpoints=normalized_breakpoints,
            variants=variants,
            layer_contract=(
                dict(row.get("layer_contract", {}))
                if isinstance(row.get("layer_contract"), dict)
                else {}
            ),
            landmarks=landmarks,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "geometry_version": self.geometry_version,
            "theme": self.theme,
            "light_direction": list(self.light_direction),
            "key_light_origins": {name: list(point) for name, point in self.key_light_origins.items()},
            "appearance": dict(self.appearance),
            "variant_contract": dict(self.variant_contract),
            "variant_breakpoints": dict(self.variant_breakpoints),
            "variants": {name: dict(value) for name, value in self.variants.items()},
            "layer_contract": dict(self.layer_contract),
            "landmarks": [dict(landmark) for landmark in self.landmarks],
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
        if base_type not in {"pot", "dirt_mound", "direct_soil", "legacy"}:
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
            "direct_soil": (0.42, 0.04),
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
    THEME_ALIASES: dict[str, str] = {}
    RELEASE_PLANT_STAGES = ("seed", "sprout", "young", "mature", "flowering", "rare")

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
        time_of_day: Optional[str] = None,
        reroll: bool = False,
        quality_preference: Optional[str] = None,
    ) -> Optional[Path]:
        resolved = self.resolve(
            category,
            key,
            query,
            provider_hint=provider_hint,
            theme=theme,
            time_of_day=time_of_day,
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
        time_of_day: Optional[str] = None,
        reroll: bool = False,
        quality_preference: Optional[str] = None,
    ) -> Optional[ResolvedAsset]:
        del query, provider_hint
        cache_key = f"{category}:{key}"
        slot = self._slot_for(category, key, theme, time_of_day=time_of_day)
        quality_pref = str(
            quality_preference
            or self.config.nested("assets", "quality_preference", default="balanced")
            or "balanced"
        )

        candidates = self._select_candidates(category, slot, quality_pref)
        if not candidates:
            return None

        valid_candidates = [
            entry for entry in candidates
            if self._valid_local_asset(self.storage.addon_dir / entry["file"], category)
        ]
        if not valid_candidates:
            return None

        idx = self._pick_index(cache_key, key, [self.storage.addon_dir / row["file"] for row in valid_candidates], reroll)
        picked_entry = valid_candidates[idx]
        picked = self.storage.addon_dir / picked_entry["file"]
        rel = str(picked.relative_to(self.storage.addon_dir))
        raw_placement = self._placement_for_entry(picked_entry, category)
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

    def _placement_for_entry(
        self,
        entry: dict[str, Any],
        category: str,
    ) -> dict[str, Any]:
        raw: dict[str, Any] = {}
        placement_ref = entry.get("placement_ref")
        if isinstance(placement_ref, str) and placement_ref:
            source = next(
                (
                    candidate
                    for candidate in self._catalog.get(category, [])
                    if candidate.get("asset_id") == placement_ref
                ),
                None,
            )
            if isinstance(source, dict) and isinstance(source.get("placement"), dict):
                raw = deepcopy(source["placement"])
        placement = entry.get("placement")
        if isinstance(placement, dict):
            raw.update(deepcopy(placement))
        surface_files = entry.get("surface_files")
        if category == "backgrounds" and isinstance(surface_files, dict):
            surface_profile = raw.get("surface_profile")
            variants = (
                surface_profile.get("variants")
                if isinstance(surface_profile, dict)
                else None
            )
            if isinstance(variants, dict):
                for variant_name, files in surface_files.items():
                    variant = variants.get(str(variant_name))
                    if not isinstance(variant, dict) or not isinstance(files, dict):
                        continue
                    for key in ("file", "occlusion_file"):
                        value = files.get(key)
                        if isinstance(value, str) and value:
                            variant[key] = value
                    layers = files.get("occlusion_layers")
                    if isinstance(layers, dict):
                        variant["occlusion_layers"] = deepcopy(layers)
        return raw

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

    def _slot_for(
        self,
        category: str,
        key: str,
        theme: Optional[str],
        *,
        time_of_day: Optional[str] = None,
    ) -> dict[str, str]:
        if category == "plants":
            normalized = str(key)
            for stage in self.RELEASE_PLANT_STAGES:
                suffix = f"_{stage}"
                if normalized.endswith(suffix):
                    return {"species": normalized[:-len(suffix)], "stage": stage}
            return {"species": normalized, "stage": "mature"}
        if category == "backgrounds":
            normalized = str(key)
            if normalized.startswith("bg_"):
                normalized = normalized[3:]
            if normalized.endswith("_any"):
                season = normalized[:-4] or "default"
                weather = "any"
            else:
                season, separator, weather = normalized.partition("_")
                if not separator:
                    weather = "any"
            configured_theme = theme or str(self.config.value("visual_theme", "verdant_twilight"))
            return {
                "season": season,
                "weather": weather,
                "time_of_day": str(time_of_day or "any"),
                "theme": self.normalize_theme(configured_theme),
            }
        if category == "weather":
            weather = key.replace("weather_", "", 1)
            return {"weather": weather}
        if category == "decorations":
            return {"decoration_id": key.replace("decor_", "", 1)}
        if category == "overlays":
            configured_theme = theme or str(self.config.value("visual_theme", "verdant_twilight"))
            return {
                "overlay_id": key.replace("overlay_", "", 1),
                "theme": self.normalize_theme(configured_theme),
            }
        if category == "ui":
            return {"ui_id": key.replace("ui_", "", 1)}
        return {"key": key}

    def normalize_theme(self, theme: str) -> str:
        return self.THEME_ALIASES.get(str(theme), str(theme))

    def release_ready_plant_species(
        self,
        *,
        theme: str = "verdant_twilight",
        geometry_version: int = 6,
    ) -> tuple[str, ...]:
        """Return complete plant lines approved for acquisition in this scene.

        Eligibility is intentionally stricter than normal asset resolution. It
        inspects exact manifest rows and never uses a legacy candidate or the
        placeholder fallback. A species is ready only when every growth stage
        has a valid, local, release-preferred V6 direct-soil asset.
        """
        normalized_theme = self.normalize_theme(theme)
        expected_version = max(1, int(geometry_version))
        if normalized_theme != "verdant_twilight" or expected_version != 6:
            return ()

        required_stages = set(self.RELEASE_PLANT_STAGES)
        ready_stages: dict[str, set[str]] = {}
        for entry in self._catalog.get("plants", []):
            if not isinstance(entry, dict) or entry.get("release_preferred") is not True:
                continue
            slot = entry.get("slot")
            if not isinstance(slot, dict):
                continue
            species = str(slot.get("species", ""))
            stage = str(slot.get("stage", ""))
            if not species or stage not in required_stages:
                continue
            variants = entry.get("variants", [])
            if not isinstance(variants, list) or f"continuity_v{expected_version}" not in variants:
                continue
            asset_id = str(entry.get("asset_id", ""))
            if f"_twilight_v{expected_version}" not in asset_id:
                continue
            if not self._valid_release_plant_placement(entry.get("placement")):
                continue
            relative_path = entry.get("file")
            if not isinstance(relative_path, str) or not relative_path.startswith(
                "assets/v6_storybook_gouache/plants/"
            ):
                continue
            if not self._valid_local_asset(self.storage.addon_dir / relative_path, "plants"):
                continue
            ready_stages.setdefault(species, set()).add(stage)

        return tuple(sorted(
            species for species, stages in ready_stages.items()
            if stages == required_stages
        ))

    @staticmethod
    def _valid_release_plant_placement(value: Any) -> bool:
        if not isinstance(value, dict):
            return False
        if value.get("base_type") != "direct_soil":
            return False
        if value.get("release_layout_candidate") is not True:
            return False
        if value.get("layer") != "plants":
            return False

        def normalized_numbers(key: str, size: int) -> tuple[float, ...] | None:
            raw = value.get(key)
            if not isinstance(raw, (list, tuple)) or len(raw) != size:
                return None
            try:
                parsed = tuple(float(item) for item in raw)
            except (TypeError, ValueError):
                return None
            if any(not math.isfinite(item) for item in parsed):
                return None
            return parsed

        ground_anchor = normalized_numbers("ground_anchor", 2)
        support_bounds = normalized_numbers("support_bounds", 4)
        if ground_anchor is None or support_bounds is None:
            return False
        if any(value < 0.0 or value > 1.0 for value in ground_anchor):
            return False
        left, top, width, height = support_bounds
        if left < 0.0 or top < 0.0 or width <= 0.0 or height <= 0.0:
            return False
        if left + width > 1.0 or top + height > 1.0:
            return False
        try:
            scene_scale = float(value.get("scene_scale_correction"))
            visual_scale = float(value.get("visual_scale_correction"))
        except (TypeError, ValueError):
            return False
        return (
            math.isfinite(scene_scale)
            and math.isfinite(visual_scale)
            and scene_scale > 0.0
            and visual_scale > 0.0
        )

    def _select_candidates(self, category: str, slot: dict[str, str], quality_pref: str) -> list[dict[str, Any]]:
        entries = self._catalog.get(category, [])
        preferred: list[dict[str, Any]] = []
        if category == "backgrounds":
            for entry in entries:
                entry_slot = entry.get("slot", {})
                if not isinstance(entry_slot, dict):
                    continue
                theme = str(entry_slot.get("theme", ""))
                if theme not in {str(slot.get("theme", "")), "any"}:
                    continue
                compatible = True
                for dimension in ("season", "weather", "time_of_day"):
                    offered = str(entry_slot.get(dimension, "any"))
                    requested = str(slot.get(dimension, "any"))
                    if offered not in {requested, "any"}:
                        compatible = False
                        break
                if compatible:
                    preferred.append(entry)
        else:
            for entry in entries:
                entry_slot = entry.get("slot", {})
                if all(str(entry_slot.get(k)) == str(v) for k, v in slot.items() if v):
                    preferred.append(entry)

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

        def background_distance(entry: dict[str, Any]) -> tuple[int, int]:
            if category != "backgrounds":
                return (0, 0)
            entry_slot = entry.get("slot", {}) or {}
            wildcard_count = sum(
                1
                for dimension in ("season", "weather", "time_of_day")
                if str(entry_slot.get(dimension, "any")) == "any"
            )
            return (
                wildcard_count,
                0 if bool(entry.get("release_preferred", False)) else 1,
            )

        preferred.sort(
            key=lambda e: (
                background_distance(e),
                0 if e.get("style_family") == "storybook_gouache" else 1,
                0 if category == "plants" and bool(e.get("release_preferred", False)) else 1,
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

    def export_metadata_json(self) -> str:
        return json.dumps(self.metadata, indent=2)
