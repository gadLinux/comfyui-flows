# Character/character-sheet.json — Character Sheet Generator

Generates a reusable **character reference sheet** (three-view turnaround, expression
sheet, pose sheet, costume sheet) for a virtual character you define once in a text
prompt, so that character can be rendered consistently across other flows.

Remote path: `workflows/Character/character-sheet.json`
Local mirror: `flows/Character/character-sheet.json`

Shipped example character: **Kailani**, an anime-style surfer girl (Animation scope).
Swap the prompt text for a different character, or duplicate this file, per the
"Usage" section below.

## Models

Per project rule: **Qwen-Image 2.1 model set, always** —
the same UNet + text encoder pairing as `common/qwen21-uc-models`, not the Flux
setup this flow originally shipped with.

| Role | File | Notes |
|------|------|-------|
| Diffusion (UNet) | `qwen-image-2.1-UC-Q8_0.gguf` (`UnetLoaderGGUF`) | Qwen-Image 2.1, Q8_0 GGUF. |
| Text encoder | `qwen3vl_8b_ablit_int8.safetensors` (`CLIPLoader`, type `qwen_image`, **device `cpu`**) | Qwen3-VL 8B text encoder, int8. |
| VAE | `qwen_image_2.1_vae_bf16.safetensors` | Decodes to **4 channels (RGBA)** — the sheets carry a real alpha channel, not just a painted-in transparent background. |

`TextEncodeQwenImage21` combines positive/negative encoding and the empty latent into
one node per panel — no separate `EmptyLatentImage`/guidance node needed the way the
Flux version required.

**Known limitation vs. the earlier Flux version**: `TextEncodeQwenImage21.resolution`
only produces a **square** canvas for pure txt2img (no reference image attached) —
confirmed by this server's own `qwen-image-size` validation module. All four panels
render at 512×512 as a result; the three-view sheet is no longer landscape and the
costume sheet no longer portrait. If non-square framing matters more than staying
on the mandated Qwen-Image path, the fix is attaching a same-aspect reference image
to shape the canvas — not swapping the base model back.

**Known risk**: this project's own `Character Flux/Ep28…` flows show Flux reliably
follows "grid layout, split image into N sections" prompts; Qwen-Image has not been
proven on multi-panel collages in this repo. QC the three-view panel first (Rule 2,
numerically) before trusting the 3×3 expression/pose grids.

## LoRAs

| # | Node | File | Strength | Status |
|---|------|------|----------|--------|
| 4 | PLACEHOLDER character LoRA slot | `Qwen-Image-2.1-viggle-turbo-v0.2.1-6step-lora-r128.safetensors` | 0 (off) | **Bypassed scaffold, not in effect and not needed.** Exists only so the LoRA-stack widget is a valid, architecture-correct combo value. Leave it bypassed — see "Consistency approach — no training required" below. |

No LoRA is active by default, and none is required. The consistency mechanism is
**same character-description text + same fixed seed (`424242`)** across all four
panels — that is the whole approach, not a placeholder for training.

## Grid layout / alpha convention

Every panel is prompted as a **grid layout with transparent alpha gutters** between
sections — no solid divider lines, no background fill between cells — rather than a
photo-style collage with borders. This is a standing rule for every sheet this flow
produces, not just this character:
- Each section's prompt explicitly says "separated by clean transparent alpha
  gutters (no solid dividers, no background fill between sections)".
- Each section also asks for a **transparent background** behind the character
  silhouette, so downstream tools can key/crop per-section without background
  cleanup.
- This relies on Qwen-Image 2.1's native 4-channel (RGBA) VAE output — no
  post-process background-removal node is wired in, and none should be needed for
  a well-behaved render. If backgrounds come out opaque anyway, that's a prompt-
  adherence failure to flag, not something to patch around with an extra node.

## Stage groups

