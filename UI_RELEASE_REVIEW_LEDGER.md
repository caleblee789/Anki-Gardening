# Anki Garden UI release review ledger

This ledger tracks the combined UI/economy candidate. The 2.1.0 capture set
`capture-sequence-20260830-184547` is a frozen visual baseline, not evidence for
the final package. Cream contact-sheet padding is outside the product UI.

Cycle 2 closes the exact-package automated and native macOS Qt evidence recorded
below. It is not independent human or cross-platform release approval; the
generated status remains `quality_status: review-required` and
`release_ready: false`.

The generated sheet index therefore keeps `Automated checks passed; visual
review pending`. The accepted rows below record Codex review in this separate
ledger and do not overwrite that independent-human-review boundary.

## Shared root causes from the baseline review

| ID | Severity | Root cause | Surfaces | Status |
| --- | --- | --- | --- | --- |
| R01 | Blocker | Equivalent cards, buttons, badges, progress rows, and dialog geometry do not consistently use the shared visual hierarchy. | 03, 07, 09-11, 13-26, 31-34 | Cleared — Cycle 2 exact-package raw and sheet review verified the shared hierarchy. |
| R02 | Blocker | Action labels sometimes repeat cost, hide clickability, or describe an implementation detail instead of the result. | 03, 05, 07, 09-10, 13, 15, 19, 23-24, 26, 29-31 | Cleared — Cycle 2 verified distinct action, cost, and balance presentation. |
| R03 | Blocker | Gold is used as generic selection and applied, preview, active, displayed, owned, queued, and locked states need clearer separation. | 04, 14, 19-25 | Cleared — Cycle 2 verified mint selection and reserved gold currency/reward semantics. |
| R04 | Blocker | Entity copy, artwork, stage, target, transaction, and reward totals must remain bound to stable IDs and committed results. | 05-12, 14, 16, 18-24, 27-34 | Cleared — Cycle 2 verified identity, artwork, transaction, and committed-reward bindings. |
| R05 | Major | Fixed or oversized layouts create excess space, weak density, or avoidable scrolling at the canonical viewport. | 03, 07, 09-11, 13, 15, 17, 20-26, 31-34 | Cleared — Cycle 2 verified canonical-viewport density, scrolling, and complete geometry. |
| R06 | Major | Stage semantics and stage-relative versus lifetime Growth are not explicit everywhere. | 05-07, 11-12, 14, 18-19, 27-28, 33-34 | Cleared — Cycle 2 verified Reached/Current/Next/Locked and stage-relative Growth copy. |
| R07 | Major | Reward and transaction presentation repeats information or lacks canonical ordering and dynamic grammar. | 10, 15-17, 22-24, 27-34 | Cleared — Cycle 2 verified canonical ordering, omission, and dynamic grammar. |
| R08 | Major | Garden Cycle and long-term project states must consume the frozen renderer-neutral economy projections without duplicating calculations. | 18, 21-24, 28-30 | Cleared — Cycle 2 verified renderer-neutral Garden Cycle and project projections. |

## Canonical surface inventory

