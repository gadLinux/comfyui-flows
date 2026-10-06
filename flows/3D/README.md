# 3D/ — Pixal3D + TRELLIS.2 character reconstruction

Two flows with one pipeline. They differ only in how the four views come in.

| Flow | Input |
|---|---|
| `3d_pixal3d_multi_views.json` | the official ComfyUI template: **one** turnaround sheet (`character_turnaround_4view_sheet.png`), cut into front / left / back / right by four `ImageCropV2` nodes with fixed crop boxes |
| `3d_pixal3d_from_views.json` | **four separate images**, one `LoadImage` per view (nodes 338 front, 341 left, 342 back, 345 right; same ids as the crops they replace). Made for the views from `Character/character-sheet-v3.json` group 07 |

Remote: `workflows/3D/`. Local mirror: `flows/3D/`.

## Models (both flows)

All downloaded to the host on 2026-10-02.

| Folder | File | Download |
|---|---|---|
| diffusion_models | `pixal3d_multiview_int8_convrot.safetensors` (5.6 GB) | [file](https://huggingface.co/Comfy-Org/Pixal3D/resolve/main/diffusion_models/pixal3d_multiview_int8_convrot.safetensors) |
| vae | `trellis_2_shape_vae_bf16.safetensors` | [file](https://huggingface.co/Comfy-Org/Pixal3D/resolve/main/vae/trellis_2_shape_vae_bf16.safetensors) |
| vae | `trellis_2_texture_vae_bf16.safetensors` | [file](https://huggingface.co/Comfy-Org/Pixal3D/resolve/main/vae/trellis_2_texture_vae_bf16.safetensors) |
| clip_vision | `dino_v3_L_naf_fp32.safetensors` | [file](https://huggingface.co/Comfy-Org/Pixal3D/resolve/main/clip_vision/dino_v3_L_naf_fp32.safetensors) |
| background_removal | `birefnet.safetensors` | [file](https://huggingface.co/Comfy-Org/BiRefNet/resolve/main/background_removal/birefnet.safetensors) |

Repos: [Comfy-Org/Pixal3D](https://huggingface.co/Comfy-Org/Pixal3D), [Comfy-Org/BiRefNet](https://huggingface.co/Comfy-Org/BiRefNet). No LoRAs.

## Stage groups (from the template; none are bypassable stages)

Preprocess Multiview Images → Conditioning (`Pixal3DMultiViewConditioning`, fov 20)
→ Models → Sparse Structure Generation → Shape Generation → Texture Generation →
Mesh Post-Processing (Remesh 768, Decimate 700k) → Texture baking (4096 textures,
normal + AO bakes) → Vertex color preview. Output: `3d/ComfyUI` (`Save3DAdvanced`).

## View conventions Pixal3D expects

From `comfy_extras/nodes_trellis2.py`:
- square views on alpha or black, object spanning about 1/1.1 of the frame, the same
  scale in every view. `ImageCropToMask` (pad 1.1, 1024², black) does this, so
  inputs only need a clean subject;
- fixed orbit: front 0°, **left 90° = the object's own left side** (the figure faces
  screen-left), back 180°, right 270°. The first connected view becomes the mesh's front.

## Using the from-views flow

1. Enable group 07 in `Character/character-sheet-v3.json` and render. For a quick
   run: `enqueue_workflow only_groups:["07"]`.
2. Copy the four RGBA PNGs from `output/Character/<name>/v3/3d-views/` to `input/`
   at the top level. The LoadImage picker doesn't list output subfolders.
   Example: `kailani_v3_3d_<view>.png`.
3. Select them in the four `View — …` loaders and queue.

## Detail settings (from-views flow, 2026-10-03)

The from-views flow runs higher-detail settings than the template. Texture
detail is capped by the TRELLIS voxel grid that the bake samples, not by the
4096 texture size, so the grid and the input views matter most.

| Node | Template | from-views | Why |
|---|---|---|---|
| 94 `Trellis2UpsampleStage.target_resolution` | 1536 | **2048** (max) | denser voxel grid: finer geometry and texture colour |
| 12 texture `KSampler.steps` | 12 | **20** | more texture refinement |
| 241 `RemeshMesh` resolution / smooth_iters | 768 / 20 | **1024 / 3** | 20 smoothing passes erased fine detail (the tooltip itself recommends 2–3) |
| 186 `DecimateMesh.target_face_count` | 700k | **1.5M** | keeps the extra geometry |
| 224 normal bake / 233 AO bake | 2048 / 1024 | **4096 / 2048** | sharper baked surface detail |
| 288 texture size | 4096 | 4096 | already denser than the voxel grid feeding it |

**Views:** render them at 1024 (`character-sheet-v3` RESOLUTION). At 512 they're
2× upscaled by `ImageCropToMask` before conditioning, which softens the texture.

Baseline for comparison: the first run (template settings, 512 views) is
`output/qc/3d-kailani/3d/ComfyUI_00001.glb` (454k vertices / 697k triangles, 15 min).

## Layout note

The official template fails `canvas_check.py` (63 violations, all its own).
The from-views variant adds none: the loaders take the crops' exact footprint.
A full re-layout is still to do.

## MCP note

Submitting through `c-comfyui-mcp` needs the 2026-10-02 converter fix. Before it,
the converter skipped the `BOUNDING_BOX` / `COLOR` / `LOAD_3D` widgets and ComfyUI
rejected the prompt (`Required input is missing`).
