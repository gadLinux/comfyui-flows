# Character/character-sheet-v2.json — Character Sheet Generator, TorchCompile

Same flow as `character-sheet.json` (v1) plus **`TorchCompileModel`** on the
diffusion model. Note: node ids differ from v1 for one node: here **RESOLUTION is
node 50** (49 is the compile node). Everything else is identical: models, character card, sheet
templates, sampler settings, stage groups, 512 native, x2 upscale, final 2×2 sheet.
**Read `character-sheet_README.md` for the full node map and usage.** This file
only documents the difference.

Remote path: `workflows/Character/character-sheet-v2.json`
Local mirror: `flows/Character/character-sheet-v2.json`
Outputs: `Character/kailani/v2/<panel>`, `…/v2/<panel>_x2`, `…/v2/sheet_x2`, kept
apart from v1's outputs so the two can be compared.

## Models

Same as v1:
- UNet: `qwen-image-2.1-UC-Q8_0.gguf` (`UnetLoaderGGUF`).
- Text encoder: `qwen3vl_8b_ablit_int8.safetensors` (`CLIPLoader`, `qwen_image`,
  **device `cpu`**, same NaN reason as v1).
- VAE: `qwen_image_2.1_vae_bf16.safetensors`.
- Upscaler: `RealESRGAN_x4plus.pth` (photographic default; `anime_6B` for drawn cards).

## LoRAs

Same as v1: node 4 is a bypassed, strength-0 placeholder. No LoRA is active.

## What v2 adds

| Node | Type | Setting | Wiring |
|------|------|---------|--------|
| 49 | `TorchCompileModel` | `backend: inductor` | LoRA slot 4 → **49** → all four KSamplers |

It compiles only the diffusion model (the UNet). The text encoder, VAE and ESRGAN
run uncompiled.

## Constraints (from the `comfyui-flow-authoring` skill, torch.compile on ROCm)

- The server must run with `--disable-comfy-compiler`; `~/git/start-comfy.sh 0`
  already passes it. Don't remove that flag while a `TorchCompileModel` node is in
  any flow.
- Works because the UNet is a **GGUF**. An int8 *safetensors* diffusion model
  (`qwen_image_2.1_int8_convrot`) breaks under compile (HIP int8 kernel is not
  traceable). Don't swap node 1 to that file in this flow.
- The **first run compiles**, which takes longer than an uncompiled run. The four
  prompts have different lengths, so Dynamo may recompile per sheet. Later runs
  with the same shapes reuse the compiled graphs until the server restarts.
- Bypass node 49 (Ctrl-B) to get plain v1 behaviour in this file.

## Stage groups, resolution, sampler

Identical to v1. See `character-sheet_README.md` sections "Stage groups",
"Resolution / sampler settings" and "06 — SUPERSCALING x2 + FINAL SHEET".

## Section labels (v2 only, 2026-10-02)

v2's expression, pose and costume templates (nodes 41, 42, 43) give every section a
**name label** instead of a number, the same way the three-view already labels
FRONT / SIDE / BACK VIEW. Each section line carries its grid position and label,
e.g. `Section 2 (top-middle, HAPPY): …`. The closing sentence lists the exact label
strings and says "No numbers anywhere on the sheet":

| Sheet | Labels |
|-------|--------|
| Expressions | NEUTRAL, HAPPY, SAD, ANGRY, EMBARRASSED, CONFUSED, SURPRISED, SMUG, SLEEPY |
| Poses | STANDING, WALKING, SITTING, RUNNING, THINKING, WAVING, POINTING, CELEBRATING, SIGNATURE ACTION |
| Costumes | DEFAULT OUTFIT, CASUAL, SPECIAL, NIGHTWEAR |

The labels stay character-neutral, so changing the card does not change them. v1
(`character-sheet.json`) is unchanged.

## 07 — 3D RECONSTRUCTION VIEWS (v2 only, 2026-10-02) — BYPASSED by default

Makes the four separate views that `3D/3d_pixal3d_multi_views.json` (Pixal3D)
needs: **front, left, back, right**, one image each, as RGBA PNGs.

