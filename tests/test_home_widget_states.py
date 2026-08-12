import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ankigarden.ui.home_widget import (
    HomeWidgetData,
    HomeWidgetSnapshot,
    HomeWidgetStateController,
    build_home_widget_success_data,
    render_home_widget,
)


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


def test_loading_state_renders_spinner_placeholder() -> None:
    html = render_home_widget(HomeWidgetSnapshot(request_id=1, phase="loading"))

    assert 'data-state="loading"' in html
    assert 'data-testid="home-loading"' in html
    assert 'role="status" aria-live="polite"' in html
    assert 'class="ag-home__state"' in html
    assert "Loading overview…" in html


def test_empty_state_renders_empty_message() -> None:
    html = render_home_widget(HomeWidgetSnapshot(request_id=0, phase="empty"))

    assert 'data-state="empty"' in html
    assert 'data-testid="home-empty"' in html
    assert 'role="region" aria-label="Anki Garden"' in html
    assert "Ready to grow" in html


def test_recoverable_error_renders_retry_action() -> None:
    html = render_home_widget(HomeWidgetSnapshot(request_id=2, phase="error", error_message="Network timeout"))

    assert 'data-state="error"' in html
    assert "Network timeout" in html
    assert 'data-testid="home-retry"' in html
    assert 'role="alert"' in html
    assert 'aria-label="Retry loading overview"' in html


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
    assert 'data-testid="home-active-name">Moss</div>' in html
    assert 'data-testid="home-reviews"' not in html
    assert "Weather: Cloudy" not in html


def test_success_state_renders_key_fields() -> None:
    html = render_home_widget(HomeWidgetSnapshot(request_id=4, phase="success", data=_sample_data()))

    assert 'data-state="success"' in html
    assert 'data-testid="home-reviews"' not in html
    assert 'data-testid="home-active-name">Moss</div>' in html
    assert 'data-testid="home-growth">30</span>' in html
    assert 'data-testid="home-currency">35</div>' in html
    assert 'data-testid="home-streak"><span class="ag-home__streak-number">7</span><span class="ag-home__streak-unit">days</span></div>' in html
    assert '<div class="ag-home__metric-label">Nurtured plant</div>' in html
    assert '<div class="ag-home__growth-label">Growth</div>' in html
    assert '<span class="ag-home__growth-slash">/</span>' in html
    assert '<div class="ag-home__metric-label">Anki streak</div>' in html
    assert '<div class="ag-home__metric-label">Garden Coins</div>' in html
    assert '<span class="ag-home__metric-badge">+5% Growth</span>' in html
    assert '<div class="ag-home__metric-support">Next bonus: +10% at 14 days</div>' in html
    assert "study days in a row" in html
    assert "Vitality" not in html
    assert "Garden daily goal" not in html
    assert html.count('data-testid="home-open"') == 1
    assert 'data-testid="home-refresh"' not in html
    assert 'role="progressbar"' in html
    assert 'aria-label="Anki streak progress"' in html
    assert 'aria-valuemin="0" aria-valuemax="100" aria-valuenow="33"' in html
    assert 'aria-valuetext="7-day Anki streak; +5% Growth bonus. Next bonus: +10% at 14 days"' in html
    assert 'aria-label="Open Garden"' in html
    assert 'role="region" aria-label="Anki Garden"' in html
    assert '<div class="ag-home__eyebrow" aria-hidden="true">Anki Garden</div>' in html
    assert '<h2 class="ag-home__focus-name">My Garden</h2>' in html
    assert "max-width: 1480px" in html
    assert "grid-template-columns:minmax(440px,65%) minmax(340px,35%)" in html
    assert "@media (max-width: 480px)" in html
    assert html.count('tabindex="0" aria-label=') >= 3
    assert '<aside class="ag-home__details home-summary-panel">' in html
    assert '<header class="ag-home__identity-row summary-header">' in html
    assert ".ag-home__metrics { display:flex; flex-direction:column" in html
    assert '<div class="ag-home__metrics" role="group" aria-label="Garden summary">' in html
    assert 'nurtured-plant-summary' in html
    assert 'streak-metric' in html
    assert 'coins-metric' in html
    assert "summary-card" not in html
    assert 'class="ag-home__tooltip" role="tooltip" hidden' in html
    assert ' title=' not in html
    assert "min-height:176px" not in html.split(".ag-home__body", 1)[1].split("}", 1)[0]
    assert "min-height:42px" in html
    assert "min-width:120px" in html
    assert "this.disabled=true" in html
    assert "setTimeout" in html


