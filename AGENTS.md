# AGENTS.md — ComfyUI workspace notes

## Remote ComfyUI host
- Runs at **172.16.0.101:8188** (Linux, ROCm, AMD GPU ~16GB, ComfyUI **0.38.0** — verify with
  `comfyui_get_system_stats` if a node behaves unexpectedly; this line drifts).
- Reachable from this machine over the network: `http://172.16.0.101:8188`.
- SSH access as normal user: `ssh gaguilar@172.16.0.101` (BatchMode keys work).
- ComfyUI code+models on the host: `~/git/ComfyUI/` (models in `~/git/ComfyUI/models/`).

## RULE: reach ComfyUI through c-comfyui-mcp tools, never raw HTTP
Do **not** hand-roll ComfyUI requests. No `curl http://172.16.0.101:8188/...`, no
`wget`, no `python -c "requests.post(...)"`, no `POST /prompt` typed by hand, and no
`npx comfyui-mcp@latest`. Those paths are how this workspace produced a silently
broken render: a payload with link refs rewritten from `["3", 0]` to
`{"item": ["3", "0"]}`, every scalar stringified, and only one node of the graph
actually executed. **The tool layer owns transport; the model layer owns intent.**

Exception: `ssh gaguilar@172.16.0.101 "<cmd>"` for host-level work that has no MCP
tool (the CivitAI download script, `nvidia-smi`/`rocm-smi`, editing files under
`~/git/ComfyUI/`). Files on the remote host are not ComfyUI access.

### Tool map — what to call instead
Use the **`c-comfyui-mcp`** server (tools below). The stock `comfyui` server
(`comfyui_*`, `npx comfyui-mcp@latest`) stays registered only for reading
`panel_*`/host-console state; **do not render through it** — it is the one that
mangled the payload described above.

| Intent | Tool (`c-comfyui-mcp`) |
|---|---|
| Check server / GPU / versions | `c-comfyui-mcp__system_stats` — first call before a long run |
| List / read a saved workflow | `c-comfyui-mcp__userdata_list`, `c-comfyui-mcp__userdata_read` |
| Inspect a graph's nodes, links, schemas | `c-comfyui-mcp__graph_convert`, `c-comfyui-mcp__graph_subgraph`, `c-comfyui-mcp__node_schema` |
| Edit a saved workflow | `c-comfyui-mcp__graph_edit` (`write_to` to persist) |
| Validate without editing | `c-comfyui-mcp__validate_workflow` (adds model rules to the structural check) |
| **Submit and wait for a render** | `c-comfyui-mcp__enqueue_workflow` — **blocking by default** |
| Poll / attach to a run | `c-comfyui-mcp__queue_status` (one prompt id, one verdict), `c-comfyui-mcp__queue_list`, `c-comfyui-mcp__queue_wait` |
| **Follow a long run live** | `c-comfyui-mcp__queue_progress` (node + step snapshot); for continuous updates run `node ~/git/c-comfyui-mcp/bin/comfy-watch.js <prompt_id>` under the **Monitor** tool — one notification per node/step, exits on done/error. Don't loop `queue_wait`. |
| Cancel a run | `c-comfyui-mcp__queue_cancel` (`clear_pending:true` empties the queue) |
| **Look at an output image** | `c-comfyui-mcp__image_get` with the filename a run reported |
| Which models exist | `c-comfyui-mcp__node_schema` on the loader node — its dropdown lists the server's real files |

`enqueue_workflow` returns the terminal state plus the output files in **one**
call, because it waits for you. Use `queue_status`/`queue_wait` only when that
call timed out or to pick up a run started from the web UI.

If `c-comfyui-mcp__*` is not in your tool list, the server was not connected when
the session started — ask the user to restart/reconnect rather than falling back
to the stock server.

### Rules that follow from using the tools
- Never hand-build the API payload. Load the graph (`source.userdata` /
  `source.filename`) and let the tool convert it; the converter expands subgraph
  instances, keeps link refs as `[nodeId, slot]`, and preserves JSON types.
- A saved workflow may contain **subgraph instances**. The backend cannot execute
  them; they must be expanded. `enqueue_workflow` does this automatically
  and reports what it expanded — if you see `expanded` in the result, the graph you
  read is not the graph that ran.