| # | Manifest surface ID | Baseline review finding | Owner | Cycle 1 | Final |
| ---: | --- | --- | --- | --- | --- |
| 01 | `starter-deck-browser-home` | Match active-card shell; keep one compact explicit action and no starter progress decoration. | Scene/Home | Not run (full only) | Accepted — Cycle 2 exact-package full raw |
| 02 | `starter-garden-onboarding` | Preserve safe upper placement and step state; make Skip a real tertiary control without over-dimming the scene. | Dashboard | Accepted | Accepted — Cycle 2 exact-package full raw |
| 03 | `starter-nursery-plants` | Replace plain Choose text with aligned compact buttons and keep View stages secondary. | Dashboard | Accepted | Accepted — Cycle 2 exact-package full raw |
| 04 | `starter-placement` | Keep one compact step bar; mint selected bed and dynamic `Plant in Bed N`; preserve immediate success state. | Dashboard/Scene | Not run (full only) | Accepted — Cycle 2 exact-package full raw |
| 05 | `full-garden` | Normalize the three-part header and make empty nurtured state obviously actionable. | Dashboard/Scene | Not run (full only) | Accepted — Cycle 2 exact-package full raw |
| 06 | `plant-at-every-stage` | Audit species/stage artwork identity, soil-line anchoring, scale, overlap, and scenery compatibility. | Scene/Home | Recapture required | Accepted — Cycle 2 exact-package full raw |
| 07 | `selected-plant-nurtured` | Compact the panel, normalize actions, and use canonical nurtured toast copy. | Dashboard | Recapture required | Accepted — Cycle 2 exact-package full raw |
| 08 | `move-mode` | Bind every label/art target to plant IDs; contextualize destination labels and preserve nurture by ID. | Dashboard/Scene | Not run (full only) | Accepted — Cycle 2 exact-package full raw |
| 09 | `fertilizer-active` | Replace timed expiry with exact cards remaining; show the stored Basic dose as `Queue`; align upgrade rows and keep Open nursery tertiary. | Dashboard | Recapture required | Accepted — Cycle 2 exact-package full raw |
| 10 | `purchase-confirmation-fertilizer-queue` | Reduce scale; show price once; keep compact target and before/after balance rows. | Dashboard | Not run (full only) | Accepted — Cycle 2 exact-package full raw |
| 11 | `plant-story` | Show Reached/Current/Next/Locked and explain stage-relative versus lifetime Growth without clipping six stages. | Dashboard | Accepted | Accepted — Cycle 2 exact-package full raw |
| 12 | `active-deck-browser-home-after-nurture` | Match starter shell and keep only garden, nurtured plant, stage progress, and compact action. | Scene/Home | Accepted | Accepted — Cycle 2 exact-package full raw |
| 13 | `progress-today-cards` | Use Due at start, completed wording, an actionable bonus control, distinct appearance rows, and no needless scroll. | Dashboard | Not run (full only) | Accepted — Cycle 2 exact-package full raw |
| 14 | `growth-nonzero` | Rename Today, preserve reconciled totals, and use consistent future-stage artwork policy. | Dashboard | Accepted | Accepted — Cycle 2 exact-package full raw |
| 15 | `streak-active` | Replace repeated Completed copy with check/date, add Reward label, and content-size the dialog. | Dashboard | Not run (full only) | Accepted — Cycle 2 exact-package full raw |
| 16 | `coins-activity` | Emphasize current balance and rename final ledger column Running balance. | Dashboard | Not run (full only) | Accepted — Cycle 2 exact-package full raw |
| 17 | `progress-achievements` | Remove duplicate completion signals, label rewards, reduce padding, and protect bottom-row visibility. | Dashboard | Not run (full only) | Accepted — Cycle 2 exact-package full raw |
| 18 | `progress-collection` | Compact metrics to Species/Entries, align filters, and retain a responsive clickable grid/no-results state. | Dashboard | Recapture required | Accepted — Cycle 2 exact-package full raw |
| 19 | `collection-species-overview` | Use mint, distinguish catalog preview from personal progress, and use explicit View plant/Nurture states. | Dashboard | Not run (full only) | Accepted — Cycle 2 exact-package full raw |
| 20 | `collection-loadout-detail` | Compact appearance metadata; distinguish Current, preview, and dirty states; use Enabled/Disabled. | Dashboard/Scene | Accepted; visual correction queued | Accepted — Cycle 2 exact-package full raw |
| 21 | `nursery-plants` | Reduce completion-card height and keep the one-time-species completion action concise. | Dashboard | Not run (full only) | Accepted — Cycle 2 exact-package full raw |
| 22 | `nursery-fertilizer-booster` | Use Active/Queued/Owned/Available and the production card-counted actions `Queue`, `Use`, and `Buy and queue`; never imply a wall-clock expiry. | Dashboard | Recapture required | Accepted — Cycle 2 exact-package full raw |
| 23 | `nursery-garden-spaces` | Use mint for Next bed; show unlocked beds plus one explicit earned Bed 3 card with progression guidance and no purchase control or price. | Dashboard | Not run (full only) | Accepted — Cycle 2 exact-package full raw |
| 24 | `nursery-garden-decorations-scenery` | Separate Displayed and Active today, show effects, and replace passive discovery text with a disclosure. | Dashboard | Not run (full only) | Accepted — Cycle 2 exact-package full raw |
| 25 | `settings-display-advanced-open` | Use shared appearance wording, Enabled/Disabled, concise setting labels, and draft Restore defaults behavior. | Dashboard/Scene | Recapture required | Accepted — Cycle 2 exact-package full raw |
| 26 | `diagnostics-warning` | Make copy confirmation transient, details bounded, and checking/all-clear geometry stable. | Dashboard | Not run (full only) | Accepted — Cycle 2 exact-package full raw |
| 27 | `reviewer-hud-expanded` | Use Next card, clamp names, protect native controls, and keep compact stable geometry. | Reviewer | Recapture required | Accepted — Cycle 2 exact-package full raw |
| 28 | `session-summary-after-review` | Omit zero sections, preserve canonical ordering, reconcile committed totals, and pin header/footer around one body scroll. | Reviewer | Recapture required | Accepted — Cycle 2 exact-package full raw |
| 29 | `sync-rewards-summary` | Use reviews terminology, dynamic discovery grammar, reconciled committed totals, and an explicit Close control. | Reviewer | Recapture required | Accepted — Cycle 2 exact-package full raw |
| 30 | `reviewer-reward-dock-bundle` | Promote Choose next plant; show Stored Growth/project status at endgame; queue events at stable height. | Reviewer | Recapture required | Accepted — Cycle 2 exact-package full raw |
| 31 | `purchase-confirmation-growth-charge` | Remove repeated price, reduce vertical gaps, and use `Buy charge`. | Dashboard | Accepted | Accepted — Cycle 2 exact-package full raw |
| 32 | `purchase-success-inventory-collection` | Clarify collection versus plant-instance result; update balance immediately without replay or large layout shift. | Dashboard | Not run (full only) | Accepted — Cycle 2 exact-package full raw |
| 33 | `growth-charge-use-ready` | Remove duplicate result/transition copy; preserve engine preview/commit parity and multi-transition handling. | Dashboard | Recapture required | Accepted — Cycle 2 exact-package full raw |
| 34 | `growth-charge-success-stage-reward` | Add Before/After treatment, increase progress contrast, hide absent reward section, and prevent reapplication. | Dashboard | Not run (full only) | Accepted — Cycle 2 exact-package full raw |

