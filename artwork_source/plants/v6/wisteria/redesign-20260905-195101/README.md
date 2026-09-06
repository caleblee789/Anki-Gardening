# Wisteria redesign handoff

The complete six-stage Wisteria line is installed in its existing runtime paths. The six canonical compatibility PNGs were also updated. The shared manifest and installer are ready for the coordinator to integrate using the supplied replacements and calibration.

The original Wisteria theme is retained: warm natural twisted bark, paired green leaflets and lilac hanging flowers. The new line improves early-stage vitality, soil contact, progression and the final crown. Full Bloom has a cascading flower curtain and natural bark; the old metallic trunk and detached particle ring are removed.

| Stage | Design change | Visible height relative to Flowering |
| --- | --- | --- |
| Seed | Compact bean, green hook, short connected root nub | 0.30 |
| Sprout | Sturdy green S-curve and three readable leaflet groups | 0.50 |
| Young | First woody twist, open branching crown | 0.82 |
| Mature | Broad layered green crown and small closed buds | 0.90 |
| Flowering | Separated lilac racemes with clear branch gaps | 1.00 |
| Full Bloom | Longer overlapping flower curtain and weeping crown | 1.05 |

Young was raised from the initial 0.70 target to satisfy the existing far-Home minimum readability check. Mature remains wider and denser. Every stage retains the original world soil anchor in all nine sceneries.

## Integration files

- [Six asset-ID-keyed replacement rows](</Users/test/Documents/Anki Gardening.nosync/build/wisteria-redesign/20260905-195101-final/manifest-replacements.json>)
- [Prior entry hashes](</Users/test/Documents/Anki Gardening.nosync/build/wisteria-redesign/20260905-195101-final/prior-entry-hashes.json>) — SHA-256 of each original row encoded as sorted-key compact JSON.
- [Original rows and runtime hashes](</Users/test/Documents/Anki Gardening.nosync/build/wisteria-redesign/20260905-195101-final/prior-entries.json>)
- [Species installer calibration](</Users/test/Documents/Anki Gardening.nosync/build/wisteria-redesign/20260905-195101-final/installer-calibration.json>)
- [Proposed installer patch](</Users/test/Documents/Anki Gardening.nosync/build/wisteria-redesign/20260905-195101-final/installer-proposed.patch>) — a proposal against the retained installer baseline, not applied to the shared file.
- [Installed file hashes](</Users/test/Documents/Anki Gardening.nosync/build/wisteria-redesign/20260905-195101-final/install-manifest.json>)
- [Source and export provenance](</Users/test/Documents/Anki Gardening.nosync/build/wisteria-redesign/20260905-195101-final/asset-provenance.json>)

Merge only the six Wisteria replacement rows by asset ID. Add the supplied Wisteria placement/source overrides to the central installer so a future metadata refresh preserves the reviewed geometry. Retain the current audited thumbnail calibration and the canonical internal `rare` stage ID. No catalog-wide installer was run in this task.

The final source archive is [redesign-20260905-195101](</Users/test/Documents/Anki Gardening.nosync/artwork_source/plants/v6/wisteria/redesign-20260905-195101>). It contains the six selected generated cyan masters, six normalized RGBA masters, prompts, prior runtime/source files and integration metadata. Re-export from the retained RGBA masters when exact alpha is required; the magenta PNGs are compatibility sources.

## Review and validation

- [Before and after line](</Users/test/Documents/Anki Gardening.nosync/build/wisteria-redesign/20260905-195101-final/before-after-line.png>)
- [Scenery sheet 1](</Users/test/Documents/Anki Gardening.nosync/build/wisteria-redesign/20260905-195101-final/contact-sheets/09-wisteria-page-1.png>) and [sheet 2](</Users/test/Documents/Anki Gardening.nosync/build/wisteria-redesign/20260905-195101-final/contact-sheets/09-wisteria-page-2.png>)
- [Native icon ladder at 1×](</Users/test/Documents/Anki Gardening.nosync/build/wisteria-redesign/20260905-195101-final/icon-review-1x.png>) and [2×](</Users/test/Documents/Anki Gardening.nosync/build/wisteria-redesign/20260905-195101-final/icon-review-2x.png>)
- [All six beds at Full Bloom](</Users/test/Documents/Anki Gardening.nosync/build/wisteria-redesign/20260905-195101-final/six-beds-full-bloom.png>)
- [Home overview](</Users/test/Documents/Anki Gardening.nosync/build/wisteria-redesign/20260905-195101-final/home-review.png>)
- [Native render manifest](</Users/test/Documents/Anki Gardening.nosync/build/wisteria-redesign/20260905-195101-final/render-manifest.json>) and [Home render manifest](</Users/test/Documents/Anki Gardening.nosync/build/wisteria-redesign/20260905-195101-final/home-render-manifest.json>)
- [Existing test output](</Users/test/Documents/Anki Gardening.nosync/build/wisteria-redesign/20260905-195101-final/pytest-wisteria.log>): **111 passed, 649 deselected**. No new test file was added.

The final frozen-source review includes 108 before/after native Qt crops (six stages × nine sceneries × two states), 324 planted-bed states, 336 native thumbnails at 14 sizes from 28–300 logical pixels and DPR 1/2, and 28 Home scene/card views at 340/800-pixel browser widths. The two large contact sheets preserve each native 880×680 crop without resampling. All native scene geometry checks passed.

Each runtime WebP is 1254×1254 lossless RGBA and decodes exactly to its retained normalized PNG. RGB-only edge cleanup reuses the repository's nearest-clean-edge repair with a detector matching the generated cyan matte, before and after normalization. Alpha and silhouettes are byte-identical to the first normalized pass, with zero remaining matches under the documented visible cyan-edge detector. See [edge cleanup](</Users/test/Documents/Anki Gardening.nosync/build/wisteria-redesign/20260905-195101-final/edge-cleanup.json>) and [alpha integrity](</Users/test/Documents/Anki Gardening.nosync/build/wisteria-redesign/20260905-195101-final/alpha-integrity.json>).

## Shared work handed to the coordinator

Scenery-specific lighting and lighting-cache identity, Garden/Home shadow parity, and native physical-size image prefiltering remain central renderer work. SmoothPixmapTransform alone produced little improvement; prefiltering to the physical draw size reduced harsh sampling. The controlled sampling probe is retained in the earlier 20260905-190548 run and is separate from the final evidence.

The frozen Home renderer heavily darkens the left plants and crops the front planting row at the wide card width. Compare [compact Home](</Users/test/Documents/Anki Gardening.nosync/build/wisteria-redesign/20260905-195101-final/home-cards/default-rotation-2-340.png>) and [wide Home](</Users/test/Documents/Anki Gardening.nosync/build/wisteria-redesign/20260905-195101-final/home-cards/default-rotation-2-800.png>). Species geometry was not distorted to compensate for that shared presentation behavior.

These are offscreen native Qt and disposable-browser render reviews. Live Anki window/profile QA, final integrated shared-renderer captures, human visual acceptance and release/package acceptance remain with the coordinator. No normal Anki profile was opened.

Earlier passes remain intact at the sibling 20260905-190548 and 20260905-195101 directories; this **20260905-195101-final** run is the final Wisteria handoff.
