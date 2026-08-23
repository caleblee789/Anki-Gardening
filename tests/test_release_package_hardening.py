from __future__ import annotations

import ast
import zipfile
from pathlib import Path

import pytest

import scripts.package_addon as package_addon
from scripts.package_addon import (
    CAPABILITY_MODULE,
    CAPTURE_BUILD,
    CAPTURE_HARNESS,
    OUTPUT,
    PRODUCTION_BUILD,
    _compression_for,
    _raw_deflated_size,
    build,
)


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_PATH = ROOT / "ankigarden" / "ui" / "dashboard.py"
CAPTURE_FIXTURE_PATH = ROOT / "ankigarden" / "capture_ui_faces.py"


def _literal_constants(source: str) -> dict[str, object]:
    constants: dict[str, object] = {}
    for node in ast.parse(source).body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name):
            constants[target.id] = ast.literal_eval(node.value)
    return constants


def test_production_archive_excludes_capture_surface_and_disables_capabilities(
    tmp_path: Path,
) -> None:
    output = build(
        PRODUCTION_BUILD,
        output=tmp_path / "anki_garden_production.ankiaddon",
    )

    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
        capabilities = _literal_constants(
            archive.read(CAPABILITY_MODULE).decode("utf-8")
        )
        packaged_game = archive.read("game.py").decode("utf-8")
        packaged_ui_sources = {
            name: archive.read(name).decode("utf-8")
            for name in names
            if name.startswith("ui/") and name.endswith(".py")
        }
        packaged_scene = packaged_ui_sources["ui/scene.py"]
        packaged_ui = "\n".join(
            packaged_ui_sources[name] for name in sorted(packaged_ui_sources)
        )

    assert CAPTURE_HARNESS not in names
    assert capabilities["BUILD_MODE"] == PRODUCTION_BUILD
    assert capabilities["CAPTURE_HARNESS_ENABLED"] is False
    assert capabilities["DEVELOPMENT_MUTATION_ENABLED"] is False
    assert "if not build_capabilities.DEVELOPMENT_MUTATION_ENABLED:" in packaged_game
    assert "from ..build_capabilities import CAPTURE_HARNESS_ENABLED" in packaged_scene
    assert "CAPTURE_HARNESS_ENABLED\n            and (" in packaged_scene
    for forbidden_control in (
        "Unlock development tools",
        "Populate test garden",
        "Restore backup",
        "unlock_development",
        "populate_development",
        "restore_development",
    ):
        assert forbidden_control not in packaged_ui


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


def test_automatic_reward_sources_never_present_a_pending_state() -> None:
    dashboard_source = DASHBOARD_PATH.read_text("utf-8")
    capture_fixture_source = CAPTURE_FIXTURE_PATH.read_text("utf-8")

    assert "Reward pending" not in dashboard_source
    assert "Reward pending" not in capture_fixture_source
    assert '"One-time streak achievements"' in dashboard_source
    assert "achievement_presentations(state)" in dashboard_source
    assert "STREAK_REWARD_MILESTONES" not in dashboard_source
