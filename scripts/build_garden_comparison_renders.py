from __future__ import annotations

import html
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["ANKI_GARDEN_SKIP_STARTUP"] = "1"

from ankigarden.ui.plant_display import (
    Rect,
    bed_badge_rect,
    move_badge_label,
    plant_layout,
    requires_native_destination_selector,
    scene_surface_variant,
    theme_integration_profile,
)


ADDON = ROOT / "ankigarden"
MANIFEST = ADDON / "assets" / "manifest.json"
OUTPUT = ROOT / "build" / "garden-comparison-renders"
THEMES = ("verdant_dusk", "verdant_dawn", "moonlit_study")
QUALITY_TIERS = ("performance", "balanced", "ultra")
STAGES = ("seed", "sprout", "young", "mature", "flowering", "rare")
SIZES = (
    ("narrow-320", 320, 240), ("narrow-480", 480, 320), ("4:3", 640, 480),
    ("3:2", 720, 480), ("16:9", 800, 450), ("home", 1000, 420), ("wide", 1600, 900),
)
SPECIES = ("bonsai", "rose", "cactus", "orchid", "moonflower", "sunbloom", "fern", "ivy")
QUALITY_ORDER = {"performance": 0, "balanced": 1, "ultra": 2}


def _asset_url(row: dict[str, Any]) -> str:
    return (ADDON / str(row["file"])).resolve().as_uri()


def _file_url(relative_path: Any) -> str:
    path = ADDON / str(relative_path or "")
    return path.resolve().as_uri() if path.is_file() else ""


def _pick(rows: list[dict[str, Any]], category: str, **slot: str) -> dict[str, Any]:
    matches = [
        row for row in rows
        if row.get("category") == category
        and all(str((row.get("slot") or {}).get(key)) == value for key, value in slot.items())
    ]
    return sorted(matches, key=lambda row: (
        0 if row.get("style_family") == "storybook_gouache" else 1,
        -float(row.get("quality_score", 0)), str(row.get("file", "")),
    ))[0]


def _pick_plant(rows: list[dict[str, Any]], species: str, stage: str, quality: str) -> dict[str, Any]:
    matches = [
        row for row in rows
        if row.get("category") == "plants"
        and (row.get("slot") or {}).get("species") == species
        and (row.get("slot") or {}).get("stage") == stage
    ]
    target = QUALITY_ORDER[quality]
    return sorted(matches, key=lambda row: (
        0 if row.get("style_family") == "storybook_gouache" else 1,
        0 if "continuity_v4" in row.get("variants", []) else 1 if "continuity_v3" in row.get("variants", []) else 2,
        abs(QUALITY_ORDER.get(str(row.get("quality_tier", "balanced")), 1) - target),
        -float(row.get("quality_score", 0)), str(row.get("file", "")),
    ))[0]


def _warning_rows(layouts: list[Any], width: int, height: int, move_mode: bool) -> list[str]:
    warnings: list[str] = []
    visible = [row.visible for row in layouts]
    if any(row.x < 0 or row.y < 0 or row.right > width or row.bottom > height for row in visible):
        warnings.append("clipping")
    if any(left.base_rect.intersects(right.base_rect) for index, left in enumerate(layouts) for right in layouts[index + 1:]):
        warnings.append("base overlap")
    if any(
        left.foliage_rect.intersection_area(right.foliage_rect)
        / max(1.0, min(left.foliage_rect.area, right.foliage_rect.area))
        > (0.78 if abs(left.z_depth - right.z_depth) >= height * 0.04 else 0.60)
        for index, left in enumerate(layouts) for right in layouts[index + 1:]
    ):
        warnings.append("foliage overlap above policy")
    if any(row.hit.width < 44 or row.hit.height < 44 for row in layouts):
        warnings.append("small target")
    if any(abs(row.base_rect.bottom - row.depth) > 0.5 for row in layouts):
        warnings.append("ground contact")
    if any(
        row.surface_id and (
            row.support_rect.x < row.contact_plane.x - .5
            or row.support_rect.right > row.contact_plane.right + .5
            or not row.contact_plane.y <= row.depth <= row.contact_plane.bottom
        )
        for row in layouts
    ):
        warnings.append("support outside painted plane")
    if any(row.target_error > .081 or not .919 <= row.fit_scale <= 1.001 for row in layouts):
        warnings.append("physical target drift")
    if move_mode and width >= 480:
        for row in layouts:
            if width < 380 and row.slot_index not in {0, 1}:
                continue
            obstacles = [
                other.foliage_rect.expanded(3, 2) for other in layouts
                if other.slot_index != row.slot_index
            ]
            badge = row.control_rect
            if any(
                badge.intersection_area(obstacle) / max(1.0, obstacle.area) > 0.10
                or badge.intersection_area(obstacle) / max(1.0, badge.area) > 0.25
                for obstacle in obstacles
            ):
                warnings.append("control overlap")
                break
    for row in layouts:
        warnings.extend(row.validation_warnings)
    return sorted(set(warnings))


