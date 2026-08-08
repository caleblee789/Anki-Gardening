from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any

from ..display_telemetry import DISPLAY_TELEMETRY
from .formatters import format_integer, format_percent, format_status_label
from .plant_display import compact_plant_layout, scene_surface_variant, theme_integration_profile


@dataclass(frozen=True)
class HomeWidgetData:
    reviews_today: int
    health_ratio: float
    growth_earned: int
    growth_cap: int
    streak_days: int
    weather: str
    scene_items: tuple[dict[str, Any], ...] = ()
    stage_transition_message: str = ""
    background_url: str = ""
    garden_overlay_url: str = ""
    focus_plant_name: str = ""
    focus_stage: str = ""
    focus_points_remaining: int = 0
    next_milestone: int | None = None
    total_reviews: int = 0
    milestone_ready: bool = False
    status_notice: str = ""
    unlocked_slots: int = 0


@dataclass(frozen=True)
class HomeWidgetSnapshot:
    request_id: int
    phase: str
    data: HomeWidgetData | None = None
    error_message: str | None = None


class HomeWidgetStateController:
    """Tracks request lifecycles and protects the UI against stale responses."""

    def __init__(self) -> None:
        self._next_request_id = 0
        self.snapshot = HomeWidgetSnapshot(request_id=0, phase="empty")

    def begin_request(self) -> int:
        self._next_request_id += 1
        req_id = self._next_request_id
        self.snapshot = HomeWidgetSnapshot(request_id=req_id, phase="loading")
        return req_id

    def resolve_success(self, request_id: int, data: HomeWidgetData) -> bool:
        if request_id != self.snapshot.request_id:
            return False
        self.snapshot = HomeWidgetSnapshot(request_id=request_id, phase="success", data=data)
        return True

    def resolve_partial(self, request_id: int, data: HomeWidgetData, error_message: str) -> bool:
        if request_id != self.snapshot.request_id:
            return False
        self.snapshot = HomeWidgetSnapshot(
            request_id=request_id,
            phase="partial",
            data=data,
            error_message=error_message,
        )
        return True

    def resolve_error(self, request_id: int, error_message: str) -> bool:
        if request_id != self.snapshot.request_id:
            return False
        self.snapshot = HomeWidgetSnapshot(request_id=request_id, phase="error", error_message=error_message)
        return True


DEFAULT_ERROR_MESSAGE = "Unable to load garden stats right now. Retry to refresh."


