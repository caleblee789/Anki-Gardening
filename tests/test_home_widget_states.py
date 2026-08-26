import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ankigarden.ui.home_widget import (
    HomeWidgetData,
    HomeWidgetSnapshot,
    HomeWidgetStateController,
    build_home_widget_success_data,
    render_home_widget,
)
from ankigarden.models.state import Achievement
from ankigarden.ui.state import garden_preview_from_values


def _sample_data(reviews_today: int = 12, growth_earned: int = 30, weather: str = "sunny") -> HomeWidgetData:
    return HomeWidgetData(
        reviews_today=reviews_today,
        growth_earned=growth_earned,
        base_growth=max(0, growth_earned - 2),
        streak_bonus_growth=min(2, growth_earned),
        fertilizer_growth=0,
        bonus_growth=min(2, growth_earned),
        all_due_completed=False,
        streak_days=7,
        streak_bonus_percent=5,
        next_streak_day=14,
        next_streak_bonus_percent=10,
        garden_currency=35,
        weather=weather,
        scene_items=({
            "slot_index": 0,
            "name": "Bonsai",
            "url": "/_addons/123/assets/bonsai.png",
            "placement": {"visible_bounds": [0.1, 0.05, 0.8, 0.9], "base_type": "pot"},
        },),
        unlocked_slots=2,
        collection_count=2,
        active_plant_name="Moss",
        active_plant_stage="seed",
        active_growth_points=growth_earned,
        active_stage_points=growth_earned,
        active_stage_goal=500,
        active_next_stage="sprout",
        active_points_remaining=max(0, 500 - growth_earned),
    )


def test_loading_state_preserves_preview_geometry_without_actions() -> None:
    html = render_home_widget(HomeWidgetSnapshot(request_id=1, phase="loading"))

    assert 'data-state="loading"' in html
    assert 'data-testid="home-loading"' in html
    assert 'role="status" aria-live="polite"' in html
    assert 'aria-busy="true"' in html
    assert 'class="ag-home__loading-track" aria-hidden="true"' in html
    assert 'class="ag-home__state"' in html
    assert "Loading garden..." in html
    assert "Loading garden preview…" not in html
    assert 'data-testid="home-open"' not in html
    assert 'data-testid="home-retry"' not in html
    assert "height:136px" in html


def test_empty_state_renders_empty_message() -> None:
    html = render_home_widget(HomeWidgetSnapshot(request_id=0, phase="empty"))

    assert 'data-state="empty"' in html
    assert 'data-testid="home-empty"' in html
    assert 'role="region" aria-label="Anki Garden"' in html
    assert "Choose a starter" in html
    assert "Your first plant is free." in html
    assert "Start with one free seed." not in html
    assert "Reviews completed before setup do not earn Growth." not in html
    assert "Choose a starter for your garden." in html
    assert "Reviews completed beforehand cannot earn Growth." not in html
    assert "pycmd('anki-garden:choose-starter')" in html
    assert "Answer your first card" not in html


def test_recoverable_error_renders_retry_action() -> None:
    html = render_home_widget(HomeWidgetSnapshot(request_id=2, phase="error", error_message="Network timeout"))

    assert 'data-state="error"' in html
    assert "Network timeout" in html
    assert "Garden preview unavailable" in html
    assert "Your garden can still be opened." in html
    assert "could not be generated" not in html
    assert 'data-testid="home-open"' in html
    assert 'data-testid="home-retry"' in html
    assert 'role="alert"' in html
    assert 'aria-label="Retry garden preview"' in html
    assert 'class="ag-home__secondary"' in html


def test_missing_preview_payload_keeps_open_and_retry_recovery_paths() -> None:
    html = render_home_widget(HomeWidgetSnapshot(request_id=7, phase="success"))

    assert 'data-state="error"' in html
    assert "Garden preview unavailable" in html
    assert html.count('data-testid="home-open"') == 1
    assert html.count('data-testid="home-retry"') == 1
    assert "Your garden can still be opened." in html


def test_partial_state_renders_available_data_and_error_banner() -> None:
    html = render_home_widget(
        HomeWidgetSnapshot(
            request_id=3,
            phase="partial",
            data=_sample_data(reviews_today=5, weather="cloudy"),
            error_message="Achievements are temporarily unavailable",
        )
    )

    assert 'data-state="partial"' in html
    assert 'data-testid="home-partial-error"' in html
    assert 'class="ag-home__partial-message"' in html
    assert 'data-testid="home-support" title="Moss · Seed · 30 / 500 toward Sprout"' in html
    assert 'data-testid="home-today-answers"' not in html
    assert 'data-testid="home-streak"' not in html
    assert 'data-testid="home-currency"' not in html
    assert 'data-testid="home-reviews"' not in html
    assert "Weather: Cloudy" not in html