| Group | Nodes | Default mode | Purpose |
|-------|-------|--------------|---------|
| 00 — MODELS | 1–3, 49 | active | Loaders, plus node 49 **RESOLUTION** (`PrimitiveInt`), linked to the `resolution` input of all four encoders (5, 9, 13, 17). Change the size here only. |
| CHARACTER CARD (purple `#a1309b`) | 39–43 | active | **The only text you edit.** Node 39 holds the character; nodes 40–43 (`StringConcatenate`) each join it with one sheet's template and feed that panel's encoder `prompt`. |
| 01 — LORA STACK `[bypass to disable]` | 4 | **bypassed, leave as is** | Wiring placeholder only — no LoRA is used or needed at this stage. |
| 02 — THREE-VIEW TURNAROUND | 5–8 | **active** | Front/side/back turnaround, 512×512. Render this one first. |
| 03 — EXPRESSION SHEET `[bypass to disable]` | 9–12 | **bypassed** | 3×3 grid of 9 expressions, 512×512. |
| 04 — POSE SHEET `[bypass to disable]` | 13–16 | **bypassed** | 3×3 grid of 9 poses, 512×512. |
| 05 — COSTUME SHEET `[bypass to disable]` | 17–20 | **bypassed** | 4-section outfit variants, 512×512. |
| 06 — SUPERSCALING x2 + FINAL SHEET `[bypass to disable]` (amber `#b58b2a`) | 22–38, 45–48 | active | Each panel → `ImageRemoveAlpha+` → `ImageUpscaleWithModel` (x4) → `ImageScaleBy 0.5 lanczos` (net x2, 1024×1024) → `Save x2`, then three `ImageStitch` nodes build a 2×2 final sheet (2048×2048). **Needs all four panel groups active** — see below. |

Each panel is one `TextEncodeQwenImage21 → KSampler → VAEDecode → SaveImage` chain;
there's no separate shared-negative node anymore (each `TextEncodeQwenImage21`
carries its own `negative_prompt` widget, kept identical across all four by
convention, not by wiring).

Toggle a group from the canvas: select its nodes and press **Ctrl-B**, or use the
rgthree "Fast Groups Bypasser". Only the three-view panel runs by default so a
naive "queue prompt" doesn't burn a 4x render; un-bypass the others as needed.

## Usage

1. Edit **only** the `CHARACTER CARD` node (39). Keep one labelled field per
   line, because the sheet templates refer to these fields by name:
   ```
   Character name: KAILANI
   Scope: Animation
   Art style: anime style, clean line art, cel shading
   Character: <appearance: body, skin, hair, eyes, age/gender>
   Default outfit: <outfit worn in the three-view, pose and expression sheets>
   Signature prop: <held in the three-view, used in pose 9>
   Setting: <world flavour for pose backgrounds and costume variants>
   Color palette: <3–4 colours, used for every costume>
   ```
2. Don't edit the four `Compose prompt —` nodes (40–43) unless you want to
   change a *sheet* (sections, labels, layout). Their `string_b` templates are
   character-neutral on purpose: they say "the signature prop" and "the
   character's setting", never "surfboard" or "beach". The old `prompt` text
   boxes on the encoders (5, 9, 13, 17) are blanked, because the linked
   composed prompt overrides them.
3. Leave the seed at `424242` (fixed) in all four `KSampler` nodes — same seed
   + same identity text is the free way to keep a family resemblance across
   panels without training anything.
4. Render the three-view panel first. QC it numerically (Rule 2 in the
   `comfyui-flow-authoring` skill — this model has no image input), then
   un-bypass expressions/poses/costumes one at a time.
5. Filename prefixes default to `Character/kailani/<panel>` — rename `kailani`
   to your character's name (nodes 8, 12, 16, 20, and the x2/sheet saves 25, 28,
   31, 34, 38) before rendering, or
   duplicate this flow file per character once you have more than one.

## Consistency approach — no training required

**This flow does not require training anything, by design, and that's the current
decision, not a temporary gap.** Consistency comes entirely from: one character
card fed verbatim into all four panel prompts (by wiring, so the identity text
cannot drift between sheets), and reusing the same fixed seed (`424242`) in all
four `KSampler` nodes. That's it —
no dataset, no training job, no extra models beyond what's already on the remote.
This gives a *loose* family resemblance (same character description in, same
general look out), not pixel-identical panels — good enough for a reference sheet.

The LoRA slot (node 4) stays bypassed and at strength 0 for the same reason: it's
a wiring placeholder, not a step you need to complete. Leave it bypassed.

If tighter consistency is ever wanted later (not needed now — listed only so the
option is on record, not as a next step):

- **Train a character LoRA.** Explicitly parked: the MCP's `train_prepare_dataset`
  / `train_start` tools only train a Flux1-dev LoRA, not Qwen-Image, so this would
  need a Qwen-capable trainer or a parallel Flux flow just for LoRA-source
  generation — real setup work, not a quick toggle.
