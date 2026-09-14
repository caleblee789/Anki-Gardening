# Publication handoff — drafts only

The repository remains private until the owner chooses to release it. This is intentional. Nothing in this launch kit authorizes publication, an AnkiWeb listing, a Reddit post, or a Codex for Open Source application.

## Prepared files

- `PREVIEW.html`: review the AnkiWeb listing and the same Reddit post for all three communities locally.
- `ANKIWEB_TITLE.txt` and `ANKIWEB.html`: listing title and description fragment. `ANKIWEB.md` is the editable source; the plain-text version contains the same copy.
- `REDDIT_TITLE.txt` and `REDDIT.md`: one shared title and body for r/Anki, r/medicalschoolanki, and r/GetStudying. The preview reads this same source for every destination, so the posts stay identical.
- `media/anki-garden-demo.mp4`: the new 26-second edit for a native Reddit attachment. The reviewer GIF and short MP4 are refreshed from the same current HUD recording. The original poster and Dahlia growth GIF are retained unchanged.
- `manifest.json`: media hashes, draft titles, launch status, and an empty traction record. Record observations here instead of creating another tracking document.

## Demo provenance and acceptance

The 26-second demonstration reuses the existing concept and Dahlia growth animation, with fresh native Anki 26.08.1 footage of the current package. It shows a real answer and stage transition, compact reviewing, the current reward history, the garden, and the plant shop. Waiting time between actions is cut out; reward and UI animations within the native clips run at their real speed. Close-ups show the current HUD clearly, including its single-line “Items & finds” label. The final five seconds retain the existing Dahlia GIF at twice its original speed. No explanatory overlays or end card are added.

The reviewer showcase GIF and MP4 are a tighter 10-second edit of the same current HUD footage. The README and AnkiWeb use the same updated GIF. The original assets are retained in the local evidence folder for comparison.

The disposable garden starts near a growth milestone. The rare reward-history segment is explicitly prepared using current reward definitions and artwork: Garden Treasury and Root Core are Exceptional finds; Rich Compost is Rare. It does not show typical reward frequency, and the plant-stage montage is not real-time growth. No production reward rate, progression value, or gameplay code was changed to make the footage. Keep this short disclosure in the post copy. No learning or retention benefit has been established for Garden itself.

The installed production payload matched the exact Windows/macOS-tested archive before and after capture. Recording used a fresh, logged-out, sync-disabled profile; the normal Anki collection was untouched. Technical decoding and editorial inspection do not constitute the owner's visual approval. Provenance and clip timings are in `build/release-launch-20260913/video-evidence.json`. Recap export was deferred by its separate task and is excluded from this release.

## Remaining launch checks

| Item | Completion condition |
| --- | --- |
| Final package | Complete the remaining persistence, sync, UI and responsiveness checks; retain the exact archive hash. The current runtime matches the Windows/macOS-tested archive and excludes deferred recap export. The existing release hold stays in force until acceptance is complete. |
| Hosted checks | GitHub currently refuses to start jobs because of the account's billing/spending restriction. The owner must resolve the account restriction, then rerun checks on the chosen release commit. A job that never starts is not evidence of a code failure. |
| First use | Observe five real volunteers using a disposable or backed-up collection. Record installation, first plant, Nurture, first answer, first visible Growth, finding the garden again, and any confusion or assistance. Confirm that they understand desktop-only UI and local Garden storage. Fix observed blockers and repeat only affected steps. No volunteer results have been collected. |
| Compatibility copy | Preserve the stated test scope until release acceptance is complete. Do not turn scoped macOS or Windows results into a blanket cross-platform claim; Linux is unverified. |
| Public links | At the authorized release, make source and issue links accessible, assign the real AnkiWeb code, replace `{{ANKIWEB_CODE}}`, and verify a clean download/install. GitHub links in these drafts are intended for that public release. |
| Media URLs | AnkiWeb images use relative paths for local review. Replace them with working public media URLs in every listing format at publication; verify the editor's rendering. |
| Community rules | Recheck each community immediately before posting. Prior r/Anki guidance requested price/license information, direct project links, AI-development disclosure, and no spam. Do not infer approval for other communities or post identical copies simultaneously. |
| Owner approval | Review the exact package, edited demo, and final copy. Public release and application submission remain separate owner decisions. |

## Publication and traction

Once the owner requests release and the gates pass: make the repository public, publish the verified package and release notes, publish the AnkiWeb listing, insert its assigned code, and verify installation before posting. Start with r/Anki; use the same post for r/medicalschoolanki and r/GetStudying where current rules permit and after addressing early installation problems. Keep time available to answer reports and ship confirmed fixes.

Use the existing bug-report form and **Copy support report** in Garden settings. Ask people to review the report before sharing it. Do not request collections, card contents, credentials, or patient information.

Record actual source/date/download counts, confirmed installations, voluntary day-seven follow-up cohort size and responses, continued use, organic shares, issues, and fixes in `manifest.json`. Downloads do not equal unique users. Report denominators and response rates; do not add telemetry or manufacture usage. A five-person first-use check finds usability problems and is not a retention study.

Two to four weeks after launch, assess whether the evidence supports an application. The [Codex for Open Source form](https://openai.com/form/codex-for-oss/) asks for a public project and maintainer context, with usage/ecosystem impact and maintenance needs relevant to selection. It publishes no guaranteed star threshold or acceptance probability. Use the user's real maintainer contributions, actual adoption, issues resolved, and a concrete explanation of how Codex supports ongoing work. Timing is a planning choice, not a program deadline.

## Licensing and prior preparation

The owner approved AGPL-3.0-or-later for code and CC BY 4.0 for project artwork to the extent of rights held. Existing license texts, attribution, and third-party exclusions remain authoritative. Source must accompany distribution under its terms; private development does not change distribution obligations. See [AnkiWeb terms](https://ankiweb.net/account/terms), [the sharing guide](https://addon-docs.ankiweb.net/sharing.html), and [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). No new legal or artwork-rights audit was performed.

The earlier launch-kit work added the README, supplied media, and approved licenses to private GitHub main. This update edits that existing material and adds the requested demonstration, with one shared Reddit post across all three communities. Historical preparation and test records remain intact. No public release, listing, Reddit submission, or application has been performed.
