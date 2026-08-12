from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any

from ..display_telemetry import DISPLAY_TELEMETRY
from ..terminology import (
    ANKI_STREAK_EXPLANATION,
    GARDEN_CURRENCY_EXPLANATION,
    GROWTH_EXPLANATION,
)
from ..models.state import STREAK_BONUS_TIERS
from .formatters import format_integer, format_status_label
from .plant_display import compact_plant_layout, growth_display, scene_surface_variant


@dataclass(frozen=True)
class HomeWidgetData:
    reviews_today: int
    growth_earned: int
    base_growth: int
    streak_bonus_growth: int
    fertilizer_growth: int
    bonus_growth: int
    all_due_completed: bool
    streak_days: int
    streak_bonus_percent: int
    next_streak_day: int | None
    next_streak_bonus_percent: int | None
    garden_currency: int
    weather: str
    scene_items: tuple[dict[str, Any], ...] = ()
    background_placement: dict[str, Any] | None = None
    stage_transition_message: str = ""
    background_url: str = ""
    garden_overlay_url: str = ""
    total_reviews: int = 0
    status_notice: str = ""
    unlocked_slots: int = 0
    collection_count: int = 0
    active_plant_name: str = ""
    active_plant_stage: str = ""
    active_growth_points: int = 0
    active_stage_points: int = 0
    active_stage_goal: int = 0
    active_next_stage: str = ""
    active_points_remaining: int = 0
    active_fully_grown: bool = False
    garden_name: str = "My Garden"


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


DEFAULT_ERROR_MESSAGE = "Garden progress could not be loaded. Try again in a moment."


