# Documentation index

These documents describe the current schema-26 Anki Garden 2.2.0 working-tree
candidate.
Runtime source and persisted-state behavior remain authoritative when prose and
implementation disagree.

## Current product and release contracts

- `feature-evidence-matrix.md`: feature behavior and automated/live acceptance
  gates.
- `progression-rewards-effects-reference.md`: complete current economy,
  progression, catalog, migration, and replay rules.
- `release-notes-2.2.0.md`: learner-visible economy changes and schema-26
  compatibility notes.
- `release-notes-2.1.0.md`: frozen notes for the merged UI prerequisite.
- `display-validation-matrix.md`: prominent values and their authoritative
  sources.
- `e2e_display_assertions.md`: exact-package isolated-Anki journeys that remain
  required for live acceptance.
- `ui/data_contracts.md`: detailed persistence, reward identity, Garden Finds,
  Growth, purchases, and migration boundaries.
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
- `ui/final-ui-audit-2.1.0.md`: frozen prerequisite automated/macOS Qt evidence
  and its explicitly unrun human/platform gates; it does not approve 2.2.0.
- `garden-features.md`: the active registry, fixed layout, migration boundary,
  and static Home/native rendering contract.
- `references/garden-decorations-reference.docx`: illustrated 2.1.0 Garden
  Decoration prerequisite retained for visual provenance; use the 2.2.0
  progression reference for current mechanics.

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
archives, and lineage may remain under ignored `build/`; only the current full
contact-sheet set is retained as the active presentation aid.

The active UI capture contract remains v26, contract schema 2 and scenario
schema 3. Schema-26 economy changes require fresh exact-package evidence;
schema-25/v25 and the merged 2.1.0 evidence remain frozen historical material.
The [2.1.0 UI audit](ui/final-ui-audit-2.1.0.md) records that prerequisite’s
package and capture bindings and still-open human/platform gates. It is not a
2.2.0 release approval.
