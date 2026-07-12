# Focused state contract

The persisted boundary is `user_files/garden_state.json`, currently schema version `8`.

UI-critical fields are:

- Totals: `streak_days`, `total_reviews`, `total_correct`, `total_wrong`.
- Today: `daily_stats.day`, review/accuracy counters, `growth_earned`, and quest metrics.
- Garden: `plants[]` with stable IDs, generated/editable names, planted dates, slots, non-negative growth, vitality in `0..1`, derived stages, and semantic milestone memories.
- Progression: `focus_plant_id` identifies the valid plant receiving 80% of new growth; `pending_milestone_reward` stores one earned review threshold and up to three stable species choices.
- Motivation: `daily_quests[]`, `achievements`, and `quest_history`.
- Appearance: `selected_weather`, inventory, and equipped local artwork.
- Review ingestion: `retrospective_last_revlog_id` prevents replaying already-seen history.

Configuration is stored by Anki in `meta.json`; the packaged defaults are `config.json`. User-facing settings cover daily goal, home visibility, theme, asset quality, animations, and weather-particle intensity. Values are type/range validated and the active configuration changes only after `writeConfig` succeeds.

Plant memories store only a stable ID, supported event kind, Anki-day date, numeric milestone, and optional stage transition. Rendered prose is not persisted. Supported kinds are planting, first focus, growth stage, streak landmark, and review landmark; duplicate IDs and malformed records are discarded during repair. Deck names, note fields, and card content are never stored.

Because the add-on is not yet publicly released, all earlier development schema versions are backed up and reset when v8 loads. Appearance configuration remains separate and is not reset with garden progress.
