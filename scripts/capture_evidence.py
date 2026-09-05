#!/usr/bin/env python3
"""Incremental evidence planning and assembly for Anki Garden UI captures.

This module is deliberately Qt-free.  The disposable Anki process owns raw
capture; this module decides which existing records remain trustworthy and
assembles one self-contained, canonically ordered evidence directory.
"""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import textwrap
import zipfile
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
SCENARIO_REUSE_SCHEMA_VERSION = 3
_LEGACY_SCENARIO_REUSE_SCHEMA_VERSIONS = frozenset({1, 2})
RENDERER_OWNERSHIP_REUSE_SCHEMA_VERSION = 2
_SCENARIO_UNKNOWN = object()
DIALOG_SCROLL_FOUR_STATE_NAMES = (
    "no-overflow-list",
    "one-row-list",
    "enough-rows-to-scroll",
    "final-item-at-maximum-scroll",
)
LEGACY_CAPTURE_ACCEPTANCE_POLICY = "gross-failures-only"
V26_CAPTURE_ACCEPTANCE_POLICY = "gross-and-semantic-fail-closed"
_V26_DEPRECATED_VISIBLE_COPY_PATTERNS = (
    r"\bstage [1-5] of 5\b",
    r"\b1 find\b",
    r"\bnew environments?\b",
    r"\benvironment discoveries\b",
    r"\benvironment discovery guarantees\b",
    r"\bfuture growth will be shared or stored\b",
    r"\btoday['’]s environment\b",
    r"\bnursery weather scenery\b",
    r"\bgarden item unlocked\b",
)

_DEFERRED_SPECIES_OVERVIEW_EDGE = (
    "GardenDashboard._refresh_collection_list",
    "GardenDashboard._open_species_overview",
)
_DEFERRED_SPECIES_OVERVIEW_DROPPED_FRAGMENTS = frozenset({
    "GardenDashboard._build_species_overview_dialog",
    "GardenDashboard._local_date",
    "GardenDashboard._open_species_overview",
    "_dispose_owned_dialog",
})
_SPECIES_OVERVIEW_LABELS = frozenset({
    "collection-species-overview",
    "collection-known-not-collected-overview",
})

# These shared runner methods route capture-time behavior by the immutable
# surface label passed through the scenario contract.  Their per-label AST
# path belongs to the surface; unrelated branches belong to their own labels.
# Every other helper remains byte-exact/fail-closed unless it becomes reachable
# from one of these projected paths.
_SCENARIO_LABEL_PATH_METHODS = frozenset({
    "_audit_capture_pixel_contracts",
    "_capture_and_advance",
    "_capture_metric",
    "_surface_stability_signature",
    "_wait_for_visual_stability",
})

# These source-owned metadata helpers also route exclusively on their immutable
# ``label`` argument.  Hash their evaluated per-label path rather than their
# aggregate source body so adding one surface to a fixture checkpoint cannot
# invalidate unrelated evidence.  All other top-level functions remain exact
# shared dependencies.
_SCENARIO_LABEL_PATH_TOP_LEVELS = frozenset({
    "capture_scenario_checkpoint",
    "capture_scenario_internal_setups",
    "capture_scenario_prerequisites",
})

# Literal maps are scoped only when every declared key is a known capture
# label and the projected method reads the entry through that immutable label.
# Unknown keys or any whole-map use retain the aggregate source hash.
_SCENARIO_LABEL_SCOPED_TOP_LEVELS = frozenset({
    "RENDERED_PIXEL_EVIDENCE_KEYS",
})

# The current runner deliberately ignores these legacy scheduling arguments
# (`_capture_and_advance()` deletes them before any branch).  Literal values
# therefore do not own captured pixels or fixture evidence.  Callback and
# predicate bodies remain surface-owned because a gate-only run does not
# replay every surface lifecycle.
_SCENARIO_POST_CAPTURE_LITERAL_KEYWORDS = frozenset({
    "close_ms",
    "next_ms",
})


class CaptureEvidenceError(ValueError):
    """Raised when incremental evidence cannot be trusted or assembled."""


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256_bytes(encoded)


def _scenario_static_value(node: ast.AST, environment: Mapping[str, Any]) -> Any:
    """Evaluate only the side-effect-free expressions used to route scenarios."""

    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return environment.get(node.id, _SCENARIO_UNKNOWN)
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        values = [_scenario_static_value(item, environment) for item in node.elts]
        if any(value is _SCENARIO_UNKNOWN for value in values):
            return _SCENARIO_UNKNOWN
        if isinstance(node, ast.Tuple):
            return tuple(values)
        if isinstance(node, ast.Set):
            return set(values)
        return values
    if isinstance(node, ast.Dict):
        keys = [_scenario_static_value(item, environment) for item in node.keys]
        values = [_scenario_static_value(item, environment) for item in node.values]
        if any(value is _SCENARIO_UNKNOWN for value in (*keys, *values)):
            return _SCENARIO_UNKNOWN
        try:
            return dict(zip(keys, values))
        except (TypeError, ValueError):
            return _SCENARIO_UNKNOWN
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        value = _scenario_static_value(node.operand, environment)
        return _SCENARIO_UNKNOWN if value is _SCENARIO_UNKNOWN else not bool(value)
    if isinstance(node, ast.BoolOp):
        values = [_scenario_static_value(item, environment) for item in node.values]
        if isinstance(node.op, ast.And):
            if any(value is not _SCENARIO_UNKNOWN and not bool(value) for value in values):
                return False
            return True if all(value is not _SCENARIO_UNKNOWN for value in values) else _SCENARIO_UNKNOWN
        if isinstance(node.op, ast.Or):
            if any(value is not _SCENARIO_UNKNOWN and bool(value) for value in values):
                return True
            return False if all(value is not _SCENARIO_UNKNOWN for value in values) else _SCENARIO_UNKNOWN
    if isinstance(node, ast.Compare):
        left = _scenario_static_value(node.left, environment)
        if left is _SCENARIO_UNKNOWN:
            return _SCENARIO_UNKNOWN
        for operator, comparator_node in zip(node.ops, node.comparators):
            right = _scenario_static_value(comparator_node, environment)
            if right is _SCENARIO_UNKNOWN:
                return _SCENARIO_UNKNOWN
            try:
                if isinstance(operator, ast.Eq):
                    passed = left == right
                elif isinstance(operator, ast.NotEq):
                    passed = left != right
                elif isinstance(operator, ast.In):
                    passed = left in right
                elif isinstance(operator, ast.NotIn):
                    passed = left not in right
                elif isinstance(operator, ast.Is):
                    passed = left is right
                elif isinstance(operator, ast.IsNot):
                    passed = left is not right
                elif isinstance(operator, ast.Lt):
                    passed = left < right
                elif isinstance(operator, ast.LtE):
                    passed = left <= right
                elif isinstance(operator, ast.Gt):
                    passed = left > right
                elif isinstance(operator, ast.GtE):
                    passed = left >= right
                else:
                    return _SCENARIO_UNKNOWN
            except (TypeError, ValueError):
                return _SCENARIO_UNKNOWN
            if not passed:
                return False
            left = right
        return True
    if isinstance(node, ast.Subscript):
        owner = _scenario_static_value(node.value, environment)
        key = _scenario_static_value(node.slice, environment)
        if owner is _SCENARIO_UNKNOWN or key is _SCENARIO_UNKNOWN:
            return _SCENARIO_UNKNOWN
        try:
            return owner[key]
        except (KeyError, IndexError, TypeError):
            return _SCENARIO_UNKNOWN
    if isinstance(node, ast.Call):
        arguments = [_scenario_static_value(item, environment) for item in node.args]
        keywords = {
            item.arg: _scenario_static_value(item.value, environment)
            for item in node.keywords
            if item.arg is not None
        }
        if any(value is _SCENARIO_UNKNOWN for value in (*arguments, *keywords.values())):
            return _SCENARIO_UNKNOWN
        if (
            isinstance(node.func, ast.Name)
            and node.func.id == "expected_capture_state_profile"
            and len(arguments) == 1
            and not keywords
        ):
            profiles = environment.get(
                "__capture_expected_state_profiles__",
                _SCENARIO_UNKNOWN,
            )
            if isinstance(profiles, Mapping):
                return profiles.get(arguments[0], _SCENARIO_UNKNOWN)
        if isinstance(node.func, ast.Name) and node.func.id in {
            "bool",
            "frozenset",
            "int",
            "list",
            "set",
            "str",
            "tuple",
        }:
            constructors = {
                "bool": bool,
                "frozenset": frozenset,
                "int": int,
                "list": list,
                "set": set,
                "str": str,
                "tuple": tuple,
            }
            try:
                return constructors[node.func.id](*arguments, **keywords)
            except (TypeError, ValueError):
                return _SCENARIO_UNKNOWN
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
        ):
            owner = _scenario_static_value(node.func.value, environment)
            if isinstance(owner, Mapping) and 1 <= len(arguments) <= 2:
                return owner.get(*arguments)
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in {"endswith", "startswith"}
        ):
            owner = _scenario_static_value(node.func.value, environment)
            if isinstance(owner, str):
                try:
                    return getattr(owner, node.func.attr)(*arguments, **keywords)
                except (TypeError, ValueError):
                    return _SCENARIO_UNKNOWN
    return _SCENARIO_UNKNOWN


def _scenario_literal_environment(module: ast.Module) -> dict[str, Any]:
    """Load literal module constants used by postcondition routing."""

    environment: dict[str, Any] = {}
    for statement in module.body:
        if isinstance(statement, ast.Assign):
            targets = statement.targets
            value_node = statement.value
        elif isinstance(statement, ast.AnnAssign):
            targets = [statement.target]
            value_node = statement.value
        else:
            continue
        if value_node is None:
            continue
        value = _scenario_static_value(value_node, environment)
        if value is _SCENARIO_UNKNOWN:
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                environment[target.id] = value
    return environment


