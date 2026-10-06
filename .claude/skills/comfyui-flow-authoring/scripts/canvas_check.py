#!/usr/bin/env python3
"""Check a ComfyUI UI-format workflow against the project's canvas layout rules.

    python3 canvas_check.py flow.json [flow2.json ...]

Rules (SKILL.md, Rule 3):
  1. No two nodes overlap.
  2. A group fully contains every node inside it, with >= MIN_PAD px on every side
     (the top margin is measured from below the group's title bar).
  3. Groups are >= MIN_GAP px apart on every side.

Geometry follows LiteGraph: a node's `pos` is the top-left of its BODY; its title
bar sits above it, so the node box is [x, y - 30, w, h + 30]. A group's `bounding`
is [x, y, w, h] with its ~34px title drawn inside the top edge. A node belongs to
the group that contains its centre; a node that merely touches a group it does not
belong to is a violation (half in, half out).

Exit status 1 when any rule is broken, so it can gate a write.
"""
import json
import sys

NODE_TITLE = 30
GROUP_TITLE = 34
MIN_PAD = 50
MIN_GAP = 50


def node_box(n):
    x, y = n["pos"]
    w, h = n.get("size") or [0, 0]
    if (n.get("flags") or {}).get("collapsed"):
        h = 0
    return (x, y - NODE_TITLE, w, h + NODE_TITLE)


def overlap(a, b, gap=0):
    return not (a[0] + a[2] + gap <= b[0] or b[0] + b[2] + gap <= a[0]
                or a[1] + a[3] + gap <= b[1] or b[1] + b[3] + gap <= a[1])


def contains_point(g, x, y):
    return g[0] <= x <= g[0] + g[2] and g[1] <= y <= g[1] + g[3]


def check(wf):
    nodes = wf.get("nodes", [])
    groups = wf.get("groups", [])
    errors = []
    boxes = {n["id"]: node_box(n) for n in nodes}

    ids = sorted(boxes)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            if overlap(boxes[a], boxes[b]):
                errors.append(f"rule 1: nodes {a} and {b} overlap")

    for nid, box in boxes.items():
        cx, cy = box[0] + box[2] / 2, box[1] + box[3] / 2
        homes = [g for g in groups if contains_point(g["bounding"], cx, cy)]
        home = min(homes, key=lambda g: g["bounding"][2] * g["bounding"][3]) if homes else None
        for g in groups:
            if g is not home and overlap(box, g["bounding"]):
                errors.append(f"rule 2: node {nid} sticks into group {g['id']} \"{g['title'][:40]}\" without belonging to it")
        if home:
            gx, gy, gw, gh = home["bounding"]
            margins = {
                "left": box[0] - gx,
                "right": gx + gw - (box[0] + box[2]),
                "top (below title)": box[1] - (gy + GROUP_TITLE),
                "bottom": gy + gh - (box[1] + box[3]),
            }
            for side, m in margins.items():
                if m < MIN_PAD:
                    errors.append(f"rule 2: node {nid} is {m:.0f}px from the {side} of group {home['id']} \"{home['title'][:40]}\" (min {MIN_PAD})")

    for i, a in enumerate(groups):
        for b in groups[i + 1:]:
            if overlap(a["bounding"], b["bounding"], gap=MIN_GAP):
                errors.append(f"rule 3: groups {a['id']} \"{a['title'][:30]}\" and {b['id']} \"{b['title'][:30]}\" are closer than {MIN_GAP}px")
    return errors


def main(paths):
    bad = False
    for path in paths:
        errors = check(json.load(open(path)))
        if errors:
            bad = True
            print(f"FAIL {path} ({len(errors)} violation(s))")
            for e in errors:
                print("  " + e)
        else:
            print(f"OK   {path}")
    return 1 if bad else 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1:]))
