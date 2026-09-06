from __future__ import annotations

"""Exact comparison helpers for production-engine balance traces.

The accelerated simulator does not claim engine parity by itself. A production
trace can be exported with these field names and compared row-for-row before a
release report promotes the parity status.
"""

from hashlib import sha256
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Callable, Iterable, Mapping, Sequence, Tuple

from .catalog import canonical_json_bytes, to_primitive


TRACE_FIELDS: Tuple[str, ...] = (
    "event_identity",
    "day",
    "study",
    "answers",
    "completed_today",
    "study_run",
    "garden_rhythm_percent",
    "growth_total_units",
    "growth_applied_units",
    "growth_stored_balance_units",
    "growth_spent_units",
    "growth_routed_to_storage_units_lifetime",
    "growth_contributed_to_landmarks_units",
    "growth_contributed_to_mastery_units",
    "growth_contributed_to_legacy_units",
    "growth_unallocated_overflow_units",
    "coins_gross",
    "coins_spent",
    "coins_wallet",
    "finds_total",
    "environments_owned",
    "beds_owned",
    "species_owned",
    "achievements_claimed",
    "active_garden_bonus_id",
    "active_scenery_id",
    "environment_effect_growth_units",
    "environment_effect_coins",
    "garden_cycle_remainder",
    "coin_sources",
)


REQUIRED_PARITY_BEHAVIORS: Tuple[str, ...] = (
    "rating_again",
    "rating_hard",
    "rating_good",
    "rating_easy",
    "eligible_answer",
    "excluded_answer",
    "local_review_reward",
    "synced_review_reward",
    "duplicate_sync_delivery",
    "application_restart",
    "anki_day_rollover",
    "todays_cards_completion",
    "fifth_garden_cycle_completion",
    "seventh_streak_day_reward",
    "standard_find_natural",
    "standard_find_forced",
    "daily_find_uncapped",
    "rare_environment_natural",
    "very_rare_environment_natural",
    "ultra_rare_environment_natural",
    "environment_card_pity",
    "environment_completion_pity",
    "simultaneously_forced_environment_tiers",
    "booster_activation",
    "fertilizer_activation_and_queue_extension",
    "garden_bonus_counters",
    "scenery_counters",
    "full_bloom",
    "bed_achievement_unlock",
    "landmark_contribution_and_claim",
    "mastery_contribution_and_claim",
    "garden_legacy_level",
    "insufficient_coin_purchase",
    "stale_purchase_quote",
    "failed_persistence_rollback",
    "repeated_request_identity",
    "undo_and_reanswer_lineage",
)


REQUIRED_PARITY_STATE_FIELDS: Tuple[str, ...] = (
    "garden_coin_wallet",
    "coin_ledger_entries",
    "coin_source_ids",
    "plant_exact_growth_units",
    "stored_growth_balance",
    "lifetime_stored_routing_total",
    "landmark_funding",
    "landmark_claims",
    "mastery_funding_by_species",
    "mastery_claims",
    "garden_legacy_progress",
    "stage_flags",
    "checkpoint_flags",
    "bed_ownership",
    "achievement_ownership",
    "consumable_inventory",
    "fertilizer_queues",
    "booster_remaining_cards",
    "garden_bonus_counters",
    "scenery_counters",
    "garden_cycle_remainder",
    "find_drought_counter",
    "daily_find_cap_and_count",
    "environment_pity_counters",
    "environment_ownership",
    "todays_cards_completion_state",
    "equipped_items",
    "reward_identities",
    "purchase_identities",
    "undo_lineage",
    "state_revision",
)


COVERED_PARITY_STATE_FIELDS: Tuple[str, ...] = (
    "garden_coin_wallet",
    "coin_source_ids",
    "stored_growth_balance",
    "lifetime_stored_routing_total",
    "bed_ownership",
    "garden_cycle_remainder",
)


# These are real checkpoint comparisons, not documentation-only coverage.
# `coin_sources` includes the exact source IDs and amounts.  Fields whose trace
# is only an aggregate count (for example environment ownership) are
# deliberately not promoted to release-state coverage.
TRACE_PARITY_STATE_FIELD_PATHS: Mapping[str, str] = {
    "garden_coin_wallet": "coins_wallet",
    "coin_source_ids": "coin_sources",
    "stored_growth_balance": "growth_stored_balance_units",
    "lifetime_stored_routing_total": (
        "growth_routed_to_storage_units_lifetime"
    ),
    "bed_ownership": "beds_owned",
    "garden_cycle_remainder": "garden_cycle_remainder",
}


class TraceMismatch(AssertionError):
    def __init__(
        self,
        message: str,
        *,
        event_identity: str = "",
        json_pointer: str = "",
        trace_prefix: Sequence[Mapping[str, object]] = (),
    ) -> None:
        super().__init__(message)
        self.event_identity = event_identity
        self.json_pointer = json_pointer
        self.trace_prefix = tuple(trace_prefix)


def _first_release_state_difference(
    expected: object,
    actual: object,
    *,
    path: str,
) -> tuple[str, object, object] | None:
    """Return the first exact, stable-path difference between two snapshots."""

    if isinstance(expected, Mapping) and isinstance(actual, Mapping):
        expected_keys = tuple(sorted(str(key) for key in expected))
        actual_keys = tuple(sorted(str(key) for key in actual))
        if expected_keys != actual_keys:
            return path, expected_keys, actual_keys
        for key in expected_keys:
            child = _first_release_state_difference(
                expected[key],
                actual[key],
                path=f"{path}/{key}",
            )
            if child is not None:
                return child
        return None
    if (
        isinstance(expected, Sequence)
        and not isinstance(expected, (str, bytes, bytearray))
        and isinstance(actual, Sequence)
        and not isinstance(actual, (str, bytes, bytearray))
    ):
        if len(expected) != len(actual):
            return f"{path}/length", len(expected), len(actual)
        for index, (left, right) in enumerate(zip(expected, actual)):
            child = _first_release_state_difference(
                left,
                right,
                path=f"{path}/{index}",
            )
            if child is not None:
                return child
        return None
    if expected != actual or type(expected) is not type(actual):
        return path, expected, actual
    return None


