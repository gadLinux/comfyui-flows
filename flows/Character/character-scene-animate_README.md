# Character/character-scene-animate.json — animate a character scene (Wan 2.2 I2V)

Turns one still from `Character/character-scene.json` into a 5-second clip with
Wan 2.2 image-to-video (A14B, two-expert high/low noise). It is a flat graph built from
ComfyUI's official `video_wan2_2_14B_i2v` template, with no subgraph, so the MCP
converter and validator can read every node.

Remote path: `workflows/Character/character-scene-animate.json`
Local mirror: `flows/Character/character-scene-animate.json`
Outputs: `output/Character/kailani/video/scene-surf_XXXXX_.mp4` (16 fps raw) and
`…/scene-surf-32fps_XXXXX_.mp4` (RIFE-interpolated, group 05)

## Models (00 — MODELS)

| Role | Node | File |
|---|---|---|
| UNet, high-noise expert (steps 0–2) | 1 `UNETLoader` | `wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors` |
| UNet, low-noise expert (steps 2–4) | 2 `UNETLoader` | `wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors` |
| Text encoder | 3 `CLIPLoader` (`wan`) | `umt5_xxl_fp8_e4m3fn_scaled.safetensors` |
| VAE | 4 `VAELoader` | `wan_2.1_vae.safetensors` (Wan 2.2 14B uses the 2.1 VAE) |

The host also has GGUF versions (`unet/Wan2.2-I2V-A14B-HighNoise-Q4_K_S.gguf`,
`…LowNoise-Q4_0.gguf`). They're smaller but lower quality. Swap them in with
`UnetLoaderGGUF` if VRAM is short.

## LoRAs (01 — SPEED LoRA)

| # | Node | Source | File in `models/loras/` | Strength | Trigger words |
|---|------|--------|-------------------------|----------|---------------|
| 5 | lightx2v 4-step — HIGH | [lightx2v / Comfy-Org Wan 2.2 repack](https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged) | `wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors` | 1.0 | — |
| 6 | lightx2v 4-step — LOW | same | `wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors` | 1.0 | — |

These are step-distillation LoRAs. With them, the clip takes 4 steps at cfg 1.
**Bypassing group 01 requires changing the samplers**, or the output is undercooked
mush. On both KSamplerAdvanced nodes, set:

| | steps | cfg | node 13 `end_at_step` | node 14 `start_at_step` |
|---|---|---|---|---|
| LoRA on (shipped) | 4 | 1.0 | 2 | 2 |
| LoRA off (bypassed) | 20 | 3.5 | 10 | 10 |

Other Wan 2.2 I2V LoRAs on the host, not wired in:
- `Wan2.2-I2V-A14B-4steps-lora-rank64-Seko-V1-{high,low}_noise_model` (an alternative 4-step distill);
- `SVI_v2_PRO_…` (for long, multi-part videos; used by `Wan 2.2 Video Infinity.json`).

## Stage groups

| Group | Contents | Bypassable |
|---|---|---|
| 00 — MODELS | nodes 1–4 | no |
| 01 — SPEED LoRA | nodes 5, 6 | yes. Retune the samplers as in the table above |
| 02 — START FRAME + MOTION PROMPT | 9 `LoadImage`, 10 positive, 11 negative, 12 `WanImageToVideo` | no |
| 03 — SAMPLER | 7/8 `ModelSamplingSD3` shift 5, 13 high-noise sampler, 14 low-noise sampler | no |
| 04 — DECODE + SAVE | 15 `VAEDecode`, 16 `CreateVideo` 16 fps, 17 `SaveVideo` (raw) | no |
| 05 — RIFE x2 INTERPOLATION | 20 `RIFE VFI` (`rife49.pth`, ×2, fast_mode, ensemble, fp32), 21 `CreateVideo` 32 fps, 22 `SaveVideo` | **yes**. A separate branch off the decoded frames, so bypassing it only drops the 32 fps file; the 16 fps raw clip is unaffected. |

**How the two experts split the work.** Node 13 adds the noise, runs steps 0–2 on the
high-noise expert and returns the latent *with leftover noise*. Node 14 continues
from step 2 to the end on the low-noise expert, without adding new noise. The seed is
on node 13 (424242, `fixed`). Change it for a different take.

## Input and prompt

- **Start frame (node 9):** `kailani/scene-surf.png`, a copy of
  `output/Character/kailani/scenes/scene_00017_.png` (1024×768). Like the character-scene
  flow, it loads from `input/<character>/`, not from the generated-images picker (see
  `character-scene_README.md`). To animate a new render:
  ```bash
  ssh gaguilar@172.16.0.101 'cd ~/git/ComfyUI && cp output/Character/kailani/scenes/<render>.png input/kailani/scene-<name>.png'
  ```
