import base64
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ankigarden.asset_manager import AssetManager, AssetPlacement
from ankigarden.config import DEFAULT_CONFIG, ConfigManager


class DummyConfig:
    def __init__(self, overrides=None):
        self.cfg = json.loads(json.dumps(DEFAULT_CONFIG))
        if overrides:
            self.cfg = ConfigManager._merge(self.cfg, overrides)

    def value(self, key, default=None):
        return self.cfg.get(key, default)

    def nested(self, *keys, default=None):
        node = self.cfg
        for key in keys:
            node = node.get(key) if isinstance(node, dict) else None
            if node is None:
                return default
        return node


class DummyStorage:
    def __init__(self, root: Path):
        self.addon_dir = root
        self.assets_root = root / "assets"
        self.cache_dir = self.assets_root / "cache"
        self.assets_root.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._meta = {}
        self.save_calls = []

    def load_asset_metadata(self):
        return self._meta

    def save_asset_metadata(self, data):
        self.save_calls.append(json.loads(json.dumps(data)))
        self._meta = data


def _build_manifest(storage: DummyStorage, assets: list[dict]):
    manifest = storage.assets_root / "manifest.json"
    manifest.write_text(json.dumps({"schema_version": 1, "assets": assets}, indent=2), encoding="utf-8")


def _touch_asset(storage: DummyStorage, rel_path: str):
    p = storage.addon_dir / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    payloads = {
        ".png": "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFUlEQVR4nGOU8Db5z8DAwMAEIkAYABd8AZq1W63BAAAAAElFTkSuQmCC",
        ".webp": "UklGRjAAAABXRUJQVlA4ICQAAABwAQCdASoCAAIAAUAmJZACdAFAAAD++APns39bfjn81zuAAAA=",
    }
    if p.suffix.lower() in payloads:
        p.write_bytes(base64.b64decode(payloads[p.suffix.lower()]))
    else:
        p.write_text('<svg xmlns="http://www.w3.org/2000/svg"></svg>', encoding="utf-8")


def test_local_selection_is_deterministic(tmp_path):
    storage = DummyStorage(tmp_path)
    assets = [
        {
            "asset_id": "bg_a",
            "category": "backgrounds",
            "slot": {"season": "spring", "weather": "breeze", "theme": "verdant_dusk"},
            "file": "assets/backgrounds/verdant_dusk/spring_breeze_a.svg",
            "width": 1920,
            "height": 1080,
            "quality_tier": "balanced",
            "quality_score": 0.82,
        },
        {
            "asset_id": "bg_b",
            "category": "backgrounds",
            "slot": {"season": "spring", "weather": "breeze", "theme": "verdant_dusk"},
            "file": "assets/backgrounds/verdant_dusk/spring_breeze_b.svg",
            "width": 1920,
            "height": 1080,
            "quality_tier": "balanced",
            "quality_score": 0.81,
        },
    ]
    _build_manifest(storage, assets)
    for row in assets:
        _touch_asset(storage, row["file"])

    manager = AssetManager(DummyConfig(), storage)
    first = manager.get_or_fetch("backgrounds", "bg_spring_breeze", "ignored", theme="verdant_dusk")
    second = manager.get_or_fetch("backgrounds", "bg_spring_breeze", "ignored", theme="verdant_dusk")

    assert first is not None and second is not None
    assert first == second
    assert storage._meta == {}
    assert storage.save_calls == []


def test_exact_background_beats_release_wildcard_fallback(tmp_path):
    storage = DummyStorage(tmp_path)
    assets = [
        {
            "asset_id": "legacy_exact",
            "category": "backgrounds",
            "slot": {"season": "autumn", "weather": "fireflies", "theme": "verdant_dusk"},
            "file": "assets/backgrounds/legacy_exact.svg",
            "width": 1200,
            "height": 900,
            "quality_tier": "ultra",
            "quality_score": 0.99,
        },
        {
            "asset_id": "dusk_v4",
            "category": "backgrounds",
            "slot": {
                "season": "any",
                "weather": "any",
                "time_of_day": "any",
                "theme": "verdant_dusk",
            },
            "file": "assets/backgrounds/dusk_v4.svg",
            "width": 1200,
            "height": 900,
            "quality_tier": "ultra",
            "quality_score": 0.98,
            "release_preferred": True,
        },
    ]
    _build_manifest(storage, assets)
    for row in assets:
        _touch_asset(storage, row["file"])

    resolved = AssetManager(DummyConfig(), storage).resolve(
        "backgrounds",
        "bg_autumn_fireflies",
        "ignored",
        theme="verdant_dusk",
        time_of_day="night",
    )

    assert resolved is not None
    assert resolved.asset_id == "legacy_exact"
    assert resolved.metadata["slot"]["season"] == "autumn"
    assert resolved.metadata["slot"]["weather"] == "fireflies"