def test_success_state_uses_resolved_background_as_compact_scene() -> None:
    base = _sample_data()
    data = HomeWidgetData(**{**base.__dict__, "background_url": "/_addons/123/assets/garden.webp"})

    html = render_home_widget(HomeWidgetSnapshot(request_id=5, phase="success", data=data))

    assert 'data-testid="home-scene"' in html
    assert 'data-slot-index="0"' in html
    assert 'data-base-type="pot"' in html
    assert "garden.webp" in html
    assert "background-size: cover" in html


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
    assert "terrace.svg" not in html
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

    assert ".ag-home__identity-row { display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:center; gap:12px; min-width:0; min-height:48px; }" in html
    assert ".ag-home__open { min-width:112px !important; min-height:40px !important" in html
    assert ".ag-home__metric--plant { min-height:0; border-color:rgba(125,174,132,.34)" in html
    assert ".ag-home__metric--streak,.ag-home__metric--coins { min-height:0; }" in html
    assert ".ag-home__metric--coins .ag-home__metric-value { color:#f2dda4; }" in html
    assert ".ag-home__metric:focus-visible" in html
    assert "outline:3px solid #e5f2a6" in html
    assert "outline-offset:-3px" in html
    assert ".ag-home__metric-label { min-width:0; color:#9fb9a8; font-size:12px" in html
    assert ".ag-home__metric-label::before" not in html
    assert ".ag-home__metric-badge {" in html and "font-size:12px" in html
    assert ".ag-home__growth-label { color:#9fb9a8; font-size:13px" in html
    assert ".ag-home__growth-value { margin-top:2px; color:#edf5ea; font-size:18px" in html
    assert ".ag-home__metric-support { margin-top:4px; color:#aebfb4; font-size:13.5px" in html
    assert "text-align:left" in html
    metrics_rule = html.split(".ag-home__metrics {", 1)[1].split("}", 1)[0]
    assert "display:flex" in metrics_rule
    assert "flex-direction:column" in metrics_rule
    assert "gap:10px" in metrics_rule
    assert "background:" not in metrics_rule
    assert ".ag-home__streak-value { display:flex; align-items:baseline; gap:6px" in html
    assert "font-variant-numeric:tabular-nums; white-space:nowrap" in html
    assert ".ag-home__streak-number { font-size:36px; }" in html
    assert ".ag-home__coins-value { margin-top:6px; font-size:32px" in html
    assert "height: 8px" in html
    assert "transition:background-color" not in html
    plant_markup = html.index('nurtured-plant-summary')
    metrics_markup = html.index('<div class="ag-home__metrics" role="group"')
    assert plant_markup < metrics_markup
    assert ".ag-home__scene {\n  position: relative;\n  width: 100%;\n  max-width: 100%;\n  min-width: 0;\n  min-height: 260px;" in html
    assert "aspect-ratio: 12 / 5" in html
    assert "@media (max-width: 900px)" in html
    assert "@media (max-width: 480px)" in html


def test_home_long_unbroken_plant_name_wraps_without_displacing_stage_badge() -> None:
    name = "FoxgloveFoxgloveFoxgloveFoxgloveFoxglove"
    assert len(name) == 40
    base = _sample_data()
    data = HomeWidgetData(**{
        **base.__dict__,
        "active_plant_name": name,
        "active_plant_stage": "flowering",
    })

    html = render_home_widget(HomeWidgetSnapshot(request_id=5, phase="success", data=data))

    value = (
        f'<div class="ag-home__metric-value ag-home__metric-value--plant" '
        f'data-testid="home-active-name">{name}</div>'
    )
    badge = '<span class="ag-home__metric-badge">Flowering</span>'
    assert value in html
    assert badge in html
    assert html.index(badge) < html.index(value)
    assert ".ag-home__metric-value { min-width:0; max-width:100%" in html
    assert ".ag-home__metric-value--plant { margin-top:6px; overflow:hidden;" in html
    assert "text-overflow:ellipsis; white-space:nowrap" in html
    assert ".ag-home__metric-badge { flex:0 0 auto;" in html
    for breakpoint in (900, 600, 480):
        assert f"@media (max-width: {breakpoint}px)" in html


