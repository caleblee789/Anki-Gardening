from __future__ import annotations

import copy
from pathlib import Path

import pytest
from PIL import Image

from scripts.validate_ui_capture import (
    CONTACT_SHEET_PADDING_RGBA,
    CaptureValidationError,
    _count_aligned_rgba_pixels,
    _unpainted_client_record_issues,
    load_capture_contract,
)


ROOT = Path(__file__).resolve().parents[1]
CAPTURE_SOURCE = ROOT / "ankigarden" / "capture" / "runtime.py"
NON_CREAM_RGBA = (9, 19, 29, 255)


def _save_rgba(path: Path, image: Image.Image) -> None:
    assert image.mode == "RGBA"
    image.save(path, format="PNG")


def _pixel_audit(
    *,
    scanned_rect: list[int],
    total: int,
    exempt: int = 0,
    threshold: int = 0,
    exemptions: object | None = None,
) -> dict[str, object]:
    effective = max(0, total - exempt)
    return {
        "color_rgb": list(CONTACT_SHEET_PADDING_RGBA[:3]),
        "match": "exact-rgba-opaque",
        "scanned_rect": scanned_rect,
        "host_region_exemptions": [] if exemptions is None else exemptions,
        "total_cream_pixel_count": total,
        "exempt_cream_pixel_count": exempt,
        "effective_cream_pixel_count": effective,
        "maximum_effective_cream_pixels": threshold,
        "passed": effective <= threshold,
    }


def _reviewer_issues(
    tmp_path: Path,
    *,
    cream_pixels: tuple[tuple[int, int], ...],
    exemptions: object | None = None,
) -> list[str]:
    image = Image.new("RGBA", (16, 16), NON_CREAM_RGBA)
    for point in cream_pixels:
        image.putpixel(point, CONTACT_SHEET_PADDING_RGBA)
    screenshot = tmp_path / "reviewer.png"
    _save_rgba(screenshot, image)
    overlay_bounds = [2, 2, 4, 4]
    scanned_rect = [4, 4, 8, 8]
    overlay_cream = sum(
        4 <= x < 12 and 4 <= y < 12
        for x, y in cream_pixels
    )
    sentinel = _pixel_audit(
        scanned_rect=scanned_rect,
        total=overlay_cream,
        exemptions=exemptions,
    )
    record = {
        "width": 8,
        "height": 8,
        "unpainted_client_pixel_audit": sentinel,
    }
    audit = {
        "reviewer_overlay_geometry": {"overlay_bounds": overlay_bounds},
        "unpainted_client_pixel_audit": copy.deepcopy(sentinel),
    }
    return _unpainted_client_record_issues(
        label="reviewer-answer",
        record=record,
        audit=audit,
        screenshot_path=screenshot,
    )


def test_aligned_rgba_count_ignores_cross_pixel_byte_sequence() -> None:
    payload = bytes((0, 0, 216, 209, 190, 255, 0, 0))

    assert payload.count(bytes(CONTACT_SHEET_PADDING_RGBA)) == 1
    assert _count_aligned_rgba_pixels(
        payload,
        width=2,
        height=1,
        row_stride=8,
    ) == 0


def test_unpainted_audit_ignores_cross_pixel_byte_sequence(tmp_path: Path) -> None:
    image = Image.new("RGBA", (2, 1))
    image.putdata(((0, 0, 216, 209), (190, 255, 0, 0)))
    screenshot = tmp_path / "cross-pixel.png"
    _save_rgba(screenshot, image)
    sentinel = _pixel_audit(scanned_rect=[0, 0, 2, 1], total=0)

    assert _unpainted_client_record_issues(
        label="garden-onboarding",
        record={
            "width": 2,
            "height": 1,
            "unpainted_client_pixel_audit": sentinel,
        },
        audit={"unpainted_client_pixel_audit": copy.deepcopy(sentinel)},
        screenshot_path=screenshot,
    ) == []


def test_aligned_rgba_count_honors_pixels_and_ignores_row_padding() -> None:
    payload = (
        bytes(CONTACT_SHEET_PADDING_RGBA)
        + bytes(CONTACT_SHEET_PADDING_RGBA)
        + bytes(NON_CREAM_RGBA)
        + bytes(CONTACT_SHEET_PADDING_RGBA)
    )

    assert _count_aligned_rgba_pixels(
        payload,
        width=1,
        height=2,
        row_stride=8,
    ) == 1