def test_missing_file_fails_closed_without_a_packaged_placeholder(tmp_path):
    storage = DummyStorage(tmp_path)
    assets = [
        {
            "asset_id": "decor_missing",
            "category": "decorations",
            "slot": {"decoration_id": "bench_corner"},
            "file": "assets/decorations/bench_corner/missing.svg",
            "width": 1024,
            "height": 1024,
            "quality_tier": "balanced",
            "quality_score": 0.8,
        }
    ]
    _build_manifest(storage, assets)

    manager = AssetManager(DummyConfig(), storage)
    picked = manager.get_or_fetch("decorations", "decor_bench_corner", "ignored")

    assert picked is None


def test_corrupt_png_is_skipped_for_a_valid_webp_candidate(tmp_path):
    storage = DummyStorage(tmp_path)
    assets = [
        {
            "asset_id": "rose_png_corrupt",
            "category": "plants",
            "slot": {"species": "rose", "stage": "young"},
            "file": "assets/plants/rose_young.png",
            "format": "png",
            "style_family": "storybook_gouache",
            "width": 1024,
            "height": 1024,
            "quality_tier": "ultra",
            "quality_score": 0.99,
        },
        {
            "asset_id": "rose_webp_valid",
            "category": "plants",
            "slot": {"species": "rose", "stage": "young"},
            "file": "assets/plants/rose_young.webp",
            "format": "webp",
            "style_family": "storybook_gouache",
            "width": 1024,
            "height": 1024,
            "quality_tier": "ultra",
            "quality_score": 0.98,
        },
    ]
    _build_manifest(storage, assets)
    corrupt = storage.addon_dir / assets[0]["file"]
    corrupt.parent.mkdir(parents=True, exist_ok=True)
    corrupt.write_bytes(b"not a png")
    _touch_asset(storage, assets[1]["file"])

    resolved = AssetManager(DummyConfig(), storage).resolve(
        "plants", "rose_young", "ignored"
    )

    assert resolved is not None
    assert resolved.asset_id == "rose_webp_valid"
    assert resolved.path.suffix == ".webp"


def test_truncated_or_mislabeled_containers_fail_closed(tmp_path):
    storage = DummyStorage(tmp_path)
    assets = [
        {
            "asset_id": "broken_png",
            "category": "ui",
            "slot": {"ui_id": "broken_png"},
            "file": "assets/ui/broken.png",
            "format": "png",
            "width": 512,
            "height": 512,
            "quality_tier": "balanced",
            "quality_score": 0.9,
        },
        {
            "asset_id": "broken_webp",
            "category": "ui",
            "slot": {"ui_id": "broken_webp"},
            "file": "assets/ui/broken.webp",
            "format": "webp",
            "width": 512,
            "height": 512,
            "quality_tier": "balanced",
            "quality_score": 0.9,
        },
        {
            "asset_id": "broken_svg",
            "category": "weather",
            "slot": {"weather": "broken"},
            "file": "assets/weather/broken.svg",
            "format": "svg",
            "width": 256,
            "height": 192,
            "quality_tier": "balanced",
            "quality_score": 0.9,
        },
    ]
    _build_manifest(storage, assets)
    for row in assets:
        path = storage.addon_dir / row["file"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"RIFF\x00\x00\x00\x00not-image")

    manager = AssetManager(DummyConfig(), storage)

    assert manager.resolve_ui_asset("broken_png") is None
    assert manager.resolve_ui_asset("broken_webp") is None
    assert manager.resolve("weather", "weather_broken", "ignored") is None