def assert_release_state_parity(
    expected: Mapping[str, object],
    actual: Mapping[str, object],
    *,
    event_identity: str,
    fields: Sequence[str] = REQUIRED_PARITY_STATE_FIELDS,
    trace_prefix: Sequence[Mapping[str, object]] = (),
) -> None:
    """Compare selected renderer-neutral release state and fail on first path.

    This helper is also used around a real SQLite close/reopen boundary. It is
    intentionally exact: no float tolerance, absent-key default, or aggregate
    substitution is allowed.
    """

    field_names = tuple(str(field) for field in fields)
    missing_expected = tuple(
        field for field in field_names if field not in expected
    )
    missing_actual = tuple(field for field in field_names if field not in actual)
    if missing_expected or missing_actual:
        raise TraceMismatch(
            "release state is missing required fields; "
            f"expected={missing_expected}, actual={missing_actual}",
            event_identity=event_identity,
            json_pointer="/",
            trace_prefix=trace_prefix,
        )
    for field in field_names:
        difference = _first_release_state_difference(
            expected[field],
            actual[field],
            path=f"/{field}",
        )
        if difference is None:
            continue
        path, left, right = difference
        raise TraceMismatch(
            f"release state mismatch after {event_identity} at {path}: "
            f"expected {left!r}, actual {right!r}",
            event_identity=event_identity,
            json_pointer=path,
            trace_prefix=trace_prefix,
        )


@dataclass(frozen=True)
class ProductionReplayEvent:
    event_identity: str
    event_type: str
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class ProductionReplayResult:
    rows: Tuple[Mapping[str, object], ...]
    committed_event_identities: Tuple[str, ...]


@dataclass(frozen=True)
class ReleaseParityCase:
    """One bounded, replayable production-parity case.

    ``scenario_id`` is populated for the 66 approved scenario representatives;
    randomized multi-event cases use a stable ``randomized:<index>`` identity.
    The manifest is intentionally a union, not a Cartesian product.
    """

    case_id: str
    case_kind: str
    scenario_id: str
    seed_index: int
    events: Tuple[ProductionReplayEvent, ...]


def representative_scenario_parity_cases(
    scenario_ids: Iterable[str],
    *,
    scheduler_day: str = "2026-08-30",
) -> Tuple[ReleaseParityCase, ...]:
    """Create one deterministic smoke event for every approved scenario.

    These rows prove catalog/loadout initialization across all 66 IDs, but are
    intentionally not described as the required annual scenario traces.
    """

    rows = []
    base_ms = 1_788_100_000_000
    for index, scenario_id in enumerate(tuple(scenario_ids)):
        event = ProductionReplayEvent(
            event_identity=f"scenario:{scenario_id}:day:1",
            event_type="study_day",
            payload={
                "scheduler_day": scheduler_day,
                "trace_day": 1,
                "trace_study_run": 1,
                "answers": 1,
                "complete": True,
                "eases": (1 + index % 4,),
                "revlog_base": base_ms + index * 10_000,
                "card_base": 1_000_000 + index * 10,
            },
        )
        rows.append(ReleaseParityCase(
            case_id=f"scenario:{scenario_id}",
            case_kind="approved_scenario_smoke",
            scenario_id=str(scenario_id),
            seed_index=0,
            events=(event,),
        ))
    return tuple(rows)


def randomized_multi_event_parity_cases(
    *,
    count: int = 32,
    scheduler_day: str = "2026-08-30",
) -> Tuple[ReleaseParityCase, ...]:
    """Return a small deterministic set of rating/retry/restart/day traces.

    The arithmetic is deliberately integer-only.  This is a fixed trace set,
    not another simulation dimension, so the release matrix remains 66 cases.
    """

    total = max(0, int(count))
    start = date.fromisoformat(scheduler_day)
    rows = []
    for seed_index in range(total):
        # Two through eight checkpoints cross restart, retry, missing-day,
        # Garden Rhythm, Garden Cycle, and seven-day streak paths.
        day_count = 2 + seed_index % 7
        events = []
        calendar_offset = 0
        previous_calendar_offset = -1
        study_run = 0
        for day_index in range(day_count):
            if day_index and (seed_index + day_index) % 7 == 0:
                calendar_offset += 1  # one intentionally missed day
            current = start + timedelta(days=calendar_offset)
            complete = day_index % 5 != 4
            study_run = (
                study_run + 1
                if previous_calendar_offset == calendar_offset - 1 else 1
            )
            ease = 1 + ((seed_index * 3 + day_index) % 4)
            answer_number = day_index + 1
            events.append(ProductionReplayEvent(
                event_identity=(
                    f"randomized:{seed_index:02d}:day:{answer_number}"
                ),
                event_type="study_day",
                payload={
                    "scheduler_day": current.isoformat(),
                    "trace_day": calendar_offset + 1,
                    "trace_study_run": study_run,
                    "answers": 1,
                    "complete": complete,
                    "eases": (ease,),
                    "revlog_base": (
                        1_788_100_000_000
                        + calendar_offset * 86_400_000
                        + seed_index * 1_000
                    ),
                    "card_base": seed_index * 100 + day_index + 1,
                    "duplicate_answer_numbers": (
                        (1,) if (seed_index + day_index) % 4 == 0 else ()
                    ),
                    "historical_sync_answer_numbers": (
                        (1,)
                        if day_index == 0 and seed_index % 3 == 0
                        else ()
                    ),
                    "include_excluded_answer": bool(
                        day_index == 0 and seed_index % 5 == 1
                    ),
                    "find_mode": (
                        "forced"
                        if day_index == 0 and seed_index == 10
                        else "natural"
                        if day_index == 0 and seed_index == 11
                        else ""
                    ),
                    "environment_mode": (
                        "rare_natural"
                        if day_index == 0 and seed_index == 12
                        else "very_rare_natural"
                        if day_index == 0 and seed_index == 13
                        else "ultra_rare_natural"
                        if day_index == 0 and seed_index == 14
                        else "card_pity_simultaneous"
                        if day_index == 0 and seed_index == 15
                        else "completion_pity_simultaneous"
                        if day_index == 0 and seed_index == 16
                        else ""
                    ),
                    "verify_find_caps": bool(
                        day_index == 0 and seed_index == 17
                    ),
                    "restart_after_answer_numbers": (
                        (1,) if (seed_index + day_index) % 6 == 0 else ()
                    ),
                },
            ))
            previous_calendar_offset = calendar_offset
            calendar_offset += 1
        rows.append(ReleaseParityCase(
            case_id=f"randomized:{seed_index:02d}",
            case_kind="deterministic_randomized_multi_event",
            scenario_id="",
            seed_index=seed_index,
            events=tuple(events),
        ))
    return tuple(rows)