## Regeneration record

| Cycle | Production SHA-256 | Representative | Full | Raw review | Sheet review | Open blockers |
| --- | --- | --- | --- | --- | --- | --- |
| Baseline 2.1.0 | `0f498f043a6a66c56114b2595df0e6ae1207cc747e92bde3ed149ec53cccf1cb` | Frozen | `34/34` frozen | Reviewed as input | `5/5` reviewed as input | R01-R08 |
| 1 | `44e45f675f16a769567e05c019d8bd5ebeaad723c55ef965d1bda550022db477` | `7/18` accepted from 12 raws; package parity and clean shutdown passed; runner exit 1 (`review-required`) | Not run | Complete for all 12 raws | Not generated (`0` sheets; no evidence ZIP) | Incomplete diagnostic cycle; superseded by Cycle 2. |
| 2 | `f782d6b58ddd682bc92cacea4f28de44caf481a7e2e1e39a1bb44d558dda8971` | `capture-sequence-20260831-154002`: `18/18` raw-valid exact-package preflight; parity and clean shutdown passed; sheets intentionally deferred. | `capture-sequence-20260831-155312`: `34/34`, valid, complete, exact-package parity and clean shutdown passed. | `18/18` representative and `34/34` full raws reviewed and accepted. | `5/5` full sheets reviewed and accepted. | Zero automated blockers or advisories; independent acceptance gates remain open. |

**Complete regeneration-cycle count: 1.** Cycle 2 is the only complete
regeneration cycle for the integrated 2.2.0 candidate. The frozen baseline,
incomplete Cycle 1, and targeted/raw-review probes do not increment this count.

### Cycle 2 diagnostic native probes

These targeted or sheet-deferred probes all ended with
`capture_complete: false` and zero contact sheets. Their status was either
`review-required` or `raw-review-ready`; clean shutdown passed. They are
diagnostic/incomplete runs within Cycle 2 verification and do not increment the
complete regeneration-cycle count.

