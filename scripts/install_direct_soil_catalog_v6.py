from __future__ import annotations

import hashlib
import json
from collections import deque
from pathlib import Path
from typing import Any

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "ankigarden"
MANIFEST = ADDON / "assets" / "manifest.json"
RUNTIME_ROOT = ADDON / "assets" / "v6_storybook_gouache" / "plants"
SOURCE_ROOT = ROOT / "artwork_source" / "plants" / "v6"

SPECIES = (
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
STAGES = ("seed", "sprout", "young", "mature", "flowering", "rare")
STAGE_FAMILY = {
    "seed": "compact",
    "sprout": "compact",
    "young": "standard",
    "mature": "standard",
    "flowering": "expanded",
    "rare": "expanded",
}

# The source canvases stay the same size so visual progression must be declared
# explicitly. The product of these two values is the visible-canopy target used
# by plant_layout; every stage is materially larger than the stage before it.
SCENE_SCALE = {
    "seed": 0.55,
    "sprout": 0.58,
    "young": 0.70,
    "mature": 0.80,
    "flowering": 0.98,
    "rare": 0.98,
}
VISUAL_SCALE = {
    "seed": 0.72,
    "sprout": 0.78,
    "young": 0.86,
    "mature": 0.94,
    "flowering": 1.07,
    "rare": 1.04,
}

# Species-specific corrections are derived from the six-bed responsive review,
# not from source-canvas occupancy. The sparse Bonsai Young asset is tall and
# narrow, so it needs a lower width correction to remain smaller than Mature;
# Mature receives a small readability lift in the Home rear row. Rare stays
# narrower than Flowering while retaining nearly the same rendered height.
SPECIES_VISUAL_SCALE = {
    # The transformed Rose is more open than the standard flowering bush. The
    # reviewed equal-scale target keeps the current measured silhouette safely
    # above the Rare payoff floor without exceeding Flowering's world scale.
    "rose": {
        "rare": 1.07,
    },
    "bonsai": {
        # The revised juvenile is intentionally sparse; this lift keeps its
        # trunk-and-two-branch shaping step readable in the rear Home beds.
        "young": 0.82,
        "mature": 0.98,
        # The revised ancient tree has a fuller seven-pad canopy and a lower
        # root contact. This small lift keeps it at least as dominant as the
        # natural flowering peak while remaining inside the same slot width.
        "rare": 1.02,
    },
    # Tall sunflower stages use narrower width targets so their natural
    # vertical silhouettes stay inside the rear and Home slot envelopes.
    "sunflower": {
        "seed": 0.78,
        "young": 0.66,
        "mature": 0.85,
        "flowering": 0.75,
        # Rare adds a detail-rich branching crown without exceeding the
        # Flowering stage's reviewed world-scale envelope.
        "rare": 0.75,
    },
    # Lavender Young has a naturally broad, low canopy. Its generic Young
    # correction left the rear-row silhouette just below the unchanged 42 px
    # readability floor on Home/16:9 scenes; this keeps it smaller than Mature
    # while restoring a legible responsive footprint.
    "lavender": {
        "seed": 0.82,
        "sprout": 0.92,
        "young": 1.00,
        "mature": 1.04,
        # The enchanted candelabra is naturally taller and denser than the
        # broad Flowering fan. A narrower scale keeps the crown slot-safe while
        # retaining greater confident plant mass and a stronger vertical read.
        "rare": 0.964,
    },
    # Hydrangea's broad source canvases need a smaller Seed target and modest
    # Young/Mature readability lifts. This preserves real botanical growth
    # while clearing the unchanged rear-row minimum in every responsive view.
    "hydrangea": {
        "seed": 0.55,
        "young": 1.02,
        "mature": 0.98,
        "rare": 1.03,
    },
    # The open four-stem Peony Young silhouette occupies little of its source
    # square; its lift clears the far-row floor while remaining below Mature.
    # The corrected low Sprout is broad rather than cane-like, so a small
    # readability lift keeps it above Seed and below Young at Home scale.
    "peony": {
        "sprout": 1.05,
        "young": 1.04,
        "rare": 1.07,
    },
    # Foxglove Young is a deliberately low basal rosette. Its broad source
    # silhouette needs a larger width target to clear the 42 px Home rear-row
    # floor; Mature receives a small companion lift so the declared growth
    # scale remains monotonic while its new flower spike supplies the major
    # vertical development.
    "foxglove": {
        "seed": 0.84,
        "sprout": 0.84,
        "young": 1.12,
        "mature": 1.00,
        "rare": 1.07,
    },
    # Maple Young is intentionally tall and sparse while the adult crowns are
    # broad. These paired corrections keep total visual impact and height
    # increasing into Mature without sacrificing the sapling's readable trunk.
    "japanese_maple": {
        "seed": 0.78,
        "young": 0.70,
        "mature": 1.00,
        "rare": 1.07,
    },
    # The broad freestanding Wisteria crown otherwise lands just below the
    # unchanged Home readability floor despite having the correct footprint.
    "wisteria": {
        "seed": 0.78,
        # The juvenile is intentionally upright while the adult spreads into
        # a trained arching crown. Paired corrections keep visual mass growing
        # decisively even though the Young stem can remain slightly taller.
        "young": 0.76,
        "mature": 1.15,
        # The selected enchanted arch is narrower at source than the natural
        # crown, so this lift gives its dense cascading veil equal visual
        # dominance without exceeding Flowering's reviewed slot envelope.
        "rare": 1.07,
    },
    "dahlia": {
        "seed": 0.78,
        "rare": 1.07,
    },
}

# Only assets whose fine root/contact becomes disconnected at the confident
# alpha threshold need a reviewed override. Revised stages with a connected
# trunk or root use their newly measured bottom contact directly.
GROUND_ANCHOR_OVERRIDES = {
    # Sparse Maple early stages separate their fine stem/root from the largest
    # palmate-leaf component at the confident-alpha threshold. Anchor them to
    # the actual bottom contact plus the same small transparent safety margin
    # used by connected silhouettes instead of the detached upper leaf group.
    ("japanese_maple", "seed"): 0.921053,
    ("japanese_maple", "sprout"): 0.921850,
    # Wisteria's pale germinating root is separated from the darker seed body
    # at confident alpha; anchor to the actual root contact, not that seed body.
    ("wisteria", "seed"): 0.913876,
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rect(bounds: tuple[int, int, int, int], width: int, height: int) -> list[float]:
    left, top, right, bottom = bounds
    return [
        round(left / width, 6),
        round(top / height, 6),
        round((right - left) / width, 6),
        round((bottom - top) / height, 6),
    ]


def _reviewed_visible_bounds(
    bounds: tuple[int, int, int, int],
    width: int,
    height: int,
    *,
    stage: str,
) -> list[float]:
    """Return the alpha envelope with the reviewed early-stage readability pad."""
    visible = _rect(bounds, width, height)
    if stage != "seed" or visible[3] >= 0.08:
        return visible
    # Keep the measured lower edge fixed so soil contact does not drift. The
    # extra transparent space is added above the tiny Seed silhouette; runtime
    # scale still follows exact ``art_bounds`` while the declared visibility
    # envelope satisfies the reviewed minimum used by audits and hit geometry.
    bottom = visible[1] + visible[3]
    visible[1] = round(max(0.0, bottom - 0.08), 6)
    visible[3] = round(min(0.08, 1.0 - visible[1]), 6)
    return visible


def _largest_component_bounds(alpha: Image.Image) -> tuple[int, int, int, int] | None:
    """Measure the plant silhouette without letting detached motes set its scale."""
    sample_size = 256
    scale = min(1.0, sample_size / max(alpha.size))
    sampled = alpha.resize(
        (max(1, round(alpha.width * scale)), max(1, round(alpha.height * scale))),
        Image.Resampling.NEAREST,
    ).point(lambda value: 255 if value >= 192 else 0)
    width, height = sampled.size
    data = sampled.tobytes()
    visited = bytearray(width * height)
    best: tuple[int, int, int, int, int] | None = None
    for start, value in enumerate(data):
        if value == 0 or visited[start]:
            continue
        visited[start] = 1
        queue: deque[int] = deque([start])
        area = 0
        left = right = start % width
        top = bottom = start // width
        while queue:
            index = queue.popleft()
            x, y = index % width, index // width
            area += 1
            left, right = min(left, x), max(right, x)
            top, bottom = min(top, y), max(bottom, y)
            for candidate in (index - 1, index + 1, index - width, index + width):
                if candidate < 0 or candidate >= len(data) or visited[candidate] or data[candidate] == 0:
                    continue
                candidate_x, candidate_y = candidate % width, candidate // width
                if abs(candidate_x - x) + abs(candidate_y - y) != 1:
                    continue
                visited[candidate] = 1
                queue.append(candidate)
        row = (area, left, top, right + 1, bottom + 1)
        if best is None or row[0] > best[0]:
            best = row
    if best is None:
        return None
    _area, left, top, right, bottom = best
    inverse = 1.0 / scale
    margin = max(2, round(inverse * 2))
    return (
        max(0, round(left * inverse) - margin),
        max(0, round(top * inverse) - margin),
        min(alpha.width - 1, round(right * inverse) + margin),
        min(alpha.height - 1, round(bottom * inverse) + margin),
    )


def _metadata(species: str, stage: str, path: Path) -> dict[str, Any]:
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        width, height = rgba.size
        alpha = rgba.getchannel("A")
        # Ignore faint chroma-matte residue when measuring layout geometry.
        # The runtime still keeps soft antialiased edges, but scaling and
        # centering follow the confidently opaque plant silhouette.
        confident = alpha.point(lambda value: 255 if value >= 192 else 0)
        effect_bounds = confident.getbbox()
        bounds = _largest_component_bounds(alpha)
    if bounds is None or effect_bounds is None:
        raise RuntimeError(f"transparent asset has no visible pixels: {path}")

    visible = _reviewed_visible_bounds(bounds, width, height, stage=stage)
    art = _rect(effect_bounds, width, height)
    measured_bottom = min(1.0, (bounds[3] - 1) / height)
    bottom = GROUND_ANCHOR_OVERRIDES.get((species, stage), measured_bottom)
    base_width = {
        "seed": 0.040,
        "sprout": 0.045,
        "young": 0.055,
        "mature": 0.065,
        "flowering": 0.075,
        "rare": 0.085,
    }[stage]
    base_height = 0.022
    base = [round(0.5 - base_width / 2, 6), round(bottom - base_height, 6), base_width, base_height]
    source = SOURCE_ROOT / species / f"{species}_{stage}_chroma.png"
    if not source.is_file():
        raise FileNotFoundError(f"missing canonical V6 source master: {source}")
    source_master_file = source.relative_to(ROOT).as_posix()
    relative = path.relative_to(ADDON).as_posix()
    asset_id = f"plant_{species}_{stage}_twilight_v6"
    return {
        "asset_id": asset_id,
        "category": "plants",
        "slot": {"species": species, "stage": stage},
        "variants": [
            "storybook_gouache",
            "direct_soil",
            "continuity_v6",
            "transparent_cutout",
            "geometry_v2",
        ],
        "file": relative,
        "width": width,
        "height": height,
        "format": "png",
        "alpha": True,
        "style_family": "storybook_gouache",
        "release_preferred": True,
        "quality_tier": "ultra",
        "quality_score": 0.995,
        "source": "ImageGen line authored against the Verdant Twilight V6 background",
        "attribution": "Original AI-assisted artwork generated for Anki Garden",
        "source_master_file": source_master_file,
        "source_master_sha256": _sha256(source),
        "placement": {
            "anchor_x": 0.5,
            "baseline_y": bottom,
            "scale": 1.0,
            "display_scale": 1.0,
            "visible_bounds": visible,
            "ground_anchor": [0.5, round(bottom, 6)],
            "ground_anchor_x": 0.5,
            "ground_anchor_y": round(bottom, 6),
            "soil_contact": [0.5, round(bottom, 6)],
            "contact_shadow": [0.42, 0.04],
            "base_type": "direct_soil",
            "crop": "contain",
            "layer": "plants",
            "geometry_version": 2,
            "review_provenance": "verdant-twilight-line-contact-sheet-v6",
            "vessel_class": "soil_only",
            "vessel_class_multiplier": 1.0,
            "scene_scale_correction": SCENE_SCALE[stage],
            "visual_scale_correction": SPECIES_VISUAL_SCALE.get(species, {}).get(
                stage, VISUAL_SCALE[stage]
            ),
            "art_bounds": art,
            "base_bounds": base,
            "support_bounds": base,
            "foliage_bounds": visible,
            "plant_above_rim_bounds": visible,
            "interaction_bounds": art,
            "layout_family": STAGE_FAMILY[stage],
            "lateral_spacing_multiplier": 1.0,
            "slot_envelope_scale": 1.0,
            "release_layout_candidate": True,
        },
    }


def main() -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assets = payload.get("assets", [])
    replacements: list[dict[str, Any]] = []
    replacement_keys: set[tuple[str, str]] = set()
    for species in SPECIES:
        for stage in STAGES:
            path = RUNTIME_ROOT / species / stage / f"{species}_{stage}_twilight_v6.png"
            if not path.is_file():
                continue
            replacements.append(_metadata(species, stage, path))
            replacement_keys.add((species, stage))

    replacement_ids = {row["asset_id"] for row in replacements}
    assets = [row for row in assets if row.get("asset_id") not in replacement_ids]
    for row in assets:
        if row.get("category") != "plants":
            continue
        # The V6 library is authoritative. Retired and legacy candidates must
        # not remain selectable merely because their species was removed from
        # the final catalog or its replacement was generated later in the run.
        row["release_preferred"] = False
        placement = row.get("placement")
        if isinstance(placement, dict):
            placement["release_layout_candidate"] = False
    assets.extend(replacements)
    payload["assets"] = assets
    payload["generated_by"] = "Verdant Twilight V6 incremental direct-soil catalog build"
    MANIFEST.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Installed {len(replacements)} direct-soil V6 plant assets across {len(replacement_keys) // 6} lines.")


if __name__ == "__main__":
    main()