def release_parity_manifest(
    scenario_ids: Iterable[str],
) -> Tuple[ReleaseParityCase, ...]:
    """Bounded smoke/focused manifest; annual scenario replay is separate."""

    return (
        *representative_scenario_parity_cases(scenario_ids),
        *randomized_multi_event_parity_cases(count=32),
    )


def assert_release_parity_manifest(
    cases: Sequence[ReleaseParityCase],
    kernel_rows_by_case: Mapping[str, Sequence[Mapping[str, object]]],
    engine_rows_by_case: Mapping[str, Sequence[Mapping[str, object]]],
) -> Mapping[str, object]:
    """Verify and summarize the bounded release parity manifest.

    This bounded function compares all 66 scenario-ID smoke cases and all 32
    randomized traces, then reports the annual trace set separately as missing.
    It therefore cannot be mistaken for the complete release gate.
    """

    ordered = tuple(cases)
    scenario_smoke_count = sum(
        case.case_kind == "approved_scenario_smoke"
        for case in ordered
    )
    randomized_count = sum(
        case.case_kind == "deterministic_randomized_multi_event"
        for case in ordered
    )
    identities = tuple(case.case_id for case in ordered)
    if (
        len(ordered) != 98
        or scenario_smoke_count != 66
        or randomized_count != 32
        or len(set(identities)) != len(identities)
    ):
        raise ValueError(
            "bounded parity requires exactly 66 scenario smoke and 32 randomized cases"
        )
    missing_kernel = [
        case_id for case_id in identities if case_id not in kernel_rows_by_case
    ]
    missing_engine = [
        case_id for case_id in identities if case_id not in engine_rows_by_case
    ]
    extra_kernel = sorted(set(kernel_rows_by_case) - set(identities))
    extra_engine = sorted(set(engine_rows_by_case) - set(identities))
    if missing_kernel or missing_engine or extra_kernel or extra_engine:
        raise ValueError(
            "release parity result coverage mismatch; "
            f"missing_kernel={missing_kernel}, missing_engine={missing_engine}, "
            f"extra_kernel={extra_kernel}, extra_engine={extra_engine}"
        )

    checkpoint_count = 0
    trace_hash_inputs = []
    state_hash_inputs = []
    for case in ordered:
        kernel_rows = kernel_rows_by_case[case.case_id]
        engine_rows = engine_rows_by_case[case.case_id]
        try:
            assert_engine_trace_parity(kernel_rows, engine_rows)
        except TraceMismatch as exc:
            raise TraceMismatch(
                f"release parity case {case.case_id}: {exc}",
                event_identity=exc.event_identity,
                json_pointer=exc.json_pointer,
                trace_prefix=exc.trace_prefix,
            ) from exc
        checkpoint_count += len(kernel_rows)
        trace_hash_inputs.append({
            "case_id": case.case_id,
            "kernel_sha256": trace_sha256(kernel_rows),
            "engine_sha256": trace_sha256(engine_rows),
        })
        state_hash_inputs.append({
            "case_id": case.case_id,
            "kernel": [
                {
                    state_field: to_primitive(row[trace_field])
                    for state_field, trace_field in (
                        TRACE_PARITY_STATE_FIELD_PATHS.items()
                    )
                }
                for row in canonical_trace_rows(kernel_rows)
            ],
            "engine": [
                {
                    state_field: to_primitive(row[trace_field])
                    for state_field, trace_field in (
                        TRACE_PARITY_STATE_FIELD_PATHS.items()
                    )
                }
                for row in canonical_trace_rows(engine_rows)
            ],
        })

    manifest_payload = [
        {
            "case_id": case.case_id,
            "case_kind": case.case_kind,
            "scenario_id": case.scenario_id,
            "seed_index": case.seed_index,
            "events": [
                {
                    "event_identity": event.event_identity,
                    "event_type": event.event_type,
                    "payload": to_primitive(event.payload),
                }
                for event in case.events
            ],
        }
        for case in ordered
    ]
    covered_behaviors = _covered_behaviors_from_manifest(ordered)
    missing_behaviors = tuple(
        behavior for behavior in REQUIRED_PARITY_BEHAVIORS
        if behavior not in covered_behaviors
    )
    missing_state_fields = tuple(
        field for field in REQUIRED_PARITY_STATE_FIELDS
        if field not in COVERED_PARITY_STATE_FIELDS
    )
    annual_scenario_trace_count = 0
    missing_trace_sets = ("annual_365_day_scenario_traces",)
    complete = bool(
        annual_scenario_trace_count == 66
        and not missing_trace_sets
        and not missing_behaviors
        and not missing_state_fields
    )
    return {
        "status": "pass" if complete else "focused_incomplete",
        "production_engine_trace_equivalent": complete,
        # Compatibility count retained for old evidence readers. The explicit
        # kind below prevents it from being mistaken for annual evidence.
        "scenario_trace_count": scenario_smoke_count,
        "scenario_smoke_trace_count": scenario_smoke_count,
        "annual_scenario_trace_count": annual_scenario_trace_count,
        "randomized_trace_count": randomized_count,
        "trace_count": len(ordered),
        "checkpoint_count": checkpoint_count,
        "compared_fields": list(TRACE_FIELDS),
        "required_behaviors": list(REQUIRED_PARITY_BEHAVIORS),
        "covered_behaviors": list(covered_behaviors),
        "missing_behaviors": list(missing_behaviors),
        "required_state_fields": list(REQUIRED_PARITY_STATE_FIELDS),
        "covered_state_fields": list(COVERED_PARITY_STATE_FIELDS),
        "missing_state_fields": list(missing_state_fields),
        "missing_trace_sets": list(missing_trace_sets),
        "manifest_sha256": sha256(
            canonical_json_bytes(manifest_payload)
        ).hexdigest(),
        "trace_pairs_sha256": sha256(
            canonical_json_bytes(trace_hash_inputs)
        ).hexdigest(),
        "state_pairs_sha256": sha256(
            canonical_json_bytes(state_hash_inputs)
        ).hexdigest(),
        "note": (
            "The compared 66 one-event scenario smoke cases and 32 "
            "deterministic randomized traces matched GardenGameEngine exactly, "
            "but release remains blocked until the 66 annual scenario traces, "
            "every listed focused behavior, and every state field are covered."
            if not complete else
            "All required production parity behaviors and fields matched "
            "GardenGameEngine exactly."
        ),
    }


