# Anki Garden 2.1.0 final UI audit

Status: current automated and macOS Qt capture record for Release 2.1.0.

## Canonical evidence

Capture contract v19 contains 126 distinct ordered surfaces, each captured once
at canonical 100% scale. The retained run is:

- manifest:
  `build/ui-face-captures/capture-sequence-20260823-000843/20260823-000847/manifest.json`;
- contact sheets:
  `build/ui-face-captures/contact-sheets/anki-garden-ui-contact-sheet-2.1.0-20260823-000843`;
- evidence ZIP: `build/ui-face-captures/anki-garden-ui-faces-20260823-000843.zip`.

The manifest is complete at 126/126, requested scale factor `1.0`, primary
display, zero capture failures, and zero text-layout warnings. The independent
validator reports all 126 surfaces and all 17 contact sheets valid.

Artifact identities:

| Artifact | Identity |
|---|---|
| Production archive | 273 entries, 81,884,216 bytes, SHA-256 `005cae6ee1278bcdc68756f6d36b9e3857c3babbec5124219e8eea9930189dc7` |
| Capture derivative | SHA-256 `10e7760fb1dfa098acfaab018693fa3acb281c4bcdaccb9b401550b31a2d43ff` |
| Evidence ZIP | SHA-256 `9c49b19d22c796abe7fc0b288bf4633462fb547bd72468b6dd831b742eb51295` |
| Shared payload | 272 byte-identical entries, SHA-256 `47eb2980055297b05753c9c8739dd110ba2c45260b20afbcef39151106d92a9d` |

Only the explicit capture harness and mode-specific build-capability payload may
differ between production and capture archives.

## Covered surfaces

The canonical set covers:

- first-run Home, resumable onboarding, starter selection, placement,
  completion, and persistence failure;
- full Garden, plant selection, Nurture, all six marker positions, Move,
  Story, long values, missing artwork, and save recovery;
- Plant Growth, streak, Garden Coins, achievements, Garden Finds, reward
  history, Reviewer notifications, and Collection;
- four-tab Nursery, ownership, empty states, all purchase confirmations,
  typed errors, receipts, Garden spaces, Weather, Scenery, and Growth Charges;
- Settings, diagnostics, production-only capability absence, keyboard focus,
  reduced motion, loading, stale, empty, warning, error, and success states.

Resize, breakpoint, 150%, and 200% screenshot duplicates are intentionally
excluded. Responsive geometry, scroll reachability, text layout, dialog
lifecycle, focus, and reduced-motion behavior remain automated release gates.

## Automated boundary

The recorded final release evidence is:

- full repository suite: 1,856 passed and 8 skipped;
- package checks: 10 passed before the final capture-only framing work;
- focused post-fix checks: 3 passed, plus Python compilation and
  `git diff --check`;
- production/capture shared-payload parity: 272/272;
- capture and contact-sheet validation: 126/126 surfaces and 17/17 pages.

The local workspace intentionally retains only this canonical v19 evidence set.
Earlier complete and partial runs are predecessor evidence, not current-source
acceptance, and are available only through recovery material until that material
is permanently discarded.

## Unrun acceptance

Clean automated capture metadata does not prove:

- final-production exact-hash startup, restart, persistence, or every journey
  in `docs/e2e_display_assertions.md`;
- native Windows or Linux GUI behavior, true OS scaling, high/mixed-DPI display
  transitions, or platform font differences;
- screen-reader, contrast, keyboard-walkthrough, human/device visual, or full
  end-to-end acceptance.

These remain explicit release gates. They must not be relabeled as passed from
source tests, a capture derivative, or this macOS Qt evidence alone.
