# Character/character-scene.json — Scene from Character Sheet (Qwen-Image 2.1)

Draws **one finished scene** of a character that was designed with
`character-sheet-v2.json`. The four sheets it produced (three-view, expressions,
poses, costumes) go into the Qwen 2.1 encoder as reference images, together with
the same CHARACTER CARD text and a per-render SCENE prompt. No extra model:
`TextEncodeQwenImage21` natively takes up to 16 reference images and splices them
into the sequence (vision tokens + VAE reference latents).

Remote path: `workflows/Character/character-scene.json`
Local mirror: `flows/Character/character-scene.json`
Outputs: `Character/kailani/scenes/scene`, `…/scenes/scene_x2`

## Models

Same trio as the sheet flow (Qwen-Image 2.1 rule):
- UNet: `qwen-image-2.1-UC-Q8_0.gguf` (`UnetLoaderGGUF`).
- Text encoder: `qwen3vl_8b_ablit_int8.safetensors` (`CLIPLoader`, `qwen_image`, device `default`).
- VAE: `qwen_image_2.1_vae_bf16.safetensors`.
- Upscaler: `RealESRGAN_x4plus.pth` (photographic default; `anime_6B` for drawn cards).

No `TorchCompileModel`: reference-image sequences change length with every
reference/resolution change, which would force Dynamo recompiles.

## LoRAs

| Node | File | Strength | Trigger | Link |
|------|------|----------|---------|------|
| 4 | `Qwen-Image-2.1-viggle-turbo-v0.2.1-6step-lora-r128.safetensors` | 0 (bypassed placeholder) | — | — |

No LoRA is active. Slot 4 is the upgrade path for a trained character LoRA.

## Stage groups

| Group | Nodes | Bypassable |
|-------|-------|------------|
| 00 — MODELS | 1, 2, 3 | no |
| 01 — LORA STACK | 4 | yes (shipped bypassed) |
| CHARACTER CARD | 39 | no — **same text as the sheet flow; keep them in sync** |
| 02 — REFERENCE SHEETS, required | 11 `<image1>` three-view, 12 `<image2>` expressions, 15 resolution | no |
| 02b — POSE SHEET, optional | 13 LoadImage, 40 "Append — pose sheet sentence" | **yes, shipped bypassed** |
| 02c — COSTUME SHEET, optional | 14 LoadImage, 41 "Append — costume sheet sentence" | **yes, shipped bypassed** |
| 03 — SCENE PROMPT / ENCODE | 20 SCENE, 21/22 compose, 23 encoder | no |
| 04 — SAMPLER / DECODE / SAVE | 24 canvas, 6, 7, 8 | no |
| 06 — SUPERSCALING x2 | 30–34 (ESRGAN x4 → 0.5 lanczos) | yes (Ctrl-B the whole group) |

Prompt = CARD + scene template (node 21) [+ pose sentence (40)] [+ costume
sentence (41)] + `Scene: ` + SCENE (node 20). **Edit only node 20 per render** (and
node 39 for a different character).

### Optional reference sheets — how skipping works

The three-view and expression sheets are always used. The pose and costume sheets
each live in their own group, **shipped bypassed**. To use one, select its group and
press Ctrl-B, or use rgthree's Fast Groups Bypasser. Always toggle the **whole
group**, never only the `LoadImage`:
- A bypassed `LoadImage` has nothing to pass through, so its link into the encoder
  is dropped and the `images.image_N` slot stays empty. The sheet is not loaded or
  vision-encoded, and adds no time.
- The group's `StringConcatenate` (40/41) forwards `string_a` when bypassed, so the
  sentence about that sheet disappears from the prompt along with the image.

The encoder numbers the images it actually receives in slot order. The pose sheet is
always `<image3>` when present. The costume sheet is `<image4>` with poses on, but
`<image3>` with poses off. That is why node 41 calls it "the last reference image"
instead of using a tag. Template 21 names only `<image1>` and `<image2>`.

