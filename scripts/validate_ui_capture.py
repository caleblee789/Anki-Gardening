from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import re
import struct
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import Image, ImageChops, ImageOps, UnidentifiedImageError


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CAPTURE_SOURCE = ROOT / "ankigarden" / "capture" / "runtime.py"
CAPTURE_BOOTSTRAP_SOURCE = ROOT / "ankigarden" / "capture_ui_faces.py"
DEFAULT_CAPTURE_CONTRACT = (
    ROOT / "ankigarden" / "capture" / "capture-contract-v26.json"
)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
CONTINUED_SUFFIX = " (continued)"
CONTACT_SHEET_COLUMNS = 2
CONTACT_SHEET_MAX_ROWS = 5
CONTACT_SHEET_WIDTH = 3000
CONTACT_SHEET_MARGIN = 64
CONTACT_SHEET_GUTTER = 32
CONTACT_SHEET_HEADER_HEIGHT = 250
CONTACT_SHEET_GROUP_HEADER_HEIGHT = 84
CONTACT_SHEET_CELL_HEIGHT = 930
CONTACT_SHEET_GROUP_GAP = 30
CONTACT_SHEET_PREVIEW_TOP = 110
CONTACT_SHEET_PREVIEW_SIDE = 22
CONTACT_SHEET_PREVIEW_BOTTOM = 40
# Reserve the 3px frame plus the full 6px screenshot outline and two sampled
# cream pixels between them; neither semantic boundary may overwrite another.
CONTACT_SHEET_PREVIEW_INSET = 12
CONTACT_SHEET_PREVIEW_FRAME_FILL = (216, 209, 190)  # #d8d1be
CONTACT_SHEET_PREVIEW_FRAME_OUTLINE = (158, 148, 124)  # #9e947c
CONTACT_SHEET_SCREENSHOT_OUTLINE = (73, 102, 92)  # #49665c
CONTACT_SHEET_FRAME_OUTLINE_WIDTH = 3
CONTACT_SHEET_OUTLINE_WIDTH = 6
CONTACT_SHEET_PADDING_LEGEND = "Cream = contact-sheet padding outside captured UI"
CONTACT_SHEET_QUALITY_STATUS = "Automated checks passed; visual review pending"
LEGACY_CAPTURE_ACCEPTANCE_POLICY = "gross-failures-only"
V26_CAPTURE_ACCEPTANCE_POLICY = "gross-and-semantic-fail-closed"
_V26_DEPRECATED_VISIBLE_COPY_PATTERNS = (
    r"\bstage [1-5] of 5\b",
    r"\bgarden finds?\b",
    r"\b1 find\b",
    r"\bnew environments?\b",
    r"\buse bonus\b",
    r"\benvironment discoveries\b",
    r"\benvironment discovery guarantees\b",
    r"\bfuture growth will be shared or stored\b",
    r"\btoday['’]s environment\b",
    r"\bnursery weather scenery\b",
    r"\bgarden item unlocked\b",
)
LEGACY_V24_PROFILE_SURFACE_COUNTS = {
    "representative": 26,
    "full": 126,
}
LEGACY_V24_PROFILE_CONTACT_SHEET_PAGE_COUNTS = {
    "representative": 4,
    "full": 17,
}
CONTACT_SHEET_PADDING_RGBA = (216, 209, 190, 255)
MIN_LOGICAL_CAPTURE_DIMENSION = 100
MAX_PNG_PIXELS = 100_000_000
CAPTURE_SCALE_FACTOR = 1.0
MEMORY_PROBE_CYCLES = 12
MEMORY_PROBE_CLASSES = (
    "NurseryDialog",
    "DialogShell",
    "PlantStoryDialog",
    "GardenDialog",
    "PurchaseConfirmationDialog",
    "FertilizerReplacementDialog",
    "GrowthChargeConfirmationDialog",
)
DIALOG_SCROLL_FOUR_STATE_NAMES = (
    "no-overflow-list",
    "one-row-list",
    "enough-rows-to-scroll",
    "final-item-at-maximum-scroll",
)
COMPACT_HOME_BANNED_COPY = (
    "today",
    "streak",
    "garden coins",
    "coins",
    "closest",
    "planted starter",
)
MISSING_ARTWORK_CAPTURE_TYPES = (
    "plant",
    "fertilizer",
    "weather",
    "scenery",
    "growth-charge",
)
WEB_ROOT_OVERFLOW_EVIDENCE_SOURCE = (
    "document-root-and-visible-addon-roots"
)
RENDERED_PIXEL_EVIDENCE_KEYS: dict[str, tuple[str, ...]] = {
    "full-garden": ("full-garden-scene",),
    "collection-loadout-detail": ("loadout-preview-scene",),
    "progress-overview-redirect-growth": (
        "direct-growth-label",
        "direct-growth-value",
    ),
    "streak-achievement-earned-next": (
        "streak-achievement-disclosure",
        "streak-completed-achievement",
        "streak-next-achievement",
    ),
    "collection-preview-restored": ("restored-preview-banner",),
    "reduced-motion-enabled": ("reduced-motion-control",),
    "nursery-item-owned": ("owned-item-card",),
    "missing-artwork-graphical-fallback": ("missing-art-weather",),
    "collection-environment-mechanics": (
        "environment-toolbar",
        "environment-summary-title",
        "environment-summary-selection",
        "environment-edit-appearance",
        "environment-item-title",
        "environment-item-status",
        "environment-effect",
        "environment-mechanics",
    ),
    "collection-loadout-persistence-error": (
        "loadout-preview-scene",
        "loadout-persistence-error",
    ),
}
_NO_INFERRED_VALUE = object()
# These are evidence aliases, not broad duplicate exemptions.  A duplicate hash
# must match one complete set exactly; subsets and supersets still fail.
INTENTIONAL_DUPLICATE_VISUALS: dict[frozenset[str], str] = {
    frozenset({"starter-nursery-plants", "starter-action-above-footer"}): (
        "The same first-run Nursery painting is captured once for state and once "
        "for the action-above-footer geometry audit."
    ),
}


class CaptureValidationError(ValueError):
    """Raised when capture evidence does not satisfy the source contract."""

    def __init__(self, issues: Sequence[str]) -> None:
        self.issues = tuple(str(issue) for issue in issues)
        super().__init__("; ".join(self.issues))


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class CaptureContract:
    version: int
    groups: tuple[tuple[str, tuple[str, ...]], ...]
    profile: str = "representative"
    scenario_schema_version: int = 1
    compiled_digest: str = ""

    @property
    def labels(self) -> tuple[str, ...]:
        return tuple(
            label
            for _group, labels in self.groups
            for label in labels
        )

    @property
    def digest(self) -> str:
        if self.compiled_digest:
            return self.compiled_digest
        payload = {
            "capture_contract_version": self.version,
            "capture_profile": self.profile,
            "groups": [
                {"name": name, "labels": list(labels)}
                for name, labels in self.groups
            ],
            "scenario_schema_version": self.scenario_schema_version,
        }
        return hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()


def _is_current_contract_source(source_path: Path) -> bool:
    try:
        resolved = source_path.resolve()
    except OSError:
        return False
    return resolved in {
        DEFAULT_CAPTURE_SOURCE.resolve(),
        CAPTURE_BOOTSTRAP_SOURCE.resolve(),
    }


def _load_current_contract_payload(
    path: Path = DEFAULT_CAPTURE_CONTRACT,
) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CaptureValidationError(
            (f"could not read compiled v26 capture contract {path}: {error}",)
        ) from error
    if not isinstance(payload, dict):
        raise CaptureValidationError(("compiled v26 capture contract must be an object",))
    normalized = dict(payload)
    expected_digest = normalized.pop("contract_digest", None)
    actual_digest = hashlib.sha256(
        json.dumps(
            normalized,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    profiles = payload.get("profiles")
    surfaces = payload.get("surfaces")
    issues: list[str] = []
    if payload.get("schema_version") != 2:
        issues.append("compiled capture contract schema is not v2")
    if payload.get("contract_version") != 26:
        issues.append("compiled capture contract is not v26")
    if payload.get("scenario_schema_version") != 3:
        issues.append("compiled capture scenario schema is not v3")
    if expected_digest != actual_digest:
        issues.append("compiled capture contract digest is stale")
    if not isinstance(profiles, dict) or not profiles:
        issues.append("compiled capture contract has no profiles")
    elif set(profiles) != {"representative", "full"}:
        issues.append("compiled capture profiles must be representative and full")
    if not isinstance(surfaces, list) or not surfaces:
        issues.append("compiled capture contract has no surfaces")
    else:
        active = [
            row for row in surfaces
            if isinstance(row, dict) and row.get("active") is True
        ]
        active_ids = {str(row.get("id", "")) for row in active}
        retired_ids = set(payload.get("retired_ids", ()))
        if len(active) != 34 or payload.get("surface_count") != 34:
            issues.append("compiled v26 contract must contain 34 active surfaces")
        if "nursery-garden-decorations-scenery" not in active_ids:
            issues.append("compiled v26 contract is missing renamed nursery surface")
        if "nursery-weather-scenery" not in retired_ids:
            issues.append("compiled v26 contract did not reserve the retired nursery ID")
        for index, row in enumerate(surfaces):
            if not isinstance(row, dict):
                continue
            if not isinstance(row.get("scenario_id"), str):
                issues.append(f"compiled surface {index} has no scenario_id")
            if not isinstance(row.get("fixture_id"), str):
                issues.append(f"compiled surface {index} has no fixture_id")
            if type(row.get("scenario_step")) is not int or row.get(
                "scenario_step", 0
            ) < 1:
                issues.append(f"compiled surface {index} has invalid scenario_step")
    if isinstance(profiles, dict):
        for profile, expected in {
            "representative": (18, 2),
            "full": (34, 5),
        }.items():
            raw_profile = profiles.get(profile)
            if not isinstance(raw_profile, dict) or (
                raw_profile.get("surface_count"),
                raw_profile.get("contact_sheet_page_count"),
            ) != expected:
                issues.append(
                    f"compiled {profile} topology must remain {expected[0]} surfaces / "
                    f"{expected[1]} pages"
                )
    if issues:
        raise CaptureValidationError(issues)
    return payload


def _current_surface_map() -> dict[str, dict[str, Any]]:
    payload = _load_current_contract_payload()
    result = {
        str(row.get("id")): dict(row)
        for row in payload.get("surfaces", ())
        if isinstance(row, dict) and row.get("active") is True
    }
    if len(result) != int(payload.get("surface_count", -1)):
        raise CaptureValidationError(("compiled v26 surface count is stale",))
    return result


@dataclass(frozen=True)
class PngEvidence:
    width: int
    height: int
    visual_digest: str
    sampled_color_count: int
    dominant_sample_ratio: float


def _assignment_value(module: ast.Module, name: str) -> ast.expr:
    for node in module.body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == name
            and node.value is not None
        ):
            return node.value
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name
            for target in node.targets
        ):
            return node.value
    raise CaptureValidationError((f"capture source is missing {name}",))


def load_capture_contract(
    source_path: Path = DEFAULT_CAPTURE_SOURCE,
    *,
    profile: str = "representative",
) -> CaptureContract:
    """Read one canonical capture profile without importing Anki or Qt."""

    profile = str(profile).strip().lower()
    if _is_current_contract_source(source_path):
        payload = _load_current_contract_payload()
        raw_profile = dict(payload.get("profiles", {}).get(profile, {}) or {})
        raw_groups = raw_profile.get("groups")
        if not isinstance(raw_groups, list) or not raw_groups:
            raise CaptureValidationError((f"unknown capture profile {profile!r}",))
        groups = tuple(
            (
                str(group.get("name", "")),
                tuple(str(label) for label in group.get("labels", ())),
            )
            for group in raw_groups
            if isinstance(group, dict)
        )
        labels = [label for _name, group_labels in groups for label in group_labels]
        if (
            len(groups) != len(raw_groups)
            or not labels
            or len(labels) != len(set(labels))
            or len(labels) != int(raw_profile.get("surface_count", -1))
        ):
            raise CaptureValidationError((f"compiled profile {profile!r} is malformed",))
        return CaptureContract(
            26,
            groups,
            profile,
            3,
            str(payload.get("contract_digest", "")),
        )
    assignment_name = {
        "representative": "CAPTURE_FACE_GROUPS",
        "full": "EXHAUSTIVE_CAPTURE_FACE_GROUPS",
    }.get(profile)
    if assignment_name is None:
        raise CaptureValidationError((f"unknown capture profile {profile!r}",))

    try:
        source = source_path.read_text(encoding="utf-8")
        module = ast.parse(source, filename=str(source_path))
        version_value = ast.literal_eval(
            _assignment_value(module, "CAPTURE_CONTRACT_VERSION")
        )
        groups_value = ast.literal_eval(
            _assignment_value(module, assignment_name)
        )
        scenario_schema_value = ast.literal_eval(
            _assignment_value(module, "CAPTURE_SCENARIO_SCHEMA_VERSION")
        )
    except CaptureValidationError:
        raise
    except (OSError, SyntaxError, ValueError) as error:
        raise CaptureValidationError(
            (f"could not read literal capture contract from {source_path}: {error}",)
        ) from error

    issues: list[str] = []
    if type(version_value) is not int or version_value < 1:
        issues.append("CAPTURE_CONTRACT_VERSION must be a positive integer literal")
    if type(scenario_schema_value) is not int or scenario_schema_value < 1:
        issues.append("CAPTURE_SCENARIO_SCHEMA_VERSION must be a positive integer literal")

    normalized_groups: list[tuple[str, tuple[str, ...]]] = []
    if not isinstance(groups_value, (tuple, list)) or not groups_value:
        issues.append(f"{assignment_name} must be a non-empty literal sequence")
    else:
        for group_index, raw_group in enumerate(groups_value, start=1):
            if not isinstance(raw_group, (tuple, list)) or len(raw_group) != 2:
                issues.append(
                    f"{assignment_name} group {group_index} must contain a name and labels"
                )
                continue
            raw_name, raw_labels = raw_group
            name = raw_name.strip() if isinstance(raw_name, str) else ""
            if not name:
                issues.append(
                    f"{assignment_name} group {group_index} has an empty name"
                )
            if not isinstance(raw_labels, (tuple, list)) or not raw_labels:
                issues.append(
                    f"{assignment_name} group {name or group_index!r} has no labels"
                )
                continue
            labels = tuple(
                label.strip() if isinstance(label, str) else ""
                for label in raw_labels
            )
            if any(not label for label in labels):
                issues.append(
                    f"{assignment_name} group {name or group_index!r} has an invalid label"
                )
            normalized_groups.append((name, labels))

    group_names = [name for name, _labels in normalized_groups]
    labels = [label for _name, group_labels in normalized_groups for label in group_labels]
    if len(group_names) != len(set(group_names)):
        issues.append(f"{assignment_name} contains duplicate group names")
    if len(labels) != len(set(labels)):
        issues.append(f"{assignment_name} contains duplicate labels")
    required_surface_count = LEGACY_V24_PROFILE_SURFACE_COUNTS[profile]
    if len(labels) != required_surface_count:
        issues.append(
            f"{profile} capture contract must contain exactly "
            f"{required_surface_count} surfaces, found {len(labels)}"
        )
    if issues:
        raise CaptureValidationError(issues)
    return CaptureContract(
        int(version_value),
        tuple(normalized_groups),
        profile,
        int(scenario_schema_value),
    )


def load_dialog_scroll_capture_coverage(
    source_path: Path = DEFAULT_CAPTURE_SOURCE,
    *,
    contract: CaptureContract | None = None,
) -> dict[str, dict[str, str]]:
    """Load the source-owned surface, label, and page-semantic scroll proof."""

    if _is_current_contract_source(source_path):
        contract = contract or load_capture_contract(source_path)
        surfaces = _current_surface_map()
        names = {
            "PurchaseConfirmationDialog": "Purchase confirmation",
            "NurseryDialog": "Nursery",
            "FertilizerDialog": "Fertilizer selection",
            "FertilizerReplacementDialog": "Fertilizer replacement",
            "PlantStoryDialog": "Plant Story",
            "SpeciesOverviewDialog": "Species overview",
            "GardenSettingsDialog": "Settings",
            "GardenProgressDialog": "Garden Progress",
            "CollectibleDetailDialog": "Collection loadout details",
            "GrowthChargeConfirmationDialog": "Growth Charge confirmation",
        }
        grouped: dict[str, dict[str, str]] = {}
        for label in contract.labels:
            requirements = tuple(surfaces[label].get("evidence_requirements", ()))
            scroll = next(
                (
                    str(requirement).split(":", 1)[1]
                    for requirement in requirements
                    if str(requirement).startswith("scroll:")
                ),
                "",
            )
            if not scroll:
                continue
            root = scroll.split(":", 1)[0]
            group = names.get(root, root)
            if scroll == "GardenProgressDialog:collection":
                group = "Collection"
            grouped.setdefault(group, {})[label] = scroll
        return grouped

    module = _source_module(source_path)
    contract = contract or load_capture_contract(source_path)
    try:
        raw_coverage = ast.literal_eval(
            _assignment_value(module, "DIALOG_SCROLL_CAPTURE_COVERAGE")
        )
        raw_semantics = ast.literal_eval(
            _assignment_value(module, "DIALOG_SCROLL_CAPTURE_SEMANTICS")
        )
    except CaptureValidationError:
        raise
    except (ValueError, SyntaxError) as error:
        raise CaptureValidationError(
            ("dialog scroll capture coverage must be literal",)
        ) from error

    issues: list[str] = []
    contract_labels = set(contract.labels)
    try:
        exhaustive_groups = ast.literal_eval(
            _assignment_value(module, "EXHAUSTIVE_CAPTURE_FACE_GROUPS")
        )
        exhaustive_labels = {
            label
            for _group, labels in exhaustive_groups
            for label in labels
        }
    except (CaptureValidationError, TypeError, ValueError, SyntaxError):
        exhaustive_labels = contract_labels
    normalized: dict[str, dict[str, str]] = {}
    all_labels: list[str] = []
    if not isinstance(raw_coverage, dict) or not raw_coverage:
        issues.append("DIALOG_SCROLL_CAPTURE_COVERAGE must be a non-empty object")
    else:
        for raw_surface, raw_labels in raw_coverage.items():
            surface = raw_surface.strip() if isinstance(raw_surface, str) else ""
            if not surface:
                issues.append("dialog scroll coverage contains an empty surface")
                continue
            if not isinstance(raw_labels, (tuple, list)) or not raw_labels:
                issues.append(f"dialog scroll surface {surface!r} has no labels")
                continue
            surface_contract: dict[str, str] = {}
            for raw_label in raw_labels:
                label = raw_label.strip() if isinstance(raw_label, str) else ""
                if not label:
                    issues.append(
                        f"dialog scroll surface {surface!r} has an invalid label"
                    )
                    continue
                all_labels.append(label)
                if label not in exhaustive_labels:
                    issues.append(
                        f"dialog scroll label {label!r} is outside the declared capture profiles"
                    )
                semantic = (
                    raw_semantics.get(label, "").strip()
                    if isinstance(raw_semantics, dict)
                    and isinstance(raw_semantics.get(label), str)
                    else ""
                )
                if not semantic:
                    issues.append(
                        f"dialog scroll label {label!r} has no page semantic"
                    )
                if label in contract_labels:
                    surface_contract[label] = semantic
            if surface_contract:
                normalized[surface] = surface_contract

    if len(all_labels) != len(set(all_labels)):
        duplicates = sorted(
            label for label in set(all_labels) if all_labels.count(label) > 1
        )
        issues.append(
            "dialog scroll labels belong to multiple surfaces: "
            + ", ".join(duplicates)
        )
    if not isinstance(raw_semantics, dict):
        issues.append("DIALOG_SCROLL_CAPTURE_SEMANTICS must be an object")
    else:
        semantic_labels = {
            label for label in raw_semantics if isinstance(label, str)
        }
        if semantic_labels != set(all_labels):
            issues.append(
                "DIALOG_SCROLL_CAPTURE_SEMANTICS must exactly match coverage labels"
            )
    if issues:
        raise CaptureValidationError(issues)
    return normalized


def _source_module(source_path: Path) -> ast.Module:
    try:
        return ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    except (OSError, SyntaxError) as error:
        raise CaptureValidationError(
            (f"could not parse capture source {source_path}: {error}",)
        ) from error


def _static_renderer_value(
    expression: ast.expr,
    module: ast.Module,
    *,
    bindings: dict[str, int] | None = None,
) -> Any:
    """Evaluate the tiny source syntax used to declare renderer label sets."""

    bindings = bindings or {}
    if isinstance(expression, ast.Constant) and isinstance(expression.value, (str, int)):
        return expression.value
    if isinstance(expression, ast.Name):
        if expression.id in bindings:
            return bindings[expression.id]
        return _static_renderer_value(_assignment_value(module, expression.id), module)
    if isinstance(expression, (ast.Set, ast.Tuple, ast.List)):
        values: list[Any] = []
        for element in expression.elts:
            if isinstance(element, ast.Starred):
                expanded = _static_renderer_value(
                    element.value,
                    module,
                    bindings=bindings,
                )
                if not isinstance(expanded, (tuple, list, set, frozenset)):
                    raise CaptureValidationError(
                        ("renderer label-set expansion is not a static sequence",)
                    )
                values.extend(expanded)
            else:
                values.append(
                    _static_renderer_value(element, module, bindings=bindings)
                )
        if isinstance(expression, ast.Set):
            return frozenset(values)
        return tuple(values)
    if (
        isinstance(expression, ast.Call)
        and isinstance(expression.func, ast.Name)
        and expression.func.id == "frozenset"
        and len(expression.args) == 1
        and not expression.keywords
    ):
        return frozenset(_static_renderer_value(expression.args[0], module))
    if isinstance(expression, ast.GeneratorExp):
        if len(expression.generators) != 1:
            raise CaptureValidationError(("renderer generator must have one clause",))
        generator = expression.generators[0]
        if (
            generator.is_async
            or generator.ifs
            or not isinstance(generator.target, ast.Name)
            or not isinstance(generator.iter, ast.Call)
            or not isinstance(generator.iter.func, ast.Name)
            or generator.iter.func.id != "range"
            or generator.iter.keywords
        ):
            raise CaptureValidationError(("renderer generator is not a static range",))
        try:
            range_args = [ast.literal_eval(argument) for argument in generator.iter.args]
        except ValueError as error:
            raise CaptureValidationError(("renderer range arguments must be literals",)) from error
        if not range_args or any(type(argument) is not int for argument in range_args):
            raise CaptureValidationError(("renderer range arguments must be integers",))
        return tuple(
            _static_renderer_value(
                expression.elt,
                module,
                bindings={**bindings, generator.target.id: value},
            )
            for value in range(*range_args)
        )
    if isinstance(expression, ast.JoinedStr):
        pieces: list[str] = []
        for value in expression.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                pieces.append(value.value)
            elif (
                isinstance(value, ast.FormattedValue)
                and value.format_spec is None
                and isinstance(value.value, ast.Name)
                and value.value.id in bindings
            ):
                pieces.append(str(bindings[value.value.id]))
            else:
                raise CaptureValidationError(("renderer f-string is not statically supported",))
        return "".join(pieces)
    raise CaptureValidationError(
        (f"unsupported renderer declaration syntax: {type(expression).__name__}",)
    )


def load_capture_layout_contract(
    source_path: Path = DEFAULT_CAPTURE_SOURCE,
) -> tuple[dict[str, float | int], dict[str, int], frozenset[str]]:
    """Load the shell telemetry thresholds without importing Anki or Qt."""

    module = _source_module(source_path)
    try:
        raw_limits = ast.literal_eval(
            _assignment_value(module, "CAPTURE_LAYOUT_LIMITS")
        )
        raw_heights = ast.literal_eval(
            _assignment_value(module, "CAPTURE_BUTTON_HEIGHTS")
        )
        raw_tabular = _static_renderer_value(
            _assignment_value(module, "TABULAR_NUMERAL_CAPTURE_LABELS"),
            module,
        )
    except (SyntaxError, ValueError) as error:
        raise CaptureValidationError(
            (f"capture layout telemetry contract is not literal: {error}",)
        ) from error
    expected_limit_keys = {
        "maximum_client_gutter_px",
        "maximum_content_footer_gap_px",
        "maximum_nursery_root_offset_px",
        "maximum_action_width_ratio",
        "minimum_rendered_text_px",
        "maximum_overflow_owner_count",
    }
    expected_height_keys = {
        "compact-row",
        "banner",
        "secondary",
        "primary",
        "onboarding",
        "icon",
    }
    issues: list[str] = []
    if not isinstance(raw_limits, dict) or set(raw_limits) != expected_limit_keys:
        issues.append("CAPTURE_LAYOUT_LIMITS has an invalid schema")
    elif any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0
        for value in raw_limits.values()
    ):
        issues.append("CAPTURE_LAYOUT_LIMITS values must be finite and nonnegative")
    if not isinstance(raw_heights, dict) or set(raw_heights) != expected_height_keys:
        issues.append("CAPTURE_BUTTON_HEIGHTS has an invalid schema")
    elif any(type(value) is not int or value <= 0 for value in raw_heights.values()):
        issues.append("CAPTURE_BUTTON_HEIGHTS values must be positive integers")
    if not isinstance(raw_tabular, frozenset) or any(
        not isinstance(label, str) or not label for label in raw_tabular
    ):
        issues.append("TABULAR_NUMERAL_CAPTURE_LABELS must be a static label set")
    if issues:
        raise CaptureValidationError(issues)
    return dict(raw_limits), dict(raw_heights), frozenset(raw_tabular)


def _branch_labels(test: ast.expr, module: ast.Module) -> frozenset[str]:
    if not isinstance(test, ast.Compare) or len(test.ops) != 1 or len(test.comparators) != 1:
        raise CaptureValidationError(("renderer branch must use one label comparison",))
    if not isinstance(test.left, ast.Name) or test.left.id != "label":
        raise CaptureValidationError(("renderer branch must compare label",))
    comparator = test.comparators[0]
    if isinstance(test.ops[0], ast.Eq):
        value = _static_renderer_value(comparator, module)
        if not isinstance(value, str):
            raise CaptureValidationError(("renderer equality label must be a string",))
        return frozenset({value})
    if isinstance(test.ops[0], ast.In):
        value = _static_renderer_value(comparator, module)
        if not isinstance(value, (tuple, list, set, frozenset)) or any(
            not isinstance(label, str) for label in value
        ):
            raise CaptureValidationError(("renderer membership labels must be strings",))
        return frozenset(value)
    raise CaptureValidationError(("renderer branch comparison is unsupported",))


def load_expected_renderer_families(
    source_path: Path = DEFAULT_CAPTURE_SOURCE,
    *,
    contract: CaptureContract | None = None,
) -> dict[str, str]:
    """Derive label-to-renderer ownership from source without importing Anki."""

    if _is_current_contract_source(source_path):
        contract = contract or load_capture_contract(source_path)
        surfaces = _current_surface_map()
        missing = [label for label in contract.labels if label not in surfaces]
        if missing:
            raise CaptureValidationError((
                "compiled renderer mapping is missing: " + ", ".join(missing),
            ))
        return {
            label: str(surfaces[label].get("renderer_family", ""))
            for label in contract.labels
        }

    module = _source_module(source_path)
    contract = contract or load_capture_contract(source_path)
    function = next(
        (
            node
            for node in module.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "expected_capture_window_family"
        ),
        None,
    )
    if not isinstance(function, ast.FunctionDef):
        raise CaptureValidationError(("capture source is missing expected_capture_window_family",))

    mapping: dict[str, str] = {}
    def add(labels: Sequence[str], family: str) -> None:
        if not family:
            raise CaptureValidationError(("renderer family must be non-empty",))
        for label in labels:
            if label in mapping:
                raise CaptureValidationError(
                    (f"renderer label {label!r} is declared more than once",)
                )
            mapping[label] = family

    for statement in function.body:
        if (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        ):
            continue
        if isinstance(statement, ast.If):
            if statement.orelse or len(statement.body) != 1 or not isinstance(statement.body[0], ast.Return):
                raise CaptureValidationError(("renderer branch body is unsupported",))
            return_value = statement.body[0].value
            if not isinstance(return_value, ast.Constant) or not isinstance(return_value.value, str):
                raise CaptureValidationError(("renderer branch must return a string literal",))
            add(tuple(_branch_labels(statement.test, module)), return_value.value)
            continue
        if (
            isinstance(statement, ast.Return)
            and isinstance(statement.value, ast.Constant)
            and statement.value.value == ""
        ):
            continue
        raise CaptureValidationError(
            (f"unsupported statement in expected_capture_window_family: {type(statement).__name__}",)
        )

    expected = set(contract.labels)
    actual = set(mapping)
    try:
        exhaustive_groups = ast.literal_eval(
            _assignment_value(module, "EXHAUSTIVE_CAPTURE_FACE_GROUPS")
        )
        declared = {
            label
            for _group, labels in exhaustive_groups
            for label in labels
        }
    except (CaptureValidationError, TypeError, ValueError, SyntaxError):
        declared = expected
    if not expected.issubset(actual) or actual != declared:
        missing = sorted(expected - actual)
        undeclared = sorted(actual - declared)
        unowned = sorted(declared - actual)
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if undeclared:
            details.append("undeclared " + ", ".join(undeclared))
        if unowned:
            details.append("unowned " + ", ".join(unowned))
        raise CaptureValidationError(("renderer mapping does not cover the contract: " + "; ".join(details),))
    return {label: mapping[label] for label in contract.labels}


def load_expected_resize_layout_modes(
    source_path: Path = DEFAULT_CAPTURE_SOURCE,
) -> dict[str, str]:
    """Read the source-owned semantic layout mode for every resize fixture."""

    module = _source_module(source_path)
    try:
        specs = ast.literal_eval(_assignment_value(module, "RESIZE_MATRIX_SPECS"))
        purchase_specs = ast.literal_eval(
            _assignment_value(module, "PURCHASE_CONFIRMATION_RESIZE_SPECS")
        )
        growth_charge_specs = ast.literal_eval(
            _assignment_value(module, "GROWTH_CHARGE_RESIZE_SPECS")
        )
        modes = ast.literal_eval(
            _assignment_value(module, "RESIZE_MATRIX_LAYOUT_MODES")
        )
    except (ValueError, SyntaxError) as error:
        raise CaptureValidationError(
            ("resize layout-mode declarations must be literals",)
        ) from error
    if (
        not isinstance(specs, (tuple, list))
        or not isinstance(purchase_specs, (tuple, list))
        or not isinstance(growth_charge_specs, (tuple, list))
        or not isinstance(modes, dict)
    ):
        raise CaptureValidationError(("resize layout-mode declarations are malformed",))
    specs = (*specs, *purchase_specs, *growth_charge_specs)
    labels = tuple(
        spec[0]
        for spec in specs
        if isinstance(spec, (tuple, list)) and spec and isinstance(spec[0], str)
    )
    if len(labels) != len(specs) or len(labels) != len(set(labels)):
        raise CaptureValidationError(("resize layout-mode specifications are malformed",))
    if set(modes) != set(labels) or any(
        not isinstance(mode, str) or not mode.strip()
        for mode in modes.values()
    ):
        raise CaptureValidationError(
            ("RESIZE_MATRIX_LAYOUT_MODES must exactly cover resize labels",)
        )
    return {label: modes[label] for label in labels}


def _schema_condition_value(expression: ast.expr, environment: dict[str, Any]) -> Any:
    if isinstance(expression, ast.Constant):
        return expression.value
    if isinstance(expression, ast.Name) and expression.id in environment:
        return environment[expression.id]
    if isinstance(expression, (ast.Set, ast.Tuple, ast.List, ast.Dict)):
        try:
            return ast.literal_eval(expression)
        except (ValueError, SyntaxError) as error:
            raise CaptureValidationError(("postcondition condition is not literal",)) from error
    if isinstance(expression, ast.UnaryOp) and isinstance(expression.op, ast.Not):
        return not bool(_schema_condition_value(expression.operand, environment))
    if isinstance(expression, ast.BoolOp):
        values = [
            bool(_schema_condition_value(value, environment))
            for value in expression.values
        ]
        if isinstance(expression.op, ast.And):
            return all(values)
        if isinstance(expression.op, ast.Or):
            return any(values)
    if (
        isinstance(expression, ast.Call)
        and isinstance(expression.func, ast.Attribute)
        and expression.func.attr in {"startswith", "endswith"}
        and len(expression.args) == 1
        and not expression.keywords
    ):
        owner = _schema_condition_value(expression.func.value, environment)
        argument = _schema_condition_value(expression.args[0], environment)
        if not isinstance(owner, str) or not isinstance(argument, str):
            raise CaptureValidationError(("postcondition string condition is invalid",))
        return getattr(owner, expression.func.attr)(argument)
    if (
        isinstance(expression, ast.Compare)
        and len(expression.ops) == 1
        and len(expression.comparators) == 1
    ):
        left = _schema_condition_value(expression.left, environment)
        right = _schema_condition_value(expression.comparators[0], environment)
        operator = expression.ops[0]
        if isinstance(operator, ast.Eq):
            return left == right
        if isinstance(operator, ast.NotEq):
            return left != right
        if isinstance(operator, ast.In):
            return left in right
        if isinstance(operator, ast.NotIn):
            return left not in right
        if isinstance(operator, ast.Is):
            return left is right
        if isinstance(operator, ast.IsNot):
            return left is not right
    raise CaptureValidationError(
        (f"unsupported postcondition schema condition: {ast.dump(expression)}",)
    )


def _required_postcondition_facts(
    function: ast.FunctionDef,
    *,
    environment: dict[str, Any],
    inferred_values: dict[str, Any] | None = None,
) -> tuple[str, ...]:
    facts: list[str] = []

    def infer_passing_value(call: ast.Call) -> Any:
        if len(call.args) < 3:
            return _NO_INFERRED_VALUE
        condition, value = call.args[1:3]
        if (
            isinstance(condition, ast.Call)
            and isinstance(condition.func, ast.Name)
            and condition.func.id == "bool"
            and ast.dump(condition) == ast.dump(value)
        ):
            return True
        if (
            isinstance(condition, ast.Compare)
            and len(condition.ops) == 1
            and isinstance(condition.ops[0], ast.Is)
            and len(condition.comparators) == 1
            and isinstance(condition.comparators[0], ast.Constant)
            and isinstance(condition.comparators[0].value, (bool, type(None)))
            and ast.dump(condition.left) == ast.dump(value)
        ):
            return condition.comparators[0].value
        if (
            isinstance(condition, ast.BoolOp)
            and isinstance(condition.op, ast.And)
            and isinstance(value, ast.IfExp)
            and any(
                ast.dump(term) == ast.dump(value.test)
                for term in condition.values
            )
        ):
            try:
                return ast.literal_eval(value.body)
            except (ValueError, SyntaxError):
                pass
        return _NO_INFERRED_VALUE

    def walk(statements: Sequence[ast.stmt]) -> None:
        for statement in statements:
            if (
                isinstance(statement, ast.Expr)
                and isinstance(statement.value, ast.Call)
                and isinstance(statement.value.func, ast.Name)
                and statement.value.func.id == "require"
                and statement.value.args
            ):
                try:
                    fact = ast.literal_eval(statement.value.args[0])
                except (ValueError, SyntaxError) as error:
                    raise CaptureValidationError(
                        ("postcondition fact name must be literal",)
                    ) from error
                if not isinstance(fact, str) or not fact or fact in facts:
                    raise CaptureValidationError(
                        (f"postcondition fact name is invalid or duplicated: {fact!r}",)
                    )
                facts.append(fact)
                inferred = infer_passing_value(statement.value)
                if inferred_values is not None and inferred is not _NO_INFERRED_VALUE:
                    inferred_values[fact] = inferred
            elif isinstance(statement, ast.If):
                if not any(
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "require"
                    for node in ast.walk(statement)
                ):
                    # Runtime-only presentation branches do not alter the
                    # declared postcondition fact schema.
                    continue
                branch = (
                    statement.body
                    if bool(_schema_condition_value(statement.test, environment))
                    else statement.orelse
                )
                walk(branch)
            elif any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "require"
                for node in ast.walk(statement)
            ):
                raise CaptureValidationError(
                    (
                        "postcondition require call moved under unsupported "
                        f"{type(statement).__name__} control flow",
                    )
                )

    walk(function.body)
    if not facts:
        raise CaptureValidationError(("postcondition fact schema is empty",))
    return tuple(facts)


def _state_expression_value(expression: ast.expr, environment: dict[str, Any]) -> Any:
    if isinstance(expression, ast.Constant):
        return expression.value
    if isinstance(expression, ast.Name):
        if expression.id in environment:
            return environment[expression.id]
        raise CaptureValidationError((f"unknown state-profile name {expression.id}",))
    if isinstance(expression, ast.Dict):
        return {
            _state_expression_value(key, environment): _state_expression_value(value, environment)
            for key, value in zip(expression.keys, expression.values)
            if key is not None
        }
    if isinstance(expression, (ast.List, ast.Tuple, ast.Set)):
        values = [_state_expression_value(value, environment) for value in expression.elts]
        if isinstance(expression, ast.List):
            return values
        if isinstance(expression, ast.Tuple):
            return tuple(values)
        return set(values)
    if isinstance(expression, ast.IfExp):
        branch = expression.body if bool(
            _state_expression_value(expression.test, environment)
        ) else expression.orelse
        return _state_expression_value(branch, environment)
    if isinstance(expression, ast.UnaryOp) and isinstance(expression.op, ast.Not):
        return not bool(_state_expression_value(expression.operand, environment))
    if isinstance(expression, ast.BinOp) and isinstance(expression.op, ast.Sub):
        return _state_expression_value(expression.left, environment) - _state_expression_value(
            expression.right,
            environment,
        )
    if isinstance(expression, ast.Compare):
        return _schema_condition_value(expression, environment)
    if isinstance(expression, ast.BoolOp):
        return _schema_condition_value(expression, environment)
    if isinstance(expression, ast.Subscript):
        owner = _state_expression_value(expression.value, environment)
        key = _state_expression_value(expression.slice, environment)
        return owner[key]
    if isinstance(expression, ast.Call):
        arguments = [
            _state_expression_value(argument, environment)
            for argument in expression.args
        ]
        if isinstance(expression.func, ast.Name):
            if expression.func.id == "expected_capture_window_family" and len(arguments) == 1:
                return environment["__renderer_families"][arguments[0]]
            if expression.func.id == "int" and len(arguments) == 1:
                return int(arguments[0])
        if isinstance(expression.func, ast.Attribute):
            if (
                isinstance(expression.func.value, ast.Name)
                and expression.func.value.id == "re"
                and expression.func.attr == "search"
                and len(arguments) == 2
            ):
                return re.search(arguments[0], arguments[1])
            owner = _state_expression_value(expression.func.value, environment)
            if expression.func.attr in {"startswith", "endswith"}:
                return getattr(owner, expression.func.attr)(*arguments)
            if expression.func.attr == "get" and isinstance(owner, dict):
                return owner.get(*arguments)
            if expression.func.attr == "group" and isinstance(owner, re.Match):
                return owner.group(*arguments)
    raise CaptureValidationError(
        (f"unsupported state-profile expression: {ast.dump(expression)}",)
    )