def test_success_state_renders_key_fields() -> None:
    html = render_home_widget(HomeWidgetSnapshot(request_id=4, phase="success", data=_sample_data()))

    assert 'data-state="success"' in html
    assert 'data-testid="home-reviews"' not in html
    assert 'data-testid="home-title" aria-label="My Garden"' in html
    assert 'data-testid="home-support" title="Moss · Seed · 30 / 500 toward Sprout"' in html
    assert 'data-testid="home-active-name"' not in html
    assert 'data-testid="home-growth"' not in html
    assert 'data-testid="home-currency"' not in html
    assert 'data-testid="home-streak"' not in html
    assert 'data-testid="home-today-answers"' not in html
    assert html.count('data-testid="home-open"') == 1
    assert 'data-testid="home-refresh"' not in html
    assert 'data-testid="home-accessible-summary"' not in html
    assert "12 today" not in html
    assert "7-day streak" not in html
    assert "35 coins" not in html
    assert 'id="ag-home-root"' in html
    assert 'role="region"' in html
    assert 'role="button" tabindex="0"' not in html
    assert (
        'aria-label="My Garden Anki Garden summary. Moss · Seed · 30 / 500 toward Sprout"'
        in html
    )
    assert 'aria-label="Open My Garden"' in html
    assert '<div class="ag-home__eyebrow" aria-hidden="true">Anki Garden</div>' in html
    assert '<h2 class="ag-home__focus-name" data-testid="home-title" aria-label="My Garden"' in html
    assert "max-width:600px" in html
    assert "height:136px" in html
    assert "@container (max-width:420px)" in html
    assert '<aside class="ag-home__details home-summary-panel">' in html
    assert '<header class="ag-home__identity-row summary-header">' in html
    assert '<div class="ag-home__metrics"' not in html
    assert ".ag-home__garden-context,.ag-home__status-notice { display:none; }" in html
    assert "min-height:36px" in html
    assert "max-height:36px" in html
    assert "min-width:104px" in html
    assert "outline: 2px solid #82E2AC" in html
    assert "outline-offset: 2px" in html
    assert "box-shadow:0 0 0 4px #071A15" in html
    assert "this.disabled=true" in html
    assert "setTimeout" in html


def test_home_preview_never_renders_weather_or_sun_and_uses_compact_action() -> None:
    base = _sample_data(weather="sunny")
    data = HomeWidgetData(**{
        **base.__dict__,
        "weather_url": "/_addons/123/assets/weather/sun.webp",
    })

    html = render_home_widget(
        HomeWidgetSnapshot(request_id=4, phase="success", data=data)
    )

    assert "ag-home__weather-layer" not in html
    assert "home-weather-layer" not in html
    assert "weather/sun.webp" not in html
    assert "min-height:36px !important" in html
    assert "max-height:36px !important" in html
    assert 'data-testid="home-open"' in html


def test_success_state_uses_resolved_background_as_compact_scene() -> None:
    base = _sample_data()
    data = HomeWidgetData(**{**base.__dict__, "background_url": "/_addons/123/assets/garden.webp"})

    html = render_home_widget(HomeWidgetSnapshot(request_id=5, phase="success", data=data))

    assert 'data-testid="home-scene"' in html
    assert 'data-slot-index="0"' in html
    assert 'data-base-type="pot"' in html
    assert "garden.webp" in html
    assert "background-size:100% 100%" in html
    assert 'data-preview-crop="0.000,0.080,1.000,0.840"' in html
    assert "aspect-ratio:var(--ag-source-aspect, 2.4)" in html


def test_home_scene_layers_theme_terrace_and_readable_seedling_cue() -> None:
    base = _sample_data()
    seed = ({
        **base.scene_items[0],
        "stage": "seed",
        "background_placement": {
            "bed_anchors": [
                {
                    "x": 0.31, "y": 0.89, "depth": 0.78, "plant_scale": 1.0,
                    "footprint": [0.175, 0.06], "label_anchor": [0.17, 0.825],
                },
                {
                    "x": 0.69, "y": 0.89, "depth": 0.78, "plant_scale": 1.0,
                    "footprint": [0.175, 0.06], "label_anchor": [0.83, 0.825],
                },
                {
                    "x": 0.5, "y": 0.69, "depth": 0.26, "plant_scale": 0.82,
                    "footprint": [0.145, 0.05], "label_anchor": [0.5, 0.585],
                },
                {
                    "x": 0.24, "y": 0.72, "depth": 0.3, "plant_scale": 0.86,
                    "footprint": [0.145, 0.052], "label_anchor": [0.13, 0.625],
                },
                {
                    "x": 0.76, "y": 0.72, "depth": 0.3, "plant_scale": 0.86,
                    "footprint": [0.145, 0.052], "label_anchor": [0.87, 0.625],
                },
                {
                    "x": 0.5, "y": 0.92, "depth": 0.9, "plant_scale": 1.04,
                    "footprint": [0.185, 0.064], "label_anchor": [0.5, 0.835],
                },
            ]
        },
    },)
    data = HomeWidgetData(**{
        **base.__dict__,
        "scene_items": seed,
        "garden_overlay_url": "/_addons/123/assets/terrace.svg",
    })

    html = render_home_widget(HomeWidgetSnapshot(request_id=5, phase="success", data=data))

    assert 'class="ag-home__terrace"' not in html
    assert 'class="ag-home__scenery-layer"' in html
    assert "terrace.svg" in html
    assert 'class="ag-home__seedling-cue"' not in html
    assert "🌱" not in html