HOME_WIDGET_STYLE = """
<style>
#ag-home-root {
  max-width: 1480px;
  margin: 18px auto;
  padding: 0;
  box-sizing: border-box;
  overflow: visible;
  border: 1px solid rgba(118, 151, 126, 0.52);
  border-radius: 16px;
  background: #0d201d;
  color: #edf5ea;
  box-shadow: 0 18px 42px rgba(2, 11, 10, 0.28);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
.ag-home__state {
  box-sizing: border-box;
  min-height: 160px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  justify-content: center;
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
  box-sizing: border-box;
  width: 100%;
  overflow-wrap: anywhere;
  margin: 0;
  padding: 10px 16px;
  border-bottom: 1px solid rgba(223, 180, 98, 0.28);
  background: rgba(105, 70, 32, 0.34);
  color: #f1d59b;
}
.ag-home__body { display:grid; grid-template-columns:minmax(440px,65%) minmax(340px,35%); align-items:stretch; }
.ag-home__art { position:absolute; inset:0; overflow:hidden; }
.ag-home__plant { position:absolute; object-fit:contain; animation:none !important; transition:none !important; filter:contrast(var(--ag-contrast,1)) saturate(var(--ag-saturation,1)) brightness(var(--ag-brightness,1)); }
.ag-home__plant-tint { position:absolute; pointer-events:none; background:linear-gradient(90deg,transparent,rgba(255,230,190,var(--ag-key-alpha,0))),linear-gradient(180deg,transparent 70%,rgba(10,18,16,var(--ag-base-ao,0))),var(--ag-tint,transparent); opacity:var(--ag-tint-alpha,0); -webkit-mask-image:var(--ag-mask); -webkit-mask-position:center; -webkit-mask-repeat:no-repeat; -webkit-mask-size:contain; mask-image:var(--ag-mask); mask-position:center; mask-repeat:no-repeat; mask-size:contain; }
.ag-home__occlusion { position:absolute; inset:0; z-index:3; width:100%; height:100%; object-fit:cover; object-position:var(--ag-focal-x,50%) var(--ag-focal-y,50%); pointer-events:none; }
.ag-home__shadow-plane { position:absolute; inset:0; pointer-events:none; }
.ag-home__contact,.ag-home__cast { position:absolute; border-radius:50%; pointer-events:none; }
.ag-home__contact { background:radial-gradient(ellipse,rgba(54,34,22,.44),rgba(61,40,25,.22) 56%,transparent 80%); filter:blur(1px); }
.ag-home__cast { background:radial-gradient(ellipse,rgba(55,34,21,.18),rgba(61,40,25,.08) 58%,transparent 82%); filter:blur(1.4px); }
.ag-home__plant-fallback { position:absolute; display:flex; align-items:flex-end; justify-content:center; line-height:1; }
.ag-home__fallback-silhouette { position:absolute; left:50%; bottom:18%; width:2px; height:45%; transform:translateX(-50%); background:#7f9e7c; border-radius:2px; opacity:.78; }
.ag-home__fallback-silhouette::before,.ag-home__fallback-silhouette::after { content:""; position:absolute; width:14px; height:9px; top:25%; border:1px solid #8fb18a; background:rgba(72,108,73,.74); }
.ag-home__fallback-silhouette::before { right:0; border-radius:12px 2px 12px 2px; transform:rotate(18deg); transform-origin:right center; }
.ag-home__fallback-silhouette::after { left:0; top:48%; border-radius:2px 12px 2px 12px; transform:rotate(-18deg); transform-origin:left center; }
.ag-home__fallback-label { max-width:92%; overflow:hidden; padding:4px 6px; border-radius:5px; background:rgba(8,27,23,.84); color:#dce9dd; font-size:11px; line-height:1.2; text-align:center; }
.ag-home__fallback-label > span { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.ag-home__fallback-stage { margin-top:1px; color:#aac3b1; }
.ag-home__metrics { display:flex; flex-direction:column; gap:10px; min-width:0; min-height:0; }
.ag-home__scene {
  position: relative;
  width: 100%;
  max-width: 100%;
  min-width: 0;
  min-height: 260px;
  aspect-ratio: 12 / 5;
  overflow: hidden;
  background-position: var(--ag-focal-x,50%) var(--ag-focal-y,50%);
  background-size: cover;
}
.ag-home__scene::after { content:""; position:absolute; inset:0; pointer-events:none; box-shadow:inset -24px 0 38px rgba(5,16,14,.24), inset 0 -18px 32px rgba(5,14,12,.16); }
.ag-home__details { min-width:0; min-height:0; padding:12px 16px 14px; display:flex; flex-direction:column; gap:10px; overflow:visible; background:radial-gradient(circle at 92% 3%,rgba(50,106,75,.18),transparent 38%),linear-gradient(150deg,#102a25,#0a1d1a 78%); border-left:1px solid rgba(137,165,137,.22); box-shadow:inset 1px 0 rgba(226,239,223,.025); }
.ag-home__details,.ag-home__details * { box-sizing:border-box; }
.ag-home__identity-row { display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:center; gap:12px; min-width:0; min-height:48px; }
.ag-home__identity { min-width:0; }
.ag-home__eyebrow { margin-bottom:2px; color:#d8b875; font-size:11.5px; font-weight:700; letter-spacing:.1em; line-height:1.1; text-transform:uppercase; }
.ag-home__focus-name {
  display:block;
  overflow:hidden;
  margin:0;
  color:#f3f7f2;
  font-size:24px;
  font-weight:800;
  line-height:1.1;
  text-overflow:ellipsis;
  white-space:nowrap;
}
.ag-home__metric {
  display:flex;
  flex-direction:column;
  justify-content:flex-start;
  min-width:0;
  padding:11px 14px 12px;
  border:1px solid rgba(128,160,135,.16);
  border-radius:12px;
  background:rgba(11,40,34,.48);
  box-shadow:inset 0 1px 0 rgba(235,246,232,.025);
  cursor:help;
}
.ag-home__metric:hover { border-color:rgba(139,178,148,.28); background:rgba(15,48,40,.58); }
.ag-home__metric:focus-visible { position:relative; z-index:1; outline:3px solid #e5f2a6; outline-offset:-3px; }
.ag-home__metric-label { min-width:0; color:#9fb9a8; font-size:12px; font-weight:700; letter-spacing:.075em; line-height:1.3; text-transform:uppercase; }
.ag-home__metric-value { min-width:0; max-width:100%; color:#f1f6f1; font-weight:800; line-height:1.1; }
.ag-home__metric-value--plant { margin-top:6px; overflow:hidden; color:#b5e1aa; font-size:23px; text-overflow:ellipsis; white-space:nowrap; text-shadow:0 1px 12px rgba(109,184,112,.12); }
.ag-home__metric--plant { min-height:0; border-color:rgba(125,174,132,.34); background:rgba(20,58,47,.68); box-shadow:inset 0 1px 0 rgba(221,242,218,.04),0 5px 16px rgba(1,15,11,.08); }
.ag-home__metric--plant:hover { border-color:rgba(153,199,158,.48); background:rgba(24,66,53,.72); }
.ag-home__metric--streak,.ag-home__metric--coins { min-height:0; }
.ag-home__metric--coins .ag-home__metric-value { color:#f2dda4; }
.ag-home__metric-heading,.ag-home__metric-value-row { display:flex; align-items:center; justify-content:space-between; gap:12px; min-width:0; }
.ag-home__metric-heading > div,.ag-home__metric-value-row > .ag-home__metric-value { min-width:0; flex:1 1 auto; }
.ag-home__metric-badge { flex:0 0 auto; min-height:24px; padding:3px 8px; border:1px solid rgba(214,186,121,.34); border-radius:999px; background:rgba(216,184,117,.08); color:#dfc98d; font-size:12px; font-weight:700; line-height:1.2; white-space:nowrap; }
.ag-home__growth-block { margin-top:10px; }
.ag-home__growth-row { display:flex; align-items:end; justify-content:space-between; gap:12px; min-width:0; }
.ag-home__growth-label { color:#9fb9a8; font-size:13px; font-weight:650; line-height:1.2; }
.ag-home__growth-value { margin-top:2px; color:#edf5ea; font-size:18px; font-weight:750; font-variant-numeric:tabular-nums; line-height:1.15; white-space:nowrap; }
.ag-home__growth-slash { padding:0 2px; color:#7f998a; font-weight:500; }
.ag-home__growth-next { min-width:0; overflow:hidden; color:#b9cec0; font-size:13px; line-height:1.25; text-align:right; text-overflow:ellipsis; white-space:nowrap; }
.ag-home__growth-total { margin-top:5px; color:#91aa9b; font-size:12.5px; line-height:1.25; }
.ag-home__streak-value { display:flex; align-items:baseline; gap:6px; margin-top:6px; font-variant-numeric:tabular-nums; white-space:nowrap; text-shadow:0 1px 14px rgba(224,239,219,.12); }
.ag-home__streak-number { font-size:36px; }
.ag-home__streak-unit { font-size:18px; font-weight:650; }
.ag-home__coins-value { margin-top:6px; font-size:32px; font-variant-numeric:tabular-nums; white-space:nowrap; text-shadow:0 1px 14px rgba(216,184,117,.14); }
.ag-home__metric-support { margin-top:4px; color:#aebfb4; font-size:13.5px; font-weight:400; line-height:1.3; text-align:left; }
.ag-home__status-notice { box-sizing:border-box; width:100%; margin:0; padding:8px 10px; border:1px solid rgba(223,180,98,.28); border-radius:9px; background:rgba(105,70,32,.24); color:#f1d59b; font-size:12px; line-height:1.4; overflow-wrap:anywhere; }
.ag-home__tooltip { position:fixed; z-index:9999; box-sizing:border-box; max-width:280px; max-height:calc(100vh - 16px); overflow:auto; padding:7px 9px; border-radius:7px; background:#10201d; color:#eef9f0; box-shadow:0 4px 16px rgba(0,0,0,.3); font-size:12px; line-height:1.35; pointer-events:none; }
.ag-home__bar-track {
  position:relative;
  height: 8px;
  margin: 6px 0 0;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.1);
}
.ag-home__bar-track--milestones { background-color:rgba(255,255,255,.08); background-image:repeating-linear-gradient(90deg,transparent 0,transparent calc(16.666% - .5px),rgba(230,241,225,.22) calc(16.666% - .5px),rgba(230,241,225,.22) calc(16.666% + .5px),transparent calc(16.666% + .5px),transparent 16.666%); }
.ag-home__bar-fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg,#4bbf82,#b9d77d 72%,#d9d77d);
  box-shadow:0 0 10px rgba(75,191,130,.18);
}
.ag-home__stage-up {
  box-sizing: border-box;
  width: calc(100% - 32px);
  margin: 10px 16px 0;
  padding: 8px 10px;
  border: 1px solid rgba(244, 213, 138, 0.44);
  border-radius: 8px;
  background: rgba(117, 82, 35, 0.34);
  color: #f4d58a;
  font-weight: 700;
  overflow-wrap: anywhere;
  text-align: center;
}
#ag-home-root button {
  display:inline-flex;
  align-items:center;
  justify-content:center;
  min-width:120px;
  min-height:42px;
  box-sizing:border-box;
  line-height:1.2;
  flex:none;
  margin: 0;
  padding: 7px 16px;
  border: 1px solid rgba(132,180,146,.72);
  border-radius: 12px;
  background: #286346;
  color: #eef9f0;
  font-size:15px;
  font-weight: 700;
  white-space:nowrap;
  cursor: pointer;
  box-shadow:inset 0 1px 0 rgba(242,250,240,.08),0 6px 14px rgba(1,14,10,.14);
}
#ag-home-root button.ag-home__open::after { content:"→"; margin-left:7px; font-size:15px; line-height:1; }
#ag-home-root button.ag-home__open:disabled::after { content:""; margin:0; }
#ag-home-root button:hover { background: #327653; }
#ag-home-root button:active { background:#183828; transform:translateY(1px); }
#ag-home-root button:disabled { cursor:wait; opacity:.72; }
#ag-home-root button:focus-visible {
  outline: 3px solid #e5f2a6;
  outline-offset: 2px;
}
.ag-home__open { min-width:112px !important; min-height:40px !important; padding:6px 13px !important; border-radius:10px !important; font-size:14px !important; box-shadow:inset 0 1px 0 rgba(242,250,240,.08),0 4px 12px rgba(1,14,10,.12) !important; }
.nightMode #ag-home-root { background:#0d201d; color:#edf5ea; border-color:rgba(118,157,132,.48); }
@media (max-width: 900px) {
  .ag-home__body { grid-template-columns:1fr; }
  .ag-home__scene { min-height:0; aspect-ratio:12 / 5; }
  .ag-home__details { border-left:0; border-top:1px solid rgba(137,165,137,.22); }
}
@media (max-width: 600px) {
  #ag-home-root { margin:10px 8px; border-radius:12px; }
  .ag-home__details { padding:14px; }
  .ag-home__focus-name { font-size:23px; }
}
@media (max-width: 480px) {
  .ag-home__identity-row { grid-template-columns:1fr; align-items:stretch; gap:12px; }
  #ag-home-root button { width:100%; }
  .ag-home__growth-row { align-items:flex-start; flex-direction:column; gap:4px; }
  .ag-home__growth-next { text-align:left; }
}
</style>
"""