def test_success_state_renders_stage_transition_message() -> None:
    base = _sample_data()
    data = HomeWidgetData(**{**base.__dict__, "stage_transition_message": "Your Rose reached Flowering!"})
    html = render_home_widget(HomeWidgetSnapshot(request_id=5, phase="success", data=data))

    assert 'data-testid="home-stage-up"' in html
    assert "Your Rose reached Flowering!" in html
    assert html.index('data-testid="home-stage-up"') < html.index('class="ag-home__body"')
    assert "overflow-wrap: anywhere" in html


def test_home_tooltip_chooses_an_above_viewport_position_when_needed() -> None:
    html = render_home_widget(HomeWidgetSnapshot(request_id=5, phase="success", data=_sample_data()))

    assert "maxTop=Math.max(margin,window.innerHeight-tip.offsetHeight-margin)" in html
    assert "above=r.top-tip.offsetHeight-gap" in html
    assert "window.addEventListener('resize'" in html


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


def test_success_state_is_garden_wide_and_does_not_duplicate_selected_plant_details() -> None:
    base = _sample_data()
    html = render_home_widget(HomeWidgetSnapshot(request_id=6, phase="success", data=base))

    assert 'data-testid="home-focus"' not in html
    assert '<h2 class="ag-home__focus-name">My Garden</h2>' in html
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


def test_streak_tooltip_stays_short_and_explains_its_effect() -> None:
    base = _sample_data()
    html = render_home_widget(HomeWidgetSnapshot(request_id=6, phase="success", data=base))
    assert "can add up to 25% Growth" in html
    assert "day 365" not in html
    assert html.count('data-testid="home-open"') == 1


def test_zero_day_streak_invites_study_without_a_zero_bonus_badge() -> None:
    base = _sample_data()
    data = HomeWidgetData(**{
        **base.__dict__,
        "streak_days": 0,
        "streak_bonus_percent": 0,
        "next_streak_day": 1,
        "next_streak_bonus_percent": 0,
    })

    html = render_home_widget(HomeWidgetSnapshot(request_id=6, phase="success", data=data))

    assert 'data-testid="home-streak"><span class="ag-home__streak-number">0</span><span class="ag-home__streak-unit">days</span></div>' in html
    assert "Study today to begin" in html
    assert 'aria-label="No Anki streak yet. Study today to start your streak."' in html
    assert "+0% Growth" not in html
    assert "at day 1" not in html
    assert "·" not in html


def test_day_one_streak_points_to_the_first_real_bonus() -> None:
    base = _sample_data()
    data = HomeWidgetData(**{
        **base.__dict__,
        "streak_days": 1,
        "streak_bonus_percent": 0,
        "next_streak_day": 7,
        "next_streak_bonus_percent": 5,
    })

    html = render_home_widget(HomeWidgetSnapshot(request_id=6, phase="success", data=data))

    assert 'data-testid="home-streak"><span class="ag-home__streak-number">1</span><span class="ag-home__streak-unit">day</span></div>' in html
    assert "Next bonus: +5% at 7 days" in html
    assert "+0% Growth" not in html
    assert 'aria-label="1-day Anki streak"' in html


def test_large_streak_and_coin_values_keep_number_units_and_balances_atomic() -> None:
    base = _sample_data()

    for streak_days, coins in ((749, 0), (1_234, 9_999), (9_999, 54_321)):
        data = HomeWidgetData(**{
            **base.__dict__,
            "streak_days": streak_days,
            "garden_currency": coins,
        })
        html = render_home_widget(HomeWidgetSnapshot(request_id=6, phase="success", data=data))

        assert (
            f'<span class="ag-home__streak-number">{streak_days:,}</span>'
            '<span class="ag-home__streak-unit">days</span>'
        ) in html
        assert f'data-testid="home-currency">{coins:,}</div>' in html
        assert ".ag-home__streak-value" in html
        assert ".ag-home__coins-value" in html
        assert "white-space:nowrap" in html
        assert "font-variant-numeric:tabular-nums" in html
        coin_label = html.index('<div class="ag-home__metric-label">Garden Coins</div>')
        coin_value = html.index(f'data-testid="home-currency">{coins:,}</div>')
        coin_support = html.index("For Nursery plants, items, and upgrades")
        assert coin_label < coin_value < coin_support
        assert "ag-home__coins-row" not in html


