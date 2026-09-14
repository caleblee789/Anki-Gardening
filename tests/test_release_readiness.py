import json
import zipfile

from scripts import check_release_readiness as gate


def test_release_gate_requires_current_artifacts_native_evidence_and_unskipped_qt(tmp_path, monkeypatch):
    addon = tmp_path / "addon"
    addon.mkdir()
    source = addon / "__init__.py"
    source.write_text("# production\n")
    package = tmp_path / "candidate.ankiaddon"
    with zipfile.ZipFile(package, "w") as archive:
        archive.write(source, "__init__.py")
    identity = {"sha256": "current source"}
    monkeypatch.setattr(gate, "source_identity", lambda: identity)
    monkeypatch.setattr(gate, "ADDON", addon)
    monkeypatch.setattr(gate, "package_files", lambda _mode: [source])
    monkeypatch.setattr(gate, "package_payload", lambda path, _mode: path.read_bytes())
    tests = tmp_path / "tests.xml"
    tests.write_text('<testsuite><testcase name="passed"/></testsuite>')
    evidence = {"path": tests.name, "sha256": gate.sha(tests)}
    digest = gate.sha(package)
    report = {
        "schema_version": 1, "source": identity,
        "package": {"path": package.name, "sha256": digest},
        "gates": {name: {"status": "pass", "evidence": [evidence],
                         "package_sha256": digest, "platform": "macOS",
                         "anki_version": "26.8.1"}
                  for name in gate.REQUIRED_GATES},
    }
    path = tmp_path / "readiness.json"

    def check():
        path.write_text(json.dumps(report))
        return gate.check(path)

    assert check()[1]
    # Historical reports may retain the retired minimum-version acceptance
    # gate. It remains unverified but no longer blocks this release.
    report["gates"]["native_macos_2507"] = {"status": "pending"}
    assert check()[1]
    report["gates"]["human_review"]["status"] = "pending"
    assert check()[0]["pending_gates"] == ["human_review"]
    report["gates"]["human_review"]["status"] = "pass"
    tests.write_text('<testsuite><testcase name="missing Qt"><skipped/></testcase></testsuite>')
    evidence["sha256"] = gate.sha(tests)
    assert "Required Qt evidence contains skipped tests" in check()[0]["errors"]
    tests.write_text('<testsuite><testcase name="passed"/></testsuite>')
    evidence["sha256"] = gate.sha(tests)
    report["gates"]["persistence"]["package_sha256"] = "older package"
    assert not check()[1]
    report["gates"]["persistence"]["package_sha256"] = digest
    monkeypatch.setattr(gate, "source_identity", lambda: {"sha256": "changed source"})
    assert "Source changed since this evidence was recorded" in check()[0]["errors"]
    monkeypatch.setattr(gate, "source_identity", lambda: identity)
    source.write_text("# changed production\n")
    assert "Production package payload differs from source" in check()[0]["errors"]
