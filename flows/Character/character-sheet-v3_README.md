# Character/character-sheet-v3.json — Character Sheet Generator, subgraphs + patch bay

Same output as `character-sheet-v2.json`: the three-view, expressions, poses and
costumes sheets, x4 upscales, the 2x2 final sheet, and the bypassed 3D views. The
difference is the **wiring**. Each repeated chain is one reusable subgraph, and the
shared values travel on a KJNodes **Set/Get patch bay** instead of long wires. The
canvas went from 81 nodes / 152 links (v2) to 52 nodes / 41 links. v2 stays as the
reference to compare renders against.

Remote path: `workflows/Character/character-sheet-v3.json`
Local mirror: `flows/Character/character-sheet-v3.json`
Outputs: `Character/kailani/v3/<panel>`, `…/<panel>_x4`, `…/sheet_x4`, `…/3d-views/<view>[_raw]`

## Models

| Folder | File | Loader |
|---|---|---|
| diffusion_models | `qwen-image-2.1-UC-Q8_0.gguf` | `UnetLoaderGGUF` (1) |
| text_encoders | `qwen3vl_8b_ablit_int8.safetensors` | `CLIPLoader` (2), type `qwen_image` |
| vae | `qwen_image_2.1_vae_bf16.safetensors` | `VAELoader` (3) |
| upscale_models | `RealESRGAN_x4plus.pth` (`anime_6B` for drawn cards) | `UpscaleModelLoader` (22), group 06 |
| background_removal | `birefnet.safetensors` | `LoadBackgroundRemovalModel` (51), group 07 |

Download links are in the canvas note **MODEL & LoRA LINKS** (top-left group). The
VAE and BiRefNet links are verified. The GGUF, the Qwen3-VL text encoder and the
ESRGAN file have no recorded source in this workspace yet, and the note says so
rather than guessing a URL.

## LoRAs

Node 4 is the placeholder slot from v1/v2: `LoraLoaderModelOnly`, bypassed,
strength 0. No LoRA is active. The host's Qwen-Image 1 LoRAs don't load on 2.1.

## Needs

- **comfyui-kjnodes** (installed on the host) for `SetNode` / `GetNode`.
- **c-comfyui-mcp ≥ the 2026-10-02 Set/Get change** (`src/setget.js`) to
  validate or submit this flow through MCP. An older MCP session reports
  `GetNode … is not installed`. Reconnect the server (`/mcp`) to pick up the change.
- ComfyUI frontend with subgraphs (1.53.6 on the host).

## Subgraphs (edit once, every instance changes)

Double-click an instance to open its definition. Each instance only holds its own
promoted widgets.

| Subgraph | Instances | Inside | Per-instance widgets |
|---|---|---|---|
| **Qwen panel** — card + template → image | 8: sheets 02–05, 3D views ×4 | Get CARD/CLIP/VAE/RESOLUTION/STEPS → `StringConcatenate` → `TextEncodeQwenImage21` (optional `ref_1` … `ref_4`) → `KSampler` (424242 fixed, steps = Get STEPS, cfg 4.5, euler/simple, denoise 1) → `VAEDecode` → `SaveImage` | `template`, `negative`, `filename_prefix`; sockets `model`, `ref_1` … `ref_4` |
| **RGBA cutout** — BiRefNet → transparent PNG | 4: 3D views | Get BG_MODEL → `RemoveBackground` → `InvertMask` → `JoinImageWithAlpha` → `SaveImage` | `filename_prefix` |
| **ESRGAN x4** | 4: group 06 | Get UPSCALER → `ImageRemoveAlpha+` → `ImageUpscaleWithModel` → `SaveImage` | `filename_prefix` |

The seed lives **inside** the panel subgraph, so all eight panels share 424242,
same as v2. It isn't promoted, because a promoted seed widget carries an extra
`control_after_generate` slot that misaligns instance widget values in the
converter. To change it, edit the subgraph's KSampler once.

