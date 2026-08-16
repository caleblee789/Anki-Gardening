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
from typing import Any, Sequence

from PIL import Image, ImageChops, ImageOps, UnidentifiedImageError


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CAPTURE_SOURCE = ROOT / "ankigarden" / "capture_ui_faces.py"
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
CONTACT_SHEET_PREVIEW_INSET = 8
MIN_LOGICAL_CAPTURE_DIMENSION = 100
MAX_PNG_PIXELS = 100_000_000
CAPTURE_SCALE_FACTOR = 1.5
MEMORY_PROBE_CYCLES = 12
MEMORY_PROBE_CLASSES = (
    "NurseryDialog",
    "DialogShell",
    "PlantStoryDialog",
    "GardenDialog",
)
_NO_INFERRED_VALUE = object()
# These are evidence aliases, not broad duplicate exemptions.  A duplicate hash
# must match one complete set exactly; subsets and supersets still fail.
INTENTIONAL_DUPLICATE_VISUALS: dict[frozenset[str], str] = {
    frozenset({"starter-nursery-plants", "starter-action-above-footer"}): (
        "The same first-run Nursery painting is captured once for state and once "
        "for the action-above-footer geometry audit."
    ),
    frozenset({
        "display-scaling-200-qt-representative",
        "resize-dashboard-minimum",
    }): (
        "Both are the 620x520 logical dashboard at the unchanged 150 percent "
        "process scale; one is explicitly a Qt logical-viewport proxy."
    ),
}


class CaptureValidationError(ValueError):
    """Raised when capture evidence does not satisfy the source contract."""

    def __init__(self, issues: Sequence[str]) -> None:
        self.issues = tuple(str(issue) for issue in issues)
        super().__init__("; ".join(self.issues))


@dataclass(frozen=True)
class CaptureContract:
    version: int
    groups: tuple[tuple[str, tuple[str, ...]], ...]

    @property
    def labels(self) -> tuple[str, ...]:
        return tuple(
            label
            for _group, labels in self.groups
            for label in labels
        )


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


