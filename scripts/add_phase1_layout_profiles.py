from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "ankigarden" / "assets" / "manifest.json"


# Bottom-center soil-contact points in the rendered garden. Every count owns
# six unique targets; the first N form the intentional visible composition.
COMPOSITIONS: dict[int, list[tuple[float, float, float]]] = {
    1: [(.50, .84, 1.00), (.35, .80, .90), (.65, .80, .90), (.27, .57, .74), (.49, .52, .78), (.75, .57, .74)],
    2: [(.37, .81, .94), (.63, .81, .94), (.49, .53, .78), (.25, .58, .74), (.75, .58, .74), (.50, .87, 1.00)],
    3: [(.49, .54, .78), (.35, .81, .94), (.65, .81, .94), (.25, .59, .74), (.75, .59, .74), (.51, .88, 1.00)],
    4: [(.26, .57, .76), (.74, .57, .76), (.40, .81, .94), (.60, .81, .94), (.49, .52, .78), (.51, .87, 1.00)],
    5: [(.25, .57, .74), (.49, .52, .78), (.75, .57, .74), (.35, .81, .94), (.65, .81, .94), (.52, .87, 1.00)],
    # Final six-space composition. The third value is perspective projection
    # relative to front-center, not a species or growth-stage scale.
    6: [(.25, .52, .76), (.48, .49, .80), (.76, .53, .76),
        (.29, .84, .93), (.53, .89, 1.00), (.70, .84, .93)],
}

THEMES = {
    "verdant_dusk": {"focal_x": 0.50, "x": (0, 0, 0, 0, 0, 0), "y": (0, 0, 0, 0, 0, 0)},
    "verdant_dawn": {"focal_x": 0.48, "x": (-.01, 0, -.01, 0, 0, 0), "y": (0, 0, 0, 0, 0, 0)},
    "moonlit_study": {"focal_x": 0.52, "x": (.01, -.01, -.01, .01, .01, -.01), "y": (-.01, -.01, -.01, -.01, -.01, -.01)},
}

PROFILES = {
    "4:3": {"focal_y": 0.43, "scale": 0.96, "zone": [0.07, 0.93, 0.49, 0.91]},
    "3:2": {"focal_y": 0.62, "scale": 1.00, "zone": [0.06, 0.94, 0.49, 0.91]},
    "16:9": {"focal_y": 0.72, "scale": 0.96, "zone": [0.05, 0.95, 0.48, 0.91]},
    # The compact preview has a fixed 50:21 art ratio, matching its shared
    # 1000 x 420 layout surface.
    "home": {"focal_y": 0.82, "scale": 1.02, "zone": [0.035, 0.965, 0.48, 0.91]},
}


def _anchor(x: float, y: float, depth_scale: float, *, profile_scale: float, slot: int) -> dict[str, object]:
    far = y < 0.68
    # All spaces share the same front-center physical reference. Perspective
    # is applied once through plant_scale; this prevents accidental double
    # depth scaling while preserving the intended 78-84% rear projection.
    physical_width_ratio = 0.16
    return {
        "x": round(x, 4),
        "y": round(y, 4),
        "depth": round(y, 4),
        "plant_scale": round(profile_scale * depth_scale, 4),
        "physical_width_ratio": physical_width_ratio,
        "footprint": [0.115 if far else 0.145, 0.040 if far else 0.050],
        "label_anchor": [round(x, 4), round(min(.94, y + (0.055 if far else 0.045)), 4)],
    }


def build_profiles(theme: str) -> dict[str, object]:
    theme_tune = THEMES[theme]
    result: dict[str, object] = {}
    for profile_name, profile in PROFILES.items():
        zone = profile["zone"]
        compositions: dict[str, list[dict[str, object]]] = {}
        for count, points in COMPOSITIONS.items():
            rows = []
            for slot, (x, y, depth_scale) in enumerate(points):
                # Keep focal one/two/three-plant arrangements exactly centered;
                # theme-specific path tuning matters once the fuller scene is used.
                if count >= 4:
                    x += float(theme_tune["x"][slot])
                    y += float(theme_tune["y"][slot])
                rows.append(_anchor(x, y, depth_scale, profile_scale=float(profile["scale"]), slot=slot))
            compositions[str(count)] = rows
        focal = [float(theme_tune["focal_x"]), float(profile["focal_y"])]
        result[profile_name] = {
            "focal_point": focal,
            "coordinate_space": "viewport",
            "planting_zone": {"left": zone[0], "right": zone[1], "far_y": zone[2], "near_y": zone[3]},
            "compositions": compositions,
        }
    return result


def main() -> None:
    payload = json.loads(MANIFEST.read_text("utf-8"))
    updated = deepcopy(payload)
    count = 0
    for row in updated.get("assets", []):
        if row.get("category") == "plants":
            row.pop("seedling_cue", None)
            row.pop("seedling_anchor", None)
        if row.get("category") != "backgrounds" or row.get("style_family") != "storybook_gouache":
            continue
        theme = str((row.get("slot") or {}).get("theme", ""))
        if theme not in THEMES:
            continue
        placement = row.setdefault("placement", {})
        placement["layout_profiles"] = build_profiles(theme)
        count += 1
    if count != 3:
        raise SystemExit(f"Expected three storybook backgrounds, updated {count}.")
    MANIFEST.write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")
    print(f"Updated {count} background layout profiles in {MANIFEST}")


if __name__ == "__main__":
    main()
