# Anki Garden 2.2.0 UI release-quality review

This pass implements the 36-surface brief and the subsequent feedback about plant artwork, Collection copy, bonus controls, Stored Growth, and Landmark placement. The original contact sheets and all intermediate captures remain unchanged in `build/`.

## Shared changes

- The persistent Garden window has a 60-pixel header, four aligned main tabs, quieter secondary tabs, a clickable Coin balance, and stable name elision. Typography uses the shared 20/16/14/13/12-pixel roles with compact controls and consistent content gutters.
- Existing Garden backgrounds blend into the window at their decorative edges. Plant beds, plants, selection targets, and scene coordinates retain their gameplay behavior. The nurtured plant strip connects to the scene and links to Garden setup.
- Scenery, Decorations, and Landmarks share one preview and saved-equipment panel. Browsing tiles show concise effects; selected details retain complete conditions. Preview, appearance, visibility, today's bonus, scheduled bonus, and Landmark construction are separate states and actions.
- Scenery, Decoration, and Landmark headings are prominent. Visibility controls say **Show artwork**. There is no **Show preview** control. Upcoming changes appear under **Scheduled bonuses**, with actual local dates/times and separate cancellation actions. Repetitive ownership explanations and “next study day” wording are removed from the ordinary UI.
- **Coins**, **Growth**, stage-relative progress, cards, Garden Finds, and Garden discoveries use shared formatting and icons. Exact fractional Growth survives quote/outcome and sync presentation. Stored Growth has a prominent mint balance badge.
- Existing artwork is fitted by visual bounds and role. Starter cards combine large Mature artwork with clear seed thumbnails. The native plant chooser uses appropriately sized artwork, and small icons remain centered and legible.
- All six Landmark assets retain their original images, names, IDs, costs, and rewards. Per-item ground placement, ground-plane proportions, contact shadows, and scenery lighting integrate them into all nine backgrounds. No Landmark buff is implied.

The engine's existing recent-completion Growth bonus is correctly labelled **Garden Rhythm**. Anki streak rewards remain Coins. The brief's generic “streak bonus” example does not change those mechanics. Removing the preview toggle also supersedes the earlier compact-window proposal for a collapsible preview; the smaller window keeps a static preview and independent column scrolling.

## Disposition of the 36 reviewed surfaces

Every row was checked for artwork scale, text hierarchy and fit, spacing, alignment, controls, repeated copy, metric consistency, and unfinished styling. Ordinary scrolling and contact-sheet padding are not clipping defects.

| # | Surface | Implemented and reviewed result |
|---|---|---|
| 01 | Starter Home card | Compact title, readable shading, separate action, consistent plant metadata and progress. |
| 02 | Starter picker | Bounded centered onboarding, explicit Choose actions, large Mature art and seed thumbnails. |
| 03 | Starter selected | Same composition; returning from placement retains the selected tile. |
| 04 | Starter placement | Blended scene, compact instruction bar, clear selected bed, Back and Plant actions. |
| 05 | Garden overview | Refined four-tab header, blended perimeter, contextual nurtured-plant strip. |
| 06 | Nurtured inspector | Compact identity/progress/actions; selected bed remains visible and independent from nurturing. |
| 07 | Available inspector | Same spacing and pointer conventions, clear Nurture action, consistent artwork scale. |
| 08 | Move plant | Shared instruction treatment, distinct current/destination states, reachable swap/cancel controls. |
| 09 | Fertilizer supplies | Content-fitting dialog, aligned effect/duration/Owned columns, authoritative action labels. |
| 10 | Growth Charge supplies | Consistent item rows, fitted height and artwork, nearby Shop supplies action. |
| 11 | Collection Plants | Consistent five-column default grid, artwork containers, name/metadata baselines and discovery wording. |
| 12 | Plant-type details | Growth stages heading, concise explanation, aligned owned-plant row and stage-relative progress. |
| 13 | Plant details | Compact identity and Rename group, meaningful stage strip, tighter history and progress. |
| 14 | Collection Scenery | Shared preview/equipment panel, visible catalog bonuses, separate preview/apply and saved states. |
| 15 | Collection Decorations | Same panel and catalog hierarchy; appearance and active bonus sources are explicit. |
| 16 | Collection Landmarks | Prominent Stored Growth, separate construction/display roles, previews for unbuilt items, concise statuses. |
| 17 | Shop Plants | Bounded card widths, aligned artwork/name/View stages/price/action, intentional small assortment. |
| 18 | Shop Supplies | Clear target plant, stable row columns and category spacing, final item reachable. |
| 19 | Shop Scenery | Consistent image areas, aligned titles/effects/ownership/actions, complete bonus conditions. |
| 20 | Shop Decorations | Matching catalog structure; long effect descriptions wrap without displacing neighboring titles. |
| 21 | Fertilizer purchase | Shared dialog title and transaction rows, exact target/predecessor/price/balance, concise copy. |
| 22 | Growth Charge purchase | Consistent owned-count and balance changes, Coins terminology, no unnecessary gaps. |
| 23 | Purchase receipt | Rounded success banner without rectangular backing, separated actions, stable remaining card widths. |
| 24 | Today | Matching card/streak headings, accurate empty-versus-complete state, scoped totals and shared metrics. |
| 25 | Today details | Plain due-card explanation, concise Find-limit details, bonus management through Garden setup. |
| 26 | Achievements | Common gutters, section headings, title/date alignment, distinct status and reward treatments. |
| 27 | Coins | Coherent balance/activity section, gold Coin treatment, compact useful empty state. |
| 28 | Settings | Display/Rewards grouping, aligned switches, stable title/footer and staged Save/Cancel. |
| 29 | Artwork check | Consistent disclosure, compact result and actions, technical details contained in their section. |
| 30 | Active Home card | Long-name handling keeps the stage visible, consistent Growth progress, compact footprint. |
| 31 | Reviewer HUD | Preserved width, readable long names and plant art, canonical metrics, Next card wording. |
| 32 | Session summary | Sentence-case title, scoped card totals, Growth/Coins/Find order, consistent rewards and footer. |
| 33 | Sync summary | Matching metric hierarchy and icons, rounded outer shell, explicit syncing scope and concise heading. |
| 34 | Reviewer reward bundle | Reduced repeated outcome headings, clear reward amounts and Find rows, consistent session footer. |
| 35 | Growth Charge preview | Single plant identity, aligned transition art, exact Growth/quantity/progress and Stage reward on use. |
| 36 | Growth Charge success | Concise outcome headline, preserved transaction geometry, Stage reward earned and appropriate actions. |