def test_home_does_not_draw_a_duplicate_soil_ellipse_over_empty_beds() -> None:
    base = _sample_data()
    placement = {
        "layout_profiles": {
            "home": {
                "focal_point": [0.5, 0.82],
                "bed_anchors": [
                    {"x": 0.4, "y": 0.5, "footprint": [0.2, 0.08]},
                    {"x": 0.6, "y": 0.5, "footprint": [0.2, 0.08]},
                ],
            },
        },
    }
    data = HomeWidgetData(**{
        **base.__dict__,
        "background_placement": placement,
        "unlocked_slots": 2,
    })

    html = render_home_widget(HomeWidgetSnapshot(request_id=5, phase="success", data=data))

    assert 'class="ag-home__soil' not in html
    assert 'data-slot-index="0"' in html  # The real plant remains rendered.


def test_home_summary_panel_uses_compact_visual_hierarchy_at_each_breakpoint() -> None:
    html = render_home_widget(HomeWidgetSnapshot(request_id=5, phase="success", data=_sample_data()))

    assert "grid-template-columns:minmax(0,280px) 120px" in html
    assert "justify-content:space-between" in html
    assert "gap:16px" in html
    assert "#ag-home-root button,.ag-home__open" in html
    assert '<div class="ag-home__metrics"' not in html
    assert "height:136px" in html
    assert "height:4px" in html
    assert "width:min(100%,280px)" in html
    assert "filter:brightness(1.12)" in html
    assert "linear-gradient(90deg,rgba(4,14,11,.88)" in html
    assert "linear-gradient(180deg,rgba(4,14,11,.18)" in html
    assert "top:var(--ag-home-focal-y,var(--ag-preview-y,50%))" in html
    assert "@container (max-width:420px)" in html


def test_home_long_unbroken_plant_name_truncates_without_displacing_button() -> None:
    name = "FoxgloveFoxgloveFoxgloveFoxgloveFoxglove"
    assert len(name) == 40
    base = _sample_data()
    data = HomeWidgetData(**{
        **base.__dict__,
        "active_plant_name": name,
        "active_plant_stage": "flowering",
        "active_next_stage": "rare",
    })

    html = render_home_widget(HomeWidgetSnapshot(request_id=5, phase="success", data=data))

    assert f'title="{name} · Flowering · 30 / 500 toward Rare"' in html
    assert f'>{name} · Flowering · 30 / 500 toward Rare</span>' in html
    assert "text-overflow:ellipsis; white-space:nowrap" in html
    assert ".ag-home__support" in html
    assert "@container (max-width: 488px)" in html


def test_success_state_renders_stage_transition_message() -> None:
    base = _sample_data()
    data = HomeWidgetData(**{**base.__dict__, "stage_transition_message": "Your Rose reached Flowering!"})
    html = render_home_widget(HomeWidgetSnapshot(request_id=5, phase="success", data=data))

    assert 'data-testid="home-stage-up"' in html
    assert "Your Rose reached Flowering!" in html
    assert html.index('class="ag-home__body"') < html.index('data-testid="home-stage-up"')
    assert html.index('data-testid="home-stage-up"') < html.index('class="ag-home__details home-summary-panel"')
    assert "overflow-wrap: anywhere" in html


def test_home_summary_has_one_keyboard_reachable_explicit_action() -> None:
    html = render_home_widget(HomeWidgetSnapshot(request_id=5, phase="success", data=_sample_data()))

    assert 'data-tooltip=' not in html
    assert 'role="tooltip"' not in html
    assert 'role="region"' in html
    assert 'role="button" tabindex="0"' not in html
    assert "event.key==='Enter'||event.key===' '" not in html
    assert html.count("onclick=") == 1
    assert html.count('data-testid="home-open"') == 1


def test_home_surface_occlusion_is_behind_plants() -> None:
    base = _sample_data()
    data = HomeWidgetData(**{
        **base.__dict__,
        "scene_items": ({
            **base.scene_items[0],
            "background_placement": {
                "layout_profiles": {
                    "home": {"focal_point": [0.5, 0.82]},
                },
                "surface_profile": {
                    "variants": {
                        "home": {
                            "url": "/_addons/123/assets/garden.webp",
                            "occlusion_url": "/_addons/123/assets/garden_occlusion.webp",
                        },
                    },
                },
            },
        },),
    })
    html = render_home_widget(HomeWidgetSnapshot(request_id=5, phase="success", data=data))

    art = html[html.index('class="ag-home__art"'):]
    assert art.index('class="ag-home__occlusion"') < art.index('class="ag-home__plant"')
    assert ".ag-home__occlusion { position:absolute; inset:0; z-index:3" in html