def _scenario(
    rows: list[dict[str, Any]], theme: str, quality: str, stage: str,
    size_name: str, width: int, height: int, count: int, move_mode: bool,
) -> dict[str, Any]:
    background = _pick(rows, "backgrounds", theme=theme)
    placement = background.get("placement", {})
    items: list[dict[str, Any]] = []
    assets: dict[int, dict[str, Any]] = {}
    for slot in range(6):
        species = SPECIES[slot % len(SPECIES)]
        plant = _pick_plant(rows, species, stage, quality)
        assets[slot] = plant
        items.append({
            "slot_index": slot,
            "species": species,
            "placement": plant.get("placement", {}),
            "canvas_aspect": float(plant["width"]) / float(plant["height"]),
            "occupied": slot < count,
        })
    surface = "home" if size_name == "home" else "dashboard"
    layouts = plant_layout(
        width, height, items, placement, surface_context=surface, composition_count=count,
        protected_status=False,
        reserve_move_controls=width >= 900 and surface != "home",
    )
    occupied = set(range(count))
    names = {slot: SPECIES[slot].title() for slot in occupied}
    native_selector = bool(
        move_mode
        and (
            surface == "home"
            or requires_native_destination_selector(layouts, width, height, occupied)
        )
    )
    plants = []
    shadows = []
    rings = []
    badges = []
    badge_rects: list[Rect] = []
    for depth_rank, row in enumerate(layouts):
        if row.slot_index < count:
            asset = assets[row.slot_index]
            integration = theme_integration_profile(theme, row.shadow_depth)
            z_base = 10 + depth_rank * 4
            shadows.append({
                "x": row.footprint.x / width * 100, "y": row.footprint.y / height * 100,
                "w": row.footprint.width / width * 100, "h": row.footprint.height / height * 100,
                "z": z_base, "opacity": row.shadow_opacity,
            })
            if row.slot_index == 0:
                rings.append({
                    "x": (row.support_rect.x - 4) / width * 100,
                    "y": (row.support_rect.bottom - 6) / height * 100,
                    "w": (row.support_rect.width + 8) / width * 100,
                    "h": max(5.0, row.footprint.height) / height * 100,
                    "z": z_base,
                })
            plants.append({
                "slot": row.slot_index, "species": SPECIES[row.slot_index], "src": _asset_url(asset),
                "x": row.draw.x / width * 100, "y": row.draw.y / height * 100,
                "w": row.draw.width / width * 100, "h": row.draw.height / height * 100,
                "z": z_base + 1,
                "contrast": integration["contrast"], "saturation": integration["saturation"],
                "tint": integration["tint"], "tint_alpha": integration["tint_alpha"],
            })
        if move_mode and not native_selector:
            label, state = move_badge_label(
                row.slot_index, origin_slot=0, destination_slot=1 if count > 1 else 0,
                unlocked_slots=max(2, count), occupied_slots=occupied, occupant_names=names,
            )
            visual_label = str(row.slot_index + 1)
            if width < 380 and state not in {"active", "current"}:
                continue
            obstacles = [
                item.visible.expanded(3, 2) for item in layouts
                if item.slot_index < count
            ] + badge_rects
            badge = bed_badge_rect(row, visual_label, width, height, obstacles)
            badge_rects.append(badge)
            badges.append({
                "label": visual_label, "state": state, "x": badge.x / width * 100,
                "y": badge.y / height * 100, "w": badge.width / width * 100,
                "h": badge.height / height * 100,
            })
    _surface_name, surface_variant = scene_surface_variant(placement, width, height, surface)
    profiles = placement.get("layout_profiles", {})
    profile_key = "home" if surface == "home" else "4:3" if width / height <= 1.42 else "3:2" if width / height <= 1.66 else "16:9"
    profile = profiles.get(profile_key, {}) if isinstance(profiles, dict) else {}
    focal = surface_variant.get("focal_point", profile.get("focal_point", placement.get("focal_point", [0.5, 0.5])))
    background_url = _file_url(surface_variant.get("file")) or _asset_url(background)
    occlusion_url = _file_url(surface_variant.get("occlusion_file"))
    return {
        "key": "|".join(map(str, (theme, quality, stage, size_name, count, int(move_mode)))),
        "theme": theme, "quality": quality, "stage": stage, "size": size_name,
        "width": width, "height": height, "count": count, "move": move_mode,
        "background": background_url, "occlusion": occlusion_url, "focal": focal,
        "plants": plants, "shadows": shadows, "rings": rings, "badges": badges,
        "native_selector": native_selector,
        "warnings": _warning_rows(
            [row for row in layouts if row.slot_index < count], width, height,
            move_mode and not native_selector,
        ),
    }


