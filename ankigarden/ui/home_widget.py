from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any

from ..display_telemetry import DISPLAY_TELEMETRY
from .formatters import format_integer, format_percent, format_status_label
from .plant_display import plant_layout


@dataclass(frozen=True)
class HomeWidgetData:
    cards_today: int
    health_ratio: float
    growth_earned: int
    growth_cap: int
    streak_days: int
    weather: str
    scene_items: tuple[dict[str, Any], ...] = ()
    stage_transition_message: str = ""
    background_url: str = ""
    focus_plant_name: str = ""
    focus_stage: str = ""
    focus_points_remaining: int = 0
    next_milestone: int | None = None
    total_reviews: int = 0
    milestone_ready: bool = False


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
  margin: 14px 0;
  padding: 0;
  overflow: hidden;
  border: 1px solid rgba(75, 117, 90, 0.36);
  border-radius: 8px;
  background: #10201d;
  color: #e9f5ee;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
.ag-home__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 0;
  padding: 12px 14px;
  background: rgba(8, 20, 17, 0.84);
}
.ag-home__title {
  font-size: 15px;
  font-weight: 700;
}
.ag-home__art { position:relative; width:100%; height:clamp(180px,24vw,240px); overflow:hidden; }
.ag-home__plant { position:absolute; object-fit:contain; transform-origin:50% 100%; }
.ag-home__contact { position:absolute; border-radius:50%; background:rgba(5,12,10,.34); filter:blur(2px); }
.ag-home__plant-fallback { position:absolute; display:flex; align-items:flex-end; justify-content:center; line-height:1; }
.ag-home__focus-marker { position:absolute; display:flex; align-items:center; justify-content:center; width:20px; height:20px; border-radius:50%; background:#eef2a6; color:#173425; font-size:12px; font-weight:800; box-shadow:0 2px 8px rgba(0,0,0,.38); }
.ag-home__metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(145px, 1fr));
  gap: 8px;
}
.ag-home__scene {
  padding: 0;
  background-position: center;
  background-size: cover;
}
.ag-home__details { padding:10px 14px; background:#10201d; }
.ag-home__footer {
  padding: 0 14px 10px;
}
.ag-home__metric {
  padding: 8px;
  border-radius: 8px;
  background: rgba(8, 18, 16, 0.42);
}
.ag-home__bar-track {
  height: 8px;
  margin: 8px 0 0;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.12);
}
#ag-home-root [data-testid="home-growth-bar"] {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #55c77c, #d6f58f);
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
.ag-home__progress-note { margin-top: 8px; color: #cfe4d4; }
.ag-home__plant--focus { filter: drop-shadow(0 0 8px rgba(232, 242, 166, .72)); }
#ag-home-root button {
  margin-top: 6px;
  padding: 6px 10px;
  border: 1px solid #49725a;
  border-radius: 8px;
  background: #244735;
  color: #eef9f0;
  font-weight: 600;
}
@media (max-width: 520px) {
  .ag-home__header { align-items:flex-start; flex-direction:column; gap:4px; }
  .ag-home__metrics { grid-template-columns:1fr; }
  .ag-home__details, .ag-home__footer { padding-left:10px; padding-right:10px; }
}
@media (prefers-reduced-motion: reduce) {
  .ag-home__plant { transition:none !important; animation:none !important; }
}
</style>
"""


def _plant_fallback(stage: Any) -> str:
    return {
        "seed": "🌰",
        "sprout": "🌱",
        "young": "🌿",
        "mature": "🪴",
        "flowering": "🌼",
        "rare": "✨",
    }.get(str(stage or "").lower(), "🌱")


def render_home_widget(snapshot: HomeWidgetSnapshot) -> str:
    DISPLAY_TELEMETRY.track_render("home_widget")
    phase = snapshot.phase
    if phase == "loading":
        return (
            HOME_WIDGET_STYLE
            +
            '<div id="ag-home-root" data-state="loading">'
            '<div data-testid="home-loading">Loading garden…</div>'
            "</div>"
        )
    if phase == "empty":
        return (
            HOME_WIDGET_STYLE
            +
            '<div id="ag-home-root" data-state="empty">'
            '<div data-testid="home-empty">No garden data yet. Start reviewing to grow your first plant.</div>'
            "</div>"
        )
    if phase == "error":
        message = escape(snapshot.error_message or DEFAULT_ERROR_MESSAGE)
        return (
            HOME_WIDGET_STYLE
            +
            '<div id="ag-home-root" data-state="error">'
            f'<div data-testid="home-error">{message}</div>'
            '<button data-testid="home-retry" type="button" onclick="pycmd(\'anki-garden:refresh\')">Retry</button>'
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
            '<div id="ag-home-root" data-state="error">'
            '<div data-testid="home-error">Invalid home widget payload.</div>'
            "</div>"
        )
    if not data.weather:
        DISPLAY_TELEMETRY.track_fallback(route="home_widget", field="weather")

    growth_cap = max(1, data.growth_cap)
    growth_pct = int(min(100, (data.growth_earned / growth_cap) * 100))
    partial_banner = ""
    if phase == "partial":
        partial_error = escape(snapshot.error_message or "Some details are temporarily unavailable.")
        partial_banner = f'<div data-testid="home-partial-error">{partial_error}</div>'

    stage_up_html = ""
    if data.stage_transition_message:
        stage_up_html = (
            '<div class="ag-home__stage-up" data-testid="home-stage-up">'
            f'{escape(data.stage_transition_message)}</div>'
        )

    background_style = ""
    if data.background_url:
        background_style = f' style="background-image:linear-gradient(180deg,rgba(5,14,12,.08),rgba(5,14,12,.58)),url(&quot;{escape(data.background_url, quote=True)}&quot;)"'

    background_placement = data.scene_items[0].get("background_placement", {}) if data.scene_items else {}
    zone = background_placement.get("planting_zone", {}) if isinstance(background_placement, dict) else {}
    layouts = plant_layout(1200, 900, data.scene_items, zone if isinstance(zone, dict) else None)
    by_slot = {int(item.get("slot_index", index)): item for index, item in enumerate(data.scene_items)}
    plant_markup = []
    for layout in layouts:
        item = by_slot.get(layout.slot_index, {})
        src = escape(str(item.get("url", "")), quote=True)
        base_type = str(item.get("placement", {}).get("base_type", "legacy")) if isinstance(item.get("placement"), dict) else "legacy"
        depth_index = max(1, int(round(layout.depth * 10)))
        shadow = f'<span class="ag-home__contact" aria-hidden="true" style="left:{layout.footprint.x/12:.3f}%;top:{layout.footprint.y/9:.3f}%;width:{layout.footprint.width/12:.3f}%;height:{layout.footprint.height/9:.3f}%;z-index:{depth_index}"></span>'
        alt = escape(str(item.get("name", "Plant")), quote=True)
        focus_class = " ag-home__plant--focus" if item.get("is_focus") else ""
        common = f'left:{layout.draw.x/12:.3f}%;top:{layout.draw.y/9:.3f}%;width:{layout.draw.width/12:.3f}%;height:{layout.draw.height/9:.3f}%;z-index:{depth_index + 1}'
        if src:
            plant = f'<img class="ag-home__plant{focus_class}" data-slot-index="{layout.slot_index}" src="{src}" alt="{alt}" style="{common}" data-base-type="{escape(base_type, quote=True)}">'
        else:
            fallback = _plant_fallback(item.get("stage"))
            font_size = max(24, min(58, int(layout.visible.height / 5)))
            plant = f'<span class="ag-home__plant-fallback{focus_class}" data-slot-index="{layout.slot_index}" role="img" aria-label="{alt}" style="{common};font-size:{font_size}px">{fallback}</span>'
        marker = ""
        if item.get("is_focus"):
            marker_x = (layout.visible.right / 12) - 1.667
            marker_y = (layout.visible.y / 9) + 0.5
            marker = f'<span class="ag-home__focus-marker" aria-label="Focus plant" title="Focus plant" style="left:{marker_x:.3f}%;top:{marker_y:.3f}%;z-index:{depth_index + 2}">★</span>'
        plant_markup.append(shadow + plant + marker)

    focus_html = ""
    if data.focus_plant_name:
        detail = f" • {escape(format_status_label(data.focus_stage))}"
        if data.focus_points_remaining > 0:
            detail += f" • {format_integer(data.focus_points_remaining)} GP to next stage"
        focus_html = (
            '<div class="ag-home__progress-note" data-testid="home-focus">'
            f'Nurturing {escape(data.focus_plant_name)}{detail}</div>'
        )
    milestone_html = ""
    if data.milestone_ready:
        milestone_html = (
            '<div class="ag-home__stage-up" data-testid="home-milestone">'
            'A new garden plant is ready to choose. Open Garden to claim it.</div>'
        )
    elif data.next_milestone is not None:
        remaining = max(0, data.next_milestone - data.total_reviews)
        milestone_html = (
            '<div class="ag-home__progress-note" data-testid="home-milestone-progress">'
            f'{format_integer(remaining)} reviews until your next plant choice.</div>'
        )

    return f"""{HOME_WIDGET_STYLE}