def test_home_bedless_planter_contract_replaces_every_legacy_bed_layer() -> None:
    base = _sample_data()
    manifest = json.loads(
        (
            Path(__file__).parents[1]
            / "ankigarden"
            / "assets"
            / "manifest.json"
        ).read_text(encoding="utf-8")
    )
    background_placement = next(
        row["placement"]
        for row in manifest["assets"]
        if row.get("asset_id") == "bg_verdant_twilight_any_soil_master_v6"
    )
    profile = background_placement["surface_profile"]
    for variant_name, variant in profile["planter_family"]["variants"].items():
        variant["url"] = f"/_addons/123/planters/{variant_name}.webp"
        variant["foreground_url"] = (
            f"/_addons/123/planters/{variant_name}-foreground.webp"
        )
    profile["variants"]["home"]["url"] = "/_addons/123/backgrounds/bedless-home.webp"
    profile["variants"]["home"]["occlusion_url"] = "/_addons/123/backgrounds/legacy-bed-overlay.webp"
    profile["variants"]["home"]["occlusion_layer_urls"] = {
        "rear": "/_addons/123/backgrounds/legacy-rear.webp",
        "front": "/_addons/123/backgrounds/legacy-front.webp",
    }
    scene_items = tuple(
        {
            "slot_index": slot,
            "name": f"Plant {slot + 1}",
            "stage": "sprout",
            "url": f"/_addons/123/plants/plant-{slot + 1}.webp",
            "placement": {"visible_bounds": [0.1, 0.05, 0.8, 0.9], "base_type": "pot"},
        }
        for slot in (0, 2, 4)
    )
    data = HomeWidgetData(
        **{
            **base.__dict__,
            "scene_items": scene_items,
            "background_placement": background_placement,
        }
    )

    html = render_home_widget(
        HomeWidgetSnapshot(request_id=6, phase="success", data=data)
    )
    art = html[html.index('class="ag-home__art"'):]

    assert art.count('class="ag-home__planter ag-home__planter--base"') == 6
    assert art.count('class="ag-home__planter ag-home__planter--foreground"') == 6
    assert art.count('class="ag-home__planter-fallback ag-home__planter-fallback--base"') == 6
    assert art.count('class="ag-home__planter-fallback ag-home__planter-fallback--foreground"') == 6
    assert art.count("var f=this.nextElementSibling;if(f){f.style.display='block';}") == 12
    assert art.count('data-planter-band="far"') == 4
    assert art.count('data-planter-band="middle"') == 4
    assert art.count('data-planter-band="near"') == 4
    assert "legacy-bed-overlay.webp" not in art
    assert "legacy-rear.webp" not in art
    assert "legacy-front.webp" not in art
    assert 'class="ag-home__occlusion"' not in art
    far_plant = 'src="/_addons/123/plants/plant-1.webp"'
    middle_plant = 'src="/_addons/123/plants/plant-3.webp"'
    near_plant = 'src="/_addons/123/plants/plant-5.webp"'
    assert art.index('data-planter-band="far"') < art.index(far_plant)
    assert art.index(far_plant) < art.index('data-planter-band="middle"')
    assert art.index('data-planter-band="middle"') < art.index(middle_plant)
    assert art.index(middle_plant) < art.index('data-planter-band="near"')
    assert art.index('data-planter-band="near"') < art.index(near_plant)


def test_success_state_is_garden_wide_and_does_not_duplicate_selected_plant_details() -> None:
    base = _sample_data()
    html = render_home_widget(HomeWidgetSnapshot(request_id=6, phase="success", data=base))

    assert 'data-testid="home-focus"' not in html
    assert '<h2 class="ag-home__focus-name" data-testid="home-title" aria-label="My Garden"' in html
    assert "Study garden" not in html
    assert "Your garden</" not in html
    assert "A quiet view of your current garden" not in html
    assert "species ·" not in html
    assert "beds" not in html
    assert "reviews remaining" not in html
    assert "Fertilizer:" not in html
    assert ".ag-home__focus-name" in html
    assert "text-overflow:ellipsis" in html
    assert "white-space:nowrap" in html


def test_compact_preview_omits_reward_metrics_from_visible_and_accessible_copy() -> None:
    base = _sample_data()
    html = render_home_widget(HomeWidgetSnapshot(request_id=6, phase="success", data=base))

    assert "12 today" not in html
    assert "7-day streak" not in html
    assert "35 coins" not in html
    assert "Today" not in html
    assert "Streak" not in html
    assert "Garden Coins" not in html
    assert 'data-testid="home-today-answers"' not in html
    assert 'data-testid="home-streak"' not in html
    assert 'data-testid="home-currency"' not in html
    assert 'data-testid="home-accessible-summary"' not in html
    assert 'data-testid="home-reward-progress"' not in html
    assert "data-tooltip" not in html
    assert html.count('data-testid="home-open"') == 1


