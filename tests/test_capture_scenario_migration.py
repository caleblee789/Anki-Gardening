from __future__ import annotations

import copy
import hashlib
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.capture_evidence import (
    CaptureEvidenceError,
    SCENARIO_REUSE_SCHEMA_VERSION,
    _legacy_capture_source_bytes,
    _legacy_scenario_reuse_digests,
    _scenario_reuse_digests,
    canonical_json_sha256,
    plan_incremental_capture,
)


LABEL = "surface-a"
CONTRACT_VERSION = 24
ENVIRONMENT_DIGEST = "1" * 64
SCHEMA_DIGEST = "2" * 64
PACKAGE_DIGEST = "3" * 64
RUN_DIGEST = "4" * 64
CONTRACT_DIGEST = "5" * 64
PNG_BYTES = b"\x89PNG\r\n\x1a\nscenario-migration"


def _method_digests(source: str) -> dict[str, str]:
    import ast

    module = ast.parse(source)
    runner = next(
        node for node in module.body
        if isinstance(node, ast.ClassDef)
        and node.name == "_UiFaceCaptureRunner"
    )
    result: dict[str, str] = {}
    for method in runner.body:
        if not isinstance(method, ast.FunctionDef):
            continue
        fragment = ast.get_source_segment(source, method)
        assert fragment is not None
        result[method.name] = hashlib.sha256(fragment.encode("utf-8")).hexdigest()
    return result


def _top_level_digests(source: str) -> dict[str, str]:
    import ast

    module = ast.parse(source)
    result: dict[str, str] = {}
    for node in module.body:
        names: list[str] = []
        if isinstance(node, ast.FunctionDef):
            names.append(node.name)
        elif isinstance(node, ast.Assign):
            names.extend(
                target.id for target in node.targets
                if isinstance(target, ast.Name)
            )
        for name in names:
            fragment = ast.get_source_segment(source, node)
            assert fragment is not None
            result[name] = hashlib.sha256(fragment.encode("utf-8")).hexdigest()
    return result


def _scenario_contracts(source: str) -> dict[str, dict[str, object]]:
    method_digests = _method_digests(source)
    top_level_digests = _top_level_digests(source)
    result: dict[str, dict[str, object]] = {}
    for label in ("alpha", "beta"):
        identity: dict[str, object] = {
            "label": label,
            "callable": f"_capture_{label}",
            "checkpoint": f"checkpoint:{label}",
            "capture_prerequisites": [],
            "internal_setups": [f"setup:{label}"],
            "renderer_family": "SyntheticDialog",
            "state_contract": {
                "kind": "dialog",
                "profile": {
                    "profile_id": label,
                    "kind": "dialog",
                    "state": label,
                },
                "required_facts": [f"fact:{label}"],
                "expected_fact_values": {},
                "fact_constraints": {},
            },
            "method_inputs": {
                "_capture_fixture_postcondition": method_digests[
                    "_capture_fixture_postcondition"
                ],
                "_alpha_branch_audit": method_digests["_alpha_branch_audit"],
                f"_capture_{label}": method_digests[f"_capture_{label}"],
            },
            "top_level_inputs": {
                name: top_level_digests[name]
                for name in (
                    "_ALPHA_STATES",
                    "alpha_top_helper",
                    "capture_scenario_internal_setups",
                )
            },
        }
        identity["digest"] = canonical_json_sha256(identity)
        result[label] = identity
    return result


def _synthetic_source() -> str:
    return '''\
_ALPHA_STATES = frozenset({"alpha"})

def alpha_top_helper():
    return "alpha-top-v1"

def capture_scenario_internal_setups(label):
    shared_setup_contract = "shared-setup-v1"
    if label in _ALPHA_STATES:
        return ("alpha", shared_setup_contract)
    return ("default", shared_setup_contract)

class _UiFaceCaptureRunner:
    def _capture_alpha(self):
        return self._capture_fixture_postcondition("alpha", None)

    def _capture_beta(self):
        return self._capture_fixture_postcondition("beta", None)

    def _alpha_branch_audit(self):
        return "alpha-audit-v1"

    def _capture_fixture_postcondition(self, label, widget):
        shared_contract = "shared-v1"
        if label == "alpha":
            branch_contract = (
                "alpha-v1",
                self._alpha_branch_audit(),
                alpha_top_helper(),
            )
        elif label == "beta":
            branch_contract = "beta-v1"
        setup_contract = capture_scenario_internal_setups(label)
        if runtime_capture_condition():
            runtime_contract = "runtime-v1"
        return shared_contract
'''