HOME_WIDGET_STYLE = """
<style>
#ag-home-root {
  max-width: 1480px;
  margin: 18px auto;
  padding: 0;
  overflow: hidden;
  border: 1px solid rgba(118, 151, 126, 0.52);
  border-radius: 16px;
  background: #0d201d;
  color: #edf5ea;
  box-shadow: 0 18px 42px rgba(2, 11, 10, 0.28);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
.ag-home__state {
  padding: 20px;
}
.ag-home__state-title {
  margin-bottom: 4px;
  font-size: 17px;
  font-weight: 800;
}
.ag-home__state-message, .ag-home__partial-message {
  line-height: 1.45;
}
.ag-home__partial-message {
  margin: 0;
  padding: 10px 16px;
  border-bottom: 1px solid rgba(223, 180, 98, 0.28);
  background: rgba(105, 70, 32, 0.34);
  color: #f1d59b;
}
.ag-home__body { display:grid; grid-template-columns:minmax(420px,62%) minmax(310px,38%); align-items:stretch; }
.ag-home__art { position:absolute; inset:0; overflow:hidden; }
.ag-home__plant { position:absolute; object-fit:contain; animation:none !important; transition:none !important; filter:contrast(var(--ag-contrast,1)) saturate(var(--ag-saturation,1)); }
.ag-home__plant-tint { position:absolute; pointer-events:none; background:var(--ag-tint,transparent); opacity:var(--ag-tint-alpha,0); -webkit-mask-image:var(--ag-mask); -webkit-mask-position:center; -webkit-mask-repeat:no-repeat; -webkit-mask-size:contain; mask-image:var(--ag-mask); mask-position:center; mask-repeat:no-repeat; mask-size:contain; }
.ag-home__selected-ring { position:absolute; border-bottom:2px solid rgba(232,188,105,.52); border-radius:45% 55% 51% 49%; transform:skewX(-10deg); pointer-events:none; }
.ag-home__occlusion { position:absolute; inset:0; z-index:90; width:100%; height:100%; object-fit:cover; object-position:var(--ag-focal-x,50%) var(--ag-focal-y,50%); pointer-events:none; }
.ag-home__contact { position:absolute; border-radius:47% 53% 55% 45%; transform:translate(-7%,2%) skewX(-11deg); background:radial-gradient(ellipse at 62% 42%,rgba(54,34,22,.40),rgba(61,40,25,.19) 55%,transparent 78%); filter:blur(1.4px); }
.ag-home__soil { position:absolute; border-radius:48% 52% 46% 54%; transform:translate(-50%,-50%); background:rgba(123,78,43,.68); border:1px solid rgba(174,116,62,.58); }
.ag-home__soil--locked { display:none; }
.ag-home__plant-fallback { position:absolute; display:flex; align-items:flex-end; justify-content:center; line-height:1; }
.ag-home__metrics {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
  min-height: 0;
  margin-top: 12px;
  flex: 1;
}
.ag-home__scene {
  position: relative;
  min-height: 300px;
  aspect-ratio: 12 / 5;
  overflow: hidden;
  background-position: var(--ag-focal-x,50%) var(--ag-focal-y,50%);
  background-size: cover;
}
.ag-home__scene::after { content:""; position:absolute; inset:0; pointer-events:none; box-shadow:inset -24px 0 38px rgba(5,16,14,.24), inset 0 -18px 32px rgba(5,14,12,.16); }
.ag-home__details { min-width:0; padding:18px 20px; display:flex; flex-direction:column; background:linear-gradient(145deg,#102a25,#0b1f1c 72%); border-left:1px solid rgba(137,165,137,.22); }
.ag-home__identity-row { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; }
.ag-home__identity { min-width:0; }
.ag-home__eyebrow { margin-bottom:4px; color:#d8b875; font-size:11px; font-weight:800; letter-spacing:.09em; text-transform:uppercase; }
.ag-home__focus-name {
  display:-webkit-box;
  overflow:hidden;
  -webkit-box-orient:vertical;
  -webkit-line-clamp:2;
  font-size:22px;
  font-weight:800;
  line-height:1.15;
}
.ag-home__focus-stage { margin-top:3px; color:#b9cec0; font-size:12px; }
.ag-home__metric {
  display:flex;
  flex-direction:column;
  justify-content:center;
  min-height:52px;
  padding:10px 12px;
  border:1px solid rgba(117,151,125,.18);
  border-radius:10px;
  background:rgba(5,18,16,.28);
}
.ag-home__metric:hover, .ag-home__metric:focus-visible { border-color:rgba(216,184,117,.52); outline:none; }
.ag-home__metric-label { color:#8eab9a; font-size:10px; font-weight:700; letter-spacing:.06em; text-transform:uppercase; }
.ag-home__metric-value { margin-top:2px; color:#edf5ea; font-size:16px; font-weight:750; }
.ag-home__tooltip { position:fixed; z-index:9999; max-width:280px; padding:7px 9px; border-radius:7px; background:#10201d; color:#eef9f0; box-shadow:0 4px 16px rgba(0,0,0,.3); font-size:12px; line-height:1.35; pointer-events:none; }
.ag-home__bar-track {
  height: 6px;
  margin: 6px 0 0;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.12);
}
#ag-home-root [data-testid="home-growth-bar"] {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #4bbf82, #d9d77d);
}
.ag-home__stage-up {
  margin: 8px 0;
  padding: 8px 10px;
  border: 1px solid rgba(244, 213, 138, 0.44);
  border-radius: 8px;
  background: rgba(117, 82, 35, 0.34);
  color: #f4d58a;
  font-weight: 700;
}
#ag-home-root button {
  display:inline-flex;
  align-items:center;
  justify-content:center;
  min-width:132px;
  min-height:44px;
  box-sizing:border-box;
  line-height:1.2;
  flex:none;
  margin: 0;
  padding: 8px 14px;
  border: 1px solid #618a6e;
  border-radius: 10px;
  background: #24583f;
  color: #eef9f0;
  font-weight: 600;
  cursor: pointer;
}
#ag-home-root button:hover { background: #2f6b4d; }
#ag-home-root button:active { background:#183828; transform:translateY(1px); }
#ag-home-root button:disabled { cursor:wait; opacity:.72; }
#ag-home-root button:focus-visible {
  outline: 3px solid #e5f2a6;
  outline-offset: 2px;
}
.nightMode #ag-home-root { background:#0d201d; color:#edf5ea; border-color:rgba(118,157,132,.48); }
@media (max-width: 900px) {
  .ag-home__body { grid-template-columns:1fr; }
  .ag-home__scene { min-height:0; }
  .ag-home__details { border-left:0; border-top:1px solid rgba(137,165,137,.22); }
  .ag-home__metrics { grid-template-columns:repeat(3,minmax(0,1fr)); }
}
@media (max-width: 600px) {
  #ag-home-root { margin:10px 8px; border-radius:12px; }
  .ag-home__details { padding:14px; }
  .ag-home__identity-row { align-items:stretch; flex-direction:column; }
  #ag-home-root button { width:100%; }
}
@media (max-width: 480px) {
  .ag-home__metrics { grid-template-columns:1fr; }
}
</style>
"""


