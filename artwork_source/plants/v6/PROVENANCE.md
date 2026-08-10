# Verdant Twilight V6 plant-generation provenance

Last audited: 2026-08-10

This ledger covers the selected generation masters for the complete ten-line
V6 plant library. It records provenance only and does not make the machine-local
Codex session or generated-output directories part of the release artifact.

## Generation contract

- **Mode:** built-in ImageGen. Create Mature as a new image from its full text
  prompt, then use reference-image edits for every related stage. Use an
  independent text-only regeneration only after repeated reference-edit failure.
- **Medium and framing:** one isolated, direct-soil plant in polished storybook
  gouache, square canvas, centered bottom soil-contact anchor, clean silhouette,
  solid chroma-key background, and no pot, planter, mound, scenery, text, logo,
  or watermark.
- **Exact six-stage workflow:**
  1. Generate **Mature** as the line's new-image identity anchor.
  2. Edit Mature into **Young**.
  3. Edit Young into **Sprout**.
  4. Edit Sprout into **Seed**.
  5. Edit Mature into **Flowering**.
  6. Edit Flowering into **Rare**.

This branching is intentional: the juvenile chain steps backward from Mature,
while Flowering and Rare preserve the established adult identity.

## Chroma extraction

The canonical helper invocation and settings for the current pipeline are:

```sh
./.venv/bin/python /Users/test/.codex/skills/.system/imagegen/scripts/remove_chroma_key.py \
  --input artwork_source/plants/v6/{species}/{species}_{stage}_chroma.png \
  --out ankigarden/assets/v6_storybook_gouache/plants/{species}/{stage}/{species}_{stage}_twilight_v6.png \
  --auto-key border \
  --soft-matte \
  --transparent-threshold 12 \
  --opaque-threshold 220 \
  --despill \
  --force
```

The result must then satisfy the V6 transparent-canvas normalization and slot
geometry checks; chroma extraction alone is not visual approval.

ImageGen's raw outputs used a subtly graded magenta field even when prompted
for a mathematically flat key. The selected canonical source masters therefore
apply one content-preserving preparation step: pixels classified as fully
background by the same ImageGen chroma helper are rewritten to exact
`#FF00FF`, while every non-background plant/effect pixel is retained. Re-run or
verify this contract with:

```sh
./.venv/bin/python scripts/normalize_v6_chroma_sources.py --check
```

For edge-sensitive assets, the reviewed runtime pipeline uses connected hard
keying followed by pure-magenta soft despill, then premultiplied-alpha vertical
normalization where required. This preserves intentional plant colors and
prevents resampling from reintroducing a chroma fringe. The final Sunflower,
Foxglove, Wisteria, and Dahlia Seed runtimes use this path; selected adult
sprites with red, blue, or connected fine structure use it when the standard
automatic matte would remove botanical detail.

## Selected canonical names

- Source master:
  `artwork_source/plants/v6/{species}/{species}_{stage}_chroma.png`
- Runtime asset:
  `ankigarden/assets/v6_storybook_gouache/plants/{species}/{stage}/{species}_{stage}_twilight_v6.png`
- Stage slugs, in order: `seed`, `sprout`, `young`, `mature`, `flowering`,
  `rare`.
- Species slugs: `bonsai`, `rose`, `sunflower`, `lavender`, `hydrangea`,
  `peony`, `foxglove`, `japanese_maple`, `wisteria`, `dahlia`.

The unversioned `_chroma.png` files are the selected authoring masters in this
ledger. Revision and draft siblings are local generation evidence only: they
are excluded from source control and never alternate canonical names.
The installer records each selected unversioned master in `source_master_file`
and hashes that exact file in `source_master_sha256`; a missing canonical master
fails the catalog build rather than falling back to a legacy revision or runtime
sprite.

## Global Rare acceptance

Rare must remain the same species and keep the same bottom-center soil anchor.
Flowering is the natural botanical peak; Rare is its supernatural prestige
transformation. Rare must feel at least as full and visually dominant as
Flowering at the smallest Home size, while earning that dominance through a
structurally distinct silhouette, species-specific branching or botanical
detail, refined material/color, and restrained luminosity rather than mainly
through enlargement or a detached effect field. A shared presentation language
of subtle illumination, a small particle or falling-petal set, and an optional
tight root-contact glow may support the species-specific transformation.

For every completed line, Rare must:

- remain at or below 108% of Flowering's visible width and height and 115% of
  Flowering's visible area in every tested layout;
- retain at least 90% of Flowering's visible width and height and 88% of its
  visible area unless a reviewed asymmetric silhouette is demonstrably more
  dominant at Home scale;
- stay centered inside the slot envelope with no validation warnings;
- have a related but distinct scale/aspect-normalized primary silhouette, with
  silhouette IoU in the accepted `0.12..0.82` interval; and
- avoid a simple resize, palette swap, glow-only treatment, oversized aura,
  noisy particle field, or saturated effect that compromises chroma extraction.

## Standard stage semantics

- **Seed:** the species' actual seed, nutlet, samara, achene, or tuber; enlarged
  only as needed for Home readability, without reading as a decorative bud.
