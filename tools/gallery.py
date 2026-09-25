#!/usr/bin/env python3
"""Every object model in the game, laid out on a grid with its number on it.

    python3 tools/gallery.py              writes out/godot/gallery.gltf and its labels
    godot-4 --path out/godot              then press K in the world

This exists because of a question no amount of reading has answered: **which
model does an object of type N actually use?** The port assumes `MO.T[type]`,
which was never checked against the game, and a player looking at the two side
by side reports armour standing where doors should be and a person where a thing
should be. The placement is not at fault — the disc records and the live table
agree on the type id for 347 of 347 slots — so it is the model lookup.

The way to settle it is to make the correspondence visible: here is every model
with its number, and there in the world is every object with its slot and its
type. Stand in the same place in both, say "that is a chest", find the chest
here, and the pair `type -> model` is one fact. A handful of those name the rule,
whether it is an offset, a table, or something else entirely.

Models are drawn at their own scale with a neutral shade rather than the
lighting of any cell, because the question is what shape a thing is, not how a
particular corner of level 0 lit it.
"""
import json
import math
import os
import sys

sys.path.insert(0, "tools")
import gltf                                                           # noqa: E402
import level3d                                                        # noqa: E402
import tmd                                                            # noqa: E402
from tarc import TArc                                                 # noqa: E402

UNIT = level3d.UNIT
SPACING = 4096          # two cells between models, room for the biggest
VIEWER_SPACING = 200000  # in the standalone viewer, far enough apart that only
                         # the one you are looking at is in the frame
PER_ROW = 20
# Godot takes at most 256 surfaces in one mesh and the whole archive needs 309,
# so the gallery goes out in pieces of a hundred models. Each comes to 159 or
# fewer, and the scene instances all of them together.
CHUNK = 100


MOF_SHOWN = 128         # enough of MOF.T to cover every type level 0 places


def entries(archive="MO"):
    t = TArc(f"extract/CD/COM/{archive}.T")
    n = t.count if isinstance(getattr(t, "count", None), int) else len(t.offs) - 1
    return n


def numbered():
    """Every model, under the number an object type reaches it by.

    The gallery is numbered the way `tmd.model_of` numbers: `MO.T` is 0 to 427
    and `MOF.T` continues from 428, so the number over a model here is the same
    number a world label's type plus 128 gives.
    """
    for i in range(entries("MO")):
        yield i, "MO", i
    for i in range(min(MOF_SHOWN, entries("MOF"))):
        yield tmd.MO_COUNT + i, "MOF", i


