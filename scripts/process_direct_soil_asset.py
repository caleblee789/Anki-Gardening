from __future__ import annotations

import argparse
from collections import deque
from pathlib import Path

from PIL import Image, ImageFilter


def _is_boundary_chroma_spill(pixel: tuple[int, int, int, int]) -> bool:
    """Return whether a visible edge pixel still carries a chroma-key color."""
    red, green, blue, alpha = pixel
    if alpha < 16:
        return False
    magenta_spill = (
        red >= 220
        and blue >= 180
        and green <= 75
        and min(red, blue) - green >= 125
    )
    cyan_spill = red <= 20 and green >= 245 and blue >= 245
    return magenta_spill or cyan_spill


def _despill_transparency_boundary(
    image: Image.Image,
    *,
    boundary_radius: int = 2,
    replacement_radius: int = 12,
) -> tuple[Image.Image, int]:
    """Replace chroma-contaminated edge RGB without changing the alpha mask.

    Image generators can leave a one- or two-pixel magenta/cyan matte around an
    otherwise clean cutout. Making those pixels transparent erodes fine leaves,
    petals, and roots, so this pass copies color from the closest clean visible
    subject pixel while preserving the original alpha byte exactly.
    """

    radius = max(1, int(boundary_radius))
    search_radius = max(radius + 1, int(replacement_radius))
    rgba = image.convert("RGBA")
    width, height = rgba.size
    alpha = rgba.getchannel("A")
    near_transparency = alpha.point(
        lambda value: 255 if value < 16 else 0
    ).filter(ImageFilter.MaxFilter(radius * 2 + 1))
    pixels = rgba.load()
    near_pixels = near_transparency.load()
    alpha_pixels = alpha.load()
    candidate_mask = bytearray(width * height)
    candidates: list[tuple[int, int]] = []

    for y in range(height):
        for x in range(width):
            if near_pixels[x, y] and _is_boundary_chroma_spill(pixels[x, y]):
                candidate_mask[y * width + x] = 1
                candidates.append((x, y))

    source = rgba.copy()
    source_pixels = source.load()
    for x, y in candidates:
        replacement: tuple[int, int, int, int] | None = None
        for distance in range(1, search_radius + 1):
            choices: list[tuple[int, int, int, int, int, int]] = []
            left, right = max(0, x - distance), min(width - 1, x + distance)
            top, bottom = max(0, y - distance), min(height - 1, y + distance)
            for candidate_y in range(top, bottom + 1):
                for candidate_x in range(left, right + 1):
                    if max(abs(candidate_x - x), abs(candidate_y - y)) != distance:
                        continue
                    index = candidate_y * width + candidate_x
                    if (
                        candidate_mask[index]
                        or alpha_pixels[candidate_x, candidate_y] < 16
                    ):
                        continue
                    pixel = source_pixels[candidate_x, candidate_y]
                    if _is_boundary_chroma_spill(pixel):
                        continue
                    # Prefer confidently opaque, interior pixels; coordinate
                    # tie-breakers keep the raster byte-for-byte deterministic.
                    choices.append(
                        (
                            1 if pixel[3] >= 192 else 0,
                            1 if near_pixels[candidate_x, candidate_y] == 0 else 0,
                            pixel[3],
                            -candidate_y,
                            -candidate_x,
                            index,
                        )
                    )
            if choices:
                source_index = max(choices)[-1]
                replacement = source_pixels[source_index % width, source_index // width]
                break
        if replacement is None:
            raise ValueError(
                f"could not find clean subject color within {search_radius}px of {(x, y)}"
            )
        _red, _green, _blue, original_alpha = pixels[x, y]
        pixels[x, y] = (*replacement[:3], original_alpha)

    return rgba, len(candidates)


def despill_transparency_boundary(
    source: Path,
    output: Path,
    *,
    boundary_radius: int = 2,
    replacement_radius: int = 12,
) -> None:
    """Write an RGBA cutout with deterministic, alpha-preserving edge color."""

    with Image.open(source) as opened:
        original = opened.convert("RGBA")
    original_alpha = original.getchannel("A").tobytes()
    result, replaced = _despill_transparency_boundary(
        original,
        boundary_radius=boundary_radius,
        replacement_radius=replacement_radius,
    )
    if result.getchannel("A").tobytes() != original_alpha:
        raise RuntimeError("boundary despill changed the alpha silhouette")
    output.parent.mkdir(parents=True, exist_ok=True)
    result.save(output, "PNG", optimize=True)
    print(f"Wrote {output} despilled_boundary_pixels={replaced}")


def _border_key(image: Image.Image) -> tuple[int, int, int]:
    rgb = image.convert("RGB")
    samples: list[tuple[int, int, int]] = []
    for x in range(rgb.width):
        samples.append(rgb.getpixel((x, 0)))
        samples.append(rgb.getpixel((x, rgb.height - 1)))
    for y in range(rgb.height):
        samples.append(rgb.getpixel((0, y)))
        samples.append(rgb.getpixel((rgb.width - 1, y)))
    channels = [sorted(pixel[index] for pixel in samples) for index in range(3)]
    middle = len(samples) // 2
    return channels[0][middle], channels[1][middle], channels[2][middle]


def _distance(pixel: tuple[int, int, int], key: tuple[int, int, int]) -> float:
    return sum((int(value) - int(reference)) ** 2 for value, reference in zip(pixel, key)) ** 0.5


def normalize_transparent_height(
    source: Path,
    output: Path,
    *,
    vertical_scale: float,
    remove_small_border_components: bool = False,
    max_border_component_pixels: int = 64,
    preview: Path | None = None,
) -> None:
    """Shorten an RGBA silhouette while preserving its visible soil contact.

    This is a geometry-only correction for an already keyed runtime sprite. It
    keeps the canvas and horizontal silhouette unchanged, and aligns the
    resized confidently opaque silhouette to the same bottom pixel so the
    reviewed ground contact does not drift.
    """

    if not 0.5 <= float(vertical_scale) <= 1.0:
        raise ValueError("vertical scale must be between 0.5 and 1.0")
    image = Image.open(source).convert("RGBA")
    removed_border_pixels = 0
    if remove_small_border_components:
        alpha = image.getchannel("A")
        width, height = image.size
        alpha_pixels = alpha.load()
        visited = bytearray(width * height)
        seeds = [
            *((x, 0) for x in range(width)),
            *((x, height - 1) for x in range(width)),
            *((0, y) for y in range(1, height - 1)),
            *((width - 1, y) for y in range(1, height - 1)),
        ]
        for seed_x, seed_y in seeds:
            start = seed_y * width + seed_x
            if visited[start] or alpha_pixels[seed_x, seed_y] == 0:
                continue
            visited[start] = 1
            queue: deque[tuple[int, int]] = deque([(seed_x, seed_y)])
            component: list[tuple[int, int]] = []
            while queue:
                x, y = queue.popleft()
                component.append((x, y))
                if len(component) > max(1, int(max_border_component_pixels)):
                    raise ValueError(
                        "visible subject touches the canvas border; refusing to remove it"
                    )
                for candidate_x, candidate_y in (
                    (x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)
                ):
                    if not (0 <= candidate_x < width and 0 <= candidate_y < height):
                        continue
                    candidate = candidate_y * width + candidate_x
                    if visited[candidate] or alpha_pixels[candidate_x, candidate_y] == 0:
                        continue
                    visited[candidate] = 1
                    queue.append((candidate_x, candidate_y))
            for x, y in component:
                alpha_pixels[x, y] = 0
            removed_border_pixels += len(component)
        image.putalpha(alpha)
    confident = image.getchannel("A").point(lambda value: 255 if value >= 192 else 0)
    source_bounds = confident.getbbox()
    if source_bounds is None:
        raise ValueError(f"transparent source has no confidently visible pixels: {source}")

    resized_height = max(1, round(image.height * float(vertical_scale)))
    # Resize premultiplied color so RGB hidden under transparent chroma pixels
    # cannot bleed into the antialiased edge during vertical normalization.
    # Converting back to straight RGBA after resampling preserves the caller's
    # expected runtime format while keeping the visible matte decontaminated.
    resized = (
        image.copy()
        if resized_height == image.height
        else image.convert("RGBa")
        .resize((image.width, resized_height), Image.Resampling.LANCZOS)
        .convert("RGBA")
    )
    resized_confident = resized.getchannel("A").point(
        lambda value: 255 if value >= 192 else 0
    )
    resized_bounds = resized_confident.getbbox()
    if resized_bounds is None:
        raise ValueError(f"normalized source has no confidently visible pixels: {source}")
    offset_y = source_bounds[3] - resized_bounds[3]
    if offset_y < 0 or offset_y + resized.height > image.height:
        raise ValueError("vertical normalization would leave the source canvas")

    result = Image.new("RGBA", image.size, (0, 0, 0, 0))
    result.alpha_composite(resized, (0, offset_y))
    output.parent.mkdir(parents=True, exist_ok=True)
    result.save(output, "PNG", optimize=True)
    if preview is not None:
        checker = Image.new("RGB", result.size, "#d8d8d8")
        block = 48
        pixels = checker.load()
        for y in range(result.height):
            for x in range(result.width):
                if (x // block + y // block) % 2:
                    pixels[x, y] = (238, 238, 238)
        checker.paste(result, mask=result.getchannel("A"))
        preview.parent.mkdir(parents=True, exist_ok=True)
        checker.save(preview, "PNG", optimize=True)
    print(
        f"Wrote {output} vertical_scale={vertical_scale:.4f} "
        f"contact_row={source_bounds[3] - 1} "
        f"removed_border_pixels={removed_border_pixels}"
    )


def remove_connected_chroma(
    source: Path,
    output: Path,
    *,
    transparent_threshold: float = 8.0,
    connection_threshold: float = 34.0,
    preview: Path | None = None,
    include_enclosed_chroma: bool = True,
) -> None:
    image = Image.open(source).convert("RGBA")
    rgb = image.convert("RGB")
    key = _border_key(image)
    width, height = image.size
    visited = bytearray(width * height)
    background = bytearray(width * height)
    queue: deque[tuple[int, int]] = deque()

    def add(x: int, y: int) -> None:
        index = y * width + x
        if visited[index]:
            return
        visited[index] = 1
        if _distance(rgb.getpixel((x, y)), key) <= connection_threshold:
            background[index] = 1
            queue.append((x, y))

    for x in range(width):
        add(x, 0)
        add(x, height - 1)
    for y in range(height):
        add(0, y)
        add(width - 1, y)

    while queue:
        x, y = queue.popleft()
        if x:
            add(x - 1, y)
        if x + 1 < width:
            add(x + 1, y)
        if y:
            add(x, y - 1)
        if y + 1 < height:
            add(x, y + 1)

    if include_enclosed_chroma:
        # Dense plants form closed loops between stems, leaves, and petals.
        # A flat key-colored pixel is still background inside those loops, but
        # cannot be reached by the border flood. Marking only key-near pixels
        # preserves the subject while removing those enclosed pockets.
        for y in range(height):
            for x in range(width):
                index = y * width + x
                if _distance(rgb.getpixel((x, y)), key) <= connection_threshold:
                    background[index] = 1

    pixels = image.load()
    transparent = partial = 0
    for y in range(height):
        for x in range(width):
            index = y * width + x
            if not background[index]:
                pixels[x, y] = (*pixels[x, y][:3], 255)
                continue
            distance = _distance(rgb.getpixel((x, y)), key)
            if distance <= transparent_threshold:
                alpha = 0
                transparent += 1
            else:
                alpha = round(
                    255
                    * (distance - transparent_threshold)
                    / max(1.0, connection_threshold - transparent_threshold)
                )
                alpha = max(0, min(255, alpha))
                partial += 1
            pixels[x, y] = (*pixels[x, y][:3], alpha)

    image, despilled = _despill_transparency_boundary(image)

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, "PNG", optimize=True)
    if preview is not None:
        checker = Image.new("RGB", image.size, "#d8d8d8")
        block = 48
        pixels = checker.load()
        for y in range(image.height):
            for x in range(image.width):
                if (x // block + y // block) % 2:
                    pixels[x, y] = (238, 238, 238)
        checker.paste(image, mask=image.getchannel("A"))
        preview.parent.mkdir(parents=True, exist_ok=True)
        checker.save(preview, "PNG", optimize=True)
    print(
        f"Wrote {output} key=#{key[0]:02x}{key[1]:02x}{key[2]:02x} "
        f"transparent={transparent} partial={partial} "
        f"despilled_boundary_pixels={despilled}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remove only border-connected chroma from a plant sprite."
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--transparent-threshold", type=float, default=8.0)
    parser.add_argument("--connection-threshold", type=float, default=34.0)
    parser.add_argument("--preview", type=Path)
    parser.add_argument(
        "--already-transparent",
        action="store_true",
        help="Apply only deterministic RGBA geometry normalization; skip chroma removal.",
    )
    parser.add_argument(
        "--despill-boundary-only",
        action="store_true",
        help="Preserve the existing alpha mask and remove only chroma-colored edge RGB.",
    )
    parser.add_argument(
        "--vertical-scale",
        type=float,
        default=1.0,
        help="Vertical RGBA scale used with --already-transparent (default: 1.0).",
    )
    parser.add_argument(
        "--remove-small-border-components",
        action="store_true",
        help="Remove only tiny disconnected alpha components touching the canvas edge.",
    )
    parser.add_argument("--max-border-component-pixels", type=int, default=64)
    parser.add_argument(
        "--connected-only",
        action="store_true",
        help="Leave enclosed key-colored pockets opaque (diagnostic only).",
    )
    args = parser.parse_args()
    if args.despill_boundary_only:
        if args.already_transparent or args.vertical_scale != 1.0:
            parser.error("--despill-boundary-only cannot be combined with geometry options")
        despill_transparency_boundary(args.input, args.out)
        return
    if args.already_transparent:
        normalize_transparent_height(
            args.input,
            args.out,
            vertical_scale=args.vertical_scale,
            remove_small_border_components=args.remove_small_border_components,
            max_border_component_pixels=args.max_border_component_pixels,
            preview=args.preview,
        )
        return
    if args.vertical_scale != 1.0 or args.remove_small_border_components:
        parser.error(
            "--vertical-scale and --remove-small-border-components require --already-transparent"
        )
    remove_connected_chroma(
        args.input,
        args.out,
        transparent_threshold=args.transparent_threshold,
        connection_threshold=args.connection_threshold,
        preview=args.preview,
        include_enclosed_chroma=not args.connected_only,
    )


if __name__ == "__main__":
    main()
