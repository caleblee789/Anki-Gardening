"""Compile and independently validate the immutable v25 capture contract."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from .registry import REGISTRY, SurfaceRegistry


CONTRACT_VERSION = 25
CONTRACT_SCHEMA_VERSION = 1
SCENARIO_SCHEMA_VERSION = 2
CAPTURE_CONTRACT_PATH = Path(__file__).with_name("capture-contract-v25.json")


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
        issues.append("capture contract is not v25")
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
    required_surface_fields = {
        "id", "active", "retired_reason", "placements", "executor", "arguments",
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
        if raw.get("active") is True:
            active_ids.add(stable_id)
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
    if set(payload.get("retired_ids", ())) != retired_ids:
        issues.append("capture contract retired ID ledger is stale")

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
        topology = {"profile": profile, "groups": groups}
        if raw_profile.get("topology_digest") != hashlib.sha256(
            _canonical_bytes(topology)
        ).hexdigest():
            issues.append(f"profile {profile!r} topology digest is stale")
    full = profiles.get("full") if isinstance(profiles, dict) else None
    if isinstance(full, dict):
        full_ids = {
            str(label)
            for group in full.get("groups", ())
            if isinstance(group, dict)
            for label in group.get("labels", ())
        }
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