Measured 2026-10-02 (scene_00012, 768², both optional sheets off): **190 s**, vs
~350 s with all four sheets and ~46 s text-only. Mean brightness was 148.9, vs
57.5 for the dim four-sheet render `scene_00003`, so the pose/costume sheets may be
what darkens the output. That is one comparison, not a proven cause.

Needs `c-comfyui-mcp` with the 2026-10-02 bypass fixes when submitting through the
MCP. Older builds refused the dropped optional link ("hang off a muted/bypassed
node"), and with both groups off they silently cut the card and template out of
the prompt (chained bypass).

## Reference images

The four `LoadImage` nodes read copies in **`input/kailani/`**:

| Node | Value | Copied from `output/Character/kailani/v2/` |
|------|-------|-------------------------------------------|
| 11 `<image1>` (required) | `kailani/three-view.png` | `three-view_x2_00018_.png` |
| 12 `<image2>` (required) | `kailani/expressions.png` | `expressions_x2_00019_.png` |
| 13 pose sheet (optional) | `kailani/poses.png` | `poses_x2_00019_.png` |
| 14 costume sheet (optional) | `kailani/costumes.png` | `costumes_x2_00019_.png` |

Stock `LoadImage` lists only the top level of `input/`, and the frontend reports any
value that isn't a dropdown option as "The image for `<image1>` … couldn't be
loaded". The host therefore runs a small patch,
**`custom_nodes/input_subfolders.py`** (added 2026-10-02). It adds every image
under `input/<subfolder>/` to the dropdown as `<subfolder>/<file>` and registers no
nodes. If that file is removed, these four values show as missing again.

To use a newer sheet render, overwrite the copies (newest `_x2` of each panel):

```bash
ssh gaguilar@172.16.0.101 'cd ~/git/ComfyUI && for p in three-view expressions poses costumes; do \
  cp "$(ls -t output/Character/kailani/v2/${p}_x2_*.png | head -1)" input/kailani/${p}.png; done'
```

For another character, copy its sheets to `input/<name>/` and set the four nodes.

**Don't pick the sheets from the picker's generated/output list.** On frontend
1.53.6 it stores `name.png [output]` without the subfolder, so the backend can't
find the file. Its missing-media check for `[output]` values also only knows
outputs in the in-memory job history, which is cleared on restart. A typed full
path (`Character/kailani/v2/x.png [output]`) runs, but `/view` strips the
directory (`server.py` `os.path.basename`), so it never previews.

Use the individual `_x2` panels, not the stitched `sheet_x2`: each reference is
resized to about RESOLUTION² (node 15, 768), so a 2×2 sheet would give each panel a
quarter of the detail.

## Canvas layout rules

Laid out by script (2026-10-02) to these rules — keep them when adding nodes:
- No two nodes overlap (node box = body + 30px title bar).
- Every node sits ≥50px inside its group on all sides (below the group title on top).
- Groups are ≥50px apart on all sides (currently 100px).

Left→right: MODELS / LORA / CARD stacked · REFERENCE SHEETS / POSE / COSTUME stacked · SCENE PROMPT /
ENCODE · SAMPLER / DECODE / SAVE · SUPERSCALING.

## Resolution / sampler

- Scene canvas: **the encoder's own `latent` output (node 23 → KSampler
  `latent_image`)**, as rewired by the user on 2026-10-02. It takes the first
  reference's shape, which is square for the three-view sheet, so renders come out
  **768×768**. Node 24 `EmptyLatentImage` (1024×768) is still on the canvas but
  unconnected. Reconnect it to `latent_image` for a landscape canvas: `KSampler`
  converts an empty 4-ch latent to Qwen 2.1's 64-ch one
  (`comfy/sample.py fix_empty_latent_channels`), and the `qwen-image-size`
  validator warning about it is stale on 0.38.
- Reference resolution: 768 (node 15).
- Sampler: seed 424242 fixed, 30 steps, cfg 4.5, euler / simple, denoise 1.0.
- Delivery: x2 → 1536×1536 (2048×1536 with the node-24 canvas).

