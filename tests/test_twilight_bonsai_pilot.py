from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from ankigarden.ui.plant_display import plant_layout


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "ankigarden" / "assets" / "manifest.json"
STAGES = ("seed", "sprout", "young", "mature", "flowering", "rare")
SIZES = ((960, 720, "dashboard"), (960, 540, "dashboard"), (960, 400, "home"))


def _rows() -> list[dict]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))["assets"]


def _background(rows: list[dict]) -> dict:
    matches = [
        row
        for row in rows
        if row.get("asset_id") == "bg_verdant_twilight_any_soil_master_v6"
        and row.get("release_preferred") is True
    ]
    assert len(matches) == 1
    return matches[0]


def _bonsai(rows: list[dict], stage: str) -> dict:
    matches = [
        row for row in rows if row.get("asset_id") == f"plant_bonsai_{stage}_twilight_v6"
    ]
    assert len(matches) == 1
    return matches[0]


def _layouts(rows: list[dict], stage: str, width: int, height: int, context: str) -> list:
    asset = _bonsai(rows, stage)
    return plant_layout(
        width,
        height,
        [
            {
                "plant_id": f"bonsai-{stage}-{slot}",
                "slot_index": slot,
                "species": "bonsai",
                "stage": stage,
                "placement": asset["placement"],
                "canvas_aspect": asset["width"] / asset["height"],
            }
            for slot in range(6)
        ],
        _background(rows)["placement"],
        surface_context=context,
        composition_count=6,
        protected_status=False,
        reserve_move_controls=False,
    )


def test_bonsai_line_has_six_clean_direct_soil_assets_and_gradual_stage_scaling() -> None:
    rows = _rows()
    scales: list[float] = []
    for stage in STAGES:
        asset = _bonsai(rows, stage)
        placement = asset["placement"]
        assert asset["release_preferred"] is True
        assert asset["alpha"] is True
        assert placement["base_type"] == "direct_soil"
        assert placement["ground_anchor"] == placement["soil_contact"]
        assert placement["release_layout_candidate"] is True
        assert placement["review_provenance"] == "verdant-twilight-line-contact-sheet-v6"
        path = ROOT / "ankigarden" / asset["file"]
        with Image.open(path) as image:
            assert image.mode == "RGBA"
            alpha = image.getchannel("A")
            assert alpha.getextrema() == (0, 255)
            assert alpha.getbbox() is not None
        scales.append(placement["scene_scale_correction"] * placement["visual_scale_correction"])
    assert scales[:5] == sorted(scales[:5])
    assert scales[1] >= scales[0] * 1.14
    # Young is intentionally tall and sparse, so its rendered area grows more
    # than this width correction alone suggests.
    assert scales[2] >= scales[1] * 1.06
    assert scales[3] >= scales[2] * 1.12
    assert scales[4] >= scales[3] * 1.14
    assert scales[-2] * 0.90 <= scales[-1] <= scales[-2]


@pytest.mark.parametrize("stage", STAGES)
def test_each_bonsai_stage_is_centered_seated_and_contained_on_all_six_beds(stage: str) -> None:
    rows = _rows()
    for width, height, context in SIZES:
        layouts = _layouts(rows, stage, width, height, context)
        assert len(layouts) == 6
        assert [layout.z_depth for layout in layouts] == sorted(layout.z_depth for layout in layouts)
        for layout in layouts:
            assert layout.surface_kind == "soil"
            assert layout.allowed_base_types == ("direct_soil",)
            assert layout.contact_plane.contains(*layout.ground_anchor)
            assert layout.base_rect.x >= layout.contact_plane.x - 0.5
            assert layout.base_rect.right <= layout.contact_plane.right + 0.5
            assert layout.target_error <= 0.01
            assert layout.visible.x >= 0 and layout.visible.right <= width
            assert layout.visible.y >= 0 and layout.visible.bottom <= height
            assert not layout.validation_warnings
            if stage == "seed":
                assert layout.visible.width >= 18
                assert layout.visible.height >= 14


def test_bonsai_growth_reads_gradually_and_rare_is_full_but_slot_safe() -> None:
    rows = _rows()
    for width, height, context in SIZES:
        by_stage = {
            stage: _layouts(rows, stage, width, height, context)
            for stage in STAGES
        }
        for slot in range(6):
            areas = [
                by_stage[stage][slot].visible.width * by_stage[stage][slot].visible.height
                for stage in STAGES[:5]
            ]
            assert areas == sorted(areas)
            assert areas[3] <= areas[4] * 0.82
            flowering = by_stage["flowering"][slot]
            rare = by_stage["rare"][slot]
            assert flowering.visible.width * 0.90 <= rare.visible.width <= flowering.visible.width * 1.02
            assert rare.visible.height <= flowering.visible.height * 1.02
            assert rare.visible.area >= flowering.visible.area * 0.95
            assert rare.slot_envelope.contains(
                rare.visible.x + rare.visible.width / 2,
                rare.visible.y + rare.visible.height / 2,
            )
            assert not rare.validation_warnings


def test_later_bonsai_stages_keep_the_same_centered_bed_anchor() -> None:
    rows = _rows()
    later_stages = ("young", "mature", "flowering", "rare")
    for width, height, context in SIZES:
        by_stage = {
            stage: _layouts(rows, stage, width, height, context)
            for stage in later_stages
        }
        for slot in range(6):
            anchors = [by_stage[stage][slot].ground_anchor for stage in later_stages]
            assert all(anchor == pytest.approx(anchors[0], abs=0.01) for anchor in anchors[1:])
