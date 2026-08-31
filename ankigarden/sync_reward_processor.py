from __future__ import annotations

"""Atomic processing and presentation shaping for sync-introduced answers."""

from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

from .environment import ENVIRONMENT_CATALOG, GROWTH_CHARGES
from .garden_finds import standard_find_artwork_ref
from .game import CommittedAnswerResult
from .growth import GROWTH_UNITS_PER_POINT, stage_progress
from .models.state import GROWTH_STAGES
from .models.sync_reward import (
    SyncPlantCheckpoint,
    SyncPlantResult,
    SyncProjectGrowthAllocation,
    SyncRewardSummary,
)
from .sync_review_detector import SyncAttemptSnapshot


_RARITY_RANK = {
    "ultra rare": 0, "ultra environment": 0,
    "very rare": 1, "very rare environment": 1,
    "rare": 2, "rare environment": 2,
    "uncommon": 3, "common": 4, "": 5,
}


def _record(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    fields = (
        "plant_id", "plant_name", "name", "species", "stage",
        "growth_units", "slot_index", "fully_grown", "checkpoint_claims",
        "stage_reward_claims",
    )
    return {
        field: getattr(value, field)
        for field in fields
        if hasattr(value, field)
    }


def _plants_from_facts(facts: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    raw = facts.get("plants", {})
    rows = raw.values() if isinstance(raw, Mapping) else raw if isinstance(raw, (list, tuple)) else ()
    result: dict[str, dict[str, Any]] = {}
    for value in rows:
        row = _record(value)
        plant_id = str(row.get("plant_id", "") or "")
        if plant_id:
            result[plant_id] = row
    return result


def _plants_from_results(
    results: tuple[CommittedAnswerResult, ...], *, before: bool
) -> dict[str, dict[str, Any]]:
    rows = results[0].plants_before if before else results[-1].plants_after
    return {str(row.plant_id): _record(row) for row in rows if str(row.plant_id)}


def _asset_path(asset: Any) -> str:
    path = getattr(asset, "path", None)
    return str(path) if path else ""


def _plant_art(engine: Any, species: str, stage: str) -> str:
    resolver = getattr(engine, "resolve_plant_asset", None)
    if callable(resolver):
        try:
            return _asset_path(resolver(species, stage))
        except Exception:
            pass
    return ""


def _item_art(engine: Any, artwork_ref: str, item_id: str = "") -> str:
    raw = str(artwork_ref or item_id or "")
    if raw and Path(raw).is_file():
        return raw
    resolver = getattr(engine, "resolve_item_asset", None)
    if callable(resolver):
        for candidate in (raw, str(item_id or "")):
            candidate = candidate.removeprefix("ui_")
            if not candidate:
                continue
            try:
                resolved = _asset_path(resolver(candidate))
            except Exception:
                resolved = ""
            if resolved:
                return resolved
    return raw


def _environment_item(environment_id: str) -> tuple[str, Any | None]:
    for kind, catalog in ENVIRONMENT_CATALOG.items():
        item = catalog.get(str(environment_id))
        if item is not None:
            return str(kind), item
    return "", None


def _environment_art(engine: Any, environment_id: str) -> str:
    kind, _item = _environment_item(environment_id)
    resolver = getattr(
        engine,
        "resolve_garden_feature_preview_asset"
        if kind == "garden_feature" else "resolve_scenery_preview_asset",
        None,
    )
    if callable(resolver):
        try:
            return _asset_path(resolver(environment_id))
        except Exception:
            pass
    return ""


def _receipt_identity(engine: Any, receipt: Any) -> tuple[Any, ...]:
    resolver = getattr(engine, "_reward_receipt_identity", None)
    if callable(resolver):
        try:
            return tuple(resolver(receipt))
        except Exception:
            pass
    return (
        str(getattr(receipt, "event_key", "")),
        str(getattr(receipt, "reward_type", "")),
        str(getattr(receipt, "source", "")),
        str(getattr(receipt, "source_id", "")),
        str(getattr(receipt, "correlation_id", "")),
        int(getattr(receipt, "amount", 0) or 0),
        str(getattr(receipt, "item_id", "")),
        str(getattr(receipt, "plant_id", "")),
    )


def _new_receipts(
    engine: Any,
    results: tuple[CommittedAnswerResult, ...],
    baseline: Mapping[str, Any],
) -> tuple[Any, ...]:
    previous = {
        tuple(value) if isinstance(value, (list, tuple)) else value
        for value in (baseline.get("reward_receipts", ()) or ())
    }
    batch_correlations = {
        str(result.correlation_id)
        for result in results
        if str(result.correlation_id)
    }
    ordered = [receipt for result in results for receipt in result.reward_receipts]
    for receipt in getattr(getattr(engine, "state", None), "recent_reward_receipts", ()) or ():
        if (
            _receipt_identity(engine, receipt) not in previous
            and (
                not batch_correlations
                or str(getattr(receipt, "correlation_id", ""))
                in batch_correlations
            )
        ):
            ordered.append(receipt)
    unique: dict[tuple[Any, ...], Any] = {}
    for receipt in ordered:
        unique.setdefault(_receipt_identity(engine, receipt), receipt)
    return tuple(unique.values())


def _post_facts(engine: Any) -> dict[str, Any]:
    resolver = getattr(engine, "sync_reward_baseline", None)
    if not callable(resolver):
        return {}
    try:
        value = resolver()
    except Exception:
        return {}
    return dict(value) if isinstance(value, Mapping) else {}


def _item_name_rarity(item_id: str) -> tuple[str, str]:
    charge = GROWTH_CHARGES.get(str(item_id))
    if charge is not None:
        return str(charge.name), str(charge.rarity)
    names = {
        "booster_potion": "Booster Potion",
        "fertilizer_basic": "Basic Fertilizer",
        "fertilizer_quality": "Quality Fertilizer",
        "fertilizer_premium": "Premium Fertilizer",
    }
    return names.get(str(item_id), str(item_id).replace("_", " ").title()), ""


def _rarity_key(value: Any) -> int:
    normalized = str(value or "").replace("_", " ").casefold()
    return _RARITY_RANK.get(normalized, 5)


def build_sync_reward_summary(
    batch_id: str,
    results: tuple[CommittedAnswerResult, ...],
    *,
    baseline: Mapping[str, Any] | None = None,
    engine: Any = None,
) -> SyncRewardSummary | None:
    """Shape only engine-confirmed batch facts; never calculate rewards."""

    if not results:
        return None
    before_facts = dict(baseline or {})
    after_facts = _post_facts(engine)
    before_plants = _plants_from_facts(before_facts) or _plants_from_results(results, before=True)
    after_plants = _plants_from_facts(after_facts) or _plants_from_results(results, before=False)
    active_after = str(after_facts.get("active_plant_id") or results[-1].active_plant_after_id or "")

    plant_rows: list[dict[str, Any]] = []
    for plant_id, after in after_plants.items():
        before = before_plants.get(plant_id, {})
        before_units = max(0, int(before.get("growth_units", 0) or 0))
        after_units = max(0, int(after.get("growth_units", 0) or 0))
        delta_units = max(0, after_units - before_units)
        before_progress = stage_progress(before_units // GROWTH_UNITS_PER_POINT)
        after_progress = stage_progress(after_units // GROWTH_UNITS_PER_POINT)
        if not delta_units and before_progress.stage == after_progress.stage:
            continue
        species = str(after.get("species", "") or "")
        stage_after = str(after_progress.stage)
        plant_rows.append({
            "plant_id": plant_id,
            "plant_name": str(after.get("plant_name") or after.get("name") or "Plant"),
            "species": species,
            "plant_image": _plant_art(engine, species, stage_after),
            "growth_delta_units": delta_units,
            "stage_before": str(before_progress.stage),
            "stage_after": stage_after,
            "stage_progress_before": int(round(before_progress.progress * 100)),
            "stage_progress_after": int(round(after_progress.progress * 100)),
            "next_stage": str(after_progress.next_stage or ""),
            "fully_grown": bool(after.get("fully_grown", after_progress.fully_grown)),
            "active": plant_id == active_after,
        })
    plant_rows.sort(key=lambda row: (
        not bool(row["active"]), -int(row["growth_delta_units"]),
        str(row["plant_name"]).casefold(), str(row["plant_id"]),
    ))

    stored_before = max(0, int(before_facts.get(
        "stored_growth_units", results[0].stored_growth_before_units
    ) or 0))
    stored_after = max(0, int(after_facts.get(
        "stored_growth_units", results[-1].stored_growth_after_units
    ) or 0))
    stored_delta = max(0, stored_after - stored_before)
    # Project funding is copied only from immutable committed answer results.
    # Mutable post-sync state is deliberately not a presentation authority.
    landmark_delta = sum(
        max(0, int(result.landmark_growth_delta_units)) for result in results
    )
    mastery_delta = sum(
        max(0, int(result.mastery_growth_delta_units)) for result in results
    )
    legacy_delta = sum(
        max(0, int(result.legacy_growth_delta_units)) for result in results
    )
    project_totals: dict[tuple[str, str], int] = {}
    for result in results:
        for allocation in result.project_allocations:
            raw_type = getattr(allocation, "target_type", "")
            target_type = str(getattr(raw_type, "value", raw_type) or "")
            target_id = str(getattr(allocation, "target_id", "") or "")
            units = max(0, int(getattr(allocation, "units", 0) or 0))
            if target_type not in {"landmark", "mastery", "legacy"}:
                continue
            if not target_id or units <= 0:
                continue
            key = (target_type, target_id)
            project_totals[key] = project_totals.get(key, 0) + units
    project_allocations = tuple(
        SyncProjectGrowthAllocation(target_type, target_id, units)
        for (target_type, target_id), units in project_totals.items()
    )
    accounted_growth_units = (
        stored_delta
        + landmark_delta
        + mastery_delta
        + legacy_delta
        + sum(
            max(
                0,
                int(after.get("growth_units", 0) or 0)
                - int(
                    before_plants.get(plant_id, {}).get("growth_units", 0)
                    or 0
                ),
            )
            for plant_id, after in after_plants.items()
        )
    )
    if "total_growth_units" in before_facts and "total_growth_units" in after_facts:
        growth_total_units = max(
            accounted_growth_units,
            max(
                0,
                int(after_facts.get("total_growth_units", 0) or 0)
                - int(before_facts.get("total_growth_units", 0) or 0),
            ),
        )
    else:
        growth_total_units = accounted_growth_units
    shared_growth_units = sum(max(0, int(result.award.shared_growth_units)) for result in results)

    receipts = _new_receipts(engine, results, before_facts)
    if "garden_coin_balance" in before_facts and "garden_coin_balance" in after_facts:
        coins = max(
            0,
            int(after_facts.get("garden_coin_balance", 0) or 0)
            - int(before_facts.get("garden_coin_balance", 0) or 0),
        )
    else:
        transactions: dict[str, Any] = {}
        for result in results:
            for transaction in result.currency_transactions:
                transactions.setdefault(str(transaction.transaction_id), transaction)
        coins = sum(
            max(0, int(transaction.delta))
            for transaction in transactions.values()
            if str(getattr(transaction, "transaction_type", "credit")) != "debit"
        )

    finds_by_id: dict[str, dict[str, Any]] = {}
    environments: dict[str, dict[str, Any]] = {}
    represented_find_inventory: dict[str, int] = defaultdict(int)
    for result in results:
        for outcome in result.garden_find_outcomes:
            if str(outcome.status) != "hit" or not str(outcome.reward_id):
                continue
            reward_id = str(outcome.reward_id)
            if str(outcome.pool_id) == "environment":
                kind, item = _environment_item(reward_id)
                environments[reward_id] = {
                    "environment_id": reward_id,
                    "display_name": str(getattr(item, "name", "") or outcome.display_name or reward_id),
                    "rarity": str(getattr(item, "rarity", "") or outcome.tier or ""),
                    "preview_asset": _environment_art(engine, reward_id) or _item_art(engine, outcome.artwork_ref, reward_id),
                    "environment_kind": kind,
                }
                continue
            row = finds_by_id.setdefault(reward_id, {
                "reward_id": reward_id,
                "display_name": str(outcome.display_name or reward_id),
                "quantity": 0,
                "rarity": str(outcome.tier or ""),
                "image_asset": _item_art(
                    engine,
                    standard_find_artwork_ref(reward_id, outcome.artwork_ref),
                    outcome.item_id or reward_id,
                ),
                "reward_type": str(outcome.reward_type or ""),
            })
            quantity = (
                max(1, int(outcome.amount or 1))
                if str(outcome.reward_type) == "inventory_item" else 1
            )
            row["quantity"] = int(row["quantity"]) + quantity
            if str(outcome.reward_type) == "inventory_item" and outcome.item_id:
                represented_find_inventory[str(outcome.item_id)] += quantity

    has_consumable_conservation = bool(
        "consumables" in before_facts and "consumables" in after_facts
    )
    for receipt in receipts:
        source = str(getattr(receipt, "source", ""))
        reward_type = str(getattr(receipt, "reward_type", ""))
        item_id = str(getattr(receipt, "item_id", "") or getattr(receipt, "source_id", ""))
        if reward_type == "environment_item" or source == "garden_find_environment":
            kind, item = _environment_item(item_id)
            if item is not None:
                environments.setdefault(item_id, {
                    "environment_id": item_id,
                    "display_name": str(item.name), "rarity": str(item.rarity),
                    "preview_asset": _environment_art(engine, item_id),
                    "environment_kind": kind,
                })
            continue
        if reward_type != "inventory_item" or source == "garden_find" or not item_id:
            continue
        name, rarity = _item_name_rarity(item_id)
        row = finds_by_id.setdefault(item_id, {
            "reward_id": item_id, "display_name": name, "quantity": 0,
            "rarity": rarity, "image_asset": _item_art(engine, item_id, item_id),
            "reward_type": "inventory_item",
        })
        if not has_consumable_conservation:
            row["quantity"] = int(row["quantity"]) + max(
                1, int(getattr(receipt, "amount", 1) or 1)
            )

    # Conservation catches batch-wide achievement/milestone rewards not
    # attached to an individual answer result.
    before_consumables = dict(before_facts.get("consumables", {}) or {})
    after_consumables = dict(after_facts.get("consumables", {}) or {})
    for item_id, after_quantity in sorted(after_consumables.items()):
        net = max(0, int(after_quantity or 0) - int(before_consumables.get(item_id, 0) or 0))
        missing = max(0, net - represented_find_inventory[str(item_id)])
        if missing <= 0:
            continue
        name, rarity = _item_name_rarity(str(item_id))
        row = finds_by_id.setdefault(str(item_id), {
            "reward_id": str(item_id), "display_name": name, "quantity": 0,
            "rarity": rarity, "image_asset": _item_art(engine, str(item_id), str(item_id)),
            "reward_type": "inventory_item",
        })
        row["quantity"] = int(row["quantity"]) + missing

    before_env = dict(before_facts.get("environments", {}) or {})
    after_env = dict(after_facts.get("environments", {}) or {})
    for kind in ("garden_feature", "scenery"):
        for environment_id in sorted(set(after_env.get(kind, ()) or ()) - set(before_env.get(kind, ()) or ())):
            _catalog_kind, item = _environment_item(str(environment_id))
            if item is not None:
                environments.setdefault(str(environment_id), {
                    "environment_id": str(environment_id),
                    "display_name": str(item.name), "rarity": str(item.rarity),
                    "preview_asset": _environment_art(engine, str(environment_id)),
                    "environment_kind": kind,
                })

    transitions_by_plant: dict[str, list[Any]] = defaultdict(list)
    seen_transitions: set[tuple[str, str, str, str]] = set()
    for result in results:
        for transition in result.stage_transitions:
            identity = (
                str(transition.plant_id), str(transition.previous_stage),
                str(transition.new_stage), str(transition.source),
            )
            if identity not in seen_transitions:
                seen_transitions.add(identity)
                transitions_by_plant[str(transition.plant_id)].append(transition)
    progression: list[dict[str, Any]] = []
    for plant_id, transitions in transitions_by_plant.items():
        final = transitions[-1]
        count = len(transitions)
        full_bloom = str(final.new_stage).casefold() in {"rare", "full_bloom", "full bloom"}
        stage_name = "Full Bloom" if full_bloom else str(final.new_stage).replace("_", " ").title()
        name = str(final.plant_name or "Plant")
        progression.append({
            "event_id": f"stage:{batch_id}:{plant_id}:{final.new_stage}",
            "plant_id": plant_id,
            "plant_name": name,
            "event_type": "full_bloom" if full_bloom else "stage",
            "stage_name": stage_name,
            "display_text": (
                f"{name} reached Full Bloom" if full_bloom
                else f"{name} advanced {count} stages and reached {stage_name}" if count > 1
                else f"{name} reached {stage_name}"
            ),
            "transition_source": str(final.source or ""),
        })
    covered_stage_claims = {
        (str(transition.plant_id), str(transition.new_stage))
        for transitions in transitions_by_plant.values()
        for transition in transitions
    }
    for plant_id, after in after_plants.items():
        before_stages = set(
            before_plants.get(plant_id, {}).get("stage_reward_claims", ()) or ()
        )
        newly_claimed = [
            str(stage_id)
            for stage_id in set(after.get("stage_reward_claims", ()) or ())
            - before_stages
            if (plant_id, str(stage_id)) not in covered_stage_claims
        ]
        newly_claimed.sort(key=lambda stage_id: (
            GROWTH_STAGES.index(stage_id)
            if stage_id in GROWTH_STAGES else len(GROWTH_STAGES),
            stage_id,
        ))
        if newly_claimed:
            final_stage = newly_claimed[-1]
            full_bloom = final_stage == "rare"
            stage_name = (
                "Full Bloom" if full_bloom
                else final_stage.replace("_", " ").title()
            )
            name = str(after.get("plant_name") or after.get("name") or "Plant")
            progression.append({
                "event_id": f"stage:{batch_id}:{plant_id}:{final_stage}",
                "plant_id": plant_id,
                "plant_name": name,
                "event_type": "full_bloom" if full_bloom else "stage",
                "stage_name": stage_name,
                "display_text": (
                    f"{name} reached Full Bloom" if full_bloom
                    else f"{name} advanced {len(newly_claimed)} stages and reached {stage_name}"
                    if len(newly_claimed) > 1
                    else f"{name} reached {stage_name}"
                ),
            })
    for plant_id, after in after_plants.items():
        before_claims = set(before_plants.get(plant_id, {}).get("checkpoint_claims", ()) or ())
        after_claims = set(after.get("checkpoint_claims", ()) or ())
        name = str(after.get("plant_name") or after.get("name") or "Plant")
        for claim in sorted(after_claims - before_claims):
            stage_id, _separator, percent = str(claim).partition(":")
            stage_name = "Full Bloom" if stage_id == "rare" else stage_id.replace("_", " ").title()
            checkpoint_name = f"{percent}% toward {stage_name}"
            progression.append({
                "event_id": f"checkpoint:{batch_id}:{plant_id}:{claim}",
                "plant_id": plant_id, "event_type": "checkpoint",
                "plant_name": name,
                "checkpoint_name": checkpoint_name, "stage_name": stage_name,
                "checkpoint_percent": (
                    max(0, min(100, int(percent))) if percent.isdigit() else 0
                ),
                "display_text": f"{checkpoint_name} reached",
            })

    current_day_resolver = getattr(engine, "_scheduler_day", None)
    try:
        current_day = str(current_day_resolver()) if callable(current_day_resolver) else ""
    except Exception:
        current_day = ""
    all_clear_receipts = tuple(
        receipt for receipt in receipts
        if str(getattr(receipt, "source", "")) == "all_due"
        and (not current_day or str(getattr(receipt, "scheduler_day", "")) == current_day)
    )
    fertilizer_changed = bool(
        "fertilizer_signature" in before_facts and "fertilizer_signature" in after_facts
        and before_facts.get("fertilizer_signature") != after_facts.get("fertilizer_signature")
    )
    booster_changed = bool(
        "booster_signature" in before_facts and "booster_signature" in after_facts
        and before_facts.get("booster_signature") != after_facts.get("booster_signature")
    )
    fertilizer_item_id = str(after_facts.get("fertilizer_item_id", "") or "")
    booster_item_id = str(after_facts.get("booster_item_id", "") or "")
    finds = tuple(sorted(finds_by_id.values(), key=lambda row: (
        _rarity_key(row.get("rarity")), str(row.get("display_name", "")).casefold(), str(row.get("reward_id", "")),
    )))
    discoveries = tuple(sorted(environments.values(), key=lambda row: (
        _rarity_key(row.get("rarity")), str(row.get("display_name", "")).casefold(), str(row.get("environment_id", "")),
    )))
    progression.sort(key=lambda row: (
        0 if row.get("event_type") == "full_bloom" else 1 if row.get("event_type") == "stage" else 2,
        str(row.get("plant_id", "")), str(row.get("event_id", "")),
    ))
    grouped_rows = {str(row.get("plant_id", "")): row for row in plant_rows}
    for event in progression:
        plant_id = str(event.get("plant_id", "") or "")
        if not plant_id or plant_id in grouped_rows:
            continue
        after = after_plants.get(plant_id, {})
        before = before_plants.get(plant_id, {})
        before_units = max(0, int(before.get("growth_units", 0) or 0))
        after_units = max(0, int(after.get("growth_units", 0) or 0))
        before_progress = stage_progress(before_units // GROWTH_UNITS_PER_POINT)
        after_progress = stage_progress(after_units // GROWTH_UNITS_PER_POINT)
        species = str(after.get("species", "") or "")
        grouped_rows[plant_id] = {
            "plant_id": plant_id,
            "plant_name": str(
                after.get("plant_name")
                or after.get("name")
                or event.get("plant_name")
                or "Plant"
            ),
            "species": species,
            "plant_image": _plant_art(engine, species, str(after_progress.stage)),
            "growth_delta_units": max(0, after_units - before_units),
            "stage_before": str(before_progress.stage),
            "stage_after": str(after_progress.stage),
            "stage_progress_before": int(round(before_progress.progress * 100)),
            "stage_progress_after": int(round(after_progress.progress * 100)),
            "next_stage": str(after_progress.next_stage or ""),
            "fully_grown": bool(after.get("fully_grown", after_progress.fully_grown)),
            "active": plant_id == active_after,
        }

    events_by_plant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in progression:
        events_by_plant[str(event.get("plant_id", "") or "")].append(event)
    plant_results: list[SyncPlantResult] = []
    for row in grouped_rows.values():
        plant_id = str(row.get("plant_id", "") or "")
        events = events_by_plant.get(plant_id, [])
        checkpoints = tuple(
            SyncPlantCheckpoint(
                event_id=str(event.get("event_id", "") or ""),
                percent=max(0, min(100, int(event.get("checkpoint_percent", 0) or 0))),
                stage_name=str(event.get("stage_name", "") or ""),
                display_text=str(event.get("display_text", "") or ""),
            )
            for event in events
            if str(event.get("event_type", "")).casefold() == "checkpoint"
        )
        stage_events = [
            event for event in events
            if str(event.get("event_type", "")).casefold() != "checkpoint"
        ]
        stage_event = stage_events[-1] if stage_events else {}
        full_bloom = any(
            str(event.get("event_type", "")).casefold() == "full_bloom"
            for event in stage_events
        )
        plant_results.append(SyncPlantResult(
            plant_id=plant_id,
            display_name=str(row.get("plant_name", "") or "Plant"),
            species=str(row.get("species", "") or ""),
            artwork_asset=str(row.get("plant_image", "") or ""),
            growth_delta_units=max(0, int(row.get("growth_delta_units", 0) or 0)),
            stage_before=str(row.get("stage_before", "") or ""),
            stage_after=str(row.get("stage_after", "") or ""),
            stage_progress_before=max(0, min(100, int(row.get("stage_progress_before", 0) or 0))),
            stage_progress_after=max(0, min(100, int(row.get("stage_progress_after", 0) or 0))),
            next_stage=str(row.get("next_stage", "") or ""),
            fully_grown=bool(row.get("fully_grown", False)),
            active=bool(row.get("active", False)),
            checkpoints=checkpoints,
            stage_event_id=str(stage_event.get("event_id", "") or ""),
            stage_event_text=str(stage_event.get("display_text", "") or ""),
            full_bloom=full_bloom,
            transition_source=str(
                stage_event.get("transition_source", "") or ""
            ),
        ))
    plant_results.sort(key=lambda row: (
        not row.active,
        not row.full_bloom,
        -row.growth_delta_units,
        row.display_name.casefold(),
        row.plant_id,
    ))
    summary = SyncRewardSummary(
        batch_id=str(batch_id),
        anki_days=tuple(sorted({str(result.scheduler_day) for result in results})),
        eligible_answer_count=sum(max(0, int(result.cards_completed)) for result in results),
        growth_total_units=growth_total_units,
        plant_results=tuple(plant_results),
        plant_growth=tuple(plant_rows),
        shared_growth_delta_units=shared_growth_units,
        stored_growth_delta_units=stored_delta,
        landmark_growth_delta_units=landmark_delta,
        mastery_growth_delta_units=mastery_delta,
        legacy_growth_delta_units=legacy_delta,
        project_allocations=project_allocations,
        garden_coin_delta=coins,
        finds=finds,
        environment_discoveries=discoveries,
        progression_events=tuple(progression),
        all_clear_earned=bool(all_clear_receipts),
        all_clear_coin_reward=sum(
            max(0, int(getattr(receipt, "amount", 0) or 0))
            for receipt in all_clear_receipts
            if str(getattr(receipt, "reward_type", "")) == "coins"
        ),
        fertilizer_cards_remaining=max(
            0,
            int(after_facts.get("fertilizer_cards_remaining", 0) or 0),
        ),
        fertilizer_remaining_seconds=max(0, int(after_facts.get("fertilizer_remaining_seconds", 0) or 0)),
        fertilizer_state_changed=fertilizer_changed,
        fertilizer_item_id=fertilizer_item_id,
        fertilizer_art_asset=(
            _item_art(engine, fertilizer_item_id, fertilizer_item_id)
            if fertilizer_item_id else ""
        ),
        booster_cards_remaining=max(0, int(after_facts.get("booster_cards_remaining", 0) or 0)),
        booster_state_changed=booster_changed,
        booster_item_id=booster_item_id,
        booster_art_asset=(
            _item_art(engine, booster_item_id, booster_item_id)
            if booster_item_id else ""
        ),
        source_batch_ids=(str(batch_id),),
    )
    return summary if summary.meaningful else None


class SyncRewardProcessor:
    def __init__(self, engine: Any, storage: Any, presenter: Any) -> None:
        self.engine = engine
        self.storage = storage
        self.presenter = presenter

    def process(
        self,
        snapshot: SyncAttemptSnapshot | None,
        *,
        presentation_enabled: bool = True,
    ) -> SyncRewardSummary | None:
        if snapshot is None:
            return None
        if not snapshot.valid:
            if snapshot.one_way_replacement:
                baseline = getattr(self.engine, "baseline_reward_history", None)
                if callable(baseline):
                    baseline(snapshot.invalidation_reason or "collection_replaced", persist=True)
            return None

        due_status = None
        resolver = getattr(self.storage, "due_obligations", None)
        if callable(resolver):
            try:
                due_status = resolver()
            except Exception:
                due_status = None
        created: list[SyncRewardSummary] = []

        def factory(results: tuple[CommittedAnswerResult, ...]) -> SyncRewardSummary | None:
            summary = build_sync_reward_summary(
                snapshot.batch_id,
                results,
                baseline=snapshot.reward_baseline,
                engine=self.engine,
            )
            if summary is not None:
                created.append(summary)
            return summary

        ok, _message = self.engine.reconcile_reward_history(
            persist=True,
            include_open_day=True,
            due_status=due_status,
            pending_summary_factory=factory if presentation_enabled else None,
            emit_feedback=False,
        )
        if not ok or not presentation_enabled or not created:
            return None
        pending = SyncRewardSummary.from_dict(self.engine.state.pending_sync_reward_summary)
        if pending is None:
            return None
        enqueue = getattr(self.presenter, "enqueue", None)
        if callable(enqueue):
            enqueue(pending)
        return created[-1]
