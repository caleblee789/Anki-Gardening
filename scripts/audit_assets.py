from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "ankigarden"
ASSETS = ADDON / "assets"
MANIFEST = ASSETS / "manifest.json"
SURFACE_FIXTURE = ROOT / "tests" / "fixtures" / "verdant_twilight_surface_v6.json"

CURRENT_SPECIES = {
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
}
STAGES = {"seed", "sprout", "young", "mature", "flowering", "rare"}
WEATHER = {
    "sunny",
    "cloudy",
    "fireflies",
    "gentle_rain",
    "breeze",
    "snow_flurry",
    "rainbow_sunshower",
}
SCENERY = (
    "spring",
    "summer",
    "autumn",
    "snowy",
    "rainbow_horizon",
    "halloween",
    "full_moon",
    "eclipse",
)
EXPECTED_COUNTS = {
    "backgrounds": 9,
    "decorations": 1,
    "plants": 60,
    "ui": 7,
    "weather": 7,
}
RUNTIME_ROOTS = (
    "assets/v6_storybook_gouache/",
    "assets/support/",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _alpha_sha256(path: Path) -> str:
    with Image.open(path) as image:
        alpha = image.convert("RGBA").getchannel("A")
        return hashlib.sha256(alpha.tobytes()).hexdigest()


def _asset_references(value: Any) -> set[str]:
    references: set[str] = set()
    if isinstance(value, dict):
        for nested in value.values():
            references.update(_asset_references(nested))
    elif isinstance(value, list):
        for nested in value:
            references.update(_asset_references(nested))
    elif isinstance(value, str) and value.startswith("assets/"):
        references.add(value)
    return references


def _validate_file(row: dict[str, Any]) -> None:
    relative = str(row.get("file", ""))
    if not relative.startswith(RUNTIME_ROOTS):
        raise ValueError(f"asset is outside current runtime roots: {relative}")
    if any(token in relative.lower() for token in ("fallback", "legacy")):
        raise ValueError(f"fallback or legacy asset remains in the catalog: {relative}")
    path = ADDON / relative
    if not path.is_file():
        raise FileNotFoundError(path)
    declared_format = str(row.get("format", "")).lower()
    if declared_format not in {"svg", "png", "webp"}:
        raise ValueError(f"unsupported format for {relative}: {declared_format}")
    if path.suffix.lower() != f".{declared_format}":
        raise ValueError(f"format and extension differ for {relative}")

    width = int(row.get("width", 0))
    height = int(row.get("height", 0))
    if width <= 0 or height <= 0:
        raise ValueError(f"invalid dimensions for {relative}")
    if declared_format == "svg":
        text = path.read_text(encoding="utf-8")
        if "viewBox=" not in text[:500]:
            raise ValueError(f"SVG is missing a viewBox: {relative}")
        return
    with Image.open(path) as image:
        if image.size != (width, height):
            raise ValueError(
                f"manifest dimensions differ for {relative}: {image.size} != {(width, height)}"
            )


def _validate_background(rows: list[dict[str, Any]]) -> None:
    backgrounds = [row for row in rows if row.get("category") == "backgrounds"]
    expected_ids = [
        "bg_verdant_twilight_any_soil_master_v6",
        *(f"bg_{item_id}_any_soil_master_v6" for item_id in SCENERY),
    ]
    if [row.get("asset_id") for row in backgrounds] != expected_ids:
        raise ValueError("the runtime scenery set is incomplete or out of canonical order")
    background = backgrounds[0]
    if background.get("release_preferred") is not True:
        raise ValueError("the V6 background must be release preferred")
    expected_profile = json.loads(SURFACE_FIXTURE.read_text(encoding="utf-8"))
    actual_profile = (background.get("placement") or {}).get("surface_profile")
    if actual_profile != expected_profile:
        raise ValueError("the runtime V6 surface profile differs from the reviewed fixture")
    expected_sizes = {"4:3": (1280, 960), "16:9": (1672, 941), "home": (1942, 809)}
    source_root = "assets/v6_storybook_gouache/backgrounds/verdant_twilight/soil_master"
    for row, item_id in zip(backgrounds[1:], SCENERY):
        slot = row.get("slot") or {}
        if slot.get("season") != item_id or slot.get("weather") != "any":
            raise ValueError(f"scenery slot differs from its catalog id: {item_id}")
        if row.get("placement_ref") != "bg_verdant_twilight_any_soil_master_v6":
            raise ValueError(f"scenery does not inherit the canonical V6 geometry: {item_id}")
        if row.get("placement"):
            raise ValueError(f"scenery may not override canonical V6 placement: {item_id}")
        surface_files = row.get("surface_files")
        if not isinstance(surface_files, dict) or set(surface_files) != set(expected_sizes):
            raise ValueError(f"scenery viewport family is incomplete: {item_id}")
        target_root = f"assets/v6_storybook_gouache/backgrounds/{item_id}/soil_master"
        for variant, expected_size in expected_sizes.items():
            filename_variant = variant.replace(":", "x")
            files = surface_files.get(variant)
            if not isinstance(files, dict):
                raise ValueError(f"scenery surface files are invalid: {item_id}/{variant}")
            expected_file = f"{target_root}/{item_id}_{filename_variant}.webp"
            if files.get("file") != expected_file:
                raise ValueError(f"scenery background path is noncanonical: {item_id}/{variant}")
            with Image.open(ADDON / expected_file) as image:
                if image.size != expected_size:
                    raise ValueError(f"scenery dimensions drifted: {item_id}/{variant}")
            expected_occlusion = f"{target_root}/{item_id}_{filename_variant}_occlusion.webp"
            if files.get("occlusion_file") != expected_occlusion:
                raise ValueError(f"scenery occlusion path is noncanonical: {item_id}/{variant}")
            layers = files.get("occlusion_layers") or {}
            for layer in ("rear", "front"):
                target = f"{target_root}/{item_id}_{filename_variant}_{layer}_occlusion.webp"
                source = f"{source_root}/verdant_twilight_{filename_variant}_{layer}_occlusion.webp"
                if layers.get(layer) != target or _alpha_sha256(ADDON / target) != _alpha_sha256(ADDON / source):
                    raise ValueError(f"scenery {layer} occlusion drifted: {item_id}/{variant}")
            source_combined = f"{source_root}/verdant_twilight_{filename_variant}_occlusion.webp"
            if _alpha_sha256(ADDON / expected_occlusion) != _alpha_sha256(ADDON / source_combined):
                raise ValueError(f"scenery combined occlusion drifted: {item_id}/{variant}")


def _validate_plants(rows: list[dict[str, Any]]) -> None:
    plants = [row for row in rows if row.get("category") == "plants"]
    pairs = {
        (str((row.get("slot") or {}).get("species", "")), str((row.get("slot") or {}).get("stage", "")))
        for row in plants
    }
    expected_pairs = {(species, stage) for species in CURRENT_SPECIES for stage in STAGES}
    if pairs != expected_pairs or len(plants) != len(expected_pairs):
        raise ValueError("the current V6 species/stage catalog is incomplete or duplicated")

    for row in plants:
        species = str((row.get("slot") or {}).get("species", ""))
        stage = str((row.get("slot") or {}).get("stage", ""))
        expected_id = f"plant_{species}_{stage}_twilight_v6"
        expected_file = (
            f"assets/v6_storybook_gouache/plants/{species}/{stage}/"
            f"{species}_{stage}_twilight_v6.webp"
        )
        if row.get("asset_id") != expected_id or row.get("file") != expected_file:
            raise ValueError(f"noncanonical V6 plant entry: {species}/{stage}")
        if row.get("release_preferred") is not True:
            raise ValueError(f"plant is not release preferred: {species}/{stage}")
        variants = row.get("variants", [])
        if "continuity_v6" not in variants or "direct_soil" not in variants:
            raise ValueError(f"plant lacks the V6 direct-soil contract: {species}/{stage}")
        placement = row.get("placement")
        if not isinstance(placement, dict):
            raise ValueError(f"plant lacks placement metadata: {species}/{stage}")
        required = {
            "art_bounds",
            "base_bounds",
            "support_bounds",
            "foliage_bounds",
            "plant_above_rim_bounds",
            "soil_contact",
            "interaction_bounds",
            "ground_anchor",
        }
        if not required.issubset(placement) or placement.get("base_type") != "direct_soil":
            raise ValueError(f"plant placement is incomplete: {species}/{stage}")
        if placement.get("soil_contact") != placement.get("ground_anchor"):
            raise ValueError(f"plant soil contact drifts from its anchor: {species}/{stage}")

        source_relative = str(row.get("source_master_file", ""))
        source = ROOT / source_relative
        if not source.is_file() or _sha256(source) != row.get("source_master_sha256"):
            raise ValueError(f"plant source master is missing or changed: {species}/{stage}")
        with Image.open(ADDON / expected_file) as image:
            if image.mode != "RGBA" or image.size != (1254, 1254):
                raise ValueError(f"plant runtime canvas is invalid: {species}/{stage}")


def _validate_support_assets(rows: list[dict[str, Any]]) -> None:
    decorations = [row for row in rows if row.get("category") == "decorations"]
    if len(decorations) != 1 or decorations[0].get("asset_id") != "decor_lantern":
        raise ValueError("the current bundle must contain only the Lantern decoration")
    if decorations[0].get("file") != "assets/support/decorations/lantern.webp":
        raise ValueError("the Lantern decoration is outside its current support path")

    weather_rows = [row for row in rows if row.get("category") == "weather"]
    observed = Counter(
        (
            str((row.get("slot") or {}).get("weather", "")),
            str(row.get("quality_tier", "")),
        )
        for row in weather_rows
    )
    expected = Counter((weather, "balanced") for weather in WEATHER)
    if observed != expected:
        raise ValueError("weather support assets must contain one automatic balanced overlay per state")

    ui_rows = [row for row in rows if row.get("category") == "ui"]
    expected_ui = {
        "ui_fertilizer_basic": "assets/v6_storybook_gouache/ui/fertilizer_basic.webp",
        "ui_fertilizer_quality": "assets/v6_storybook_gouache/ui/fertilizer_quality.webp",
        "ui_fertilizer_magical": "assets/v6_storybook_gouache/ui/fertilizer_premium.webp",
        "ui_booster_potion": "assets/v6_storybook_gouache/ui/booster_potion.webp",
        "ui_growth_charge_small": "assets/v6_storybook_gouache/ui/growth_charge_small.webp",
        "ui_growth_charge_standard": "assets/v6_storybook_gouache/ui/growth_charge_standard.webp",
        "ui_growth_charge_grand": "assets/v6_storybook_gouache/ui/growth_charge_grand.webp",
    }
    observed_ui = {
        str(row.get("asset_id", "")): str(row.get("file", "")) for row in ui_rows
    }
    if observed_ui != expected_ui:
        raise ValueError("the V6 catalog item artwork set is incomplete or noncanonical")
    if any(row.get("alpha") is not True for row in ui_rows):
        raise ValueError("catalog item artwork must retain transparency")
    for row in ui_rows:
        path = ADDON / str(row["file"])
        with Image.open(path) as image:
            if image.mode != "RGBA":
                raise ValueError(f"catalog item artwork is not RGBA: {row['asset_id']}")
            alpha_min, alpha_max = image.getchannel("A").getextrema()
            if alpha_min != 0 or alpha_max == 0:
                raise ValueError(
                    f"catalog item artwork lacks usable transparency: {row['asset_id']}"
                )


def audit() -> dict[str, int]:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows = payload.get("assets")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("asset manifest rows must be objects")

    counts = Counter(str(row.get("category", "")) for row in rows)
    if dict(counts) != EXPECTED_COUNTS:
        raise ValueError(f"asset coverage changed: expected {EXPECTED_COUNTS}, got {dict(counts)}")
    asset_ids = [str(row.get("asset_id", "")) for row in rows]
    files = [str(row.get("file", "")) for row in rows]
    if len(asset_ids) != len(set(asset_ids)) or "" in asset_ids:
        raise ValueError("asset IDs must be unique and non-empty")
    if len(files) != len(set(files)) or "" in files:
        raise ValueError("primary asset paths must be unique and non-empty")
    if any("fallback_asset_id" in row for row in rows):
        raise ValueError("fallback catalog links are not allowed in the current bundle")

    for row in rows:
        _validate_file(row)
    _validate_background(rows)
    _validate_plants(rows)
    _validate_support_assets(rows)

    referenced = _asset_references(payload)
    missing = sorted(relative for relative in referenced if not (ADDON / relative).is_file())
    if missing:
        raise FileNotFoundError(f"referenced runtime assets are missing: {', '.join(missing)}")
    on_disk = {
        path.relative_to(ADDON).as_posix()
        for path in ASSETS.rglob("*")
        if path.is_file() and path != MANIFEST
    }
    unreferenced = sorted(on_disk - referenced)
    if unreferenced:
        raise ValueError(f"unreferenced runtime assets remain: {', '.join(unreferenced)}")

    return dict(counts)


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, sort_keys=True))