def test_zero_day_streak_does_not_change_compact_preview_copy() -> None:
    base = _sample_data()
    data = HomeWidgetData(**{
        **base.__dict__,
        "streak_days": 0,
        "streak_bonus_percent": 0,
        "next_streak_day": 1,
        "next_streak_bonus_percent": 0,
    })

    html = render_home_widget(HomeWidgetSnapshot(request_id=6, phase="success", data=data))

    assert "0-day streak" not in html
    assert "+0% Growth" not in html
    assert "at day 1" not in html


def test_day_one_streak_does_not_change_compact_preview_copy() -> None:
    base = _sample_data()
    data = HomeWidgetData(**{
        **base.__dict__,
        "streak_days": 1,
        "streak_bonus_percent": 0,
        "next_streak_day": 7,
        "next_streak_bonus_percent": 5,
    })

    html = render_home_widget(HomeWidgetSnapshot(request_id=6, phase="success", data=data))

    assert "1-day streak" not in html
    assert "+0% Growth" not in html


def test_large_streak_and_coin_values_never_leak_into_compact_preview() -> None:
    base = _sample_data()

    for streak_days, coins in ((1, 1), (749, 0), (1_234, 9_999), (9_999, 54_321)):
        data = HomeWidgetData(**{
            **base.__dict__,
            "streak_days": streak_days,
            "garden_currency": coins,
        })
        html = render_home_widget(HomeWidgetSnapshot(request_id=6, phase="success", data=data))

        assert f"{streak_days:,}-day streak" not in html
        assert f"{coins:,} coins" not in html
        assert 'data-testid="home-streak"' not in html
        assert 'data-testid="home-currency"' not in html


def test_long_preview_values_keep_full_accessible_names_and_responsive_rail() -> None:
    base = _sample_data()
    garden_name = "A Very Long Garden Name That Must Not Move The Open Button"
    plant_name = "Japanese Maple With An Extra Long Generated Name"
    data = HomeWidgetData(**{
        **base.__dict__,
        "garden_name": garden_name,
        "active_plant_name": plant_name,
        "active_plant_stage": "rare",
        "active_growth_points": 50_000,
        "active_stage_points": 50_000,
        "active_stage_goal": 50_000,
        "active_next_stage": "",
        "active_fully_grown": True,
        "streak_days": 365,
        "garden_currency": 54_321,
    })

    html = render_home_widget(HomeWidgetSnapshot(request_id=7, phase="success", data=data))

    assert f'aria-label="{garden_name}"' in html
    assert f'title="{plant_name} · Rare · 50,000 total Growth"' in html
    assert "365-day streak" not in html
    assert "54,321 coins" not in html
    assert "text-overflow:ellipsis" in html


def test_home_has_one_action_and_currency_unlocks_stay_in_dashboard() -> None:
    base = _sample_data()
    html = render_home_widget(HomeWidgetSnapshot(request_id=7, phase="success", data=base))

    assert 'data-testid="home-milestone"' not in html
    assert "Open garden to claim it" not in html
    assert html.count('data-testid="home-open"') == 1


def test_home_preview_never_exposes_scene_landmark_actions() -> None:
    base = _sample_data()
    scene_items = ({
        **base.scene_items[0],
        "background_placement": {
            "surface_profile": {
                "landmarks": [{
                    "landmark_id": "nursery_entrance",
                    "action_id": "garden.nursery.open",
                    "label": "Nursery",
                    "tooltip": "Open nursery",
                }],
            },
        },
    },)
    data = HomeWidgetData(**{**base.__dict__, "scene_items": scene_items})

    html = render_home_widget(HomeWidgetSnapshot(request_id=8, phase="success", data=data))

    assert 'data-testid="home-scene" aria-hidden="true"' in html
    assert "garden.nursery.open" not in html
    assert "data-landmark" not in html
    assert "Open nursery" not in html
    assert html.count('data-testid="home-open"') == 1