- **Sprout:** the first connected shoot with cotyledons or earliest species-
  appropriate leaves.
- **Young:** a recognizable juvenile with clearly developing stems, trunk, or
  branching, but still visibly below the adult form.
- **Mature:** the full foliage and branch framework with closed or developing
  buds only; no open peak blooms.
- **Flowering:** the natural, fully developed bloom payoff.
- **Rare:** a related but structurally distinct supernatural transformation.

## Evidence locations

Stage order for every six-item output list below is Seed, Sprout, Young, Mature,
Flowering, Rare.

- `S1`: exact built-in ImageGen prompt/call history at
  `/Users/test/.codex/sessions/2026/08/08/rollout-2026-08-08T23-41-21-019fe4d3-50fd-7cf1-b6c6-3a6940e244d3.jsonl`
- `S2`: Bonsai V3 Seed/Rare built-in ImageGen prompt/call history at
  `/Users/test/.codex/sessions/2026/08/09/rollout-2026-08-09T15-08-38-019fe824-43bd-7870-99e7-bdbf7a51afae.jsonl`
- `P1`: supplied baseline prompt pack at
  `/Users/test/.codex/attachments/535a2d9b-464c-4e2d-935d-d2961b3a305b/pasted-text.txt`
- `G1`: `/Users/test/.codex/generated_images/019fe4d3-50fd-7cf1-b6c6-3a6940e244d3/`
- `G2`: `/Users/test/.codex/generated_images/019fe824-43bd-7870-99e7-bdbf7a51afae/`
- `G3`: `/Users/test/.codex/generated_images/019fea22-b536-7763-a524-57428de451c2/`
- `G4`: `/Users/test/.codex/generated_images/019febeb-b676-7472-b91b-383cb4acae03/`

On 2026-08-10, SHA-256 comparison linked the selected pre-normalization images
to the listed built-in ImageGen outputs. Hydrangea Flowering was subsequently
revised from its original `G1` output by the repo-local prompt recorded in
`hydrangea/GENERATION_PROMPTS.md`; `G4` is the selected revision. The canonical
`_chroma.png` masters are the background-normalized derivatives described
above, so their whole-file hashes intentionally differ while the selected plant
content and output lineage remain unchanged. The runtime manifest records the
current canonical source hash for every stage.

### Completed lines

