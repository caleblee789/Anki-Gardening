from __future__ import annotations

from dataclasses import dataclass
from html import escape
from math import isfinite
from typing import Any

from ..display_telemetry import DISPLAY_TELEMETRY
from ..models.state import STREAK_BONUS_TIERS
from ..reward_presentation import achievement_presentations
from .copy import (
    CHOOSE_STARTER_ACTION,
    FALLBACK_GARDEN_NAME,
    HOME_ACTIVE_ACTION,
    HOME_NO_STARTER_ACCESSIBLE,
    HOME_NO_STARTER_BODY,
    HOME_NO_STARTER_TITLE,
)
from .formatters import format_growth_fifths, format_integer, format_status_label
from .state import (
    GardenPreviewSnapshot,
    garden_preview_from_values,
    preview_with_phase,
)
from .plant_display import (
    compact_plant_layout,
    growth_display,
    nurtured_marker_fallback_rect,
    plant_layout,
    planter_draw_rect,
    Rect,
    SceneGeometryLayout,
    scene_surface_variant,
)


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
    weather_url: str = ""
    nurtured_marker_url: str = ""
    nurtured_marker_spout_right_url: str = ""
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
    # A planted starter is not an active/nurtured plant until the persisted
    # active_plant_id points to it. Keep that identity in a separate contract.
    planted_starter_name: str = ""
    planted_starter_stage: str = ""
    starter_planted_not_nurtured: bool = False
    garden_name: str = FALLBACK_GARDEN_NAME
    # Direct callers from older surfaces omit this derived field. Treat those
    # snapshots as established Gardens; the state builder sets it explicitly.
    starter_selected: bool = True
    preview_snapshot: GardenPreviewSnapshot | None = None
    study_growth_generated: int = 0
    nurtured_growth_today: int = 0
    passive_growth_fifths_today: int = 0
    passive_growth_credited_today: int = 0
    charge_growth_today: int = 0
    direct_reward_growth_today: int = 0
    growth_accounting_stale: bool = False
    nearest_achievement_name: str = ""
    nearest_achievement_progress: str = ""
    nearest_achievement_reward: str = ""


@dataclass(frozen=True)
class HomeWidgetSnapshot:
    request_id: int
    phase: str
    data: HomeWidgetData | None = None
    error_message: str | None = None
    enable_animations: bool = True
    reduced_motion: bool = False

    @property
    def motion_enabled(self) -> bool:
        return bool(self.enable_animations and not self.reduced_motion)


class HomeWidgetStateController:
    """Tracks request lifecycles and protects the UI against stale responses."""

    def __init__(self) -> None:
        self._next_request_id = 0
        self._last_valid_data: HomeWidgetData | None = None
        self.snapshot = HomeWidgetSnapshot(request_id=0, phase="empty")

    def set_motion_preferences(
        self,
        *,
        enable_animations: bool,
        reduced_motion: bool,
    ) -> None:
        """Project the add-on motion settings without persisting WebView state."""

        current = self.snapshot
        self.snapshot = HomeWidgetSnapshot(
            request_id=current.request_id,
            phase=current.phase,
            data=current.data,
            error_message=current.error_message,
            enable_animations=bool(enable_animations),
            reduced_motion=bool(reduced_motion),
        )

    def _snapshot(
        self,
        *,
        request_id: int,
        phase: str,
        data: HomeWidgetData | None = None,
        error_message: str | None = None,
    ) -> HomeWidgetSnapshot:
        return HomeWidgetSnapshot(
            request_id=request_id,
            phase=phase,
            data=data,
            error_message=error_message,
            enable_animations=self.snapshot.enable_animations,
            reduced_motion=self.snapshot.reduced_motion,
        )

    def begin_request(self) -> int:
        self._next_request_id += 1
        req_id = self._next_request_id
        self.snapshot = self._snapshot(
            request_id=req_id,
            phase="stale" if self._last_valid_data is not None else "loading",
            data=self._last_valid_data,
            error_message=(
                "Showing the last available garden preview. Updating..."
                if self._last_valid_data is not None else None
            ),
        )
        return req_id

    def resolve_success(self, request_id: int, data: HomeWidgetData) -> bool:
        if request_id != self.snapshot.request_id:
            return False
        self.snapshot = self._snapshot(
            request_id=request_id,
            phase="success",
            data=data,
        )
        self._last_valid_data = data
        return True

    def resolve_partial(self, request_id: int, data: HomeWidgetData, error_message: str) -> bool:
        if request_id != self.snapshot.request_id:
            return False
        self.snapshot = self._snapshot(
            request_id=request_id,
            phase="partial",
            data=data,
            error_message=error_message,
        )
        return True

    def resolve_error(self, request_id: int, error_message: str) -> bool:
        if request_id != self.snapshot.request_id:
            return False
        retained = self.snapshot.data or self._last_valid_data
        self.snapshot = self._snapshot(
            request_id=request_id,
            phase="stale" if retained is not None else "error",
            data=retained,
            error_message=error_message,
        )
        return True

    def resolve_stale(
        self,
        request_id: int,
        error_message: str = "Showing the last available garden preview. Updating...",
    ) -> bool:
        if request_id != self.snapshot.request_id or self._last_valid_data is None:
            return False
        self.snapshot = self._snapshot(
            request_id=request_id,
            phase="stale",
            data=self._last_valid_data,
            error_message=error_message,
        )
        return True


DEFAULT_ERROR_MESSAGE = "Garden progress could not be loaded. Try again in a moment."

HOME_COMPACT_CONTAINER_MAX_WIDTH = 469
HOME_NARROW_CONTAINER_MAX_WIDTH = 420
HOME_LAYOUT_STANDARD = "standard"
HOME_LAYOUT_COMPACT = "compact"
HOME_LAYOUT_NARROW = "narrow"


