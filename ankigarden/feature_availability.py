"""Internal release availability; never persisted as a learner preference.

Landmark contracts and saved progress remain intact while the feature is
dormant. Developer fixtures may explicitly enable it to exercise the backend.
"""

LANDMARKS_ENABLED = False


def landmarks_enabled() -> bool:
    return LANDMARKS_ENABLED


def growth_target_enabled(target_type: object) -> bool:
    return str(getattr(target_type, "value", target_type)) != "landmark" or landmarks_enabled()
