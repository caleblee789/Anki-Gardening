# Focused state contract

The persisted boundary is `user_files/garden_state.json`, currently schema version `7`.

UI-critical fields are:

- Totals: `streak_days`, `total_reviews`, `total_correct`, `total_wrong`.
- Today: `daily_stats.day`, review/accuracy counters, `growth_earned`, and quest metrics.
- Garden: `plants[]` with stable IDs, species, names, slots, non-negative growth, vitality in `0..1`, and derived stages.
- Progression: `focus_plant_id` identifies the valid plant receiving 80% of new growth; `pending_milestone_reward` stores one earned review threshold and up to three stable species choices.
- Motivation: `daily_quests[]`, `achievements`, and `quest_history`.
- Appearance: `selected_weather`, inventory, and equipped local artwork.
- Review ingestion: `retrospective_last_revlog_id` prevents replaying already-seen history.

Configuration is stored by Anki in `meta.json`; the packaged defaults are `config.json`. User-facing settings cover daily goal, home visibility, theme, asset quality, animations, and weather-particle intensity. Values are type/range validated and the active configuration changes only after `writeConfig` succeeds.

Version 6 migrates once to v7, preserving visible progress while dropping dormant focus-session, exam, deck-map, shop/currency, event, mastery, rare-event, passive-reward, cloud, and social fields. Invalid layouts receive deterministic ID/slot/focus repair. Other schema versions are backed up and reset. Appearance configuration remains separate and is not reset with garden progress.