def test_large_png_validation_uses_bounded_reads_and_file_identity_cache(
    tmp_path, monkeypatch
):
    storage = DummyStorage(tmp_path)
    asset = {
        "asset_id": "bounded_png",
        "category": "ui",
        "slot": {"ui_id": "bounded"},
        "file": "assets/ui/bounded.png",
        "format": "png",
        "width": 512,
        "height": 512,
        "quality_tier": "balanced",
        "quality_score": 0.9,
    }
    _build_manifest(storage, [asset])
    path = storage.addon_dir / asset["file"]
    path.parent.mkdir(parents=True, exist_ok=True)
    file_size = 2 * 1024 * 1024
    header = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    trailer = b"\x00\x00\x00\x00IEND\xaeB`\x82"
    path.write_bytes(header + (b"\x00" * (file_size - 28)) + trailer)
    manager = AssetManager(DummyConfig(), storage)

    original_open = Path.open
    open_count = 0
    read_sizes = []

    class CountingReader:
        def __init__(self, raw):
            self.raw = raw

        def __enter__(self):
            self.raw.__enter__()
            return self

        def __exit__(self, *exc_info):
            return self.raw.__exit__(*exc_info)

        def read(self, size=-1):
            assert size >= 0, "container validation must not read an entire raster"
            payload = self.raw.read(size)
            read_sizes.append(len(payload))
            return payload

        def seek(self, offset, whence=0):
            return self.raw.seek(offset, whence)

    def counting_open(candidate, *args, **kwargs):
        nonlocal open_count
        raw = original_open(candidate, *args, **kwargs)
        if candidate == path and args and args[0] == "rb":
            open_count += 1
            return CountingReader(raw)
        return raw

    monkeypatch.setattr(Path, "open", counting_open)

    first = manager.resolve_ui_asset("bounded")
    manager.clear_runtime_cache("ui")
    second = manager.resolve_ui_asset("bounded")

    assert first is not None and second is not None
    assert open_count == 1
    assert read_sizes == [16, 12]
    assert sum(read_sizes) == 28


def test_container_validation_cache_invalidates_when_file_mtime_changes(tmp_path):
    storage = DummyStorage(tmp_path)
    asset = {
        "asset_id": "changing_png",
        "category": "ui",
        "slot": {"ui_id": "changing"},
        "file": "assets/ui/changing.png",
        "format": "png",
        "width": 512,
        "height": 512,
        "quality_tier": "balanced",
        "quality_score": 0.9,
    }
    _build_manifest(storage, [asset])
    _touch_asset(storage, asset["file"])
    path = storage.addon_dir / asset["file"]
    manager = AssetManager(DummyConfig(), storage)

    assert manager.resolve_ui_asset("changing") is not None
    original_info = path.stat()
    corrupted = bytearray(path.read_bytes())
    corrupted[:8] = b"not-png!"
    path.write_bytes(corrupted)
    os.utime(
        path,
        ns=(original_info.st_atime_ns, original_info.st_mtime_ns + 1_000_000),
    )
    assert path.stat().st_mtime_ns != original_info.st_mtime_ns

    manager.clear_runtime_cache("ui")

    assert manager.resolve_ui_asset("changing") is None


def test_quality_preference_prefers_higher_tier(tmp_path):
    storage = DummyStorage(tmp_path)
    assets = [
        {
            "asset_id": "weather_perf",
            "category": "weather",
            "slot": {"weather": "breeze"},
            "file": "assets/weather/breeze/perf.svg",
            "width": 1280,
            "height": 720,
            "quality_tier": "performance",
            "quality_score": 0.7,
        },
        {
            "asset_id": "weather_ultra",
            "category": "weather",
            "slot": {"weather": "breeze"},
            "file": "assets/weather/breeze/ultra.svg",
            "width": 1280,
            "height": 720,
            "quality_tier": "ultra",
            "quality_score": 0.95,
        },
    ]
    _build_manifest(storage, assets)
    for row in assets:
        _touch_asset(storage, row["file"])

    manager = AssetManager(DummyConfig({"assets": {"quality_preference": "ultra"}}), storage)
    picked = manager.get_or_fetch("weather", "weather_breeze", "ignored")

    assert picked is not None
    assert picked.name == "ultra.svg"


