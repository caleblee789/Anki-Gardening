# Documentation index

Use the references below for the state-schema-30 Anki Garden 2.2.0 candidate.
Runtime source and persisted-state behavior remain authoritative when prose and
implementation disagree. Dated audit reports describe their own frozen candidates.

## Release status

The rebuilt [2.2.0 archive](../dist/anki_garden.ankiaddon) has 272 entries,
96,641,056 bytes (92.16 MiB), SHA-256
`7a28a409c7eeb3b918e4d5d317cbc46ca40eeb6b0dcb5c91a8074fdef251db7a`.
The final runtime change disposes the reviewer's Reset position menu after use:
20 repeated openings retain zero menus instead of 20, with identical pixels and
actions. All artwork and the other 271 archive payloads match the prior
Windows-fix candidate. Further sampled lossless artwork compression saved only
0.014% of the archive, so no artwork was changed.

[Final verification](../build/final-release-20260915/) includes 863 passing
release/Qt checks with zero skips, 51 focused HUD/layout passes, asset and compile
checks, and exact production-package parity. Combined default evidence has
1,802 passes and 17 retired-contract skips: the refreshed default lane plus the
unchanged passing annual engine simulation from this run. One release-note
acceptance statement was restored after the first full run caught its removal
during consolidation; the original result and rerun provenance are retained. Native macOS Anki
26.08.1 passed eight answers across all ratings and both HUD modes, 194 HUD paints
without overlap, 12 surfaces, and minimum/fullscreen transitions. Sixteen
Activity/Settings reopen cycles held widget and active-timer counts constant.
Anki's installer, a clean restart, and switching to a second disconnected profile
preserved garden progress, inventory, balances, review totals and settings.

The [final readiness record](../build/final-release-20260915/readiness.json)
tracks exact source and package identity. The owner authorized publication of
this package. The [previous readiness record](../build/release-launch-20260913/readiness.json)
and [Windows/macOS report](../build/windows-vm-qa-20260913/REPORT.md) preserve
historical results. Windows ARM and x64 under ARM emulation passed the prior
scoped fixes. Native macOS verification covers the final archive.

Use the [development guide](development.md#freeze-and-check-release-readiness)
for gate commands and evidence requirements, and the
[publication handoff](../release-copy/PUBLISHING_NOTES.md) for launch actions.

## Current product and release contracts

- [Development guide](development.md): source installation, packaging, and local checks.
- [Functional acceptance](feature-evidence-matrix.md): feature coverage and exact-package native journeys.
- [Release notes](release-notes-2.2.0.md): learner-visible 2.2.0 changes and migration notes.
- [Progression, rewards, and effects](progression-rewards-effects-reference.md): current Growth, Coins,
  consumable, purchase, Study rewards, achievement, Collection, Landmark,
  Mastery, Legacy, persistence, and replay authority.
- [UI data contracts](ui/data_contracts.md): persistence, reward identity, Garden Finds, Growth,
  purchases, and migration boundaries for UI consumers.
- [Reviewer and reward UI](reviewer-hud-specification.md): HUD geometry,
  plant/checkpoint presentation, persistent-copy exclusions, integrated
  reward-dock bundles, responsive behavior, and accessibility.
- [UI state scenarios](ui/state_scenarios.md): supported first-run, Garden, Nursery, Collection,
  Settings, responsive, and failure states.
- [UI entry points](ui/entrypoint_matrix.md): supported navigation routes.
- [UI surface inventory](ui-surface-inventory.md): capture profiles, execution, and handoff requirements from the active compiled registry.
- [Garden features](garden-features.md): the active registry, fixed layout, migration boundary,
  and static Home/native rendering contract.
- [Illustrated decoration reference](references/garden-decorations-reference.docx): current Garden
  Decoration catalog, acquisition methods, Garden Find rates, Garden Bonuses,
  and runtime artwork.

## Visual and future-work contracts

- [Artwork](storybook-gouache-assets.md): current Verdant Twilight V6 visual language,
  asset topology, and release-readiness rules.
- [Plant and planter geometry](planter-family-geometry-baseline.md): current six-slot scene and planter
  geometry invariants.
- [Future features](future-features.md): ideas intentionally outside the shipped release,
  including layered foliage wind animation.

## Historical evidence

- [September 12–13 hardening](pre-release-hardening-20260912.md): frozen tests, capture, sync and performance results, with unresolved native diagnostics.
- [September 8 package/performance audit](performance-package-audit-20260908.md): measured size and runtime improvements with pixel/parity evidence.
- [September 8 cleanup](project-cleanup-20260908.md): retained evidence and diagnostic recovery.
- [Progression audit](balance-audit-20260905.md): earlier simulations and findings; current accepted pacing is in the release notes.
- [Historical UI architecture and display matrix](ui-release-overhaul-contract.md): superseded layout/mechanics and their original source mappings.
- [UI quality review](ui/release-quality-20260904.md), [polish report](ui/release-polish-20260904.md), [2.2.0 audit](ui/final-ui-audit-2.2.0.md), and [2.1.0 audit](ui/final-ui-audit-2.1.0.md): earlier package-bound visual evidence.

Other dated reports retain distinct experiments, fixes, limitations, and evidence
links. Raw runs, manifests, archives, and lineage may remain under ignored
`build/`; superseded artifacts may instead survive in Git or the retained
diagnostic archive. Historical results do not certify a newer candidate.
