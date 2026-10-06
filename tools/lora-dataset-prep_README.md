# tools/lora-dataset-prep.json — LoRA training dataset from a folder of photos

Turns a folder of photos into a **ready-to-train LoRA dataset**: square crops at the
training resolution, each with a caption file that starts with your trigger word. It
works like the FaceID folder in `Character/character-sheet-v3.json` (point it at a
folder, everything in it is used), but its output is meant to *train* a LoRA, not to be
used at render time. The trained LoRA then goes into the LoRA slot (node 4,
`LoraLoaderModelOnly`) of the Character flows, where the identity is present in every
sampling step instead of being repainted afterwards.

Remote path: `workflows/tools/lora-dataset-prep.json`
Local mirror: `tools/lora-dataset-prep.json`

## Models

Groups 00–04 load **no model**. Only the optional group 05 does:

| Folder | File | Loader |
|---|---|---|
| text_encoders | `qwen3vl_8b_ablit_int8.safetensors` | `CLIPLoader` (9), type `qwen_image` |
| vae | `qwen_image_2.1_vae_bf16.safetensors` | `VAELoader` (10) |

These match the UC trio used by the Qwen flows, so the cached dataset encodes exactly as
`qwen-image-2.1-UC-Q8_0.gguf` would see it. Download links are in the canvas note
**MODEL & LoRA LINKS**. No LoRA is loaded by this flow.

## How to use

1. Copy the photos into **ComfyUI `input/lora/<name>/`** on the host. The loader only
   lists folders inside `input/`; symlinks pointing outside are rejected on purpose
   (`secure_subfolder_path`). The Ale set is already in `input/lora/ale/`.
2. Optional: next to any photo, put a `.txt` with the same name describing what is
   *not* identity (`wearing sunglasses`, `side view, hair tied up`). Those words get
   attributed to the caption instead of being learned as part of the face.
3. Set the folder in node 1, the trigger in node 5 (`string_a`, default
   `aleface person`), and the export folder in node 7 (`folder_name`).
4. Run. Output: `ComfyUI/output/lora_datasets/<name>/<prefix>_00000.png` + `.txt`, …

Caption written per image = `<trigger>, <your .txt caption or nothing>`.

## Stage groups

| Group | Nodes | Default | Notes |
|---|---|---|---|
| MODEL & LoRA LINKS | 13 | note | read first |
| 00 — SOURCE | 1 `LoadImageTextDataSetFromFolder` | on | images + optional `.txt` captions |
| 01 — FACE CROP | 2 `AutoCropFaces` (head & shoulders, 1 face, 1:1) | **bypassed** | enable only for wide / full-body / group photos (see below) |
| 02 — SIZE | 3 resize shorter edge **1032** → 4 center crop **1024²** | on | the +8 margin guarantees an exact 1024 crop |
| 03 — CAPTIONS | 5 `StringConcatenate` (trigger + caption) | on | edit the trigger here |
| 04 — EXPORT | 7 `SaveImageTextDataSetToFolder`, 8 preview | on | the dataset for external trainers |
| 05 — COMFY CACHE | 9–12 encode → `SaveTrainingDataset` (`datasets/lora/<name>_<res>`) | **bypassed** | only for ComfyUI's own trainer (see below) |

### Why face crop ships bypassed

On close-up selfies the face already fills the frame. Asked for a crop 3× the face size,
AutoCropFaces clamps at the photo edges and returns a crop that is *smaller* than the
face. On the Ale set, 4 of 7 crops came out as half faces (checked visually,
2026-10-06). The plain resize + center crop keeps the whole face on selfies, so it's the
default. Enable 01 for folders where people are small in the frame.

### Why captions use `StringConcatenate`, not the dataset text nodes

`AddTextPrefix` / `StripWhitespace` (in `comfy_extras/nodes_dataset.py`) wrap each
per-item result in a one-element list without declaring a list output. Downstream
then receives lists instead of strings (`'list' object has no attribute 'strip'`,
`write() argument must be str, not list`). Core `StringConcatenate` gets mapped once
per caption by ComfyUI and yields clean strings.

## Training: outside ComfyUI for now

ComfyUI ships a trainer (`TrainLoraNode`), and it was tried on 2026-10-06 with the UC
GGUF. It does not fit this GPU yet:

- **GGUF couldn't be trained at all** at first: `TrainLoraNode` deep-copies the model via
  the loader's `cached_patcher_init`, which `UnetLoaderGGUF` didn't set. This is fixed on
  the host in **`custom_nodes/ComfyUI-GGUF`, branch `trainable-gguf`** (commit `a07ce42`,
  11 lines; `main` is untouched). Keep that branch checked out, or re-apply the commit
  after updating ComfyUI-GGUF.
- **Out of GPU memory on the first backward pass** (28 GB of 30 GB), even with the text
  encoder kept off the GPU (dataset cached by group 05) and with `offloading`. In bypass
  mode every quantized layer is dequantized to bf16 with gradient tracking, so autograd
  holds about a bf16 copy of the model.

So train with a dedicated trainer that does fp8 + block swapping (e.g. ai-toolkit or
musubi-tuner) on the **group 04 export**, which is in the image + same-name `.txt` layout
they read. Suggested starting point for a face LoRA on Qwen-Image 2.1 from ~7–20
photos: rank 16, learning rate 1e-4, ~1,500 steps, batch 1, resolution 1024. Then copy
the `.safetensors` into `models/loras/` and select it in node 4 of the Character flows,
with the trigger word in the card.