def test_final_art_revision_precedes_older_quality_variants(tmp_path):
    storage = DummyStorage(tmp_path)
    assets = [
        {
            "asset_id": "ivy_rare_old",
            "category": "plants",
            "slot": {"species": "ivy", "stage": "rare"},
            "variants": ["rare", "storybook_gouache", "continuity_v3"],
            "style_family": "storybook_gouache",
            "file": "assets/plants/ivy_rare_v3.svg",
            "width": 512, "height": 512, "quality_tier": "performance", "quality_score": 0.999,
        },
        {
            "asset_id": "ivy_rare_final",
            "category": "plants",
            "slot": {"species": "ivy", "stage": "rare"},
            "variants": ["rare", "storybook_gouache", "continuity_v4"],
            "style_family": "storybook_gouache",
            "file": "assets/plants/ivy_rare_v4.svg",
            "width": 512, "height": 512, "quality_tier": "ultra", "quality_score": 0.9995,
        },
    ]
    _build_manifest(storage, assets)
    manager = AssetManager(DummyConfig(), storage)

    candidates = manager._select_candidates("plants", {"species": "ivy", "stage": "rare"}, "performance")

    assert candidates[0]["asset_id"] == "ivy_rare_final"


def test_catalog_svg_manifest_dimensions_are_accepted(tmp_path):
    storage = DummyStorage(tmp_path)
    assets = [
        {
            "asset_id": "plant_svg",
            "category": "plants",
            "slot": {"species": "rose", "stage": "young"},
            "file": "assets/v2_cozy_handpainted/plants/rose/young/rose_young.svg",
            "width": 256,
            "height": 256,
            "quality_tier": "balanced",
            "quality_score": 0.9,
        }
    ]
    _build_manifest(storage, assets)
    _touch_asset(storage, assets[0]["file"])

    manager = AssetManager(DummyConfig(), storage)
    picked = manager.get_or_fetch("plants", "rose_young", "ignored")

    assert picked is not None
    assert picked.name == "rose_young.svg"


def test_storybook_png_is_preferred_over_matching_v2_svg(tmp_path):
    storage = DummyStorage(tmp_path)
    assets = [
        {
            "asset_id": "rose_v2",
            "category": "plants",
            "slot": {"species": "rose", "stage": "young"},
            "file": "assets/v2/rose.svg",
            "format": "svg",
            "width": 256,
            "height": 256,
            "quality_tier": "balanced",
            "quality_score": 0.9,
        },
        {
            "asset_id": "rose_v3",
            "category": "plants",
            "slot": {"species": "rose", "stage": "young"},
            "file": "assets/v3/rose.png",
            "format": "png",
            "style_family": "storybook_gouache",
            "width": 1024,
            "height": 1024,
            "quality_tier": "ultra",
            "quality_score": 0.98,
        },
    ]
    _build_manifest(storage, assets)
    for row in assets:
        _touch_asset(storage, row["file"])

    picked = AssetManager(DummyConfig(), storage).get_or_fetch("plants", "rose_young", "ignored")

    assert picked is not None and picked.name == "rose.png"


def test_resolved_asset_carries_sanitized_placement_metadata(tmp_path):
    storage = DummyStorage(tmp_path)
    assets = [{
        "asset_id": "bonsai_v3",
        "category": "plants",
        "slot": {"species": "bonsai", "stage": "young"},
        "file": "assets/v3/bonsai.png",
        "format": "png",
        "width": 1254,
        "height": 1254,
        "quality_tier": "ultra",
        "quality_score": 0.98,
        "style_family": "storybook_gouache",
        "placement": {"anchor_x": 0.48, "baseline_y": 0.91, "scale": 0.86, "crop": "contain", "layer": "plants"},
    }]
    _build_manifest(storage, assets)
    _touch_asset(storage, assets[0]["file"])

    resolved = AssetManager(DummyConfig(), storage).resolve("plants", "bonsai_young", "ignored")

    assert resolved is not None
    assert resolved.asset_id == "bonsai_v3"
    assert resolved.placement.anchor_x == 0.48
    assert resolved.placement.baseline_y == 0.91
    assert resolved.placement.display_scale == 0.86
    assert resolved.to_payload()["metadata"]["style_family"] == "storybook_gouache"
    assert resolved.to_payload()["placement"]["baseline_y"] == 0.91


