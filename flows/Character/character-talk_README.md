# Character/character-talk.json — character talking clip (voice + lip-sync)

The next step after `character-scene-animate.json`: the same character, now **speaking**.
A script becomes speech with **Qwen3-TTS VoiceDesign**, and the voice timbre comes from the
card's new `Voice:` line. **Wan 2.2 S2V** (speech-to-video) then animates a frontal portrait
of the character, lip-synced to that audio. The output is one mp4 with the speech muxed in.

**Languages:** English and Spanish, both rendered and checked (see Status). The TTS also speaks ZH, JA, KO, FR, DE, PT, RU and IT.

The graph is flat, built from ComfyUI's official `video_wan2_2_14B_s2v` template. That
template's "Video S2V Extend" subgraphs are expanded into plain nodes here, so the MCP
converter and validator can read every node.

Remote path: `workflows/Character/character-talk.json`
Local mirror: `flows/Character/character-talk.json`
Outputs:
- `output/Character/kailani/talk/voice_XXXXX_.mp3`: the speech alone, saved before the video is sampled
- `output/Character/kailani/talk/talk_XXXXX_.mp4`: 640×640, 16 fps, with audio

## Models (00 — MODELS)

| Role | Node | File |
|---|---|---|
| UNet (speech-to-video) | 1 `UNETLoader` | `diffusion_models/wan2.2_s2v_14B_fp8_scaled.safetensors` |
| Text encoder | 2 `CLIPLoader` (`wan`) | `text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors` |
| VAE | 3 `VAELoader` | `vae/wan_2.1_vae.safetensors` |
| Audio encoder | 4 `AudioEncoderLoader` | `audio_encoders/wav2vec2_large_english_fp16.safetensors` |
| TTS | 9 `FB_Qwen3TTSVoiceDesign` (1.7B, bf16) | `models/qwen-tts/Qwen3-TTS-12Hz-1.7B-VoiceDesign/` (HF repo folder, downloaded to the host on 2026-10-02) + `qwen-tts/Qwen3-TTS-Tokenizer-12Hz/` |

