import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ankigarden.ui.home_widget import (
    HomeWidgetData,
    HomeWidgetSnapshot,
    HomeWidgetStateController,
    render_home_widget,
)


def _sample_data(reviews_today: int = 12, growth_earned: int = 30, weather: str = "sunny") -> HomeWidgetData:
    return HomeWidgetData(
        reviews_today=reviews_today,
        health_ratio=0.84,
        growth_earned=growth_earned,
        growth_cap=220,
        streak_days=7,
        weather=weather,
        scene_items=({
            "slot_index": 0,
            "name": "Bonsai",
            "url": "/_addons/123/assets/bonsai.png",
            "placement": {"visible_bounds": [0.1, 0.05, 0.8, 0.9], "base_type": "pot"},
        },),
    )


def test_loading_state_renders_spinner_placeholder() -> None:
    html = render_home_widget(HomeWidgetSnapshot(request_id=1, phase="loading"))

    assert 'data-state="loading"' in html
    assert 'data-testid="home-loading"' in html
    assert 'role="status" aria-live="polite"' in html
    assert 'class="ag-home__state"' in html


def test_empty_state_renders_empty_message() -> None:
    html = render_home_widget(HomeWidgetSnapshot(request_id=0, phase="empty"))

    assert 'data-state="empty"' in html
    assert 'data-testid="home-empty"' in html
    assert 'role="region" aria-label="Anki Garden"' in html


def test_recoverable_error_renders_retry_action() -> None:
    html = render_home_widget(HomeWidgetSnapshot(request_id=2, phase="error", error_message="Network timeout"))

    assert 'data-state="error"' in html
    assert "Network timeout" in html
    assert 'data-testid="home-retry"' in html
    assert 'role="alert"' in html
    assert 'aria-label="Retry loading Anki Garden"' in html


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
    assert 'data-testid="home-reviews">5</div>' in html
    assert "Weather: Cloudy" not in html


def test_success_state_renders_key_fields() -> None:
    html = render_home_widget(HomeWidgetSnapshot(request_id=4, phase="success", data=_sample_data()))

    assert 'data-state="success"' in html
    assert 'data-testid="home-reviews">12</div>' in html
    assert 'data-testid="home-vitality">84%</div>' in html
    assert 'data-testid="home-growth">30 of 220</div>' in html
    assert html.count('data-testid="home-open"') == 1
    assert 'data-testid="home-refresh"' not in html
    assert 'role="progressbar"' in html
    assert 'aria-valuemin="0" aria-valuemax="220" aria-valuenow="30"' in html
    assert 'aria-label="Open Garden"' in html
    assert "grid-template-columns:minmax(420px,62%) minmax(310px,38%)" in html
    assert "@media (max-width: 480px)" in html
    assert html.count('class="ag-home__metric"') == 3
    assert 'class="ag-home__header"' not in html
    assert 'class="ag-home__identity-row"' in html
    assert "grid-template-columns:repeat(3,minmax(0,1fr))" in html
    assert 'class="ag-home__tooltip" role="tooltip" hidden' in html
    assert ' title=' not in html
    assert "min-height:176px" not in html.split(".ag-home__body", 1)[1].split("}", 1)[0]
    assert "min-height:44px" in html
    assert "min-width:132px" in html
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


def test_success_state_renders_stage_transition_message() -> None:
    base = _sample_data()
    data = HomeWidgetData(**{**base.__dict__, "stage_transition_message": "Your Rose reached Flowering!"})
    html = render_home_widget(HomeWidgetSnapshot(request_id=5, phase="success", data=data))

    assert 'data-testid="home-stage-up"' in html
    assert "Your Rose reached Flowering!" in html


def test_success_state_renders_compact_focus_identity_without_dashboard_explanations() -> None:
    base = _sample_data()
    data = HomeWidgetData(**{
        **base.__dict__,
        "focus_plant_name": "Rose",
        "focus_stage": "young",
        "focus_points_remaining": 42,
        "next_milestone": 250,
        "total_reviews": 100,
    })

    html = render_home_widget(HomeWidgetSnapshot(request_id=6, phase="success", data=data))

    assert 'data-testid="home-focus"' in html
    assert '<div class="ag-home__focus-name">Rose</div>' in html
    assert '<div class="ag-home__focus-stage">Young</div>' in html
    assert "42 growth points to the next stage" not in html
    assert "receives 80% of growth earned from reviews" not in html
    assert "reviews until your next plant choice" not in html
    assert "-webkit-line-clamp:2" in html


def test_rare_stage_has_focus_visible_custom_tooltip() -> None:
    base = _sample_data()
    data = HomeWidgetData(**{**base.__dict__, "focus_plant_name": "Rose", "focus_stage": "rare"})
    html = render_home_widget(HomeWidgetSnapshot(request_id=6, phase="success", data=data))
    assert 'data-tooltip="This plant has reached the final Rare growth stage." tabindex="0"' in html
    assert html.count('data-testid="home-open"') == 1


def test_ready_milestone_stays_on_dashboard_and_does_not_add_a_second_home_action() -> None:
    base = _sample_data()
    data = HomeWidgetData(**{**base.__dict__, "milestone_ready": True})

    html = render_home_widget(HomeWidgetSnapshot(request_id=7, phase="success", data=data))

    assert 'data-testid="home-milestone"' not in html
    assert "Open Garden to claim it" not in html
    assert html.count('data-testid="home-open"') == 1


def test_scene_preserves_depth_order_without_animating_or_highlighting_nurtured_plant() -> None:
    base = _sample_data()
    plants = (
        {"slot_index": 0, "name": "Rose", "stage": "flowering", "url": "rose.svg", "is_focus": True},
        {"slot_index": 1, "name": "Fern", "stage": "young", "url": "fern.svg"},
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
    assert 'role="img" aria-label="Rose"' in html
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
    assert 'data-testid="home-reviews">7</div>' in html
    assert 'data-testid="home-growth">14 of 220</div>' in html
    assert 'data-testid="home-reviews">99</div>' not in html


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
    assert 'data-testid="home-reviews">21</div>' in success_html
    assert "Temporary backend failure" not in success_html
