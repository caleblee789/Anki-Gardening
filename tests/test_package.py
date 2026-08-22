import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from scripts.package_addon import (
    ADDON,
    CAPABILITY_MODULE,
    CAPTURE_BUILD,
    CAPTURE_HARNESS,
    OUTPUT,
    PACKAGE_TIMESTAMP,
    PRODUCTION_BUILD,
    _raw_deflated_size,
    _requested_cli_build,
    _requested_cli_mode,
    build,
    package_files,
    package_payload,
    package_report,
    runtime_asset_paths,
)


OBSOLETE_ROSE_V6_ALIASES = {
    f"assets/v6_storybook_gouache/plants/rose/{stage}/rose_{stage}.png"
    for stage in ("seed", "sprout", "young", "mature", "flowering", "rare")
}

SCHEMA_21_REQUIRED_RUNTIME_FILES = frozenset({
    "achievements.py",
    "addon.py",
    "game.py",
    "garden_finds.py",
    "hooks/reviewer.py",
    "models/state.py",
    "reward_ledger.py",
    "reward_presentation.py",
    "storage.py",
})

EXPECTED_PACKAGED_USER_FILES = frozenset({"user_files/README.txt"})


def _archive_capabilities(archive: zipfile.ZipFile) -> dict[str, object]:
    namespace: dict[str, object] = {}
    source = archive.read(CAPABILITY_MODULE).decode("utf-8")
    exec(compile(source, CAPABILITY_MODULE, "exec"), namespace)
    return namespace


def test_distribution_manifest_is_complete() -> None:
    payload = json.loads((ADDON / "manifest.json").read_text("utf-8"))
    assert payload["package"] == "anki_garden"
    assert payload["min_point_version"] <= payload["max_point_version"]
    assert payload["min_point_version"] <= 260800 <= payload["max_point_version"]


def test_package_contains_runtime_and_excludes_mutable_data() -> None:
    build()
    with zipfile.ZipFile(OUTPUT) as archive:
        names = set(archive.namelist())
        capabilities = _archive_capabilities(archive)
        packaged_game = archive.read("game.py").decode("utf-8")
        expected = {
            path.relative_to(ADDON).as_posix(): package_payload(path)
            for path in package_files()
        }
        assert names == set(expected)
        for name, payload in expected.items():
            assert archive.read(name) == payload
        manifest_info = archive.getinfo("manifest.json")
        assert manifest_info.compress_type == zipfile.ZIP_DEFLATED
        assert manifest_info.compress_size == _raw_deflated_size(
            expected["manifest.json"]
        )
        assert any(
            info.compress_type == zipfile.ZIP_STORED for info in archive.infolist()
        )
        capability_source = ADDON / CAPABILITY_MODULE
        generated_capabilities = package_payload(capability_source)
        checked_in_capabilities = capability_source.read_bytes()
        assert generated_capabilities.endswith(b"\n")
        assert checked_in_capabilities.endswith(b"\n")
        assert generated_capabilities.rstrip(b"\n") == checked_in_capabilities.rstrip(
            b"\n"
        )
    assert {"__init__.py", "manifest.json", "config.json", "assets/manifest.json"} <= names
    assert SCHEMA_21_REQUIRED_RUNTIME_FILES <= names, sorted(
        SCHEMA_21_REQUIRED_RUNTIME_FILES - names
    )
    packaged_user_files = {
        name for name in names if name.startswith("user_files/")
    }
    assert packaged_user_files == EXPECTED_PACKAGED_USER_FILES
    assert "meta.json" not in names
    assert not any(name.endswith("garden_state.json") or "__pycache__" in name for name in names)
    assert CAPTURE_HARNESS not in names
    assert capabilities["BUILD_MODE"] == PRODUCTION_BUILD
    assert capabilities["CAPTURE_HARNESS_ENABLED"] is False
    assert capabilities["DEVELOPMENT_MUTATION_ENABLED"] is False
    assert "if not build_capabilities.DEVELOPMENT_MUTATION_ENABLED:" in packaged_game

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
    # The schema-20 release ships all nine responsive scenery plates, the
    # complete six-stage plant library, and the geometry-matched planter set.
    # Ratchet the complete schema-20 art library to the next 0.25 MiB boundary
    # above the optimized release artifact. This preserves a small deterministic
    # build margin without allowing the former 82 MiB budget to return.
    assert OUTPUT.stat().st_size < (78 * 1024 * 1024) + (256 * 1024)


def test_capture_package_explicitly_enables_and_contains_capture_capabilities(
    tmp_path: Path,
) -> None:
    output = build(CAPTURE_BUILD, output=tmp_path / "anki_garden_capture.ankiaddon")

    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
        capabilities = _archive_capabilities(archive)
        expected = {
            path.relative_to(ADDON).as_posix(): package_payload(path, CAPTURE_BUILD)
            for path in package_files(CAPTURE_BUILD)
        }
        assert names == set(expected)
        for name, payload in expected.items():
            assert archive.read(name) == payload

    assert CAPTURE_HARNESS in names
    assert capabilities["BUILD_MODE"] == CAPTURE_BUILD
    assert capabilities["CAPTURE_HARNESS_ENABLED"] is True
    assert capabilities["DEVELOPMENT_MUTATION_ENABLED"] is True


def test_package_build_is_byte_reproducible(tmp_path: Path) -> None:
    first = build(PRODUCTION_BUILD, output=tmp_path / "first.ankiaddon")
    second = build(PRODUCTION_BUILD, output=tmp_path / "second.ankiaddon")

    assert hashlib.sha256(first.read_bytes()).digest() == hashlib.sha256(
        second.read_bytes()
    ).digest()
    with zipfile.ZipFile(first) as archive:
        assert all(info.date_time == PACKAGE_TIMESTAMP for info in archive.infolist())
        assert all(info.external_attr >> 16 == 0o644 for info in archive.infolist())

    first_report = package_report(first)
    second_report = package_report(second)
    first_report.pop("output")
    second_report.pop("output")
    assert first_report == second_report
    assert first_report["file_count"] == (
        first_report["deflated_entries"] + first_report["stored_entries"]
    )
    assert first_report["archive_size_bytes"] == first.stat().st_size
    with pytest.raises(ValueError, match="do not describe a capture build"):
        package_report(first, CAPTURE_BUILD)


def test_package_cli_defaults_to_production_and_requires_explicit_capture_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ANKI_GARDEN_PACKAGE_MODE", CAPTURE_BUILD)
    assert _requested_cli_mode([]) == PRODUCTION_BUILD
    assert _requested_cli_mode(["--production"]) == PRODUCTION_BUILD
    capture_output = tmp_path / "anki_garden_capture.ankiaddon"
    assert _requested_cli_build(
        ["--capture", "--output", str(capture_output)]
    ) == (CAPTURE_BUILD, capture_output)

    with pytest.raises(SystemExit):
        _requested_cli_build(["--capture"])
    with pytest.raises(SystemExit):
        _requested_cli_build(["--output", str(capture_output)])