def _covered_behaviors_from_manifest(
    cases: Sequence[ReleaseParityCase],
) -> Tuple[str, ...]:
    """Derive coverage only from replayed event payloads.

    This prevents a release evidence edit from claiming behavior coverage by
    changing a metadata constant without adding an actual bounded trace path.
    """

    covered: set[str] = set()
    complete_counts: Counter[str] = Counter()
    max_study_run: Counter[str] = Counter()
    scheduler_days: dict[str, set[str]] = {}
    rating_names = {
        1: "rating_again",
        2: "rating_hard",
        3: "rating_good",
        4: "rating_easy",
    }
    for case in cases:
        days = scheduler_days.setdefault(case.case_id, set())
        for event in case.events:
            if event.event_type == "rollover":
                covered.add("anki_day_rollover")
                continue
            if event.event_type not in {"answer", "study_day"}:
                continue
            values = event.payload
            answers = max(0, int(values.get("answers", 1) or 0))
            eases = tuple(values.get("eases", ()))
            if event.event_type == "answer":
                eases = (values.get("ease", 3),)
            for ease in eases[:answers]:
                name = rating_names.get(max(1, min(4, int(ease))))
                if name:
                    covered.add(name)
            if answers:
                covered.add("eligible_answer")
            historical = {
                max(0, int(value))
                for value in values.get(
                    "historical_sync_answer_numbers", ()
                )
            }
            duplicates = {
                max(0, int(value))
                for value in values.get("duplicate_answer_numbers", ())
            }
            if historical:
                covered.add("synced_review_reward")
            if any(
                position not in historical
                for position in range(1, answers + 1)
            ):
                covered.add("local_review_reward")
            if historical.intersection(duplicates):
                covered.add("duplicate_sync_delivery")
            if values.get("include_excluded_answer"):
                covered.add("excluded_answer")
            find_mode = str(values.get("find_mode", "") or "")
            if find_mode == "natural":
                covered.add("standard_find_natural")
            elif find_mode == "forced":
                covered.add("standard_find_forced")
            if values.get("verify_find_caps"):
                covered.add("daily_find_uncapped")
            environment_mode = str(
                values.get("environment_mode", "") or ""
            )
            environment_behavior = {
                "rare_natural": "rare_environment_natural",
                "very_rare_natural": "very_rare_environment_natural",
                "ultra_rare_natural": "ultra_rare_environment_natural",
                "card_pity_simultaneous": "environment_card_pity",
                "completion_pity_simultaneous": (
                    "environment_completion_pity"
                ),
            }.get(environment_mode)
            if environment_behavior:
                covered.add(environment_behavior)
            if environment_mode in {
                "card_pity_simultaneous",
                "completion_pity_simultaneous",
            }:
                covered.add("simultaneously_forced_environment_tiers")
            # The bounded kernel lane uses fast in-memory storage. A restart
            # marker there is useful arithmetic sequencing, but is not durable
            # production/kernel restart evidence and must not claim coverage.
            scheduler_day = str(values.get("scheduler_day", "") or "")
            if scheduler_day:
                days.add(scheduler_day)
            if bool(values.get("complete", False)):
                complete_counts[case.case_id] += 1
                covered.add("todays_cards_completion")
            max_study_run[case.case_id] = max(
                max_study_run[case.case_id],
                max(0, int(values.get("trace_study_run", 0) or 0)),
            )
    if any(len(days) > 1 for days in scheduler_days.values()):
        covered.add("anki_day_rollover")
    if any(count >= 5 for count in complete_counts.values()):
        covered.add("fifth_garden_cycle_completion")
    if any(value >= 7 for value in max_study_run.values()):
        covered.add("seventh_streak_day_reward")
    return tuple(
        behavior for behavior in REQUIRED_PARITY_BEHAVIORS
        if behavior in covered
    )