TTS custom node pack: `ComfyUI-Qwen-TTS` ([flybirdxx](https://github.com/flybirdxx/ComfyUI-Qwen-TTS)).
VoiceDesign exists only as a 1.7B model. The node is set to
`unload_model_after_generate: true`, so the ~4 GB of TTS weights leave VRAM before the 14B S2V model loads.

**wav2vec2 is "english", but Spanish lip-sync works.** The encoder turns *sound* into
mouth-motion features. It doesn't read words, so any language drives the lips. It is the only
audio encoder Wan 2.2 S2V was trained with, so there is nothing to swap for Spanish.

## LoRAs (01 — SPEED LoRA)

| # | Node | Source | File in `models/loras/` | Strength | Trigger words |
|---|------|--------|-------------------------|----------|---------------|
| 5 | lightx2v 4-step | [lightx2v Wan2.2-Lightning](https://huggingface.co/lightx2v/Wan2.2-Lightning) via the [Comfy-Org repack](https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged) | `wan2.2_t2v_lightx2v_4steps_lora_v1.1_high_noise.safetensors` | 1.0 | — |

This is the LoRA Comfy-Org's S2V template uses. It's a T2V distill, and many keys don't match the
S2V model, but it still cuts sampling from 20 steps to 4. **Bypass group 01 → set the two
primitives in group 04:** `STEPS` 20 and `CFG` 6.0. They are linked into all three samplers,
so those two widgets are the only things to change.

| | STEPS (node 19) | CFG (node 20) |
|---|---|---|
| LoRA on (shipped) | 4 | 1.0 |
| LoRA off (group 01 bypassed) | 20 | 6.0 |

## Stage groups

| Group | Contents | Bypassable |
|---|---|---|
| 00 — MODELS | 1–4 | no |
| 01 — SPEED LoRA | 5 | yes. Then set STEPS 20 / CFG 6 |
| CHARACTER CARD | 6 | no. **Edit for a new character** |
| 02 — VOICE | 7 SCRIPT, 8 `RegexExtract` (Voice line), 9 TTS, 10 `SaveAudioMP3`, 36 note | no |
| 03 — PORTRAIT + TALKING PROMPT + SPEECH ENCODE | 11 PORTRAIT, 12 PERFORMANCE, 13/14 compose, 15 positive, 16 negative, 17 `AudioEncoderEncode` | no |
| 04 — CHUNK 1 (0–5 s) | 18 shift 8, 19 STEPS, 20 CFG, 21 `WanSoundImageToVideo` 640×640×77, 22 sampler (seed 424242, fixed) | no |
| 05 — CHUNK 2 (5–10 s) | 23 `WanSoundImageToVideoExtend`, 24 sampler (seed 1), 25 append | **yes** |
| 06 — CHUNK 3 (10–15 s) | 26, 27 (seed 2), 28 | **yes** |
| 07 — DECODE + SAVE | 29/30 first-frame fix, 31 decode, 32 drop lead frames, 33 `CreateVideo` 16 fps + audio, 34 `SaveVideo` | no |
| MODEL & LoRA LINKS | 35 `MarkdownNote` | — (frontend-only, dropped at submit) |

**How chunk bypass degrades.** A bypassed group forwards by type: the `Append` node passes
its first latent (the video so far), the sampler passes its `latent_image`, and the extend node
passes its conditioning. So bypassing 06 gives a 10 s clip, and bypassing 05 + 06 gives 5 s.
Always toggle a **whole** group, never single nodes.

**First-frame fix (29–32)** comes from the official template: the VAE over-bakes the first
frame, so the first latent frame is duplicated in front, then the lead frames are dropped
after decoding (`ImageFromBatch` index 3).

## Per-render inputs (what to edit)

1. **SCRIPT (node 7).** What the character says, in English or Spanish. The speaking rate
   measured for this voice is **English ≈ 2.5 words/s and Spanish ≈ 2.1 words/s**, so the shipped
   3 chunks (15 s) hold **≤ 35 English or ≤ 30 Spanish words**. Speech longer than the video is
   **cut off**. Shorter speech leaves a silent idle tail, so bypass a chunk instead. Node 36 has
   the table; check the duration of `voice_*.mp3` if in doubt.
2. **PERFORMANCE (node 12).** Body language and mood for this line, e.g. "tilts her head at
   'Big waves?'". It is appended to the card and the character-neutral talking template (node 13).
3. **TTS language (node 9).** Shipped as `Auto`, which detects EN/ES from the script. Set `Spanish` /
   `English` explicitly if the accent drifts.
4. **PORTRAIT (node 11).** `input/kailani/portrait.png`, a frontal head-and-shoulders still.
   S2V keeps the reference framing, so a wide scene gives a tiny face and weak lip-sync. The
   shipped portrait was rendered with `character-scene.json` (SCENE = "head-and-shoulders portrait,
   facing the camera…", canvas 768) and copied in:
   ```bash
   ssh gaguilar@172.16.0.101 'cd ~/git/ComfyUI && cp output/Character/kailani/portrait/<render>.png input/kailani/portrait.png'
   ```

### The CHARACTER CARD and its Voice line

The card (node 6) is the same card as in the sheet/scene flows, plus one line:

```
Voice: a young woman in her late teens with a bright, warm, slightly husky mid-high voice; …
```

Node 8 (`RegexExtract`, `^[ \t]*Voice:[ \t]*(.+)$`, multiline) pulls that line out and feeds it to the
TTS `instruct` input. The whole card (including the Voice line) also goes into the video prompt.
Write the Voice line in English even for Spanish scripts: it describes timbre, age and
energy, not language. **A card without a `Voice:` line makes the TTS fail** (empty instruct).
The other Character flows don't have the Voice line yet. Copy it over if you want the cards
identical; their Qwen image encoders ignore it harmlessly.

**Voice consistency across clips.** VoiceDesign creates the voice from the description each
run. The same Voice line + the same TTS seed (4242, fixed) gives a very similar voice, but it isn't
bit-identical across different scripts. For a locked voice, save one good `voice_*.mp3` and switch
to `FB_Qwen3TTSVoiceClone` with it as `ref_audio`. That uses the Base model, which is already on
the host at `models/qwen-tts/Qwen3-TTS-12Hz-1.7B-Base`. This flow doesn't do that yet.

## Resolution / length

- **640×640** (template default). Change it on node 21; the extend nodes take the size from the
  latent. Both sides must be multiples of 16. Non-square portraits work (e.g. 576×704), but
  match the portrait's aspect.
- **77 frames per chunk** (S2V needs ≥73). Video = 5 s × chunks, at 16 fps.

## Performance (R9700 32 GB, measured 2026-10-02, 3 chunks, 640×640, 4 steps)

| Stage | Time |
|---|---|
| TTS (VoiceDesign 1.7B, first load included), 13.7 s of speech | ≈ 74 s |
| S2V 14B fp8 load + LoRA | ≈ 75 s |
| Chunk 1 sampling (4 steps, includes warm-up) | ≈ 164 s |
| Chunks 2 and 3 | ≈ 93 s each |
| Decode + mux + save | ≈ 48 s |
| **Total, cold** | **≈ 9.5 min** |

Call `free_vram` (c-comfyui-mcp) first when the previous job used Qwen image models, as in
`character-scene-animate`.

## Status

**English: rendered and checked 2026-10-02.** `talk_00001_.mp4` is 640×640, 16 fps, 238 frames,
14.9 s, H.264 + AAC. The speech track is 13.7 s at −20.5 dB mean / −3.4 dB peak.
- **Speech content:** a Whisper-small transcription of `voice_00001.mp3` reads back the script
  word for word: "Hey, I'm Kailani. Every morning I paddle out before sunrise when the water
  is glassy and the beach is still asleep. Big waves? I love them. A little scary, sure. But
  that's the fun part."
- **Video:** a contact sheet of every 24th frame keeps Kailani on-model for all 15 s: face,
  turquoise eyes, blue-tipped hair and coral rash guard all hold. Expressions change (open-mouth
  laugh, smile, raised brows). A mouth crop of frames 40–63 shows varied visemes (wide open,
  rounded "o", closed lips), so the lip motion is audio-driven, not a frozen face.
- The last ~1 s after the speech ends is an idle smile, as expected (13.7 s speech in 15 s of video).
- I checked frames and transcripts. **I did not hear the audio**, so judge the voice timbre and
  the A/V sync by ear before you rely on it.

**Spanish: rendered and checked 2026-10-02** (same flow; only SCRIPT/PERFORMANCE changed,
TTS language left on `Auto`). `talk-es_00001_.mp4` is 640×640, 238 frames, 14.9 s.
- **Speech content:** Whisper-small reads `voice-es_00001.mp3` back as Spanish: "Hola, soy Kailani.
  Cada mañana salgo a remar ante Salamaneser [antes del amanecer], cuando el agua está como un
  espejo y la playa todavía dorme. Hola [¿Olas], grandes, me encantan. Dan un poco de miedo, sí,
  pero ese es lo divertido." The bracketed misreads are homophone errors typical of the small model.
  `Auto` picked Spanish correctly.
- **Video:** on-model for all 15 s. The mouth crop shows opening/closing that follows the speech,
  with somewhat more smiling than the English take.
- **Found: Spanish is slower.** The 36-word line ran 16.9 s, so the video (and its muxed audio)
  ends at 14.9 s and the last ~2 s ("…¡pero eso es lo divertido!") are cut. The length guidance
  (node 36, SCRIPT title, this README) now gives separate EN/ES word budgets. The Spanish test
  line needs to lose ~6 words, or add a 4th chunk.

QC method: `ffprobe` for durations and streams, ffmpeg contact sheets (every 24th frame plus a
mouth crop), and `openai/whisper-small` on the host CPU (cached in `~/.cache/huggingface`).

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

"photorealistic" was removed from the NEGATIVE prompt (16). It actively fought photographic cards.

## Default card: photorealistic Kailani (2026-10-05)

The CHARACTER CARD now holds a **photorealistic** Kailani (`Scope: Live-action film`,
`Art style: photorealistic photograph …`), now a woman in her early twenties
(the original card said "teenage"). The original anime card is kept verbatim in the
**EXAMPLE CARD — Kailani, original anime** MarkdownNote, right under the card in the
same group. Copy it back into the card to render the drawn version, and switch the
upscaler to `anime_6B` too.

The card's `Voice:` line is kept on both versions. In the photo card its age now
reads "in her early twenties" to match the character. The image this flow animates
comes from the scene flow, so render a photographic scene first.
