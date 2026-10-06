---
name: comfyui-flow-authoring
description: Use when creating, editing, staging, or debugging ComfyUI flows for this project — building a new flow, adding bypassable stage groups (LoRA stack, ControlNet, SuperScaling, model choice), wiring TorchCompileModel, choosing sampler/CFG/steps, or fixing a render that crashed or came out as noise. Encodes the project's staged-group colour convention, the ROCm torch.compile constraints, the numeric render-QC procedure, the canvas layout rules (no node overlap, groups padded ≥50px and spaced ≥50px, checked by scripts/canvas_check.py), and how to drive our own c-comfyui-mcp (userdata_*/node_schema/graph_edit/graph_convert) instead of hand-editing JSON. Triggers on: ComfyUI flow/workflow JSON, groups/bypass, TorchCompileModel, --disable-comfy-compiler, KSampler, LoraLoader, ImageUpscaleWithModel, userdata_read, graph_edit, node_schema, output/, 172.16.0.101.
license: MIT
metadata:
  server: c-comfyui-mcp
  comfyui: "0.38.0"
  host: "172.16.0.101:8188"
---

# ComfyUI flow authoring (this project)

Canonical flows live in the **remote** userdata library, `~/git/ComfyUI/user/default/workflows/`.
`flows/` in this repo is the dev mirror only. Build/edit structurally with our own
`c-comfyui-mcp`, never by hand-editing JSON or by round-tripping through the stock converter.

---

## Rule 0 — every flow ships with a README, named per its shape

Project-wide rule (see `AGENTS.md`): no flow is finished without a doc file
sitting next to it. This applies to every flow directory, not just Character/.
**The filename encodes whether the flow is independent or part of a family:**

- **One independent flow** — a single workflow JSON that stands alone: name
  the doc `<flow-name>_README.md`, next to that JSON. E.g. `character-sheet.json`
  → `character-sheet_README.md`. Do **not** use a bare `_README.md` for this
  case — a folder with several unrelated single-flow files would otherwise
  collide on one filename.
- **A workflow composed of several flow files meant to be read as one unit**
  (variants, stages, companion pieces — e.g. the `3D/` pixal3d pair):
  put all of those files in one folder, and name the folder's doc plainly
  `README.md` (no prefix) — it documents the folder, not one file in it.

- Location: `flows/<Category>/` in this repo (the git-tracked mirror), using
  whichever filename the rule above selects. If the remote userdata directory
  holds the flow(s) in their own subfolder, write the same file there too via
  `userdata_write` so it travels with the JSON.