def test_success_data_uses_active_plant_stage_progress() -> None:
    state = SimpleNamespace(
        daily_stats=SimpleNamespace(
            growth_earned=30,
            base_growth=30,
            streak_bonus_growth=0,
            fertilizer_growth=0,
            bonus_growth=0,
            completed_due_cards=False,
        ),
        plants=[SimpleNamespace(
            plant_id="plant-1",
            name="Briar",
            growth_stage="sprout",
            growth_points=600,
        )],
        active_plant_id="plant-1",
        selected_weather="breeze",
        streak_days=6,
        currency_balance=25,
        total_reviews=50,
        unlocked_slots=2,
        achievements={
            "streak_7": Achievement(
                achievement_id="streak_7",
                name="7-Day Anki Streak",
                description="Reach a 7-day active Anki streak.",
                progress=6 / 7,
            ),
            "retention_90": Achievement(
                achievement_id="retention_90",
                name="Clear Recall",
                description="Finalized compound achievement",
                progress=1.0,
            ),
        },
    )

    data = build_home_widget_success_data(state=state, reviews_today=3, scene_items=[])
    html = render_home_widget(HomeWidgetSnapshot(request_id=9, phase="success", data=data))

    assert data.active_plant_name == "Briar"
    assert data.active_stage_points == 100
    assert data.active_stage_goal == 2_000
    assert data.active_next_stage == "young"
    assert 'data-testid="home-support" title="Briar · Sprout · 100 / 2,000 toward Young"' in html
    assert 'data-testid="home-growth-progress"' in html
    assert ".ag-home__growth-track {\n  position:relative;" in html
    assert ".ag-home__growth-track > span {\n  display:block;\n  position:absolute;" in html
    assert "\n  left:0;\n  width:var(--ag-growth-percent,0%);" in html
    assert 'data-testid="home-today-answers"' not in html
    assert 'data-testid="home-nearest-achievement"' not in html
    assert "7-Day Anki Streak · 6 of 7" not in html
    assert "Clear Recall" not in html
    assert "Reward: +10 Garden Coins" not in html


def test_planted_starter_without_active_assignment_stays_distinct_from_nurtured() -> None:
    state = SimpleNamespace(
        daily_stats=SimpleNamespace(
            growth_earned=0,
            base_growth=0,
            streak_bonus_growth=0,
            fertilizer_growth=0,
            bonus_growth=0,
            completed_due_cards=False,
        ),
        plants=[SimpleNamespace(
            plant_id="starter-1",
            name="Briar",
            growth_stage="seed",
            growth_points=0,
            planted=True,
            slot_index=0,
        )],
        starter_selection_complete=True,
        active_plant_id=None,
        selected_weather="breeze",
        streak_days=0,
        currency_balance=0,
        total_reviews=0,
        unlocked_slots=1,
        garden_name="Willow Garden",
    )

    data = build_home_widget_success_data(
        state=state,
        reviews_today=0,
        scene_items=[],
    )
    html = render_home_widget(
        HomeWidgetSnapshot(request_id=10, phase="success", data=data)
    )

    assert data.starter_selected is True
    assert data.active_plant_name == ""
    assert data.starter_planted_not_nurtured is True
    assert data.planted_starter_name == "Briar"
    assert data.planted_starter_stage == "seed"
    assert (
        'data-testid="home-support" '
        'title="Briar · Seed · 0 / 500 toward Sprout"'
    ) in html
    assert "Planted starter" not in html
    assert 'data-testid="home-growth-progress"' in html
    assert "No nurtured plant" not in html
    assert 'data-anki-garden-command="anki-garden:open"' in html
    assert 'data-anki-garden-command="anki-garden:choose-starter"' not in html


def test_home_handles_no_nurtured_plant_without_inventing_progress() -> None:
    base = _sample_data()
    data = HomeWidgetData(**{
        **base.__dict__,
        "active_plant_name": "",
        "active_plant_stage": "",
        "active_growth_points": 0,
        "active_stage_points": 0,
        "active_stage_goal": 0,
        "active_next_stage": "",
    })

    html = render_home_widget(HomeWidgetSnapshot(request_id=10, phase="success", data=data))

    assert 'data-testid="home-support" title=""' in html
    assert "Choose a plant to begin growing." not in html
    assert 'data-testid="home-growth-bar"' not in html


def test_fully_grown_active_plant_has_complete_progress() -> None:
    base = _sample_data()
    data = HomeWidgetData(**{
        **base.__dict__,
        "active_plant_name": "Clover",
        "active_plant_stage": "rare",
        "active_growth_points": 50_000,
        "active_stage_points": 0,
        "active_stage_goal": 0,
        "active_next_stage": "",
        "active_fully_grown": True,
    })

    html = render_home_widget(HomeWidgetSnapshot(request_id=11, phase="success", data=data))

    assert 'data-testid="home-support" title="Clover · Rare · 50,000 total Growth"' in html
    assert "Clover · Rare · 50,000 total Growth" in html
    assert 'data-testid="home-growth-progress"' in html


