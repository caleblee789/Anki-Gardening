from pathlib import Path, PureWindowsPath

import pytest

from scripts.build_refinement_handoff import CopyPlan, evidence_file, relative_path, sha


pytestmark = pytest.mark.release_evidence


def test_handoff_copies_verified_inputs_only_after_complete_preflight(tmp_path):
    selected = tmp_path / "selected"
    selected.mkdir()
    source = selected / "source.py"
    source.write_text("# frozen source\n")
    output = tmp_path / "handoff"
    plan = CopyPlan(output)
    plan.add(evidence_file(str(source), selected, [selected]), PureWindowsPath("source/source.py"), sha(source))
    assert not output.exists()
    outside = tmp_path / "outside.py"
    outside.write_text("# other input\n")
    (selected / "linked.py").symlink_to(outside)
    with pytest.raises(SystemExit, match="outside"):
        evidence_file("linked.py", selected, [selected])
    assert not output.exists()
    with pytest.raises(SystemExit, match="hash"):
        plan.add(source, "bad.py", None)
    assert not output.exists()
    plan.copy()
    assert (output / "source/source.py").read_bytes() == source.read_bytes()
    assert not (output / "bad.py").exists()
    assert outside.read_text() == "# other input\n"


@pytest.mark.parametrize("name", ["../page.png", "/page.png", "folder/page.png", "folder\\page.png", "C:page.png"])
def test_contact_sheet_names_must_be_portable_basenames(name):
    with pytest.raises(SystemExit, match="relative evidence path"):
        relative_path(name, basename=True)


def test_handoff_rejects_destination_aliases_and_symlink_escapes(tmp_path):
    source = tmp_path / "source.py"
    source.write_text("# source\n")
    output = tmp_path / "handoff"
    plan = CopyPlan(output, reserved=("README.md",))
    plan.add(source, "raw/Page.png")
    for name in ("raw/page.png", "README.md/child", "../other.py"):
        with pytest.raises(SystemExit):
            plan.add(source, name)
    assert not output.exists()
    output.mkdir()
    (output / "source").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(SystemExit, match="leaves its selected root"):
        CopyPlan(output).add(source, "source/other.py")
    assert not (tmp_path / "other.py").exists()
