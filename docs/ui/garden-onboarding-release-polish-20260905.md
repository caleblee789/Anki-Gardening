# Garden and onboarding UI polish — Sheet 1

Implemented the approved changes for the 12 Garden/onboarding surfaces. The footer retains its **Nurtured** badge beside the current plant name, as explicitly requested. Final visual review uses the normal **1040 × 720** Garden window; no further small-window testing is part of this handoff.

| Surface | Resolution |
| --- | --- |
| Starter Deck Browser Home | Retained its existing Anki layout and garden framing. The single action leads into the first-plant selector. Final native review includes title, helper, button and background fit. |
| Garden Starter Picker | Bounded selector directly below navigation, with four consistent cards at normal size. Removed the oversized top gap after the user reviewed the centered version. Removed the empty reserved selection row; protected the 164 px artwork region against stylesheet collapse. Preview controls use concise stage labels. |
| Garden Starter Selected | Inset checkmark and selected border use the same card geometry. Selecting a card only changes local selection; **Choose a bed** performs the existing engine action. Preview arrows never select or commit a plant. |
| Garden Starter Placement | One clear **Plant here** action, a concise **Bed 1** destination label, restrained eligible-bed highlights and the same cancel/back behavior. |
| Starter Awaiting Nurture | The plant is planted before it is nurtured. Both the engine feedback and success receipt now say “Bonsai planted.” The footer says “Choose Nurture to start growing.” Closing the inspector leaves a **View plant** recovery action. |
| Welcome Settled | Short greeting and one sentence, with optional **View rewards** disclosure. The existing nonmodal first-visit behavior and committed reward accounting remain. |
| Welcome Rewards Expanded | Welcome gift and past-study rewards use consistent vertical artwork rows. Past-study copy gives the actual review count. Removed the empty trailing stretch; only optional reward details can scroll. |
| Garden Overview | Replaced the default native backdrop's baked horizontal lawn bands with continuous grass. Kept the original Home background. Ground anchors, plant dimensions, species/stage assets and shadow geometry remain authoritative. Native lighting now applies its bounded contrast field. |
| Nurtured Plant Inspector | Preserved the compact floating inspector and its distinct role. Footer identity stays tied to the actual nurtured plant, with Nurtured badge, Growth progress and View plant. |
| Available Plant Inspector | Inspecting another plant does not change which plant earns Growth. Nurture remains an explicit action. Existing canonical species/stage naming and supplies navigation are shared with the other implementation lanes. |
| Move Plant | Instruction now reads “Choose an empty bed or a plant to swap with.” Eligible bed accents are subdued, and accents are clipped behind foreground artwork. Inactive footer actions are visually quiet. |
| Decoration Inspector | Uses the actual item name, shared concise bonus description, and an obtained date only when recorded. Added an explicit close control and a genuinely transparent rounded backing. Placement prioritizes keeping the selected decoration and plants visible. |

The starter group's width no longer inherits a four-column minimum that can exceed its scroll viewport on first open. This fixes first-load clipping without increasing type sizes. The footer measures 68 px in the observed normal layout, and keeps the badge adjacent to its name rather than stretching them apart.

True modal dialogs use a workspace scrim; nonmodal Garden inspectors and welcome cards retain their existing interaction model. The Settings/Progress lane independently reviewed the scrim in its native captures.

## Implementation boundaries

Primary files: `ui/dashboard.py` (starter cards/selector, NurturedPlantBar, modal scrim, onboarding and move copy), `ui/scene.py`, `ui/plant_display.py`, `ui/decoration_card.py`, `ui/welcome.py`, `ui/copy.py`, and the default background entry in `assets/manifest.json`. `game.py` changes only the two starter success strings; rewards, persistence, inventory, timing and progression are unchanged.

The shared repository contains concurrent Sheet 2–5 work. Do not restore the entire frozen dashboard or capture runtime over newer work. Collection owns the merged plant/appearance routes; Shop owns supplies and charge actions; Progress owns its mounted pages and Settings; Reviewer owns its HUD and reward feedback.

## Artwork provenance

New file: `ankigarden/assets/v6_storybook_gouache/backgrounds/verdant_twilight/soil_master/verdant_twilight_garden_continuous.png` (1448 × 1086).

Generated with the built-in ImageGen editor from the existing default backdrop. Editing direction: remove only the two painted horizontal lawn bands while preserving the twilight composition, buildings, sky, path, palette and edge foliage. Inspected the generated result before installing it. The manifest's `native_garden_file` override is consumed only by the native dashboard renderer. Original botanical images, original background and Home framing remain available and unchanged by this lane.

Full provenance: `build/sheet1-ui-polish/background-provenance.json`.

## Verification

- Existing focused Garden/asset/inspection checks: **271 passed, 18 skipped** (`build/sheet1-ui-polish/sheet1-tests.log`). This run preceded the instruction to stop small-window testing.
- After the final success-copy change, existing engine-only onboarding checks: **21 passed** (`build/sheet1-ui-polish/onboarding-engine-tests.log`).
- Reused existing tests; no new repository test files or broad accessibility test project.
- Final normal-size native review: **12/12 requested surfaces passed**, zero text-layout warnings and no recaptures required. Both inspected beds fit without clipping or scroll overflow and leave their selected plants visible. The Nurtured footer remains 68 px high.

## Final evidence and release boundary

Final frozen source: `build/sheet1-ui-polish/snapshot-04`. Anki 26.8.1, primary display, capture scale 100 percent. All final Garden frames use 1040 × 720; the Home frame retains its normal Anki window. No additional small-window testing was performed after the user changed that scope.

- [Native manifest](../../build/sheet1-ui-polish/capture-04/20260905-234620/manifest.json)
- [Per-surface validation](../../build/sheet1-ui-polish/capture-04/surface-validation.json)
- [Visual review and PNG hashes](../../build/sheet1-ui-polish/capture-04/visual-review.json)
- [Inspector layout audit](../../build/sheet1-ui-polish/capture-04/20260905-234620/plant-menu-layouts/layout-audit.json)
- [Package parity](../../build/sheet1-ui-polish/capture-04/package-derivative.json)
- [Starter picker with the top gap removed](../../build/sheet1-ui-polish/capture-04/20260905-234620/02-garden-starter-picker.png)
- [Garden footer with Nurtured badge](../../build/sheet1-ui-polish/capture-04/20260905-234620/05-garden-overview.png)

Production SHA-256: `ec02268dd1ec638d85f52caf44f4b82079ed0315d17de97288999ae0447ebe1b`.

Capture SHA-256: `d8b02189a32cc4bbcd0e384bd5ca7ee99a5aafdfa8a2cf3ccc23ae264267cf4c`. All 329 shared production/capture entries are byte-identical. Owned dashboard nodes also match the current worktree.

Disposable base: `/private/tmp/anki-release-qa.v1l_cno7`. Instance-key fingerprint: `23a392b43942`. Isolation checks passed, sync remained disconnected, and Anki exited gracefully.

The overall capture report deliberately remains incomplete: this Sheet 1 subset does not include the four required scrolling-list states from the other surfaces. Its per-surface records all pass. Preserve that global gate for the combined release run; do not change the manifest to claim completion or generate a final release contact-sheet set from this subset. Other lanes still have user-directed follow-up work. Final integration must use the then-current surface inventory and one frozen combined package. No public release, installation into the normal profile, or human release approval is claimed.