| Probe | Production SHA-256 | Captured / requested | Recorded blocking result | Status |
| --- | --- | ---: | --- | --- |
| `capture-sequence-20260831-085008` | `117f7e6e06e34e5df5de56dd413a614de824e0b456a4811a06acadfad98c3f1f` | `12/18` | Progress Collection, Reviewer HUD, Session Summary, Sync Summary, reward dock, and Growth Charge replacement surfaces did not complete. | Diagnostic / incomplete; not a regeneration cycle |
| `capture-sequence-20260831-090755` | `13c3d39e5b520887360735421a54e6b55aa799bd1ab644326d42f75c513cef1c` | `14/18` | Progress Collection, Reviewer HUD, Session Summary, and Sync Summary remained incomplete after the targeted dependency probe. | Diagnostic / incomplete; not a regeneration cycle |
| `capture-sequence-20260831-092417` | `1158dac568b286e1380c2ff95ef186d02c7b3029809438c85f06e5ddf58b74b1` | `11/14` | Fertilizer active-plant identity/semantic audit; Progress Collection acceptance; HUD `1280x600-short-expanded`; Session `1280x720` collapsed audit; Sync subtitle `NameError`. | Diagnostic / incomplete; not a regeneration cycle |
| `capture-sequence-20260831-093726` | `3f8750ec3720d4eb4451d28abe5d8a974f661b01987cfbc787dabef53ecce85b` | `3/6` | Fertilizer active-plant identity/semantic audit; Progress Collection acceptance; HUD `1280x600-short-expanded`; Session `1280x720` collapsed audit; Sync nonmodal geometry. | Diagnostic / incomplete; not a regeneration cycle |
| `capture-sequence-20260831-094537` | `3ab1312cde3bfb4244ffd3e43246ab32af6de00aaa43a6765b83e40f491fad21` | `15/18` | Progress Collection acceptance; HUD `1280x600-short-expanded`; Session `1280x720` collapsed audit; Sync nonmodal geometry. | Diagnostic / incomplete; not a regeneration cycle |
| `capture-sequence-20260831-095846` | `9e4d8094e5301479832961293386e528192e15196fbe5bcd0b9e55cff898d430` | `1/6` | Growth fixture restore and cleanup raised `RewardLedgerCheckpointError`; later targets were not captured. | Diagnostic / incomplete; not a regeneration cycle |
| `capture-sequence-20260831-100411` | `9e4d8094e5301479832961293386e528192e15196fbe5bcd0b9e55cff898d430` | `9/12` | Progress Collection acceptance; HUD `1600x1000-expanded` did not settle; Session Retina collapsed audit reported 27 px default scroll; Sync nonmodal geometry. | Diagnostic / incomplete; not a regeneration cycle |
| `capture-sequence-20260831-101412` | `9965d92e5ccd60946a51317aa68da10ddd16e8633f9bb2f2612014f5df4faeaf` | `1/6` | Growth fixture restore and cleanup raised `RewardLedgerCheckpointError`; later targets were not captured. | Diagnostic / incomplete; not a regeneration cycle |
| `capture-sequence-20260831-101707` | `9965d92e5ccd60946a51317aa68da10ddd16e8633f9bb2f2612014f5df4faeaf` | `4/6` | HUD one-effect content state; Session sparse-zero omission predicates; Sync summary-copy semantic audit. | Diagnostic / incomplete; not a regeneration cycle |
| `capture-sequence-20260831-102313` | `9c26b6f3a7fcee77180ebfa55aa965a8ed35c8fc9cf971999e73a96bcfa28adb` | `2/4` | HUD canonical maximized state did not restore; Session long-name/six-digit-total predicate. | Diagnostic / incomplete; not a regeneration cycle |
| `capture-sequence-20260831-103551` | `935bebdeefdfc643a59f6a3663bee21c2b9ed1b5f5eea74d4c081eefbd528109` | `16/18` | Fertilizer Active and Reviewer HUD replacements did not complete; the other assembled surfaces passed. | Diagnostic / incomplete; not a regeneration cycle |
| `capture-sequence-20260831-125105` | `5e688cd5d16fd1fc39ad6210f4f7499fc9d7e50e2075f583d2efa5d5537f3f3e` | `17/18` | Session Summary did not complete; the other representative surfaces passed. | Diagnostic / incomplete; not a regeneration cycle |
| `capture-sequence-20260831-132635` | `62f2bc6930345b1271145c05a090a63fe41a28615a03e52dee68b69b155afb3e` | `17/18` | Session Summary did not complete after the exact-package representative attempt. | Diagnostic / incomplete; not a regeneration cycle |
| `capture-sequence-20260831-133025` | `62f2bc6930345b1271145c05a090a63fe41a28615a03e52dee68b69b155afb3e` | `17/18` | The targeted Session Summary replacement still did not complete. | Diagnostic / incomplete; not a regeneration cycle |
| `capture-sequence-20260831-133338` | `62f2bc6930345b1271145c05a090a63fe41a28615a03e52dee68b69b155afb3e` | `18/18` | All raw surface rows passed, but independent Reviewer HUD and Session Summary semantic predicates rejected the assembled set. | Diagnostic / incomplete; not a regeneration cycle |
| `capture-sequence-20260831-134500` | `62f2bc6930345b1271145c05a090a63fe41a28615a03e52dee68b69b155afb3e` | `31/34` | Progress Today’s Cards, Nursery Decorations and Scenery, and Growth Charge stage-reward acceptance did not complete. | Diagnostic / incomplete; not a regeneration cycle |
| `capture-sequence-20260831-135249` | `31df41f516fbbe52a4dcb5ccc5ffb3081240852295384b81bcd10056107dac52` | `18/18` | Representative raw set passed independently, but sheets were deferred and later source corrections superseded the package. | Raw-review-ready / incomplete; not a regeneration cycle |
| `capture-sequence-20260831-135758` | `31df41f516fbbe52a4dcb5ccc5ffb3081240852295384b81bcd10056107dac52` | `34/34` | Raw surfaces passed, but the standalone Streak first-fold scroll-owner predicate rejected the set; later source corrections superseded the package. | Diagnostic / incomplete; not a regeneration cycle |
| `capture-sequence-20260831-152405` | `4443f0ec66e9aca85fff5d638bb9dd73f0545a032f8f3e95c1dbc576ab2191e9` | `33/34` | Starter Placement did not capture; Move Mode fixed occupant identity but retained misaligned destination outlines. | Diagnostic / incomplete; not a regeneration cycle |
| `capture-sequence-20260831-152812` | `4443f0ec66e9aca85fff5d638bb9dd73f0545a032f8f3e95c1dbc576ab2191e9` | `34/34` | Raw validation passed with sheets deferred; Move Mode destination-outline visual correction remained pending. | Raw-review-ready / incomplete; not a regeneration cycle |
| `capture-sequence-20260831-154002` | `f782d6b58ddd682bc92cacea4f28de44caf481a7e2e1e39a1bb44d558dda8971` | `18/18` | Exact-package representative preflight passed raw validation, parity, and clean shutdown; sheets were intentionally deferred. | Accepted preflight / incomplete as a standalone regeneration cycle |
| `capture-sequence-20260831-154414` | `f782d6b58ddd682bc92cacea4f28de44caf481a7e2e1e39a1bb44d558dda8971` | `34/34` | Exact-package full raw set passed validation and final Move Mode contour review; sheets were deferred for the reviewed final assembly. | Accepted raw source / incomplete as a standalone regeneration cycle |