def test_home_has_one_action_and_currency_unlocks_stay_in_dashboard() -> None:
    base = _sample_data()
    html = render_home_widget(HomeWidgetSnapshot(request_id=7, phase="success", data=base))

    assert 'data-testid="home-milestone"' not in html
    assert "Open Garden to claim it" not in html
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
                    "tooltip": "Open Nursery",
                }],
            },
        },
    },)
    data = HomeWidgetData(**{**base.__dict__, "scene_items": scene_items})

    html = render_home_widget(HomeWidgetSnapshot(request_id=8, phase="success", data=data))

    assert 'aria-label="Garden preview. Open Garden to interact."' in html
    assert "garden.nursery.open" not in html
    assert "data-landmark" not in html
    assert "Open Nursery" not in html
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
        streak_days=7,
        currency_balance=25,
        total_reviews=50,
        unlocked_slots=2,
    )

    data = build_home_widget_success_data(state=state, reviews_today=3, scene_items=[])
    html = render_home_widget(HomeWidgetSnapshot(request_id=9, phase="success", data=data))

    assert data.active_plant_name == "Briar"
    assert data.active_stage_points == 100
    assert data.active_stage_goal == 2_000
    assert data.active_next_stage == "young"
    assert 'data-testid="home-active-name">Briar</div>' in html
    assert '100<span class="ag-home__growth-slash">/</span>2,000' in html
    assert '<div class="ag-home__growth-next">Young next</div>' in html
    assert 'aria-valuemax="2000" aria-valuenow="100"' in html


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

    assert 'data-testid="home-active-name">None selected</div>' in html
    assert "Open Garden to choose one." in html
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

    assert '<div class="ag-home__growth-next">Fully grown</div>' in html
    assert '<div class="ag-home__growth-value">50,000</div>' in html
    assert 'aria-label="Clover is fully grown"' in html
    assert 'data-testid="home-growth-bar" aria-hidden="true" style="width:100%"' in html


def test_scene_preserves_depth_order_without_animating_or_highlighting_nurtured_plant() -> None:
    base = _sample_data()
    plants = (
        {"slot_index": 0, "name": "Rose", "stage": "flowering", "url": "rose.svg", "is_active": True},
        {"slot_index": 1, "name": "Lavender", "stage": "young", "url": "lavender.png"},
    )
    data = HomeWidgetData(**{**base.__dict__, "scene_items": plants})

    html = render_home_widget(HomeWidgetSnapshot(request_id=8, phase="success", data=data))

    assert "z-index:0" not in html
    assert "ag-home__plant--focus" not in html
    assert "ag-home__contact--focus" not in html
    assert "animation:none !important; transition:none !important" in html
    assert "ag-home__focus-marker" not in html
    assert ">★</span>" not in html


def test_scene_uses_readable_fallback_when_plant_asset_is_missing() -> None:
    base = _sample_data()
    plants = ({"slot_index": 0, "name": "Rose", "stage": "flowering", "url": ""},)
    data = HomeWidgetData(**{**base.__dict__, "scene_items": plants})

    html = render_home_widget(HomeWidgetSnapshot(request_id=9, phase="success", data=data))

    assert 'class="ag-home__plant-fallback"' in html
    assert 'role="img" aria-label="Rose, Flowering"' in html
    assert '<span class="ag-home__fallback-label"><span>Rose</span>' in html
    assert '<span class="ag-home__fallback-stage">Flowering</span>' in html
    assert "·" not in html
    assert "🌼" not in html


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
    assert 'data-testid="home-growth">14</span>' in html
    assert 'data-testid="home-growth">99</span>' not in html


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
    assert 'data-testid="home-growth">33</span>' in success_html
    assert "Temporary backend failure" not in success_html