def load_capture_contract(source_path: Path = DEFAULT_CAPTURE_SOURCE) -> CaptureContract:
    """Read the release capture contract without importing Anki or Qt."""

    try:
        source = source_path.read_text(encoding="utf-8")
        module = ast.parse(source, filename=str(source_path))
        version_value = ast.literal_eval(
            _assignment_value(module, "CAPTURE_CONTRACT_VERSION")
        )
        groups_value = ast.literal_eval(
            _assignment_value(module, "CAPTURE_FACE_GROUPS")
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

    normalized_groups: list[tuple[str, tuple[str, ...]]] = []
    if not isinstance(groups_value, (tuple, list)) or not groups_value:
        issues.append("CAPTURE_FACE_GROUPS must be a non-empty literal sequence")
    else:
        for group_index, raw_group in enumerate(groups_value, start=1):
            if not isinstance(raw_group, (tuple, list)) or len(raw_group) != 2:
                issues.append(
                    f"CAPTURE_FACE_GROUPS group {group_index} must contain a name and labels"
                )
                continue
            raw_name, raw_labels = raw_group
            name = raw_name.strip() if isinstance(raw_name, str) else ""
            if not name:
                issues.append(
                    f"CAPTURE_FACE_GROUPS group {group_index} has an empty name"
                )
            if not isinstance(raw_labels, (tuple, list)) or not raw_labels:
                issues.append(
                    f"CAPTURE_FACE_GROUPS group {name or group_index!r} has no labels"
                )
                continue
            labels = tuple(
                label.strip() if isinstance(label, str) else ""
                for label in raw_labels
            )
            if any(not label for label in labels):
                issues.append(
                    f"CAPTURE_FACE_GROUPS group {name or group_index!r} has an invalid label"
                )
            normalized_groups.append((name, labels))

    group_names = [name for name, _labels in normalized_groups]
    labels = [label for _name, group_labels in normalized_groups for label in group_labels]
    if len(group_names) != len(set(group_names)):
        issues.append("CAPTURE_FACE_GROUPS contains duplicate group names")
    if len(labels) != len(set(labels)):
        issues.append("CAPTURE_FACE_GROUPS contains duplicate labels")
    if issues:
        raise CaptureValidationError(issues)
    return CaptureContract(int(version_value), tuple(normalized_groups))


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
    saw_resize_loop = False

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
        if isinstance(statement, ast.For):
            # The resize matrix is repository-owned data.  Fail closed if the
            # renderer function no longer iterates over that exact source.
            if (
                saw_resize_loop
                or not isinstance(statement.iter, ast.Name)
                or statement.iter.id != "RESIZE_MATRIX_SPECS"
                or len(statement.body) != 1
                or not isinstance(statement.body[0], ast.If)
            ):
                raise CaptureValidationError(("resize renderer loop is unsupported",))
            saw_resize_loop = True
            try:
                specs = ast.literal_eval(_assignment_value(module, "RESIZE_MATRIX_SPECS"))
                families = ast.literal_eval(_assignment_value(module, "_RESIZE_WINDOW_FAMILIES"))
            except (ValueError, SyntaxError) as error:
                raise CaptureValidationError(("resize renderer declarations must be literals",)) from error
            if not isinstance(specs, (tuple, list)) or not isinstance(families, dict):
                raise CaptureValidationError(("resize renderer declarations are malformed",))
            for spec in specs:
                if not isinstance(spec, (tuple, list)) or len(spec) < 2:
                    raise CaptureValidationError(("resize renderer specification is malformed",))
                label, family_key = spec[:2]
                family = families.get(family_key)
                if not isinstance(label, str) or not isinstance(family, str) or not family:
                    raise CaptureValidationError(("resize renderer family is missing",))
                add((label,), family)
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

    if not saw_resize_loop:
        raise CaptureValidationError(("renderer mapping is missing the resize matrix",))
    expected = set(contract.labels)
    actual = set(mapping)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if extra:
            details.append("extra " + ", ".join(extra))
        raise CaptureValidationError(("renderer mapping does not cover the contract: " + "; ".join(details),))
    return {label: mapping[label] for label in contract.labels}


def load_expected_resize_layout_modes(
    source_path: Path = DEFAULT_CAPTURE_SOURCE,
) -> dict[str, str]:
    """Read the source-owned semantic layout mode for every resize fixture."""

    module = _source_module(source_path)
    try:
        specs = ast.literal_eval(_assignment_value(module, "RESIZE_MATRIX_SPECS"))
        modes = ast.literal_eval(
            _assignment_value(module, "RESIZE_MATRIX_LAYOUT_MODES")
        )
    except (ValueError, SyntaxError) as error:
        raise CaptureValidationError(
            ("resize layout-mode declarations must be literals",)
        ) from error
    if not isinstance(specs, (tuple, list)) or not isinstance(modes, dict):
        raise CaptureValidationError(("resize layout-mode declarations are malformed",))
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
        "_NURSERY_CAPTURE_LABELS",
        "_SETTINGS_CAPTURE_LABELS",
    ):
        source_values[name] = _static_renderer_value(
            _assignment_value(module, name),
            module,
        )
    try:
        resize_specs = ast.literal_eval(_assignment_value(module, "RESIZE_MATRIX_SPECS"))
    except (ValueError, SyntaxError) as error:
        raise CaptureValidationError(("resize state profiles must be literal",)) from error
    resize_modes = load_expected_resize_layout_modes(source_path)
    source_values["RESIZE_MATRIX_SPECS"] = resize_specs
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
                "nursery", "settings", "customize", "dialog",
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
    """Bind every rendered tile preview to its exact manifest screenshot."""

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
                preview_y = (
                    preview_box[1]
                    + (preview_box[3] - preview_box[1] - preview.height) // 2
                )
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
            y += (
                math.ceil(len(labels) / CONTACT_SHEET_COLUMNS)
                * CONTACT_SHEET_CELL_HEIGHT
                + CONTACT_SHEET_GROUP_GAP
            )
    except (OSError, UnidentifiedImageError, ValueError) as error:
        issues.append(f"could not bind contact preview pixels: {error}")
    return issues


def _contact_metadata_issues(
    page_path: Path,
    *,
    page_number: int,
    page_count: int,
    package_version: str,
    package_sha256: str,
    manifest_path: Path,
) -> list[str]:
    """Verify generator-owned PNG text provenance for one contact page."""

    try:
        with Image.open(page_path) as opened:
            opened.load()
            metadata = dict(opened.text)
    except (OSError, UnidentifiedImageError, ValueError) as error:
        return [f"could not read contact-sheet PNG provenance: {error}"]

    issues: list[str] = []
    expected = {
        "Anki Garden release": package_version,
        "Package SHA-256": package_sha256,
        "Contact sheet page": f"{page_number} of {page_count}",
    }
    for key, value in expected.items():
        if metadata.get(key) != value:
            issues.append(f"PNG metadata {key!r} must be {value!r}")
    raw_manifest = metadata.get("Capture manifest")
    resolved_manifest = _resolved_evidence_path(raw_manifest, page_path.parent)
    if resolved_manifest != manifest_path.resolve():
        issues.append("PNG metadata 'Capture manifest' references a different manifest")
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
    breakpoint_fixture = "-content-" in label
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


def _validate_memory_probe(payload: dict[str, Any], issues: list[str]) -> None:
    if payload.get("dialog_memory_probe_complete") is not True:
        issues.append("dialog_memory_probe_complete must be true")
    probe = payload.get("dialog_memory_probe")
    if not isinstance(probe, dict):
        issues.append("dialog_memory_probe must be an object")
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


