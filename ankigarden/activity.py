"""Saved, read-only views of committed Garden activity.

These records live in the reward ledger's transaction. They describe rewards;
they never grant them. Group totals are a disposable, indexed projection of
the event rows, so opening Activity does not scan a lifetime of answers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from typing import Any, Iterable, Mapping


ACTIVITY_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS activity_event (
        event_key TEXT PRIMARY KEY, group_id TEXT NOT NULL,
        scheduler_day TEXT NOT NULL, occurred_at TEXT NOT NULL,
        occurred_ms INTEGER NOT NULL, source TEXT NOT NULL,
        correlation_id TEXT NOT NULL, coins INTEGER NOT NULL,
        growth_units INTEGER NOT NULL, card_answers INTEGER NOT NULL,
        finds INTEGER NOT NULL, adjustment INTEGER NOT NULL,
        payload_json TEXT NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS activity_event_group_idx ON activity_event(group_id, occurred_ms)",
    "CREATE INDEX IF NOT EXISTS activity_event_day_idx ON activity_event(scheduler_day, occurred_ms)",
    "CREATE INDEX IF NOT EXISTS activity_event_source_idx ON activity_event(source, scheduler_day)",
    """CREATE TABLE IF NOT EXISTS activity_group (
        group_id TEXT PRIMARY KEY, kind TEXT NOT NULL,
        started_at TEXT NOT NULL, ended_at TEXT NOT NULL, status TEXT NOT NULL,
        scheduler_day TEXT NOT NULL DEFAULT '', sort_ms INTEGER NOT NULL DEFAULT 0,
        card_answers INTEGER NOT NULL DEFAULT 0, earned INTEGER NOT NULL DEFAULT 0,
        spent INTEGER NOT NULL DEFAULT 0, adjustments INTEGER NOT NULL DEFAULT 0,
        growth_units INTEGER NOT NULL DEFAULT 0, finds INTEGER NOT NULL DEFAULT 0)""",
    "CREATE INDEX IF NOT EXISTS activity_group_recent_idx ON activity_group(sort_ms DESC, group_id)",
)


def timestamp_ms(value: str) -> int:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return int(parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).timestamp() * 1000)
    except (ValueError, TypeError, OverflowError):
        return 0


def iso_from_ms(value: int) -> str:
    return datetime.fromtimestamp(max(0, value) / 1000, timezone.utc).isoformat()


@dataclass(frozen=True)
class ActivityEvent:
    event_key: str
    group_id: str
    scheduler_day: str
    occurred_at: str
    source: str
    correlation_id: str = ""
    coins: int = 0
    growth_units: int = 0
    card_answers: int = 0
    finds: int = 0
    adjustment: bool = False
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ActivitySession:
    group_id: str
    kind: str = "session"
    started_at: str = ""
    ended_at: str = ""
    status: str = "open"


@dataclass(frozen=True)
class ActivityEntry:
    group_id: str
    kind: str
    started_at: str
    ended_at: str
    status: str
    scheduler_day: str
    sort_ms: int
    card_answers: int
    earned: int
    spent: int
    adjustments: int
    growth_units: int
    finds: int


ALIASES = {
    "daily_activity": "first_eligible_answer",
    "all_due": "todays_cards",
    "garden_find": "standard_find",
    "achievement_backfill": "achievement",
    "environment_daily_gift": "environment_completion_gift",
}


def source_name(source: str, source_id: str = "", reason: str = "",
                achievement_names: Mapping[str, str] | None = None) -> str:
    """Translate known identities, keeping unknown and old records honest."""
    from .ui.copy import learner_card_copy
    from .ui.economy_presenters import coin_reward_receipt

    source = ALIASES.get(source, source)
    if source in {"fertilizer_use", "booster_use", "growth_charge_use"}:
        from .reward_presentation import _inventory_item_name
        return f"{_inventory_item_name(source_id)} used" if source_id else "Garden item used"
    if source == "achievement":
        from .achievements import BED_MILESTONES
        if source_id in BED_MILESTONES:
            return f"Bed {BED_MILESTONES[source_id]} unlocked"
        name = (achievement_names or {}).get(source_id, "")
        if not name:
            from .achievements import ACHIEVEMENTS_BY_ID
            definition = ACHIEVEMENTS_BY_ID.get(source_id)
            name = str(getattr(definition, "name", "") or "")
        return f"Achievement · {name}" if name else "Achievement reward"
    if source == "first_eligible_answer":
        return "First card today"
    if source == "standard_find":
        name = reason.removeprefix("Standard Find: ").removeprefix("Garden Find: ")
        return learner_card_copy(name) if name else "Garden Find"
    if source in {"plant_milestone", "full_bloom", "purchase", "migration", "refund"}:
        return learner_card_copy(reason) if reason else {
            "plant_milestone": "Plant milestone", "full_bloom": "Full Bloom",
            "purchase": "Purchase", "migration": "Coin adjustment", "refund": "Refund",
        }[source]
    if source == "autumn_hearth" and reason.startswith("Autumn Hearth bonus for "):
        return learner_card_copy(reason)
    names = {
        "welcome": "Welcome gift", "garden_reward": "Garden reward",
        "legacy": "Earlier Coin activity", "garden_find_environment": "Garden discovery",
        "environment_completion_gift": "Scenery gift",
        "garden_decoration": "Garden bonus", "growth_charge": "Growth Charge used",
        "charge": "Growth Charge used", "answer_growth": "Review Growth",
        "prism_harvest": "Prism Trellis", "adjustment": "Coin adjustment",
    }
    if source in names:
        if source in {"environment_completion_gift", "garden_decoration"} and reason:
            return learner_card_copy(reason)
        return names[source]
    receipt = coin_reward_receipt(source, 0)
    return receipt.title if receipt.source_id != "other" else "Garden reward"


def event_from_economy(record: Any, *, state: Any = None,
                       correlation_id: str = "", earlier: bool = False) -> ActivityEvent:
    key = str(record.event_key)
    source = str(record.source_id or record.event_kind or "legacy")
    if str(record.event_kind).startswith("migration"):
        source = "migration"
    if record.event_kind in {"growth_charge_use", "fertilizer_use", "booster_use"}:
        source = record.event_kind
    coin_delta = int(record.coins_earned) - int(record.coins_spent)
    if record.coins_spent:
        source = "purchase"
    transactions = getattr(state, "currency_transactions", ()) or ()
    transaction = next((tx for tx in reversed(transactions) if transaction_event_key(tx) == key), None)
    receipts = tuple(r for r in (getattr(state, "recent_reward_receipts", ()) or ())
                     if r.event_key == key)
    payload: dict[str, Any] = {"earlier": earlier}
    if transaction is not None:
        source = str(transaction.source or source)
        payload.update(source_id=transaction.source_id, reason=transaction.reason)
        correlation_id = correlation_id or str(transaction.correlation_id)
    elif receipts:
        payload.update(source_id=receipts[0].source_id, reason=receipts[0].title)
    else:
        payload.update(source_id=str(record.item_id or ""))
        if key.startswith("achievement:"):
            payload["source_id"] = key.partition(":")[2]
    if receipts:
        payload["items"] = [
            {"kind": r.reward_type, "item_id": r.item_id, "amount": r.amount,
             "name": r.title}
            for r in receipts if r.reward_type in {"inventory_item", "environment_item"}
        ]
    metrics = dict(record.metric_deltas or {})
    payload["destinations"] = {
        "plants": int(record.growth_applied_to_plants_units),
        "storage": max(0, int(record.stored_growth_balance_delta_units)),
        "projects": sum(int(getattr(record, name, 0)) for name in (
            "growth_contributed_to_landmarks_units", "growth_contributed_to_mastery_units",
            "growth_contributed_to_legacy_units")),
    }
    if record.item_id and record.quantity and not payload.get("items") and not metrics.get("consumables_used"):
        payload["items"] = [{"kind": "inventory_item", "item_id": record.item_id,
                             "amount": record.quantity, "name": ""}]
    if source == "purchase":
        purchase = next((item.outcome for item in reversed(
            getattr(state, "completed_purchase_requests", ()) or ())
            if f"purchase:{item.request_id}" == key), None)
        if purchase is not None:
            payload["reason"] = purchase.item_name + (f" ×{purchase.quantity:,}" if purchase.quantity > 1 else "")
            payload["purchase_named"] = True
    growth = int(record.growth_generated_units)
    if earlier and not growth and record.growth_flow_kind == "legacy_unreconciled":
        payload["growth_unavailable"] = True
    return ActivityEvent(
        key, key, str(record.scheduler_day), str(record.occurred_at), source,
        correlation_id, coin_delta, growth, 0,
        sum(int(v) for v in dict(metrics.get("finds_by_outcome", {})).values()),
        source in {"migration", "refund", "adjustment"} or record.event_kind == "migration",
        payload,
    )


def transaction_event_key(tx: Any) -> str:
    key = str(tx.event_key)
    if str(tx.source) == "purchase" and key.startswith("purchase-request:"):
        return "purchase:" + key.partition(":")[2]
    return key


def event_from_transaction(tx: Any, *, earlier: bool = True) -> ActivityEvent:
    key = transaction_event_key(tx)
    return ActivityEvent(key, key, str(tx.scheduler_day or ""),
                         str(tx.occurred_at), str(tx.source or "legacy"),
                         str(tx.correlation_id or ""), int(tx.delta),
                         adjustment=str(tx.source) in {"migration", "refund", "adjustment"},
                         payload={"source_id": str(tx.source_id), "reason": str(tx.reason),
                                  "earlier": earlier})


def write_activity(connection: Any, events: Iterable[ActivityEvent],
                   sessions: Iterable[ActivitySession]) -> None:
    """Called only inside RewardLedger's atomic commit."""
    deltas: dict[str, list[int]] = {}

    def accumulate(group_id, coins, growth, answers, finds, adjustment, sign=1):
        values = (answers, max(0, coins) if not adjustment else 0,
                  max(0, -coins), max(0, coins) if adjustment else 0, growth, finds)
        delta = deltas.setdefault(group_id, [0] * 6)
        for index, value in enumerate(values):
            delta[index] += sign * value

    for event in events:
        old = connection.execute("""SELECT group_id, coins, growth_units,
            card_answers, finds, adjustment FROM activity_event WHERE event_key=?""",
                                 (event.event_key,)).fetchone()
        if old:
            accumulate(*old, sign=-1)
        accumulate(event.group_id, event.coins, event.growth_units,
                   event.card_answers, event.finds, event.adjustment)
        values = (event.event_key, event.group_id, event.scheduler_day, event.occurred_at,
                  timestamp_ms(event.occurred_at), event.source, event.correlation_id,
                  event.coins, event.growth_units, event.card_answers, event.finds,
                  int(event.adjustment), json.dumps(dict(event.payload), ensure_ascii=False))
        connection.execute("""INSERT INTO activity_event VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(event_key) DO UPDATE SET group_id=excluded.group_id,
            scheduler_day=excluded.scheduler_day, occurred_at=excluded.occurred_at,
            occurred_ms=excluded.occurred_ms, source=excluded.source,
            correlation_id=excluded.correlation_id, coins=excluded.coins,
            growth_units=excluded.growth_units, card_answers=excluded.card_answers,
            finds=excluded.finds, adjustment=excluded.adjustment, payload_json=excluded.payload_json""", values)
        kind = ("adjustment" if event.adjustment else "purchase" if event.coins < 0 else
                "use" if event.source.endswith("_use") else "reward")
        connection.execute("""INSERT OR IGNORE INTO activity_group
            (group_id,kind,started_at,ended_at,status) VALUES (?,?,?,?,?)""",
            (event.group_id, kind, event.occurred_at, event.occurred_at, "recorded"))
    for session in sessions:
        deltas.setdefault(session.group_id, [0] * 6)
        connection.execute("""INSERT INTO activity_group
            (group_id,kind,started_at,ended_at,status) VALUES (?,?,?,?,?)
            ON CONFLICT(group_id) DO UPDATE SET kind=excluded.kind,
            started_at=CASE WHEN excluded.started_at='' THEN activity_group.started_at
                ELSE excluded.started_at END,
            ended_at=CASE WHEN excluded.status='open' AND activity_group.status='recorded' THEN ''
                WHEN excluded.ended_at='' THEN activity_group.ended_at
                ELSE excluded.ended_at END,
            status=CASE WHEN activity_group.status IN ('ended','interrupted') AND excluded.status='open'
                THEN activity_group.status ELSE excluded.status END""",
            (session.group_id, session.kind, session.started_at, session.ended_at, session.status))
    for group_id, delta in deltas.items():
        # Subtract the previous event before adding its replacement. This keeps
        # upserts and group moves exact without re-summing a growing session on
        # every answer. The event and these totals share the ledger transaction.
        connection.execute("""UPDATE activity_group SET card_answers=card_answers+?,
            earned=earned+?, spent=spent+?, adjustments=adjustments+?,
            growth_units=growth_units+?, finds=finds+? WHERE group_id=?""",
            (*delta, group_id))
        latest = connection.execute("""SELECT scheduler_day, occurred_ms FROM activity_event
            WHERE group_id=? ORDER BY occurred_ms DESC, event_key DESC LIMIT 1""", (group_id,)).fetchone()
        if latest is None:
            connection.execute("DELETE FROM activity_group WHERE group_id=? AND kind NOT IN ('session','sync','study')", (group_id,))
            continue
        end = connection.execute("SELECT ended_at FROM activity_group WHERE group_id=?", (group_id,)).fetchone()
        connection.execute("UPDATE activity_group SET scheduler_day=?, sort_ms=? WHERE group_id=?",
            (latest[0], max(int(latest[1]), timestamp_ms(end[0])), group_id))


