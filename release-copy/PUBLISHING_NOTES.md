# Publication handoff — finalized drafts

The owner authorized publication of Anki Garden 2.2.0. Reddit remains draft-only.

## Prepared files

- `PREVIEW.html`: review the AnkiWeb listing and the single shared Reddit post locally.
- `ANKIWEB_TITLE.txt` and `ANKIWEB.html`: listing title and description fragment. `ANKIWEB.md` is the editable source; the plain-text version contains the same copy.
- `REDDIT_TITLE.txt` and `REDDIT.md`: one shared title and body intended for each approved Reddit destination. The preview shows that universal post once rather than duplicating it by community.
- `media/anki-garden-demo.mp4`: the 34.4-second native demonstration. `media/anki-garden-growth-stages.mp4` and its GIF present the existing ten-second Dahlia animation separately at its original speed.
- `media/anki-garden-reddit-lead.png`: image-generated composition of the owner-supplied garden poster and current expanded reviewer screenshot, used as the video thumbnail. The native expanded HUD frame remains in `media/anki-garden-expanded-hud.png`. The main demo and Dahlia growth video are embedded within each Reddit preview. The HTML video elements in `REDDIT.md` represent media placement; attach the referenced files in the Reddit editor when publishing.
- The AnkiWeb description embeds the main demonstration and separate Dahlia video, with visible playback links and linked images as fallbacks. The plain-text description keeps the playback links.
- `manifest.json`: media hashes, draft titles, launch status, and an empty traction record. Record observations here instead of creating another tracking document.

## Media placement at publication

In Reddit's desktop rich-text editor, insert the demo after the introduction and the Dahlia growth video after the paragraph introducing the ten plant species. Use the final lead image as the demo thumbnail where the editor supports a custom cover. Do not paste literal HTML video tags into Reddit; [Reddit's formatting help](https://support.reddithelp.com/hc/en-us/articles/205191185-How-do-I-format-my-comment-or-post) distinguishes its rich-text and Markdown editors. Preview the post in the actual destination before submitting, since media controls depend on the editor and community.

The [AnkiWeb upload editor](https://ankiweb.net/shared/upload) states that Markdown and basic HTML are supported; native video acceptance was not confirmed. Replace relative media paths with public URLs, then check the listing's rendering. If it removes the video element, use the final lead image linked to the main MP4 in that position and retain the playback link and Dahlia growth GIF. No public upload or test post was made to check this.

## Demo provenance and acceptance

The 34.4-second demonstration uses fresh native Anki 26.08.1 footage of the current package. Its continuous opening shows two expanded reviews, an expanded-HUD drag, collapse through the native control, two collapsed reviews, and a collapsed-HUD drag. The complete review window keeps fixed framing. The garden sequence hovers the house and greenhouse, then selects a plant. A quick tour shows the plant collection, Trophy Room, full plant shop with a short scroll, and scenery catalog, before revealing Halloween Garden, Full Moon Garden, and Celestial Eclipse. The Trophy Room uses a native still held for 1.8 seconds. Native actions retain their original speed. No explanatory overlays or end card are added.

The separate ten-second Dahlia video replaces the repetitive reviewer showcase in the posting previews. It reuses the existing six-stage animation at its original speed and is excluded from the main demo. The README's reviewer GIF uses the current continuous native footage; its existing Dahlia GIF remains unchanged.

The disposable footage uses prepared examples. The Shop shot temporarily has zero of ten species discovered so the complete catalog is available; the garden state is restored afterward. The rare reward history uses current definitions and artwork: Garden Treasury and Root Core are Exceptional finds; Rich Compost is Rare. The three scenery examples are prepared in the disposable inventory. These examples do not represent typical reward frequency, and the Dahlia montage is a stage showcase rather than real-time growth. No production reward rate, progression value, or gameplay code was changed. The owner requested removing this disclosure block from the Reddit body; this preparation record retains the provenance.

The installed production payload matched the exact Windows/macOS-tested archive before and after capture. Recording used a fresh, logged-out, sync-disabled profile; the normal Anki collection was untouched. Provenance and clip timings are in `build/release-launch-20260913/video-evidence.json`. Recap export was deferred by its separate task and is excluded from this release.

## Publication

The owner authorized the 2.2.0 GitHub release, public repository, and AnkiWeb listing.
Use the exact archive identified in `docs/README.md` and `manifest.json`.
The r/Anki post is to be saved as a draft for owner review.

## Publication and traction

Publication sequence: make the repository public, publish the verified package and release notes, publish the AnkiWeb listing, insert its assigned code, and verify installation before posting. Start with r/Anki; use the same post for r/medicalschoolanki and r/GetStudying where current rules permit and after addressing early installation problems. Keep time available to answer reports and ship confirmed fixes.

Use the existing bug-report form and **Copy support report** in Garden settings. Ask people to review the report before sharing it. Do not request collections, card contents, credentials, or patient information.

Record actual source/date/download counts, confirmed installations, voluntary day-seven follow-up cohort size and responses, continued use, organic shares, issues, and fixes in `manifest.json`. Downloads do not equal unique users. Report denominators and response rates; do not add telemetry or manufacture usage. A five-person first-use check finds usability problems and is not a retention study.

Two to four weeks after launch, assess whether the evidence supports an application. The [Codex for Open Source form](https://openai.com/form/codex-for-oss/) asks for a public project and maintainer context, with usage/ecosystem impact and maintenance needs relevant to selection. It publishes no guaranteed star threshold or acceptance probability. Use the user's real maintainer contributions, actual adoption, issues resolved, and a concrete explanation of how Codex supports ongoing work. Timing is a planning choice, not a program deadline.

## Licensing and prior preparation

The owner approved AGPL-3.0-or-later for code and CC BY 4.0 for project artwork to the extent of rights held. Existing license texts, attribution, and third-party exclusions remain authoritative. Source must accompany distribution under its terms; private development does not change distribution obligations. See [AnkiWeb terms](https://ankiweb.net/account/terms), [the sharing guide](https://addon-docs.ankiweb.net/sharing.html), and [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). No new legal or artwork-rights audit was performed.

The earlier launch-kit work added the README, supplied media, and approved licenses to private GitHub main. This update edits that existing material and adds the requested demonstration, with one shared Reddit post across all three communities. Historical preparation and test records remain intact. Publication status and URLs are recorded in `manifest.json`.