def _reuse_digests(source: str) -> dict[str, str]:
    return _scenario_reuse_digests(
        capture_source=source.encode("utf-8"),
        scenario_contracts=_scenario_contracts(source),
    )


def test_postcondition_branch_change_invalidates_only_affected_label() -> None:
    before_source = _synthetic_source()
    after_source = before_source.replace("alpha-v1", "alpha-v2")

    before = _reuse_digests(before_source)
    after = _reuse_digests(after_source)

    assert before["alpha"] != after["alpha"]
    assert before["beta"] == after["beta"]


def test_postcondition_shared_or_runtime_change_fails_closed_for_all_labels() -> None:
    source = _synthetic_source()
    baseline = _reuse_digests(source)

    shared = _reuse_digests(source.replace("shared-v1", "shared-v2"))
    runtime = _reuse_digests(source.replace("runtime-v1", "runtime-v2"))

    assert all(baseline[label] != shared[label] for label in baseline)
    assert all(baseline[label] != runtime[label] for label in baseline)


def test_branch_owned_method_and_top_level_helpers_remain_label_scoped() -> None:
    source = _synthetic_source()
    baseline = _reuse_digests(source)

    method_change = _reuse_digests(
        source.replace("alpha-audit-v1", "alpha-audit-v2")
    )
    top_level_change = _reuse_digests(
        source.replace("alpha-top-v1", "alpha-top-v2")
    )

    assert baseline["alpha"] != method_change["alpha"]
    assert baseline["beta"] == method_change["beta"]
    assert baseline["alpha"] != top_level_change["alpha"]
    assert baseline["beta"] == top_level_change["beta"]


def test_label_scoped_setup_membership_does_not_invalidate_other_label() -> None:
    source = _synthetic_source()
    baseline = _reuse_digests(source)
    changed = _reuse_digests(
        source.replace(
            '_ALPHA_STATES = frozenset({"alpha"})',
            '_ALPHA_STATES = frozenset({"alpha", "beta"})',
        )
    )

    assert changed["alpha"] == baseline["alpha"]
    assert changed["beta"] != baseline["beta"]


def test_label_scoped_setup_shared_change_still_invalidates_every_label() -> None:
    source = _synthetic_source()
    baseline = _reuse_digests(source)
    changed = _reuse_digests(
        source.replace("shared-setup-v1", "shared-setup-v2")
    )

    assert all(changed[label] != baseline[label] for label in baseline)


def test_new_unmapped_branch_dependencies_fail_closed() -> None:
    source = _synthetic_source()
    method_source = source.replace(
        "    def _capture_fixture_postcondition(self, label, widget):\n",
        "    def _unmapped_branch_helper(self):\n"
        "        return 'unmapped'\n\n"
        "    def _capture_fixture_postcondition(self, label, widget):\n",
    ).replace(
        "                self._alpha_branch_audit(),\n",
        "                self._alpha_branch_audit(),\n"
        "                self._unmapped_branch_helper(),\n",
    )
    with pytest.raises(CaptureEvidenceError, match="method ownership is incomplete"):
        _reuse_digests(method_source)

    top_level_source = source.replace(
        "def alpha_top_helper():\n",
        "def unmapped_top_helper():\n"
        "    return 'unmapped'\n\n"
        "def alpha_top_helper():\n",
    ).replace(
        "                alpha_top_helper(),\n",
        "                alpha_top_helper(),\n"
        "                unmapped_top_helper(),\n",
    )
    with pytest.raises(CaptureEvidenceError, match="projected dependency is unbound"):
        _reuse_digests(top_level_source)