def validate_capture_manifest(
    manifest_path: Path,
    *,
    capture_source: Path = DEFAULT_CAPTURE_SOURCE,
) -> dict[str, Any]:
    """Validate one full release manifest and all manifest-owned PNG evidence."""

    contract = load_capture_contract(capture_source)
    renderer_families = load_expected_renderer_families(
        capture_source,
        contract=contract,
    )
    resize_layout_modes = load_expected_resize_layout_modes(capture_source)
    state_evidence_contracts = load_expected_state_evidence_contracts(
        capture_source,
        contract=contract,
    )
    manifest_path = manifest_path.resolve()
    payload = _load_json_object(manifest_path, "capture manifest")
    session_dir = manifest_path.parent.resolve()
    expected_labels = contract.labels
    expected_count = len(expected_labels)
    issues: list[str] = []

    if payload.get("capture_contract_version") != contract.version:
        issues.append(
            "capture_contract_version does not match the repository contract "
            f"({payload.get('capture_contract_version')!r} != {contract.version})"
        )
    if payload.get("capture_profile") != "full":
        issues.append("capture_profile must be 'full' for release evidence")
    raw_scale = payload.get("requested_scale_factor")
    try:
        scale = float(raw_scale) if not isinstance(raw_scale, bool) else math.nan
    except (TypeError, ValueError):
        scale = math.nan
    if not math.isfinite(scale) or not math.isclose(scale, CAPTURE_SCALE_FACTOR):
        issues.append("requested_scale_factor must be numeric-equivalent to 1.5")
    if _manifest_groups(payload) != contract.groups:
        issues.append("capture_groups does not exactly match source order and labels")
    if payload.get("expected_faces") != list(expected_labels):
        issues.append("expected_faces does not exactly match source order and labels")
    if payload.get("expected_count") != expected_count:
        issues.append(
            f"expected_count must be {expected_count}, found {payload.get('expected_count')!r}"
        )
    if payload.get("complete") is not True:
        issues.append("capture manifest is not marked complete")
    if payload.get("fixture_validations_complete") is not True:
        issues.append("fixture_validations_complete is not true")

    failures = payload.get("failures")
    if not isinstance(failures, list):
        issues.append("failures must be a list")
    elif failures:
        issues.append(f"capture manifest reports {len(failures)} failure(s)")
    warnings = payload.get("text_layout_warnings")
    if not isinstance(warnings, list):
        issues.append("text_layout_warnings must be a list")
    elif warnings:
        issues.append(f"capture manifest reports {len(warnings)} text-layout warning(s)")
    _validate_memory_probe(payload, issues)

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
    for index, label in enumerate(expected_labels, start=1):
        state_contract = state_evidence_contracts[label]
        expected_state_profile = state_contract["profile"]
        expected_name = f"{index:02d}-{label}.png"
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
        record_path = _resolved_evidence_path(record.get("path"), session_dir)
        if record_path != screenshot_path:
            issues.append(f"capture {index:03d} {label}: record path does not match screenshots")

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
            issues.append(
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
                issues.append(
                    f"capture {index:03d} {label}: {warning_field} is not empty"
                )

        fixture_source = record.get("fixture_source")
        if (
            not isinstance(fixture_source, str)
            or not fixture_source.startswith("ordered-step-")
        ):
            issues.append(f"capture {index:03d} {label}: fixture_source is missing")
            fixture_source = ""
        fixture = record.get("fixture_validation")
        if not isinstance(fixture, dict):
            issues.append(f"capture {index:03d} {label}: fixture_validation is missing")
            continue
        if fixture.get("passed") is not True:
            issues.append(f"capture {index:03d} {label}: fixture validation did not pass")
        if type(fixture.get("capture_id")) is not int or fixture.get("capture_id") != index:
            issues.append(f"capture {index:03d} {label}: fixture capture_id must be {index}")
        if fixture.get("fixture_id") != label:
            issues.append(f"capture {index:03d} {label}: fixture_id does not match label")
        if fixture.get("fixture_source") != fixture_source:
            issues.append(f"capture {index:03d} {label}: fixture sources disagree")
        if fixture.get("state_profile") != label:
            issues.append(
                f"capture {index:03d} {label}: state_profile must match the capture label"
            )
        postcondition = fixture.get("postcondition")
        if not isinstance(postcondition, dict):
            issues.append(f"capture {index:03d} {label}: postcondition must be an object")
        else:
            if postcondition.get("profile_id") != label:
                issues.append(
                    f"capture {index:03d} {label}: postcondition profile_id must match label"
                )
            kind = postcondition.get("kind")
            if kind != state_contract["kind"]:
                issues.append(
                    f"capture {index:03d} {label}: postcondition kind must be "
                    f"{state_contract['kind']!r}"
                )
            facts = postcondition.get("facts")
            if not isinstance(facts, dict) or not facts:
                issues.append(
                    f"capture {index:03d} {label}: postcondition facts must be nonempty"
                )
            elif set(facts) != set(state_contract["required_facts"]):
                missing_facts = sorted(
                    set(state_contract["required_facts"]) - set(facts)
                )
                extra_facts = sorted(
                    set(facts) - set(state_contract["required_facts"])
                )
                issues.append(
                    f"capture {index:03d} {label}: postcondition fact schema mismatch "
                    f"(missing={missing_facts!r}, extra={extra_facts!r})"
                )
            if isinstance(facts, dict):
                for fact_name, expected_value in state_contract[
                    "expected_fact_values"
                ].items():
                    if facts.get(fact_name) != expected_value:
                        issues.append(
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
                        issues.append(
                            f"capture {index:03d} {label}: postcondition fact "
                            "'keyboard_focus_fixture_cleared' must prove the "
                            "Progress button does not own focus"
                        )
            if label in resize_layout_modes:
                if kind != "resize":
                    issues.append(
                        f"capture {index:03d} {label}: resize postcondition kind must be resize"
                    )
                if (
                    not isinstance(facts, dict)
                    or facts.get("layout_mode") != resize_layout_modes[label]
                ):
                    issues.append(
                        f"capture {index:03d} {label}: resize layout_mode fact must be "
                        f"{resize_layout_modes[label]!r}"
                    )
                if layout_mode != resize_layout_modes[label]:
                    issues.append(
                        f"capture {index:03d} {label}: recorded layout_mode must be "
                        f"{resize_layout_modes[label]!r}"
                    )
                if (
                    not isinstance(facts, dict)
                    or facts.get("geometry_acceptance") != geometry_acceptance
                ):
                    issues.append(
                        f"capture {index:03d} {label}: postcondition geometry acceptance "
                        "does not match the record"
                    )
            if postcondition.get("issues") != []:
                issues.append(
                    f"capture {index:03d} {label}: postcondition issues must be empty"
                )
            if postcondition.get("passed") is not True:
                issues.append(
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
        if isinstance(audit, dict):
            record_audits[label] = audit
        if logical_size is not None and dpr is not None:
            record_geometry[label] = (
                logical_size[0],
                logical_size[1],
                dpr,
                renderer_families[label],
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
            issues.append(
                "unapproved duplicate visual evidence: " + ", ".join(digest_labels)
            )
            continue
        geometries = {record_geometry.get(label) for label in digest_labels}
        if None in geometries or len(geometries) != 1:
            issues.append(
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
                issues.append("starter Nursery duplicate lacks the footer-clearance audit")
        elif label_set == frozenset({
            "display-scaling-200-qt-representative", "resize-dashboard-minimum"
        }):
            scaling_audit = record_audits.get("display-scaling-200-qt-representative", {})
            if not (
                scaling_audit.get("representative_kind") == "deterministic-qt-logical-viewport"
                and scaling_audit.get("effective_scale_percent") == 200
                and scaling_audit.get("os_display_scaling_changed") is False
            ):
                issues.append("display-scaling duplicate lacks explicit Qt-proxy provenance")

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
        "manifest": str(manifest_path),
        "status": "valid",
    }


def validate_contact_sheet_set(
    contact_sheet_set_path: Path,
    *,
    manifest_path: Path,
    capture_source: Path = DEFAULT_CAPTURE_SOURCE,
) -> dict[str, Any]:
    """Validate optional contact-sheet index, PNG pages, order, and counts."""

    contract = load_capture_contract(capture_source)
    expected_count = len(contract.labels)
    expected_group_names = [name for name, _labels in contract.groups]
    expected_pages = expected_contact_sheet_pages(contract)
    expected_label_pages = expected_contact_sheet_page_groups(contract)
    contact_sheet_set_path = contact_sheet_set_path.resolve()
    manifest_path = manifest_path.resolve()
    payload = _load_json_object(contact_sheet_set_path, "contact-sheet set")
    set_dir = contact_sheet_set_path.parent.resolve()
    issues: list[str] = []
    manifest_payload = _load_json_object(manifest_path, "capture manifest")
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
            path = _resolved_evidence_path(record.get("path"), manifest_path.parent)
            if path is not None:
                capture_paths[label] = path
        if manifest_record_labels != list(contract.labels):
            issues.append(
                "capture manifest record order does not match contact-sheet contract"
            )

    if payload.get("complete") is not True:
        issues.append("contact-sheet set is not marked complete")
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
        help="Optional path to contact-sheet-set.json",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
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