## Supplemental native review

The representative capture also records:

- Unsaved scenery preview and reset without persisted changes.
- Different displayed artwork and active bonus sources, scheduled replacements, and independent cancellations.
- Expanded active and pending supplies, correct plant/duration, and Garden Rhythm.
- Failed saves retaining committed state and presenting inline recovery.
- Unbuilt Landmark previews, displayed Landmarks, bright scenery, and 860 × 580 layouts.
- Both ends of the full Scenery and Decoration catalogs, including long bonus conditions.
- Four plant-menu layouts across current/edge beds and the two supported window sizes.
- 540 plant artwork records: every one of the 60 plant-stage images in nine display roles, plus the actual native chooser.
- 66 Landmark screenshots: all six Landmarks in Garden and Collection at 1040 × 720 and 860 × 580, plus each in the other seven Garden sceneries. Placement uses actual painted bounds and nonempty bed regions; saved state is restored exactly.

The delegated Landmark review examined all 66 originals in pass 12. The final candidate repeats the same rendering code and full matrix. Its report and the independent visual review are preserved under the evidence root.

## Final evidence

The final production candidate is Anki Garden **2.2.0**, verified in disposable, sync-disabled Anki 26.08 profiles at the canonical 100% scale on the primary display. The normal Anki profile and supplied baseline evidence were not changed.

| Artifact | SHA-256 |
|---|---|
| [Production package](../../build/ui-release-quality-20260904-220713/candidate-final/anki_garden.ankiaddon) · 322 entries · 100,416,072 bytes | `e2970498b50434870bad148ffc6ad31dda587d8f62a369edfd9e12e286c96775` |
| [Representative capture derivative](../../build/ui-release-quality-20260904-220713/candidate-final/anki_garden_capture.ankiaddon) | `6cae4e3d77c91a92f10e8b562472f716e0367bdba5aa821b79371a9f5d32d595` |
| [Final capture derivative](../../build/ui-release-quality-20260904-220713/candidate-final/anki_garden_capture_final.ankiaddon) · 338 entries · 100,858,302 bytes | `af344fc288573680cd5c01026ff138a2966ef2b74d02bca1025320b27b3bda8d` |
| [Complete screenshot archive](../../build/ui-release-quality-20260904-220713/pass-17/full/anki-garden-ui-faces-20260905-022838.zip) | `6c04c40a2a2aa4b336717863172dd019f99ea525a0ec272759c1bc5d105feccb` |

The production archive and both derivatives have **321 byte-identical shared entries**. The expected mode-specific `build_capabilities.py` differs. The only change between representative and final capture code corrects a fixture from “1 card remaining” to “1 card left”; production code and gameplay are identical. See the [package comparison](../../build/ui-release-quality-20260904-220713/final-verification/garden-package-parity-final.json).

### Captures and visual review

- [Representative preflight report](../../build/ui-release-quality-20260904-220713/pass-16/representative/capture-sequence-20260905-021243/capture-report.json): **18/18 surfaces**, two sheets, all validators valid, no text-layout warnings or advisories, graceful shutdown passed.
- [Final full capture report](../../build/ui-release-quality-20260904-220713/pass-17/full/capture-sequence-20260905-022838/capture-report.json): **36/36 surfaces**, five sheets, surface/release/contact-sheet validators valid, **zero text-layout warnings and zero advisories**, graceful shutdown passed.
- [Final original screenshots and supplemental records](../../build/ui-release-quality-20260904-220713/pass-17/full/capture-sequence-20260905-022838/attempts/01-capture-session/20260905-023033/).
- [Final contact-sheet manifest](../../build/ui-release-quality-20260904-220713/pass-17/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260905-022838/contact-sheet-set.json).