@pytest.mark.parametrize(
    ("payload", "width", "height", "row_stride"),
    (
        (b"\x00" * 7, 2, 1, 8),
        (b"\x00" * 7, 2, 1, 7),
        (b"\x00" * 5, 1, 1, 4),
    ),
)
def test_aligned_rgba_count_rejects_malformed_buffers(
    payload: bytes,
    width: int,
    height: int,
    row_stride: int,
) -> None:
    with pytest.raises(ValueError, match="RGBA"):
        _count_aligned_rgba_pixels(
            payload,
            width=width,
            height=height,
            row_stride=row_stride,
        )


def test_reviewer_host_pixels_outside_addon_overlay_are_exempt(tmp_path: Path) -> None:
    assert _reviewer_issues(tmp_path, cream_pixels=((0, 0),)) == []


def test_reviewer_cream_inside_addon_overlay_fails(tmp_path: Path) -> None:
    issues = _reviewer_issues(tmp_path, cream_pixels=((6, 6),))

    assert "raw capture contains excess contact-sheet cream pixels" in issues


@pytest.mark.parametrize(
    ("exemptions", "expected"),
    (
        ("not-a-list", "host-region cream exemptions must be a list"),
        ([None], "host-region cream exemption is malformed"),
        (
            [{"kind": "unexpected", "rect": "not-a-rectangle"}],
            "host-region cream exemption rectangle is malformed",
        ),
    ),
)
def test_reviewer_malformed_exemption_collection_fails_closed(
    tmp_path: Path,
    exemptions: object,
    expected: str,
) -> None:
    issues = _reviewer_issues(
        tmp_path,
        cream_pixels=(),
        exemptions=exemptions,
    )

    assert expected in issues


@pytest.mark.parametrize(("effective_cream", "passes"), ((64, True), (65, False)))
def test_home_host_exemption_preserves_exact_64_pixel_threshold(
    tmp_path: Path,
    effective_cream: int,
    passes: bool,
) -> None:
    width, height = 10, 110
    image = Image.new("RGBA", (width, height), NON_CREAM_RGBA)
    host_cream_points = tuple((column, 0) for column in range(5))
    body_cream_points = tuple(
        (index % width, 96 + index // width)
        for index in range(effective_cream)
    )
    for point in (*host_cream_points, *body_cream_points):
        image.putpixel(point, CONTACT_SHEET_PADDING_RGBA)
    screenshot = tmp_path / f"home-{effective_cream}.png"
    _save_rgba(screenshot, image)
    exemptions = [{
        "kind": "anki-home-host-toolbar",
        "rect": [0, 0, width, 96],
        "cream_pixel_count": len(host_cream_points),
    }]
    sentinel = _pixel_audit(
        scanned_rect=[0, 0, width, height],
        total=len(host_cream_points) + effective_cream,
        exempt=len(host_cream_points),
        threshold=64,
        exemptions=exemptions,
    )
    record = {
        "width": width,
        "height": height,
        "unpainted_client_pixel_audit": sentinel,
    }
    audit = {"unpainted_client_pixel_audit": copy.deepcopy(sentinel)}

    issues = _unpainted_client_record_issues(
        label="starter-deck-browser-home",
        record=record,
        audit=audit,
        screenshot_path=screenshot,
    )

    if passes:
        assert issues == []
    else:
        assert "raw capture contains excess contact-sheet cream pixels" in issues


def _write_capture_source(
    path: Path,
    *,
    representative_count: int = 26,
    full_count: int = 126,
) -> None:
    representative = tuple(f"representative-{index}" for index in range(representative_count))
    full = tuple(f"full-{index}" for index in range(full_count))
    path.write_text(
        "CAPTURE_CONTRACT_VERSION = 24\n"
        "CAPTURE_SCENARIO_SCHEMA_VERSION = 1\n"
        f"CAPTURE_FACE_GROUPS = {(('Representative', representative),)!r}\n"
        f"EXHAUSTIVE_CAPTURE_FACE_GROUPS = {(('Full', full),)!r}\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("profile", "representative_count", "full_count", "expected"),
    (
        ("representative", 25, 126, "exactly 26 surfaces, found 25"),
        ("representative", 27, 126, "exactly 26 surfaces, found 27"),
        ("full", 26, 125, "exactly 126 surfaces, found 125"),
        ("full", 26, 127, "exactly 126 surfaces, found 127"),
    ),
)
def test_capture_contract_rejects_noncanonical_surface_count(
    tmp_path: Path,
    profile: str,
    representative_count: int,
    full_count: int,
    expected: str,
) -> None:
    source = tmp_path / "capture_source.py"
    _write_capture_source(
        source,
        representative_count=representative_count,
        full_count=full_count,
    )

    with pytest.raises(CaptureValidationError, match=expected):
        load_capture_contract(source, profile=profile)