def test_non_postcondition_scenario_dependency_remains_exact() -> None:
    source = _synthetic_source()
    scenarios = _scenario_contracts(source)
    before = _scenario_reuse_digests(
        capture_source=source.encode("utf-8"),
        scenario_contracts=scenarios,
    )
    changed_source = source.replace(
        "    def _capture_alpha(self):\n",
        "    def _capture_alpha(self):\n        alpha_capture_revision = 2\n",
    )
    changed = _scenario_contracts(changed_source)
    after = _scenario_reuse_digests(
        capture_source=changed_source.encode("utf-8"),
        scenario_contracts=changed,
    )

    assert before["alpha"] != after["alpha"]
    assert before["beta"] == after["beta"]


def _harness_source() -> str:
    return '''\
RENDERED_PIXEL_EVIDENCE_KEYS = {
    "alpha": ("alpha-pixels-v1",),
}
RUN_GATE_REVISION = "run-v1"

class _UiFaceCaptureRunner:
    def _capture_alpha(self):
        def cleanup_alpha():
            return self._cleanup_helper()
        return self._capture_and_advance(
            "alpha",
            before_capture=self._before_capture_helper,
            close_callback=cleanup_alpha,
            cleanup_predicate=lambda: True,
            close_ms=700,
            next_ms=1000,
        )

    def _capture_beta(self):
        return self._capture_and_advance("beta")

    def _before_capture_helper(self):
        return "before-capture-v1"

    def _cleanup_helper(self):
        return "cleanup-v1"

    def _cleanup_factory(self):
        return lambda: "cleanup-factory-v1"

    def _capture_and_advance(
        self,
        label,
        *,
        before_capture=None,
        close_callback=None,
        cleanup_predicate=None,
        close_ms=None,
        next_ms=None,
    ):
        del close_ms, next_ms
        return (
            self._wait_for_visual_stability(label),
            self._audit_capture_pixel_contracts(label),
        )

    def _wait_for_visual_stability(self, label):
        shared_wait = "shared-wait-v1"
        if label == "alpha":
            routed_signature = "alpha-signature-v1"
        else:
            routed_signature = "other-signature-v1"
        return shared_wait, routed_signature, self._surface_stability_signature(label)

    def _surface_stability_signature(self, label):
        shared_signature = "shared-signature-v1"
        return shared_signature

    def _audit_capture_pixel_contracts(self, label):
        required_keys = RENDERED_PIXEL_EVIDENCE_KEYS.get(label, ())
        if not required_keys:
            return ()
        return required_keys, self._widget_bounds_evidence()

    def _widget_bounds_evidence(self):
        return "bounds-v1"

    def _capture_fixture_postcondition(self, label, widget):
        return "postcondition-v1"
'''


def _harness_contracts(source: str) -> dict[str, dict[str, object]]:
    method_digests = _method_digests(source)
    top_level_digests = _top_level_digests(source)
    result: dict[str, dict[str, object]] = {}
    for label in ("alpha", "beta"):
        identity: dict[str, object] = {
            "label": label,
            "callable": f"_capture_{label}",
            "checkpoint": f"checkpoint:{label}",
            "capture_prerequisites": [],
            "internal_setups": [f"setup:{label}"],
            "renderer_family": "SyntheticDialog",
            "state_contract": {
                "kind": "dialog",
                "profile": {
                    "profile_id": label,
                    "kind": "dialog",
                    "state": label,
                },
                "required_facts": [f"fact:{label}"],
                "expected_fact_values": {},
                "fact_constraints": {},
            },
            "method_inputs": dict(method_digests),
            "top_level_inputs": {
                "RENDERED_PIXEL_EVIDENCE_KEYS": top_level_digests[
                    "RENDERED_PIXEL_EVIDENCE_KEYS"
                ],
            },
        }
        identity["digest"] = canonical_json_sha256(identity)
        result[label] = identity
    return result


def _harness_reuse_digests(source: str) -> dict[str, str]:
    return _scenario_reuse_digests(
        capture_source=source.encode("utf-8"),
        scenario_contracts=_harness_contracts(source),
    )


def test_shared_harness_label_branch_invalidates_only_its_surface() -> None:
    source = _harness_source()
    baseline = _harness_reuse_digests(source)
    changed = _harness_reuse_digests(
        source.replace("alpha-signature-v1", "alpha-signature-v2")
    )

    assert changed["alpha"] != baseline["alpha"]
    assert changed["beta"] == baseline["beta"]