class GardenGameEngineReplayAdapter:
    """Replay typed events through a real ``GardenGameEngine`` instance.

    The adapter intentionally accepts an engine factory so tests and release
    tooling can supply transactional temporary storage without importing Qt or
    mutating a user profile. Snapshot projection is caller-owned and must return
    the canonical trace schema used by the corresponding accelerated adapter.
    """

    def __init__(
        self,
        engine_factory: Callable[[], Any],
        snapshot: Callable[[Any, ProductionReplayEvent], Mapping[str, object]],
    ) -> None:
        self._engine_factory = engine_factory
        self._snapshot = snapshot

    def replay(
        self,
        events: Sequence[ProductionReplayEvent],
    ) -> ProductionReplayResult:
        engine = self._engine_factory()
        rows = []
        committed = []
        for event in events:
            event_type = str(event.event_type)
            payload = dict(event.payload)
            if event_type == "answer":
                engine.register_review(payload)
            elif event_type == "study_day":
                engine = self._replay_study_day(engine, payload)
            elif event_type == "today_cards":
                due_status = payload.pop("due_status", None)
                if due_status is None:
                    raise ValueError("today_cards event requires due_status")
                engine.evaluate_today_cards(due_status, **payload)
            elif event_type == "rollover":
                storage = engine.storage
                for key, value in payload.items():
                    setattr(storage, key, value)
                engine.rollover_if_needed()
            elif event_type == "undo":
                engine.record_review_undo(**payload)
            elif event_type == "restart":
                engine = self._engine_factory()
            elif event_type == "call":
                method_name = str(payload.pop("method"))
                method = getattr(engine, method_name)
                method(**payload)
            else:
                raise ValueError(f"unknown production replay event: {event_type}")
            projected = dict(self._snapshot(engine, event))
            projected.setdefault("event_identity", event.event_identity)
            rows.append(projected)
            committed.append(event.event_identity)
        return ProductionReplayResult(tuple(rows), tuple(committed))

    def _replay_study_day(self, engine: Any, payload: Mapping[str, Any]) -> Any:
        """Replay one daily checkpoint through public production operations."""

        values = dict(payload)
        scheduler_day = str(values.get("scheduler_day", "") or "")
        storage = engine.storage
        if scheduler_day:
            if hasattr(storage, "day"):
                storage.day = scheduler_day
            if hasattr(storage, "day_start_ms"):
                ordinal_delta = (
                    date.fromisoformat(scheduler_day)
                    - date.fromisoformat("2026-08-30")
                ).days
                storage.day_start_ms = (
                    1_788_099_990_000 + ordinal_delta * 86_400_000
                )
            if hasattr(storage, "now_ms"):
                storage.now_ms = int(
                    getattr(storage, "day_start_ms", 1_788_099_990_000)
                ) + 10_000
            engine.rollover_if_needed()

        answers = max(0, int(values.get("answers", 0) or 0))
        complete = bool(values.get("complete", False))
        due_total = answers if complete else answers + int(answers > 0)
        if answers:
            engine.observe_due_start(_due_status(review_count=due_total))
        eases = tuple(values.get("eases", ()))
        duplicate_numbers = {
            max(0, int(item))
            for item in values.get("duplicate_answer_numbers", ())
        }
        restart_numbers = {
            max(0, int(item))
            for item in values.get("restart_after_answer_numbers", ())
        }
        historical_sync_numbers = {
            max(0, int(item))
            for item in values.get("historical_sync_answer_numbers", ())
        }
        revlog_base = max(1, int(values.get("revlog_base", 1)))
        card_base = max(1, int(values.get("card_base", 1)))
        for position in range(1, answers + 1):
            ease = int(eases[position - 1]) if position <= len(eases) else 3
            revlog_id = revlog_base + position
            answer_payload = {
                "queue": 2,
                "ease": max(1, min(4, ease)),
                "lapse_count": int(ease == 1),
                "revlog_id": revlog_id,
                "answered_at_ms": revlog_id,
                "card_id": card_base + position,
                "answer_identity": f"parity:{revlog_id}:{card_base + position}",
                "scheduler_day": scheduler_day,
                "first_answer_of_day": position == 1,
                "day_answer_number": position,
                "history_counted": True,
                "emit_feedback": False,
            }
            if position in historical_sync_numbers:
                answer_payload.update({
                    "historical_sync": True,
                    "streak_days": max(
                        0, int(values.get("trace_study_run", 0) or 0)
                    ),
                    "environment_growth_known": True,
                    "correlation_id": (
                        f"parity-sync:{scheduler_day}:{revlog_id}"
                    ),
                })
            engine.register_review(answer_payload)
            if position in duplicate_numbers:
                engine.register_review(dict(answer_payload))
            remaining = max(0, due_total - position)
            engine.evaluate_today_cards(
                _due_status(review_count=remaining),
                record_completed_delta=True,
                emit_feedback=False,
            )
            if position in restart_numbers:
                engine = self._engine_factory()
        if values.get("include_excluded_answer"):
            # A reviewer hook without a durable revlog identity is explicitly
            # excluded by production and therefore has no accelerated event.
            excluded = engine.register_review({
                "queue": 2,
                "ease": 3,
                "revlog_id": 0,
                "answered_at_ms": 0,
                "card_id": card_base + answers + 1,
                "scheduler_day": scheduler_day,
                "emit_feedback": False,
            })
            if any((
                int(getattr(excluded, "total_growth", 0) or 0),
                int(getattr(excluded, "coins_awarded", 0) or 0),
            )):
                raise AssertionError(
                    "excluded parity answer unexpectedly changed resources"
                )
        if values.get("verify_find_caps"):
            reviewed_before = int(engine.state.daily_stats.reviewed)
            try:
                for reviewed, expected_cap in ((10, None), (199, None), (200, None), (399, None), (400, None), (1000, None)):
                    engine.state.daily_stats.reviewed = reviewed
                    observed_cap = engine.garden_find_status().daily_cap
                    if observed_cap != expected_cap:
                        raise AssertionError(
                            "production Find cap differs at "
                            f"{reviewed} cards: {observed_cap} != {expected_cap}"
                        )
            finally:
                engine.state.daily_stats.reviewed = reviewed_before
        recorder = getattr(storage, "record_replay_day", None)
        if callable(recorder):
            recorder(scheduler_day, complete=complete, studied=bool(answers))
        return engine