- Contents, minimum: which checkpoint/GGUF + CLIP + VAE the flow loads, every
  LoRA in the stack (filename, strength, trigger words, civitai link — the
  same table style as `flows/common/README.md`), which stage groups exist and
  which are bypassable, the native/delivery resolution, and any
  flow-specific usage guideline (e.g. "fill in the character-card Note before
  rendering", "run the three-view panel first to lock the seed").
- Treat it as part of the build, not an afterthought: write or update it in
  the same pass as step 9 of the Build recipe below, before you consider the
  flow done.
- A flow that changes structurally (new stage, new LoRA, new bypass) but
  leaves its README stale is an incomplete edit, same class of bug as a
  dropped link.

### Rule 0b: every flow also carries an in-canvas "MODEL & LoRA LINKS" note

The README lives outside the canvas, and people who open the flow in the
browser never see it. So every flow also needs a `MarkdownNote` node titled
**`MODEL & LoRA LINKS`**, inside its own group titled
`MODEL & LoRA LINKS (read me first)` (colour `#b58b2a`). The note must contain:

- **One table row per model file the flow loads**: UNet/checkpoint/GGUF,
  text encoder/CLIP, VAE, CLIP-vision, upscaler, ControlNet, and every LoRA.
  Columns: `models/` subfolder | exact filename | direct download link |
  model page. Use Hugging Face `…/resolve/main/…` URLs for the download link and
  civitai(.red) model URLs for the page. For a LoRA, also give the strength and
  trigger words.
- Optional, lower-VRAM alternatives (e.g. GGUF repos), if any.
- The sampler settings that depend on a bypassable stage (e.g. "speed LoRA
  bypassed → 20 steps / cfg 3.5").
- A reminder that downloads go **on the host only**, via `~/git/civitai_dl.sh`
  for CivitAI files.

Take URLs from a real source: the official template's "Model Links" note
(`comfyui_workflow_templates_json/templates/*.json` in the host venv), the
CivitAI MCP (`get_model`/`get_model_version`), or `flows/common/README.md`. Never
guess a URL. A `MarkdownNote` has no ports, so the submit path drops it
(`dropped_frontend_nodes`) and it never affects a run. `validate_workflow`
warns about it, and that warning is expected.

Like the README, a flow that adds or swaps a model or LoRA without updating
this note is an incomplete edit. Reference implementation:
`Character/character-scene-animate.json`, node 18.

---

## Rule 1 — MCP first, and never the stock converter

Two hard-won rules. Both cost real debugging time.

**Use `c-comfyui-mcp` for every structural edit.** Its tools are
`userdata_list`, `userdata_read`, `userdata_write`, `userdata_delete`,
`node_schema`, `graph_edit`, `graph_convert`, `graph_subgraph`,
`list_validations`, `validate_workflow`, `check_image_size`.
It connects via `COMFYUI_URL` (`http://172.16.0.101:8188`).

**Never save a flow in API format through the stock `comfyui_save_workflow`.**
Its API→UI converter does not understand connection references and silently
drops them (`expects a connection but got a literal value — dropped`). The save
reports success and the canvas then shows a pile of disconnected nodes.
Feed `save_workflow` **UI format** (`{nodes, links}`) verbatim, or better,
bypass it entirely and use `userdata_write` / `graph_edit write_to`.

### Division of labour

| Task | Tool |
| --- | --- |
| List the flow library | `userdata_list` |
| Read a flow byte-exact | `userdata_read` |
| Exact schema for a node type | `node_schema` |
| Add / connect / remove / set widgets | `graph_edit` |
| API ⇄ UI conversion | `graph_convert` |
| Inspect subgraph definitions | `graph_subgraph` |
| Preflight without editing | `validate_workflow`, `list_validations` |
| Write a finished UI graph | `userdata_write` (or `graph_edit` + `write_to`) |
| Queue, poll, fetch output | stock `comfyui_enqueue_workflow`, `comfyui_queue`, `comfyui_get_history`, `comfyui_get_image` |
| List/download models | stock `comfyui_list_local_models`, `comfyui_download_model` |

### `graph_edit` surface

Ops: `add_node`, `connect`, `disconnect`, `remove_node`, `set_widget`, `validate`.

- `graph_edit`/`graph_convert` edit **UI format only** (`{nodes, links}`).
  API format is valid as *input* to `graph_convert`.
- One call with an ordered `ops` array is the sane way to build anything: it
  loads, applies every op, validates once, writes once.
- Always pass `dry_run: true` first, read the validation result, then repeat
  without it. `ok:false` means nothing was written.
- **Subgraphs cannot be expressed in API format** — `graph_convert` to `api`
  *refuses* on a graph containing them. Edit those in UI format. To retarget a
  subgraph instance's promoted inputs, call `graph_subgraph` first to learn the
  exposed input names, then `set_widget` on the instance.

---

## Rule 2 — QC renders numerically; look when it matters

`c-comfyui-mcp__image_get` returns the image itself, so a render *can* be looked at
(2026-10-06: viewing two AutoCropFaces crops showed sharp frontal faces and overturned a
wrong "this photo has no face" conclusion). Still lead with numbers: they're reproducible
and comparable across runs. Never report a render as good or as noise without either
numbers or an actual look, and never judge success by `status: success`.

Compute statistics and compare against a known-good reference. Use
**`c-comfyui-mcp__image_stats`** with the files a run reported (`compare:"first"`,
reference first). It uses the same formulas as `scripts/imgstats.py`, which stays
as the SSH fallback:

```bash
ssh gaguilar@172.16.0.101 \
  'cd ~/git/ComfyUI/output/UI && /mnt/linux-games/comfyui-venv/bin/python \
   <repo>/.claude/skills/comfyui-flow-authoring/scripts/imgstats.py *.png'
```

Metrics: `mean`, `std` (global contrast), `|dH|`/`|dV|` (mean absolute
neighbour gradient), `rough` (local gradient ratio — image structure vs noise).
For RGBA outputs `image_stats` adds `alpha.opaque_pct`, `bbox`, `height_frac` and
`mid_width` (silhouette width across the middle of the body; a side profile is
about half a front/back view). Pairwise `mean_abs_diff` (and `_mirrored`) near 0
means one output **copied** another. That is how a "left view" that was really
the front reference (1.3/255) was caught on 2026-10-02.

**Run only the part you're testing; don't make scratch copies.**
`enqueue_workflow` takes per-run scope options, and the saved file is never touched:
`only_groups:["07"]` (enable those groups and execute only their outputs, plus
upstream dependencies, via `partial_execution_targets`), `groups:{enable,bypass}`,
`targets:[node ids]` and `output_prefix:"qc/"`. The result's `scope` field shows
what changed. A near-instant `success` with every node cached means the graph's
inputs are identical to an earlier run. That's useful proof that a restructure
(e.g. v2 → v3 subgraphs) preserved behaviour.

Reading them:

- **Noise / salt-and-pepper**: `std` collapses and `rough` collapses with it.
- **Undercooked (too few steps)**: `std` halves and `rough` drops ~25% —
  e.g. a 4-step Qwen smoke measured `mean 128.9 / std 38.2 / rough 1.48`
  against a healthy `126.9 / 77.3 / 1.95` (std −51%). That is a *step-count*
  artifact, not a broken flow.
- **Healthy**: every metric lands within a few percent of the reference render
  (the `00004` vs `00001` comparison came in under 1% on all three).

Always state which reference image you compared against, and say plainly that
the verdict is statistical rather than visual.

---

## Rule 3 — canvas layout: no overlap, padded groups, spaced groups

Every flow's canvas must satisfy all three, on every create **and** every edit:

1. **No two nodes overlap.**
2. **A group fully contains each node inside it, with ≥ 50 px on every side.**
   The top margin is measured from *below* the group's title bar. A node that
   sticks into a group it doesn't belong to (half in, half out) is a violation.
3. **Groups are ≥ 50 px apart on every side.** No group touches or overlaps another.

Geometry, as LiteGraph draws it — get this wrong and a "passing" layout still overlaps:
- A node's `pos` is the top-left of its **body**; its 30 px title bar sits
  *above* `pos`. Node box = `[x, y − 30, w, h + 30]`.
- A group's `bounding` is `[x, y, w, h]`; its ~34 px title is drawn *inside* the top edge.
- Use the `size` the frontend saved, not the schema default: after a web-UI save,
  nodes are often wider (a CLIPLoader at 665 px, a LoadImage preview at 340×340).
  So re-read the file from userdata before laying out, never lay out a stale copy.

How to lay out: by script, not by hand-picked coordinates. Give each group an
ordered list of inner columns (top-to-bottom node ids), stack nodes with a 40 px gap,
pad 60 px inside, and place groups in canvas columns with a 100 px gap, flowing
left→right in stage order (MODELS / LORA / CARD stacked → inputs → PROMPT/ENCODE →
SAMPLER → SUPERSCALING). Change only `pos` and group `bounding` — diff the
before/after nodes with `pos` stripped to prove nothing else moved.

Then **verify numerically** (exit 1 on any violation, so it can gate a write):

```bash
python3 .claude/skills/comfyui-flow-authoring/scripts/canvas_check.py flows/<Category>/<flow>.json
```

`graph_edit add_node` places nodes wherever `pos` says (or stacks them at a
default), so a flow built or extended with it **always** needs this pass afterwards.
Reference layout: `Character/character-scene.json` (2026-10-02).

---

## Environment (as of 2026-09-30)

- Remote host `172.16.0.101:8188`, Linux, **ROCm**, AMD Radeon AI PRO R9700 (~32 GB VRAM).
- ComfyUI `0.38.0`, Python `3.12.13`, PyTorch `2.13.0+rocm10.0.0`.
- `comfy-kitchen 0.2.35` installed (0.2.36 available), `comfy-aimdo 0.5.5`.
- Launch argv: `main.py --listen --port 8188 --use-pytorch-cross-attention --disable-comfy-compiler`.
- Custom nodes present: `rgthree-comfy`, `comfyui-impact-pack`,
  `comfyui-impact-subpack`, `comfyui-easy-use`, `ComfyUI-GGUF`.
- Model weights only ever live on the remote under `~/git/ComfyUI/models/`.
  Download with `ssh gaguilar@172.16.0.101 "~/git/civitai_dl.sh <version_id>"`.
  **Never pull model bytes onto this machine.**

---

## The staged architecture

Every new flow is built as ordered, colour-coded **stage groups**. Optional
stages are bypassable as a unit so one flow covers several jobs (LoRA on/off,
ControlNet on/off, 768 preview vs 1920 deliverable, model swap).

Title format: `NN — TITLE`, and append `[bypass to disable]` on optional stages.
The suffix is the human-readable contract; verify it by actually setting
`mode: 4`.

| # | Stage | Colour | Bypassable |
| --- | --- | --- | --- |
| 00 | MODELS | `#3f789e` | optional (model swap) |
| 01 | LORA STACK | `#4f9d69` | **yes** |
| 02 | CONTROLNET | `#8A8` | **yes** |
| 03 | PROMPT / ENCODE | `#3f789e` | no |
| 04 | SAMPLER | `#3f789e` | no |
| 05 | DECODE | — | no |
| 06 | SUPERSCALING | `#b58b2a` | **yes** |
| 07 | SAVE | — | no |
| — | CHARACTER CARD (Character/ flows) | `#a1309b` | no |

Colour provenance — do not silently "correct" these:
`#3f789e` (models/base), `#b58b2a` (upscale), `#8A8`/`#88A`/`#8AA` (ControlNet)
are the values actually present across the existing remote flows.
`#4f9d69` (LoRA) and `#a1309b` (character card, first used in
`Character/character-sheet.json`) are **proposed here**, chosen to stay far from
blue/amber/grey; change them if you prefer others.

One flow currently uses a bare string colour (`"42"`) for its FullHD output
group — accepted by the front-end, but migrate new work to the table above.

### Bypass mechanics

- Node field `mode`: `0` = active, `2` = muted, `4` = bypassed.
  Bypass (`4`) reroutes the node's inputs to its outputs and skips execution;
  muted (`2`) still evaluates but skips the output.
- To toggle a whole group from the canvas: **rgthree "Fast Groups Bypasser"**,
  or select the nodes and press **Ctrl-B** (that is what the existing
  Klein/v1 flows rely on). `rgthree-comfy` is installed.
- Bypassed loaders pass input→output by slot index, which is exactly why a
  bypassed `LoraLoaderModelOnly` cleanly forwards the MODEL untouched.
  Prefer `LoraLoaderBypass` / `LoraLoaderBypassModelOnly` where available —
  they are explicit about the pass-through instead of relying on slot order.
- **Design the bypass so it degrades correctly.** The common trap: bypassing
  `ImageUpscaleWithModel` alone leaves the downstream `Image Resize` still
  forcing 1920, so a "disabled" upscale upscales a 768 image with a resampler
  and softens it. Put the whole chain (upscale → resize) in the bypass group so
  disabling it yields the native 768 straight through to SaveImage.

---

## Stage specs

### 00 MODELS
- Diffusion: `UnetLoaderGGUF` (`ComfyUI-GGUF`) with a Q8_0 GGUF. Qwen-Image 2.1
  loads via the same architecture class as the safetensors path, so a GGUF swap
  does **not** change which torch.compile constraints apply.
- Text encoder: `CLIPLoader`, `type = qwen_image`. On this box prefer running it
  on **`default`/GPU** with a non-int8 variant; int8_convrot on CPU is the
  fallback that sidesteps the HIP int8 kernel entirely.
- VAE: `VAELoader`, `qwen_image_2.1_vae_bf16.safetensors`.
- `TorchCompileModel` belongs in this stage, between the loader and the sampler.

### 01 LORA STACK
- Chain `LoraLoaderModelOnly` (or `LoraLoaderBypassModelOnly`) from the model
  output. Order matters: later loaders see the already-patched model.
- Pack the stack into a **subgraph** when it has more than ~2 LoRAs, so the
  instance exposes one strength per LoRA as a promoted widget.
  `graph_convert` to `api` refuses on subgraph graphs — keep those UI-format.
- Keep a `Note` node in the group listing, per LoRA: filename, recommended
  strength, trigger words, and the civitai URL. The Character flows do this
  and it is the single most useful node in the file.
- To turn a LoRA fully off, either bypass its loader or set strength to 0.

### 02 CONTROLNET
- `LoadImage` → `DWPreprocessor` → `ControlNetLoader` → `ControlNetApplyAdvanced`
  → sampler `positive` slot.
- Muted (`mode: 2`) is the normal shipped state; use bypass only when you want
  the input dropped entirely. `ControlNetApplyAdvanced` takes
  `[strength, start, end]` in that widget order.
- Group a whole instance (`front`/`back`/`left`/`right` multiview) so it can be
  bypassed as a unit.

### 03 PROMPT / ENCODE
- Qwen-Image 2.1 uses `TextEncodeQwenImage21`, widgets
  `[prompt, negative_prompt, width]`.
- Encode at the **native** resolution (768×768), then upscale — encoding at the
  output resolution wastes time and degrades text/layout.

### 04 SAMPLER — see conventions below
### 05 DECODE
- `VAEDecode`. For inputs with alpha, `ImageRemoveAlpha+` before decoding.

### 06 SUPERSCALING
- `UpscaleModelLoader` (`4x-UltraSharp.pth`) → `ImageUpscaleWithModel`
  (x4) → `Image Resize (rgthree)` to the delivery size. Net x2 effective.
- Output folder convention: `SaveImage` prefix carries the category,
  e.g. `UI/coupon-app-android`, `Character/sheet`.

### Character-consistency flows (Character/)

A "character sheet" flow (turnaround, expressions, poses, costumes) is a
fan-out of the normal staged pipeline, not a new shape:

- **One shared character-card stage — the only text a user edits.** A single
  `PrimitiveStringMultiline` titled `CHARACTER CARD` holds everything
  character-specific; every panel's prompt is composed from it. Never restate
  the identity separately per panel, or panels drift. Reference implementation:
  `Character/character-sheet.json`, nodes 39–43.
  - **Card fields** (one per line, labelled, so templates can refer to them by
    name): `Character name`, `Scope`, `Art style`, `Character` (appearance),
    `Default outfit`, `Signature prop`, `Setting`, `Color palette`.
  - **Composition:** one core `StringConcatenate` per panel.
    `string_a` = linked from the card, `string_b` = that panel's template
    (widget text), `delimiter` = `\n\n`. Its output is linked into the panel
    encoder's `prompt` input (`TextEncodeQwenImage21.prompt`). Card first,
    template second ("Using the character described above, draw …").
  - **Templates must be character-neutral.** They carry only the sheet's
    layout, section list and labels, and refer to card fields by name ("the
    character's name", "the scope", "the art style given above", "the default
    outfit", "the signature prop", "the character's setting", "the color
    palette"). Anything concrete in a template (a surfboard, a beach, a
    wetsuit) leaks into every future character. Test: swapping the card
    alone must produce a coherent sheet for a different character.
  - **Templates must be medium-neutral too (2026-10-05).** Never name a style
    or medium in a template, compose string or negative: no "draw"/"drawn",
    "illustration", "line weight", "flat lighting", "cinematic",
    "photorealistic". Say "create … in the art style given above" and let the
    card's `Art style:` line decide drawing vs photograph. "draw … consistent
    line weight" made photographic cards render as line art in every
    Character/ flow. A style word in a *negative* is just as bad, because it
    pushes away from that medium for every character.
  - Negative prompts stay as a per-encoder widget: they're generic
    (anatomy/artifact terms), not character data.
  - Once `prompt` is linked, the encoder's old widget text is ignored. Blank it
    (`""`) so nobody edits a dead text box.
  - **Tooling gap:** `graph_edit` `connect` refuses to link into a widget input
    ("is a WIDGET, not a socket"). The frontend and the MCP's own API converter
    both support it: a linked widget keeps its `widget` marker and gains a
    `link`, and the converter gives the link priority. Until the guard in
    `c-comfyui-mcp/src/graph.js` `connect()` is relaxed, add the nodes with
    `graph_edit`, then add the widget links with a small script that does
    exactly what `connect()` does: append `[id, src, 0, dst, slot, "STRING"]`
    to `links`, set `inputs[slot].link`, push onto the source output's
    `links`, bump `last_link_id`. Then re-validate with `graph_convert`/a run.
- **One bypassable SAMPLER→DECODE→SAVE group per panel type** (three-view,
  expressions, poses, costumes), each fed by its own encode but the *same*
  MODEL/LORA output and, ideally, the *same* seed. Same seed + same identity
  text is the cheap, no-new-nodes way to keep a family resemblance across
  panels without training anything.
- **Keep 01 LORA STACK scaffolded even when empty.** It is the upgrade path:
  a dedicated "character turnaround/expression sheet" LoRA (SDXL/Illustrious
  ecosystem mostly) turns a single panel's prompt into a reliable multi-view
  grid instead of relying on prose alone. Note the gap in the flow's
  README rather than silently shipping without it.
- **Grids in one prompt: verify, don't assume.** Most txt2img backbones
  render *one* coherent subject per encode, and a prose "3x3 grid of 9
  expressions" often comes back as duplicated or blended faces. **Exception
  observed 2026-09-30:** Qwen-Image 2.1 UC (cfg 4.5, 30 steps, 768) rendered
  clean, distinct 3×3 expression and pose grids and a 4-section costume sheet
  in `Character/character-sheet.json`, with numbered sections listed explicitly
  in the prompt. So one prompt per sheet is acceptable on that backbone. On any
  other backbone, or if sections start blending, fall back to one
  encode+sample per section and composite afterwards (`ImageStitch`/grid nodes).
- **Output convention**: `SaveImage` prefix `Character/<character-name>/<panel>`,
  e.g. `Character/zhozho/three-view`, `Character/zhozho/expressions`.
- **Final deliverable: stage 06 = per-panel x4 + one composite.** Each panel's
  `VAEDecode` → `ImageRemoveAlpha+` → `ImageUpscaleWithModel` (x4) →
  `SaveImage <panel>_x4`, then `ImageStitch` right/right/down into a 2×2
  `sheet_x4`. Use stitch `spacing_width 0`: `ImageStitch` can only pad with a
  solid colour, which the grid/alpha convention forbids. The composite
  **depends on every panel group**: bypassing one panel without bypassing 06
  leaves that upscale chain without input, so say so in the README.

---

## Sampler conventions

Observed across the Qwen flows — follow these unless a LoRA demands otherwise.

| Case | steps | cfg | sampler | scheduler | denoise |
| --- | --- | --- | --- | --- | --- |
| Qwen-Image 2.1 base | 30 | 4 – 4.5 | `euler` | `simple` | 1.0 |
| Qwen-Image 2.1 + turbo/6-step LoRA | 6 | 1.0 | `euler` | `simple` | 1.0 |
| img2img / edit | — | reuse base | reuse base | reuse base | 0.5 – 0.85 |

- **Don't copy CFG from ComfyUI's official `image_qwen_image_2_1_*` templates.**
  They use `cfg 1` / 25 steps for the official int8_convrot model. With this
  project's UC GGUF, `cfg 1` gives noise (int8 encoder) or NaN (bf16
  encoder). Also don't add `QwenImage21Cache` with `device: off`, which gives
  NaN at cfg 4.5. A NaN render saves as all-zero RGBA and looks white, so
  check pixel std before judging.
- `denoise` must be **1.0** for txt2img. A sampler at denoise < 1.0 on an empty
  latent silently wastes steps.
- Native latent is **768×768×1**; deliverable is 1920×1920 via stage 06.
- Pin `control_after_generate` to `fixed` in delivered flows so a saved file
  reproduces exactly. Change it deliberately, not accidentally.

---

## torch.compile on ROCm — the contract

`TorchCompileModel` (`comfy_api/torch_helpers/torch_compile.py`) wraps
`model.get_model_object("diffusion_model")` in `torch.compile` and attaches the
wrapper at sample time. Node input `backend` accepts `inductor` or `cudagraphs`;
we use `inductor`. It must sit **between the model loader and the sampler**.

### Two independent failures

1. **AIMDO under Dynamo.** `--disable-comfy-compiler` is what keeps this at bay.
   `comfy/ldm/qwen_image21/model.py` calls `malloc_graph_begin`
   unconditionally; under compile the reconstructed `torch.Stream` has no
   `.cuda_stream`. Because that call is architecture-level, **a GGUF swap does
   not avoid it** — `UnetLoaderGGUF` builds the same QwenImage21 class.
2. **HIP int8 non-opaque kernel.** With an int8 (`*_int8_convrot.safetensors`)
   model, Dynamo traces into `comfy_kitchen`'s plain-Python HIP `int8_linear`,
   which calls `FakeTensor.__dlpack__(stream=-1)` →
   `Cannot access data pointer of Tensor`. The eager path is properly wrapped
   in `torch.library.custom_op`; the HIP path is not.
   `comfy-kitchen` 0.2.36 does **not** fix this — inspected, no `custom_op`,
   `_dl` unchanged. Upgrading is not a remedy.
3. **Reference images + compile → GPU crash (2026-10-02).** A
   `TextEncodeQwenImage21` with `images.image_N` wired adds reference latents to
   the sequence. That's a new shape, so Dynamo recompiles, and on this ROCm build
   the recompile died with `hipErrorIllegalAddress` in `KSampler`. The error is
   **sticky**: afterwards `/system_stats` returns 500 and every run fails until
   ComfyUI restarts. Rule: samplers whose encoder has reference images take the
   **uncompiled** model (the LoRA-slot output, not `TorchCompileModel`). See the
   `MODEL` / `MODEL_EAGER` split in `Character/character-sheet-v3.json`.

### Consequence — the launch-flag rule

`--disable-comfy-compiler` sets `disable_cuda_graphs = True`. It does **not**
disable `TorchCompileModel`.

- Keep the flag **while any `TorchCompileModel` node is active**.
- Remove it only after deleting the compile nodes, or after patching AIMDO to be
  compile-safe.
- Never "fix" the `.cuda_stream` error with
  `torch._C._cuda_getCurrentRawStream(0)` — it returns `0` on this ROCm build.

### Choosing whether to compile

Compile is not free: it costs a long first-run warm-up and it disables CUDA
graphs. Benchmark both ways at the real step count before committing it to a
delivered flow.

---

## Build recipe

1. **Pick the nearest existing flow and copy it** — they already carry correct
   stage groups, the upscale chain and the LoRA notes. Read one with
   `userdata_read` first, never reconstruct from memory.
2. **`node_schema` every node type you plan to add.** Do not guess slot
   indices, widget names, widget order, or combo values; custom-node packs
   rename these freely.
3. **`list_validations`** to see what preflight rules exist for this project.
4. **Build with one `graph_edit` call**, ordered `ops`, `dry_run: true` first.
5. **Validate**: `validate_workflow`, then `check_image_size` for the
   resolution budget.
6. **Lay out the canvas** (Rule 3): script the positions and group boxes, then
   `canvas_check.py` must print `OK`. Not optional — a flow that overlaps is
   unfinished, same as a flow without a README.
7. **Write**: `userdata_write` with the UI-format graph (or `graph_edit` +
   `write_to`).
8. **Sync the mirror**: copy to `flows/` in this repo.
9. **Write/refresh the flow's README** (Rule 0 — `<flow-name>_README.md` if
   independent, `README.md` if it's one of a family sharing a folder) — not
   optional, not a follow-up task. Also add or update the in-canvas
   `MODEL & LoRA LINKS` MarkdownNote and its group (Rule 0b) before step 6,
   so the layout check covers it.
10. **QC render**. For anything longer than about a minute (video, 4-panel sheets), submit with
   `enqueue_workflow wait:false`, then arm the Monitor tool with
   `node ~/git/c-comfyui-mcp/bin/comfy-watch.js <prompt_id> --every 25`. Node and step
   events arrive as notifications and the watch ends with the run, so no `queue_wait`
   polling. `queue_progress` gives a one-off snapshot.
   Then the QC itself: at production steps, then `image_stats` against a reference.
   To test one stage, use `only_groups` + `output_prefix:"qc/"` (Rule 2), not a scratch copy.

## Traps log

- **FaceDetailer on tiny faces can kill the server (ROCm, 2026-10-06).** At
  RESOLUTION 512 a three-view face is ~30 px. `guide_size 512` upscaled it 8.8× to
  a ~1024 crop, and the SDXL VAE encode faulted the GPU (`amdgpu … page fault`,
  process gone, no Python traceback). Ship FaceDetailer with `max_size 768` and
  `tiled_encode`/`tiled_decode` on, and run face-refine stages at 768. Check
  `journalctl -k` when the server vanishes mid-run without a traceback.

- **Never judge a render from a low step count.** A 4-step Qwen sample looks
  like noise and is *not* evidence of a broken flow. Use production steps.
- **A muted/bypassed output node still "succeeds"** — it renders, then writes
  nothing usable. Check `history.outputs` actually has files, and check the
  image dimensions match intent (a stray latent can yield an unexpected size).
- **Canvas edits are not saved.** A workflow file's mtime is the truth; an edit
  visible on the canvas that was never saved reverts on reload. Verify the file
  changed after the user edits on canvas.
- **Keep `mode: 4` semantics in mind when editing links** — a bypassed node in
  the middle of a chain still routes, but removing its input link changes what
  the bypass forwards.
- **Subgraphs + API format are incompatible.** If a flow carries a LoRA stack
  subgraph, it stays UI-format forever; queue it via the canvas or a stored
  prompt, not an API-format POST.
- **Reference images get copied, not reinterpreted.** On Qwen-Image 2.1 edit
  mode, a side view given the *front view* as a second reference came back as a
  near-pixel copy of it. Give only references that already show the target angle
  (e.g. the turnaround sheet), and say in the prompt what must NOT match
  ("this is NOT the front view"). Check with `image_stats` `compare:"pairs"`.
- **Repeated chains → subgraphs; shared values → KJNodes Set/Get.** Reference:
  `Character/character-sheet-v3.json` (3 subgraphs, 16 instances, a patch bay of
  ~12 names; 52 nodes / 41 links vs v2's 81 / 152). Promote only plain widgets
  (text, prefix). A promoted **seed** carries a `control_after_generate` slot the
  converter doesn't count, so keep seeds inside the definition. Set/Get resolves in
  `c-comfyui-mcp/src/setget.js`; names must be unique per graph. A GetNode inside a
  subgraph can read a root SetNode.
- **Model-rule validations only scan the root graph.** A decoder inside a
  subgraph isn't checked by `qwen-image-channels` (v3 reports 0 findings).
  Validate the expanded graph, or QC the output, until the rules recurse.
- **Verify `set_widget` on nodes with a dynamic combo.** Before c-comfyui-mcp
  `e2d6c7d` (2026-10-03), `graph_edit set_widget` wrote widgets *after* a dynamic
  combo into the combo's option fields (`RemeshMesh smooth_iters=3` landed in the
  boolean `sign_mode.drop_enclosed_components`). It's fixed. Still, after editing
  such a node, convert to API and read the values back: the validator only warns
  ("widgets_values were left untouched") and doesn't check them.
