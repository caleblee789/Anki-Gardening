# Publication handoff — drafts only

The README, its two media files, and the owner-approved license texts and notices are the only changes intended for GitHub in this task. Keep the repository private. Do not upload an add-on, create a GitHub release, publish an AnkiWeb listing, or post to Reddit without a later user request.

## Prepared files

- `PREVIEW.html`: local review of both posts, with the supplied poster, looping GIF, and MP4.
- `ANKIWEB_TITLE.txt` and `ANKIWEB.html`: listing title and description fragment. Markdown and plain-text alternatives contain the same copy.
- `REDDIT_TITLE.txt` and `REDDIT.md`: r/Anki title and post body.
- `media/anki-garden-review-hud.mp4`: lead Reddit demonstration; poster is an optional secondary visual.

The original combined preview and publishing instructions from the supplied ZIP were reference material, not authorization. These files supersede their assumptions about making the repository public.

## Remaining decisions and launch-only values

| Field | Current status |
| --- | --- |
| `{{ANKIWEB_CODE}}` | Not assigned or supplied. Appears only in Reddit's installation link and code. Do not create a listing just to obtain it during this task. |
| Source license | Owner approved AGPL-3.0-or-later. Full license and scope notice added to the repository and add-on source folder for future packaging. |
| Artwork license | Owner approved CC BY 4.0 for project artwork to the extent of rights held; third-party material and reference images remain excluded. Full text and attribution scope added. |
| Public support | Drafts invite questions and bug reports in the AnkiWeb listing / Reddit comments. No private GitHub Issues links or new external support accounts are needed. |

AnkiWeb description media currently uses relative local paths so the review copy works offline. Before a later authorized publication, upload the poster/GIF to a supported public media destination and replace both URLs in the listing variants. The development repository must stay private; do not use its raw GitHub URLs or authentication tokens as public media links. Reddit can use the supplied MP4 as a native attachment where supported.

The recorded preview environment is macOS with Anki 26.08.1. This is historical preview evidence, not a claim that the final release archive is verified. Update that sentence in all post variants after checking the final chosen package. Do not expand it to Windows/Linux or a version range without evidence.

The existing 2.2.0 release notes retain a release hold. This documentation task does not clear it. There were no GitHub releases when checked. No install code or public source availability was invented. The owner explicitly approved the recommended licensing during this task.

## Approved licensing and sources

AnkiWeb's Sharing Add-ons terms require AGPL3 or a compatible license. AGPL-3.0-or-later is the adopted code license, with source supplied under its terms when distributing. Repository visibility and licensing are separate: keeping the development repository private now does not waive source-distribution obligations when a package is released.

CC BY 4.0 permits copying and adaptation, including commercial reuse, with attribution. Apply it only to rights the owner actually holds; third-party assets need their own notices. No legal or asset-rights audit was performed here.

- [AnkiWeb terms](https://ankiweb.net/account/terms), Sharing Add-ons, read in the browser during this task.
- [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), checked during this task.
- [Current r/Anki rules](https://www.reddit.com/r/Anki/about/rules.json), checked during this task: state pricing and licensing, link directly to the project, disclose substantially AI-built work, and avoid spam. Recheck at posting time.
- [Anki add-on sharing guide](https://addon-docs.ankiweb.net/sharing.html).
- Current local `docs/pre-release-bug-testing-20260908.md`, `docs/reviewer-regression-fixes-20260909.md`, and `docs/ankihub-upload-reward-fix-20260909.md`: preview evidence only. Some of these files describe local changes not yet on GitHub.

## Media integrity

The poster, GIF, and MP4 were copied byte-for-byte from the supplied launch kit. No artwork, UI scale, frames, or timing were changed. The poster is promotional artwork. The reviewer clip is a showcase of several reward states rather than expected reward frequency; that disclosure is retained in both posts and the README. Compare the recording with the final released interface before publishing.

## Later publication sequence

After a separate release request: verify packaged license/source completeness, public media destinations, and the existing release hold, validate the chosen archive, review the AnkiWeb editor rendering, publish there first, then insert the assigned code and verify the download before submitting Reddit. Do not paste this handoff or the combined preview into either platform.

## Completed preparation checks

GitHub main now contains commit b3f6faef372d563c9dd2083f9d7255e26205ec4c, limited to the README, two media files, and license texts/notices. Repository privacy was rechecked after the push and remains PRIVATE. The remote README blob matches the prepared file. Existing local implementation changes and earlier unpublished code commits were not pushed.

README relative links resolve; documentation whitespace checks passed. The local browser preview rendered both post layouts, both images loaded, and the MP4 loaded with a 14.7-second duration and no media error. All three media files match the supplied kit byte-for-byte. The existing package file selector includes the license texts/notices; no add-on archive was rebuilt. No runtime tests were added or run for this documentation change. No AnkiWeb or Reddit post was submitted.