def _due_status(*, review_count: int = 0) -> Any:
    # Importing here keeps the analysis module importable without Anki/Qt.
    from ankigarden.storage import DueObligationStatus

    return DueObligationStatus(review_count=max(0, int(review_count)))


def project_production_engine_trace_row(
    engine: Any,
    event: ProductionReplayEvent,
) -> Mapping[str, object]:
    """Project one real-engine checkpoint into the accelerated trace schema."""

    state = engine.state
    daily = state.daily_stats
    aggregates = state.lifetime_economy_aggregates
    receipts = tuple(getattr(state, "recent_reward_receipts", ()) or ())
    coin_sources: Counter = Counter()
    for receipt in receipts:
        amount = max(0, int(getattr(receipt, "amount", 0) or 0))
        source = str(getattr(receipt, "source", "") or "")
        reward_type = str(getattr(receipt, "reward_type", "") or "")
        if source and amount and reward_type == "coins":
            coin_sources[source] += amount
    transactions = tuple(getattr(state, "currency_transactions", ()) or ())
    spent = sum(
        max(0, -int(getattr(row, "amount", 0) or 0))
        for row in transactions
    )
    raw_achievements = getattr(state, "achievements", ()) or ()
    achievements = tuple(
        raw_achievements.values()
        if isinstance(raw_achievements, Mapping)
        else raw_achievements
    )
    completed_achievements = sum(
        bool(
            getattr(row, "unlocked", False)
            or getattr(row, "completed", False)
            or getattr(row, "claimed", False)
        )
        for row in achievements
    )
    loadout = state.loadout
    standard_find_growth_units = sum(
        max(0, int(getattr(receipt, "amount", 0) or 0)) * 100
        for receipt in receipts
        if str(getattr(receipt, "source", "") or "") == "standard_find"
        and str(getattr(receipt, "reward_type", "") or "") == "growth"
    )
    project = getattr(state, "garden_project", None)
    raw_find_outcomes = getattr(state, "garden_find_outcomes", {}) or {}
    if isinstance(raw_find_outcomes, Mapping):
        finds_total = sum(
            str(getattr(value, "pool_id", "") or "") == "standard"
            and str(getattr(value, "status", "")).lower() == "hit"
            for value in raw_find_outcomes.values()
        )
    else:
        finds_total = len(raw_find_outcomes)
    from ankigarden.garden_finds import SPECIAL_ENVIRONMENT_POOL

    owned_environment_ids = {
        *(
            str(value)
            for value in state.inventory.get("garden_features", ())
        ),
        *(str(value) for value in state.inventory.get("scenery", ())),
    }
    environment_ownership_keys = {
        str(item.item_id) for item in SPECIAL_ENVIRONMENT_POOL
    }
    return {
        "event_identity": event.event_identity,
        "day": int(event.payload.get("trace_day", 0) or 0),
        "study": event.event_type in {"answer", "study_day"},
        "answers": int(getattr(daily, "reviewed", 0) or 0),
        "completed_today": bool(getattr(daily, "completed_due_cards", False)),
        "study_run": int(event.payload.get("trace_study_run", 0) or 0),
        "garden_rhythm_percent": int(
            engine.current_streak_bonus_percent()
            if hasattr(engine, "current_streak_bonus_percent")
            else event.payload.get("trace_rhythm_percent", 0) or 0
        ),
        "growth_total_units": int(getattr(aggregates, "growth_generated_units", 0) or 0),
        "growth_applied_units": int(getattr(aggregates, "growth_applied_to_plants_units", 0) or 0),
        "growth_stored_balance_units": int(
            getattr(state, "stored_growth_balance_units", 0) or 0
        ),
        "growth_spent_units": sum((
            int(getattr(aggregates, "growth_contributed_to_landmarks_units", 0) or 0),
            int(getattr(aggregates, "growth_contributed_to_mastery_units", 0) or 0),
            int(getattr(aggregates, "growth_contributed_to_legacy_units", 0) or 0),
        )),
        "growth_routed_to_storage_units_lifetime": int(getattr(aggregates, "growth_routed_to_storage_units_lifetime", 0) or 0),
        "growth_contributed_to_landmarks_units": int(getattr(aggregates, "growth_contributed_to_landmarks_units", 0) or 0),
        "growth_contributed_to_mastery_units": int(getattr(aggregates, "growth_contributed_to_mastery_units", 0) or 0),
        "growth_contributed_to_legacy_units": int(getattr(aggregates, "growth_contributed_to_legacy_units", 0) or 0),
        "growth_unallocated_overflow_units": int(getattr(aggregates, "growth_unallocated_overflow_units", 0) or 0),
        "coins_gross": sum(coin_sources.values()),
        "coins_spent": spent,
        "coins_wallet": int(getattr(state, "currency_balance", 0) or 0),
        "finds_total": finds_total,
        "environments_owned": len(
            owned_environment_ids.intersection(environment_ownership_keys)
        ),
        "beds_owned": int(getattr(state, "unlocked_slots", 0) or 0),
        "species_owned": len(getattr(state, "unlocked_species", ()) or ()),
        "achievements_claimed": completed_achievements,
        "active_garden_bonus_id": str(getattr(loadout, "active_garden_bonus_id", "") or ""),
        "active_scenery_id": str(getattr(loadout, "active_scenery_effect_id", "") or ""),
        "environment_effect_growth_units": sum((
            max(0, int(getattr(daily, "weather_growth", 0) or 0)) * 100,
            max(0, int(getattr(daily, "scenery_growth", 0) or 0)) * 100,
            max(
                0,
                int(getattr(daily, "instant_growth_units", 0) or 0)
                - standard_find_growth_units,
            ),
        )),
        "environment_effect_coins": sum(
            amount for source, amount in coin_sources.items()
            if source in {"harvest_bell", "autumn_hearth", "other"}
        ),
        "garden_cycle_remainder": int(getattr(state, "garden_cycle_remainder", 0) or 0),
        "coin_sources": dict(sorted(coin_sources.items())),
    }