| Line | Final prompt evidence | Selected built-in output IDs |
| --- | --- | --- |
| Rose | Exact final prompts/calls in `S1`; no repo-local prompt ledger. | `G1/exec-4e6ff0e4-daad-437e-af56-c70262d00811.png`, `G1/exec-72da26ba-7ff4-41a6-8e05-94477813cbee.png`, `G1/exec-e2511830-efd4-48af-94ac-a8703af8ba72.png`, `G1/exec-665cc155-59fa-49eb-b11d-2123bb6e0ab5.png`, `G1/exec-a1a6fcbc-4b4f-4aac-b118-6217761d4675.png`, `G1/exec-6166e98b-36a7-4300-9256-1694e9aa58fd.png` |
| Bonsai | Repo-local base and revision prompts in `bonsai/GENERATION_PROMPTS.md`, `bonsai/GENERATION_PROMPTS_V2.md`, and `bonsai/GENERATION_PROMPTS_V3.md`; generation calls in `S1`, with the final V3 Seed/Rare calls in `S2`. | `G2/exec-822f6bce-fdc8-4500-b9a8-2d1e6a5a375f.png`, `G1/exec-4b0dd549-639d-43d6-9512-0f6933f3ee96.png`, `G1/exec-3f657c6c-4e6e-4a18-8fe2-31c256d3302c.png`, `G1/exec-48d4366d-903e-45cb-8e4a-6251d1dfc676.png`, `G1/exec-e06ee3b1-54f9-4634-acfc-00d8b91477f8.png`, `G2/exec-f44719c3-3a0f-4e76-9c0e-4da331b81271.png` |
| Sunflower | Exact baseline prompts in `P1`; exact selected generation and correction calls in `S1`; no repo-local prompt ledger. | `G1/exec-2d14cc76-1a47-459c-be45-4f8c089705b5.png`, `G1/exec-75107e5e-7181-4d0f-9cb9-4804c96cec4d.png`, `G1/exec-4fba72b0-11db-4b92-a85e-5261e4d2e24c.png`, `G1/exec-f3a3cd3b-181a-4002-8847-2b450fd249e4.png`, `G1/exec-04a1e232-3346-4f00-871c-b23bdfac1653.png`, `G1/exec-d6febecd-7d00-44c5-8d23-bf44b97307b1.png` |
| Lavender | Exact baseline prompts in `P1`; exact selected generation and correction calls in `S1`; no repo-local prompt ledger. | `G1/exec-b2c34cac-aa4f-4e83-b389-cdae2926b289.png`, `G1/exec-df8130e3-25b6-48bf-a820-171480b4b712.png`, `G1/exec-76245cc0-3f98-4d10-9025-53edb8ccc6f4.png`, `G1/exec-98654687-05c7-4e2c-ae06-020d78e3d522.png`, `G1/exec-7dbc12f9-2f2e-423d-ab2e-644606aa297d.png`, `G1/exec-459a3813-c528-47cb-a377-c82a472a38d9.png` |
| Hydrangea | Baseline prompts in `P1`, original calls in `S1`, and the selected Flowering revision prompt in `hydrangea/GENERATION_PROMPTS.md`. | `G1/exec-1374f652-f12c-4fea-b3cd-277c4b2c47f9.png`, `G1/exec-ca73e833-4bd4-4be9-932f-1452c9ace168.png`, `G1/exec-523f39a3-ef6d-4726-8ed9-dc2f6bb8a1f9.png`, `G1/exec-ce638753-a78b-4aca-af0c-fca9f28dc05a.png`, `G4/exec-d128f04f-6b38-4332-98cd-1bb8e538a7a2.png`, `G1/exec-e03398f0-24f8-46d4-a344-992abaf1dd2f.png` |
| Peony | Exact baseline prompts in `P1`; exact selected generation and correction calls in `S1`; no repo-local prompt ledger. | `G1/exec-7622c530-5aca-4e50-8480-58ca0be7065b.png`, `G1/exec-d65c62d4-743c-4cdf-8582-69d72cab811f.png`, `G1/exec-e480bf83-d391-45bd-81e3-85d47e47f4e0.png`, `G1/exec-e97405b5-03a2-4d1a-8183-719135ab0635.png`, `G1/exec-56154d90-592a-4668-9d2c-62acaac7858b.png`, `G1/exec-94c1aeda-02c8-45c2-b6ae-06b90dd33d09.png` |
| Foxglove | Exact baseline prompts in `P1`; exact selected generation and correction calls in `S1`; no repo-local prompt ledger. | `G1/exec-803c049f-e5a7-46d6-afe9-fc32e3453e30.png`, `G1/exec-0342ea35-9513-4eeb-9097-0e9c4d069e3e.png`, `G1/exec-7e6cb62d-17ea-4fbf-b388-7eaf40874648.png`, `G1/exec-8dfe5b30-c618-4002-901f-15fedfc42d8a.png`, `G1/exec-efafe0bc-11be-4321-836f-b734a974c952.png`, `G1/exec-fac21d6a-c60f-4922-a704-0ecd3b13a129.png` |
| Japanese Maple | Exact baseline prompts in `P1`; exact selected generation and correction calls in `S1`; no repo-local prompt ledger. | `G1/exec-3d7cf4f9-0f92-4093-9512-0f4ceb4b3bc1.png`, `G1/exec-81aa32b8-6da7-4ebf-a26d-50712d3d57d5.png`, `G1/exec-61bee647-0b85-4f6e-bd7c-fe57b081c303.png`, `G1/exec-81ce2f9b-aca1-457e-a6be-217bd5e7074f.png`, `G1/exec-08d843a4-5af8-4f98-9b46-2e221284bb29.png`, `G1/exec-21020cf3-58dd-4272-8e86-3e3451478faa.png` |
| Wisteria | Exact baseline prompts in `P1`; exact selected generation and correction calls in `S1`; no repo-local prompt ledger. | `G1/exec-f73a73b9-6684-4909-9689-9e7b06418e12.png`, `G1/exec-fb38952d-f07c-421c-b8f5-a7971c55ff8d.png`, `G1/exec-e3bbb072-a475-40d1-a9e4-2973eadaf48b.png`, `G1/exec-4f1a46b2-96a5-4c9a-aeab-27a326e1dcdc.png`, `G1/exec-f36549c4-cf01-4395-9d79-4907396ebe69.png`, `G1/exec-3e7ce98e-c759-4d0c-ab80-0e15791322f4.png` |
| Dahlia | Exact selected prompts and output IDs in `dahlia/GENERATION_PROMPTS.md`; baseline prompt pack in `P1`. | `G3/exec-528c737d-f060-4cc8-927b-3374fe73b4ac.png`, `G3/exec-c5441859-38ed-4d8e-8242-3075f88ca0c4.png`, `G3/exec-5addf065-4c3a-4954-88f1-9d62ba24904f.png`, `G3/exec-962e00af-b516-4af7-876b-445d10fc52c2.png`, `G3/exec-4edf09b5-8f99-4ae5-8f22-ef703cf06dae.png`, `G3/exec-f24eb2dd-687c-481e-8a73-213befd50c8d.png` |

## Known provenance gaps

- Bonsai and Dahlia have exact prompt text stored beside their source masters.
  The other eight lines rely on machine-local `S1` for their exact final or
  corrective prompts.
- `P1`, `S1`, `S2`, `G1`, `G2`, and `G3` are outside the repository and are not durable
  release provenance. The selected source masters preserve the final pixels,
  but not the complete prompt-to-output chain.
- There is no repo-local per-stage ledger containing both the final prompt and
  SHA-256 for Rose, Sunflower, Lavender, Peony, Foxglove, Japanese Maple, or
  Wisteria. Hydrangea's selected Flowering revision is recorded locally, but
  its other five stages still rely on `P1` and `S1`.
