#!/usr/bin/env python3
"""Build the shared subgraph library (workflows/common).

Every component is assembled from REAL nodes copied out of an existing flow, so widget
values, sizes and node properties are exactly what those flows already run. Each master
file is shaped like a frontend subgraph blueprint: the root graph holds a single instance
node and `definitions.subgraphs` holds its one definition. The same file therefore opens
as a normal workflow and can be published unchanged under userdata `subgraphs/`.

UUIDs are uuid5 of the component slug, so a rebuild keeps the id every flow embeds.
`adopt()` can keep an id that flows already embed instead.

    python3 common_subgraphs.py --src <snapshot of workflows/> --out <dir>
"""
import argparse
import copy
import json
import os
import uuid

NS = uuid.UUID('6f1c2a7e-0b9d-4c55-9a51-0c0ffee0c0de')
VIN, VOUT = -10, -20


def uid(*parts):
    return str(uuid.uuid5(NS, '/'.join(parts)))


class Src:
    """Read-only access to the flow snapshot, root and subgraph nodes alike."""

    def __init__(self, root):
        self.root, self.cache = root, {}

    def flow(self, path):
        if path not in self.cache:
            with open(os.path.join(self.root, path)) as f:
                self.cache[path] = json.load(f)
        return self.cache[path]

    def node(self, path, nid, sub=None):
        g = self.flow(path)
        nodes = g['nodes'] if sub is None else next(
            s for s in g['definitions']['subgraphs'] if s['name'].startswith(sub))['nodes']
        return copy.deepcopy(next(n for n in nodes if n['id'] == nid))

    def subgraph(self, path, name):
        g = self.flow(path)
        return copy.deepcopy(next(s for s in g['definitions']['subgraphs'] if s['name'].startswith(name)))


