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


def package_files() -> list[Path]:
    files: list[Path] = []
    for path in ADDON.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ADDON)
        if path.name in EXCLUDED_NAMES or any(part in EXCLUDED_PARTS for part in rel.parts):
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