| Contact sheet | Surfaces |
|---|---|
| [First run and Garden](../../build/ui-release-quality-20260904-220713/pass-17/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260905-022838/01-first-run-garden.png) | 01–10 |
| [Collection](../../build/ui-release-quality-20260904-220713/pass-17/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260905-022838/02-collection.png) | 11–16 |
| [Shop](../../build/ui-release-quality-20260904-220713/pass-17/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260905-022838/03-shop.png) | 17–23 |
| [Progress and Settings](../../build/ui-release-quality-20260904-220713/pass-17/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260905-022838/04-progress-and-settings.png) | 24–29 |
| [Anki and rewards](../../build/ui-release-quality-20260904-220713/pass-17/full/contact-sheets/anki-garden-ui-contact-sheet-2.2.0-20260905-022838/05-anki-and-rewards.png) | 30–36 |

All 36 pass-16 originals were inspected at readable size. The final refresh is pixel-identical on 33 surfaces; the other three were re-inspected at full size: the artwork-check timestamp, Home-card artwork within the Session summary capture, and the corrected reward-panel card text. All five final sheets were then reviewed together. The [pixel comparison](../../build/ui-release-quality-20260904-220713/final-verification/garden-final-pixel-comparison.json) preserves this relationship. No further obvious visual defects remained in the reviewed states. This is a recorded visual assessment, not a claim of certainty for every possible state.

The [Landmark agent report](../../build/ui-release-quality-20260904-220713/landmark-visual-audit-review.md) records the independent review of all six Landmarks across nine sceneries and the default/minimum layouts. The supplemental native audits cover preview/state independence, failures, long catalog text, plant menus, and artwork sizing described above.

Raw archives, original screenshots, logs, and package derivatives remain in the local ignored `build/` evidence directory. The [README overview image](../images/garden-overview-2.2.0.png) is tracked and copied from the final capture. Historical evidence has not been replaced.

### Verification and cleanup

The existing scoped suite passed with **1,569 passed, 21 skipped, and 822 deselected** in 153.22 seconds:

```bash
PYTHONPYCACHEPREFIX=/private/tmp/garden-ui-pyc .venv/bin/pytest -q -k 'not test_complete_release_manifest_matches_the_real_engine'
```

The final reviewer-header refinement additionally passed **79 existing tests** in `test_reviewer_hud.py`, `test_reward_bundle_projection.py`, and `test_capture_visual_acceptance.py`. These overlap the scoped suite and are not added to its count. Existing package checks and the asset audit passed; the asset audit covers nine backgrounds, eight cosmetics, eight garden features, six Landmarks, four Mastery images, 60 plant-stage images, and 19 UI assets. Logs are preserved in [final-verification](../../build/ui-release-quality-20260904-220713/final-verification/). No extensive new test matrix was introduced.

The final folder cleanup removed 57 generated Python cache files and one `.DS_Store` from `ankigarden/`, then removed empty cache directories. Saved garden state and `user_files/README.txt` hashes were unchanged. See the [cleanup record](../../build/ui-release-quality-20260904-220713/final-verification/cleanup.json). The README now explains setup, navigation, bonuses, supplies, and Landmarks in user-facing language; developer commands are in the [development guide](../development.md).

The [precommit verification](../../build/ui-release-quality-20260904-220713/final-verification/precommit-checks.json) confirms the final production and capture archives still match their source payloads, all new documentation links resolve locally, the add-on folder contains no generated cache clutter, and saved state remains unchanged. Implementation commit `2d6c9530adddc229444dca0385cc269342b3f72c` was pushed to `origin/main` and verified against the remote branch before completing the checklist below.


## Acceptance and completion checklist

- [x] Implement the complete UI brief and all subsequent copy, artwork, bonus-panel, and Landmark feedback.
- [x] Reuse and update existing focused checks; exercise state independence, transactions, timing, and failure recovery natively.
- [x] Review every final original and all five contact sheets together; correct and recapture remaining visible defects.
- [x] Record package identities, capture results, every surface's disposition, and remaining evidence limits.
- [x] **Last:** clean generated clutter from the add-on folder, finish the friendly user-facing README with minimal developer language, then integrate all changes into `main` and push `origin/main`.

The Codex visual review and automated/native checks are recorded separately from a person's public-release sign-off. Human release acceptance and a broader platform matrix are not claimed; the capture contract retains `quality_status: review-required` and `release_ready: false`. The annual 66-scenario economy simulation is outside this UI pass. It does not prevent the explicitly authorized source integration.
