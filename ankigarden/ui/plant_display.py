from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Any, Iterable

from ..asset_manager import DEFAULT_BED_ANCHORS, BedAnchor
from ..growth import StageProgress, stage_progress
from .state_contracts import CURRENT_ONBOARDING_VERSION
from .responsive import (
    COMPACT_MODE,
    adaptive_layout_mode,
    responsive_interpolate,
    responsive_progress,
)


NURTURED_MARKER_MAX_PLANT_DISTANCE_RATIO = 0.90
NURTURED_MARKER_MAX_GROUND_DELTA_RATIO = 1.50

SCENE_COMPACT_ASPECT = 4 / 3
SCENE_STANDARD_ASPECT = 16 / 9
SCENE_WIDE_ASPECT = 12 / 5
SCENE_COMPACT_BLEND_START = 520.0
SCENE_COMPACT_BLEND_END = 720.0
SCENE_WIDE_BLEND_START = 1200.0
SCENE_WIDE_BLEND_END = 1600.0
STATUS_OVERLAY_MIN_WIDTH = 520.0
STATUS_OVERLAY_HEIGHT = 68.0
GARDEN_CANVAS_WIDTH = 1240.0
GARDEN_CANVAS_HEIGHT = 840.0
GARDEN_CANVAS_ASPECT = GARDEN_CANVAS_WIDTH / GARDEN_CANVAS_HEIGHT

# Desktop plant details use one bounded component regardless of the selected
# bed.  Compact/mobile docking is an explicit viewport decision; it is never a
# collision fallback for an otherwise desktop scene.
PLANT_POPOVER_PREFERRED_WIDTH = 304.0
PLANT_POPOVER_MIN_WIDTH = 288.0
PLANT_POPOVER_MIN_HEIGHT = 1.0
PLANT_POPOVER_MAX_WIDTH = 320.0
PLANT_POPOVER_MAX_HEIGHT = 420.0
PLANT_POPOVER_MAX_SCENE_RATIO = 1.0
PLANT_POPOVER_EDGE_PADDING = 12.0
PLANT_POPOVER_CLEARANCE = 14.0
# Compatibility name for callers that still need an emergency-width check.
# Docking is based on actual measured fit, not a broad desktop breakpoint.
PLANT_POPOVER_COMPACT_BREAKPOINT = (
    PLANT_POPOVER_MIN_WIDTH + PLANT_POPOVER_EDGE_PADDING * 2.0
)

THEME_INTEGRATION_PROFILES: dict[str, dict[str, dict[str, Any]]] = {
    "verdant_twilight": {
        "rear": {"contrast": .97, "saturation": .94, "tint": "#E6A46F", "tint_alpha": .03},
        "front": {"contrast": .99, "saturation": .97, "tint": "#E6A46F", "tint_alpha": .015},
    },
    "verdant_dusk": {
        "rear": {"contrast": .94, "saturation": .92, "tint": "#C58A55", "tint_alpha": .04},
        "front": {"contrast": .98, "saturation": .97, "tint": "#C58A55", "tint_alpha": .02},
    },
    "verdant_dawn": {
        "rear": {"contrast": .96, "saturation": .94, "tint": "#E6B66E", "tint_alpha": .03},
        "front": {"contrast": .99, "saturation": .98, "tint": "#E6B66E", "tint_alpha": .015},
    },
    "moonlit_study": {
        "rear": {"contrast": .92, "saturation": .90, "tint": "#7183A6", "tint_alpha": .06},
        "front": {"contrast": .96, "saturation": .95, "tint": "#7183A6", "tint_alpha": .03},
    },
}


