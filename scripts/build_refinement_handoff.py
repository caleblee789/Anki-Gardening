#!/usr/bin/env python3
"""Package validated v29 captures into five independently assignable briefs."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import shutil
import zipfile
from pathlib import Path


OWNERSHIP = (
    "Garden scene, onboarding, welcome, plant inspectors and decoration inspector. Own shared workspace navigation integration; collect focused patches from the other four agents.",
    "CollectionSection, plant/species details, appearance selection, equipment and additional bonuses. Coordinate shared dashboard.py edits by class or method; do not replace the whole file.",
    "Shop catalogs, purchase confirmation/receipt, Fertilizer and Growth Charge selection and outcomes. Keep quoted and committed engine results authoritative.",
    "Progress pages, Trophy Room, GardenSettingsDialog and diagnostics. Preserve staged Save/Cancel behavior and existing scrolling owners.",
    "Anki Home card, Reviewer HUD, reward list/dock, Session Summary and Sync Rewards. Preserve host controls, summary coordination and focus behavior.",
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
    "progress-today-details": "Progress → Today → expand details",
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
)


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--visual-review", type=Path, required=True)
    parser.add_argument("--source-snapshot", type=Path, required=True)
    parser.add_argument("--supporting-evidence", type=Path, action="append", default=[])
    args = parser.parse_args()
    report = read(args.report)
    manifest_path = Path(report["manifest"])
    manifest = read(manifest_path)
    sheet_index_path = Path(report["contact_sheet_index"])
    sheet_index = read(sheet_index_path)
    review = read(args.visual_review)
    pages = sheet_index["pages"]
    captures = manifest["captures"]
    labels = [row["label"] for row in captures]
    assignments = [label for page in pages for label in page["surface_ids"]]
    if (not report.get("capture_complete") or len(captures) != 51 or len(pages) != 5
            or len(set(assignments)) != 51 or set(assignments) != set(labels)):
        raise SystemExit("Handoff requires complete 51-surface, five-sheet validated evidence")
    if set(NAVIGATION) != set(labels):
        raise SystemExit("Public navigation paths must cover the exact inventory")
    if report.get("surface_validation", {}).get("status") != "valid" or report.get("contact_sheet_validation", {}).get("status") != "valid":
        raise SystemExit("Independent surface and sheet validation must pass")
    if (set(review.get("reviewed_surface_ids", [])) != set(labels)
            or set(review.get("reviewed_sheets", [])) != {p["file"] for p in pages}):
        raise SystemExit("Every raw image and every sheet must be visually reviewed")
    if review.get("raw_sha256") != {row["label"]: row["png_sha256"] for row in captures}:
        raise SystemExit("Visual review must bind the exact raw PNG hashes")
    if review.get("sheet_sha256") != {p["file"]: sha(sheet_index_path.parent / p["file"]) for p in pages}:
        raise SystemExit("Visual review must bind the exact contact-sheet hashes")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    raw = output / "raw"
    raw.mkdir()
    provenance = output / "provenance"
    provenance.mkdir()
    supporting_reports = {}
    for source in [Path(__file__), *args.supporting_evidence]:
        target = provenance / source.name
        if target.exists():
            raise SystemExit(f"Duplicate supporting evidence name: {source.name}")
        shutil.copy2(source, target)
        supporting_reports[source.name] = sha(target)
    snapshot = args.source_snapshot.resolve()
    source_inventory = read(snapshot / "source-snapshot.json")
    for entry in source_inventory["files"]:
        path = snapshot / entry["path"]
        if sha(path) != entry["sha256"]:
            raise SystemExit(f"Frozen source changed: {path}")
        if path.suffix == ".py" or path.name == "capture-contract-v29.json":
            dest = output / "source" / entry["path"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
    shutil.copy2(snapshot / "source-snapshot.json", provenance / "source-snapshot.json")
    # Retain immutable original records together with their native evidence
    # archive. Its lineage, isolation gates and validation are the
    # original machine-verifiable evidence; coverage-index is the portable map.
    evidence_archive = Path(report["archive"])
    if sha(evidence_archive) != report["archive_sha256"]:
        raise SystemExit("Native evidence archive hash changed")
    shutil.copy2(evidence_archive, provenance / evidence_archive.name)
    package_hashes = {}
    for key, digest_key in (("production_package", "production_package_sha256"), ("package", "package_sha256")):
        if sha(Path(report[key])) != report[digest_key]:
            raise SystemExit(f"Package hash mismatch: {key}")
        package_hashes[key] = report[digest_key]
        shutil.copy2(Path(report[key]), provenance / Path(report[key]).name)
    rows = {}
    for row in captures:
        source = Path(row["path"])
        source = source if source.is_absolute() else manifest_path.parent / source
        if sha(source) != row["png_sha256"]:
            raise SystemExit(f"Changed raw capture: {row['label']}")
        dest = raw / source.name
        shutil.copy2(source, dest)
        rows[row["label"]] = {"raw_image": str(dest.relative_to(output)), "sha256": sha(dest),
                              "scenario_id": row["scenario_id"], "fixture_id": row["fixture_id"],
                              "scenario_step": row["scenario_step"]}
    contract = manifest["render_inputs"]["capture_contract_snapshot"]
    specs = {row["id"]: row for row in contract["surfaces"] if row["active"]}
    links = []
    for index, page in enumerate(pages, 1):
        filename = page["file"]
        shutil.copy2(sheet_index_path.parent / filename, output / filename)
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
    shutil.copy2(args.visual_review, output / "visual-review.json")
    shutil.copy2(args.report, output / "capture-report.json")
    shutil.copy2(manifest_path, output / "capture-manifest.json")
    shutil.copy2(sheet_index_path, output / "contact-sheet-set.json")
    (output / "validation-report.json").write_text(json.dumps({
        "capture_complete": True, "expected_surfaces": 51, "valid_captures": 51,
        "sheets": 5, "omissions": [], "duplicates": [], "package_hashes": package_hashes,
        "supporting_evidence_sha256": supporting_reports,
        "surface_validation": report["surface_validation"],
        "contact_sheet_validation": report["contact_sheet_validation"],
        "visual_review_complete": True, "quality_status": "review-required", "release_ready": False,
        "provenance_note": "Original manifests retain source paths; coverage-index.json maps portable raw files. The native archive retains original lineage; both verified packages are beside it in provenance.",
    }, indent=2) + "\n")
    coverage = {"surface_count": 51, "sheet_count": 5, "quality_status": "review-required",
                "release_ready": False, "production_package_sha256": report.get("production_package_sha256"),
                "capture_package_sha256": report.get("capture_package_sha256", report.get("package_sha256")),
                "source_manifest": str(manifest_path), "surfaces": rows,
                "excluded": [{"surface_id": "collection-landmarks-page", "reason": "Landmarks disabled in current release; historical evidence preserved."}]}
    (output / "coverage-index.json").write_text(json.dumps(coverage, indent=2) + "\n")
    (output / "README.md").write_text("# Anki Garden UI refinement handoff\n\n51 current surfaces across five agent assignments.\n\n" + "\n".join(links) +
        "\n\n[Coverage and provenance](coverage-index.json) · [Validation report](validation-report.json) · [Visual review](visual-review.json)\n\nRaw PNGs are authoritative. Sheet padding is not application UI. Caption dimensions use Qt logical pixels; Retina raw images contain twice as many pixels on each axis. Codex has inspected all raw images and sheets; the sheets' pending visual-review label refers to the later human refinement review.\n\nThe collapsed Reviewer label clipping is preserved and documented in brief 5. Landmarks is disabled and excluded; historical captures remain preserved.\n\nStatus: `review-required`; `release_ready: false`.\n" +
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
