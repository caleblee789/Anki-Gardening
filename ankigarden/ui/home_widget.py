from __future__ import annotations
from ..feature_availability import landmarks_enabled

from dataclasses import dataclass
from enum import Enum
from html import escape
import logging
from math import isfinite
from typing import Any

from ..display_telemetry import DISPLAY_TELEMETRY
from ..environment import DEFAULT_SCENERY_ID
from ..models.state import STREAK_BONUS_TIERS
from ..achievements import streak_growth_progress
from .copy import (
    CHOOSE_STARTER_ACTION,
    FALLBACK_GARDEN_NAME,
    GARDEN_TITLE,
    HOME_ACTIVE_ACTION,
    HOME_NO_STARTER_BODY,
    HOME_NO_STARTER_ACCESSIBLE,
    HOME_NO_STARTER_TITLE,
    garden_preview_title,
)
from .formatters import format_growth, format_plant_name, format_stage_progress, format_status_label
from .landmark_display import (
    GARDEN_LANDMARK_ANCHOR,
    GARDEN_LANDMARK_ANCHORS,
    landmark_asset_identity_matches,
    landmark_ground_compression,
    landmark_scene_lighting,
    mastery_asset_identity_matches,
)
from .state import (
    GardenHomePreview,
    garden_preview_from_values,
    preview_with_phase,
)
from .plant_display import (
    plant_growth_points,
    compact_plant_layout,
    growth_display,
    plant_layout,
    planter_draw_rect,
    repair_unique_slot_items,
    scene_surface_variant,
)
from .theme import GARDEN_THEME


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
    garden_feature_pad_url: str = ""
    landmark_id: str = ""
    landmark_asset: dict[str, Any] | None = None
    landmark_url: str = ""
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
    preview_snapshot: GardenHomePreview | None = None
    study_growth_generated: int = 0
    nurtured_growth_today: int = 0
    passive_growth_fifths_today: int = 0
    passive_growth_credited_today: int = 0
    charge_growth_today: int = 0
    direct_reward_growth_today: int = 0
    growth_accounting_stale: bool = False
    weather_visible: bool = True
    visible_scenery: str = DEFAULT_SCENERY_ID
    planted_starter_growth_points: int = 0


class HomeSurfaceMode(str, Enum):
    """Product states rendered by the one compact Home-card shell."""

    STARTER = "starter"
    EMPTY = "empty"
    ACTIVE_ZERO = "active-zero"
    ACTIVE_PARTIAL = "active-partial"
    ACTIVE_COMPLETE = "active-complete"


@dataclass(frozen=True)
class HomeSurfaceViewModel:
    """Renderer-neutral state shared by starter and established Home cards.

    The lifecycle snapshot still owns loading/error/stale behavior. This model
    owns the product state inside the successful compact shell so Surfaces 01
    and 12 cannot drift into separate geometry or progress calculations.
    """

    mode: HomeSurfaceMode
    action_text: str
    action_command: str
    progress_current: int = 0
    progress_maximum: int = 0

    @property
    def progress_percent(self) -> float:
        if self.mode is HomeSurfaceMode.ACTIVE_COMPLETE:
            return 100.0
        if self.progress_maximum <= 0:
            return 0.0
        return min(
            100.0,
            max(0.0, self.progress_current / self.progress_maximum * 100.0),
        )

    @property
    def shows_progress(self) -> bool:
        return self.mode in {
            HomeSurfaceMode.ACTIVE_ZERO,
            HomeSurfaceMode.ACTIVE_PARTIAL,
            HomeSurfaceMode.ACTIVE_COMPLETE,
        }


def home_surface_view_model(data: HomeWidgetData) -> HomeSurfaceViewModel:
    """Project starter/empty/zero/partial/complete through one state machine."""

    if not bool(data.starter_selected):
        return HomeSurfaceViewModel(
            HomeSurfaceMode.STARTER,
            CHOOSE_STARTER_ACTION,
            "choose-starter",
        )
    if not str(data.active_plant_name or "") and not str(
        data.planted_starter_name or ""
    ):
        return HomeSurfaceViewModel(
            HomeSurfaceMode.EMPTY,
            HOME_ACTIVE_ACTION,
            "open",
        )

    if not str(data.active_plant_name or ""):
        starter_progress = growth_display(max(0, data.planted_starter_growth_points))
        completed = bool(starter_progress.fully_grown)
        current = max(0, data.planted_starter_growth_points if completed else starter_progress.stage_points)
        maximum = max(1, current) if completed else max(0, int(starter_progress.stage_goal))
        mode = (
            HomeSurfaceMode.ACTIVE_COMPLETE if completed else
            HomeSurfaceMode.ACTIVE_ZERO if current <= 0 else
            HomeSurfaceMode.ACTIVE_PARTIAL
        )
        return HomeSurfaceViewModel(
            mode,
            HOME_ACTIVE_ACTION,
            "open",
            current,
            maximum,
        )

    if bool(data.active_fully_grown):
        total = max(0, data.active_growth_points)
        return HomeSurfaceViewModel(
            HomeSurfaceMode.ACTIVE_COMPLETE,
            HOME_ACTIVE_ACTION,
            "open",
            total,
            max(1, total),
        )

    current = max(0, data.active_stage_points)
    maximum = max(0, int(data.active_stage_goal))
    mode = (
        HomeSurfaceMode.ACTIVE_ZERO
        if current <= 0
        else HomeSurfaceMode.ACTIVE_COMPLETE
        if maximum > 0 and current >= maximum
        else HomeSurfaceMode.ACTIVE_PARTIAL
    )
    return HomeSurfaceViewModel(
        mode,
        HOME_ACTIVE_ACTION,
        "open",
        current,
        maximum,
    )


