# Documentation index

These documents describe the current state-schema-27 Anki Garden 2.2.0
working-tree candidate.
Runtime source and persisted-state behavior remain authoritative when prose and
implementation disagree.

## Current product and release contracts

- `feature-evidence-matrix.md`: feature behavior and automated/live acceptance
  gates.
- `release-notes-2.2.0.md`: learner-visible 2.2.0 changes and migration notes.
- `progression-rewards-effects-reference.md`: current Growth, Garden Coin,
  consumable, purchase, Garden Cycle, achievement, Collection, Landmark,
  Mastery, Legacy, persistence, and replay authority.
- `display-validation-matrix.md`: prominent values and their authoritative
  sources.
- `e2e_display_assertions.md`: exact-package isolated-Anki journeys that remain
  required for live acceptance.
- `ui/data_contracts.md`: persistence, reward identity, Garden Finds, Growth,
  purchases, and migration boundaries for UI consumers.
- `reviewer-hud-specification.md`: exact Today’s Cards copy, HUD geometry,
  plant/checkpoint presentation, persistent-copy exclusions, integrated
  reward-dock bundles, responsive behavior, and accessibility.
- `ui/state_scenarios.md`: supported first-run, Garden, Nursery, Collection,
  Settings, responsive, and failure states.
- `ui/entrypoint_matrix.md`: supported UI entry points.
- `ui-release-overhaul-contract.md`: current UI architecture, routing,
  transaction, responsive, accessibility, and capture contract.
- `ui-surface-inventory.md`: registry-derived v26 release inventory and the
  automated/manual acceptance boundary.
- `garden-features.md`: the active registry, fixed layout, migration boundary,
  and static Home/native rendering contract.
- `references/garden-decorations-reference.docx`: illustrated current Garden
  Decoration catalog, acquisition methods, Garden Find rates, Garden Bonuses,
  and runtime artwork.

## Visual and future-work contracts

- `storybook-gouache-assets.md`: current Verdant Twilight V6 visual language,
  asset topology, and release-readiness rules.
- `planter-family-geometry-baseline.md`: current six-slot scene and planter
  geometry invariants.
- `future-features.md`: ideas intentionally outside the shipped release,
  including layered foliage wind animation.

Superseded capture chronologies, intermediate package hashes, and pre-overhaul
audit ledgers remain available through Git history or preserved raw local
evidence. They are not active product or release evidence. Raw runs, manifests,
archives, and lineage may remain under ignored `build/`.

The active UI evidence contract is v26, contract schema 2 and scenario schema
3. It derives 18 representative surfaces on two sheets and 34 full surfaces on
five sheets. State schema 27 changes the product data and economy without
changing that topology; v25 capture evidence remains frozen historical
material and is never reused as v26 evidence.

The retained [2.1.0 UI audit](ui/final-ui-audit-2.1.0.md) and
[184547 five-page contact-sheet index](../build/ui-face-captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.1.0-20260830-184547/contact-sheet-set.json)
form a frozen v26 baseline only. They do not certify the integrated 2.2.0
candidate and are not current release evidence. A new 2.2.0 audit, exact
package binding, hashes, manifests, and contact-sheet index will be recorded
only after fresh native capture and review. Automated evidence will continue to
leave human, platform, accessibility, and mixed-DPI gates open.