def _plant_fallback(_stage: Any) -> str:
    """Artwork failures remain named and quiet; system emoji are never substituted."""
    return ""


def render_home_widget(snapshot: HomeWidgetSnapshot) -> str:
    DISPLAY_TELEMETRY.track_render("home_widget")
    phase = snapshot.phase
    if phase == "loading":
        return (
            HOME_WIDGET_STYLE
            +
            '<div id="ag-home-root" data-state="loading" role="region" aria-label="Anki Garden">'
            '<div class="ag-home__state" data-testid="home-loading" role="status" aria-live="polite">'
            '<div class="ag-home__state-title">Anki Garden</div>'
            '<div class="ag-home__state-message">Loading garden…</div></div>'
            "</div>"
        )
    if phase == "empty":
        return (
            HOME_WIDGET_STYLE
            +
            '<div id="ag-home-root" data-state="empty" role="region" aria-label="Anki Garden">'
            '<div class="ag-home__state" data-testid="home-empty" role="status">'
            '<div class="ag-home__state-title">Your garden is ready</div>'
            '<div class="ag-home__state-message">Review your first card to start growing your garden.</div></div>'
            "</div>"
        )
    if phase == "error":
        message = escape(snapshot.error_message or DEFAULT_ERROR_MESSAGE)
        return (
            HOME_WIDGET_STYLE
            +
            '<div id="ag-home-root" data-state="error" role="region" aria-label="Anki Garden">'
            '<div class="ag-home__state">'
            '<div class="ag-home__state-title">Garden unavailable</div>'
            f'<div class="ag-home__state-message" data-testid="home-error" role="alert">{message}</div>'
            '<button data-testid="home-retry" type="button" aria-label="Retry loading Anki Garden" '
            'onclick="pycmd(\'anki-garden:refresh\')">Retry</button></div>'
            "</div>"
        )

    data = snapshot.data
    if data is None:
        DISPLAY_TELEMETRY.record_missing_or_invalid_field(
            route="home_widget",
            field="payload",
            reason="snapshot_data_missing",
            required=True,
        )
        return (
            HOME_WIDGET_STYLE
            +
            '<div id="ag-home-root" data-state="error" role="region" aria-label="Anki Garden">'
            '<div class="ag-home__state">'
            '<div class="ag-home__state-title">Garden unavailable</div>'
            '<div class="ag-home__state-message" data-testid="home-error" role="alert">Invalid home widget payload.</div></div>'
            "</div>"
        )
    if not data.weather:
        DISPLAY_TELEMETRY.track_fallback(route="home_widget", field="weather")

    growth_cap = max(1, data.growth_cap)
    growth_pct = int(min(100, (data.growth_earned / growth_cap) * 100))
    partial_banner = ""
    if phase == "partial":
        partial_error = escape(snapshot.error_message or "Some details are temporarily unavailable.")
        partial_banner = (
            '<div class="ag-home__partial-message" data-testid="home-partial-error" '
            f'role="status" aria-live="polite">{partial_error}</div>'
        )

    stage_up_html = ""
    if data.stage_transition_message:
        stage_up_html = (
            '<div class="ag-home__stage-up" data-testid="home-stage-up" role="status" aria-live="polite">'
            f'{escape(data.stage_transition_message)}</div>'
        )

    background_placement = data.scene_items[0].get("background_placement", {}) if data.scene_items else {}
    _surface_name, surface_variant = scene_surface_variant(
        background_placement if isinstance(background_placement, dict) else None,
        1000,
        420,
        "home",
    )
    profiles = background_placement.get("layout_profiles", {}) if isinstance(background_placement, dict) else {}
    home_profile = profiles.get("home", {}) if isinstance(profiles, dict) else {}
    focal = home_profile.get("focal_point", [0.5, 0.82]) if isinstance(home_profile, dict) else [0.5, 0.82]
    focal_x = max(0.0, min(1.0, float(focal[0]))) if isinstance(focal, (list, tuple)) and len(focal) == 2 else 0.5
    focal_y = max(0.0, min(1.0, float(focal[1]))) if isinstance(focal, (list, tuple)) and len(focal) == 2 else 0.82
    background_style = f' style="--ag-focal-x:{focal_x * 100:.2f}%;--ag-focal-y:{focal_y * 100:.2f}%'
    background_url = str(surface_variant.get("url") or data.background_url)
    if background_url:
        background_style += f';background-image:linear-gradient(180deg,rgba(5,14,12,.04),rgba(5,14,12,.38)),url(&quot;{escape(background_url, quote=True)}&quot;)'
    background_style += '"'
    layouts = compact_plant_layout(
        1000,
        420,
        data.scene_items,
        background_placement if isinstance(background_placement, dict) else None,
    )
    by_slot = {int(item.get("slot_index", index)): item for index, item in enumerate(data.scene_items)}
    anchors = home_profile.get("bed_anchors", background_placement.get("bed_anchors", [])) if isinstance(home_profile, dict) else background_placement.get("bed_anchors", [])
    soil_markup: list[str] = []
    if isinstance(anchors, list):
        for slot, anchor in enumerate(anchors[:6]):
            if not isinstance(anchor, dict):
                continue
            footprint = anchor.get("footprint", [0.16, 0.055])
            fw = float(footprint[0]) if isinstance(footprint, (list, tuple)) and len(footprint) == 2 else 0.16
            fh = float(footprint[1]) if isinstance(footprint, (list, tuple)) and len(footprint) == 2 else 0.055
            state = "locked" if slot >= data.unlocked_slots else "occupied" if slot in by_slot else "empty"
            if state == "occupied":
                continue
            soil_markup.append(
                f'<span class="ag-home__soil ag-home__soil--{state}" data-slot-index="{slot}" aria-hidden="true" '
                f'style="left:{float(anchor.get("x", .5))*100:.3f}%;top:{float(anchor.get("y", .8))*100:.3f}%;width:{fw*100:.3f}%;height:{fh*100:.3f}%"></span>'
            )
    plant_markup = []
    theme = str(data.scene_items[0].get("background_theme", "verdant_dusk")) if data.scene_items else "verdant_dusk"
    for order, layout in enumerate(layouts):
        item = by_slot.get(layout.slot_index, {})
        src = escape(str(item.get("url", "")), quote=True)
        base_type = str(item.get("placement", {}).get("base_type", "legacy")) if isinstance(item.get("placement"), dict) else "legacy"
        depth_index = 10 + order * 4
        depth_band = "rear" if layout.depth < 420 * .68 else "front"
        integration = theme_integration_profile(theme, depth_band)
        shadow = f'<span class="ag-home__contact" aria-hidden="true" style="left:{layout.footprint.x/10:.3f}%;top:{layout.footprint.y/4.2:.3f}%;width:{layout.footprint.width/10:.3f}%;height:{layout.footprint.height/4.2:.3f}%;z-index:{depth_index}"></span>'
        alt = escape(str(item.get("name", "Plant")), quote=True)
        common = f'left:{layout.draw.x/10:.3f}%;top:{layout.draw.y/4.2:.3f}%;width:{layout.draw.width/10:.3f}%;height:{layout.draw.height/4.2:.3f}%;z-index:{depth_index + 1};--ag-contrast:{float(integration["contrast"]):.3f};--ag-saturation:{float(integration["saturation"]):.3f}'
        if src:
            plant = f'<img class="ag-home__plant" data-slot-index="{layout.slot_index}" src="{src}" alt="{alt}" style="{common}" data-base-type="{escape(base_type, quote=True)}">'
            tint = (
                f'<span class="ag-home__plant-tint" aria-hidden="true" style="left:{layout.draw.x/10:.3f}%;'
                f'top:{layout.draw.y/4.2:.3f}%;width:{layout.draw.width/10:.3f}%;height:{layout.draw.height/4.2:.3f}%;'
                f'z-index:{depth_index + 2};--ag-tint:{escape(str(integration["tint"]), quote=True)};'
                f'--ag-tint-alpha:{float(integration["tint_alpha"]):.3f};--ag-mask:url(&quot;{src}&quot;)"></span>'
            )
        else:
            fallback = _plant_fallback(item.get("stage"))
            font_size = max(24, min(58, int(layout.visible.height / 5)))
            plant = f'<span class="ag-home__plant-fallback" data-slot-index="{layout.slot_index}" role="img" aria-label="{alt}" style="{common};font-size:{font_size}px">{fallback}</span>'
            tint = ""
        selected_ring = ""
        if bool(item.get("is_focus")):
            selected_ring = (
                f'<span class="ag-home__selected-ring" aria-hidden="true" style="left:{(layout.support_rect.x - 4)/10:.3f}%;'
                f'top:{(layout.support_rect.bottom - 6)/4.2:.3f}%;width:{(layout.support_rect.width + 8)/10:.3f}%;'
                f'height:{max(5.0, layout.footprint.height)/4.2:.3f}%;z-index:{depth_index}"></span>'
            )
        plant_markup.append(selected_ring + shadow + plant + tint)
    focus_html = (
        '<div class="ag-home__identity"><div class="ag-home__eyebrow">Study garden</div>'
        '<div class="ag-home__focus-name">Your garden</div></div>'
    )
    if data.focus_plant_name:
        stage_tooltip = (
            ' data-tooltip="This plant has reached the final Rare growth stage." tabindex="0"'
            if str(data.focus_stage).lower() == "rare" else ""
        )
        focus_html = (
            '<div class="ag-home__identity" data-testid="home-focus">'
            '<div class="ag-home__eyebrow">Nurtured plant</div>'
            f'<div class="ag-home__focus-name">{escape(data.focus_plant_name)}</div>'
            f'<div class="ag-home__focus-stage"{stage_tooltip}>{escape(format_status_label(data.focus_stage))}</div></div>'
        )

    return f"""{HOME_WIDGET_STYLE}
<div id=\"ag-home-root\" data-state=\"{escape(phase)}\" role=\"region\" aria-label=\"Anki Garden\">
  {partial_banner}
  <div class=\"ag-home__body\">
    <div class=\"ag-home__scene\" data-testid=\"home-scene\"{background_style}>
      <div class=\"ag-home__art\" data-testid=\"home-plants\">{''.join(soil_markup)}{''.join(plant_markup)}{f'<img class="ag-home__occlusion" src="{escape(str(surface_variant.get("occlusion_url", "")), quote=True)}" alt="" aria-hidden="true">' if surface_variant.get("occlusion_url") else ''}</div>
    </div>
    <div class=\"ag-home__details\">
      {stage_up_html}
      <div class=\"ag-home__identity-row\">
        {focus_html}
        <button data-testid=\"home-open\" type=\"button\" aria-label=\"Open Garden\" data-tooltip=\"Open the full garden, plant controls, quests, and achievements.\"
          onclick=\"if(this.disabled)return;this.disabled=true;this.textContent='Opening…';pycmd('anki-garden:open');setTimeout(()=>{{this.disabled=false;this.textContent='Open Garden';}},1500)\">Open Garden</button>
      </div>
      {f'<p class="ag-home__partial-message" role="status">{escape(data.status_notice)}</p>' if data.status_notice else ''}
      <div class=\"ag-home__metrics\">
        <div class=\"ag-home__metric\" tabindex=\"0\" aria-label=\"{format_integer(data.reviews_today)} reviews today\" data-tooltip=\"The total number of cards reviewed today.\"><div class=\"ag-home__metric-label\">Reviews today</div><div class=\"ag-home__metric-value\" data-testid=\"home-reviews\">{format_integer(data.reviews_today)}</div></div>
        <div class=\"ag-home__metric\" tabindex=\"0\" aria-label=\"{format_integer(data.growth_earned)} of {format_integer(growth_cap)} daily growth\" data-tooltip=\"The total garden growth earned today and progress toward the daily goal.\"><div class=\"ag-home__metric-label\">Daily growth</div><div class=\"ag-home__metric-value\" data-testid=\"home-growth\">{format_integer(data.growth_earned)} of {format_integer(growth_cap)}</div>
          <div class=\"ag-home__bar-track\" role=\"progressbar\" aria-label=\"Daily growth\" aria-valuemin=\"0\" aria-valuemax=\"{growth_cap}\" aria-valuenow=\"{min(max(0, data.growth_earned), growth_cap)}\"><div data-testid=\"home-growth-bar\" aria-hidden=\"true\" style=\"width:{growth_pct}%\"></div></div>
        </div>
        <div class=\"ag-home__metric\" tabindex=\"0\" aria-label=\"{format_percent(data.health_ratio, places=0)} garden vitality\" data-tooltip=\"Garden vitality reflects the consistency of your recent study activity.\"><div class=\"ag-home__metric-label\">Garden vitality</div><div class=\"ag-home__metric-value\" data-testid=\"home-vitality\">{format_percent(data.health_ratio, places=0)}</div></div>
      </div>
    </div>
  </div>
  <div class=\"ag-home__tooltip\" role=\"tooltip\" hidden></div>
  <script>(function(root){{const tip=root.querySelector('.ag-home__tooltip');function show(e){{const el=e.target.closest('[data-tooltip]');if(!el)return;tip.textContent=el.dataset.tooltip;tip.hidden=false;const r=el.getBoundingClientRect();tip.style.left=Math.max(8,Math.min(window.innerWidth-tip.offsetWidth-8,r.left))+'px';tip.style.top=Math.max(8,r.bottom+6)+'px';}}function hide(e){{if(!e.relatedTarget||!root.contains(e.relatedTarget)||!e.relatedTarget.closest('[data-tooltip]'))tip.hidden=true;}}root.addEventListener('mouseover',show);root.addEventListener('focusin',show);root.addEventListener('mouseout',hide);root.addEventListener('focusout',hide);}})(document.currentScript.parentElement);</script>
</div>
"""