- Frontend-only annotation nodes (`Note`) make a prompt unsubmittable
  (`missing_node_type`). The submit path drops port-less unregistered nodes and
  reports them under `dropped_frontend_nodes`.
- `structural.ok === false` means nothing was submitted and the result lists the
  errors. Fix them, or pass `skip_validation` only when you already know why they
  are acceptable.
- A run that reports `state:"unknown"` did **not** execute. Never present an
  unknown prompt id as a success.

## Project layout
- See `README.md` for the full project structure and how to push flows to the remote.
- Shared subgraph library: `flows/common/README.md` (components, UUIDs, model tables).

## Workflow files
- Canonical flows live in the remote **userdata** dir under `workflows/`, e.g.
  `workflows/Character/character-sheet-v3.json`.
  - Read/write through MCP: `c-comfyui-mcp__userdata_read` (by library name, e.g.
    `Character/character-sheet-v3.json`) or
    `c-comfyui-mcp__graph_edit` with `write_to`. Slash-separated library names,
    **not** percent-encoded paths.
  - If you must touch the raw endpoint from a script on the remote host, use the
    deployed MCP transport (`~/git/c-comfyui-mcp/src/comfy.js`) rather than ad-hoc
    HTTP.
- Local mirror of templates/dev scripts: `flows/` in this directory.
- Workflow **tools** (not art flows) go under `workflows/tools/` remotely and
  `tools/` locally, e.g. `prompt-from-image-v1.json`.

## Rule: every flow needs a README — naming depends on whether it's independent
Every flow (a workflow JSON under `workflows/`/`flows/`) must be accompanied by a
doc file — no exceptions, not even for quick/experimental flows. **Which filename**
depends on the shape of the thing being documented:
- **One independent flow** (a single workflow JSON that stands alone): the doc is
  named `<flow-name>_README.md`, sitting right next to that JSON file — e.g.
  `character-sheet.json` → `character-sheet_README.md`.
- **A workflow composed of several flow files that work together** (variants,
  stages, or companion pieces meant to be read as one unit — e.g. the `3D/`
  family): put all of those flow files in one folder, and the doc for the whole
  folder is named plainly `README.md` (no prefix), sitting in that folder.

Either way it must describe:
- Which checkpoint/GGUF, CLIP, and VAE the flow(s) load.
- Every LoRA in the stack: filename, strength, trigger words, and CivitAI link
  (see `flows/common/README.md` for the table format to copy).
- Which stage groups exist and which are bypassable (and how to toggle them).
- Native/delivery resolution and any usage guideline specific to the flow.
Keep it in `flows/<Category>/` in this repo (as `<flow-name>_README.md` or
`README.md` per the rule above), and mirror it to the remote userdata folder
alongside the JSON when that flow has its own remote subfolder. Treat a structural
edit to a flow (new stage, new LoRA, new bypass) that doesn't update its doc as an
incomplete edit. See `comfyui-flow-authoring` skill, Rule 0, for the full write-up.

## Downloading CivitAI models — ALWAYS on the remote host, never this machine
Rule: **never download model files into this host.** Run the script directly on 172.16.0.101 so the file lands in `~/git/ComfyUI/models/<folder>/`.

Script (already deployed): **`~/git/civitai_dl.sh`** on the remote host.
- Token lives at `~/.config/civitai_token` on the remote host (also honors `$CIVITAI_API_KEY`).
- Accepts a bare model-version id **or a full download URL**.
- Auto-routes the file to the right subfolder from the model type (LORA→loras, Checkpoint→checkpoints, etc.); you can force a folder or output filename as extra args.

Usage examples (run via ssh):

```bash
# bare version id
ssh gaguilar@172.16.0.101 "~/git/civitai_dl.sh <version_id>"

# full URL with fileId (what the browser download link is)
ssh gaguilar@172.16.0.101 "~/git/civitai_dl.sh 'https://civitai.com/api/download/models/<version_id>?fileId=<file_id>'"

# force subfolder + filename
ssh gaguilar@172.16.0.101 "~/git/civitai_dl.sh <version_id> loras my_lora.safetensors"
```

Notes:
- The script uses `https://civitai.com/api/v1/model-versions/<vid>` for metadata and `https://civitai.com/api/download/models/<vid>` (or the given URL) for the bytes; gated models require the token.
- After downloads, refresh ComfyUI model lists (or restart the server) so new files appear in loaders.