## Performance

The Qwen3-VL text encoder (node 2, device `default`) runs **on the GPU**: the log
shows `QwenImage21TEModel_` loaded completely into VRAM (9.5 GB). No node in this
flow runs on the CPU. Sampling is ~1.75 s/step (~55 s for 30 steps). The rest of
each run is the encoder vision-encoding every connected sheet, so time grows with
the number of sheets (all 2026-10-02):

| References | Time |
|---|---|
| none (text-only) | ~46 s |
| three-view + expressions (shipped) | 190 s |
| all four | 350 s |

Lower node 15 (e.g. 512) for faster iteration.

## Known issues / history

- **Don't add instructions to the template that name the reference sheets.**
  A sentence like "do not draw the prop standing beside the character as on the
  reference sheets" made the model paste the whole `<image1>` sheet (title and
  labels included) into the scene. This happened on both the 1024×768 and the
  square canvas. Bisected 2026-10-02: same SCENE and seed, template without that
  paragraph → clean (`bisect-A`), with it → sheet pasted (`bisect-B`). Fix
  duplicates and extra props **in SCENE** instead: say where the single prop is,
  and make background people visibly different.
- `<image1>` is copied very literally. Feeding the wrong sheet into node 11 (e.g.
  the costume sheet) reproduces that sheet's layout in the scene; the costume
  sheet's front/back outfit pair showed up on the beach in `scene_00014`.
- An artist-style signature sometimes appears in a corner even though
  "signature" is in the negative prompt.

- Needs `c-comfyui-mcp` with the autogrow fix (API keys `images.image_N`). Older
  builds collapsed them into a bare `images` key, which ComfyUI 0.38 silently
  treats as *no references* — the run "succeeds" text-only in ~46 s. If a render
  finishes that fast, the references did not reach the encoder.
- Text-only test render (`scene_00001_`) drew the character twice and invented a
  crop top; with the references (`scene_00003_`) she appears once, in the
  short-sleeved rash guard from the three-view.
- Rendering is moodier/painterly vs the sheets' flat cel shading under a golden-hour
  prompt; add "flat cel shading, clean line art" to SCENE if you want it closer.

## Art style lives only in the card (2026-10-05)

The fixed prompt text in this flow (templates, compose strings, negatives) never
names a style or medium: no "draw", "drawn", "illustration", "line weight", "flat",
"cinematic", "photorealistic". It only points at "the art style given above". The
card's `Art style:` line is the single place that decides drawing vs photograph.
Before this change the templates said "draw … drawn in the art style …" and
"consistent line weight", and a photographic card still came out as line art.

For a photographic character, say *photograph* plainly. The sheet layout is an
illustration-heavy concept, so a vague "realistic" will lose to it. For example:
`Art style: photorealistic photograph, real person, natural skin texture, DSLR studio photo, 85mm lens, soft diffused studio lighting. Not a drawing, not an illustration, not anime.`
Also change `Scope:` (e.g. `Live-action film`, not `Animation`).

The x4 upscaler is `RealESRGAN_x4plus.pth` (photographic default since 2026-10-05).
For a drawn card, switch the upscale loader back to `RealESRGAN_x4plus_anime_6B.pth`,
because the general model leaves halos on flat cel fills.

## Default card: photorealistic Kailani (2026-10-05)

The CHARACTER CARD now holds a **photorealistic** Kailani (`Scope: Live-action film`,
`Art style: photorealistic photograph …`), now a woman in her early twenties
(the original card said "teenage"). The original anime card is kept verbatim in the
**EXAMPLE CARD — Kailani, original anime** MarkdownNote, right under the card in the
same group. Copy it back into the card to render the drawn version, and switch the
upscaler to `anime_6B` too.

The scene's reference sheets (`input/kailani/*.png`) are still the **anime** sheets,
and the encoder copies references closely. With the photo card, re-render the
sheets with a sheet flow first and copy them over the four `LoadImage` inputs.
Otherwise the scene comes out drawn.