def test_adding_new_label_branch_does_not_invalidate_other_surface() -> None:
    source = _harness_source()
    baseline = _harness_reuse_digests(source)
    changed = _harness_reuse_digests(
        source.replace(
            '        shared_wait = "shared-wait-v1"\n',
            '        shared_wait = "shared-wait-v1"\n'
            '        if label == "beta":\n'
            '            beta_wait = "beta-wait-v1"\n',
        )
    )

    assert changed["alpha"] == baseline["alpha"]
    assert changed["beta"] != baseline["beta"]


def test_shared_harness_runtime_change_still_fails_closed_for_all_surfaces() -> None:
    source = _harness_source()
    baseline = _harness_reuse_digests(source)
    changed = _harness_reuse_digests(
        source.replace("shared-wait-v1", "shared-wait-v2")
    )

    assert all(changed[label] != baseline[label] for label in baseline)


def test_dynamic_loop_assignment_cannot_narrow_later_label_branch() -> None:
    source = _harness_source().replace(
        '        shared_wait = "shared-wait-v1"\n',
        '        shared_wait = "shared-wait-v1"\n'
        '        selector = label\n'
        '        for _candidate in runtime_candidates():\n'
        '            selector = "beta"\n'
        '        if selector == "alpha":\n'
        '            uncertain_loop_contract = "loop-contract-v1"\n',
    )
    baseline = _harness_reuse_digests(source)
    changed = _harness_reuse_digests(
        source.replace("loop-contract-v1", "loop-contract-v2")
    )

    assert all(changed[label] != baseline[label] for label in baseline)


def test_projected_label_argument_cannot_be_reassigned() -> None:
    source = _harness_source().replace(
        '        shared_wait = "shared-wait-v1"\n',
        '        label = "alpha"\n'
        '        shared_wait = "shared-wait-v1"\n',
    )

    with pytest.raises(CaptureEvidenceError, match="immutable scenario name"):
        _harness_reuse_digests(source)


def test_label_scoped_pixel_map_and_geometry_dependency_are_minimal() -> None:
    source = _harness_source()
    baseline = _harness_reuse_digests(source)

    alpha_map_change = _harness_reuse_digests(
        source.replace("alpha-pixels-v1", "alpha-pixels-v2")
    )
    geometry_change = _harness_reuse_digests(
        source.replace("bounds-v1", "bounds-v2")
    )
    beta_map_change = _harness_reuse_digests(
        source.replace(
            '    "alpha": ("alpha-pixels-v1",),\n',
            '    "alpha": ("alpha-pixels-v1",),\n'
            '    "beta": ("beta-pixels-v1",),\n',
        )
    )

    assert alpha_map_change["alpha"] != baseline["alpha"]
    assert alpha_map_change["beta"] == baseline["beta"]
    assert geometry_change["alpha"] != baseline["alpha"]
    assert geometry_change["beta"] == baseline["beta"]
    assert beta_map_change["alpha"] == baseline["alpha"]
    assert beta_map_change["beta"] != baseline["beta"]


def test_unknown_pixel_map_owner_falls_back_to_shared_invalidation() -> None:
    source = _harness_source()
    baseline = _harness_reuse_digests(source)
    changed = _harness_reuse_digests(
        source.replace(
            '    "alpha": ("alpha-pixels-v1",),\n',
            '    "alpha": ("alpha-pixels-v1",),\n'
            '    "unknown-surface": ("unknown-pixels",),\n',
        )
    )

    assert all(changed[label] != baseline[label] for label in baseline)


def test_unreferenced_run_gate_change_does_not_invalidate_surface_path() -> None:
    source = _harness_source()
    changed_source = source.replace("run-v1", "run-v2")

    assert _harness_reuse_digests(changed_source) == _harness_reuse_digests(source)
    assert hashlib.sha256(changed_source.encode()).hexdigest() != hashlib.sha256(
        source.encode()
    ).hexdigest()


def test_cleanup_behavior_remains_surface_owned_but_ignored_timing_does_not() -> None:
    source = _harness_source()
    baseline = _harness_reuse_digests(source)
    cleanup_body = _harness_reuse_digests(
        source.replace("cleanup-v1", "cleanup-v2")
    )
    cleanup_timing = _harness_reuse_digests(
        source.replace("close_ms=700", "close_ms=701")
    )

    assert cleanup_body["alpha"] != baseline["alpha"]
    assert cleanup_body["beta"] == baseline["beta"]
    assert cleanup_timing == baseline
    assert hashlib.sha256(source.encode()).hexdigest() != hashlib.sha256(
        source.replace("cleanup-v1", "cleanup-v2").encode()
    ).hexdigest()


