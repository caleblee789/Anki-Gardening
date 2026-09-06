import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from ankigarden.asset_manager import AssetPlacement
import scripts.package_addon as package_addon
from scripts.package_addon import (
    ADDON,
    CAPABILITY_MODULE,
    CAPTURE_BUILD,
    CAPTURE_HARNESS,
    CAPTURE_SUBTREE,
    OUTPUT,
    PACKAGE_TIMESTAMP,
    PRODUCTION_BUILD,
    _compression_for,
    _raw_deflated_size,
    _requested_cli_build,
    _requested_cli_mode,
    build,
    capture_derivative_report,
    package_files,
    package_payload,
    package_report,
    runtime_asset_paths,
)


pytestmark = pytest.mark.release_evidence


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
    "models/sync_reward.py",
    "models/state.py",
    "reward_ledger.py",
    "reward_presentation.py",
    "storage.py",
    "sync_review_detector.py",
    "sync_reward_presenter.py",
    "sync_reward_processor.py",
    "ui/sync_reward_summary.py",
})

EXPECTED_PACKAGED_USER_FILES = frozenset({"user_files/README.txt"})


@pytest.fixture(scope="module")
def package_archives(
    tmp_path_factory: pytest.TempPathFactory,
) -> dict[str, Path]:
    """Build each archive variant once for all read-only package assertions."""

    root = tmp_path_factory.mktemp("package-archives")
    return {
        "production": build(output=root / "anki_garden_production.ankiaddon"),
        "production_rebuild": build(
            PRODUCTION_BUILD,
            output=root / "anki_garden_production_rebuild.ankiaddon",
        ),
        "capture": build(
            CAPTURE_BUILD,
            output=root / "anki_garden_capture.ankiaddon",
        ),
    }


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


def test_required_runtime_files_are_in_production_source_set() -> None:
    names = {
        path.relative_to(ADDON).as_posix()
        for path in package_files(PRODUCTION_BUILD)
    }

    assert SCHEMA_21_REQUIRED_RUNTIME_FILES <= names, sorted(
        SCHEMA_21_REQUIRED_RUNTIME_FILES - names
    )


def test_package_contains_runtime_and_excludes_mutable_data(
    package_archives: dict[str, Path],
) -> None:
    production_output = package_archives["production"]
    with zipfile.ZipFile(production_output) as archive:
        names = set(archive.namelist())
        capabilities = _archive_capabilities(archive)
        packaged_game = archive.read("game.py").decode("utf-8")
        asset_manifest = json.loads(archive.read("assets/manifest.json"))
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
    assert not any(
        "/backgrounds/" in name and "_16x9" in name for name in packaged_assets
    )
    assert not any(
        "/backgrounds/" in name
        and (name.endswith("_4x3.webp") or "/masks/" in name)
        for name in packaged_assets
    )
    backgrounds = [
        row for row in asset_manifest["assets"] if row.get("category") == "backgrounds"
    ]
    for row in backgrounds:
        assert row["file"] == row["native_garden_file"]
        assert row["file"] in packaged_assets
        assert (row["width"], row["height"]) == (1448, 1086)
    background = next(
        row for row in asset_manifest["assets"]
        if row.get("category") == "backgrounds" and "placement" in row
    )
    placement = AssetPlacement.from_manifest(
        background["placement"], category="backgrounds"
    )
    assert placement.surface_profile is not None
    assert set(placement.surface_profile.variants) == {"4:3", "home"}
    assert not any("fallback" in name.lower() for name in packaged_assets)
    assert not any(
        name.startswith(f"assets/v{version}_storybook_gouache/")
        for version in (2, 3, 4, 5)
        for name in packaged_assets
    )
    assert "assets/migration_manifest_v2.json" not in packaged_assets
    # Ship the active Garden/Home layouts for all nine scenery plates, the
    # complete six-stage plant library, the geometry-matched planter set,
    # and the canonical Rich Compost reward artwork.
    # Keep the reviewed plant catalog, continuous lawn, and discovery icon
    # within a 100 MiB budget using lossless artwork encodings.
    assert production_output.stat().st_size < 100 * 1024 * 1024


