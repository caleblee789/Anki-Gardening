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
  min-height: 260px;
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
.ag-home__metrics {
  display: grid;
  grid-template-columns: repeat(2,minmax(0,1fr));
  gap: 10px;
  min-height: 0;
  margin-top: 16px;
  align-content: start;
}
.ag-home__scene {
  position: relative;
  min-height: 260px;
  aspect-ratio: 12 / 5;
  overflow: hidden;
  background-position: var(--ag-focal-x,50%) var(--ag-focal-y,50%);
  background-size: cover;
}
.ag-home__scene::after { content:""; position:absolute; inset:0; pointer-events:none; box-shadow:inset -24px 0 38px rgba(5,16,14,.24), inset 0 -18px 32px rgba(5,14,12,.16); }
.ag-home__details { min-width:0; min-height:0; padding:20px 22px; display:flex; flex-direction:column; overflow:visible; background:radial-gradient(circle at 92% 3%,rgba(50,106,75,.16),transparent 35%),linear-gradient(150deg,#102a25,#0a1d1a 78%); border-left:1px solid rgba(137,165,137,.22); }
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
.ag-home__focus-stage { margin-top:3px; color:#b9cec0; font-size:12px; line-height:1.35; }
.ag-home__metric {
  display:flex;
  flex-direction:column;
  justify-content:flex-start;
  min-height:72px;
  padding:12px 14px;
  border:1px solid rgba(121,158,131,.24);
  border-radius:12px;
  background:linear-gradient(145deg,rgba(14,47,40,.72),rgba(6,26,22,.58));
  box-shadow:inset 0 1px 0 rgba(231,244,228,.035);
}
.ag-home__metric:hover { border-color:rgba(216,184,117,.52); }
.ag-home__metric:focus-visible { border-color:rgba(229,242,166,.72); outline:3px solid #e5f2a6; outline-offset:2px; }
.ag-home__metric-label { color:#9ab7a6; font-size:12px; font-weight:700; letter-spacing:.045em; text-transform:uppercase; }
.ag-home__metric-value { min-width:0; max-width:100%; margin-top:2px; color:#edf5ea; font-size:18px; font-weight:750; line-height:1.18; overflow-wrap:anywhere; word-break:break-word; }
.ag-home__metric-value--plant { display:-webkit-box; overflow:hidden; -webkit-box-orient:vertical; -webkit-line-clamp:2; }
.ag-home__metric--plant { grid-column:1 / -1; min-height:98px; border-color:rgba(117,161,128,.32); background:linear-gradient(145deg,rgba(21,62,51,.82),rgba(7,31,26,.66)); }
.ag-home__metric--coins { background:linear-gradient(145deg,rgba(56,51,25,.42),rgba(8,30,25,.62)); }
.ag-home__metric-heading,.ag-home__metric-value-row { display:flex; align-items:flex-start; justify-content:space-between; gap:10px; min-width:0; }
.ag-home__metric-heading > div,.ag-home__metric-value-row > .ag-home__metric-value { min-width:0; flex:1 1 auto; }
.ag-home__metric-badge { flex:0 0 auto; max-width:42%; overflow:hidden; padding:4px 8px; border:1px solid rgba(214,186,121,.28); border-radius:999px; background:rgba(216,184,117,.08); color:#d9c58e; font-size:12px; font-weight:700; line-height:1.2; text-overflow:ellipsis; white-space:nowrap; }
.ag-home__metric-support { margin-top:5px; color:#b9cec0; font-size:12px; line-height:1.35; }
.ag-home__metric-progress-copy { margin-top:8px; color:#d5e3d7; font-size:12px; font-weight:650; line-height:1.25; }
.ag-home__tooltip { position:fixed; z-index:9999; box-sizing:border-box; max-width:280px; max-height:calc(100vh - 16px); overflow:auto; padding:7px 9px; border-radius:7px; background:#10201d; color:#eef9f0; box-shadow:0 4px 16px rgba(0,0,0,.3); font-size:12px; line-height:1.35; pointer-events:none; }
.ag-home__bar-track {
  height: 6px;
  margin: 6px 0 0;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.12);
}
.ag-home__bar-fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #4bbf82, #d9d77d);
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
  .ag-home__scene { min-height:210px; aspect-ratio:16 / 7; }
  .ag-home__details { border-left:0; border-top:1px solid rgba(137,165,137,.22); }
  .ag-home__metrics { grid-template-columns:repeat(3,minmax(0,1fr)); }
  .ag-home__metric--plant { grid-column:auto; }
}
@media (max-width: 700px) {
  .ag-home__metrics { grid-template-columns:repeat(2,minmax(0,1fr)); }
  .ag-home__metric--plant { grid-column:1 / -1; }
}
@media (max-width: 600px) {
  #ag-home-root { margin:10px 8px; border-radius:12px; }
  .ag-home__details { padding:14px; }
  .ag-home__identity-row { align-items:stretch; flex-direction:column; }
  .ag-home__metric { min-height:46px; padding:8px; }
  .ag-home__metric-value { font-size:15px; }
  #ag-home-root button { width:100%; }
}
@media (max-width: 480px) {
  .ag-home__metrics { grid-template-columns:1fr; }
  .ag-home__metric--plant { grid-column:auto; }
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
            '<div class="ag-home__state-message">Answer your first card to start growing your garden.</div></div>'
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
    garden_identity_html = (
        '<div class="ag-home__identity"><div class="ag-home__eyebrow">Study garden</div>'
        '<div class="ag-home__focus-name">Your garden</div>'
        '<div class="ag-home__focus-stage">A quiet view of your current garden</div></div>'
    )
    streak_unit = "day" if data.streak_days == 1 else "days"
    growth_help = escape(GROWTH_EXPLANATION, quote=True)
    streak_help = escape(ANKI_STREAK_EXPLANATION, quote=True)
    currency_help = escape(
        GARDEN_CURRENCY_EXPLANATION.replace("Garden Currency", "Garden Coins"),
        quote=True,
    )
    if data.streak_days <= 0:
        streak_next = "Study today to start your streak"
        streak_max = 1
    elif data.next_streak_day is None:
        streak_next = "Maximum streak Growth bonus reached"
        streak_max = max(1, data.streak_days)
    else:
        next_day_unit = "day" if data.next_streak_day == 1 else "days"
        streak_next = (
            f"Next bonus: +{data.next_streak_bonus_percent}% at "
            f"{data.next_streak_day} {next_day_unit}"
        )
        streak_max = max(1, data.next_streak_day)
    streak_progress = int(min(100, max(0, data.streak_days) / streak_max * 100))
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
            active_progress_text = f"Fully grown with {format_integer(data.active_growth_points)} Growth"
            active_progress_max = 1
            active_progress_now = 1
            active_progress_percent = 100
            active_progress_label = f"{active_name} is fully grown"
        else:
            next_stage = format_status_label(data.active_next_stage or "next stage")
            active_progress_text = (
                f"{format_integer(data.active_stage_points)} of {format_integer(data.active_stage_goal)} "
                f"Growth to {next_stage}"
            )
            active_progress_max = max(1, int(data.active_stage_goal))
            active_progress_now = min(active_progress_max, max(0, int(data.active_stage_points)))
            active_progress_percent = int(active_progress_now / active_progress_max * 100)
            active_progress_label = f"{active_name} progress to {next_stage}"
        active_growth_html = (
            f'<div class="ag-home__metric ag-home__metric--plant" tabindex="0" aria-label="{escape(active_progress_label, quote=True)}" '
            f'data-tooltip="{growth_help}"><div class="ag-home__metric-heading"><div>'
            f'<div class="ag-home__metric-label">Nurtured plant</div>'
            f'<div class="ag-home__metric-value ag-home__metric-value--plant" data-testid="home-active-name">{escape(active_name)}</div></div>'
            f'<span class="ag-home__metric-badge">{escape(active_stage)}</span></div>'
            f'<div class="ag-home__metric-support"><span data-testid="home-growth">'
            f'{format_integer(data.active_growth_points)}</span> total Growth</div>'
            f'<div class="ag-home__metric-progress-copy">{escape(active_progress_text)}</div>'
            f'<div class="ag-home__bar-track" role="progressbar" aria-label="{escape(active_progress_label, quote=True)}" '
            f'aria-valuemin="0" aria-valuemax="{active_progress_max}" aria-valuenow="{active_progress_now}">'
            f'<div class="ag-home__bar-fill" data-testid="home-growth-bar" aria-hidden="true" '
            f'style="width:{active_progress_percent}%"></div></div></div>'
        )
    else:
        active_growth_html = (
            f'<div class="ag-home__metric ag-home__metric--plant" tabindex="0" aria-label="No nurtured plant selected" '
            f'data-tooltip="{growth_help}"><div class="ag-home__metric-label">Nurtured plant</div>'
            '<div class="ag-home__metric-value" data-testid="home-active-name">No plant selected</div>'
            '<div class="ag-home__metric-support">Open Garden to choose a plant.</div></div>'
        )

    return f"""{HOME_WIDGET_STYLE}
<div id=\"ag-home-root\" data-state=\"{escape(phase)}\" role=\"region\" aria-label=\"Anki Garden\">
  {partial_banner}
  {stage_up_html}
  <div class=\"ag-home__body\">
    <div class=\"ag-home__scene\" data-testid=\"home-scene\" aria-label=\"Garden preview. Open Garden to interact.\"{background_style}>
      <div class=\"ag-home__art\" data-testid=\"home-plants\">{legacy_occlusion}{''.join(plant_markup['rear'])}{occlusion_markup.get('rear', '')}{''.join(plant_markup['front'])}{occlusion_markup.get('front', '')}</div>
    </div>
    <div class=\"ag-home__details\">
      <div class=\"ag-home__identity-row\">
        {garden_identity_html}
        <button data-testid=\"home-open\" type=\"button\" aria-label=\"Open Garden\" data-tooltip=\"Open the full garden.\"
          onclick=\"if(this.disabled)return;this.disabled=true;this.textContent='Opening…';pycmd('anki-garden:open');setTimeout(()=>{{this.disabled=false;this.textContent='Open Garden';}},1500)\">Open Garden</button>
      </div>
      {f'<p class="ag-home__partial-message" role="status">{escape(data.status_notice)}</p>' if data.status_notice else ''}
      <div class=\"ag-home__metrics\">
        {active_growth_html}
        <div class=\"ag-home__metric ag-home__metric--streak\" tabindex=\"0\" aria-label=\"{escape(streak_accessible_label, quote=True)}\" data-tooltip=\"{streak_help}\"><div class=\"ag-home__metric-label\">Anki streak</div><div class=\"ag-home__metric-value-row\"><div class=\"ag-home__metric-value\" data-testid=\"home-streak\">{format_integer(data.streak_days)} {streak_unit}</div>{streak_badge_html}</div><div class=\"ag-home__metric-support\">{streak_next}</div><div class=\"ag-home__bar-track\" role=\"progressbar\" aria-label=\"Anki streak progress\" aria-valuemin=\"0\" aria-valuemax=\"{streak_max}\" aria-valuenow=\"{min(max(0, data.streak_days), streak_max)}\"><div class=\"ag-home__bar-fill\" data-testid=\"home-streak-bar\" aria-hidden=\"true\" style=\"width:{streak_progress}%\"></div></div></div>
        <div class=\"ag-home__metric ag-home__metric--coins\" tabindex=\"0\" aria-label=\"{format_integer(data.garden_currency)} Garden Coins\" data-tooltip=\"{currency_help}\"><div class=\"ag-home__metric-label\">Garden Coins</div><div class=\"ag-home__metric-value\" data-testid=\"home-currency\">{format_integer(data.garden_currency)}</div><div class=\"ag-home__metric-support\">For Fertilizer and new plants</div></div>
      </div>
    </div>
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
