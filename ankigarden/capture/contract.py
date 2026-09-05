"""Compile and independently validate the immutable v27 capture contract."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Mapping

from .registry import REGISTRY, SurfaceRegistry


CONTRACT_VERSION = 27
CONTRACT_SCHEMA_VERSION = 2
SCENARIO_SCHEMA_VERSION = 3
CAPTURE_CONTRACT_PATH = Path(__file__).with_name("capture-contract-v27.json")

_IDENTITY_ID = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")
_EXPECTED_PROFILE_TOTALS = {
    "representative": (18, 2),
    "full": (36, 5),
}
_EXPECTED_ACTIVE_SURFACE_COUNT = 36
_RENAMED_SURFACE = "nursery-garden-decorations-scenery"
_RETIRED_SURFACE = "nursery-weather-scenery"
_SCENARIO_OVERRIDES: dict[str, tuple[str, int]] = {
    "starter-deck-browser-home": ("garden_first_run", 1),
    "garden-starter-picker": ("garden_first_run", 2),
    "garden-starter-selected": ("garden_first_run", 3),
    "garden-starter-placement": ("garden_first_run", 4),
    "fertilizer-active": ("fertilizer_queue", 1),
    "purchase-confirmation-fertilizer-queue": ("fertilizer_queue", 2),
    "reviewer-hud-expanded": ("reviewer_hud_base", 1),
    "session-summary-after-review": ("session_summary", 1),
    "sync-rewards-summary": ("sync_rewards", 1),
    "reviewer-reward-dock-bundle": ("reviewer_hud_full_bloom", 1),
    "growth-charge-use-ready": ("growth_charge_transition", 1),
    "growth-charge-success-stage-reward": ("growth_charge_transition", 2),
}


class ContractValidationError(ValueError):
    def __init__(self, issues: list[str] | tuple[str, ...]) -> None:
        self.issues = tuple(issues)
        super().__init__("; ".join(self.issues))


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def contract_digest(payload: Mapping[str, Any]) -> str:
    normalized = dict(payload)
    normalized.pop("contract_digest", None)
    return hashlib.sha256(_canonical_bytes(normalized)).hexdigest()


def _contact_sheet_page_count(groups: list[Any]) -> int:
    capacity = 2 * 5
    pages = 0
    used_rows = 0
    for group in groups:
        labels = group.get("labels", ()) if isinstance(group, dict) else ()
        if not isinstance(labels, list) or not labels:
            continue
        if len(labels) > capacity:
            if used_rows:
                pages += 1
                used_rows = 0
            pages += math.ceil(len(labels) / capacity)
            continue
        rows = math.ceil(len(labels) / 2)
        if used_rows and used_rows + rows > 5:
            pages += 1
            used_rows = 0
        used_rows += rows
    return pages + bool(used_rows)


def compile_contract(registry: SurfaceRegistry = REGISTRY) -> dict[str, Any]:
    profiles = {
        profile: {
            "groups": [
                {"name": name, "labels": list(labels)}
                for name, labels in registry.profile_groups(profile)
            ],
            "surface_count": len(registry.profile_labels(profile)),
            "contact_sheet_page_count": registry.profile_page_count(profile),
            "topology_digest": registry.profile_digest(profile),
        }
        for profile in registry.profile_names
    }
    payload: dict[str, Any] = {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "scenario_schema_version": SCENARIO_SCHEMA_VERSION,
        "profiles": profiles,
        "surface_count": len(registry.active_surfaces),
        "retired_ids": [surface.stable_id for surface in registry.retired_surfaces],
        "surfaces": [
            {
                **surface.as_dict(),
                "dependency_digest": registry.surface_digest(surface.stable_id),
            }
            for surface in registry.surfaces
        ],
    }
    payload["contract_digest"] = contract_digest(payload)
    validate_contract_payload(payload)
    return payload


def validate_contract_payload(payload: Mapping[str, Any]) -> None:
    """Validate compiled data without importing the Python surface registry."""

    issues: list[str] = []
    if payload.get("schema_version") != CONTRACT_SCHEMA_VERSION:
        issues.append("unsupported capture-contract schema version")
    if payload.get("contract_version") != CONTRACT_VERSION:
        issues.append("capture contract is not v27")
    if payload.get("scenario_schema_version") != SCENARIO_SCHEMA_VERSION:
        issues.append("unsupported scenario schema version")
    surfaces = payload.get("surfaces")
    profiles = payload.get("profiles")
    if not isinstance(surfaces, list) or not surfaces:
        issues.append("capture contract has no surfaces")
        surfaces = []
    if not isinstance(profiles, dict) or not profiles:
        issues.append("capture contract has no profiles")
        profiles = {}

    ids: list[str] = []
    active_ids: set[str] = set()
    retired_ids: set[str] = set()
    surface_by_id: dict[str, Mapping[str, Any]] = {}
    active_scenario_steps: dict[str, list[int]] = {}
    scenario_fixtures: dict[str, str] = {}
    scenario_seeded_checkpoints: dict[str, tuple[object, object, object]] = {}
    required_surface_fields = {
        "id", "active", "retired_reason", "placements", "executor", "arguments",
        "scenario_id", "fixture_id", "scenario_step",
        "renderer_family", "acquisition_policy", "allow_foreground_fallback",
        "checkpoint_cohort", "checkpoint", "prerequisites", "internal_setups",
        "readiness", "cleanup", "evidence_requirements", "owned_dependency_groups",
        "owned_module_dependencies", "state_contract", "dependency_digest",
    }
    for index, raw in enumerate(surfaces):
        if not isinstance(raw, dict):
            issues.append(f"surface {index} is not an object")
            continue
        missing = required_surface_fields.difference(raw)
        if missing:
            issues.append(
                f"surface {index} is missing fields: " + ", ".join(sorted(missing))
            )
            continue
        stable_id = raw.get("id")
        if not isinstance(stable_id, str) or not stable_id:
            issues.append(f"surface {index} has an invalid ID")
            continue
        ids.append(stable_id)
        surface_by_id[stable_id] = raw
        scenario_id = raw.get("scenario_id")
        fixture_id = raw.get("fixture_id")
        scenario_step = raw.get("scenario_step")
        if (
            not isinstance(scenario_id, str)
            or _IDENTITY_ID.fullmatch(scenario_id) is None
        ):
            issues.append(f"surface {stable_id!r} has an invalid scenario ID")
        if (
            not isinstance(fixture_id, str)
            or _IDENTITY_ID.fullmatch(fixture_id) is None
        ):
            issues.append(f"surface {stable_id!r} has an invalid fixture ID")
        elif isinstance(scenario_id, str) and fixture_id != f"{scenario_id}-v1":
            issues.append(f"surface {stable_id!r} has a noncanonical fixture ID")
        if type(scenario_step) is not int or scenario_step < 1:
            issues.append(f"surface {stable_id!r} has an invalid scenario step")
        if raw.get("active") is True:
            active_ids.add(stable_id)
            if isinstance(scenario_id, str) and isinstance(fixture_id, str):
                prior_fixture = scenario_fixtures.setdefault(scenario_id, fixture_id)
                if prior_fixture != fixture_id:
                    issues.append(
                        f"scenario {scenario_id!r} has multiple fixture IDs"
                    )
            internal_setups = raw.get("internal_setups")
            first_internal_setup = (
                internal_setups[0]
                if isinstance(internal_setups, list) and internal_setups
                else None
            )
            if isinstance(scenario_id, str):
                seeded_checkpoint = (
                    raw.get("checkpoint_cohort"),
                    raw.get("checkpoint"),
                    first_internal_setup,
                )
                prior_seeded_checkpoint = scenario_seeded_checkpoints.setdefault(
                    scenario_id,
                    seeded_checkpoint,
                )
                if prior_seeded_checkpoint != seeded_checkpoint:
                    issues.append(
                        f"scenario {scenario_id!r} has multiple seeded "
                        "checkpoint lineages"
                    )
            if isinstance(scenario_id, str) and type(scenario_step) is int:
                active_scenario_steps.setdefault(scenario_id, []).append(
                    scenario_step
                )
            expected_scenario, expected_step = _SCENARIO_OVERRIDES.get(
                stable_id,
                (stable_id, 1),
            )
            if scenario_id != expected_scenario or scenario_step != expected_step:
                issues.append(
                    f"surface {stable_id!r} has unexpected v27 scenario identity"
                )
            if raw.get("retired_reason"):
                issues.append(f"active surface {stable_id!r} has a retirement reason")
        elif raw.get("active") is False:
            retired_ids.add(stable_id)
            if not str(raw.get("retired_reason", "")).strip():
                issues.append(f"retired surface {stable_id!r} has no reason")
        else:
            issues.append(f"surface {stable_id!r} has invalid active state")
        digest = raw.get("dependency_digest")
        pixel = {
            "stable_id": stable_id,
            **{
                key: raw[key]
                for key in (
                    "scenario_id", "fixture_id", "scenario_step",
                    "executor", "arguments", "renderer_family", "acquisition_policy",
                    "allow_foreground_fallback", "checkpoint_cohort", "checkpoint",
                    "prerequisites", "internal_setups", "readiness", "cleanup",
                    "evidence_requirements", "owned_dependency_groups",
                    "owned_module_dependencies", "state_contract",
                )
            },
        }
        if digest != hashlib.sha256(_canonical_bytes(pixel)).hexdigest():
            issues.append(f"surface {stable_id!r} has a mismatched dependency digest")
    if len(ids) != len(set(ids)):
        issues.append("capture contract repeats a stable ID")
    if payload.get("surface_count") != len(active_ids):
        issues.append("capture contract active surface count is stale")
    if len(active_ids) != _EXPECTED_ACTIVE_SURFACE_COUNT:
        issues.append(
            f"v27 must contain exactly {_EXPECTED_ACTIVE_SURFACE_COUNT} active surfaces"
        )
    if set(payload.get("retired_ids", ())) != retired_ids:
        issues.append("capture contract retired ID ledger is stale")
    if _RETIRED_SURFACE not in retired_ids:
        issues.append(f"v27 must permanently retire {_RETIRED_SURFACE!r}")
    for scenario_id, steps in active_scenario_steps.items():
        if sorted(steps) != list(range(1, len(steps) + 1)):
            issues.append(
                f"scenario {scenario_id!r} steps are not unique and contiguous"
            )

    if set(profiles) != set(_EXPECTED_PROFILE_TOTALS):
        issues.append("v27 capture profiles must be representative and full")

    for profile, raw_profile in profiles.items():
        if not isinstance(profile, str) or not isinstance(raw_profile, dict):
            issues.append("capture profile entry is invalid")
            continue
        groups = raw_profile.get("groups")
        labels: list[str] = []
        if not isinstance(groups, list) or not groups:
            issues.append(f"profile {profile!r} has no groups")
            continue
        for group in groups:
            if not isinstance(group, dict) or not str(group.get("name", "")).strip():
                issues.append(f"profile {profile!r} has an invalid group")
                continue
            group_labels = group.get("labels")
            if not isinstance(group_labels, list) or not group_labels:
                issues.append(f"profile {profile!r} has an empty group")
                continue
            labels.extend(str(label) for label in group_labels)
        if len(labels) != len(set(labels)):
            issues.append(f"profile {profile!r} repeats a surface")
        if not set(labels).issubset(active_ids):
            issues.append(f"profile {profile!r} references inactive or unknown surfaces")
        position = {stable_id: index for index, stable_id in enumerate(labels)}
        for stable_id, dependent_position in position.items():
            raw_surface = surface_by_id.get(stable_id, {})
            for prerequisite in raw_surface.get("prerequisites", ()):
                prerequisite_position = position.get(str(prerequisite))
                if (
                    prerequisite_position is not None
                    and prerequisite_position >= dependent_position
                ):
                    issues.append(
                        f"profile {profile!r} places prerequisite "
                        f"{prerequisite!r} after dependent surface {stable_id!r}"
                    )
        if raw_profile.get("surface_count") != len(labels):
            issues.append(f"profile {profile!r} surface count is stale")
        expected_totals = _EXPECTED_PROFILE_TOTALS.get(profile)
        if expected_totals is not None and len(labels) != expected_totals[0]:
            issues.append(
                f"profile {profile!r} must contain exactly "
                f"{expected_totals[0]} surfaces"
            )
        page_count = _contact_sheet_page_count(groups)
        if raw_profile.get("contact_sheet_page_count") != page_count:
            issues.append(f"profile {profile!r} contact-sheet page count is stale")
        if expected_totals is not None and page_count != expected_totals[1]:
            issues.append(
                f"profile {profile!r} must produce exactly "
                f"{expected_totals[1]} contact-sheet pages"
            )
        topology = {"profile": profile, "groups": groups}
        if raw_profile.get("topology_digest") != hashlib.sha256(
            _canonical_bytes(topology)
        ).hexdigest():
            issues.append(f"profile {profile!r} topology digest is stale")
    full = profiles.get("full") if isinstance(profiles, dict) else None
    if isinstance(full, dict):
        full_labels = [
            str(label)
            for group in full.get("groups", ())
            if isinstance(group, dict)
            for label in group.get("labels", ())
        ]
        full_ids = set(full_labels)
        if full_ids != active_ids:
            issues.append("full profile does not exactly cover active surfaces")
    if payload.get("contract_digest") != contract_digest(payload):
        issues.append("capture contract digest is stale")
    if issues:
        raise ContractValidationError(issues)


def write_compiled_contract(
    path: Path = CAPTURE_CONTRACT_PATH,
    *,
    registry: SurfaceRegistry = REGISTRY,
) -> Path:
    payload = compile_contract(registry)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def load_compiled_contract(path: Path = CAPTURE_CONTRACT_PATH) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContractValidationError([f"could not read capture contract: {error}"]) from error
    if not isinstance(payload, dict):
        raise ContractValidationError(["capture contract root must be an object"])
    validate_contract_payload(payload)
    return payload


def contract_diff(
    previous: Mapping[str, Any],
    current: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    current = current or compile_contract()
    previous_surfaces = {
        str(item.get("id")): item
        for item in previous.get("surfaces", ())
        if isinstance(item, dict)
    }
    current_surfaces = {
        str(item.get("id")): item
        for item in current.get("surfaces", ())
        if isinstance(item, dict)
    }
    previous_ids = set(previous_surfaces)
    current_ids = set(current_surfaces)
    changed = sorted(
        stable_id for stable_id in previous_ids & current_ids
        if previous_surfaces[stable_id].get("dependency_digest")
        != current_surfaces[stable_id].get("dependency_digest")
    )
    reordered_profiles = sorted(
        profile for profile in set(previous.get("profiles", ())) & set(current.get("profiles", ()))
        if previous["profiles"][profile].get("topology_digest")
        != current["profiles"][profile].get("topology_digest")
    )
    return {
        "added": sorted(current_ids - previous_ids),
        "removed": sorted(previous_ids - current_ids),
        "changed": changed,
        "reordered_profiles": reordered_profiles,
        "unchanged": sorted((previous_ids & current_ids).difference(changed)),
    }