def test_scene_preserves_depth_order_without_scenic_watering_can() -> None:
    base = _sample_data()
    plants = (
        {"slot_index": 0, "name": "Rose", "stage": "flowering", "url": "rose.svg", "is_active": True},
        {"slot_index": 1, "name": "Lavender", "stage": "young", "url": "lavender.png"},
    )
    data = HomeWidgetData(**{
        **base.__dict__,
        "scene_items": plants,
        "nurtured_marker_url": "/_addons/123/assets/nurtured_marker.webp",
        "nurtured_marker_spout_right_url": (
            "/_addons/123/assets/nurtured_marker_spout_right.webp"
        ),
    })

    html = render_home_widget(HomeWidgetSnapshot(request_id=8, phase="success", data=data))

    assert "z-index:0" not in html
    assert "ag-home__plant--focus" not in html
    assert "ag-home__contact--focus" not in html
    assert "animation:none !important; transition:none !important" in html
    assert "ag-home__focus-marker" not in html
    assert ">★</span>" not in html
    assert 'data-testid="home-nurturing-marker"' not in html
    assert 'data-testid="home-nurturing-marker-fallback"' not in html
    assert 'data-testid="home-nurturing-marker-shadow"' not in html
    assert 'class="ag-home__marker-layer"' not in html
    assert "/_addons/123/assets/nurtured_marker.webp" not in html
    assert "/_addons/123/assets/nurtured_marker_spout_right.webp" not in html
    assert 'data-active-slot="0"' in html
    assert "Watering can:" not in html


