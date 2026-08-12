from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any

from ..display_telemetry import DISPLAY_TELEMETRY
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
  width: min(calc(100% - 32px), 520px);
  max-width: 520px;
  margin: 28px auto 18px;
  padding: 0;
  box-sizing: border-box;
  overflow: hidden;
  border: 1px solid rgba(118, 151, 126, 0.38);
  border-radius: 14px;
  background: #0d201d;
  color: #edf5ea;
  box-shadow: 0 5px 16px rgba(2, 11, 10, 0.16);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  container-type: inline-size;
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
  background: rgba(105, 70, 32, 0.34);
  color: #f1d59b;
}
.ag-home__body {
  display:flex;
  flex-direction:column;
  min-width:0;
}
.ag-home__art { position:absolute; inset:0; overflow:hidden; pointer-events:none; }
.ag-home__plant { position:absolute; object-fit:contain; animation:none !important; transition:none !important; filter:contrast(var(--ag-contrast,1)) saturate(var(--ag-saturation,1)) brightness(var(--ag-brightness,1)); }
.ag-home__plant-tint { position:absolute; pointer-events:none; background:linear-gradient(90deg,transparent,rgba(255,230,190,var(--ag-key-alpha,0))),linear-gradient(180deg,transparent 70%,rgba(10,18,16,var(--ag-base-ao,0))),var(--ag-tint,transparent); opacity:var(--ag-tint-alpha,0); -webkit-mask-image:var(--ag-mask); -webkit-mask-position:center; -webkit-mask-repeat:no-repeat; -webkit-mask-size:contain; mask-image:var(--ag-mask); mask-position:center; mask-repeat:no-repeat; mask-size:contain; }
.ag-home__occlusion { position:absolute; inset:0; z-index:3; width:100%; height:100%; object-fit:fill; pointer-events:none; }
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
.ag-home__sr-only { position:absolute !important; width:1px !important; height:1px !important; padding:0 !important; margin:-1px !important; overflow:hidden !important; clip:rect(0,0,0,0) !important; white-space:nowrap !important; border:0 !important; }
.ag-home__scene {
  position: relative;
  width: 100%;
  min-width: 0;
  height:180px;
  flex:none;
  overflow: hidden;
  background:#142b25;
  pointer-events:none;
  user-select:none;
  -webkit-user-select:none;
}
.ag-home__scene-frame {
  position:absolute;
  left:50%;
  top:50%;
  width:100%;
  min-height:100%;
  aspect-ratio:var(--ag-source-aspect, 2.4);
  transform:translate(-50%,-50%);
  overflow:hidden;
  background-position:center;
  background-repeat:no-repeat;
  background-size:100% 100%;
}
.ag-home__scene::after { content:""; position:absolute; inset:0; z-index:90; pointer-events:none; box-shadow:inset 0 -12px 24px rgba(5,14,12,.13); }
.ag-home__details {
  position:relative;
  min-width:0;
  min-height:62px;
  padding:2px 12px;
  background:linear-gradient(155deg,#102a25,#0a1d1a 82%);
}
.ag-home__details::before {
  content:"";
  position:absolute;
  left:0;
  right:0;
  top:-14px;
  height:14px;
  pointer-events:none;
  background:linear-gradient(to bottom,transparent,#102a25);
}
.ag-home__details,.ag-home__details * { box-sizing:border-box; }
.ag-home__identity-row { display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:center; gap:10px; min-width:0; }
.ag-home__identity { min-width:0; }
.ag-home__eyebrow { margin-bottom:1px; color:#d8b875; font-size:10px; font-weight:700; letter-spacing:.09em; line-height:1.05; text-transform:uppercase; }
.ag-home__focus-name {
  display:block;
  overflow:hidden;
  margin:0;
  color:#f3f7f2;
  font-size:18px;
  font-weight:750;
  line-height:1.05;
  text-overflow:ellipsis;
  white-space:nowrap;
}
.ag-home__metrics {
  display:grid;
  grid-template-columns:minmax(0,1.7fr) auto auto;
  align-items:center;
  gap:0;
  min-width:0;
  margin-top:0;
}
.ag-home__metric { min-width:0; color:#edf5ea; font-size:13px; line-height:1.08; }
.ag-home__metric + .ag-home__metric { margin-left:12px; padding-left:12px; border-left:1px solid rgba(153,178,159,.22); }
.ag-home__metric strong { display:block; min-width:0; overflow:hidden; color:#edf5ea; font-size:13px; font-weight:700; text-overflow:ellipsis; white-space:nowrap; }
.ag-home__metric span { display:block; min-width:0; margin-top:1px; overflow:hidden; color:#aebfb4; font-size:11.5px; font-weight:500; font-variant-numeric:tabular-nums; text-overflow:ellipsis; white-space:nowrap; }
.ag-home__metric--streak strong { color:#edf5ea; }
.ag-home__metric--coins strong { color:#f2dda4; }
.ag-home__status-notice { box-sizing:border-box; width:calc(100% + 24px); margin:4px -12px 2px; padding:5px 12px; background:rgba(105,70,32,.24); color:#f1d59b; font-size:11.5px; line-height:1.3; overflow-wrap:anywhere; }
.ag-home__stage-up {
  box-sizing: border-box;
  width: 100%;
  margin: 0;
  padding: 8px 10px;
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
  min-width:112px;
  min-height:34px;
  box-sizing:border-box;
  line-height:1.2;
  flex:none;
  margin: 0;
  padding: 6px 14px;
  border: 1px solid rgba(132,180,146,.72);
  border-radius: 9px;
  background: #286346;
  color: #eef9f0;
  font-size:13px;
  font-weight: 700;
  white-space:nowrap;
  cursor: pointer;
  box-shadow:inset 0 1px 0 rgba(242,250,240,.08),0 3px 9px rgba(1,14,10,.12);
}
#ag-home-root button.ag-home__open::after { content:"→"; margin-left:6px; font-size:12px; line-height:1; }
#ag-home-root button.ag-home__open:disabled::after { content:""; margin:0; }
#ag-home-root button:hover { background: #327653; }
#ag-home-root button:active { background:#183828; transform:translateY(1px); }
#ag-home-root button:disabled { cursor:wait; opacity:.72; }
#ag-home-root button:focus-visible {
  outline: 3px solid #e5f2a6;
  outline-offset: 2px;
}
.ag-home__open { flex:none; min-width:112px !important; min-height:34px !important; padding:6px 14px !important; border-radius:9px !important; font-size:13px !important; }
.nightMode #ag-home-root { background:#0d201d; color:#edf5ea; border-color:rgba(118,157,132,.48); }
@media (max-width: 600px) {
  #ag-home-root { margin-top:18px; }
}
@container (max-width: 469px) {
  .ag-home__scene { height:160px; }
  .ag-home__details { padding-top:3px; padding-bottom:4px; }
  .ag-home__metrics { grid-template-columns:minmax(0,1fr) auto; grid-template-areas:"plant plant" "streak coins"; row-gap:3px; }
  .ag-home__metric--plant { grid-area:plant; display:flex; align-items:baseline; gap:6px; }
  .ag-home__metric--plant strong,.ag-home__metric--plant span { max-width:50%; }
  .ag-home__metric--plant span { margin-top:0; }
  .ag-home__metric--streak { grid-area:streak; }
  .ag-home__metric--coins { grid-area:coins; }
  .ag-home__metric--streak { margin-left:0 !important; padding-left:0 !important; border-left:0 !important; }
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
    source_width = max(1, int(surface_variant.get("width", 1000) or 1000))
    source_height = max(1, int(surface_variant.get("height", 420) or 420))
    source_aspect = source_width / source_height
    preview_crop = surface_variant.get("preview_crop", {})
    if not isinstance(preview_crop, dict):
        preview_crop = {}
    crop_x = max(0.0, min(1.0, float(preview_crop.get("x", 0.0) or 0.0)))
    crop_y = max(0.0, min(1.0, float(preview_crop.get("y", 0.08) or 0.08)))
    crop_width = max(0.01, min(1.0 - crop_x, float(preview_crop.get("width", 1.0) or 1.0)))
    crop_height = max(0.01, min(1.0 - crop_y, float(preview_crop.get("height", 0.84) or 0.84)))
    crop_center_x = crop_x + crop_width / 2
    crop_center_y = crop_y + crop_height / 2
    background_style = (
        f' style="--ag-source-aspect:{source_aspect:.6f};'
        f'--ag-preview-x:{crop_center_x * 100:.2f}%;--ag-preview-y:{crop_center_y * 100:.2f}%'
    )
    background_url = str(surface_variant.get("url") or data.background_url)
    if background_url:
        background_style += f';background-image:linear-gradient(180deg,rgba(5,14,12,.03),rgba(5,14,12,.16)),url(&quot;{escape(background_url, quote=True)}&quot;)'
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
    garden_name_value = str(data.garden_name or "My Garden")
    garden_name = escape(garden_name_value)
    garden_identity_html = (
        '<div class="ag-home__identity"><div class="ag-home__eyebrow" aria-hidden="true">Anki Garden</div>'
        f'<h2 class="ag-home__focus-name" aria-label="{escape(garden_name_value, quote=True)}">{garden_name}</h2></div>'
    )
    streak_progress = _streak_milestone_progress(data.streak_days)
    streak_text = f"{format_integer(data.streak_days)}-day streak"
    coin_unit = "coin" if data.garden_currency == 1 else "coins"
    coin_text = f"{format_integer(data.garden_currency)} {coin_unit}"
    active_name = str(data.active_plant_name or "").strip()
    if active_name:
        active_stage = format_status_label(data.active_plant_stage or "seed")
        if data.active_fully_grown:
            active_progress_text = f"{format_integer(data.active_growth_points)} Growth"
            active_progress_max = 1
            active_progress_now = 1
            active_progress_label = f"{active_name} is fully grown"
            active_accessible_text = (
                f"{active_name}, {active_stage} stage, fully grown at "
                f"{format_integer(data.active_growth_points)} Growth"
            )
        else:
            next_stage = format_status_label(data.active_next_stage or "next stage")
            active_progress_text = (
                f"{format_integer(data.active_stage_points)} / "
                f"{format_integer(data.active_stage_goal)} Growth"
            )
            active_progress_max = max(1, int(data.active_stage_goal))
            active_progress_now = min(active_progress_max, max(0, int(data.active_stage_points)))
            active_progress_label = f"{active_name} progress to {next_stage}"
        active_growth_html = (
            f'<div class="ag-home__metric ag-home__metric--plant nurtured-plant-summary">'
            f'<strong data-testid="home-active-name" aria-label="{escape(active_name, quote=True)}, {escape(active_stage, quote=True)} stage">'
            f'{escape(active_name)} · {escape(active_stage)}</strong>'
            f'<span data-testid="home-growth">{active_progress_text}</span>'
            f'<span class="ag-home__sr-only" role="progressbar" aria-label="{escape(active_progress_label, quote=True)}" '
            f'aria-valuemin="0" aria-valuemax="{active_progress_max}" aria-valuenow="{active_progress_now}"></span></div>'
        )
        if not data.active_fully_grown:
            active_accessible_text = (
                f"{active_name}, {active_stage} stage, {active_progress_now} of "
                f"{active_progress_max} Growth"
            )
    else:
        active_growth_html = (
            '<div class="ag-home__metric ag-home__metric--plant nurtured-plant-summary">'
            '<strong data-testid="home-active-name">No nurtured plant</strong>'
            '<span data-testid="home-growth">Open Garden to choose one</span></div>'
        )
        active_accessible_text = "No nurtured plant selected"

    metrics_accessible_label = escape(
        f"{active_accessible_text}; {streak_text}; "
        f"{format_integer(data.garden_currency)} Garden Coins",
        quote=True,
    )

    return f"""{HOME_WIDGET_STYLE}
<div id=\"ag-home-root\" data-state=\"{escape(phase)}\" role=\"region\" aria-label=\"Anki Garden\">
  {partial_banner}
  {stage_up_html}
  <div class=\"ag-home__body\">
    <div class=\"ag-home__scene\" data-testid=\"home-scene\" aria-hidden=\"true\">
      <div class=\"ag-home__scene-frame\" data-preview-crop=\"{crop_x:.3f},{crop_y:.3f},{crop_width:.3f},{crop_height:.3f}\"{background_style}>
        <div class=\"ag-home__art\" data-testid=\"home-plants\">{legacy_occlusion}{''.join(plant_markup['rear'])}{occlusion_markup.get('rear', '')}{''.join(plant_markup['front'])}{occlusion_markup.get('front', '')}</div>
      </div>
    </div>
    <aside class=\"ag-home__details home-summary-panel\">
      <header class=\"ag-home__identity-row summary-header\">
        {garden_identity_html}
        <button class=\"ag-home__open\" data-testid=\"home-open\" type=\"button\" aria-label=\"Open {escape(garden_name_value, quote=True)}\"
          onclick=\"if(this.disabled)return;this.disabled=true;this.textContent='Opening…';pycmd('anki-garden:open');setTimeout(()=>{{this.disabled=false;this.textContent='Open Garden';}},1500)\">Open Garden</button>
      </header>
      {f'<p class="ag-home__status-notice" role="status">{escape(data.status_notice)}</p>' if data.status_notice else ''}
      <div class=\"ag-home__metrics\" role=\"group\" aria-label=\"{metrics_accessible_label}\">
        {active_growth_html}
        <div class=\"ag-home__metric ag-home__metric--streak streak-metric\"><strong data-testid=\"home-streak\">{streak_text}</strong><span class=\"ag-home__sr-only\" role=\"progressbar\" aria-label=\"Anki streak progress\" aria-valuemin=\"0\" aria-valuemax=\"100\" aria-valuenow=\"{streak_progress}\"></span></div>
        <div class=\"ag-home__metric ag-home__metric--coins coins-metric\"><strong data-testid=\"home-currency\">{coin_text}</strong></div>
      </div>
    </aside>
  </div>
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