def home_container_layout(width: int | float) -> str:
    """Return the CSS-equivalent Home layout range for one inline size."""

    try:
        available = float(width)
    except (TypeError, ValueError) as exc:
        raise ValueError("Home container width must be finite") from exc
    if not isfinite(available):
        raise ValueError("Home container width must be finite")
    available = max(0.0, available)
    if available <= HOME_NARROW_CONTAINER_MAX_WIDTH:
        return HOME_LAYOUT_NARROW
    if available <= HOME_COMPACT_CONTAINER_MAX_WIDTH:
        return HOME_LAYOUT_COMPACT
    return HOME_LAYOUT_STANDARD


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
.ag-home__loading-track {
  width:100%;
  height:4px;
  margin-top:14px;
  overflow:hidden;
  border-radius:4px;
  background:#183a30;
}
.ag-home__loading-track::after {
  content:"";
  display:block;
  width:42%;
  height:100%;
  border-radius:4px;
  background:#5cc58b;
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
.ag-home__scenery-layer,.ag-home__weather-layer { position:absolute; inset:0; width:100%; height:100%; object-fit:fill; pointer-events:none; }
.ag-home__scenery-layer { z-index:2; }
.ag-home__weather-layer { z-index:5; }
.ag-home__marker-layer { position:absolute; z-index:84; inset:0; overflow:hidden; pointer-events:none; }
.ag-home__plant { position:absolute; object-fit:contain; animation:none !important; transition:none !important; filter:contrast(var(--ag-contrast,1)) saturate(var(--ag-saturation,1)) brightness(var(--ag-brightness,1)); }
.ag-home__nurtured-marker { position:absolute; object-fit:contain; pointer-events:none; }
.ag-home__nurtured-marker-fallback { position:absolute; display:none; box-sizing:border-box; border:1px solid #4c3e18; border-radius:50%; background:#dfbd57; pointer-events:none; }
.ag-home__nurtured-marker-fallback::after { content:""; position:absolute; left:29%; top:28%; width:42%; height:34%; border-radius:70% 25% 70% 25%; background:#fff; transform:rotate(-12deg); }
.ag-home__planter { position:absolute; object-fit:contain; pointer-events:none; }
.ag-home__planter-fallback { position:absolute; display:none; pointer-events:none; }
.ag-home__planter-fallback--base::before { content:""; position:absolute; left:10%; top:38%; width:80%; height:42%; border-radius:12% 12% 44% 44%; background:linear-gradient(180deg,rgba(132,124,110,.92),rgba(86,82,75,.96)); }
.ag-home__planter-fallback--base::after { content:""; position:absolute; left:10%; top:31%; width:80%; height:26%; border-radius:50%; background:radial-gradient(ellipse,rgba(77,52,36,.98),rgba(104,79,57,.94) 58%,rgba(166,151,124,.92) 62%,rgba(94,88,78,.96) 72%); }
.ag-home__planter-fallback--foreground::after { content:""; position:absolute; left:10%; top:31%; width:80%; height:26%; box-sizing:border-box; border-radius:50%; border-top:2px solid rgba(201,185,153,.86); }
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
.ag-home__fallback-label { max-width:92%; overflow:hidden; padding:4px 6px; border-radius:5px; background:rgba(8,27,23,.84); color:#dce9dd; font-size:12px; line-height:1.2; text-align:center; }
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
.ag-home--no-starter .ag-home__scene { height:150px; }
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
  background-color:#17332d;
  opacity:var(--ag-scene-opacity,1);
  transition:opacity 140ms ease;
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
.ag-home__garden-context { display:block; margin-top:2px; color:#aebfb4; font-size:12px; line-height:1.2; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.ag-home__eyebrow { margin-bottom:1px; color:#d8b875; font-size:12px; font-weight:700; letter-spacing:.09em; line-height:1.2; text-transform:uppercase; }
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
.ag-home__metric span { display:block; min-width:0; margin-top:1px; overflow:hidden; color:#aebfb4; font-size:12px; font-weight:500; font-variant-numeric:tabular-nums; text-overflow:ellipsis; white-space:nowrap; }
.ag-home__metric--streak strong { color:#edf5ea; }
.ag-home__metric--coins strong { color:#f2dda4; }
.ag-home__status-notice { box-sizing:border-box; width:calc(100% + 24px); margin:4px -12px 2px; padding:5px 12px; background:rgba(105,70,32,.24); color:#f1d59b; font-size:12px; line-height:1.3; overflow-wrap:anywhere; }
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
  min-width:108px;
  min-height:36px;
  box-sizing:border-box;
  line-height:1.2;
  flex:none;
  margin: 0;
  padding: 0 14px;
  border: 1px solid #5b9a70;
  border-radius: 8px;
  background: #2d7653;
  color: #f7fff8;
  font-size:13px;
  font-weight: 700;
  white-space:nowrap;
  cursor: pointer;
  box-shadow:inset 0 1px 0 rgba(242,250,240,.08),0 3px 9px rgba(1,14,10,.12);
}
#ag-home-root button.ag-home__open::after { content:""; display:none; }
#ag-home-root button.ag-home__open:disabled::after { content:""; margin:0; }
#ag-home-root button:hover { background: #357f5b; }
#ag-home-root button:active { background:#225e42; transform:translateY(1px); }
#ag-home-root button:disabled { cursor:wait; background:#172721; border-color:#30443b; color:#83968b; }
#ag-home-root button:focus-visible {
  outline: 3px solid #e8f59e;
  outline-offset: 2px;
}
.ag-home__open { flex:none; min-width:108px !important; min-height:36px !important; padding:0 14px !important; border-radius:8px !important; font-size:13px !important; }
.ag-home__state-actions { display:flex; flex-wrap:wrap; gap:8px; margin-top:14px; }
#ag-home-root button.ag-home__secondary {
  border-color:#4F806E;
  background:#123228;
  color:#F4F7F5;
  box-shadow:none;
}
#ag-home-root button.ag-home__secondary:hover { background:#173B30; }
#ag-home-root button.ag-home__secondary:active { background:#0C261F; }
.nightMode #ag-home-root { background:#0d201d; color:#edf5ea; border-color:rgba(118,157,132,.48); }

/* Release redesign: one artwork-first, full-bleed preview with a bottom scrim. */
#ag-home-root {
  position:relative;
  width:min(calc(100% - 32px), 720px);
  max-width:720px;
  height:180px;
  margin:24px auto 18px;
  border-color:rgba(128,178,155,.28);
  border-radius:12px;
  background:#071A15;
  box-shadow:0 10px 28px rgba(0,0,0,.24);
  cursor:pointer;
  transition:transform 120ms ease,border-color 120ms ease,box-shadow 120ms ease;
}
#ag-home-root:hover {
  transform:translateY(-2px);
  border-color:#4F806E;
  box-shadow:0 14px 34px rgba(0,0,0,.3);
}
#ag-home-root:focus-visible {
  outline:3px solid #82E2AC;
  outline-offset:3px;
}
.ag-home__state { min-height:180px; padding:24px; }
.ag-home__body { position:relative; height:100%; }
.ag-home__scene,.ag-home--no-starter .ag-home__scene {
  position:absolute;
  inset:0;
  height:100%;
}
.ag-home__scene-frame {
  top:var(--ag-preview-y,50%);
  background-position:var(--ag-preview-x,50%) var(--ag-preview-y,50%);
}
.ag-home__scene::after {
  z-index:88;
  background:linear-gradient(to bottom,rgba(4,14,11,.02) 24%,rgba(4,14,11,.24) 58%,rgba(4,14,11,.92) 100%);
  box-shadow:inset 0 0 0 1px rgba(255,255,255,.02);
}
.ag-home__details {
  position:absolute;
  z-index:100;
  left:0;
  right:0;
  bottom:0;
  min-height:0;
  padding:30px 16px 14px;
  background:linear-gradient(to bottom,transparent,rgba(5,20,16,.9) 48%,rgba(5,20,16,.97));
}
.ag-home__details::before { display:none; }
.ag-home__identity-row { gap:16px; align-items:end; }
.ag-home__eyebrow { margin-bottom:3px; color:#E7C96A; font-size:12px; }
.ag-home__focus-name { font-size:20px; line-height:1.15; }
.ag-home__support {
  display:block;
  max-width:520px;
  margin-top:3px;
  overflow:hidden;
  color:#D3DDD8;
  font-size:13px;
  font-weight:400;
  line-height:1.35;
  text-overflow:ellipsis;
  white-space:nowrap;
}
.ag-home__reward-progress {
  display:flex;
  flex-direction:column;
  min-width:0;
  gap:2px;
  margin-top:5px;
  color:#D3DDD8;
  font-size:12px;
  line-height:1.25;
}
.ag-home__reward-progress > span { min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.ag-home__reward-progress strong { color:#F0D57C; font-weight:700; }
.ag-home__metrics,.ag-home__garden-context,.ag-home__status-notice { display:none; }
.ag-home__partial-message,.ag-home__stage-up {
  position:absolute;
  z-index:110;
  top:10px;
  left:12px;
  right:12px;
  width:auto;
  padding:7px 10px;
  border-radius:8px;
  background:rgba(62,48,22,.88);
  font-size:12.5px;
  text-align:left;
}
.ag-home__stage-up + .ag-home__partial-message { top:48px; }
#ag-home-root button,.ag-home__open {
  min-height:44px !important;
  min-width:112px !important;
  padding:0 14px !important;
  border-color:#5CC58B;
  background:#5CC58B;
  color:#062017;
  font-size:14px !important;
  font-weight:650;
  box-shadow:0 4px 14px rgba(0,0,0,.22);
}
#ag-home-root button:hover { background:#71D39C; }
#ag-home-root button:active { background:#49AA75; }
#ag-home-root button.ag-home__open::after { content:""; display:none; }
#ag-home-root[data-motion="reduced"] { transition:none; }
#ag-home-root[data-motion="reduced"]:hover { transform:none; }
#ag-home-root[data-motion="reduced"] button:active { transform:none; }
#ag-home-root[data-motion="reduced"] .ag-home__scene-frame { transition:none; }
@media (prefers-reduced-motion: reduce) {
  #ag-home-root { transition:none; }
  #ag-home-root:hover { transform:none; }
  #ag-home-root button:active { transform:none; }
  .ag-home__scene-frame { transition:none; }
}
@container (max-width: 469px) {
  .ag-home__body { min-height:168px; }
  .ag-home__details { padding:26px 14px 12px; }
  .ag-home__support { max-width:100%; }
  .ag-home--no-starter .ag-home__support {
    overflow:visible;
    text-overflow:clip;
    white-space:normal;
  }
}
@container (max-width:420px) {
  .ag-home__details { padding:24px 12px 12px; }
  .ag-home__identity-row { gap:12px; }
  .ag-home__support { max-width:100%; font-size:12.5px; }
  .ag-home__focus-name { font-size:18px; }
}
#ag-home-root[data-summary-clearance="center-left-marker"] .ag-home__identity-row {
  grid-template-columns:minmax(0,32%) auto;
  justify-content:space-between;
}
#ag-home-root[data-summary-clearance="center-left-marker"] .ag-home__identity {
  text-align:left;
}
#ag-home-root[data-summary-clearance="center-left-marker"] .ag-home__support {
  display:-webkit-box;
  white-space:normal;
  -webkit-box-orient:vertical;
  -webkit-line-clamp:2;
}
</style>
"""


def _plant_fallback(_stage: Any) -> str:
    """Return a quiet code-native silhouette; system emoji are never substituted."""
    return '<span class="ag-home__fallback-silhouette" aria-hidden="true"></span>'


def render_home_widget(snapshot: HomeWidgetSnapshot) -> str:
    DISPLAY_TELEMETRY.track_render("home_widget")
    phase = snapshot.phase
    motion_mode = "standard" if snapshot.motion_enabled else "reduced"
    motion_attribute = f' data-motion="{motion_mode}"'
    if phase == "loading":
        return (
            HOME_WIDGET_STYLE
            +
            f'<div id="ag-home-root" data-state="loading"{motion_attribute} role="region" '
            'aria-label="Anki Garden" aria-busy="true">'
            '<div class="ag-home__state" data-testid="home-loading">'
            '<div class="ag-home__state-title">Anki Garden</div>'
            '<div class="ag-home__state-message" role="status" aria-live="polite">'
            'Loading garden preview…</div>'
            '<div class="ag-home__loading-track" role="progressbar" aria-label="Loading garden preview"></div>'
            '<div class="ag-home__state-actions">'
            '<button data-testid="home-open" class="ag-home__open" type="button" '
            'aria-label="Open Garden while the preview loads" '
            'onclick="pycmd(\'anki-garden:open\')">Open Garden</button>'
            '<button data-testid="home-retry" class="ag-home__secondary" type="button" '
            'aria-label="Retry garden preview" '
            'onclick="pycmd(\'anki-garden:refresh\')">Retry preview</button>'
            '</div></div>'
            "</div>"
        )
    if phase == "empty":
        return (
            HOME_WIDGET_STYLE
            +
            f'<div id="ag-home-root" data-state="empty"{motion_attribute} role="region" aria-label="Anki Garden">'
            '<div class="ag-home__state" data-testid="home-empty" role="status">'
            f'<div class="ag-home__state-title">{HOME_NO_STARTER_TITLE}</div>'
            f'<div class="ag-home__state-message">{HOME_NO_STARTER_BODY}</div>'
            f'<span class="ag-home__sr-only">{HOME_NO_STARTER_ACCESSIBLE}</span>'
            f'<button data-testid="home-open" type="button" aria-label="{CHOOSE_STARTER_ACTION}" '
            f'onclick="pycmd(\'anki-garden:choose-starter\')">{CHOOSE_STARTER_ACTION}</button></div>'
            "</div>"
        )
    if phase == "error":
        detail = escape(snapshot.error_message or DEFAULT_ERROR_MESSAGE)
        return (
            HOME_WIDGET_STYLE
            +
            f'<div id="ag-home-root" data-state="error"{motion_attribute} role="region" aria-label="Anki Garden">'
            '<div class="ag-home__state">'
            '<div class="ag-home__state-title">Garden preview unavailable</div>'
            '<div class="ag-home__state-message" data-testid="home-error" role="alert">'
            'The preview could not be generated, but your garden is still available. '
            f'<span class="ag-home__sr-only">{detail}</span></div>'
            '<div class="ag-home__state-actions">'
            '<button data-testid="home-open" class="ag-home__open" type="button" '
            'aria-label="Open Garden" onclick="pycmd(\'anki-garden:open\')">Open Garden</button>'
            '<button data-testid="home-retry" class="ag-home__secondary" type="button" '
            'aria-label="Retry garden preview" '
            'onclick="pycmd(\'anki-garden:refresh\')">Retry preview</button>'
            '</div></div>'
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
            f'<div id="ag-home-root" data-state="error"{motion_attribute} role="region" aria-label="Anki Garden">'
            '<div class="ag-home__state">'
            '<div class="ag-home__state-title">Garden preview unavailable</div>'
            '<div class="ag-home__state-message" data-testid="home-error" role="alert">'
            'The preview could not be generated, but your garden is still available.</div>'
            '<div class="ag-home__state-actions">'
            '<button data-testid="home-open" class="ag-home__open" type="button" '
            'aria-label="Open Garden" onclick="pycmd(\'anki-garden:open\')">Open Garden</button>'
            '<button data-testid="home-retry" class="ag-home__secondary" type="button" '
            'aria-label="Retry garden preview" '
            'onclick="pycmd(\'anki-garden:refresh\')">Retry preview</button>'
            '</div></div>'
            "</div>"
        )
    if not data.weather:
        DISPLAY_TELEMETRY.track_fallback(route="home_widget", field="weather")

    source_preview = data.preview_snapshot
    if source_preview is None:
        source_preview = garden_preview_from_values(
            consumer="home",
            garden_name=data.garden_name,
            active_plant_name=data.active_plant_name,
            active_stage=data.active_plant_stage,
            active_growth_points=data.active_growth_points,
            active_stage_points=data.active_stage_points,
            active_stage_goal=data.active_stage_goal,
            active_fully_grown=data.active_fully_grown,
            starter_selected=data.starter_selected,
            planted_starter_name=data.planted_starter_name,
            planted_starter_stage=data.planted_starter_stage,
            selected_weather=data.weather,
            scene_items=data.scene_items,
            unlocked_slots=data.unlocked_slots,
        )
    requested_preview_phase = (
        phase if phase in {"stale", "disabled"} else source_preview.phase
    )
    preview = preview_with_phase(
        source_preview,
        requested_preview_phase,
        motion_enabled=snapshot.motion_enabled,
        status_text=(snapshot.error_message or source_preview.status_text),
    )

    partial_banner = ""
    if phase == "partial":
        partial_error = escape(snapshot.error_message or "Some details are temporarily unavailable.")
        partial_banner = (
            '<div class="ag-home__partial-message" data-testid="home-partial-error" '
            f'role="status" aria-live="polite">{partial_error}</div>'
        )
    elif preview.status_text:
        partial_banner = (
            '<div class="ag-home__partial-message" data-testid="home-preview-status" '
            f'role="status" aria-live="polite">{escape(preview.status_text)}</div>'
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
        f'--ag-preview-x:{crop_center_x * 100:.2f}%;--ag-preview-y:{crop_center_y * 100:.2f}%;'
        f'--ag-scene-opacity:{preview.scene_opacity:.3f}'
    )
    background_url = str(surface_variant.get("url") or data.background_url)
    fallback_background = (
        "linear-gradient(180deg,#244954 0%,#31594d 55%,#294a35 55%,#17332d 100%)"
    )
    if background_url:
        background_style += (
            ";background-image:"
            "linear-gradient(180deg,rgba(5,14,12,.03),rgba(5,14,12,.16)),"
            f"url(&quot;{escape(background_url, quote=True)}&quot;),"
            f"{fallback_background}"
        )
    else:
        background_style += f";background-image:{fallback_background}"
    background_style += '"'
    scenery_identity = (
        ' data-testid="home-scenery-layer"'
        f' data-scenery="{escape(preview.selected_scenery, quote=True)}"'
        if background_url else
        ""
    )
    layouts = compact_plant_layout(
        1000,
        420,
        data.scene_items,
        background_placement if isinstance(background_placement, dict) else None,
    )
    by_slot = {int(item.get("slot_index", index)): item for index, item in enumerate(data.scene_items)}
    surface_profile = (
        background_placement.get("surface_profile", {})
        if isinstance(background_placement, dict)
        else {}
    )
    planter_family = (
        surface_profile.get("planter_family", {})
        if isinstance(surface_profile, dict)
        else {}
    )
    planter_variants = (
        planter_family.get("variants", {})
        if isinstance(planter_family, dict)
        else {}
    )
    planter_enabled = (
        isinstance(planter_variants, dict)
        and set(planter_variants) >= {"back", "middle", "front"}
        and str(planter_family.get("background_contract", "")) == "bedless_v1"
    )
    slot_layouts = plant_layout(
        1000,
        420,
        [
            {"slot_index": slot, "occupied": False}
            for slot in range(6)
        ],
        background_placement,
        surface_context="home",
        composition_count=6,
        protected_status=False,
        reserve_move_controls=False,
    )
    planter_boxes = {
        slot_layout.slot_index: planter_draw_rect(slot_layout, planter_family)
        for slot_layout in slot_layouts
    }
    occupied_layouts = {layout.slot_index: layout for layout in layouts}
    home_geometry = SceneGeometryLayout.from_placements(
        1000,
        420,
        (
            occupied_layouts.get(layout.slot_index, layout)
            for layout in slot_layouts
        ),
        planter_family=planter_family,
    )
    marker_obstacles = [
        layout.visible.expanded(4.0, 4.0)
        for layout in layouts
    ]
    # The scenic Home card paints its identity and action rail over the bottom
    # of the scene. Keep the marker clear of both visible text lanes.
    marker_protected_regions = (
        Rect(0.0, 300.0, 700.0, 120.0),
        Rect(760.0, 300.0, 240.0, 120.0),
    )
    plant_markup: dict[str, list[str]] = {
        "far": [],
        "middle": [],
        "near": [],
    }
    marker_overlays: dict[str, list[str]] = {
        "far": [],
        "middle": [],
        "near": [],
    }
    summary_clearance = "none"
    theme = str(data.scene_items[0].get("background_theme", "verdant_twilight")) if data.scene_items else "verdant_twilight"
    band_counts = {"far": 0, "middle": 0, "near": 0}
    plant_z_base = {"far": 10, "middle": 40, "near": 70}
    for layout in layouts:
        item = by_slot.get(layout.slot_index, {})
        src = escape(str(item.get("url", "")), quote=True)
        base_type = str(item.get("placement", {}).get("base_type", "legacy")) if isinstance(item.get("placement"), dict) else "legacy"
        depth_band = layout.depth_band if layout.depth_band in plant_markup else "near"
        depth_index = plant_z_base[depth_band] + band_counts[depth_band] * 3
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
        fallback = _plant_fallback(item.get("stage"))
        stage_label = escape(format_status_label(item.get("stage") or "plant"))
        fallback_markup = (
            f'<span class="ag-home__plant-fallback" data-slot-index="{layout.slot_index}" role="img" '
            f'aria-label="{alt}, {stage_label}" style="{common}">{fallback}'
            f'<span class="ag-home__fallback-label"><span>{alt}</span>'
            f'<span class="ag-home__fallback-stage">{stage_label}</span></span></span>'
        )
        if src:
            load_failure = (
                "this.onerror=null;this.style.display='none';"
                "var f=this.nextElementSibling;if(f){f.style.display='flex';"
                "f.setAttribute('aria-hidden','false');}"
                "var t=f?f.nextElementSibling:null;if(t){t.style.display='none';}"
            )
            hidden_fallback = fallback_markup.replace(
                f'style="{common}"',
                f'aria-hidden="true" style="{common};display:none"',
                1,
            )
            plant = (
                f'<img class="ag-home__plant" data-slot-index="{layout.slot_index}" '
                f'src="{src}" alt="{alt}" style="{common}" '
                f'data-base-type="{escape(base_type, quote=True)}" '
                f'onerror="{load_failure}">' + hidden_fallback
            )
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
            plant = fallback_markup
            tint = ""
        marker_markup = ""
        if bool(item.get("is_active")):
            placement_protected_regions = marker_protected_regions
            center_left_summary_region: Rect | None = None
            marker_needs_center_left_clearance = (
                layout.depth_band == "near"
                and float(layout.ground_anchor[0]) < 500.0
            )
            if marker_needs_center_left_clearance:
                # Derive the summary gap from the front-left soil region, not
                # a plot-number exception. This keeps the same collision-safe
                # placement if the scene metadata reorders its plots.
                center_left_summary_region = Rect(0.0, 300.0, 340.0, 120.0)
                placement_protected_regions = (
                    center_left_summary_region,
                    marker_protected_regions[1],
                )
            marker_placement = home_geometry.resolve_watering_can(
                layout.slot_index,
                layout,
                obstacles=marker_obstacles,
                protected_regions=placement_protected_regions,
            )
            if (
                center_left_summary_region is not None
                and marker_placement.pulse_bounds.intersects(
                    center_left_summary_region
                )
            ):
                summary_clearance = "center-left-marker"
            marker_box = marker_placement.rect
            marker_common = (
                f"left:{marker_box.x / 10:.3f}%;top:{marker_box.y / 4.2:.3f}%;"
                f"width:{marker_box.width / 10:.3f}%;height:{marker_box.height / 4.2:.3f}%"
            )
            marker_rect_data = ",".join(
                f"{value:.3f}"
                for value in (
                    marker_box.x,
                    marker_box.y,
                    marker_box.width,
                    marker_box.height,
                )
            )
            marker_pulse_data = ",".join(
                f"{value:.3f}"
                for value in (
                    marker_placement.pulse_bounds.x,
                    marker_placement.pulse_bounds.y,
                    marker_placement.pulse_bounds.width,
                    marker_placement.pulse_bounds.height,
                )
            )
            marker_target_ground_data = ",".join(
                f"{value:.3f}" for value in layout.ground_anchor
            )
            marker_planter_data = ",".join(
                f"{value:.3f}"
                for value in (
                    marker_placement.planter_rect.x,
                    marker_placement.planter_rect.y,
                    marker_placement.planter_rect.width,
                    marker_placement.planter_rect.height,
                )
            )
            marker_bed = home_geometry.bed(layout.slot_index)
            marker_exclusions_data = ";".join(
                ",".join(
                    f"{value:.3f}"
                    for value in (
                        exclusion.x,
                        exclusion.y,
                        exclusion.width,
                        exclusion.height,
                    )
                )
                for exclusion in (
                    marker_bed.planter_exclusions if marker_bed is not None else ()
                )
            )
            fallback_box = nurtured_marker_fallback_rect(marker_placement)
            fallback_common = (
                f"left:{fallback_box.x / 10:.3f}%;top:{fallback_box.y / 4.2:.3f}%;"
                f"width:{fallback_box.width / 10:.3f}%;height:{fallback_box.height / 4.2:.3f}%"
            )
            marker_url = (
                data.nurtured_marker_spout_right_url
                if marker_placement.orientation == "spout-right"
                else data.nurtured_marker_url
            )
            marker_src = escape(str(marker_url or ""), quote=True)
            fallback_display = (
                "none"
                if marker_src and not marker_placement.used_fallback
                else "block"
            )
            marker_markup = (
                (
                    '<img class="ag-home__nurtured-marker" '
                    'data-testid="home-nurturing-marker" aria-hidden="true" alt="" '
                    f'data-marker-slot="{layout.slot_index}" '
                    f'data-marker-side="{marker_placement.side}" '
                    f'data-marker-orientation="{marker_placement.orientation}" '
                    f'data-marker-rect="{marker_rect_data}" '
                    f'data-marker-pulse="{marker_pulse_data}" '
                    f'data-marker-target-ground="{marker_target_ground_data}" '
                    f'data-marker-planter-rect="{marker_planter_data}" '
                    f'data-marker-planter-exclusions="{marker_exclusions_data}" '
                    f'src="{marker_src}" style="{marker_common}" '
                    'onerror="this.style.display=\'none\';var f=this.nextElementSibling;'
                    'if(f){f.style.display=\'block\';}">'
                )
                if marker_src and not marker_placement.used_fallback else
                ""
            ) + (
                '<span class="ag-home__nurtured-marker-fallback" '
                'data-testid="home-nurturing-marker-fallback" aria-hidden="true" '
                f'data-marker-slot="{layout.slot_index}" '
                f'data-marker-side="{marker_placement.side}" '
                f'data-marker-rect="{marker_rect_data}" '
                f'data-marker-pulse="{marker_pulse_data}" '
                f'data-marker-target-ground="{marker_target_ground_data}" '
                f'data-marker-planter-rect="{marker_planter_data}" '
                f'data-marker-planter-exclusions="{marker_exclusions_data}" '
                f'style="{fallback_common};display:{fallback_display}"></span>'
            )
            marker_overlays[depth_band].append(marker_markup)
        plant_markup[depth_band].append(shadow + plant + tint)

    planter_markup: dict[str, dict[str, list[str]]] = {
        band: {"base": [], "foreground": []}
        for band in ("far", "middle", "near")
    }
    if planter_enabled:
        surface_band_by_slot: dict[int, str] = {}
        raw_surfaces = surface_variant.get("surfaces", [])
        if isinstance(raw_surfaces, list):
            for surface in raw_surfaces:
                if not isinstance(surface, dict):
                    continue
                try:
                    slot = int(surface.get("slot", -1))
                except (TypeError, ValueError):
                    continue
                band = str(surface.get("depth_band", ""))
                if 0 <= slot < 6 and band in {"far", "middle", "near"}:
                    surface_band_by_slot[slot] = band
        if planter_enabled:
            variant_for_band = {
                "far": "back",
                "middle": "middle",
                "near": "front",
            }
            planter_z = {
                "far": (4, 28),
                "middle": (34, 58),
                "near": (64, 88),
            }
            for layout in slot_layouts:
                # Normal runtime placements already carry the V6 depth band.
                # The surface metadata remains the authoritative fallback for
                # lightweight Home snapshots that omit duplicated layout
                # profiles (for example degraded-art recovery).
                band = surface_band_by_slot.get(layout.slot_index, layout.depth_band)
                variant = planter_variants.get(variant_for_band.get(band, ""), {})
                if not isinstance(variant, dict):
                    continue
                box = planter_boxes[layout.slot_index]
                common = (
                    f'left:{box.x / 10:.3f}%;top:{box.y / 4.2:.3f}%;'
                    f'width:{box.width / 10:.3f}%;height:{box.height / 4.2:.3f}%'
                )
                for layer, url_key, z_index in (
                    ("base", "url", planter_z[band][0]),
                    ("foreground", "foreground_url", planter_z[band][1]),
                ):
                    url = str(variant.get(url_key, "") or "")
                    fallback_display = "none" if url else "block"
                    fallback_layer = (
                        f'<span class="ag-home__planter-fallback '
                        f'ag-home__planter-fallback--{layer}" data-fallback-planter-band="{band}" '
                        f'data-fallback-slot-index="{layout.slot_index}" aria-hidden="true" '
                        f'style="{common};z-index:{z_index};display:{fallback_display}"></span>'
                    )
                    planter = ""
                    if url:
                        planter = (
                            f'<img class="ag-home__planter ag-home__planter--{layer}" '
                            f'data-planter-band="{band}" data-slot-index="{layout.slot_index}" '
                            f'src="{escape(url, quote=True)}" alt="" aria-hidden="true" '
                            f'style="{common};z-index:{z_index}" '
                            "onerror=\"this.onerror=null;this.style.display='none';"
                            "var f=this.nextElementSibling;if(f){f.style.display='block';}\">"
                        )
                    planter_markup[band][layer].append(planter + fallback_layer)
    layer_urls = surface_variant.get("occlusion_layer_urls", {})
    occlusion_markup: dict[str, str] = {}
    if not planter_enabled and isinstance(layer_urls, dict):
        for row, z_index in (("rear", 30), ("front", 70)):
            url = str(layer_urls.get(row, "") or "")
            if url:
                occlusion_markup[row] = f'<img class="ag-home__occlusion" style="z-index:{z_index}" src="{escape(url, quote=True)}" alt="" aria-hidden="true" onerror="this.onerror=null;this.style.display=\'none\';">'
    legacy_occlusion_url = str(surface_variant.get("occlusion_url", "") or "")
    legacy_occlusion = (
        f'<img class="ag-home__occlusion" src="{escape(legacy_occlusion_url, quote=True)}" alt="" aria-hidden="true" onerror="this.onerror=null;this.style.display=\'none\';">'
        if not planter_enabled and legacy_occlusion_url and not occlusion_markup else ""
    )
    marker_z = {"far": 27, "middle": 57, "near": 87}
    marker_layers = {
        band: (
            '<div class="ag-home__marker-layer" aria-hidden="true" '
            f'data-marker-band="{band}" style="z-index:{marker_z[band]}">'
            + "".join(marker_overlays[band])
            + "</div>"
            if marker_overlays[band] else
            ""
        )
        for band in ("far", "middle", "near")
    }
    if planter_enabled:
        layered_art = "".join(
            "".join(planter_markup[band]["base"])
            + "".join(plant_markup[band])
            + marker_layers[band]
            + "".join(planter_markup[band]["foreground"])
            for band in ("far", "middle", "near")
        )
    else:
        layered_art = (
            legacy_occlusion
            + "".join(plant_markup["far"])
            + marker_layers["far"]
            + "".join(plant_markup["middle"])
            + marker_layers["middle"]
            + occlusion_markup.get("rear", "")
            + "".join(plant_markup["near"])
            + marker_layers["near"]
            + occlusion_markup.get("front", "")
        )
    scenery_layer = (
        f'<img class="ag-home__scenery-layer" data-testid="home-garden-overlay-layer" '
        f'src="{escape(data.garden_overlay_url, quote=True)}" alt="" aria-hidden="true" '
        'onerror="this.onerror=null;this.style.display=\'none\';">'
        if data.garden_overlay_url else
        ""
    )
    weather_layer = (
        f'<img class="ag-home__weather-layer" data-testid="home-weather-layer" '
        f'src="{escape(data.weather_url, quote=True)}" alt="" aria-hidden="true" '
        'onerror="this.onerror=null;this.style.display=\'none\';">'
        if data.weather_url else
        ""
    )
    starter_selected = bool(data.starter_selected)
    starter_waiting_for_nurture = bool(data.starter_planted_not_nurtured)
    planted_starter_name = str(data.planted_starter_name or "").strip()
    planted_starter_stage = format_status_label(
        data.planted_starter_stage or "seed"
    )
    garden_name_value = str(preview.garden_name or FALLBACK_GARDEN_NAME)
    garden_name = escape(garden_name_value)
    preview_title = preview.title
    preview_support = preview.summary
    answer_unit = "answer" if data.reviews_today == 1 else "answers"
    today_answers_text = f"{format_integer(data.reviews_today)} {answer_unit} today"
    streak_text = f"{format_integer(data.streak_days)}-day Anki streak"
    coin_unit = "Garden Coin" if data.garden_currency == 1 else "Garden Coins"
    coin_text = f"{format_integer(data.garden_currency)} {coin_unit}"
    nearest_achievement_text = ""
    nearest_achievement_accessible = ""
    if data.nearest_achievement_name and data.nearest_achievement_progress:
        nearest_achievement_text = (
            f"{data.nearest_achievement_name} · {data.nearest_achievement_progress}"
        )
        nearest_achievement_accessible = (
            f". Closest achievement: {nearest_achievement_text}"
            + (
                f". Reward: {data.nearest_achievement_reward}"
                if data.nearest_achievement_reward else ""
            )
        )
    reward_progress_html = (
        '<div class="ag-home__reward-progress" data-testid="home-reward-progress">'
        '<span>'
        f'<span data-testid="home-today-answers">{escape(today_answers_text)}</span> · '
        f'<span data-testid="home-streak">{escape(streak_text)}</span> · '
        f'<span data-testid="home-currency">{escape(coin_text)}</span>'
        '</span>'
        + (
            f'<span data-testid="home-nearest-achievement" '
            f'aria-label="Closest achievement: {escape(nearest_achievement_text, quote=True)}'
            + (
                f'. Reward: {escape(data.nearest_achievement_reward, quote=True)}'
                if data.nearest_achievement_reward else ""
            )
            + f'" title="{escape(data.nearest_achievement_reward, quote=True)}">'
            f'<strong>Closest</strong> · {escape(nearest_achievement_text)}</span>'
            if nearest_achievement_text else ""
        )
        + '</div>'
    )
    home_progress_accessible = (
        f". {today_answers_text}. {streak_text}. {coin_text}"
        f"{nearest_achievement_accessible}"
        if starter_selected else ""
    )
    if not starter_selected:
        reward_progress_html = ""
    garden_identity_html = (
        '<div class="ag-home__identity">'
        '<div class="ag-home__eyebrow" aria-hidden="true">Anki Garden</div>'
        f'<h2 class="ag-home__focus-name" data-testid="home-title" '
        f'aria-label="{escape(preview_title, quote=True)}" '
        f'title="{escape(preview_title, quote=True)}">{escape(preview_title)}</h2>'
        f'<span class="ag-home__support" data-testid="home-support" '
        f'title="{escape(preview_support, quote=True)}">{escape(preview_support)}</span>'
        '</div>'
    )
    streak_progress = _streak_milestone_progress(data.streak_days)
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
    elif starter_waiting_for_nurture:
        starter_display_name = planted_starter_name or "Starter plant"
        active_growth_html = (
            '<div class="ag-home__metric ag-home__metric--plant planted-starter-summary">'
            f'<strong data-testid="home-active-name">{escape(starter_display_name)} · '
            f'{escape(planted_starter_stage)}</strong>'
            '<span data-testid="home-growth">Planted starter · Ready to nurture</span>'
            '</div>'
        )
        active_accessible_text = (
            f"{starter_display_name}, {planted_starter_stage} stage, planted starter. "
            "Open the Garden to nurture it."
        )
    else:
        active_growth_html = (
            '<div class="ag-home__metric ag-home__metric--plant nurtured-plant-summary">'
            + (
                f'<strong data-testid="home-active-name">{HOME_NO_STARTER_TITLE}</strong>'
                f'<span data-testid="home-growth">{CHOOSE_STARTER_ACTION} before studying</span>'
                if not starter_selected else
                '<strong data-testid="home-active-name">No nurtured plant</strong>'
                '<span data-testid="home-growth">Open Garden to choose one</span>'
            )
            + '</div>'
        )
        active_accessible_text = (
            f"{HOME_NO_STARTER_TITLE}. {HOME_NO_STARTER_ACCESSIBLE}"
            if not starter_selected else "No nurtured plant selected"
        )

    metrics_accessible_label = escape(
        f"{active_accessible_text}; {streak_text}; "
        f"{coin_text}; "
        f"Study Growth generated {format_integer(data.study_growth_generated)}; "
        f"nurtured allocation {format_integer(data.nurtured_growth_today)}; "
        f"other planted plants credited "
        f"{format_integer(data.passive_growth_credited_today)} passive Growth from "
        f"{format_growth_fifths(data.passive_growth_fifths_today)} exact Growth"
        + (
            "; today’s allocation detail is partially stale until scheduler rollover"
            if data.growth_accounting_stale else ""
        ),
        quote=True,
    )

    action_text = HOME_ACTIVE_ACTION if starter_selected else CHOOSE_STARTER_ACTION
    action_label = f"Open {garden_name_value}" if starter_selected else CHOOSE_STARTER_ACTION
    action_command = "open" if starter_selected else "choose-starter"
    action_reset = HOME_ACTIVE_ACTION if starter_selected else CHOOSE_STARTER_ACTION
    no_starter_body = (
        f'<span id="home-no-starter-accessible" class="ag-home__sr-only">{HOME_NO_STARTER_ACCESSIBLE}</span>'
        if not starter_selected else ""
    )
    metrics_html = (
        f'<span class="ag-home__sr-only" data-testid="home-accessible-summary">'
        f'{metrics_accessible_label}</span>'
    )
    marker_plant = next(
        (
            item
            for item in data.scene_items
            if isinstance(item, dict) and bool(item.get("is_active"))
        ),
        None,
    )
    marker_visible = marker_plant is not None
    marker_slot = int(marker_plant.get("slot_index", -1)) if marker_plant else -1
    marker_plant_name = escape(
        str(marker_plant.get("name") or "This plant"),
        quote=True,
    ) if marker_plant is not None else ""
    marker_accessible = (
        f". Watering can: {marker_plant_name} is nurtured and receives full Growth from "
        "future Anki card answers; other eligible planted plants receive 20 percent of "
        "that Growth after bonuses"
        if marker_visible else
        ""
    )

    root_class = "ag-home--no-starter" if not starter_selected else ""
    return f"""{HOME_WIDGET_STYLE}
<div id=\"ag-home-root\" class=\"{root_class}\" data-state=\"{escape(phase)}\" data-motion=\"{motion_mode}\" data-active-slot=\"{marker_slot}\" data-summary-clearance=\"{summary_clearance}\" role=\"button\" tabindex=\"0\"
  aria-label=\"{escape(action_label, quote=True)}. {escape(preview_support, quote=True)}{escape(home_progress_accessible, quote=True)}{marker_accessible}\"
  data-anki-garden-command=\"anki-garden:{action_command}\"
  onclick=\"if(event.target.closest('button'))return;pycmd('anki-garden:{action_command}')\"
  onkeydown=\"if(event.key==='Enter'||event.key===' '){{event.preventDefault();pycmd('anki-garden:{action_command}')}}\">
  <div class=\"ag-home__body\">
    {stage_up_html}
    {partial_banner}
    <div class=\"ag-home__scene\" data-testid=\"home-scene\" aria-hidden=\"true\">
      <div class=\"ag-home__scene-frame\"{scenery_identity} data-preview-crop=\"{crop_x:.3f},{crop_y:.3f},{crop_width:.3f},{crop_height:.3f}\"{background_style}>
        {scenery_layer}
        <div class=\"ag-home__art\" data-testid=\"home-plants\">{layered_art}</div>
        {weather_layer}
      </div>
    </div>
    <aside class=\"ag-home__details home-summary-panel\">
      <header class=\"ag-home__identity-row summary-header\">
        {garden_identity_html}
        <button class=\"ag-home__open\" data-testid=\"home-open\" data-anki-garden-command=\"anki-garden:{action_command}\" type=\"button\" aria-label=\"{escape(action_label, quote=True)}\"
          title=\"{escape(HOME_NO_STARTER_ACCESSIBLE if not starter_selected else action_label, quote=True)}\"
          onclick=\"event.stopPropagation();if(this.disabled)return;this.disabled=true;this.textContent='Opening…';pycmd('anki-garden:{action_command}');setTimeout(()=>{{this.disabled=false;this.textContent='{action_reset}';}},1500)\">{action_text}</button>
      </header>
      {reward_progress_html}
      {f'<p class="ag-home__status-notice" role="status">{escape(data.status_notice)}</p>' if data.status_notice else ''}
      {no_starter_body}
      {metrics_html}
    </aside>
  </div>
</div>
"""


def build_home_widget_success_data(
    *,
    state: Any,
    reviews_today: int,
    scene_items: list[dict[str, Any]],
    background_placement: dict[str, Any] | None = None,
    stage_transition_message: str = "",
    background_url: str = "",
    garden_overlay_url: str = "",
    weather_url: str = "",
    nurtured_marker_url: str = "",
    nurtured_marker_spout_right_url: str = "",
    status_notice: str = "",
) -> HomeWidgetData:
    stats = state.daily_stats
    plants = list(getattr(state, "plants", []) or [])
    starter_complete = getattr(state, "starter_selection_complete", None)
    if starter_complete is None:
        starter_complete = bool(plants)
    active_id = str(getattr(state, "active_plant_id", "") or "")
    active_plant = next(
        (plant for plant in plants if str(getattr(plant, "plant_id", "") or "") == active_id),
        None,
    )
    # Starter selection appends the first Plant before paid collection items.
    # Do not relabel a later planted purchase as the starter if that first
    # plant has since been moved out of the garden.
    first_plant = plants[0] if plants else None
    planted_starter = (
        first_plant
        if first_plant is not None and bool(getattr(first_plant, "planted", True))
        else None
    )
    starter_waiting_for_nurture = bool(
        starter_complete and active_plant is None and planted_starter is not None
    )
    active_growth = growth_display(getattr(active_plant, "growth_points", 0))
    (
        nearest_achievement_name,
        nearest_achievement_progress,
        nearest_achievement_reward,
    ) = _nearest_locked_achievement(state)
    if getattr(state, "selected_weather", None) in (None, ""):
        DISPLAY_TELEMETRY.record_missing_or_invalid_field(
            route="home_widget",
            field="selected_weather",
            reason="missing_or_empty",
            value=getattr(state, "selected_weather", None),
        )
    preview_snapshot = garden_preview_from_values(
        consumer="home",
        phase="success",
        garden_name=str(getattr(state, "garden_name", FALLBACK_GARDEN_NAME) or FALLBACK_GARDEN_NAME),
        active_plant_name=str(getattr(active_plant, "name", "") or ""),
        active_stage=str(getattr(active_plant, "growth_stage", "") or ""),
        active_growth_points=max(0, int(getattr(active_plant, "growth_points", 0) or 0)),
        active_stage_points=active_growth.stage_points if active_plant is not None else 0,
        active_stage_goal=active_growth.stage_goal if active_plant is not None else 0,
        active_fully_grown=active_growth.fully_grown if active_plant is not None else False,
        starter_selected=bool(starter_complete),
        planted_starter_name=(
            str(getattr(planted_starter, "name", "") or "")
            if starter_waiting_for_nurture else ""
        ),
        planted_starter_stage=(
            str(getattr(planted_starter, "growth_stage", "") or "")
            if starter_waiting_for_nurture else ""
        ),
        selected_weather=str(getattr(state, "selected_weather", "sunny") or "sunny"),
        selected_scenery=str(getattr(state, "selected_background", "verdant_twilight") or "verdant_twilight"),
        scene_items=scene_items,
        unlocked_slots=max(0, min(6, int(getattr(state, "unlocked_slots", 0) or 0))),
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
        weather_url=weather_url,
        nurtured_marker_url=nurtured_marker_url,
        nurtured_marker_spout_right_url=nurtured_marker_spout_right_url,
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
        planted_starter_name=(
            str(getattr(planted_starter, "name", "") or "")
            if starter_waiting_for_nurture else ""
        ),
        planted_starter_stage=(
            str(getattr(planted_starter, "growth_stage", "") or "")
            if starter_waiting_for_nurture else ""
        ),
        starter_planted_not_nurtured=starter_waiting_for_nurture,
        garden_name=str(getattr(state, "garden_name", FALLBACK_GARDEN_NAME) or FALLBACK_GARDEN_NAME),
        starter_selected=bool(starter_complete),
        preview_snapshot=preview_snapshot,
        study_growth_generated=max(
            0, int(getattr(stats, "study_growth_generated", 0) or 0)
        ),
        nurtured_growth_today=sum(
            max(0, int(value))
            for value in getattr(stats, "plant_nurtured_growth", {}).values()
        ),
        passive_growth_fifths_today=sum(
            max(0, int(value))
            for value in getattr(stats, "plant_passive_growth_fifths", {}).values()
        ),
        passive_growth_credited_today=sum(
            max(0, int(value))
            for value in getattr(stats, "plant_passive_growth_credited", {}).values()
        ),
        charge_growth_today=max(0, int(getattr(stats, "charge_growth", 0) or 0)),
        direct_reward_growth_today=max(
            0, int(getattr(stats, "direct_reward_growth", 0) or 0)
        ),
        growth_accounting_stale=bool(
            getattr(stats, "growth_accounting_stale", False)
        ),
        nearest_achievement_name=nearest_achievement_name,
        nearest_achievement_progress=nearest_achievement_progress,
        nearest_achievement_reward=nearest_achievement_reward,
    )


def _nearest_locked_achievement(state: Any) -> tuple[str, str, str]:
    """Return one useful locked milestone from the canonical presentation layer."""

    try:
        presentations = achievement_presentations(state)
    except (AttributeError, TypeError, ValueError):
        return "", "", ""
    relevant_metrics = {
        "streak_days",
        "daily_answers",
        "lifetime_answers",
        "consecutive_non_again",
    }
    locked = [
        item
        for item in presentations
        if (
            not item.unlocked
            and item.evaluation_mode == "immediate"
            and item.progress_metric in relevant_metrics
        )
    ]
    if not locked:
        return "", "", ""
    underway = [item for item in locked if item.current > 0]
    candidates = underway or [
        item for item in locked if item.progress_metric == "streak_days"
    ] or locked
    nearest = max(
        candidates,
        key=lambda item: (
            item.progress,
            -max(0, item.progress_target - item.current),
            -item.progress_target,
        ),
    )
    return nearest.name, nearest.value_text, nearest.reward_summary


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