def _plant_fallback(_stage: Any) -> str:
    """Return a quiet code-native silhouette; system emoji are never substituted."""
    return '<span class="ag-home__fallback-silhouette" aria-hidden="true"></span>'


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
            '<div class="ag-home__state-message">Loading overview…</div></div>'
            "</div>"
        )
    if phase == "empty":
        return (
            HOME_WIDGET_STYLE
            +
            '<div id="ag-home-root" data-state="empty" role="region" aria-label="Anki Garden">'
            '<div class="ag-home__state" data-testid="home-empty" role="status">'
            '<div class="ag-home__state-title">Ready to grow</div>'
            '<div class="ag-home__state-message">Answer your first card to begin nurturing a plant.</div></div>'
            "</div>"
        )
    if phase == "error":
        message = escape(snapshot.error_message or DEFAULT_ERROR_MESSAGE)
        return (
            HOME_WIDGET_STYLE
            +
            '<div id="ag-home-root" data-state="error" role="region" aria-label="Anki Garden">'
            '<div class="ag-home__state">'
            '<div class="ag-home__state-title">Overview unavailable</div>'
            f'<div class="ag-home__state-message" data-testid="home-error" role="alert">{message}</div>'
            '<button data-testid="home-retry" type="button" aria-label="Retry loading overview" '
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
            '<div class="ag-home__state-title">Overview unavailable</div>'
            '<div class="ag-home__state-message" data-testid="home-error" role="alert">The summary could not be displayed.</div></div>'
            "</div>"
        )
    if not data.weather:
        DISPLAY_TELEMETRY.track_fallback(route="home_widget", field="weather")

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

    background_placement = (
        data.background_placement
        if isinstance(data.background_placement, dict)
        else data.scene_items[0].get("background_placement", {})
        if data.scene_items
        else {}
    )
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
    # Empty and locked beds already belong to the background artwork. Drawing
    # another soil ellipse here creates a conspicuous orange oval and can cover
    # the hand-painted bed rim, so Home only layers real plant content.
    plant_markup: dict[str, list[str]] = {"rear": [], "front": []}
    theme = str(data.scene_items[0].get("background_theme", "verdant_twilight")) if data.scene_items else "verdant_twilight"
    band_counts = {"rear": 0, "front": 0}
    for layout in layouts:
        item = by_slot.get(layout.slot_index, {})
        src = escape(str(item.get("url", "")), quote=True)
        base_type = str(item.get("placement", {}).get("base_type", "legacy")) if isinstance(item.get("placement"), dict) else "legacy"
        depth_band = "rear" if layout.depth < 420 * .68 else "front"
        # Reserve a row-specific z-index range below its foreground mask.
        # This keeps a full six-plant rear row behind the rear occlusion.
        depth_index = (10 if depth_band == "rear" else 40) + band_counts[depth_band] * 3
        band_counts[depth_band] += 1
        lighting = layout.grounding.lighting
        integration = {
            "contrast": lighting.contrast,
            "saturation": lighting.saturation,
            "exposure": lighting.exposure,
            "tint": lighting.tint,
            "tint_alpha": lighting.tint_alpha,
            "key_strength": lighting.key_strength,
            "base_ao": lighting.base_ao,
        }
        contact = layout.grounding.contact_shadow
        cast = layout.grounding.cast_shadow
        plane = ",".join(f"{x/10:.3f}% {y/4.2:.3f}%" for x, y in layout.grounding.shadow_plane)
        shadow = (
            f'<span class="ag-home__shadow-plane" aria-hidden="true" style="z-index:{depth_index};clip-path:polygon({plane})">'
            f'<span class="ag-home__cast" style="left:{cast.x/10:.3f}%;top:{cast.y/4.2:.3f}%;width:{cast.width/10:.3f}%;height:{cast.height/4.2:.3f}%"></span>'
            f'<span class="ag-home__contact" style="left:{contact.x/10:.3f}%;top:{contact.y/4.2:.3f}%;width:{contact.width/10:.3f}%;height:{contact.height/4.2:.3f}%"></span></span>'
        )
        alt = escape(str(item.get("name", "Plant")), quote=True)
        common = f'left:{layout.draw.x/10:.3f}%;top:{layout.draw.y/4.2:.3f}%;width:{layout.draw.width/10:.3f}%;height:{layout.draw.height/4.2:.3f}%;z-index:{depth_index + 1};--ag-contrast:{float(integration["contrast"]):.3f};--ag-saturation:{float(integration["saturation"]):.3f};--ag-brightness:{1.0 + float(integration.get("exposure", 0.0)):.3f}'
        if src:
            plant = f'<img class="ag-home__plant" data-slot-index="{layout.slot_index}" src="{src}" alt="{alt}" style="{common}" data-base-type="{escape(base_type, quote=True)}">'
            tint = (
                f'<span class="ag-home__plant-tint" aria-hidden="true" style="left:{layout.draw.x/10:.3f}%;'
                f'top:{layout.draw.y/4.2:.3f}%;width:{layout.draw.width/10:.3f}%;height:{layout.draw.height/4.2:.3f}%;'
                f'z-index:{depth_index + 2};--ag-tint:{escape(str(integration["tint"]), quote=True)};'
                f'--ag-tint-alpha:{float(integration["tint_alpha"]):.3f};'
                f'--ag-key-alpha:{float(integration.get("key_strength", 0.0)):.3f};'
                f'--ag-base-ao:{float(integration.get("base_ao", 0.0)):.3f};'
                f'--ag-mask:url(&quot;{src}&quot;)"></span>'
            )
        else:
            fallback = _plant_fallback(item.get("stage"))
            stage_label = escape(format_status_label(item.get("stage") or "plant"))
            plant = (
                f'<span class="ag-home__plant-fallback" data-slot-index="{layout.slot_index}" role="img" '
                f'aria-label="{alt}, {stage_label}" style="{common}">{fallback}'
                f'<span class="ag-home__fallback-label"><span>{alt}</span>'
                f'<span class="ag-home__fallback-stage">{stage_label}</span></span></span>'
            )
            tint = ""
        plant_markup[depth_band].append(shadow + plant + tint)
    layer_urls = surface_variant.get("occlusion_layer_urls", {})
    occlusion_markup: dict[str, str] = {}
    if isinstance(layer_urls, dict):
        for row, z_index in (("rear", 30), ("front", 70)):
            url = str(layer_urls.get(row, "") or "")
            if url:
                occlusion_markup[row] = f'<img class="ag-home__occlusion" style="z-index:{z_index}" src="{escape(url, quote=True)}" alt="" aria-hidden="true">'
    legacy_occlusion_url = str(surface_variant.get("occlusion_url", "") or "")
    legacy_occlusion = (
        f'<img class="ag-home__occlusion" src="{escape(legacy_occlusion_url, quote=True)}" alt="" aria-hidden="true">'
        if legacy_occlusion_url and not occlusion_markup else ""
    )
    garden_name = escape(str(data.garden_name or "My Garden"))
    garden_identity_html = (
        '<div class="ag-home__identity"><div class="ag-home__eyebrow" aria-hidden="true">Anki Garden</div>'
        f'<h2 class="ag-home__focus-name">{garden_name}</h2></div>'
    )
    streak_unit = "day" if data.streak_days == 1 else "days"
    growth_help = escape(GROWTH_EXPLANATION, quote=True)
    streak_help = escape(ANKI_STREAK_EXPLANATION, quote=True)
    currency_help = escape(GARDEN_CURRENCY_EXPLANATION, quote=True)
    if data.streak_days <= 0:
        streak_next = "Study today to begin"
    elif data.next_streak_day is None:
        streak_next = "Maximum Growth bonus reached"
    else:
        next_day_unit = "day" if data.next_streak_day == 1 else "days"
        streak_next = (
            f"Next bonus: +{data.next_streak_bonus_percent}% at "
            f"{data.next_streak_day} {next_day_unit}"
        )
    streak_progress = _streak_milestone_progress(data.streak_days)
    streak_badge_html = (
        f'<span class="ag-home__metric-badge">+{data.streak_bonus_percent}% Growth</span>'
        if data.streak_bonus_percent > 0
        else ""
    )
    if data.streak_days <= 0:
        streak_accessible_label = "No Anki streak yet. Study today to start your streak."
    elif data.streak_bonus_percent > 0:
        streak_accessible_label = (
            f"{format_integer(data.streak_days)}-day Anki streak; "
            f"+{data.streak_bonus_percent}% Growth bonus"
        )
    else:
        streak_accessible_label = f"{format_integer(data.streak_days)}-day Anki streak"
    active_name = str(data.active_plant_name or "").strip()
    if active_name:
        active_stage = format_status_label(data.active_plant_stage or "seed")
        if data.active_fully_grown:
            active_progress_value = format_integer(data.active_growth_points)
            active_progress_target = "Fully grown"
            active_progress_max = 1
            active_progress_now = 1
            active_progress_percent = 100
            active_progress_label = f"{active_name} is fully grown"
        else:
            next_stage = format_status_label(data.active_next_stage or "next stage")
            active_progress_value = (
                f"{format_integer(data.active_stage_points)}"
                f'<span class="ag-home__growth-slash">/</span>'
                f"{format_integer(data.active_stage_goal)}"
            )
            active_progress_target = f"{next_stage} next"
            active_progress_max = max(1, int(data.active_stage_goal))
            active_progress_now = min(active_progress_max, max(0, int(data.active_stage_points)))
            active_progress_percent = int(active_progress_now / active_progress_max * 100)
            active_progress_label = f"{active_name} progress to {next_stage}"
        active_growth_html = (
            f'<section class="ag-home__metric ag-home__metric--plant nurtured-plant-summary" tabindex="0" aria-label="{escape(active_progress_label, quote=True)}" '
            f'data-tooltip="{growth_help}"><div class="ag-home__metric-heading">'
            f'<div class="ag-home__metric-label">Nurtured plant</div>'
            f'<span class="ag-home__metric-badge">{escape(active_stage)}</span></div>'
            f'<div class="ag-home__metric-value ag-home__metric-value--plant" data-testid="home-active-name">{escape(active_name)}</div>'
            f'<div class="ag-home__growth-block"><div class="ag-home__growth-row"><div>'
            f'<div class="ag-home__growth-label">Growth</div>'
            f'<div class="ag-home__growth-value">{active_progress_value}</div></div>'
            f'<div class="ag-home__growth-next">{escape(active_progress_target)}</div></div>'
            f'<div class="ag-home__bar-track ag-home__bar-track--growth" role="progressbar" aria-label="{escape(active_progress_label, quote=True)}" '
            f'aria-valuemin="0" aria-valuemax="{active_progress_max}" aria-valuenow="{active_progress_now}">'
            f'<div class="ag-home__bar-fill" data-testid="home-growth-bar" aria-hidden="true" '
            f'style="width:{active_progress_percent}%"></div></div>'
            f'<div class="ag-home__growth-total"><span data-testid="home-growth">'
            f'{format_integer(data.active_growth_points)}</span> total Growth</div></div></section>'
        )
    else:
        active_growth_html = (
            f'<section class="ag-home__metric ag-home__metric--plant nurtured-plant-summary" tabindex="0" aria-label="No nurtured plant selected" '
            f'data-tooltip="{growth_help}"><div class="ag-home__metric-label">Nurtured plant</div>'
            '<div class="ag-home__metric-value ag-home__metric-value--plant" data-testid="home-active-name">None selected</div>'
            '<div class="ag-home__metric-support">Open Garden to choose one.</div></section>'
        )

    return f"""{HOME_WIDGET_STYLE}
<div id=\"ag-home-root\" data-state=\"{escape(phase)}\" role=\"region\" aria-label=\"Anki Garden\">
  {partial_banner}
  {stage_up_html}
  <div class=\"ag-home__body\">
    <div class=\"ag-home__scene\" data-testid=\"home-scene\" aria-label=\"Garden preview. Open Garden to interact.\"{background_style}>
      <div class=\"ag-home__art\" data-testid=\"home-plants\">{legacy_occlusion}{''.join(plant_markup['rear'])}{occlusion_markup.get('rear', '')}{''.join(plant_markup['front'])}{occlusion_markup.get('front', '')}</div>
    </div>
    <aside class=\"ag-home__details home-summary-panel\">
      <header class=\"ag-home__identity-row summary-header\">
        {garden_identity_html}
        <button class=\"ag-home__open\" data-testid=\"home-open\" type=\"button\" aria-label=\"Open Garden\" data-tooltip=\"View and manage your plants.\"
          onclick=\"if(this.disabled)return;this.disabled=true;this.textContent='Opening…';pycmd('anki-garden:open');setTimeout(()=>{{this.disabled=false;this.textContent='Open Garden';}},1500)\">Open Garden</button>
      </header>
      {f'<p class="ag-home__status-notice" role="status">{escape(data.status_notice)}</p>' if data.status_notice else ''}
      {active_growth_html}
      <div class=\"ag-home__metrics\" role=\"group\" aria-label=\"Garden summary\">
        <section class=\"ag-home__metric ag-home__metric--streak streak-metric\" tabindex=\"0\" aria-label=\"{escape(streak_accessible_label, quote=True)}\" data-tooltip=\"{streak_help}\"><div class=\"ag-home__metric-heading\"><div class=\"ag-home__metric-label\">Anki streak</div>{streak_badge_html}</div><div class=\"ag-home__metric-value ag-home__streak-value\" data-testid=\"home-streak\"><span class=\"ag-home__streak-number\">{format_integer(data.streak_days)}</span><span class=\"ag-home__streak-unit\">{streak_unit}</span></div><div class=\"ag-home__metric-support\">{streak_next}</div><div class=\"ag-home__bar-track ag-home__bar-track--milestones\" role=\"progressbar\" aria-label=\"Anki streak progress\" aria-valuemin=\"0\" aria-valuemax=\"100\" aria-valuenow=\"{streak_progress}\" aria-valuetext=\"{escape(streak_accessible_label, quote=True)}. {escape(streak_next, quote=True)}\"><div class=\"ag-home__bar-fill\" data-testid=\"home-streak-bar\" aria-hidden=\"true\" style=\"width:{streak_progress}%\"></div></div></section>
        <section class=\"ag-home__metric ag-home__metric--coins coins-metric\" tabindex=\"0\" aria-label=\"{format_integer(data.garden_currency)} Garden Coins\" data-tooltip=\"{currency_help}\"><div class=\"ag-home__metric-label\">Garden Coins</div><div class=\"ag-home__metric-value ag-home__coins-value\" data-testid=\"home-currency\">{format_integer(data.garden_currency)}</div><div class=\"ag-home__metric-support\">For Nursery plants, items, and upgrades</div></section>
      </div>
    </aside>
  </div>
  <div class=\"ag-home__tooltip\" role=\"tooltip\" hidden id=\"ag-home-tooltip\"></div>
  <script>(function(root){{const tip=root.querySelector('.ag-home__tooltip');let active=null;function position(el){{if(!el||tip.hidden)return;const r=el.getBoundingClientRect();const margin=8;const gap=6;const maxLeft=Math.max(margin,window.innerWidth-tip.offsetWidth-margin);const left=Math.min(maxLeft,Math.max(margin,r.left));const maxTop=Math.max(margin,window.innerHeight-tip.offsetHeight-margin);const below=r.bottom+gap;const above=r.top-tip.offsetHeight-gap;const top=below<=maxTop?below:(above>=margin?above:maxTop);tip.style.left=left+'px';tip.style.top=top+'px';}}function clear(){{if(active&&active.getAttribute('aria-describedby')===tip.id)active.removeAttribute('aria-describedby');active=null;tip.hidden=true;}}function show(e){{const el=e.target.closest('[data-tooltip]');if(!el)return;if(active!==el)clear();active=el;active.setAttribute('aria-describedby',tip.id);tip.textContent=el.dataset.tooltip;tip.hidden=false;requestAnimationFrame(()=>position(active));}}function hide(e){{const related=e.relatedTarget;const next=related&&typeof related.closest==='function'?related.closest('[data-tooltip]'):null;if(next===active)return;clear();}}root.addEventListener('mouseover',show);root.addEventListener('focusin',show);root.addEventListener('mouseout',hide);root.addEventListener('focusout',hide);window.addEventListener('resize',()=>position(active),{{passive:true}});window.addEventListener('scroll',()=>position(active),{{passive:true,capture:true}});}})(document.currentScript.parentElement);</script>
</div>
"""