def test_capture_package_explicitly_enables_and_contains_capture_capabilities(
    package_archives: dict[str, Path],
) -> None:
    from scripts.capture_support import capture_derivative_report as supported_report

    production_output = package_archives["production"]
    output = package_archives["capture"]
    derivative = capture_derivative_report(production_output, output)
    assert supported_report(ADDON.parent, production_output, output) == derivative

    with zipfile.ZipFile(production_output) as production_archive, zipfile.ZipFile(
        output
    ) as archive:
        names = set(archive.namelist())
        production_names = set(production_archive.namelist())
        capabilities = _archive_capabilities(archive)
        expected = {
            path.relative_to(ADDON).as_posix(): package_payload(path, CAPTURE_BUILD)
            for path in package_files(CAPTURE_BUILD)
        }
        assert names == set(expected)
        for name, payload in expected.items():
            assert archive.read(name) == payload
        capture_only = sorted(names - production_names)
        shared_names = sorted(production_names.difference({CAPABILITY_MODULE}))
        digest = hashlib.sha256()
        digest.update(b"anki-garden-shared-payload-v1\0")
        for name in shared_names:
            encoded_name = name.encode("utf-8")
            payload = archive.read(name)
            digest.update(len(encoded_name).to_bytes(8, "big"))
            digest.update(encoded_name)
            digest.update(len(payload).to_bytes(8, "big"))
            digest.update(payload)

    assert CAPTURE_HARNESS in names
    assert capabilities["BUILD_MODE"] == CAPTURE_BUILD
    assert capabilities["CAPTURE_HARNESS_ENABLED"] is True
    assert capabilities["DEVELOPMENT_MUTATION_ENABLED"] is True
    assert capabilities["CAPTURE_CONTRACT_VERSION"] == 29
    assert capabilities["CAPTURE_RUNTIME_PACKAGE"] == "capture"
    assert derivative == {
        "capture_archive": str(output.resolve()),
        "capture_archive_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "capture_only_entries": capture_only,
        "mode_specific_entries": [CAPABILITY_MODULE],
        "production_archive": str(production_output.resolve()),
        "production_archive_sha256": hashlib.sha256(
            production_output.read_bytes()
        ).hexdigest(),
        "shared_payload_entry_count": len(shared_names),
        "shared_payload_sha256": digest.hexdigest(),
        "shared_payloads_identical": True,
    }
    assert CAPTURE_HARNESS in capture_only
    assert any(name.startswith(f"{CAPTURE_SUBTREE}/") for name in capture_only)
    with pytest.raises(ValueError, match="package entries"):
        capture_derivative_report(output, output)


def test_package_build_is_byte_reproducible(
    package_archives: dict[str, Path],
) -> None:
    first = package_archives["production"]
    second = package_archives["production_rebuild"]

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


def test_capture_build_requires_a_separate_explicit_target() -> None:
    with pytest.raises(ValueError, match="explicit output"):
        build(CAPTURE_BUILD)

    with pytest.raises(ValueError, match="cannot overwrite"):
        build(CAPTURE_BUILD, output=OUTPUT)


def test_atomic_build_preserves_previous_artifact_and_removes_temporary_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "anki_garden.ankiaddon"
    previous = b"previous valid release candidate"
    target.write_bytes(previous)

    def fail_after_partial_write(temporary: Path, _mode: str) -> None:
        temporary.write_bytes(b"partial replacement")
        raise OSError("simulated package write failure")

    monkeypatch.setattr(package_addon, "_write_archive", fail_after_partial_write)
    with pytest.raises(OSError, match="simulated package write failure"):
        package_addon.build(PRODUCTION_BUILD, output=target)

    assert target.read_bytes() == previous
    assert not list(tmp_path.glob(f".{target.name}.*.tmp"))


def test_compression_uses_maximum_deflate_with_strictly_smaller_stored_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compressible = b"anki-garden" * 4096
    incompressible = bytes(range(256))

    assert _raw_deflated_size(compressible) < len(compressible)
    assert _compression_for(compressible) == zipfile.ZIP_DEFLATED
    assert _raw_deflated_size(incompressible) > len(incompressible)
    assert _compression_for(incompressible) == zipfile.ZIP_STORED

    monkeypatch.setattr(package_addon, "_raw_deflated_size", len)
    assert package_addon._compression_for(b"equal-size") == zipfile.ZIP_DEFLATED