class SG:
    def __init__(self, slug, name, description, sg_id=None):
        self.slug, self.name, self.description = slug, name, description
        self.id = sg_id or uid('sg', slug)
        self.nodes, self.links, self.ins, self.outs = [], [], [], []
        self.next_link = 1

    # -- nodes -------------------------------------------------------------
    def add(self, node, nid, col, row=0, title=None, widgets=None):
        n = node
        n['id'], n['mode'] = nid, 0
        n['_cell'] = (col, row)  # resolved to a size-aware pos by _layout()
        n.pop('order', None)
        if title:
            n['title'] = title
        for i in n.get('inputs', []):
            i['link'] = None
        for o in n.get('outputs', []):
            o['links'] = []
        if 'widgets_values_named' not in n and n.get('widgets_values'):
            n['widgets_values_named'] = self._named(n)
        for k, v in (widgets or {}).items():
            self._set_widget(n, k, v)
        self.nodes.append(n)
        return n

    def _set_widget(self, n, name, value):
        named = n.get('widgets_values_named')
        if not isinstance(named, dict) or name not in named:
            raise SystemExit(f'{self.slug}: node {n["id"]} {n["type"]} has no named widget {name!r}; '
                             f'known: {list((named or {}).keys())}')
        names = list(named.keys())
        named[name] = value
        n['widgets_values'][self._widget_index(n, names, name)] = value

    @staticmethod
    def _named(n):
        """widgets_values keyed by the node's widget inputs, skipping a seed's control slot."""
        vals, out, idx = n['widgets_values'], {}, 0
        for inp in n.get('inputs', []):
            if not inp.get('widget') or idx >= len(vals):
                continue
            out[inp['name']] = vals[idx]
            idx += 1
            if inp['name'] in ('seed', 'noise_seed') and idx < len(vals) and \
                    vals[idx] in ('fixed', 'randomize', 'increment', 'decrement'):
                idx += 1
        return out

    @staticmethod
    def _widget_index(n, names, name):
        # widgets_values carries an extra control_after_generate slot right after a seed.
        idx = 0
        for k in names:
            if k == name:
                return idx
            idx += 1
            if k in ('seed', 'noise_seed') and idx < len(n['widgets_values']) and \
                    n['widgets_values'][idx] in ('fixed', 'randomize', 'increment', 'decrement'):
                idx += 1
        raise KeyError(name)

    def by(self, nid):
        return next(n for n in self.nodes if n['id'] == nid)

    def _slot(self, n, name, typ=None):
        for i, inp in enumerate(n.get('inputs', [])):
            if inp['name'] == name:
                return i
        if typ is None:
            raise SystemExit(f'{self.slug}: node {n["id"]} {n["type"]} has no input {name!r}; '
                             f'inputs: {[i["name"] for i in n.get("inputs", [])]}')
        n.setdefault('inputs', []).append(
            {'localized_name': name, 'name': name, 'type': typ, 'widget': {'name': name}, 'link': None})
        return len(n['inputs']) - 1

    def _link(self, o, os_, t, ts, typ):
        lid = self.next_link
        self.next_link += 1
        self.links.append({'id': lid, 'origin_id': o, 'origin_slot': os_,
                           'target_id': t, 'target_slot': ts, 'type': typ})
        return lid

    # -- wiring ------------------------------------------------------------
    def wire(self, src, slot, dst, name, typ=None):
        s, d = self.by(src), self.by(dst)
        ts = self._slot(d, name, typ)
        t = typ or s['outputs'][slot]['type']
        lid = self._link(src, slot, dst, ts, t)
        s['outputs'][slot]['links'].append(lid)
        d['inputs'][ts]['link'] = lid

    def expose_in(self, name, typ, targets, default=None):
        """targets: [(node_id, input_name)]. A widget-backed target makes this a promoted widget."""
        slot = len(self.ins)
        lids, widget = [], False
        for nid, iname in targets:
            d = self.by(nid)
            ts = self._slot(d, iname, typ)
            widget = widget or bool(d['inputs'][ts].get('widget'))
            lid = self._link(VIN, slot, nid, ts, typ)
            d['inputs'][ts]['link'] = lid
            lids.append(lid)
        self.ins.append({'name': name, 'type': typ, 'linkIds': lids, 'widget': widget, 'default': default})

    def expose_out(self, name, typ, src, slot):
        s = self.by(src)
        lid = self._link(src, slot, VOUT, len(self.outs), typ)
        s['outputs'][slot]['links'].append(lid)
        self.outs.append({'name': name, 'type': typ, 'linkIds': [lid]})

    # -- output ------------------------------------------------------------
    GAP = 80
    TITLE = 30

    def _layout(self):
        """Columns as wide as their widest node; nodes stacked by real height (Rule 3: no overlap)."""
        size = lambda n: n.get('size') or [300, 100]
        cols = sorted({n['_cell'][0] for n in self.nodes if '_cell' in n})
        x = 0
        for c in cols:
            members = sorted((n for n in self.nodes if n.get('_cell', (None,))[0] == c), key=lambda n: n['_cell'][1])
            y = 0
            for n in members:
                n['pos'] = [x, y]
                y += size(n)[1] + self.TITLE + self.GAP
                del n['_cell']
            x += max(size(n)[0] for n in members) + self.GAP

    def definition(self):
        if any('_cell' in n for n in self.nodes):
            self._layout()
        width = max([n['pos'][0] + n.get('size', [300, 100])[0] for n in self.nodes] + [0])
        return {
            'id': self.id, 'version': 1,
            'state': {'lastGroupId': 0, 'lastNodeId': max(n['id'] for n in self.nodes),
                      'lastLinkId': self.next_link - 1, 'lastRerouteId': 0},
            'revision': 0, 'config': {}, 'name': self.name, 'description': self.description,
            'inputNode': {'id': VIN, 'bounding': [-400, 0, 140, 40 + 20 * len(self.ins)]},
            'outputNode': {'id': VOUT, 'bounding': [width + 120, 0, 140, 40 + 20 * max(1, len(self.outs))]},
            'inputs': [{'id': uid('in', self.slug, p['name']), 'name': p['name'], 'type': p['type'],
                        'linkIds': p['linkIds'], 'localized_name': p['name'], 'pos': [-300, 20 + 20 * i]}
                       for i, p in enumerate(self.ins)],
            'outputs': [{'id': uid('out', self.slug, p['name']), 'name': p['name'], 'type': p['type'],
                         'linkIds': p['linkIds'], 'localized_name': p['name'],
                         'pos': [width + 140, 20 + 20 * i]} for i, p in enumerate(self.outs)],
            'widgets': [], 'nodes': self.nodes, 'groups': [], 'links': self.links,
            'extra': {'workflowRendererVersion': 'LG'},
        }

    def instance(self, nid=1, pos=(0, 0), title=None):
        widgets = [p for p in self.ins if p['widget']]
        return {
            'id': nid, 'type': self.id, 'pos': list(pos),
            'size': [380, 46 + 24 * (len(self.ins) + len(widgets))],
            'flags': {}, 'order': 0, 'mode': 0,
            'inputs': [dict({'localized_name': p['name'], 'name': p['name'], 'type': p['type'], 'link': None},
                            **({'widget': {'name': p['name']}} if p['widget'] else {})) for p in self.ins],
            'outputs': [{'localized_name': p['name'], 'name': p['name'], 'type': p['type'], 'links': []}
                        for p in self.outs],
            'title': title or self.name,
            'properties': {'proxyWidgets': [['-1', p['name']] for p in widgets], 'cnr_id': 'comfy-core'},
            'widgets_values': [p['default'] for p in widgets],
            'widgets_values_named': {p['name']: p['default'] for p in widgets},
        }

    def blueprint(self):
        return {
            'id': uid('wf', self.slug), 'revision': 0, 'last_node_id': 1, 'last_link_id': 0,
            'nodes': [self.instance()], 'links': [], 'groups': [],
            'definitions': {'subgraphs': [self.definition()]},
            'config': {}, 'extra': {'common_subgraph': {'slug': self.slug, 'id': self.id}}, 'version': 0.4,
        }