def build(out="out/godot", archive="MO", lv=0, spacing=None, per_row=None):
    spacing = SPACING if spacing is None else spacing
    per_row = PER_ROW if per_row is None else per_row
    vram = level3d.object_vram(lv)
    labels = []
    n_ok = n_bad = ntri = 0
    catalogue = list(numbered())
    total = len(catalogue)
    written = []

    for chunk in range((total + CHUNK - 1) // CHUNK):
        g = gltf.Gltf()
        groups = {}
        for idx, arch, entry in catalogue[chunk * CHUNK:(chunk + 1) * CHUNK]:
            try:
                _flags, objs = tmd.load(arch, entry)
            except Exception:
                n_bad += 1
                labels.append({"n": idx,
                               "x": (idx % per_row) * spacing / UNIT,
                               "z": -(idx // per_row) * spacing / UNIT,
                               "empty": True, "prims": 0, "ext": None})
                continue
            col, row = idx % per_row, idx // per_row
            ox, oz = col * spacing, row * spacing
            drawn = 0

            def place(v, ox=ox, oz=oz):
                return ((ox + v[0]) / UNIT, -v[1] / UNIT, -(oz + v[2]) / UNIT)

            before = sum(len(b[0]) for b in groups.values())
            # The same loop the world build uses, and shared with it on purpose:
            # this file had a copy that never wound a triangle to agree with the
            # model's own normal, so half of every model faced away and was
            # culled. A player saw the same helmet whole in the world and torn
            # into layers here, with "some polygons transparent" -- which is what
            # a back-facing triangle looks like against a single-sided material.
            level3d.emit_object(objs, place, lambda _raw: (0.85, 0.85, 0.85),
                                groups)
            drawn = sum(len(b[0]) for b in groups.values()) - before

            if drawn:
                n_ok += 1
            vs = [v for a in objs for v in a.verts]
            ext = None
            if vs:
                ext = [max(v[k] for v in vs) - min(v[k] for v in vs)
                       for k in range(3)]
            labels.append({"n": idx, "x": ox / UNIT, "z": -oz / UNIT,
                           "empty": drawn == 0, "archive": arch, "entry": entry,
                           "prims": sum(len(a.prims) for a in objs), "ext": ext})

        prims = []
        for (tpage, clut), (pos, nrm, uv, col) in groups.items():
            name = f"tex_{tpage:04x}_{clut:04x}"
            # The objects' own copy of the page, the one the world uses, so a
            # model looks the same here as standing in the level.
            rel = level3d.page_texture(out, lv, tpage, clut, vram)
            # Pages at 8 or 16 bits a pixel are not written -- `page4` reads four
            # -- so those primitives get a plain material rather than one naming
            # a file that is not there, which Godot reports once per primitive.
            m = (g.material(name, rel, double=True) if rel
                 else g.plain(name + "_flat", (0.8, 0.75, 0.7, 1.0)))
            pr = g.primitive(pos, nrm, uv, col)
            pr["material"] = m
            prims.append(pr)
            ntri += len(pos) // 3
        if prims:
            written.append(g.write(f"{out}/gallery{chunk}.gltf", prims,
                                   f"gallery{chunk}")[0])

    with open(f"{out}/gallery.json", "w") as f:
        json.dump({"archive": archive, "spacing": spacing / UNIT,
                   "per_row": per_row, "chunks": len(written),
                   "bias": tmd.MODEL_BIAS, "labels": labels}, f,
                  separators=(",", ":"))
    print(f"gallery: {n_ok} of {total} models drawn, {n_bad} unreadable, "
          f"{ntri} triangles in {len(written)} pieces "
          f"(MO.T 0-{tmd.MO_COUNT - 1}, then MOF.T)")
    return written


def world_labels(lv=0, out="out/godot"):
    """Where every placed object stands, with its slot and type, for the world.

    The port draws these as floating text so the two windows can be compared by
    name rather than by memory: the thing you are looking at in the game has a
    number here.
    """
    import objload
    import placement
    load = objload.Load(lv).first_frame()
    grid = level3d.grid_of(lv)
    rows = []
    for o in placement.objects(lv):
        cx, cz = o["cx"], o["cz"]
        if not (0 <= cx < level3d.W and 0 <= cz < level3d.W):
            continue
        c = grid[(cz * level3d.W + cx) * level3d.CELLB:][:level3d.CELLB]
        r = load.recs.get(o["slot"])
        rows.append({"slot": o["slot"], "type": o["type"],
                     "x": o["x"] / UNIT, "y": 128 * c[6] / UNIT,
                     "z": -o["z"] / UNIT,
                     "scale": r["scale"][0] if r else 0x1000,
                     "op": r["op"] if r else 0xFF,
                     "drawn": bool(r and load.drawn(r)),
                     "text": o["text"]})
    with open(f"{out}/objlabels{lv:02d}.json", "w") as f:
        json.dump(rows, f, separators=(",", ":"))
    print(f"object labels: {len(rows)} placed objects -> "
          f"{out}/objlabels{lv:02d}.json")


VIEWER_PROJECT = """[application]
config/name="King's Field II - model catalogue"
run/main_scene="res://view.tscn"
config/features=PackedStringArray("4.3", "Forward Plus")

[display]
window/size/viewport_width=1280
window/size/viewport_height=800

[rendering]
textures/canvas_textures/default_texture_filter=0
anti_aliasing/quality/msaa_3d=0
"""

VIEWER_SCENE = """[gd_scene load_steps={steps} format=3]

[ext_resource type="Script" path="res://viewer.gd" id="1"]
{res}

[sub_resource type="Environment" id="Env"]
background_mode = 1
background_color = Color(0.05, 0.05, 0.07, 1)
ambient_light_source = 0

[node name="View" type="Node3D"]
script = ExtResource("1")

[node name="WorldEnvironment" type="WorldEnvironment" parent="."]
environment = SubResource("Env")

[node name="Camera" type="Camera3D" parent="."]
current = true
far = 100.0
{nodes}

[node name="UI" type="CanvasLayer" parent="."]

[node name="Hud" type="Label" parent="UI"]
offset_left = 14.0
offset_top = 10.0
text = "loading"
"""


def project(out="out/gallery", lv=0):
    """A catalogue you can page through, one model at a time.

    The grid in the world build is fine for seeing everything at once and no
    good at all for finding number 381 among five hundred. This is the other
    shape of the same data: models two hundred metres apart so only one is ever
    in frame, arrows to step, digits to jump, and a readout saying which object
    type reaches this model and how many of them level 0 places.
    """
    import shutil
    os.makedirs(out, exist_ok=True)
    build(out=out, lv=lv, spacing=VIEWER_SPACING, per_row=1000)
    world_labels(lv, out)
    shutil.copyfile("godot/viewer.gd", f"{out}/viewer.gd")
    pieces = sorted(p for p in os.listdir(out)
                    if p.startswith("gallery") and p.endswith(".gltf"))
    res = "\n".join(f'[ext_resource type="PackedScene" path="res://{p}" '
                     f'id="{2 + i}"]' for i, p in enumerate(pieces))
    nodes = "\n".join(f'\n[node name="g{i}" parent="." '
                       f'instance=ExtResource("{2 + i}")]'
                       for i in range(len(pieces)))
    open(f"{out}/project.godot", "w").write(VIEWER_PROJECT)
    open(f"{out}/view.tscn", "w").write(
        VIEWER_SCENE.format(steps=3 + len(pieces), res=res, nodes=nodes))
    reimport(out)
    print(f"catalogue: godot-4 --path {out}")
    return out


def reimport(out):
    """Make Godot read the geometry that is on disc rather than what it cached.

    **Running the game does not re-import.** Godot keeps converted meshes in
    `.godot/imported/` and only refreshes them when the *editor* runs, so a
    rebuilt `.gltf` beside a stale cache shows the old model with no warning at
    all. That cost a whole round trip: two real bugs were fixed, the files were
    rewritten, and the player looked at the same broken meshes and reported no
    change -- because the cache was three quarters of an hour older than the
    files it was standing in for.
    """
    import shutil
    import subprocess
    godot = shutil.which("godot-4") or shutil.which("godot")
    if not godot:
        print("godot not found; run --import yourself before looking")
        return
    subprocess.run([godot, "--headless", "--path", out, "--import"],
                   capture_output=True, text=True, timeout=900)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "view":
        project()
    else:
        build()
        world_labels()