## Cycle 1 consolidated correction batch

Cycle 1 is diagnostic evidence only. It did not produce a complete manifest,
contact sheets, or an evidence archive, and it does not change the candidate's
`review-required` status. The following corrections were applied as one batch
and verified in the final Cycle 2 evidence.

| ID | Cycle 1 finding | Correction in the single batch | Status |
| --- | --- | --- | --- |
| C1-01 | The shared Garden header clipped Growth and plant-stage text on the `plant-at-every-stage` and `selected-plant-nurtured` raws. | Increased the compact metric-cell allowance and kept wide metrics horizontal while compact layouts stack. | Verified in Cycle 2 |
| C1-02 | Garden Appearance values on the accepted `collection-loadout-detail` raw used oversized summary typography instead of a compact definition-list hierarchy. | Added a compact appearance-value role with restrained type size and weight. | Verified in Cycle 2 |
| C1-03 | Fertilizer capture checks still asserted legacy timed behavior and the retired 500-Growth Sprout threshold. | Bound the fixture and validator to the production card-counted batch, 400-Growth threshold, cards remaining, and `Queue` action. | Verified in Cycle 2 |
| C1-04 | Collection capture setup used the compatibility registry and produced the retired 30/93 metric. | Switched capture projections to the canonical 39-entry Collection authority. | Verified in Cycle 2 |
| C1-05 | Nursery capture copy and accessibility checks expected `Buy and apply` and the obsolete Magical-only tab name. | Normalized the player-facing tab to `Fertilizers and boosts`, its catalog accessibility name, and the result-specific `Use` action. | Verified in Cycle 2 |
| C1-06 | Settings validation omitted the active Garden Bonus effect from the expected row. | Made the check consume the complete active-bonus name and effect presentation. | Verified in Cycle 2 |
| C1-07 | Reviewer HUD capture raised a packaged `HUD_TOP_MARGIN` name error, cascading into reviewer reward evidence. | Imported the shared HUD margin constant and retained bounded reviewer geometry. | Verified in Cycle 2 |
| C1-08 | Session Summary lacked deterministic home-clearance defaults when opened through the capture path. | Initialized the clearance properties before layout and retained the existing committed-result projection. | Verified in Cycle 2 |
| C1-09 | Sync Summary used unstable singular discovery grammar in the one-item fixture. | Made the compact metric label consistently read `Garden discoveries`. | Verified in Cycle 2 |
| C1-10 | Growth Charge fixtures still modeled 500 Growth and duplicated the obsolete before/after values. | Aligned preview and committed capture evidence to 350→450 across the frozen 400-Growth Sprout threshold, with 50/1,600 stage-relative Growth. | Verified in Cycle 2 |
| C1-11 | The full-only Fertilizer queue fixture still modeled a four-hour timed dose. | Replaced it with a 100-card Basic batch followed by a queued 400-card Magical batch, with no expiry timestamp. | Verified in Cycle 2 |

