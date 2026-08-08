from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "ankigarden"
MANIFEST = ADDON / "assets" / "manifest.json"
GEOMETRY_FIXTURE = ROOT / "tests" / "fixtures" / "approved_asset_geometry_v2.json"
SURFACE_FIXTURE = ROOT / "tests" / "fixtures" / "verdant_dusk_surface_v1.json"
SUPPORTED_FORMATS = {"svg", "png", "webp"}


def audit() -> dict[str, int]:
    payload = json.loads(MANIFEST.read_text("utf-8"))
    rows = payload.get("assets", [])
    fixture_payload = json.loads(GEOMETRY_FIXTURE.read_text("utf-8"))
    approved_geometry = fixture_payload.get("assets", {})
    surface_fixture = json.loads(SURFACE_FIXTURE.read_text("utf-8"))
    expected_surface_profile = {
        key: surface_fixture[key]
        for key in (
            "profile_id", "geometry_version", "theme", "light_direction",
            "variant_breakpoints", "variants",
        )
    }
    found_surface_profile = False
    if fixture_payload.get("geometry_version") != 2 or len(approved_geometry) != 150:
        raise ValueError("approved geometry-v2 fixture must contain exactly 150 assets")
    if not isinstance(rows, list) or not rows:
        raise ValueError("asset manifest is empty")

    seen: set[str] = set()
    asset_ids = {str(row.get("asset_id", "")) for row in rows if isinstance(row, dict)}
    counts: Counter[str] = Counter()
    plant_stages: dict[tuple[str, str], set[str]] = {}
    stage_scales: dict[tuple[str, str], float] = {}
    selected_semantic_pots: dict[tuple[str, str], tuple[float, float]] = {}
    for row in rows:
        rel = str(row.get("file", ""))
        category = str(row.get("category", ""))
        if not rel or not category:
            raise ValueError(f"invalid manifest row: {row!r}")
        if rel in seen:
            raise ValueError(f"duplicate asset path: {rel}")
        seen.add(rel)
        path = ADDON / rel
        if not path.is_file():
            raise FileNotFoundError(path)
        declared_format = str(row.get("format", "")).lower()
        if declared_format not in SUPPORTED_FORMATS or path.suffix.lower() != f".{declared_format}":
            raise ValueError(f"unsupported or mismatched asset format: {rel}")
        if declared_format == "svg":
            root = ET.parse(path).getroot()
            if not root.tag.endswith("svg") or not root.attrib.get("viewBox"):
                raise ValueError(f"SVG lacks a valid viewBox: {rel}")
        elif declared_format == "png":
            png_header = path.read_bytes()[:26]
            if png_header[:8] != b"\x89PNG\r\n\x1a\n":
                raise ValueError(f"invalid PNG signature: {rel}")
            if row.get("alpha") is True and (len(png_header) < 26 or png_header[25] not in {4, 6}):
                raise ValueError(f"PNG declared alpha but has no alpha channel: {rel}")
            if category == "plants":
                with Image.open(path) as image:
                    rgba = image.convert("RGBA")
                    alpha = rgba.getchannel("A")
                    if alpha.getbbox() is None:
                        raise ValueError(f"plant PNG has no visible alpha content: {rel}")
                    if {"continuity_v3", "continuity_v4"}.intersection(row.get("variants", [])):
                        width, height = rgba.size
                        edges = list(alpha.crop((0, 0, width, 1)).getdata())
                        edges += list(alpha.crop((0, height - 1, width, height)).getdata())
                        edges += list(alpha.crop((0, 0, 1, height)).getdata())
                        edges += list(alpha.crop((width - 1, 0, width, height)).getdata())
                        if max(edges) > 0:
                            raise ValueError(f"continuity asset has edge-touching alpha: {rel}")
        elif declared_format == "webp":
            signature = path.read_bytes()[:12]
            if signature[:4] != b"RIFF" or signature[8:] != b"WEBP":
                raise ValueError(f"invalid WebP signature: {rel}")
        if int(row.get("width", 0)) <= 0 or int(row.get("height", 0)) <= 0:
            raise ValueError(f"manifest dimensions are invalid: {rel}")
        fallback_id = str(row.get("fallback_asset_id", ""))
        if fallback_id and fallback_id not in asset_ids:
            raise ValueError(f"missing fallback asset {fallback_id!r}: {rel}")
        placement = row.get("placement")
        if placement is not None:
            if not isinstance(placement, dict):
                raise ValueError(f"invalid placement metadata: {rel}")
            for key in ("anchor_x", "baseline_y", "scale"):
                try:
                    value = float(placement[key])
                except (KeyError, TypeError, ValueError):
                    raise ValueError(f"invalid placement {key}: {rel}")
                if key != "scale" and not 0.0 <= value <= 1.0:
                    raise ValueError(f"placement {key} out of range: {rel}")
                if key == "scale" and not 0.1 <= value <= 2.5:
                    raise ValueError(f"placement scale out of range: {rel}")
            if placement.get("crop") not in {"contain", "cover"} or not placement.get("layer"):
                raise ValueError(f"invalid placement crop/layer: {rel}")
            contact_shadow = placement.get("contact_shadow")
            if contact_shadow is not None:
                if not isinstance(contact_shadow, list) or len(contact_shadow) != 2:
                    raise ValueError(f"invalid contact shadow metadata: {rel}")
                width_ratio, height_ratio = (float(value) for value in contact_shadow)
                if not 0.2 <= width_ratio <= 1.0 or not 0.015 <= height_ratio <= 0.12:
                    raise ValueError(f"contact shadow metadata out of range: {rel}")
        if category in {"plants", "backgrounds", "overlays"}:
            # Every production profile must be resolvable to the complete
            # category contract, including assets that rely on legacy defaults.
            resolved = dict(placement or {})
            if category == "plants":
                resolved.setdefault("visible_bounds", [0.08, 0.04, 0.84, 0.92])
                resolved.setdefault("ground_anchor", [0.5, 0.96])
                resolved.setdefault("display_scale", resolved.get("scale", 1.0))
                resolved.setdefault("base_type", "legacy")
                resolved.setdefault("contact_shadow", [0.56, 0.055])
                required = {"visible_bounds", "ground_anchor", "display_scale", "base_type", "contact_shadow", "layer"}
                explicit = {
                    "visible_bounds", "ground_anchor", "display_scale",
                    "base_type", "contact_shadow", "crop", "layer",
                }
                if not isinstance(placement, dict) or not explicit.issubset(placement):
                    raise ValueError(f"plant lacks explicit placement contract: {rel}")
                visible = placement["visible_bounds"]
                ground = placement["ground_anchor"]
                if not isinstance(visible, list) or len(visible) != 4:
                    raise ValueError(f"invalid visible bounds: {rel}")
                if not isinstance(ground, list) or len(ground) != 2:
                    raise ValueError(f"invalid ground anchor: {rel}")
                semantic_keys = {
                    "art_bounds", "base_bounds", "support_bounds", "foliage_bounds",
                    "plant_above_rim_bounds", "soil_contact", "interaction_bounds",
                }
                has_semantic_bounds = semantic_keys.issubset(placement)
                if int(placement.get("geometry_version", 0)) != 2:
                    raise ValueError(f"bundled plant lacks geometry_version 2: {rel}")
                approved = approved_geometry.get(str(row.get("asset_id", "")))
                if not isinstance(approved, dict):
                    raise ValueError(f"bundled plant is absent from approved geometry fixture: {rel}")
                audited_keys = semantic_keys | {
                    "geometry_version", "review_provenance", "vessel_class",
                    "vessel_class_multiplier", "scene_scale_correction",
                }
                mismatch = sorted(key for key in audited_keys if placement.get(key) != approved.get(key))
                if mismatch:
                    raise ValueError(f"runtime geometry differs from approved fixture for {rel}: {mismatch}")
                if has_semantic_bounds:
                    for semantic_key in (
                        "art_bounds", "base_bounds", "support_bounds", "foliage_bounds",
                        "plant_above_rim_bounds", "interaction_bounds",
                    ):
                        value = placement[semantic_key]
                        if not isinstance(value, list) or len(value) != 4:
                            raise ValueError(f"invalid {semantic_key}: {rel}")
                        x, y, width, height = (float(item) for item in value)
                        if min(x, y, width, height) < 0 or x + width > 1.001 or y + height > 1.001:
                            raise ValueError(f"out-of-range {semantic_key}: {rel}")
                    soil = placement["soil_contact"]
                    base = placement["base_bounds"]
                    support = placement["support_bounds"]
                    if not isinstance(soil, list) or len(soil) != 2:
                        raise ValueError(f"invalid soil contact: {rel}")
                    if not (float(base[0]) <= float(soil[0]) <= float(base[0]) + float(base[2])):
                        raise ValueError(f"soil contact is outside the base: {rel}")
                    if abs((float(base[1]) + float(base[3])) - float(soil[1])) > 0.002:
                        raise ValueError(f"soil contact does not match the pot base: {rel}")
                    if not (float(support[0]) <= float(soil[0]) <= float(support[0]) + float(support[2])):
                        raise ValueError(f"soil contact is outside the lower support: {rel}")
                    if abs((float(support[1]) + float(support[3])) - float(soil[1])) > 0.002:
                        raise ValueError(f"soil contact does not match the lower support: {rel}")
                elif abs((float(visible[1]) + float(visible[3])) - float(ground[1])) > 0.001:
                    raise ValueError(f"ground anchor does not match visible base: {rel}")
                species = str((row.get("slot", {}) or {}).get("species", ""))
                stage = str((row.get("slot", {}) or {}).get("stage", ""))
                family = str(row.get("style_family", "cozy_handpainted"))
                plant_stages.setdefault((family, species), set()).add(stage)
                key = (species, stage)
                scale = float(placement["display_scale"])
                previous = stage_scales.setdefault(key, scale)
                if not has_semantic_bounds and abs(previous - scale) > 0.0001:
                    raise ValueError(f"quality tiers change composition scale for {species}/{stage}: {rel}")
                if has_semantic_bounds and {"continuity_v3", "continuity_v4", "phase2_grounded"}.intersection(row.get("variants", [])):
                    base = placement["support_bounds"]
                    canvas_aspect = float(row["width"]) / float(row["height"])
                    # Renderer-equivalent base width when the normalized canvas
                    # is drawn at one source-height unit. This catches transparent
                    # canvas/aspect changes that the former base_width * display_scale
                    # proxy incorrectly ignored.
                    candidate = (
                        float(row.get("quality_score", 0)),
                        float(base[2]) * canvas_aspect,
                    )
                    current = selected_semantic_pots.get((species, stage))
                    if current is None or candidate[0] > current[0]:
                        selected_semantic_pots[(species, stage)] = candidate
                if stage == "seed":
                    if "seedling_cue" in row or "seedling_anchor" in row:
                        raise ValueError(f"Seed stage still depends on a runtime seedling cue: {rel}")
                    if float(visible[3]) < 0.08:
                        raise ValueError(f"Seed artwork is too small to remain readable: {rel}")
            else:
                resolved.setdefault("focal_point", [0.5, 0.43])
                resolved.setdefault("planting_zone", {"left": 0.08, "right": 0.92, "far_y": 0.62, "near_y": 0.91})
                resolved.setdefault("bed_anchors", [])
                required = {"planting_zone", "bed_anchors", "layer"}
                if category == "backgrounds":
                    required.add("focal_point")
            resolved.setdefault("layer", "plants" if category == "plants" else "background")
            if not required.issubset(resolved):
                raise ValueError(f"resolved production placement metadata incomplete: {rel}")
            if category in {"backgrounds", "overlays"}:
                anchors = resolved["bed_anchors"]
                if not isinstance(anchors, list) or len(anchors) != 6:
                    raise ValueError(f"garden placement must define six beds: {rel}")
                for index, anchor in enumerate(anchors):
                    required_anchor = {"x", "y", "depth", "plant_scale", "footprint", "label_anchor"}
                    if not isinstance(anchor, dict) or not required_anchor.issubset(anchor):
                        raise ValueError(f"bed {index + 1} placement incomplete: {rel}")
                if category == "backgrounds" and row.get("style_family") == "storybook_gouache":
                    profiles = resolved.get("layout_profiles")
                    if not isinstance(profiles, dict) or set(profiles) != {"4:3", "3:2", "16:9", "home"}:
                        raise ValueError(f"storybook background lacks Phase 1 layout profiles: {rel}")
                    for profile_name, profile in profiles.items():
                        compositions = profile.get("compositions") if isinstance(profile, dict) else None
                        if not isinstance(compositions, dict) or set(compositions) != {str(value) for value in range(1, 7)}:
                            raise ValueError(f"layout profile {profile_name} lacks count compositions: {rel}")
                        if any(not isinstance(value, list) or len(value) != 6 for value in compositions.values()):
                            raise ValueError(f"layout profile {profile_name} has incomplete beds: {rel}")
                    surface_profile = resolved.get("surface_profile")
                    if (row.get("slot") or {}).get("theme") == "verdant_dusk":
                        if surface_profile != expected_surface_profile:
                            raise ValueError("Verdant Dusk runtime surfaces differ from the reviewed fixture")
                        found_surface_profile = True
                        for variant_name, variant in surface_profile["variants"].items():
                            if len(variant.get("surfaces", [])) != 6:
                                raise ValueError(f"Dusk {variant_name} must register six surfaces")
                            for key in ("file", "occlusion_file"):
                                variant_path = ADDON / str(variant.get(key, ""))
                                if not variant_path.is_file():
                                    raise FileNotFoundError(variant_path)
                                with Image.open(variant_path) as image:
                                    expected_size = (int(variant["width"]), int(variant["height"]))
                                    if image.size != expected_size:
                                        raise ValueError(
                                            f"Dusk {variant_name} {key} size {image.size} != {expected_size}"
                                        )
                                    if key == "occlusion_file" and image.mode != "RGBA":
                                        raise ValueError(f"Dusk {variant_name} occlusion must be RGBA")
        counts[category] += 1

    if not found_surface_profile:
        raise ValueError("Verdant Dusk reviewed surface profile is not installed")
    expected_stages = {"seed", "sprout", "young", "mature", "flowering", "rare"}
    complete_species = {
        species for (family, species), stages in plant_stages.items()
        if family == "cozy_handpainted" and stages == expected_stages
    }
    if complete_species != {"bonsai", "rose", "cactus", "orchid", "moonflower", "sunbloom", "fern", "ivy"}:
        raise ValueError(f"complete species/stage catalog missing: {sorted(complete_species)}")
    storybook_species = {
        species for (family, species), stages in plant_stages.items()
        if family == "storybook_gouache" and stages == expected_stages
    }
    if storybook_species != {"bonsai", "rose", "cactus", "orchid", "moonflower", "sunbloom", "fern", "ivy"}:
        raise ValueError(f"complete storybook species/stage catalog missing: {sorted(storybook_species)}")
    for species in {key[0] for key in selected_semantic_pots}:
        widths = [selected_semantic_pots[(species, stage)][1] for stage in expected_stages]
        if min(widths) <= 0:
            raise ValueError(f"semantic base width is invalid for {species}: {widths}")
    phase2_species = {"bonsai", "rose", "cactus", "orchid", "moonflower", "fern", "ivy"}
    phase2_selected = {
        key: value for key, value in selected_semantic_pots.items() if key[0] in phase2_species
    }
    if len(phase2_selected) != 42:
        raise ValueError(f"Phase 2 must select 42 semantic potted assets, found {len(phase2_selected)}")
    phase2_widths = [value[1] for value in phase2_selected.values()]
    # Physical normalization divides the target width by each semantic base
    # width before drawing, so the renderer-equivalent result must reproduce
    # the target regardless of canvas aspect or transparent padding.
    canonical_target = 0.155
    normalized_widths = [width * (canonical_target / width) for width in phase2_widths]
    if max(normalized_widths) / min(normalized_widths) > 1.0001:
        raise ValueError(f"normalized physical pot sizes diverge: {normalized_widths}")
    storybook_rows = [
        row for row in rows
        if row.get("category") == "plants" and row.get("style_family") == "storybook_gouache"
    ]
    if len(storybook_rows) != 99 or any(
        not {"art_bounds", "base_bounds", "support_bounds", "foliage_bounds", "plant_above_rim_bounds", "soil_contact", "interaction_bounds"}
        .issubset(row.get("placement", {}))
        for row in storybook_rows
    ):
        raise ValueError("all storybook plants must expose semantic grounded geometry")
    progression = [stage_scales[("rose", stage)] for stage in ("seed", "sprout", "young", "mature", "flowering", "rare")]
    if progression != sorted(progression) or len(set(progression)) != len(progression):
        raise ValueError(f"stage display scales are not deliberately increasing: {progression}")

    expected = {"backgrounds": 78, "decorations": 5, "plants": 150, "ui": 3, "weather": 10, "overlays": 3}
    if dict(counts) != expected:
        raise ValueError(f"asset coverage changed: expected {expected}, got {dict(counts)}")
    return dict(counts)


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True))