def project_production_release_state(engine: Any) -> Mapping[str, object]:
    """Project every release-gate field without Qt or renderer inference."""

    state = engine.state
    storage = engine.storage
    ledger = getattr(storage, "_reward_ledger", None)
    connection = getattr(ledger, "_connection", None)
    if connection is None:
        reward_identities = tuple(sorted({
            str(value) for value in state.applied_reward_event_keys
        }))
        purchase_identities = tuple(sorted(
            str(record.request_id)
            for record in state.completed_purchase_requests
        ))
    else:
        reward_identities = tuple(
            str(row["event_key"])
            for row in connection.execute(
                "SELECT event_key FROM reward_event ORDER BY event_key"
            ).fetchall()
        )
        purchase_identities = tuple(
            str(row["operation_id"])
            for row in connection.execute(
                "SELECT operation_id FROM idempotency_record "
                "WHERE operation_kind = 'purchase' ORDER BY operation_id"
            ).fetchall()
        )
    bindings_resolver = getattr(storage, "all_answer_lineage_bindings", None)
    answer_lineage_bindings = (
        bindings_resolver()
        if callable(bindings_resolver)
        else dict(state.answer_lineage_bindings)
    )
    pending_resolver = getattr(storage, "pending_reanswer_lineages", None)
    pending_reanswers = (
        pending_resolver()
        if callable(pending_resolver)
        else dict(state.pending_reanswer_lineages)
    )
    aggregates = state.lifetime_economy_aggregates
    project = state.garden_project
    mastery = state.cultivation_mastery
    plants = tuple(sorted(
        (
            {
                "plant_id": str(plant.plant_id),
                "growth_units": max(0, int(plant.growth_units)),
                "stage": str(plant.growth_stage),
                "checkpoint_flags": tuple(sorted({
                    str(value) for value in plant.checkpoint_claims
                })),
                "stage_flags": tuple(sorted({
                    str(value) for value in plant.stage_reward_claims
                })),
                "slot_index": (
                    None if plant.slot_index is None else int(plant.slot_index)
                ),
                "fully_grown": bool(plant.fully_grown),
                "completion_cards": max(
                    0, int(getattr(plant, "completion_cards", 0) or 0)
                ),
                "completion_active_days": max(
                    0,
                    int(getattr(plant, "completion_active_days", 0) or 0),
                ),
            }
            for plant in state.plants
        ),
        key=lambda row: row["plant_id"],
    ))
    coin_ledger_entries = tuple(
        {
            "event_key": str(transaction.event_key),
            "transaction_type": str(transaction.transaction_type),
            "source": str(transaction.source),
            "source_id": str(transaction.source_id),
            "scheduler_day": str(transaction.scheduler_day),
            "correlation_id": str(transaction.correlation_id),
            "delta": int(transaction.delta),
            "balance": int(transaction.balance),
        }
        for transaction in state.currency_transactions
    )
    fertilizer_queues = tuple(
        {
            "plant_id": str(plant.plant_id),
            "active": tuple(
                (
                    str(batch.effect_id),
                    int(batch.growth_per_card_units),
                    int(batch.total_cards),
                    int(batch.remaining_cards),
                    str(batch.source_event_key),
                )
                for batch in plant.fertilizer_card_batches
            ),
            "queued": tuple(
                (
                    str(batch.effect_id),
                    int(batch.growth_per_card_units),
                    int(batch.total_cards),
                    int(batch.remaining_cards),
                    str(batch.source_event_key),
                )
                for batch in plant.fertilizer_card_queue
            ),
        }
        for plant in sorted(state.plants, key=lambda item: item.plant_id)
    )
    booster_queues = tuple(
        {
            "plant_id": str(plant.plant_id),
            "active": tuple(
                (
                    str(batch.effect_id),
                    int(batch.growth_per_card_units),
                    int(batch.total_cards),
                    int(batch.remaining_cards),
                    str(batch.source_event_key),
                )
                for batch in plant.booster_card_batches
            ),
            "queued": tuple(
                (
                    str(batch.effect_id),
                    int(batch.growth_per_card_units),
                    int(batch.total_cards),
                    int(batch.remaining_cards),
                    str(batch.source_event_key),
                )
                for batch in plant.booster_card_queue
            ),
        }
        for plant in sorted(state.plants, key=lambda item: item.plant_id)
    )
    completion = state.daily_completion
    inventory = state.inventory
    find_status = engine.garden_find_status()
    return {
        "garden_coin_wallet": max(0, int(state.currency_balance)),
        "coin_ledger_entries": coin_ledger_entries,
        "coin_source_ids": tuple(
            sorted({row["source"] for row in coin_ledger_entries if row["source"]})
        ),
        "plant_exact_growth_units": plants,
        "stored_growth_balance": max(
            0, int(state.stored_growth_balance_units)
        ),
        "lifetime_stored_routing_total": max(
            0, int(aggregates.growth_routed_to_storage_units_lifetime)
        ),
        "landmark_funding": max(
            0, int(project.landmark_growth_units_funded)
        ),
        "landmark_claims": max(
            0, int(project.landmark_highest_claimed_tier)
        ),
        "mastery_funding_by_species": dict(sorted(
            (
                str(species_id), max(0, int(units))
            )
            for species_id, units in (
                mastery.growth_units_funded_by_species or {}
            ).items()
        )),
        "mastery_claims": dict(sorted(
            (
                str(species_id), str(rank_id)
            )
            for species_id, rank_id in (
                mastery.highest_claimed_rank_by_species or {}
            ).items()
        )),
        "garden_legacy_progress": {
            "level": max(0, int(state.garden_legacy_level)),
            "progress_units": max(0, int(state.garden_legacy_progress_units)),
        },
        "stage_flags": {
            row["plant_id"]: row["stage_flags"] for row in plants
        },
        "checkpoint_flags": {
            row["plant_id"]: row["checkpoint_flags"] for row in plants
        },
        "bed_ownership": {
            "unlocked_slots": max(0, int(state.unlocked_slots)),
            "earned_bed_unlocks": tuple(sorted({
                max(0, int(value)) for value in state.earned_bed_unlocks
            })),
        },
        "achievement_ownership": tuple(sorted(
            str(achievement_id)
            for achievement_id, achievement in state.achievements.items()
            if achievement.unlocked
        )),
        "consumable_inventory": dict(sorted(
            (
                str(item_id), max(0, int(quantity))
            )
            for item_id, quantity in state.consumables.items()
        )),
        "fertilizer_queues": fertilizer_queues,
        "booster_remaining_cards": booster_queues,
        "garden_bonus_counters": {
            "wind_chime": max(0, int(state.wind_chime_progress)),
            "watering_station": max(0, int(state.watering_station_progress)),
            "firefly_lantern": max(0, int(state.firefly_lantern_progress)),
            "prism_pending_growth_units": max(
                0, int(state.prism_pending_growth_units)
            ),
            "hourglass_completion": max(
                0, int(state.hourglass_completion_progress)
            ),
        },
        "scenery_counters": {
            "snow_completion": max(0, int(state.snow_completion_progress)),
            "full_moon_completion": max(
                0, int(state.full_moon_completion_progress)
            ),
            "prism_released_anki_day_id": str(
                state.prism_released_anki_day_id or ""
            ),
        },
        "garden_cycle_remainder": max(0, int(state.garden_cycle_remainder)),
        "find_drought_counter": max(0, int(state.garden_find_drought_count)),
        "daily_find_cap_and_count": {
            "cap": find_status.daily_cap,
            "count": max(0, int(find_status.finds_today)),
        },
        "environment_pity_counters": {
            "card": dict(sorted(
                (
                    str(tier), max(0, int(value))
                )
                for tier, value in state.environment_pity_misses.items()
            )),
            "completion": dict(sorted(
                (
                    str(tier), max(0, int(value))
                )
                for tier, value in (
                    state.environment_completion_pity_misses or {}
                ).items()
            )),
        },
        "environment_ownership": {
            "garden_features": tuple(sorted({
                str(value) for value in inventory.get("garden_features", ())
            })),
            "scenery": tuple(sorted({
                str(value) for value in inventory.get("scenery", ())
            })),
        },
        "todays_cards_completion_state": {
            "scheduler_day": str(completion.scheduler_day),
            "status": str(completion.status),
            "reward_claimed": bool(completion.reward_claimed),
            "completed_due_cards": bool(state.daily_stats.completed_due_cards),
        },
        "equipped_items": {
            "decoration_id": str(state.loadout.display_decoration_id),
            "scenery_id": str(state.loadout.display_scenery_id),
        },
        "reward_identities": reward_identities,
        "purchase_identities": purchase_identities,
        "undo_lineage": {
            "bindings": dict(sorted(
                (str(key), str(value))
                for key, value in answer_lineage_bindings.items()
            )),
            "pending_reanswers": dict(sorted(
                (str(key), int(value))
                for key, value in pending_reanswers.items()
            )),
        },
        "state_revision": max(
            0, int(getattr(engine.storage, "_ledger_revision", 0) or 0)
        ),
    }