class _ScenarioPathProjector(ast.NodeTransformer):
    """Keep one label's statically reachable capture and contract path.

    Runtime-dependent conditions remain intact with both branches. This is the
    fail-closed boundary: only conditions derived from immutable scenario
    metadata can narrow invalidation. Simple local literal assignments are
    propagated so an empty per-label evidence requirement can close before it
    pulls unrelated geometry helpers into the surface digest.
    """

    def __init__(
        self,
        environment: Mapping[str, Any],
        *,
        immutable_names: Iterable[str] = (),
        rebindable_immutable_names: Iterable[str] = (),
        label_scoped_mappings: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> None:
        self.environment = dict(environment)
        self.immutable_names = frozenset(str(name) for name in immutable_names)
        self.rebindable_immutable_names = frozenset(
            str(name) for name in rebindable_immutable_names
        )
        self.label_scoped_mappings = dict(label_scoped_mappings or {})

    def _child(self) -> _ScenarioPathProjector:
        return _ScenarioPathProjector(
            self.environment,
            immutable_names=self.immutable_names,
            rebindable_immutable_names=self.rebindable_immutable_names,
            label_scoped_mappings=self.label_scoped_mappings,
        )

    @staticmethod
    def _literal_node(value: Any) -> ast.AST:
        try:
            return ast.parse(repr(value), mode="eval").body
        except (SyntaxError, ValueError) as error:
            raise CaptureEvidenceError(
                "Capture scenario literal projection failed"
            ) from error

    def _visit_block(self, statements: Sequence[ast.stmt]) -> list[ast.stmt]:
        projected: list[ast.stmt] = []
        for statement in statements:
            value = self.visit(statement)
            if value is None:
                continue
            if isinstance(value, list):
                projected.extend(value)
            else:
                projected.append(value)
            if projected and isinstance(
                projected[-1],
                (ast.Break, ast.Continue, ast.Raise, ast.Return),
            ):
                break
        return projected

    def _update_assignment(self, targets: Sequence[ast.AST], value: ast.AST) -> None:
        resolved = _scenario_static_value(value, self.environment)
        for target in targets:
            if not isinstance(target, ast.Name):
                self._invalidate_target(target)
                continue
            if target.id in self.immutable_names:
                if (
                    target.id in self.rebindable_immutable_names
                    and resolved is not _SCENARIO_UNKNOWN
                    and target.id in self.environment
                    and resolved == self.environment[target.id]
                ):
                    continue
                raise CaptureEvidenceError(
                    "Capture path reassigns immutable scenario name: "
                    + target.id
                )
            if resolved is _SCENARIO_UNKNOWN:
                self.environment.pop(target.id, None)
            else:
                self.environment[target.id] = resolved

    def _invalidate_target(self, target: ast.AST) -> None:
        """Forget any mutable local reached by a non-literal assignment."""

        if isinstance(target, ast.Name):
            if target.id in self.immutable_names:
                raise CaptureEvidenceError(
                    "Capture path reassigns immutable scenario name: "
                    + target.id
                )
            self.environment.pop(target.id, None)
            return
        if isinstance(target, (ast.List, ast.Tuple)):
            for child in target.elts:
                self._invalidate_target(child)
            return
        owner = target
        while isinstance(owner, (ast.Attribute, ast.Subscript)):
            owner = owner.value
        if isinstance(owner, ast.Name):
            if owner.id in self.immutable_names:
                raise CaptureEvidenceError(
                    "Capture path mutates immutable scenario name: "
                    + owner.id
                )
            self.environment.pop(owner.id, None)

    def _preserve_uncertain_control_flow(self, node: ast.AST) -> ast.AST:
        """Keep dynamic loops/handlers intact and discard their assignments.

        A projected label branch inside one of these constructs would require
        path-sensitive loop/exception analysis.  Retaining the original AST is
        deliberately conservative: its complete dependency closure remains in
        every affected surface, while locals that may be reassigned cannot
        incorrectly steer a later projection.
        """

        for child in ast.walk(node):
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                self._invalidate_target(child)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:  # noqa: N802
        child = self._child()
        node.body = child._visit_block(node.body)
        return node

    def visit_AsyncFunctionDef(  # noqa: N802
        self,
        node: ast.AsyncFunctionDef,
    ) -> ast.AST:
        child = self._child()
        node.body = child._visit_block(node.body)
        return node

    def visit_Assign(self, node: ast.Assign) -> ast.AST:  # noqa: N802
        node.value = self.visit(node.value)
        self._update_assignment(node.targets, node.value)
        return node

    def visit_AnnAssign(self, node: ast.AnnAssign) -> ast.AST:  # noqa: N802
        if node.value is not None:
            node.value = self.visit(node.value)
            self._update_assignment((node.target,), node.value)
        else:
            self._invalidate_target(node.target)
        return node

    def visit_AugAssign(self, node: ast.AugAssign) -> ast.AST:  # noqa: N802
        node = self.generic_visit(node)
        self._invalidate_target(node.target)
        return node

    def visit_Delete(self, node: ast.Delete) -> ast.AST:  # noqa: N802
        for target in node.targets:
            self._invalidate_target(target)
        return node

    def visit_NamedExpr(self, node: ast.NamedExpr) -> ast.AST:  # noqa: N802
        node = self.generic_visit(node)
        self._invalidate_target(node.target)
        return node

    def visit_For(self, node: ast.For) -> ast.AST:  # noqa: N802
        return self._preserve_uncertain_control_flow(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> ast.AST:  # noqa: N802
        return self._preserve_uncertain_control_flow(node)

    def visit_While(self, node: ast.While) -> ast.AST:  # noqa: N802
        return self._preserve_uncertain_control_flow(node)

    def visit_With(self, node: ast.With) -> ast.AST:  # noqa: N802
        return self._preserve_uncertain_control_flow(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> ast.AST:  # noqa: N802
        return self._preserve_uncertain_control_flow(node)

    def visit_Try(self, node: ast.Try) -> ast.AST:  # noqa: N802
        return self._preserve_uncertain_control_flow(node)

    if hasattr(ast, "TryStar"):
        def visit_TryStar(self, node: ast.TryStar) -> ast.AST:  # noqa: N802
            return self._preserve_uncertain_control_flow(node)

    def visit_Match(self, node: ast.Match) -> ast.AST:  # noqa: N802
        return self._preserve_uncertain_control_flow(node)

    def visit_If(self, node: ast.If) -> ast.AST | list[ast.stmt]:  # noqa: N802
        decision = _scenario_static_value(node.test, self.environment)
        if decision is _SCENARIO_UNKNOWN:
            node.test = self.visit(node.test)
            before = dict(self.environment)
            body_projector = self._child()
            body_projector.environment = dict(before)
            node.body = body_projector._visit_block(node.body)
            else_projector = self._child()
            else_projector.environment = dict(before)
            node.orelse = else_projector._visit_block(node.orelse)
            merged = {
                name: value
                for name, value in body_projector.environment.items()
                if (
                    name in else_projector.environment
                    and else_projector.environment[name] == value
                )
            }
            for name in self.immutable_names:
                if name in before:
                    merged[name] = before[name]
            self.environment = merged
            return node
        selected = node.body if bool(decision) else node.orelse
        return self._visit_block(selected)

    def visit_IfExp(self, node: ast.IfExp) -> ast.AST:  # noqa: N802
        decision = _scenario_static_value(node.test, self.environment)
        if decision is _SCENARIO_UNKNOWN:
            return self.generic_visit(node)
        selected = node.body if bool(decision) else node.orelse
        return self.visit(selected)

    def visit_Call(self, node: ast.Call) -> ast.AST:  # noqa: N802
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in self.label_scoped_mappings
            and 1 <= len(node.args) <= 2
        ):
            key = _scenario_static_value(node.args[0], self.environment)
            label = self.environment.get("label", _SCENARIO_UNKNOWN)
            if key is not _SCENARIO_UNKNOWN and key == label:
                mapping = self.label_scoped_mappings[node.func.value.id]
                default = (
                    _scenario_static_value(node.args[1], self.environment)
                    if len(node.args) == 2 else
                    None
                )
                if default is not _SCENARIO_UNKNOWN:
                    return self._literal_node(mapping.get(key, default))
        return self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> ast.AST:  # noqa: N802
        if (
            isinstance(node.value, ast.Name)
            and node.value.id in self.label_scoped_mappings
        ):
            key = _scenario_static_value(node.slice, self.environment)
            label = self.environment.get("label", _SCENARIO_UNKNOWN)
            mapping = self.label_scoped_mappings[node.value.id]
            if key is not _SCENARIO_UNKNOWN and key == label and key in mapping:
                return self._literal_node(mapping[key])
        return self.generic_visit(node)


class _ScenarioSurfacePathProjector(ast.NodeTransformer):
    """Remove only ignored literal timing from one surface method."""

    def __init__(
        self,
        root: ast.FunctionDef | ast.AsyncFunctionDef,
        *,
        ignored_literal_keywords: Iterable[str],
    ) -> None:
        self.root = root
        self.ignored_literal_keywords = frozenset(
            str(name) for name in ignored_literal_keywords
        )

    @staticmethod
    def _is_capture_advance_call(node: ast.Call) -> bool:
        return bool(
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in {"self", "cls"}
            and node.func.attr == "_capture_and_advance"
        )

    @staticmethod
    def _literal_timing_is_safe(value: ast.AST) -> bool:
        resolved = _scenario_static_value(value, {})
        return bool(
            resolved is None
            or isinstance(resolved, int) and not isinstance(resolved, bool)
        )

    def visit_Call(self, node: ast.Call) -> ast.AST:  # noqa: N802
        node = self.generic_visit(node)
        if not self._is_capture_advance_call(node):
            return node
        retained: list[ast.keyword] = []
        for keyword in node.keywords:
            if (
                keyword.arg in self.ignored_literal_keywords
                and self._literal_timing_is_safe(keyword.value)
            ):
                continue
            retained.append(keyword)
        node.keywords = retained
        return node

    def project(self) -> ast.FunctionDef | ast.AsyncFunctionDef:
        candidate = self.visit(self.root)
        if not isinstance(candidate, (ast.FunctionDef, ast.AsyncFunctionDef)):
            raise CaptureEvidenceError("Capture surface-path projection failed")
        return candidate


def _scenario_reuse_digests(
    *,
    capture_source: bytes,
    scenario_contracts: Mapping[str, Mapping[str, Any]],
) -> dict[str, str]:
    """Return label-scoped scenario digests with strict shared-code ownership."""

    try:
        source_text = capture_source.decode("utf-8")
        module = ast.parse(source_text)
    except (UnicodeDecodeError, SyntaxError) as error:
        raise CaptureEvidenceError("Capture scenario source is invalid") from error
    runner = next(
        (
            node for node in module.body
            if isinstance(node, ast.ClassDef)
            and node.name == "_UiFaceCaptureRunner"
        ),
        None,
    )
    method_nodes = {
        node.name: node
        for node in (runner.body if isinstance(runner, ast.ClassDef) else ())
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    postcondition = method_nodes.get("_capture_fixture_postcondition")
    if not isinstance(postcondition, (ast.FunctionDef, ast.AsyncFunctionDef)):
        raise CaptureEvidenceError(
            "Capture runner is missing _capture_fixture_postcondition"
        )
    source_lines = [
        line.encode("utf-8")
        for line in source_text.splitlines(keepends=True)
    ]

    def source_segment_bytes(node: ast.AST) -> bytes:
        """Slice one AST span without repeatedly splitting the whole file."""

        try:
            start_line = int(node.lineno) - 1
            end_line = int(node.end_lineno) - 1
            start_column = int(node.col_offset)
            end_column = int(node.end_col_offset)
        except (AttributeError, TypeError, ValueError) as error:
            raise CaptureEvidenceError(
                "Capture source location is unavailable"
            ) from error
        if not (0 <= start_line <= end_line < len(source_lines)):
            raise CaptureEvidenceError("Capture source location is invalid")
        if start_line == end_line:
            return source_lines[start_line][start_column:end_column]
        return b"".join((
            source_lines[start_line][start_column:],
            *source_lines[start_line + 1:end_line],
            source_lines[end_line][:end_column],
        ))

    method_hashes: dict[str, str] = {}
    for method_name, method_node in method_nodes.items():
        method_hashes[method_name] = sha256_bytes(source_segment_bytes(method_node))

    def method_references(node: ast.AST) -> frozenset[str]:
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

    method_dependencies = {
        name: method_references(node)
        for name, node in method_nodes.items()
    }
    capture_advance = method_nodes.get("_capture_and_advance")
    ignored_literal_keywords: set[str] = set()
    if isinstance(capture_advance, (ast.FunctionDef, ast.AsyncFunctionDef)):
        top_level_deleted = {
            target.id
            for statement in capture_advance.body
            if isinstance(statement, ast.Delete)
            for target in statement.targets
            if isinstance(target, ast.Name)
        }
        loaded_names = {
            child.id
            for child in ast.walk(capture_advance)
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load)
        }
        ignored_literal_keywords = {
            name for name in _SCENARIO_POST_CAPTURE_LITERAL_KEYWORDS
            if name in top_level_deleted and name not in loaded_names
        }
    surface_method_nodes: dict[
        str,
        ast.FunctionDef | ast.AsyncFunctionDef,
    ] = {}
    surface_method_hashes: dict[str, str] = {}
    for method_name, method_node in method_nodes.items():
        has_capture_advance_call = any(
            isinstance(child, ast.Call)
            and _ScenarioSurfacePathProjector._is_capture_advance_call(child)
            for child in ast.walk(method_node)
        )
        candidate = (
            _ScenarioSurfacePathProjector(
                copy.deepcopy(method_node),
                ignored_literal_keywords=ignored_literal_keywords,
            ).project()
            if has_capture_advance_call else
            method_node
        )
        ast.fix_missing_locations(candidate)
        surface_method_nodes[method_name] = candidate
        surface_method_hashes[method_name] = sha256_bytes(
            ast.dump(
                candidate,
                annotate_fields=True,
                include_attributes=False,
            ).encode("utf-8")
        )
    top_level_nodes: dict[str, ast.AST] = {}
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
    top_level_hashes: dict[str, str] = {}
    for name, node in top_level_nodes.items():
        top_level_hashes[name] = sha256_bytes(source_segment_bytes(node))

    def top_level_references(node: ast.AST) -> frozenset[str]:
        return frozenset({
            child.id
            for child in ast.walk(node)
            if (
                isinstance(child, ast.Name)
                and isinstance(child.ctx, ast.Load)
                and child.id in top_level_nodes
            )
        })

    top_level_dependencies = {
        name: top_level_references(node) - {name}
        for name, node in top_level_nodes.items()
    }
    literal_environment = _scenario_literal_environment(module)
    expected_label_set = {str(label) for label in scenario_contracts}
    label_scoped_mappings: dict[str, Mapping[str, Any]] = {}
    for name in _SCENARIO_LABEL_SCOPED_TOP_LEVELS:
        value = literal_environment.get(name)
        if (
            isinstance(value, Mapping)
            and all(isinstance(key, str) for key in value)
            and set(value).issubset(expected_label_set)
        ):
            label_scoped_mappings[name] = value
    for method_name in _SCENARIO_LABEL_PATH_METHODS:
        node = method_nodes.get(method_name)
        if node is None:
            continue
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or not any(
            argument.arg == "label"
            for argument in (
                *node.args.posonlyargs,
                *node.args.args,
                *node.args.kwonlyargs,
            )
        ):
            raise CaptureEvidenceError(
                "Capture label-path method is missing its immutable label: "
                + method_name
            )
    for function_name in _SCENARIO_LABEL_PATH_TOP_LEVELS:
        node = top_level_nodes.get(function_name)
        if node is None:
            continue
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or not any(
            argument.arg == "label"
            for argument in (
                *node.args.posonlyargs,
                *node.args.args,
                *node.args.kwonlyargs,
            )
        ):
            raise CaptureEvidenceError(
                "Capture label-path top-level is missing its immutable label: "
                + function_name
            )
    hidden_raw = literal_environment.get(
        "CAPTURE_SCENARIO_HIDDEN_METHOD_REFERENCES",
        {},
    )
    if not isinstance(hidden_raw, dict):
        raise CaptureEvidenceError(
            "Capture scenario hidden-method ownership is invalid"
        )
    hidden_method_edges: set[tuple[str, str]] = set()
    for raw_caller, raw_callees in hidden_raw.items():
        caller = str(raw_caller)
        if caller not in method_nodes or not isinstance(raw_callees, (list, tuple)):
            raise CaptureEvidenceError(
                f"Capture scenario hidden-method caller is invalid: {caller}"
            )
        for raw_callee in raw_callees:
            callee = str(raw_callee)
            if callee not in method_dependencies.get(caller, ()):
                raise CaptureEvidenceError(
                    "Capture scenario hidden-method edge is invalid: "
                    f"{caller} -> {callee}"
                )
            hidden_method_edges.add((caller, callee))
    results: dict[str, str] = {}
    for label, raw_scenario in scenario_contracts.items():
        scenario = copy.deepcopy(dict(raw_scenario))
        if scenario.get("label") != label:
            raise CaptureEvidenceError(
                f"Capture scenario label identity is invalid for {label}"
            )
        method_inputs = scenario.get("method_inputs")
        if not isinstance(method_inputs, dict) or (
            method_inputs.get("_capture_fixture_postcondition")
            != method_hashes["_capture_fixture_postcondition"]
        ):
            raise CaptureEvidenceError(
                f"Capture postcondition dependency is unbound for {label}"
            )
        if any(
            method_hashes.get(str(name)) != digest
            for name, digest in method_inputs.items()
        ):
            raise CaptureEvidenceError(
                f"Capture method dependency is unbound for {label}"
            )
        top_level_inputs = scenario.get("top_level_inputs")
        if not isinstance(top_level_inputs, dict) or any(
            top_level_hashes.get(str(name)) != digest
            for name, digest in top_level_inputs.items()
        ):
            raise CaptureEvidenceError(
                f"Capture top-level dependency is unbound for {label}"
            )
        state_contract = scenario.get("state_contract")
        profile = (
            state_contract.get("profile")
            if isinstance(state_contract, dict) else None
        )
        if not isinstance(profile, dict) or profile.get("profile_id") != label:
            raise CaptureEvidenceError(
                f"Capture state profile is invalid for {label}"
            )
        kind = str(profile.get("kind", ""))
        state_name = str(profile.get("state", label))
        environment = {
            **literal_environment,
            "__capture_expected_state_profiles__": {label: profile},
            "canonical_page": str(profile.get("canonical_page", "")),
            "expectation": profile,
            "kind": kind,
            "label": label,
            "state_name": state_name,
        }
        projected = _ScenarioPathProjector(
            environment,
            immutable_names={
                "canonical_page",
                "expectation",
                "kind",
                "label",
                "state_name",
            },
            rebindable_immutable_names={
                "canonical_page",
                "expectation",
                "kind",
                "state_name",
            },
            label_scoped_mappings=label_scoped_mappings,
        ).visit(
            copy.deepcopy(postcondition)
        )
        if not isinstance(projected, (ast.FunctionDef, ast.AsyncFunctionDef)):
            raise CaptureEvidenceError(
                f"Capture postcondition projection failed for {label}"
            )
        ast.fix_missing_locations(projected)
        postcondition_path_digest = sha256_bytes(
            ast.dump(projected, annotate_fields=True, include_attributes=False).encode(
                "utf-8"
            )
        )
        allowed_methods = set(method_inputs)
        root_method = str(scenario.get("callable", ""))
        if root_method not in allowed_methods:
            raise CaptureEvidenceError(
                f"Capture scenario callable is unbound for {label}"
            )
        projected_methods: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
        projected_top_levels: dict[str, ast.AST] = {}

        def scenario_method(method_name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
            cached = projected_methods.get(method_name)
            if cached is not None:
                return cached
            raw_node = surface_method_nodes.get(method_name)
            if not isinstance(raw_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                raise CaptureEvidenceError(
                    f"Capture scenario method is unavailable for {label}: {method_name}"
                )
            if method_name in _SCENARIO_LABEL_PATH_METHODS:
                candidate = _ScenarioPathProjector(
                    {
                        **literal_environment,
                        "label": label,
                    },
                    immutable_names={"label"},
                    label_scoped_mappings=label_scoped_mappings,
                ).visit(copy.deepcopy(raw_node))
                if not isinstance(
                    candidate,
                    (ast.FunctionDef, ast.AsyncFunctionDef),
                ):
                    raise CaptureEvidenceError(
                        f"Capture method projection failed for {label}: {method_name}"
                    )
                ast.fix_missing_locations(candidate)
            else:
                candidate = raw_node
            projected_methods[method_name] = candidate
            return candidate

        def scenario_top_level(name: str) -> ast.AST:
            cached = projected_top_levels.get(name)
            if cached is not None:
                return cached
            raw_node = top_level_nodes.get(name)
            if raw_node is None:
                raise CaptureEvidenceError(
                    f"Capture top-level dependency is unavailable for {label}: {name}"
                )
            if name in _SCENARIO_LABEL_PATH_TOP_LEVELS:
                candidate = _ScenarioPathProjector(
                    {
                        **literal_environment,
                        "label": label,
                    },
                    immutable_names={"label"},
                    label_scoped_mappings=label_scoped_mappings,
                ).visit(copy.deepcopy(raw_node))
                if not isinstance(
                    candidate,
                    (ast.FunctionDef, ast.AsyncFunctionDef),
                ):
                    raise CaptureEvidenceError(
                        f"Capture top-level projection failed for {label}: {name}"
                    )
                ast.fix_missing_locations(candidate)
            else:
                candidate = raw_node
            projected_top_levels[name] = candidate
            return candidate

        scoped_method_names: set[str] = set()
        pending_methods: list[tuple[str | None, str]] = [(None, root_method)]
        while pending_methods:
            caller, method_name = pending_methods.pop()
            if (
                method_name == "_capture_fixture_postcondition"
                or method_name in scoped_method_names
            ):
                continue
            if method_name not in allowed_methods:
                if caller is not None and (caller, method_name) in hidden_method_edges:
                    continue
                raise CaptureEvidenceError(
                    "Capture scenario method ownership is incomplete for "
                    f"{label}: {caller} -> {method_name}"
                )
            scoped_method_names.add(method_name)
            pending_methods.extend(
                (method_name, dependency)
                for dependency in method_references(scenario_method(method_name))
            )
        pending_methods = [
            ("_capture_fixture_postcondition", dependency)
            for dependency in method_references(projected)
        ]
        while pending_methods:
            caller, method_name = pending_methods.pop()
            if (
                method_name == "_capture_fixture_postcondition"
                or method_name in scoped_method_names
            ):
                continue
            if method_name not in allowed_methods:
                if (caller, method_name) in hidden_method_edges:
                    continue
                raise CaptureEvidenceError(
                    "Capture projected method ownership is incomplete for "
                    f"{label}: {caller} -> {method_name}"
                )
            scoped_method_names.add(method_name)
            pending_methods.extend(
                (method_name, dependency)
                for dependency in method_references(scenario_method(method_name))
            )

        allowed_top_level = set(top_level_inputs)
        pending_top_level = list(top_level_references(projected))
        for method_name in scoped_method_names:
            pending_top_level.extend(
                top_level_references(scenario_method(method_name))
            )
        scoped_top_level_names: set[str] = set()
        while pending_top_level:
            name = pending_top_level.pop()
            if name in scoped_top_level_names:
                continue
            if name not in allowed_top_level:
                raise CaptureEvidenceError(
                    f"Capture projected dependency is unbound for {label}: {name}"
                )
            scoped_top_level_names.add(name)
            pending_top_level.extend(
                top_level_references(scenario_top_level(name))
            )
        scenario.pop("digest", None)
        scenario["method_inputs"] = {
            name: (
                sha256_bytes(
                    ast.dump(
                        scenario_method(name),
                        annotate_fields=True,
                        include_attributes=False,
                    ).encode("utf-8")
                )
                if name in _SCENARIO_LABEL_PATH_METHODS else
                surface_method_hashes[name]
            )
            for name in sorted(scoped_method_names)
        }
        scenario["top_level_inputs"] = {
            name: (
                sha256_bytes(
                    ast.dump(
                        scenario_top_level(name),
                        annotate_fields=True,
                        include_attributes=False,
                    ).encode("utf-8")
                )
                if name in _SCENARIO_LABEL_PATH_TOP_LEVELS else
                top_level_inputs[name]
            )
            for name in sorted(scoped_top_level_names)
        }
        scenario["postcondition_path_digest"] = postcondition_path_digest
        scenario["scenario_reuse_schema_version"] = SCENARIO_REUSE_SCHEMA_VERSION
        results[label] = canonical_json_sha256(scenario)
    return results


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _safe_manifest_path(value: object, root: Path) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    if resolved != root and root not in resolved.parents:
        return None
    return resolved


def _node_source_fragment(node: ast.AST, lines: Sequence[str]) -> bytes:
    decorators = getattr(node, "decorator_list", ())
    start = min(
        [int(getattr(node, "lineno", 1))]
        + [int(getattr(item, "lineno", 1)) for item in decorators]
    )
    end = int(getattr(node, "end_lineno", start))
    return "".join(lines[start - 1 : end]).encode("utf-8")


def _source_without_top_level_definition(source: bytes, name: str) -> bytes:
    """Remove exactly one named top-level definition's UTF-8 AST span."""

    try:
        tree = ast.parse(source.decode("utf-8"))
    except (SyntaxError, UnicodeDecodeError) as error:
        raise CaptureEvidenceError("Renderer source is not parseable") from error
    matches = [
        node for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    ]
    if len(matches) != 1:
        raise CaptureEvidenceError(
            f"Renderer source must contain exactly one top-level {name} definition"
        )
    node = matches[0]
    start_node = min(
        (node, *node.decorator_list),
        key=lambda item: (
            int(getattr(item, "lineno", 1)),
            int(getattr(item, "col_offset", 0)),
        ),
    )
    if not hasattr(node, "end_lineno") or not hasattr(node, "end_col_offset"):
        raise CaptureEvidenceError(
            f"Renderer source span is unavailable for top-level {name}"
        )
    lines = source.splitlines(keepends=True)

    def byte_offset(line_number: int, column: int) -> int:
        if line_number < 1 or line_number > len(lines):
            raise CaptureEvidenceError(
                f"Renderer source span is invalid for top-level {name}"
            )
        line = lines[line_number - 1]
        if column < 0 or column > len(line):
            raise CaptureEvidenceError(
                f"Renderer source span is invalid for top-level {name}"
            )
        return sum(len(value) for value in lines[: line_number - 1]) + column

    start = byte_offset(
        int(getattr(start_node, "lineno", 1)),
        int(getattr(start_node, "col_offset", 0)),
    )
    end = byte_offset(int(node.end_lineno), int(node.end_col_offset))
    if start >= end:
        raise CaptureEvidenceError(
            f"Renderer source span is empty for top-level {name}"
        )
    return source[:start] + source[end:]


def _dashboard_source_fragments(
    source: bytes,
) -> tuple[
    dict[str, bytes],
    dict[str, bytes],
    dict[str, dict[str, bytes]],
]:
    """Return top-level, class-contract, and exact class-method fragments."""

    text = source.decode("utf-8")
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    top_level: dict[str, bytes] = {}
    class_contracts: dict[str, bytes] = {}
    class_methods: dict[str, dict[str, bytes]] = {}
    for node in tree.body:
        names: list[str] = []
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.append(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    names.append(target.id)
        if not names or not hasattr(node, "end_lineno"):
            continue
        fragment = _node_source_fragment(node, lines)
        for name in names:
            top_level[name] = fragment
        if not isinstance(node, ast.ClassDef):
            continue
        methods: dict[str, bytes] = {}
        class_contract_parts: list[bytes] = []
        first_body_line = min(
            (int(getattr(item, "lineno", node.lineno + 1)) for item in node.body),
            default=int(node.end_lineno),
        )
        class_start = min(
            [int(node.lineno)]
            + [int(getattr(item, "lineno", node.lineno)) for item in node.decorator_list]
        )
        class_contract_parts.append(
            "".join(lines[class_start - 1 : first_body_line - 1]).encode("utf-8")
        )
        for member in node.body:
            if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods[member.name] = _node_source_fragment(member, lines)
            else:
                class_contract_parts.append(_node_source_fragment(member, lines))
        class_contracts[node.name] = b"\n".join(class_contract_parts)
        class_methods[node.name] = methods
    return top_level, class_contracts, class_methods


def _literal_assignment(source: bytes, name: str) -> Any:
    tree = ast.parse(source.decode("utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = node.targets
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value = node.value
        else:
            continue
        if any(isinstance(target, ast.Name) and target.id == name for target in targets):
            try:
                return ast.literal_eval(value)
            except (TypeError, ValueError, SyntaxError) as error:
                raise CaptureEvidenceError(
                    f"Capture renderer dependency {name} must be a literal"
                ) from error
    raise CaptureEvidenceError(f"Capture renderer dependency {name} is missing")


def _renderer_method_dependencies(
    *,
    capture_source: bytes,
    labels: Sequence[str],
    renderer_families: Mapping[str, str],
    class_methods: Mapping[str, Mapping[str, bytes]],
    surface_specs: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[
    dict[str, tuple[str, ...]],
    dict[str, tuple[str, ...]],
    frozenset[str],
    frozenset[tuple[str, str]],
    dict[str, frozenset[str]],
    dict[str, tuple[str, ...]],
]:
    """Expand and verify the source-owned per-state method dependency map."""

    if _literal_assignment(capture_source, "CAPTURE_CONTRACT_VERSION") >= 27:
        # Every workspace page now shares one mounted dashboard. Own its whole
        # module and imported renderers rather than maintaining method lists
        # for the retired dialog boundaries. This deliberately broadens
        # invalidation and still binds every production byte used to render it.
        native_labels = frozenset(label for label in labels if renderer_families[label] != "AnkiQt")
        return ({}, {label: () for label in labels}, frozenset(), frozenset(), {"ui/dashboard.py": native_labels}, {})

    groups_raw = _literal_assignment(
        capture_source,
        "CAPTURE_RENDERER_DEPENDENCY_GROUPS",
    )
    shared_raw = _literal_assignment(
        capture_source,
        "CAPTURE_RENDERER_SHARED_CLASS_METHODS",
    )
    state_raw = _literal_assignment(
        capture_source,
        "CAPTURE_RENDERER_STATE_CLASS_METHODS",
    )
    hidden_calls_raw = _literal_assignment(
        capture_source,
        "CAPTURE_RENDERER_HIDDEN_CALL_EXCEPTIONS",
    )
    exact_module_owners_raw = _literal_assignment(
        capture_source,
        "CAPTURE_RENDERER_EXACT_MODULE_OWNERS",
    )
    family_bases_raw = _literal_assignment(
        capture_source,
        "CAPTURE_RENDERER_FAMILY_BASES",
    )
    exhaustive_groups = _literal_assignment(
        capture_source,
        "EXHAUSTIVE_CAPTURE_FACE_GROUPS",
    )
    if not all(
        isinstance(value, dict)
        for value in (
            groups_raw,
            shared_raw,
            state_raw,
            hidden_calls_raw,
            exact_module_owners_raw,
            family_bases_raw,
        )
    ):
        raise CaptureEvidenceError("Capture renderer dependency declarations are malformed")
    exhaustive_labels = {
        str(label)
        for _group_name, group_labels in exhaustive_groups
        for label in group_labels
    }
    active_labels = tuple(str(label) for label in labels)
    active_set = set(active_labels)
    known_labels = exhaustive_labels | active_set
    def resolve_selectors(
        owner: str,
        raw_selectors: Any,
    ) -> tuple[str, ...]:
        if not isinstance(raw_selectors, (tuple, list)):
            raise CaptureEvidenceError(
                f"Renderer dependency selector owner {owner} must be a sequence"
            )
        resolved_labels: list[str] = []
        for raw_selector in raw_selectors:
            selector = str(raw_selector)
            if selector.startswith("label:"):
                declared = selector.removeprefix("label:")
                if declared not in known_labels:
                    raise CaptureEvidenceError(
                        f"Renderer dependency owner {owner} names unknown label {declared}"
                    )
                matches = [declared] if declared in active_set else []
            elif selector.startswith("prefix:"):
                prefix = selector.removeprefix("prefix:")
                if not prefix or not any(
                    label.startswith(prefix) for label in known_labels
                ):
                    raise CaptureEvidenceError(
                        f"Renderer dependency owner {owner} has invalid prefix {prefix!r}"
                    )
                matches = [label for label in active_labels if label.startswith(prefix)]
            elif selector.startswith("family:"):
                family = selector.removeprefix("family:")
                if not family:
                    raise CaptureEvidenceError(
                        f"Renderer dependency owner {owner} has an empty family"
                    )
                matches = [
                    label for label in active_labels
                    if renderer_families.get(label) == family
                ]
            else:
                raise CaptureEvidenceError(
                    f"Renderer dependency selector is unsupported: {selector!r}"
                )
            resolved_labels.extend(matches)
        return tuple(dict.fromkeys(resolved_labels))

    if surface_specs is None:
        groups: dict[str, tuple[str, ...]] = {
            str(raw_name): resolve_selectors(str(raw_name), raw_selectors)
            for raw_name, raw_selectors in groups_raw.items()
        }
        exact_owner_rows = {
            str(raw_entry): frozenset(
                resolve_selectors(str(raw_entry), raw_selectors)
            )
            for raw_entry, raw_selectors in exact_module_owners_raw.items()
        }
    else:
        if set(surface_specs) != active_set:
            raise CaptureEvidenceError(
                "SurfaceSpec dependency metadata does not cover active labels"
            )
        groups = {
            str(group_name): tuple(
                label for label in active_labels
                if str(group_name) in tuple(
                    str(value) for value in surface_specs[label].get(
                        "owned_dependency_groups", ()
                    )
                )
            )
            for group_name in state_raw
        }
        exact_entries = tuple(dict.fromkeys(
            str(entry)
            for label in active_labels
            for entry in surface_specs[label].get(
                "owned_module_dependencies", ()
            )
        ))
        exact_owner_rows = {
            entry: frozenset(
                label for label in active_labels
                if entry in tuple(
                    str(value) for value in surface_specs[label].get(
                        "owned_module_dependencies", ()
                    )
                )
            )
            for entry in exact_entries
        }
    exact_module_owners: dict[str, frozenset[str]] = {}
    for raw_entry, resolved_owners in exact_owner_rows.items():
        entry = str(raw_entry)
        if not entry.endswith(".py") or entry.startswith("/") or ".." in Path(entry).parts:
            raise CaptureEvidenceError(
                f"Exact renderer module entry is invalid: {entry!r}"
            )
        exact_module_owners[entry] = frozenset(resolved_owners)

    family_bases: dict[str, tuple[str, ...]] = {}
    for raw_family, raw_bases in family_bases_raw.items():
        family = str(raw_family).strip()
        if not family or not isinstance(raw_bases, (tuple, list)):
            raise CaptureEvidenceError(
                f"Renderer family bases for {raw_family!r} are malformed"
            )
        bases = tuple(str(base).strip() for base in raw_bases)
        if not bases or any(not base for base in bases) or len(set(bases)) != len(bases):
            raise CaptureEvidenceError(
                f"Renderer family bases for {family!r} must be unique class names"
            )
        family_bases[family] = bases

    shared: dict[str, tuple[str, ...]] = {}
    declared_method_keys: set[str] = set()
    audited_classes: set[str] = set()
    for raw_class, raw_methods in shared_raw.items():
        class_name = str(raw_class)
        audited_classes.add(class_name)
        if not isinstance(raw_methods, (tuple, list)):
            raise CaptureEvidenceError(
                f"Shared renderer methods for {class_name} must be a sequence"
            )
        methods = tuple(str(method) for method in raw_methods)
        if len(set(methods)) != len(methods):
            raise CaptureEvidenceError(
                f"Shared renderer methods for {class_name} contain duplicates"
            )
        shared[class_name] = methods
        declared_method_keys.update(f"{class_name}.{method}" for method in methods)

    state_by_label: dict[str, list[str]] = {label: [] for label in active_labels}
    for raw_group, raw_method_keys in state_raw.items():
        group_name = str(raw_group)
        if group_name not in groups:
            raise CaptureEvidenceError(
                f"Renderer state methods reference unknown group {group_name}"
            )
        if not isinstance(raw_method_keys, (tuple, list)):
            raise CaptureEvidenceError(
                f"Renderer state methods for {group_name} must be a sequence"
            )
        for raw_key in raw_method_keys:
            key = str(raw_key)
            if "." not in key:
                raise CaptureEvidenceError(f"Renderer method key is invalid: {key!r}")
            class_name, method_name = key.split(".", 1)
            audited_classes.add(class_name)
            declared_method_keys.add(key)
            if method_name not in class_methods.get(class_name, {}):
                raise CaptureEvidenceError(
                    f"Renderer method dependency is missing from ui/dashboard.py: {key}"
                )
            for label in groups[group_name]:
                state_by_label[label].append(key)

    for class_name in sorted(audited_classes):
        actual = {
            f"{class_name}.{method}"
            for method in class_methods.get(class_name, {})
        }
        if not actual:
            raise CaptureEvidenceError(
                f"Audited renderer class is missing from ui/dashboard.py: {class_name}"
            )
        declared = {
            key for key in declared_method_keys if key.startswith(f"{class_name}.")
        }
        missing = sorted(actual - declared)
        extra = sorted(declared - actual)
        if missing or extra:
            details = []
            if missing:
                details.append("unmapped/new=" + ",".join(missing))
            if extra:
                details.append("missing=" + ",".join(extra))
            raise CaptureEvidenceError(
                f"Renderer method map for {class_name} is not closed: "
                + "; ".join(details)
            )
    for family, base_classes in sorted(family_bases.items()):
        missing_bases = sorted(
            base for base in base_classes
            if base not in audited_classes or base not in class_methods
        )
        if missing_bases:
            raise CaptureEvidenceError(
                f"Renderer family {family} has unaudited base classes: "
                + ", ".join(missing_bases)
            )
    hidden_call_exceptions: set[tuple[str, str]] = set()
    for raw_caller, raw_callees in hidden_calls_raw.items():
        caller = str(raw_caller)
        if not isinstance(raw_callees, (tuple, list)):
            raise CaptureEvidenceError(
                f"Hidden renderer calls for {caller} must be a sequence"
            )
        if "." not in caller:
            raise CaptureEvidenceError(f"Hidden renderer caller is invalid: {caller}")
        caller_class, caller_method = caller.split(".", 1)
        caller_fragment = class_methods.get(caller_class, {}).get(caller_method)
        if caller_fragment is None:
            raise CaptureEvidenceError(f"Hidden renderer caller is missing: {caller}")
        method_references = _same_class_method_references(
            caller_fragment,
            class_name=caller_class,
            available_methods=class_methods.get(caller_class, {}),
        )
        for raw_callee in raw_callees:
            callee = str(raw_callee)
            if "." not in callee:
                raise CaptureEvidenceError(
                    f"Hidden renderer callee is invalid: {callee}"
                )
            callee_class, callee_method = callee.split(".", 1)
            if (
                callee_class != caller_class
                or callee_method not in method_references
                or callee_method not in class_methods.get(callee_class, {})
            ):
                raise CaptureEvidenceError(
                    f"Hidden renderer edge is not a same-class method reference: "
                    f"{caller} -> {callee}"
                )
            hidden_call_exceptions.add((caller, callee))
    return (
        shared,
        {
            label: tuple(dict.fromkeys(state_by_label[label]))
            for label in active_labels
        },
        frozenset(audited_classes),
        frozenset(hidden_call_exceptions),
        exact_module_owners,
        family_bases,
    )


def _fragment_references(
    fragment: bytes,
    *,
    class_name: str = "",
) -> tuple[set[str], set[str]]:
    """Return loaded global names and same-class method references."""

    try:
        tree = ast.parse(textwrap.dedent(fragment.decode("utf-8")))
    except (SyntaxError, UnicodeDecodeError) as error:
        raise CaptureEvidenceError("Renderer source fragment is not parseable") from error
    class _RuntimeNameVisitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.names: set[str] = set()

        def visit_Name(self, node: ast.Name) -> None:  # noqa: N802
            if isinstance(node.ctx, ast.Load):
                self.names.add(node.id)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
            for decorator in node.decorator_list:
                self.visit(decorator)
            for default in (*node.args.defaults, *node.args.kw_defaults):
                if default is not None:
                    self.visit(default)
            for statement in node.body:
                self.visit(statement)

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: N802
            self.visit(node.target)
            if node.value is not None:
                self.visit(node.value)

    visitor = _RuntimeNameVisitor()
    visitor.visit(tree)
    names = visitor.names
    self_methods = {
        node.func.attr
        for node in ast.walk(tree)
        if (
            class_name
            and isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in {"self", "cls"}
        )
    }
    return names, self_methods


def _same_class_method_references(
    fragment: bytes,
    *,
    class_name: str,
    available_methods: Mapping[str, bytes],
) -> set[str]:
    """Return every ``self``/``cls`` method reference, calls or callbacks."""

    try:
        tree = ast.parse(textwrap.dedent(fragment.decode("utf-8")))
    except (SyntaxError, UnicodeDecodeError) as error:
        raise CaptureEvidenceError("Renderer source fragment is not parseable") from error
    if not class_name:
        return set()
    available = set(available_methods)
    return {
        node.attr
        for node in ast.walk(tree)
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in {"self", "cls"}
            and node.attr in available
        )
    }


def _expanded_dashboard_fragment_closure(
    *,
    root_symbols: Iterable[str],
    root_method_keys: Iterable[str],
    top_level: Mapping[str, bytes],
    class_contracts: Mapping[str, bytes],
    class_methods: Mapping[str, Mapping[str, bytes]],
    shared_class_methods: Mapping[str, Sequence[str]],
    audited_classes: frozenset[str],
    hidden_call_exceptions: frozenset[tuple[str, str]],
) -> tuple[dict[str, bytes], set[str], set[str]]:
    """Recursively close mapped fragments over globals and ``self`` calls."""

    pending: list[tuple[str, str]] = []
    for symbol in root_symbols:
        if symbol in audited_classes:
            pending.append(("class", symbol))
            pending.extend(
                ("method", f"{symbol}.{method}")
                for method in shared_class_methods.get(symbol, ())
            )
        else:
            pending.append(("top", str(symbol)))
    for raw_key in root_method_keys:
        key = str(raw_key)
        if "." in key:
            class_name, _method_name = key.split(".", 1)
            # A state-owned class method also owns the class header, bases,
            # signals, and non-method body declarations that establish the
            # widget contract.  This is normally already present through a
            # family root; narrow state-only widgets (for example the selected
            # plant card) depend on this explicit edge.
            if (
                class_name in audited_classes
                and class_name not in shared_class_methods
            ):
                pending.append(("class", class_name))
        pending.append(("method", key))
    fragments: dict[str, bytes] = {}
    loaded_names: set[str] = set()
    resolved_top_names: set[str] = set()
    seen: set[tuple[str, str]] = set()
    while pending:
        kind, key = pending.pop(0)
        token = (kind, key)
        if token in seen:
            continue
        seen.add(token)
        class_name = ""
        if kind == "top":
            fragment = top_level.get(key)
            output_key = key
            resolved_top_names.add(key)
        elif kind == "class":
            fragment = class_contracts.get(key)
            output_key = f"{key}.__class_contract__"
        else:
            if "." not in key:
                fragment = None
            else:
                class_name, method_name = key.split(".", 1)
                fragment = class_methods.get(class_name, {}).get(method_name)
            output_key = key
        if fragment is None:
            raise CaptureEvidenceError(
                f"Declared renderer fragment is missing from ui/dashboard.py: {key}"
            )
        fragments[output_key] = fragment
        # Class headers without executable body are not standalone Python.
        # Their base/decorator names are already source-owned by the manual
        # class root; method/global closures cover pixel-producing call sites.
        if kind == "class":
            continue
        names, self_methods = _fragment_references(
            fragment,
            class_name=class_name,
        )
        loaded_names.update(names)
        for name in sorted(names):
            if name not in top_level:
                continue
            # Top-level classes are state roots owned by the family map. Large
            # dashboards eagerly construct hidden dialogs, so recursively
            # following every class name would bind their offscreen pages to
            # the visible canvas. Unmapped/new classes remain in the global
            # fail-closed digest below; functions/constants close recursively.
            if name in class_methods:
                continue
            pending.append(("top", name))
        if class_name:
            available = class_methods.get(class_name, {})
            pending.extend(
                ("method", f"{class_name}.{method}")
                for method in sorted(self_methods)
                if (
                    method in available
                    and (
                        key,
                        f"{class_name}.{method}",
                    ) not in hidden_call_exceptions
                )
            )
    return fragments, loaded_names, resolved_top_names


def _audit_renderer_method_reference_ownership(
    *,
    fragment_closures: Mapping[str, Mapping[str, bytes]],
    class_methods: Mapping[str, Mapping[str, bytes]],
    hidden_reference_exceptions: frozenset[tuple[str, str]],
) -> None:
    """Fail closed when a callback can bypass its callee's label owners.

    Direct calls already close recursively. Signal, timer, and other callback
    references are safe only when every face that owns the caller also owns
    the callee, or when the source contract explicitly classifies the edge as
    interaction-only/offscreen for those additional faces.
    """

    owners: dict[str, set[str]] = {}
    for label, fragments in fragment_closures.items():
        for key in fragments:
            if "." not in key or key.endswith(".__class_contract__"):
                continue
            owners.setdefault(key, set()).add(str(label))

    for caller, caller_labels in sorted(owners.items()):
        class_name, method_name = caller.split(".", 1)
        fragment = class_methods.get(class_name, {}).get(method_name)
        if fragment is None:
            raise CaptureEvidenceError(
                f"Renderer ownership references missing method {caller}"
            )
        for callee_method in sorted(_same_class_method_references(
            fragment,
            class_name=class_name,
            available_methods=class_methods.get(class_name, {}),
        )):
            callee = f"{class_name}.{callee_method}"
            missing = sorted(caller_labels - owners.get(callee, set()))
            if not missing or (caller, callee) in hidden_reference_exceptions:
                continue
            raise CaptureEvidenceError(
                "Renderer method reference is not closed over its pixel owners: "
                f"{caller} -> {callee}; unmapped labels=" + ",".join(missing)
            )


def _renderer_class_owners(
    fragment_closures: Mapping[str, Mapping[str, bytes]],
) -> dict[str, list[str]]:
    """Return the exact labels that own each mapped class contract."""

    owners: dict[str, set[str]] = {}
    for label, fragments in fragment_closures.items():
        for key in fragments:
            suffix = ".__class_contract__"
            if key.endswith(suffix):
                owners.setdefault(key.removesuffix(suffix), set()).add(str(label))
    return {
        class_name: sorted(labels)
        for class_name, labels in sorted(owners.items())
    }


def _renderer_fragment_owners(
    fragment_closures: Mapping[str, Mapping[str, bytes]],
) -> dict[str, list[str]]:
    """Return the exact labels that own each dashboard source fragment."""

    owners: dict[str, set[str]] = {}
    for label, fragments in fragment_closures.items():
        for key in fragments:
            owners.setdefault(str(key), set()).add(str(label))
    return {
        key: sorted(labels)
        for key, labels in sorted(owners.items())
    }


def _renderer_ownership_proof(
    *,
    production_archive_sha256: str,
    dashboard_source: bytes,
    dashboard_fragments: Mapping[str, bytes],
    dashboard_class_methods: Mapping[str, Mapping[str, bytes]],
    audited_classes: Iterable[str],
    hidden_call_exceptions: Iterable[tuple[str, str]],
    unmapped_top_level: Mapping[str, str],
    fragment_closures: Mapping[str, Mapping[str, bytes]],
) -> dict[str, Any]:
    """Seal the AST ownership facts needed for narrow migrations."""

    payload: dict[str, Any] = {
        "schema_version": RENDERER_OWNERSHIP_REUSE_SCHEMA_VERSION,
        "production_archive_sha256": str(production_archive_sha256),
        "dashboard_entry_sha256": sha256_bytes(dashboard_source),
        "dashboard_without_plant_info_card_sha256": sha256_bytes(
            _source_without_top_level_definition(
                dashboard_source,
                "PlantInfoCard",
            )
        ),
        "top_level_digests": {
            name: sha256_bytes(fragment)
            for name, fragment in sorted(dashboard_fragments.items())
        },
        "method_digests": {
            f"{class_name}.{method_name}": sha256_bytes(fragment)
            for class_name in sorted(audited_classes)
            for method_name, fragment in sorted(
                dashboard_class_methods.get(class_name, {}).items()
            )
        },
        "audited_classes": sorted(str(value) for value in audited_classes),
        "unmapped_top_level_digests": dict(sorted(unmapped_top_level.items())),
        "unmapped_top_level_digest": canonical_json_sha256(
            dict(sorted(unmapped_top_level.items()))
        ),
        "class_owners": _renderer_class_owners(fragment_closures),
        "fragment_owners": _renderer_fragment_owners(fragment_closures),
        "hidden_call_exceptions": [
            [str(caller), str(callee)]
            for caller, callee in sorted(hidden_call_exceptions)
        ],
    }
    payload["digest"] = canonical_json_sha256(payload)
    return payload


def _renderer_ownership_proof_is_consistent(
    proof: object,
    *,
    expected_labels: Iterable[str] = (),
) -> bool:
    if not isinstance(proof, dict):
        return False
    normalized = copy.deepcopy(proof)
    digest = normalized.pop("digest", None)
    if (
        normalized.get("schema_version")
        != RENDERER_OWNERSHIP_REUSE_SCHEMA_VERSION
        or not isinstance(digest, str)
        or SHA256_RE.fullmatch(digest) is None
        or canonical_json_sha256(normalized) != digest
    ):
        return False
    for field in (
        "production_archive_sha256",
        "dashboard_entry_sha256",
        "dashboard_without_plant_info_card_sha256",
    ):
        value = normalized.get(field)
        if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
            return False
    top_level = normalized.get("top_level_digests")
    method_digests = normalized.get("method_digests")
    unmapped = normalized.get("unmapped_top_level_digests")
    audited = normalized.get("audited_classes")
    owners = normalized.get("class_owners")
    fragment_owners = normalized.get("fragment_owners")
    hidden_call_exceptions = normalized.get("hidden_call_exceptions")
    if (
        not isinstance(top_level, dict)
        or not isinstance(method_digests, dict)
        or not isinstance(unmapped, dict)
        or not isinstance(audited, list)
        or not isinstance(owners, dict)
        or not isinstance(fragment_owners, dict)
        or not isinstance(hidden_call_exceptions, list)
        or any(
            not isinstance(name, str)
            or not isinstance(value, str)
            or SHA256_RE.fullmatch(value) is None
            for name, value in top_level.items()
        )
        or any(
            not isinstance(name, str)
            or "." not in name
            or not isinstance(value, str)
            or SHA256_RE.fullmatch(value) is None
            for name, value in method_digests.items()
        )
        or any(
            name not in top_level or top_level.get(name) != value
            for name, value in unmapped.items()
        )
        or len(audited) != len(set(audited))
        or any(not isinstance(name, str) or not name for name in audited)
        or canonical_json_sha256(dict(sorted(unmapped.items())))
        != normalized.get("unmapped_top_level_digest")
    ):
        return False
    allowed_labels = {str(value) for value in expected_labels}
    for class_name, raw_labels in owners.items():
        if (
            not isinstance(class_name, str)
            or class_name not in audited
            or not isinstance(raw_labels, list)
            or len(raw_labels) != len(set(raw_labels))
            or any(not isinstance(label, str) or not label for label in raw_labels)
            or (allowed_labels and not set(raw_labels) <= allowed_labels)
        ):
            return False
    for fragment, raw_labels in fragment_owners.items():
        if (
            not isinstance(fragment, str)
            or not fragment
            or not isinstance(raw_labels, list)
            or len(raw_labels) != len(set(raw_labels))
            or raw_labels != sorted(raw_labels)
            or any(not isinstance(label, str) or not label for label in raw_labels)
            or (allowed_labels and not set(raw_labels) <= allowed_labels)
        ):
            return False
    normalized_edges: list[tuple[str, str]] = []
    for raw_edge in hidden_call_exceptions:
        if (
            not isinstance(raw_edge, list)
            or len(raw_edge) != 2
            or any(not isinstance(value, str) or not value for value in raw_edge)
        ):
            return False
        edge = (raw_edge[0], raw_edge[1])
        if edge[0] not in method_digests or edge[1] not in method_digests:
            return False
        normalized_edges.append(edge)
    if (
        len(normalized_edges) != len(set(normalized_edges))
        or normalized_edges != sorted(normalized_edges)
    ):
        return False
    return True


def _reconstruct_renderer_ownership_proof(
    *,
    capture_source: bytes,
    dashboard_source: bytes,
    labels: Sequence[str],
    renderer_families: Mapping[str, str],
    production_archive_sha256: str,
) -> dict[str, Any]:
    """Rebuild historical renderer ownership from sealed source bytes."""

    (
        dashboard_fragments,
        dashboard_class_contracts,
        dashboard_class_methods,
    ) = _dashboard_source_fragments(dashboard_source)
    (
        shared_class_methods,
        state_methods_by_label,
        audited_classes,
        hidden_call_exceptions,
        _exact_module_owners,
        family_bases,
    ) = _renderer_method_dependencies(
        capture_source=capture_source,
        labels=labels,
        renderer_families=renderer_families,
        class_methods=dashboard_class_methods,
    )
    all_root_symbols = set(_DASHBOARD_COMMON_SYMBOLS)
    for values in _DASHBOARD_FAMILY_SYMBOLS.values():
        all_root_symbols.update(values)
    for values in family_bases.values():
        all_root_symbols.update(values)
    all_method_keys = {
        f"{class_name}.{method_name}"
        for class_name in audited_classes
        for method_name in dashboard_class_methods.get(class_name, {})
    }
    _all_fragments, _all_loaded, classified_top_level = (
        _expanded_dashboard_fragment_closure(
            root_symbols=all_root_symbols,
            root_method_keys=all_method_keys,
            top_level=dashboard_fragments,
            class_contracts=dashboard_class_contracts,
            class_methods=dashboard_class_methods,
            shared_class_methods=shared_class_methods,
            audited_classes=audited_classes,
            hidden_call_exceptions=hidden_call_exceptions,
        )
    )
    unmapped_top_level = {
        name: sha256_bytes(dashboard_fragments[name])
        for name in sorted(set(dashboard_fragments) - classified_top_level)
        if name not in audited_classes
    }
    fragment_closures: dict[str, dict[str, bytes]] = {}
    for label in labels:
        family = str(renderer_families.get(label, ""))
        symbols = (
            _DASHBOARD_FAMILY_SYMBOLS.get(family, frozenset())
            | frozenset(family_bases.get(family, ()))
        )
        if family != "AnkiQt":
            symbols = _DASHBOARD_COMMON_SYMBOLS | symbols
        closure, _loaded, _resolved = _expanded_dashboard_fragment_closure(
            root_symbols=symbols,
            root_method_keys=state_methods_by_label.get(label, ()),
            top_level=dashboard_fragments,
            class_contracts=dashboard_class_contracts,
            class_methods=dashboard_class_methods,
            shared_class_methods=shared_class_methods,
            audited_classes=audited_classes,
            hidden_call_exceptions=hidden_call_exceptions,
        )
        fragment_closures[str(label)] = closure
    _audit_renderer_method_reference_ownership(
        fragment_closures=fragment_closures,
        class_methods=dashboard_class_methods,
        hidden_reference_exceptions=hidden_call_exceptions,
    )
    return _renderer_ownership_proof(
        production_archive_sha256=production_archive_sha256,
        dashboard_source=dashboard_source,
        dashboard_fragments=dashboard_fragments,
        dashboard_class_methods=dashboard_class_methods,
        audited_classes=audited_classes,
        hidden_call_exceptions=hidden_call_exceptions,
        unmapped_top_level=unmapped_top_level,
        fragment_closures=fragment_closures,
    )


def _entry_module_name(entry: str) -> str:
    if not entry.endswith(".py"):
        return ""
    value = entry[:-3].replace("/", ".")
    return value


def _module_entry_candidates(module_name: str) -> tuple[str, ...]:
    stem = module_name.replace(".", "/")
    return (f"{stem}.py", f"{stem}/__init__.py")


def _resolve_local_module_entry(
    module_name: str,
    entries: Mapping[str, str],
) -> str | None:
    normalized = module_name.removeprefix("ankigarden.")
    for candidate in _module_entry_candidates(normalized):
        if candidate in entries:
            return candidate
    return None


def _module_import_bindings(
    *,
    entry: str,
    source: str,
    entries: Mapping[str, str],
    include_nested: bool = False,
) -> tuple[dict[str, str], set[str]]:
    """Map module-scope local imports, tracking unresolved local bindings.

    Function-local lazy imports belong to the exact callable that executes
    them. Following every lazy import from a whole module would, for example,
    bind every ``GameEngine`` consumer to the reviewer-only reward projection.
    Those call-site dependencies are source-owned by the per-label renderer
    map (and its fail-closed audit) instead of being widened here.
    """

    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        raise CaptureEvidenceError(f"Packaged Python module is invalid: {entry}") from error
    current = _entry_module_name(entry).split(".")
    bindings: dict[str, str] = {}
    unresolved: set[str] = set()
    class _ModuleImportVisitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.imports: list[ast.Import | ast.ImportFrom] = []

        def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
            self.imports.append(node)

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
            self.imports.append(node)

        # Imports under module-level try/if blocks remain module-scope, while
        # imports inside callables/classes are owned by their call closures.
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
            if include_nested:
                self.generic_visit(node)
            return

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
            if include_nested:
                self.generic_visit(node)
            return

        def visit_Lambda(self, node: ast.Lambda) -> None:  # noqa: N802
            if include_nested:
                self.generic_visit(node)
            return

    import_visitor = _ModuleImportVisitor()
    import_visitor.visit(tree)
    for node in import_visitor.imports:
        if isinstance(node, ast.ImportFrom):
            if node.level:
                base_parts = current[:-node.level]
                if node.module:
                    base_parts.extend(node.module.split("."))
                module_name = ".".join(base_parts)
                local_import = True
            else:
                module_name = str(node.module or "")
                local_import = module_name == "ankigarden" or module_name.startswith(
                    "ankigarden."
                )
            base_entry = _resolve_local_module_entry(module_name, entries)
            for alias in node.names:
                binding = alias.asname or alias.name
                target = base_entry
                if target is None:
                    child_name = ".".join(
                        part for part in (module_name, alias.name) if part
                    )
                    target = _resolve_local_module_entry(child_name, entries)
                if target is not None:
                    bindings[binding] = target
                elif local_import:
                    unresolved.add(binding)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                target = _resolve_local_module_entry(alias.name, entries)
                if target is not None:
                    bindings[alias.asname or alias.name.split(".", 1)[0]] = target
    return bindings, unresolved


def _used_local_import_targets(
    *,
    entry: str,
    source: str,
    entries: Mapping[str, str],
) -> frozenset[str]:
    """Resolve local imports used anywhere in one mapped render fragment."""

    normalized_source = textwrap.dedent(source)
    bindings, unresolved = _module_import_bindings(
        entry=entry,
        source=normalized_source,
        entries=entries,
        include_nested=True,
    )
    loaded, _self_methods = _fragment_references(normalized_source.encode("utf-8"))
    unresolved_used = sorted(unresolved & loaded)
    if unresolved_used:
        raise CaptureEvidenceError(
            f"Mapped renderer fragment {entry} has unresolved local imports: "
            + ", ".join(unresolved_used)
        )
    return frozenset(
        target for binding, target in bindings.items()
        if binding in loaded
    )


def _module_dependency_closure(
    *,
    entries: Mapping[str, str],
    roots: Iterable[str],
) -> frozenset[str]:
    """Close whole renderer modules over every referenced local import."""

    pending = list(dict.fromkeys(str(root) for root in roots))
    closure: set[str] = set()
    while pending:
        entry = pending.pop(0)
        if entry in closure:
            continue
        source = entries.get(entry)
        if source is None:
            raise CaptureEvidenceError(
                f"Renderer module dependency is absent from the archive: {entry}"
            )
        closure.add(entry)
        if not entry.endswith(".py"):
            continue
        bindings, unresolved = _module_import_bindings(
            entry=entry,
            source=source,
            entries=entries,
        )
        loaded, _self_methods = _fragment_references(source.encode("utf-8"))
        unresolved_used = sorted(unresolved & loaded)
        if unresolved_used:
            raise CaptureEvidenceError(
                f"Renderer module {entry} has unresolved local imports: "
                + ", ".join(unresolved_used)
            )
        pending.extend(
            target
            for binding, target in sorted(bindings.items())
            if binding in loaded and target not in closure
        )
    return frozenset(closure)


_DASHBOARD_COMMON_SYMBOLS = frozenset({
    "UI_TEXT",
    "_FocusTooltipFilter",
    "_set_focus_accessible_tooltip",
    "ElidingLabel",
    "set_button_size",
    "_set_button_variant",
    "_set_compact_row_action",
    "DialogShell",
    "GardenDialogHeader",
    "GardenDialogFooter",
    "GardenButton",
    "GardenIconButton",
    "GardenDialog",
    "_garden_dialog_stylesheet",
    "ToastRegion",
    "apply_explanatory_tooltip",
    "GardenImageFrame",
    "ArtworkThumbnail",
    "_button_stylesheet",
    "GardenTabs",
    "SectionCard",
    "GardenBadge",
    "GardenStatusBanner",
    "EmptyState",
    "ActionFooter",
})

_DASHBOARD_FAMILY_SYMBOLS: dict[str, frozenset[str]] = {
    # Anki home/reviewer faces are rendered by packaged home/reviewer modules,
    # not by the dialog module's GardenDashboard class.
    "AnkiQt": frozenset(),
    "GardenDashboard": frozenset({
        "GardenDashboard",
        "GardenPlantSummary",
        "GardenSceneOverlay",
        "GardenPopover",
        "GardenStatsStrip",
        "RearrangeBar",
        "GardenSideNavigation",
    }),
    "GardenProgressDialog": frozenset({
        "GardenProgressDialog",
        "_TabbedProgressShell",
        "LabeledProgress",
        "ProgressBar",
        "ProgressRow",
        "ProgressCardGrid",
        "ResponsiveTileGrid",
        "CollectionFilterControls",
        "DataTable",
    }),
    "GardenSettingsDialog": frozenset({
        "GardenSettingsDialog",
        "ToggleSwitch",
    }),
    "NurseryDialog": frozenset({
        "NurseryDialog",
        "_CompleteCatalogViewportGuard",
        "ResponsiveTileGrid",
        "ResponsiveActionCard",
        "GardenOutcomePreview",
        "_asset_preview_label",
        "_item_preview_label",
        "_missing_artwork_pixmap",
        "_environment_preview_pixmap",
        "_garden_bed_purchase_preview",
    }),
    "CollectibleDetailDialog": frozenset({
        "CollectibleDetailDialog",
        "CollectionFilterControls",
        "ResponsiveSplit",
    }),
    "FertilizerDialog": frozenset({
        "FertilizerStatusBlock",
    }),
    "FertilizerReplacementDialog": frozenset({
        "FertilizerReplacementDialog",
        "ConfirmationDialog",
        "GardenOutcomePreview",
    }),
    "PlantStoryDialog": frozenset({"PlantStoryDialog", "MemoryTimeline"}),
    # The species dialog is constructed directly as a GardenDialog by the
    # mapped GardenDashboard builder. It does not render GardenDetailsDialog;
    # binding that class would drag unrelated Progress reward projections into
    # the species evidence digest.
    "SpeciesOverviewDialog": frozenset({"_CompleteSectionBoundaryGuard"}),
    "PurchaseConfirmationDialog": frozenset({
        "PurchaseConfirmationDialog",
        "ConfirmationDialog",
        "GardenOutcomePreview",
    }),
    "GrowthChargeConfirmationDialog": frozenset({
        "GrowthChargeConfirmationDialog",
        "GardenOutcomePreview",
    }),
}


def _label_bucket(label: str, renderer_family: str = "") -> str:
    """Return the complete active-surface dependency family."""

    if label.startswith("starter-"):
        return "starter"
    if renderer_family == "AnkiQt":
        return (
            "settings-transactions"
            if label.startswith("reviewer-")
            else "home-garden"
        )
    if renderer_family in {
        "GardenDashboard",
        "FertilizerDialog",
        "FertilizerReplacementDialog",
        "PlantStoryDialog",
    }:
        return "home-garden"
    if renderer_family == "GardenProgressDialog":
        return "progress"
    if renderer_family in {
        "NurseryDialog",
        "CollectibleDetailDialog",
        "SpeciesOverviewDialog",
    }:
        return "collection-nursery"
    return "settings-transactions"


def _entry_buckets(name: str) -> frozenset[str] | None:
    """Return affected buckets; None means global/fail-safe impact."""

    global_entries = {
        "__init__.py",
        "addon.py",
        "build_capabilities.py",
        "config.py",
        "config.json",
        "display_telemetry.py",
        "manifest.json",
        "terminology.py",
        "ui/__init__.py",
        "ui/accessibility.py",
        "ui/copy.py",
        "ui/formatters.py",
        "ui/icons.py",
        "ui/responsive.py",
        "ui/state.py",
        "ui/state_contracts.py",
        "assets/manifest.json",
    }
    if name in global_entries:
        return None
    if name in {"ui/dialog_foundations.py", "ui/theme.py"}:
        # These renderer modules are included only when a surface's mapped
        # dashboard/module dependency closure actually imports them. Treating
        # either file as a global fallback invalidates unrelated Anki-owned
        # Home and Reviewer pixels even though those renderers do not consume
        # the dialog/theme implementation. Missing or unresolved ownership
        # still fails closed in the module-closure audit below.
        return frozenset()
    if name == "ui/dashboard.py":
        return frozenset()
    if name.startswith("assets/v6_storybook_gouache/plants/"):
        return frozenset({"starter", "home-garden", "collection-nursery"})
    if name.startswith("assets/v6_storybook_gouache/backgrounds/"):
        return frozenset({"home-garden", "collection-nursery"})
    if name.startswith("assets/v6_storybook_gouache/ui/"):
        return frozenset({"home-garden", "collection-nursery", "settings-transactions"})
    if name.startswith("assets/support/"):
        return frozenset({"home-garden", "collection-nursery"})
    exact: dict[str, frozenset[str]] = {
        "achievements.py": frozenset({"progress", "settings-transactions"}),
        "collectibles.py": frozenset({"collection-nursery"}),
        "environment.py": frozenset({"home-garden", "collection-nursery"}),
        "game.py": frozenset({"starter", "home-garden", "progress", "collection-nursery"}),
        "garden_finds.py": frozenset({"settings-transactions"}),
        "growth.py": frozenset({"home-garden", "progress", "settings-transactions"}),
        "purchases.py": frozenset({"home-garden", "collection-nursery", "settings-transactions"}),
        "reward_ledger.py": frozenset({"progress", "settings-transactions"}),
        "reward_presentation.py": frozenset({"settings-transactions"}),
        "ui/garden_studio.py": frozenset({"home-garden"}),
        "ui/home_widget.py": frozenset({"starter", "home-garden"}),
        "ui/landmarks.py": frozenset({"home-garden"}),
        "ui/plant_display.py": frozenset({"starter", "home-garden", "collection-nursery"}),
        "ui/plant_presenters.py": frozenset({"starter", "home-garden", "collection-nursery"}),
        "ui/scene.py": frozenset({"home-garden"}),
        "hooks/reviewer.py": frozenset({"settings-transactions"}),
    }
    if name in exact:
        return exact[name]
    if name.startswith("models/") or name in {"storage.py", "asset_manager.py"}:
        return None
    # Unknown payloads are deliberately global. A new packaged file can never
    # slip past reuse merely because no impact rule has been written for it.
    return None


def _entry_affects_surface(
    name: str,
    *,
    label: str,
    renderer_family: str,
    bucket: str,
) -> bool:
    """Return label-aware packaged-file impact without weakening fail-closed defaults."""

    settings_preview = (
        label.startswith("settings-display")
        or label in {
            "settings-unsaved-changes",
            "settings-validation-error",
            "reduced-motion-enabled",
        }
    )
    if name == "ui/dashboard.py":
        return False
    if name == "ui/home_widget.py":
        return renderer_family == "AnkiQt" and not label.startswith("reviewer-")
    if name == "ui/garden_studio.py":
        return settings_preview
    if name in {
        "hooks/reviewer.py",
    }:
        return label.startswith("reviewer-")
    if name in {"reward_presentation.py", "garden_finds.py"}:
        return (
            label.startswith("reviewer-")
            or renderer_family == "GardenProgressDialog"
        )
    if name in {"ui/scene.py", "ui/landmarks.py"}:
        return renderer_family == "GardenDashboard" or settings_preview
    if name in {"ui/plant_display.py", "ui/plant_presenters.py"}:
        affected = _entry_buckets(name)
        return settings_preview or affected is None or bucket in affected
    affected = _entry_buckets(name)
    return affected is None or bucket in affected


def build_render_input_catalog(
    production_archive: Path,
    *,
    capture_source: Path,
    validator_source: Path,
    labels: Sequence[str],
    renderer_families: Mapping[str, str],
    profile: str = "representative",
    contract_digest: str = "",
    scenario_contracts: Mapping[str, Mapping[str, Any]] | None = None,
    runtime_inputs: Mapping[str, Any] | None = None,
    dialog_scroll_contract: Mapping[str, Mapping[str, str]] | None = None,
    surface_specs: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build exact render, scenario, and run-level dependency digests.

    ``validator_source`` is deliberately *not* folded into a surface render
    digest.  A validator-only change must revalidate existing pixels, not
    force them to be captured again.  Likewise, the profile is recorded but
    not included in overlapping surface digests, so a representative preflight
    can seed identical faces in a later full-profile run.
    """

    profile = str(profile).strip().lower()
    if profile not in {"representative", "full"}:
        raise CaptureEvidenceError(f"Unknown capture profile: {profile!r}")
    scenario_contracts = dict(scenario_contracts or {})
    missing_scenarios = [label for label in labels if label not in scenario_contracts]
    if missing_scenarios:
        raise CaptureEvidenceError(
            "Scenario identities are missing for: " + ", ".join(missing_scenarios)
        )
    environment_inputs = dict(runtime_inputs or {"capture_scale_factor": "1.0"})
    environment_digest = canonical_json_sha256(environment_inputs)
    production_archive_sha256 = sha256_file(production_archive)
    evidence_schema_inputs = {
        "validator-source": sha256_file(validator_source),
    }
    evidence_schema_digest = canonical_json_sha256(evidence_schema_inputs)
    with zipfile.ZipFile(production_archive) as archive:
        entry_bytes = {
            info.filename: archive.read(info.filename)
            for info in archive.infolist()
            if not info.is_dir()
        }
    entries = {
        name: sha256_bytes(value) for name, value in entry_bytes.items()
    }
    module_sources = {
        name: value.decode("utf-8")
        for name, value in entry_bytes.items()
        if name.endswith(".py")
    }
    try:
        dashboard_source = entry_bytes["ui/dashboard.py"]
    except KeyError as error:
        raise CaptureEvidenceError(
            "Production archive is missing ui/dashboard.py"
        ) from error
    (
        dashboard_fragments,
        dashboard_class_contracts,
        dashboard_class_methods,
    ) = _dashboard_source_fragments(dashboard_source)
    capture_source_bytes = capture_source.read_bytes()
    scenario_reuse_ready = all(
        isinstance(scenario_contracts[label], Mapping)
        and scenario_contracts[label].get("label") == label
        and isinstance(scenario_contracts[label].get("method_inputs"), dict)
        and isinstance(scenario_contracts[label].get("state_contract"), dict)
        for label in labels
    )
    # Small renderer-closure unit catalogs intentionally provide only an
    # opaque scenario digest. They remain valid for exact comparisons, but
    # cannot participate in the migration optimization. Production catalogs
    # carry the complete source-derived identity and therefore take this path.
    scenario_reuse_digests = (
        _scenario_reuse_digests(
            capture_source=capture_source_bytes,
            scenario_contracts=scenario_contracts,
        )
        if scenario_reuse_ready else {}
    )
    (
        shared_class_methods,
        state_methods_by_label,
        audited_classes,
        hidden_call_exceptions,
        exact_module_owners,
        family_bases,
    ) = _renderer_method_dependencies(
        capture_source=capture_source_bytes,
        labels=labels,
        renderer_families=renderer_families,
        class_methods=dashboard_class_methods,
        surface_specs=surface_specs,
    )
    missing_exact_modules = sorted(set(exact_module_owners) - set(module_sources))
    if missing_exact_modules:
        raise CaptureEvidenceError(
            "Exact renderer module ownership references missing archive entries: "
            + ", ".join(missing_exact_modules)
        )
    all_root_symbols = set(_DASHBOARD_COMMON_SYMBOLS)
    for values in _DASHBOARD_FAMILY_SYMBOLS.values():
        all_root_symbols.update(values)
    for values in family_bases.values():
        all_root_symbols.update(values)
    all_method_keys = {
        f"{class_name}.{method_name}"
        for class_name in audited_classes
        for method_name in dashboard_class_methods.get(class_name, {})
    }
    (_all_fragments, _all_loaded, classified_top_level) = (
        _expanded_dashboard_fragment_closure(
            root_symbols=all_root_symbols,
            root_method_keys=all_method_keys,
            top_level=dashboard_fragments,
            class_contracts=dashboard_class_contracts,
            class_methods=dashboard_class_methods,
            shared_class_methods=shared_class_methods,
            audited_classes=audited_classes,
            hidden_call_exceptions=hidden_call_exceptions,
        )
    )
    unmapped_top_level = {
        name: sha256_bytes(dashboard_fragments[name])
        for name in sorted(set(dashboard_fragments) - classified_top_level)
        if name not in audited_classes
    }
    unmapped_top_level_digest = canonical_json_sha256(unmapped_top_level)
    dashboard_imports, dashboard_unresolved_imports = _module_import_bindings(
        entry="ui/dashboard.py",
        source=dashboard_source.decode("utf-8"),
        entries=module_sources,
    )

    catalog: dict[str, Any] = {}
    surface_fragment_closures: dict[str, dict[str, bytes]] = {}
    for label in labels:
        family = str(renderer_families.get(label, ""))
        bucket = _label_bucket(label, family)
        scenario = dict(scenario_contracts[label])
        scenario_digest = str(scenario.get("digest", ""))
        scenario_id = str(scenario.get("scenario_id", label))
        fixture_id = str(scenario.get("fixture_id", f"{label}-v1"))
        scenario_step = scenario.get("scenario_step", 1)
        if SHA256_RE.fullmatch(scenario_digest) is None:
            raise CaptureEvidenceError(
                f"Scenario identity digest is invalid for {label}"
            )
        if (
            not scenario_id
            or not fixture_id
            or type(scenario_step) is not int
            or scenario_step < 1
        ):
            raise CaptureEvidenceError(
                f"Scenario sequence identity is invalid for {label}"
            )
        symbols = (
            _DASHBOARD_FAMILY_SYMBOLS.get(family, frozenset())
            | frozenset(family_bases.get(family, ()))
        )
        if family != "AnkiQt":
            symbols = _DASHBOARD_COMMON_SYMBOLS | symbols
        fragment_closure, loaded_names, _resolved_top = (
            _expanded_dashboard_fragment_closure(
                root_symbols=symbols,
                root_method_keys=state_methods_by_label.get(label, ()),
                top_level=dashboard_fragments,
                class_contracts=dashboard_class_contracts,
                class_methods=dashboard_class_methods,
                shared_class_methods=shared_class_methods,
                audited_classes=audited_classes,
                hidden_call_exceptions=hidden_call_exceptions,
            )
        )
        unresolved_used = sorted(dashboard_unresolved_imports & loaded_names)
        if unresolved_used:
            raise CaptureEvidenceError(
                "Mapped ui/dashboard.py fragments have unresolved local imports "
                f"for {label}: " + ", ".join(unresolved_used)
            )
        module_roots = {
            target
            for binding, target in dashboard_imports.items()
            if binding in loaded_names
        }
        owned_module_roots = {
            entry for entry, owners in exact_module_owners.items()
            if label in owners
        }
        if family == "AnkiQt":
            owned_module_roots.add(
                "hooks/reviewer.py"
                if label.startswith("reviewer-")
                else "ui/home_widget.py"
            )
        module_roots.update(owned_module_roots)
        module_closure = _module_dependency_closure(
            entries=module_sources,
            roots=module_roots,
        )
        inputs = dict(environment_inputs)
        included_entries: set[str] = set()
        for name, digest in entries.items():
            exact_owners = exact_module_owners.get(name)
            affected = (
                label in exact_owners
                if exact_owners is not None
                else (
                    name in module_closure
                    or _entry_affects_surface(
                        name,
                        label=label,
                        renderer_family=family,
                        bucket=bucket,
                    )
                )
            )
            if affected:
                inputs[f"archive:{name}"] = digest
                included_entries.add(name)
        mapped_import_sources = [
            (f"ui/dashboard.py#{key}", fragment.decode("utf-8"))
            for key, fragment in fragment_closure.items()
        ]
        # Exact/source-owned roots represent a whole renderer module, so their
        # direct and function-local imports must also be owned. Broad modules
        # beyond that boundary deliberately remain covered by their own module
        # digest/bucket: recursively expanding a scene -> terminology -> game
        # chain would drag unrelated reward actions into every Garden canvas.
        mapped_import_sources.extend(
            (entry, module_sources[entry])
            for entry in sorted(owned_module_roots)
        )
        missing_import_targets: dict[str, list[str]] = {}
        for origin, source in mapped_import_sources:
            import_entry = (
                "ui/dashboard.py"
                if origin.startswith("ui/dashboard.py#")
                else origin
            )
            missing = sorted(
                _used_local_import_targets(
                    entry=import_entry,
                    source=source,
                    entries=module_sources,
                ) - included_entries
            )
            if missing:
                missing_import_targets[origin] = missing
        if missing_import_targets:
            details = "; ".join(
                f"{origin} -> {','.join(targets)}"
                for origin, targets in sorted(missing_import_targets.items())
            )
            raise CaptureEvidenceError(
                f"Mapped renderer imports bypass dependency ownership for {label}: "
                + details
            )
        for key, fragment in sorted(fragment_closure.items()):
            inputs[f"archive:ui/dashboard.py#{key}"] = sha256_bytes(fragment)
        inputs[
            "archive:ui/dashboard.py#__unmapped_top_level__"
        ] = unmapped_top_level_digest
        applied_method_keys = {
            key for key in fragment_closure if "." in key
        }
        inputs["capture-source:renderer-method-closure"] = canonical_json_sha256(
            sorted(applied_method_keys)
        )
        inputs["archive:renderer-module-closure"] = canonical_json_sha256(
            sorted(module_closure)
        )
        inputs["scenario-identity"] = scenario_digest
        if surface_specs is not None:
            spec_digest = str(
                surface_specs[label].get("dependency_digest", "")
            )
            if SHA256_RE.fullmatch(spec_digest) is None:
                raise CaptureEvidenceError(
                    f"SurfaceSpec dependency digest is invalid for {label}"
                )
            inputs["surface-spec"] = spec_digest
        surface_contract = {
            "renderer_family": family,
            "scenario_id": scenario_id,
            "fixture_id": fixture_id,
            "scenario_step": scenario_step,
            "scenario_identity_digest": scenario_digest,
            "render_inputs": dict(sorted(inputs.items())),
        }
        if label in scenario_reuse_digests:
            surface_contract.update({
                "scenario_reuse_digest": scenario_reuse_digests[label],
                "scenario_reuse_schema_version": SCENARIO_REUSE_SCHEMA_VERSION,
            })
        surface_contract_digest = canonical_json_sha256(surface_contract)
        catalog[label] = {
            "bucket": bucket,
            "renderer_family": family,
            "scenario_id": scenario_id,
            "fixture_id": fixture_id,
            "scenario_step": scenario_step,
            "environment_digest": environment_digest,
            "input_count": len(inputs),
            "inputs": dict(sorted(inputs.items())),
            "scenario_identity_digest": scenario_digest,
            "surface_contract_digest": surface_contract_digest,
            # Kept as the runtime-facing alias used by the capture runner.
            "digest": surface_contract_digest,
        }
        if label in scenario_reuse_digests:
            catalog[label].update({
                "scenario_reuse_digest": scenario_reuse_digests[label],
                "scenario_reuse_schema_version": SCENARIO_REUSE_SCHEMA_VERSION,
            })
        surface_fragment_closures[label] = fragment_closure
    _audit_renderer_method_reference_ownership(
        fragment_closures=surface_fragment_closures,
        class_methods=dashboard_class_methods,
        hidden_reference_exceptions=hidden_call_exceptions,
    )
    renderer_ownership_proof = _renderer_ownership_proof(
        production_archive_sha256=production_archive_sha256,
        dashboard_source=dashboard_source,
        dashboard_fragments=dashboard_fragments,
        dashboard_class_methods=dashboard_class_methods,
        audited_classes=audited_classes,
        hidden_call_exceptions=hidden_call_exceptions,
        unmapped_top_level=unmapped_top_level,
        fragment_closures=surface_fragment_closures,
    )
    scenario_contract_digest = canonical_json_sha256({
        label: str(scenario_contracts[label].get("digest", ""))
        for label in labels
    })
    scroll_contract = {
        surface: dict(sorted(labels_by_semantic.items()))
        for surface, labels_by_semantic in sorted(
            dict(dialog_scroll_contract or {}).items()
        )
    }
    run_level_inputs = {
        "capture_source_sha256": sha256_file(capture_source),
        "dialog_scroll_contract": scroll_contract,
        # Memory/lifecycle evidence is valid only for the exact production
        # package whose widgets were exercised.  Surface digests remain
        # selective, while this run gate deliberately covers the whole
        # archive so a package change cannot inherit an older process probe.
        "production_archive_sha256": production_archive_sha256,
        "runtime_environment_digest": environment_digest,
    }
    run_level_digest = canonical_json_sha256(run_level_inputs)
    return {
        "capture_profile": profile,
        "capture_contract_digest": contract_digest,
        "dialog_scroll_contract": scroll_contract,
        "environment_digest": environment_digest,
        "environment_inputs": environment_inputs,
        "evidence_schema_digest": evidence_schema_digest,
        "evidence_schema_inputs": evidence_schema_inputs,
        "production_archive_sha256": production_archive_sha256,
        "renderer_ownership_proof": renderer_ownership_proof,
        "run_level_digest": run_level_digest,
        "run_level_inputs": run_level_inputs,
        "scenario_contract_digest": scenario_contract_digest,
        "scenario_reuse_schema_version": SCENARIO_REUSE_SCHEMA_VERSION,
        "scenario_schema_version": 3 if surface_specs is not None else 1,
        "surfaces": catalog,
    }


def _load_manifest(path: Path) -> tuple[Path, dict[str, Any]]:
    resolved = path.expanduser().resolve()
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CaptureEvidenceError(f"Invalid capture manifest: {resolved}") from exc
    if not isinstance(payload, dict):
        raise CaptureEvidenceError(f"Capture manifest is not an object: {resolved}")
    return resolved, payload


def _capture_records_by_label(
    payload: Mapping[str, Any],
    *,
    source: Path,
) -> dict[str, dict[str, Any]]:
    """Return unambiguous capture records from one manifest."""

    raw_records = payload.get("captures", ())
    if not isinstance(raw_records, (list, tuple)):
        raise CaptureEvidenceError(
            f"Capture records must be a sequence: {source}"
        )
    records: dict[str, dict[str, Any]] = {}
    for record in raw_records:
        if not isinstance(record, dict):
            raise CaptureEvidenceError(
                f"Capture record is not an object: {source}"
            )
        label = str(record.get("label", ""))
        if not label:
            raise CaptureEvidenceError(
                f"Capture record label is missing: {source}"
            )
        if label in records:
            raise CaptureEvidenceError(
                f"Duplicate capture label {label!r}: {source}"
            )
        records[label] = record
    return records


def _v26_deprecated_visible_copy_issues(
    evidence: Any,
) -> tuple[str, ...]:
    """Independently reject missing or contradictory painted-copy proof."""

    if not isinstance(evidence, dict):
        return ("deprecated visible copy evidence is missing",)
    issues: list[str] = []
    visible_copy = evidence.get("visible_copy")
    if not isinstance(visible_copy, str):
        issues.append("deprecated visible copy text is invalid")
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
        issues.append("deprecated visible copy hits are invalid")
    else:
        if tuple(reported_hits) != recomputed_hits:
            issues.append("deprecated visible copy hits contradict the text")
        if reported_hits:
            issues.append("deprecated visible copy was detected")
    if recomputed_hits:
        issues.append("deprecated visible copy was detected")
    if evidence.get("collection_issues") != []:
        issues.append("deprecated visible copy collection did not pass")
    if evidence.get("passed") is not True:
        issues.append("deprecated visible copy audit did not pass")
    return tuple(dict.fromkeys(issues))


def _v26_surface_acceptance_issues(
    record: Mapping[str, Any],
) -> tuple[str, ...]:
    """Return fail-closed v26 semantic evidence issues for one surface."""

    issues: list[str] = []
    fixture = record.get("fixture_validation")
    if not isinstance(fixture, dict):
        issues.append("v26 fixture validation is missing")
    else:
        if fixture.get("semantic_audit_passed") is not True:
            issues.append("v26 fixture semantic audit did not pass")
        postcondition = fixture.get("postcondition")
        if (
            not isinstance(postcondition, dict)
            or postcondition.get("passed") is not True
            or postcondition.get("issues") != []
        ):
            issues.append("v26 fixture postcondition did not pass")

    acceptance = record.get("capture_acceptance")
    if not isinstance(acceptance, dict):
        issues.append("v26 capture acceptance is missing")
    else:
        if acceptance.get("policy") != V26_CAPTURE_ACCEPTANCE_POLICY:
            issues.append("v26 capture acceptance policy did not match")
        gross_checks = acceptance.get("gross_checks")
        if (
            not isinstance(gross_checks, dict)
            or not gross_checks
            or any(value is not True for value in gross_checks.values())
            or acceptance.get("gross_passed") is not True
        ):
            issues.append("v26 gross capture result did not pass")
        if acceptance.get("semantic_audit_passed") is not True:
            issues.append("v26 semantic capture acceptance did not pass")
        if acceptance.get("passed") is not True:
            issues.append("v26 capture acceptance did not pass")

    audit = record.get("audit")
    if (
        not isinstance(audit, dict)
        or audit.get("semantic_audit_passed") is not True
    ):
        issues.append("v26 capture audit semantic result did not pass")
    deprecated_copy = (
        audit.get("deprecated_visible_copy")
        if isinstance(audit, dict) else
        None
    )
    issues.extend(
        f"v26 {issue}"
        for issue in _v26_deprecated_visible_copy_issues(deprecated_copy)
    )
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
            issues.append(
                "v26 first-run selection transition did not pass"
            )
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
            issues.append(
                "v26 Nursery collection counts are not canonical"
            )

    native_layout = record.get("native_layout_telemetry")
    if (
        not isinstance(native_layout, dict)
        or native_layout.get("passed") is not True
        or native_layout.get("issues") != []
    ):
        issues.append("v26 native layout telemetry did not pass")

    visual_contract = record.get("visual_contract_audit")
    if (
        not isinstance(visual_contract, dict)
        or visual_contract.get("passed") is not True
        or visual_contract.get("issues") != []
    ):
        issues.append("v26 visual contract audit did not pass")

    scroll_audit = record.get("dialog_scroll_audit")
    if not isinstance(scroll_audit, dict):
        issues.append("v26 dialog scroll audit is missing")
    elif scroll_audit.get("applicable") is True:
        if (
            scroll_audit.get("passed") is not True
            or scroll_audit.get("issues") != []
        ):
            issues.append("v26 dialog scroll audit did not pass")
        four_state = scroll_audit.get("four_state_scroll_matrix")
        if (
            not isinstance(four_state, dict)
            or four_state.get("passed") is not True
            or four_state.get("issues") != []
        ):
            issues.append("v26 four-state scroll evidence did not pass")
    elif scroll_audit.get("applicable") is not False:
        issues.append("v26 dialog scroll applicability is invalid")

    return tuple(dict.fromkeys(issues))


def surface_validation_report(manifest_path: Path) -> dict[str, Any]:
    """Classify an attempt or assembled manifest without discarding good faces."""

    manifest_path, payload = _load_manifest(manifest_path)
    session_root = manifest_path.parent.resolve()
    expected = [str(value) for value in payload.get("expected_faces", ())]
    requested = [str(value) for value in payload.get("requested_faces", expected)]
    records = _capture_records_by_label(payload, source=manifest_path)
    failure_map: dict[str, list[str]] = {label: [] for label in expected}
    advisory_map: dict[str, list[str]] = {label: [] for label in expected}
    global_issues: list[str] = []
    global_advisories: list[str] = []
    # A partial attempt or failed run-level gate is globally incomplete, but
    # neither invalidates an already-atomic, independently verified surface.
    reuse_barrier_issues: list[str] = []
    raw_invalidated = payload.get("invalidated_faces", ())
    if not isinstance(raw_invalidated, (list, tuple)) or any(
        not isinstance(value, str) or not value
        for value in raw_invalidated
    ):
        issue = "invalidated capture labels are malformed"
        global_issues.append(issue)
        reuse_barrier_issues.append(issue)
        invalidated: tuple[str, ...] = ()
    else:
        invalidated = tuple(dict.fromkeys(raw_invalidated))
    contract_version = int(
        payload.get("capture_contract_version", 0) or 0
    )
    profile = str(payload.get("capture_profile", ""))
    if profile not in {"representative", "full"}:
        issue = "capture profile is invalid"
        global_issues.append(issue)
        reuse_barrier_issues.append(issue)
    try:
        scale = float(payload.get("requested_scale_factor"))
    except (TypeError, ValueError):
        scale = 0.0
    if scale != 1.0:
        issue = "capture scale is not 1.0"
        global_issues.append(issue)
        reuse_barrier_issues.append(issue)
    calibration = payload.get("capture_calibration")
    if not isinstance(calibration, dict) or calibration.get("passed") is not True:
        issue = "capture calibration did not pass"
        global_issues.append(issue)
        reuse_barrier_issues.append(issue)
    if payload.get("scope_complete") is not True:
        global_issues.append("capture scope did not complete")
    recovered_partial = (
        manifest_path.name == "manifest.recovered.json"
        and payload.get("capture_scope") == "recovered-partial"
    )
    completion_path = session_root / "capture-complete.json"
    completion_loaded = True
    try:
        completion = json.loads(completion_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        completion_loaded = False
        completion = {}
        if not recovered_partial:
            issue = "capture completion record is missing"
            global_issues.append(issue)
            reuse_barrier_issues.append(issue)
    except (OSError, json.JSONDecodeError):
        completion_loaded = False
        completion = {}
        issue = "capture completion record is invalid"
        global_issues.append(issue)
        reuse_barrier_issues.append(issue)
    if completion_loaded and not isinstance(completion, dict):
        issue = "capture completion record is not an object"
        global_issues.append(issue)
        reuse_barrier_issues.append(issue)
        completion_loaded = False
        completion = {}
    if completion_loaded:
        if completion.get("manifest_sha256") != sha256_file(manifest_path):
            issue = "capture completion manifest hash does not match"
            global_issues.append(issue)
            reuse_barrier_issues.append(issue)
        referenced = _safe_manifest_path(
            completion.get("manifest"),
            session_root,
        )
        if referenced != manifest_path:
            issue = "capture completion references another manifest"
            global_issues.append(issue)
            reuse_barrier_issues.append(issue)
        expected_scope_complete = payload.get("scope_complete") is True
        expected_complete = payload.get("complete") is True
        expected_exit_code = 0 if expected_scope_complete else 1
        if (
            completion.get("scope_complete") is not expected_scope_complete
            or completion.get("complete") is not expected_complete
            or completion.get("exit_code") != expected_exit_code
        ):
            issue = "capture completion status contradicts the manifest"
            global_issues.append(issue)
            reuse_barrier_issues.append(issue)
    for failure in payload.get("failures", ()):
        if not isinstance(failure, dict):
            global_issues.append("malformed-capture-failure")
            continue
        label = str(failure.get("label", ""))
        reason = str(failure.get("reason", "capture failure"))
        if label in requested:
            failure_map.setdefault(label, []).append(reason)
        else:
            global_issues.append(f"{label or 'capture'}: {reason}")
    for advisory in payload.get("capture_advisories", ()):
        if not isinstance(advisory, dict):
            global_advisories.append("malformed-capture-advisory")
            continue
        label = str(advisory.get("label", ""))
        reason = str(advisory.get("reason", "capture advisory"))
        if label in expected:
            advisory_map.setdefault(label, []).append(reason)
        else:
            global_advisories.append(f"{label or 'capture'}: {reason}")
    for warning in payload.get("text_layout_warnings", ()):
        if not isinstance(warning, dict):
            global_advisories.append("malformed-layout-warning")
            continue
        label = str(warning.get("capture", ""))
        kind = str(warning.get("kind", "layout-warning"))
        if label in requested:
            advisory_map.setdefault(label, []).append(kind)
        else:
            global_advisories.append(f"{label or 'capture'}: {kind}")

    surfaces: dict[str, Any] = {}
    for label in expected:
        issues = list(failure_map.get(label, ()))
        advisories = list(advisory_map.get(label, ()))
        record = records.get(label)
        if label not in requested and record is None:
            surfaces[label] = {
                "status": "not-requested",
                "issues": [],
            }
            continue
        if record is None:
            issues.append("capture record is missing")
        else:
            path = _safe_manifest_path(record.get("path"), session_root)
            if path is None or not path.is_file():
                issues.append("PNG is missing or outside the session")
            else:
                try:
                    with path.open("rb") as handle:
                        if handle.read(8) != PNG_SIGNATURE:
                            issues.append("PNG signature is invalid")
                    actual_sha = sha256_file(path)
                    if record.get("png_sha256") != actual_sha:
                        issues.append("PNG SHA-256 does not match the record")
                except OSError:
                    issues.append("PNG could not be read")
            for field in (
                "render_input_digest",
                "capture_environment_digest",
                "scenario_identity_digest",
                "surface_contract_digest",
                "evidence_schema_digest",
            ):
                value = record.get(field)
                if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
                    issues.append(f"{field} is missing or invalid")
            fixture = record.get("fixture_validation")
            if not isinstance(fixture, dict) or fixture.get("passed") is not True:
                issues.append("fixture validation did not pass")
            if contract_version >= 25:
                acceptance = record.get("capture_acceptance")
                expected_acceptance_policy = (
                    V26_CAPTURE_ACCEPTANCE_POLICY
                    if contract_version >= 26 else
                    LEGACY_CAPTURE_ACCEPTANCE_POLICY
                )
                if (
                    not isinstance(acceptance, dict)
                    or acceptance.get("policy") != expected_acceptance_policy
                    or acceptance.get("passed") is not True
                ):
                    issues.append("gross capture acceptance did not pass")
            if contract_version >= 26:
                issues.extend(_v26_surface_acceptance_issues(record))
            audit = record.get("audit")
            if not isinstance(audit, dict) or audit.get("passed") is not True:
                issues.append("capture audit did not pass")
            if record.get("text_layout_warnings"):
                advisories.append("record reports text-layout warnings")
            if record.get("geometry_layout_warnings"):
                advisories.append("record reports geometry warnings")
            lineage = record.get("lineage")
            if not isinstance(lineage, dict) or not lineage.get("source_run_id"):
                issues.append("capture lineage is missing")
        surfaces[label] = {
            "status": "failed" if issues or reuse_barrier_issues else "passed",
            "issues": list(dict.fromkeys(issues)),
            "advisories": list(dict.fromkeys(advisories)),
            "capture_id": record.get("capture_id") if record else None,
            "path": record.get("path") if record else None,
        }

    reusable = [
        label for label in expected
        if surfaces.get(label, {}).get("status") == "passed"
    ]
    recapture = [
        label for label in expected
        if label in requested and surfaces.get(label, {}).get("status") != "passed"
    ]
    return {
        "capture_contract_version": payload.get("capture_contract_version"),
        "capture_profile": profile,
        "capture_scope": payload.get("capture_scope", "full"),
        "global_advisories": list(dict.fromkeys(global_advisories)),
        "global_issues": list(dict.fromkeys(global_issues)),
        "invalidated_faces": list(invalidated),
        "reuse_barrier_issues": list(dict.fromkeys(reuse_barrier_issues)),
        "manifest": str(manifest_path),
        "recapture_required": recapture,
        "requested_faces": requested,
        "reusable_faces": reusable,
        "run_level_evidence": payload.get("run_level_evidence", {}),
        "status": "valid" if not global_issues and not recapture else "invalid",
        "surfaces": surfaces,
    }


def _legacy_capture_derivative_entries(
    manifest_path: Path,
    payload: Mapping[str, Any],
    *,
    entries: Sequence[str],
) -> dict[str, bytes] | None:
    """Return exact entries from one unambiguous sealed capture derivative."""

    render_inputs = payload.get("render_inputs")
    run_inputs = (
        render_inputs.get("run_level_inputs")
        if isinstance(render_inputs, dict) else None
    )
    expected_digest = (
        run_inputs.get("capture_source_sha256")
        if isinstance(run_inputs, dict) else None
    )
    if not isinstance(expected_digest, str) or SHA256_RE.fullmatch(
        expected_digest
    ) is None:
        return None
    candidates: list[Path] = []
    for parent in (manifest_path.parent, manifest_path.parent.parent):
        candidate = (parent / "anki_garden_capture.ankiaddon").resolve()
        if candidate.is_file() and candidate not in candidates:
            candidates.append(candidate)
    if len(candidates) != 1:
        return None
    requested = tuple(dict.fromkeys(str(value) for value in entries))
    if not requested or any(not value for value in requested):
        return None
    try:
        with zipfile.ZipFile(candidates[0]) as archive:
            archive_entries: dict[str, list[zipfile.ZipInfo]] = {}
            for info in archive.infolist():
                if not info.is_dir():
                    archive_entries.setdefault(info.filename, []).append(info)
            required = {"capture_ui_faces.py", *requested}
            if any(len(archive_entries.get(name, ())) != 1 for name in required):
                return None
            result = {
                name: archive.read(archive_entries[name][0])
                for name in required
            }
    except (KeyError, OSError, zipfile.BadZipFile):
        return None
    if sha256_bytes(result["capture_ui_faces.py"]) != expected_digest:
        return None
    return {name: result[name] for name in requested}


def _legacy_capture_source_bytes(
    manifest_path: Path,
    payload: Mapping[str, Any],
) -> bytes | None:
    """Return an exact archive-bound legacy capture source, if available."""

    result = _legacy_capture_derivative_entries(
        manifest_path,
        payload,
        entries=("capture_ui_faces.py",),
    )
    return result.get("capture_ui_faces.py") if result is not None else None


def _legacy_scenario_reuse_digests(
    manifest_path: Path,
    payload: Mapping[str, Any],
) -> dict[str, str] | None:
    """Derive v24 reuse identities from a sealed legacy capture derivative."""

    source = _legacy_capture_source_bytes(manifest_path, payload)
    profile = str(payload.get("capture_profile", ""))
    expected = tuple(str(value) for value in payload.get("expected_faces", ()))
    if source is None or profile not in {"representative", "full"} or not expected:
        return None
    try:
        from scripts.validate_ui_capture import (
            load_capture_contract,
            load_capture_scenario_contracts,
        )

        with tempfile.TemporaryDirectory(prefix="anki-garden-scenario-reuse-") as raw:
            source_path = Path(raw) / "capture_ui_faces.py"
            source_path.write_bytes(source)
            contract = load_capture_contract(source_path, profile=profile)
            if tuple(contract.labels) != expected:
                return None
            scenarios = load_capture_scenario_contracts(
                source_path,
                contract=contract,
            )
    except Exception:
        # Legacy migration is an optimization, never a trust prerequisite.
        # Any parse, schema, or source-identity ambiguity simply recaptures.
        return None
    if tuple(scenarios) != expected:
        return None
    expected_contract_digest = canonical_json_sha256({
        label: str(scenarios[label].get("digest", ""))
        for label in expected
    })
    render_inputs = payload.get("render_inputs")
    if (
        payload.get("scenario_contract_digest") != expected_contract_digest
        or not isinstance(render_inputs, dict)
        or render_inputs.get("scenario_contract_digest")
        != expected_contract_digest
    ):
        return None
    surfaces = render_inputs.get("surfaces")
    if not isinstance(surfaces, dict):
        return None
    for label in expected:
        surface = surfaces.get(label)
        if not isinstance(surface, dict) or surface.get(
            "scenario_identity_digest"
        ) != scenarios[label].get("digest"):
            return None
    try:
        return _scenario_reuse_digests(
            capture_source=source,
            scenario_contracts=scenarios,
        )
    except CaptureEvidenceError:
        return None


def _scenario_surface_contract_is_consistent(
    surface: Mapping[str, Any],
) -> bool:
    inputs = surface.get("inputs")
    scenario_digest = surface.get("scenario_identity_digest")
    renderer_family = surface.get("renderer_family")
    if (
        not isinstance(inputs, dict)
        or not isinstance(renderer_family, str)
        or not isinstance(scenario_digest, str)
        or SHA256_RE.fullmatch(scenario_digest) is None
        or inputs.get("scenario-identity") != scenario_digest
        or surface.get("input_count") != len(inputs)
    ):
        return False
    surface_contract = {
        "renderer_family": renderer_family,
        "scenario_identity_digest": scenario_digest,
        "render_inputs": dict(sorted(inputs.items())),
    }
    if "scenario_reuse_digest" in surface:
        reuse_digest = surface.get("scenario_reuse_digest")
        reuse_version = surface.get("scenario_reuse_schema_version")
        if (
            reuse_version not in {
                SCENARIO_REUSE_SCHEMA_VERSION,
                *_LEGACY_SCENARIO_REUSE_SCHEMA_VERSIONS,
            }
            or not isinstance(reuse_digest, str)
            or SHA256_RE.fullmatch(reuse_digest) is None
        ):
            return False
        surface_contract.update({
            "scenario_reuse_digest": reuse_digest,
            "scenario_reuse_schema_version": reuse_version,
        })
    elif "scenario_reuse_schema_version" in surface:
        return False
    surface_digest = canonical_json_sha256(surface_contract)
    return bool(
        surface.get("digest") == surface_digest
        and surface.get("surface_contract_digest") == surface_digest
    )


def _scenario_reuse_digest_compatible(
    *,
    label: str,
    source_path: Path,
    payload: Mapping[str, Any],
    source: Mapping[str, Any],
    current: Mapping[str, Any],
    legacy_cache: dict[Path, dict[str, str] | None],
) -> bool:
    """Return whether two surfaces share one versioned scenario path."""

    current_reuse_digest = current.get("scenario_reuse_digest")
    if (
        current.get("scenario_reuse_schema_version")
        != SCENARIO_REUSE_SCHEMA_VERSION
        or not isinstance(current_reuse_digest, str)
        or SHA256_RE.fullmatch(current_reuse_digest) is None
    ):
        return False
    source_version = source.get("scenario_reuse_schema_version")
    if (
        "scenario_reuse_digest" in source
        and source_version == SCENARIO_REUSE_SCHEMA_VERSION
    ):
        source_reuse_digest = source.get("scenario_reuse_digest")
        if (
            not isinstance(source_reuse_digest, str)
            or SHA256_RE.fullmatch(source_reuse_digest) is None
        ):
            return False
    else:
        if (
            source_version is not None
            and source_version not in _LEGACY_SCENARIO_REUSE_SCHEMA_VERSIONS
        ):
            return False
        if source_path not in legacy_cache:
            legacy_cache[source_path] = _legacy_scenario_reuse_digests(
                source_path,
                payload,
            )
        legacy = legacy_cache[source_path]
        source_reuse_digest = legacy.get(label) if isinstance(legacy, dict) else None
    return bool(source_reuse_digest == current_reuse_digest)


def _scenario_migration_compatible(
    *,
    label: str,
    source_path: Path,
    payload: Mapping[str, Any],
    record: Mapping[str, Any],
    current: Mapping[str, Any],
    legacy_cache: dict[Path, dict[str, str] | None],
) -> bool:
    """Allow reuse only for a proven label-local scenario identity change."""

    render_inputs = payload.get("render_inputs")
    source_surfaces = (
        render_inputs.get("surfaces")
        if isinstance(render_inputs, dict) else None
    )
    source = source_surfaces.get(label) if isinstance(source_surfaces, dict) else None
    if not isinstance(source, dict):
        return False
    if not (
        _scenario_surface_contract_is_consistent(source)
        and _scenario_surface_contract_is_consistent(current)
    ):
        return False
    if (
        record.get("render_input_digest") != source.get("digest")
        or record.get("scenario_identity_digest")
        != source.get("scenario_identity_digest")
        or record.get("surface_contract_digest")
        != source.get("surface_contract_digest")
        or record.get("capture_environment_digest")
        != source.get("environment_digest")
        or not _scenario_reuse_digest_compatible(
            label=label,
            source_path=source_path,
            payload=payload,
            source=source,
            current=current,
            legacy_cache=legacy_cache,
        )
    ):
        return False
    source_inputs = source.get("inputs")
    current_inputs = current.get("inputs")
    if not isinstance(source_inputs, dict) or not isinstance(current_inputs, dict):
        return False
    source_without_scenario = dict(source_inputs)
    current_without_scenario = dict(current_inputs)
    source_without_scenario.pop("scenario-identity", None)
    current_without_scenario.pop("scenario-identity", None)
    return bool(
        source.get("renderer_family") == current.get("renderer_family")
        and source.get("bucket") == current.get("bucket")
        and source.get("environment_digest") == current.get("environment_digest")
        and source_without_scenario == current_without_scenario
    )


def _legacy_renderer_ownership_proof(
    manifest_path: Path,
    payload: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Reconstruct one historical ownership proof from its sealed derivative."""

    derivative = _legacy_capture_derivative_entries(
        manifest_path,
        payload,
        entries=("capture_ui_faces.py", "ui/dashboard.py"),
    )
    expected = tuple(str(value) for value in payload.get("expected_faces", ()))
    profile = str(payload.get("capture_profile", ""))
    render_inputs = payload.get("render_inputs")
    surfaces = (
        render_inputs.get("surfaces")
        if isinstance(render_inputs, dict) else None
    )
    production_digest = (
        render_inputs.get("production_archive_sha256")
        if isinstance(render_inputs, dict) else None
    )
    if (
        derivative is None
        or not expected
        or profile not in {"representative", "full"}
        or not isinstance(surfaces, dict)
        or not isinstance(production_digest, str)
        or SHA256_RE.fullmatch(production_digest) is None
        or payload.get("production_package_sha256") != production_digest
    ):
        return None
    try:
        assignment = (
            "CAPTURE_FACE_GROUPS"
            if profile == "representative" else
            "EXHAUSTIVE_CAPTURE_FACE_GROUPS"
        )
        declared_groups = _literal_assignment(
            derivative["capture_ui_faces.py"],
            assignment,
        )
        declared_labels = tuple(
            str(label)
            for _group_name, group_labels in declared_groups
            for label in group_labels
        )
        if declared_labels != expected:
            return None
        renderer_families = {
            label: str(surfaces[label].get("renderer_family", ""))
            for label in expected
            if isinstance(surfaces.get(label), dict)
        }
        if set(renderer_families) != set(expected) or any(
            not family for family in renderer_families.values()
        ):
            return None
        proof = _reconstruct_renderer_ownership_proof(
            capture_source=derivative["capture_ui_faces.py"],
            dashboard_source=derivative["ui/dashboard.py"],
            labels=expected,
            renderer_families=renderer_families,
            production_archive_sha256=production_digest,
        )
    except (CaptureEvidenceError, TypeError, ValueError):
        return None
    return proof if _renderer_ownership_proof_is_consistent(
        proof,
        expected_labels=expected,
    ) else None


def _renderer_method_closure_digest(inputs: Mapping[str, Any]) -> str:
    prefix = "archive:ui/dashboard.py#"
    method_keys = sorted(
        key.removeprefix(prefix)
        for key in inputs
        if key.startswith(prefix) and "." in key.removeprefix(prefix)
    )
    return canonical_json_sha256(method_keys)


def _deferred_species_builder_ownership_migration(
    *,
    label: str,
    source_path: Path,
    payload: Mapping[str, Any],
    record: Mapping[str, Any],
    current_render_inputs: Mapping[str, Any],
    current: Mapping[str, Any],
    legacy_cache: dict[Path, dict[str, Any] | None],
    scenario_cache: dict[Path, dict[str, str] | None],
) -> dict[str, Any] | None:
    """Prove one old deferred callback closure no longer owns this surface.

    Older v24 catalogs followed the Collection species-card callback through
    ``_open_species_overview`` and therefore bound the whole species-dialog
    builder subtree to every Collection face.  The current source contract
    classifies that exact callback edge as deferred interaction and owns the
    subtree only for the two surfaces that actually invoke the builder.

    This is deliberately not a generic dropped-input normalizer.  Both source
    graphs are reconstructed from sealed capture derivatives; the exact edge,
    owner sets, four-fragment subtree, unchanged support fragments, derived
    closure digests, and every remaining surface input must all agree.
    """

    render_inputs = payload.get("render_inputs")
    source_surfaces = (
        render_inputs.get("surfaces")
        if isinstance(render_inputs, dict) else None
    )
    source = source_surfaces.get(label) if isinstance(source_surfaces, dict) else None
    current_proof = current_render_inputs.get("renderer_ownership_proof")
    expected_labels = tuple(str(value) for value in current_render_inputs.get(
        "surfaces",
        {},
    ))
    if (
        not isinstance(source, dict)
        or not _scenario_surface_contract_is_consistent(source)
        or not _scenario_surface_contract_is_consistent(current)
        or not isinstance(render_inputs, dict)
        or not isinstance(current_proof, dict)
        or not _renderer_ownership_proof_is_consistent(
            current_proof,
            expected_labels=expected_labels,
        )
        or current_proof.get("production_archive_sha256")
        != current_render_inputs.get("production_archive_sha256")
        or record.get("render_input_digest") != source.get("digest")
        or record.get("scenario_identity_digest")
        != source.get("scenario_identity_digest")
        or record.get("surface_contract_digest")
        != source.get("surface_contract_digest")
        or record.get("capture_environment_digest")
        != source.get("environment_digest")
    ):
        return None
    scenario_changed = (
        source.get("scenario_identity_digest")
        != current.get("scenario_identity_digest")
    )
    if scenario_changed and not _scenario_reuse_digest_compatible(
        label=label,
        source_path=source_path,
        payload=payload,
        source=source,
        current=current,
        legacy_cache=scenario_cache,
    ):
        return None
    if source_path not in legacy_cache:
        legacy_cache[source_path] = _legacy_renderer_ownership_proof(
            source_path,
            payload,
        )
    source_proof = legacy_cache[source_path]
    if not isinstance(source_proof, dict):
        return None

    old_method_digests = source_proof.get("method_digests")
    new_method_digests = current_proof.get("method_digests")
    old_top_level_digests = source_proof.get("top_level_digests")
    new_top_level_digests = current_proof.get("top_level_digests")
    old_fragment_owners = source_proof.get("fragment_owners")
    new_fragment_owners = current_proof.get("fragment_owners")
    old_hidden = source_proof.get("hidden_call_exceptions")
    new_hidden = current_proof.get("hidden_call_exceptions")
    if not all(
        isinstance(value, expected_type)
        for value, expected_type in (
            (old_method_digests, dict),
            (new_method_digests, dict),
            (old_top_level_digests, dict),
            (new_top_level_digests, dict),
            (old_fragment_owners, dict),
            (new_fragment_owners, dict),
            (old_hidden, list),
            (new_hidden, list),
        )
    ):
        return None
    edge = list(_DEFERRED_SPECIES_OVERVIEW_EDGE)
    if edge in old_hidden or edge not in new_hidden:
        return None
    caller, builder_route = _DEFERRED_SPECIES_OVERVIEW_EDGE
    builder = "GardenDashboard._build_species_overview_dialog"
    expected_current_owners = sorted(
        _SPECIES_OVERVIEW_LABELS & set(expected_labels)
    )
    if (
        label in _SPECIES_OVERVIEW_LABELS
        or label not in old_fragment_owners.get(caller, ())
        or label not in new_fragment_owners.get(caller, ())
        or label not in old_fragment_owners.get(builder_route, ())
        or label in new_fragment_owners.get(builder_route, ())
        or label not in old_fragment_owners.get(builder, ())
        or label in new_fragment_owners.get(builder, ())
        or new_fragment_owners.get(builder) != expected_current_owners
        or old_method_digests.get(caller) != new_method_digests.get(caller)
        or old_method_digests.get(builder_route)
        != new_method_digests.get(builder_route)
        or old_method_digests.get(builder) == new_method_digests.get(builder)
    ):
        return None

    def fragment_digest(
        fragment: str,
        *,
        methods: Mapping[str, Any],
        top_level: Mapping[str, Any],
    ) -> Any:
        return methods.get(fragment, top_level.get(fragment))

    changed_fragment = builder
    for fragment in _DEFERRED_SPECIES_OVERVIEW_DROPPED_FRAGMENTS:
        if (
            label not in old_fragment_owners.get(fragment, ())
            or label in new_fragment_owners.get(fragment, ())
        ):
            return None
        old_digest = fragment_digest(
            fragment,
            methods=old_method_digests,
            top_level=old_top_level_digests,
        )
        new_digest = fragment_digest(
            fragment,
            methods=new_method_digests,
            top_level=new_top_level_digests,
        )
        if (
            not isinstance(old_digest, str)
            or SHA256_RE.fullmatch(old_digest) is None
            or not isinstance(new_digest, str)
            or SHA256_RE.fullmatch(new_digest) is None
            or (fragment != changed_fragment and old_digest != new_digest)
        ):
            return None

    source_inputs = source.get("inputs")
    current_inputs = current.get("inputs")
    if not isinstance(source_inputs, dict) or not isinstance(current_inputs, dict):
        return None
    closure_key = "capture-source:renderer-method-closure"
    if (
        source_inputs.get(closure_key)
        != _renderer_method_closure_digest(source_inputs)
        or current_inputs.get(closure_key)
        != _renderer_method_closure_digest(current_inputs)
    ):
        return None
    dropped_input_keys = {
        f"archive:ui/dashboard.py#{fragment}"
        for fragment in _DEFERRED_SPECIES_OVERVIEW_DROPPED_FRAGMENTS
    }
    for fragment in _DEFERRED_SPECIES_OVERVIEW_DROPPED_FRAGMENTS:
        input_key = f"archive:ui/dashboard.py#{fragment}"
        if input_key not in source_inputs or input_key in current_inputs:
            return None
        old_digest = fragment_digest(
            fragment,
            methods=old_method_digests,
            top_level=old_top_level_digests,
        )
        if source_inputs.get(input_key) != old_digest:
            return None
    source_comparable = dict(source_inputs)
    current_comparable = dict(current_inputs)
    for key in dropped_input_keys:
        source_comparable.pop(key, None)
    source_comparable.pop(closure_key, None)
    current_comparable.pop(closure_key, None)
    if scenario_changed:
        source_comparable.pop("scenario-identity", None)
        current_comparable.pop("scenario-identity", None)
    if not (
        source_proof.get("production_archive_sha256")
        == render_inputs.get("production_archive_sha256")
        and source.get("renderer_family") == current.get("renderer_family")
        and source.get("bucket") == current.get("bucket")
        and source.get("environment_digest") == current.get("environment_digest")
        and source_comparable == current_comparable
    ):
        return None
    return {
        "type": "deferred-renderer-ownership",
        "reason": "species-overview-callback-no-longer-owns-unopened-dialog",
        "edge": edge,
        "changed_fragment": changed_fragment,
        "dropped_inputs": sorted(dropped_input_keys),
        "source_proof_digest": source_proof.get("digest"),
        "current_proof_digest": current_proof.get("digest"),
    }


def _renderer_ownership_migration_compatible(
    *,
    label: str,
    source_path: Path,
    payload: Mapping[str, Any],
    record: Mapping[str, Any],
    current_render_inputs: Mapping[str, Any],
    current: Mapping[str, Any],
    legacy_cache: dict[Path, dict[str, Any] | None],
    scenario_cache: dict[Path, dict[str, str] | None],
) -> bool:
    """Migrate only the proven PlantInfoCard unmapped-to-owned transition.

    The historical aggregate is never normalized generically.  Reuse is
    available only to non-owner labels and only when the sealed old/new AST
    catalogs show PlantInfoCard as the sole changed top-level definition.
    """

    render_inputs = payload.get("render_inputs")
    source_surfaces = (
        render_inputs.get("surfaces")
        if isinstance(render_inputs, dict) else None
    )
    source = source_surfaces.get(label) if isinstance(source_surfaces, dict) else None
    current_proof = current_render_inputs.get("renderer_ownership_proof")
    expected_labels = tuple(str(value) for value in current_render_inputs.get(
        "surfaces",
        {},
    ))
    if (
        not isinstance(source, dict)
        or not _scenario_surface_contract_is_consistent(source)
        or not _scenario_surface_contract_is_consistent(current)
        or not _renderer_ownership_proof_is_consistent(
            current_proof,
            expected_labels=expected_labels,
        )
        or not isinstance(current_proof, dict)
        or current_proof.get("production_archive_sha256")
        != current_render_inputs.get("production_archive_sha256")
    ):
        return False
    if (
        record.get("render_input_digest") != source.get("digest")
        or record.get("scenario_identity_digest")
        != source.get("scenario_identity_digest")
        or record.get("surface_contract_digest")
        != source.get("surface_contract_digest")
        or record.get("capture_environment_digest")
        != source.get("environment_digest")
    ):
        return False
    scenario_changed = (
        source.get("scenario_identity_digest")
        != current.get("scenario_identity_digest")
    )
    if scenario_changed and not _scenario_reuse_digest_compatible(
        label=label,
        source_path=source_path,
        payload=payload,
        source=source,
        current=current,
        legacy_cache=scenario_cache,
    ):
        return False
    if source_path not in legacy_cache:
        legacy_cache[source_path] = _legacy_renderer_ownership_proof(
            source_path,
            payload,
        )
    source_proof = legacy_cache[source_path]
    if not isinstance(source_proof, dict):
        return False
    old_top = source_proof.get("top_level_digests")
    new_top = current_proof.get("top_level_digests")
    old_unmapped = source_proof.get("unmapped_top_level_digests")
    new_unmapped = current_proof.get("unmapped_top_level_digests")
    old_audited = source_proof.get("audited_classes")
    new_audited = current_proof.get("audited_classes")
    class_owners = current_proof.get("class_owners")
    if not all(
        isinstance(value, expected_type)
        for value, expected_type in (
            (old_top, dict),
            (new_top, dict),
            (old_unmapped, dict),
            (new_unmapped, dict),
            (old_audited, list),
            (new_audited, list),
            (class_owners, dict),
        )
    ):
        return False
    changed_top_level = {
        name for name in set(old_top) | set(new_top)
        if old_top.get(name) != new_top.get(name)
    }
    plant_owners = class_owners.get("PlantInfoCard")
    if not (
        changed_top_level == {"PlantInfoCard"}
        and "PlantInfoCard" in old_unmapped
        and "PlantInfoCard" not in old_audited
        and "PlantInfoCard" not in new_unmapped
        and "PlantInfoCard" in new_audited
        and isinstance(plant_owners, list)
        and plant_owners
        and label not in plant_owners
    ):
        return False
    source_inputs = source.get("inputs")
    current_inputs = current.get("inputs")
    unmapped_key = "archive:ui/dashboard.py#__unmapped_top_level__"
    if (
        not isinstance(source_inputs, dict)
        or not isinstance(current_inputs, dict)
        or source_inputs.get(unmapped_key)
        != source_proof.get("unmapped_top_level_digest")
        or current_inputs.get(unmapped_key)
        != current_proof.get("unmapped_top_level_digest")
    ):
        return False
    source_without_unmapped = dict(source_inputs)
    current_without_unmapped = dict(current_inputs)
    source_without_unmapped.pop(unmapped_key, None)
    current_without_unmapped.pop(unmapped_key, None)
    if scenario_changed:
        source_without_unmapped.pop("scenario-identity", None)
        current_without_unmapped.pop("scenario-identity", None)
    return bool(
        source_proof.get("production_archive_sha256")
        == render_inputs.get("production_archive_sha256")
        and source_proof.get("dashboard_without_plant_info_card_sha256")
        == current_proof.get("dashboard_without_plant_info_card_sha256")
        and source.get("renderer_family") == current.get("renderer_family")
        and source.get("bucket") == current.get("bucket")
        and source.get("environment_digest") == current.get("environment_digest")
        and source_without_unmapped == current_without_unmapped
    )


def plan_incremental_capture(
    *,
    base_manifest: Path | None = None,
    evidence_manifests: Sequence[Path] = (),
    current_render_inputs: Mapping[str, Any],
    expected_labels: Sequence[str],
    contract_version: int,
    contract_digest: str = "",
    profile: str = "representative",
    explicit_surfaces: Iterable[str] = (),
) -> dict[str, Any]:
    """Select the newest exact evidence per state and return minimum recapture.

    Manifests are considered in caller order (newest first). A failed
    replacement is never silently substituted here: once a label is explicitly
    requested it remains in ``recapture_required`` until a later run passes.
    """

    ordered_paths: list[Path] = []
    if base_manifest is not None:
        ordered_paths.append(base_manifest)
    ordered_paths.extend(evidence_manifests)
    deduplicated: list[Path] = []
    seen_paths: set[Path] = set()
    for raw_path in ordered_paths:
        resolved = raw_path.expanduser().resolve()
        if resolved not in seen_paths:
            seen_paths.add(resolved)
            deduplicated.append(resolved)
    candidates: list[tuple[Path, dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]] = []
    rejected_manifests: list[dict[str, Any]] = []
    for path in deduplicated:
        try:
            resolved, payload = _load_manifest(path)
            report = surface_validation_report(resolved)
            records = _capture_records_by_label(payload, source=resolved)
        except CaptureEvidenceError as error:
            rejected_manifests.append({"manifest": str(path), "reason": str(error)})
            continue
        candidates.append((resolved, payload, report, records))
    explicit = {str(label) for label in explicit_surfaces}
    unknown = explicit - set(expected_labels)
    if unknown:
        raise CaptureEvidenceError(
            "Unknown capture surface(s): " + ", ".join(sorted(unknown))
        )
    current_surfaces = current_render_inputs.get("surfaces")
    if not isinstance(current_surfaces, dict):
        raise CaptureEvidenceError("Current render-input catalog is invalid")
    profile = str(profile).strip().lower()
    if profile not in {"representative", "full"}:
        raise CaptureEvidenceError(f"Unknown capture profile: {profile!r}")

    reusable: list[str] = []
    recapture: list[str] = []
    reasons: dict[str, list[str]] = {}
    selected_sources: dict[str, dict[str, Any]] = {}
    legacy_scenario_cache: dict[Path, dict[str, str] | None] = {}
    legacy_renderer_ownership_cache: dict[Path, dict[str, Any] | None] = {}
    for label in expected_labels:
        label_reasons: list[str] = []
        if label in explicit:
            label_reasons.append("explicitly-requested")
        current = current_surfaces.get(label, {})
        selected: tuple[
            Path,
            dict[str, Any],
            dict[str, Any],
            str,
            dict[str, Any] | None,
        ] | None = None
        observed_reasons: list[str] = []
        newer_pass_seen = False
        if not label_reasons:
            for source_path, payload, report, records in candidates:
                source_contract_version = payload.get("capture_contract_version")
                if source_contract_version != contract_version:
                    observed_reasons.append(
                        "v25-reuse-forbidden"
                        if contract_version == 26 and source_contract_version == 25 else
                        "capture-contract-changed"
                    )
                    continue
                source_profile = str(payload.get("capture_profile", ""))
                if source_profile not in {"representative", "full"}:
                    observed_reasons.append("capture-profile-invalid")
                    continue
                # Cross-profile reuse is allowed only for labels present in
                # both contracts and only when every per-state digest matches.
                if label not in payload.get("expected_faces", ()):
                    continue
                state = report.get("surfaces", {}).get(label, {})
                if state.get("status") != "passed":
                    if (
                        not newer_pass_seen
                        and label in report.get("invalidated_faces", ())
                    ):
                        observed_reasons.append("failed-recapture-tombstone")
                        # Candidate order is newest first. An explicit failed
                        # replacement invalidates every older record for this
                        # state until a newer passing record clears it.
                        break
                    observed_reasons.append("previous-evidence-invalid")
                    continue
                newer_pass_seen = True
                record = records.get(label, {})
                comparisons = (
                    (
                        "scenario_identity_digest",
                        "scenario_identity_digest",
                        "scenario-identity-changed",
                    ),
                    (
                        "surface_contract_digest",
                        "surface_contract_digest",
                        "surface-contract-changed",
                    ),
                    (
                        "render_input_digest",
                        "digest",
                        "render-inputs-changed",
                    ),
                    (
                        "capture_environment_digest",
                        "environment_digest",
                        "capture-environment-changed",
                    ),
                )
                mismatch = False
                for record_field, current_field, reason in comparisons:
                    if record.get(record_field) != current.get(current_field):
                        observed_reasons.append(reason)
                        mismatch = True
                if mismatch:
                    migration_provenance: dict[str, Any] | None = None
                    if _scenario_migration_compatible(
                        label=label,
                        source_path=source_path,
                        payload=payload,
                        record=record,
                        current=current,
                        legacy_cache=legacy_scenario_cache,
                    ):
                        reuse_mode = "scenario-path"
                    else:
                        migration_provenance = (
                            _deferred_species_builder_ownership_migration(
                                label=label,
                                source_path=source_path,
                                payload=payload,
                                record=record,
                                current_render_inputs=current_render_inputs,
                                current=current,
                                legacy_cache=legacy_renderer_ownership_cache,
                                scenario_cache=legacy_scenario_cache,
                            )
                        )
                        if migration_provenance is not None:
                            reuse_mode = (
                                "scenario-path+deferred-renderer-ownership"
                                if record.get("scenario_identity_digest")
                                != current.get("scenario_identity_digest") else
                                "deferred-renderer-ownership"
                            )
                        elif _renderer_ownership_migration_compatible(
                            label=label,
                            source_path=source_path,
                            payload=payload,
                            record=record,
                            current_render_inputs=current_render_inputs,
                            current=current,
                            legacy_cache=legacy_renderer_ownership_cache,
                            scenario_cache=legacy_scenario_cache,
                        ):
                            reuse_mode = (
                                "scenario-path+renderer-ownership"
                                if record.get("scenario_identity_digest")
                                != current.get("scenario_identity_digest") else
                                "renderer-ownership"
                            )
                        else:
                            continue
                    selected = (
                        source_path,
                        payload,
                        record,
                        reuse_mode,
                        migration_provenance,
                    )
                    break
                selected = (source_path, payload, record, "exact", None)
                break
        if label_reasons or selected is None:
            if not label_reasons:
                label_reasons.extend(observed_reasons or ["no-valid-evidence"])
            recapture.append(label)
            reasons[label] = list(dict.fromkeys(label_reasons))
        else:
            reusable.append(label)
            (
                source_path,
                payload,
                record,
                reuse_mode,
                migration_provenance,
            ) = selected
            selected_sources[label] = {
                "manifest": str(source_path),
                "manifest_sha256": sha256_file(source_path),
                "record_sha256": _record_digest(record),
                "reuse_mode": reuse_mode,
                "source_profile": payload.get("capture_profile"),
                "source_run_id": source_path.parent.name,
            }
            if migration_provenance is not None:
                selected_sources[label][
                    "migration_provenance"
                ] = migration_provenance

    current_run_digest = str(current_render_inputs.get("run_level_digest", ""))
    selected_run_level_source: dict[str, Any] | None = None
    # v25 lifecycle evidence normally comes from the same single process that
    # captured the surfaces. A zero-surface process is needed only when every
    # PNG is reusable but the shutdown binding changed.
    run_level_candidates = (
        () if contract_version < 25 and profile == "full" else candidates
    )
    for source_path, payload, report, _records in run_level_candidates:
        # Run-level evidence describes the whole process lifecycle. Unlike an
        # atomic surface record, it cannot be salvaged from an incomplete,
        # unsealed, or otherwise globally invalid session.
        if report.get("global_issues"):
            continue
        run_level = payload.get("run_level_evidence")
        if not isinstance(run_level, dict):
            continue
        memory = run_level.get("dialog_memory_probe")
        shutdown = run_level.get("clean_shutdown")
        shutdown_valid = (
            isinstance(shutdown, dict)
            and shutdown.get("passed") is True
            and shutdown.get("capture_environment_digest")
            == current_render_inputs.get("environment_digest")
            and shutdown.get("run_level_digest") == current_run_digest
        )
        memory_valid = (
            profile != "full"
            or contract_version >= 25
            or (
                isinstance(memory, dict)
                and memory.get("passed") is True
                and memory.get("run_level_digest") == current_run_digest
            )
        )
        if shutdown_valid and memory_valid:
            selected_run_level_source = {
                "manifest": str(source_path),
                "manifest_sha256": sha256_file(source_path),
                "run_level_sha256": canonical_json_sha256(run_level),
                "source_run_id": source_path.parent.name,
            }
            break
    return {
        "base_manifest": str(deduplicated[0]) if deduplicated else None,
        "evidence_manifests": [str(path) for path in deduplicated],
        "rejected_manifests": rejected_manifests,
        "capture_contract_version": contract_version,
        "capture_contract_digest": contract_digest,
        "capture_profile": profile,
        "recapture_required": recapture,
        "reused": reusable,
        "reasons": reasons,
        "selected_sources": selected_sources,
        "run_level_reuse_policy": (
            "current-session-required"
            if profile == "full" and contract_version < 25
            else "exact-reuse-allowed"
        ),
        "run_level_recapture_required": selected_run_level_source is None,
        "selected_run_level_source": selected_run_level_source,
        "status": "ready",
    }


def _record_digest(record: Mapping[str, Any]) -> str:
    normalized = copy.deepcopy(dict(record))
    normalized.pop("path", None)
    normalized.pop("lineage", None)
    return canonical_json_sha256(normalized)


def _copy_png(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    shutil.copyfile(source, temporary)
    os.replace(temporary, destination)


def recover_progress_manifest(
    capture_dir: Path,
    *,
    output_dir: Path | None = None,
) -> Path:
    """Recover every complete atomic sidecar after timeout or process exit.

    The recovered manifest is intentionally incomplete and has no fabricated
    completion sentinel. Its passing surface records can enter a later exact
    reuse plan while unfinished or corrupt sidecars remain explicitly failed.
    """

    capture_dir = capture_dir.expanduser().resolve()
    recovery_output_dir = (
        capture_dir
        if output_dir is None
        else output_dir.expanduser().resolve()
    )
    recovery_output_dir.mkdir(parents=True, exist_ok=True)
    partial_path = capture_dir / "manifest.partial.json"
    _partial_path, payload = _load_manifest(partial_path)
    expected = [str(value) for value in payload.get("expected_faces", ())]
    expected_index = {label: index for index, label in enumerate(expected, start=1)}
    partial_records = {
        str(record.get("label", "")): record
        for record in payload.get("captures", ())
        if isinstance(record, dict)
    }
    recovered: dict[str, dict[str, Any]] = {}
    rejected: list[dict[str, str]] = []
    merged_partial_cleanup: list[str] = []
    for sidecar in sorted((capture_dir / "progress").glob("*.json")):
        try:
            _sidecar_path, sidecar_payload = _load_manifest(sidecar)
        except CaptureEvidenceError as error:
            rejected.append({"path": str(sidecar), "reason": str(error)})
            continue
        record = sidecar_payload.get("record")
        if not isinstance(record, dict):
            rejected.append({"path": str(sidecar), "reason": "record is missing"})
            continue
        label = str(record.get("label", ""))
        capture_id = record.get("capture_id")
        if label not in expected_index or capture_id != expected_index[label]:
            rejected.append({
                "path": str(sidecar),
                "reason": "record identity does not match the declared contract",
            })
            continue
        png = _safe_manifest_path(record.get("path"), capture_dir)
        if (
            png is None
            or not png.is_file()
            or record.get("png_sha256") != sha256_file(png)
        ):
            rejected.append({
                "path": str(sidecar),
                "reason": "record PNG is missing or its hash changed",
            })
            continue
        if label in recovered:
            raise CaptureEvidenceError(
                f"Duplicate recovered capture label {label!r}: {sidecar}"
            )
        recovered_record = copy.deepcopy(record)
        partial_record = partial_records.get(label)
        if (
            "cleanup_ms" not in recovered_record
            and isinstance(partial_record, dict)
            and all(
                partial_record.get(field) == recovered_record.get(field)
                for field in ("label", "capture_id", "path", "png_sha256")
            )
        ):
            sidecar_without_cleanup = copy.deepcopy(recovered_record)
            partial_without_cleanup = copy.deepcopy(partial_record)
            partial_cleanup = partial_without_cleanup.pop("cleanup_ms", None)
            sidecar_without_cleanup.pop("cleanup_ms", None)
            if (
                sidecar_without_cleanup == partial_without_cleanup
                and type(partial_cleanup) in {int, float}
                and float(partial_cleanup) >= 0.0
            ):
                recovered_record["cleanup_ms"] = partial_cleanup
                merged_partial_cleanup.append(label)
        recovered[label] = recovered_record
    records = [recovered[label] for label in expected if label in recovered]
    relocated_pngs: list[str] = []
    if recovery_output_dir != capture_dir:
        for record in records:
            source_png = _safe_manifest_path(record.get("path"), capture_dir)
            if source_png is None or not source_png.is_file():
                raise CaptureEvidenceError(
                    f"Recovered PNG cannot be relocated: {record.get('path')!r}"
                )
            destination_png = recovery_output_dir / source_png.name
            _copy_png(source_png, destination_png)
            if record.get("png_sha256") != sha256_file(destination_png):
                raise CaptureEvidenceError(
                    f"Relocated recovered PNG changed: {destination_png}"
                )
            record["path"] = destination_png.name
            relocated_pngs.append(str(record["label"]))
    payload.update({
        "capture_scope": "recovered-partial",
        "requested_faces": [str(value) for value in payload.get("requested_faces", ())],
        "captured_faces": [str(record["label"]) for record in records],
        "reused_faces": [],
        "screenshots": [str(record["path"]) for record in records],
        "captures": records,
        "recovery": {
            "source": str(partial_path),
            "accepted_sidecar_count": len(records),
            "merged_partial_cleanup_faces": merged_partial_cleanup,
            "relocated_png_faces": relocated_pngs,
            "rejected_sidecars": rejected,
        },
        "fixture_validations_complete": False,
        "dialog_scroll_audits_complete": False,
        "scope_complete": False,
        "complete": False,
    })
    recovered_path = recovery_output_dir / "manifest.recovered.json"
    atomic_json(recovered_path, payload)
    atomic_json(recovery_output_dir / "recovery-report.json", {
        "manifest": str(recovered_path),
        "recovered_faces": [str(record["label"]) for record in records],
        "merged_partial_cleanup_faces": merged_partial_cleanup,
        "relocated_png_faces": relocated_pngs,
        "rejected_sidecars": rejected,
        "status": "recovered" if records else "empty",
    })
    return recovered_path


def _source_manifest_closure(
    roots: Sequence[Path],
) -> dict[Path, tuple[str, dict[str, Any]]]:
    """Load complete local lineage bundles, resolving nested rows by SHA.

    Assembled manifests flatten every immutable ancestor snapshot into their
    own ``lineage`` directory. The snapshots retain their original bytes, so a
    nested relative path becomes stale after the next assembly generation.
    Each root manifest nevertheless declares the complete flattened bundle.
    Build a root-local digest index from that declaration and use nested row
    SHA values as the durable identity.
    """

    closure: dict[Path, tuple[str, dict[str, Any]]] = {}
    for raw_root in roots:
        root, root_payload = _load_manifest(raw_root)
        root_digest = sha256_file(root)
        digest_index: dict[str, Path] = {root_digest: root}
        declared_rows = root_payload.get("source_manifests", ())
        if not isinstance(declared_rows, (list, tuple)):
            raise CaptureEvidenceError(
                f"Malformed lineage manifest closure in {root}"
            )
        pending: list[tuple[Path, str]] = [(root, root_digest)]
        declared_digests: set[str] = set()
        for row in declared_rows:
            if not isinstance(row, dict):
                raise CaptureEvidenceError(
                    f"Malformed lineage manifest entry in {root}"
                )
            digest = row.get("sha256")
            if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
                raise CaptureEvidenceError(
                    f"Lineage manifest SHA is invalid in {root}"
                )
            if digest in declared_digests:
                raise CaptureEvidenceError(
                    f"Duplicate lineage manifest SHA {digest} in {root}"
                )
            declared_digests.add(digest)
            nested = _safe_manifest_path(row.get("path"), root.parent)
            if nested is None or not nested.is_file():
                raise CaptureEvidenceError(
                    f"Lineage manifest is missing or outside its source: {root}"
                )
            nested_digest = sha256_file(nested)
            if digest != nested_digest:
                raise CaptureEvidenceError(
                    f"Lineage manifest hash changed: {nested}"
                )
            digest_index[digest] = nested
            pending.append((nested, digest))

        visited_digests: set[str] = set()
        while pending:
            path, expected_digest = pending.pop(0)
            if expected_digest in visited_digests:
                continue
            resolved, payload = _load_manifest(path)
            actual_digest = sha256_file(resolved)
            if actual_digest != expected_digest:
                raise CaptureEvidenceError(
                    f"Lineage manifest hash changed: {resolved}"
                )
            existing = closure.get(resolved)
            if existing is not None and existing[0] != actual_digest:
                raise CaptureEvidenceError(
                    f"Lineage manifest identity is ambiguous: {resolved}"
                )
            closure[resolved] = (actual_digest, payload)
            visited_digests.add(actual_digest)
            nested_rows = payload.get("source_manifests", ())
            if not isinstance(nested_rows, (list, tuple)):
                raise CaptureEvidenceError(
                    f"Malformed lineage manifest closure in {resolved}"
                )
            for row in nested_rows:
                if not isinstance(row, dict):
                    raise CaptureEvidenceError(
                        f"Malformed lineage manifest entry in {resolved}"
                    )
                nested_digest = row.get("sha256")
                if (
                    not isinstance(nested_digest, str)
                    or SHA256_RE.fullmatch(nested_digest) is None
                ):
                    raise CaptureEvidenceError(
                        f"Lineage manifest SHA is invalid in {resolved}"
                    )
                nested = digest_index.get(nested_digest)
                if nested is None:
                    # Compatibility with an older non-flattened source: admit
                    # only a path contained beside that immutable snapshot,
                    # then bind it into this root-local digest index.
                    nested = _safe_manifest_path(row.get("path"), resolved.parent)
                    if nested is None or not nested.is_file():
                        raise CaptureEvidenceError(
                            "Lineage manifest is missing from the root-local "
                            f"digest index: {nested_digest}"
                        )
                    if sha256_file(nested) != nested_digest:
                        raise CaptureEvidenceError(
                            f"Lineage manifest hash changed: {nested}"
                        )
                    digest_index[nested_digest] = nested
                pending.append((nested, nested_digest))
    return closure


def _dialog_scroll_summary(
    *,
    profile: str,
    records: Mapping[str, Mapping[str, Any]],
    contract: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    if profile != "full":
        return {
            "required": False,
            "required_count": 0,
            "records": [],
            "four_state_scroll_matrix": {
                "required": False,
                "required_states": [],
                "observations": [],
                "witness_labels": {},
                "canonical_scroll_value_before": 0,
                "canonical_scroll_value_after": 0,
                "canonical_scroll_restored": True,
                "issues": [],
                "passed": True,
            },
            "passed": True,
        }
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
    rows: list[dict[str, Any]] = []
    for surface, labels in contract.items():
        for label, semantic in labels.items():
            audit = records.get(label, {}).get("dialog_scroll_audit", {})
            issues: list[str] = []
            if not isinstance(audit, dict):
                audit = {}
                issues.append("missing-dialog-scroll-audit")
            if audit.get("passed") is not True or audit.get("issues") != []:
                issues.append("dialog-scroll-audit-did-not-pass")
            if audit.get("surface") != surface:
                issues.append("scroll-coverage-surface-mismatch")
            if audit.get("actual_page_semantic") != semantic:
                issues.append("actual-scroll-page-semantic-mismatch")
            state_matrix = audit.get("four_state_scroll_matrix")
            if (
                not isinstance(state_matrix, dict)
                or state_matrix.get("passed") is not True
                or state_matrix.get("issues") != []
            ):
                issues.append("four-state-scroll-evidence-not-passed")
            row = {
                "label": label,
                "surface": surface,
                "expected_page_semantic": semantic,
                "actual_page_semantic": audit.get("actual_page_semantic", ""),
                **{field: audit.get(field) for field in metric_fields},
                "four_state_scroll_matrix": copy.deepcopy(state_matrix),
                "issues": list(dict.fromkeys(issues)),
                "passed": not issues,
            }
            rows.append(row)
    witness_observations: list[dict[str, Any]] = []
    witness_labels: dict[str, str] = {}
    for state in DIALOG_SCROLL_FOUR_STATE_NAMES:
        for row in rows:
            matrix = row.get("four_state_scroll_matrix")
            if not isinstance(matrix, dict):
                continue
            observation = next((
                item
                for item in list(matrix.get("observations", ()) or ())
                if isinstance(item, dict)
                and item.get("state") == state
                and item.get("passed") is True
                and item.get("issues") == []
            ), None)
            if observation is None:
                continue
            witness = copy.deepcopy(observation)
            witness["label"] = str(row.get("label", ""))
            witness_observations.append(witness)
            witness_labels[state] = witness["label"]
            break
    matrix_issues = [
        f"missing-scroll-state:{state}"
        for state in DIALOG_SCROLL_FOUR_STATE_NAMES
        if state not in witness_labels
    ]
    aggregate_matrix = {
        "required": True,
        "required_states": list(DIALOG_SCROLL_FOUR_STATE_NAMES),
        "observations": witness_observations,
        "witness_labels": witness_labels,
        "canonical_scroll_value_before": 0,
        "canonical_scroll_value_after": 0,
        "canonical_scroll_restored": True,
        "issues": matrix_issues,
        "passed": not matrix_issues,
    }
    expected_count = sum(len(values) for values in contract.values())
    aggregate_complete = len(rows) == expected_count
    return {
        "required": True,
        "required_count": len(rows),
        "attempted_count": len(rows),
        "aggregate_complete": aggregate_complete,
        "records": rows,
        "four_state_scroll_matrix": aggregate_matrix,
        "passed": bool(
            rows
            and aggregate_complete
            and aggregate_matrix["passed"]
            and all(row["passed"] for row in rows)
        ),
    }


def _run_level_valid(
    evidence: Any,
    *,
    profile: str,
    environment_digest: str,
    run_level_digest: str,
    contract_version: int = 24,
) -> bool:
    if not isinstance(evidence, dict):
        return False
    shutdown = evidence.get("clean_shutdown")
    if not (
        isinstance(shutdown, dict)
        and shutdown.get("passed") is True
        and shutdown.get("capture_environment_digest") == environment_digest
        and shutdown.get("run_level_digest") == run_level_digest
    ):
        return False
    if profile != "full" or contract_version >= 25:
        return True
    memory = evidence.get("dialog_memory_probe")
    return bool(
        isinstance(memory, dict)
        and memory.get("passed") is True
        and memory.get("run_level_digest") == run_level_digest
    )


def assemble_capture_manifest(
    *,
    reuse_plan: Mapping[str, Any],
    current_render_inputs: Mapping[str, Any],
    output_dir: Path,
    patch_manifest: Path | None = None,
    patch_manifests: Sequence[Path] = (),
    base_manifest: Path | None = None,
    evidence_manifests: Sequence[Path] = (),
) -> Path:
    """Assemble the exact latest passing state and run evidence atomically."""

    current_surfaces = current_render_inputs.get("surfaces")
    if not isinstance(current_surfaces, dict) or not current_surfaces:
        raise CaptureEvidenceError("Current render-input catalog is invalid")
    expected = [str(label) for label in current_surfaces]
    profile = str(reuse_plan.get(
        "capture_profile",
        current_render_inputs.get("capture_profile", "representative"),
    ))
    if profile not in {"representative", "full"}:
        raise CaptureEvidenceError(f"Unknown capture profile: {profile!r}")
    raw_patch_paths = ([patch_manifest] if patch_manifest is not None else []) + list(
        patch_manifests
    )
    patch_paths: list[Path] = []
    patch_payloads: dict[Path, dict[str, Any]] = {}
    patch_sources: dict[
        str,
        tuple[Path, dict[str, Any], dict[str, Any], dict[str, Any] | None],
    ] = {}
    patch_requested: set[str] = set()
    for raw_patch_path in raw_patch_paths:
        patch_path, patch = _load_manifest(raw_patch_path)
        if patch_path in patch_payloads:
            continue
        patch_report = surface_validation_report(patch_path)
        if patch.get("capture_profile") != profile:
            raise CaptureEvidenceError("Patch manifest uses a different capture profile")
        patch_records = _capture_records_by_label(patch, source=patch_path)
        requested = {
            str(value) for value in patch.get("requested_faces", ())
        }
        duplicate = requested.intersection(patch_requested)
        if duplicate:
            raise CaptureEvidenceError(
                "Patch manifests overlap capture surfaces: "
                + ", ".join(sorted(duplicate))
            )
        patch_paths.append(patch_path)
        patch_payloads[patch_path] = patch
        patch_requested.update(requested)
        for label in requested:
            patch_sources[label] = (
                patch_path,
                patch,
                patch_report,
                patch_records.get(label),
            )

    selected_sources = dict(reuse_plan.get("selected_sources", {}) or {})
    if base_manifest is not None and not selected_sources:
        base_path, base_payload = _load_manifest(base_manifest)
        base_records = _capture_records_by_label(base_payload, source=base_path)
        base_manifest_sha = sha256_file(base_path)
        for label in reuse_plan.get("reused", ()):
            source_record = base_records.get(str(label))
            if source_record is None:
                raise CaptureEvidenceError(
                    f"Base manifest has no selected record for {label}"
                )
            selected_sources[str(label)] = {
                "manifest": str(base_path),
                "manifest_sha256": base_manifest_sha,
                "record_sha256": _record_digest(source_record),
                "source_run_id": base_path.parent.name,
                "source_profile": base_payload.get("capture_profile"),
            }
    source_paths = {
        Path(str(row.get("manifest", ""))).expanduser().resolve()
        for row in selected_sources.values()
        if isinstance(row, dict) and row.get("manifest")
    }
    source_paths.update(patch_paths)
    run_source_row = reuse_plan.get("selected_run_level_source")
    if isinstance(run_source_row, dict) and run_source_row.get("manifest"):
        source_paths.add(Path(str(run_source_row["manifest"])).expanduser().resolve())
    if not source_paths:
        raise CaptureEvidenceError("No captured or reusable evidence is available")
    closure = _source_manifest_closure(sorted(source_paths))
    source_payloads = {path: payload for path, (_digest, payload) in closure.items()}
    source_records = {
        path: _capture_records_by_label(payload, source=path)
        for path, payload in source_payloads.items()
    }

    # Bind assembly to the exact immutable evidence selected by the planner.
    # Reopening the same path is insufficient: a coherent rewrite could update
    # both the manifest and its completion sentinel between planning and here.
    for raw_label, selection in selected_sources.items():
        label = str(raw_label)
        if label not in current_surfaces:
            raise CaptureEvidenceError(
                f"Selected evidence names an unknown capture surface: {label}"
            )
        if not isinstance(selection, dict) or not selection.get("manifest"):
            raise CaptureEvidenceError(
                f"Selected evidence binding is malformed for {label}"
            )
        source_path = Path(str(selection["manifest"])).expanduser().resolve()
        source_entry = closure.get(source_path)
        expected_manifest_sha = selection.get("manifest_sha256")
        if (
            not isinstance(expected_manifest_sha, str)
            or SHA256_RE.fullmatch(expected_manifest_sha) is None
        ):
            raise CaptureEvidenceError(
                f"Selected manifest SHA binding is invalid for {label}"
            )
        if source_entry is None or source_entry[0] != expected_manifest_sha:
            raise CaptureEvidenceError(
                f"Selected manifest changed after planning for {label}"
            )
        source_record = source_records.get(source_path, {}).get(label)
        expected_record_sha = selection.get("record_sha256")
        if (
            not isinstance(expected_record_sha, str)
            or SHA256_RE.fullmatch(expected_record_sha) is None
        ):
            raise CaptureEvidenceError(
                f"Selected record SHA binding is invalid for {label}"
            )
        if (
            source_record is None
            or _record_digest(source_record) != expected_record_sha
        ):
            raise CaptureEvidenceError(
                f"Selected record changed after planning for {label}"
            )

    if isinstance(run_source_row, dict) and run_source_row.get("manifest"):
        run_source_path = Path(
            str(run_source_row["manifest"])
        ).expanduser().resolve()
        expected_run_manifest_sha = run_source_row.get("manifest_sha256")
        if (
            not isinstance(expected_run_manifest_sha, str)
            or SHA256_RE.fullmatch(expected_run_manifest_sha) is None
        ):
            raise CaptureEvidenceError(
                "Selected run-level manifest SHA binding is invalid"
            )
        run_source_entry = closure.get(run_source_path)
        if (
            run_source_entry is None
            or run_source_entry[0] != expected_run_manifest_sha
        ):
            raise CaptureEvidenceError(
                "Selected run-level manifest changed after planning"
            )
        expected_run_level_sha = run_source_row.get("run_level_sha256")
        if (
            not isinstance(expected_run_level_sha, str)
            or SHA256_RE.fullmatch(expected_run_level_sha) is None
        ):
            raise CaptureEvidenceError(
                "Selected run-level evidence SHA binding is invalid"
            )
        current_run_level = source_payloads.get(run_source_path, {}).get(
            "run_level_evidence"
        )
        if (
            not isinstance(current_run_level, dict)
            or canonical_json_sha256(current_run_level) != expected_run_level_sha
        ):
            raise CaptureEvidenceError(
                "Selected run-level evidence changed after planning"
            )

    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    lineage_dir = output_dir / "lineage"
    lineage_dir.mkdir()
    for source_path, (digest, _payload) in closure.items():
        destination = lineage_dir / f"manifest-{digest}.json"
        if not destination.exists():
            shutil.copyfile(source_path, destination)
        if sha256_file(destination) != digest:
            raise CaptureEvidenceError(
                f"Lineage manifest changed while assembling: {source_path}"
            )

    captures: list[dict[str, Any]] = []
    screenshots: list[str] = []
    captured_faces: list[str] = []
    reused_faces: list[str] = []
    failures: list[dict[str, str]] = []
    width = max(2, len(str(len(expected))))
    for capture_id, label in enumerate(expected, start=1):
        source_path: Path | None = None
        source_payload: dict[str, Any] | None = None
        source_record: dict[str, Any] | None = None
        selection: Mapping[str, Any] | None = None
        evidence_status = ""
        if label in patch_requested:
            patch_path, patch, patch_report, patch_record = patch_sources[label]
            if patch_report.get("surfaces", {}).get(label, {}).get("status") == "passed":
                source_path = patch_path
                source_payload = patch
                source_record = patch_record
                evidence_status = "captured"
                captured_faces.append(label)
            else:
                failures.append({
                    "label": label,
                    "reason": "Replacement capture did not pass; prior evidence was not reused",
                })
        else:
            selection = selected_sources.get(label)
            if isinstance(selection, dict) and selection.get("manifest"):
                candidate = Path(str(selection["manifest"])).expanduser().resolve()
                source_path = candidate
                source_payload = source_payloads.get(candidate)
                source_record = source_records.get(candidate, {}).get(label)
                evidence_status = "reused"
                reused_faces.append(label)
        if source_path is None or source_payload is None or source_record is None:
            if not any(row["label"] == label for row in failures):
                failures.append({"label": label, "reason": "No valid evidence is available"})
            continue
        source_png = _safe_manifest_path(source_record.get("path"), source_path.parent)
        if source_png is None or not source_png.is_file():
            failures.append({"label": label, "reason": "Source PNG is unavailable"})
            continue
        destination = output_dir / f"{capture_id:0{width}d}-{label}.png"
        _copy_png(source_png, destination)
        copied_sha = sha256_file(destination)
        if copied_sha != source_record.get("png_sha256"):
            raise CaptureEvidenceError(f"Copied PNG hash changed for {label}")
        current = dict(current_surfaces.get(label, {}) or {})
        source_manifest_sha = closure[source_path][0]
        record = copy.deepcopy(source_record)
        lineage = {
            "evidence_status": evidence_status,
            "source_manifest_sha256": source_manifest_sha,
            "source_package_sha256": source_record.get(
                "source_package_sha256",
                source_payload.get("production_package_sha256", ""),
            ),
            "source_record_sha256": _record_digest(source_record),
            "source_run_id": source_path.parent.name,
        }
        migration_provenance = (
            selection.get("migration_provenance")
            if isinstance(selection, Mapping) else None
        )
        if isinstance(migration_provenance, dict):
            lineage["migration_provenance"] = copy.deepcopy(
                migration_provenance
            )
        source_advisories = [
            copy.deepcopy(advisory)
            for advisory in source_payload.get("capture_advisories", ())
            if isinstance(advisory, dict)
            and str(advisory.get("label", "")) == label
        ]
        record.update({
            "capture_id": capture_id,
            "evidence_status": evidence_status,
            "label": label,
            # Keep assembled-owned artifacts relative to the final manifest
            # so the evidence directory remains valid after relocation.
            "path": destination.name,
            "png_sha256": copied_sha,
            "render_input_digest": current.get("digest"),
            "render_input_count": current.get("input_count"),
            "capture_environment_digest": current.get("environment_digest"),
            "scenario_identity_digest": current.get("scenario_identity_digest"),
            "surface_contract_digest": current.get("surface_contract_digest"),
            "evidence_schema_digest": current_render_inputs.get("evidence_schema_digest"),
            "lineage": lineage,
            "capture_advisories": source_advisories,
        })
        # Capture ids are profile-local ordinals.  A representative capture
        # reused by the full contract therefore needs every destination-owned
        # identity mirror rewritten, while its source step and immutable
        # source-record digest remain preserved in lineage.
        fixture = record.get("fixture_validation")
        if isinstance(fixture, dict):
            fixture["capture_id"] = capture_id
            audit = record.get("audit")
            if isinstance(audit, dict):
                audit["fixture_identity"] = copy.deepcopy(fixture)
        captures.append(record)
        screenshots.append(destination.name)

    records_by_label = {str(record["label"]): record for record in captures}
    dialog_scroll = _dialog_scroll_summary(
        profile=profile,
        records=records_by_label,
        contract=dict(current_render_inputs.get("dialog_scroll_contract", {}) or {}),
    )
    environment_digest = str(current_render_inputs.get("environment_digest", ""))
    run_digest = str(current_render_inputs.get("run_level_digest", ""))
    contract_version = int(reuse_plan.get("capture_contract_version", 0) or 0)
    run_level: dict[str, Any] = {}
    run_source_path: Path | None = None
    # Prefer current process evidence, then exact reusable run evidence.
    for patch_path in patch_paths:
        patch = patch_payloads[patch_path]
        if _run_level_valid(
            patch.get("run_level_evidence"),
            profile=profile,
            environment_digest=environment_digest,
            run_level_digest=run_digest,
            contract_version=contract_version,
        ):
            run_level = copy.deepcopy(patch["run_level_evidence"])
            run_source_path = patch_path
            break
    if not run_level and isinstance(run_source_row, dict) and run_source_row.get("manifest"):
        candidate = Path(str(run_source_row["manifest"])).expanduser().resolve()
        source_run = source_payloads.get(candidate, {}).get("run_level_evidence")
        if _run_level_valid(
            source_run,
            profile=profile,
            environment_digest=environment_digest,
            run_level_digest=run_digest,
            contract_version=contract_version,
        ):
            run_level = copy.deepcopy(source_run)
            run_source_path = candidate
    if run_source_path is not None:
        run_level["lineage"] = {
            "source_manifest_sha256": closure[run_source_path][0],
            "source_run_id": run_source_path.parent.name,
        }
    else:
        failures.append({
            "label": "run-level-evidence",
            "reason": "No valid clean-shutdown/run-level evidence is available",
        })

    complete = bool(
        not failures
        and len(captures) == len(expected)
        and _run_level_valid(
            run_level,
            profile=profile,
            environment_digest=environment_digest,
            run_level_digest=run_digest,
            contract_version=contract_version,
        )
    )
    displays = list(dict.fromkeys(
        str(record.get("capture_display", ""))
        for record in captures
        if str(record.get("capture_display", "")) in {"primary", "secondary"}
    ))
    template = (
        patch_payloads[patch_paths[0]]
        if patch_paths else
        next(iter(source_payloads.values()))
    )
    memory_entry = (
        run_level.get("dialog_memory_probe", {})
        if isinstance(run_level, dict) else {}
    )
    memory_result = (
        copy.deepcopy(memory_entry.get("result", {}))
        if isinstance(memory_entry, dict) else {}
    )
    if (profile != "full" or contract_version >= 25) and not memory_result:
        memory_result = {"status": "not-run", "cycles": 0}
    assembled_warnings: list[dict[str, Any]] = []
    assembled_advisories: list[dict[str, Any]] = []
    for record in captures:
        label = str(record.get("label", ""))
        for warning_field in (
            "text_layout_warnings",
            "geometry_layout_warnings",
        ):
            for raw_warning in record.get(warning_field, ()):
                if not isinstance(raw_warning, dict):
                    continue
                warning = copy.deepcopy(raw_warning)
                warning.setdefault("capture", label)
                assembled_warnings.append(warning)
        for raw_advisory in record.get("capture_advisories", ()):
            if isinstance(raw_advisory, dict):
                assembled_advisories.append(copy.deepcopy(raw_advisory))
    payload = copy.deepcopy(template)
    payload.update({
        "capture_contract_version": reuse_plan.get("capture_contract_version"),
        "capture_contract_digest": current_render_inputs.get("capture_contract_digest"),
        "scenario_schema_version": current_render_inputs.get("scenario_schema_version"),
        "scenario_contract_digest": current_render_inputs.get("scenario_contract_digest"),
        "evidence_schema_digest": current_render_inputs.get("evidence_schema_digest"),
        "capture_profile": profile,
        "capture_scope": "assembled",
        "capture_display": displays[0] if len(displays) == 1 else "mixed",
        "capture_displays": displays,
        "requested_faces": expected,
        "captured_faces": captured_faces,
        "reused_faces": reused_faces,
        "invalidated_faces": list(reuse_plan.get("recapture_required", ())),
        "screenshots": screenshots,
        "captures": captures,
        "failures": failures,
        "capture_advisories": assembled_advisories,
        "text_layout_warnings": assembled_warnings,
        "expected_count": len(expected),
        "fixture_validations_complete": len(captures) == len(expected),
        "dialog_scroll_audits": dialog_scroll,
        "dialog_scroll_audits_complete": dialog_scroll.get("passed") is True,
        "dialog_memory_probe": memory_result,
        "dialog_memory_probe_complete": (
            contract_version >= 25
            or profile != "full"
            or (
                isinstance(memory_entry, dict)
                and memory_entry.get("passed") is True
            )
        ),
        "responsive_stability": {
            "required": False,
            "pair_count": 0,
            "pairs": [],
            "coverage": "automated-responsive-geometry",
            "passed": True,
        },
        "responsive_stability_complete": True,
        "scope_complete": complete,
        "complete": complete,
        "production_package_sha256": current_render_inputs.get("production_archive_sha256"),
        "capture_environment_digest": environment_digest,
        "render_inputs": copy.deepcopy(dict(current_render_inputs)),
        "run_level_evidence": run_level,
        "source_manifests": [
            {"path": f"lineage/manifest-{digest}.json", "sha256": digest}
            for digest in sorted({row[0] for row in closure.values()})
        ],
    })
    manifest = output_dir / "manifest.json"
    atomic_json(manifest, payload)
    atomic_json(output_dir / "capture-complete.json", {
        "complete": complete,
        "exit_code": 0 if complete else 1,
        "manifest": manifest.name,
        "manifest_sha256": sha256_file(manifest),
        "scope_complete": complete,
    })
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("manifest", type=Path)
    plan_parser = subparsers.add_parser("plan")
    plan_parser.add_argument("base_manifest", type=Path)
    plan_parser.add_argument("render_inputs", type=Path)
    plan_parser.add_argument("--contract-version", type=int, required=True)
    plan_parser.add_argument("--surface", action="append", default=[])
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    if arguments.command == "inspect":
        result = surface_validation_report(arguments.manifest)
    else:
        base_path, base = _load_manifest(arguments.base_manifest)
        del base_path
        current = json.loads(arguments.render_inputs.read_text(encoding="utf-8"))
        result = plan_incremental_capture(
            base_manifest=arguments.base_manifest,
            current_render_inputs=current,
            expected_labels=[str(value) for value in base.get("expected_faces", ())],
            contract_version=arguments.contract_version,
            contract_digest=str(current.get("capture_contract_digest", "")),
            profile=str(current.get("capture_profile", "representative")),
            explicit_surfaces=arguments.surface,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CaptureEvidenceError as error:
        print(json.dumps({"error": str(error), "status": "failed"}), file=sys.stderr)
        raise SystemExit(1)