def test_invalid_placement_values_fall_back_or_clamp():
    placement = AssetPlacement.from_manifest(
        {"anchor_x": 9, "baseline_y": -2, "scale": "bad", "crop": "stretch"},
        category="plants",
    )

    assert placement.anchor_x == 1.0
    assert placement.baseline_y == 0.0
    assert placement.scale == 1.0
    assert placement.crop == "contain"
    assert placement.base_type == "legacy"
    assert placement.visible_bounds == (0.08, 0.04, 0.84, 0.92)
    assert placement.thumbnail_bounds == placement.visible_bounds
    assert placement.thumbnail_optical_center == (0.5, 0.5)
    assert placement.thumbnail_scale == 1.0
    assert placement.thumbnail_safe_padding == 0.10
    assert len(placement.bed_anchors) == 6


def test_legacy_planting_zone_receives_stable_six_bed_fallback():
    placement = AssetPlacement.from_manifest(
        {"planting_zone": {"left": 0.1, "right": 0.9, "far_y": 0.6, "near_y": 0.94}},
        category="backgrounds",
    )
    payload = placement.to_dict()

    assert len(payload["bed_anchors"]) == 6
    assert payload["planting_zone"] == {"left": 0.1, "right": 0.9, "far_y": 0.6, "near_y": 0.94}
    assert all(
        set(anchor) == {
            "x", "y", "depth", "plant_scale", "footprint", "label_anchor",
            "physical_width_ratio", "surface_id", "contact_plane", "shadow_plane", "shadow_depth",
            "shadow_opacity", "occlusion_id", "support_line", "surface_kind",
            "allowed_base_types", "seating_depth", "depth_band", "shadow_color",
            "light_direction",
        }
        for anchor in payload["bed_anchors"]
    )


def test_current_production_plants_use_alpha_aware_grounding_metadata():
    manifest_path = Path(__file__).resolve().parents[1] / "ankigarden/assets/manifest.json"
    assets = json.loads(manifest_path.read_text(encoding="utf-8"))["assets"]
    plants = [row for row in assets if row.get("category") == "plants"]

    assert len(plants) == 60
    for row in plants:
        placement = row["placement"]
        normalized = AssetPlacement.from_manifest(placement, category="plants")
        thumbnail = normalized.to_dict()
        visible = placement["visible_bounds"]
        ground = placement["ground_anchor"]
        assert len(visible) == 4 and visible[2] > 0 and visible[3] > 0
        assert len(ground) == 2
        assert int(placement.get("geometry_version", 0)) == 2
        assert placement["soil_contact"] == ground
        for semantic_base in ("base_bounds", "support_bounds"):
            bounds = placement[semantic_base]
            assert bounds[0] <= ground[0] <= bounds[0] + bounds[2]
            assert abs((bounds[1] + bounds[3]) - ground[1]) < 0.001
        assert placement["display_scale"] > 0
        assert placement["base_type"] == "direct_soil"
        assert 0.2 <= placement["contact_shadow"][0] <= 1.0
        assert 0.015 <= placement["contact_shadow"][1] <= 0.12
        assert len(thumbnail["thumbnail_bounds"]) == 4
        assert thumbnail["thumbnail_bounds"][2] > 0
        assert thumbnail["thumbnail_bounds"][3] > 0
        assert len(thumbnail["thumbnail_optical_center"]) == 2
        assert 0.5 <= thumbnail["thumbnail_scale"] <= 1.5
        assert 0.0 <= thumbnail["thumbnail_safe_padding"] <= 0.3


