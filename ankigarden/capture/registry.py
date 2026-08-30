"""Materialize and query the single v26 capture surface registry."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import replace
from typing import Iterable, Iterator, Mapping, Sequence

from ._surface_specs import SURFACE_ROWS
from .model import ProfilePlacement, SurfaceSpec


PROFILE_COLUMNS = 2
PROFILE_MAX_ROWS = 5
RELEASE_PROFILE = "full"


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _surface_from_row(row: Mapping[str, object]) -> SurfaceSpec:
    placements = tuple(
        ProfilePlacement(
            str(raw[0]),
            str(raw[1]),
            int(raw[2]),
            int(raw[3]),
            int(raw[4]),
        )
        for raw in row.get("placements", ())  # type: ignore[arg-type]
    )
    return SurfaceSpec(
        stable_id=str(row["id"]),
        scenario_id=str(row["scenario_id"]),
        fixture_id=str(row["fixture_id"]),
        scenario_step=int(row["scenario_step"]),
        active=bool(row["active"]),
        placements=placements,
        executor=str(row["executor"]),
        arguments=tuple(row.get("arguments", ())),  # type: ignore[arg-type]
        renderer_family=str(row["renderer_family"]),
        acquisition_policy=str(row["acquisition_policy"]),
        allow_foreground_fallback=bool(row["allow_foreground_fallback"]),
        checkpoint_cohort=str(row["checkpoint_cohort"]),
        checkpoint=str(row["checkpoint"]),
        prerequisites=tuple(str(value) for value in row.get("prerequisites", ())),  # type: ignore[arg-type]
        internal_setups=tuple(str(value) for value in row.get("internal_setups", ())),  # type: ignore[arg-type]
        readiness=tuple(str(value) for value in row.get("readiness", ())),  # type: ignore[arg-type]
        cleanup=tuple(str(value) for value in row.get("cleanup", ())),  # type: ignore[arg-type]
        evidence_requirements=tuple(
            str(value) for value in row.get("evidence_requirements", ())  # type: ignore[arg-type]
        ),
        owned_dependency_groups=tuple(
            str(value) for value in row.get("owned_dependency_groups", ())  # type: ignore[arg-type]
        ),
        owned_module_dependencies=tuple(
            str(value) for value in row.get("owned_module_dependencies", ())  # type: ignore[arg-type]
        ),
        state_contract=dict(row.get("state_contract", {})),  # type: ignore[arg-type]
        retired_reason=str(row.get("retired_reason", "")),
    )


class SurfaceRegistry:
    """Validated immutable collection with dynamic profile topology."""

    def __init__(self, surfaces: Iterable[SurfaceSpec]) -> None:
        self._surfaces = tuple(surfaces)
        self._by_id = {surface.stable_id: surface for surface in self._surfaces}
        self._validate()

    def _validate(self) -> None:
        if not self._surfaces:
            raise ValueError("capture registry cannot be empty")
        if len(self._by_id) != len(self._surfaces):
            raise ValueError("capture registry contains duplicate stable IDs")
        active_ids = {surface.stable_id for surface in self.active_surfaces}
        scenario_fixtures: dict[str, str] = {}
        scenario_seeded_checkpoints: dict[str, tuple[str, str, str]] = {}
        scenario_steps: dict[str, list[int]] = {}
        for surface in self.active_surfaces:
            fixture_id = scenario_fixtures.setdefault(
                surface.scenario_id,
                surface.fixture_id,
            )
            if fixture_id != surface.fixture_id:
                raise ValueError(
                    f"scenario {surface.scenario_id!r} has multiple fixture IDs"
                )
            seeded_checkpoint = (
                surface.checkpoint_cohort,
                surface.checkpoint,
                surface.internal_setups[0],
            )
            prior_seeded_checkpoint = scenario_seeded_checkpoints.setdefault(
                surface.scenario_id,
                seeded_checkpoint,
            )
            if prior_seeded_checkpoint != seeded_checkpoint:
                raise ValueError(
                    f"scenario {surface.scenario_id!r} has multiple seeded "
                    "checkpoint lineages"
                )
            scenario_steps.setdefault(surface.scenario_id, []).append(
                surface.scenario_step
            )
            unknown = set(surface.prerequisites).difference(active_ids)
            if unknown:
                raise ValueError(
                    f"surface {surface.stable_id!r} has unknown prerequisites: "
                    + ", ".join(sorted(unknown))
                )

        for scenario_id, steps in scenario_steps.items():
            if sorted(steps) != list(range(1, len(steps) + 1)):
                raise ValueError(
                    f"scenario {scenario_id!r} steps must be unique and contiguous"
                )

        for profile in self.profile_names:
            placements = self._placements(profile)
            orders = [placement.order for _surface, placement in placements]
            if orders != list(range(len(orders))):
                raise ValueError(f"profile {profile!r} orders must be contiguous")
            order_by_id = {
                surface.stable_id: placement.order
                for surface, placement in placements
            }
            for surface, placement in placements:
                for prerequisite in surface.prerequisites:
                    prerequisite_order = order_by_id.get(prerequisite)
                    if (
                        prerequisite_order is not None
                        and prerequisite_order >= placement.order
                    ):
                        raise ValueError(
                            f"profile {profile!r} places prerequisite "
                            f"{prerequisite!r} after dependent surface "
                            f"{surface.stable_id!r}"
                        )
            group_names: dict[int, str] = {}
            group_within: dict[int, list[int]] = {}
            for _surface, placement in placements:
                previous = group_names.setdefault(placement.group_order, placement.group)
                if previous != placement.group:
                    raise ValueError(f"profile {profile!r} reuses a group ordinal")
                group_within.setdefault(placement.group_order, []).append(
                    placement.within_group_order
                )
            if sorted(group_names) != list(range(len(group_names))):
                raise ValueError(f"profile {profile!r} group orders must be contiguous")
            for group_order, within in group_within.items():
                if within != list(range(len(within))):
                    raise ValueError(
                        f"profile {profile!r} group {group_order} orders must be contiguous"
                    )
        if RELEASE_PROFILE in self.profile_names and (
            set(self.profile_labels(RELEASE_PROFILE)) != active_ids
        ):
            raise ValueError("the full profile must contain every active capture surface")

    def __iter__(self) -> Iterator[SurfaceSpec]:
        return iter(self._surfaces)

    def __len__(self) -> int:
        return len(self._surfaces)

    def __contains__(self, stable_id: object) -> bool:
        return isinstance(stable_id, str) and stable_id in self._by_id

    def __getitem__(self, stable_id: str) -> SurfaceSpec:
        try:
            return self._by_id[stable_id]
        except KeyError as error:
            raise KeyError(f"unknown capture surface {stable_id!r}") from error

    @property
    def surfaces(self) -> tuple[SurfaceSpec, ...]:
        return self._surfaces

    @property
    def active_surfaces(self) -> tuple[SurfaceSpec, ...]:
        return tuple(surface for surface in self._surfaces if surface.active)

    @property
    def retired_surfaces(self) -> tuple[SurfaceSpec, ...]:
        return tuple(surface for surface in self._surfaces if not surface.active)

    @property
    def profile_names(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(
            placement.profile
            for surface in self.active_surfaces
            for placement in surface.placements
        ))

    def _placements(
        self,
        profile: str,
    ) -> list[tuple[SurfaceSpec, ProfilePlacement]]:
        rows = [
            (surface, placement)
            for surface in self.active_surfaces
            for placement in surface.placements
            if placement.profile == profile
        ]
        rows.sort(key=lambda row: row[1].order)
        if not rows:
            raise KeyError(f"unknown capture profile {profile!r}")
        return rows

    def profile_labels(self, profile: str) -> tuple[str, ...]:
        return tuple(surface.stable_id for surface, _placement in self._placements(profile))

    def profile_groups(self, profile: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
        grouped: dict[int, tuple[str, list[str]]] = {}
        for surface, placement in self._placements(profile):
            name, labels = grouped.setdefault(
                placement.group_order,
                (placement.group, []),
            )
            if name != placement.group:
                raise ValueError(f"profile {profile!r} has conflicting group names")
            labels.append(surface.stable_id)
        return tuple(
            (name, tuple(labels))
            for _order, (name, labels) in sorted(grouped.items())
        )

    def profile_page_count(
        self,
        profile: str,
        *,
        columns: int = PROFILE_COLUMNS,
        max_rows: int = PROFILE_MAX_ROWS,
    ) -> int:
        if columns < 1 or max_rows < 1:
            raise ValueError("contact-sheet dimensions must be positive")
        capacity = columns * max_rows
        pages = 0
        used_rows = 0
        for _name, labels in self.profile_groups(profile):
            if len(labels) > capacity:
                if used_rows:
                    pages += 1
                    used_rows = 0
                pages += math.ceil(len(labels) / capacity)
                continue
            rows = math.ceil(len(labels) / columns)
            if used_rows and used_rows + rows > max_rows:
                pages += 1
                used_rows = 0
            used_rows += rows
        return pages + bool(used_rows)

    def profile_digest(self, profile: str) -> str:
        return _canonical_digest({
            "profile": profile,
            "groups": [
                {"name": name, "labels": list(labels)}
                for name, labels in self.profile_groups(profile)
            ],
        })

    def surface_digest(self, stable_id: str) -> str:
        return _canonical_digest(self[stable_id].pixel_contract())

    def with_surfaces(self, surfaces: Sequence[SurfaceSpec]) -> "SurfaceRegistry":
        return SurfaceRegistry(tuple(surfaces))

    def add(self, surface: SurfaceSpec) -> "SurfaceRegistry":
        if surface.stable_id in self._by_id:
            raise ValueError(f"stable ID {surface.stable_id!r} is permanently reserved")
        return SurfaceRegistry((*self._surfaces, surface))

    def retire(self, stable_id: str, reason: str) -> "SurfaceRegistry":
        if not reason.strip():
            raise ValueError("retirement reason is required")
        replacement = replace(
            self[stable_id],
            active=False,
            placements=(),
            retired_reason=reason.strip(),
        )
        return SurfaceRegistry(tuple(
            replacement if surface.stable_id == stable_id else surface
            for surface in self._surfaces
        ))


REGISTRY = SurfaceRegistry(_surface_from_row(row) for row in SURFACE_ROWS)


def capture_scenario_internal_setups(stable_id: str) -> tuple[str, ...]:
    return REGISTRY[stable_id].internal_setups


def capture_scenario_prerequisites(stable_id: str) -> tuple[str, ...]:
    return REGISTRY[stable_id].prerequisites


def capture_scenario_checkpoint(stable_id: str) -> str:
    return REGISTRY[stable_id].checkpoint


def capture_scenario_id(stable_id: str) -> str:
    return REGISTRY[stable_id].scenario_id


def capture_fixture_id(stable_id: str) -> str:
    return REGISTRY[stable_id].fixture_id


def capture_scenario_step(stable_id: str) -> int:
    return REGISTRY[stable_id].scenario_step