logger = logging.getLogger(__name__)
_HOME_WEATHER_FAILURES_LOGGED: set[str] = set()


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
                "Refreshing…"
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
        error_message: str = "Refreshing…",
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


DEFAULT_ERROR_MESSAGE = "Garden preview unavailable."

HOME_COMPACT_CONTAINER_MAX_WIDTH = 400
HOME_NARROW_CONTAINER_MAX_WIDTH = 340
HOME_LAYOUT_STANDARD = "standard"
HOME_LAYOUT_COMPACT = "compact"
HOME_LAYOUT_NARROW = "narrow"
HOME_WEATHER_CANONICAL_AREA = 960.0 * 400.0


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
  width: min(calc(100% - 48px), 520px);
  max-width: 520px;
  margin: 24px auto 18px;
  padding: 0;
  box-sizing: border-box;
  overflow: hidden;
  border: 1px solid #315247;
  border-radius: 14px;
  background: #08251c;
  color: #f4f3df;
  box-shadow: 0 5px 16px rgba(2, 11, 10, 0.16);
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif;
  container-type: inline-size;
}
.ag-home__state {
  box-sizing: border-box;
  min-height: 100px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.ag-home__state-title {
  margin-bottom: 4px;
  font-size: 17px;
  font-weight: 600;
}
.ag-home__state-message, .ag-home__partial-message {
  line-height: 1.45;
}
.ag-home__loading-track {
  width:100%;
  height:6px;
  margin-top:14px;
  overflow:hidden;
  border-radius:4px;
  background:#123d31;
}
.ag-home__loading-track::after {
  content:"";
  display:block;
  width:42%;
  height:100%;
  border-radius:4px;
  background:#63d99f;
}
.ag-home__partial-message {
  box-sizing: border-box;
  width: 100%;
  overflow-wrap: anywhere;
  margin: 0;
  padding: 10px 16px;
  background: rgba(105, 70, 32, 0.34);
  color: #f2a35b;
}
.ag-home__body {
  display:flex;
  flex-direction:column;
  min-width:0;
}
.ag-home__art { position:absolute; inset:0; overflow:hidden; pointer-events:none; }
.ag-home__scenery-layer { position:absolute; inset:0; width:100%; height:100%; object-fit:fill; pointer-events:none; }
.ag-home__scenery-layer { z-index:2; }
.ag-home__scene-frame { container-type:size; }
.ag-home__landmark { position:absolute; pointer-events:none; object-fit:contain; z-index:5; filter:drop-shadow(0 1.2cqh 1.4cqh rgba(8,18,14,.34)); }
.ag-home__plant { position:absolute; object-fit:contain; animation:none !important; transition:none !important; filter:contrast(var(--ag-contrast,1)) saturate(var(--ag-saturation,1)) brightness(var(--ag-brightness,1)); }
.ag-home__mastery { position:absolute; object-fit:contain; pointer-events:none; animation:none !important; transition:none !important; }
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
  background:#0d3026;
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
  background-color:#123d31;
  opacity:var(--ag-scene-opacity,1);
  transition:opacity 140ms ease;
}
.ag-home__scene::after { content:""; position:absolute; inset:0; z-index:90; pointer-events:none; box-shadow:inset 0 -12px 24px rgba(5,14,12,.13); }
.ag-home__details {
  position:relative;
  min-width:0;
  min-height:62px;
  padding:2px 12px;
  background:linear-gradient(155deg,#0d3026,#08251c 82%);
}
.ag-home__details::before {
  content:"";
  position:absolute;
  left:0;
  right:0;
  top:-14px;
  height:14px;
  pointer-events:none;
  background:linear-gradient(to bottom,transparent,#0d3026);
}
.ag-home__details,.ag-home__details * { box-sizing:border-box; }
.ag-home__identity-row { display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:center; gap:10px; min-width:0; }
.ag-home__identity { min-width:0; }
.ag-home__garden-context { display:block; margin-top:2px; color:#95a89f; font-size:12px; line-height:1.2; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.ag-home__eyebrow { margin-bottom:1px; color:#95a89f; font-size:12px; font-weight:650; letter-spacing:.08em; line-height:16px; text-transform:uppercase; }
.ag-home__focus-name {
  display:block;
  overflow:hidden;
  margin:0;
  color:#f4f3df;
  font-size:18px;
  font-weight:600;
  line-height:1.05;
  text-overflow:ellipsis;
  white-space:nowrap;
}
.ag-home__status-notice { box-sizing:border-box; width:calc(100% + 24px); margin:4px -12px 2px; padding:5px 12px; background:rgba(242,163,91,.14); color:#f2a35b; font-size:12px; line-height:16px; overflow-wrap:anywhere; }
.ag-home__stage-up {
  box-sizing: border-box;
  width: 100%;
  margin: 0;
  padding: 8px 10px;
  background: rgba(117, 82, 35, 0.34);
  color: #e7b94a;
  font-weight: 600;
  overflow-wrap: anywhere;
  text-align: center;
}
#ag-home-root button {
  display:inline-flex;
  align-items:center;
  justify-content:center;
  min-width:104px;
  min-height:36px;
  box-sizing:border-box;
  line-height:1.2;
  flex:none;
  margin: 0;
  padding: 0 14px;
  border: 1px solid #63d99f;
  border-radius: 8px;
  background: #63d99f;
  color: #08251c;
  font-size:13px;
  font-weight: 600;
  white-space:nowrap;
  cursor: pointer;
  box-shadow:inset 0 1px 0 rgba(242,250,240,.08),0 3px 9px rgba(1,14,10,.12);
}
#ag-home-root button.ag-home__open::after { content:""; display:none; }
#ag-home-root button.ag-home__open:disabled::after { content:""; margin:0; }
#ag-home-root button:hover { background: #75e3ae; }
#ag-home-root button:active { background:#4fc98e; transform:translateY(1px); }
#ag-home-root button:disabled { cursor:wait; background:#172721; border-color:#30443b; color:#83968b; }
#ag-home-root button:focus-visible {
  outline: 2px solid #75E3AE;
  outline-offset: 2px;
  box-shadow:0 0 0 4px #081814;
}
.ag-home__open { flex:none; min-width:104px !important; min-height:36px !important; padding:0 12px !important; border-radius:8px !important; font-size:13px !important; }
.ag-home__state-actions { display:flex; flex-wrap:wrap; gap:8px; margin-top:14px; }
#ag-home-root button.ag-home__secondary {
  border-color:#70998A;
  background:#123D31;
  color:#F4F3DF;
  box-shadow:none;
}
#ag-home-root button.ag-home__secondary:hover { background:#174B3C; }
#ag-home-root button.ag-home__secondary:active { background:#0D3026; }
.nightMode #ag-home-root { background:#08251C; color:#F4F3DF; border-color:#315247; }

/* Canonical GardenHomePreview: stable text, artwork, and action zones. */
#ag-home-root {
  position:relative;
  width:min(calc(100% - 48px), 520px);
  max-width:520px;
  height:auto;
  min-height:100px;
  margin:24px auto 18px;
  border-color:#315247;
  border-radius:12px;
  background:#081814;
  box-shadow:0 10px 28px rgba(0,0,0,.24);
  cursor:default;
  transition:transform 120ms ease,border-color 120ms ease,box-shadow 120ms ease;
}
#ag-home-root:focus-visible {
  outline:2px solid #75E3AE;
  outline-offset:2px;
  box-shadow:0 0 0 4px #081814,0 14px 34px rgba(0,0,0,.3);
}
.ag-home__state {
  min-height:98px;
  padding:16px;
  background:linear-gradient(90deg,rgba(3,13,10,.995),rgba(4,17,13,.96) 45%,rgba(6,23,18,.68) 70%,rgba(7,27,20,.38));
}
.ag-home__body { position:relative; min-height:98px; }
.ag-home__scene,.ag-home--no-starter .ag-home__scene {
  position:absolute;
  inset:0;
  height:100%;
}
.ag-home__scene-frame {
  top:var(--ag-home-focal-y,var(--ag-preview-y,50%));
  background-position:var(--ag-preview-x,50%) var(--ag-preview-y,50%);
  filter:brightness(1.12);
}
.ag-home__scene::after {
  z-index:90;
  background:
    linear-gradient(90deg,rgba(3,12,9,.99) 0%,rgba(3,13,10,.86) 42%,rgba(4,14,11,.42) 66%,rgba(4,14,11,.05) 100%),
    linear-gradient(180deg,rgba(4,14,11,.18) 0%,transparent 58%,rgba(4,14,11,.08) 100%);
  box-shadow:inset 0 0 0 1px rgba(255,255,255,.02);
}
.ag-home__details {
  position:relative;
  z-index:100;
  min-height:98px;
  padding:9px 16px;
  display:flex;
  flex-direction:column;
  justify-content:flex-start;
  background:none;
  text-align:left;
}
.ag-home__details::before { display:none; }
.ag-home__identity-row {
  display:grid;
  grid-template-columns:minmax(0,260px) minmax(0,1fr) max-content;
  column-gap:12px;
  align-items:start;
}
.ag-home__identity { width:100%; max-width:260px; min-width:0; grid-column:1; }
.ag-home__artwork-zone { min-width:0; grid-column:2; pointer-events:none; }
.ag-home__identity-row > .ag-home__open,
.ag-home__identity-row > button { grid-column:3; }
.ag-home__eyebrow { margin-bottom:2px; color:#95A89F; font-size:12px; font-weight:650; letter-spacing:.08em; line-height:13px; }
.ag-home__focus-name { font-size:18px; line-height:1.2; font-weight:650; white-space:normal; overflow-wrap:anywhere; }
.ag-home__support {
  display:block;
  max-width:260px;
  margin-top:0;
  overflow:hidden;
  color:#B7C4BD;
  font-size:14px;
  font-weight:400;
  line-height:1.35;
  font-variant-numeric:tabular-nums;
  white-space:normal;
  overflow-wrap:anywhere;
}
.ag-home__progress-copy {
  display:block;
  max-width:260px;
  margin-top:0;
  overflow:hidden;
  color:#B7C4BD;
  font-size:13px;
  line-height:1.35;
  font-variant-numeric:tabular-nums;
  white-space:normal;
  overflow-wrap:anywhere;
}
.ag-home__identity--planted .ag-home__focus-name { font-size:14px; font-weight:400; color:#B7C4BD; line-height:20px; }
.ag-home__support--plant { display:flex; gap:4px; font-size:18px; font-weight:600; color:#F4F7F5; line-height:22px; }
.ag-home__plant-name { min-width:0; overflow-wrap:anywhere; }
.ag-home__plant-stage { flex:none; }
.ag-home__growth-track {
  max-width:100%;
  position:relative;
  left:0;
  right:auto;
  bottom:auto;
  width:260px;
  height:4px;
  margin:4px 0 0;
  overflow:hidden;
  border-radius:999px;
  background:rgba(99,217,159,.26);
}
.ag-home__growth-track > span {
  display:block;
  position:absolute;
  top:0;
  bottom:0;
  left:0;
  width:var(--ag-growth-percent,0%);
  height:100%;
  margin:0;
  border-radius:inherit;
  background:#63D99F;
}
.ag-home__garden-context,.ag-home__status-notice { display:none; }
.ag-home__partial-message,.ag-home__stage-up {
  position:relative;
  z-index:110;
  top:auto;
  left:auto;
  right:auto;
  width:auto;
  max-width:100%;
  margin:10px 16px 0;
  padding:7px 10px;
  border-radius:8px;
  background:rgba(12,42,33,.94);
  font-size:12.5px;
  text-align:left;
}
.ag-home__stage-up + .ag-home__partial-message { margin-top:6px; }
#ag-home-root[data-state="stale"] .ag-home__partial-message {
  top:auto;
  right:auto;
}
#ag-home-root button,#ag-home-root button.ag-home__open {
  appearance:none;
  height:36px !important;
  max-height:36px !important;
  min-height:36px !important;
  min-width:112px !important;
  width:auto;
  max-width:100%;
  padding:0 12px !important;
  line-height:16px !important;
  align-self:start !important;
  box-sizing:border-box !important;
  border-color:#63D99F;
  background:#63D99F;
  color:#08251C;
  font-size:13px !important;
  font-weight:600;
  box-shadow:0 4px 14px rgba(0,0,0,.22);
}
#ag-home-root button:hover { background:#75E3AE; }
#ag-home-root button:active { background:#4FC98E; }
#ag-home-root button.ag-home__open::after { content:""; display:none; }
#ag-home-root[data-motion="reduced"] { transition:none; }
#ag-home-root[data-motion="reduced"]:hover { transform:none; }
#ag-home-root[data-motion="reduced"] button:active { transform:none; }
#ag-home-root[data-motion="reduced"] .ag-home__scene-frame { transition:none; }
#ag-home-root[data-home-mode="starter"] { height:auto; min-height:0; }
#ag-home-root[data-home-mode="starter"] .ag-home__body { height:auto; }
#ag-home-root[data-home-mode="starter"] .ag-home__details { position:relative; inset:auto; padding:16px; }
#ag-home-root[data-home-mode="starter"] .ag-home__state { min-height:0; padding:16px; }
#ag-home-root[data-home-mode="starter"] .ag-home__identity-row { align-items:center; }
@media (max-width:560px) {
  #ag-home-root[data-home-mode="starter"] .ag-home__identity-row { grid-template-columns:minmax(0,1fr); row-gap:12px; }
  #ag-home-root[data-home-mode="starter"] .ag-home__identity-row > button { grid-column:1; justify-self:start; }
  #ag-home-root[data-home-mode="starter"] .ag-home__artwork-zone { display:none; }
}
@media (prefers-reduced-motion: reduce) {
  #ag-home-root { transition:none; }
  #ag-home-root:hover { transform:none; }
  #ag-home-root button:active { transform:none; }
  .ag-home__scene-frame { transition:none; }
}
@container (max-width: 400px) {
  #ag-home-root { min-height:100px; }
  .ag-home__state { min-height:100px; }
  .ag-home__details { padding:9px 14px; }
  .ag-home__identity-row {
    grid-template-columns:minmax(0,1fr) max-content;
    gap:10px;
  }
  .ag-home__artwork-zone { display:none; }
  .ag-home__identity-row > .ag-home__open,
  .ag-home__identity-row > button { grid-column:2; }
  #ag-home-root button,.ag-home__open {
    width:auto;
    max-width:100%;
    justify-self:end;
  }
  .ag-home__support { max-width:100%; }
  .ag-home__growth-track { left:0; right:auto; bottom:auto; width:100%; }
}
@container (max-width:340px) {
  .ag-home__details { padding:12px; }
  .ag-home__identity-row { grid-template-columns:minmax(0,1fr); gap:10px; }
  .ag-home__identity { max-width:100%; }
  .ag-home__identity-row > .ag-home__open,
  .ag-home__identity-row > button { grid-column:1; justify-self:start; }
  .ag-home__support,.ag-home__progress-copy { max-width:100%; }
}
</style>
"""

# The Home surface is HTML/CSS, but it consumes the same semantic authority as
# the Qt views. Literal fallbacks keep the stylesheet readable in snapshots;
# this binding step makes token changes propagate instead of forking a WebView
# palette.
for _home_literal, _home_token in (
    ("#081814", GARDEN_THEME["garden_background"]),
    ("#08251C", GARDEN_THEME["dialog_surface"]),
    ("#0D3026", GARDEN_THEME["raised_surface"]),
    ("#123D31", GARDEN_THEME["selected_surface"]),
    ("#174B3C", GARDEN_THEME["elevated_surface"]),
    ("#315247", GARDEN_THEME["subtle_border"]),
    ("#70998A", GARDEN_THEME["strong_border"]),
    ("#F4F3DF", GARDEN_THEME["text_primary"]),
    ("#B7C4BD", GARDEN_THEME["text_secondary"]),
    ("#95A89F", GARDEN_THEME["text_muted"]),
    ("#63D99F", GARDEN_THEME["action_accent"]),
    ("#75E3AE", GARDEN_THEME["action_hover"]),
    ("#4FC98E", GARDEN_THEME["action_pressed"]),
    ("#F2A35B", GARDEN_THEME["warning"]),
    ("#E7B94A", GARDEN_THEME["coin_accent"]),
    ("#172721", GARDEN_THEME["disabled_surface"]),
    ("#30443B", GARDEN_THEME["disabled_border"]),
    ("#83968B", GARDEN_THEME["disabled_text"]),
):
    HOME_WIDGET_STYLE = HOME_WIDGET_STYLE.replace(
        _home_literal,
        _home_token,
    ).replace(
        _home_literal.lower(),
        _home_token,
    )


def _plant_fallback(_stage: Any) -> str:
    """Return a quiet code-native silhouette; system emoji are never substituted."""
    return '<span class="ag-home__fallback-silhouette" aria-hidden="true"></span>'


def _log_home_weather_failure_once(key: str, message: str, *, exc_info: bool = False) -> None:
    if key in _HOME_WEATHER_FAILURES_LOGGED:
        return
    _HOME_WEATHER_FAILURES_LOGGED.add(key)
    logger.warning(message, exc_info=exc_info)


def _home_landmark_markup(
    data: HomeWidgetData,
    *,
    phase: str,
) -> str:
    """Render one noninteractive completed Landmark with exact artwork."""

    if not landmarks_enabled():
        return ""

    landmark_id = str(data.landmark_id or "")
    landmark_url = str(data.landmark_url or "")
    if (
        phase in {"loading", "error", "disabled"}
        or not landmark_url
        or not landmark_asset_identity_matches(data.landmark_asset, landmark_id)
    ):
        return ""
    anchor = GARDEN_LANDMARK_ANCHORS.get(landmark_id, GARDEN_LANDMARK_ANCHOR)
    brightness, saturation = landmark_scene_lighting(data.visible_scenery)
    compression = landmark_ground_compression(landmark_id)
    return (
        '<img class="ag-home__landmark" data-testid="home-garden-landmark" '
        f'data-landmark="{escape(landmark_id, quote=True)}" '
        f'data-landmark-anchor="{anchor.identity}" '
        f'src="{escape(landmark_url, quote=True)}" alt="" aria-hidden="true" '
        f'style="left:{anchor.left * 100:.3f}%;top:{anchor.top * 100:.3f}%;'
        f'width:{anchor.width * 100:.3f}%;height:{anchor.height * 100:.3f}%;'
        f'filter:saturate({saturation:.2f}) brightness({brightness:.2f});'
        f'transform:scaleY({compression:.2f});transform-origin:center bottom" '
        'onerror="this.onerror=null;this.style.display=\'none\';">'
    )


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
            '<div class="ag-home__eyebrow">Anki Garden</div>'
            '<div class="ag-home__state-title" role="status" aria-live="polite">'
            'Loading garden...</div>'
            '<div class="ag-home__loading-track" aria-hidden="true"></div>'
            '</div>'
            "</div>"
        )
    if phase == "empty":
        return (
            HOME_WIDGET_STYLE
            +
            f'<div id="ag-home-root" data-state="empty" data-home-mode="starter"{motion_attribute} role="region" aria-label="Anki Garden">'
            '<div class="ag-home__state" data-testid="home-empty" role="status">'
            '<div class="ag-home__identity-row"><div class="ag-home__identity">'
            '<div class="ag-home__eyebrow">Anki Garden</div>'
            f'<div class="ag-home__state-title">{HOME_NO_STARTER_TITLE}</div>'
            f'<div class="ag-home__state-message">{HOME_NO_STARTER_BODY}</div>'
            f'<span class="ag-home__sr-only">{HOME_NO_STARTER_ACCESSIBLE}</span>'
            '</div>'
            '<span class="ag-home__artwork-zone" aria-hidden="true"></span>'
            f'<button data-testid="home-open" type="button" aria-label="{CHOOSE_STARTER_ACTION}" '
            f'onclick="pycmd(\'anki-garden:choose-starter\')">{CHOOSE_STARTER_ACTION}</button>'
            '</div></div>'
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
            'Your garden can still be opened. '
            f'<span class="ag-home__sr-only">{detail}</span></div>'
            '<div class="ag-home__state-actions">'
            '<button data-testid="home-open" class="ag-home__open" type="button" '
            f'aria-label="{HOME_ACTIVE_ACTION}" onclick="pycmd(\'anki-garden:open\')">{HOME_ACTIVE_ACTION}</button>'
            '<button data-testid="home-retry" class="ag-home__secondary" type="button" '
            'aria-label="Retry garden preview" '
            'onclick="pycmd(\'anki-garden:refresh\')">Try again</button>'
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
            'Your garden can still be opened.</div>'
            '<div class="ag-home__state-actions">'
            '<button data-testid="home-open" class="ag-home__open" type="button" '
            f'aria-label="{HOME_ACTIVE_ACTION}" onclick="pycmd(\'anki-garden:open\')">{HOME_ACTIVE_ACTION}</button>'
            '<button data-testid="home-retry" class="ag-home__secondary" type="button" '
            'aria-label="Retry garden preview" '
            'onclick="pycmd(\'anki-garden:refresh\')">Try again</button>'
            '</div></div>'
            "</div>"
        )
    if not data.weather:
        DISPLAY_TELEMETRY.track_fallback(
            route="home_widget",
            field="garden_feature",
        )

    surface_view = home_surface_view_model(data)
    # Repair invalid or duplicate bed indexes once, then use that exact list for
    # both geometry and markup.  Re-normalizing only inside the layout helper
    # can otherwise put one plant's artwork and name on another plant's bed.
    scene_items = tuple(
        repair_unique_slot_items(
            item for item in data.scene_items if isinstance(item, dict)
        )
    )

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
            reviews_today=data.reviews_today,
            streak_days=data.streak_days,
            garden_currency=data.garden_currency,
            starter_selected=data.starter_selected,
            planted_starter_name=data.planted_starter_name,
            planted_starter_stage=data.planted_starter_stage,
            selected_weather=data.weather,
            selected_scenery=data.visible_scenery,
            scene_items=scene_items,
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
        partial_error = escape(snapshot.error_message or "Some details are unavailable.")
        partial_banner = (
            '<div class="ag-home__partial-message" data-testid="home-partial-error" '
            f'role="status" aria-live="polite">{partial_error}</div>'
        )
    elif preview.status_text:
        status_copy = "Refreshing…" if preview.phase == "stale" else preview.status_text
        partial_banner = (
            '<div class="ag-home__partial-message" data-testid="home-preview-status" '
            f'role="status" aria-live="polite">{escape(status_copy)}</div>'
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
        else scene_items[0].get("background_placement", {})
        if scene_items
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
        f' data-scenery="{escape(data.visible_scenery, quote=True)}"'
        if background_url else
        ""
    )
    feature_scene_class = (
        "light"
        if str(data.visible_scenery) in {
            "spring", "summer", "autumn", "snowy", "rainbow_horizon"
        }
        else "dark"
    )
    scenery_identity += f' data-feature-scene="{feature_scene_class}"'
    layouts = compact_plant_layout(
        1000,
        420,
        scene_items,
        background_placement if isinstance(background_placement, dict) else None,
    )
    by_slot = {
        int(item.get("slot_index", index)): item
        for index, item in enumerate(scene_items)
    }
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
    plant_markup: dict[str, list[str]] = {
        "far": [],
        "middle": [],
        "near": [],
    }
    summary_clearance = "none"
    theme = str(scene_items[0].get("background_theme", "verdant_twilight")) if scene_items else "verdant_twilight"
    band_counts = {"far": 0, "middle": 0, "near": 0}
    plant_z_base = {"far": 10, "middle": 40, "near": 70}
    for layout in layouts:
        item = by_slot.get(layout.slot_index, {})
        src = escape(str(item.get("url", "")), quote=True)
        plant_id = escape(str(item.get("plant_id", "")), quote=True)
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
            f'<span class="ag-home__plant-fallback" data-plant-id="{plant_id}" '
            f'data-slot-index="{layout.slot_index}" role="img" '
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
                f'<img class="ag-home__plant" data-plant-id="{plant_id}" '
                f'data-slot-index="{layout.slot_index}" '
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
        mastery_rank = str(item.get("mastery_rank_id", "") or "")
        mastery_url = str(item.get("mastery_url", "") or "")
        mastery = (
            f'<img class="ag-home__mastery" data-plant-id="{plant_id}" '
            f'data-slot-index="{layout.slot_index}" '
            f'data-mastery-rank="{escape(mastery_rank, quote=True)}" '
            f'src="{escape(mastery_url, quote=True)}" alt="" aria-hidden="true" '
            f'style="left:{layout.draw.x/10:.3f}%;top:{layout.draw.y/4.2:.3f}%;'
            f'width:{layout.draw.width/10:.3f}%;height:{layout.draw.height/4.2:.3f}%;'
            f'z-index:{depth_index + 2}" '
            'onerror="this.onerror=null;this.style.display=\'none\';">'
            if plant_id
            and mastery_url
            and mastery_asset_identity_matches(
                item.get("mastery_asset"),
                mastery_rank,
            )
            else ""
        )
        plant_markup[depth_band].append(shadow + plant + tint + mastery)

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
    if planter_enabled:
        layered_art = "".join(
            "".join(planter_markup[band]["base"])
            + "".join(plant_markup[band])
            + "".join(planter_markup[band]["foreground"])
            for band in ("far", "middle", "near")
        )
    else:
        layered_art = (
            legacy_occlusion
            + "".join(plant_markup["far"])
            + "".join(plant_markup["middle"])
            + occlusion_markup.get("rear", "")
            + "".join(plant_markup["near"])
            + occlusion_markup.get("front", "")
        )
    scenery_layer = (
        f'<img class="ag-home__scenery-layer" data-testid="home-garden-overlay-layer" '
        f'src="{escape(data.garden_overlay_url, quote=True)}" alt="" aria-hidden="true" '
        'onerror="this.onerror=null;this.style.display=\'none\';">'
        if data.garden_overlay_url else
        ""
    )

    landmark_layer = _home_landmark_markup(data, phase=phase)
    starter_selected = bool(data.starter_selected)
    preview_title = garden_preview_title(preview.title)
    display_growth_current = max(0, preview.growth_current)
    display_growth_goal = max(0, int(preview.growth_goal))
    display_fully_grown = bool(data.active_fully_grown)
    preview_identity = ""
    preview_plant_name = ""
    preview_plant_stage = ""
    preview_progress = ""
    preview_support_progress = ""
    if preview.active_plant_name:
        stage = format_status_label(preview.active_stage or preview.stage_text or "Plant")
        if display_fully_grown:
            display_growth_current = max(0, data.active_growth_points)
            display_growth_goal = max(1, display_growth_current)
            growth_text = f"{display_growth_current:,} total Growth"
        elif display_growth_goal > 0:
            destination = format_status_label(data.active_next_stage or "the next stage")
            growth_text = format_stage_progress(display_growth_current, display_growth_goal, destination)
        else:
            growth_text = preview.growth_text or "0"
        preview_identity = preview.active_plant_name
        preview_plant_name, preview_plant_stage = preview.active_plant_name, stage
        preview_progress = growth_text
        preview_support_progress = (
            format_growth(display_growth_current, display_growth_goal)
            if display_growth_goal > 0 and not display_fully_grown
            else growth_text
        )
        preview_support = f"{preview_identity} · {preview_support_progress}"
    elif data.planted_starter_name:
        starter_progress = growth_display(max(0, data.planted_starter_growth_points))
        display_growth_current = max(0, starter_progress.stage_points)
        display_growth_goal = max(0, int(starter_progress.stage_goal))
        starter_stage = format_status_label(
            data.planted_starter_stage or starter_progress.stage or "Seed"
        )
        preview_identity = data.planted_starter_name
        preview_plant_name, preview_plant_stage = data.planted_starter_name, starter_stage
        display_fully_grown = bool(starter_progress.fully_grown)
        if display_fully_grown:
            display_growth_current = max(0, data.planted_starter_growth_points)
            display_growth_goal = max(1, display_growth_current)
            preview_support_progress = f"{display_growth_current:,} total Growth"
        else:
            preview_support_progress = format_growth(display_growth_current, display_growth_goal)
        preview_progress = preview_support_progress
        if starter_progress.next_stage:
            preview_progress += (
                f" to {format_status_label(starter_progress.next_stage)}"
            )
        preview_support = f"{preview_identity} · {preview_support_progress}"
    else:
        preview_support = HOME_NO_STARTER_BODY if not starter_selected else preview.summary
        preview_identity = preview_support
    identity_content = (
        f'<span class="ag-home__plant-name">{escape(preview_plant_name)}</span> '
        if preview_plant_name else escape(preview_identity)
    )
    support_class = "ag-home__support ag-home__support--plant" if preview_plant_name else "ag-home__support"
    garden_identity_html = (
        f'<div class="ag-home__identity{" ag-home__identity--planted" if preview_plant_name else ""}">'
        f'<h2 class="ag-home__focus-name" data-testid="home-title" '
        f'aria-label="{escape(preview_title, quote=True)}" '
        f'title="{escape(preview_title, quote=True)}">{escape(preview_title)}</h2>'
        f'<span class="{support_class}" data-testid="home-support" '
        f'title="{escape(preview_support, quote=True)}">{identity_content}</span>'
        + (
            f'<span class="ag-home__progress-copy" data-testid="home-progress-copy">'
            f'{escape(preview_progress)}</span>'
            if preview_progress else ""
        )
        + (
            '<div class="ag-home__growth-track" data-testid="home-growth-progress" '
            f'role="progressbar" aria-label="{escape(preview_support, quote=True)}" '
            f'aria-valuemin="0" aria-valuemax="{max(1, display_growth_goal)}" '
            f'aria-valuenow="{min(display_growth_current, max(1, display_growth_goal))}" '
            f'style="--ag-growth-percent:{min(100.0, max(0.0, display_growth_current / max(1, display_growth_goal) * 100)):.2f}%">'
            '<span></span></div>'
            if display_growth_goal > 0 else ""
        )
        + '</div>'
    )
    action_text = surface_view.action_text
    action_label = f"Open {GARDEN_TITLE}" if starter_selected else CHOOSE_STARTER_ACTION
    action_command = surface_view.action_command
    action_reset = HOME_ACTIVE_ACTION if starter_selected else CHOOSE_STARTER_ACTION
    no_starter_body = (
        f'<span id="home-no-starter-accessible" class="ag-home__sr-only">{HOME_NO_STARTER_ACCESSIBLE}</span>'
        if not starter_selected else ""
    )
    active_plant = next(
        (
            item
            for item in scene_items
            if isinstance(item, dict) and bool(item.get("is_active"))
        ),
        None,
    )
    active_slot = int(active_plant.get("slot_index", -1)) if active_plant else -1
    active_layout = next(
        (layout for layout in layouts if layout.slot_index == active_slot),
        None,
    )
    active_band = (
        active_layout.depth_band
        if active_layout is not None
        and active_layout.depth_band in {"far", "middle", "near"}
        else "none"
    )
    active_side = (
        "left"
        if active_layout is not None and active_layout.ground_anchor[0] < 500.0
        else "right"
        if active_layout is not None
        else "none"
    )
    focal_y = {
        "far": 70.0,
        "middle": 40.0,
        "near": 10.0,
    }.get(active_band)
    focal_style = (
        f' style="--ag-home-focal-y:{focal_y:.1f}%"'
        if focal_y is not None
        else ""
    )

    root_class = "ag-home--no-starter" if not starter_selected else ""
    return f"""{HOME_WIDGET_STYLE}