def test_runtime_catalog_contains_one_current_asset_per_species_and_stage():
    manifest_path = Path(__file__).resolve().parents[1] / "ankigarden/assets/manifest.json"
    rows = json.loads(manifest_path.read_text(encoding="utf-8"))["assets"]
    plants = [row for row in rows if row.get("category") == "plants"]
    expected_species = {
        "bonsai", "rose", "sunflower", "lavender", "hydrangea", "peony",
        "foxglove", "japanese_maple", "wisteria", "dahlia",
    }
    expected_stages = {"seed", "sprout", "young", "mature", "flowering", "rare"}

    assert len(plants) == len(expected_species) * len(expected_stages)
    assert {row["slot"]["species"] for row in plants} == expected_species
    assert {
        (row["slot"]["species"], row["slot"]["stage"])
        for row in plants
    } == {
        (species, stage)
        for species in expected_species
        for stage in expected_stages
    }
    for row in plants:
        placement = row["placement"]
        assert {
            "visible_bounds", "ground_anchor", "contact_shadow", "base_type", "crop", "layer"
        }.issubset(placement)
        assert row.get("release_preferred") is True
        assert "continuity_v6" in row.get("variants", [])
        assert row["file"].startswith("assets/v6_storybook_gouache/plants/")
        assert row.get("fallback_asset_id") in {None, ""}
        assert placement["base_type"] == "direct_soil"
        assert "seedling_cue" not in row
        assert "seedling_anchor" not in row


def test_manifest_exposes_canonical_v6_geometry_and_eight_scenery_reskins():
    manifest_path = Path(__file__).resolve().parents[1] / "ankigarden/assets/manifest.json"
    rows = json.loads(manifest_path.read_text(encoding="utf-8"))["assets"]
    backgrounds = [
        row for row in rows
        if row.get("category") == "backgrounds" and row.get("style_family") == "storybook_gouache"
    ]
    assert [row["asset_id"] for row in backgrounds] == [
        "bg_verdant_twilight_any_soil_master_v6",
        "bg_spring_any_soil_master_v6",
        "bg_summer_any_soil_master_v6",
        "bg_autumn_any_soil_master_v6",
        "bg_snowy_any_soil_master_v6",
        "bg_rainbow_horizon_any_soil_master_v6",
        "bg_halloween_any_soil_master_v6",
        "bg_full_moon_any_soil_master_v6",
        "bg_eclipse_any_soil_master_v6",
    ]
    base = backgrounds[0]
    profiles = base["placement"]["layout_profiles"]
    assert set(profiles) == {"4:3", "3:2", "16:9", "home"}
    for profile in profiles.values():
        assert set(profile["compositions"]) == {str(count) for count in range(1, 7)}
        assert all(len(anchors) == 6 for anchors in profile["compositions"].values())
    for row in backgrounds[1:]:
        assert row["placement_ref"] == base["asset_id"]
        assert set(row["surface_files"]) == {"4:3", "16:9", "home"}
        if row["asset_id"] == "bg_autumn_any_soil_master_v6":
            override = row["landmark_overrides"]["garden_house"]["variants"]
            assert set(override) == {"4:3", "16:9", "home"}
        else:
            assert "landmark_overrides" not in row
        assert row.get("release_preferred") is False


def test_storybook_season_master_serves_every_weather(tmp_path):
    storage = DummyStorage(tmp_path)
    assets = [
        {
            "asset_id": "summer_master",
            "category": "backgrounds",
            "slot": {"season": "summer", "weather": "any", "theme": "verdant_dusk"},
            "file": "assets/v3/summer.webp",
            "format": "webp",
            "style_family": "storybook_gouache",
            "width": 1448,
            "height": 1086,
            "quality_tier": "ultra",
            "quality_score": 0.98,
        }
    ]
    _build_manifest(storage, assets)
    _touch_asset(storage, assets[0]["file"])

    picked = AssetManager(DummyConfig(), storage).get_or_fetch(
        "backgrounds", "bg_summer_gentle_rain", "ignored", theme="verdant_dusk"
    )

    assert picked is not None and picked.name == "summer.webp"


def test_morning_bloom_theme_alias_selects_verdant_dawn_assets(tmp_path):
    storage = DummyStorage(tmp_path)
    assets = [
        {
            "asset_id": "bg_dawn",
            "category": "backgrounds",
            "slot": {"season": "spring", "weather": "breeze", "theme": "verdant_dawn"},
            "file": "assets/v2_cozy_handpainted/backgrounds/verdant_dawn/spring_breeze.svg",
            "width": 512,
            "height": 384,
            "quality_tier": "balanced",
            "quality_score": 0.9,
        }
    ]
    _build_manifest(storage, assets)
    _touch_asset(storage, assets[0]["file"])

    manager = AssetManager(DummyConfig(), storage)
    picked = manager.get_or_fetch("backgrounds", "bg_spring_breeze", "ignored", theme="morning_bloom")

    assert picked is not None
    assert "verdant_dawn" in picked.as_posix()


