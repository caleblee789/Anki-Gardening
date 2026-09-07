"""Internal release availability; never persisted as a learner preference.

Deferred progression contracts and saved progress remain intact. Developer
fixtures may explicitly enable them to exercise the retained backend.
"""

LANDMARKS_ENABLED = False
MASTERY_ENABLED = False
GARDEN_LEGACY_ENABLED = False


def landmarks_enabled() -> bool:
    return LANDMARKS_ENABLED


def mastery_enabled() -> bool:
    return MASTERY_ENABLED


def garden_legacy_enabled() -> bool:
    return GARDEN_LEGACY_ENABLED


def growth_target_enabled(target_type: object) -> bool:
    kind = str(getattr(target_type, "value", target_type))
    return {
        "landmark": landmarks_enabled(),
        "mastery": mastery_enabled(),
        "legacy": garden_legacy_enabled(),
    }.get(kind, True)
