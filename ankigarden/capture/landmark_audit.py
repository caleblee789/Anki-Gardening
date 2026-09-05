"""Supplemental native evidence for the six cosmetic Garden Landmarks."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path

from aqt.qt import QApplication, QEvent, QRectF, QRegion

from ..balance_catalog import LANDMARKS
from ..environment import SCENERY_CATALOG
from ..models.state import GardenProjectState
from ..ui.landmark_display import (
    landmark_asset_identity_matches,
    project_garden_landmark_rect,
    project_landmark_artwork_rect,
)


def _settle() -> None:
    app = QApplication.instance()
    app.processEvents()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def capture_landmark_audit(runner) -> None:
    """Render every existing asset in both views without a gameplay commit.

    Only the disposable capture state's displayed Landmark and scenery are
    varied. An exact backup restores even an interrupted run; no purchase,
    construction, reward, inventory, or bonus operation is called.
    """
    if getattr(runner, "_landmark_audit_captured", False):
        return
    runner._landmark_audit_captured = True
    dashboard = runner.app.dashboard
    storage = runner.app.storage
    snapshot = runner._capture_fixture_state_snapshot(
        "landmark-visual-audit", exact_ledger_restore=True,
    )
    original_size = dashboard.size()
    panel = dashboard.collection_section.appearance
    original_state = deepcopy(storage.state.to_dict())
    original_target = storage.state.garden_project.selected_project_id
    output = runner.session_dir / "landmark-audit"
    output.mkdir(exist_ok=True)
    records = []
    restored = False

    def inspect_and_save(landmark_id, scenery, scene, surface):
        _settle()
        # Grabbing paints the current frame, so layer evidence refers to this
        # asset rather than the previous item in the sequence.
        scene.grab()
        canvas = scene._garden_canvas_rect()
        box = QRectF(*project_garden_landmark_rect(
            canvas.x(), canvas.y(), canvas.width(), canvas.height(), landmark_id,
        ))

        def painted_bounds(path, target, *, contain=True):
            source = scene._pixmap_for(path)
            if source is None:
                return None, None
            opaque = QRegion(source.mask()).boundingRect()
            if opaque.isEmpty():
                return None, None
            if contain:
                scale = min(target.width() / source.width(), target.height() / source.height())
                scale_x = scale_y = scale
                draw_left = target.x() + (target.width() - source.width() * scale) / 2
                draw_top = target.y() + (target.height() - source.height() * scale) / 2
            else:
                scale_x = target.width() / source.width()
                scale_y = target.height() / source.height()
                draw_left, draw_top = target.x(), target.y()
            return QRectF(
                draw_left + opaque.x() * scale_x, draw_top + opaque.y() * scale_y,
                opaque.width() * scale_x, opaque.height() * scale_y,
            ), opaque

        scene.geometry_layout()
        # Derive occupied bounds from the same raster and contain transform
        # used by the painter. Optional manifest accessory exclusions are not
        # present in every resolved planter family; empty metadata is not
        # evidence that the beds are clear.
        bed_boxes = []
        bed_assets = []
        family = scene._planter_family_record()
        for placement in scene._slot_placements.values():
            layer = scene._planter_layer_record(placement, family, foreground=False)
            if layer is None:
                continue
            bed_path, target = layer
            painted, opaque = painted_bounds(bed_path, target)
            if painted is None:
                continue
            bed_boxes.append(painted)
            bed_assets.append({"bed": placement.slot_index, "asset": bed_path,
                               "source_opaque_bounds": list(opaque.getRect())})
        value = scene.scene.get("asset_paths", {}).get("landmark")
        path = Path(str(value.get("path", ""))) if isinstance(value, dict) else None
        artwork_box = QRectF(*project_landmark_artwork_rect(
            canvas.x(), canvas.y(), canvas.width(), canvas.height(), landmark_id,
        ))
        landmark_painted, _ = painted_bounds(str(path), artwork_box, contain=False) if path else (None, None)
        checks = {
            "correct_displayed_id": scene.scene.get("landmark_id") == landmark_id,
            "correct_scenery": scene.scene.get("visible_scenery", scene.scene.get("scenery")) == scenery,
            "matching_catalog_asset": landmark_asset_identity_matches(value, landmark_id),
            "asset_file_present": bool(path and path.is_file()),
            "rendered_landmark_layer": "garden-landmark" in scene._feature_layer_trace,
            "landmark_within_scene": canvas.contains(box),
            "landmark_clear_of_beds": landmark_painted is not None and len(bed_boxes) == 6 and all(not landmark_painted.intersects(bed) for bed in bed_boxes),
            "construction_target_preserved": storage.state.garden_project.selected_project_id == original_target,
        }
        name = f"{len(records) + 1:02d}-{landmark_id}-{surface}-{dashboard.width()}x{dashboard.height()}-{scenery}"
        image_path = output / f"{name}.png"
        checks["screenshot_saved"] = bool(dashboard.grab().save(str(image_path), "PNG"))
        records.append({
            "landmark_id": landmark_id, "surface": surface, "scenery": scenery,
            "window": [dashboard.width(), dashboard.height()],
            "landmark_box": list(box.getRect()), "scene_canvas": list(canvas.getRect()),
            "artwork_box": list(artwork_box.getRect()),
            "painted_landmark_region": list(landmark_painted.getRect()) if landmark_painted is not None else [],
            "painted_bed_regions": [list(bed.getRect()) for bed in bed_boxes],
            "painted_bed_assets": bed_assets,
            "asset": str(path) if path else "",
            "asset_sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path and path.is_file() else "",
            "screenshot": str(image_path),
            "sha256": hashlib.sha256(image_path.read_bytes()).hexdigest() if image_path.is_file() else "",
            "checks": checks,
        })

    try:
        scenarios = [(1040, 720, "default", True), (860, 580, "spring", True)]
        scenarios.extend((1040, 720, scenery, False) for scenery in (
            "summer", "autumn", "snowy", "rainbow_horizon", "halloween", "full_moon", "eclipse",
        ))
        for width, height, scenery, include_collection in scenarios:
            dashboard.resize(width, height)
            for definition in LANDMARKS:
                landmark_id = str(definition.landmark_id)
                state = storage.state
                state.inventory["scenery"] = list(SCENERY_CATALOG)
                state.selected_background = scenery
                state.loadout.visibility["scenery"] = True
                state.garden_project = GardenProjectState(
                    landmark_highest_claimed_tier=len(LANDMARKS),
                    displayed_landmark_tier_id=landmark_id,
                    selected_project_id=original_target,
                )
                before = deepcopy(state.to_dict())
                dashboard.refresh_all()
                dashboard.open_section("garden")
                dashboard.scene.dismiss_selection()
                dashboard.toast_region.clear()
                inspect_and_save(landmark_id, scenery, dashboard.scene, "garden")
                if include_collection:
                    dashboard.open_section("collection", "garden-landmarks")
                    panel.discard_preview()
                    panel.setup_scroll.verticalScrollBar().setValue(0)
                    inspect_and_save(landmark_id, scenery, panel.preview_scene, "collection")
                unchanged = before == storage.state.to_dict()
                records[-1]["checks"]["rendering_does_not_mutate_state"] = unchanged
                if include_collection:
                    records[-2]["checks"]["rendering_does_not_mutate_state"] = unchanged
    finally:
        runner._restore_capture_fixture_state(snapshot)
        restored = original_state == storage.state.to_dict()
        dashboard.resize(original_size)
        dashboard.refresh_all()
        dashboard.open_section("collection", "scenery")
        panel.discard_preview()
        _settle()
        passed = restored and len(records) == 66 and all(
            all(row["checks"].values()) for row in records
        )
        (output / "landmark-audit.json").write_text(json.dumps({
            "passed": passed, "restored_original_state": restored,
            "source_artwork_modified": False, "records": records,
        }, indent=2))
    if not passed:
        failures = [{"landmark_id": row["landmark_id"], "surface": row["surface"],
                     "failed": [key for key, value in row["checks"].items() if not value]}
                    for row in records if not all(row["checks"].values())]
        raise RuntimeError(f"Landmark visual audit failed: restored={restored}, {failures}")
