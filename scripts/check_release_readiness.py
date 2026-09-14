#!/usr/bin/env python3
"""Check a retained release record against current source and exact artifacts.

This is a local evidence gate, not an authenticity or anti-tampering service.
Passing test lanes alone cannot satisfy native acceptance or human approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_refinement_handoff import contained_path
from scripts.package_addon import ADDON, PRODUCTION_BUILD, package_files, package_payload

REQUIRED_GATES = (
    "default_tests", "release_qt", "assets", "compile", "package",
    "native_macos_260801", "persistence",
    "review_correctness", "sync_companions", "ui_acceptance",
    "responsiveness", "human_review",
)
PACKAGE_BOUND_GATES = set(REQUIRED_GATES[5:])


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_identity():
    names = subprocess.check_output(
        ["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=ROOT,
    ).decode().split("\0")
    files = {}
    for name in sorted(set(names)):
        path = ROOT / name
        if not name or not path.is_file():
            continue
        parts = Path(name).parts
        if parts[0] not in {"ankigarden", "scripts", "tests", ".github", "docs"} and name not in {"pytest.ini", "README.md"}:
            continue
        if "user_files" in parts and path.name != "README.txt":
            continue
        files[name] = sha(path)
    return {
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "files": files,
        "sha256": hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(),
    }


def junit_counts(path):
    cases = list(ET.parse(path).getroot().iter("testcase"))
    return {
        "tests": len(cases),
        "failed": sum(case.find("failure") is not None or case.find("error") is not None for case in cases),
        "skipped": sum(case.find("skipped") is not None for case in cases),
    }


def check(report_path, *, allow_pending=False):
    report_path = report_path.resolve()
    report = json.loads(report_path.read_text())
    problems = []
    if report.get("schema_version") != 1:
        problems.append("Unsupported release record schema")
    if report.get("source") != source_identity():
        problems.append("Source changed since this evidence was recorded")

    def artifact(record):
        path = contained_path(report_path.parent, record["path"])
        if not path.is_file() or sha(path) != record.get("sha256"):
            raise ValueError(f"Missing or changed evidence: {record['path']}")
        return path

    package_digest = report.get("package", {}).get("sha256")
    try:
        package = artifact(report["package"])
        with zipfile.ZipFile(package) as archive:
            expected = {p.relative_to(ADDON).as_posix(): package_payload(p, PRODUCTION_BUILD)
                        for p in package_files(PRODUCTION_BUILD)}
            if len(archive.namelist()) != len(expected) or set(archive.namelist()) != set(expected):
                raise ValueError("Production package file set differs from source")
            if any(archive.read(name) != payload for name, payload in expected.items()):
                raise ValueError("Production package payload differs from source")
    except (KeyError, ValueError, OSError, zipfile.BadZipFile) as error:
        problems.append(str(error))

    pending = []
    for name in REQUIRED_GATES:
        gate = report.get("gates", {}).get(name, {})
        if gate.get("status") != "pass":
            pending.append(name)
            if gate.get("status") == "fail":
                problems.append(f"Failed gate: {name}")
            continue
        try:
            records = gate.get("evidence", [])
            if not records:
                raise ValueError(f"Passing gate has no retained evidence: {name}")
            paths = [artifact(record) for record in records]
            if name in {"default_tests", "release_qt"}:
                xml_paths = [path for path in paths if path.suffix == ".xml"]
                if not xml_paths:
                    raise ValueError(f"Test gate requires JUnit results: {name}")
                counts = [junit_counts(path) for path in xml_paths]
                if not sum(row["tests"] for row in counts) or any(row["failed"] for row in counts):
                    raise ValueError(f"Empty or failing test evidence: {name}")
                if name == "release_qt" and any(row["skipped"] for row in counts):
                    raise ValueError("Required Qt evidence contains skipped tests")
            if name in PACKAGE_BOUND_GATES and gate.get("package_sha256") != package_digest:
                raise ValueError(f"Native/approval evidence is for another package: {name}")
            expected_version = {"native_macos_260801": {"26.8.1", "26.08.1"}}.get(name)
            if expected_version and (gate.get("platform") != "macOS"
                                     or gate.get("anki_version") not in expected_version):
                raise ValueError(f"Native platform/version is not the required endpoint: {name}")
        except (KeyError, ValueError, OSError, ET.ParseError) as error:
            problems.append(str(error))
    result = {"release_ready": not problems and not pending,
              "pending_gates": pending, "errors": problems,
              "package_sha256": package_digest}
    return result, not problems and (allow_pending or not pending)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--allow-pending", action="store_true",
                        help="Check integrity while retaining pending gates; does not approve release.")
    args = parser.parse_args()
    try:
        result, valid = check(args.report, allow_pending=args.allow_pending)
    except (KeyError, ValueError, OSError, SystemExit) as error:
        print(json.dumps({"release_ready": False, "errors": [str(error)]}))
        return 1
    print(json.dumps(result, indent=2))
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