def _interpreted_state_profile(
    function: ast.FunctionDef,
    *,
    label: str,
    renderer_families: dict[str, str],
    source_values: dict[str, Any],
) -> dict[str, Any]:
    environment: dict[str, Any] = {
        **source_values,
        "label": label,
        "__renderer_families": renderer_families,
    }

    def assign(target: ast.expr, value: Any) -> None:
        if isinstance(target, ast.Name):
            environment[target.id] = value
            return
        if isinstance(target, ast.Subscript):
            owner = _state_expression_value(target.value, environment)
            key = _state_expression_value(target.slice, environment)
            owner[key] = value
            return
        if isinstance(target, (ast.Tuple, ast.List)):
            values = list(value)
            starred = next(
                (index for index, item in enumerate(target.elts) if isinstance(item, ast.Starred)),
                None,
            )
            if starred is None:
                if len(values) != len(target.elts):
                    raise CaptureValidationError(("state-profile unpack length mismatch",))
                for item, item_value in zip(target.elts, values):
                    assign(item, item_value)
                return
            trailing = len(target.elts) - starred - 1
            for item, item_value in zip(target.elts[:starred], values[:starred]):
                assign(item, item_value)
            assign(target.elts[starred].value, values[starred : len(values) - trailing])
            if trailing:
                for item, item_value in zip(target.elts[-trailing:], values[-trailing:]):
                    assign(item, item_value)
            return
        raise CaptureValidationError(("unsupported state-profile assignment target",))

    def run(statements: Sequence[ast.stmt]) -> tuple[bool, Any]:
        for statement in statements:
            if (
                isinstance(statement, ast.Expr)
                and isinstance(statement.value, ast.Constant)
                and isinstance(statement.value.value, str)
            ):
                continue
            if isinstance(statement, ast.Assign):
                value = _state_expression_value(statement.value, environment)
                for target in statement.targets:
                    assign(target, value)
                continue
            if isinstance(statement, ast.AnnAssign) and statement.value is not None:
                assign(
                    statement.target,
                    _state_expression_value(statement.value, environment),
                )
                continue
            if isinstance(statement, ast.If):
                selected = statement.body if bool(
                    _state_expression_value(statement.test, environment)
                ) else statement.orelse
                returned, value = run(selected)
                if returned:
                    return True, value
                continue
            if isinstance(statement, ast.For):
                iterable = _state_expression_value(statement.iter, environment)
                for item in iterable:
                    assign(statement.target, item)
                    returned, value = run(statement.body)
                    if returned:
                        return True, value
                returned, value = run(statement.orelse)
                if returned:
                    return True, value
                continue
            if (
                isinstance(statement, ast.Expr)
                and isinstance(statement.value, ast.Call)
                and isinstance(statement.value.func, ast.Attribute)
                and statement.value.func.attr == "update"
                and len(statement.value.args) == 1
                and not statement.value.keywords
            ):
                owner = _state_expression_value(statement.value.func.value, environment)
                update = _state_expression_value(statement.value.args[0], environment)
                if not isinstance(owner, dict) or not isinstance(update, dict):
                    raise CaptureValidationError(("state-profile update is invalid",))
                owner.update(update)
                continue
            if isinstance(statement, ast.Return):
                return True, (
                    _state_expression_value(statement.value, environment)
                    if statement.value is not None else None
                )
            raise CaptureValidationError(
                (f"unsupported state-profile statement: {type(statement).__name__}",)
            )
        return False, None

    returned, value = run(function.body)
    if not returned or not isinstance(value, dict):
        raise CaptureValidationError((f"state profile for {label} did not return an object",))
    return value


def load_expected_state_evidence_contracts(
    source_path: Path = DEFAULT_CAPTURE_SOURCE,
    *,
    contract: CaptureContract | None = None,
) -> dict[str, dict[str, Any]]:
    """Derive each label's state kind and exact fact keys from capture source."""

    if _is_current_contract_source(source_path):
        contract = contract or load_capture_contract(source_path)
        surfaces = _current_surface_map()
        result: dict[str, dict[str, Any]] = {}
        for label in contract.labels:
            raw = surfaces[label].get("state_contract")
            if not isinstance(raw, dict):
                raise CaptureValidationError(
                    (f"compiled state contract is missing for {label}",)
                )
            profile = raw.get("profile")
            if (
                not isinstance(profile, dict)
                or profile.get("profile_id") != label
                or not isinstance(raw.get("required_facts"), (list, tuple))
                or not isinstance(raw.get("expected_fact_values"), dict)
                or not isinstance(raw.get("fact_constraints"), dict)
            ):
                raise CaptureValidationError(
                    (f"compiled state contract is invalid for {label}",)
                )
            result[label] = dict(raw)
        return result

    module = _source_module(source_path)
    contract = contract or load_capture_contract(source_path)
    renderer_families = load_expected_renderer_families(
        source_path,
        contract=contract,
    )
    profile_function = next(
        (
            node for node in module.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "expected_capture_state_profile"
        ),
        None,
    )
    runner = next(
        (
            node for node in module.body
            if isinstance(node, ast.ClassDef)
            and node.name == "_UiFaceCaptureRunner"
        ),
        None,
    )
    postcondition_function = next(
        (
            node for node in (runner.body if isinstance(runner, ast.ClassDef) else ())
            if isinstance(node, ast.FunctionDef)
            and node.name == "_capture_fixture_postcondition"
        ),
        None,
    )
    if not isinstance(profile_function, ast.FunctionDef) or not isinstance(
        postcondition_function,
        ast.FunctionDef,
    ):
        raise CaptureValidationError(("capture source is missing state evidence functions",))

    source_values: dict[str, Any] = {}
    for name in (
        "_HOME_CAPTURE_LABELS",
        "_DASHBOARD_CAPTURE_LABELS",
        "_PROGRESS_CAPTURE_LABELS",
        "_REVIEWER_CAPTURE_LABELS",
        "_GROWTH_CHARGE_CAPTURE_LABELS",
        "_NURSERY_CAPTURE_LABELS",
        "_SETTINGS_CAPTURE_LABELS",
    ):
        source_values[name] = _static_renderer_value(
            _assignment_value(module, name),
            module,
        )
    try:
        resize_specs = ast.literal_eval(_assignment_value(module, "RESIZE_MATRIX_SPECS"))
        purchase_resize_specs = ast.literal_eval(
            _assignment_value(module, "PURCHASE_CONFIRMATION_RESIZE_SPECS")
        )
        growth_charge_resize_specs = ast.literal_eval(
            _assignment_value(module, "GROWTH_CHARGE_RESIZE_SPECS")
        )
    except (ValueError, SyntaxError) as error:
        raise CaptureValidationError(("resize state profiles must be literal",)) from error
    resize_modes = load_expected_resize_layout_modes(source_path)
    source_values["RESIZE_MATRIX_SPECS"] = resize_specs
    source_values["PURCHASE_CONFIRMATION_RESIZE_SPECS"] = purchase_resize_specs
    source_values["GROWTH_CHARGE_RESIZE_SPECS"] = growth_charge_resize_specs
    source_values["RESIZE_MATRIX_LAYOUT_MODES"] = resize_modes

    result: dict[str, dict[str, Any]] = {}
    for label in contract.labels:
        family = renderer_families[label]
        profile = _interpreted_state_profile(
            profile_function,
            label=label,
            renderer_families=renderer_families,
            source_values=source_values,
        )
        if (
            profile.get("profile_id") != label
            or profile.get("window_family") != family
            or profile.get("kind") not in {
                "home", "resize", "dashboard", "progress",
                "nursery", "settings", "collectible-detail", "dialog",
                "reviewer",
            }
        ):
            raise CaptureValidationError(
                (f"source state profile for {label} is incomplete or inconsistent",)
            )

        expected_values: dict[str, Any] = {
            "ordered_fixture_label": label,
            "state_profile_declared": label,
            "window_family": family,
        }
        kind = profile["kind"]
        if kind == "home":
            expected_values.update({
                "anki_surface": profile["surface"],
                "source_fixture_state": profile["fixture_state"],
                "dom_capture_label": label,
            })
            if "active_slot" in profile:
                expected_values.update({
                    "active_plant_slot": profile["active_slot"],
                    "dom_active_slot": profile["active_slot"],
                })
        elif kind == "resize":
            expected_values.update({
                "geometry_fixture_label": label,
                "declared_client_size": profile["declared_client_size"],
                "requested_client_size": profile["declared_client_size"],
                "transition_path": profile["transition_path"],
                "layout_mode": profile["layout_mode"],
            })
            if "canonical_page" in profile:
                expected_values["canonical_progress_page"] = profile["canonical_page"]
        elif kind == "progress":
            expected_values["progress_page"] = profile["page"]
        elif kind == "nursery":
            expected_values.update({
                "nursery_tab": profile["tab"],
                "starter_mode": profile["starter_mode"],
            })
        elif kind == "settings":
            expected_values["settings_tab"] = profile["tab"]

        state_name = str(profile.get("state", label))
        inferred_fact_values: dict[str, Any] = {}
        required_facts = _required_postcondition_facts(
            postcondition_function,
            environment={
                **source_values,
                "label": label,
                "expectation": profile,
                "kind": kind,
                "state_name": state_name,
                "canonical_page": str(profile.get("canonical_page", "")),
            },
            inferred_values=inferred_fact_values,
        )
        for fact_name, inferred_value in inferred_fact_values.items():
            expected_values.setdefault(fact_name, inferred_value)
        if not set(expected_values).issubset(required_facts):
            raise CaptureValidationError(
                (f"expected state values are outside fact schema for {label}",)
            )
        result[label] = {
            "kind": kind,
            "profile": profile,
            "required_facts": required_facts,
            "expected_fact_values": expected_values,
            "fact_constraints": (
                {"keyboard_focus_fixture_cleared": "focus-cleared-object"}
                if "keyboard_focus_fixture_cleared" in required_facts
                else {}
            ),
        }
    return result


def _canonical_digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def load_capture_scenario_contracts(
    source_path: Path = DEFAULT_CAPTURE_SOURCE,
    *,
    contract: CaptureContract | None = None,
) -> dict[str, dict[str, Any]]:
    """Load callable, checkpoint, and fixture identities offline."""

    module = _source_module(source_path)
    contract = contract or load_capture_contract(source_path)
    current_surfaces = (
        _current_surface_map() if _is_current_contract_source(source_path) else None
    )
    selected_names = {
        "EXHAUSTIVE_CAPTURE_FACE_GROUPS",
        "EXHAUSTIVE_CAPTURE_FACE_LABELS",
        "EXHAUSTIVE_CAPTURE_SCENARIO_CALLABLES",
        "CAPTURE_SCENARIO_HIDDEN_METHOD_REFERENCES",
        "CAPTURE_SCENARIO_SETUP_BOUNDARY",
        "CAPTURE_SCENARIO_FRESH_LABELS",
        "CAPTURE_SCENARIO_NURTURED_ACTIVE_LABELS",
        "CAPTURE_SCENARIO_DEVELOPMENT_STRESS_LABELS",
    }
    selected_functions = {
        "capture_scenario_internal_setups",
        "capture_scenario_prerequisites",
        "capture_scenario_checkpoint",
    }
    namespace: dict[str, Any] = {}
    if current_surfaces is None:
        selected: list[ast.stmt] = []
        for node in module.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if any(
                    isinstance(target, ast.Name) and target.id in selected_names
                    for target in targets
                ):
                    selected.append(node)
            elif isinstance(node, ast.FunctionDef) and node.name in selected_functions:
                selected.append(node)
        namespace = {"frozenset": frozenset, "range": range}
        try:
            exec(
                compile(
                    ast.Module(body=selected, type_ignores=[]),
                    str(source_path),
                    "exec",
                ),
                namespace,
            )
        except Exception as error:
            raise CaptureValidationError(
                (f"capture scenario metadata could not be evaluated: {error}",)
            ) from error
        full_labels = tuple(namespace.get("EXHAUSTIVE_CAPTURE_FACE_LABELS", ()))
        callable_rows = tuple(
            namespace.get("EXHAUSTIVE_CAPTURE_SCENARIO_CALLABLES", ())
        )
    else:
        full_contract = load_capture_contract(source_path, profile="full")
        full_labels = full_contract.labels
        callable_rows = tuple(
            (label, str(current_surfaces[label].get("executor", "")))
            for label in full_labels
        )
    callable_map = dict(callable_rows)
    if (
        not full_labels
        or len(callable_rows) != len(full_labels)
        or tuple(callable_map) != full_labels
        or len(callable_map) != len(full_labels)
    ):
        raise CaptureValidationError(
            ("capture scenario callable identities must cover the full profile",)
        )

    runner = next(
        (
            node for node in module.body
            if isinstance(node, ast.ClassDef)
            and node.name == "_UiFaceCaptureRunner"
        ),
        None,
    )
    if not isinstance(runner, ast.ClassDef):
        raise CaptureValidationError(("capture runner class is unavailable",))
    source_text = source_path.read_text(encoding="utf-8")
    method_nodes = {
        node.name: node
        for node in runner.body
        if isinstance(node, ast.FunctionDef)
    }
    method_fragment_hashes: dict[str, str] = {}
    method_references: dict[str, frozenset[str]] = {}

    def runner_method_references(node: ast.FunctionDef) -> frozenset[str]:
        references = {
            child.attr
            for child in ast.walk(node)
            if (
                isinstance(child, ast.Attribute)
                and isinstance(child.value, ast.Name)
                and child.value.id in {"self", "cls"}
                and child.attr in method_nodes
            )
        }
        references.update(
            str(child.args[1].value)
            for child in ast.walk(node)
            if (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id == "getattr"
                and len(child.args) >= 2
                and isinstance(child.args[0], ast.Name)
                and child.args[0].id in {"self", "cls"}
                and isinstance(child.args[1], ast.Constant)
                and isinstance(child.args[1].value, str)
                and child.args[1].value in method_nodes
            )
        )
        return frozenset(references)

    for name, node in method_nodes.items():
        fragment = ast.get_source_segment(source_text, node)
        if fragment is None:
            raise CaptureValidationError(
                (f"capture method source is unavailable for {name!r}",)
            )
        method_fragment_hashes[name] = hashlib.sha256(
            fragment.encode("utf-8")
        ).hexdigest()
        method_references[name] = runner_method_references(node)

    hidden_raw = (
        {"_next_after": ("_next_step",)}
        if current_surfaces is not None else
        namespace.get("CAPTURE_SCENARIO_HIDDEN_METHOD_REFERENCES", {})
    )
    if not isinstance(hidden_raw, dict):
        raise CaptureValidationError(
            ("CAPTURE_SCENARIO_HIDDEN_METHOD_REFERENCES must be a mapping",)
        )
    hidden_references: set[tuple[str, str]] = set()
    for raw_caller, raw_callees in hidden_raw.items():
        caller = str(raw_caller)
        if caller not in method_nodes or not isinstance(raw_callees, (tuple, list)):
            raise CaptureValidationError(
                (f"capture scenario hidden caller is invalid: {caller!r}",)
            )
        for raw_callee in raw_callees:
            callee = str(raw_callee)
            if callee not in method_references[caller]:
                raise CaptureValidationError(
                    (
                        "capture scenario hidden edge is not a runner method "
                        f"reference: {caller} -> {callee}",
                    )
                )
            hidden_references.add((caller, callee))
    method_dependencies = {
        name: tuple(sorted(
            reference for reference in references
            if (name, reference) not in hidden_references
        ))
        for name, references in method_references.items()
    }

    top_level_nodes: dict[str, ast.stmt] = {}
    for node in module.body:
        names: list[str] = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.append(node.name)
        elif isinstance(node, ast.Assign):
            names.extend(
                target.id for target in node.targets
                if isinstance(target, ast.Name)
            )
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.append(node.target.id)
        for name in names:
            top_level_nodes[name] = node
    top_level_fragment_hashes: dict[str, str] = {}
    top_level_dependencies: dict[str, tuple[str, ...]] = {}
    for name, node in top_level_nodes.items():
        fragment = ast.get_source_segment(source_text, node)
        if fragment is None:
            raise CaptureValidationError(
                (f"capture top-level source is unavailable for {name!r}",)
            )
        top_level_fragment_hashes[name] = hashlib.sha256(
            fragment.encode("utf-8")
        ).hexdigest()
        top_level_dependencies[name] = tuple(sorted({
            child.id
            for child in ast.walk(node)
            if (
                isinstance(child, ast.Name)
                and isinstance(child.ctx, ast.Load)
                and child.id in top_level_nodes
                and child.id != name
            )
        }))
    method_top_level_dependencies = {
        name: tuple(sorted({
            child.id
            for child in ast.walk(node)
            if (
                isinstance(child, ast.Name)
                and isinstance(child.ctx, ast.Load)
                and child.id in top_level_nodes
            )
        }))
        for name, node in method_nodes.items()
    }

    dependency_cache: dict[
        str,
        tuple[dict[str, str], dict[str, str]],
    ] = {}

    def method_dependency_inputs(
        root_method: str,
    ) -> tuple[dict[str, str], dict[str, str]]:
        if root_method in dependency_cache:
            methods, top_level = dependency_cache[root_method]
            return dict(methods), dict(top_level)
        pending = [root_method]
        visited: set[str] = set()
        fragments: dict[str, str] = {}
        while pending:
            name = pending.pop()
            if name in visited:
                continue
            visited.add(name)
            if name not in method_nodes:
                raise CaptureValidationError(
                    (f"capture scenario references missing method {name!r}",)
                )
            fragments[name] = method_fragment_hashes[name]
            pending.extend(
                child for child in method_dependencies[name]
                if child not in visited
            )
        pending_top_level = sorted({
            dependency
            for method_name in visited
            for dependency in method_top_level_dependencies[method_name]
        })
        visited_top_level: set[str] = set()
        top_level_fragments: dict[str, str] = {}
        while pending_top_level:
            name = pending_top_level.pop()
            if name in visited_top_level:
                continue
            visited_top_level.add(name)
            digest = top_level_fragment_hashes.get(name)
            if digest is None:
                raise CaptureValidationError(
                    (f"capture scenario references missing top-level input {name!r}",)
                )
            top_level_fragments[name] = digest
            pending_top_level.extend(
                dependency for dependency in top_level_dependencies[name]
                if dependency not in visited_top_level
            )
        method_result = dict(sorted(fragments.items()))
        top_level_result = dict(sorted(top_level_fragments.items()))
        dependency_cache[root_method] = (method_result, top_level_result)
        return dict(method_result), dict(top_level_result)

    renderer_families = load_expected_renderer_families(
        source_path,
        contract=contract,
    )
    state_contracts = load_expected_state_evidence_contracts(
        source_path,
        contract=contract,
    )
    if current_surfaces is None:
        internal_setups = namespace["capture_scenario_internal_setups"]
        prerequisites = namespace["capture_scenario_prerequisites"]
        checkpoint = namespace["capture_scenario_checkpoint"]
    else:
        internal_setups = lambda label: tuple(
            current_surfaces[label].get("internal_setups", ())
        )
        prerequisites = lambda label: tuple(
            current_surfaces[label].get("prerequisites", ())
        )
        checkpoint = lambda label: str(current_surfaces[label].get("checkpoint", ""))
    results: dict[str, dict[str, Any]] = {}
    for label in contract.labels:
        callable_name = str(callable_map.get(label, ""))
        raw_surface = (
            current_surfaces.get(label, {})
            if current_surfaces is not None else
            {}
        )
        scenario_id = str(raw_surface.get("scenario_id", label))
        fixture_id = str(raw_surface.get("fixture_id", f"{label}-v1"))
        scenario_step = raw_surface.get("scenario_step", 1)
        setup_values = tuple(str(value) for value in internal_setups(label))
        prerequisite_values = tuple(str(value) for value in prerequisites(label))
        checkpoint_value = str(checkpoint(label))
        if (
            not callable_name
            or not setup_values
            or not checkpoint_value
            or not scenario_id
            or not fixture_id
            or type(scenario_step) is not int
            or scenario_step < 1
            or any(value not in full_labels for value in prerequisite_values)
        ):
            raise CaptureValidationError(
                (f"capture scenario identity is incomplete for {label}",)
            )
        method_inputs, top_level_inputs = method_dependency_inputs(callable_name)
        identity = {
            "label": label,
            "scenario_id": scenario_id,
            "fixture_id": fixture_id,
            "scenario_step": scenario_step,
            "callable": callable_name,
            "checkpoint": checkpoint_value,
            "capture_prerequisites": list(prerequisite_values),
            "internal_setups": list(setup_values),
            "renderer_family": renderer_families[label],
            "state_contract": state_contracts[label],
            "method_inputs": method_inputs,
            "top_level_inputs": top_level_inputs,
        }
        if current_surfaces is not None:
            identity["surface_spec_dependency_digest"] = str(
                current_surfaces[label].get("dependency_digest", "")
            )
        identity["digest"] = _canonical_digest(identity)
        results[label] = identity
    return results