def build_home_widget_success_data(*, state: Any, reviews_today: int, scene_items: list[dict[str, Any]], background_placement: dict[str, Any] | None = None, stage_transition_message: str = "", background_url: str = "", garden_overlay_url: str = "", status_notice: str = "") -> HomeWidgetData:
    stats = state.daily_stats
    plants = list(getattr(state, "plants", []) or [])
    active_id = str(getattr(state, "active_plant_id", "") or "")
    active_plant = next(
        (plant for plant in plants if str(getattr(plant, "plant_id", "") or "") == active_id),
        None,
    )
    active_growth = growth_display(getattr(active_plant, "growth_points", 0))
    if getattr(state, "selected_weather", None) in (None, ""):
        DISPLAY_TELEMETRY.record_missing_or_invalid_field(
            route="home_widget",
            field="selected_weather",
            reason="missing_or_empty",
            value=getattr(state, "selected_weather", None),
        )
    return HomeWidgetData(
        reviews_today=reviews_today,
        growth_earned=int(stats.growth_earned),
        base_growth=int(getattr(stats, "base_growth", 0)),
        streak_bonus_growth=int(getattr(stats, "streak_bonus_growth", 0)),
        fertilizer_growth=int(getattr(stats, "fertilizer_growth", 0)),
        bonus_growth=int(getattr(stats, "bonus_growth", 0)),
        all_due_completed=bool(getattr(stats, "completed_due_cards", False)),
        streak_days=int(state.streak_days),
        streak_bonus_percent=_streak_bonus_percent(int(state.streak_days)),
        next_streak_day=_next_streak_day(int(state.streak_days)),
        next_streak_bonus_percent=_next_streak_bonus(int(state.streak_days)),
        garden_currency=max(0, int(getattr(state, "currency_balance", 0))),
        weather=str(state.selected_weather or "N/A"),
        scene_items=tuple(scene_items),
        background_placement=background_placement,
        stage_transition_message=stage_transition_message,
        background_url=background_url,
        garden_overlay_url=garden_overlay_url,
        total_reviews=max(0, int(getattr(state, "total_reviews", 0) or 0)),
        status_notice=status_notice,
        unlocked_slots=max(0, min(6, int(getattr(state, "unlocked_slots", 0) or 0))),
        collection_count=max(0, len(plants)),
        active_plant_name=str(getattr(active_plant, "name", "") or ""),
        active_plant_stage=str(getattr(active_plant, "growth_stage", "") or ""),
        active_growth_points=max(0, int(getattr(active_plant, "growth_points", 0) or 0)),
        active_stage_points=active_growth.stage_points if active_plant is not None else 0,
        active_stage_goal=active_growth.stage_goal if active_plant is not None else 0,
        active_next_stage=str(active_growth.next_stage or "") if active_plant is not None else "",
        active_points_remaining=active_growth.points_remaining if active_plant is not None else 0,
        active_fully_grown=active_growth.fully_grown if active_plant is not None else False,
        garden_name=str(getattr(state, "garden_name", "My Garden") or "My Garden"),
    )


def _streak_bonus_percent(streak_days: int) -> int:
    bonus = 0
    for threshold, percent in STREAK_BONUS_TIERS:
        if streak_days >= threshold:
            bonus = percent
        else:
            break
    return bonus


def _next_streak_day(streak_days: int) -> int | None:
    return next((threshold for threshold, _percent in STREAK_BONUS_TIERS if streak_days < threshold), None)


def _next_streak_bonus(streak_days: int) -> int | None:
    return next((percent for threshold, percent in STREAK_BONUS_TIERS if streak_days < threshold), None)


def _streak_milestone_progress(streak_days: int) -> int:
    """Map uneven day thresholds onto equal visual milestone segments."""

    days = max(0, int(streak_days))
    points = (0, *(threshold for threshold, _percent in STREAK_BONUS_TIERS))
    if days >= points[-1]:
        return 100
    for index in range(len(points) - 1):
        start, end = points[index], points[index + 1]
        if start <= days < end:
            interval = max(1, end - start)
            progress = (days - start) / interval
            return int(round((index + progress) / (len(points) - 1) * 100))
    return 0