def theme_integration_profile(
    theme: str,
    depth_band: str,
    x_ratio: float = 0.5,
    y_ratio: float = 0.5,
    key_light_origin: tuple[float, float] | None = None,
    appearance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return shared, bounded plant grading for one scene position."""
    profiles = THEME_INTEGRATION_PROFILES.get(str(theme), THEME_INTEGRATION_PROFILES["verdant_twilight"])
    result = dict(profiles["rear" if depth_band == "rear" else "front"])
    if str(theme) in {"verdant_dusk", "verdant_twilight"}:
        spec = appearance if isinstance(appearance, dict) else {}
        prefix = "rear" if depth_band == "rear" else "front"
        lamp_x, lamp_y = key_light_origin or (0.91, 0.18)
        distance = ((float(x_ratio) - lamp_x) ** 2 + (float(y_ratio) - lamp_y) ** 2) ** 0.5
        light_amount = max(0.0, min(1.0, 1.0 - distance / 1.02))
        result.update({
            "contrast": _number(spec.get(f"{prefix}_contrast"), 0.97 if depth_band == "rear" else 0.99, 0.88, 1.08),
            "saturation": _number(spec.get(f"{prefix}_saturation"), 0.94 if depth_band == "rear" else 0.97, 0.82, 1.05),
            "exposure": _number(spec.get(f"{prefix}_exposure"), -0.043 if depth_band == "rear" else -0.025, -0.12, 0.12)
            + 0.065 * light_amount,
            "tint": str(spec.get("key_tint", "#C58A55")),
            "tint_alpha": _number(spec.get("base_tint_alpha"), 0.012, 0.0, 0.08)
            + _number(spec.get("distance_tint_alpha"), 0.032, 0.0, 0.08) * light_amount,
            "light_amount": light_amount,
            "key_strength": _number(spec.get("base_key_strength"), 0.018, 0.0, 0.08)
            + _number(spec.get("distance_key_strength"), 0.035, 0.0, 0.08) * light_amount,
            "base_ao": _number(spec.get(f"{prefix}_base_ao"), 0.045 if depth_band == "rear" else 0.035, 0.0, 0.10),
        })
    else:
        result.update({"exposure": 0.0, "light_amount": 0.5, "key_strength": 0.0, "base_ao": 0.0})
    return result

def settings_layout_is_compact(width: int) -> bool:
    """Compatibility wrapper for the shared content-measured Settings split."""

    return adaptive_layout_mode(
        width,
        (280, 360),
        spacing=20,
    ) == COMPACT_MODE


def scene_preferred_aspect(width: float) -> float:
    """Return a continuous, clamped scene aspect for the available width."""

    safe_width = max(1.0, float(width))
    compact_progress = responsive_progress(
        safe_width,
        SCENE_COMPACT_BLEND_START,
        SCENE_COMPACT_BLEND_END,
    )
    aspect = SCENE_COMPACT_ASPECT + (
        SCENE_STANDARD_ASPECT - SCENE_COMPACT_ASPECT
    ) * compact_progress
    wide_progress = responsive_progress(
        safe_width,
        SCENE_WIDE_BLEND_START,
        SCENE_WIDE_BLEND_END,
    )
    aspect += (SCENE_WIDE_ASPECT - SCENE_STANDARD_ASPECT) * wide_progress
    return max(SCENE_COMPACT_ASPECT, min(SCENE_WIDE_ASPECT, aspect))


def scene_height_for_width(
    width: float,
    *,
    minimum: int = 250,
    maximum: int = 800,
) -> int:
    """Return the stable Qt height hint for a scene of ``width`` pixels."""

    safe_width = max(1.0, float(width))
    lower = max(1, int(minimum))
    upper = max(lower, int(maximum))
    preferred = int(round(safe_width / scene_preferred_aspect(safe_width)))
    return max(lower, min(upper, preferred))


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    def contains(self, x: float, y: float) -> bool:
        return self.x <= x <= self.right and self.y <= y <= self.bottom

    def intersects(self, other: "Rect") -> bool:
        return not (self.right <= other.x or other.right <= self.x or self.bottom <= other.y or other.bottom <= self.y)

    def expanded(self, x_pad: float, y_pad: float | None = None) -> "Rect":
        y_pad = x_pad if y_pad is None else y_pad
        return Rect(self.x - x_pad, self.y - y_pad, self.width + 2 * x_pad, self.height + 2 * y_pad)

    @property
    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)

    def intersection_area(self, other: "Rect") -> float:
        width = max(0.0, min(self.right, other.right) - max(self.x, other.x))
        height = max(0.0, min(self.bottom, other.bottom) - max(self.y, other.y))
        return width * height

    def clipped_to(self, other: "Rect") -> "Rect":
        left = max(self.x, other.x)
        top = max(self.y, other.y)
        right = min(self.right, other.right)
        bottom = min(self.bottom, other.bottom)
        return Rect(
            left,
            top,
            max(0.0, right - left),
            max(0.0, bottom - top),
        )


def contained_canvas_rect(
    width: float,
    height: float,
    *,
    aspect: float = GARDEN_CANVAS_ASPECT,
    origin_x: float = 0.0,
    origin_y: float = 0.0,
) -> Rect:
    """Center one complete design canvas without stretching or cropping it."""

    safe_width = max(1.0, float(width))
    safe_height = max(1.0, float(height))
    safe_aspect = max(0.01, float(aspect))
    available_aspect = safe_width / safe_height
    if available_aspect > safe_aspect:
        draw_height = safe_height
        draw_width = draw_height * safe_aspect
    else:
        draw_width = safe_width
        draw_height = draw_width / safe_aspect
    return Rect(
        float(origin_x) + (safe_width - draw_width) / 2.0,
        float(origin_y) + (safe_height - draw_height) / 2.0,
        draw_width,
        draw_height,
    )


def _offset_rect(rect: Rect, x_offset: float, y_offset: float) -> Rect:
    return Rect(
        rect.x + float(x_offset),
        rect.y + float(y_offset),
        rect.width,
        rect.height,
    )


def status_overlay_rect(
    width: float,
    *,
    protected: bool = True,
    surface_context: str = "dashboard",
) -> Rect | None:
    """Return the one visible status-panel geometry shared by layout and paint."""

    safe_width = max(1.0, float(width))
    if (
        not protected
        or str(surface_context) == "home"
        or safe_width < STATUS_OVERLAY_MIN_WIDTH
    ):
        return None
    return Rect(
        16.0,
        14.0,
        min(430.0, max(1.0, safe_width - 32.0)),
        STATUS_OVERLAY_HEIGHT,
    )


def nurtured_marker_rect(
    canvas_width: float,
    canvas_height: float,
    visible: Rect,
    plant_draw_width: float,
    *,
    margin: float = 6.0,
    gap: float = 6.0,
) -> Rect:
    """Place the Nurturing marker beside a plant without changing plant geometry."""

    safe_width = max(1.0, float(canvas_width))
    safe_height = max(1.0, float(canvas_height))
    maximum_fit = max(1.0, min(safe_width, safe_height) - margin * 2)
    # The label is part of the illustration, so give it enough scene area to
    # remain recognizable in the full Garden and compact preview renderers.
    size = min(maximum_fit, max(78.0, min(112.0, float(plant_draw_width) * 0.52)))
    preferred_y = visible.y + min(12.0, max(0.0, visible.height * 0.08))
    preferred_y = max(margin, min(safe_height - margin - size, preferred_y))
    centered_x = visible.x + (visible.width - size) / 2

    candidates = (
        Rect(visible.right + gap, preferred_y, size, size),
        Rect(visible.x - gap - size, preferred_y, size, size),
        Rect(centered_x, visible.y - gap - size, size, size),
        Rect(centered_x, visible.bottom + gap, size, size),
    )
    for candidate in candidates:
        within_canvas = (
            candidate.x >= margin
            and candidate.y >= margin
            and candidate.right <= safe_width - margin
            and candidate.bottom <= safe_height - margin
        )
        if within_canvas and not candidate.intersects(visible):
            return candidate

    clamped = tuple(
        Rect(
            max(margin, min(safe_width - margin - size, candidate.x)),
            max(margin, min(safe_height - margin - size, candidate.y)),
            size,
            size,
        )
        for candidate in candidates
    )
    return min(clamped, key=lambda candidate: candidate.intersection_area(visible))


def nurtured_badge_rect(
    canvas_width: float,
    canvas_height: float,
    visible: Rect,
    plant_draw_width: float,
    *,
    margin: float = 6.0,
) -> Rect:
    """Place the original compact nurtured badge beside a plant."""

    safe_width = max(1.0, float(canvas_width))
    safe_height = max(1.0, float(canvas_height))
    radius = max(11.0, min(13.0, float(plant_draw_width) * 0.055))
    right_x = visible.right + radius + 4.0
    left_x = visible.x - radius - 4.0
    center_x = right_x if right_x + radius <= safe_width - margin else left_x
    center_x = max(margin + radius, min(safe_width - margin - radius, center_x))
    center_y = max(radius + margin, visible.y + radius * 0.35)
    center_y = min(safe_height - margin - radius, center_y)
    return Rect(
        center_x - radius,
        center_y - radius,
        radius * 2,
        radius * 2,
    )


@dataclass(frozen=True)
class PlantLighting:
    contrast: float = 1.0
    saturation: float = 1.0
    exposure: float = 0.0
    tint: str = "#000000"
    tint_alpha: float = 0.0
    light_amount: float = 0.5
    key_strength: float = 0.0
    base_ao: float = 0.0


@dataclass(frozen=True)
class GroundingPlan:
    """Resolved physical integration shared by live and review renderers."""

    contact_shadow: Rect = Rect(0, 0, 0, 0)
    cast_shadow: Rect = Rect(0, 0, 0, 0)
    shadow_plane: tuple[tuple[float, float], ...] = ()
    shadow_direction: tuple[float, float] = (-0.22, 0.18)
    contact_opacity: float = 0.34
    cast_opacity: float = 0.136
    row: str = "front"
    surface_kind: str = "soil"
    support_line: tuple[tuple[float, float], ...] = ()
    contact_color: str = "#1c1b19"
    cast_color: str = "#23201d"
    lighting: PlantLighting = PlantLighting()


@dataclass(frozen=True)
class PlantPlacement:
    slot_index: int
    draw: Rect
    visible: Rect
    hit: Rect
    footprint: Rect
    depth: float
    smart_card_anchor: Rect
    scale: float
    bed_footprint: Rect
    label_anchor: tuple[float, float]
    z_depth: float
    base_rect: Rect = Rect(0, 0, 0, 0)
    support_rect: Rect = Rect(0, 0, 0, 0)
    foliage_rect: Rect = Rect(0, 0, 0, 0)
    control_rect: Rect = Rect(0, 0, 0, 0)
    effective_scale: float = 1.0
    ideal_physical_scale: float = 1.0
    depth_scale: float = 1.0
    vessel_class_multiplier: float = 1.0
    asset_correction: float = 1.0
    fit_scale: float = 1.0
    target_error: float = 0.0
    protected_region_intersections: tuple[str, ...] = ()
    adjustment_reason: str = "preferred-anchor"
    validation_warnings: tuple[str, ...] = ()
    surface_id: str = ""
    contact_plane: Rect = Rect(0, 0, 0, 0)
    shadow_depth: str = "front"
    shadow_opacity: float = 0.34
    occlusion_id: str = ""
    slot_envelope: Rect = Rect(0, 0, 0, 0)
    ground_anchor: tuple[float, float] = (0.5, 1.0)
    layout_family: str = "standard"
    visual_scale_correction: float = 1.0
    release_layout_candidate: bool = False
    grounding: GroundingPlan = GroundingPlan()
    surface_kind: str = "soil"
    allowed_base_types: tuple[str, ...] = ("direct_soil",)
    depth_band: str = "near"


def translated_plant_placement(
    placement: PlantPlacement,
    x_offset: float,
    y_offset: float,
) -> PlantPlacement:
    """Move every visual and interaction coordinate by one canvas offset."""

    dx = float(x_offset)
    dy = float(y_offset)
    grounding = replace(
        placement.grounding,
        contact_shadow=_offset_rect(placement.grounding.contact_shadow, dx, dy),
        cast_shadow=_offset_rect(placement.grounding.cast_shadow, dx, dy),
        shadow_plane=tuple((x + dx, y + dy) for x, y in placement.grounding.shadow_plane),
        support_line=tuple((x + dx, y + dy) for x, y in placement.grounding.support_line),
    )
    rect_fields = (
        "draw",
        "visible",
        "hit",
        "footprint",
        "smart_card_anchor",
        "bed_footprint",
        "base_rect",
        "support_rect",
        "foliage_rect",
        "control_rect",
        "contact_plane",
        "slot_envelope",
    )
    translated = {
        field: _offset_rect(getattr(placement, field), dx, dy)
        for field in rect_fields
    }
    return replace(
        placement,
        **translated,
        depth=placement.depth + dy,
        z_depth=placement.z_depth + dy,
        label_anchor=(
            placement.label_anchor[0] + dx,
            placement.label_anchor[1] + dy,
        ),
        ground_anchor=(
            placement.ground_anchor[0] + dx,
            placement.ground_anchor[1] + dy,
        ),
        grounding=grounding,
    )


@dataclass(frozen=True)
class NurturedMarkerPlacement:
    """Resolved watering-can geometry shared by native and Home renderers."""

    rect: Rect
    pulse_bounds: Rect
    planter_rect: Rect
    side: str
    asset_key: str
    orientation: str
    used_fallback: bool = False
    contact_shadow: Rect = Rect(0, 0, 0, 0)
    perspective_scale: float = 1.0


def _nurtured_marker_perspective_scale(layout: PlantPlacement) -> float:
    """Return the release row scale for the watering-can accessory."""

    return {
        "far": 0.78,
        "rear": 0.78,
        "middle": 0.90,
        "near": 1.00,
        "front": 1.00,
    }.get(str(layout.depth_band), 1.00)


def _nurtured_marker_contact_shadow(
    marker: Rect,
    canvas_width: float,
    canvas_height: float,
    margin: float,
) -> Rect:
    """Resolve a subtle, bounded ground-contact shadow below the can."""

    shadow_width = marker.width * 0.68
    shadow_height = max(3.0, marker.height * 0.12)
    shadow_x = marker.x + (marker.width - shadow_width) / 2.0
    shadow_y = marker.y + marker.height * 0.87
    safe_right = max(margin, float(canvas_width) - margin)
    safe_bottom = max(margin, float(canvas_height) - margin)
    return Rect(
        max(margin, min(shadow_x, safe_right - shadow_width)),
        max(margin, min(shadow_y, safe_bottom - shadow_height)),
        min(shadow_width, max(1.0, safe_right - margin)),
        min(shadow_height, max(1.0, safe_bottom - margin)),
    )


@dataclass(frozen=True)
class PopoverPlacement:
    rectangle: Rect
    chosen_side: str
    connector_start: tuple[float, float]
    connector_end: tuple[float, float]
    maximum_content_height: float
    avoided_beds: tuple[int, ...] = ()
    docked: bool = False


@dataclass(frozen=True)
class SceneBedGeometry:
    bed_id: int
    sprite_anchor: tuple[float, float]
    ground_anchor: tuple[float, float]
    visible_region: Rect
    selection_region: Rect
    popover_anchor: tuple[float, float]
    popover_candidates: tuple[str, ...]
    watering_can_accessory_lanes: tuple[Rect, ...]
    move_target: Rect
    hotspot: Rect
    safe_bounds: Rect
    slot_envelope: Rect
    depth: float
    foreground_occlusion: str
    plant_bounds: Rect
    planter_bounds: Rect
    planter_exclusions: tuple[Rect, ...]


@dataclass(frozen=True)
class SceneGeometryLayout:
    """One logical-coordinate authority for every scene interaction layer."""

    scene_bounds: Rect
    safe_bounds: Rect
    beds: tuple[SceneBedGeometry, ...]
    device_pixel_ratio: float = 1.0

    @classmethod
    def from_placements(
        cls,
        width: float,
        height: float,
        placements: Iterable[PlantPlacement],
        *,
        device_pixel_ratio: float = 1.0,
        margin: float = 12.0,
        planter_family: dict[str, Any] | None = None,
        scene_bounds: Rect | None = None,
    ) -> "SceneGeometryLayout":
        safe_width = max(1.0, float(width))
        safe_height = max(1.0, float(height))
        scene = (
            scene_bounds.clipped_to(Rect(0.0, 0.0, safe_width, safe_height))
            if isinstance(scene_bounds, Rect)
            else Rect(0.0, 0.0, safe_width, safe_height)
        )
        inset = max(
            0.0,
            min(float(margin), scene.width / 4, scene.height / 4),
        )
        safe = Rect(
            scene.x + inset,
            scene.y + inset,
            max(1.0, scene.width - inset * 2),
            max(1.0, scene.height - inset * 2),
        )

        def contained_target(rectangle: Rect, bounds: Rect) -> Rect:
            """Translate a target inside its bounds before reducing its size."""

            target_width = min(rectangle.width, bounds.width)
            target_height = min(rectangle.height, bounds.height)
            return Rect(
                max(bounds.x, min(rectangle.x, bounds.right - target_width)),
                max(bounds.y, min(rectangle.y, bounds.bottom - target_height)),
                target_width,
                target_height,
            )

        beds: list[SceneBedGeometry] = []
        for placement in sorted(placements, key=lambda row: row.slot_index):
            envelope = (
                placement.slot_envelope
                if placement.slot_envelope.area > 0
                else safe
            ).clipped_to(safe)
            visible = placement.visible.clipped_to(safe)
            selection = placement.visible.expanded(5.0, 4.0)
            minimum_width = max(44.0, selection.width)
            minimum_height = max(44.0, selection.height)
            selection = contained_target(Rect(
                selection.x - (minimum_width - selection.width) / 2,
                selection.y - (minimum_height - selection.height) / 2,
                minimum_width,
                minimum_height,
            ), envelope.clipped_to(safe))
            bed_target = placement.bed_footprint.expanded(8.0, 6.0)
            target_width = max(44.0, bed_target.width)
            target_height = max(44.0, bed_target.height)
            bed_target = contained_target(Rect(
                bed_target.x - (target_width - bed_target.width) / 2,
                bed_target.y - (target_height - bed_target.height) / 2,
                target_width,
                target_height,
            ), envelope.clipped_to(safe))
            planter = planter_draw_rect(placement, planter_family)
            planter_exclusions = tuple(
                region.clipped_to(scene)
                for region in planter_accessory_exclusions(
                    placement,
                    planter_family,
                )
                if region.clipped_to(scene).area > 0
            )
            marker_scale = _nurtured_marker_perspective_scale(placement)
            marker_size = max(
                44.0,
                min(88.0, max(68.0, planter.width * 0.45) * marker_scale),
            )
            lane_width = marker_size + 18.0
            vertical_sweep = marker_size * 0.85
            lane_height = marker_size + vertical_sweep * 2.0 + 16.0
            lane_y = (
                placement.ground_anchor[1]
                - marker_size * 0.916
                - vertical_sweep
                - 8.0
            )
            blocked_left = min(
                (placement.visible.x, *(region.x for region in planter_exclusions)),
            )
            blocked_right = max(
                (placement.visible.right, *(region.right for region in planter_exclusions)),
            )

            def lane(side: str) -> Rect:
                raw_x = (
                    blocked_left - lane_width - 4.0
                    if side == "left"
                    else blocked_right + 4.0
                )
                return Rect(
                    max(safe.x, min(raw_x, safe.right - lane_width)),
                    max(safe.y, min(lane_y, safe.bottom - lane_height)),
                    min(lane_width, safe.width),
                    min(lane_height, safe.height),
                ).clipped_to(safe)

            preferred = "left" if int(placement.slot_index) % 2 == 0 else "right"
            alternate = "right" if preferred == "left" else "left"
            center_x = visible.x + visible.width / 2
            anchor_y = visible.y + min(visible.height * 0.42, 80.0)
            horizontal_preference = (
                "left" if center_x >= safe.x + safe.width / 2 else "right"
            )
            vertical_preference = (
                "above" if anchor_y >= safe.y + safe.height / 2 else "below"
            )
            opposite_horizontal = (
                "right" if horizontal_preference == "left" else "left"
            )
            opposite_vertical = (
                "below" if vertical_preference == "above" else "above"
            )
            beds.append(SceneBedGeometry(
                bed_id=int(placement.slot_index),
                sprite_anchor=placement.ground_anchor,
                ground_anchor=placement.ground_anchor,
                visible_region=visible,
                selection_region=selection,
                popover_anchor=(center_x, anchor_y),
                popover_candidates=(
                    horizontal_preference,
                    vertical_preference,
                    opposite_horizontal,
                    opposite_vertical,
                    "bottom-docked",
                    "top-docked",
                ),
                watering_can_accessory_lanes=(lane(preferred), lane(alternate)),
                move_target=bed_target,
                hotspot=bed_target,
                safe_bounds=safe,
                slot_envelope=envelope,
                depth=float(placement.z_depth),
                foreground_occlusion=str(placement.occlusion_id or placement.depth_band),
                plant_bounds=placement.draw.clipped_to(scene),
                planter_bounds=planter.clipped_to(scene),
                planter_exclusions=planter_exclusions,
            ))
        return cls(
            scene_bounds=scene,
            safe_bounds=safe,
            beds=tuple(beds),
            device_pixel_ratio=max(1.0, float(device_pixel_ratio or 1.0)),
        )

    def bed(self, bed_id: int) -> SceneBedGeometry | None:
        return next((bed for bed in self.beds if bed.bed_id == int(bed_id)), None)

    def resolve_watering_can(
        self,
        bed_id: int,
        placement: PlantPlacement,
        *,
        obstacles: Iterable[Rect] = (),
        protected_regions: Iterable[Rect] = (),
    ) -> NurturedMarkerPlacement:
        """Resolve one can while keeping opaque planter and soil art clear."""

        bed = self.bed(bed_id)
        if bed is None:
            raise ValueError(f"unknown garden bed {bed_id}")
        planter_exclusions = tuple(
            exclusion
            for candidate in self.beds
            for exclusion in candidate.planter_exclusions
        )
        offset_x = self.scene_bounds.x
        offset_y = self.scene_bounds.y
        local_layout = translated_plant_placement(
            placement,
            -offset_x,
            -offset_y,
        )
        local_result = nurtured_marker_placement(
            self.scene_bounds.width,
            self.scene_bounds.height,
            local_layout,
            planter_rect=_offset_rect(
                bed.planter_bounds,
                -offset_x,
                -offset_y,
            ),
            obstacles=tuple(
                _offset_rect(obstacle, -offset_x, -offset_y)
                for obstacle in obstacles
            ),
            protected_regions=tuple(
                _offset_rect(region, -offset_x, -offset_y)
                for region in (*tuple(protected_regions), *planter_exclusions)
            ),
            accessory_lanes=tuple(
                _offset_rect(lane, -offset_x, -offset_y)
                for lane in bed.watering_can_accessory_lanes
            ),
        )
        return replace(
            local_result,
            rect=_offset_rect(local_result.rect, offset_x, offset_y),
            pulse_bounds=_offset_rect(
                local_result.pulse_bounds,
                offset_x,
                offset_y,
            ),
            planter_rect=_offset_rect(
                local_result.planter_rect,
                offset_x,
                offset_y,
            ),
            contact_shadow=_offset_rect(
                local_result.contact_shadow,
                offset_x,
                offset_y,
            ),
        )

    def resolve_popover(
        self,
        bed_id: int,
        preferred_size: tuple[float, float],
        minimum_size: tuple[float, float],
        extra_obstacles: Iterable[Rect] = (),
        *,
        selected_accessory_regions: Iterable[Rect] = (),
        allow_docked: bool | None = None,
    ) -> PopoverPlacement:
        """Place one bounded plant panel clear of its selected plant.

        Desktop scenes always resolve an anchored right/left/above/below
        placement.  A docked panel is available only to an explicitly compact
        viewport, never because a particular bed has less anchor space.
        """

        selected = self.bed(bed_id)
        if selected is None:
            raise ValueError(f"unknown garden bed {bed_id}")
        popover_inset = min(
            PLANT_POPOVER_EDGE_PADDING,
            self.scene_bounds.width / 4.0,
            self.scene_bounds.height / 4.0,
        )
        popover_bounds = Rect(
            self.scene_bounds.x + popover_inset,
            self.scene_bounds.y + popover_inset,
            max(1.0, self.scene_bounds.width - popover_inset * 2.0),
            max(1.0, self.scene_bounds.height - popover_inset * 2.0),
        )
        requested_minimum_height = max(1.0, float(minimum_size[1]))
        compact_viewport = bool(
            popover_bounds.width < PLANT_POPOVER_MIN_WIDTH
            or popover_bounds.height < requested_minimum_height
        )
        docking_allowed = (
            compact_viewport if allow_docked is None else bool(allow_docked)
        )
        if docking_allowed:
            minimum_width = min(
                popover_bounds.width,
                max(1.0, float(minimum_size[0])),
            )
            preferred_width = min(
                popover_bounds.width,
                PLANT_POPOVER_MAX_WIDTH,
                max(minimum_width, float(preferred_size[0])),
            )
        else:
            desktop_width_cap = min(
                popover_bounds.width,
                PLANT_POPOVER_MAX_WIDTH,
                self.scene_bounds.width * PLANT_POPOVER_MAX_SCENE_RATIO,
            )
            preferred_width = min(
                desktop_width_cap,
                max(
                    PLANT_POPOVER_MIN_WIDTH,
                    float(preferred_size[0]),
                ),
            )
            minimum_width = min(
                preferred_width,
                max(
                    PLANT_POPOVER_MIN_WIDTH,
                    float(minimum_size[0]),
                ),
            )
        minimum_height = min(
            popover_bounds.height,
            PLANT_POPOVER_MAX_HEIGHT,
            max(1.0, float(minimum_size[1])),
        )
        preferred_height = min(
            popover_bounds.height,
            PLANT_POPOVER_MAX_HEIGHT,
            max(minimum_height, float(preferred_size[1])),
        )
        if not docking_allowed:
            # The caller has already measured the real Qt content. Avoid
            # solving a collision by clipping that content to a shorter card.
            minimum_height = preferred_height
        sizes = [(preferred_width, preferred_height)]
        if (
            abs(preferred_width - minimum_width) > 1e-6
            or abs(preferred_height - minimum_height) > 1e-6
        ):
            sizes.append((minimum_width, minimum_height))
        gap = PLANT_POPOVER_CLEARANCE
        anchor_x, anchor_y = selected.popover_anchor

        def clamp(rect: Rect) -> Rect:
            return Rect(
                max(popover_bounds.x, min(rect.x, popover_bounds.right - rect.width)),
                max(popover_bounds.y, min(rect.y, popover_bounds.bottom - rect.height)),
                rect.width,
                rect.height,
            )

        selected_parts = tuple(
            part
            for part in (
                selected.selection_region,
                # ``plant_bounds`` is the complete transparent asset canvas.
                # Anchor clearance follows painted pixels and the outlined
                # bed so empty image padding cannot force an overlapping
                # fallback for small seed/sprout artwork.
                selected.visible_region,
                selected.planter_bounds,
                *tuple(selected_accessory_regions),
            )
            if isinstance(part, Rect) and part.area > 0
        )
        selected_target = Rect(
            min(part.x for part in selected_parts),
            min(part.y for part in selected_parts),
            max(part.right for part in selected_parts)
            - min(part.x for part in selected_parts),
            max(part.bottom for part in selected_parts)
            - min(part.y for part in selected_parts),
        )

        def candidate(side: str, width: float, height: float) -> Rect:
            if side == "right":
                return Rect(
                    selected_target.right + gap,
                    selected_target.y,
                    width,
                    height,
                )
            if side == "left":
                return Rect(
                    selected_target.x - gap - width,
                    selected_target.y,
                    width,
                    height,
                )
            if side == "above":
                return Rect(
                    anchor_x - width / 2,
                    selected_target.y - gap - height,
                    width,
                    height,
                )
            return Rect(
                anchor_x - width / 2,
                selected_target.bottom + gap,
                width,
                height,
            )

        # Floating-UI-style deterministic order: right-start, left-start,
        # above, then below.  Clamping supplies the shift behavior while the
        # later candidates provide flip behavior.
        sides = ("right", "left", "above", "below")
        # Fourteen logical pixels remain clear around the plant artwork, planter,
        # and selected-state accessory as one protected target.
        selected_obstacle = selected_target.expanded(
            PLANT_POPOVER_CLEARANCE
        )
        soft = {
            bed.bed_id: bed.selection_region.expanded(5.0)
            for bed in self.beds
            if bed.bed_id != selected.bed_id
        }
        hard = [
            obstacle
            for obstacle in extra_obstacles
            if isinstance(obstacle, Rect) and obstacle.area > 0
        ]

        scored: list[tuple[tuple[float, ...], str, Rect]] = []
        preferred_area = max(1.0, preferred_width * preferred_height)
        if not compact_viewport:
            for side_index, side in enumerate(sides):
                for size_index, (width, height) in enumerate(sizes):
                    raw = candidate(side, width, height)
                    rectangle = clamp(raw)
                    if rectangle.intersects(selected_obstacle):
                        continue
                    if any(rectangle.intersects(obstacle) for obstacle in hard):
                        continue
                    soft_overlap = sum(
                        rectangle.intersection_area(obstacle)
                        for obstacle in soft.values()
                    )
                    shrink_ratio = 1.0 - rectangle.area / preferred_area
                    clamp_shift = abs(rectangle.x - raw.x) + abs(rectangle.y - raw.y)
                    scored.append((
                        (
                            max(0.0, shrink_ratio),
                            soft_overlap,
                            float(side_index),
                            float(size_index),
                            clamp_shift,
                        ),
                        side,
                        rectangle,
                    ))

        chosen_side = ""
        chosen: Rect | None = None
        if scored:
            _, chosen_side, chosen = min(scored, key=lambda row: row[0])

        docked = False
        if chosen is None and docking_allowed:
            docked = True
            dock_width = min(PLANT_POPOVER_MAX_WIDTH, popover_bounds.width)
            dock_x = popover_bounds.x + (popover_bounds.width - dock_width) / 2.0
            dock_height = min(
                preferred_height,
                max(minimum_height, popover_bounds.height * 0.44),
            )
            dock_candidates = (
                (
                    "bottom-docked",
                    Rect(
                        dock_x,
                        popover_bounds.bottom - dock_height,
                        dock_width,
                        dock_height,
                    ),
                ),
                (
                    "top-docked",
                    Rect(
                        dock_x,
                        popover_bounds.y,
                        dock_width,
                        dock_height,
                    ),
                ),
            )
            viable_docks = [
                (side, rectangle)
                for side, rectangle in dock_candidates
                if not rectangle.intersects(selected_obstacle)
                and not any(rectangle.intersects(obstacle) for obstacle in hard)
            ]
            if viable_docks:
                chosen_side, chosen = min(
                    viable_docks,
                    key=lambda row: sum(
                        row[1].intersection_area(obstacle)
                        for obstacle in soft.values()
                    ),
                )
            else:
                # Unsupported viewports still receive a bounded panel. Normal
                # release layouts are tested to resolve a target-clear option.
                chosen_side, chosen = min(
                    dock_candidates,
                    key=lambda row: row[1].intersection_area(selected_obstacle),
                )
        elif chosen is None:
            # A dense desktop scene still receives the same compact anchored
            # component. Choose the least-obstructive shifted placement rather
            # than changing its anatomy into a bottom sheet.
            fallback_candidates: list[
                tuple[tuple[float, ...], str, Rect]
            ] = []
            for side_index, side in enumerate(sides):
                for size_index, (width, height) in enumerate(sizes):
                    raw = candidate(side, width, height)
                    rectangle = clamp(raw)
                    selected_overlap = rectangle.intersection_area(
                        selected_obstacle
                    )
                    hard_overlap = sum(
                        rectangle.intersection_area(obstacle)
                        for obstacle in hard
                    )
                    soft_overlap = sum(
                        rectangle.intersection_area(obstacle)
                        for obstacle in soft.values()
                    )
                    clamp_shift = (
                        abs(rectangle.x - raw.x)
                        + abs(rectangle.y - raw.y)
                    )
                    fallback_candidates.append((
                        (
                            hard_overlap,
                            selected_overlap,
                            soft_overlap,
                            float(side_index),
                            float(size_index),
                            clamp_shift,
                        ),
                        side,
                        rectangle,
                    ))
            _, chosen_side, chosen = min(
                fallback_candidates,
                key=lambda row: row[0],
            )

        avoided = tuple(
            bed_key for bed_key, obstacle in sorted(soft.items())
            if not chosen.intersects(obstacle)
        )
        pointer_inset = min(20.0, max(0.0, chosen.height / 2.0))
        pointer_x_inset = min(20.0, max(0.0, chosen.width / 2.0))
        if chosen_side == "right":
            start = (selected_target.right, anchor_y)
            end = (
                chosen.x,
                max(
                    chosen.y + pointer_inset,
                    min(anchor_y, chosen.bottom - pointer_inset),
                ),
            )
        elif chosen_side == "left":
            start = (selected_target.x, anchor_y)
            end = (
                chosen.right,
                max(
                    chosen.y + pointer_inset,
                    min(anchor_y, chosen.bottom - pointer_inset),
                ),
            )
        elif chosen_side in {"above", "top-docked"}:
            start = (anchor_x, selected_target.y)
            end = (
                max(
                    chosen.x + pointer_x_inset,
                    min(anchor_x, chosen.right - pointer_x_inset),
                ),
                chosen.bottom,
            )
        else:
            start = (anchor_x, selected_target.bottom)
            end = (
                max(
                    chosen.x + pointer_x_inset,
                    min(anchor_x, chosen.right - pointer_x_inset),
                ),
                chosen.y,
            )
        return PopoverPlacement(
            rectangle=chosen,
            chosen_side=chosen_side,
            connector_start=start,
            connector_end=end,
            maximum_content_height=chosen.height,
            avoided_beds=avoided,
            docked=docked,
        )


def planter_draw_rect(
    layout: PlantPlacement,
    family: dict[str, Any] | None = None,
) -> Rect:
    """Return the exact planter box used by both native and Home renderers."""

    resolved_family = family if isinstance(family, dict) else {}
    variant_name = {
        "far": "back",
        "middle": "middle",
        "near": "front",
    }.get(str(layout.depth_band), "")
    variants = resolved_family.get("variants", {})
    variant = variants.get(variant_name, {}) if isinstance(variants, dict) else {}
    if not isinstance(variant, dict):
        variant = {}
    canvas = resolved_family.get("canvas", [1024, 512])
    soil_anchor = resolved_family.get("soil_anchor", [0.5, 220 / 512])
    try:
        canvas_width = max(1.0, float(canvas[0]))
        canvas_height = max(1.0, float(canvas[1]))
        anchor_x = max(0.0, min(1.0, float(soil_anchor[0])))
        anchor_y = max(0.0, min(1.0, float(soil_anchor[1])))
        width_multiplier = max(
            1.0,
            min(
                1.6,
                float(
                    variant.get(
                        "width_multiplier",
                        resolved_family.get("width_multiplier", 1.28),
                    )
                ),
            ),
        )
    except (IndexError, TypeError, ValueError):
        canvas_width = 1024.0
        canvas_height = 512.0
        anchor_x = 0.5
        anchor_y = 220 / 512
        width_multiplier = 1.28
    draw_width = layout.bed_footprint.width * width_multiplier
    draw_height = draw_width * canvas_height / canvas_width
    return Rect(
        layout.ground_anchor[0] - anchor_x * draw_width,
        layout.ground_anchor[1] - anchor_y * draw_height,
        draw_width,
        draw_height,
    )


def planter_accessory_exclusions(
    layout: PlantPlacement,
    family: dict[str, Any] | None = None,
) -> tuple[Rect, ...]:
    """Project normalized opaque planter/soil bounds into scene coordinates."""

    resolved_family = family if isinstance(family, dict) else {}
    variant_name = {
        "far": "back",
        "middle": "middle",
        "near": "front",
    }.get(str(layout.depth_band), "")
    variants = resolved_family.get("variants", {})
    variant = variants.get(variant_name, {}) if isinstance(variants, dict) else {}
    if not isinstance(variant, dict):
        return ()
    raw_exclusions = variant.get("accessory_exclusions", ())
    if not isinstance(raw_exclusions, (list, tuple)):
        return ()
    planter = planter_draw_rect(layout, resolved_family)
    projected: list[Rect] = []
    for record in raw_exclusions:
        bounds = record.get("bounds", ()) if isinstance(record, dict) else ()
        if not isinstance(bounds, (list, tuple)) or len(bounds) != 4:
            continue
        try:
            x, y, width, height = (float(value) for value in bounds)
        except (TypeError, ValueError):
            continue
        normalized = Rect(
            max(0.0, min(1.0, x)),
            max(0.0, min(1.0, y)),
            max(0.0, min(1.0 - max(0.0, min(1.0, x)), width)),
            max(0.0, min(1.0 - max(0.0, min(1.0, y)), height)),
        )
        if normalized.area <= 0:
            continue
        projected.append(Rect(
            planter.x + normalized.x * planter.width,
            planter.y + normalized.y * planter.height,
            normalized.width * planter.width,
            normalized.height * planter.height,
        ))
    return tuple(projected)


def _nurtured_marker_side_placement(
    canvas_width: float,
    canvas_height: float,
    layout: PlantPlacement,
    *,
    planter_rect: Rect | None = None,
    obstacles: Iterable[Rect] = (),
    protected_regions: Iterable[Rect] = (),
    margin: float = 6.0,
    side_override: str | None = None,
    lane: Rect | None = None,
    allow_scaling: bool = True,
) -> NurturedMarkerPlacement:
    """Place one inward-facing watering can beside its nurtured plant."""

    safe_width = max(1.0, float(canvas_width))
    safe_height = max(1.0, float(canvas_height))
    support = planter_rect or planter_draw_rect(layout)
    side = (
        str(side_override)
        if side_override in {"left", "right"}
        else "left" if int(layout.slot_index) % 2 == 0 else "right"
    )
    asset_key = (
        "nurtured_marker_spout_right"
        if side == "left"
        else "nurtured_marker"
    )
    orientation = "spout-right" if side == "left" else "spout-left"
    perspective_scale = _nurtured_marker_perspective_scale(layout)
    desired_size = max(
        44.0,
        min(88.0, max(68.0, support.width * 0.45) * perspective_scale),
    )
    blocked = [
        rect for rect in tuple(obstacles) + tuple(protected_regions)
        if isinstance(rect, Rect) and rect.area > 0
    ]

    sizes: list[float] = [desired_size]
    if allow_scaling:
        size = desired_size - 4.0
        while size >= 44.0:
            sizes.append(size)
            size -= 4.0
        if sizes[-1] > 44.0:
            sizes.append(44.0)

    candidates: list[tuple[float, float, float, float, NurturedMarkerPlacement]] = []
    for candidate_size in sizes:
        pulse_pad = candidate_size * 0.04
        # Anchor to the plant silhouette rather than the full transparent
        # planter canvas. Opaque planter/soil bounds are supplied separately as
        # protected regions, so transparent padding never pushes the can away.
        # Obstacles already carry a four-pixel plant clearance; the additional
        # two pixels keep the entire pulse envelope visibly separate.
        gap = pulse_pad + 6.0
        base_x = (
            layout.visible.x - gap - candidate_size
            if side == "left"
            else layout.visible.right + gap
        )
        # The runtime asset's painted base ends at roughly 91.6% of its square
        # canvas. Align that visible contact point with the shared soil anchor,
        # not the bottom of the planter artwork. The artwork extends well below
        # the soil on the middle/front rows; using its lower edge makes the can
        # look detached from the plant it is meant to identify.
        base_y = layout.ground_anchor[1] - candidate_size * 0.916
        minimum_x = margin + pulse_pad
        maximum_x = safe_width - margin - pulse_pad - candidate_size
        minimum_y = margin + pulse_pad
        maximum_y = safe_height - margin - pulse_pad - candidate_size
        if isinstance(lane, Rect) and lane.area > 0:
            minimum_x = max(minimum_x, lane.x + pulse_pad)
            maximum_x = min(maximum_x, lane.right - pulse_pad - candidate_size)
            minimum_y = max(minimum_y, lane.y + pulse_pad)
            maximum_y = min(maximum_y, lane.bottom - pulse_pad - candidate_size)
        if minimum_x > maximum_x or minimum_y > maximum_y:
            continue

        # Try the exact plant-side lane first. If another silhouette blocks it,
        # boundary candidates can move outward on the same side. All sizes are
        # considered before choosing: a modest shrink near the plant is clearer
        # than a full-size can stranded at the canvas edge.
        x_candidates = {
            max(minimum_x, min(maximum_x, base_x)),
            minimum_x if side == "left" else maximum_x,
        }
        for blocker in blocked:
            x_candidates.add(
                blocker.x - candidate_size - pulse_pad
                if side == "left"
                else blocker.right + pulse_pad
            )

        for candidate_x in x_candidates:
            if not minimum_x <= candidate_x <= maximum_x:
                continue
            if side == "left":
                if candidate_x > base_x + 1e-6:
                    continue
            elif candidate_x < base_x - 1e-6:
                continue
            pulse_left = candidate_x - pulse_pad
            pulse_right = candidate_x + candidate_size + pulse_pad
            y_candidates = {
                max(minimum_y, min(maximum_y, base_y)),
                minimum_y,
                maximum_y,
            }
            for blocker in blocked:
                horizontally_blocked = not (
                    pulse_right <= blocker.x or blocker.right <= pulse_left
                )
                if not horizontally_blocked:
                    continue
                y_candidates.add(blocker.y - candidate_size - pulse_pad)
                y_candidates.add(blocker.bottom + pulse_pad)

            for candidate_y in y_candidates:
                if not minimum_y <= candidate_y <= maximum_y:
                    continue
                candidate = Rect(
                    candidate_x,
                    candidate_y,
                    candidate_size,
                    candidate_size,
                )
                pulse = candidate.expanded(pulse_pad)
                if any(pulse.intersects(rect) for rect in blocked):
                    continue
                center_x = candidate.x + candidate.width / 2
                ground_y = candidate.y + candidate.height * 0.916
                horizontal_distance = abs(center_x - layout.ground_anchor[0])
                ground_delta = abs(ground_y - layout.ground_anchor[1])
                distance = math.hypot(horizontal_distance, ground_delta * 1.25)
                shrink_penalty = (desired_size - candidate_size) * 0.75
                candidates.append((
                    distance + shrink_penalty,
                    ground_delta,
                    horizontal_distance,
                    -candidate_size,
                    NurturedMarkerPlacement(
                        rect=candidate,
                        pulse_bounds=pulse,
                        planter_rect=support,
                        side=side,
                        asset_key=asset_key,
                        orientation=orientation,
                        contact_shadow=_nurtured_marker_contact_shadow(
                            candidate,
                            safe_width,
                            safe_height,
                            margin,
                        ),
                        perspective_scale=perspective_scale,
                    ),
                ))

    if candidates:
        return min(candidates, key=lambda item: item[:4])[4]

    # Unsupported/degraded geometry must stay bounded and preserve the state
    # cue. Supported V6 layouts are tested never to reach this branch.
    fallback_size = max(
        1.0,
        min(44.0, safe_width - margin * 2, safe_height - margin * 2),
    )
    fallback_x = (
        layout.visible.x - 4.0 - fallback_size
        if side == "left"
        else layout.visible.right + 4.0
    )
    fallback = Rect(
        max(margin, min(safe_width - margin - fallback_size, fallback_x)),
        max(
            margin,
            min(
                safe_height - margin - fallback_size,
                layout.ground_anchor[1] - fallback_size * 0.916,
            ),
        ),
        fallback_size,
        fallback_size,
    )
    return NurturedMarkerPlacement(
        rect=fallback,
        pulse_bounds=fallback,
        planter_rect=support,
        side=side,
        asset_key=asset_key,
        orientation=orientation,
        used_fallback=True,
        contact_shadow=_nurtured_marker_contact_shadow(
            fallback,
            safe_width,
            safe_height,
            margin,
        ),
        perspective_scale=perspective_scale,
    )


def nurtured_marker_placement(
    canvas_width: float,
    canvas_height: float,
    layout: PlantPlacement,
    *,
    planter_rect: Rect | None = None,
    obstacles: Iterable[Rect] = (),
    protected_regions: Iterable[Rect] = (),
    accessory_lanes: Iterable[Rect] = (),
    margin: float = 6.0,
) -> NurturedMarkerPlacement:
    """Resolve the watering can from one bed's ordered accessory lanes.

    Both full-size lanes are tried before any scale reduction. This keeps the
    can adjacent to its plant without accepting a planter, soil, or neighbor
    collision merely to preserve the preferred left/right parity.
    """

    lanes = tuple(lane for lane in accessory_lanes if isinstance(lane, Rect) and lane.area > 0)
    preferred = "left" if int(layout.slot_index) % 2 == 0 else "right"
    attempts: list[tuple[str, Rect | None]] = []
    if lanes:
        for lane in lanes:
            lane_side = (
                "left"
                if lane.x + lane.width / 2 < layout.ground_anchor[0]
                else "right"
            )
            attempts.append((lane_side, lane))
    else:
        alternate = "right" if preferred == "left" else "left"
        attempts = [(preferred, None), (alternate, None)]

    for allow_scaling in (False, True):
        resolved: list[NurturedMarkerPlacement] = []
        for side, lane in attempts:
            candidate = _nurtured_marker_side_placement(
                canvas_width,
                canvas_height,
                layout,
                planter_rect=planter_rect,
                obstacles=obstacles,
                protected_regions=protected_regions,
                margin=margin,
                side_override=side,
                lane=lane,
                allow_scaling=allow_scaling,
            )
            candidate_ground_y = candidate.rect.y + candidate.rect.height * 0.916
            candidate_distance = math.hypot(
                candidate.rect.x + candidate.rect.width / 2 - layout.ground_anchor[0],
                candidate_ground_y - layout.ground_anchor[1],
            )
            if (
                not candidate.used_fallback
                and abs(candidate_ground_y - layout.ground_anchor[1])
                <= candidate.rect.height * NURTURED_MARKER_MAX_GROUND_DELTA_RATIO
                and candidate_distance
                <= max(1.0, (planter_rect or planter_draw_rect(layout)).width)
                * NURTURED_MARKER_MAX_PLANT_DISTANCE_RATIO
            ):
                resolved.append(candidate)
        if resolved:
            edge_target = max(float(margin), min(20.0, canvas_width * 0.04))

            def edge_penalty(candidate: NurturedMarkerPlacement) -> float:
                pulse = candidate.pulse_bounds
                clearance = min(
                    pulse.x,
                    pulse.y,
                    float(canvas_width) - pulse.right,
                    float(canvas_height) - pulse.bottom,
                )
                return max(0.0, edge_target - clearance)

            return min(
                resolved,
                key=lambda candidate: (
                    -candidate.rect.width,
                    edge_penalty(candidate),
                    0 if candidate.side == preferred else 1,
                    math.hypot(
                        candidate.rect.x + candidate.rect.width / 2 - layout.ground_anchor[0],
                        candidate.rect.y + candidate.rect.height * 0.916 - layout.ground_anchor[1],
                    ),
                ),
            )

    # Preserve an explicit, bounded state cue on unsupported geometry. The
    # validator treats this fallback as a release failure for supported beds.
    side, lane = attempts[0]
    return _nurtured_marker_side_placement(
        canvas_width,
        canvas_height,
        layout,
        planter_rect=planter_rect,
        obstacles=obstacles,
        protected_regions=protected_regions,
        margin=margin,
        side_override=side,
        lane=lane,
        allow_scaling=True,
    )


def nurtured_marker_fallback_rect(
    placement: NurturedMarkerPlacement,
) -> Rect:
    """Center the compact degraded marker inside the resolved can lane."""

    size = max(22.0, min(26.0, placement.rect.width * 0.32))
    return Rect(
        placement.rect.x + (placement.rect.width - size) / 2,
        placement.rect.y + (placement.rect.height - size) / 2,
        size,
        size,
    )


def partition_scene_rows(
    rows: Iterable[tuple[dict[str, Any], PlantPlacement]],
) -> dict[str, list[tuple[dict[str, Any], PlantPlacement]]]:
    """Return stable physical rows sorted only by soil-contact depth."""
    result = {"rear": [], "front": []}
    for item in rows:
        result["rear" if item[1].shadow_depth == "rear" else "front"].append(item)
    for values in result.values():
        values.sort(key=lambda item: item[1].z_depth)
    return result


def scene_render_trace(layouts: Iterable[PlantPlacement]) -> tuple[str, ...]:
    """Describe the shared physical layer contract for tests and QA tools."""
    grouped = {"rear": [], "front": []}
    for layout in layouts:
        grouped["rear" if layout.shadow_depth == "rear" else "front"].append(layout)
    trace: list[str] = ["background", "decorations"]
    for row in ("rear", "front"):
        ordered = sorted(grouped[row], key=lambda item: item.z_depth)
        trace.extend(f"{row}:shadow:{item.slot_index}" for item in ordered)
        trace.extend(f"{row}:plant:{item.slot_index}" for item in ordered)
        trace.append(f"{row}:occlusion")
    trace.append("interaction")
    return tuple(trace)


PlantGrowthDisplay = StageProgress


def growth_display(growth_points: Any) -> PlantGrowthDisplay:
    """Compatibility wrapper for the shared renderer-neutral projection."""

    return stage_progress(growth_points)


def _number(value: Any, default: float, low: float, high: float) -> float:
    try:
        return max(low, min(high, float(value)))
    except (TypeError, ValueError):
        return default


def _rect(value: Any, default: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return default
    x, y, w, h = (_number(v, d, 0.0, 1.0) for v, d in zip(value, default))
    return x, y, max(0.01, min(w, 1.0 - x)), max(0.01, min(h, 1.0 - y))


def plant_layout_item(item: Any, slot_index: int) -> dict[str, Any]:
    """Normalize resolved scene payloads for the shared layout engine."""
    result = dict(item) if isinstance(item, dict) else {}
    result["occupied"] = bool(result)
    asset = result.get("asset")
    if not isinstance(result.get("placement"), dict) and isinstance(asset, dict):
        placement = asset.get("placement")
        if isinstance(placement, dict):
            result["placement"] = dict(placement)
    if isinstance(asset, dict):
        dimensions = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else asset
        try:
            source_width = float(dimensions.get("width", 0))
            source_height = float(dimensions.get("height", 0))
            if source_width > 0 and source_height > 0:
                result["canvas_aspect"] = source_width / source_height
        except (TypeError, ValueError):
            pass
    result["slot_index"] = int(slot_index)
    return result


def repair_unique_slot_items(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Repair duplicate or invalid runtime slots without changing plant IDs."""
    result: list[dict[str, Any]] = []
    used: set[int] = set()
    for order, source in enumerate(list(items)[:6]):
        item = dict(source) if isinstance(source, dict) else {}
        raw_slot = item.get("slot_index", order)
        try:
            slot = int(raw_slot)
        except (TypeError, ValueError):
            slot = -1
        if isinstance(raw_slot, bool) or slot < 0 or slot >= 6 or slot in used:
            slot = next(candidate for candidate in range(6) if candidate not in used)
        item["slot_index"] = slot
        used.add(slot)
        result.append(item)
    return result


def scene_profile_name(width: float, height: float, surface_context: str = "dashboard") -> str:
    if surface_context == "home":
        return "home"
    ratio = max(1.0, float(width)) / max(1.0, float(height))
    if ratio <= 1.42:
        return "4:3"
    if ratio <= 1.66:
        return "3:2"
    return "16:9"


def scene_surface_variant(
    placement: dict[str, Any] | None,
    width: float,
    height: float,
    surface_context: str = "dashboard",
) -> tuple[str, dict[str, Any]]:
    """Resolve the painted background variant used by layout and rendering."""
    contract = placement if isinstance(placement, dict) else {}
    surface_profile = contract.get("surface_profile")
    profile_name = scene_profile_name(width, height, surface_context)
    if isinstance(surface_profile, dict):
        ratio = max(1.0, float(width)) / max(1.0, float(height))
        breakpoints = surface_profile.get("variant_breakpoints", {})
        four_three_max = _number(
            breakpoints.get("four_three_max") if isinstance(breakpoints, dict) else None,
            1.42, 1.0, 2.0,
        )
        ultrawide_min = _number(
            breakpoints.get("ultrawide_min") if isinstance(breakpoints, dict) else None,
            2.05, 1.4, 4.0,
        )
        if surface_context == "home" or ratio >= ultrawide_min:
            profile_name = "home"
        elif ratio <= four_three_max:
            profile_name = "4:3"
    profiles = contract.get("layout_profiles")
    layout_profile = profiles.get(profile_name, {}) if isinstance(profiles, dict) else {}
    variants = surface_profile.get("variants", {}) if isinstance(surface_profile, dict) else {}
    requested = (
        str(layout_profile.get("surface_variant", ""))
        if isinstance(layout_profile, dict)
        else ""
    )
    if requested not in variants:
        requested = "home" if profile_name == "home" else "4:3" if profile_name == "4:3" else "16:9"
    variant = variants.get(requested, {}) if isinstance(variants, dict) else {}
    return requested, dict(variant) if isinstance(variant, dict) else {}


def cover_project_point(
    x: float,
    y: float,
    *,
    width: float,
    height: float,
    source_aspect: float = 4 / 3,
    focal: tuple[float, float] = (0.5, 0.5),
) -> tuple[float, float]:
    """Project a source point through the release canvas' contain transform.

    The legacy name remains because landmark helpers import it directly. The
    runtime no longer crops the source artwork: unused width or height becomes
    a centered gutter and every bed, plant, landmark, and hit region follows
    the same scale.
    """

    scene_aspect = max(1.0, float(width)) / max(1.0, float(height))
    # The exported 16:9 artwork is 1672 x 941, which is microscopically
    # narrower than mathematical 16:9.  Preserve the frozen sub-pixel planter
    # geometry for effectively identical aspect ratios; a contain projection
    # would only trade a 0.05 px vertical correction for a 0.05 px horizontal
    # correction without revealing any additional artwork.  Material aspect
    # differences still use the complete-canvas contain transform below.
    if abs(scene_aspect - source_aspect) / source_aspect <= 0.005:
        if scene_aspect > source_aspect:
            scale_y = scene_aspect / source_aspect
            return x, y * scale_y - (scale_y - 1.0) * focal[1]
        if scene_aspect < source_aspect:
            scale_x = source_aspect / scene_aspect
            return x * scale_x - (scale_x - 1.0) * focal[0], y
        return x, y
    if scene_aspect > source_aspect:
        scale_x = source_aspect / scene_aspect
        return 0.5 + (x - 0.5) * scale_x, y
    if scene_aspect < source_aspect:
        scale_y = scene_aspect / source_aspect
        return x, 0.5 + (y - 0.5) * scale_y
    return x, y


def _placement_contract(
    value: dict[str, Any] | None,
    *,
    width: float,
    height: float,
    surface_context: str,
    composition_count: int,
) -> tuple[dict[str, Any], tuple[BedAnchor, ...], str]:
    """Resolve ratio- and count-specific beds while preserving legacy manifests."""
    contract = value if isinstance(value, dict) else {}
    profile_name = scene_profile_name(width, height, surface_context)
    surface_profile = contract.get("surface_profile")
    if isinstance(surface_profile, dict):
        ratio = max(1.0, float(width)) / max(1.0, float(height))
        breakpoints = surface_profile.get("variant_breakpoints", {})
        ultrawide_min = _number(
            breakpoints.get("ultrawide_min") if isinstance(breakpoints, dict) else None,
            2.05, 1.4, 4.0,
        )
        if surface_context == "home" or ratio >= ultrawide_min:
            profile_name = "home"
    profiles = contract.get("layout_profiles")
    profile = profiles.get(profile_name, {}) if isinstance(profiles, dict) else {}
    if not isinstance(profile, dict):
        profile = {}
    nested_zone = profile.get("planting_zone", contract.get("planting_zone"))
    zone = nested_zone if isinstance(nested_zone, dict) else contract
    compositions = profile.get("compositions")
    raw_anchors = compositions.get(str(composition_count)) if isinstance(compositions, dict) else None
    if not isinstance(raw_anchors, list):
        raw_anchors = contract.get("bed_anchors")
    if isinstance(raw_anchors, list) and len(raw_anchors) == len(DEFAULT_BED_ANCHORS):
        anchors = tuple(
            BedAnchor.from_manifest(raw, DEFAULT_BED_ANCHORS[index])
            for index, raw in enumerate(raw_anchors)
        )
    else:
        anchors = DEFAULT_BED_ANCHORS
    if profile.get("coordinate_space") in {"source_4_3", "source"}:
        focal_raw = profile.get("focal_point", [0.5, 0.5])
        focal = (
            _number(focal_raw[0], 0.5, 0.0, 1.0),
            _number(focal_raw[1], 0.5, 0.0, 1.0),
        ) if isinstance(focal_raw, (list, tuple)) and len(focal_raw) == 2 else (0.5, 0.5)
        source_aspect = _number(profile.get("source_aspect_ratio"), 4 / 3, 0.5, 4.0)
        scene_aspect = max(1.0, float(width)) / max(1.0, float(height))
        scale_x = source_aspect / scene_aspect if scene_aspect < source_aspect else 1.0
        scale_y = scene_aspect / source_aspect if scene_aspect > source_aspect else 1.0
        projected: list[BedAnchor] = []
        for anchor in anchors:
            x, y = cover_project_point(
                anchor.x, anchor.y, width=width, height=height,
                source_aspect=source_aspect, focal=focal,
            )
            label_x, label_y = cover_project_point(
                anchor.label_anchor[0], anchor.label_anchor[1], width=width, height=height,
                source_aspect=source_aspect, focal=focal,
            )
            plane_x, plane_y, plane_w, plane_h = anchor.contact_plane
            plane_left, plane_top = cover_project_point(
                plane_x, plane_y, width=width, height=height,
                source_aspect=source_aspect, focal=focal,
            )
            plane_right, plane_bottom = cover_project_point(
                plane_x + plane_w, plane_y + plane_h, width=width, height=height,
                source_aspect=source_aspect, focal=focal,
            )
            projected_shadow_plane = tuple(
                cover_project_point(
                    point[0], point[1], width=width, height=height,
                    source_aspect=source_aspect, focal=focal,
                )
                for point in anchor.shadow_plane
            )
            projected_support_line = tuple(
                cover_project_point(
                    point[0], point[1], width=width, height=height,
                    source_aspect=source_aspect, focal=focal,
                )
                for point in anchor.support_line
            )
            projected.append(BedAnchor(
                x, y, y, anchor.plant_scale,
                (anchor.footprint[0] * scale_x, anchor.footprint[1] * scale_y),
                (label_x, label_y),
                anchor.physical_width_ratio,
                surface_id=anchor.surface_id,
                contact_plane=(
                    plane_left,
                    plane_top,
                    max(0.01, plane_right - plane_left),
                    max(0.01, plane_bottom - plane_top),
                ),
                shadow_plane=projected_shadow_plane,
                support_line=projected_support_line,
                shadow_depth=anchor.shadow_depth,
                shadow_opacity=anchor.shadow_opacity,
                occlusion_id=anchor.occlusion_id,
                surface_kind=anchor.surface_kind,
                allowed_base_types=anchor.allowed_base_types,
                seating_depth=anchor.seating_depth * scale_y,
                depth_band=anchor.depth_band,
                shadow_color=anchor.shadow_color,
                light_direction=anchor.light_direction,
            ))
        anchors = tuple(projected)
    return zone, anchors, profile_name


def plant_layout(width: float, height: float, plants: int | Iterable[dict[str, Any]],
                 planting_zone: dict[str, Any] | None = None, *,
                 surface_context: str = "dashboard", composition_count: int | None = None,
                 protected_status: bool = True, reserve_move_controls: bool = False) -> list[PlantPlacement]:
    """Compose up to six plants against permanent, metadata-backed garden beds."""
    items = (
        [{"slot_index": index} for index in range(max(0, min(6, plants)))]
        if isinstance(plants, int)
        else repair_unique_slot_items(plants)
    )
    if not items:
        return []
    width, height = max(1.0, float(width)), max(1.0, float(height))
    count = max(1, min(6, int(composition_count if composition_count is not None else len(items))))
    zone, bed_anchors, profile_name = _placement_contract(
        planting_zone,
        width=width,
        height=height,
        surface_context=surface_context,
        composition_count=count,
    )
    surface_profile = (
        planting_zone.get("surface_profile", {})
        if isinstance(planting_zone, dict)
        else {}
    )
    light_direction_raw = surface_profile.get("light_direction", [-0.22, 0.18]) if isinstance(surface_profile, dict) else [-0.22, 0.18]
    light_direction = (
        _number(light_direction_raw[0], -0.22, -1.0, 1.0),
        _number(light_direction_raw[1], 0.18, -1.0, 1.0),
    ) if isinstance(light_direction_raw, (list, tuple)) and len(light_direction_raw) == 2 else (-0.22, 0.18)
    surface_theme = str(surface_profile.get("theme", "")) if isinstance(surface_profile, dict) else ""
    appearance = surface_profile.get("appearance", {}) if isinstance(surface_profile, dict) else {}
    if not isinstance(appearance, dict):
        appearance = {}
    origin_key = "home" if profile_name == "home" else "16:9" if profile_name == "16:9" else "4:3"
    raw_origins = surface_profile.get("key_light_origins", {}) if isinstance(surface_profile, dict) else {}
    raw_origin = raw_origins.get(origin_key, [0.91, 0.18]) if isinstance(raw_origins, dict) else [0.91, 0.18]
    key_light_origin = (
        _number(raw_origin[0], 0.91, 0.0, 1.0),
        _number(raw_origin[1], 0.18, 0.0, 1.0),
    ) if isinstance(raw_origin, (list, tuple)) and len(raw_origin) == 2 else (0.91, 0.18)
    enforce_slot_envelopes = (
        isinstance(surface_profile, dict)
        and str(surface_profile.get("profile_id", "")).startswith(("verdant_dusk_surface_v", "verdant_twilight_surface_v"))
    )
    left = _number(zone.get("left"), 0.08, 0.0, 0.45) * width
    right = _number(zone.get("right"), 0.92, 0.55, 1.0) * width
    clearance = max(3.0, (right - left) * 0.012)
    left, right = left + clearance, right - clearance

    available_w = right - left
    if profile_name == "home":
        context_scale = 1.14
    else:
        compact_scale = responsive_interpolate(
            width,
            360,
            520,
            1.18,
            1.10,
        )
        context_scale = responsive_interpolate(
            width,
            600,
            840,
            compact_scale,
            1.0,
        )
        # Preserve the already-generous compact composition while giving the
        # desktop Garden the requested 8–12% readability lift.
        context_scale = min(1.20, context_scale * 1.10)
    nominal_h = min(height * 0.29, available_w * 0.205) * context_scale
    specs: list[
        tuple[int, dict[str, Any], BedAnchor, tuple[float, float, float, float], tuple[float, float]]
    ] = []
    active_slots: set[int] = set()
    for order, item in enumerate(items):
        try:
            slot = max(0, min(5, int(item.get("slot_index", order))))
        except (AttributeError, TypeError, ValueError):
            slot = order
        bed = bed_anchors[slot]
        placement = item.get("placement", {}) if isinstance(item, dict) else {}
        if not isinstance(item, dict) or bool(item.get("occupied", True)):
            active_slots.add(slot)
        visible_bounds = _rect(placement.get("art_bounds", placement.get("visible_bounds")), (0.08, 0.04, 0.84, 0.92))
        ground_anchor = placement.get("soil_contact", placement.get("ground_anchor", [0.5, visible_bounds[1] + visible_bounds[3]]))
        if not isinstance(ground_anchor, (list, tuple)) or len(ground_anchor) != 2:
            ground_anchor = [0.5, visible_bounds[1] + visible_bounds[3]]
        ground_anchor = [
            placement.get("ground_anchor_x", ground_anchor[0]),
            placement.get("ground_anchor_y", ground_anchor[1]),
        ]
        specs.append((
            slot,
            item,
            bed,
            visible_bounds,
            (_number(ground_anchor[0], 0.5, 0, 1), _number(ground_anchor[1], 0.96, 0, 1)),
        ))

    def envelope_for(bed: BedAnchor, placement: dict[str, Any]) -> Rect:
        """Return the deterministic same-depth-band visual envelope for a bed."""
        use_depth_band = bed.depth_band in {"far", "middle", "near"}
        peers = sorted(
            (
                candidate for candidate in bed_anchors
                if (
                    candidate.depth_band == bed.depth_band
                    if use_depth_band
                    else candidate.shadow_depth == bed.shadow_depth
                )
            ),
            key=lambda candidate: candidate.x,
        )
        index = next((position for position, candidate in enumerate(peers) if candidate == bed), 0)
        center = width * bed.x
        left_edge = 3.0 if index == 0 else width * (peers[index - 1].x + bed.x) / 2
        right_edge = width - 3.0 if index >= len(peers) - 1 else width * (bed.x + peers[index + 1].x) / 2
        inset = max(3.0, width * 0.006)
        left_edge += inset
        right_edge -= inset
        envelope_scale = _number(placement.get("slot_envelope_scale"), 1.0, 0.82, 1.08)
        available = max(44.0, right_edge - left_edge)
        # Envelopes are visual-mass limits, not hard grid cells.  A modest
        # amount of foliage may cross the midpoint between beds while each
        # base and primary silhouette remain readable.
        envelope_width = max(44.0, available * 1.58 * envelope_scale)
        envelope_width = min(envelope_width, max(44.0, width - 6.0))
        envelope_center = max(
            3.0 + envelope_width / 2,
            min(width - 3.0 - envelope_width / 2, center),
        )
        depth = height * bed.y
        return Rect(
            envelope_center - envelope_width / 2,
            3.0,
            envelope_width,
            max(44.0, min(height - 3.0, depth + max(8.0, height * 0.035)) - 3.0),
        )

    def build(
        group_scale: float,
        adjustments: dict[int, tuple[float, float, float]],
        reasons: dict[int, set[str]] | None = None,
        warning_map: dict[int, set[str]] | None = None,
    ) -> list[PlantPlacement]:
        def support_y(points: tuple[tuple[float, float], ...], x_ratio: float, fallback: float) -> float:
            if len(points) < 2:
                return fallback
            ordered = sorted(points)
            if x_ratio <= ordered[0][0]:
                return ordered[0][1]
            if x_ratio >= ordered[-1][0]:
                return ordered[-1][1]
            for left_point, right_point in zip(ordered, ordered[1:]):
                if left_point[0] <= x_ratio <= right_point[0]:
                    span = max(1e-6, right_point[0] - left_point[0])
                    progress = (x_ratio - left_point[0]) / span
                    return left_point[1] + (right_point[1] - left_point[1]) * progress
            return fallback

        result: list[PlantPlacement] = []
        for slot, item, bed, vb, anchor in specs:
            placement = item.get("placement", {}) if isinstance(item, dict) else {}
            slot_scale, offset_x, offset_y = adjustments.get(slot, (1.0, 0.0, 0.0))
            base_type = str(placement.get("base_type", "legacy"))
            has_semantic_base = isinstance(placement.get("base_bounds"), (list, tuple))
            has_semantic_support = isinstance(placement.get("support_bounds"), (list, tuple))
            canvas_aspect = _number(item.get("canvas_aspect"), 1.0, 0.05, 20.0)
            vessel_multiplier = _number(placement.get("vessel_class_multiplier"), 1.0, 0.5, 1.5)
            asset_correction = _number(placement.get("scene_scale_correction"), 1.0, 0.5, 1.5)
            visual_correction = _number(placement.get("visual_scale_correction"), 1.0, 0.70, 1.40)
            depth_scale = _number(bed.plant_scale, 1.0, 0.5, 1.5)
            ideal_scale = min(height * bed.physical_width_ratio, available_w * 0.14)
            target_vessel_w = ideal_scale * depth_scale * vessel_multiplier * asset_correction * visual_correction
            if base_type in {"pot", "dirt_mound", "direct_soil"} and has_semantic_base:
                # Geometry-v2 assets declare the lower support separately. The
                # base fallback remains only for third-party/legacy assets and
                # is reported as a packaging-blocking warning below.
                support_bounds = _rect(
                    placement.get("support_bounds"),
                    _rect(placement.get("base_bounds"), (0.30, 0.72, 0.40, 0.24)),
                )
                base_bounds = _rect(placement.get("base_bounds"), (0.30, 0.72, 0.40, 0.24))
                target_semantic_width = vb[2] if base_type == "direct_soil" else support_bounds[2]
                draw_w = target_vessel_w * group_scale * slot_scale / target_semantic_width
                draw_h = draw_w / canvas_aspect
                visible_w, visible_h = draw_w * vb[2], draw_h * vb[3]
                final_scale = draw_w
            else:
                legacy_scale = _number(
                    placement.get("display_scale", placement.get("scale", 1.0)), 1.0, 0.25, 2.5
                )
                visible_h = nominal_h * legacy_scale * bed.plant_scale * group_scale * slot_scale
                visible_w = visible_h * (vb[2] / vb[3])
                draw_w, draw_h = visible_w / vb[2], visible_h / vb[3]
                final_scale = legacy_scale * bed.plant_scale * group_scale * slot_scale
            base_x = width * bed.x + offset_x
            base_y = height * bed.y + offset_y
            plane_x, plane_y, plane_w, plane_h = bed.contact_plane
            contact_plane = Rect(
                width * plane_x,
                height * plane_y,
                width * plane_w,
                height * plane_h,
            )
            if bed.surface_id:
                # Registered surfaces are real painted planes. Horizontal fitting
                # may move a vessel along that plane, but its soil-contact Y is
                # immutable and its support must remain within the painted top.
                support_half = max(1.0, target_vessel_w * group_scale * slot_scale / 2)
                min_x = contact_plane.x + support_half
                max_x = contact_plane.right - support_half
                base_x = (contact_plane.x + contact_plane.right) / 2 if min_x > max_x else max(min_x, min(max_x, base_x))
                resolved_y = support_y(bed.support_line, base_x / width, bed.y)
                base_y = height * (resolved_y + bed.seating_depth)
                base_y = max(contact_plane.y, min(contact_plane.bottom, base_y))
            # Anchor the artwork's declared point of ground contact to the scene
            # baseline. This works for both potted plants and dirt mounds and avoids
            # treating transparent image padding as part of the plant's height.
            draw = Rect(base_x - anchor[0] * draw_w, base_y - anchor[1] * draw_h, draw_w, draw_h)
            visible = Rect(draw.x + vb[0] * draw_w, draw.y + vb[1] * draw_h,
                           vb[2] * draw_w, vb[3] * draw_h)
            def semantic_rect(key: str, fallback: tuple[float, float, float, float]) -> Rect:
                sx, sy, sw, sh = _rect(placement.get(key), fallback)
                return Rect(draw.x + sx * draw_w, draw.y + sy * draw_h, sw * draw_w, sh * draw_h)

            base_rect = semantic_rect("base_bounds", (vb[0] + vb[2] * 0.25, vb[1] + vb[3] * 0.72, vb[2] * 0.5, vb[3] * 0.28))
            support_rect = semantic_rect("support_bounds", _rect(placement.get("base_bounds"), (vb[0] + vb[2] * 0.25, vb[1] + vb[3] * 0.72, vb[2] * 0.5, vb[3] * 0.28)))
            foliage_rect = semantic_rect("foliage_bounds", vb)
            interaction_rect = semantic_rect("interaction_bounds", vb)
            motion = max(4.0, visible_w * 0.045)
            hit = interaction_rect.expanded(motion + max(5.0, visible_w * 0.05), max(5.0, visible_h * 0.025))
            default_contact = {
                "pot": (0.52, 0.045),
                "dirt_mound": (0.68, 0.04),
                "direct_soil": (0.42, 0.04),
                "legacy": (0.56, 0.055),
            }.get(base_type, (0.56, 0.055))
            contact = placement.get("contact_shadow", default_contact)
            if not isinstance(contact, (list, tuple)) or len(contact) != 2:
                contact = default_contact
            contact_w = support_rect.width * _number(contact[0], 0.78, 0.35, 0.95)
            contact_h = max(2.0, support_rect.width * _number(contact[1], 0.055, 0.035, 0.10))
            footprint = Rect(base_x - contact_w * 0.50, base_y - contact_h * 0.38, contact_w, contact_h)
            if bed.shadow_plane:
                shadow_plane = tuple((width * point[0], height * point[1]) for point in bed.shadow_plane)
            else:
                shadow_plane = (
                    (contact_plane.x, contact_plane.y),
                    (contact_plane.right, contact_plane.y),
                    (contact_plane.right, contact_plane.bottom),
                    (contact_plane.x, contact_plane.bottom),
                )
            cast_width = contact_w * 1.08
            cast_height = max(2.5, contact_h * 1.45)
            surface_light_direction = bed.light_direction or light_direction
            cast_dx = surface_light_direction[0] * support_rect.width
            cast_dy = surface_light_direction[1] * support_rect.width * 0.35
            cast_shadow = Rect(
                base_x - cast_width * 0.52 + cast_dx,
                base_y - cast_height * 0.42 + cast_dy,
                cast_width,
                cast_height,
            )
            integration = theme_integration_profile(
                surface_theme,
                bed.shadow_depth,
                base_x / width,
                base_y / height,
                key_light_origin,
                appearance,
            )
            lighting = PlantLighting(
                contrast=float(integration["contrast"]),
                saturation=float(integration["saturation"]),
                exposure=float(integration["exposure"]),
                tint=str(integration["tint"]),
                tint_alpha=float(integration["tint_alpha"]),
                light_amount=float(integration["light_amount"]),
                key_strength=float(integration.get("key_strength", 0.0)),
                base_ao=float(integration.get("base_ao", 0.0)),
            )
            resolved_support_line = tuple((width * point[0], height * point[1]) for point in bed.support_line)
            grounding = GroundingPlan(
                contact_shadow=footprint,
                cast_shadow=cast_shadow,
                shadow_plane=shadow_plane,
                shadow_direction=surface_light_direction,
                contact_opacity=bed.shadow_opacity,
                cast_opacity=bed.shadow_opacity * 0.40,
                row=bed.shadow_depth,
                surface_kind=bed.surface_kind,
                support_line=resolved_support_line,
                contact_color=bed.shadow_color or str(appearance.get("contact_shadow_color", "#1c1b19")),
                cast_color=bed.shadow_color or str(appearance.get("cast_shadow_color", "#23201d")),
                lighting=lighting,
            )
            bed_width = max(32.0, width * bed.footprint[0])
            bed_height = max(12.0, height * bed.footprint[1])
            bed_footprint = Rect(base_x - bed_width / 2, base_y - bed_height / 2, bed_width, bed_height)
            # Normal-mode interaction follows the declared visible artwork
            # bounds. Garden-bed targets are handled separately in rearrange
            # mode, so transparent margins and nearby empty soil do not steal
            # hover/clicks from a visually topmost plant.
            hit_center_x = hit.x + hit.width / 2
            hit_center_y = hit.y + hit.height / 2
            hit_width, hit_height = max(44.0, hit.width), max(44.0, hit.height)
            hit = Rect(
                hit_center_x - hit_width / 2,
                hit_center_y - hit_height / 2,
                hit_width,
                hit_height,
            )
            label_anchor = (width * bed.label_anchor[0], height * bed.label_anchor[1])
            slot_envelope = envelope_for(bed, placement)
            control_width = min(148.0, max(74.0, bed_width * 0.92))
            control_rect = Rect(label_anchor[0] - control_width / 2, label_anchor[1] - 22, control_width, 44)
            protected = status_overlay_rect(
                width,
                protected=protected_status,
                surface_context=surface_context,
            ) or Rect(0, 0, 0, 0)
            protected_hits = ("status",) if visible.intersects(protected) else ()
            slot_reasons = reasons.get(slot, set()) if reasons else set()
            slot_warnings = set(warning_map.get(slot, set())) if warning_map else set()
            if base_type not in {"pot", "dirt_mound", "direct_soil"} or not has_semantic_base or not has_semantic_support:
                slot_warnings.add("legacy visible-height fallback")
            fit_scale = group_scale * slot_scale
            target_width = ideal_scale * depth_scale * vessel_multiplier * asset_correction * visual_correction
            measured_width = visible.width if base_type == "direct_soil" else support_rect.width
            target_error = abs(measured_width - target_width) / max(1.0, target_width)
            result.append(PlantPlacement(slot, draw, visible, hit, footprint, base_y,
                                         Rect(visible.x, visible.y, visible.width, min(24.0, visible.height)),
                                         final_scale,
                                         bed_footprint, label_anchor, base_y,
                                         base_rect, support_rect, foliage_rect, control_rect,
                                         final_scale, ideal_scale, depth_scale,
                                         vessel_multiplier, asset_correction, fit_scale, target_error,
                                         protected_hits,
                                         ", ".join(sorted(slot_reasons)) if slot_reasons else "preferred-anchor",
                                         tuple(sorted(slot_warnings)),
                                         bed.surface_id,
                                         contact_plane,
                                         bed.shadow_depth,
                                         bed.shadow_opacity,
                                         bed.occlusion_id,
                                         slot_envelope,
                                         (base_x, base_y),
                                         str(placement.get("layout_family", "standard")),
                                         visual_correction,
                                         bool(placement.get("release_layout_candidate", False)),
                                         grounding,
                                         bed.surface_kind,
                                         bed.allowed_base_types,
                                         bed.depth_band))
        return result

    adjustments: dict[int, tuple[float, float, float]] = {}
    for slot, item, bed, _vb, _anchor in specs:
        placement = item.get("placement", {}) if isinstance(item, dict) else {}
        family = str(placement.get("layout_family", "standard"))
        spacing = {"compact": 0.0025, "standard": 0.007, "expanded": 0.018}.get(family, 0.007)
        spacing *= _number(placement.get("lateral_spacing_multiplier"), 1.0, 0.8, 1.35)
        # One-, two-, and three-plant compositions have purpose-built centered
        # anchors.  Stage-aware spreading is only needed at dense layouts.
        if count < 4:
            spacing = 0.0
        surface_id = str(bed.surface_id)
        # Every named Dusk surface is a discrete painted planting spot, not an
        # abstract row coordinate. Keep the plant's semantic support centered
        # on that spot. Canopy fitting may change scale, but must never slide a
        # pot or dirt mound toward a rim to manufacture extra spacing.
        fixed_surface_center = bool(bed.surface_id)
        if fixed_surface_center:
            spacing = 0.0
        direction = -1.0 if "left" in surface_id or (not surface_id and bed.x < 0.42) else 1.0 if "right" in surface_id or (not surface_id and bed.x > 0.58) else 0.0
        surface_x_overrides = placement.get("surface_x_offsets", {})
        surface_y_overrides = placement.get("surface_y_offsets", {})
        x_overrides = placement.get("slot_x_offsets", [])
        y_overrides = placement.get("slot_y_offsets", [])
        x_override = (
            _number(surface_x_overrides.get(surface_id), 0.0, -0.06, 0.06)
            if isinstance(surface_x_overrides, dict) and surface_id in surface_x_overrides
            else _number(x_overrides[slot], 0.0, -0.06, 0.06)
            if isinstance(x_overrides, (list, tuple)) and len(x_overrides) > slot
            else 0.0
        )
        y_override = (
            _number(surface_y_overrides.get(surface_id), 0.0, -0.03, 0.03)
            if isinstance(surface_y_overrides, dict) and surface_id in surface_y_overrides
            else _number(y_overrides[slot], 0.0, -0.03, 0.03)
            if isinstance(y_overrides, (list, tuple)) and len(y_overrides) > slot
            else 0.0
        )
        base_type = str(placement.get("base_type", "legacy"))
        # Dirt mounds have a wider semantic support than pots. At dense
        # six-bed layouts, normalize that support modestly so a small direct-
        # soil stage does not read as a larger physical planting base merely
        # because neighboring potted canopies required local fitting.
        initial_scale = 0.95 if count >= 4 and base_type == "dirt_mound" else 1.0
        adjustments[slot] = (
            initial_scale,
            0.0 if fixed_surface_center else direction * width * spacing + width * x_override,
            0.0 if bed.surface_id else height * y_override,
        )
    reasons: dict[int, set[str]] = {slot: set() for slot in adjustments}
    warning_map: dict[int, set[str]] = {slot: set() for slot in adjustments}
    expanded_slots = {
        slot
        for slot, item, _bed, _vb, _anchor in specs
        if str((item.get("placement") or {}).get("layout_family", "standard")) == "expanded"
    }
    group_scale = 1.0
    protected = status_overlay_rect(
        width,
        protected=protected_status,
        surface_context=surface_context,
    ) or Rect(0, 0, 0, 0)

    def adjust(slot: int, *, scale_by: float = 1.0, dx: float = 0.0, dy: float = 0.0, reason: str) -> bool:
        current_scale, current_x, current_y = adjustments[slot]
        # At five/six-plant density in genuinely narrow Dusk scenes, unusually
        # wide Flowering/Rare canopies need a little extra local fit room. This
        # is selective (only a colliding sprite is reduced) and comes after
        # anchor, perspective, spacing, and envelope placement.
        minimum_local_scale = (
            responsive_interpolate(width, 660, 780, 0.74, 0.84)
            if enforce_slot_envelopes and count >= 4
            else 0.92
        )
        next_scale = max(minimum_local_scale, current_scale * scale_by)
        x_limit = width * (
            0.07 if count >= 4 and slot in expanded_slots
            else 0.07 if count >= 4
            else 0.03
        )
        bed = bed_anchors[slot]
        next_x = current_x if bed.surface_id else max(-x_limit, min(x_limit, current_x + dx))
        next_y = (
            current_y
            if bed.surface_id
            else max(-height * 0.02, min(height * 0.08, current_y + dy))
        )
        changed = (next_scale, next_x, next_y) != (current_scale, current_x, current_y)
        adjustments[slot] = (next_scale, next_x, next_y)
        if changed:
            reasons[slot].add(reason)
        return changed

    def finish(rows: list[PlantPlacement]) -> list[PlantPlacement]:
        resolved: list[PlantPlacement] = []
        compact_readable_art = responsive_interpolate(
            width,
            440,
            520,
            22.0,
            33.0,
        )
        readable_art = responsive_interpolate(
            width,
            680,
            760,
            compact_readable_art,
            42.0,
        )
        placed_controls: list[Rect] = []
        severe_by_slot: dict[int, set[str]] = {row.slot_index: set() for row in rows}
        active_rows = [row for row in rows if row.slot_index in active_slots]
        for index, first in enumerate(active_rows):
            for second in active_rows[index + 1:]:
                if first.base_rect.intersects(second.base_rect):
                    severe_by_slot[first.slot_index].add("unresolved base overlap")
                    severe_by_slot[second.slot_index].add("unresolved base overlap")
                canopy_ratio = first.foliage_rect.intersection_area(second.foliage_rect) / max(
                    1.0, min(first.foliage_rect.area, second.foliage_rect.area)
                )
                if canopy_ratio > 0.60:
                    severe_by_slot[first.slot_index].add("foliage overlap above policy")
                    severe_by_slot[second.slot_index].add("foliage overlap above policy")
                for canopy, base_owner in ((first, second), (second, first)):
                    # A rear plant is painted first, so its foliage cannot
                    # visually cover the later foreground pot even when their
                    # semantic rectangles intersect. Only later/on-top plants
                    # can obscure an earlier plant's base.
                    if canopy.z_depth < base_owner.z_depth:
                        continue
                    base_coverage = canopy.foliage_rect.intersection_area(base_owner.base_rect) / max(
                        1.0, base_owner.base_rect.area
                    )
                    # A foreground canopy is expected to pass in front of a
                    # rear plant in this deliberately staggered perspective.
                    # Foliage bounds are rectangular and include substantial
                    # transparent/irregular silhouette space, so reserve the
                    # strict limit for plants on the same depth plane.
                    base_limit = 0.86 if abs(canopy.z_depth - base_owner.z_depth) >= height * 0.04 else 0.25
                    if base_coverage > base_limit:
                        severe_by_slot[canopy.slot_index].add("neighbor base obscured")
                        severe_by_slot[base_owner.slot_index].add("neighbor base obscured")
        for row in rows:
            obstacles = [
                other.foliage_rect.expanded(3, 2) for other in rows
                if other.slot_index in active_slots
            ] + placed_controls
            control = bed_badge_rect(row, "Move here", width, height, obstacles)
            placed_controls.append(control)
            strict = enforce_slot_envelopes and row.release_layout_candidate
            warnings = set(row.validation_warnings)
            if strict:
                warnings |= severe_by_slot.get(row.slot_index, set())
            else:
                warnings -= {
                    "unresolved base overlap",
                    "foliage overlap above policy",
                    "neighbor base obscured",
                    "slot envelope intrusion",
                    "below readable minimum",
                }
            # Direct-soil Seed/Sprout silhouettes are intentionally compact;
            # holding them to the mature-canopy minimum would erase the early
            # growth progression. Keep a small but explicit UI-size floor.
            row_readable_art = (
                min(readable_art, 18.0)
                if row.layout_family == "compact" and row.allowed_base_types == ("direct_soil",)
                else readable_art
            )
            if strict and row.slot_index in active_slots and max(row.visible.width, row.visible.height) < row_readable_art:
                warnings.add("below readable minimum")
            if row.slot_index in active_slots and (row.base_rect.intersects(protected) or row.foliage_rect.intersects(protected)):
                warnings.add("protected-region intrusion")
            if strict and row.slot_index in active_slots and count >= 4:
                inside = row.visible.intersection_area(row.slot_envelope)
                if inside / max(1.0, row.visible.area) < 0.88:
                    warnings.add("slot envelope intrusion")
            resolved.append(replace(row, control_rect=control, validation_warnings=tuple(sorted(warnings))))
        return sorted(resolved, key=lambda plant: plant.z_depth)

    # Preferred anchors first; then deterministic per-species scale/offset
    # corrections. Base intersections are forbidden. Foliage may overlap by up
    # to 12% when depth ordering makes that overlap read naturally.
    for iteration in range(32):
        result = build(group_scale, adjustments, reasons, warning_map)
        changed = False
        active_result = [row for row in result if row.slot_index in active_slots]
        for row in active_result:
            margin_x = max(4.0, row.visible.width * 0.025)
            if row.visible.x < left:
                changed |= adjust(row.slot_index, dx=left - row.visible.x + margin_x, reason="scene-edge offset")
            elif row.visible.right > right:
                changed |= adjust(row.slot_index, dx=right - row.visible.right - margin_x, reason="scene-edge offset")
            if row.visible.y < 0:
                changed |= adjust(row.slot_index, dy=-row.visible.y + 4, reason="scene-edge offset")
            elif row.visible.bottom > height:
                changed |= adjust(row.slot_index, dy=height - row.visible.bottom - 3, reason="scene-edge offset")
            if row.foliage_rect.intersects(protected):
                move_right = protected.right - row.foliage_rect.x + 6
                move_down = protected.bottom - row.foliage_rect.y + 5
                if move_right <= width * 0.075:
                    changed |= adjust(row.slot_index, dx=move_right, reason="status exclusion")
                else:
                    changed |= adjust(row.slot_index, dy=move_down, scale_by=0.98, reason="status exclusion")
            if count >= 4 and enforce_slot_envelopes:
                envelope = row.slot_envelope
                if row.visible.width > envelope.width:
                    changed |= adjust(
                        row.slot_index,
                        scale_by=max(0.92, envelope.width / max(1.0, row.visible.width)),
                        reason="slot envelope fit",
                    )
                elif row.visible.x < envelope.x:
                    changed |= adjust(row.slot_index, dx=envelope.x - row.visible.x + 2, reason="slot envelope offset")
                elif row.visible.right > envelope.right:
                    changed |= adjust(row.slot_index, dx=envelope.right - row.visible.right - 2, reason="slot envelope offset")

        for index, first in enumerate(active_result):
            for second in active_result[index + 1:]:
                if first.base_rect.intersects(second.base_rect):
                    overlap = first.base_rect.intersection_area(second.base_rect)
                    push = max(4.0, min(18.0, overlap / max(1.0, min(first.base_rect.height, second.base_rect.height))))
                    first_center = first.base_rect.x + first.base_rect.width / 2
                    second_center = second.base_rect.x + second.base_rect.width / 2
                    direction = -1.0 if first_center <= second_center else 1.0
                    changed |= adjust(first.slot_index, dx=direction * push / 2, scale_by=0.985, reason="base separation")
                    changed |= adjust(second.slot_index, dx=-direction * push / 2, scale_by=0.985, reason="base separation")
                    continue
                for canopy, base_owner in ((first, second), (second, first)):
                    base_coverage = canopy.foliage_rect.intersection_area(base_owner.base_rect) / max(
                        1.0, base_owner.base_rect.area
                    )
                    base_limit = 0.86 if abs(canopy.z_depth - base_owner.z_depth) >= height * 0.04 else 0.25
                    if base_coverage > base_limit:
                        canopy_center = canopy.foliage_rect.x + canopy.foliage_rect.width / 2
                        base_center = base_owner.base_rect.x + base_owner.base_rect.width / 2
                        direction = -1.0 if canopy_center <= base_center else 1.0
                        changed |= adjust(
                            canopy.slot_index,
                            scale_by=0.97,
                            # After seating the rear row on the lower slab
                            # lip, preserve rear-pot readability with lateral
                            # separation instead of a whole-garden shrink.
                            dx=direction * (
                                4.5
                                if abs(canopy.z_depth - base_owner.z_depth) >= height * 0.04
                                else 3.0
                            ),
                            reason="neighbor base visibility",
                        )
                overlap = first.foliage_rect.intersection_area(second.foliage_rect)
                denominator = max(1.0, min(first.foliage_rect.area, second.foliage_rect.area))
                ratio = overlap / denominator
                allowed = 0.12 if abs(first.z_depth - second.z_depth) >= height * 0.04 else 0.08
                if ratio > allowed:
                    larger = first if first.foliage_rect.area >= second.foliage_rect.area else second
                    smaller = second if larger is first else first
                    larger_center = larger.foliage_rect.x + larger.foliage_rect.width / 2
                    smaller_center = smaller.foliage_rect.x + smaller.foliage_rect.width / 2
                    direction = -1.0 if larger_center <= smaller_center else 1.0
                    changed |= adjust(larger.slot_index, scale_by=0.975, dx=direction * 3.0, reason="foliage fit")

        # Reserve compact move badges during the same fitting pass.  If the
        # best control position is still blocked, reduce the blocking plant
        # locally before considering a whole-garden shrink.
        if reserve_move_controls:
            for row in active_result:
                obstacles = [other.foliage_rect.expanded(3, 2) for other in active_result]
                badge = bed_badge_rect(row, "Move here", width, height, obstacles)
                blockers = [other for other in active_result if badge.intersects(other.foliage_rect.expanded(3, 2))]
                for blocker in blockers:
                    blocker_center = blocker.foliage_rect.y + blocker.foliage_rect.height / 2
                    badge_center = badge.y + badge.height / 2
                    vertical_nudge = -3.0 if blocker_center <= badge_center else 3.0
                    changed |= adjust(
                        blocker.slot_index, scale_by=0.97, dy=vertical_nudge,
                        reason="control exclusion",
                    )

        if not changed:
            return finish(result)

    final = build(group_scale, adjustments, reasons, warning_map)
    active_final = [row for row in final if row.slot_index in active_slots]
    for index, first in enumerate(active_final):
        for second in active_final[index + 1:]:
            if first.base_rect.intersects(second.base_rect):
                warning_map[first.slot_index].add("unresolved base overlap")
                warning_map[second.slot_index].add("unresolved base overlap")
            ratio = first.foliage_rect.intersection_area(second.foliage_rect) / max(
                1.0, min(first.foliage_rect.area, second.foliage_rect.area)
            )
            # Alpha-backed garden art is highly irregular; these rectangular
            # foliage bounds are a coarse crowding preflight, not a claim that
            # every transparent pixel inside the rectangle is painted.
            allowed = 0.78 if abs(first.z_depth - second.z_depth) >= height * 0.04 else 0.60
            if ratio > allowed:
                warning_map[first.slot_index].add("foliage overlap above policy")
                warning_map[second.slot_index].add("foliage overlap above policy")
            for canopy, base_owner in ((first, second), (second, first)):
                base_coverage = canopy.foliage_rect.intersection_area(base_owner.base_rect) / max(
                    1.0, base_owner.base_rect.area
                )
                base_limit = 0.86 if abs(canopy.z_depth - base_owner.z_depth) >= height * 0.04 else 0.25
                if base_coverage > base_limit:
                    warning_map[canopy.slot_index].add("neighbor base obscured")
                    warning_map[base_owner.slot_index].add("neighbor base obscured")
    return finish(build(group_scale, adjustments, reasons, warning_map))


def compact_plant_layout(width: float, height: float, plants: Iterable[dict[str, Any]],
                         planting_zone: dict[str, Any] | None = None) -> list[PlantPlacement]:
    """Lay out a snapshot on the exact same normalized bed anchors as the dashboard."""
    items = repair_unique_slot_items(plants)
    if not items:
        return []
    by_slot: dict[int, dict[str, Any]] = {}
    for index, item in enumerate(items):
        slot = max(0, min(5, int(item.get("slot_index", index))))
        normalized = dict(item)
        by_slot[slot] = normalized
    stable_items = [
        plant_layout_item(by_slot.get(slot, {}), slot)
        for slot in range(6)
    ]
    rows = plant_layout(
        width,
        height,
        stable_items,
        planting_zone,
        surface_context="home",
        composition_count=len(items),
        reserve_move_controls=False,
    )
    return [row for row in rows if row.slot_index in by_slot]


def slot_layout(width: float, height: float, slot_count: int,
                planting_zone: dict[str, Any] | None = None) -> list[PlantPlacement]:
    """Return the stable composition-safe positions for unlocked garden slots."""
    count = max(0, min(6, int(slot_count)))
    return plant_layout(
        width,
        height,
        [{"slot_index": index} for index in range(count)],
        planting_zone,
        composition_count=count,
    )


@dataclass(frozen=True)
class BedInteractionState:
    """One semantic and visual projection for a garden bed interaction."""

    slot_index: int
    state: str
    label: str
    pointer_enabled: bool
    occupied: bool


def bed_interaction_state(
    slot_index: int,
    *,
    origin_slot: int | None,
    destination_slot: int | None,
    unlocked_slots: int,
    occupied_slots: set[int],
    occupant_names: dict[int, str] | None = None,
    starter_placement: bool = False,
) -> BedInteractionState:
    """Resolve copy, state, and pointer eligibility without scene duplication."""

    slot = int(slot_index)
    unlocked = max(0, min(6, int(unlocked_slots)))
    occupied = slot in occupied_slots
    names = occupant_names or {}
    if slot >= unlocked:
        return BedInteractionState(slot, "locked", "Locked", False, occupied)
    if slot == origin_slot:
        return BedInteractionState(slot, "current", "Current bed", False, occupied)
    selected = slot == destination_slot
    if starter_placement:
        label = f"Bed {slot + 1} selected" if selected else "Available"
        return BedInteractionState(
            slot,
            "selected" if selected else "available",
            label,
            True,
            occupied,
        )
    if occupied:
        occupant = str(names.get(slot) or "plant").strip()
        label = f"Swap with {occupant}"
    else:
        label = "Move here"
    return BedInteractionState(
        slot,
        "selected" if selected else "available",
        label,
        True,
        occupied,
    )


def move_badge_label(
    slot_index: int,
    *,
    origin_slot: int | None,
    destination_slot: int | None,
    unlocked_slots: int,
    occupied_slots: set[int],
    occupant_names: dict[int, str] | None = None,
) -> tuple[str, str]:
    """Return compact painted copy plus a semantic bed state."""
    state = bed_interaction_state(
        slot_index,
        origin_slot=origin_slot,
        destination_slot=destination_slot,
        unlocked_slots=unlocked_slots,
        occupied_slots=occupied_slots,
        occupant_names=occupant_names,
    )
    return state.label, state.state


def move_target_state(
    slot_index: int | None,
    *,
    origin_slot: int | None,
    valid_destination_slots: Iterable[int],
    unlocked_slots: int,
) -> str:
    """Return the visual/input state for a Move-mode garden space.

    The scene deliberately distinguishes an unlocked-but-disallowed space from
    a locked one. Both reject placement, but only the latter should explain
    that the learner has not unlocked the space yet.
    """
    if slot_index is None:
        return "outside"
    if slot_index == origin_slot:
        return "current"
    if slot_index in set(valid_destination_slots):
        return "valid"
    if slot_index >= max(0, min(6, int(unlocked_slots))):
        return "locked"
    return "unavailable"


def bed_badge_rect(
    placement: PlantPlacement,
    label: str,
    width: float,
    height: float,
    obstacles: Iterable[Rect] = (),
    *,
    canvas_bounds: Rect | None = None,
) -> Rect:
    """Place a compact badge from its dedicated anchor without covering plants."""
    # These controls are painted over a detailed scene and must remain legible
    # at Anki's supported display scales.  Reserve enough logical width for the
    # complete semantic label instead of relying on painter clipping.
    badge_width = max(52.0, min(150.0, 18.0 + len(label) * 6.0))
    badge_height = 26.0
    anchor_x, anchor_y = placement.label_anchor
    candidates = (
        Rect(anchor_x - badge_width / 2, anchor_y - badge_height / 2, badge_width, badge_height),
        Rect(anchor_x - badge_width / 2, placement.bed_footprint.bottom + 6, badge_width, badge_height),
        Rect(anchor_x - badge_width / 2, placement.bed_footprint.y - badge_height - 8, badge_width, badge_height),
        Rect(anchor_x - badge_width / 2, placement.visible.y - badge_height - 7, badge_width, badge_height),
        Rect(placement.bed_footprint.x - badge_width - 8, placement.depth - badge_height / 2, badge_width, badge_height),
        Rect(placement.bed_footprint.right + 8, placement.depth - badge_height / 2, badge_width, badge_height),
        Rect(placement.bed_footprint.x - badge_width - 6, placement.visible.y - badge_height * 0.35, badge_width, badge_height),
        Rect(placement.bed_footprint.right + 6, placement.visible.y - badge_height * 0.35, badge_width, badge_height),
    )
    safe_width = max(1.0, float(width))
    safe_height = max(1.0, float(height))
    safe = (
        canvas_bounds.clipped_to(Rect(0.0, 0.0, safe_width, safe_height))
        if isinstance(canvas_bounds, Rect)
        else Rect(0.0, 0.0, safe_width, safe_height)
    )
    left = safe.x + 4.0
    top = safe.y + 4.0
    right = safe.right - 4.0
    bottom = safe.bottom - 4.0
    blocked = list(obstacles)
    for candidate in candidates:
        clamped = Rect(
            max(left, min(candidate.x, right - candidate.width)),
            max(top, min(candidate.y, bottom - candidate.height)),
            candidate.width,
            candidate.height,
        )
        if not any(clamped.intersects(obstacle) for obstacle in blocked):
            return clamped

    # Dense gardens can block every local candidate even though a clear lane
    # still exists between silhouettes. Search obstacle edges deterministically
    # before accepting any overlap; this remains cheap (a few hundred bounded
    # candidates) and keeps rearrange controls off both plants and one another.
    x_positions = {
        left,
        right - badge_width,
        anchor_x - badge_width / 2,
    }
    y_positions = {
        top,
        bottom - badge_height,
        anchor_y - badge_height / 2,
        placement.visible.y - badge_height - 6.0,
    }
    for obstacle in blocked:
        x_positions.update({
            obstacle.x - badge_width - 6.0,
            obstacle.x,
            obstacle.right - badge_width,
            obstacle.right + 6.0,
        })
        y_positions.update({
            obstacle.y - badge_height - 6.0,
            obstacle.y,
            obstacle.bottom - badge_height,
            obstacle.bottom + 6.0,
        })

    ranked: list[tuple[float, float, float, Rect]] = []
    for raw_x in x_positions:
        for raw_y in y_positions:
            candidate = Rect(
                max(left, min(raw_x, right - badge_width)),
                max(top, min(raw_y, bottom - badge_height)),
                badge_width,
                badge_height,
            )
            overlaps = [
                candidate.intersection_area(obstacle)
                / max(1.0, min(candidate.area, obstacle.area))
                for obstacle in blocked
            ]
            maximum_overlap = max(overlaps, default=0.0)
            total_overlap = sum(overlaps)
            distance = (
                (candidate.x + candidate.width / 2 - anchor_x) ** 2
                + (candidate.y + candidate.height / 2 - anchor_y) ** 2
            )
            ranked.append((maximum_overlap, total_overlap, distance, candidate))
    return min(ranked, key=lambda row: row[:3])[3]


def requires_native_destination_selector(
    layouts: Iterable[PlantPlacement],
    width: float,
    height: float,
    active_slots: Iterable[int],
) -> bool:
    """Compatibility hook: Move destinations now always remain in-scene.

    Compact scenes use footprint rings and reserve numbered badges for the
    current and keyboard-selected spaces, so no dropdown fallback is needed.
    """
    del layouts, width, height, active_slots
    return False


def smart_card_rect(
    width: float,
    height: float,
    anchor_x: float,
    anchor_y: float,
    card_width: float = 252.0,
    card_height: float = 184.0,
    obstacles: Iterable[Rect] = (),
    planting_top: float | None = None,
    protected_obstacle: Rect | None = None,
) -> tuple[float, float, float, float] | None:
    """Return an anchored card rectangle that never covers its selected plant.

    Candidate order is the product contract: right, left, above, then below.
    Other plants are soft obstacles in a full six-bed composition, but the
    selected plant is always protected. Narrow-layout bottom sheets are handled
    by the caller because they depend on the surrounding native card geometry.
    """
    margin = 12.0
    gap = 12.0
    safe_width, safe_height = max(1.0, width), max(1.0, height)
    card_width = max(136.0, min(card_width, safe_width - 2 * margin))
    card_height = max(132.0, min(card_height, safe_height - 2 * margin))
    candidates = [
        Rect(anchor_x + gap, anchor_y - card_height / 2, card_width, card_height),
        Rect(anchor_x - card_width - gap, anchor_y - card_height / 2, card_width, card_height),
        Rect(anchor_x - card_width / 2, anchor_y - card_height - gap, card_width, card_height),
        Rect(anchor_x - card_width / 2, anchor_y + gap, card_width, card_height),
    ]
    def clamp(r: Rect) -> Rect:
        max_x = max(margin, safe_width - card_width - margin)
        max_y = max(margin, safe_height - card_height - margin)
        return Rect(
            max(margin, min(r.x, max_x)),
            max(margin, min(r.y, max_y)),
            card_width,
            card_height,
        )
    blocked = list(obstacles)
    checked: set[tuple[float, float]] = set()

    def clear(candidate: Rect) -> tuple[float, float, float, float] | None:
        candidate = clamp(candidate)
        key = (round(candidate.x, 4), round(candidate.y, 4))
        if key in checked:
            return None
        checked.add(key)
        if protected_obstacle is not None and candidate.intersects(protected_obstacle):
            return None
        if any(candidate.intersects(obstacle) for obstacle in blocked):
            return None
        return candidate.x, candidate.y, candidate.width, candidate.height

    for candidate in candidates:
        result = clear(candidate)
        if result is not None:
            return result

    # Plant silhouettes vary widely, so anchor-relative candidates alone can
    # miss a clean side lane. Search obstacle edges deterministically before
    # choosing the least-obstructive clamped fallback.
    x_positions = {
        margin,
        safe_width - card_width - margin,
        anchor_x - card_width / 2,
        anchor_x + gap,
        anchor_x - card_width - gap,
    }
    y_positions = {
        margin,
        safe_height - card_height - margin,
        anchor_y - card_height - gap,
        anchor_y + gap,
    }
    if planting_top is not None:
        y_positions.add(float(planting_top) - card_height - gap)
    for obstacle in blocked:
        x_positions.update((obstacle.x - card_width - gap, obstacle.right + gap))
        y_positions.update((obstacle.y - card_height - gap, obstacle.bottom + gap))

    ranked: list[tuple[float, float, float, float]] = []
    for raw_x in x_positions:
        for raw_y in y_positions:
            candidate = clamp(Rect(raw_x, raw_y, card_width, card_height))
            if protected_obstacle is not None and candidate.intersects(protected_obstacle):
                continue
            if any(candidate.intersects(obstacle) for obstacle in blocked):
                continue
            distance = (
                (candidate.x + candidate.width / 2 - anchor_x) ** 2
                + (candidate.y + candidate.height / 2 - anchor_y) ** 2
            )
            ranked.append((distance, candidate.x, candidate.y, candidate.width))
    if not ranked:
        # A dense mature garden may have no completely empty side lane. Keep
        # the selected plant protected and prefer a candidate touching at most
        # one unrelated plant/plot before comparing overlap area and distance.
        fallbacks = [
            clamp(candidate)
            for candidate in candidates
            if protected_obstacle is None
            or not clamp(candidate).intersects(protected_obstacle)
        ]
        if not fallbacks:
            return None

        def obstruction_rank(row: Rect) -> tuple[int, float, float]:
            intersections = [obstacle for obstacle in blocked if row.intersects(obstacle)]
            overlap = sum(row.intersection_area(obstacle) for obstacle in intersections)
            distance = (
                (row.x + row.width / 2 - anchor_x) ** 2
                + (row.y + row.height / 2 - anchor_y) ** 2
            )
            return len(intersections), overlap, distance

        candidate = min(fallbacks, key=obstruction_rank)
        return candidate.x, candidate.y, candidate.width, candidate.height
    _distance, candidate_x, candidate_y, candidate_width = min(ranked)
    return candidate_x, candidate_y, candidate_width, card_height


def hit_test(layouts: list[PlantPlacement], point_x: float, point_y: float) -> int | None:
    for index in range(len(layouts) - 1, -1, -1):
        if layouts[index].hit.contains(point_x, point_y):
            return index
    return None


class PlantInteractionState:
    def __init__(self) -> None:
        self.hovered_id: str | None = None
        self.pinned_id: str | None = None
        self.focused_index = -1
        self.dragged_id: str | None = None
        self.drag_origin_slot: int | None = None
        self.destination_slot: int | None = None
        self.move_mode = False
    @property
    def active_id(self) -> str | None: return self.pinned_id or self.hovered_id
    def reconcile(self, plant_ids: list[str]) -> None:
        valid = set(plant_ids)
        if self.hovered_id not in valid: self.hovered_id = None
        if self.pinned_id not in valid: self.pinned_id = None
        # Starter and Collection placement intentionally begin before the
        # selected plant exists in the scene payload.  A scene refresh must not
        # silently retire that explicit unplaced session; its placement token
        # remains the authority until finish_move() or cancellation invalidates
        # it.  Persisted-plant moves still fail closed when their plant vanishes.
        if self.dragged_id not in valid and self.drag_origin_slot != -1:
            self.cancel_placement()
        self.focused_index = -1 if not plant_ids else min(self.focused_index, len(plant_ids) - 1)
    def hover(self, plant_id: str | None) -> None: self.hovered_id = plant_id
    def toggle_pin(self, plant_id: str | None) -> None:
        self.pinned_id = None if plant_id is None or self.pinned_id == plant_id else plant_id
        if plant_id is not None: self.hovered_id = plant_id
    def dismiss(self) -> None: self.pinned_id = self.hovered_id = None
    @property
    def placing(self) -> bool:
        return self.dragged_id is not None or self.move_mode
    def begin_placement(self, plant_id: str, origin_slot: int, valid_slots: list[int], *, keyboard: bool) -> bool:
        if not plant_id or origin_slot not in valid_slots:
            return False
        self.dragged_id = plant_id
        self.drag_origin_slot = origin_slot
        self.destination_slot = origin_slot
        self.move_mode = keyboard
        self.pinned_id = plant_id
        return True
    def begin_unplaced(self, plant_id: str, valid_slots: list[int]) -> bool:
        if not plant_id or not valid_slots:
            return False
        self.dragged_id = plant_id
        self.drag_origin_slot = -1
        self.destination_slot = valid_slots[0]
        self.move_mode = True
        self.pinned_id = None
        return True
    def cycle_destination(self, valid_slots: list[int], direction: int) -> int | None:
        if not valid_slots or not self.placing:
            return None
        current = self.destination_slot
        index = valid_slots.index(current) if current in valid_slots else 0
        self.destination_slot = valid_slots[(index + direction) % len(valid_slots)]
        return self.destination_slot
    def choose_destination(self, slot_index: int, valid_slots: list[int]) -> bool:
        if not self.placing or slot_index not in valid_slots:
            return False
        self.destination_slot = slot_index
        return True
    def cancel_placement(self) -> None:
        self.dragged_id = None
        self.drag_origin_slot = None
        self.destination_slot = None
        self.move_mode = False
    def complete_placement(self) -> tuple[str, int] | None:
        if self.dragged_id is None or self.destination_slot is None:
            return None
        result = (self.dragged_id, self.destination_slot)
        self.cancel_placement()
        return result
    def cycle_focus(self, plant_ids: list[str], direction: int) -> str | None:
        if not plant_ids: self.focused_index = -1; return None
        self.focused_index = (0 if direction >= 0 else len(plant_ids)-1) if self.focused_index < 0 else (self.focused_index + direction) % len(plant_ids)
        self.hovered_id = plant_ids[self.focused_index]; return self.hovered_id
    def focused_id(self, plant_ids: list[str]) -> str | None:
        return plant_ids[self.focused_index] if 0 <= self.focused_index < len(plant_ids) else None


def chronological_memories(memories: list[Any]) -> list[Any]:
    """Order memories by day while preserving their insertion order within a day."""
    return sorted(list(memories), key=lambda item: str(getattr(item, "occurred_on", "")))


def story_is_just_beginning(memories: list[Any]) -> bool:
    """Return whether planting is the only memory recorded for a plant."""
    return len(memories) == 1 and str(getattr(memories[0], "kind", "")) == "planted"


@dataclass(frozen=True)
class OnboardingDisplay:
    visible: bool
    title: str = ""
    message: str = ""
    action_label: str = ""


def onboarding_display(total_reviews: Any, onboarding_version: Any, *, just_completed: bool = False) -> OnboardingDisplay:
    """Return calm first-use guidance without mutating garden progress."""
    if just_completed:
        return OnboardingDisplay(
            True,
            "Your garden is ready",
            "",
        )
    try:
        version = int(onboarding_version)
    except (TypeError, ValueError):
        version = 0
    if version >= CURRENT_ONBOARDING_VERSION:
        return OnboardingDisplay(False)
    try:
        reviews = max(0, int(total_reviews))
    except (TypeError, ValueError):
        reviews = 0
    if reviews == 0:
        return OnboardingDisplay(
            True,
            "Choose a starter",
            "Pick a free plant for your garden.",
            "Choose starter",
        )
    return OnboardingDisplay(
        True,
        "Choose a starter",
        "Pick a free plant for your garden.",
        "Choose starter",
    )