def test_home_preview_omits_watering_can_for_each_nurtured_slot() -> None:
    base = _sample_data()
    manifest = json.loads(
        (
            Path(__file__).parents[1]
            / "ankigarden"
            / "assets"
            / "manifest.json"
        ).read_text(encoding="utf-8")
    )
    background_placement = next(
        row["placement"]
        for row in manifest["assets"]
        if row.get("asset_id") == "bg_verdant_twilight_any_soil_master_v6"
    )
    assets = [
        row for row in manifest["assets"]
        if row.get("category") == "plants"
        and isinstance(row.get("placement"), dict)
    ][:6]
    assert len(assets) == 6

    for active_slot in range(6):
        plants = tuple(
            {
                "slot_index": slot,
                "name": f"Plant {slot + 1}",
                "stage": asset["slot"]["stage"],
                "url": f"/_addons/123/plants/plant-{slot + 1}.webp",
                "placement": asset["placement"],
                "is_active": slot == active_slot,
            }
            for slot, asset in enumerate(assets)
        )
        data = HomeWidgetData(**{
            **base.__dict__,
            "scene_items": plants,
            "background_placement": background_placement,
            "nurtured_marker_url": "/_addons/123/assets/nurtured_marker.webp",
            "nurtured_marker_spout_right_url": (
                "/_addons/123/assets/nurtured_marker_spout_right.webp"
            ),
        })

        html = render_home_widget(
            HomeWidgetSnapshot(
                request_id=90 + active_slot,
                phase="success",
                data=data,
            )
        )

        for forbidden in (
            'data-testid="home-nurturing-marker"',
            'data-testid="home-nurturing-marker-fallback"',
            'data-testid="home-nurturing-marker-shadow"',
            'class="ag-home__marker-layer"',
            "data-marker-slot=",
            "/_addons/123/assets/nurtured_marker.webp",
            "/_addons/123/assets/nurtured_marker_spout_right.webp",
        ):
            assert forbidden not in html
        expected_band = ("far", "middle", "near")[active_slot // 2]
        expected_side = "left" if active_slot % 2 == 0 else "right"
        expected_focal_y = ("70.0", "40.0", "10.0")[active_slot // 2]
        assert f'data-active-slot="{active_slot}"' in html
        assert f'data-active-band="{expected_band}"' in html
        assert f'data-active-side="{expected_side}"' in html
        assert f"--ag-home-focal-y:{expected_focal_y}%" in html


def test_home_preview_omits_watering_can_fallback_without_asset_urls() -> None:
    base = _sample_data()
    plants = (
        {
            "slot_index": 0,
            "name": "Rose",
            "stage": "seed",
            "url": "rose.svg",
            "is_active": True,
        },
    )
    data = HomeWidgetData(**{
        **base.__dict__,
        "scene_items": plants,
    })

    html = render_home_widget(
        HomeWidgetSnapshot(request_id=81, phase="success", data=data)
    )

    assert 'data-testid="home-nurturing-marker-fallback"' not in html
    assert 'data-testid="home-nurturing-marker"' not in html
    assert 'data-testid="home-nurturing-marker-shadow"' not in html
    assert 'class="ag-home__marker-layer"' not in html


def test_scene_uses_readable_fallback_when_plant_asset_is_missing() -> None:
    base = _sample_data()
    plants = ({"slot_index": 0, "name": "Rose", "stage": "flowering", "url": ""},)
    data = HomeWidgetData(**{**base.__dict__, "scene_items": plants})

    html = render_home_widget(HomeWidgetSnapshot(request_id=9, phase="success", data=data))

    assert 'class="ag-home__plant-fallback"' in html
    assert 'role="img" aria-label="Rose, Flowering"' in html
    assert '<span class="ag-home__fallback-label"><span>Rose</span>' in html
    assert '<span class="ag-home__fallback-stage">Flowering</span>' in html
    assert "🌼" not in html


def test_scene_recovers_from_browser_asset_load_errors_without_changing_geometry() -> None:
    base = _sample_data()
    html = render_home_widget(
        HomeWidgetSnapshot(request_id=10, phase="success", data=base)
    )

    assert 'class="ag-home__plant"' in html
    assert 'class="ag-home__plant-fallback"' in html
    assert "this.onerror=null;this.style.display='none';" in html
    assert "f.style.display='flex'" in html
    assert "t.style.display='none'" in html
    assert 'aria-hidden="true" style="left:' in html
    assert ";display:none\"><span class=\"ag-home__fallback-silhouette\"" in html
    assert (
        "linear-gradient(180deg,#244954 0%,#31594d 55%,"
        "#294a35 55%,#17332d 100%)"
    ) in html


def test_state_transitions_ignore_stale_requests_and_replace_displayed_data() -> None:
    controller = HomeWidgetStateController()

    request_1 = controller.begin_request()
    request_2 = controller.begin_request()

    stale_applied = controller.resolve_success(request_1, _sample_data(reviews_today=99, growth_earned=99, weather="sunny"))
    fresh_applied = controller.resolve_success(request_2, _sample_data(reviews_today=7, growth_earned=14, weather="breeze"))

    html = render_home_widget(controller.snapshot)

    assert stale_applied is False
    assert fresh_applied is True
    assert 'data-testid="home-reviews"' not in html
    assert 'data-testid="home-support" title="Moss · Seed · 14 / 500 toward Sprout"' in html
    assert "Moss · Seed · 99 / 500 toward Sprout" not in html

    refresh_request = controller.begin_request()
    assert refresh_request > request_2
    stale_html = render_home_widget(controller.snapshot)
    assert 'data-state="stale"' in stale_html
    assert 'data-testid="home-preview-status"' in stale_html
    assert "Moss · Seed · 14 / 500 toward Sprout" in stale_html
    assert "Refreshing…" in stale_html
    assert "--ag-scene-opacity:0.720" in stale_html
    assert '#ag-home-root[data-state="stale"] .ag-home__partial-message' in stale_html
    assert "top:52px" in stale_html


@pytest.mark.parametrize(
    ("consumer", "phase", "enabled", "expected_opacity"),
    (
        ("deck-browser", "loading", True, 1.0),
        ("overview", "empty", True, 1.0),
        ("first-run", "success", True, 1.0),
        ("active-plant", "stale", True, 0.72),
        ("settings", "error", True, 1.0),
        ("settings", "success", False, 0.46),
    ),
)
def test_shared_preview_matrix_preserves_scene_data_phase_and_unified_fade(
    consumer,
    phase,
    enabled,
    expected_opacity,
):
    scene_items = ({"plant_id": "moss", "slot_index": 2, "is_active": True},)
    preview = garden_preview_from_values(
        consumer=consumer,
        phase=phase,
        garden_name="The Long Moss and Moon Garden",
        active_plant_name="Moss",
        active_stage="young",
        selected_weather="gentle_rain",
        selected_scenery="spring",
        scene_items=scene_items,
        unlocked_slots=6,
        enabled=enabled,
        motion_enabled=False,
        status_text="Refreshing…" if phase == "stale" else "",
    )

    assert preview.consumer == consumer
    assert preview.phase == ("disabled" if not enabled else phase)
    assert preview.scene_items == scene_items
    assert preview.selected_weather == "gentle_rain"
    assert preview.selected_scenery == "spring"
    assert preview.scene_opacity == expected_opacity
    assert preview.motion_enabled is False
    assert preview.summary.count("Young") <= 1
    assert tuple(metric.metric_id for metric in preview.metrics) == (
        "today", "streak", "coins"
    )
    assert preview.action_label == "Open garden"
    assert preview.action_command == "home-open"
    assert preview.status_tone == {
        "loading": "info",
        "stale": "info",
        "error": "error",
        "disabled": "neutral",
    }.get(preview.phase, "neutral")


def test_retry_and_refresh_flow_replaces_previous_error_view() -> None:
    controller = HomeWidgetStateController()

    first = controller.begin_request()
    controller.resolve_error(first, "Temporary backend failure")
    error_html = render_home_widget(controller.snapshot)
    assert "Temporary backend failure" in error_html

    retry_request = controller.begin_request()
    loading_html = render_home_widget(controller.snapshot)
    assert 'data-state="loading"' in loading_html
    assert "Temporary backend failure" not in loading_html

    controller.resolve_success(retry_request, _sample_data(reviews_today=21, growth_earned=33, weather="gentle_rain"))
    success_html = render_home_widget(controller.snapshot)

    assert 'data-state="success"' in success_html
    assert 'data-testid="home-reviews"' not in success_html
    assert 'data-testid="home-support" title="Moss · Seed · 33 / 500 toward Sprout"' in success_html
    assert "Temporary backend failure" not in success_html