def canonical_trace_rows(rows: Iterable[Mapping[str, object]]) -> Tuple[Mapping[str, object], ...]:
    normalized = []
    for index, row in enumerate(rows):
        missing = [field for field in TRACE_FIELDS if field not in row]
        extra = sorted(set(row) - set(TRACE_FIELDS))
        if missing or extra:
            raise ValueError(
                f"trace row {index} schema mismatch; missing={missing}, extra={extra}"
            )
        normalized.append({field: to_primitive(row[field]) for field in TRACE_FIELDS})
    return tuple(normalized)


def trace_sha256(rows: Iterable[Mapping[str, object]]) -> str:
    return sha256(canonical_json_bytes(canonical_trace_rows(rows))).hexdigest()


def assert_engine_trace_parity(
    kernel_rows: Sequence[Mapping[str, object]],
    engine_rows: Sequence[Mapping[str, object]],
) -> None:
    expected = canonical_trace_rows(kernel_rows)
    observed = canonical_trace_rows(engine_rows)
    if len(expected) != len(observed):
        raise TraceMismatch(
            f"trace row count differs: kernel={len(expected)}, engine={len(observed)}",
            json_pointer="/",
            trace_prefix=expected[:min(len(expected), len(observed))],
        )
    for index, (kernel_row, engine_row) in enumerate(zip(expected, observed)):
        if kernel_row == engine_row:
            continue
        differences = [
            field for field in TRACE_FIELDS
            if kernel_row[field] != engine_row[field]
        ]
        field = differences[0]
        event_identity = str(kernel_row.get("event_identity", ""))
        pointer = f"/{index}/{field}"
        raise TraceMismatch(
            f"trace event {event_identity or index} differs at {pointer}: "
            f"kernel={kernel_row[field]!r}, engine={engine_row[field]!r}",
            event_identity=event_identity,
            json_pointer=pointer,
            trace_prefix=expected[:index + 1],
        )