def test_theme_aware_garden_overlay_uses_matching_bed_contract(tmp_path):
    storage = DummyStorage(tmp_path)
    assets = [{
        "asset_id": "beds_dawn",
        "category": "overlays",
        "slot": {"overlay_id": "garden_beds", "theme": "verdant_dawn"},
        "file": "assets/overlays/dawn.svg",
        "format": "svg",
        "width": 1200,
        "height": 900,
        "quality_tier": "balanced",
        "quality_score": 0.98,
        "placement": {
            "anchor_x": 0.5,
            "baseline_y": 0.5,
            "scale": 1.0,
            "crop": "cover",
            "layer": "overlay",
        },
    }]
    _build_manifest(storage, assets)
    _touch_asset(storage, assets[0]["file"])

    resolved = AssetManager(DummyConfig(), storage).resolve(
        "overlays",
        "overlay_garden_beds",
        "ignored",
        theme="morning_bloom",
    )

    assert resolved is not None
    assert resolved.asset_id == "beds_dawn"
    assert resolved.placement.layer == "overlay"
    assert len(resolved.placement.bed_anchors) == 6


def test_explicit_preview_quality_overrides_config_preference(tmp_path):
    storage = DummyStorage(tmp_path)
    assets = [
        {
            "asset_id": "weather_perf",
            "category": "weather",
            "slot": {"weather": "sunny"},
            "file": "assets/v2_cozy_handpainted/weather/sunny/sunny_performance.svg",
            "width": 256,
            "height": 192,
            "quality_tier": "performance",
            "quality_score": 0.7,
        },
        {
            "asset_id": "weather_balanced",
            "category": "weather",
            "slot": {"weather": "sunny"},
            "file": "assets/v2_cozy_handpainted/weather/sunny/sunny_balanced.svg",
            "width": 256,
            "height": 192,
            "quality_tier": "balanced",
            "quality_score": 0.9,
        },
    ]
    _build_manifest(storage, assets)
    for row in assets:
        _touch_asset(storage, row["file"])

    manager = AssetManager(DummyConfig({"assets": {"quality_preference": "performance"}}), storage)
    picked = manager.get_or_fetch("weather", "weather_sunny", "ignored", quality_preference="balanced")

    assert picked is not None
    assert picked.name == "sunny_balanced.svg"


def test_reroll_cycles_through_local_alternatives(tmp_path):
    storage = DummyStorage(tmp_path)
    assets = [
        {
            "asset_id": "plant1",
            "category": "plants",
            "slot": {"species": "bonsai", "stage": "mature"},
            "file": "assets/plants/bonsai/mature/a.svg",
            "width": 1024,
            "height": 1024,
            "quality_tier": "balanced",
            "quality_score": 0.85,
        },
        {
            "asset_id": "plant2",
            "category": "plants",
            "slot": {"species": "bonsai", "stage": "mature"},
            "file": "assets/plants/bonsai/mature/b.svg",
            "width": 1024,
            "height": 1024,
            "quality_tier": "balanced",
            "quality_score": 0.84,
        },
    ]
    _build_manifest(storage, assets)
    for row in assets:
        _touch_asset(storage, row["file"])

    manager = AssetManager(DummyConfig(), storage)
    initial = manager.get_or_fetch("plants", "bonsai_mature", "ignored")
    assert storage.save_calls == []
    first = manager.get_or_fetch("plants", "bonsai_mature", "ignored", reroll=True)
    restarted_manager = AssetManager(DummyConfig(), storage)
    second = restarted_manager.get_or_fetch(
        "plants", "bonsai_mature", "ignored", reroll=True
    )

    assert initial is not None and first is not None and second is not None
    assert initial != first
    assert first != second
    assert len(storage.save_calls) == 2
    cycles = storage._meta[AssetManager._LOCAL_CATALOG_CYCLES_KEY]
    assert cycles["plants:bonsai_mature"] == {
        "local_path": "assets/plants/bonsai/mature/a.svg",
        "catalog_cycle_index": 0,
    }