<div id=\"ag-home-root\" class=\"{root_class}\" data-state=\"{escape(phase)}\" data-home-mode=\"{surface_view.mode.value}\" data-progress-current=\"{surface_view.progress_current}\" data-progress-maximum=\"{surface_view.progress_maximum}\" data-progress-percent=\"{surface_view.progress_percent:.2f}\" data-motion=\"{motion_mode}\" data-active-slot=\"{active_slot}\" data-active-band=\"{active_band}\" data-active-side=\"{active_side}\" data-summary-clearance=\"{summary_clearance}\"{focal_style} role=\"region\"
  aria-label=\"{GARDEN_TITLE} summary. {escape(preview_support, quote=True)}\">
  <div class=\"ag-home__body\">
    {stage_up_html}
    {partial_banner}
    <div class=\"ag-home__scene\" data-testid=\"home-scene\" aria-hidden=\"true\">
      <div class=\"ag-home__scene-frame\"{scenery_identity} data-preview-crop=\"{crop_x:.3f},{crop_y:.3f},{crop_width:.3f},{crop_height:.3f}\"{background_style}>
        {scenery_layer}
        {landmark_layer}
        <div class=\"ag-home__art\" data-testid=\"home-plants\">{layered_art}</div>
      </div>
    </div>
    <aside class=\"ag-home__details home-summary-panel\">
      <header class=\"ag-home__identity-row summary-header\">
        {garden_identity_html}
        <span class=\"ag-home__artwork-zone\" aria-hidden=\"true\"></span>
        <button class=\"ag-home__open\" data-testid=\"home-open\" data-anki-garden-command=\"anki-garden:{action_command}\" type=\"button\" aria-label=\"{escape(action_label, quote=True)}\"
          title=\"{escape(HOME_NO_STARTER_ACCESSIBLE if not starter_selected else action_label, quote=True)}\"
          onclick=\"event.stopPropagation();if(this.disabled)return;this.disabled=true;this.textContent='Opening…';pycmd('anki-garden:{action_command}');setTimeout(()=>{{this.disabled=false;this.textContent='{action_reset}';}},1500)\">{action_text}</button>
      </header>
      {f'<p class="ag-home__status-notice" role="status">{escape(data.status_notice)}</p>' if data.status_notice else ''}
      {no_starter_body}
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
    garden_feature_pad_url: str = "",
    landmark_id: str = "",
    landmark_asset: dict[str, Any] | None = None,
    landmark_url: str = "",
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
    active_growth = growth_display(plant_growth_points(active_plant))
    weather_visible = True
    selected_scenery = str(
        getattr(state, "selected_background", DEFAULT_SCENERY_ID)
        or DEFAULT_SCENERY_ID
    )
    visible_scenery = selected_scenery
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
        garden_name=GARDEN_TITLE,
        active_plant_name=format_plant_name(active_plant) if active_plant is not None else "",
        active_stage=str(getattr(active_plant, "growth_stage", "") or ""),
        active_growth_points=plant_growth_points(active_plant),
        active_stage_points=active_growth.stage_points if active_plant is not None else 0,
        active_stage_goal=active_growth.stage_goal if active_plant is not None else 0,
        active_fully_grown=active_growth.fully_grown if active_plant is not None else False,
        reviews_today=reviews_today,
        streak_days=int(getattr(state, "streak_days", 0) or 0),
        garden_currency=max(0, int(getattr(state, "currency_balance", 0) or 0)),
        starter_selected=bool(starter_complete),
        planted_starter_name=(
            format_plant_name(planted_starter)
            if starter_waiting_for_nurture else ""
        ),
        planted_starter_stage=(
            str(getattr(planted_starter, "growth_stage", "") or "")
            if starter_waiting_for_nurture else ""
        ),
        selected_weather=str(
            getattr(
                state,
                "displayed_garden_feature",
                getattr(state, "selected_garden_feature", "seedling_sign"),
            )
            or "seedling_sign"
        ),
        selected_scenery=visible_scenery,
        scene_items=scene_items,
        unlocked_slots=max(0, min(6, int(getattr(state, "unlocked_slots", 0) or 0))),
    )
    retained_percent, next_tier = streak_growth_progress(state)
    return HomeWidgetData(
        reviews_today=reviews_today,
        growth_earned=int(stats.growth_earned),
        base_growth=int(getattr(stats, "base_growth", 0)),
        streak_bonus_growth=int(getattr(stats, "streak_bonus_growth", 0)),
        fertilizer_growth=int(getattr(stats, "fertilizer_growth", 0)),
        bonus_growth=int(getattr(stats, "bonus_growth", 0)),
        all_due_completed=bool(getattr(stats, "completed_due_cards", False)),
        streak_days=int(state.streak_days),
        streak_bonus_percent=retained_percent,
        next_streak_day=next_tier.progress_target if next_tier else None,
        next_streak_bonus_percent=next_tier.reward.permanent_growth_percent if next_tier else None,
        garden_currency=max(0, int(getattr(state, "currency_balance", 0))),
        weather=str(
            getattr(
                state,
                "displayed_garden_feature",
                getattr(state, "selected_garden_feature", state.selected_weather),
            )
            or "N/A"
        ),
        weather_visible=weather_visible,
        visible_scenery=visible_scenery,
        scene_items=tuple(scene_items),
        background_placement=background_placement,
        stage_transition_message=stage_transition_message,
        background_url=background_url,
        garden_overlay_url=garden_overlay_url,
        weather_url=weather_url,
        garden_feature_pad_url=garden_feature_pad_url,
        landmark_id=str(landmark_id or ""),
        landmark_asset=landmark_asset,
        landmark_url=landmark_url,
        nurtured_marker_url=nurtured_marker_url,
        nurtured_marker_spout_right_url=nurtured_marker_spout_right_url,
        total_reviews=max(0, int(getattr(state, "total_reviews", 0) or 0)),
        status_notice=status_notice,
        unlocked_slots=max(0, min(6, int(getattr(state, "unlocked_slots", 0) or 0))),
        collection_count=max(0, len(plants)),
        active_plant_name=format_plant_name(active_plant) if active_plant is not None else "",
        active_plant_stage=str(getattr(active_plant, "growth_stage", "") or ""),
        active_growth_points=plant_growth_points(active_plant),
        active_stage_points=active_growth.stage_points if active_plant is not None else 0,
        active_stage_goal=active_growth.stage_goal if active_plant is not None else 0,
        active_next_stage=str(active_growth.next_stage or "") if active_plant is not None else "",
        active_points_remaining=active_growth.points_remaining if active_plant is not None else 0,
        active_fully_grown=active_growth.fully_grown if active_plant is not None else False,
        planted_starter_name=(
            format_plant_name(planted_starter)
            if starter_waiting_for_nurture else ""
        ),
        planted_starter_stage=(
            str(getattr(planted_starter, "growth_stage", "") or "")
            if starter_waiting_for_nurture else ""
        ),
        starter_planted_not_nurtured=starter_waiting_for_nurture,
        planted_starter_growth_points=(
            plant_growth_points(planted_starter) if starter_waiting_for_nurture else 0
        ),
        garden_name=GARDEN_TITLE,
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
    )


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