- **Face-only identity lock via IPAdapter FaceID.** The LoRA files are already on
  the remote, but the IPAdapter custom-node pack is not installed, and it's an
  SDXL-only path, not Qwen-Image — a parallel flow, not an addition to this one.
- **ControlNet-guided poses** for the pose sheet specifically. Qwen-Image 2.1's
  built-in ControlNet path crashes on 2.1 (it expects a 5D tensor and DWPose
  gives 4D); a DiffSynth union control LoRA is the known workaround and would
  need validating against this checkpoint first.

## Resolution / sampler settings

All four panels render **512×512**, set once on the **RESOLUTION** node (49), which
feeds every `TextEncodeQwenImage21`. Stage 06 upscales them x2 to 1024. At 512 each 3×3 grid cell is ~170px, so
expression/pose faces and the small labels lose detail; raise to 768 for finals.
See "Known limitation" above.

### 06 — SUPERSCALING x2 + FINAL SHEET

| Node | What |
|------|------|
| 22 `UpscaleModelLoader` | `RealESRGAN_x4plus.pth`: matches the photographic default card. For the anime example card, swap to `RealESRGAN_x4plus_anime_6B.pth` (all on the server). |
| 23/26/29/32 `ImageRemoveAlpha+` | ESRGAN models take 3-channel RGB; the Qwen 2.1 VAE outputs RGBA. Allowed by the grid/alpha rule (alpha is only dropped right before an RGB-only upscaler). In practice the panels come out fully opaque anyway (alpha ≥ 231 on every render so far), so nothing visible is lost. |
| 24/27/30/33 `ImageUpscaleWithModel` | x4: 512 → 2048 (all ESRGAN models on the server are x4-only). |
| 45/46/47/48 `ImageScaleBy` | `lanczos`, 0.5 → 1024: net x2, keeping the ESRGAN detail. |
| 25/28/31/34 `SaveImage` | `Character/kailani/<panel>_x2`. |
| 35 `ImageStitch` (right) | top row: three-view \| expressions |
| 36 `ImageStitch` (right) | bottom row: poses \| costumes |
| 37 `ImageStitch` (down) | top over bottom → 2048×2048 |
| 38 `SaveImage` | `Character/kailani/sheet_x2` — the final composite. |

Stitch spacing is `0`: the panels already carry their own margins, and
`ImageStitch` can only pad with a solid colour (white/black/red/green/blue), which
would be a solid divider — against the grid/alpha convention.

**Group dependency:** stage 06 upscales and stitches **all four** panels, so it
needs groups 02–05 active. If you bypass a panel group, bypass 06 too. Otherwise its
upscale chain for that panel has no input, ComfyUI rejects those outputs, and the
final sheet isn't built. The native 512 `Save` nodes in each panel still run. For
a quick three-view-only iteration, bypass 03–06.

Sampler settings (all four panels, matches this project's Qwen-Image 2.1 base
convention): `steps 30, cfg 4.5, sampler euler, scheduler simple, denoise 1,
seed 424242 fixed`.

**Don't change these without re-testing** — each of these broke this flow on 2026-09-30
(ComfyUI 0.38.0, UC GGUF):
- `cfg 1` (what ComfyUI's official 2.1 templates use) → noise with the int8
  encoder, NaN (fully transparent black PNG, looks white) with the bf16 encoder. The
  UC GGUF wants real CFG.
- A `QwenImage21Cache` node with `device: off` at cfg 4.5 → NaN output.
- **Text encoder on GPU (`device: default`) → NaN for some prompts.** The GPU HIP
  int8 kernel returns NaN conditioning for certain prompt texts (deterministic
  per prompt): three-view/expressions/poses blank while costumes rendered, and
  the reverse after a subtitle edit. Same encoder with `device: cpu` rendered all
  four cleanly. Keep node 2 on `cpu`; the cost is a slower encode (8B on the
  Xeon), and the encoded prompts are cached between runs until the card changes.
- **No `QwenImage21Cache` node.** It was tried (`off` → NaN; `cpu`) and removed:
  it didn't fix anything, and the model's built-in default cache (`auto`) applies
  without it.
- The step-2 crash `The size of tensor a (…) must match the size of tensor b (…)`
  from `comfy/ldm/wan/model_animate2.py` `self.slots.remove(s)` is fixed by a local
  ComfyUI patch (see `~/git/ComfyUI/LOCAL_PATCHES.md` on the server). It comes
  back if a ComfyUI update overwrites that line.
- A blank/white output is NaN, not a transparent-background success — check pixel
  std before judging a render.

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