def test_before_capture_or_dynamic_cleanup_factory_remains_surface_owned() -> None:
    source = _harness_source()
    baseline = _harness_reuse_digests(source)
    before_capture = _harness_reuse_digests(
        source.replace("before-capture-v1", "before-capture-v2")
    )
    factory_source = source.replace(
        "close_callback=cleanup_alpha,",
        "close_callback=self._cleanup_factory(),",
    )
    factory_baseline = _harness_reuse_digests(factory_source)
    factory_changed = _harness_reuse_digests(
        factory_source.replace("cleanup-factory-v1", "cleanup-factory-v2")
    )

    assert before_capture["alpha"] != baseline["alpha"]
    assert before_capture["beta"] == baseline["beta"]
    assert factory_changed["alpha"] != factory_baseline["alpha"]
    assert factory_changed["beta"] == factory_baseline["beta"]


def test_timing_literal_is_surface_owned_if_capture_runner_reads_it() -> None:
    source = _harness_source().replace(
        "        del close_ms, next_ms\n",
        "        cleanup_schedule = next_ms\n",
    )
    baseline = _harness_reuse_digests(source)
    changed = _harness_reuse_digests(
        source.replace("next_ms=1000", "next_ms=1001")
    )

    assert changed["alpha"] != baseline["alpha"]
    assert changed["beta"] == baseline["beta"]


def _surface(
    *,
    scenario_digest: str,
    reuse_digest: str,
    archive_digest: str = "6" * 64,
    reuse_schema_version: int = SCENARIO_REUSE_SCHEMA_VERSION,
) -> dict[str, object]:
    inputs = {
        "archive:ui/surface.py": archive_digest,
        "capture_scale_factor": "1.0",
        "scenario-identity": scenario_digest,
    }
    surface_digest = canonical_json_sha256({
        "renderer_family": "SyntheticDialog",
        "scenario_identity_digest": scenario_digest,
        "scenario_reuse_digest": reuse_digest,
        "scenario_reuse_schema_version": reuse_schema_version,
        "render_inputs": dict(sorted(inputs.items())),
    })
    return {
        "bucket": "settings-transactions",
        "digest": surface_digest,
        "environment_digest": ENVIRONMENT_DIGEST,
        "input_count": len(inputs),
        "inputs": inputs,
        "renderer_family": "SyntheticDialog",
        "scenario_identity_digest": scenario_digest,
        "scenario_reuse_digest": reuse_digest,
        "scenario_reuse_schema_version": reuse_schema_version,
        "surface_contract_digest": surface_digest,
    }


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _manifest(tmp_path: Path, surface: dict[str, object]) -> Path:
    root = tmp_path / "source"
    root.mkdir(parents=True)
    png = root / f"{LABEL}.png"
    png.write_bytes(PNG_BYTES)
    record = {
        "audit": {"passed": True},
        "capture_environment_digest": ENVIRONMENT_DIGEST,
        "capture_id": 1,
        "evidence_schema_digest": SCHEMA_DIGEST,
        "evidence_status": "captured",
        "fixture_validation": {"passed": True},
        "geometry_layout_warnings": [],
        "label": LABEL,
        "lineage": {"source_run_id": "scenario-source"},
        "path": png.name,
        "png_sha256": hashlib.sha256(PNG_BYTES).hexdigest(),
        "render_input_count": surface["input_count"],
        "render_input_digest": surface["digest"],
        "scenario_identity_digest": surface["scenario_identity_digest"],
        "surface_contract_digest": surface["surface_contract_digest"],
        "text_layout_warnings": [],
    }
    payload = {
        "capture_calibration": {"passed": True},
        "capture_contract_digest": CONTRACT_DIGEST,
        "capture_contract_version": CONTRACT_VERSION,
        "capture_profile": "representative",
        "capture_scope": "full",
        "captures": [record],
        "complete": True,
        "expected_count": 1,
        "expected_faces": [LABEL],
        "failures": [],
        "invalidated_faces": [],
        "render_inputs": {"surfaces": {LABEL: surface}},
        "requested_faces": [LABEL],
        "requested_scale_factor": "1.0",
        "scope_complete": True,
        "text_layout_warnings": [],
    }
    manifest = root / "manifest.json"
    _write_json(manifest, payload)
    _write_json(root / "capture-complete.json", {
        "complete": True,
        "exit_code": 0,
        "manifest": manifest.name,
        "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "scope_complete": True,
    })
    return manifest


