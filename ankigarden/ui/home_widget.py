from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any

from ..display_telemetry import DISPLAY_TELEMETRY
from .formatters import format_integer, format_percent, format_status_label


@dataclass(frozen=True)
class HomeWidgetData:
    cards_today: int
    health_ratio: float
    growth_earned: int
    growth_cap: int
    streak_days: int
    weather: str
    event: str
    plants_html: str
    stage_transition_message: str = ""


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
  padding: 14px;
  border: 1px solid rgba(75, 117, 90, 0.36);
  border-radius: 8px;
  background: linear-gradient(180deg, #182a25 0%, #10201d 100%);
  color: #e9f5ee;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
.ag-home__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}
.ag-home__title {
  font-size: 15px;
  font-weight: 700;
}
.ag-home__plants [data-testid="home-plants"] {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 8px 0 12px;
}
.ag-home__plant {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 180px;
  padding: 5px 8px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.08);
}
.ag-home__plant-thumb {
  width: 24px;
  height: 24px;
  flex: 0 0 24px;
  object-fit: contain;
}
.ag-home__plant-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ag-home__metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(145px, 1fr));
  gap: 8px;
}
.ag-home__metric {
  padding: 8px;
  border-radius: 8px;
  background: rgba(8, 18, 16, 0.42);
}
.ag-home__bar-track {
  height: 8px;
  margin: 8px 0 10px;
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
.ag-home__event {
  color: #c4d7d0;
}
#ag-home-root button {
  margin-top: 10px;
  padding: 6px 10px;
  border: 1px solid #49725a;
  border-radius: 8px;
  background: #244735;
  color: #eef9f0;
  font-weight: 600;
}
</style>
"""


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
    if not data.event:
        DISPLAY_TELEMETRY.track_fallback(route="home_widget", field="event")
    if not data.weather:
        DISPLAY_TELEMETRY.track_fallback(route="home_widget", field="weather")

    growth_cap = max(1, data.growth_cap)
    growth_pct = int(min(100, (data.growth_earned / growth_cap) * 100))
    partial_banner = ""
    if phase == "partial":
        partial_error = escape(snapshot.error_message or "Some details are temporarily unavailable.")
        partial_banner = f'<div data-testid="home-partial-error">{partial_error}</div>'

    event_html = ""
    if data.event and not data.event.startswith("No Active Event") and data.event != "N/A":
        event_html = f'<div class="ag-home__event"><div data-testid="home-event">Event: {escape(data.event)}</div></div>'

    stage_up_html = ""
    if data.stage_transition_message:
        stage_up_html = (
            '<div class="ag-home__stage-up" data-testid="home-stage-up">'
            f'{escape(data.stage_transition_message)}</div>'
        )

    return f"""{HOME_WIDGET_STYLE}
<div id=\"ag-home-root\" data-state=\"{escape(phase)}\">
  {partial_banner}
  <div class=\"ag-home__header\">
    <div class=\"ag-home__title\">Anki Garden</div>
    <div data-testid=\"home-streak\">{format_integer(data.streak_days)}d streak</div>
  </div>
  <div class=\"ag-home__plants\"><div data-testid=\"home-plants\">{data.plants_html}</div></div>
  {stage_up_html}
  <div class=\"ag-home__metrics\">
    <div class=\"ag-home__metric\"><div data-testid=\"home-cards\">Cards Today: {format_integer(data.cards_today)}</div></div>
    <div class=\"ag-home__metric\"><div data-testid=\"home-health\">Garden Health: {format_percent(data.health_ratio, places=0)}</div></div>
    <div class=\"ag-home__metric\"><div data-testid=\"home-weather\">Weather: {format_status_label(data.weather)}</div></div>
    <div class=\"ag-home__metric\"><div data-testid=\"home-growth\">Growth today: {format_integer(data.growth_earned)}/{format_integer(growth_cap)}</div></div>
  </div>
  <div class=\"ag-home__bar-track\"><div data-testid=\"home-growth-bar\" style=\"width:{growth_pct}%\"></div></div>
  {event_html}
  <button data-testid=\"home-open\" type=\"button\" onclick=\"pycmd('anki-garden:open')\">Open Garden</button>
  <button data-testid=\"home-refresh\" type=\"button\" onclick=\"pycmd('anki-garden:refresh')\">Refresh</button>
</div>
"""


def build_home_widget_success_data(*, state: Any, cards_today: int, health_ratio: float, growth_cap: int, plants_html: str, event: str, stage_transition_message: str = "") -> HomeWidgetData:
    stats = state.daily_stats
    if getattr(state, "selected_weather", None) in (None, ""):
        DISPLAY_TELEMETRY.record_missing_or_invalid_field(
            route="home_widget",
            field="selected_weather",
            reason="missing_or_empty",
            value=getattr(state, "selected_weather", None),
        )
    if event in (None, ""):
        DISPLAY_TELEMETRY.record_missing_or_invalid_field(
            route="home_widget",
            field="event",
            reason="missing_or_empty",
            value=event,
        )
    return HomeWidgetData(
        cards_today=cards_today,
        health_ratio=health_ratio,
        growth_earned=int(stats.growth_earned),
        growth_cap=int(growth_cap),
        streak_days=int(state.streak_days),
        weather=str(state.selected_weather or "N/A"),
        event=event or "N/A",
        plants_html=plants_html,
        stage_transition_message=stage_transition_message,
    )
