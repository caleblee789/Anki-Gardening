# Focused state contract

The persisted boundary is `user_files/garden_state.json`, currently schema version `10`.

UI-critical fields are:

- Totals: `streak_days`, `total_reviews`, `total_correct`, `total_wrong`.
- Today: `daily_stats.day`, review/accuracy counters, `growth_earned`, and quest metrics.
- Garden: `plants[]` with stable IDs, generated/editable names, planted dates, slots, non-negative growth, vitality in `0..1`, derived stages, and semantic milestone memories.
- Progression: `focus_plant_id` identifies the valid plant receiving 80% of new growth; `pending_milestone_reward` stores one earned review threshold and up to three stable species choices.
- Motivation: `daily_quests[]`, `achievements`, and `quest_history`.
- Appearance: `selected_weather`, inventory, and equipped local artwork. New gardens equip the explicit `none` decoration; migrated gardens preserve any selected decoration, including the lantern.
- Review ingestion: `retrospective_last_revlog_id` prevents replaying already-seen history.

Configuration is stored by Anki in `meta.json`; the packaged defaults are `config.json`. User-facing settings cover daily goal, home visibility, theme, asset quality, animations, and weather-particle intensity. Values are type/range validated and the active configuration changes only after `writeConfig` succeeds.

First-use guidance stores only a versioned `onboarding_version` preference in Anki configuration. Its visible step is derived from review totals, never persisted in `garden_state.json`; the former `plant_interaction_hint_seen=true` preference is interpreted as completed onboarding for compatibility.

Plant memories store only a stable ID, supported event kind, Anki-day date, numeric milestone, and optional stage transition. Rendered prose is not persisted. Supported kinds are planting, first focus, growth stage, streak landmark, and review landmark; duplicate IDs and malformed records are discarded during repair. Deck names, note fields, and card content are never stored.

Versions 8 and 9 migrate in place to version 10 without changing plant IDs, slot indices, stages, growth, or intentional decoration choices. Unsupported earlier development schemas are backed up and reset. Appearance configuration remains separate and is not reset with garden progress.
