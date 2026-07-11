import json
import zipfile
from pathlib import Path

from scripts.package_addon import ADDON, OUTPUT, build


def test_distribution_manifest_is_complete() -> None:
    payload = json.loads((ADDON / "manifest.json").read_text("utf-8"))
    assert payload["package"] == "anki_garden"
    assert payload["min_point_version"] <= payload["max_point_version"]


def test_package_contains_runtime_and_excludes_mutable_data() -> None:
    build()
    with zipfile.ZipFile(OUTPUT) as archive:
        names = set(archive.namelist())
    assert {"__init__.py", "manifest.json", "config.json", "assets/manifest.json"} <= names
    assert "user_files/README.txt" in names
    assert "meta.json" not in names
    assert not any(name.endswith("garden_state.json") or "__pycache__" in name for name in names)