**Steps** are the exception: they come from the root `STEPS` primitive (node 231,
group 00, default **30**) through Set/Get STEPS, so one number drives all eight
panels (sheets 02–05 and the four 3D views). The KSampler's own `steps` widget is
linked and ignored. Keep 30 for final renders on the UC GGUF, since fewer steps
undercook it (see *Resolution / sampler*). Set 6 only if you enable a 6-step turbo
LoRA in 01 and also drop cfg to 1 inside the subgraph. FaceDetailer in 02G keeps
its own 20 steps and does not read STEPS.

## Patch bay (Set → Get)

| Name | Set in | From | Read by |
|---|---|---|---|
| MODEL | 00 | TorchCompile (49), **shipped bypassed** → effectively the LoRA slot (4) | sheets 02–05 |
| MODEL_EAGER | 00 | LoRA slot (4), no compile | 3D views |
| CLIP, VAE, RESOLUTION, STEPS | 00 | 2, 3, 50, 231 | inside every Qwen panel |
| CARD | CHARACTER CARD | card (39) → face sentence (139, group 02F) | inside every Qwen panel |
| FACE_1 … FACE_4 | 02F | face photo → square pad: 140→141, 143→144, 146→147, 149→150 | `ref_1` … `ref_4` of every sheet panel (02–05) |
| SHEET, EXPRESSIONS_IMG, POSES_IMG, COSTUMES_IMG | 02–05 | each panel's image | 06 upscales; SHEET also feeds the 3D views as `ref_1` |
| UPSCALER | 06 | loader 22 | inside ESRGAN x4 |
| BG_MODEL | 07 | loader 51 | inside RGBA cutout |

Set/Get exists only in the browser. When a prompt is queued, each Get is replaced
by a real link to its Set's upstream, by the browser or by `c-comfyui-mcp`. One
name per Set: the converter rejects duplicates, as KJNodes does.

## Stage groups