def _current_render_inputs(surface: dict[str, object]) -> dict[str, object]:
    return {
        "capture_contract_digest": CONTRACT_DIGEST,
        "capture_profile": "representative",
        "environment_digest": ENVIRONMENT_DIGEST,
        "evidence_schema_digest": SCHEMA_DIGEST,
        "production_archive_sha256": PACKAGE_DIGEST,
        "run_level_digest": RUN_DIGEST,
        "surfaces": {LABEL: surface},
    }


def _plan(manifest: Path, surface: dict[str, object]) -> dict[str, object]:
    return plan_incremental_capture(
        evidence_manifests=(manifest,),
        current_render_inputs=_current_render_inputs(surface),
        expected_labels=(LABEL,),
        contract_version=CONTRACT_VERSION,
        contract_digest=CONTRACT_DIGEST,
        profile="representative",
    )


def test_planner_reuses_only_proven_scenario_path_migration(tmp_path: Path) -> None:
    reuse_digest = "7" * 64
    old = _surface(scenario_digest="8" * 64, reuse_digest=reuse_digest)
    manifest = _manifest(tmp_path, old)
    current = _surface(scenario_digest="9" * 64, reuse_digest=reuse_digest)

    plan = _plan(manifest, current)

    assert plan["reused"] == [LABEL]
    assert plan["recapture_required"] == []
    assert plan["selected_sources"][LABEL]["reuse_mode"] == "scenario-path"

    changed_path = copy.deepcopy(current)
    changed_path["scenario_reuse_digest"] = "a" * 64
    assert _plan(manifest, changed_path)["recapture_required"] == [LABEL]

    changed_archive = _surface(
        scenario_digest="9" * 64,
        reuse_digest=reuse_digest,
        archive_digest="b" * 64,
    )
    assert _plan(manifest, changed_archive)["recapture_required"] == [LABEL]


def test_planner_reconstructs_only_supported_legacy_scenario_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import capture_evidence

    migrated_digest = "7" * 64
    legacy = _surface(
        scenario_digest="8" * 64,
        reuse_digest="0" * 64,
        reuse_schema_version=1,
    )
    manifest = _manifest(tmp_path, legacy)
    current = _surface(
        scenario_digest="9" * 64,
        reuse_digest=migrated_digest,
    )
    monkeypatch.setattr(
        capture_evidence,
        "_legacy_scenario_reuse_digests",
        lambda *_args, **_kwargs: {LABEL: migrated_digest},
    )

    plan = _plan(manifest, current)

    assert plan["reused"] == [LABEL]
    assert plan["selected_sources"][LABEL]["reuse_mode"] == "scenario-path"

    unsupported = copy.deepcopy(legacy)
    unsupported["scenario_reuse_schema_version"] = 99
    unsupported_contract = {
        "renderer_family": unsupported["renderer_family"],
        "scenario_identity_digest": unsupported["scenario_identity_digest"],
        "scenario_reuse_digest": unsupported["scenario_reuse_digest"],
        "scenario_reuse_schema_version": 99,
        "render_inputs": dict(sorted(unsupported["inputs"].items())),
    }
    unsupported_digest = canonical_json_sha256(unsupported_contract)
    unsupported["digest"] = unsupported_digest
    unsupported["surface_contract_digest"] = unsupported_digest
    unsupported_manifest = _manifest(tmp_path / "unsupported", unsupported)
    assert _plan(unsupported_manifest, current)["recapture_required"] == [LABEL]