def read_entries(connection: Any, *, filter_key: str = "all", limit: int = 20,
                 before: tuple[int, str] | None = None) -> tuple[ActivityEntry, ...]:
    conditions = ["sort_ms>0"]
    params: list[Any] = []
    predicate = {"study": "kind IN ('session','sync','study') AND card_answers>0",
                 "earned": "(earned>0 OR growth_units>0 OR finds>0 OR kind='reward') AND kind!='adjustment'",
                 "spent": "spent>0"}.get(filter_key)
    if predicate:
        conditions.append(predicate)
    if before is not None:
        conditions.append("(sort_ms<? OR (sort_ms=? AND group_id<?))")
        params.extend((before[0], before[0], before[1]))
    params.append(min(100, max(1, int(limit))))
    rows = connection.execute("SELECT * FROM activity_group WHERE " + " AND ".join(conditions)
        + " ORDER BY sort_ms DESC, group_id DESC LIMIT ?", params).fetchall()
    return tuple(ActivityEntry(**dict(row)) for row in rows)


def read_events(connection: Any, group_id: str) -> tuple[ActivityEvent, ...]:
    rows = connection.execute("SELECT * FROM activity_event WHERE group_id=? ORDER BY occurred_ms,event_key",
                              (group_id,)).fetchall()
    return tuple(ActivityEvent(
        event_key=row["event_key"], group_id=row["group_id"], scheduler_day=row["scheduler_day"],
        occurred_at=row["occurred_at"], source=row["source"], correlation_id=row["correlation_id"],
        coins=row["coins"], growth_units=row["growth_units"], card_answers=row["card_answers"],
        finds=row["finds"], adjustment=bool(row["adjustment"]), payload=json.loads(row["payload_json"]),
    ) for row in rows)


def read_day_totals(connection: Any, day: str) -> dict[str, int]:
    row = connection.execute("""SELECT COALESCE(SUM(card_answers),0),
        COALESCE(SUM(CASE WHEN coins>0 AND adjustment=0 THEN coins ELSE 0 END),0),
        COALESCE(SUM(growth_units),0), COALESCE(SUM(finds),0)
        FROM activity_event WHERE scheduler_day=?""", (day,)).fetchone()
    return dict(zip(("card_answers", "coins", "growth_units", "finds"), map(int, row)))