def adopt(slug, folder, sub, sg_id=None, name=None, defaults=None):
    """Wrap an existing definition (already a subgraph somewhere) as a library master."""
    sub = copy.deepcopy(sub)
    sub['id'] = sg_id or sub['id']
    sub['name'] = name or sub['name']
    for n in sub['nodes']:
        n['mode'] = 0  # on/off belongs to the instance, never to inner nodes
    sg = SG(slug, sub['name'], sub.get('description', ''), sub['id'])
    by = {n['id']: n for n in sub['nodes']}
    sg.ins = []
    for p in sub['inputs']:
        tgt = next(l for l in sub['links'] if l['id'] == p['linkIds'][0])
        widget = bool(by[tgt['target_id']]['inputs'][tgt['target_slot']].get('widget'))
        sg.ins.append({'name': p['name'], 'type': p['type'], 'linkIds': p['linkIds'], 'widget': widget,
                       'default': (defaults or {}).get(p['name'])})
    sg.outs = [{'name': p['name'], 'type': p['type'], 'linkIds': p['linkIds']} for p in sub['outputs']]
    sg.definition = lambda: sub
    return folder, sg


# ---------------------------------------------------------------------------
# Component specs. Sources are the remote flows as of 2026-10-06.
# ---------------------------------------------------------------------------
V3 = 'Character/character-sheet-v3.json'
V1 = 'Character/character-sheet.json'
ANIM = 'Character/character-scene-animate.json'


