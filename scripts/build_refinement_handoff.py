#!/usr/bin/env python3
"""Package validated v29 captures into independently assignable briefs."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import shutil
import unicodedata
import zipfile
from pathlib import Path, PurePath, PureWindowsPath


_NO_DIGEST = object()

OWNERSHIP = (
    "Garden scene, onboarding, welcome, plant inspectors and decoration inspector. Own shared workspace navigation integration; collect focused patches from the other four agents.",
    "CollectionSection, plant/species details, appearance selection, equipment and additional bonuses. Coordinate shared dashboard.py edits by class or method; do not replace the whole file.",
    "Shop catalogs, purchase confirmation/receipt, Fertilizer and Growth Charge selection and outcomes. Keep quoted and committed engine results authoritative.",
    "Progress pages, Trophy Room, GardenSettingsDialog and diagnostics. Preserve staged Save/Cancel behavior and existing scrolling owners.",
    "Anki Home card, Reviewer HUD, reward list/dock, Session Summary and Sync Rewards. Preserve host controls, summary coordination and focus behavior.",
    "Plant bed progression, requirements and unlocked states. Preserve the engine-owned unlock rules and current scroll behavior.",
)

CODE = (
    "ankigarden/ui/dashboard.py (GardenDashboard, PlantInfoCard, NurturedPlantBar); ankigarden/ui/scene.py; ankigarden/ui/welcome.py; ankigarden/ui/decoration_card.py",
    "ankigarden/ui/dashboard.py (CollectionSection, PlantCollectionPane, PlantStoryDialog, CollectibleDetailDialog and species overview handlers)",
    "ankigarden/ui/dashboard.py (NurseryDialog, PurchaseConfirmationDialog, GrowthChargeConfirmationDialog and item-use handlers)",
    "ankigarden/ui/dashboard.py (GardenProgressDialog, GardenSettingsDialog, ProgressCardGrid); ankigarden/ui/trophy_room.py; ankigarden/ui/garden_studio.py",
    "ankigarden/ui/home_widget.py; ankigarden/ui/reviewer_hud_widget.py; ankigarden/ui/session_summary_card.py; ankigarden/ui/sync_reward_summary.py; ankigarden/hooks/reviewer.py",
)

# These are the public navigation paths an assigned agent can follow. Capture
# executor names remain in the machine index as fixture implementation detail.
NAVIGATION = {
    "progress-plant-beds-starting": "Progress → Plant beds → starting Garden",
    "progress-plant-beds-partial": "Progress → Plant beds → partially unlocked Garden",
    "progress-plant-beds-unlocked": "Progress → Plant beds → all beds unlocked",
    "starter-deck-browser-home": "Anki Decks → first-run Garden Home card",
    "garden-starter-picker": "Home card → Open Garden → choose first plant",
    "garden-starter-selected": "Select starter → placement → Back (selection retained)",
    "garden-starter-placement": "Choose starter → Choose a bed",
    "workspace-starter-awaiting-nurture": "Place starter → select its bed → Nurture available",
    "workspace-welcome-settled": "Nurture first starter → welcome animation settles",
    "workspace-welcome-rewards-expanded": "First Nurture → welcome → View rewards (past-study fixture)",
    "garden-overview": "Open Garden → Garden tab",
    "garden-inspector-nurtured": "Garden → select nurtured plant",
    "garden-inspector-available": "Garden → select another planted plant",
    "garden-move-plant": "Garden → plant inspector → More → Move",
    "workspace-decoration-inspector": "Garden → select displayed decoration",
    "collection-plants-page": "Collection → Plants",
    "collection-species-details": "Collection → Plants → select a species",
    "collection-plant-details": "Collection → Plants → species → plant name",
    "workspace-collection-plant-menu": "Collection → Plants → species → planted row overflow icon",
    "workspace-collection-storage-confirmation": "Collection → Plants → species → More → Move to storage",
    "collection-scenery-page": "Collection → Scenery",
    "workspace-scenery-preview": "Collection → Scenery → select Spring",
    "workspace-scenery-applied-undo": "Collection → Scenery → select Spring → card Equip → Undo visible",
    "collection-decorations-page": "Collection → Decorations",
    "workspace-additional-bonuses-expanded": "Collection → Decorations → Other active bonuses → scroll to lower content",
    "shop-plants-page": "Shop → Plants",
    "shop-scenery-page": "Shop → Scenery",
    "shop-decorations-page": "Shop → Decorations",
    "shop-supplies-page": "Shop → Supplies (top)",
    "workspace-shop-supplies-scroll-end": "Shop → Supplies → scroll to end (lower section)",
    "shop-fertilizer-confirmation": "Shop → Supplies → buy Fertilizer",
    "purchase-confirmation-growth-charge": "Shop → Supplies → buy Growth Charge",
    "shop-purchase-receipt": "Shop → Plants → buy Sunflower Seed → confirm purchase → receipt",
    "garden-use-fertilizer": "Garden → plant inspector → More → Plant supplies → Fertilizer",
    "garden-use-growth-charges": "Garden → plant inspector → More → Plant supplies → Growth Charges",
    "growth-charge-use-ready": "Choose Growth Charge → use confirmation",
    "growth-charge-success-stage-reward": "Confirm Growth Charge → committed stage reward",
    "progress-today-page": "Progress → Today",
    "progress-today-details": "Progress → Activity → retained Growth bonus after a broken streak",
    "progress-achievements-page": "Progress → Achievements (top)",
    "workspace-achievements-scroll-end": "Progress → Achievements → scroll to end (final rows)",
    "workspace-trophy-room": "Progress → Trophy Room (locked and unlocked)",
    "progress-coins-page": "Progress → Coins",
    "garden-settings": "Workspace gear → Settings",
    "workspace-settings-unsaved": "Settings → edit Garden name → unsaved Save/Cancel state",
    "garden-diagnostics": "Settings → Artwork check → scroll to result",
    "workspace-diagnostics-warning-details": "Settings → Artwork check → warning → Technical details → scroll to end",
    "active-deck-browser-home-after-nurture": "Nurture plant → close Garden → Anki Decks Home card",
    "reviewer-hud-expanded": "Anki study → expand Garden Reviewer HUD",
    "workspace-reviewer-collapsed": "Anki study → collapse Garden Reviewer HUD",
    "reviewer-reward-dock-bundle": "Anki study → committed reward → integrated reward dock",
    "workspace-reviewer-rewards-list": "Collapsed Reviewer presentation → expand reward summary",
    "session-summary-after-review": "Study cards → leave Reviewer → Session Summary",
    "sync-rewards-summary": "Anki Home → Sync Rewards receipt (committed offline fixture; network sync disabled)",
}

SYMBOLS = (
    (("ui/dashboard.py", "GardenDashboard"), ("ui/dashboard.py", "PlantInfoCard"),
     ("ui/welcome.py", "WelcomeCard"), ("ui/decoration_card.py", None), ("ui/scene.py", None)),
    (("ui/dashboard.py", "CollectionSection"), ("ui/dashboard.py", "PlantStoryDialog"),
     ("ui/dashboard.py", "_build_species_overview_dialog"), ("ui/dashboard.py", "CollectibleDetailDialog")),
    (("ui/dashboard.py", "NurseryDialog"), ("ui/dashboard.py", "PurchaseConfirmationDialog"),
     ("ui/dashboard.py", "GrowthChargeConfirmationDialog")),
    (("ui/dashboard.py", "GardenProgressDialog"), ("ui/dashboard.py", "GardenSettingsDialog"),
     ("ui/trophy_room.py", None)),
    (("ui/home_widget.py", None), ("ui/reviewer_hud_widget.py", None),
     ("ui/session_summary_card.py", None), ("ui/sync_reward_summary.py", None), ("hooks/reviewer.py", None)),
    (("ui/plant_beds.py", "PlantBedsPage"),),
)


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative_path(value, *, basename=False):
    """Accept portable, unambiguous relative metadata paths only."""
    if isinstance(value, PurePath):
        value = value.as_posix()
    if (not isinstance(value, str) or not value or "\\" in value or "\0" in value or ":" in value
            or PureWindowsPath(value).drive
            or any(part in {"", ".", ".."} for part in value.split("/"))
            or (basename and "/" in value)):
        raise SystemExit(f"Invalid relative evidence path: {value!r}")
    return Path(value)


def contained_path(root, relative):
    root = root.resolve()
    path = (root / relative_path(relative)).resolve()
    if not path.is_relative_to(root):
        raise SystemExit(f"Evidence path leaves its selected root: {relative}")
    return path


def evidence_file(value, parent, roots):
    if (not isinstance(value, str) or not value or "\0" in value
            or (os.name != "nt" and "\\" in value)):
        raise SystemExit(f"Invalid evidence file: {value!r}")
    path = Path(value)
    if not path.is_absolute():
        path = parent / relative_path(value.replace("\\", "/") if os.name == "nt" else value)
    path = path.resolve()
    if not any(path.is_relative_to(root) for root in roots):
        raise SystemExit(f"Evidence file is outside the selected --evidence-root directories: {path}")
    if not path.is_file():
        raise SystemExit(f"Evidence file is missing: {path}")
    return path


class CopyPlan:
    """Preflight every destination and digest before publishing any output."""

    def __init__(self, output, reserved=()):
        self.output = output.resolve()
        self.jobs = []
        self.destinations = set()
        for relative in reserved:
            self.reserve(relative)

    def reserve(self, relative):
        target = contained_path(self.output, relative)
        key = unicodedata.normalize("NFC", target.relative_to(self.output).as_posix()).casefold()
        if any(key == existing or key.startswith(existing + "/")
               or existing.startswith(key + "/") for existing in self.destinations):
            raise SystemExit(f"Duplicate or conflicting handoff destination: {relative}")
        self.destinations.add(key)
        return target

    def add(self, source, relative, expected=_NO_DIGEST):
        target = self.reserve(relative)
        source = source.resolve(strict=True)
        digest = sha(source)
        if expected is not _NO_DIGEST and digest != expected:
            raise SystemExit(f"Evidence hash changed: {source}")
        self.jobs.append((source, target, digest))
        return target, digest

    def copy(self):
        self.output.mkdir(parents=True, exist_ok=False)
        for source, target, digest in self.jobs:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            if sha(target) != digest:
                raise SystemExit(f"Evidence changed during handoff: {source}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--visual-review", type=Path, required=True)
    parser.add_argument("--source-snapshot", type=Path, required=True)
    parser.add_argument("--supporting-evidence", type=Path, action="append", default=[])
    parser.add_argument("--evidence-root", type=Path, action="append", default=[],
                        help="Additional trusted input directory; repeat for packages or sibling capture sets. "
                             "The selected report directory is always allowed.")
    args = parser.parse_args()
    report_path = args.report.resolve(strict=True)
    roots = [report_path.parent, *(path.resolve(strict=True) for path in args.evidence_root)]
    if any(not path.is_dir() for path in roots):
        raise SystemExit("Each --evidence-root must be an existing directory")
    report = read(report_path)
    manifest_path = evidence_file(report["manifest"], report_path.parent, roots)
    manifest = read(manifest_path)
    sheet_index_path = evidence_file(report["contact_sheet_index"], report_path.parent, roots)
    sheet_index = read(sheet_index_path)
    review = read(args.visual_review)
    pages = sheet_index["pages"]
    sheet_sources = {}
    for page in pages:
        name = str(relative_path(page["file"], basename=True))
        if Path(name).suffix.lower() != ".png":
            raise SystemExit("Contact-sheet filenames must end in .png")
        sheet_sources[name] = evidence_file(name, sheet_index_path.parent, [sheet_index_path.parent])
    captures = manifest["captures"]
    labels = [row["label"] for row in captures]
    assignments = [label for page in pages for label in page["surface_ids"]]
    contract = manifest["render_inputs"]["capture_contract_snapshot"]
    specs = {row["id"]: row for row in contract["surfaces"] if row["active"]}
    if (not report.get("capture_complete") or not captures or len(pages) not in {5, 6}
            or len(set(labels)) != len(captures) or len(assignments) != len(captures)
            or len(set(assignments)) != len(assignments)
            or set(assignments) != set(labels) or set(labels) != set(specs)):
        raise SystemExit("Handoff requires every active surface exactly once in validated evidence")
    if not set(labels).issubset(NAVIGATION):
        raise SystemExit("Public navigation paths must cover the exact inventory")
    if report.get("surface_validation", {}).get("status") != "valid" or report.get("contact_sheet_validation", {}).get("status") != "valid":
        raise SystemExit("Independent surface and sheet validation must pass")
    if (set(review.get("reviewed_surface_ids", [])) != set(labels)
            or set(review.get("reviewed_sheets", [])) != {p["file"] for p in pages}):
        raise SystemExit("Every raw image and every sheet must be visually reviewed")
    if review.get("raw_sha256") != {row["label"]: row["png_sha256"] for row in captures}:
        raise SystemExit("Visual review must bind the exact raw PNG hashes")
    if review.get("sheet_sha256") != {p["file"]: sha(sheet_sources[p["file"]]) for p in pages}:
        raise SystemExit("Visual review must bind the exact contact-sheet hashes")
    output = args.output.resolve()
    if output.exists() or output.with_suffix(".zip").exists() or output.with_suffix(".zip").is_symlink():
        raise SystemExit("Handoff output and archive must both be new")
    copies = CopyPlan(output, reserved=("README.md", "validation-report.json", "coverage-index.json"))
    supporting_reports = {}
    for source in [Path(__file__), *args.supporting_evidence]:
        target, digest = copies.add(source, Path("provenance") / source.name)
        supporting_reports[source.name] = digest
    snapshot = args.source_snapshot.resolve()
    inventory_path = evidence_file("source-snapshot.json", snapshot, [snapshot])
    source_inventory = read(inventory_path)
    for entry in source_inventory["files"]:
        relative = relative_path(entry["path"])
        path = evidence_file(str(relative), snapshot, [snapshot])
        if sha(path) != entry["sha256"]:
            raise SystemExit(f"Frozen source changed: {path}")
        if path.suffix == ".py" or path.name == "capture-contract-v29.json":
            copies.add(path, Path("source") / relative, entry["sha256"])
    copies.add(inventory_path, "provenance/source-snapshot.json")
    # Retain immutable original records together with their native evidence
    # archive. Its lineage, isolation gates and validation are the
    # original machine-verifiable evidence; coverage-index is the portable map.
    evidence_archive = evidence_file(report["archive"], report_path.parent, roots)
    copies.add(evidence_archive, Path("provenance") / evidence_archive.name, report["archive_sha256"])
    package_hashes = {}
    for key, digest_key in (("production_package", "production_package_sha256"), ("package", "package_sha256")):
        package = evidence_file(report[key], report_path.parent, roots)
        package_hashes[key] = report[digest_key]
        copies.add(package, Path("provenance") / package.name, report[digest_key])
    rows = {}
    for row in captures:
        source = evidence_file(row["path"], manifest_path.parent, roots)
        dest, digest = copies.add(source, Path("raw") / source.name, row["png_sha256"])
        rows[row["label"]] = {"raw_image": str(dest.relative_to(output)), "sha256": digest,
                              "scenario_id": row["scenario_id"], "fixture_id": row["fixture_id"],
                              "scenario_step": row["scenario_step"]}
    for page in pages:
        filename = page["file"]
        copies.add(sheet_sources[filename], filename)
        copies.reserve(Path(filename).with_suffix(".md"))
    for source, name in ((args.visual_review, "visual-review.json"),
                         (report_path, "capture-report.json"),
                         (manifest_path, "capture-manifest.json"),
                         (sheet_index_path, "contact-sheet-set.json")):
        copies.add(source, name)
    copies.copy()
    links = []
    for index, page in enumerate(pages, 1):
        filename = page["file"]
        title = page["groups"][0]
        brief = output / (Path(filename).stem + ".md")
        code_links = []
        for relative, symbol in SYMBOLS[index-1]:
            source = output / "source/ankigarden" / relative
            line = 1
            if symbol:
                node = next(n for n in ast.walk(ast.parse(source.read_text()))
                            if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name == symbol)
                line = node.lineno
            code_links.append(f"[{symbol or relative}]({source.relative_to(output)}#L{line}) (line {line})")
        lines = [f"# Agent {index}: {title}", "", f"[Contact sheet]({filename})", "",
                 OWNERSHIP[index-1], "", "Frozen code sections: " + "; ".join(code_links), "",
                 "Refine the visible UI using the current native captures as the baseline. Preserve gameplay, transactions, stored state and public navigation. Use the full-resolution PNGs before judging small text or spacing.", "",
                 "Shared theme, copy and navigation changes go through the Garden/onboarding integration owner. Submit focused changes to shared files; never overwrite another agent's work.", "",
                 "| Surface | Native navigation path | Full-resolution image |", "|---|---|---|"]
        for label in page["surface_ids"]:
            spec = specs[label]
            route = spec.get("state_contract", {}).get("profile", {}).get("route") or spec["executor"]
            record = rows[label]
            record.update(sheet=index, sheet_file=filename, route=route, navigation=NAVIGATION[label])
            lines.append(f"| `{label}` | {NAVIGATION[label]} | [PNG]({record['raw_image']}) |")
        findings = [item for item in review.get("findings", []) if item.get("surface_id") in page["surface_ids"]]
        lines.extend(["", "## Observed issues", ""])
        lines.extend(["- " + item["finding"] + f" (`{item['surface_id']}`)" for item in findings] or
                     ["No blocking capture defect observed. The UI remains open for refinement; capture acceptance is not design approval."])
        lines.extend(["", "Evidence status: `quality_status: review-required`; `release_ready: false`.", ""])
        brief.write_text("\n".join(lines))
        links.append(f"{index}. [{title}]({filename}) — {len(page['surface_ids'])} surfaces · [Agent brief]({brief.name})")
    (output / "validation-report.json").write_text(json.dumps({
        "capture_complete": True, "expected_surfaces": len(specs), "valid_captures": len(captures),
        "sheets": len(pages), "omissions": [], "duplicates": [], "package_hashes": package_hashes,
        "supporting_evidence_sha256": supporting_reports,
        "surface_validation": report["surface_validation"],
        "contact_sheet_validation": report["contact_sheet_validation"],
        "visual_review_complete": True, "quality_status": "review-required", "release_ready": False,
        "provenance_note": "Original manifests retain source paths; coverage-index.json maps portable raw files. The native archive retains original lineage; both verified packages are beside it in provenance.",
    }, indent=2) + "\n")
    coverage = {"surface_count": len(captures), "sheet_count": len(pages), "quality_status": "review-required",
                "release_ready": False, "production_package_sha256": report.get("production_package_sha256"),
                "capture_package_sha256": report.get("capture_package_sha256", report.get("package_sha256")),
                "source_manifest": str(manifest_path), "surfaces": rows,
                "excluded": [{"surface_id": "collection-landmarks-page", "reason": "Landmarks disabled in current release; historical evidence preserved."}]}
    (output / "coverage-index.json").write_text(json.dumps(coverage, indent=2) + "\n")
    (output / "README.md").write_text(f"# Anki Garden UI refinement handoff\n\n{len(captures)} current surfaces across {len(pages)} assignments.\n\n" + "\n".join(links) +
        "\n\n[Coverage and provenance](coverage-index.json) · [Validation report](validation-report.json) · [Visual review](visual-review.json)\n\nRaw PNGs are authoritative. Sheet padding is not application UI. Caption dimensions use Qt logical pixels; Retina raw images contain twice as many pixels on each axis. Codex has inspected all raw images and sheets; the sheets' pending visual-review label refers to the later human refinement review.\n\nObserved issues are recorded in the individual briefs. Landmarks is disabled and excluded; historical captures remain preserved.\n\nStatus: `review-required`; `release_ready: false`.\n" +
        ("\n[Capture scope, scenery change and refinement notes](provenance/capture-notes.md)\n" if "capture-notes.md" in supporting_reports else ""))
    archive = output.with_suffix(".zip")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for path in sorted(output.rglob("*")):
            if path.is_file():
                z.write(path, path.relative_to(output.parent), compress_type=(
                    zipfile.ZIP_STORED if path.suffix in {".png", ".zip", ".ankiaddon"}
                    else zipfile.ZIP_DEFLATED))
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:
            raise SystemExit("Handoff archive failed ZIP integrity")
    print(json.dumps({"handoff": str(output), "archive": str(archive), "sha256": sha(archive)}))


if __name__ == "__main__":
    main()