def test_legacy_remote_metadata_is_preserved_and_not_selected(tmp_path):
    storage = DummyStorage(tmp_path)
    old = storage.addon_dir / "assets/backgrounds/legacy_remote.jpg"
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_bytes(b"legacy")
    storage._meta = {
        "backgrounds:bg_spring_breeze": {
            "source_kind": "remote",
            "local_path": "assets/backgrounds/legacy_remote.jpg",
            "provider": "wikimedia",
        }
    }
    legacy_metadata = json.loads(json.dumps(storage._meta))
    assets = [
        {
            "asset_id": "bg_local",
            "category": "backgrounds",
            "slot": {"season": "spring", "weather": "breeze", "theme": "verdant_dusk"},
            "file": "assets/backgrounds/verdant_dusk/spring_breeze.svg",
            "width": 1920,
            "height": 1080,
            "quality_tier": "balanced",
            "quality_score": 0.85,
        }
    ]
    _build_manifest(storage, assets)
    _touch_asset(storage, assets[0]["file"])

    manager = AssetManager(DummyConfig(), storage)
    picked = manager.get_or_fetch("backgrounds", "bg_spring_breeze", "ignored", theme="verdant_dusk")

    assert picked is not None
    assert picked.name == "spring_breeze.svg"
    assert storage._meta == legacy_metadata
    assert storage.save_calls == []


def test_reroll_accepts_legacy_local_cycle_without_rewriting_legacy_record(tmp_path):
    storage = DummyStorage(tmp_path)
    cache_key = "plants:bonsai_mature"
    storage._meta = {
        cache_key: {
            "provider": "local_catalog",
            "source_kind": "local_catalog",
            "local_path": "assets/plants/bonsai/mature/a.svg",
            "catalog_cycle_index": 0,
            "downloaded_at": 123,
        }
    }
    legacy_record = json.loads(json.dumps(storage._meta[cache_key]))
    assets = [
        {
            "asset_id": "plant1",
            "category": "plants",
            "slot": {"species": "bonsai", "stage": "mature"},
            "file": "assets/plants/bonsai/mature/a.svg",
            "width": 1024,
            "height": 1024,
            "quality_tier": "balanced",
            "quality_score": 0.85,
        },
        {
            "asset_id": "plant2",
            "category": "plants",
            "slot": {"species": "bonsai", "stage": "mature"},
            "file": "assets/plants/bonsai/mature/b.svg",
            "width": 1024,
            "height": 1024,
            "quality_tier": "balanced",
            "quality_score": 0.84,
        },
    ]
    _build_manifest(storage, assets)
    for row in assets:
        _touch_asset(storage, row["file"])

    picked = AssetManager(DummyConfig(), storage).get_or_fetch(
        "plants", "bonsai_mature", "ignored", reroll=True
    )

    assert picked is not None
    assert picked.name == "b.svg"
    assert storage._meta[cache_key] == legacy_record
    assert storage._meta[AssetManager._LOCAL_CATALOG_CYCLES_KEY][cache_key] == {
        "local_path": "assets/plants/bonsai/mature/b.svg",
        "catalog_cycle_index": 1,
    }
    assert len(storage.save_calls) == 1


def test_single_candidate_reroll_does_not_repeat_metadata_write(tmp_path):
    storage = DummyStorage(tmp_path)
    asset = {
        "asset_id": "only_plant",
        "category": "plants",
        "slot": {"species": "bonsai", "stage": "mature"},
        "file": "assets/plants/bonsai/mature/only.svg",
        "width": 1024,
        "height": 1024,
        "quality_tier": "balanced",
        "quality_score": 0.85,
    }
    _build_manifest(storage, [asset])
    _touch_asset(storage, asset["file"])
    manager = AssetManager(DummyConfig(), storage)

    first = manager.get_or_fetch("plants", "bonsai_mature", "ignored", reroll=True)
    second = manager.get_or_fetch("plants", "bonsai_mature", "ignored", reroll=True)

    assert first == second
    assert len(storage.save_calls) == 1


def test_config_merge_keeps_new_visual_defaults():
    merged = ConfigManager._merge(DEFAULT_CONFIG.copy(), {"enable_sounds": True})
    assert merged["enable_sounds"] is True
    assert merged["assets"]["mode"] == "local_only"
    assert "weather_particle_density" in merged["theme_overrides"]