def build(src):
    out = []

    # C1 — Qwen-Image 2.1 model trio
    sg = SG('qwen21-uc-models', 'Qwen 2.1 models — GGUF Q8 + Qwen3-VL TE + 2.1 VAE',
            'UnetLoaderGGUF qwen-image-2.1-UC-Q8_0 + CLIPLoader (qwen_image) + VAELoader qwen_image_2.1_vae_bf16. '
            'TorchCompile and the LoRA slot stay outside so they remain bypassable.')
    sg.add(src.node(V3, 1), 1, 0, 0)
    sg.add(src.node(V3, 2), 2, 0, 1)
    sg.add(src.node(V3, 3), 3, 0, 2)
    sg.expose_in('clip_name', 'COMBO', [(2, 'clip_name')], 'qwen3vl_8b_ablit_int8.safetensors')
    sg.expose_in('clip_device', 'COMBO', [(2, 'device')], 'default')
    sg.expose_out('MODEL', 'MODEL', 1, 0)
    sg.expose_out('CLIP', 'CLIP', 2, 0)
    sg.expose_out('VAE', 'VAE', 3, 0)
    out.append(('common', sg))

    # C5 — character card + panel template
    sg = SG('card-compose', 'Card compose — card + template → prompt',
            'StringConcatenate(card, template, "\\n\\n"): card first, then the character-neutral template.')
    sg.add(src.node(V3, 220, 'Qwen panel'), 1, 0)
    sg.expose_in('card', 'STRING', [(1, 'string_a')], '')
    sg.expose_in('template', 'STRING', [(1, 'string_b')], '')
    sg.expose_out('STRING', 'STRING', 1, 0)
    out.append(('common', sg))

    # C2 — Qwen panel: compose → encode (≤4 refs) → sample → decode → save
    sg = SG('qwen-panel', 'Qwen panel — card + template → image',
            'Card+template compose, TextEncodeQwenImage21 with up to 4 reference images, KSampler '
            '(seed 424242 fixed, euler/simple, denoise 1), VAEDecode, SaveImage. Explicit inputs, no hidden Get nodes.')
    sg.add(src.node(V3, 220, 'Qwen panel'), 1, 0)
    sg.add(src.node(V3, 221, 'Qwen panel'), 2, 1)
    sg.add(src.node(V3, 5, 'Qwen panel'), 3, 2)
    sg.add(src.node(V3, 6, 'Qwen panel'), 4, 3)
    sg.add(src.node(V3, 7, 'Qwen panel'), 5, 4)
    sg.wire(1, 0, 2, 'prompt')
    sg.wire(2, 0, 3, 'positive')
    sg.wire(2, 1, 3, 'negative')
    sg.wire(2, 2, 3, 'latent_image')
    sg.wire(3, 0, 4, 'samples')
    sg.wire(4, 0, 5, 'images')
    sg.expose_in('model', 'MODEL', [(3, 'model')])
    sg.expose_in('clip', 'CLIP', [(2, 'clip')])
    sg.expose_in('vae', 'VAE', [(2, 'vae'), (4, 'vae')])
    for i in range(1, 5):
        sg.expose_in(f'ref_{i}', 'IMAGE', [(2, f'images.image_{i}')])
    sg.expose_in('card', 'STRING', [(1, 'string_a')], '')
    sg.expose_in('template', 'STRING', [(1, 'string_b')], '')
    sg.expose_in('negative', 'STRING', [(2, 'negative_prompt')], '')
    sg.expose_in('resolution', 'INT', [(2, 'resolution')], 768)
    sg.expose_in('steps', 'INT', [(3, 'steps')], 30)
    sg.expose_in('cfg', 'FLOAT', [(3, 'cfg')], 4.5)
    sg.expose_in('filename_prefix', 'STRING', [(5, 'filename_prefix')], 'Character/x')
    sg.expose_out('IMAGE', 'IMAGE', 4, 0)
    out.append(('common', sg))

    # C3a — ESRGAN x4 then rescale (net x2 at 0.5)
    sg = SG('esrgan-upscale-rescale', 'ESRGAN x4 → rescale → save',
            'ImageRemoveAlpha+ → ImageUpscaleWithModel → ImageScaleBy (lanczos) → SaveImage. scale_by 0.5 = net x2.')
    sg.add(src.node(V1, 23), 1, 0)
    sg.add(src.node(V1, 24), 2, 1)
    sg.add(src.node(V1, 45), 3, 2)
    sg.add(src.node(V1, 25), 4, 3)
    sg.wire(1, 0, 2, 'image')
    sg.wire(2, 0, 3, 'image')
    sg.wire(3, 0, 4, 'images')
    sg.expose_in('image', 'IMAGE', [(1, 'image')])
    sg.expose_in('upscale_model', 'UPSCALE_MODEL', [(2, 'upscale_model')])
    sg.expose_in('scale_by', 'FLOAT', [(3, 'scale_by')], 0.5)
    sg.expose_in('filename_prefix', 'STRING', [(4, 'filename_prefix')], 'Character/x_x2')
    sg.expose_out('IMAGE', 'IMAGE', 3, 0)
    out.append(('common', sg))

    # C3b — ESRGAN x4 (v3 variant, no rescale)
    sg = SG('esrgan-x4', 'ESRGAN x4 → save',
            'ImageRemoveAlpha+ → ImageUpscaleWithModel → SaveImage. Full x4, no resampling pass.')
    sg.add(src.node(V3, 228, 'ESRGAN'), 1, 0)
    sg.add(src.node(V3, 229, 'ESRGAN'), 2, 1)
    sg.add(src.node(V3, 230, 'ESRGAN'), 3, 2)
    sg.wire(1, 0, 2, 'image')
    sg.wire(2, 0, 3, 'images')
    sg.expose_in('image', 'IMAGE', [(1, 'image')])
    sg.expose_in('upscale_model', 'UPSCALE_MODEL', [(2, 'upscale_model')])
    sg.expose_in('filename_prefix', 'STRING', [(3, 'filename_prefix')], 'Character/x_x4')
    sg.expose_out('IMAGE', 'IMAGE', 2, 0)
    out.append(('common', sg))

    # C4 — 2×2 sheet
    sg = SG('sheet-2x2', 'Sheet 2×2 — stitch four panels → save',
            'ImageStitch(1 right 2), ImageStitch(3 right 4), ImageStitch(top down bottom), spacing 0 → SaveImage.')
    sg.add(src.node(V1, 35), 1, 0, 0)
    sg.add(src.node(V1, 36), 2, 0, 1)
    sg.add(src.node(V1, 37), 3, 1)
    sg.add(src.node(V1, 38), 4, 2)
    sg.wire(1, 0, 3, 'image1')
    sg.wire(2, 0, 3, 'image2')
    sg.wire(3, 0, 4, 'images')
    sg.expose_in('image_1', 'IMAGE', [(1, 'image1')])
    sg.expose_in('image_2', 'IMAGE', [(1, 'image2')])
    sg.expose_in('image_3', 'IMAGE', [(2, 'image1')])
    sg.expose_in('image_4', 'IMAGE', [(2, 'image2')])
    sg.expose_in('filename_prefix', 'STRING', [(4, 'filename_prefix')], 'Character/x/sheet')
    sg.expose_out('IMAGE', 'IMAGE', 3, 0)
    out.append(('common', sg))

    # C8 — RGBA cutout
    sg = SG('rgba-cutout', 'RGBA cutout — BiRefNet → transparent PNG',
            'RemoveBackground → InvertMask → JoinImageWithAlpha → SaveImage. Background model passed in.')
    sg.add(src.node(V3, 223, 'RGBA'), 1, 0)
    sg.add(src.node(V3, 224, 'RGBA'), 2, 1)
    sg.add(src.node(V3, 225, 'RGBA'), 3, 2)
    sg.add(src.node(V3, 226, 'RGBA'), 4, 3)
    orig = src.subgraph(V3, 'RGBA')
    bgtype = next(n for n in orig['nodes'] if n['id'] == 222)['outputs'][0]['type']
    for l in orig['links']:  # replay the definition's own inner wiring
        if l['origin_id'] in (223, 224, 225) and l['target_id'] in (224, 225, 226):
            m = {223: 1, 224: 2, 225: 3, 226: 4}
            sg.wire(m[l['origin_id']], l['origin_slot'], m[l['target_id']],
                    sg.by(m[l['target_id']])['inputs'][l['target_slot']]['name'])
    img_targets = [({223: 1, 225: 3}[l['target_id']], sg.by({223: 1, 225: 3}[l['target_id']])['inputs'][l['target_slot']]['name'])
                   for l in orig['links'] if l['origin_id'] == VIN and l['origin_slot'] == 0]
    sg.expose_in('image', 'IMAGE', img_targets)
    sg.expose_in('bg_model', bgtype, [(1, next(i['name'] for i in sg.by(1)['inputs'] if i['type'] == bgtype))])
    sg.expose_in('filename_prefix', 'STRING', [(4, 'filename_prefix')], 'Character/x_rgba')
    sg.expose_out('IMAGE', 'IMAGE', 3, 0)
    out.append(('common', sg))

    # C9a — Wan 2.2 I2V A14B models
    sg = SG('wan22-i2v-models', 'Wan 2.2 I2V A14B models — high + low fp8, umt5, Wan 2.1 VAE',
            'UNETLoader high/low noise fp8, CLIPLoader umt5 (wan), VAELoader wan_2.1_vae. The speed LoRA pair '
            'stays outside so it remains bypassable.')
    sg.add(src.node(ANIM, 1), 1, 0, 0)
    sg.add(src.node(ANIM, 2), 2, 0, 1)
    sg.add(src.node(ANIM, 3), 3, 0, 2)
    sg.add(src.node(ANIM, 4), 4, 0, 3)
    sg.expose_out('MODEL_HIGH', 'MODEL', 1, 0)
    sg.expose_out('MODEL_LOW', 'MODEL', 2, 0)
    sg.expose_out('CLIP', 'CLIP', 3, 0)
    sg.expose_out('VAE', 'VAE', 4, 0)
    out.append(('common', sg))

    # C9b — Wan 2.2 two-stage sampler
    sg = SG('wan22-two-stage-sampler', 'Wan 2.2 two-stage sampler — high noise → low noise',
            'ModelSamplingSD3 on each model, KSamplerAdvanced high (0 → split, leftover noise) then low '
            '(split → end). steps/cfg/split exposed: 4/1/2 with lightx2v, 20/3.5/10 without.')
    sg.add(src.node(ANIM, 7), 1, 0, 0)
    sg.add(src.node(ANIM, 8), 2, 0, 1)
    sg.add(src.node(ANIM, 13), 3, 1, 0)
    sg.add(src.node(ANIM, 14), 4, 2, 0)
    sg.wire(1, 0, 3, 'model')
    sg.wire(2, 0, 4, 'model')
    sg.wire(3, 0, 4, 'latent_image')
    sg.expose_in('model_high', 'MODEL', [(1, 'model')])
    sg.expose_in('model_low', 'MODEL', [(2, 'model')])
    sg.expose_in('positive', 'CONDITIONING', [(3, 'positive'), (4, 'positive')])
    sg.expose_in('negative', 'CONDITIONING', [(3, 'negative'), (4, 'negative')])
    sg.expose_in('latent', 'LATENT', [(3, 'latent_image')])
    hi = sg.by(3)['widgets_values_named']
    sg.expose_in('steps', 'INT', [(3, 'steps'), (4, 'steps')], hi['steps'])
    sg.expose_in('cfg', 'FLOAT', [(3, 'cfg'), (4, 'cfg')], hi['cfg'])
    sg.expose_in('split_step', 'INT', [(3, 'end_at_step'), (4, 'start_at_step')], hi['end_at_step'])
    sg.expose_out('LATENT', 'LATENT', 4, 0)
    out.append(('common', sg))

    # C10a — frames → mp4
    sg = SG('video-save', 'Frames → mp4 (optional audio)',
            'CreateVideo(fps, optional audio) → SaveVideo.')
    sg.add(src.node(ANIM, 16), 1, 0)
    sg.add(src.node(ANIM, 17), 2, 1)
    sg.wire(1, 0, 2, 'video')
    sg.expose_in('frames', 'IMAGE', [(1, 'images')])
    sg.expose_in('audio', 'AUDIO', [(1, 'audio')])
    sg.expose_in('fps', 'FLOAT', [(1, 'fps')], sg.by(1)['widgets_values_named']['fps'])
    sg.expose_in('filename_prefix', 'STRING', [(2, 'filename_prefix')], sg.by(2)['widgets_values_named']['filename_prefix'])
    out.append(('common', sg))

    # C10b — RIFE x2 → mp4
    sg = SG('rife-x2-video-save', 'RIFE x2 interpolation → mp4',
            'RIFE VFI (rife49, x2) → CreateVideo(fps) → SaveVideo. Bypass the instance to skip interpolation.')
    sg.add(src.node(ANIM, 20), 1, 0)
    sg.add(src.node(ANIM, 21), 2, 1)
    sg.add(src.node(ANIM, 22), 3, 2)
    sg.wire(1, 0, 2, 'images')
    sg.wire(2, 0, 3, 'video')
    sg.expose_in('frames', 'IMAGE', [(1, 'frames')])
    sg.expose_in('fps', 'FLOAT', [(2, 'fps')], sg.by(2)['widgets_values_named']['fps'])
    sg.expose_in('filename_prefix', 'STRING', [(3, 'filename_prefix')], sg.by(3)['widgets_values_named']['filename_prefix'])
    sg.expose_out('IMAGE', 'IMAGE', 1, 0)
    out.append(('common', sg))

    # C12a — FaceID setup (SDXL + IPAdapter FaceID PlusV2 + InsightFace + detector + face prompts)
    sg = SG('faceid-sdxl-setup', 'FaceID setup — SDXL + IPAdapter FaceID PlusV2 + face prompts',
            'Loads the SDXL checkpoint, patches it with FaceID from every image in a folder (256 px margin, '
            'InsightFace buffalo_l on ROCM), encodes the card face prompt + negative, loads the YOLOv8m face '
            'detector. Feeds face-detail-rgba.')
    ids = {169: 1, 170: 2, 202: 3, 201: 4, 205: 5, 171: 6, 203: 7, 177: 8, 178: 9, 179: 10, 180: 11}
    cols = {169: 0, 170: 1, 202: 1, 201: 0, 205: 1, 171: 2, 203: 3, 177: 2, 178: 3, 179: 3, 180: 3}
    rows = {169: 0, 170: 0, 202: 1, 201: 2, 205: 2, 171: 0, 203: 0, 177: 3, 178: 3, 179: 4, 180: 5}
    for o, n in ids.items():
        sg.add(src.node(V3, o), n, cols[o], rows[o])
    g3 = src.flow(V3)
    for L in g3['links']:
        if L[1] in ids and L[3] in ids:
            d = sg.by(ids[L[3]])
            sg.wire(ids[L[1]], L[2], ids[L[3]], src.node(V3, L[3])['inputs'][L[4]]['name'])
    sg.expose_in('card', 'STRING', [(8, 'string_a')], '')
    sg.expose_in('face_folder', 'STRING', [(4, 'folder')], '')
    sg.expose_out('MODEL', 'MODEL', 6, 0)
    sg.expose_out('CLIP', 'CLIP', 1, 1)
    sg.expose_out('VAE', 'VAE', 1, 2)
    sg.expose_out('positive', 'CONDITIONING', 9, 0)
    sg.expose_out('negative', 'CONDITIONING', 10, 0)
    sg.expose_out('bbox_detector', 'BBOX_DETECTOR', 11, 0)
    out.append(('common', sg))

    # C12b — per-panel face detail that keeps alpha
    sg = SG('face-detail-rgba', 'Face detail (alpha-safe) — split → FaceDetailer → rejoin → save',
            'SplitImageWithAlpha → FaceDetailer (guide 512, max 768, tiled enc/dec) → JoinImageWithAlpha → SaveImage.')
    for o, n in {181: 1, 182: 2, 183: 3, 184: 4}.items():
        sg.add(src.node(V3, o), n, n - 1)
    sg.wire(1, 0, 2, 'image')
    sg.wire(2, 0, 3, 'image')
    sg.wire(1, 1, 3, 'alpha')
    sg.wire(3, 0, 4, 'images')
    sg.expose_in('image', 'IMAGE', [(1, 'image')])
    for name, typ in [('model', 'MODEL'), ('clip', 'CLIP'), ('vae', 'VAE'), ('positive', 'CONDITIONING'),
                      ('negative', 'CONDITIONING'), ('bbox_detector', 'BBOX_DETECTOR')]:
        sg.expose_in(name, typ, [(2, name)])
    sg.expose_in('filename_prefix', 'STRING', [(4, 'filename_prefix')], 'Character/x_faceid')
    sg.expose_out('IMAGE', 'IMAGE', 3, 0)
    out.append(('common', sg))

    return out


def write(specs):
    """CLI shared by every library built on these helpers: --src snapshot, --out dir."""
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    for folder, sg in specs(Src(a.src)):
        path = os.path.join(a.out, folder, sg.slug + '.json')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump(sg.blueprint(), f, indent=2, ensure_ascii=False)
        print(f'{folder}/{sg.slug}.json  {sg.id}  in={[p["name"] for p in sg.ins]}  out={[p["name"] for p in sg.outs]}')


if __name__ == '__main__':
    write(build)
