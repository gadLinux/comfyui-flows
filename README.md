# ComfyUI Flow Definitions

This project holds **automatic flow definitions** for the remote ComfyUI instance at `172.16.0.101`. Each workflow is a JSON graph that can be loaded directly into ComfyUI and queued for rendering without manual node construction.

## Layout

```
AGENTS.md          — agent instructions: remote host, download script, file conventions
README.md          — this file
flows/             — local mirror of workflow templates and dev scripts
tools/             — utility workflows (dataset prep, etc.), mirrored to remote `workflows/tools/`
faces/             — face reference photos used by FaceID / character flows
qwen21-t2i-template.json  — base Qwen-Image-2.1 txt2img template
```

## How flows work

A "flow" is a ComfyUI workflow JSON file stored in two places:

1. **Remote (canonical)**: `~/git/ComfyUI/userdata/workflows/<category>/<name>.json` on the ComfyUI host. This is what the ComfyUI web UI reads and what gets queued for rendering.
2. **Local (mirror/dev)**: `flows/` in this directory. Used for version control, script-driven generation (`make_variants.py`), and offline editing before pushing to the remote.

To push a local flow to the remote:

```bash
# percent-encode slashes in the path
WF="workflows/myflow/test.json"
ENC=$(echo "$WF" | sed 's|/|%2F|g')
curl -X POST "http://172.16.0.101:8188/userdata/$ENC" \
     -H "Content-Type: application/json" \
     -d @flows/test.json
```

Or use the `c-comfyui-mcp` tools (`graph_edit` with `write_to`, or `userdata_write`).

## Model files

All model weights (LoRAs, checkpoints, VAEs, controlnets) live on the remote host under `~/git/ComfyUI/models/`. They are **never** downloaded to this machine. Use the download script on the remote:

```bash
ssh gaguilar@172.16.0.101 "~/git/civitai_dl.sh <version_id>"
```

See `AGENTS.md` for full details and the token setup.

## Adding a new flow

1. Copy `qwen21-t2i-template.json` as a starting point, or build from scratch with `comfyui-mcp create_workflow`.
2. Edit locally in `flows/` or directly on the remote via `graph_edit`.
3. Validate: `c-comfyui-mcp_graph_edit op:"validate" userdata:"workflows/<path>"`.
4. Push to remote if edited locally (see above).
5. Test-render from the ComfyUI web UI at `http://172.16.0.101:8188`.

## Categories

| Path | Purpose |
|------|---------|
| `workflows/Character/` | Character sheet generator (Qwen-Image 2.1) — turnaround/expression/pose/costume sheets for a consistent virtual character, reused across other flows |
| `workflows/myflow/` | General / experimental flows |

## Flow documentation rule

Every flow ships with a doc file (in `flows/<Category>/` locally, and mirrored to
the remote userdata folder when the flow has its own subfolder there) describing
its models, LoRAs, bypassable stages, and usage guidelines. Naming depends on
shape: an independent single-flow JSON gets `<flow-name>_README.md` next to it
(e.g. `character-sheet.json` → `character-sheet_README.md`); a folder holding
several flow files meant to be read as one workflow gets a plain `README.md` in
that folder instead. See `AGENTS.md` and the `comfyui-flow-authoring` skill
(Rule 0) for the full requirement.

## Using this project from another repo

This repo is designed to be embedded as a **git submodule** (conventionally at
`core/`) by downstream flow projects. They reuse, without copying:

- the shared subgraph library in `flows/common/` (fixed UUIDs — never rename a slug),
- the `comfyui-flow-authoring` skill (symlink `.claude/skills/comfyui-flow-authoring`
  → `core/.claude/skills/comfyui-flow-authoring`),
- the generator helpers in `common_subgraphs.py` (`SG`, `adopt`, `Src`, `uid`, `write`)
  to build their own component libraries with UUIDs from the same namespace,
- `AGENTS.md` as the base agent rules.

Keep those interfaces stable; a breaking change here needs a submodule bump downstream.