<div id=\"ag-home-root\" data-state=\"{escape(phase)}\">
  {partial_banner}
  <div class=\"ag-home__header\">
    <div class=\"ag-home__title\">Anki Garden</div>
    <div data-testid=\"home-streak\">{format_integer(data.streak_days)}d streak</div>
  </div>
  <div class=\"ag-home__scene\" data-testid=\"home-scene\"{background_style}>
    <div class=\"ag-home__art\" data-testid=\"home-plants\">{''.join(plant_markup)}</div>
  </div>
  <div class=\"ag-home__details\">
    {stage_up_html}
    {milestone_html}
    <div class=\"ag-home__metrics\">
      <div class=\"ag-home__metric\"><div data-testid=\"home-cards\">Cards Today: {format_integer(data.cards_today)}</div></div>
      <div class=\"ag-home__metric\"><div data-testid=\"home-health\">Garden Health: {format_percent(data.health_ratio, places=0)}</div></div>
      <div class=\"ag-home__metric\"><div data-testid=\"home-weather\">Weather: {format_status_label(data.weather)}</div></div>
      <div class=\"ag-home__metric\"><div data-testid=\"home-growth\">Growth today: {format_integer(data.growth_earned)}/{format_integer(growth_cap)}</div></div>
    </div>
    <div class=\"ag-home__bar-track\"><div data-testid=\"home-growth-bar\" style=\"width:{growth_pct}%\"></div></div>
    {focus_html}
  </div>
  <div class=\"ag-home__footer\">
    <button data-testid=\"home-open\" type=\"button\" onclick=\"pycmd('anki-garden:open')\">Open Garden</button>
  </div>