def test_full_profile_reuses_surfaces_but_requires_current_session_run_gate(
    tmp_path: Path,
) -> None:
    surface = _surface(
        scenario_digest="8" * 64,
        reuse_digest="7" * 64,
    )
    manifest = _manifest(tmp_path, surface)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["capture_profile"] = "full"
    payload["run_level_evidence"] = {
        "clean_shutdown": {
            "capture_environment_digest": ENVIRONMENT_DIGEST,
            "passed": True,
            "run_level_digest": RUN_DIGEST,
        },
        "dialog_memory_probe": {
            "passed": True,
            "run_level_digest": RUN_DIGEST,
        },
    }
    _write_json(manifest, payload)
    _write_json(manifest.parent / "capture-complete.json", {
        "complete": True,
        "exit_code": 0,
        "manifest": manifest.name,
        "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "scope_complete": True,
    })

    plan = plan_incremental_capture(
        evidence_manifests=(manifest,),
        current_render_inputs={
            **_current_render_inputs(surface),
            "capture_profile": "full",
        },
        expected_labels=(LABEL,),
        contract_version=CONTRACT_VERSION,
        contract_digest=CONTRACT_DIGEST,
        profile="full",
    )

    assert plan["reused"] == [LABEL]
    assert plan["recapture_required"] == []
    assert plan["run_level_recapture_required"] is True
    assert plan["selected_run_level_source"] is None
    assert plan["run_level_reuse_policy"] == "current-session-required"


def test_legacy_capture_source_requires_exact_hash_and_unambiguous_archive(
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "run"
    assembled = run_root / "assembled"
    assembled.mkdir(parents=True)
    manifest = assembled / "manifest.json"
    manifest.write_text("{}\n", encoding="utf-8")
    source = _synthetic_source().encode("utf-8")
    archive = run_root / "anki_garden_capture.ankiaddon"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("capture_ui_faces.py", source)
    payload = {
        "render_inputs": {
            "run_level_inputs": {
                "capture_source_sha256": hashlib.sha256(source).hexdigest(),
            },
        },
    }

    assert _legacy_capture_source_bytes(manifest, payload) == source

    changed = copy.deepcopy(payload)
    changed["render_inputs"]["run_level_inputs"]["capture_source_sha256"] = "c" * 64
    assert _legacy_capture_source_bytes(manifest, changed) is None

    with zipfile.ZipFile(assembled / "anki_garden_capture.ankiaddon", "w") as handle:
        handle.writestr("capture_ui_faces.py", source)
    assert _legacy_capture_source_bytes(manifest, payload) is None


def test_legacy_scenario_metadata_requires_recapture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_text = _synthetic_source()
    source = source_text.encode("utf-8")
    scenarios = _scenario_contracts(source_text)
    labels = tuple(scenarios)
    scenario_contract_digest = canonical_json_sha256({
        label: scenarios[label]["digest"]
        for label in labels
    })
    run_root = tmp_path / "run"
    assembled = run_root / "assembled"
    assembled.mkdir(parents=True)
    manifest = assembled / "manifest.json"
    manifest.write_text("{}\n", encoding="utf-8")
    with zipfile.ZipFile(run_root / "anki_garden_capture.ankiaddon", "w") as handle:
        handle.writestr("capture_ui_faces.py", source)
    payload = {
        "capture_profile": "representative",
        "expected_faces": list(labels),
        "scenario_contract_digest": scenario_contract_digest,
        "render_inputs": {
            "run_level_inputs": {
                "capture_source_sha256": hashlib.sha256(source).hexdigest(),
            },
            "scenario_contract_digest": scenario_contract_digest,
            "surfaces": {
                label: {
                    "scenario_identity_digest": scenarios[label]["digest"],
                }
                for label in labels
            },
        },
    }
    from scripts import validate_ui_capture

    monkeypatch.setattr(
        validate_ui_capture,
        "load_capture_contract",
        lambda *_args, **_kwargs: SimpleNamespace(labels=labels),
    )
    legacy_source = tmp_path / "capture_ui_faces.py"
    legacy_source.write_bytes(source)
    with pytest.raises(validate_ui_capture.CaptureValidationError, match="recapture"):
        validate_ui_capture.load_capture_scenario_contracts(legacy_source)
    assert _legacy_scenario_reuse_digests(manifest, payload) is None

    changed = copy.deepcopy(payload)
    changed["scenario_contract_digest"] = "d" * 64
    assert _legacy_scenario_reuse_digests(manifest, changed) is None
