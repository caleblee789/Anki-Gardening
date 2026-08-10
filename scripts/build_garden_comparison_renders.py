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
THEMES = ("verdant_twilight",)
QUALITY_TIERS = ("performance", "balanced", "ultra")
STAGES = ("seed", "sprout", "young", "mature", "flowering", "rare")
SIZES = (
    ("minimum-dashboard", 572, 429), ("compact-wide", 620, 349), ("4:3", 640, 480),
    ("3:2", 720, 480), ("16:9", 800, 450), ("home", 1000, 420), ("wide", 1600, 900),
)
SPECIES = ("bonsai", "rose")
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
        and all(
            str((row.get("slot") or {}).get(key, "any")) in {value, "any"}
            for key, value in slot.items()
        )
    ]
    return sorted(matches, key=lambda row: (
        0 if category == "backgrounds" and bool(row.get("release_preferred", False)) else 1,
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
        0 if bool(row.get("release_preferred", False)) else 1,
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
    dense = len(layouts) >= 4
    dense_narrow = dense and width <= 720
    maximum_fit_error = .261 if dense_narrow else .161 if dense else .081
    minimum_fit_scale = .739 if dense_narrow else .839 if dense else .919
    if any(
        row.target_error > maximum_fit_error
        or not minimum_fit_scale <= row.fit_scale <= 1.001
        for row in layouts
    ):
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
        reserve_move_controls=move_mode and width >= 900 and surface != "home",
    )
    occupied = set(range(count))
    names = {slot: SPECIES[slot % len(SPECIES)].title() for slot in occupied}
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
    guides = []
    badge_rects: list[Rect] = []
    for depth_rank, row in enumerate(layouts):
        def percent_rect(rect: Any) -> dict[str, float]:
            return {
                "x": rect.x / width * 100, "y": rect.y / height * 100,
                "w": rect.width / width * 100, "h": rect.height / height * 100,
            }

        direction = row.grounding.shadow_direction
        guides.append({
            "slot": row.slot_index,
            "surface": row.surface_id,
            "band": row.depth_band,
            "kind": row.surface_kind,
            "plant_scale": row.depth_scale,
            "effective_scale": row.effective_scale,
            "z": row.z_depth,
            "visible": percent_rect(row.visible),
            "base": percent_rect(row.base_rect),
            "contact": percent_rect(row.contact_plane),
            "envelope": percent_rect(row.slot_envelope),
            "anchor": [row.ground_anchor[0] / width * 100, row.ground_anchor[1] / height * 100],
            "support": [
                [x / width * 100, y / height * 100]
                for x, y in row.grounding.support_line
            ],
            "light_to": [
                (row.ground_anchor[0] + direction[0] * row.support_rect.width) / width * 100,
                (row.ground_anchor[1] + direction[1] * row.support_rect.width * .35) / height * 100,
            ],
        })
        if row.slot_index < count:
            asset = assets[row.slot_index]
            integration = theme_integration_profile(theme, row.shadow_depth, row.ground_anchor[0] / width)
            z_base = 10 + depth_rank * 4
            for shadow_type, shadow_rect, opacity in (
                ("cast", row.grounding.cast_shadow, row.grounding.cast_opacity),
                ("contact", row.grounding.contact_shadow, row.grounding.contact_opacity),
            ):
                shadows.append({
                    "type": shadow_type, "row": row.shadow_depth,
                    "x": shadow_rect.x / width * 100, "y": shadow_rect.y / height * 100,
                    "w": shadow_rect.width / width * 100, "h": shadow_rect.height / height * 100,
                    "z": z_base, "opacity": opacity,
                })
            if row.slot_index == 0:
                marker_width = row.support_rect.width * 1.15
                marker_height = max(6.0, row.support_rect.width * .08)
                rings.append({
                    "x": (row.ground_anchor[0] - marker_width / 2) / width * 100,
                    "y": (row.depth - marker_height * .52) / height * 100,
                    "w": marker_width / width * 100,
                    "h": marker_height / height * 100,
                    "z": 92,
                })
            plants.append({
                "slot": row.slot_index,
                "species": SPECIES[row.slot_index % len(SPECIES)],
                "src": _asset_url(asset),
                "row": row.shadow_depth,
                "x": row.draw.x / width * 100, "y": row.draw.y / height * 100,
                "w": row.draw.width / width * 100, "h": row.draw.height / height * 100,
                "z": z_base + 1,
                "contrast": integration["contrast"], "saturation": integration["saturation"],
                "brightness": 1.0 + integration.get("exposure", 0.0),
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
    raw_occlusions = surface_variant.get("occlusion_layers", {})
    occlusions = {
        row: _file_url(path) for row, path in raw_occlusions.items()
    } if isinstance(raw_occlusions, dict) else {}
    legacy_occlusion = _file_url(surface_variant.get("occlusion_file")) if not occlusions else ""
    hotspots = []
    raw_surface_profile = placement.get("surface_profile", {}) if isinstance(placement, dict) else {}
    raw_landmarks = raw_surface_profile.get("landmarks", []) if isinstance(raw_surface_profile, dict) else []
    for landmark in raw_landmarks if isinstance(raw_landmarks, list) else []:
        variants = landmark.get("variants", {}) if isinstance(landmark, dict) else {}
        geometry = variants.get(_surface_name, {}) if isinstance(variants, dict) else {}
        bounds = geometry.get("bounds", []) if isinstance(geometry, dict) else []
        if isinstance(bounds, list) and len(bounds) == 4:
            hotspots.append({
                "label": str(landmark.get("action_id", "landmark")),
                "x": float(bounds[0]) * 100, "y": float(bounds[1]) * 100,
                "w": float(bounds[2]) * 100, "h": float(bounds[3]) * 100,
            })
    return {
        "key": "|".join(map(str, (theme, quality, stage, size_name, count, int(move_mode)))),
        "theme": theme, "quality": quality, "stage": stage, "size": size_name,
        "width": width, "height": height, "count": count, "move": move_mode,
        "background": background_url, "occlusions": occlusions, "occlusion": legacy_occlusion, "focal": focal,
        "plants": plants, "shadows": shadows, "rings": rings, "badges": badges,
        "guides": guides, "hotspots": hotspots,
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
h1{{margin:0 0 10px;font-size:20px}} .controls{{display:flex;flex-wrap:wrap;gap:8px}} label{{display:grid;gap:3px;color:#bcd0c2;font-size:11px}} select,button{{min-height:44px;border:1px solid #436458;border-radius:8px;background:#1b3029;color:#eef7ef;padding:5px 9px}} button{{align-self:end;cursor:pointer}} main{{padding:18px}} .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px}} figure{{margin:0;padding:10px;background:#17251f;border:1px solid #334a40;border-radius:12px}} .scene{{position:relative;width:100%;overflow:hidden;border-radius:9px;background-size:cover}} .plant,.occlusion{{position:absolute;object-fit:cover}} .plant{{object-fit:contain;filter:contrast(var(--contrast,1)) saturate(var(--saturation,1)) brightness(var(--brightness,1))}} .tint{{position:absolute;pointer-events:none;background:var(--tint);opacity:var(--tint-alpha);-webkit-mask-image:var(--mask);-webkit-mask-position:center;-webkit-mask-repeat:no-repeat;-webkit-mask-size:contain;mask-image:var(--mask);mask-position:center;mask-repeat:no-repeat;mask-size:contain}} .shadow{{position:absolute;border-radius:50%;background:radial-gradient(ellipse,rgba(54,34,22,.46),rgba(61,40,25,.21) 55%,transparent 80%);filter:blur(1px)}} .shadow.cast{{background:radial-gradient(ellipse,rgba(55,34,21,.22),rgba(61,40,25,.08) 58%,transparent 82%);filter:blur(1.4px)}} .ring{{position:absolute;border:2px solid rgba(243,197,109,.68);border-radius:50%}} .status{{position:absolute;left:2%;top:2%;width:min(53%,430px);min-height:54px;padding:7px 10px;border:1px solid #cfe2d052;border-radius:10px;background:#0a1815bd}} .status small{{display:block;margin-top:4px;line-height:1.25;color:#d2e3d5}} .status-outside{{padding:7px 2px 0;color:#bcd0c2;font-size:11px}} .badge{{position:absolute;display:grid;place-items:center;text-align:center;padding:2px 6px;border:1px solid #dbe6ce77;border-radius:9px;background:#1b2d27e8;font-size:10px;line-height:1.1}} .badge.active{{border-color:#edf5b8;background:#355a39}} .badge.current{{border-color:#9ccbd1;background:#26484e}} .badge.locked{{opacity:.5}} .destination{{position:absolute;left:4%;right:4%;bottom:3%;z-index:95;min-height:44px}} .debug-box,.debug-dot,.debug-label,.debug-svg{{position:absolute;pointer-events:none;z-index:120}} .debug-visible{{border:1px solid #59e8ff}} .debug-base{{border:2px solid #ffb85c}} .debug-contact{{border:2px solid #98ff8c}} .debug-envelope{{border:1px dashed #db8eff}} .debug-dot{{width:7px;height:7px;margin:-3px;border-radius:50%;background:#ff536b}} .debug-label{{max-width:34%;padding:2px 4px;background:#071411d9;color:#fff7cf;font-size:8px;line-height:1.15}} .debug-hotspot{{border:2px solid #ffd477;background:#ffd47718}} .debug-svg{{inset:0;width:100%;height:100%}} figcaption{{padding-top:8px;color:#c7d8cb}} .warnings{{color:#f2bd78}} .clean{{color:#8de0a5}}
</style>
<header><h1>Anki Garden · surface and placement comparison</h1><div class="controls" id="controls"></div></header><main><div class="grid" id="grid"></div></main>
<script>const DATA={data};
const defs={{theme:{json.dumps(THEMES)},quality:{json.dumps(QUALITY_TIERS)},stage:{json.dumps(STAGES)},size:{json.dumps(tuple(x[0] for x in SIZES))},count:[1,2,3,4,5,6],move:[false,true]}};
const state={{theme:'verdant_twilight',quality:'ultra',stage:'flowering',size:'4:3',count:6,move:false,debug:false}}; const controls=document.querySelector('#controls'),grid=document.querySelector('#grid');
for(const [name,values] of Object.entries(defs)){{const label=document.createElement('label');label.textContent=name;const select=document.createElement('select');select.dataset.key=name;for(const value of values){{const option=document.createElement('option');option.value=String(value);option.textContent=String(value);if(String(state[name])===String(value))option.selected=true;select.append(option)}}select.onchange=()=>{{state[name]=name==='count'?Number(select.value):name==='move'?select.value==='true':select.value;renderOne()}};label.append(select);controls.append(label)}}
for(const [label,mode] of [['Current view','one'],['All stages','stages'],['All themes','themes'],['All ratios','ratios'],['Max stress','stress'],['Normal / move','move']]){{const button=document.createElement('button');button.textContent=label;button.onclick=()=>renderMode(mode);controls.append(button)}}
const debugButton=document.createElement('button');debugButton.textContent='Debug guides';debugButton.onclick=()=>{{state.debug=!state.debug;debugButton.setAttribute('aria-pressed',String(state.debug));renderOne()}};debugButton.setAttribute('aria-pressed','false');controls.append(debugButton);
function match(extra={{}}){{const wanted={{...state,...extra}};return DATA.find(row=>Object.entries(wanted).every(([key,value])=>row[key]===value))}}
function card(row){{
  const figure=document.createElement('figure');
  const stats=document.createElement('div');stats.className='status-outside';stats.innerHTML='<strong>Your garden</strong> · 7 day streak · +5% Growth · next +10% at day 14';
  const scene=document.createElement('div');scene.className='scene';scene.style.aspectRatio=`${{row.width}}/${{row.height}}`;scene.style.backgroundImage=`url("${{row.background}}")`;scene.style.backgroundPosition=`${{row.focal[0]*100}}% ${{row.focal[1]*100}}%`;
  const shadowsFor=depth=>row.shadows.filter(s=>s.row===depth).map(s=>`<span class="shadow ${{s.type}}" style="left:${{s.x}}%;top:${{s.y}}%;width:${{s.w}}%;height:${{s.h}}%;z-index:${{s.z}};opacity:${{s.opacity}}"></span>`).join('');
  const rings=row.rings.map(r=>`<span class="ring" style="left:${{r.x}}%;top:${{r.y}}%;width:${{r.w}}%;height:${{r.h}}%;z-index:${{r.z}}"></span>`).join('');
  const plantsFor=depth=>row.plants.filter(p=>p.row===depth).map(p=>`<img class="plant" src="${{p.src}}" alt="${{p.species}} ${{row.stage}}" style="left:${{p.x}}%;top:${{p.y}}%;width:${{p.w}}%;height:${{p.h}}%;z-index:${{p.z}};--contrast:${{p.contrast}};--saturation:${{p.saturation}};--brightness:${{p.brightness}}"><span class="tint" style="left:${{p.x}}%;top:${{p.y}}%;width:${{p.w}}%;height:${{p.h}}%;z-index:${{p.z+1}};--tint:${{p.tint}};--tint-alpha:${{p.tint_alpha}};--mask:url(&quot;${{p.src}}&quot;)"></span>`).join('');
  const occlusionFor=(depth,z)=>row.occlusions&&row.occlusions[depth]?`<img class="occlusion" src="${{row.occlusions[depth]}}" alt="" style="inset:0;width:100%;height:100%;z-index:${{z}};object-position:${{row.focal[0]*100}}% ${{row.focal[1]*100}}%">`:'';
  const legacyOcclusion=row.occlusion?`<img class="occlusion" src="${{row.occlusion}}" alt="" style="inset:0;width:100%;height:100%;z-index:3;object-position:${{row.focal[0]*100}}% ${{row.focal[1]*100}}%">`:'';
  const badges=row.badges.map(b=>`<span class="badge ${{b.state}}" style="left:${{b.x}}%;top:${{b.y}}%;width:${{b.w}}%;height:${{b.h}}%;z-index:95">${{b.label}}</span>`).join('');
  const selector=row.native_selector?`<select class="destination" aria-label="Move destination"><option>Choose a garden space</option><option>Space 1 · Current</option><option>Space 2</option></select>`:'';
  const rect=(d,kind)=>`<span class="debug-box debug-${{kind}}" style="left:${{d[kind].x}}%;top:${{d[kind].y}}%;width:${{d[kind].w}}%;height:${{d[kind].h}}%"></span>`;
  const debug=state.debug?row.guides.map(d=>rect(d,'visible')+rect(d,'base')+rect(d,'contact')+rect(d,'envelope')+`<span class="debug-dot" style="left:${{d.anchor[0]}}%;top:${{d.anchor[1]}}%"></span><span class="debug-label" style="left:${{d.contact.x}}%;top:${{Math.max(0,d.contact.y-5)}}%">S${{d.slot}} ${{d.surface}} · ${{d.kind}} · ${{d.band}} · scale ${{d.plant_scale.toFixed(2)}} · z ${{d.z.toFixed(1)}}</span><svg class="debug-svg" viewBox="0 0 100 100" preserveAspectRatio="none"><line x1="${{d.support[0][0]}}" y1="${{d.support[0][1]}}" x2="${{d.support[d.support.length-1][0]}}" y2="${{d.support[d.support.length-1][1]}}" stroke="#fff18a" stroke-width=".35"/><line x1="${{d.anchor[0]}}" y1="${{d.anchor[1]}}" x2="${{d.light_to[0]}}" y2="${{d.light_to[1]}}" stroke="#ffd477" stroke-width=".35"/></svg>`).join('')+row.hotspots.map(h=>`<span class="debug-box debug-hotspot" style="left:${{h.x}}%;top:${{h.y}}%;width:${{h.w}}%;height:${{h.h}}%" title="${{h.label}}"></span>`).join(''):'';
  scene.innerHTML=legacyOcclusion+shadowsFor('rear')+plantsFor('rear')+occlusionFor('rear',21)+shadowsFor('front')+plantsFor('front')+occlusionFor('front',45)+rings+badges+selector+debug;
  const caption=document.createElement('figcaption');caption.innerHTML=`${{row.theme}} · ${{row.stage}} · ${{row.size}} · ${{row.count}} plant${{row.count===1?'':'s'}} · ${{row.move?'move':'normal'}}<br><span class="${{row.warnings.length?'warnings':'clean'}}">${{row.warnings.length?'Warnings: '+row.warnings.join(', '):'No automated geometry warnings'}}</span>`;
  figure.append(stats,scene,caption);return figure;
}}
function show(rows){{grid.replaceChildren(...rows.filter(Boolean).map(card))}} function renderOne(){{show([match()])}} function renderMode(mode){{if(mode==='one')return renderOne();if(mode==='stages')return show(defs.stage.map(stage=>match({{stage}})));if(mode==='themes')return show(defs.theme.map(theme=>match({{theme}})));if(mode==='ratios')return show(defs.size.map(size=>match({{size}})));if(mode==='stress')return show(['mature','flowering','rare'].flatMap(stage=>defs.theme.map(theme=>match({{stage,theme,count:6,move:true}}))));if(mode==='move')return show([match({{move:false}}),match({{move:true}})])}} renderOne();
</script>""", encoding="utf-8")
    return output


if __name__ == "__main__":
    print(build())