</div>
"""


def build_home_widget_success_data(*, state: Any, cards_today: int, health_ratio: float, growth_cap: int, scene_items: list[dict[str, Any]], stage_transition_message: str = "", background_url: str = "", focus_plant: Any = None, focus_display: Any = None, next_milestone: int | None = None, milestone_ready: bool = False) -> HomeWidgetData:
    stats = state.daily_stats
    if getattr(state, "selected_weather", None) in (None, ""):
        DISPLAY_TELEMETRY.record_missing_or_invalid_field(
            route="home_widget",
            field="selected_weather",
            reason="missing_or_empty",
            value=getattr(state, "selected_weather", None),
        )
    return HomeWidgetData(
        cards_today=cards_today,
        health_ratio=health_ratio,
        growth_earned=int(stats.growth_earned),
        growth_cap=int(growth_cap),
        streak_days=int(state.streak_days),
        weather=str(state.selected_weather or "N/A"),
        scene_items=tuple(scene_items),
        stage_transition_message=stage_transition_message,
        background_url=background_url,
        focus_plant_name=str(getattr(focus_plant, "name", "") or ""),
        focus_stage=str(getattr(focus_display, "stage", "") or ""),
        focus_points_remaining=max(0, int(getattr(focus_display, "points_remaining", 0) or 0)),
        next_milestone=next_milestone,
        total_reviews=max(0, int(getattr(state, "total_reviews", 0) or 0)),
        milestone_ready=milestone_ready,
    )