## Final 2.2.0 evidence binding

- Production archive: [`dist/anki_garden.ankiaddon`](dist/anki_garden.ankiaddon),
  100,389,172 bytes, SHA-256
  `f782d6b58ddd682bc92cacea4f28de44caf481a7e2e1e39a1bb44d558dda8971`.
- Capture derivative: 100,781,416 bytes, SHA-256
  `c57848064ee03db9a84454df0a434b3bc68da857a197b2d392e4b135a8618afd`;
  its 321 shared payload entries are byte-identical to production with shared
  payload SHA-256
  `848e953fc3dbeddae2bc6ed67ee7114710ce21e0c93002b8ec640be26816a964`.
- Exact-package representative preflight:
  [`capture-sequence-20260831-154002`](build/ui-face-captures/representative/capture-sequence-20260831-154002),
  with `18/18` raw surfaces valid and reviewed.
- Final full run:
  [`capture-sequence-20260831-155312`](build/ui-face-captures/full/capture-sequence-20260831-155312),
  including the
  [manifest](build/ui-face-captures/full/capture-sequence-20260831-155312/assembled/manifest.json),
  [capture report](build/ui-face-captures/full/capture-sequence-20260831-155312/capture-report.json),
  [attempt-log index](build/ui-face-captures/full/capture-sequence-20260831-155312/attempt-log-index.json),
  and `34/34` accepted original-resolution raw PNGs.
- Final five-page presentation set:
  [contact-sheet index](build/ui-face-captures/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260831-155312/contact-sheet-set.json),
  with `5/5` sheets reviewed and accepted.
- Evidence archive:
  [`anki-garden-ui-faces-20260831-155312.zip`](build/ui-face-captures/full/anki-garden-ui-faces-20260831-155312.zip),
  26,126,453 bytes, SHA-256
  `8094c23a051c2d5e49d96d4f4f118160b791a94f7cfe8bd5b691d12a1593b8d3`.

The final full report records capture contract v26, package version 2.2.0,
100% scale on the primary display, exact production/capture shared-payload
parity, a passed clean-shutdown gate, `34/34` valid surfaces, zero text-layout
warnings, and zero automated blockers or advisories. The automated release gate
passed, but the report intentionally remains `quality_status: review-required`
and `release_ready: false`.

## Changed-test and remaining-acceptance summary

No new UI test files were created. The single complete union reported
**2,311 passed, 35 skipped, and 3 failed**. Those exact three closest existing
test nodes were then corrected in place for the final behavior and their
focused rerun passed; the complete union was not repeated.

The final exact-package automation, native macOS capture, raw review, and sheet
review do not close independent human approval, native Windows or Linux,
125%/150% or mixed-DPI behavior, broader keyboard use, screen-reader behavior,
contrast and forced-colors review, or device-level visual acceptance. Those
gates remain open; this ledger does not authorize publication.