def _load_json_object(path: Path, description: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise CaptureValidationError((f"could not read {description} {path}: {error}",)) from error
    except json.JSONDecodeError as error:
        raise CaptureValidationError((f"invalid JSON in {description} {path}: {error}",)) from error
    if not isinstance(payload, dict):
        raise CaptureValidationError((f"{description} must contain a JSON object",))
    return payload


def _resolved_evidence_path(raw_path: Any, parent: Path) -> Path | None:
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = parent / path
    return path.resolve()


def _inside_directory(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


def _read_png(path: Path, *, normalize_pixels: bool = True) -> PngEvidence | None:
    """Verify the complete PNG stream and decode every filtered image row."""

    try:
        payload = path.read_bytes()
    except OSError:
        return None
    if len(payload) < 45 or payload[:8] != PNG_SIGNATURE:
        return None
    offset = len(PNG_SIGNATURE)
    dimensions: tuple[int, int] | None = None
    bit_depth = -1
    color_type = -1
    palette: bytes | None = None
    transparency: bytes | None = None
    image_data: list[bytes] = []
    saw_idat = False
    idat_ended = False
    while offset < len(payload):
        if offset + 12 > len(payload):
            return None
        length = struct.unpack(">I", payload[offset : offset + 4])[0]
        chunk_type = payload[offset + 4 : offset + 8]
        chunk_end = offset + 12 + length
        if chunk_end > len(payload):
            return None
        chunk_data = payload[offset + 8 : offset + 8 + length]
        expected_crc = struct.unpack(">I", payload[offset + 8 + length : chunk_end])[0]
        actual_crc = zlib.crc32(chunk_type)
        actual_crc = zlib.crc32(chunk_data, actual_crc) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            return None
        if dimensions is None:
            if chunk_type != b"IHDR" or length != 13:
                return None
            width, height = struct.unpack(">II", chunk_data[:8])
            bit_depth, color_type, compression, filtering, interlace = chunk_data[8:]
            valid_depths = {
                0: {1, 2, 4, 8, 16},
                2: {8, 16},
                3: {1, 2, 4, 8},
                4: {8, 16},
                6: {8, 16},
            }
            if (
                width < 1
                or height < 1
                or width * height > MAX_PNG_PIXELS
                or color_type not in valid_depths
                or bit_depth not in valid_depths[color_type]
                or compression != 0
                or filtering != 0
                or interlace != 0
            ):
                return None
            dimensions = (width, height)
        elif chunk_type == b"IHDR":
            return None
        elif chunk_type == b"PLTE":
            if saw_idat or length == 0 or length % 3 or length > 768:
                return None
            palette = chunk_data
        elif chunk_type == b"tRNS":
            if saw_idat:
                return None
            transparency = chunk_data
        if chunk_type == b"IDAT":
            if idat_ended:
                return None
            saw_idat = True
            image_data.append(chunk_data)
        elif saw_idat and chunk_type != b"IEND":
            idat_ended = True
        if chunk_type == b"IEND":
            if length != 0 or chunk_end != len(payload) or not saw_idat or dimensions is None:
                return None
            break
        offset = chunk_end
    else:
        return None

    width, height = dimensions
    if color_type == 3 and palette is None:
        return None
    if color_type not in {0, 2, 3} and transparency is not None:
        return None
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]
    row_bytes = (width * channels * bit_depth + 7) // 8
    expected_size = height * (row_bytes + 1)
    try:
        decompressor = zlib.decompressobj()
        decoded = decompressor.decompress(b"".join(image_data), expected_size + 1)
        if decompressor.unconsumed_tail or len(decoded) > expected_size:
            return None
        decoded += decompressor.flush()
    except zlib.error:
        return None
    if (
        not decompressor.eof
        or decompressor.unused_data
        or len(decoded) != expected_size
    ):
        return None

    cursor = 0
    for _row_index in range(height):
        if decoded[cursor] > 4:
            return None
        cursor += row_bytes + 1
    if not normalize_pixels:
        return PngEvidence(width, height, "", 0, 1.0)

    try:
        with Image.open(path) as opened:
            if opened.format != "PNG" or opened.size != (width, height):
                return None
            opened.load()
            rgba = opened.convert("RGBA")
            rgba.load()
            rgba_bytes = rgba.tobytes()
            sample_width = min(width, 128)
            sample_height = min(height, 128)
            sampled = rgba.resize(
                (sample_width, sample_height),
                Image.Resampling.NEAREST,
            )
            sampled_colors = sampled.getcolors(
                maxcolors=sample_width * sample_height,
            )
    except (OSError, UnidentifiedImageError, ValueError):
        return None
    if not sampled_colors:
        return None
    sampled_pixels = sample_width * sample_height
    dominant_ratio = (
        max(count for count, _color in sampled_colors) / sampled_pixels
    )
    visual = hashlib.sha256()
    visual.update(struct.pack(">II", width, height))
    visual.update(rgba_bytes)
    return PngEvidence(
        width,
        height,
        visual.hexdigest(),
        len(sampled_colors),
        dominant_ratio,
    )


def _manifest_groups(payload: dict[str, Any]) -> tuple[tuple[str, tuple[str, ...]], ...] | None:
    raw_groups = payload.get("capture_groups")
    if not isinstance(raw_groups, list):
        return None
    groups: list[tuple[str, tuple[str, ...]]] = []
    for raw_group in raw_groups:
        if not isinstance(raw_group, dict):
            return None
        name = raw_group.get("name")
        labels = raw_group.get("labels")
        if not isinstance(name, str) or not isinstance(labels, list):
            return None
        if any(not isinstance(label, str) for label in labels):
            return None
        groups.append((name, tuple(labels)))
    return tuple(groups)


def _contact_sheet_slug(groups: Sequence[str]) -> str:
    raw = "-".join(name.replace(CONTINUED_SUFFIX, "") for name in groups)
    return re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-") or "ui-surfaces"


def expected_contact_sheet_page_groups(
    contract: CaptureContract,
) -> tuple[tuple[tuple[str, tuple[str, ...]], ...], ...]:
    """Return source labels in the generator-owned page/group topology."""

    capacity = CONTACT_SHEET_COLUMNS * CONTACT_SHEET_MAX_ROWS
    pages: list[tuple[tuple[str, tuple[str, ...]], ...]] = []
    current: list[tuple[str, tuple[str, ...]]] = []
    current_rows = 0
    for group_name, labels in contract.groups:
        if len(labels) > capacity:
            if current:
                pages.append(tuple(current))
                current = []
                current_rows = 0
            for offset in range(0, len(labels), capacity):
                chunk = tuple(labels[offset : offset + capacity])
                suffix = "" if offset == 0 else CONTINUED_SUFFIX
                pages.append(((f"{group_name}{suffix}", chunk),))
            continue
        group_rows = (len(labels) + CONTACT_SHEET_COLUMNS - 1) // CONTACT_SHEET_COLUMNS
        if current and current_rows + group_rows > CONTACT_SHEET_MAX_ROWS:
            pages.append(tuple(current))
            current = []
            current_rows = 0
        current.append((group_name, tuple(labels)))
        current_rows += group_rows
    if current:
        pages.append(tuple(current))
    return tuple(pages)


def expected_contact_sheet_pages(
    contract: CaptureContract,
) -> tuple[tuple[tuple[str, int], ...], ...]:
    """Return the generator-owned two-column, five-row page topology."""

    return tuple(
        tuple((name, len(labels)) for name, labels in page)
        for page in expected_contact_sheet_page_groups(contract)
    )


def expected_contact_sheet_dimensions(
    topology: Sequence[tuple[str, int]],
) -> tuple[int, int]:
    """Return the generator-owned canvas size for one topology page."""

    height = CONTACT_SHEET_HEADER_HEIGHT + CONTACT_SHEET_MARGIN
    for _group, surface_count in topology:
        rows = (surface_count + CONTACT_SHEET_COLUMNS - 1) // CONTACT_SHEET_COLUMNS
        height += (
            CONTACT_SHEET_GROUP_HEADER_HEIGHT
            + rows * CONTACT_SHEET_CELL_HEIGHT
            + CONTACT_SHEET_GROUP_GAP
        )
    return CONTACT_SHEET_WIDTH, height


def _contact_preview_issues(
    page_path: Path,
    page_groups: Sequence[tuple[str, Sequence[str]]],
    capture_paths: dict[str, Path],
) -> list[str]:
    """Bind review-aid tiles to raw, geometry-authoritative screenshots."""

    issues: list[str] = []
    cell_width = (
        CONTACT_SHEET_WIDTH
        - CONTACT_SHEET_MARGIN * 2
        - CONTACT_SHEET_GUTTER * (CONTACT_SHEET_COLUMNS - 1)
    ) // CONTACT_SHEET_COLUMNS
    try:
        with Image.open(page_path) as opened_page:
            opened_page.load()
            page_image = opened_page.convert("RGB")
        y = CONTACT_SHEET_HEADER_HEIGHT
        for _group_name, labels in page_groups:
            y += CONTACT_SHEET_GROUP_HEADER_HEIGHT
            for group_index, label in enumerate(labels):
                source_path = capture_paths.get(label)
                if source_path is None:
                    issues.append(f"contact preview {label}: manifest screenshot is missing")
                    continue
                row = group_index // CONTACT_SHEET_COLUMNS
                column = group_index % CONTACT_SHEET_COLUMNS
                x = CONTACT_SHEET_MARGIN + column * (
                    cell_width + CONTACT_SHEET_GUTTER
                )
                tile_y = y + row * CONTACT_SHEET_CELL_HEIGHT
                preview_box = (
                    x + CONTACT_SHEET_PREVIEW_SIDE,
                    tile_y + CONTACT_SHEET_PREVIEW_TOP,
                    x + cell_width - CONTACT_SHEET_PREVIEW_SIDE,
                    tile_y + CONTACT_SHEET_CELL_HEIGHT - CONTACT_SHEET_PREVIEW_BOTTOM,
                )
                with Image.open(source_path) as opened_source:
                    opened_source.load()
                    source = ImageOps.exif_transpose(opened_source).convert("RGB")
                    max_width = (
                        preview_box[2] - preview_box[0]
                        - CONTACT_SHEET_PREVIEW_INSET * 2
                    )
                    max_height = (
                        preview_box[3] - preview_box[1]
                        - CONTACT_SHEET_PREVIEW_INSET * 2
                    )
                    preview = ImageOps.contain(
                        source,
                        (min(source.width, max_width), min(source.height, max_height)),
                        method=Image.Resampling.LANCZOS,
                    )
                preview_x = (
                    preview_box[0]
                    + (preview_box[2] - preview_box[0] - preview.width) // 2
                )
                preview_y = preview_box[1] + CONTACT_SHEET_PREVIEW_INSET
                actual = page_image.crop((
                    preview_x,
                    preview_y,
                    preview_x + preview.width,
                    preview_y + preview.height,
                ))
                if ImageChops.difference(actual, preview).getbbox() is not None:
                    issues.append(
                        f"contact preview {label}: pixels do not match manifest screenshot"
                    )
                frame_mid_x = (preview_box[0] + preview_box[2]) // 2
                frame_mid_y = (preview_box[1] + preview_box[3]) // 2
                frame_outline_points = [
                    (frame_mid_x, preview_box[1] + offset)
                    for offset in range(CONTACT_SHEET_FRAME_OUTLINE_WIDTH)
                ] + [
                    (frame_mid_x, preview_box[3] - offset)
                    for offset in range(CONTACT_SHEET_FRAME_OUTLINE_WIDTH)
                ] + [
                    (preview_box[0] + offset, frame_mid_y)
                    for offset in range(CONTACT_SHEET_FRAME_OUTLINE_WIDTH)
                ] + [
                    (preview_box[2] - offset, frame_mid_y)
                    for offset in range(CONTACT_SHEET_FRAME_OUTLINE_WIDTH)
                ]
                if any(
                    page_image.getpixel(point)
                    != CONTACT_SHEET_PREVIEW_FRAME_OUTLINE
                    for point in frame_outline_points
                ):
                    issues.append(
                        f"contact preview {label}: light preview frame outline is missing"
                    )
                frame_fill_points = (
                    (frame_mid_x, preview_box[1] + CONTACT_SHEET_FRAME_OUTLINE_WIDTH + 1),
                    (frame_mid_x, preview_box[3] - CONTACT_SHEET_FRAME_OUTLINE_WIDTH - 1),
                    (preview_box[0] + CONTACT_SHEET_FRAME_OUTLINE_WIDTH + 1, frame_mid_y),
                    (preview_box[2] - CONTACT_SHEET_FRAME_OUTLINE_WIDTH - 1, frame_mid_y),
                )
                if any(
                    page_image.getpixel(point)
                    != CONTACT_SHEET_PREVIEW_FRAME_FILL
                    for point in frame_fill_points
                ):
                    issues.append(
                        f"contact preview {label}: unused frame is not the distinct light fill"
                    )

                outline_left = preview_x - CONTACT_SHEET_OUTLINE_WIDTH
                outline_top = preview_y - CONTACT_SHEET_OUTLINE_WIDTH
                outline_right = preview_x + preview.width + CONTACT_SHEET_OUTLINE_WIDTH - 1
                outline_bottom = preview_y + preview.height + CONTACT_SHEET_OUTLINE_WIDTH - 1
                screenshot_outline_points = [
                    (preview_x, outline_top + offset)
                    for offset in range(CONTACT_SHEET_OUTLINE_WIDTH)
                ] + [
                    (preview_x, outline_bottom - offset)
                    for offset in range(CONTACT_SHEET_OUTLINE_WIDTH)
                ] + [
                    (outline_left + offset, preview_y)
                    for offset in range(CONTACT_SHEET_OUTLINE_WIDTH)
                ] + [
                    (outline_right - offset, preview_y)
                    for offset in range(CONTACT_SHEET_OUTLINE_WIDTH)
                ]
                if any(
                    page_image.getpixel(point)
                    != CONTACT_SHEET_SCREENSHOT_OUTLINE
                    for point in screenshot_outline_points
                ):
                    issues.append(
                        f"contact preview {label}: explicit screenshot outline is missing"
                    )
            y += (
                math.ceil(len(labels) / CONTACT_SHEET_COLUMNS)
                * CONTACT_SHEET_CELL_HEIGHT
                + CONTACT_SHEET_GROUP_GAP
            )
    except (OSError, UnidentifiedImageError, ValueError) as error:
        issues.append(f"could not bind contact preview pixels: {error}")
    return issues


def _canonical_json_text(value: Any) -> str:
    """Serialize embedded provenance in one stable representation."""

    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _surface_scenario_identity_map(
    labels: Sequence[str],
    scenario_contracts: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Project only the scenario fields that must travel with PNG evidence."""

    identity_map: dict[str, dict[str, Any]] = {}
    for label in labels:
        scenario = scenario_contracts.get(label)
        if not isinstance(scenario, Mapping):
            raise CaptureValidationError((
                f"scenario identity is unavailable for {label}",
            ))
        identity_map[label] = {
            "scenario_id": scenario.get("scenario_id"),
            "fixture_id": scenario.get("fixture_id"),
            "scenario_step": scenario.get("scenario_step"),
        }
    return identity_map


def _read_png_text_metadata(path: Path) -> tuple[dict[str, str] | None, str | None]:
    try:
        with Image.open(path) as opened:
            opened.load()
            return (
                {str(key): str(value) for key, value in opened.text.items()},
                None,
            )
    except (OSError, UnidentifiedImageError, ValueError) as error:
        return None, str(error)


def _raw_scenario_metadata_issues(
    page_path: Path,
    scenario_contract: Mapping[str, Any],
) -> list[str]:
    """Verify scalar v26 scenario provenance embedded in one raw screenshot."""

    metadata, error = _read_png_text_metadata(page_path)
    if metadata is None:
        return [f"could not read raw PNG scenario provenance: {error}"]
    issues: list[str] = []
    for identity_field in ("scenario_id", "fixture_id", "scenario_step"):
        expected = str(scenario_contract.get(identity_field, ""))
        if metadata.get(identity_field) != expected:
            issues.append(
                f"PNG metadata {identity_field!r} must be {expected!r}"
            )
    return issues


def _contact_scenario_metadata_issues(
    metadata: Mapping[str, str],
    surface_identity_map: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    """Verify the deterministic, per-page v26 scenario identity projection."""

    expected_metadata = {
        "surface_ids": _canonical_json_text(list(surface_identity_map)),
        "surface_identity_map": _canonical_json_text(surface_identity_map),
    }
    for identity_field in ("scenario_id", "fixture_id", "scenario_step"):
        expected_metadata[identity_field] = _canonical_json_text({
            label: identity.get(identity_field)
            for label, identity in surface_identity_map.items()
        })
    return [
        f"PNG metadata {key!r} must be {value!r}"
        for key, value in expected_metadata.items()
        if metadata.get(key) != value
    ]


def _contact_metadata_issues(
    page_path: Path,
    *,
    page_number: int,
    page_count: int,
    package_version: str,
    package_sha256: str,
    manifest_path: Path,
    capture_profile: str,
    capture_contract_digest: str,
    surface_identity_map: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    """Verify generator-owned PNG text provenance for one contact page."""

    metadata, error = _read_png_text_metadata(page_path)
    if metadata is None:
        return [f"could not read contact-sheet PNG provenance: {error}"]

    issues: list[str] = []
    expected = {
        "Anki Garden release": package_version,
        "Package SHA-256": package_sha256,
        "Contact sheet page": f"{page_number} of {page_count}",
        "Capture profile": capture_profile,
        "Capture contract digest": capture_contract_digest,
        "Padding legend": CONTACT_SHEET_PADDING_LEGEND,
        "Quality status": CONTACT_SHEET_QUALITY_STATUS,
    }
    for key, value in expected.items():
        if metadata.get(key) != value:
            issues.append(f"PNG metadata {key!r} must be {value!r}")
    raw_manifest = metadata.get("Capture manifest")
    resolved_manifest = _resolved_evidence_path(raw_manifest, page_path.parent)
    if resolved_manifest != manifest_path.resolve():
        issues.append("PNG metadata 'Capture manifest' references a different manifest")
    issues.extend(
        _contact_scenario_metadata_issues(metadata, surface_identity_map)
    )
    return issues


def _strict_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _strict_size(value: Any, *, minimum: int = 1) -> tuple[int, int] | None:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or any(type(item) is not int or item < minimum for item in value)
    ):
        return None
    return value[0], value[1]


def dialog_scroll_state_observation_issue_codes(
    observation: Any,
) -> tuple[str, ...]:
    """Independently validate one painted scroll-state witness."""

    if not isinstance(observation, dict):
        return ("invalid-scroll-state-observation",)
    issues: list[str] = []
    state = str(observation.get("state", ""))
    if state not in DIALOG_SCROLL_FOUR_STATE_NAMES:
        issues.append("unknown-scroll-state")
    if observation.get("painted") is not True:
        issues.append("scroll-state-not-painted")
    digest = observation.get("paint_digest")
    if not isinstance(digest, str) or len(digest) != 64:
        issues.append("invalid-scroll-state-paint-digest")
    paint_size = observation.get("paint_size")
    if not (
        isinstance(paint_size, list)
        and len(paint_size) == 2
        and all(type(value) is int and value > 0 for value in paint_size)
    ):
        issues.append("invalid-scroll-state-paint-size")
    integer_fields = (
        "row_count",
        "scroll_minimum",
        "scroll_maximum",
        "scroll_value",
        "horizontal_scroll_minimum",
        "horizontal_scroll_maximum",
        "content_width",
        "viewport_width",
        "viewport_height",
    )
    invalid = [
        field for field in integer_fields
        if type(observation.get(field)) is not int
    ]
    issues.extend(f"invalid-scroll-state-metric:{field}" for field in invalid)
    for field in (
        "vertical_scrollbar_visible",
        "horizontal_scrollbar_visible",
    ):
        if type(observation.get(field)) is not bool:
            issues.append(f"invalid-scroll-state-metric:{field}")
    intrusions = observation.get("fixed_region_intrusions")
    if not isinstance(intrusions, list):
        issues.append("invalid-fixed-region-intrusions")
    elif intrusions:
        issues.append("scrollbar-fixed-region-intrusion")
    if invalid or any(
        issue.startswith("invalid-scroll-state-metric:")
        for issue in issues
    ):
        return tuple(dict.fromkeys(issues))

    row_count = int(observation["row_count"])
    scroll_minimum = int(observation["scroll_minimum"])
    scroll_maximum = int(observation["scroll_maximum"])
    scroll_value = int(observation["scroll_value"])
    horizontal_minimum = int(observation["horizontal_scroll_minimum"])
    horizontal_maximum = int(observation["horizontal_scroll_maximum"])
    content_width = int(observation["content_width"])
    viewport_width = int(observation["viewport_width"])
    viewport_height = int(observation["viewport_height"])
    scroll_span = scroll_maximum - scroll_minimum
    if (
        row_count < 0
        or scroll_minimum < 0
        or scroll_maximum < scroll_minimum
        or not scroll_minimum <= scroll_value <= scroll_maximum
        or viewport_width <= 0
        or viewport_height <= 0
        or content_width <= 0
    ):
        issues.append("invalid-scroll-state-geometry")
    if (
        horizontal_maximum != horizontal_minimum
        or observation.get("horizontal_scrollbar_visible") is True
        or content_width > viewport_width
    ):
        issues.append("horizontal-scroll-overflow")
    if state == "no-overflow-list":
        if scroll_span != 0:
            issues.append("no-overflow-state-has-scroll-range")
        if observation.get("vertical_scrollbar_visible") is True:
            issues.append("scrollbar-shown-when-content-fits")
    elif state == "one-row-list":
        if row_count != 1:
            issues.append("one-row-state-row-count")
        if scroll_span != 0:
            issues.append("one-row-state-has-scroll-range")
        if observation.get("vertical_scrollbar_visible") is True:
            issues.append("scrollbar-shown-when-content-fits")
    elif state == "enough-rows-to-scroll":
        if row_count < 2:
            issues.append("scrolling-state-row-count")
        if scroll_span <= 0:
            issues.append("scrolling-state-missing-range")
        if scroll_value != scroll_minimum:
            issues.append("scrolling-state-not-at-start")
    elif state == "final-item-at-maximum-scroll":
        if row_count < 2:
            issues.append("maximum-scroll-state-row-count")
        if scroll_span <= 0:
            issues.append("maximum-scroll-state-missing-range")
        if scroll_value != scroll_maximum:
            issues.append("maximum-scroll-value")
        final_bounds = observation.get("final_item_bounds")
        if not (
            isinstance(final_bounds, list)
            and len(final_bounds) == 4
            and all(type(value) is int for value in final_bounds)
            and int(final_bounds[2]) > 0
            and int(final_bounds[3]) > 0
        ):
            issues.append("invalid-final-item-bounds")
        else:
            _left, top, _width, height = final_bounds
            if top < 0 or top + height > viewport_height:
                issues.append("clipped-final-row")
        if observation.get("final_item_visible") is not True:
            issues.append("final-item-not-visible")
    if observation.get("issues") not in (None, []):
        issues.append("scroll-state-reported-issues")
    if observation.get("passed") not in (None, True):
        issues.append("scroll-state-did-not-pass")
    return tuple(dict.fromkeys(issues))


def dialog_scroll_state_matrix_issue_codes(
    matrix: Any,
    *,
    require_complete: bool,
) -> tuple[str, ...]:
    """Independently validate local or aggregate four-state evidence."""

    if not isinstance(matrix, dict):
        return ("missing-scroll-state-matrix",)
    observations = matrix.get("observations")
    if not isinstance(observations, list):
        return ("invalid-scroll-state-observations",)
    issues: list[str] = []
    seen: set[str] = set()
    for index, observation in enumerate(observations):
        if not isinstance(observation, dict):
            issues.append(f"invalid-scroll-state-observation:{index}")
            continue
        state = str(observation.get("state", ""))
        if state in seen:
            issues.append(f"duplicate-scroll-state:{state}")
        seen.add(state)
        issues.extend(
            f"{state or index}:{issue}"
            for issue in dialog_scroll_state_observation_issue_codes(
                observation
            )
        )
    if matrix.get("canonical_scroll_restored") is not True:
        issues.append("canonical-scroll-not-restored")
    before = matrix.get("canonical_scroll_value_before")
    after = matrix.get("canonical_scroll_value_after")
    if type(before) is not int or type(after) is not int or before != after:
        issues.append("canonical-scroll-value-mismatch")
    if require_complete:
        for state in DIALOG_SCROLL_FOUR_STATE_NAMES:
            if state not in seen:
                issues.append(f"missing-scroll-state:{state}")
    if matrix.get("issues") not in (None, []):
        issues.append("scroll-state-matrix-reported-issues")
    if matrix.get("passed") not in (None, True):
        issues.append("scroll-state-matrix-did-not-pass")
    return tuple(dict.fromkeys(issues))


def dialog_scroll_audit_issue_codes(
    audit: Any,
    *,
    expected_surface: str = "",
    expected_page_semantic: str = "",
) -> tuple[str, ...]:
    """Independently validate positive scroll/footer geometry evidence."""

    if not isinstance(audit, dict):
        return ("missing-dialog-scroll-audit",)
    issues: list[str] = []
    if audit.get("applicable") is not True:
        issues.append("dialog-scroll-audit-not-applicable")
    if audit.get("passed") is not True:
        issues.append("dialog-scroll-audit-did-not-pass")
    if audit.get("issues") != []:
        issues.append("dialog-scroll-audit-reported-issues")
    if (
        not isinstance(audit.get("scroll_name"), str)
        or not str(audit.get("scroll_name", "")).strip()
    ):
        issues.append("missing-scroll-name")
    expected_scroll_name = audit.get("expected_scroll_name")
    if not isinstance(expected_scroll_name, str):
        issues.append("invalid-expected-scroll-name")
    elif (
        expected_scroll_name
        and audit.get("scroll_name") != expected_scroll_name
    ):
        issues.append("unexpected-scroll-owner")
    if expected_surface and audit.get("surface") != expected_surface:
        issues.append("scroll-coverage-surface-mismatch")
    if expected_page_semantic:
        if audit.get("expected_page_semantic") != expected_page_semantic:
            issues.append("expected-scroll-page-semantic-mismatch")
        if audit.get("actual_page_semantic") != expected_page_semantic:
            issues.append("actual-scroll-page-semantic-mismatch")
    if "four_state_scroll_matrix" in audit:
        issues.extend(
            f"scroll-state:{issue}"
            for issue in dialog_scroll_state_matrix_issue_codes(
                audit.get("four_state_scroll_matrix"),
                require_complete=False,
            )
        )

    integer_fields = (
        "registered_count",
        "active_count",
        "footer_height",
        "footer_top",
        "viewport_top",
        "viewport_height",
        "viewport_bottom",
        "declared_clearance",
        "layout_clearance",
        "content_height",
        "content_size_hint_height",
        "content_minimum_size_hint_height",
        "scroll_minimum",
        "scroll_maximum",
        "last_body_child_bottom",
        "last_body_child_bottom_at_scroll_end",
        "required_content_height",
        "reachable_content_height",
    )
    invalid_metrics = [
        field for field in integer_fields
        if type(audit.get(field)) is not int
    ]
    issues.extend(f"invalid-scroll-metric:{field}" for field in invalid_metrics)
    footer_visible = audit.get("footer_visible")
    require_no_scroll = audit.get("require_no_scroll")
    if type(footer_visible) is not bool:
        issues.append("invalid-footer-visibility")
    if type(require_no_scroll) is not bool:
        issues.append("invalid-require-no-scroll")
    if (
        invalid_metrics
        or type(footer_visible) is not bool
        or type(require_no_scroll) is not bool
    ):
        return tuple(dict.fromkeys(issues))

    progress_cards_page = bool(
        audit.get("surface") == "Garden Progress"
        and audit.get("actual_page_semantic") in {
            "GardenProgressDialog:achievements",
            "GardenProgressDialog:collection",
        }
    )
    if progress_cards_page:
        if audit.get("fixed_progress_header") is not True:
            issues.append("missing-fixed-progress-header")
        progress_integer_fields = (
            "complete_row_available_height",
            "complete_row_viewport_height",
            "complete_row_bottom_gutter",
            "complete_row_content_origin_y",
            "complete_row_bottom_padding",
        )
        invalid_progress_metrics = [
            field for field in progress_integer_fields
            if type(audit.get(field)) is not int
        ]
        issues.extend(
            f"invalid-progress-scroll-metric:{field}"
            for field in invalid_progress_metrics
        )
        boundaries = audit.get("complete_row_boundaries")
        eligible_boundaries = audit.get("complete_row_eligible_boundaries")
        if not (
            isinstance(boundaries, list)
            and boundaries
            and all(type(value) is int and value > 0 for value in boundaries)
        ):
            issues.append("invalid-complete-row-boundaries")
        if not (
            isinstance(eligible_boundaries, list)
            and eligible_boundaries
            and all(
                type(value) is int and value > 0
                for value in eligible_boundaries
            )
        ):
            issues.append("invalid-complete-row-eligible-boundaries")
        if (
            invalid_progress_metrics
            or "invalid-complete-row-boundaries" in issues
            or "invalid-complete-row-eligible-boundaries" in issues
        ):
            return tuple(dict.fromkeys(issues))
        available_height = int(audit["complete_row_available_height"])
        complete_viewport_height = int(
            audit["complete_row_viewport_height"]
        )
        bottom_gutter = int(audit["complete_row_bottom_gutter"])
        bottom_padding = int(audit["complete_row_bottom_padding"])
        viewport_metric = int(audit["viewport_height"])
        if bottom_gutter > 20:
            issues.append("excess-complete-row-gutter")
        if bottom_padding < 12:
            issues.append("insufficient-progress-bottom-padding")
        if available_height != viewport_metric + bottom_gutter:
            issues.append("complete-row-available-height-mismatch")
        if complete_viewport_height != viewport_metric:
            issues.append("complete-row-viewport-height-mismatch")
        if max(eligible_boundaries) != viewport_metric:
            issues.append("complete-row-boundary-mismatch")
        if (
            eligible_boundaries != sorted(set(eligible_boundaries))
            or boundaries != sorted(set(boundaries))
            or not set(eligible_boundaries).issubset(boundaries)
            or any(value > available_height for value in eligible_boundaries)
        ):
            issues.append("inconsistent-complete-row-boundaries")

    registered = int(audit["registered_count"])
    active = int(audit["active_count"])
    expected_active_value = audit.get("expected_active_count", 1)
    if type(expected_active_value) is not int or expected_active_value not in {0, 1}:
        issues.append("invalid-expected-active-scroll-count")
        expected_active = 1
    else:
        expected_active = int(expected_active_value)
    footer_height = int(audit["footer_height"])
    footer_top = int(audit["footer_top"])
    viewport_top = int(audit["viewport_top"])
    viewport_height = int(audit["viewport_height"])
    viewport_bottom = int(audit["viewport_bottom"])
    declared_clearance = int(audit["declared_clearance"])
    layout_clearance = int(audit["layout_clearance"])
    content_height = int(audit["content_height"])
    size_hint = int(audit["content_size_hint_height"])
    minimum_hint = int(audit["content_minimum_size_hint_height"])
    scroll_minimum = int(audit["scroll_minimum"])
    scroll_maximum = int(audit["scroll_maximum"])
    last_body_child_bottom = int(audit["last_body_child_bottom"])
    last_body_child_bottom_at_scroll_end = int(
        audit["last_body_child_bottom_at_scroll_end"]
    )
    required = int(audit["required_content_height"])
    reachable = int(audit["reachable_content_height"])

    if registered < 1:
        issues.append("registered-scroll-count")
    if active != expected_active:
        issues.append("active-scroll-count")
    nonnegative = {
        "footer_height": footer_height,
        "footer_top": footer_top,
        "viewport_top": viewport_top,
        "declared_clearance": declared_clearance,
        "layout_clearance": layout_clearance,
        "content_height": content_height,
        "content_size_hint_height": size_hint,
        "content_minimum_size_hint_height": minimum_hint,
        "scroll_minimum": scroll_minimum,
        "scroll_maximum": scroll_maximum,
        "last_body_child_bottom": last_body_child_bottom,
        "last_body_child_bottom_at_scroll_end": (
            last_body_child_bottom_at_scroll_end
        ),
        "required_content_height": required,
        "reachable_content_height": reachable,
    }
    for field, value in nonnegative.items():
        if value < 0:
            issues.append(f"negative-scroll-metric:{field}")
    if viewport_height <= 0:
        issues.append("invalid-scroll-metric:viewport_height")
    if content_height <= 0:
        issues.append("invalid-scroll-metric:content_height")
    if scroll_maximum < scroll_minimum:
        issues.append("invalid-scroll-range")
    scroll_span = max(0, scroll_maximum - scroll_minimum)
    window_mode = audit.get("window_mode")
    content_screen_limited = audit.get("content_screen_limited")
    if window_mode is not None:
        if window_mode not in {"canvas", "workspace", "content"}:
            issues.append("invalid-scroll-window-mode")
        if type(content_screen_limited) is not bool:
            issues.append("invalid-content-screen-limited")
        elif window_mode in {"canvas", "workspace", "content"}:
            independently_expected = int(
                window_mode == "workspace"
                or (
                    window_mode == "content"
                    and content_screen_limited
                    and scroll_span > 0
                )
            )
            if expected_active != independently_expected:
                issues.append("expected-active-scroll-count-mismatch")
    independently_positioned_body_end = viewport_top + max(
        0,
        last_body_child_bottom - scroll_span,
    )
    if last_body_child_bottom_at_scroll_end != independently_positioned_body_end:
        issues.append("last-body-child-position-mismatch")
    body_limit = footer_top if footer_visible else viewport_bottom
    if last_body_child_bottom_at_scroll_end > body_limit:
        issues.append("last-body-child-under-footer")
    if require_no_scroll and scroll_span != 0:
        issues.append("compact-transaction-scroll-range")

    if footer_visible and footer_height <= 0:
        issues.append("visible-footer-height")
    if not footer_visible and footer_height != 0:
        issues.append("hidden-footer-height")
    # The footer is a sibling below the viewport, not an overlay. Its height
    # must not be duplicated as artificial content padding; the capture and
    # layout measurements only need to agree with each other.
    if declared_clearance != layout_clearance:
        issues.append("footer-clearance-mismatch")
    if viewport_bottom != viewport_top + viewport_height:
        issues.append("viewport-bottom-mismatch")
    if footer_visible and viewport_bottom > footer_top:
        issues.append("footer-viewport-overlap")

    # A Qt sizeHint is preferred geometry, not a reachability obligation.
    # The capture-side content_height includes the bottom-most visible
    # descendant, while minimum_hint remains the non-negotiable layout floor.
    independently_required = max(0, content_height, minimum_hint)
    independently_reachable = viewport_height + scroll_span
    if required != independently_required:
        issues.append("required-content-height-mismatch")
    if reachable != independently_reachable:
        issues.append("reachable-content-height-mismatch")
    if independently_reachable < independently_required:
        issues.append("unreachable-scroll-content")
    return tuple(dict.fromkeys(issues))


def fertilizer_flow_source_issue_codes(evidence: Any) -> tuple[str, ...]:
    """Independently validate the canonical Rose state painted in step 1."""

    if not isinstance(evidence, dict):
        return ("fertilizer-flow-source:missing",)
    issues: list[str] = []
    plant_id = str(evidence.get("plant_id", "") or "")
    plant_name = str(evidence.get("plant_name", "") or "")
    species = str(evidence.get("species", "") or "").casefold()
    stage = str(evidence.get("growth_stage", "") or "").casefold()
    asset_id = str(evidence.get("artwork_asset_id", "") or "")
    asset_source = "/" + str(
        evidence.get("artwork_source", "") or ""
    ).replace("\\", "/").lstrip("/")
    if not plant_id:
        issues.append("fertilizer-flow-source:plant-id")
    if not plant_name:
        issues.append("fertilizer-flow-source:plant-name")
    if species != "rose":
        issues.append("fertilizer-flow-source:species")
    if evidence.get("growth_points") != 500:
        issues.append("fertilizer-flow-source:growth-points")
    if evidence.get("growth_remainder_units") != 0:
        issues.append("fertilizer-flow-source:growth-remainder")
    if stage != "sprout":
        issues.append("fertilizer-flow-source:growth-stage")
    if not asset_id.startswith(f"plant_{species}_{stage}_"):
        issues.append("fertilizer-flow-source:artwork-asset")
    if f"/{species}/{stage}/" not in asset_source:
        issues.append("fertilizer-flow-source:artwork-source")
    if evidence.get("artwork_resolved") is not True:
        issues.append("fertilizer-flow-source:artwork-resolved")
    if evidence.get("artwork_painted") is not True:
        issues.append("fertilizer-flow-source:artwork-painted")
    return tuple(dict.fromkeys(issues))


def fertilizer_flow_continuity_issue_codes(records: Any) -> tuple[str, ...]:
    """Independently bind one plant and Growth artwork through both steps."""

    if not isinstance(records, dict):
        return ("fertilizer-flow:missing-records",)
    roles = ("source", "fixture", "quote", "request", "confirmation")
    issues: list[str] = []
    source = records.get("source")
    issues.extend(fertilizer_flow_source_issue_codes(source))
    if not isinstance(source, dict):
        return tuple(dict.fromkeys(issues))
    continuity_fields = (
        "plant_id",
        "plant_name",
        "species",
        "growth_points",
        "growth_remainder_units",
        "growth_stage",
        "artwork_asset_id",
        "artwork_source",
    )
    for role in roles[1:]:
        record = records.get(role)
        if not isinstance(record, dict):
            issues.append(f"fertilizer-flow:{role}:missing")
            continue
        for field in continuity_fields:
            if record.get(field) != source.get(field):
                issues.append(f"fertilizer-flow:{role}:{field.replace('_', '-')}")
        if record.get("artwork_resolved") is not True:
            issues.append(f"fertilizer-flow:{role}:artwork-resolved")
    confirmation = records.get("confirmation")
    if (
        isinstance(confirmation, dict)
        and confirmation.get("artwork_painted") is not True
    ):
        issues.append("fertilizer-flow:confirmation:artwork-painted")
    return tuple(dict.fromkeys(issues))


def deprecated_visible_copy_evidence_issue_codes(
    evidence: Any,
) -> tuple[str, ...]:
    """Independently reject missing or contradictory painted-copy proof."""

    if not isinstance(evidence, dict):
        return ("missing-deprecated-visible-copy-audit",)
    issues: list[str] = []
    visible_copy = evidence.get("visible_copy")
    if not isinstance(visible_copy, str):
        issues.append("invalid-deprecated-visible-copy-text")
        normalized = ""
    else:
        normalized = " ".join(visible_copy.casefold().split())
    recomputed_hits = tuple(
        pattern
        for pattern in _V26_DEPRECATED_VISIBLE_COPY_PATTERNS
        if re.search(pattern, normalized)
    )
    reported_hits = evidence.get("hits")
    if not (
        isinstance(reported_hits, list)
        and all(isinstance(hit, str) for hit in reported_hits)
    ):
        issues.append("invalid-deprecated-visible-copy-hits")
    else:
        if tuple(reported_hits) != recomputed_hits:
            issues.append("deprecated-visible-copy-hits-mismatch")
        if reported_hits:
            issues.append("deprecated-visible-copy-detected")
    if recomputed_hits:
        issues.append("deprecated-visible-copy-detected")
    if evidence.get("collection_issues") != []:
        issues.append("deprecated-visible-copy-collection-not-passed")
    if evidence.get("passed") is not True:
        issues.append("deprecated-visible-copy-audit-not-passed")
    return tuple(dict.fromkeys(issues))


def v26_capture_semantic_gate_issue_codes(
    record: Any,
) -> tuple[str, ...]:
    """Validate the v26 per-surface semantic acceptance envelope."""

    if not isinstance(record, dict):
        return ("invalid-capture-record",)
    issues: list[str] = []

    fixture = record.get("fixture_validation")
    if not isinstance(fixture, dict):
        issues.append("missing-fixture-validation")
    else:
        if fixture.get("semantic_audit_passed") is not True:
            issues.append("fixture-semantic-audit-not-passed")
        postcondition = fixture.get("postcondition")
        if (
            not isinstance(postcondition, dict)
            or postcondition.get("passed") is not True
            or postcondition.get("issues") != []
        ):
            issues.append("fixture-postcondition-not-passed")

    acceptance = record.get("capture_acceptance")
    if not isinstance(acceptance, dict):
        issues.append("missing-capture-acceptance")
    else:
        if acceptance.get("policy") != V26_CAPTURE_ACCEPTANCE_POLICY:
            issues.append("capture-acceptance-policy-mismatch")
        gross_checks = acceptance.get("gross_checks")
        if (
            not isinstance(gross_checks, dict)
            or not gross_checks
            or any(value is not True for value in gross_checks.values())
            or acceptance.get("gross_passed") is not True
        ):
            issues.append("gross-capture-result-not-passed")
        if acceptance.get("semantic_audit_passed") is not True:
            issues.append("semantic-capture-acceptance-not-passed")
        if acceptance.get("passed") is not True:
            issues.append("capture-acceptance-not-passed")

    audit = record.get("audit")
    if (
        not isinstance(audit, dict)
        or audit.get("semantic_audit_passed") is not True
    ):
        issues.append("capture-audit-semantic-result-not-passed")
    deprecated_copy = (
        audit.get("deprecated_visible_copy")
        if isinstance(audit, dict) else
        None
    )
    issues.extend(
        deprecated_visible_copy_evidence_issue_codes(deprecated_copy)
    )
    if str(record.get("label", "")) == "fertilizer-active":
        source = (
            audit.get("fertilizer_flow_source")
            if isinstance(audit, dict) else
            None
        )
        if not (
            isinstance(source, dict)
            and source.get("passed") is True
            and source.get("issues") == []
            and not fertilizer_flow_source_issue_codes(source)
        ):
            issues.append("fertilizer-flow-source-not-passed")
    if (
        str(record.get("label", ""))
        == "purchase-confirmation-fertilizer-queue"
    ):
        confirmation = (
            audit.get("fertilizer_queue_confirmation")
            if isinstance(audit, dict) else
            None
        )
        continuity = (
            confirmation.get("plant_state_continuity")
            if isinstance(confirmation, dict) else
            None
        )
        records = (
            continuity.get("records")
            if isinstance(continuity, dict) else
            None
        )
        if not (
            isinstance(confirmation, dict)
            and confirmation.get("passed") is True
            and isinstance(continuity, dict)
            and continuity.get("passed") is True
            and continuity.get("issues") == []
            and not fertilizer_flow_continuity_issue_codes(records)
        ):
            issues.append("fertilizer-flow-continuity-not-passed")
    if str(record.get("label", "")) == "starter-nursery-plants":
        selection = (
            audit.get("first_run_selection")
            if isinstance(audit, dict) else
            None
        )
        selected = (
            str(selection.get("selected_species", "") or "").casefold()
            if isinstance(selection, dict) else
            ""
        )
        pending = (
            str(selection.get("pending_species", "") or "").casefold()
            if isinstance(selection, dict) else
            ""
        )
        if not (
            isinstance(selection, dict)
            and selection.get("passed") is True
            and selection.get("issues") == []
            and selection.get("nursery_entry_persisted") is True
            and selection.get("step_before_selection") == "nursery"
            and selection.get("selection_action") == "Choose"
            and selection.get("selection_action_triggered") is True
            and selection.get("selection_persisted") is True
            and selection.get("step_after_selection") == "placement"
            and bool(selected)
            and selected == pending
        ):
            issues.append("first-run-selection-transition-not-passed")
    if str(record.get("label", "")) == "nursery-plants":
        counts = audit if isinstance(audit, dict) else {}
        if not (
            counts.get("passed") is True
            and counts.get("fixture_state_passed") is True
            and counts.get("species_copy")
            == "10 of 10 species discovered"
            and counts.get("collection_entries_copy")
            == "30 of 39 collection entries discovered"
            and counts.get("species_copy_visible") is True
            and counts.get("collection_entries_copy_visible") is True
        ):
            issues.append("nursery-collection-counts-not-canonical")

    native_layout = record.get("native_layout_telemetry")
    if (
        not isinstance(native_layout, dict)
        or native_layout.get("passed") is not True
        or native_layout.get("issues") != []
    ):
        issues.append("native-layout-telemetry-not-passed")

    visual_contract = record.get("visual_contract_audit")
    if (
        not isinstance(visual_contract, dict)
        or visual_contract.get("passed") is not True
        or visual_contract.get("issues") != []
    ):
        issues.append("visual-contract-audit-not-passed")

    scroll_audit = record.get("dialog_scroll_audit")
    if not isinstance(scroll_audit, dict):
        issues.append("missing-dialog-scroll-audit")
    elif scroll_audit.get("applicable") is True:
        if (
            scroll_audit.get("passed") is not True
            or scroll_audit.get("issues") != []
        ):
            issues.append("dialog-scroll-audit-not-passed")
        four_state = scroll_audit.get("four_state_scroll_matrix")
        if (
            not isinstance(four_state, dict)
            or four_state.get("passed") is not True
            or four_state.get("issues") != []
        ):
            issues.append("four-state-scroll-evidence-not-passed")
    elif scroll_audit.get("applicable") is not False:
        issues.append("invalid-dialog-scroll-applicability")

    return tuple(dict.fromkeys(issues))


def _validate_dialog_scroll_summary(
    payload: dict[str, Any],
    coverage: dict[str, dict[str, str]],
    record_audits: dict[str, dict[str, Any]],
    issues: list[str],
    *,
    required: bool,
) -> None:
    expected = [
        (label, surface, semantic)
        for surface, labels in coverage.items()
        for label, semantic in labels.items()
    ]
    if payload.get("dialog_scroll_audits_complete") is not True:
        issues.append("dialog_scroll_audits_complete must be true")
    summary = payload.get("dialog_scroll_audits")
    if not isinstance(summary, dict):
        issues.append("dialog_scroll_audits must be an object")
        return
    if not required:
        if summary.get("required") is not False:
            issues.append("dialog_scroll_audits required must be false")
        if summary.get("passed") is not True:
            issues.append("dialog_scroll_audits passed must be true")
        if summary.get("required_count") != 0:
            issues.append("dialog_scroll_audits required_count must be 0")
        if summary.get("records") != []:
            issues.append("dialog_scroll_audits records must be empty")
        matrix = summary.get("four_state_scroll_matrix")
        if not isinstance(matrix, dict):
            issues.append(
                "dialog_scroll_audits four_state_scroll_matrix must be an object"
            )
        else:
            if matrix.get("required") is not False:
                issues.append("four-state scroll matrix required must be false")
            if matrix.get("required_states") != []:
                issues.append("four-state scroll matrix required_states must be empty")
            if matrix.get("observations") != []:
                issues.append("four-state scroll matrix observations must be empty")
            if matrix.get("passed") is not True:
                issues.append("four-state scroll matrix passed must be true")
        return
    if summary.get("required") is not True:
        issues.append("dialog_scroll_audits required must be true")
    if summary.get("passed") is not True:
        issues.append("dialog_scroll_audits passed must be true")
    if summary.get("required_count") != len(expected):
        issues.append(
            f"dialog_scroll_audits required_count must be {len(expected)}"
        )
    summaries = summary.get("records")
    if not isinstance(summaries, list) or len(summaries) != len(expected):
        issues.append(
            f"dialog_scroll_audits records must contain {len(expected)} entries"
        )
        return
    metric_fields = (
        "registered_count",
        "active_count",
        "footer_height",
        "viewport_height",
        "declared_clearance",
        "layout_clearance",
        "required_content_height",
        "reachable_content_height",
        "last_body_child_bottom",
        "last_body_child_bottom_at_scroll_end",
    )
    summaries_by_label: dict[str, dict[str, Any]] = {}
    for position, summary_record in enumerate(summaries, start=1):
        if not isinstance(summary_record, dict):
            issues.append(
                f"dialog scroll summary {position:02d}: record must be an object"
            )
            continue
        summary_label = summary_record.get("label")
        if not isinstance(summary_label, str) or not summary_label:
            issues.append(
                f"dialog scroll summary {position:02d}: label must be a nonempty string"
            )
            continue
        if summary_label in summaries_by_label:
            issues.append(
                f"dialog scroll summary {position:02d}: "
                f"duplicate label {summary_label!r}"
            )
            continue
        summaries_by_label[summary_label] = summary_record
    expected_labels = {label for label, _surface, _semantic in expected}
    if set(summaries_by_label) != expected_labels:
        issues.append("dialog_scroll_audits records do not match required labels")
    for index, (label, surface, semantic) in enumerate(expected, start=1):
        prefix = f"dialog scroll summary {index:02d} {label}"
        summary_record = summaries_by_label.get(label)
        if summary_record is None:
            issues.append(f"{prefix}: record is missing")
            continue
        if summary_record.get("surface") != surface:
            issues.append(f"{prefix}: surface must be {surface!r}")
        if summary_record.get("expected_page_semantic") != semantic:
            issues.append(f"{prefix}: expected page semantic must be {semantic!r}")
        if summary_record.get("actual_page_semantic") != semantic:
            issues.append(f"{prefix}: actual page semantic must be {semantic!r}")
        if summary_record.get("issues") != []:
            issues.append(f"{prefix}: issues must be empty")
        if summary_record.get("passed") is not True:
            issues.append(f"{prefix}: passed must be true")
        audit = record_audits.get(label, {})
        local_matrix = audit.get("four_state_scroll_matrix")
        local_matrix_issues = dialog_scroll_state_matrix_issue_codes(
            local_matrix,
            require_complete=False,
        )
        for issue in local_matrix_issues:
            issues.append(f"{prefix}: scroll state {issue}")
        if summary_record.get("four_state_scroll_matrix") != local_matrix:
            issues.append(
                f"{prefix}: four_state_scroll_matrix does not match capture audit"
            )
        for field in metric_fields:
            if summary_record.get(field) != audit.get(field):
                issues.append(f"{prefix}: {field} does not match capture audit")

    matrix = summary.get("four_state_scroll_matrix")
    if not isinstance(matrix, dict):
        issues.append(
            "dialog_scroll_audits four_state_scroll_matrix must be an object"
        )
        return
    if matrix.get("required") is not True:
        issues.append("four-state scroll matrix required must be true")
    if matrix.get("required_states") != list(DIALOG_SCROLL_FOUR_STATE_NAMES):
        issues.append("four-state scroll matrix required_states are invalid")
    matrix_issues = dialog_scroll_state_matrix_issue_codes(
        matrix,
        require_complete=True,
    )
    issues.extend(f"four-state scroll matrix: {issue}" for issue in matrix_issues)
    witnesses = matrix.get("witness_labels")
    if not isinstance(witnesses, dict):
        issues.append("four-state scroll matrix witness_labels must be an object")
        return
    if set(witnesses) != set(DIALOG_SCROLL_FOUR_STATE_NAMES):
        issues.append("four-state scroll matrix witnesses are incomplete")
    observations = matrix.get("observations")
    if not isinstance(observations, list):
        return
    for observation in observations:
        if not isinstance(observation, dict):
            continue
        state = str(observation.get("state", ""))
        label = str(observation.get("label", ""))
        if witnesses.get(state) != label or label not in record_audits:
            issues.append(
                f"four-state scroll matrix witness is invalid for {state!r}"
            )
            continue
        source_matrix = record_audits[label].get("four_state_scroll_matrix")
        source_observations = (
            list(source_matrix.get("observations", ()) or ())
            if isinstance(source_matrix, dict) else
            []
        )
        comparable = dict(observation)
        comparable.pop("label", None)
        if comparable not in source_observations:
            issues.append(
                f"four-state scroll matrix witness does not match {label!r}"
            )


def expected_resize_geometry_acceptance(
    *,
    label: str,
    declared_size: tuple[int, int],
    actual_size: tuple[int, int],
    minimum_size: tuple[int, int],
    maximum_size: tuple[int, int],
    screen_limited: bool,
    constraint_limited: bool,
    native_normalized: bool,
    normalization_reason: str,
) -> dict[str, Any]:
    """Independently reproduce the harness's bounded resize-drift contract."""

    declared_width, declared_height = declared_size
    actual_width, actual_height = actual_size
    minimum_width, minimum_height = minimum_size
    maximum_width, maximum_height = maximum_size
    exact = actual_size == declared_size
    breakpoint_fixture = "-content-" in label or "-breakpoint-" in label
    reasons = {
        token.strip()
        for token in normalization_reason.split(",")
        if token.strip()
    }
    provenance_flags = {
        "screen_limited": screen_limited,
        "constraint_limited": constraint_limited,
        "native_normalized": native_normalized,
    }
    provenance_tokens_match = (
        (not screen_limited or "extends-beyond-available-screen" in reasons)
        and (not constraint_limited or "widget-constraint" in reasons)
        and (not native_normalized or "native-frame-or-scale" in reasons)
    )
    provenance_explains_drift = (
        any(provenance_flags.values())
        and bool(reasons)
        and provenance_tokens_match
    )
    breakpoint_width_within_one = (
        not breakpoint_fixture or abs(actual_width - declared_width) <= 1
    )
    safe_bounded_width = (
        max(1, minimum_width) <= actual_width <= max(1, maximum_width)
        and actual_width <= max(declared_width + 1, minimum_width)
    )
    safe_bounded_height = (
        max(1, minimum_height) <= actual_height <= max(1, maximum_height)
        and actual_height <= max(declared_height + 1, minimum_height)
    )
    accepted = exact or (
        provenance_explains_drift
        and breakpoint_width_within_one
        and safe_bounded_width
        and safe_bounded_height
    )
    return {
        "exact": exact,
        "drifted": not exact,
        "accepted": accepted,
        "breakpoint_fixture": breakpoint_fixture,
        "breakpoint_width_within_one": breakpoint_width_within_one,
        "safe_bounded_width": safe_bounded_width,
        "safe_bounded_height": safe_bounded_height,
        "provenance_explains_drift": provenance_explains_drift,
        "provenance_flags": provenance_flags,
        "normalization_reasons": sorted(reasons),
        "declared_client_size": list(declared_size),
        "actual_client_size": list(actual_size),
        "minimum_client_size": list(minimum_size),
        "maximum_client_size": list(maximum_size),
    }


def _validate_memory_probe(
    payload: dict[str, Any],
    issues: list[str],
    *,
    required: bool,
) -> None:
    if payload.get("dialog_memory_probe_complete") is not True:
        issues.append("dialog_memory_probe_complete must be true")
    probe = payload.get("dialog_memory_probe")
    if not isinstance(probe, dict):
        issues.append("dialog_memory_probe must be an object")
        return
    if not required:
        if probe.get("status") != "not-run":
            issues.append("dialog_memory_probe status must be 'not-run'")
        if probe.get("cycles") != 0:
            issues.append("dialog_memory_probe cycles must be 0")
        return
    if probe.get("status") != "measured":
        issues.append("dialog_memory_probe status must be 'measured'")
    if probe.get("passed") is not True:
        issues.append("dialog_memory_probe passed must be true")
    if type(probe.get("cycles")) is not int or probe.get("cycles") != MEMORY_PROBE_CYCLES:
        issues.append(f"dialog_memory_probe cycles must be {MEMORY_PROBE_CYCLES}")
    for field in ("visible_cycles", "closed_cycles"):
        if type(probe.get(field)) is not int or probe.get(field) != MEMORY_PROBE_CYCLES:
            issues.append(
                f"dialog_memory_probe {field} must be {MEMORY_PROBE_CYCLES}"
            )
    warmup = probe.get("warmup_observation")
    if not isinstance(warmup, dict):
        issues.append("dialog_memory_probe warmup_observation must be an object")
    else:
        if warmup.get("dialog_class") != "NurseryDialog":
            issues.append(
                "dialog_memory_probe warmup_observation has the wrong dialog class"
            )
        if warmup.get("visible") is not True:
            issues.append(
                "dialog_memory_probe warmup_observation was not visibly opened"
            )
        if warmup.get("closed") is not True:
            issues.append(
                "dialog_memory_probe warmup_observation was not closed"
            )
        if any(key.endswith("error") for key in warmup):
            issues.append("dialog_memory_probe warmup_observation reports an error")
    observations = probe.get("cycle_observations")
    if not isinstance(observations, list) or len(observations) != MEMORY_PROBE_CYCLES:
        issues.append(
            f"dialog_memory_probe cycle_observations must contain {MEMORY_PROBE_CYCLES} records"
        )
    else:
        for cycle, observation in enumerate(observations, start=1):
            if not isinstance(observation, dict):
                issues.append(
                    f"dialog_memory_probe observation {cycle} must be an object"
                )
                continue
            if type(observation.get("cycle")) is not int or observation.get("cycle") != cycle:
                issues.append(
                    f"dialog_memory_probe observation {cycle} has an invalid cycle number"
                )
            if observation.get("visible") is not True:
                issues.append(
                    f"dialog_memory_probe observation {cycle} was not visibly opened"
                )
            if observation.get("closed") is not True:
                issues.append(
                    f"dialog_memory_probe observation {cycle} was not closed"
                )
            if observation.get("dialog_class") != "NurseryDialog":
                issues.append(
                    f"dialog_memory_probe observation {cycle} has the wrong dialog class"
                )
            if "close_error" in observation:
                issues.append(
                    f"dialog_memory_probe observation {cycle} reports a close error"
                )
    if probe.get("measurement") != "QApplication.allWidgets plus process peak RSS":
        issues.append("dialog_memory_probe measurement is not the release probe")
    if probe.get("current_rss_available") is not False:
        issues.append("dialog_memory_probe must identify peak RSS as non-current memory")

    for name in ("widget_count_before", "widget_count_after"):
        if type(probe.get(name)) is not int or probe.get(name, -1) < 0:
            issues.append(f"dialog_memory_probe {name} must be a nonnegative integer")
    if type(probe.get("widget_count_delta")) is not int:
        issues.append("dialog_memory_probe widget_count_delta must be an integer")
    elif (
        type(probe.get("widget_count_before")) is int
        and type(probe.get("widget_count_after")) is int
        and probe["widget_count_delta"]
        != probe["widget_count_after"] - probe["widget_count_before"]
    ):
        issues.append(
            "dialog_memory_probe widget_count_delta does not match before/after"
        )
    elif probe.get("widget_count_delta") != 0:
        issues.append("dialog_memory_probe total widget delta must be exactly zero")
    for field in ("watched_baseline_zero", "watched_after_zero"):
        if probe.get(field) is not True:
            issues.append(f"dialog_memory_probe {field} must be true")
    before_rss = probe.get("peak_rss_before_kib")
    after_rss = probe.get("peak_rss_after_kib")
    for name, value in (
        ("peak_rss_before_kib", before_rss),
        ("peak_rss_after_kib", after_rss),
    ):
        if value is not None and (type(value) is not int or value < 0):
            issues.append(f"dialog_memory_probe {name} must be null or nonnegative")
    if (
        type(before_rss) is int
        and type(after_rss) is int
        and after_rss < before_rss
    ):
        issues.append("dialog_memory_probe peak RSS decreased unexpectedly")

    class_fields = (
        "watched_class_counts_before",
        "watched_class_counts_after",
        "watched_class_delta",
    )
    class_maps: dict[str, dict[str, Any]] = {}
    for field in class_fields:
        value = probe.get(field)
        if not isinstance(value, dict) or set(value) != set(MEMORY_PROBE_CLASSES):
            issues.append(
                f"dialog_memory_probe {field} must contain the exact watched classes"
            )
            continue
        class_maps[field] = value
        if any(type(count) is not int for count in value.values()):
            issues.append(f"dialog_memory_probe {field} values must be integers")
        if field != "watched_class_delta" and any(count < 0 for count in value.values()):
            issues.append(f"dialog_memory_probe {field} values must be nonnegative")
    if len(class_maps) == len(class_fields):
        for name in MEMORY_PROBE_CLASSES:
            before = class_maps[class_fields[0]][name]
            after = class_maps[class_fields[1]][name]
            delta = class_maps[class_fields[2]][name]
            if all(type(value) is int for value in (before, after, delta)) and delta != after - before:
                issues.append(
                    f"dialog_memory_probe delta for {name} does not match before/after"
                )
        for name in MEMORY_PROBE_CLASSES:
            before = class_maps["watched_class_counts_before"][name]
            after = class_maps["watched_class_counts_after"][name]
            delta = class_maps["watched_class_delta"][name]
            if type(before) is int and before != 0:
                issues.append(
                    f"dialog_memory_probe {name} baseline must be exactly zero"
                )
            if type(after) is int and after != 0:
                issues.append(
                    f"dialog_memory_probe {name} after-count must be exactly zero"
                )
            if type(delta) is int and delta != 0:
                issues.append(
                    f"dialog_memory_probe {name} delta must be exactly zero"
                )


def web_root_overflow_issue_codes(evidence: Any) -> tuple[str, ...]:
    """Independently verify document and visible add-on root measurements."""

    if not isinstance(evidence, dict):
        return ("missing-web-root-overflow",)
    issues: list[str] = []
    if evidence.get("source") != WEB_ROOT_OVERFLOW_EVIDENCE_SOURCE:
        issues.append("unexpected-web-root-source")
    surface_kind = evidence.get("surface_kind")
    if surface_kind not in {"home", "reviewer"}:
        issues.append("invalid-web-root-surface-kind")

    def validate_measurement(record: Any, *, prefix: str) -> None:
        if not isinstance(record, dict):
            issues.append(f"missing-{prefix}-measurement")
            return
        client_width = record.get("client_width")
        scroll_width = record.get("scroll_width")
        overflow = record.get("horizontal_overflow")
        if type(client_width) is not int or client_width <= 0:
            issues.append(f"invalid-{prefix}-client-width")
        if type(scroll_width) is not int or scroll_width <= 0:
            issues.append(f"invalid-{prefix}-scroll-width")
        if type(overflow) is not int or overflow < 0:
            issues.append(f"invalid-{prefix}-overflow")
        if (
            type(client_width) is int
            and type(scroll_width) is int
            and type(overflow) is int
            and overflow != max(0, scroll_width - client_width)
        ):
            issues.append(f"{prefix}-overflow-arithmetic-mismatch")
        if (
            type(client_width) is int
            and type(scroll_width) is int
            and scroll_width > client_width
        ):
            issues.append(f"{prefix}-horizontal-overflow")
        if record.get("passed") is not True:
            issues.append(f"{prefix}-overflow-not-passed")

    document_root = evidence.get("document_root")
    if isinstance(document_root, dict):
        if document_root.get("identity") != "document.documentElement":
            issues.append("unexpected-web-document-root-identity")
        if document_root.get("source") != "document.documentElement":
            issues.append("unexpected-web-document-root-source")
    validate_measurement(document_root, prefix="web-document-root")

    candidate_count = evidence.get("addon_root_candidate_count")
    visible_count = evidence.get("visible_addon_root_count")
    records = evidence.get("visible_addon_roots")
    if type(candidate_count) is not int or candidate_count < 0:
        issues.append("invalid-addon-root-candidate-count")
    if type(visible_count) is not int or visible_count < 0:
        issues.append("invalid-visible-addon-root-count")
    if not isinstance(records, list):
        issues.append("invalid-visible-addon-root-records")
        records = []
    if type(visible_count) is int and visible_count != len(records):
        issues.append("visible-addon-root-count-mismatch")
    if (
        type(candidate_count) is int
        and type(visible_count) is int
        and candidate_count < visible_count
    ):
        issues.append("addon-root-candidate-count-mismatch")
    if surface_kind == "home" and not records:
        issues.append("home-visible-addon-root-missing")

    identities: set[str] = set()
    prior_dom_ordinal = 0
    for index, record in enumerate(records, start=1):
        prefix = f"visible-addon-root-{index}"
        if not isinstance(record, dict):
            issues.append(f"invalid-{prefix}-record")
            continue
        identity = record.get("identity")
        root_kind = record.get("root_kind")
        selector = record.get("selector")
        dom_ordinal = record.get("dom_ordinal")
        kind_ordinal = record.get("kind_ordinal")
        if not isinstance(root_kind, str) or not root_kind:
            issues.append(f"invalid-{prefix}-kind")
        if type(kind_ordinal) is not int or kind_ordinal < 1:
            issues.append(f"invalid-{prefix}-kind-ordinal")
        expected_identity = (
            f"anki-garden:{root_kind}:{kind_ordinal}"
            if isinstance(root_kind, str)
            and root_kind
            and type(kind_ordinal) is int
            and kind_ordinal >= 1
            else None
        )
        if not isinstance(identity, str) or not identity:
            issues.append(f"invalid-{prefix}-identity")
        elif identity in identities:
            issues.append("duplicate-visible-addon-root-identity")
        elif expected_identity is not None and identity != expected_identity:
            issues.append(f"unstable-{prefix}-identity")
        if isinstance(identity, str):
            identities.add(identity)
        if not isinstance(selector, str) or not selector:
            issues.append(f"invalid-{prefix}-selector")
        if type(dom_ordinal) is not int or dom_ordinal <= prior_dom_ordinal:
            issues.append(f"nondeterministic-{prefix}-dom-order")
        else:
            prior_dom_ordinal = dom_ordinal
        if record.get("visible") is not True:
            issues.append(f"{prefix}-not-visible")
        validate_measurement(record, prefix=prefix)

    if evidence.get("dom_audit_passed") is not True:
        issues.append("web-root-dom-audit-not-passed")
    if evidence.get("passed") is not True:
        issues.append("web-root-overflow-not-passed")
    return tuple(dict.fromkeys(issues))


def native_progress_fraction(
    minimum: int,
    value: int,
    maximum: int,
) -> float:
    """Independently recompute a bounded native progress fraction."""

    lower = int(minimum)
    upper = int(maximum)
    if upper <= lower:
        return 0.0
    clamped = min(upper, max(lower, int(value)))
    return round((clamped - lower) / (upper - lower), 9)


def native_progress_bar_evidence_issue_codes(
    evidence: Any,
) -> tuple[str, ...]:
    """Independently reject missing or contradictory QProgressBar paint proof."""

    if not isinstance(evidence, dict):
        return ("native-progress-evidence-missing",)
    issues: list[str] = []
    if evidence.get("source") != "QProgressBar.initStyleOption":
        issues.append("native-progress-source")
    if evidence.get("scanned") is not True:
        issues.append("native-progress-scan-missing")
    root_semantic_id = evidence.get("root_semantic_id")
    if not isinstance(root_semantic_id, str) or not root_semantic_id.strip():
        issues.append("native-progress-root-semantic-id")
    root_geometry = evidence.get("root_geometry")
    if not (
        isinstance(root_geometry, list)
        and len(root_geometry) == 4
        and all(type(number) is int for number in root_geometry)
        and root_geometry[2] > 0
        and root_geometry[3] > 0
    ):
        issues.append("native-progress-root-geometry")

    records = evidence.get("bars")
    candidate_count = evidence.get("candidate_count")
    if not isinstance(records, list):
        return tuple(dict.fromkeys((*issues, "native-progress-records")))
    if type(candidate_count) is not int or candidate_count < 0:
        issues.append("native-progress-candidate-count")
    elif candidate_count != len(records):
        issues.append("native-progress-candidate-count-mismatch")

    semantic_ids: list[str] = []
    for index, record in enumerate(records):
        prefix = f"native-progress-{index}"
        if not isinstance(record, dict):
            issues.append(f"{prefix}-record")
            continue
        semantic_id = record.get("semantic_id")
        if not isinstance(semantic_id, str) or not semantic_id.strip():
            issues.append(f"{prefix}-semantic-id")
        else:
            semantic_ids.append(semantic_id)
        if record.get("native_class") != "QProgressBar":
            issues.append(f"{prefix}-native-class")
        if (
            record.get("visible") is not True
            or record.get("visible_to_root") is not True
            or record.get("visible_region_nonempty") is not True
        ):
            issues.append(f"{prefix}-visibility")

        geometry = record.get("geometry")
        visible_geometry = record.get("visible_geometry")
        geometry_valid = bool(
            isinstance(geometry, list)
            and len(geometry) == 4
            and all(type(number) is int for number in geometry)
            and geometry[2] > 0
            and geometry[3] > 0
        )
        visible_geometry_valid = bool(
            isinstance(visible_geometry, list)
            and len(visible_geometry) == 4
            and all(type(number) is int for number in visible_geometry)
            and visible_geometry[2] > 0
            and visible_geometry[3] > 0
        )
        if not geometry_valid:
            issues.append(f"{prefix}-geometry")
        if not visible_geometry_valid:
            issues.append(f"{prefix}-visible-geometry")
        if geometry_valid and visible_geometry_valid and (
            visible_geometry[0] < 0
            or visible_geometry[1] < 0
            or not isinstance(root_geometry, list)
            or len(root_geometry) != 4
            or visible_geometry[0] + visible_geometry[2] > root_geometry[2]
            or visible_geometry[1] + visible_geometry[3] > root_geometry[3]
        ):
            issues.append(f"{prefix}-visible-geometry-containment")

        minimum = record.get("logical_minimum")
        value = record.get("logical_value")
        maximum = record.get("logical_maximum")
        logical_valid = bool(
            type(minimum) is int
            and type(value) is int
            and type(maximum) is int
            and maximum >= minimum
        )
        if not logical_valid:
            issues.append(f"{prefix}-logical-range")
            expected_fraction = None
        else:
            expected_fraction = native_progress_fraction(
                minimum,
                value,
                maximum,
            )
            if record.get("clamped_logical_value") != min(
                maximum,
                max(minimum, value),
            ):
                issues.append(f"{prefix}-logical-clamp")
            if record.get("denominator_zero") is not (maximum <= minimum):
                issues.append(f"{prefix}-denominator-zero")
            if record.get("denominator_zero_fallback") != "zero":
                issues.append(f"{prefix}-denominator-zero-fallback")
            if record.get("expected_fraction") != expected_fraction:
                issues.append(f"{prefix}-expected-fraction")

        paint = record.get("paint_input")
        if not isinstance(paint, dict):
            issues.append(f"{prefix}-paint-input")
            continue
        if (
            paint.get("source") != "QStyleOptionProgressBar"
            or paint.get("initialized") is not True
        ):
            issues.append(f"{prefix}-paint-source")
        painted_minimum = paint.get("minimum")
        painted_value = paint.get("value")
        painted_maximum = paint.get("maximum")
        if not (
            type(painted_minimum) is int
            and type(painted_value) is int
            and type(painted_maximum) is int
            and logical_valid
            and painted_minimum == minimum
            and painted_value == value
            and painted_maximum == maximum
        ):
            issues.append(f"{prefix}-paint-range")
        elif paint.get("fraction") != expected_fraction:
            issues.append(f"{prefix}-paint-fraction")
        paint_geometry = paint.get("geometry")
        if not (
            geometry_valid
            and isinstance(paint_geometry, list)
            and paint_geometry == [0, 0, geometry[2], geometry[3]]
        ):
            issues.append(f"{prefix}-paint-geometry")
        if record.get("paint_input_consistent") is not True:
            issues.append(f"{prefix}-paint-input-consistency")

    if len(set(semantic_ids)) != len(semantic_ids):
        issues.append("native-progress-semantic-id-collision")
    if evidence.get("issues") != []:
        issues.append("native-progress-runtime-issues")
    if evidence.get("passed") is not True:
        issues.append("native-progress-runtime-not-passed")
    return tuple(dict.fromkeys(issues))


def visible_action_geometry_issue_codes(visual: Any) -> tuple[str, ...]:
    """Recompute dialog action containment and pairwise intersections."""

    if not isinstance(visual, dict):
        return ("missing-visible-action-geometry",)
    records = visual.get("visible_actions")
    if not isinstance(records, list):
        return ("invalid-visible-action-records",)
    issues: list[str] = []
    if visual.get("visible_action_count") != len(records):
        issues.append("visible-action-count-mismatch")
    dialog_size = visual.get("dialog_size")
    dialog_size_valid = bool(
        isinstance(dialog_size, list)
        and len(dialog_size) == 2
        and all(type(value) is int and value > 0 for value in dialog_size)
    )
    if not dialog_size_valid:
        issues.append("invalid-visible-action-dialog-size")
    normalized: list[tuple[int, list[int | float], bool]] = []
    for position, record in enumerate(records):
        if not isinstance(record, dict):
            issues.append("malformed-visible-action-record")
            continue
        bounds = record.get("bounds")
        bounds_valid = bool(
            isinstance(bounds, list)
            and len(bounds) == 4
            and all(
                isinstance(value, (int, float)) and not isinstance(value, bool)
                for value in bounds
            )
            and float(bounds[2]) > 0
            and float(bounds[3]) > 0
        )
        if not bounds_valid:
            issues.append("invalid-visible-action-bounds")
            continue
        if record.get("index") != position:
            issues.append("visible-action-index-mismatch")
        if not isinstance(record.get("clip_owner"), str) or not str(
            record.get("clip_owner", "")
        ).strip():
            issues.append("missing-visible-action-clip-owner")
        if record.get("visible") is not True:
            issues.append("visible-action-not-visible")
        if (
            record.get("contained_in_dialog") is not True
            or record.get("contained_in_owner") is not True
        ):
            issues.append("visible-action-outside-container")
        if dialog_size_valid:
            left, top, width, height = bounds
            independently_contained = bool(
                left >= 0
                and top >= 0
                and left + width <= dialog_size[0]
                and top + height <= dialog_size[1]
            )
            if independently_contained is not bool(
                record.get("contained_in_dialog", False)
            ):
                issues.append("visible-action-dialog-containment-mismatch")
            if not independently_contained:
                issues.append("visible-action-outside-dialog-bounds")
        eligible = record.get("pairwise_eligible")
        if type(eligible) is not bool:
            issues.append("invalid-visible-action-pairwise-eligibility")
            eligible = False
        normalized.append((position, bounds, bool(eligible)))
    computed_overlaps: list[dict[str, Any]] = []
    for index, (first_position, first, first_eligible) in enumerate(normalized):
        if not first_eligible:
            continue
        first_left, first_top, first_width, first_height = first
        for second_position, second, second_eligible in normalized[index + 1:]:
            if not second_eligible:
                continue
            second_left, second_top, second_width, second_height = second
            overlap_width = max(
                0,
                min(first_left + first_width, second_left + second_width)
                - max(first_left, second_left),
            )
            overlap_height = max(
                0,
                min(first_top + first_height, second_top + second_height)
                - max(first_top, second_top),
            )
            if overlap_width > 0 and overlap_height > 0:
                computed_overlaps.append({
                    "actions": [first_position, second_position],
                    "width": overlap_width,
                    "height": overlap_height,
                })
    reported_overlaps = visual.get("visible_action_overlaps")
    if not isinstance(reported_overlaps, list):
        issues.append("invalid-visible-action-overlap-records")
    elif reported_overlaps != computed_overlaps:
        issues.append("visible-action-overlap-evidence-mismatch")
    if computed_overlaps:
        issues.append("overlapping-visible-actions")
    if visual.get("visible_actions_contained") is not True:
        issues.append("visible-actions-containment-not-passed")
    if visual.get("visible_actions_non_overlapping") is not True:
        issues.append("visible-actions-overlap-not-passed")
    return tuple(dict.fromkeys(issues))


def streak_fold_geometry_issue_codes(evidence: Any) -> tuple[str, ...]:
    """Reject a clipped Streak detail card or insufficient list tail inset."""

    if not isinstance(evidence, dict):
        return ("missing-streak-fold-geometry",)
    issues: list[str] = []
    if evidence.get("scroll_name") != "Anki Streak details":
        issues.append("unexpected-streak-scroll-owner")
    if evidence.get("at_initial_fold") is not True:
        issues.append("streak-not-at-initial-fold")
    viewport = evidence.get("viewport_size")
    if not (
        isinstance(viewport, list)
        and len(viewport) == 2
        and all(type(value) is int and value > 0 for value in viewport)
    ):
        issues.append("invalid-streak-viewport")
    for field in ("configured_bottom_padding", "measured_bottom_padding"):
        value = evidence.get(field)
        if type(value) is not int or value < 24:
            issues.append(f"insufficient-streak-{field.replace('_', '-')}")
    cards = evidence.get("detail_cards")
    partial_indexes: list[int] = []
    if not isinstance(cards, list):
        issues.append("invalid-streak-detail-card-records")
    else:
        for record in cards:
            if not isinstance(record, dict):
                issues.append("malformed-streak-detail-card")
                continue
            bounds = record.get("bounds")
            if not (
                isinstance(bounds, list)
                and len(bounds) == 4
                and all(type(value) is int for value in bounds)
                and bounds[2] > 0
                and bounds[3] > 0
            ):
                issues.append("invalid-streak-detail-card-bounds")
            intersects = record.get("intersects_first_fold")
            contained = record.get("contained_in_first_fold")
            if type(intersects) is not bool or type(contained) is not bool:
                issues.append("invalid-streak-detail-card-visibility")
            elif (
                isinstance(bounds, list)
                and len(bounds) == 4
                and all(type(value) is int for value in bounds)
                and bounds[2] > 0
                and bounds[3] > 0
                and isinstance(viewport, list)
                and len(viewport) == 2
                and all(type(value) is int and value > 0 for value in viewport)
            ):
                left, top, width, height = bounds
                computed_intersects = bool(
                    left < viewport[0]
                    and left + width > 0
                    and top < viewport[1]
                    and top + height > 0
                )
                computed_contained = bool(
                    left >= 0
                    and top >= 0
                    and left + width <= viewport[0]
                    and top + height <= viewport[1]
                )
                if (
                    intersects is not computed_intersects
                    or contained is not computed_contained
                ):
                    issues.append("streak-detail-card-geometry-mismatch")
                if computed_intersects and not computed_contained:
                    partial_indexes.append(int(record.get("index", -1)))
    if evidence.get("partial_detail_card_indexes") != partial_indexes:
        issues.append("streak-partial-card-evidence-mismatch")
    if partial_indexes:
        issues.append("partially-visible-streak-detail-card")
    if evidence.get("passed") is not True:
        issues.append("streak-fold-geometry-not-passed")
    return tuple(dict.fromkeys(issues))


def growth_charge_rendered_value_issue_codes(
    label: str,
    evidence: Any,
) -> tuple[str, ...]:
    """Validate canonical rendered values independent of transaction flags."""

    if not isinstance(evidence, dict):
        return ("missing-growth-charge-rendered-values",)
    issues: list[str] = []
    if evidence.get("applicable") is not True:
        issues.append("growth-charge-rendered-values-inapplicable")
    if label == "growth-charge-use-ready":
        expected = {
            "variant": "ready",
            "growth_label": "Total Growth",
            "growth_value": "450 → 550",
            "inventory_label": "Charges remaining",
            "inventory_value": "2 → 1",
            "stage_badge": "Result: Sprout",
            "stage_badge_accessible": "New stage: Sprout",
            "stage_progress": "50 / 2,000 toward Young",
            "primary_action": "Use 1 charge",
            "current_growth": 450,
            "projected_growth": 550,
            "inventory_before": 2,
            "inventory_after": 1,
            "stage_carryover": 50,
            "next_stage_goal": 2_000,
        }
    elif label == "growth-charge-success-stage-reward":
        expected = {
            "variant": "success",
            "stage_transition": "Bonsai Plant reached Sprout",
            "receipt_copy": (
                "+100 Growth · 1 growth charge remaining\n"
                "Next-stage progress · 50 / 2,000 toward Young"
            ),
            "stage_reward_heading": "Stage reward",
            "reward_texts": ["Stage reward", "+2 Garden Coins"],
            "primary_action": "View plant",
            "secondary_action": "Close",
            "resulting_growth": 550,
            "stage_carryover": 50,
            "next_stage_goal": 2_000,
            "inventory_remaining": 1,
            "stage_reward_total": 2,
        }
    else:
        return ("unexpected-growth-charge-rendered-label",)
    for key, expected_value in expected.items():
        if evidence.get(key) != expected_value:
            issues.append(f"growth-charge-rendered-value-mismatch:{key}")
    if evidence.get("passed") is not True:
        issues.append("growth-charge-rendered-values-not-passed")
    return tuple(dict.fromkeys(issues))


def diagnostics_state_matrix_issue_codes(evidence: Any) -> tuple[str, ...]:
    """Independently validate Surface 26's five painted Diagnostics states."""

    if not isinstance(evidence, dict):
        return ("missing-diagnostics-state-matrix",)
    expected: dict[str, dict[str, Any]] = {
        "success": {
            "diagnostic_state": "success",
            "result_state": "success",
            "title": "All artwork is available",
            "summary": "",
            "check_enabled": True,
            "check_label": "Check again",
            "copy_confirmation_visible": False,
            "copy_confirmation": "",
            "painted": True,
        },
        "warning": {
            "diagnostic_state": "warning",
            "result_state": "warning",
            "title": "3 artwork files are missing",
            "summary": "Some plants, decorations, or scenery may not appear.",
            "check_enabled": True,
            "check_label": "Check again",
            "copy_confirmation_visible": False,
            "copy_confirmation": "",
            "painted": True,
        },
        "failure": {
            "diagnostic_state": "failure",
            "result_state": "failure",
            "title": "Display issues detected",
            "summary": (
                "Check again. Copy the current report if the issue continues."
            ),
            "check_enabled": True,
            "check_label": "Check again",
            "copy_confirmation_visible": False,
            "copy_confirmation": "",
            "painted": True,
        },
        "checking": {
            "diagnostic_state": "checking",
            "result_state": "success",
            "title": "Checking display diagnostics",
            "summary": "Scanning artwork and display telemetry.",
            "check_enabled": False,
            "check_label": "Checking…",
            "copy_confirmation_visible": False,
            "copy_confirmation": "",
            "painted": True,
        },
        "copy-confirmation": {
            "diagnostic_state": "copy-confirmation",
            "result_state": "warning",
            "title": "3 artwork files are missing",
            "summary": "Some plants, decorations, or scenery may not appear.",
            "check_enabled": True,
            "check_label": "Check again",
            "copy_confirmation_visible": True,
            "copy_confirmation": "Report copied to clipboard",
            "painted": True,
        },
    }
    issues: list[str] = []
    records = evidence.get("records")
    if not isinstance(records, dict) or set(records) != set(expected):
        issues.append("diagnostics-state-set")
        records = records if isinstance(records, dict) else {}
    for state, expected_values in expected.items():
        actual = records.get(state)
        if not isinstance(actual, dict):
            issues.append(f"diagnostics-{state}:missing")
            continue
        for key, expected_value in expected_values.items():
            if actual.get(key) != expected_value:
                issues.append(f"diagnostics-{state}:{key}")
    topology = evidence.get("topology")
    if not isinstance(topology, dict):
        issues.append("diagnostics-topology")
    else:
        if topology.get("visible_central_scroll_owners") != 1:
            issues.append("diagnostics-central-scroll-owner")
        if topology.get("diagnostics_scroll_is_owner") is not True:
            issues.append("diagnostics-scroll-identity")
        if topology.get("chrome_outside_scroll") is not True:
            issues.append("diagnostics-pinned-chrome")
    if evidence.get("passed") is not True:
        issues.append("diagnostics-state-matrix-not-passed")
    return tuple(dict.fromkeys(issues))


def sync_reward_discovery_state_matrix_issue_codes(
    evidence: Any,
) -> tuple[str, ...]:
    """Independently validate Surface 29's painted discovery variants."""

    if not isinstance(evidence, dict):
        return ("missing-sync-reward-discovery-state-matrix",)
    base_metrics = {
        "sync_review_cards": {"label": "Card answers", "value": "42"},
        "growth_resource": {"label": "Growth", "value": "+520"},
        "garden_coin": {"label": "Garden Coins", "value": "+12"},
    }
    expected: dict[str, dict[str, Any]] = {
        "no-discovery": {
            "environment_count": 0,
            "rewards_section_visible": False,
            "rewards_heading_visible": False,
            "visible_environment_rows": 0,
            "visible_standard_find_rows": 0,
            "visible_environment_ids": [],
            "visible_environment_event_ids": [],
            "visible_standard_find_ids": [],
            "visible_standard_find_event_ids": [],
            "metric_tile_count": 3,
            "metric_projection": base_metrics,
            "disclosure_visible": False,
            "disclosure_text": "",
            "expanded": False,
            "painted": True,
        },
        "multi-discovery-collapsed": {
            "environment_count": 5,
            "rewards_section_visible": True,
            "rewards_heading_visible": True,
            "visible_environment_rows": 2,
            "visible_standard_find_rows": 1,
            "visible_environment_ids": ["firefly_lantern", "moon_arch"],
            "visible_environment_event_ids": [
                "capture-sync-discovery:firefly_lantern",
                "capture-sync-discovery:moon_arch",
            ],
            "visible_standard_find_ids": ["growth_charge_small"],
            "visible_standard_find_event_ids": [
                "capture-sync-standard-find:growth_charge_small",
            ],
            "metric_tile_count": 5,
            "metric_projection": {
                **base_metrics,
                "standard_find": {
                    "label": "Standard Finds",
                    "value": "+3",
                },
                "garden_discovery": {
                    "label": "Garden discoveries",
                    "value": "+5",
                },
            },
            "disclosure_visible": True,
            "disclosure_text": "Show 3 more",
            "disclosure_accessible_name": (
                "Show 3 more sync reward entries"
            ),
            "expanded": False,
            "painted": True,
        },
    }
    issues: list[str] = []
    records = evidence.get("records")
    if not isinstance(records, dict) or set(records) != set(expected):
        issues.append("sync-reward-discovery-state-set")
        records = records if isinstance(records, dict) else {}
    for state, expected_values in expected.items():
        actual = records.get(state)
        if not isinstance(actual, dict):
            issues.append(f"sync-reward-{state}:missing")
            continue
        for key, expected_value in expected_values.items():
            if actual.get(key) != expected_value:
                issues.append(f"sync-reward-{state}:{key}")
    restored = evidence.get("restored")
    if not isinstance(restored, dict):
        issues.append("sync-reward-restored:missing")
    else:
        for key, expected_value in {
            "environment_count": 1,
            "rewards_section_visible": True,
            "visible_environment_rows": 1,
            "visible_standard_find_rows": 0,
            "visible_environment_ids": ["firefly_lantern"],
            "visible_environment_event_ids": [
                "capture-sync-environment-discovery:firefly_lantern",
            ],
            "visible_standard_find_ids": [],
            "visible_standard_find_event_ids": [],
            "metric_tile_count": 4,
            "metric_projection": {
                **base_metrics,
                "garden_discovery": {
                    "label": "Garden discoveries",
                    "value": "+1",
                },
            },
            "disclosure_visible": False,
            "expanded": False,
        }.items():
            if restored.get(key) != expected_value:
                issues.append(f"sync-reward-restored:{key}")
    if evidence.get("passed") is not True:
        issues.append("sync-reward-discovery-state-matrix-not-passed")
    return tuple(dict.fromkeys(issues))


def collection_loadout_state_matrix_issue_codes(
    evidence: Any,
) -> tuple[str, ...]:
    """Independently validate Surface 20's appearance draft lifecycle."""

    if not isinstance(evidence, dict):
        return ("missing-collection-loadout-state-matrix",)
    issues: list[str] = []
    values = evidence.get("structured_values")
    expected_keys = {
        "scenery",
        "displayed_decoration",
        "active_bonus",
        "visual_effects",
    }
    if not isinstance(values, dict) or set(values) != expected_keys:
        issues.append("collection-loadout-structured-value-keys")
        values = values if isinstance(values, dict) else {}
    if any(not str(values.get(key, "")).strip() for key in expected_keys):
        issues.append("collection-loadout-structured-value-copy")
    for key, expected_value in {
        "structured_values_visible": True,
        "initial_apply_enabled": False,
        "dirty_apply_enabled": True,
        "restored_apply_enabled": False,
        "selection_preserved_across_tabs": True,
        "selected_tile_checked_after_tabs": True,
        "dirty_state_painted": True,
        "restored_state_painted": True,
        "restored_to_persisted_draft": True,
    }.items():
        if evidence.get(key) != expected_value:
            issues.append(f"collection-loadout:{key}")
    if not str(evidence.get("selected_scenery_id", "")).strip():
        issues.append("collection-loadout-selected-scenery-id")
    preview_size = evidence.get("preview_size")
    if (
        not isinstance(preview_size, list)
        or len(preview_size) != 2
        or any(type(value) is not int or value <= 0 for value in preview_size)
        or preview_size[1] != round(preview_size[0] * 9 / 16)
    ):
        issues.append("collection-loadout-preview-aspect-ratio")
    if evidence.get("passed") is not True:
        issues.append("collection-loadout-state-matrix-not-passed")
    return tuple(dict.fromkeys(issues))


def nursery_bed_incomplete_state_issue_codes(
    evidence: Any,
) -> tuple[str, ...]:
    """Independently validate Surface 23's painted Bed 3 expansion."""

    if not isinstance(evidence, dict):
        return ("missing-nursery-bed-incomplete-state",)
    expected = {
        "unlocked_beds": 2,
        "summary": "2 of 6 beds unlocked",
        "bed_number": 3,
        "bed_title": "Unlock Bed 3",
        "price": 150,
        "price_copy": "150 Garden Coins",
        "resulting_capacity": 3,
        "action_copy": "Unlock for 150 Garden Coins",
        "action_accessible_name": "Unlock Bed 3 for 150 Garden Coins",
        "action_enabled": True,
        "painted": True,
        "contained": True,
    }
    issues: list[str] = []
    for key, expected_value in expected.items():
        if evidence.get(key) != expected_value:
            issues.append(f"nursery-bed-incomplete:{key}")
    if (
        "Unlocks Bed 3 and increases Garden capacity to 3 plants."
        not in str(evidence.get("capacity_copy", ""))
    ):
        issues.append("nursery-bed-incomplete:capacity_copy")
    if evidence.get("passed") is not True:
        issues.append("nursery-bed-incomplete-state-not-passed")
    return tuple(dict.fromkeys(issues))


def starter_nursery_geometry_issue_codes(
    evidence: Any,
) -> tuple[str, ...]:
    """Reject a starter catalog whose complete two-row choice grid is clipped."""

    if not isinstance(evidence, dict):
        return ("starter-nursery:missing",)
    issues: list[str] = []

    def valid_bounds(value: Any) -> bool:
        return bool(
            isinstance(value, list)
            and len(value) == 4
            and all(type(component) is int for component in value)
        )

    if evidence.get("applicable") is not True:
        issues.append("starter-nursery:not-applicable")
    if evidence.get("passed") is not True:
        issues.append("starter-nursery:not-passed")
    height = evidence.get("dialog_height")
    if type(height) is not int or not 370 <= height <= 410:
        issues.append("starter-nursery:dialog-height")
    viewport_size = evidence.get("catalog_viewport_size")
    if not (
        isinstance(viewport_size, list)
        and len(viewport_size) == 2
        and all(type(value) is int and value > 0 for value in viewport_size)
    ):
        issues.append("starter-nursery:catalog-viewport")
    scroll_maximum = evidence.get("catalog_scroll_maximum")
    if type(scroll_maximum) is not int or scroll_maximum != 0:
        issues.append("starter-nursery:catalog-scroll")
    if evidence.get("partial_card_ids") != []:
        issues.append("starter-nursery:partial-cards")
    records = evidence.get("records")
    if not isinstance(records, list) or len(records) != 4:
        issues.append("starter-nursery:card-count")
        records = []
    for index, record in enumerate(records):
        prefix = f"starter-nursery:card-{index + 1}"
        if not isinstance(record, dict):
            issues.append(f"{prefix}:record")
            continue
        if not str(record.get("item_id", "")).strip():
            issues.append(f"{prefix}:item-id")
        if record.get("passed") is not True:
            issues.append(f"{prefix}:not-passed")
        if record.get("contained_in_catalog_viewport") is not True:
            issues.append(f"{prefix}:viewport-containment")
        viewport_bounds = record.get("viewport_bounds")
        if not valid_bounds(viewport_bounds):
            issues.append(f"{prefix}:viewport-bounds")
        card_size = record.get("card_size")
        if not (
            isinstance(card_size, list)
            and len(card_size) == 2
            and all(type(value) is int for value in card_size)
            and 88 <= card_size[1] <= 92
        ):
            issues.append(f"{prefix}:card-size")
        for key, width_bounds, height_bounds in (
            ("seed_badge_bounds", (44, 64), (22, 26)),
            ("choose_bounds", (64, 100), (34, 36)),
        ):
            bounds = record.get(key)
            if not (
                valid_bounds(bounds)
                and width_bounds[0] <= bounds[2] <= width_bounds[1]
                and height_bounds[0] <= bounds[3] <= height_bounds[1]
            ):
                issues.append(f"{prefix}:{key.replace('_', '-')}")
        details = record.get("details_bounds")
        if not valid_bounds(details):
            issues.append(f"{prefix}:details-bounds")
    footer = evidence.get("footer")
    if not isinstance(footer, dict):
        issues.append("starter-nursery:footer")
    elif not (
        footer.get("contained") is True
        and footer.get("action_text") == "Skip for now"
        and footer.get("action_contained") is True
        and valid_bounds(footer.get("bounds"))
        and 36 <= footer["bounds"][3] <= 48
    ):
        issues.append("starter-nursery:footer")
    return tuple(dict.fromkeys(issues))


def move_occupied_hover_issue_codes(evidence: Any) -> tuple[str, ...]:
    """Independently require Surface 08's painted occupied hover state."""

    if not isinstance(evidence, dict):
        return ("move-hover:missing",)
    issues: list[str] = []
    occupied_slot = evidence.get("occupied_destination_slot")
    expected_label = str(evidence.get("expected_label", ""))
    occupant_name = str(evidence.get("occupant_display_name", ""))
    valid_destinations = list(evidence.get("valid_destinations", ()) or ())
    if evidence.get("move_mode_active") is not True:
        issues.append("move-hover:move-mode-inactive")
    if not str(evidence.get("source_plant_id", "")).strip():
        issues.append("move-hover:source-plant-id")
    if not str(evidence.get("occupant_plant_id", "")).strip():
        issues.append("move-hover:occupant-plant-id")
    if evidence.get("source_plant_id") == evidence.get("occupant_plant_id"):
        issues.append("move-hover:source-occupant-identity")
    if type(occupied_slot) is not int or occupied_slot < 0:
        issues.append("move-hover:occupied-slot")
    elif occupied_slot not in valid_destinations:
        issues.append("move-hover:occupied-slot-validity")
    if evidence.get("hovered_slot") != occupied_slot:
        issues.append("move-hover:hovered-slot")
    if not occupant_name or expected_label != f"Swap with {occupant_name}":
        issues.append("move-hover:expected-label")
    if evidence.get("painted_label") != expected_label:
        issues.append("move-hover:painted-label")
    if evidence.get("pointer_reached_target") is not True:
        issues.append("move-hover:pointer-target")
    if evidence.get("source_slot_not_selectable") is not True:
        issues.append("move-hover:source-selectable")
    if evidence.get("unrelated_controls_disabled") is not True:
        issues.append("move-hover:unrelated-controls")
    if evidence.get("issues") != []:
        issues.append("move-hover:runtime-issues")
    if evidence.get("passed") is not True:
        issues.append("move-hover:runtime-passed")
    return tuple(issues)


def growth_stage_strip_issue_codes(records: Any) -> tuple[str, ...]:
    """Independently require the canonical muted six-stage Growth strip."""

    expected = (
        ("Seed", "reached", "Reached", False),
        ("Sprout", "current", "Current", False),
        ("Young", "next", "Next", True),
        ("Mature", "locked", "Locked", True),
        ("Flowering", "locked", "Locked", True),
        ("Full Bloom", "locked", "Locked", True),
    )
    if not isinstance(records, list) or len(records) != len(expected):
        return ("growth-stage-strip-count",)
    issues: list[str] = []
    for index, (record, expected_values) in enumerate(
        zip(records, expected),
        start=1,
    ):
        label, state, state_label, future = expected_values
        prefix = f"growth-stage-strip-{index}"
        if not isinstance(record, dict):
            issues.append(f"{prefix}:record")
            continue
        if record.get("label") != label:
            issues.append(f"{prefix}:label")
        if record.get("state") != state:
            issues.append(f"{prefix}:state")
        if record.get("state_label") != state_label:
            issues.append(f"{prefix}:state-label")
        if record.get("preview_enabled") is not True:
            issues.append(f"{prefix}:preview-enabled")
        if record.get("label_enabled") is not True:
            issues.append(f"{prefix}:label-enabled")
        if record.get("preview_future_treatment") is not future:
            issues.append(f"{prefix}:preview-treatment")
        if record.get("label_future_treatment") is not future:
            issues.append(f"{prefix}:label-treatment")
        if record.get("extra_text") != []:
            issues.append(f"{prefix}:extra-text")
    return tuple(issues)


def nursery_supplement_state_matrix_issue_codes(
    evidence: Any,
) -> tuple[str, ...]:
    """Independently validate Surface 22's painted production states."""

    if not isinstance(evidence, dict):
        return ("missing-nursery-supplement-state-matrix",)
    expected: dict[str, dict[str, Any]] = {
        "sufficient-balance": {
            "balance": 500,
            "balance_copy": "500",
            "item_id": "premium",
            "price_copy": "300 coins",
            "action": "Buy and apply",
            "action_disposition": "apply",
            "action_enabled": True,
            "painted": True,
        },
        "stored-multiple": {
            "item_id": "fertilizer_basic",
            "item_name": "Rich Compost",
            "owned_copy": "3 owned",
            "action": "Apply",
            "action_disposition": "apply",
            "meta_copy": (
                "+1 Growth per eligible card answer · Lasts 1 hour"
            ),
            "artwork_ref": "rich_compost",
            "artwork_source_matches": True,
            "artwork_fallback": False,
            "booster_item_id": "booster_potion",
            "booster_owned_copy": "2 owned",
            "booster_action": "Use",
            "booster_painted": True,
            "painted": True,
        },
        "active": {
            "engine_tier": "basic",
            "item_id": "fertilizer_basic",
            "owned_copy": "2 owned",
            "action": "Extend",
            "action_disposition": "extend",
            "status_phase": "active",
            "status_copy": (
                "Basic Fertilizer · +1 Growth per eligible card answer · "
                "1 hour left"
            ),
            "painted": True,
        },
        "queued": {
            "engine_tiers": ["quality"],
            "item_id": "fertilizer_quality",
            "owned_copy": "1 owned",
            "queued_copy": "Queued",
            "action": "Extend",
            "action_disposition": "extend",
            "final_basic_action": "Queue",
            "final_basic_action_disposition": "queue",
            "final_basic_painted": True,
            "final_quality_action": "Extend",
            "final_quality_action_disposition": "extend",
            "final_quality_painted": True,
            "meta_copy": (
                "+2 Growth per eligible card answer · Lasts 2 hours"
            ),
            "painted": True,
        },
    }
    issues: list[str] = []
    records = evidence.get("records")
    if not isinstance(records, dict) or set(records) != set(expected):
        issues.append("nursery-supplement-state-set")
        records = records if isinstance(records, dict) else {}
    for state, expected_values in expected.items():
        actual = records.get(state)
        if not isinstance(actual, dict):
            issues.append(f"nursery-supplement-{state}:missing")
            continue
        for key, expected_value in expected_values.items():
            if actual.get(key) != expected_value:
                issues.append(f"nursery-supplement-{state}:{key}")
    if evidence.get("passed") is not True:
        issues.append("nursery-supplement-state-matrix-not-passed")
    return tuple(dict.fromkeys(issues))


def nursery_environment_fixture_issue_codes(evidence: Any) -> tuple[str, ...]:
    """Independently validate Surface 24's exact catalog state fixture."""

    if not isinstance(evidence, dict):
        return ("missing-nursery-environment-fixture",)
    expected = {
        "displayed_decoration": {
            "item_id": "seedling_sign",
            "ownership_state": "owned",
            "display_state": "displayed",
            "display_action": "Displayed",
            "bonus_action": "Select today’s bonus",
            "painted": True,
        },
        "active_bonus": {
            "item_id": "watering_station",
            "ownership_state": "owned",
            "bonus_state": "active",
            "action": "Garden Bonus active today",
            "painted": True,
        },
        "purchasable": {
            "item_id": "wind_chime",
            "ownership_state": "available",
            "price": 100,
            "action": "Buy",
            "action_enabled": True,
            "painted": True,
        },
        "locked": {
            "item_id": "firefly_lantern",
            "ownership_state": "locked",
            "price": 0,
            "action": "How to unlock",
            "action_enabled": False,
            "painted": True,
        },
        "scenery_heading": {
            "text": "Scenery",
            "reachable": True,
            "painted": True,
        },
    }
    issues: list[str] = []
    for state, expected_values in expected.items():
        actual = evidence.get(state)
        if not isinstance(actual, dict):
            issues.append(f"nursery-environment-{state}:missing")
            continue
        for key, expected_value in expected_values.items():
            if actual.get(key) != expected_value:
                issues.append(f"nursery-environment-{state}:{key}")
    if evidence.get("fixture_profiles") != ["full", "representative"]:
        issues.append("nursery-environment-fixture-profiles")
    if evidence.get("reversible") is not True:
        issues.append("nursery-environment-fixture-reversible")
    return tuple(dict.fromkeys(issues))


def appearance_state_matrix_issue_codes(evidence: Any) -> tuple[str, ...]:
    """Independently validate Surface 25's exact projected appearance rows."""

    if not isinstance(evidence, dict):
        return ("missing-appearance-state-matrix",)
    expected_rows = [
        ["Scenery", "Verdant Twilight"],
        ["Displayed decoration", "Seedling Sign"],
        ["Active garden bonus", "Watering Station"],
    ]
    records = evidence.get("records")
    issues: list[str] = []
    if not isinstance(records, dict) or set(records) != {"on", "off"}:
        issues.append("appearance-state-set")
        records = records if isinstance(records, dict) else {}
    for state, effects_value in (("on", "On"), ("off", "Off")):
        actual = records.get(state)
        if not isinstance(actual, dict):
            issues.append(f"appearance-{state}:missing")
            continue
        expected = [*expected_rows, ["Visual effects", effects_value]]
        if actual.get("projection_rows") != expected:
            issues.append(f"appearance-{state}:projection-rows")
        if actual.get("painted_rows") != expected:
            issues.append(f"appearance-{state}:painted-rows")
        if actual.get("painted") is not True:
            issues.append(f"appearance-{state}:painted")
    if evidence.get("final_state") != "on":
        issues.append("appearance-final-state")
    if evidence.get("draft_dirty_before") is not False:
        issues.append("appearance-draft-before")
    if evidence.get("draft_dirty_after") is not False:
        issues.append("appearance-draft-after")
    if evidence.get("draft_payload_unchanged") is not True:
        issues.append("appearance-draft-payload")
    if evidence.get("garden_name_draft_unchanged") is not True:
        issues.append("appearance-name-draft")
    if evidence.get("reversible") is not True:
        issues.append("appearance-fixture-reversible")
    if evidence.get("passed") is not True:
        issues.append("appearance-state-matrix-not-passed")
    return tuple(dict.fromkeys(issues))


def settings_name_preview_absence_issue_codes(
    evidence: Any,
) -> tuple[str, ...]:
    """Independently reject a duplicate Settings Garden-name preview."""

    if not isinstance(evidence, dict):
        return ("missing-settings-name-preview-absence",)
    issues: list[str] = []
    if evidence.get("attribute_present") is not False:
        issues.append("settings-name-preview-attribute-present")
    if evidence.get("candidate_count") != 0:
        issues.append("settings-name-preview-candidate-count")
    if evidence.get("visible_candidate_count") != 0:
        issues.append("settings-name-preview-visible-candidate")
    if evidence.get("visible_copy") != []:
        issues.append("settings-name-preview-visible-copy")
    if evidence.get("draft_echo_count") != 0:
        issues.append("settings-name-preview-draft-echo")
    if evidence.get("issues") != []:
        issues.append("settings-name-preview-audit-issues")
    if evidence.get("passed") is not True:
        issues.append("settings-name-preview-not-passed")
    return tuple(dict.fromkeys(issues))


def reviewer_reward_dock_issue_codes(
    bundle: Any,
    geometry: Any,
) -> tuple[str, ...]:
    """Validate one seven-result bundle inside the persistent Reviewer HUD."""

    if not isinstance(bundle, dict):
        return ("missing-reviewer-reward-bundle",)
    issues: list[str] = []
    expected = {
        "event_count": 7,
        "active_reveal_count": 1,
        "hero_count": 1,
        "eyebrow": "MILESTONE REACHED",
        "hero_title": "Full Bloom achieved",
        "secondary_summary_count": 2,
        "details_action_copy": "Details ›",
        "details_action_heading_row": True,
        "obsolete_bottom_details_absent": True,
        "milestone_chevron_absent": True,
        "individual_close_button_count": 0,
        "detached_toast_count": 0,
        "session_footer_visible": True,
        "integrated_divider_visible": True,
        "same_commit_bundle": True,
        "presented_once": True,
        "stable_event_ids": True,
        "passed": True,
    }
    for key, expected_value in expected.items():
        if bundle.get(key) != expected_value:
            issues.append(f"reviewer-reward-bundle-mismatch:{key}")
    if not (
        bool(str(bundle.get("bundle_id", "")).strip())
        and bundle.get("rendered_bundle_id") == bundle.get("bundle_id")
        and bool(str(bundle.get("hero_event_id", "")).strip())
        and str(bundle.get("hero_subtitle", "")).strip() == ""
        and bundle.get("active_plant_identity_suppressed") is True
        and bool(str(bundle.get("projected_hero_subtitle", "")).strip())
        and bundle.get("visible_summary_labels") == [
            "1 Standard Find",
            "Garden discoveries",
        ]
        and bundle.get("visible_summary_reward_types") == [
            "garden_find",
            "environment_discovery",
        ]
        and all(bundle.get("visible_summary_artwork_refs", ()))
        and isinstance(bundle.get("visible_summary_event_ids"), list)
        and len(bundle["visible_summary_event_ids"]) == 2
        and all(
            isinstance(group, list)
            for group in bundle["visible_summary_event_ids"]
        )
        and len(bundle["visible_summary_event_ids"][0]) == 1
        and len(bundle["visible_summary_event_ids"][1]) == 2
        and len({
            event_id
            for group in bundle["visible_summary_event_ids"]
            for event_id in group
        }) == 3
    ):
        issues.append("reviewer-reward-bundle-identity-mismatch")
    if not (
        isinstance(geometry, dict)
        and geometry.get("passed") is True
        and geometry.get("dock_visible") is True
        and geometry.get("hud_reward_visible") is True
        and geometry.get("full_bloom_settled") is True
        and geometry.get("reward_bundle_id") == bundle.get("bundle_id")
        and geometry.get("contained_in_hud") is True
        and geometry.get("in_normal_flow") is True
        and geometry.get("overlaps_bottom_controls") is False
        and geometry.get("horizontal_scroll_maximum") == 0
        and 130 <= int(geometry.get("reveal_height", 0) or 0) <= 150
        and 48 <= int(geometry.get("footer_height", 0) or 0) <= 58
        and geometry.get("single_outer_surface") is True
        and geometry.get("divider_visible") is True
        and int(geometry.get("divider_count", 0) or 0) == 1
        and geometry.get("hero_components_contained") is True
        and geometry.get("hero_components_non_overlapping") is True
        and geometry.get("title_details_non_overlapping") is True
        and geometry.get("details_heading_aligned") is True
        and int(geometry.get("details_click_height", 0) or 0) >= 28
        and geometry.get("details_visible_in_scroll_viewport") is True
        and geometry.get("details_footer_non_overlapping") is True
        and int(geometry.get("details_divider_clearance", -1)) >= 8
        and geometry.get("obsolete_bottom_details_present") is False
        and geometry.get("obsolete_milestone_disclosure_present") is False
        and int(geometry.get("compact_vertical_scroll_maximum", -1)) == 0
    ):
        issues.append("reviewer-reward-dock-geometry-mismatch")
    return tuple(dict.fromkeys(issues))


def reviewer_hud_acceptance_matrix_issue_codes(
    label: str,
    viewport: Any,
    content: Any,
    interactions: Any = None,
    resilience: Any = None,
) -> tuple[str, ...]:
    """Validate the expanded transient Reviewer release-polish matrix."""

    baseline_states = {
        "18-cards-left",
        "1-card-left",
        "no-session-rewards",
        "growth-only",
        "growth-and-coins",
        "progress-10-percent",
        "progress-38-percent",
        "before-checkpoint",
        "exact-checkpoint",
        "checkpoint-marker-semantics",
        "early-stage-art",
        "mature-stage-art",
        "zero-effects",
        "one-effect",
        "two-effects",
        "three-plus-effects",
        "long-effects-one-column",
        "short-plant-name",
        "two-line-plant-name",
        "estimate-1-card",
        "estimate-14-cards",
        "estimate-1240-cards",
        "checkpoint-crossing",
        "multiple-checkpoints-one-answer",
        "stage-change",
        "coin-balance-248",
        "coin-balance-9999",
        "coin-balance-10013",
        "coin-balance-999999",
        "coin-balance-1000000",
        "header-stable-grouping",
        "short-height",
    }
    reward_states = {
        "all-cards-complete",
        "one-garden-find",
        "discovery-new-wording",
        "full-bloom",
        "full-bloom-celebration",
        "full-bloom-settled",
        "full-bloom-details",
        "full-bloom-several-secondary",
        "reward-details-action-copy",
        "settled-height-or-safe-scroll",
        "full-bloom-short-height",
        "session-footer-reconciliation",
        "reward-reveal-lifecycle",
        "session-history-named-growth",
    }
    issues: list[str] = []
    expected_content = (
        reward_states
        if label == "reviewer-reward-dock-bundle"
        else baseline_states
    )

    def valid_bounds(value: Any) -> bool:
        return bool(
            isinstance(value, list)
            and len(value) == 4
            and all(isinstance(component, int) for component in value)
            and value[2] > 0
            and value[3] > 0
        )

    def answer_controls_exclusion_passed(
        row: dict[str, Any],
        *,
        measured_required: bool,
    ) -> bool:
        evidence = row.get("answer_controls_exclusion")
        if not isinstance(evidence, dict) or evidence.get("passed") is not True:
            return False
        if evidence.get("measured_required") is not measured_required:
            return False
        if not measured_required:
            return bool(
                evidence.get("measured_passed") is True
                or evidence.get("fallback_passed") is True
            )
        rectangles = evidence.get("control_rectangles")
        return bool(
            evidence.get("measured") is True
            and evidence.get("measured_passed") is True
            and evidence.get("fallback_passed") is False
            and evidence.get("source") == "webengine-dom"
            and evidence.get("telemetry_state") == "measured"
            and evidence.get("schema_version") == 1
            and int(evidence.get("matched_nodes", 0) or 0) >= 1
            and evidence.get("viewport_matches") is True
            and evidence.get("rect_in_viewport") is True
            and evidence.get("rectangles_intersect") is False
            and isinstance(rectangles, list)
            and len(rectangles) == 1
            and valid_bounds(rectangles[0].get("bounds"))
            and rectangles[0].get("source") == "webengine-dom"
            and int(evidence.get("hud_bottom", -1))
            <= int(evidence.get("controls_top", -2))
            and int(evidence.get("reported_clearance", -1)) >= 0
            and evidence.get("hud_answer_controls_source")
            == "webengine-dom"
        )

    def effect_geometry_passed(
        row: dict[str, Any],
        *,
        expected_count: int,
        overflow: bool,
    ) -> bool:
        chip_bounds = row.get("effect_chip_bounds")
        label_bounds = row.get("effect_label_bounds")
        return bool(
            isinstance(chip_bounds, list)
            and len(chip_bounds) == expected_count
            and all(valid_bounds(bounds) for bounds in chip_bounds)
            and isinstance(label_bounds, list)
            and len(label_bounds) == expected_count
            and all(valid_bounds(bounds) for bounds in label_bounds)
            and row.get("effect_chips_contained") is True
            and row.get("effect_labels_contained") is True
            and row.get("effect_labels_unclipped") is True
            and row.get("effect_art_passed") is True
            and row.get("effect_chip_overlap_pairs") == []
            and row.get("overflow_contained") is True
            and row.get("overflow_visible") is overflow
        )

    def measured_plant_layout_passed(
        row: dict[str, Any],
        *,
        compare_short: bool,
    ) -> bool:
        if not (
            valid_bounds(row.get("title_bounds"))
            and valid_bounds(row.get("art_bounds"))
            and valid_bounds(row.get("progress_bounds"))
            and row.get("components_contained") is True
            and row.get("components_ordered") is True
            and row.get("declared_title_anchor_stable") is True
            and row.get("title_anchor_stable") is True
        ):
            return False
        if not compare_short:
            return True
        return bool(
            valid_bounds(row.get("short_title_bounds"))
            and valid_bounds(row.get("short_art_bounds"))
            and valid_bounds(row.get("short_progress_bounds"))
            and row.get("title_position_stable") is True
            and row.get("art_position_stable") is True
            and row.get("progress_position_stable") is True
            and row.get("title_bounds") == row.get("short_title_bounds")
            and row.get("art_bounds") == row.get("short_art_bounds")
            and row.get("progress_bounds") == row.get("short_progress_bounds")
        )

    def checkpoint_post_commit_passed(row: dict[str, Any]) -> bool:
        sequence = row.get("post_commit_sequence")
        if not isinstance(sequence, dict):
            return False
        deferred = sequence.get("deferred_before_marker")
        marker = sequence.get("marker_snapshot")
        reveal = sequence.get("reveal_snapshot")
        expected_order = [
            "marker-reached",
            "reward-revealed",
            "excess-fill-complete",
            "header-increment-settled",
        ]
        return bool(
            sequence.get("passed") is True
            and sequence.get("presented") is True
            and isinstance(deferred, dict)
            and deferred == {
                "coin_update": True,
                "session_update": True,
                "header_balance": 248,
                "session_growth_units": 0,
            }
            and isinstance(marker, dict)
            and marker == {
                "progress_percent": 25,
                "reward_visible": False,
                "header_balance": 248,
            }
            and isinstance(reveal, dict)
            and reveal == {
                "progress_percent": 25,
                "reward_visible": True,
                "eyebrow": "CHECKPOINT REACHED",
                "hero_title": "25% checkpoint",
                "coin_copy": "+2 coins",
                "header_balance": 248,
            }
            and sequence.get("sequence") == expected_order
            and sequence.get("expected_sequence") == expected_order
            and sequence.get("eyebrow") == "CHECKPOINT REACHED"
            and sequence.get("hero_title") == "25% checkpoint"
            and sequence.get("coin_copy") == "+2 coins"
            and sequence.get("final_progress_percent") == 38
            and sequence.get("final_header_balance") == 250
            and sequence.get("final_session_metric_copy")
            == ["+18 growth", "+2 coins"]
            and sequence.get("marker_before_reveal") is True
            and sequence.get("reward_before_excess_fill") is True
            and sequence.get("header_increment_deferred") is True
        )

    def routine_committed_answer_passed(row: dict[str, Any]) -> bool:
        sequence = row.get("routine_committed_answer_sequence")
        if not isinstance(sequence, dict):
            return False
        applied = sequence.get("applied")
        settled = sequence.get("settled")
        restored = sequence.get("restored")
        return bool(
            sequence.get("passed") is True
            and sequence.get("presented") is True
            and sequence.get("progress_before") == 10
            and sequence.get("session_before") == 0
            and sequence.get("session_update_deferred") is True
            and applied == {
                "label": "Growth applied",
                "value": "+18 growth",
                "result_state": "applied",
                "progress_percent": 10,
                "art_pulse": True,
                "session_growth_units": 0,
            }
            and isinstance(settled, dict)
            and settled == {
                "progress_percent": 18,
                "routine_feedback_active": False,
                "session_growth_units": 1_800,
                "session_metric_copy": ["+18 growth"],
                "released_after_progress": True,
            }
            and isinstance(restored, dict)
            and restored.get("label") == "Next answer"
            and restored.get("value") == "+18 growth"
            and restored.get("result_state") == "projection"
            and restored.get("art_pulse") is False
            and restored.get("reward_visible") is False
        )

    def daily_completion_transition_passed(row: dict[str, Any]) -> bool:
        transition = row.get("daily_completion_transition")
        if not isinstance(transition, dict):
            return False
        before = transition.get("before")
        initial = transition.get("initial")
        final = transition.get("final")
        return bool(
            transition.get("passed") is True
            and before == {
                "displayed_progress_percent": 98.5,
                "heading": "Today’s cards",
                "header_balance": 250,
                "session_coins": 0,
            }
            and isinstance(initial, dict)
            and initial.get("transition_active") is True
            and initial.get("completion_settling") is True
            and 98.5
            <= float(initial.get("displayed_progress_percent", 0) or 0)
            < 100
            and initial.get("heading") == "Today’s cards"
            and initial.get("coin_update_deferred") is True
            and initial.get("session_update_deferred") is True
            and initial.get("header_balance") == 250
            and initial.get("session_coins") == 0
            and final == {
                "transition_active": False,
                "completion_status": "complete",
                "heading": "All cards complete",
                "reward_copy": "+10 coins",
                "displayed_progress_percent": 100,
                "header_balance": 260,
                "session_coins": 10,
                "session_metric_copy": ["+18 growth", "+10 coins"],
            }
        )

    def short_height_composition_passed(row: dict[str, Any]) -> bool:
        reveal = row.get("reward_reveal_bounds")
        divider = row.get("divider_bounds")
        footer = row.get("session_footer_bounds")
        if not (
            valid_bounds(reveal)
            and valid_bounds(divider)
            and valid_bounds(footer)
        ):
            return False
        reveal_bottom = int(reveal[1]) + int(reveal[3])
        divider_bottom = int(divider[1]) + int(divider[3])
        return bool(
            reveal_bottom <= int(divider[1])
            and divider_bottom <= int(footer[1])
            and reveal_bottom <= int(footer[1])
            and row.get("reward_reveal_viewport_contained") is True
            and row.get("reward_footer_non_overlapping") is True
            and row.get("divider_between_reward_and_footer") is True
        )

    def checkpoint_projection_passed(
        row: dict[str, Any],
        *,
        percent: int,
        markers: dict[str, str],
    ) -> bool:
        return bool(
            row.get("stage_percent_copy") == f"{percent}%"
            and row.get("track_progress_percent") == percent
            and row.get("painted_progress_percent") == percent
            and row.get("marker_states") == markers
            and row.get("current_position_handle") is False
            and row.get("marker_shape") == "diamond-tick"
        )

    def visible_reward_detail_rows_passed(row: dict[str, Any]) -> bool:
        rendered = row.get("visible_detail_rows")
        expected = row.get("expected_detail_rows")
        if not (
            isinstance(rendered, list)
            and isinstance(expected, list)
            and len(rendered) == len(expected) == 7
        ):
            return False
        return bool(
            row.get("visible_detail_rows_match") is True
            and all(
                isinstance(rendered_row, dict)
                and isinstance(expected_row, dict)
                and rendered_row.get("category")
                == expected_row.get("category")
                and bool(str(rendered_row.get("category_visible_text", "")).strip())
                and rendered_row.get("name") == expected_row.get("name")
                and bool(str(rendered_row.get("name_visible_text", "")).strip())
                and rendered_row.get("value") == expected_row.get("value")
                and rendered_row.get("event_ids")
                == expected_row.get("event_ids")
                for rendered_row, expected_row in zip(rendered, expected)
            )
        )

    def compact_reward_summary_passed(row: dict[str, Any]) -> bool:
        summaries = row.get("visible_summary_rows")
        if not isinstance(summaries, list) or len(summaries) != 2:
            return False
        find_row, discovery_row = summaries
        if not isinstance(find_row, dict) or not isinstance(discovery_row, dict):
            return False
        return bool(
            find_row.get("label") == "1 Standard Find"
            and find_row.get("reward_type") == "garden_find"
            and bool(str(find_row.get("artwork_ref", "")).strip())
            and find_row.get("uses_item_art") is True
            and find_row.get("icon_present") is True
            and find_row.get("icon_kind") == "item-art"
            and discovery_row.get("label") == "Garden discoveries"
            and discovery_row.get("reward_type") == "environment_discovery"
            and discovery_row.get("uses_item_art") is False
            and discovery_row.get("icon_present") is True
            and discovery_row.get("icon_kind")
            == "environment-discovery"
        )

    def stage_art_passed(
        row: dict[str, Any],
        *,
        stage_key: str,
        stage_copy: str,
    ) -> bool:
        base_passed = bool(
            row.get("stage_key") == stage_key
            and row.get("stage_copy") == stage_copy
            and bool(str(row.get("art_path", "")).strip())
            and row.get("pixmap_present") is True
            and int(row.get("pixmap_cache_key", 0) or 0) > 0
            and row.get("ground_shadow_stage") == stage_key
            and int(row.get("art_region_height", 0) or 0) >= 146
            and int(row.get("plant_art_height", 0) or 0) >= 82
            and row.get("distinct_from_other_stage") is True
        )
        if stage_key != "sprout":
            return base_passed
        return bool(
            base_passed
            and 45.0
            <= float(row.get("visible_plant_width", 0) or 0)
            <= 60.0
            and 85.0
            <= float(row.get("ground_shadow_width", 0) or 0)
            <= 105.0
        )

    def estimate_passed(
        row: dict[str, Any],
        *,
        count: int,
        rendered: str,
    ) -> bool:
        return bool(
            row.get("estimated_cards") == count
            and row.get("rendered_text") == rendered
            and row.get("contained") is True
            and row.get("text_fits") is True
            and row.get("uses_cards_copy") is True
        )

    def exact_balance_passed(
        row: dict[str, Any],
        *,
        value: int,
        rendered: str,
    ) -> bool:
        return bool(
            row.get("exact_value") == value
            and row.get("rendered_text") == rendered
            and row.get("compacted") is False
            and row.get("header_anchors_stable") is True
            and row.get("header_group_object_names")
            == ["reviewerHudTitleGroup", "reviewerHudHeaderActions"]
            and int(row.get("header_reserved_width", 0) or 0) > 0
            and row.get("balance_cluster_contained") is True
        )

    if not isinstance(content, dict):
        issues.append("missing-reviewer-hud-content-matrix")
    else:
        actual_content = {
            name
            for name, record in content.items()
            if name != "passed" and isinstance(record, dict)
        }
        if content.get("passed") is not True:
            issues.append("reviewer-hud-content-matrix-not-passed")
        if actual_content != expected_content:
            issues.append("reviewer-hud-content-matrix-state-mismatch")
        if any(
            record.get("passed") is not True
            for name, record in content.items()
            if name != "passed" and isinstance(record, dict)
        ):
            issues.append("reviewer-hud-content-state-not-passed")
        semantic_checks = {
            "18-cards-left": lambda row: (
                row.get("remaining_count") == 18
                and row.get("copy") == "18 cards left"
            ),
            "1-card-left": lambda row: (
                row.get("remaining_count") == 1
                and row.get("copy") == "1 card left"
                and row.get("near_complete_card") is True
                and row.get("near_complete_detail") is True
                and float(row.get("displayed_progress_percent", 0) or 0)
                == 98.5
                and row.get("progress_value") == 985
                and row.get("progress_maximum") == 1_000
                and row.get("minimum_unfilled_logical_pixels") == 4
                and int(
                    row.get("estimated_unfilled_logical_pixels", 0) or 0
                ) >= 4
                and row.get("visible_end_gap") is True
                and daily_completion_transition_passed(row)
            ),
            "no-session-rewards": lambda row: (
                row.get("dock_visible") is False
                and row.get("session_footer_visible") is False
            ),
            "growth-only": lambda row: (
                row.get("metric_keys") == ["growth"]
                and row.get("metric_copy") == ["+18 growth"]
                and row.get("divider_visible") is False
                and routine_committed_answer_passed(row)
            ),
            "growth-and-coins": lambda row: (
                row.get("metric_keys") == ["growth", "coins"]
                and row.get("metric_copy") == ["+18 growth", "+2 coins"]
                and row.get("zero_categories_omitted") is True
            ),
            "progress-10-percent": lambda row: checkpoint_projection_passed(
                row,
                percent=10,
                markers={
                    "25": "next",
                    "50": "future",
                    "75": "future",
                    "100": "future",
                },
            ),
            "progress-38-percent": lambda row: checkpoint_projection_passed(
                row,
                percent=38,
                markers={
                    "25": "completed",
                    "50": "next",
                    "75": "future",
                    "100": "future",
                },
            ),
            "before-checkpoint": lambda row: checkpoint_projection_passed(
                row,
                percent=24,
                markers={
                    "25": "next",
                    "50": "future",
                    "75": "future",
                    "100": "future",
                },
            ),
            "exact-checkpoint": lambda row: checkpoint_projection_passed(
                row,
                percent=25,
                markers={
                    "25": "completed",
                    "50": "next",
                    "75": "future",
                    "100": "future",
                },
            ),
            "checkpoint-marker-semantics": lambda row: (
                row.get("semantic_id") == "reviewer.hud.checkpoint-track"
                and row.get("checkpoint_percents") == [25, 50, 75, 100]
                and row.get("marker_states") == {
                    "25": "completed",
                    "50": "next",
                    "75": "future",
                    "100": "future",
                }
                and row.get("transparent_for_mouse") is True
                and row.get("focus_safe") is True
                and row.get("is_abstract_slider") is False
                and row.get("current_position_handle") is False
                and row.get("marker_shape") == "diamond-tick"
                and row.get("future_marker_diameter") == 4.5
                and row.get("final_endpoint_inset") == 2.5
                and row.get("final_endpoint_inside_track") is True
                and row.get("checkpoint_reward_context")
                == "Checkpoint reward"
            ),
            "early-stage-art": lambda row: stage_art_passed(
                row,
                stage_key="sprout",
                stage_copy="Sprout · 2 of 6 stages",
            ),
            "mature-stage-art": lambda row: stage_art_passed(
                row,
                stage_key="mature",
                stage_copy="Mature · 4 of 6 stages",
            ),
            "zero-effects": lambda row: (
                row.get("visible_effect_count") == 0
                and effect_geometry_passed(
                    row,
                    expected_count=0,
                    overflow=False,
                )
            ),
            "one-effect": lambda row: (
                row.get("visible_effect_count") == 1
                and effect_geometry_passed(
                    row,
                    expected_count=1,
                    overflow=False,
                )
            ),
            "two-effects": lambda row: (
                row.get("visible_effect_count") == 2
                and effect_geometry_passed(
                    row,
                    expected_count=2,
                    overflow=False,
                )
            ),
            "three-plus-effects": lambda row: (
                row.get("visible_effect_count") == 2
                and row.get("overflow_visible") is True
                and row.get("overflow_text") == "1 more effect ›"
                and row.get("overflow_right_aligned") is True
                and effect_geometry_passed(
                    row,
                    expected_count=2,
                    overflow=True,
                )
            ),
            "long-effects-one-column": lambda row: (
                row.get("visible_effect_count") == 2
                and row.get("single_column") is True
                and row.get("vertically_stacked") is True
                and effect_geometry_passed(
                    row,
                    expected_count=2,
                    overflow=False,
                )
            ),
            "short-plant-name": lambda row: (
                row.get("title") == "Rose"
                and row.get("class_label") == "Bonsai"
                and measured_plant_layout_passed(row, compare_short=False)
            ),
            "two-line-plant-name": lambda row: (
                row.get("title_line_count") == 2
                and row.get("title_clamped") is False
                and row.get("class_label") == "Bonsai"
                and measured_plant_layout_passed(row, compare_short=True)
            ),
            "estimate-1-card": lambda row: estimate_passed(
                row,
                count=1,
                rendered="~1 card",
            ),
            "estimate-14-cards": lambda row: estimate_passed(
                row,
                count=14,
                rendered="~14 cards",
            ),
            "estimate-1240-cards": lambda row: estimate_passed(
                row,
                count=1_240,
                rendered="~1,240 cards",
            ),
            "checkpoint-crossing": lambda row: (
                row.get("crossed_checkpoints") == [25]
                and row.get("marker_states") == {
                    "25": "completed",
                    "50": "next",
                    "75": "future",
                    "100": "future",
                }
                and row.get("current_position_handle") is False
                and row.get("excess_progress_preserved") is True
                and checkpoint_post_commit_passed(row)
            ),
            "multiple-checkpoints-one-answer": lambda row: (
                row.get("crossed_checkpoints") == [25, 50]
                and row.get("chronological") is True
                and row.get("final_progress_percent") == 55
                and row.get("next_checkpoint_percent") == 75
            ),
            "stage-change": lambda row: (
                row.get("stage_changed") is True
                and row.get("celebration") == "stage-change"
            ),
            "coin-balance-248": lambda row: exact_balance_passed(
                row,
                value=248,
                rendered="248",
            ),
            "coin-balance-9999": lambda row: exact_balance_passed(
                row,
                value=9_999,
                rendered="9,999",
            ),
            "coin-balance-10013": lambda row: (
                exact_balance_passed(
                    row,
                    value=10_013,
                    rendered="10,013",
                )
                and row.get("large_balance_samples") == [
                    {
                        "exact_value": 999_999,
                        "rendered_text": "999,999",
                        "compacted": False,
                        "header_anchors_stable": True,
                        "passed": True,
                    },
                    {
                        "exact_value": 1_000_000,
                        "rendered_text": "1,000,000",
                        "compacted": False,
                        "header_anchors_stable": True,
                        "passed": True,
                    },
                ]
            ),
            "coin-balance-999999": lambda row: exact_balance_passed(
                row,
                value=999_999,
                rendered="999,999",
            ),
            "coin-balance-1000000": lambda row: exact_balance_passed(
                row,
                value=1_000_000,
                rendered="1,000,000",
            ),
            "header-stable-grouping": lambda row: (
                row.get("balance_states") == [
                    "coin-balance-248",
                    "coin-balance-9999",
                    "coin-balance-10013",
                    "coin-balance-999999",
                    "coin-balance-1000000",
                ]
                and row.get("object_names")
                == ["reviewerHudTitleGroup", "reviewerHudHeaderActions"]
                and int(row.get("reserved_width", 0) or 0) > 0
                and len(row.get("anchor_snapshots", [])) == 5
                and len({
                    tuple(tuple(bounds) for bounds in snapshot)
                    for snapshot in row.get("anchor_snapshots", [])
                }) == 1
            ),
            "short-height": lambda row: (
                row.get("horizontal_scroll_maximum") == 0
                and int(row.get("vertical_scroll_maximum", 0) or 0) > 0
                and row.get("overlaps_bottom_controls") is False
                and row.get("minimum_art_preserved") is True
                and row.get("major_reward_visible") is True
                and row.get("session_footer_visible") is True
                and row.get("integrated_divider_visible") is True
                and row.get("reward_dock_contained") is True
                and row.get("reward_reveal_contained") is True
                and row.get("session_footer_contained") is True
                and short_height_composition_passed(row)
                and row.get("sticky_header_and_dock") is True
                and row.get("session_metric_copy")
                == ["+18 growth", "+2 coins"]
                and row.get("baseline_short_viewport_passed") is True
            ),
            "all-cards-complete": lambda row: (
                row.get("completion_status") == "complete"
                and row.get("heading") == "All cards complete"
                and row.get("displayed_progress_percent") == 100
                and row.get("reward_copy") == "+10 coins"
            ),
            "one-garden-find": lambda row: (
                row.get("find_count") == 1
                and row.get("footer_copy") == "1 Standard Find"
            ),
            "discovery-new-wording": lambda row: (
                row.get("visible_summary_labels")
                == ["1 Standard Find", "Garden discoveries"]
                and row.get("discovery_summary") == "Garden discoveries"
            ),
            "full-bloom": lambda row: (
                row.get("eyebrow") == "MILESTONE REACHED"
                and row.get("hero_title") == "Full Bloom achieved"
                and str(row.get("hero_subtitle", "")).strip() == ""
                and row.get("active_plant_identity_suppressed") is True
                and row.get("class_label") == "Bonsai"
                and row.get("bed_visible") is False
                and row.get("settled") is True
                and row.get("temporary_gold_cleared") is True
                and row.get("settled_copy")
                == (
                    "Future Growth will go to other planted plants. "
                    "Any remainder will be stored."
                )
                and row.get("select_another_visible") is True
                and row.get("select_another_copy") == "Choose next plant ›"
                and row.get("art_scale") == 1.0
                and row.get("particles_active") is False
            ),
            "full-bloom-celebration": lambda row: (
                row.get("celebration") == "full-bloom"
                and row.get("settled") is False
                and row.get("temporary_gold_visible") is True
                and (
                    row.get("motion_animation_active") is True
                    or float(row.get("art_scale", 1.0) or 1.0) > 1.0
                    or row.get("particles_active") is True
                )
                and row.get("select_another_visible") is False
            ),
            "full-bloom-settled": lambda row: (
                row.get("settled") is True
                and row.get("temporary_gold_cleared") is True
                and row.get("settled_copy")
                == (
                    "Future Growth will go to other planted plants. "
                    "Any remainder will be stored."
                )
                and row.get("select_another_visible") is True
                and row.get("select_another_copy") == "Choose next plant ›"
                and row.get("art_scale") == 1.0
                and row.get("particles_active") is False
            ),
            "full-bloom-details": lambda row: (
                row.get("details_expanded") is True
                and row.get("all_secondary_items_present") is True
                and row.get("details_action_copy") == "Hide details"
                and int(row.get("maximum_height", 0) or 0) >= 240
                and row.get("detail_row_count") == 7
                and visible_reward_detail_rows_passed(row)
                and row.get("detail_event_ids_reconciled") is True
                and row.get("detail_panel_visible") is True
                and row.get("reveal_state") == "details_open"
                and int(row.get("vertical_scroll_maximum", 0) or 0) > 0
            ),
            "full-bloom-several-secondary": lambda row: (
                row.get("visible_summary_count") == 2
                and str(row.get("hero_subtitle", "")).strip() == ""
                and row.get("active_plant_identity_suppressed") is True
                and row.get("visible_summary_labels") == [
                    "1 Standard Find",
                    "Garden discoveries",
                ]
                and compact_reward_summary_passed(row)
                and row.get("details_action_copy") == "Details ›"
                and int(row.get("details_click_height", 0) or 0) >= 28
                and row.get("details_heading_aligned") is True
                and 130 <= int(row.get("reveal_height", 0) or 0) <= 150
                and row.get("title_details_non_overlapping") is True
                and row.get("detail_event_ids_reconciled") is True
                and row.get("obsolete_bottom_details_present") is False
                and row.get("obsolete_milestone_disclosure_present") is False
                and row.get("milestone_medallion") is True
                and row.get("medallion_pixmap_present") is True
                and row.get("reveal_state") == "celebrating"
            ),
            "reward-details-action-copy": lambda row: (
                row.get("collapsed_action_copy") == "Details ›"
                and int(row.get("minimum_click_height", 0) or 0) >= 28
                and row.get("event_ids_reconciled") is True
                and row.get("heading_row_action") is True
                and row.get("obsolete_bottom_action_absent") is True
                and row.get("milestone_chevron_absent") is True
            ),
            "settled-height-or-safe-scroll": lambda row: (
                row.get("safe_area_passed") is True
                and row.get("horizontal_scroll_maximum") == 0
                and (
                    row.get("height_at_most_660") is True
                    or row.get("safe_scroll") is True
                )
            ),
            "full-bloom-short-height": lambda row: (
                row.get("requested_host_size") == [1_280, 600]
                and row.get("host_shortened") is True
                and row.get("hud_safe_area_passed") is True
                and row.get("horizontal_scroll_maximum") == 0
                and (
                    row.get("middle_content_fits") is True
                    or row.get("middle_scroll_owns_overflow") is True
                )
                and row.get("major_reward_visible") is True
                and row.get("session_footer_visible") is True
                and row.get("fixed_header_visible") is True
                and row.get("fixed_header_outside_middle_scroll") is True
                and row.get("fixed_session_footer_outside_middle_scroll") is True
                and row.get("fixed_regions_non_overlapping") is True
                and row.get("sticky_reward_and_footer") is True
                and row.get("reward_footer_non_overlapping") is True
                and 130 <= int(row.get("reveal_height", 0) or 0) <= 150
                and row.get("canonical_viewport_restored") is True
            ),
            "session-footer-reconciliation": lambda row: (
                row.get("bundle_id") in row.get("history_bundle_ids", [])
                and row.get("footer_growth_units")
                == row.get("live_growth_units") == 4_000
                and row.get("footer_coins") == row.get("live_coins") == 14
                and row.get("footer_finds") == row.get("live_finds") == 1
                and row.get("footer_copy")
                == ["+40 growth", "+14 coins", "1 Standard Find"]
            ),
            "reward-reveal-lifecycle": lambda row: (
                row.get("celebrating") == "celebrating"
                and row.get("details_open") == "details_open"
                and row.get("settled") == "settled"
                and row.get("archived") == "archived"
                and row.get("details_paused_archive") is True
            ),
            "session-history-named-growth": lambda row: (
                "Full Bloom achieved" in row.get("meaningful_names", [])
                and "Morning Dew" in row.get("meaningful_names", [])
                and "Firefly Lantern" in row.get("meaningful_names", [])
                and "Verdant Twilight" in row.get("meaningful_names", [])
                and row.get("routine_row_count") == 1
                and row.get("routine_name") == "Growth applied"
                and row.get("routine_value") == "+6 Growth"
                and row.get("routine_event_ids")
                == ["capture-routine-growth-next-commit"]
                and row.get("routine_line") == "Growth applied · +6 Growth"
                and row.get("routine_non_clickable") is True
            ),
        }
        for name in expected_content:
            record = content.get(name)
            check = semantic_checks.get(name)
            if (
                isinstance(record, dict)
                and check is not None
                and not check(record)
            ):
                issues.append(f"reviewer-hud-content-semantic-mismatch:{name}")

    if label == "reviewer-hud-expanded":
        expected_windows = {
            "1710x1041",
            "1600x1000",
            "1280x800",
            "short-height",
            "expanded",
            "collapsed",
        }
        expected_rows = {
            "1710x1041-expanded",
            "1600x1000-expanded",
            "1280x800-expanded",
            "1280x600-short-expanded",
            "1280x800-collapsed",
        }
        if not isinstance(viewport, dict):
            issues.append("missing-reviewer-hud-viewport-matrix")
        else:
            actual_rows = {
                name
                for name, record in viewport.items()
                if name not in {"passed", "covered_requirements"}
                and isinstance(record, dict)
            }
            if viewport.get("passed") is not True:
                issues.append("reviewer-hud-viewport-matrix-not-passed")
            if actual_rows != expected_rows:
                issues.append("reviewer-hud-viewport-row-mismatch")
            if set(viewport.get("covered_requirements", ()) or ()) != expected_windows:
                issues.append("reviewer-hud-window-requirement-mismatch")
            if any(
                record.get("passed") is not True
                for name, record in viewport.items()
                if name not in {"passed", "covered_requirements"}
                and isinstance(record, dict)
            ):
                issues.append("reviewer-hud-viewport-state-not-passed")
            if any(
                not answer_controls_exclusion_passed(
                    record,
                    measured_required=(name != "1280x800-collapsed"),
                )
                for name, record in viewport.items()
                if name in expected_rows and isinstance(record, dict)
            ):
                issues.append("reviewer-hud-answer-control-exclusion-not-passed")
    elif label == "reviewer-reward-dock-bundle":
        expected_interactions = {
            "collapsed-unseen-reward",
            "overflow-expanded",
            "rapid-successive-rewards",
            "collection-sync-hud-open",
            "reviewer-reload-after-reward",
            "history-remount-idempotence",
            "history-reopen",
            "no-replay",
            "details-pause-archive",
            "archive-after-next-commit",
        }
        if not isinstance(interactions, dict):
            issues.append("missing-reviewer-reward-interaction-matrix")
        else:
            actual_interactions = {
                name
                for name, record in interactions.items()
                if name != "passed" and isinstance(record, dict)
            }
            if interactions.get("passed") is not True:
                issues.append("reviewer-reward-interaction-matrix-not-passed")
            if actual_interactions != expected_interactions:
                issues.append("reviewer-reward-interaction-state-mismatch")
            if any(
                record.get("passed") is not True
                for name, record in interactions.items()
                if name != "passed" and isinstance(record, dict)
            ):
                issues.append("reviewer-reward-interaction-state-not-passed")
            no_replay = interactions.get("no-replay")
            if not (
                isinstance(no_replay, dict)
                and no_replay.get(
                    "duplicate_call_idempotently_accepted"
                ) is True
                and no_replay.get("history_count_after")
                == no_replay.get("history_count_before")
                and no_replay.get("queue_count_after")
                == no_replay.get("queue_count_before")
                and no_replay.get("reveal_visible_after")
                == no_replay.get("reveal_visible_before")
                and no_replay.get("rendered_bundle_after")
                == no_replay.get("rendered_bundle_before")
                and no_replay.get("seen_id_preserved") is True
                and no_replay.get("sync_state_preserved") is True
                and no_replay.get("resize_reposition_preserved") is True
                and no_replay.get("details_round_trip_preserved") is True
                and no_replay.get("duplicate_projection_accepted") is True
                and no_replay.get("projection_update_exercised") is True
                and no_replay.get("next_card_projection_preserved") is True
            ):
                issues.append(
                    "reviewer-reward-interaction-semantic-mismatch:no-replay"
                )
            details_pause = interactions.get("details-pause-archive")
            if not (
                isinstance(details_pause, dict)
                and details_pause.get("routine_commit_accepted") is True
                and details_pause.get("state_before_commit") == "details_open"
                and details_pause.get("state_after_commit") == "details_open"
                and details_pause.get("details_remained_open") is True
                and details_pause.get("next_commit_seen") is True
                and details_pause.get("reward_remained_visible") is True
                and details_pause.get("active_bundle_preserved") is True
                and details_pause.get("history_advanced_once") is True
            ):
                issues.append(
                    "reviewer-reward-interaction-semantic-mismatch:details-pause-archive"
                )
            archived = interactions.get("archive-after-next-commit")
            if not (
                isinstance(archived, dict)
                and archived.get("reveal_state") == "archived"
                and archived.get("details_expanded") is False
                and archived.get("reward_visible") is False
                and archived.get("active_reward_cleared") is True
            ):
                issues.append(
                    "reviewer-reward-interaction-semantic-mismatch:archive-after-next-commit"
                )
    else:
        issues.append("unexpected-reviewer-hud-matrix-label")

    if label == "reviewer-hud-expanded":
        expected_resilience = {"no-active-plant", "stored-growth"}
        if not isinstance(resilience, dict):
            issues.append("missing-reviewer-hud-resilience-matrix")
        else:
            actual_resilience = {
                name
                for name, record in resilience.items()
                if name != "passed" and isinstance(record, dict)
            }
            if actual_resilience != expected_resilience:
                issues.append("reviewer-hud-resilience-state-mismatch")
            if resilience.get("passed") is not True or any(
                record.get("passed") is not True
                for name, record in resilience.items()
                if name != "passed" and isinstance(record, dict)
            ):
                issues.append("reviewer-hud-resilience-state-not-passed")
    return tuple(dict.fromkeys(issues))


def _visual_contract_record_issues(
    *,
    label: str,
    state_kind: str,
    record: dict[str, Any],
    audit: dict[str, Any] | None,
) -> list[str]:
    """Validate source-independent rendered-geometry and high-risk state proof."""

    problems: list[str] = []

    def reject(message: str) -> None:
        problems.append(message)

    visual = record.get("visual_contract_audit")
    if not isinstance(visual, dict):
        return ["visual_contract_audit is missing"]
    if audit is None or audit.get("visual_contract") != visual:
        reject("visual contract audit does not match the capture audit")
    if visual.get("passed") is not True:
        reject("visual contract audit did not pass")
    if visual.get("issues") != []:
        reject("visual contract issues must be empty")
    applicable = visual.get("applicable")
    if type(applicable) is not bool:
        reject("visual contract applicable must be boolean")
    elif applicable:
        controls = visual.get("controls")
        if not isinstance(controls, list):
            reject("visual contract controls must be a list")
        elif any(
            not isinstance(control, dict)
            or control.get("size_passed") is not True
            or control.get("text_fit_passed") is not True
            or not isinstance(control.get("bounds"), list)
            or len(control["bounds"]) != 4
            for control in controls
        ):
            reject("visual contract controls must have passing measured bounds")
        if visual.get("control_sizes_passed") is not True:
            reject("visual contract control sizes did not pass")
        if visual.get("action_text_fits") is not True:
            reject("visual contract contains an overflowing action label")
        for issue in visible_action_geometry_issue_codes(visual):
            reject(f"visible action geometry: {issue}")
        clipping_records = visual.get("clipping_records")
        if not isinstance(clipping_records, list) or any(
            not isinstance(item, dict)
            or item.get("kind") not in {"control", "card"}
            or not isinstance(item.get("clip_owner"), str)
            or not item.get("clip_owner")
            or not isinstance(item.get("bounds"), list)
            or len(item["bounds"]) != 4
            or not isinstance(item.get("owner_size"), list)
            or len(item["owner_size"]) != 2
            or item.get("contained") is not True
            for item in (
                clipping_records if isinstance(clipping_records, list) else []
            )
        ):
            reject("visual contract contains a partially clipped control or card")
        if visual.get("clipping_checks_passed") is not True:
            reject("visual contract clipping checks did not pass")
        footer_actions = visual.get("footer_actions")
        if not isinstance(footer_actions, list) or any(
            not isinstance(action, dict)
            or action.get("footer_action") is not True
            or action.get("contained") is not True
            for action in (
                footer_actions if isinstance(footer_actions, list) else []
            )
        ):
            reject("visual contract footer actions are invalid")
        if visual.get("footer_actions_contained") is not True:
            reject("visual contract footer action is outside the dialog")
        requires_inline_close = visual.get("requires_inline_close")
        if type(requires_inline_close) is not bool:
            reject("visual contract close requirement must be boolean")
            requires_inline_close = True
        close_icons = visual.get("close_icons")
        if not isinstance(close_icons, list):
            reject("visual contract close icons must be a list")
            close_icons = []
        elif requires_inline_close and not close_icons:
            reject("visual contract has no measured inline close icon")
        if close_icons and any(
            not isinstance(icon, dict)
            or icon.get("passed") is not True
            or icon.get("glyph_pixels_present") is not True
            or icon.get("capture_pixels_present") is not True
            or not isinstance(icon.get("bounds"), list)
            or len(icon["bounds"]) != 4
            for icon in close_icons
        ):
            reject("visual contract close icon has blank pixels or invalid bounds")
        if visual.get("close_icons_passed") is not True:
            reject("visual contract close icons did not pass")
        primary_count = visual.get("primary_action_count")
        if type(primary_count) is not int or primary_count < 0:
            reject("visual contract primary action count must be nonnegative")
        primary_groups = visual.get("primary_action_groups")
        if not isinstance(primary_groups, list) or any(
            not isinstance(group, dict)
            or not isinstance(group.get("scope"), str)
            or not isinstance(group.get("actions"), list)
            or type(group.get("count")) is not int
            or group.get("count") != len(group.get("actions", []))
            or group.get("passed") is not True
            for group in (primary_groups if isinstance(primary_groups, list) else [])
        ):
            reject("visual contract primary decision groups are invalid")
            primary_groups = []
        maximum_group_count = visual.get("max_primary_actions_per_group")
        independently_maximum = max(
            (
                int(group.get("count", 0))
                for group in primary_groups
                if isinstance(group, dict)
                and type(group.get("count")) is int
            ),
            default=0,
        )
        if (
            type(maximum_group_count) is not int
            or maximum_group_count != independently_maximum
            or maximum_group_count > 1
        ):
            reject(
                "visual contract must contain at most one filled primary action per decision group"
            )
        if visual.get("visible_horizontal_scrollbars") != []:
            reject("visual contract contains a visible horizontal scrollbar")
        largest_gap = visual.get("largest_unexplained_gap")
        if (
            isinstance(largest_gap, bool)
            or not isinstance(largest_gap, (int, float))
            or largest_gap < 0
        ):
            reject("visual contract largest gap must be a nonnegative number")
        if visual.get("screen_contained") is not True:
            reject("visual contract window is outside the available screen")
        popover = visual.get("popover")
        if not isinstance(popover, dict) or popover.get("passed") is not True:
            reject("visual contract popover containment did not pass")
        elif label.startswith("popover-plot-") and not (
            popover.get("applicable") is True
            and popover.get("contained_in_scene") is True
            and popover.get("canvas_direct") is True
        ):
            reject("visual contract popover is outside the direct Garden canvas")
        if label == "selected-plant-nurtured":
            plant_actions = visual.get("plant_action_geometry")
            expected_actions = [
                "Get growth charges",
                "Apply fertilizer",
                "Move",
                "Plant story",
                "Stop nurturing",
            ]
            if not isinstance(plant_actions, dict):
                reject("selected plant action geometry is missing")
            else:
                action_records = plant_actions.get("records")
                if not (
                    plant_actions.get("applicable") is True
                    and plant_actions.get("passed") is True
                    and plant_actions.get("expected_actions") == expected_actions
                    and plant_actions.get("overlaps") == []
                    and isinstance(action_records, list)
                    and len(action_records) == len(expected_actions)
                    and [
                        record.get("expected_text")
                        for record in action_records
                        if isinstance(record, dict)
                    ] == expected_actions
                    and all(
                        isinstance(record, dict)
                        and record.get("text") == record.get("expected_text")
                        and record.get("visible") is True
                        and record.get("contained") is True
                        and isinstance(record.get("bounds"), list)
                        and len(record["bounds"]) == 4
                        for record in action_records
                    )
                ):
                    reject("selected plant actions overlap or leave the plant card")
            popover_geometry = visual.get("plant_popover_geometry")
            if not isinstance(popover_geometry, dict):
                reject("selected plant popover geometry is missing")
            else:
                card_size = popover_geometry.get("card_size")
                connector_end = popover_geometry.get("connector_end")
                if not (
                    popover_geometry.get("applicable") is True
                    and popover_geometry.get("passed") is True
                    and popover_geometry.get("content_inset") == 12
                    and isinstance(card_size, list)
                    and len(card_size) == 2
                    and 288 <= card_size[0] <= 320
                    and 300 <= card_size[1] <= 325
                    and popover_geometry.get("chosen_side")
                    in {"right", "left", "above", "below"}
                    and isinstance(connector_end, list)
                    and len(connector_end) == 2
                    and popover_geometry.get("anatomy_passed") is True
                    and popover_geometry.get("actions_aligned") is True
                    and popover_geometry.get("pointer_clear") is True
                    and popover_geometry.get("selected_clear") is True
                    and popover_geometry.get("toast_clear") is True
                    and popover_geometry.get("contained_in_scene") is True
                ):
                    reject("selected plant popover is not anchored or aligned")
        if label == "starter-nursery-plants":
            starter_geometry = visual.get("starter_card_geometry")
            if starter_nursery_geometry_issue_codes(starter_geometry):
                reject(
                    "starter Nursery must show all compact Seed cards "
                    "inside its unscrolled content-fit viewport"
                )
        if label == "fertilizer-active":
            fertilizer_status = visual.get("fertilizer_status_geometry")
            if not isinstance(fertilizer_status, dict):
                reject("active Fertilizer status geometry is missing")
            elif not (
                fertilizer_status.get("applicable") is True
                and fertilizer_status.get("passed") is True
                and fertilizer_status.get("target") == "Applying to Rose Plant"
                and fertilizer_status.get("title") == "Basic Fertilizer"
                and fertilizer_status.get("summary")
                == (
                    "+1 Growth per eligible card answer · "
                    "1 hour remaining"
                )
                and fertilizer_status.get("balance_text") == "Balance: 500"
                and fertilizer_status.get("balance_icon_present") is True
                and fertilizer_status.get("extend_text")
                == "Extend 1h · 30 coins"
                and all(
                    isinstance(fertilizer_status.get(key), list)
                    and len(fertilizer_status[key]) == 4
                    for key in (
                        "status_bounds",
                        "icon_bounds",
                        "balance_bounds",
                        "extend_bounds",
                    )
                )
            ):
                reject("active Fertilizer must use the compact icon-led status card")
    elif state_kind not in {"home", "reviewer", "reviewer_hud"}:
        reject("visual contract was inapplicable for a Qt-owned surface")

    if audit is None:
        return problems

    def audit_object(name: str) -> dict[str, Any]:
        value = audit.get(name)
        if not isinstance(value, dict):
            reject(f"{name} is missing")
            return {}
        return value

    if state_kind in {"home", "reviewer", "reviewer_hud"}:
        web_root_overflow = audit_object("web_root_overflow")
        for issue in web_root_overflow_issue_codes(web_root_overflow):
            reject(f"HTML roots overflow: {issue}")

    required_pixel_keys = RENDERED_PIXEL_EVIDENCE_KEYS.get(label, ())
    if required_pixel_keys:
        rendered_pixels = audit_object("rendered_pixel_evidence")
        pixel_results = rendered_pixels.get("results")
        if not (
            rendered_pixels.get("passed") is True
            and rendered_pixels.get("required_keys")
            == list(required_pixel_keys)
            and isinstance(pixel_results, list)
            and [
                row.get("key")
                for row in pixel_results
                if isinstance(row, dict)
            ] == list(required_pixel_keys)
            and all(
                isinstance(row, dict)
                and row.get("visible") is True
                and row.get("contained") is True
                and row.get("capture_pixels_present") is True
                and row.get("passed") is True
                for row in pixel_results
            )
        ):
            reject("required state widgets are absent from captured pixels")

    if state_kind == "home":
        compact = audit_object("compact_home_copy")
        rendered = compact.get("rendered_text")
        banned = compact.get("banned_terms")
        if compact.get("passed") is not True:
            reject("compact Home copy audit did not pass")
        if not isinstance(rendered, str):
            reject("compact Home rendered copy must be a string")
        else:
            normalized = " ".join(rendered.casefold().split())
            leaked = [term for term in COMPACT_HOME_BANNED_COPY if term in normalized]
            if leaked:
                reject("compact Home rendered or accessibility copy contains banned terms")
        if banned != []:
            reject("compact Home banned term list must be empty")
        action = str(compact.get("action_text", ""))
        if not (
            compact.get("information_model_passed") is True
            and compact.get("geometry_passed") is True
        ):
            reject("compact Home information model or CTA geometry did not pass")
        if label == "home-preview-loading":
            if "loading garden" not in str(rendered).casefold():
                reject("Home loading state copy is missing")
        elif label == "home-preview-error":
            if not (
                "garden preview unavailable" in str(rendered).casefold()
                and action == "Open Garden"
            ):
                reject("Home error state must retain the Open Garden action")
        elif not label.startswith("starter-"):
            compact_growth_present = bool(
                re.search(
                    r"\b[\d,]+\s*/\s*[\d,]+\s+growth\b",
                    str(rendered),
                    flags=re.IGNORECASE,
                )
                or " toward " in str(rendered)
                or "total growth" in str(rendered).casefold()
            )
            if not (
                compact_growth_present
                and action == "Open Garden"
                and type(compact.get("action_width")) is int
                and 104 <= compact["action_width"] <= 128
                and compact.get("action_height") == 36
            ):
                reject("compact Home must show growth progress and a 104-128 by 36 Open Garden CTA")

    if label == "full-garden":
        steady = audit_object("steady_state_visual")
        if not (
            steady.get("passed") is True
            and steady.get("overlay_free") is True
            and steady.get("scene_contained") is True
            and steady.get("onboarding_step") == "done"
            and steady.get("canvas_direct") is True
        ):
            reject("full Garden does not prove a clean contained steady state")

    if label == "starter-placement":
        locked_visuals = audit.get("locked_bed_visuals")
        if not (
            audit.get("locked_bed_visuals_passed") is True
            and audit.get("allowed_destination_slots") == [0, 1]
            and audit.get("locked_bed_slots") == [2, 3, 4, 5]
            and isinstance(locked_visuals, list)
            and len(locked_visuals) == 4
            and all(
                isinstance(record, dict)
                and isinstance(
                    record.get("relative_visual_strength"),
                    (int, float),
                )
                and not isinstance(
                    record.get("relative_visual_strength"),
                    bool,
                )
                and float(record["relative_visual_strength"]) == 0.58
                and record.get("interactive") is False
                and all(
                    isinstance(record.get(key), list)
                    and len(record[key]) == 4
                    and all(
                        isinstance(value, (int, float))
                        and not isinstance(value, bool)
                        for value in record[key]
                    )
                    and float(record[key][2]) > 0
                    and float(record[key][3]) > 0
                    for key in ("overlay_bounds", "badge_bounds")
                )
                for record in locked_visuals
            )
        ):
            reject(
                "starter placement does not prove four muted, badged, noninteractive locked beds"
            )

    if label == "growth-nonzero":
        stage_records = audit.get("growth_stage_records")
        if audit.get("reference_size") != [940, 501]:
            reject("Growth reference size is not the content-fit 940×501 contract")
        if audit.get("rendered_size") != [940, 501]:
            reject("Growth did not render at the content-fit 940×501 contract")
        if audit.get("reference_size_passed") is not True:
            reject("Growth content-fit reference size did not pass")
        if audit.get("no_vertical_scroll") is not True:
            reject("Growth content-fit surface unexpectedly scrolls")
        strip_issues = growth_stage_strip_issue_codes(stage_records)
        if audit.get("growth_stage_strip_issues") != list(strip_issues):
            reject("Growth stage-strip runtime issue record is inconsistent")
        if audit.get("future_stage_muting_passed") is not bool(
            not strip_issues
        ):
            reject("Growth stage-strip runtime result is inconsistent")
        for issue in strip_issues:
            reject(f"Growth stage strip: {issue}")

    if label == "streak-active":
        streak_fold = audit_object("streak_fold_geometry")
        for issue in streak_fold_geometry_issue_codes(streak_fold):
            reject(f"Streak first fold: {issue}")

    if label in {
        "growth-charge-use-ready",
        "growth-charge-success-stage-reward",
    }:
        rendered_values = audit_object("growth_charge_rendered_values")
        for issue in growth_charge_rendered_value_issue_codes(
            label,
            rendered_values,
        ):
            reject(f"Growth Charge rendered values: {issue}")

    if label == "progress-achievements":
        cards = audit.get("visible_achievement_cards")
        visible_days = audit.get("visible_completion_days")
        visible_categories = audit.get("visible_completion_categories")
        date_texts = audit.get("visible_completion_date_texts")
        category_days: dict[str, list[str]] = {}
        if (
            isinstance(visible_days, list)
            and isinstance(visible_categories, list)
            and len(visible_days) == len(visible_categories)
        ):
            for category, day_value in zip(visible_categories, visible_days):
                if isinstance(category, str) and isinstance(day_value, str):
                    category_days.setdefault(category, []).append(day_value)
        if not (
            audit.get("valid_distinct_completion_dates") is True
            and audit.get("achievement_card_geometry_passed") is True
            and audit.get("rendered_chronological_dates_passed") is True
            and isinstance(cards, list)
            and bool(cards)
            and all(
                isinstance(card, dict)
                and card.get("fully_contained") is True
                and isinstance(card.get("bounds"), list)
                and len(card["bounds"]) == 4
                and type(card["bounds"][3]) is int
                and 108 <= card["bounds"][3] <= 120
                for card in cards
            )
            and isinstance(visible_days, list)
            and len(visible_days) >= 4
            and len(set(visible_days)) == len(visible_days)
            and isinstance(visible_categories, list)
            and len(visible_categories) == len(visible_days)
            and all(
                isinstance(value, str) and bool(value.strip())
                for value in visible_categories
            )
            and bool(category_days)
            and all(
                days == sorted(days)
                for days in category_days.values()
            )
            and isinstance(date_texts, list)
            and len(date_texts) == len(visible_days)
            and all(
                isinstance(value, str) and bool(value.strip())
                for value in date_texts
            )
            and len(set(date_texts)) == len(date_texts)
        ):
            reject(
                "Achievements must show complete 108-120 px cards with distinct chronological dates"
            )

    if label == "progress-overview-redirect-growth":
        direct = audit_object("direct_growth_visual")
        amount = direct.get("amount")
        if not (
            direct.get("passed") is True
            and type(amount) is int
            and amount > 0
            and "Rewards and charges" in str(direct.get("label", ""))
            and direct.get("label_contained") is True
            and direct.get("value_contained") is True
        ):
            reject("Growth redirect does not visibly prove nonzero direct reward or charge Growth")

    if label == "collection-preview-restored":
        restored = audit_object("restored_preview_visual")
        if not (
            restored.get("passed") is True
            and restored.get("visible") is True
            and restored.get("contained") is True
            and bool(str(restored.get("text", "")).strip())
            and audit.get("restored_preview_dirty_cleared") is True
        ):
            reject("restored preview does not show a contained result banner")

    if label == "collection-loadout-detail":
        catalog = audit_object("catalog_geometry")
        state_matrix = audit_object("collection_loadout_state_matrix")
        tile_records = catalog.get("tile_records")
        if not (
            catalog.get("passed") is True
            and catalog.get("scroll_name") == "Scenery catalogue"
            and catalog.get("visible_scroll_names") == ["Scenery catalogue"]
            and type(catalog.get("viewport_height")) is int
            and 250 <= catalog["viewport_height"] <= 266
            and type(catalog.get("tile_count")) is int
            and catalog["tile_count"] >= 4
            and type(catalog.get("visible_tile_count")) is int
            and catalog["visible_tile_count"] >= 4
            and catalog.get("visible_row_count") == 2
            and catalog.get("partial_tiles") == []
            and type(catalog.get("bottom_padding")) is int
            and catalog["bottom_padding"] >= 12
            and catalog.get("preview_fixed") is True
            and isinstance(tile_records, list)
            and len(tile_records) == catalog.get("visible_tile_count")
            and all(
                isinstance(tile, dict)
                and tile.get("contained") is True
                and isinstance(tile.get("bounds"), list)
                and len(tile["bounds"]) == 4
                for tile in tile_records
            )
        ):
            reject(
                "Collection loadout must use a local complete-row catalogue with fixed preview"
            )
        for issue in collection_loadout_state_matrix_issue_codes(
            state_matrix
        ):
            reject(f"Collection loadout state matrix: {issue}")

    if label == "nursery-fertilizer-booster":
        first_fold = audit_object("first_fold_geometry")
        supplement_matrix = audit_object("supplement_state_matrix")
        visible_cards = first_fold.get("visible_cards")
        expected_ids = {"fertilizer_basic", "fertilizer_quality"}
        if not (
            first_fold.get("passed") is True
            and first_fold.get("scroll_name")
            == "Fertilizers and boosts catalog"
            and expected_ids.issubset(
                set(first_fold.get("visible_card_ids", ()))
            )
            and first_fold.get("partial_card_ids") == []
            and first_fold.get("partial_actions") == []
            and type(first_fold.get("bottom_padding")) is int
            and first_fold["bottom_padding"] >= 20
            and first_fold.get("premium_action_contained") is True
            and first_fold.get("price_action_same_row") is True
            and isinstance(visible_cards, list)
            and all(
                isinstance(card, dict)
                and card.get("contained") is True
                and type(card.get("height")) is int
                and card["height"] >= 88
                for card in visible_cards
            )
        ):
            reject(
                "Nursery Fertilizer first fold contains a partial row or action"
            )
        for issue in nursery_supplement_state_matrix_issue_codes(
            supplement_matrix
        ):
            reject(f"Nursery Fertilizer state matrix: {issue}")

    if label == "nursery-garden-decorations-scenery":
        environment_fixture = audit_object(
            "garden_decoration_scenery_fixture"
        )
        for issue in nursery_environment_fixture_issue_codes(
            environment_fixture
        ):
            reject(f"Nursery appearance fixture: {issue}")

    if label == "nursery-garden-spaces":
        bed_state = audit_object("nursery_bed_incomplete_state")
        for issue in nursery_bed_incomplete_state_issue_codes(bed_state):
            reject(f"Nursery bed incomplete state: {issue}")

    if label == "settings-display-advanced-open":
        display = audit_object("display_geometry")
        if not (
            display.get("passed") is True
            and display.get("outer_scroll_name") == "Display settings"
            and type(display.get("outer_vertical_range")) is int
            and display["outer_vertical_range"] <= 1
            and display.get("outer_vertical_value") == 0
            and type(display.get("outer_horizontal_range")) is int
            and display["outer_horizontal_range"] <= 1
            and type(display.get("inner_vertical_range")) is int
            and display["inner_vertical_range"] <= 1
            and display.get("settings_preview_removed") is True
            and bool(str(display.get("current_scenery", "")).strip())
            and type(display.get("appearance_to_advanced_gap")) is int
            and 8 <= display["appearance_to_advanced_gap"] <= 12
            and all(
                isinstance(display.get(key), dict)
                and display[key].get("visible") is True
                and display[key].get("contained") is True
                for key in (
                    "home_setting_bounds",
                    "home_switch_bounds",
                    "appearance_bounds",
                    "advanced_header_bounds",
                    "advanced_panel_bounds",
                )
            )
        ):
            reject(
                "Settings Display must fit its compact preview and expanded controls without scrolling"
            )
        appearance_matrix = audit_object("appearance_state_matrix")
        for issue in appearance_state_matrix_issue_codes(appearance_matrix):
            reject(f"Settings Appearance state matrix: {issue}")
        name_preview_absence = audit_object(
            "garden_name_preview_absence"
        )
        for issue in settings_name_preview_absence_issue_codes(
            name_preview_absence
        ):
            reject(f"Settings Garden-name preview absence: {issue}")

    if label == "nursery-item-owned":
        owned = audit_object("owned_item_visual")
        if not (
            owned.get("passed") is True
            and bool(owned.get("item_id"))
            and bool(owned.get("item_name"))
            and all(
                isinstance(owned.get(key), dict)
                and owned[key].get("contained") is True
                for key in ("card", "title", "action_bounds")
            )
        ):
            reject("owned Nursery item is not visibly identified and contained")

    if label in {
        "reviewer-find-environment",
        "reviewer-find-common-reduced-motion",
    }:
        geometry = audit_object("reviewer_overlay_geometry")
        bounds = geometry.get("overlay_bounds")
        controls = geometry.get("control_rects")
        if not (
            geometry.get("passed") is True
            and geometry.get("parent_is_reviewer_webview") is True
            and geometry.get("parent_contract") == "mw.reviewer.web-exact"
            and geometry.get("reviewer_state_is_review") is True
            and geometry.get("non_review_cleanup_registered") is True
            and geometry.get("viewport_contained") is True
            and geometry.get("size_in_range") is True
            and geometry.get("expected_width") == 292
            and geometry.get("width_exact") is True
            and geometry.get("width") == 292
            and isinstance(bounds, list)
            and len(bounds) == 4
            and isinstance(controls, list)
            and bool(controls)
            and type(geometry.get("minimum_control_clearance")) is int
            and geometry["minimum_control_clearance"] >= 16
        ):
            reject("Reviewer card lacks full containment or control clearance")
        if audit.get("required_overlay_pixels_present") is not True:
            reject("Reviewer card is absent from captured pixels")
    if label in {"reviewer-hud-expanded", "reviewer-reward-dock-bundle"}:
        hud_geometry = audit_object("reviewer_hud_geometry")
        answer_controls = hud_geometry.get("answer_controls_exclusion")
        control_rectangles = (
            answer_controls.get("control_rectangles")
            if isinstance(answer_controls, dict) else
            None
        )
        if not (
            hud_geometry.get("safe_area_passed") is True
            and isinstance(answer_controls, dict)
            and answer_controls.get("passed") is True
            and answer_controls.get("measured_required") is True
            and answer_controls.get("measured") is True
            and answer_controls.get("measured_passed") is True
            and answer_controls.get("fallback_passed") is False
            and answer_controls.get("source") == "webengine-dom"
            and answer_controls.get("telemetry_state") == "measured"
            and answer_controls.get("schema_version") == 1
            and int(answer_controls.get("matched_nodes", 0) or 0) >= 1
            and answer_controls.get("viewport_matches") is True
            and answer_controls.get("rect_in_viewport") is True
            and answer_controls.get("rectangles_intersect") is False
            and isinstance(control_rectangles, list)
            and len(control_rectangles) == 1
            and isinstance(control_rectangles[0], dict)
            and control_rectangles[0].get("source") == "webengine-dom"
            and isinstance(control_rectangles[0].get("bounds"), list)
            and len(control_rectangles[0]["bounds"]) == 4
            and all(
                type(component) is int
                for component in control_rectangles[0]["bounds"]
            )
            and control_rectangles[0]["bounds"][2] > 0
            and control_rectangles[0]["bounds"][3] > 0
            and int(answer_controls.get("hud_bottom", -1))
            <= int(answer_controls.get("controls_top", -2))
            and answer_controls.get("hud_answer_controls_source")
            == "webengine-dom"
        ):
            reject(
                "Reviewer HUD lacks measured answer-control exclusion rectangles"
            )
        viewport = (
            audit_object("reviewer_hud_viewport_matrix")
            if label == "reviewer-hud-expanded"
            else None
        )
        content = audit_object("reviewer_hud_content_matrix")
        interactions = (
            audit_object("reviewer_reward_interaction_matrix")
            if label == "reviewer-reward-dock-bundle"
            else None
        )
        resilience = (
            audit_object("reviewer_hud_resilience_matrix")
            if label == "reviewer-hud-expanded"
            else None
        )
        for issue in reviewer_hud_acceptance_matrix_issue_codes(
            label,
            viewport,
            content,
            interactions,
            resilience,
        ):
            reject(f"Reviewer HUD acceptance matrix: {issue}")
    if label == "reviewer-reward-dock-bundle":
        bundle = audit_object("reviewer_reward_bundle")
        geometry = audit_object("reviewer_reward_dock_geometry")
        for issue in reviewer_reward_dock_issue_codes(bundle, geometry):
            reject(f"Reviewer reward-dock capture: {issue}")
        if audit.get("required_overlay_pixels_present") is not True:
            reject("Reviewer reward dock is absent from captured pixels")

    if label == "diagnostics-warning":
        diagnostics_matrix = audit_object("diagnostics_state_matrix")
        for issue in diagnostics_state_matrix_issue_codes(diagnostics_matrix):
            reject(f"Diagnostics state matrix: {issue}")

    if label == "sync-rewards-summary":
        discovery_matrix = audit_object(
            "sync_reward_discovery_state_matrix"
        )
        for issue in sync_reward_discovery_state_matrix_issue_codes(
            discovery_matrix
        ):
            reject(f"Sync reward discovery state matrix: {issue}")

    if label == "missing-artwork-graphical-fallback":
        matrix = audit_object("missing_artwork_matrix")
        entries = matrix.get("entries")
        missing_paths = matrix.get("missing_source_paths")
        logged_fingerprints = matrix.get("diagnostic_log_fingerprints")
        visible_card = matrix.get("visible_card")
        visible_preview = matrix.get("visible_preview")
        if not (
            matrix.get("passed") is True
            and matrix.get("types") == list(MISSING_ARTWORK_CAPTURE_TYPES)
            and isinstance(entries, list)
            and len(entries) == len(MISSING_ARTWORK_CAPTURE_TYPES)
            and isinstance(missing_paths, dict)
            and set(missing_paths) == set(MISSING_ARTWORK_CAPTURE_TYPES)
            and isinstance(logged_fingerprints, list)
            and len(logged_fingerprints) == len(MISSING_ARTWORK_CAPTURE_TYPES)
            and [entry.get("type") for entry in entries if isinstance(entry, dict)]
            == list(MISSING_ARTWORK_CAPTURE_TYPES)
            and all(
                isinstance(entry, dict)
                and entry.get("passed") is True
                and entry.get("semantic_role") == "missing-art"
                and entry.get("graphic_present") is True
                and entry.get("aspect_ratio_preserved") is True
                and entry.get("diagnostic_path_logged") is True
                and bool(str(entry.get("accessible_name", "")).strip())
                and str(entry.get("accessible_description", "")).startswith(
                    "Artwork unavailable"
                )
                and str(entry.get("source_path", "")).startswith(
                    "/capture-missing/"
                )
                for entry in entries
            )
            and isinstance(visible_card, dict)
            and visible_card.get("contained") is True
            and isinstance(visible_preview, dict)
            and visible_preview.get("contained") is True
            and matrix.get("visible_missing_preview_count") == 1
        ):
            reject("missing-artwork fallback evidence is incomplete, clipped, or unlogged")

    if label == "collection-environment-mechanics":
        mechanics = audit_object("environment_mechanics_visual")
        required_keys = {
            "toolbar",
            "summary_title",
            "summary_selection",
            "edit_appearance",
            "item_title",
            "item_status",
            "effect",
            "mechanics",
        }
        bounds = mechanics.get("required_bounds")
        if not (
            mechanics.get("passed") is True
            and set(mechanics.get("required_keys", ())) == required_keys
            and isinstance(bounds, list)
            and {row.get("key") for row in bounds if isinstance(row, dict)}
            == required_keys
            and all(
                isinstance(row, dict)
                and row.get("visible") is True
                and row.get("contained") is True
                and bool(str(row.get("text", "")).strip())
                for row in bounds
            )
        ):
            reject("environment mechanics content is incomplete or clipped")
        mechanics_row = next(
            (
                row for row in bounds
                if isinstance(row, dict) and row.get("key") == "mechanics"
            ),
            {},
        ) if isinstance(bounds, list) else {}
        mechanics_copy = str(mechanics_row.get("text", ""))
        if not (
            "Available every day" in mechanics_copy
            and "Only one weather can be equipped" in mechanics_copy
            and audit.get("mechanics_always_visible") is True
            and audit.get("compact_environment_actions") is True
        ):
            reject(
                "environment mechanics must stay visible with compact Preview and Unequip actions"
            )

    if label == "collection-loadout-persistence-error":
        rendered_state = audit_object("rendered_state")
        feedback_text = str(rendered_state.get("feedback_text", ""))
        if not (
            str(audit.get("error_copy", "")).startswith(
                "Could not save changes."
            )
            and feedback_text.startswith("Could not save changes.")
            and rendered_state.get("feedback_outside_artwork") is True
            and rendered_state.get("passed") is True
        ):
            reject(
                "loadout persistence feedback must say Could not and remain outside the artwork"
            )

    return problems


def _count_aligned_rgba_pixels(
    payload: bytes | bytearray | memoryview,
    *,
    width: int,
    height: int,
    row_stride: int,
    target: tuple[int, int, int, int] = CONTACT_SHEET_PADDING_RGBA,
) -> int:
    """Count exact RGBA pixels without matching across pixels or row padding."""

    if type(width) is not int or width < 0:
        raise ValueError("RGBA width must be a non-negative integer")
    if type(height) is not int or height < 0:
        raise ValueError("RGBA height must be a non-negative integer")
    if type(row_stride) is not int or row_stride < width * 4:
        raise ValueError("RGBA row stride is smaller than the aligned pixel row")
    if (
        not isinstance(target, tuple)
        or len(target) != 4
        or any(type(channel) is not int or not 0 <= channel <= 255 for channel in target)
    ):
        raise ValueError("RGBA target must contain four byte channels")
    try:
        pixels = memoryview(payload).cast("B")
    except (TypeError, ValueError) as error:
        raise ValueError("RGBA pixel buffer must be contiguous bytes") from error
    expected_size = row_stride * height
    if pixels.nbytes != expected_size:
        raise ValueError(
            f"RGBA pixel buffer must contain exactly {expected_size} bytes, "
            f"found {pixels.nbytes}"
        )

    if width == 0 or height == 0:
        return 0
    aligned = Image.frombytes(
        "RGBA",
        (width, height),
        pixels.tobytes(),
        "raw",
        "RGBA",
        row_stride,
        1,
    )
    difference = ImageChops.difference(
        aligned,
        Image.new("RGBA", aligned.size, target),
    )
    red, green, blue, alpha = difference.split()
    nonmatching = ImageChops.lighter(
        ImageChops.lighter(red, green),
        ImageChops.lighter(blue, alpha),
    )
    return nonmatching.histogram()[0]


def _count_image_rgba_pixels(
    image: Image.Image,
    *,
    target: tuple[int, int, int, int] = CONTACT_SHEET_PADDING_RGBA,
) -> int:
    """Count exact pixels in an already-normalized Pillow RGBA image."""

    if image.mode != "RGBA":
        raise ValueError("pixel audit image must use RGBA channels")
    width, height = image.size
    row_stride = width * 4
    return _count_aligned_rgba_pixels(
        image.tobytes("raw", "RGBA"),
        width=width,
        height=height,
        row_stride=row_stride,
        target=target,
    )


def _unpainted_client_record_issues(
    *,
    label: str,
    record: dict[str, Any],
    audit: dict[str, Any] | None,
    screenshot_path: Path | None,
) -> list[str]:
    """Independently reject sheet-padding cream in raw client pixels."""

    problems: list[str] = []
    sentinel = record.get("unpainted_client_pixel_audit")
    if not isinstance(sentinel, dict):
        return ["unpainted client pixel audit is missing"]
    if audit is None or audit.get("unpainted_client_pixel_audit") != sentinel:
        problems.append("unpainted client pixel audit disagrees with capture audit")
    if screenshot_path is None or not screenshot_path.is_file():
        return [*problems, "unpainted client PNG is unavailable"]
    try:
        with Image.open(screenshot_path) as opened:
            opened.load()
            rgba = opened.convert("RGBA")
            width, height = rgba.size
            scanned_rect = [0, 0, width, height]
            expected_exemptions: list[dict[str, Any]] = []
            if label.startswith("reviewer-"):
                overlay = (
                    audit.get("reviewer_overlay_geometry")
                    if isinstance(audit, dict) else None
                )
                hud = (
                    audit.get("reviewer_hud_geometry")
                    if isinstance(audit, dict) else None
                )
                bounds = (
                    overlay.get("capture_bounds")
                    if isinstance(overlay, dict)
                    and overlay.get("capture_bounds")
                    else overlay.get("overlay_bounds")
                    if isinstance(overlay, dict)
                    and overlay.get("overlay_bounds")
                    else hud.get("capture_bounds")
                    if isinstance(hud, dict)
                    else None
                )
                logical_width = record.get("width")
                logical_height = record.get("height")
                if (
                    isinstance(bounds, list)
                    and len(bounds) == 4
                    and all(type(value) is int for value in bounds)
                    and type(logical_width) is int
                    and logical_width > 0
                    and type(logical_height) is int
                    and logical_height > 0
                ):
                    x, y, region_width, region_height = bounds
                    left = max(0, round(x * width / logical_width))
                    top = max(0, round(y * height / logical_height))
                    right = min(
                        width,
                        round((x + region_width) * width / logical_width),
                    )
                    bottom = min(
                        height,
                        round((y + region_height) * height / logical_height),
                    )
                    scanned_rect = [
                        left,
                        top,
                        max(0, right - left),
                        max(0, bottom - top),
                    ]
                else:
                    scanned_rect = []
            elif label in {
                "starter-deck-browser-home",
                "starter-overview-home",
                "deck-browser-home",
                "overview-home",
                "active-deck-browser-home-after-nurture",
                "active-overview-home-after-nurture",
                "session-summary-after-review",
                "sync-rewards-summary",
                "home-preview-loading",
                "home-preview-error",
                "home-preview-stale",
                "watering-can-deck-browser-plot-1",
                "watering-can-deck-browser-plot-3",
                "watering-can-deck-browser-plot-5",
                "watering-can-overview-plot-2",
                "watering-can-overview-plot-4",
                "watering-can-overview-plot-6",
            }:
                expected_exemptions.append({
                    "kind": "anki-home-host-toolbar",
                    "rect": [0, 0, width, min(height, 96)],
                })
            if len(scanned_rect) == 4 and scanned_rect[2] > 0 and scanned_rect[3] > 0:
                scan_x, scan_y, scan_width, scan_height = scanned_rect
                scanned = rgba.crop((
                    scan_x,
                    scan_y,
                    scan_x + scan_width,
                    scan_y + scan_height,
                ))
                total = _count_image_rgba_pixels(scanned)
            else:
                total = -1
                problems.append("reviewer add-on overlay scan rectangle is invalid")
            raw_exemptions = sentinel.get("host_region_exemptions")
            normalized_exemptions: list[dict[str, Any]] = []
            exempt_count = 0
            if not isinstance(raw_exemptions, list):
                problems.append("host-region cream exemptions must be a list")
            else:
                for row in raw_exemptions:
                    if not isinstance(row, dict):
                        problems.append("host-region cream exemption is malformed")
                        continue
                    normalized_exemptions.append({
                        "kind": row.get("kind"),
                        "rect": row.get("rect"),
                    })
                    rect = row.get("rect")
                    if (
                        isinstance(rect, list)
                        and len(rect) == 4
                        and all(type(value) is int for value in rect)
                    ):
                        x, y, region_width, region_height = rect
                        cropped = rgba.crop((
                            x,
                            y,
                            x + region_width,
                            y + region_height,
                        ))
                        count = _count_image_rgba_pixels(cropped)
                        if row.get("cream_pixel_count") != count:
                            problems.append("host exemption cream pixel count changed")
                        exempt_count += count
                    else:
                        problems.append("host-region cream exemption rectangle is malformed")
            if normalized_exemptions != expected_exemptions:
                problems.append("host-region cream exemptions are not the exact source contract")
            effective = max(0, total - exempt_count) if total >= 0 else -1
            # Match the live guard: ordinary painted surfaces may contain a
            # few isolated pixels that happen to equal the sheet-padding RGB,
            # while a leaked padding field remains orders of magnitude above
            # this allowance. Reviewer overlays stay exact.
            threshold = (
                64
                if expected_exemptions and not label.startswith("reviewer-") else
                0
                if label.startswith("reviewer-") else
                4
            )
            expected_fields = {
                "color_rgb": [216, 209, 190],
                "match": "exact-rgba-opaque",
                "scanned_rect": scanned_rect,
                "total_cream_pixel_count": total,
                "exempt_cream_pixel_count": exempt_count,
                "effective_cream_pixel_count": effective,
                "maximum_effective_cream_pixels": threshold,
                "passed": effective >= 0 and effective <= threshold,
            }
            for field, expected in expected_fields.items():
                if sentinel.get(field) != expected:
                    problems.append(f"unpainted client field {field} does not match pixels")
            if effective < 0 or effective > threshold:
                problems.append("raw capture contains excess contact-sheet cream pixels")
    except (OSError, UnidentifiedImageError, ValueError) as error:
        problems.append(f"could not inspect unpainted client pixels: {error}")
    return list(dict.fromkeys(problems))


def _native_progress_bar_record_issues(
    *,
    label: str,
    record: dict[str, Any],
    audit: dict[str, Any] | None,
) -> list[str]:
    """Bind independent progress validation across record, audit, and fixture."""

    problems: list[str] = []
    evidence = record.get("native_progress_bar_evidence")
    for issue in native_progress_bar_evidence_issue_codes(evidence):
        problems.append(issue)
    if audit is None or audit.get("native_progress_bars") != evidence:
        problems.append("native-progress-audit-record-mismatch")
    fixture = record.get("fixture_validation")
    postcondition = (
        fixture.get("postcondition")
        if isinstance(fixture, dict) else None
    )
    if (
        not isinstance(postcondition, dict)
        or postcondition.get("native_progress_bar_evidence") != evidence
    ):
        problems.append("native-progress-postcondition-record-mismatch")
    acceptance = record.get("capture_acceptance")
    gross_checks = (
        acceptance.get("gross_checks")
        if isinstance(acceptance, dict) else None
    )
    if (
        not isinstance(gross_checks, dict)
        or gross_checks.get("native_progress_bar_evidence") is not True
    ):
        problems.append("native-progress-hard-gate-missing")
    expected_root = f"capture.{label}"
    if (
        isinstance(evidence, dict)
        and evidence.get("root_semantic_id") != expected_root
    ):
        problems.append("native-progress-root-label-mismatch")
    return list(dict.fromkeys(problems))


def _native_layout_telemetry_record_issues(
    *,
    label: str,
    window_family: str,
    record: dict[str, Any],
    audit: dict[str, Any] | None,
    limits: dict[str, float | int],
    button_heights: dict[str, int],
    tabular_labels: frozenset[str],
) -> list[str]:
    """Independently validate shell-owned client, control, and text evidence."""

    problems: list[str] = []
    telemetry = record.get("native_layout_telemetry")
    if not isinstance(telemetry, dict):
        return ["native_layout_telemetry is missing"]
    if audit is None or audit.get("native_layout_telemetry") != telemetry:
        problems.append("native layout telemetry does not match the capture audit")
    if telemetry.get("passed") is not True or telemetry.get("issues") != []:
        problems.append("native layout telemetry did not pass")

    shell_expected = window_family != "AnkiQt"
    applicable = telemetry.get("applicable")
    if type(applicable) is not bool:
        problems.append("native layout applicable must be boolean")
        return problems
    if not shell_expected:
        if applicable:
            problems.append("native layout telemetry is unexpectedly applicable")
        return problems
    if not applicable:
        problems.append("DialogShell capture layout telemetry is not applicable")
        return problems
    if telemetry.get("source") != "DialogShell.capture_layout_telemetry":
        problems.append("native layout telemetry source is invalid")
    if telemetry.get("limits") != limits:
        problems.append("native layout telemetry limits drifted from source")
    if telemetry.get("buttonHeights") != button_heights:
        problems.append("native button height telemetry drifted from source")

    client_width = telemetry.get("clientWidth")
    fill = _strict_number(telemetry.get("clientSurfaceFill"))
    gutter = telemetry.get("clientGutterPx")
    if type(client_width) is not int or client_width <= 0:
        problems.append("native layout client width is invalid")
    elif fill is None or not 0.0 <= fill <= 1.0:
        problems.append("native layout client surface fill is invalid")
    elif (
        type(gutter) is not int
        or gutter != max(0, client_width - round(client_width * fill))
        or gutter > int(limits["maximum_client_gutter_px"])
    ):
        problems.append("native layout client gutter exceeds the compact limit")

    footer_gap = telemetry.get("contentToFooterGap")
    if footer_gap is not None and (
        type(footer_gap) is not int
        or footer_gap < 0
        or footer_gap > int(limits["maximum_content_footer_gap_px"])
    ):
        problems.append("native layout content-to-footer gap exceeds the limit")
    nursery_offset = telemetry.get("nurseryRootOffset")
    if window_family == "NurseryDialog":
        if (
            type(nursery_offset) is not int
            or nursery_offset < 0
            or nursery_offset
            > int(limits["maximum_nursery_root_offset_px"])
        ):
            problems.append("native Nursery root is not top-aligned")
    elif nursery_offset is not None and (
        type(nursery_offset) is not int or nursery_offset < 0
    ):
        problems.append("native layout Nursery offset is invalid")

    action_ratio = _strict_number(telemetry.get("maximumActionWidthRatio"))
    if (
        action_ratio is None
        or not 0.0 <= action_ratio <= 1.0
        or action_ratio > float(limits["maximum_action_width_ratio"])
    ):
        problems.append("native action width ratio exceeds the normal-dialog limit")
    minimum_text = _strict_number(telemetry.get("minimumRenderedTextSize"))
    if minimum_text is None or minimum_text < float(
        limits["minimum_rendered_text_px"]
    ):
        problems.append("native rendered text is below the configured text floor")

    for count_name in (
        "tooltipWidgetCount",
        "elidedWidgetCount",
        "elisionWithoutTooltipCount",
    ):
        value = telemetry.get(count_name)
        if type(value) is not int or value < 0:
            problems.append(f"native layout {count_name} is invalid")
    if telemetry.get("elisionWithoutTooltipCount") != 0:
        problems.append("native elision is missing tooltip evidence")

    rows = telemetry.get("scrollbars")
    owner_count = telemetry.get("overflowOwnerCount")
    window_mode = telemetry.get("windowMode")
    if window_mode not in {"canvas", "workspace", "content"}:
        problems.append("native dialog window mode is invalid")
        window_mode = ""
    content_fit_pending = telemetry.get("contentFitPending")
    if type(content_fit_pending) is not bool or content_fit_pending:
        problems.append("native content-fit telemetry is not settled")
    safety_scroll_active = telemetry.get("safetyScrollActive")
    if type(safety_scroll_active) is not bool:
        problems.append("native safety-scroll telemetry is invalid")
        safety_scroll_active = False

    def valid_bounds(value: Any, *, optional: bool = False) -> bool:
        if value is None:
            return optional
        return bool(
            isinstance(value, dict)
            and set(value) == {"x", "y", "width", "height"}
            and all(type(value.get(key)) is int for key in value)
            and int(value.get("width", 0)) > 0
            and int(value.get("height", 0)) > 0
        )

    if not valid_bounds(telemetry.get("clientBounds")):
        problems.append("native client bounds are invalid")
    if not valid_bounds(
        telemetry.get("bodyBounds"),
        optional=window_mode == "canvas",
    ):
        problems.append("native body bounds are invalid")
    if not valid_bounds(telemetry.get("footerBounds"), optional=True):
        problems.append("native footer bounds are invalid")
    settled_size = telemetry.get("settledSize")
    if (
        not isinstance(settled_size, dict)
        or set(settled_size) != {"width", "height"}
        or type(settled_size.get("width")) is not int
        or type(settled_size.get("height")) is not int
        or settled_size.get("width") != record.get("width")
        or settled_size.get("height") != record.get("height")
    ):
        problems.append("native settled size does not match the captured client")
    if not isinstance(rows, list):
        problems.append("native scrollbar telemetry must be a list")
        rows = []
    if (
        type(owner_count) is not int
        or owner_count < 0
        or owner_count > int(limits["maximum_overflow_owner_count"])
    ):
        problems.append("native overflow owner count is invalid")
    elif window_mode == "canvas" and owner_count != 0:
        problems.append("native canvas must not have an overflow owner")
    elif window_mode == "workspace" and owner_count != 1:
        problems.append("native workspace must have exactly one overflow owner")
    elif window_mode == "content" and (
        (bool(safety_scroll_active) and owner_count != 1)
        or (not bool(safety_scroll_active) and owner_count != 0)
    ):
        problems.append("native content overflow owner disagrees with safety mode")
    if window_mode != "content" and bool(safety_scroll_active):
        problems.append("native safety scroll is active outside content mode")
    if (
        window_mode == "content"
        and bool(safety_scroll_active)
        and record.get("screen_limited") is not True
    ):
        problems.append("native content safety scroll lacks a physical screen limit")
    measured_owners = 0
    for row in rows:
        if not isinstance(row, dict):
            problems.append("native scrollbar record is invalid")
            continue
        minimum = row.get("minimum")
        maximum = row.get("maximum")
        value = row.get("value")
        visible = row.get("visible")
        owner = row.get("overflowOwner")
        if (
            type(minimum) is not int
            or type(maximum) is not int
            or type(value) is not int
            or type(visible) is not bool
            or type(owner) is not bool
            or maximum < minimum
            or not minimum <= value <= maximum
        ):
            problems.append("native scrollbar record is invalid")
            continue
        measured_owners += int(owner)
        if owner and visible != (maximum > minimum):
            problems.append("native scrollbar visibility disagrees with its range")
        if not owner and visible:
            problems.append("native non-owner scrollbar is visible")
    if type(owner_count) is int and measured_owners != owner_count:
        problems.append("native overflow owner record count disagrees")

    button_rows = telemetry.get("buttonRecords")
    if not isinstance(button_rows, list):
        problems.append("native button telemetry must be a list")
        button_rows = []
    for button in button_rows:
        if not isinstance(button, dict):
            problems.append("native button telemetry record is invalid")
            continue
        size_name = button.get("buttonSize")
        expected_height = button_heights.get(size_name)
        text_size = _strict_number(button.get("renderedTextSize"))
        actual_height = button.get("height")
        actual_width = button.get("width")
        visual_size = button.get("visualControlSize")
        expected_outer_height = (
            expected_height
            if type(expected_height) is int else None
        )
        maximum_outer_height = (
            expected_height + 4
            if type(expected_height) is int else None
        )
        outer_allowance = (
            actual_height - visual_size
            if type(actual_height) is int and type(visual_size) is int
            else None
        )
        if (
            expected_height is None
            or button.get("expectedHeight") != expected_height
            or button.get("expectedOuterHeight") != expected_outer_height
            or button.get("maximumOuterHeight") != maximum_outer_height
            or type(actual_height) is not int
            or type(actual_width) is not int
            or type(visual_size) is not int
            or visual_size != expected_height
            or not expected_outer_height <= actual_height <= maximum_outer_height
            or type(outer_allowance) is not int
            or not 0 <= outer_allowance <= 4
            or button.get("outerBorderAllowance") != outer_allowance
            or button.get("passed") is not True
            or (
                bool(str(button.get("text", "")).strip())
                and (
                    text_size is None
                    or text_size < float(limits["minimum_rendered_text_px"])
                )
            )
            or (
                size_name == "icon"
                and (
                    actual_width != actual_height
                    or not expected_outer_height
                    <= actual_width <= maximum_outer_height
                )
            )
        ):
            problems.append("native button geometry or text size is invalid")

    tabular_rows = telemetry.get("tabularNumeralWidgets")
    tabular_count = telemetry.get("tabularNumeralWidgetCount")
    tabular_required = label in tabular_labels
    if (
        not isinstance(tabular_rows, list)
        or type(tabular_count) is not int
        or tabular_count != len(tabular_rows)
        or telemetry.get("tabularNumeralsRequired") is not tabular_required
        or (tabular_required and tabular_count < 1)
    ):
        problems.append("native tabular numeral evidence is incomplete")
    elif any(
        not isinstance(row, dict)
        or not bool(str(row.get("widget", "")).strip())
        or not any(character.isdigit() for character in str(row.get("text", "")))
        for row in tabular_rows
    ):
        problems.append("native tabular numeral record is invalid")
    return list(dict.fromkeys(problems))


def validate_capture_manifest(
    manifest_path: Path,
    *,
    capture_source: Path = DEFAULT_CAPTURE_SOURCE,
) -> dict[str, Any]:
    """Validate one profile-complete manifest and all manifest-owned PNGs."""

    manifest_path = manifest_path.resolve()
    payload = _load_json_object(manifest_path, "capture manifest")
    capture_profile = str(payload.get("capture_profile", ""))
    if capture_profile not in {"representative", "full"}:
        raise CaptureValidationError((
            "capture_profile must be 'representative' or 'full'",
        ))
    contract = load_capture_contract(capture_source, profile=capture_profile)
    renderer_families = load_expected_renderer_families(
        capture_source,
        contract=contract,
    )
    resize_layout_modes = load_expected_resize_layout_modes(capture_source)
    state_evidence_contracts = load_expected_state_evidence_contracts(
        capture_source,
        contract=contract,
    )
    scenario_contracts = load_capture_scenario_contracts(
        capture_source,
        contract=contract,
    )
    dialog_scroll_coverage = load_dialog_scroll_capture_coverage(
        capture_source,
        contract=contract,
    )
    (
        layout_limits,
        button_heights,
        tabular_labels,
    ) = load_capture_layout_contract(capture_source)
    dialog_scroll_by_label = {
        label: (surface, semantic)
        for surface, labels in dialog_scroll_coverage.items()
        for label, semantic in labels.items()
    }
    session_dir = manifest_path.parent.resolve()
    expected_labels = contract.labels
    expected_count = len(expected_labels)
    issues: list[str] = []
    advisories: list[str] = []

    if payload.get("capture_contract_version") != contract.version:
        issues.append(
            "capture_contract_version does not match the repository contract "
            f"({payload.get('capture_contract_version')!r} != {contract.version})"
        )
    if payload.get("capture_contract_digest") != contract.digest:
        issues.append("capture_contract_digest does not match the selected profile")
    if payload.get("scenario_schema_version") != contract.scenario_schema_version:
        issues.append("scenario_schema_version does not match the source contract")
    expected_scenario_digest = _canonical_digest({
        label: scenario_contracts[label]["digest"]
        for label in expected_labels
    })
    if payload.get("scenario_contract_digest") != expected_scenario_digest:
        issues.append("scenario_contract_digest does not match source scenarios")
    raw_scale = payload.get("requested_scale_factor")
    try:
        scale = float(raw_scale) if not isinstance(raw_scale, bool) else math.nan
    except (TypeError, ValueError):
        scale = math.nan
    if not math.isfinite(scale) or not math.isclose(scale, CAPTURE_SCALE_FACTOR):
        issues.append("requested_scale_factor must be numeric-equivalent to 1.0")
    if _manifest_groups(payload) != contract.groups:
        issues.append("capture_groups does not exactly match source order and labels")
    if payload.get("expected_faces") != list(expected_labels):
        issues.append("expected_faces does not exactly match source order and labels")
    if payload.get("expected_count") != expected_count:
        issues.append(
            f"expected_count must be {expected_count}, found {payload.get('expected_count')!r}"
        )
    capture_scope = payload.get("capture_scope")
    if capture_scope not in {"full", "assembled"}:
        issues.append("capture_scope must be 'full' or 'assembled' for release evidence")
    if payload.get("requested_faces") != list(expected_labels):
        issues.append("requested_faces must contain the complete ordered release contract")
    captured_faces = payload.get("captured_faces")
    reused_faces = payload.get("reused_faces")
    if not isinstance(captured_faces, list) or not isinstance(reused_faces, list):
        issues.append("captured_faces and reused_faces must be lists")
        captured_faces = []
        reused_faces = []
    else:
        captured_faces = [str(value) for value in captured_faces]
        reused_faces = [str(value) for value in reused_faces]
        if len(captured_faces) != len(set(captured_faces)):
            issues.append("captured_faces contains duplicates")
        if len(reused_faces) != len(set(reused_faces)):
            issues.append("reused_faces contains duplicates")
        if set(captured_faces) & set(reused_faces):
            issues.append("captured_faces and reused_faces overlap")
        if set(captured_faces) | set(reused_faces) != set(expected_labels):
            issues.append("captured_faces and reused_faces do not cover the release contract")
        if captured_faces != [label for label in expected_labels if label in captured_faces]:
            issues.append("captured_faces is not in canonical order")
        if reused_faces != [label for label in expected_labels if label in reused_faces]:
            issues.append("reused_faces is not in canonical order")
    invalidated_faces = payload.get("invalidated_faces")
    if not isinstance(invalidated_faces, list) or any(
        str(value) not in expected_labels for value in invalidated_faces
    ):
        issues.append("invalidated_faces must contain only contract labels")
    calibration = payload.get("capture_calibration")
    if not isinstance(calibration, dict) or calibration.get("passed") is not True:
        issues.append("capture calibration did not pass")
    if payload.get("scope_complete") is not True:
        issues.append("scope_complete is not true")
    sha_pattern = re.compile(r"[0-9a-f]{64}")
    production_package_sha256 = payload.get("production_package_sha256")
    capture_environment_digest = payload.get("capture_environment_digest")
    expected_evidence_schema_digest = _canonical_digest({
        "validator-source": _file_sha256(Path(__file__).resolve()),
    })
    if payload.get("evidence_schema_digest") != expected_evidence_schema_digest:
        issues.append("evidence_schema_digest does not match the current validator")
    if (
        not isinstance(production_package_sha256, str)
        or sha_pattern.fullmatch(production_package_sha256) is None
    ):
        issues.append("production_package_sha256 is invalid")
    if (
        not isinstance(capture_environment_digest, str)
        or sha_pattern.fullmatch(capture_environment_digest) is None
    ):
        issues.append("capture_environment_digest is invalid")
    render_inputs = payload.get("render_inputs")
    render_surfaces: dict[str, Any] = {}
    if not isinstance(render_inputs, dict):
        issues.append("render_inputs must be an object")
    else:
        if render_inputs.get("capture_profile") != capture_profile:
            issues.append("render_inputs capture profile does not match the manifest")
        if render_inputs.get("capture_contract_digest") != contract.digest:
            issues.append("render_inputs capture contract digest does not match")
        if render_inputs.get("scenario_contract_digest") != expected_scenario_digest:
            issues.append("render_inputs scenario contract digest does not match")
        if render_inputs.get("evidence_schema_digest") != expected_evidence_schema_digest:
            issues.append("render_inputs evidence schema digest does not match")
        if render_inputs.get("environment_digest") != capture_environment_digest:
            issues.append("render_inputs environment digest does not match the manifest")
        if render_inputs.get("production_archive_sha256") != production_package_sha256:
            issues.append("render_inputs production archive hash does not match the manifest")
        raw_render_surfaces = render_inputs.get("surfaces")
        if not isinstance(raw_render_surfaces, dict):
            issues.append("render_inputs surfaces must be an object")
        else:
            render_surfaces = raw_render_surfaces
            if set(render_surfaces) != set(expected_labels):
                issues.append("render_inputs surfaces do not match the release contract")
    if payload.get("foreground_policy") != "required-only":
        issues.append("foreground_policy must be 'required-only'")
    foreground_requests = payload.get("foreground_requests")
    if not isinstance(foreground_requests, list) or len(foreground_requests) > 2:
        issues.append("foreground_requests must be a list containing at most two requests")
    if payload.get("complete") is not True:
        issues.append("capture manifest is not marked complete")
    if payload.get("fixture_validations_complete") is not True:
        issues.append("fixture_validations_complete is not true")

    completion_path = session_dir / "capture-complete.json"
    completion = _load_json_object(completion_path, "capture completion")
    if completion.get("manifest_sha256") != _file_sha256(manifest_path):
        issues.append("capture completion manifest hash does not match")
    referenced_manifest = _resolved_evidence_path(
        completion.get("manifest"),
        session_dir,
    )
    if referenced_manifest != manifest_path:
        issues.append("capture completion references a different manifest")
    if completion.get("scope_complete") is not True or completion.get("exit_code") != 0:
        issues.append("capture completion does not report a clean successful scope")

    lineage_manifest_hashes: set[str] = set()
    source_manifests = payload.get("source_manifests", [])
    if capture_scope == "assembled":
        if not isinstance(source_manifests, list) or not source_manifests:
            issues.append("assembled evidence must include a local lineage closure")
            source_manifests = []
        for row in source_manifests:
            if not isinstance(row, dict):
                issues.append("lineage manifest entry must be an object")
                continue
            digest = row.get("sha256")
            path = _resolved_evidence_path(row.get("path"), session_dir)
            if not isinstance(digest, str) or sha_pattern.fullmatch(digest) is None:
                issues.append("lineage manifest SHA-256 is invalid")
                continue
            if path is None or not _inside_directory(path, session_dir / "lineage"):
                issues.append("lineage manifest is outside the local lineage directory")
                continue
            if path.name != f"manifest-{digest}.json" or not path.is_file():
                issues.append("lineage manifest filename does not match its SHA-256")
                continue
            if _file_sha256(path) != digest:
                issues.append("lineage manifest content hash does not match")
                continue
            lineage_manifest_hashes.add(digest)
        if len(lineage_manifest_hashes) != len(source_manifests):
            issues.append("lineage manifest closure contains duplicates or invalid entries")
        # Copied snapshots retain their original bytes. Resolve every nested
        # reference by SHA through the final local index, never via an archived
        # absolute path, so the assembled directory is relocatable.
        for digest in sorted(lineage_manifest_hashes):
            snapshot_path = session_dir / "lineage" / f"manifest-{digest}.json"
            try:
                snapshot = _load_json_object(snapshot_path, "lineage manifest")
            except CaptureValidationError as error:
                issues.extend(error.issues)
                continue
            for nested in snapshot.get("source_manifests", ()):
                if not isinstance(nested, dict) or nested.get("sha256") not in lineage_manifest_hashes:
                    issues.append(
                        f"lineage manifest {digest} references an unclosed nested SHA"
                    )

    failures = payload.get("failures")
    if not isinstance(failures, list):
        issues.append("failures must be a list")
    elif failures:
        issues.append(f"capture manifest reports {len(failures)} failure(s)")
    warnings = payload.get("text_layout_warnings")
    if not isinstance(warnings, list):
        issues.append("text_layout_warnings must be a list")
    elif warnings:
        advisories.append(
            f"capture manifest reports {len(warnings)} review warning(s)"
        )
    capture_advisories = payload.get("capture_advisories", [])
    if not isinstance(capture_advisories, list):
        issues.append("capture_advisories must be a list")
    else:
        for advisory in capture_advisories:
            if not isinstance(advisory, dict):
                advisories.append("capture manifest contains a malformed advisory")
                continue
            label = str(advisory.get("label", "capture") or "capture")
            reason = str(advisory.get("reason", "review required"))
            advisories.append(f"{label}: {reason}")
    _validate_memory_probe(
        payload,
        issues,
        required=(capture_profile == "full" and contract.version < 25),
    )
    run_level_evidence = payload.get("run_level_evidence")
    if not isinstance(run_level_evidence, dict):
        issues.append("run_level_evidence must be an object")
    else:
        shutdown = run_level_evidence.get("clean_shutdown")
        if not (
            isinstance(shutdown, dict)
            and shutdown.get("required") is True
            and shutdown.get("passed") is True
            and shutdown.get("status") == "passed"
            and shutdown.get("capture_environment_digest")
            == capture_environment_digest
            and shutdown.get("run_level_digest")
            == (
                render_inputs.get("run_level_digest")
                if isinstance(render_inputs, dict) else None
            )
        ):
            issues.append("run-level clean shutdown evidence did not pass")
        memory = run_level_evidence.get("dialog_memory_probe")
        if capture_profile == "full" and contract.version < 25 and not (
            isinstance(memory, dict)
            and memory.get("required") is True
            and memory.get("passed") is True
            and memory.get("run_level_digest")
            == (
                render_inputs.get("run_level_digest")
                if isinstance(render_inputs, dict) else None
            )
            and memory.get("result") == payload.get("dialog_memory_probe")
        ):
            issues.append("run-level full memory evidence did not pass")
        if capture_scope == "assembled":
            run_lineage = run_level_evidence.get("lineage")
            if (
                not isinstance(run_lineage, dict)
                or run_lineage.get("source_manifest_sha256")
                not in lineage_manifest_hashes
            ):
                issues.append("run-level evidence is outside the local lineage closure")

    raw_screenshots = payload.get("screenshots")
    if not isinstance(raw_screenshots, list):
        raw_screenshots = []
        issues.append("screenshots must be a list")
    if len(raw_screenshots) != expected_count:
        issues.append(
            f"screenshots must contain {expected_count} paths, found {len(raw_screenshots)}"
        )

    records = payload.get("captures")
    if not isinstance(records, list):
        records = []
        issues.append("captures must be a list")
    if len(records) != expected_count:
        issues.append(
            f"captures must contain {expected_count} records, found {len(records)}"
        )

    screenshot_paths: list[Path | None] = [
        _resolved_evidence_path(raw_path, session_dir)
        for raw_path in raw_screenshots
    ]
    valid_manifest_pngs: set[Path] = set()
    visual_labels: dict[str, list[str]] = {}
    record_displays: list[str] = []
    record_geometry: dict[str, tuple[int, int, float, str]] = {}
    record_audits: dict[str, dict[str, Any]] = {}
    record_scroll_audits: dict[str, dict[str, Any]] = {}
    filename_width = max(2, len(str(expected_count)))
    for index, label in enumerate(expected_labels, start=1):
        state_contract = state_evidence_contracts[label]
        scenario_contract = scenario_contracts[label]
        expected_state_profile = state_contract["profile"]
        expected_name = f"{index:0{filename_width}d}-{label}.png"
        screenshot_path = screenshot_paths[index - 1] if index <= len(screenshot_paths) else None
        png_evidence: PngEvidence | None = None
        if screenshot_path is None:
            issues.append(f"capture {index:03d} {label}: screenshot path is missing or invalid")
        else:
            if not _inside_directory(screenshot_path, session_dir):
                issues.append(
                    f"capture {index:03d} {label}: screenshot is outside the session directory"
                )
            if screenshot_path.name != expected_name:
                issues.append(
                    f"capture {index:03d} {label}: screenshot filename must be {expected_name}"
                )
            png_evidence = _read_png(screenshot_path)
            if png_evidence is None:
                issues.append(
                    f"capture {index:03d} {label}: screenshot is missing or not a valid PNG"
                )
            else:
                valid_manifest_pngs.add(screenshot_path)
                visual_labels.setdefault(png_evidence.visual_digest, []).append(label)
                if contract.version >= 26:
                    issues.extend(
                        f"capture {index:03d} {label}: {issue}"
                        for issue in _raw_scenario_metadata_issues(
                            screenshot_path,
                            scenario_contract,
                        )
                    )
                if (
                    png_evidence.sampled_color_count < 4
                    or png_evidence.dominant_sample_ratio > 0.985
                ):
                    issues.append(
                        f"capture {index:03d} {label}: screenshot lacks visual content "
                        f"({png_evidence.sampled_color_count} sampled colors; dominant "
                        f"ratio {png_evidence.dominant_sample_ratio:.4f})"
                    )

        if index > len(records):
            continue
        record = records[index - 1]
        if not isinstance(record, dict):
            issues.append(f"capture {index:03d} {label}: record must be an object")
            continue
        if type(record.get("capture_id")) is not int or record.get("capture_id") != index:
            issues.append(f"capture {index:03d} {label}: capture_id must be {index}")
        if record.get("label") != label:
            issues.append(f"capture {index:03d} {label}: record label is out of contract order")
        for identity_field in ("scenario_id", "fixture_id", "scenario_step"):
            if record.get(identity_field) != scenario_contract[identity_field]:
                issues.append(
                    f"capture {index:03d} {label}: {identity_field} does not match "
                    "the scenario contract"
                )
        record_path = _resolved_evidence_path(record.get("path"), session_dir)
        if record_path != screenshot_path:
            issues.append(f"capture {index:03d} {label}: record path does not match screenshots")
        if screenshot_path is not None and screenshot_path.is_file():
            if record.get("png_sha256") != _file_sha256(screenshot_path):
                issues.append(f"capture {index:03d} {label}: PNG SHA-256 does not match")
        evidence_status = record.get("evidence_status")
        expected_status = "reused" if label in reused_faces else "captured"
        if evidence_status != expected_status:
            issues.append(
                f"capture {index:03d} {label}: evidence_status must be {expected_status!r}"
            )
        surface_inputs = render_surfaces.get(label)
        if not isinstance(surface_inputs, dict):
            issues.append(f"capture {index:03d} {label}: render inputs are missing")
        else:
            for identity_field in ("scenario_id", "fixture_id", "scenario_step"):
                if surface_inputs.get(identity_field) != scenario_contract[
                    identity_field
                ]:
                    issues.append(
                        f"capture {index:03d} {label}: render-input {identity_field} "
                        "does not match the scenario contract"
                    )
            if record.get("render_input_digest") != surface_inputs.get("digest"):
                issues.append(f"capture {index:03d} {label}: render-input digest does not match")
            if record.get("render_input_count") != surface_inputs.get("input_count"):
                issues.append(f"capture {index:03d} {label}: render-input count does not match")
            if record.get("capture_environment_digest") != surface_inputs.get(
                "environment_digest"
            ):
                issues.append(
                    f"capture {index:03d} {label}: capture environment digest does not match"
                )
            if record.get("scenario_identity_digest") != scenario_contract["digest"]:
                issues.append(
                    f"capture {index:03d} {label}: scenario identity digest does not match"
                )
            if record.get("scenario_identity_digest") != surface_inputs.get(
                "scenario_identity_digest"
            ):
                issues.append(
                    f"capture {index:03d} {label}: scenario identity differs from render inputs"
                )
            if record.get("surface_contract_digest") != surface_inputs.get(
                "surface_contract_digest"
            ):
                issues.append(
                    f"capture {index:03d} {label}: surface contract digest does not match"
                )
            if record.get("evidence_schema_digest") != expected_evidence_schema_digest:
                issues.append(
                    f"capture {index:03d} {label}: evidence schema digest does not match"
                )
        if record.get("scenario_checkpoint") != scenario_contract["checkpoint"]:
            advisories.append(
                f"capture {index:03d} {label}: scenario checkpoint does not match"
            )
        if record.get("scenario_capture_prerequisites") != scenario_contract[
            "capture_prerequisites"
        ]:
            advisories.append(
                f"capture {index:03d} {label}: capture prerequisites do not match"
            )
        if record.get("scenario_internal_setups") != scenario_contract[
            "internal_setups"
        ]:
            advisories.append(
                f"capture {index:03d} {label}: internal setup closure does not match"
            )
        lineage = record.get("lineage")
        if not isinstance(lineage, dict):
            issues.append(f"capture {index:03d} {label}: lineage is missing")
        else:
            if lineage.get("evidence_status") != evidence_status:
                issues.append(f"capture {index:03d} {label}: lineage evidence status differs")
            if not isinstance(lineage.get("source_run_id"), str) or not str(
                lineage.get("source_run_id", "")
            ).strip():
                issues.append(f"capture {index:03d} {label}: lineage source run is missing")
            source_package = lineage.get("source_package_sha256")
            if not isinstance(source_package, str) or sha_pattern.fullmatch(source_package) is None:
                issues.append(f"capture {index:03d} {label}: lineage package hash is invalid")
            if evidence_status == "reused":
                for field in ("source_manifest_sha256", "source_record_sha256"):
                    value = lineage.get(field)
                    if not isinstance(value, str) or sha_pattern.fullmatch(value) is None:
                        issues.append(
                            f"capture {index:03d} {label}: reused lineage {field} is invalid"
                        )
            if capture_scope == "assembled":
                source_manifest_digest = lineage.get("source_manifest_sha256")
                if source_manifest_digest not in lineage_manifest_hashes:
                    issues.append(
                        f"capture {index:03d} {label}: lineage source is outside the local closure"
                    )
                source_record_digest = lineage.get("source_record_sha256")
                if (
                    not isinstance(source_record_digest, str)
                    or sha_pattern.fullmatch(source_record_digest) is None
                ):
                    issues.append(
                        f"capture {index:03d} {label}: source record digest is invalid"
                    )
        if record.get("stable") is not True:
            advisories.append(
                f"capture {index:03d} {label}: surface stability was not proven"
            )
        stable_frames = record.get("stable_frame_count")
        if type(stable_frames) is not int or stable_frames < 2:
            advisories.append(
                f"capture {index:03d} {label}: stable_frame_count is below two"
            )
        for timing_field in (
            "semantic_ready_ms",
            "stable_ms",
            "capture_ms",
            "audit_ms",
            "cleanup_ms",
        ):
            timing = _strict_number(record.get(timing_field))
            if timing is None or timing < 0:
                issues.append(
                    f"capture {index:03d} {label}: {timing_field} is invalid"
                )
        capture_method = record.get("capture_method")
        if not isinstance(capture_method, str) or not capture_method.strip():
            issues.append(f"capture {index:03d} {label}: capture_method is missing")

        width = record.get("width")
        height = record.get("height")
        logical_size: tuple[int, int] | None = None
        if (
            type(width) is not int
            or type(height) is not int
            or width < MIN_LOGICAL_CAPTURE_DIMENSION
            or height < MIN_LOGICAL_CAPTURE_DIMENSION
        ):
            issues.append(
                f"capture {index:03d} {label}: logical width and height must be integers "
                f"of at least {MIN_LOGICAL_CAPTURE_DIMENSION}px"
            )
        else:
            logical_size = width, height
        actual_size = _strict_size(
            record.get("actual_client_size"),
            minimum=MIN_LOGICAL_CAPTURE_DIMENSION,
        )
        if logical_size is None or actual_size != logical_size:
            issues.append(
                f"capture {index:03d} {label}: actual_client_size must match width and height"
            )
        requested_size = _strict_size(
            record.get("requested_client_size"),
            minimum=MIN_LOGICAL_CAPTURE_DIMENSION,
        )
        declared_size = _strict_size(
            record.get("declared_client_size"),
            minimum=MIN_LOGICAL_CAPTURE_DIMENSION,
        )
        if requested_size is None:
            issues.append(
                f"capture {index:03d} {label}: requested_client_size is invalid"
            )
        if declared_size is None:
            issues.append(f"capture {index:03d} {label}: declared_client_size is invalid")
        if label in resize_layout_modes:
            expected_declared_size = tuple(
                expected_state_profile["declared_client_size"]
            )
            if (
                requested_size != expected_declared_size
                or declared_size != expected_declared_size
            ):
                issues.append(
                    f"capture {index:03d} {label}: resize requested and declared sizes "
                    f"must match source profile {list(expected_declared_size)!r}"
                )
        elif (
            requested_size is None
            or declared_size is None
            or actual_size is None
            or requested_size != actual_size
            or declared_size != actual_size
        ):
            issues.append(
                f"capture {index:03d} {label}: canonical requested, declared, and actual sizes disagree"
            )
        frame_size = _strict_size(record.get("frame_size"), minimum=MIN_LOGICAL_CAPTURE_DIMENSION)
        if (
            frame_size is None
            or logical_size is None
            or frame_size[0] < logical_size[0]
            or frame_size[1] < logical_size[1]
        ):
            issues.append(f"capture {index:03d} {label}: frame_size is invalid")
        dpr = _strict_number(record.get("device_pixel_ratio"))
        if dpr is None or dpr < 1.0 or dpr > 8.0:
            issues.append(f"capture {index:03d} {label}: device_pixel_ratio is invalid")
        elif logical_size is not None and png_evidence is not None:
            expected_physical = (
                round(logical_size[0] * dpr),
                round(logical_size[1] * dpr),
            )
            if (
                abs(png_evidence.width - expected_physical[0]) > 1
                or abs(png_evidence.height - expected_physical[1]) > 1
            ):
                issues.append(
                    f"capture {index:03d} {label}: PNG dimensions "
                    f"{png_evidence.width}x{png_evidence.height} do not match logical "
                    f"size and DPR ({expected_physical[0]}x{expected_physical[1]})"
                )
        display = record.get("capture_display")
        if display not in {"primary", "secondary"}:
            issues.append(f"capture {index:03d} {label}: capture_display is invalid")
        else:
            record_displays.append(display)
        layout_mode = record.get("layout_mode")
        if not isinstance(layout_mode, str) or not layout_mode.strip():
            issues.append(f"capture {index:03d} {label}: layout_mode is missing")
            layout_mode = ""
        transition_path = record.get("transition_path")
        expected_transition = (
            expected_state_profile["transition_path"]
            if label in resize_layout_modes
            else "canonical-open"
        )
        if transition_path != expected_transition:
            advisories.append(
                f"capture {index:03d} {label}: transition_path must be "
                f"{expected_transition!r}"
            )
        for timing_name in ("ready_to_capture_ms", "capture_duration_ms"):
            timing = _strict_number(record.get(timing_name))
            if timing is None or timing < 0:
                issues.append(
                    f"capture {index:03d} {label}: {timing_name} must be finite and nonnegative"
                )
        geometry_flags: dict[str, bool] = {}
        for flag_name in ("screen_limited", "constraint_limited", "native_normalized"):
            flag_value = record.get(flag_name)
            if type(flag_value) is not bool:
                issues.append(f"capture {index:03d} {label}: {flag_name} must be boolean")
            else:
                geometry_flags[flag_name] = flag_value
        normalization_reason = record.get("normalization_reason")
        if not isinstance(normalization_reason, str):
            issues.append(
                f"capture {index:03d} {label}: normalization_reason must be a string"
            )
            normalization_reason = ""
        if _strict_size(record.get("frame_overhead"), minimum=0) is None:
            issues.append(f"capture {index:03d} {label}: frame_overhead is invalid")
        exact_size_reached = record.get("exact_size_reached")
        geometry_drift_accepted = record.get("geometry_drift_accepted")
        if type(exact_size_reached) is not bool:
            issues.append(f"capture {index:03d} {label}: exact_size_reached must be boolean")
        if type(geometry_drift_accepted) is not bool:
            issues.append(
                f"capture {index:03d} {label}: geometry_drift_accepted must be boolean"
            )
        geometry_acceptance = record.get("geometry_acceptance")
        expected_geometry_acceptance: dict[str, Any] | None = None
        if label in resize_layout_modes:
            if not isinstance(geometry_acceptance, dict) or not geometry_acceptance:
                issues.append(
                    f"capture {index:03d} {label}: resize geometry_acceptance is missing"
                )
            elif (
                declared_size is not None
                and actual_size is not None
                and len(geometry_flags) == 3
            ):
                minimum_size = _strict_size(
                    geometry_acceptance.get("minimum_client_size"),
                    minimum=1,
                )
                maximum_size = _strict_size(
                    geometry_acceptance.get("maximum_client_size"),
                    minimum=1,
                )
                if minimum_size is None or maximum_size is None:
                    issues.append(
                        f"capture {index:03d} {label}: geometry acceptance bounds are invalid"
                    )
                else:
                    expected_geometry_acceptance = expected_resize_geometry_acceptance(
                        label=label,
                        declared_size=declared_size,
                        actual_size=actual_size,
                        minimum_size=minimum_size,
                        maximum_size=maximum_size,
                        screen_limited=geometry_flags["screen_limited"],
                        constraint_limited=geometry_flags["constraint_limited"],
                        native_normalized=geometry_flags["native_normalized"],
                        normalization_reason=normalization_reason,
                    )
                    if geometry_acceptance != expected_geometry_acceptance:
                        issues.append(
                            f"capture {index:03d} {label}: geometry_acceptance does not "
                            "match the bounded source contract"
                        )
                    if expected_geometry_acceptance.get("accepted") is not True:
                        issues.append(
                            f"capture {index:03d} {label}: resize geometry drift is unexplained or unsafe"
                        )
                    expected_exact = bool(expected_geometry_acceptance["exact"])
                    if exact_size_reached is not expected_exact:
                        issues.append(
                            f"capture {index:03d} {label}: exact_size_reached disagrees with geometry"
                        )
                    if geometry_drift_accepted is not (not expected_exact):
                        issues.append(
                            f"capture {index:03d} {label}: geometry_drift_accepted disagrees with geometry"
                        )
        elif geometry_acceptance != {}:
            issues.append(
                f"capture {index:03d} {label}: canonical capture must not report resize geometry acceptance"
            )
        elif exact_size_reached is not True or geometry_drift_accepted is not False:
            issues.append(
                f"capture {index:03d} {label}: canonical capture geometry flags are inconsistent"
            )

        for warning_field in ("text_layout_warnings", "geometry_layout_warnings"):
            record_warnings = record.get(warning_field)
            if not isinstance(record_warnings, list):
                issues.append(f"capture {index:03d} {label}: {warning_field} must be a list")
            elif record_warnings:
                advisories.append(
                    f"capture {index:03d} {label}: {warning_field} is not empty"
                )

        scroll_audit = record.get("dialog_scroll_audit")
        if not isinstance(scroll_audit, dict):
            issues.append(
                f"capture {index:03d} {label}: dialog_scroll_audit must be an object"
            )
        else:
            record_scroll_audits[label] = scroll_audit
            strict_no_scroll = scroll_audit.get("require_no_scroll") is True
            scroll_findings = (
                issues
                if contract.version >= 26 or strict_no_scroll
                else advisories
            )
            if type(scroll_audit.get("applicable")) is not bool:
                issues.append(
                    f"capture {index:03d} {label}: dialog scroll applicable must be boolean"
                )
            if scroll_audit.get("passed") is not True:
                scroll_findings.append(
                    f"capture {index:03d} {label}: dialog scroll audit did not pass"
                )
            if scroll_audit.get("issues") != []:
                scroll_findings.append(
                    f"capture {index:03d} {label}: dialog scroll issues must be empty"
                )
            expected_scroll = dialog_scroll_by_label.get(label)
            if expected_scroll is not None:
                surface, semantic = expected_scroll
                for issue in dialog_scroll_audit_issue_codes(
                    scroll_audit,
                    expected_surface=surface,
                    expected_page_semantic=semantic,
                ):
                    scroll_findings.append(
                        f"capture {index:03d} {label}: dialog scroll {issue}"
                    )
            elif scroll_audit.get("applicable") is True:
                for issue in dialog_scroll_audit_issue_codes(scroll_audit):
                    scroll_findings.append(
                        f"capture {index:03d} {label}: dialog scroll {issue}"
                    )

        fixture_source = record.get("fixture_source")
        if (
            not isinstance(fixture_source, str)
            or not fixture_source.startswith("ordered-step-")
        ):
            issues.append(f"capture {index:03d} {label}: fixture_source is missing")
            fixture_source = ""
        if contract.version >= 25:
            acceptance = record.get("capture_acceptance")
            if not isinstance(acceptance, dict):
                issues.append(
                    f"capture {index:03d} {label}: capture_acceptance is missing"
                )
            else:
                gross_checks = acceptance.get("gross_checks")
                expected_acceptance_policy = (
                    V26_CAPTURE_ACCEPTANCE_POLICY
                    if contract.version >= 26 else
                    LEGACY_CAPTURE_ACCEPTANCE_POLICY
                )
                if acceptance.get("policy") != expected_acceptance_policy:
                    issues.append(
                        f"capture {index:03d} {label}: capture acceptance policy is invalid"
                    )
                if (
                    not isinstance(gross_checks, dict)
                    or not gross_checks
                    or any(value is not True for value in gross_checks.values())
                    or (
                        contract.version < 26
                        and acceptance.get("passed") is not True
                    )
                ):
                    issues.append(
                        f"capture {index:03d} {label}: gross capture acceptance did not pass"
                    )
                if (
                    contract.version >= 26
                    and acceptance.get("gross_passed") is not True
                ):
                    issues.append(
                        f"capture {index:03d} {label}: gross capture result did not pass"
                    )
                if (
                    contract.version >= 26
                    and acceptance.get("semantic_audit_passed") is not True
                ):
                    issues.append(
                        f"capture {index:03d} {label}: semantic capture acceptance did not pass"
                    )
                if (
                    contract.version >= 26
                    and acceptance.get("passed") is not True
                ):
                    issues.append(
                        f"capture {index:03d} {label}: capture acceptance did not pass"
                    )
        if contract.version >= 26:
            for semantic_issue in v26_capture_semantic_gate_issue_codes(record):
                issues.append(
                    f"capture {index:03d} {label}: {semantic_issue}"
                )
        fixture = record.get("fixture_validation")
        if not isinstance(fixture, dict):
            issues.append(f"capture {index:03d} {label}: fixture_validation is missing")
            continue
        if fixture.get("passed") is not True:
            issues.append(f"capture {index:03d} {label}: fixture validation did not pass")
        if (
            contract.version >= 26
            and fixture.get("semantic_audit_passed") is not True
        ):
            issues.append(
                f"capture {index:03d} {label}: fixture semantic audit did not pass"
            )
        if type(fixture.get("capture_id")) is not int or fixture.get("capture_id") != index:
            issues.append(f"capture {index:03d} {label}: fixture capture_id must be {index}")
        if fixture.get("surface_id") != label:
            issues.append(f"capture {index:03d} {label}: fixture surface_id does not match label")
        for identity_field in ("scenario_id", "fixture_id", "scenario_step"):
            if fixture.get(identity_field) != scenario_contract[identity_field]:
                issues.append(
                    f"capture {index:03d} {label}: fixture {identity_field} does not "
                    "match the scenario contract"
                )
        if fixture.get("fixture_source") != fixture_source:
            issues.append(f"capture {index:03d} {label}: fixture sources disagree")
        if fixture.get("state_profile") != label:
            advisories.append(
                f"capture {index:03d} {label}: state_profile must match the capture label"
            )
        postcondition_findings = (
            issues if contract.version >= 26 else advisories
        )
        postcondition = fixture.get("postcondition")
        if not isinstance(postcondition, dict):
            postcondition_findings.append(
                f"capture {index:03d} {label}: postcondition must be an object"
            )
        else:
            if postcondition.get("profile_id") != label:
                postcondition_findings.append(
                    f"capture {index:03d} {label}: postcondition profile_id must match label"
                )
            kind = postcondition.get("kind")
            if kind != state_contract["kind"]:
                postcondition_findings.append(
                    f"capture {index:03d} {label}: postcondition kind must be "
                    f"{state_contract['kind']!r}"
                )
            facts = postcondition.get("facts")
            if not isinstance(facts, dict) or not facts:
                postcondition_findings.append(
                    f"capture {index:03d} {label}: postcondition facts must be nonempty"
                )
            elif set(facts) != set(state_contract["required_facts"]):
                missing_facts = sorted(
                    set(state_contract["required_facts"]) - set(facts)
                )
                extra_facts = sorted(
                    set(facts) - set(state_contract["required_facts"])
                )
                postcondition_findings.append(
                    f"capture {index:03d} {label}: postcondition fact schema mismatch "
                    f"(missing={missing_facts!r}, extra={extra_facts!r})"
                )
            if isinstance(facts, dict):
                for fact_name, expected_value in state_contract[
                    "expected_fact_values"
                ].items():
                    if facts.get(fact_name) != expected_value:
                        postcondition_findings.append(
                            f"capture {index:03d} {label}: postcondition fact "
                            f"{fact_name!r} must be {expected_value!r}"
                        )
                if (
                    state_contract["fact_constraints"].get(
                        "keyboard_focus_fixture_cleared"
                    ) == "focus-cleared-object"
                ):
                    cleared = facts.get("keyboard_focus_fixture_cleared")
                    if (
                        not isinstance(cleared, dict)
                        or set(cleared) != {
                            "focus_owner",
                            "progress_button_has_focus",
                        }
                        or not isinstance(cleared.get("focus_owner"), str)
                        or cleared.get("progress_button_has_focus") is not False
                    ):
                        postcondition_findings.append(
                            f"capture {index:03d} {label}: postcondition fact "
                            "'keyboard_focus_fixture_cleared' must prove the "
                            "Progress button does not own focus"
                        )
            if label in resize_layout_modes:
                expected_kind = str(expected_state_profile.get("kind", ""))
                if kind != expected_kind:
                    postcondition_findings.append(
                        f"capture {index:03d} {label}: resize postcondition kind must be "
                        f"{expected_kind}"
                    )
                if (
                    not isinstance(facts, dict)
                    or facts.get("layout_mode") != resize_layout_modes[label]
                ):
                    postcondition_findings.append(
                        f"capture {index:03d} {label}: resize layout_mode fact must be "
                        f"{resize_layout_modes[label]!r}"
                    )
                if layout_mode != resize_layout_modes[label]:
                    advisories.append(
                        f"capture {index:03d} {label}: recorded layout_mode must be "
                        f"{resize_layout_modes[label]!r}"
                    )
                if (
                    not isinstance(facts, dict)
                    or facts.get("geometry_acceptance") != geometry_acceptance
                ):
                    postcondition_findings.append(
                        f"capture {index:03d} {label}: postcondition geometry acceptance "
                        "does not match the record"
                    )
            if postcondition.get("issues") != []:
                postcondition_findings.append(
                    f"capture {index:03d} {label}: postcondition issues must be empty"
                )
            if postcondition.get("passed") is not True:
                postcondition_findings.append(
                    f"capture {index:03d} {label}: postcondition did not pass"
                )
        expected_family = fixture.get("expected_window_family")
        actual_family = fixture.get("actual_window_family")
        if (
            expected_family != renderer_families[label]
            or actual_family != renderer_families[label]
            or record.get("window_family") != renderer_families[label]
        ):
            issues.append(
                f"capture {index:03d} {label}: renderer-family validation does not "
                f"match source-owned {renderer_families[label]}"
            )

        audit = record.get("audit")
        if not isinstance(audit, dict) or audit.get("passed") is not True:
            issues.append(f"capture {index:03d} {label}: audit is missing or did not pass")
        elif audit.get("fixture_identity") != fixture:
            issues.append(f"capture {index:03d} {label}: audit fixture identity disagrees")
        if (
            contract.version >= 26
            and (
                not isinstance(audit, dict)
                or audit.get("semantic_audit_passed") is not True
            )
        ):
            issues.append(
                f"capture {index:03d} {label}: audit semantic result did not pass"
            )
        if isinstance(audit, dict):
            record_audits[label] = audit
        if contract.version >= 26:
            for progress_issue in _native_progress_bar_record_issues(
                label=label,
                record=record,
                audit=audit if isinstance(audit, dict) else None,
            ):
                issues.append(
                    f"capture {index:03d} {label}: {progress_issue}"
                )
        if label == "move-mode":
            move_hover = (
                audit.get("move_occupied_hover")
                if isinstance(audit, dict) else None
            )
            for move_issue in move_occupied_hover_issue_codes(move_hover):
                issues.append(
                    f"capture {index:03d} {label}: {move_issue}"
                )
        native_layout_findings = (
            issues if contract.version >= 26 else advisories
        )
        for telemetry_issue in _native_layout_telemetry_record_issues(
            label=label,
            window_family=renderer_families[label],
            record=record,
            audit=audit if isinstance(audit, dict) else None,
            limits=layout_limits,
            button_heights=button_heights,
            tabular_labels=tabular_labels,
        ):
            native_layout_findings.append(
                f"capture {index:03d} {label}: {telemetry_issue}"
            )
        for visual_issue in _visual_contract_record_issues(
            label=label,
            state_kind=str(state_contract["kind"]),
            record=record,
            audit=audit if isinstance(audit, dict) else None,
        ):
            issues.append(
                f"capture {index:03d} {label}: {visual_issue}"
            )
        for pixel_issue in _unpainted_client_record_issues(
            label=label,
            record=record,
            audit=audit if isinstance(audit, dict) else None,
            screenshot_path=screenshot_path,
        ):
            issues.append(
                f"capture {index:03d} {label}: {pixel_issue}"
            )
        if logical_size is not None and dpr is not None:
            record_geometry[label] = (
                logical_size[0],
                logical_size[1],
                dpr,
                renderer_families[label],
            )

    fertilizer_flow_labels = {
        "fertilizer-active",
        "purchase-confirmation-fertilizer-queue",
    }
    if fertilizer_flow_labels.issubset(set(expected_labels)):
        source_audit = record_audits.get("fertilizer-active", {})
        queue_audit = record_audits.get(
            "purchase-confirmation-fertilizer-queue",
            {},
        )
        source = source_audit.get("fertilizer_flow_source")
        confirmation = queue_audit.get("fertilizer_queue_confirmation")
        continuity = (
            confirmation.get("plant_state_continuity")
            if isinstance(confirmation, dict) else
            None
        )
        embedded_records = (
            continuity.get("records")
            if isinstance(continuity, dict) else
            None
        )
        cross_surface_records = (
            dict(embedded_records)
            if isinstance(embedded_records, dict) else
            {}
        )
        cross_surface_records["source"] = source
        for flow_issue in fertilizer_flow_continuity_issue_codes(
            cross_surface_records
        ):
            issues.append(
                "fertilizer_queue scenario continuity: " + flow_issue
            )

    _validate_dialog_scroll_summary(
        payload,
        dialog_scroll_coverage,
        record_scroll_audits,
        advisories,
        required=capture_profile == "full",
    )

    first_seen_displays = list(dict.fromkeys(record_displays))
    if payload.get("capture_displays") != first_seen_displays:
        issues.append("capture_displays does not match first-seen per-record displays")
    aggregate_display = (
        first_seen_displays[0]
        if len(first_seen_displays) == 1
        else "mixed"
        if first_seen_displays
        else None
    )
    if payload.get("capture_display") != aggregate_display:
        issues.append("capture_display does not match per-record display provenance")

    for digest_labels in visual_labels.values():
        if len(digest_labels) < 2:
            continue
        label_set = frozenset(digest_labels)
        if label_set not in INTENTIONAL_DUPLICATE_VISUALS:
            advisories.append(
                "unapproved duplicate visual evidence: " + ", ".join(digest_labels)
            )
            continue
        geometries = {record_geometry.get(label) for label in digest_labels}
        if None in geometries or len(geometries) != 1:
            advisories.append(
                "intentional duplicate evidence has inconsistent geometry: "
                + ", ".join(digest_labels)
            )
        if label_set == frozenset({"starter-nursery-plants", "starter-action-above-footer"}):
            action_audit = record_audits.get("starter-action-above-footer", {})
            if not (
                action_audit.get("nursery_footer_clearance_audited") is True
                and action_audit.get("catalog_row") == "first"
                and type(action_audit.get("action_count")) is int
                and action_audit.get("action_count", 0) > 0
            ):
                advisories.append(
                    "starter Nursery duplicate lacks the footer-clearance audit"
                )
    normalized_screenshot_paths = [path for path in screenshot_paths if path is not None]
    if len(normalized_screenshot_paths) != len(set(normalized_screenshot_paths)):
        issues.append("screenshots contains duplicate paths")
    casefold_paths = [str(path).casefold() for path in normalized_screenshot_paths]
    if len(casefold_paths) != len(set(casefold_paths)):
        issues.append("screenshots contains case-insensitive path collisions")
    actual_session_pngs = {
        path.resolve()
        for path in session_dir.glob("*.png")
        if path.is_file()
    }
    if actual_session_pngs != valid_manifest_pngs:
        missing = sorted(str(path) for path in valid_manifest_pngs - actual_session_pngs)
        extras = sorted(str(path) for path in actual_session_pngs - valid_manifest_pngs)
        if missing:
            issues.append("manifest PNG files are missing: " + ", ".join(missing))
        if extras:
            issues.append("session contains unowned PNG files: " + ", ".join(extras))

    if issues:
        raise CaptureValidationError(issues)
    return {
        "capture_contract_version": contract.version,
        "capture_count": expected_count,
        "capture_profile": capture_profile,
        "evidence_tier": (
            "final-release" if capture_profile == "full" else "preflight"
        ),
        "manifest": str(manifest_path),
        "automated_release_gate_passed": capture_profile == "full",
        "release_ready": False,
        "status": "valid",
        "audit_advisories": list(dict.fromkeys(advisories)),
    }


def validate_contact_sheet_set(
    contact_sheet_set_path: Path,
    *,
    manifest_path: Path,
    capture_source: Path = DEFAULT_CAPTURE_SOURCE,
) -> dict[str, Any]:
    """Validate optional contact-sheet index, PNG pages, order, and counts."""

    contact_sheet_set_path = contact_sheet_set_path.resolve()
    manifest_path = manifest_path.resolve()
    manifest_payload = _load_json_object(manifest_path, "capture manifest")
    capture_profile = str(manifest_payload.get("capture_profile", ""))
    if capture_profile not in {"representative", "full"}:
        raise CaptureValidationError((
            "contact-sheet capture profile is invalid",
        ))
    contract = load_capture_contract(capture_source, profile=capture_profile)
    scenario_contracts = (
        load_capture_scenario_contracts(capture_source, contract=contract)
        if contract.version >= 26 else
        {}
    )
    expected_count = len(contract.labels)
    expected_group_names = [name for name, _labels in contract.groups]
    expected_pages = expected_contact_sheet_pages(contract)
    expected_label_pages = expected_contact_sheet_page_groups(contract)
    payload = _load_json_object(contact_sheet_set_path, "contact-sheet set")
    set_dir = contact_sheet_set_path.parent.resolve()
    issues: list[str] = []
    manifest_records = manifest_payload.get("captures")
    capture_paths: dict[str, Path] = {}
    manifest_record_labels: list[str] = []
    if not isinstance(manifest_records, list):
        issues.append("capture manifest records are unavailable for contact binding")
    else:
        for record in manifest_records:
            if not isinstance(record, dict) or not isinstance(record.get("label"), str):
                issues.append("capture manifest record is invalid for contact binding")
                continue
            label = record["label"]
            manifest_record_labels.append(label)
            if contract.version >= 26:
                scenario_contract = scenario_contracts.get(label, {})
                for identity_field in (
                    "scenario_id",
                    "fixture_id",
                    "scenario_step",
                ):
                    if record.get(identity_field) != scenario_contract.get(
                        identity_field
                    ):
                        issues.append(
                            "capture manifest record scenario identity does not "
                            f"match the contract for {label}: {identity_field}"
                        )
            path = _resolved_evidence_path(record.get("path"), manifest_path.parent)
            if path is not None:
                capture_paths[label] = path
        if manifest_record_labels != list(contract.labels):
            issues.append(
                "capture manifest record order does not match contact-sheet contract"
            )

    if payload.get("complete") is not True:
        issues.append("contact-sheet set is not marked complete")
    if payload.get("capture_profile") != capture_profile:
        issues.append("contact-sheet capture_profile does not match the manifest")
    if payload.get("capture_contract_digest") != contract.digest:
        issues.append("contact-sheet capture_contract_digest does not match")
    if payload.get("padding_legend") != CONTACT_SHEET_PADDING_LEGEND:
        issues.append("contact-sheet padding legend is missing or ambiguous")
    if payload.get("quality_status") != CONTACT_SHEET_QUALITY_STATUS:
        issues.append("contact-sheet quality status must keep visual review pending")
    package_version = payload.get("package_version")
    if not isinstance(package_version, str) or not package_version.strip():
        issues.append("contact-sheet package_version must be nonempty")
        package_version = ""
    package_sha256 = payload.get("package_sha256")
    if (
        not isinstance(package_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", package_sha256) is None
    ):
        issues.append("contact-sheet package_sha256 must be lowercase SHA-256")
        package_sha256 = ""
    referenced_manifest = _resolved_evidence_path(payload.get("capture_manifest"), set_dir)
    if referenced_manifest != manifest_path.resolve():
        issues.append("contact-sheet set references a different capture manifest")
    if payload.get("surface_count") != expected_count:
        issues.append(
            "contact-sheet surface_count must be "
            f"{expected_count}, found {payload.get('surface_count')!r}"
        )

    pages = payload.get("pages")
    if not isinstance(pages, list) or not pages:
        pages = []
        issues.append("contact-sheet pages must be a non-empty list")
    if type(payload.get("page_count")) is not int or payload.get("page_count") != len(pages):
        issues.append("contact-sheet page_count does not match pages")
    if len(pages) != len(expected_pages):
        issues.append(
            f"contact-sheet topology must contain {len(expected_pages)} pages, found {len(pages)}"
        )
    if contract.version <= 24:
        required_page_count = LEGACY_V24_PROFILE_CONTACT_SHEET_PAGE_COUNTS[
            capture_profile
        ]
        if len(expected_pages) != required_page_count or len(pages) != required_page_count:
            issues.append(
                f"legacy {capture_profile} contact-sheet evidence must contain exactly "
                f"{required_page_count} pages"
            )

    page_paths: list[Path] = []
    counted_surfaces = 0
    encountered_groups: list[str] = []
    previous_group = ""
    for page_index, page in enumerate(pages, start=1):
        if not isinstance(page, dict):
            issues.append(f"contact-sheet page {page_index}: entry must be an object")
            continue
        if type(page.get("page")) is not int or page.get("page") != page_index:
            issues.append(f"contact-sheet page {page_index}: page number is out of order")
        expected_page = expected_pages[page_index - 1] if page_index <= len(expected_pages) else ()
        expected_label_page = (
            expected_label_pages[page_index - 1]
            if page_index <= len(expected_label_pages)
            else ()
        )
        expected_page_groups = [name for name, _count in expected_page]
        expected_page_count = sum(count for _name, count in expected_page)
        expected_surface_identity_map = (
            _surface_scenario_identity_map(
                [
                    label
                    for _group_name, labels in expected_label_page
                    for label in labels
                ],
                scenario_contracts,
            )
            if contract.version >= 26 else
            {}
        )
        expected_surface_ids = list(expected_surface_identity_map)
        expected_identity_field_maps = {
            identity_field: {
                label: identity.get(identity_field)
                for label, identity in expected_surface_identity_map.items()
            }
            for identity_field in ("scenario_id", "fixture_id", "scenario_step")
        }
        expected_filename = (
            f"{page_index:02d}-{_contact_sheet_slug(expected_page_groups)}.png"
            if expected_page else
            ""
        )
        raw_file = page.get("file")
        page_path = _resolved_evidence_path(raw_file, set_dir)
        if page_path is None:
            issues.append(f"contact-sheet page {page_index}: file is missing")
        else:
            if Path(str(raw_file)).name != str(raw_file):
                issues.append(f"contact-sheet page {page_index}: file must be a local basename")
            if not _inside_directory(page_path, set_dir):
                issues.append(f"contact-sheet page {page_index}: file is outside the set directory")
            evidence = _read_png(page_path, normalize_pixels=False)
            if page_path.suffix.lower() != ".png" or evidence is None:
                issues.append(
                    f"contact-sheet page {page_index}: file is missing or not a valid PNG"
                )
            elif expected_page:
                expected_dimensions = expected_contact_sheet_dimensions(expected_page)
                if (evidence.width, evidence.height) != expected_dimensions:
                    issues.append(
                        f"contact-sheet page {page_index}: PNG dimensions must be "
                        f"{expected_dimensions[0]}x{expected_dimensions[1]}px"
                    )
                else:
                    issues.extend(
                        f"contact-sheet page {page_index}: {issue}"
                        for issue in _contact_preview_issues(
                            page_path,
                            expected_label_page,
                            capture_paths,
                        )
                    )
                    issues.extend(
                        f"contact-sheet page {page_index}: {issue}"
                        for issue in _contact_metadata_issues(
                            page_path,
                            page_number=page_index,
                            page_count=len(expected_pages),
                            package_version=package_version,
                            package_sha256=package_sha256,
                            manifest_path=manifest_path,
                            capture_profile=capture_profile,
                            capture_contract_digest=contract.digest,
                            surface_identity_map=expected_surface_identity_map,
                        )
                    )
            if expected_filename and page_path.name != expected_filename:
                issues.append(
                    f"contact-sheet page {page_index}: filename must be {expected_filename}"
                )
            page_paths.append(page_path)

        surface_count = page.get("surface_count")
        if type(surface_count) is not int or surface_count < 1:
            issues.append(f"contact-sheet page {page_index}: surface_count must be positive")
        else:
            counted_surfaces += surface_count
            if expected_page and surface_count != expected_page_count:
                issues.append(
                    f"contact-sheet page {page_index}: surface_count must be {expected_page_count}"
                )

        if contract.version >= 26:
            if page.get("surface_ids") != expected_surface_ids:
                issues.append(
                    f"contact-sheet page {page_index}: surface_ids do not match "
                    "the deterministic page order"
                )
            if page.get("surface_identity_map") != expected_surface_identity_map:
                issues.append(
                    f"contact-sheet page {page_index}: surface_identity_map does "
                    "not match the v26 scenario contract"
                )
            for identity_field, expected_field_map in (
                expected_identity_field_maps.items()
            ):
                if page.get(identity_field) != expected_field_map:
                    issues.append(
                        f"contact-sheet page {page_index}: {identity_field} map "
                        "does not match the v26 scenario contract"
                    )

        groups = page.get("groups")
        if not isinstance(groups, list) or not groups:
            issues.append(f"contact-sheet page {page_index}: groups must be non-empty")
            continue
        if expected_page and groups != expected_page_groups:
            issues.append(
                f"contact-sheet page {page_index}: groups do not match deterministic topology"
            )
        for raw_group in groups:
            if not isinstance(raw_group, str) or not raw_group:
                issues.append(f"contact-sheet page {page_index}: group name is invalid")
                continue
            continued = raw_group.endswith(CONTINUED_SUFFIX)
            group = raw_group[:-len(CONTINUED_SUFFIX)] if continued else raw_group
            if group not in expected_group_names:
                issues.append(f"contact-sheet page {page_index}: unknown group {raw_group!r}")
                continue
            if group == previous_group:
                if not continued:
                    issues.append(
                        f"contact-sheet page {page_index}: repeated group "
                        f"{group!r} is not marked continued"
                    )
            else:
                if continued:
                    issues.append(
                        f"contact-sheet page {page_index}: group {group!r} "
                        "is marked continued without a prior page"
                    )
                encountered_groups.append(group)
            previous_group = group

    if counted_surfaces != expected_count:
        issues.append(
            f"contact-sheet pages account for {counted_surfaces} surfaces, "
            f"expected {expected_count}"
        )
    if encountered_groups != expected_group_names:
        issues.append("contact-sheet groups do not cover the source contract in order")
    if len(page_paths) != len(set(page_paths)):
        issues.append("contact-sheet pages contain duplicate files")
    actual_page_pngs = {
        path.resolve()
        for path in set_dir.glob("*.png")
        if path.is_file()
    }
    expected_page_pngs = set(page_paths)
    if actual_page_pngs != expected_page_pngs:
        missing = sorted(str(path) for path in expected_page_pngs - actual_page_pngs)
        extras = sorted(str(path) for path in actual_page_pngs - expected_page_pngs)
        if missing:
            issues.append("contact-sheet PNG files are missing: " + ", ".join(missing))
        if extras:
            issues.append(
                "contact-sheet directory contains unindexed PNG files: "
                + ", ".join(extras)
            )

    if issues:
        raise CaptureValidationError(issues)
    return {
        "contact_sheet_set": str(contact_sheet_set_path),
        "capture_profile": capture_profile,
        "evidence_tier": (
            "final-release" if capture_profile == "full" else "preflight"
        ),
        "page_count": len(pages),
        "surface_count": expected_count,
        "status": "valid",
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate complete Anki Garden release capture evidence."
    )
    parser.add_argument("manifest", type=Path, help="Path to capture manifest.json")
    parser.add_argument(
        "--capture-source",
        type=Path,
        default=DEFAULT_CAPTURE_SOURCE,
        help="Capture source containing the literal release contract",
    )
    parser.add_argument(
        "--contact-sheet-set",
        type=Path,
        help=(
            "Optional contact-sheet-set.json review aid; raw manifest PNGs "
            "remain the runtime geometry authority"
        ),
    )
    parser.add_argument(
        "--surface-report",
        action="store_true",
        help=(
            "Classify each manifest-owned surface and return a minimal "
            "recapture list without requiring a complete release set"
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    if arguments.surface_report:
        try:
            try:
                from scripts.capture_evidence import surface_validation_report
            except ImportError:
                from capture_evidence import surface_validation_report
            result = surface_validation_report(arguments.manifest)
        except (OSError, ValueError) as error:
            print(
                json.dumps({"error": str(error), "status": "failed"}),
                file=sys.stderr,
            )
            return 1
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    try:
        result = validate_capture_manifest(
            arguments.manifest,
            capture_source=arguments.capture_source,
        )
        if arguments.contact_sheet_set is not None:
            result["contact_sheets"] = validate_contact_sheet_set(
                arguments.contact_sheet_set,
                manifest_path=arguments.manifest,
                capture_source=arguments.capture_source,
            )
    except CaptureValidationError as error:
        print(
            json.dumps(
                {"errors": list(error.issues), "status": "invalid"},
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