def build() -> Path:
    rows = json.loads(MANIFEST.read_text("utf-8"))["assets"]
    scenarios = [
        _scenario(rows, theme, quality, stage, size_name, width, height, count, move_mode)
        for theme in THEMES for quality in QUALITY_TIERS for stage in STAGES
        for size_name, width, height in SIZES for count in range(1, 7) for move_mode in (False, True)
    ]
    OUTPUT.mkdir(parents=True, exist_ok=True)
    output = OUTPUT / "index.html"
    (OUTPUT / "scenarios.json").write_text(json.dumps(scenarios, indent=2) + "\n", encoding="utf-8")
    warning_rows = [
        {key: row[key] for key in ("key", "theme", "quality", "stage", "size", "count", "move", "warnings")}
        for row in scenarios if row["warnings"]
    ]
    (OUTPUT / "warning-report.json").write_text(
        json.dumps({"scenario_count": len(scenarios), "warning_count": len(warning_rows), "scenarios": warning_rows}, indent=2) + "\n",
        encoding="utf-8",
    )
    data = json.dumps(scenarios, separators=(",", ":"))
    output.write_text(f"""<!doctype html><meta charset="utf-8"><title>Anki Garden surface comparison</title>
<style>
*{{box-sizing:border-box}} body{{margin:0;background:#0f1815;color:#e8f0e8;font:14px system-ui}} header{{position:sticky;top:0;z-index:999;padding:14px 18px;background:#13211ddb;border-bottom:1px solid #385046;backdrop-filter:blur(10px)}}
h1{{margin:0 0 10px;font-size:20px}} .controls{{display:flex;flex-wrap:wrap;gap:8px}} label{{display:grid;gap:3px;color:#bcd0c2;font-size:11px}} select,button{{min-height:44px;border:1px solid #436458;border-radius:8px;background:#1b3029;color:#eef7ef;padding:5px 9px}} button{{align-self:end;cursor:pointer}} main{{padding:18px}} .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px}} figure{{margin:0;padding:10px;background:#17251f;border:1px solid #334a40;border-radius:12px}} .scene{{position:relative;width:100%;overflow:hidden;border-radius:9px;background-size:cover}} .plant,.occlusion{{position:absolute;object-fit:cover}} .plant{{object-fit:contain;filter:contrast(var(--contrast,1)) saturate(var(--saturation,1))}} .tint{{position:absolute;pointer-events:none;background:var(--tint);opacity:var(--tint-alpha);-webkit-mask-image:var(--mask);-webkit-mask-position:center;-webkit-mask-repeat:no-repeat;-webkit-mask-size:contain;mask-image:var(--mask);mask-position:center;mask-repeat:no-repeat;mask-size:contain}} .shadow{{position:absolute;border-radius:47% 53% 55% 45%;transform:translate(-7%,2%) skewX(-11deg);background:radial-gradient(ellipse at 62% 42%,rgba(54,34,22,.46),rgba(61,40,25,.21) 55%,transparent 78%);filter:blur(1.4px)}} .ring{{position:absolute;border-bottom:2px solid rgba(232,188,105,.62);border-radius:45% 55% 51% 49%;transform:skewX(-10deg)}} .status{{position:absolute;left:2%;top:2%;width:min(53%,430px);min-height:54px;padding:7px 10px;border:1px solid #cfe2d052;border-radius:10px;background:#0a1815bd}} .status small{{display:block;margin-top:4px;line-height:1.25;color:#d2e3d5}} .status-outside{{padding:7px 2px 0;color:#bcd0c2;font-size:11px}} .badge{{position:absolute;display:grid;place-items:center;text-align:center;padding:2px 6px;border:1px solid #dbe6ce77;border-radius:9px;background:#1b2d27e8;font-size:10px;line-height:1.1}} .badge.active{{border-color:#edf5b8;background:#355a39}} .badge.current{{border-color:#9ccbd1;background:#26484e}} .badge.locked{{opacity:.5}} .destination{{position:absolute;left:4%;right:4%;bottom:3%;z-index:95;min-height:44px}} figcaption{{padding-top:8px;color:#c7d8cb}} .warnings{{color:#f2bd78}} .clean{{color:#8de0a5}}
</style>
<header><h1>Anki Garden · surface and placement comparison</h1><div class="controls" id="controls"></div></header><main><div class="grid" id="grid"></div></main>
<script>const DATA={data};
const defs={{theme:{json.dumps(THEMES)},quality:{json.dumps(QUALITY_TIERS)},stage:{json.dumps(STAGES)},size:{json.dumps(tuple(x[0] for x in SIZES))},count:[1,2,3,4,5,6],move:[false,true]}};
const state={{theme:'verdant_dusk',quality:'ultra',stage:'flowering',size:'4:3',count:6,move:false}}; const controls=document.querySelector('#controls'),grid=document.querySelector('#grid');
for(const [name,values] of Object.entries(defs)){{const label=document.createElement('label');label.textContent=name;const select=document.createElement('select');select.dataset.key=name;for(const value of values){{const option=document.createElement('option');option.value=String(value);option.textContent=String(value);if(String(state[name])===String(value))option.selected=true;select.append(option)}}select.onchange=()=>{{state[name]=name==='count'?Number(select.value):name==='move'?select.value==='true':select.value;renderOne()}};label.append(select);controls.append(label)}}
for(const [label,mode] of [['Current view','one'],['All stages','stages'],['All themes','themes'],['All ratios','ratios'],['Max stress','stress'],['Normal / move','move']]){{const button=document.createElement('button');button.textContent=label;button.onclick=()=>renderMode(mode);controls.append(button)}}
function match(extra={{}}){{const wanted={{...state,...extra}};return DATA.find(row=>Object.entries(wanted).every(([key,value])=>row[key]===value))}}
function card(row){{
  const figure=document.createElement('figure');
  const stats=document.createElement('div');stats.className='status-outside';stats.innerHTML='<strong>Your garden</strong> · 7 day streak · 64% daily goal · 92% vitality';
  const scene=document.createElement('div');scene.className='scene';scene.style.aspectRatio=`${{row.width}}/${{row.height}}`;scene.style.backgroundImage=`url("${{row.background}}")`;scene.style.backgroundPosition=`${{row.focal[0]*100}}% ${{row.focal[1]*100}}%`;
  const shadows=row.shadows.map(s=>`<span class="shadow" style="left:${{s.x}}%;top:${{s.y}}%;width:${{s.w}}%;height:${{s.h}}%;z-index:${{s.z}};opacity:${{s.opacity}}"></span>`).join('');
  const rings=row.rings.map(r=>`<span class="ring" style="left:${{r.x}}%;top:${{r.y}}%;width:${{r.w}}%;height:${{r.h}}%;z-index:${{r.z}}"></span>`).join('');
  const plants=row.plants.map(p=>`<img class="plant" src="${{p.src}}" alt="${{p.species}} ${{row.stage}}" style="left:${{p.x}}%;top:${{p.y}}%;width:${{p.w}}%;height:${{p.h}}%;z-index:${{p.z}};--contrast:${{p.contrast}};--saturation:${{p.saturation}}"><span class="tint" style="left:${{p.x}}%;top:${{p.y}}%;width:${{p.w}}%;height:${{p.h}}%;z-index:${{p.z+1}};--tint:${{p.tint}};--tint-alpha:${{p.tint_alpha}};--mask:url(&quot;${{p.src}}&quot;)"></span>`).join('');
  const occlusion=row.occlusion?`<img class="occlusion" src="${{row.occlusion}}" alt="" style="inset:0;width:100%;height:100%;z-index:90;object-position:${{row.focal[0]*100}}% ${{row.focal[1]*100}}%">`:'';
  const badges=row.badges.map(b=>`<span class="badge ${{b.state}}" style="left:${{b.x}}%;top:${{b.y}}%;width:${{b.w}}%;height:${{b.h}}%;z-index:95">${{b.label}}</span>`).join('');
  const selector=row.native_selector?`<select class="destination" aria-label="Move destination"><option>Choose a garden space</option><option>Space 1 · Current</option><option>Space 2</option></select>`:'';
  scene.innerHTML=rings+shadows+plants+occlusion+badges+selector;
  const caption=document.createElement('figcaption');caption.innerHTML=`${{row.theme}} · ${{row.stage}} · ${{row.size}} · ${{row.count}} plant${{row.count===1?'':'s'}} · ${{row.move?'move':'normal'}}<br><span class="${{row.warnings.length?'warnings':'clean'}}">${{row.warnings.length?'Warnings: '+row.warnings.join(', '):'No automated geometry warnings'}}</span>`;
  figure.append(stats,scene,caption);return figure;
}}
function show(rows){{grid.replaceChildren(...rows.filter(Boolean).map(card))}} function renderOne(){{show([match()])}} function renderMode(mode){{if(mode==='one')return renderOne();if(mode==='stages')return show(defs.stage.map(stage=>match({{stage}})));if(mode==='themes')return show(defs.theme.map(theme=>match({{theme}})));if(mode==='ratios')return show(defs.size.map(size=>match({{size}})));if(mode==='stress')return show(['mature','flowering','rare'].flatMap(stage=>defs.theme.map(theme=>match({{stage,theme,count:6,move:true}}))));if(mode==='move')return show([match({{move:false}}),match({{move:true}})])}} renderOne();
</script>""", encoding="utf-8")
    return output


if __name__ == "__main__":
    print(build())
