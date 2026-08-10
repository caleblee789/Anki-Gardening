from __future__ import annotations

import json
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "ankigarden"
DIST = ROOT / "dist"
OUTPUT = DIST / "anki_garden.ankiaddon"

EXCLUDED_PARTS = {"__pycache__", "cache", "metadata"}
EXCLUDED_NAMES = {"meta.json", "garden_state.json", "asset_metadata.json", ".DS_Store"}


def runtime_asset_paths() -> set[str]:
    """Return the complete, manifest-owned runtime asset set."""
    payload = json.loads((ADDON / "assets" / "manifest.json").read_text("utf-8"))
    referenced: set[str] = {"assets/manifest.json"}

    def collect(value: object) -> None:
        if isinstance(value, dict):
            for nested in value.values():
                collect(nested)
        elif isinstance(value, list):
            for nested in value:
                collect(nested)
        elif isinstance(value, str) and value.startswith("assets/"):
            referenced.add(value)

    collect(payload)
    missing = sorted(path for path in referenced if not (ADDON / path).is_file())
    if missing:
        raise FileNotFoundError(f"runtime asset paths are missing: {', '.join(missing)}")
    return referenced


def package_files() -> list[Path]:
    files: list[Path] = []
    runtime_assets = runtime_asset_paths()
    for path in ADDON.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ADDON)
        if path.name in EXCLUDED_NAMES or any(part in EXCLUDED_PARTS for part in rel.parts):
            continue
        if rel.parts and rel.parts[0] == "assets" and rel.as_posix() not in runtime_assets:
            continue
        if "user_files" in rel.parts and path.name != "README.txt":
            continue
        files.append(path)
    return sorted(files)


def build() -> Path:
    manifest = json.loads((ADDON / "manifest.json").read_text("utf-8"))
    required = {"package", "name", "human_version", "min_point_version", "max_point_version"}
    missing = required.difference(manifest)
    if missing:
        raise ValueError(f"manifest.json missing: {', '.join(sorted(missing))}")

    DIST.mkdir(exist_ok=True)
    with zipfile.ZipFile(OUTPUT, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in package_files():
            archive.write(path, path.relative_to(ADDON).as_posix())
    return OUTPUT


if __name__ == "__main__":
    print(build())