- **Motion prompt (node 10):** describe *motion*, not the picture. The start frame already
  fixes the look. Say what moves (her weight shift, hair, wave, gulls, background
  surfers) and what the camera does. Mention the style ("hand-drawn illustration") so
  Wan doesn't drift toward photoreal.
- **Negative (node 11):** Wan's stock Chinese negative, plus `signature, watermark, text,
  second surfboard, duplicate girl, morphing, flicker`. The source still has a scribbled
  signature in the bottom-right corner; the negative only discourages Wan from animating
  it, it doesn't remove it.

## Resolution / length

- **832×624, 81 frames, 16 fps = 5.0 s.** 832×624 is exactly the 4:3 shape of the
  1024×768 scene, and both sides are multiples of 16, as `WanImageToVideo` requires.
  `WanImageToVideo` resizes the start frame itself and drops its alpha channel.
- `length` must be 4n+1 (81, 97, 113…). Each extra 16 frames adds about 1 s and
  a matching share of sampling time.
- 720p class (1024×768 directly) also works on the 32 GB R9700, but it's about 1.6× slower.
  Test at 832×624 first.
- For longer clips with no cut, use `Wan 2.2 Video Infinity.json` (SVI LoRAs, part-by-part
  extension) instead of raising `length` far past 81. Wan 2.2 was trained on ~5 s clips.

## Frame interpolation (05)

RIFE 4.9 (`ComfyUI-Frame-Interpolation`) inserts one synthetic frame between each pair:
81 frames become 161, played at 32 fps over the same 5 s.
- The checkpoint is `custom_nodes/comfyui-frame-interpolation/ckpts/rife/rife49.pth`, not
  `models/`. It's 21 MB, downloaded on the host on 2026-10-02.
- **Slow motion instead of smooth motion:** set node 21's fps to 16. You get the same 161
  frames over 10 s.
- **×4 (64 fps):** set `multiplier` 4 on node 20 and fps 64 on node 21. Keep both in sync,
  because fps = 16 × multiplier.
- RIFE doesn't fix bad motion. It only fills in frames, so judge the 16 fps raw clip first.

## In-canvas notes

- **Node 19, "VIDEO LENGTH"**, sits under the Wan I2V conditioning node in group 02. It covers the
  4n+1 rule, duration vs quality (81 frames is reliable, 97–121 is usually fine, 161+ degrades),
  cost, and how to go longer (Video Infinity / SVI parts, chaining, RIFE interpolation).

## In-canvas links note

Node 18 (`MarkdownNote`, group "MODEL & LoRA LINKS") lists every model and LoRA with its
direct download link and model page, plus the bypass sampler settings. It's a frontend-only
node, so the submit path drops it.

## Performance (R9700 32 GB, measured 2026-10-02)

| Run | Time | Notes |
|---|---|---|
| 81 frames, cold (first run after Qwen flows) | **529 s** | model loads plus a VAE-encode OOM retried as tiled (Qwen weights were still resident). About 15–18 s per step × 4 steps |
| 17 frames, warm | **22 s** | both experts already loaded |
| Group 05 RIFE ×2 on 81 frames | **≈5 s** RIFE + ≈6 s encode/save (16 s total with Wan cached) | 161 frames, about 2.5 % of a cold run. The model is 21 MB, so VRAM use is negligible |

To avoid the slow cold path, call `free_vram` (c-comfyui-mcp) before the first video run
after image work.

Following a run: submit with `enqueue_workflow wait:false`, then
`node ~/git/c-comfyui-mcp/bin/comfy-watch.js <prompt_id>` (or the `queue_progress` tool) shows
the executing node and the sampler steps live.

## Status

**Rendered and checked, 2026-10-02.** `scene-surf_00001_.mp4` is 832×624, 81 frames, 16 fps, 5.06 s.
I checked a contact sheet of every 16th frame:
- Kailani and the single hibiscus board stay consistent the whole way;
- the camera pushes into the barrel as the wave curls over;
- the gulls fly and the background surfers drift out of frame.

Known issue: the scribbled signature from the source still stays fixed in the bottom-right
corner. Crop or regenerate the still without it if that matters.

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

This flow has no card. Its MOTION PROMPT now ends with "consistent with the source image's style." (it was "consistent hand-drawn illustration style."), so a photographic still stays photographic.
