import json
import zipfile
from pathlib import Path

from scripts.package_addon import (
    ADDON,
    OUTPUT,
    build,
    runtime_asset_paths,
)


OBSOLETE_ROSE_V6_ALIASES = {
    f"assets/v6_storybook_gouache/plants/rose/{stage}/rose_{stage}.png"
    for stage in ("seed", "sprout", "young", "mature", "flowering", "rare")
}


def test_distribution_manifest_is_complete() -> None:
    payload = json.loads((ADDON / "manifest.json").read_text("utf-8"))
    assert payload["package"] == "anki_garden"
    assert payload["min_point_version"] <= payload["max_point_version"]
    assert payload["min_point_version"] <= 260800 <= payload["max_point_version"]


def test_package_contains_runtime_and_excludes_mutable_data() -> None:
    build()
    with zipfile.ZipFile(OUTPUT) as archive:
        names = set(archive.namelist())
    assert {"__init__.py", "manifest.json", "config.json", "assets/manifest.json"} <= names
    assert "user_files/README.txt" in names
    assert "meta.json" not in names
    assert not any(name.endswith("garden_state.json") or "__pycache__" in name for name in names)

    asset_manifest = json.loads((ADDON / "assets" / "manifest.json").read_text("utf-8"))
    canonical_v6_plants = {
        row["file"]
        for row in asset_manifest["assets"]
        if row.get("category") == "plants"
        and row.get("file", "").startswith("assets/v6_storybook_gouache/plants/")
    }
    packaged_v6_plants = {
        name
        for name in names
        if name.startswith("assets/v6_storybook_gouache/plants/") and name.endswith(".webp")
    }
    assert len(canonical_v6_plants) == 60
    assert packaged_v6_plants == canonical_v6_plants
    assert OBSOLETE_ROSE_V6_ALIASES.isdisjoint(names)
    packaged_assets = {name for name in names if name.startswith("assets/")}
    assert packaged_assets == runtime_asset_paths()
    assert not any("fallback" in name.lower() for name in packaged_assets)
    assert not any(
        name.startswith(f"assets/v{version}_storybook_gouache/")
        for version in (2, 3, 4, 5)
        for name in packaged_assets
    )
    assert "assets/migration_manifest_v2.json" not in packaged_assets
    assert OUTPUT.stat().st_size < 52 * 1024 * 1024
