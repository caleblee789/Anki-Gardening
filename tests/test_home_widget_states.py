import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ankigarden.ui.home_widget import (
    HomeWidgetData,
    HomeWidgetSnapshot,
    HomeWidgetStateController,
    render_home_widget,
)


def _sample_data(cards_today: int = 12, growth_earned: int = 30, weather: str = "sunny") -> HomeWidgetData:
    return HomeWidgetData(
        cards_today=cards_today,
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


def test_empty_state_renders_empty_message() -> None:
    html = render_home_widget(HomeWidgetSnapshot(request_id=0, phase="empty"))

    assert 'data-state="empty"' in html
    assert 'data-testid="home-empty"' in html


def test_recoverable_error_renders_retry_action() -> None:
    html = render_home_widget(HomeWidgetSnapshot(request_id=2, phase="error", error_message="Network timeout"))

    assert 'data-state="error"' in html
    assert "Network timeout" in html
    assert 'data-testid="home-retry"' in html


def test_partial_state_renders_available_data_and_error_banner() -> None:
    html = render_home_widget(
        HomeWidgetSnapshot(
            request_id=3,
            phase="partial",
            data=_sample_data(cards_today=5, weather="cloudy"),
            error_message="Achievements are temporarily unavailable",
        )
    )

    assert 'data-state="partial"' in html
    assert 'data-testid="home-partial-error"' in html
    assert "Cards today: 5" in html
    assert "Weather: Cloudy" in html


def test_success_state_renders_key_fields() -> None:
    html = render_home_widget(HomeWidgetSnapshot(request_id=4, phase="success", data=_sample_data()))

    assert 'data-state="success"' in html
    assert 'data-testid="home-cards">Cards today: 12' in html
    assert 'data-testid="home-health">Garden health: 84%' in html
    assert 'data-testid="home-growth">Study growth today: 30 of 220' in html
    assert html.count('data-testid="home-open"') == 1
    assert 'data-testid="home-refresh"' not in html


def test_success_state_uses_resolved_background_as_compact_scene() -> None:
    base = _sample_data()
    data = HomeWidgetData(**{**base.__dict__, "background_url": "/_addons/123/assets/garden.webp"})

    html = render_home_widget(HomeWidgetSnapshot(request_id=5, phase="success", data=data))

    assert 'data-testid="home-scene"' in html
    assert 'data-slot-index="0"' in html
    assert 'data-base-type="pot"' in html
    assert "garden.webp" in html
    assert "background-size: cover" in html


def test_success_state_renders_stage_transition_message() -> None:
    base = _sample_data()
    data = HomeWidgetData(**{**base.__dict__, "stage_transition_message": "Your Rose reached Flowering!"})
    html = render_home_widget(HomeWidgetSnapshot(request_id=5, phase="success", data=data))

    assert 'data-testid="home-stage-up"' in html
    assert "Your Rose reached Flowering!" in html


def test_success_state_renders_focus_and_milestone_progress() -> None:
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
    assert "Nurturing Rose" in html
    assert "42 growth points to the next stage" in html
    assert "receives 80% of growth earned from reviews" in html
    assert "150 reviews until your next plant choice" in html


def test_success_state_renders_ready_milestone_call_to_action() -> None:
    base = _sample_data()
    data = HomeWidgetData(**{**base.__dict__, "milestone_ready": True})

    html = render_home_widget(HomeWidgetSnapshot(request_id=7, phase="success", data=data))

    assert 'data-testid="home-milestone"' in html
    assert "Open Garden to claim it" in html


def test_scene_preserves_depth_order_and_marks_focus_plant() -> None:
    base = _sample_data()
    plants = (
        {"slot_index": 0, "name": "Rose", "stage": "flowering", "url": "rose.svg", "is_focus": True},
        {"slot_index": 1, "name": "Fern", "stage": "young", "url": "fern.svg"},
    )
    data = HomeWidgetData(**{**base.__dict__, "scene_items": plants})

    html = render_home_widget(HomeWidgetSnapshot(request_id=8, phase="success", data=data))

    assert "z-index:0" not in html
    assert 'aria-label="Nurtured plant"' in html
    assert "ag-home__plant--focus" in html
    assert ">Nurturing</span>" in html
    assert ">★</span>" not in html


def test_scene_uses_readable_fallback_when_plant_asset_is_missing() -> None:
    base = _sample_data()
    plants = ({"slot_index": 0, "name": "Rose", "stage": "flowering", "url": ""},)
    data = HomeWidgetData(**{**base.__dict__, "scene_items": plants})

    html = render_home_widget(HomeWidgetSnapshot(request_id=9, phase="success", data=data))

    assert 'class="ag-home__plant-fallback"' in html
    assert 'role="img" aria-label="Rose"' in html
    assert "🌼" in html


def test_state_transitions_ignore_stale_requests_and_replace_displayed_data() -> None:
    controller = HomeWidgetStateController()

    request_1 = controller.begin_request()
    request_2 = controller.begin_request()

    stale_applied = controller.resolve_success(request_1, _sample_data(cards_today=99, growth_earned=99, weather="sunny"))
    fresh_applied = controller.resolve_success(request_2, _sample_data(cards_today=7, growth_earned=14, weather="breeze"))

    html = render_home_widget(controller.snapshot)

    assert stale_applied is False
    assert fresh_applied is True
    assert "Cards today: 7" in html
    assert "Study growth today: 14 of 220" in html
    assert "Cards today: 99" not in html


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

    controller.resolve_success(retry_request, _sample_data(cards_today=21, growth_earned=33, weather="gentle_rain"))
    success_html = render_home_widget(controller.snapshot)

    assert 'data-state="success"' in success_html
    assert "Cards today: 21" in success_html
    assert "Temporary backend failure" not in success_html