**Shipped state:** every node in the group is `mode: 4`, and the group sits below
stages 02–05. A normal run doesn't change: the API prompt still has 43 nodes.
**To enable it:** select the group and press Ctrl-B (or use rgthree Fast Groups
Bypasser). To render only the views, also bypass 03, 04, 05 and 06. **02 THREE-VIEW
must stay on**, because its decoded sheet (node 7) is the identity reference for every view.

Per view (front 52–59, left 60–67, back 68–75, right 76–83):

| Node | Type | Setting / wiring |
|------|------|------------------|
| 52/60/68/76 | `StringConcatenate` | CHARACTER CARD (39) + character-neutral view template, `\n\n` |
| 53/61/69/77 | `TextEncodeQwenImage21` | ref: `images.image_1` = three-view sheet (7), which already shows front / side / back. `resolution` ← RESOLUTION (50) |
| 54/62/70/78 | `KSampler` | 424242 fixed, 30 steps, cfg 4.5, euler/simple, denoise 1; model ← **LoRA slot (4), not TorchCompile**. See the crash note below |
| 55/63/71/79 | `VAEDecode` | VAE (3) |
| 56/64/72/80 | `RemoveBackground` | BiRefNet (51) → foreground mask |
| 57/65/73/81 | `InvertMask` | needed: `JoinImageWithAlpha` treats 1 as *transparent* |
| 58/66/74/82 | `JoinImageWithAlpha` | RGB + mask → RGBA |
| 59/67/75/83 | `SaveImage` | `Character/kailani/v2/3d-views/<front\|left\|back\|right>` |
| 51 | `LoadBackgroundRemovalModel` | `birefnet.safetensors` (shared) |

What the templates ask for, chosen to match what Pixal3D expects (its fixed orbit rig, at azimuths 0/90/180/270):
- exactly one figure, whole body, centred, about 85% of the frame height, plain white
  background (BiRefNet cuts it to alpha), no text or labels, flat shadowless light,
  long lens / low perspective;
- **neutral A-pose** (arms about 30° from the body) and **no signature prop**, so
  limbs don't merge into the torso in the mesh;
- **left = the character's own left side** facing the camera (the figure faces
  screen-left); **right** is the mirror. This matches Pixal3D's `left` = azimuth 90°.

**Two things learned in QC (2026-10-02):**
- **Don't run reference-image renders through TorchCompile.** With 07's samplers on
  node 49, the first 3D sampler crashed with `hipErrorIllegalAddress` while Dynamo
  recompiled: reference latents change the sequence shape. The crash poisons the GPU
  context until ComfyUI restarts. The sheets (no references) still use compile.
- **Don't give side views the front view as a second reference.** With
  `image_2` = front, the LEFT view came back as a near-copy of the front (mean pixel
  difference 1.3/255, same silhouette width). Side and back views now get only the
  sheet, plus an explicit "this is NOT the front view" line.

Output size follows the first reference (the square three-view sheet), so views
come out square at RESOLUTION (512 test / 768 final). Pixal3D wants square inputs.

**Using them in the 3D flow:** that flow currently takes *one* turnaround sheet
and cuts it with four hard-coded `ImageCropV2` regions. To feed these views
instead, replace `LoadImage` (364) + the four `ImageCropV2` with four
`LoadImage` nodes (front/left/back/right) wired to the existing
`RemoveBackground` / `ImageCropToMask` (pad 1.1, 1024) chains. Copy the PNGs from
`output/Character/kailani/v2/3d-views/` to `input/` first (the LoadImage picker
doesn't list output subfolders).

Model added by this group: `background_removal/birefnet.safetensors`,
[download](https://huggingface.co/Comfy-Org/BiRefNet/resolve/main/background_removal/birefnet.safetensors)
([repo](https://huggingface.co/Comfy-Org/BiRefNet)). It's already on the host.

Canvas: the whole v2 canvas was re-laid out in the same pass (positions and group boxes
only), so it passes `canvas_check.py`. Before this, the CHARACTER CARD group touched
01–05, and the TorchCompile node (49) sat outside every group. It's now inside 00 MODELS.

## Benchmark vs v1

_Filled in from the first comparison run on the server; see below._

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