| Group | Default | Bypass |
|---|---|---|
| MODEL & LoRA LINKS (read me first) | note only | — |
| 00 — MODELS | on | model swap only |
| 01 — LORA STACK | node 4 bypassed | yes |
| CHARACTER CARD | on | no. **The only text to edit for a new character** |
| 02F — FACE PHOTOS as Qwen refs | **on** (2026-10-06 16:10: the user's choice, native face fitting); photo 4 bypassed | yes: bypass for v3's text-only sheets |
| 02G — FACE ID REFINE | **bypassed** (2026-10-06 16:10) | Ctrl-B the group to enable; then use RESOLUTION 768 |
| 02 — THREE-VIEW TURNAROUND | on | **no**: 06 and 07 read SHEET |
| 03 / 04 / 05 — EXPRESSION / POSE / COSTUME | on | yes, but 06's 2x2 stitch needs all four, so bypass 06 too |
| 06 — SUPERSCALING x4 + FINAL SHEET | on | yes |
| 07 — 3D RECONSTRUCTION VIEWS | **bypassed** | select the group, Ctrl-B to enable |

## Current default (2026-10-06 16:10): Qwen-native face fitting

At the user's request the shipped state is **02F on, 02G bypassed**: the face photos go
into each Qwen sheet's encoder as reference images (identity in the sampler itself),
and there is no SDXL repaint afterwards. QC (three-view, RESOLUTION 512, Ale photos 1–3):
134 s and success. The embedded prompt shows `images.image_1..3` on the encoder, the face
sentence in the card, and no FaceID/FaceDetailer/SDXL nodes. The render is a
photorealistic three-view. The faces are only ~40 px at 512, so judge likeness at 768.
The card name came out as "SAILANI": text-rendering slips like that happen at 512.

## 02G — FACE ID REFINE (optional SDXL repaint, bypassed by default)

Added 2026-10-06, replacing 02F as the default. 02F fed the photos into Qwen as reference
images, which turned out slow (~2 min of encoding per sheet) and weak on likeness.
02G leaves the Qwen sheets alone and **repaints only the faces**, with an identity
model that is built for this job:

`sheet (Qwen) → SplitImageWithAlpha → FaceDetailer → JoinImageWithAlpha → Set_<SHEET> / Save <panel>_faceid`

- **FaceDetailer** (impact-pack) finds every face with `face_yolov8m.pt`, crops each
  one, upsamples it to 512 (`guide_size`), and repaints it at `denoise 0.5`.
- It samples on **RealVisXL V4 (SDXL) + IPAdapter FaceID PlusV2**. The photos come from
  a **folder** (BizarreBond-style). insightface (`buffalo_l`, GPU via MIGraphX) detects and
  **aligns/normalizes the face in every photo**, and FaceID injects all their identity
  embeddings (`combine_embeds: concat`) into the SDXL cross-attention. Weights:
  `weight 0.85`, `weight_faceidv2 1.0`, FaceID LoRA `0.6`.
- The face prompt is the CHARACTER CARD (via `Get_CARD`) plus a style-neutral close-up
  template. The art style still comes only from the card.
- Alpha is split off before the refine and joined back after, so the sheets keep their
  channels. The refined sheets feed `SHEET`/`EXPRESSIONS_IMG`/`POSES_IMG`/`COSTUMES_IMG`,
  so stage 06 (x4 + final 2×2) and the 3D views get the refined faces.

| Node | What |
|---|---|
| 169 | `CheckpointLoaderSimple` RealVisXL_V4.0 (photoreal; for a drawn card swap in a stylised SDXL checkpoint) |
| 170 / 171 | `IPAdapterUnifiedLoaderFaceID` (FACEID PLUS V2) / `IPAdapterFaceID` (concat) |
| **201** | **FACE PHOTOS FOLDER** (`LoadImagesFromFolderKJ`): a folder **on the host**, default `/home/gaguilar/sources/images/Ale/`. Every image in it is used, padded to 768² (never cropped) |
| 202 | `IPAdapterInsightFaceLoader` **ROCM** / buffalo_l: detects + aligns each face **on the GPU (MIGraphX)**, via the venv hook `ort_migraphx_fix.pth` (see below) |
| 203 | **NORMALIZED FACES** preview: the aligned face crops FaceID actually used. Check it after changing the folder |
| 197 → 177 → 178 | `Get_CARD` → face prompt → SDXL `CLIPTextEncode`; 179 negative |
| 180 | face detector `bbox/face_yolov8m.pt` |
| 181–196 | per sheet: Split alpha → **FaceDetailer** (seed 424242 fixed, 20 steps, cfg 5, dpmpp_2m karras, denoise 0.5, `max_size 768`, **tiled encode/decode on**) → Join alpha → Save `…/<panel>_faceid` |

Knobs:
- **Likeness vs. style:** `denoise` on the four FaceDetailers. 0.5 is the default. Go up
  (0.6–0.7) for stronger likeness, down (0.35–0.45) to keep more of the Qwen face.
- **Identity strength:** `weight` / `weight_faceidv2` on 171.
- **Tiny faces** (three-view at 512 test resolution): faces are only a few dozen pixels.
  Render at RESOLUTION 768 for the final sheets, or lower `bbox_threshold`.
- **Drawn (non-photo) cards:** RealVisXL repaints faces photographically. Use a stylised
  SDXL checkpoint in 169, or a lower denoise.

**Crash guard (2026-10-06):** the first QC, at RESOLUTION 512, crashed the server with an
amdgpu page fault. A 30×39 px three-view face was upscaled 8.8× to a 785×1024 crop, and
the SDXL VAE encode of that crop faulted. Because of that, `max_size` is 768 and tiled
VAE encode/decode is on. Use RESOLUTION **768** for any run with 02G active. At 512 the
three-view faces are too small for FaceID to add identity anyway.

Photos: make one folder per person on the host (existing ones:
`/home/gaguilar/sources/images/{Ale,Congo,Romanoff}`) and put the path in node 201.
More varied photos (angles, light) give a more robust identity. Every image must show a
detectable face: FaceID stops with "No face detected" otherwise, so remove that file
from the folder. Use `image_load_cap` / `start_index` on 201 to use only part of a big
folder.

**Close-up selfies and the 256 px face margin (node 205, 2026-10-06).** insightface
(SCRFD) cannot detect a face that fills the frame, because it needs context around the face.
`Ale/CaraAle5.jpg` is a sharp frontal close-up and failed every detector size, which
aborted the whole batch with "No face detected". (An earlier note here called it a photo
with no face. That was wrong.) `ImagePadForOutpaint` adds a 256 px gray border to every
folder photo before FaceID: tested offline, 128 px already makes all 7 Ale photos detectable,
and 256 leaves headroom. AutoCropFaces was tried and rejected: its RetinaFace crops are so
tight that insightface rejected all 7 of them. The loader **pads** to 768² instead of
BizarreBond's center **crop**, because a crop cut faces off in 4 of 7 portrait photos.

QC (three-view, RESOLUTION 768, the 6 good Ale photos): 33 s for the FaceID part. Only
the two head regions changed (0 outside them). The 6 normalized faces came out as 256×256
aligned crops.


### insightface on the GPU (MIGraphX), 2026-10-06

onnxruntime ≥1.23 has no ROCm EP. The venv gets GPU onnxruntime from AMD's MIGraphX
plugin EP, registered by `site-packages/ort_migraphx_fix.pth` → `ort_migraphx_fix.py`.
That hook maps any GPU provider request (`ROCM`, `CUDA`, …) to MIGraphX on the single
device `start-comfy.sh` exposes (`ROCR_VISIBLE_DEVICES=0`, the R9700). So nodes 170/202
ask for `ROCM`.
- **Output-order fix in the hook:** MIGraphX returned SCRFD's (N,4) boxes and (N,10)
  landmarks in each other's slots, so insightface asserted (`lmk.shape == (5, 2)`). The
  hook now puts every MIGraphX output back into the slot whose declared shape fits.
  Verified: detector matches CPU to 1e-5, and identity embeddings on all 7 Ale photos are
  identical to CPU (cosine 1.0000). 0.10 s vs 0.34 s per photo.
- **First run compiles** (~40 min for the five buffalo_l models). The result is cached in
  `~/.cache/ort-migraphx` and reused across restarts (a fresh process starts in ~10 s).
  The FaceID-only check after a restart took 22 s for the FaceID node.
- The hook needs a ComfyUI restart to take effect. `[ort_migraphx_fix] … MIGraphX on
  0000:06:00.0` in `comfyui_8188.log` confirms it loaded.

### Order, VRAM and caching in 02G (2026-10-06)

- **FaceID is computed first and only once.** Each Qwen sheet takes its `model` through
  a `VRAM_Debug` gate (214–217, "FACE ID FIRST") whose `any_input` is FaceID's
  `face_image`. ComfyUI orders execution only by data dependencies, so no Qwen sheet can
  start before the identity exists. All four FaceDetailers share that one FaceID result.
- **Cached across runs.** The folder loader's `IS_CHANGED` hashes the file list and
  modification times, so an unchanged folder is a cache hit: FaceID isn't recomputed
  until you add, remove or edit a photo (or restart the server). The FaceID embedding
  cannot be saved to disk with the installed nodes (`IPAdapterSave/LoadEmbeds` only cover
  CLIP-vision embeds). Recomputing after a restart costs a few seconds on the GPU.
- **Two model families, one GPU.** The Qwen sheets (~17 GB with the encoder) and the
  SDXL face stage (~9 GB) don't fit together. When ComfyUI's own eviction ran near the
  limit, this ROCm build page-faulted and killed the server (twice on 2026-10-06). So
  every swap is explicit: gates 214–217 unload all models before each Qwen sheet, and
  206/208/210/212 ("FREE VRAM before SDXL") before each FaceDetailer. Models reload
  from RAM in seconds.
- Every one of these nodes lives in 02G, so **bypassing 02G removes them all**: a
  bypassed `VRAM_Debug` passes `model_pass`/`image_pass` straight through.

## 02F — FACE PHOTOS as Qwen refs (bypassed since 2026-10-06)

Added 2026-10-05. Give up to four photos of one real person, and every sheet
(three-view, expressions, poses, costumes) draws the character with that face.
No extra model: the photos go into each sheet's `TextEncodeQwenImage21` as reference
images (`ref_1` … `ref_4`), the native Qwen-Image 2.1 way. IPAdapter FaceID was
considered and rejected for this flow: it only attaches to SD1.5/SDXL UNets, not Qwen.

How to use:
1. Put the photos in ComfyUI `input/` (top level; the picker drops subfolders).
2. Pick them in **FACE photo 1–3** (nodes 140, 143, 146). Photo 4 (149) ships
   bypassed: select it, its square-pad (150) and `Set_FACE_4` (151), then Ctrl-B.
   To use fewer photos, bypass the unused photo → pad → Set trio the same way.
3. Fill the CHARACTER CARD as usual. The face itself comes from the photos, so
   leave facial-structure details out of the `Character:` line.

Best photos: sharp, front or three-quarter, even light, face filling a good part
of the frame, different angles of the same person. Avoid sunglasses, heavy filters
and group photos.

What is taken from where is decided by the **face sentence** (node 139,
`string_b`), which is appended to the card. As shipped: facial structure
(face shape, jaw, nose, eyes, brows, lips, ears, apparent age) comes from the
photos. Hair, eye colour, skin tone, outfit and body come from the card. The photo's
background, lighting, clothes and pose are explicitly excluded. The sentence says
"any reference image that is a photograph of a real person", so the 3D views (whose
only reference is the generated SHEET) aren't told to look for photos they don't
have.

Each photo is padded to a white 1024² square (`ResizeAndPadImage`) before it reaches
its `Set_FACE_n`. This is not cosmetic. The panel samples on the encoder's `latent`
output, and with references the encoder sizes that latent from **`ref_1`'s aspect
ratio**. The first QC (2026-10-05) gave a 416×640 three-view from a portrait phone
photo instead of the 512² sheet. Padding, rather than cropping, never cuts off the
face.

Bypassing the whole group restores v3's text-only sheets exactly:
- Bypassed `LoadImage`s have nothing to forward, so every `ref_n` link drops.
- The bypassed `StringConcatenate` (139) forwards `string_a`, the bare card.

**TorchCompile (49) ships bypassed.** Reference images change the sequence length,
which makes Dynamo recompile. On this ROCm build that recompile crashed `KSampler`
with a sticky `hipErrorIllegalAddress` that needs a server restart (2026-10-02,
3D views). Re-enable 49 only while 02F is bypassed.

Cost: every reference image is vision-encoded and spliced into the sequence of
every sheet, so expect each sheet to take noticeably longer than text-only
(the scene flow measured ~46 s text-only vs ~190 s with two refs at 768).

## Resolution / sampler

Native size comes from RESOLUTION (50): 512 test, 768 final. Sampler steps come
from STEPS (231): 30 final. Never judge a low-step test render as broken: 4 steps
halves pixel std. The views follow the
sheet's square aspect. Stage 06 is a straight ESRGAN **x4**: 2048 from 512, 3072
from 768. That is also what v2 actually produced, since its 0.5x `ImageScaleBy`
nodes are bypassed even though its save names say `_x2`. v3 names the files `_x4`
to match.

## 07 — 3D reconstruction views

Same templates and rules as v2's group 07 (see `character-sheet-v2_README.md`):
front / left / back / right for Pixal3D, each saved twice. `…/<view>_raw` is the
render; `…/<view>` is RGBA with the BiRefNet cutout. Each view gets `ref_1` = SHEET
only and samples on **MODEL_EAGER**. Both choices come from v2's QC: compile +
reference images crashed the GPU, and a front-view second reference made the left
view copy the front.

To feed the 3D flow, copy the RGBA PNGs to `input/` and replace
`3D/3d_pixal3d_multi_views.json`'s sheet `LoadImage` + four `ImageCropV2` with four
`LoadImage` nodes.

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

The face sentence (139) is the one place "photograph" appears. It describes the *input* photos, not the output style.

## Default card: photorealistic Kailani (2026-10-05)

The CHARACTER CARD now holds a **photorealistic** Kailani (`Scope: Live-action film`,
`Art style: photorealistic photograph …`), now a woman in her early twenties
(the original card said "teenage"). The original anime card is kept verbatim in the
**EXAMPLE CARD — Kailani, original anime** MarkdownNote, right under the card in the
same group. Copy it back into the card to render the drawn version, and switch the
upscaler to `anime_6B` too.