def build_home_widget_success_data(*, state: Any, reviews_today: int, health_ratio: float, growth_cap: int, scene_items: list[dict[str, Any]], stage_transition_message: str = "", background_url: str = "", garden_overlay_url: str = "", focus_plant: Any = None, focus_display: Any = None, next_milestone: int | None = None, milestone_ready: bool = False, status_notice: str = "") -> HomeWidgetData:
    stats = state.daily_stats
    if getattr(state, "selected_weather", None) in (None, ""):
        DISPLAY_TELEMETRY.record_missing_or_invalid_field(
            route="home_widget",
            field="selected_weather",
            reason="missing_or_empty",
            value=getattr(state, "selected_weather", None),
        )
    return HomeWidgetData(
        reviews_today=reviews_today,
        health_ratio=health_ratio,
        growth_earned=int(stats.growth_earned),
        growth_cap=int(growth_cap),
        streak_days=int(state.streak_days),
        weather=str(state.selected_weather or "N/A"),
        scene_items=tuple(scene_items),
        stage_transition_message=stage_transition_message,
        background_url=background_url,
        garden_overlay_url=garden_overlay_url,
        focus_plant_name=str(getattr(focus_plant, "name", "") or ""),
        focus_stage=str(getattr(focus_display, "stage", "") or ""),
        focus_points_remaining=max(0, int(getattr(focus_display, "points_remaining", 0) or 0)),
        next_milestone=next_milestone,
        total_reviews=max(0, int(getattr(state, "total_reviews", 0) or 0)),
        milestone_ready=milestone_ready,
        status_notice=status_notice,
        unlocked_slots=max(0, min(6, int(getattr(state, "unlocked_slots", 0) or 0))),
    )
