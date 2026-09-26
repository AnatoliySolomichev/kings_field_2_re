#!/usr/bin/env python3
"""The compass: the ball with the N in the top-right corner.

    python3 tools/compass.py            the records, the model, the check
    python3 tools/compass.py --check    against every snapshot's RAM
    python3 tools/compass.py --godot    compass.json and its page for the port

It is a model, drawn without perspective. `compass_models` (`0x80081c20`) is
two 0x24-byte records, ended by 0xff:

    +0    on          render_frame: bit 0 of compass_style for the first,
                      bit 1 for the second (0x801b25de; 2 for a new character)
    +2    class       the lighting class, 0x30
    +4    model       model_table[0] -- FDAT.T entry 97 block 9, a ball of
                      26 vertices and 32 faces, 2048 across, the N on its skin
    +8    scale       three s16 over 4096: 0x40 for the first, 0x55 the second
    +0x10 place       (290, 32, 50): x and y on the 320x240 screen, and z
    +0x18 angles      the view's pitch and the ball's own yaw, then 0

`draw_model_cell_lit` (`0x8003c35c`) builds the matrix with the library's
RotMatrix (`0x80076168`) -- Rx(pitch) Ry(yaw) Rz(0), its Ry the textbook one,
not rot_matrix_y's -- turns the class's light matrix by it (L R, so the light
stays put on the screen while the ball turns), scales it, and puts the model
through MVMVA alone: **x and y of R v + place are the screen position**, and z
>> 2 its depth. model_prims (`0x80035ca4`) drops a face whose NCLIP over its
first three points is not positive, and every face of the ball is
semi-transparent: the texels with STP mix half and half with the wall behind,
the N does not. The class's fog is set too, but at z near 50 nothing is past
its near.

The yaw is not the view's. `render_frame` (`0x80042448`) runs a damped spring
each frame, its velocity the word at $gp+0xd8:

    d    = the view yaw (0x801aec5e) less the ball's, -0x7ff..0x800 (0x80016a98)
    v   += d
    v   -= (v + 7) >> 3 if v > 0, (v - 7) >> 3 if v < 0
    yaw += v >> 6            and both records get it, and the view pitch

so the N swings round after a turn, overshoots and settles.
"""
import glob
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
RECORDS = 0x80081C20
STRIDE = 0x24
TRIG = 0x800962E0              # RotMatrix's table: a (sin, cos) pair a word
VIEW_PITCH, VIEW_YAW = 0x801AEC5C, 0x801AEC5E
STYLE = 0x801B25DE


def parse(raw):
    out = []
    for k in range(8):
        rec = raw[k * STRIDE:(k + 1) * STRIDE]
        if len(rec) < STRIDE or rec[0] == 0xFF:
            break
        out.append({"index": k, "on": rec[0], "cls": rec[2],
                    "model": struct.unpack_from("<H", rec, 4)[0],
                    "scale": list(struct.unpack_from("<3h", rec, 8)),
                    "place": list(struct.unpack_from("<3h", rec, 0x10)),
                    "angles": list(struct.unpack_from("<3h", rec, 0x18))})
    return out


def records():
    import disasm
    base, _entry, text = disasm.load_text()
    return parse(text[RECORDS - base:RECORDS - base + 8 * STRIDE])


_T = None


def trig():
    """[(sin, cos)] * 4096, RotMatrix's own table.

    Not the quarter wave game_sin and game_cos read: the library's own, which
    rounds its cosines differently and repeats 0 at 2047 and 2048 -- it
    differs on 3888 of 4096 angles, by a unit or two.
    """
    global _T
    if _T is None:
        import disasm
        base, _entry, text = disasm.load_text()
        w = struct.unpack_from("<4096I", text, TRIG - base)
        _T = [(struct.unpack("<h", struct.pack("<H", v & 0xFFFF))[0],
               struct.unpack("<h", struct.pack("<H", v >> 16))[0]) for v in w]
    return _T


def _sc(a):
    """sin and cos of `a` as 0x80076168 takes them, sign and all."""
    t = trig()
    a = struct.unpack("<h", struct.pack("<H", a & 0xFFFF))[0]
    if a < 0:
        s, c = t[(-a) & 0xFFF]
        return -s, c
    return t[a & 0xFFF]


def rot_matrix(ax, ay, az):
    """0x80076168, the library's RotMatrix: Rx(ax) Ry(ay) Rz(az), 4096 to one."""
    sx, cx = _sc(ax)
    sy, cy = _sc(ay)
    sz, cz = _sc(az)
    ny = -sy               # $t4: the routine carries -sin y, and rounds with it
    return [[(cz * cy) >> 12, (-(sz * cy)) >> 12, sy],
            [((sz * cx) >> 12) - ((((cz * ny) >> 12) * sx) >> 12),
             ((cz * cx) >> 12) + ((((sz * ny) >> 12) * sx) >> 12),
             (-(cy * sx)) >> 12],
            [((sz * sx) >> 12) + ((((cz * ny) >> 12) * cx) >> 12),
             ((cz * sx) >> 12) - ((((sz * ny) >> 12) * cx) >> 12),
             (cy * cx) >> 12]]


def swing(yaw, vel, view_yaw):
    """One frame of render_frame's spring: (yaw, velocity) after it."""
    d = (view_yaw - yaw) & 0xFFF
    if d >= 0x801:
        d -= 0x1000
    vel += d
    if vel > 0:
        vel -= (vel + 7) >> 3
    elif vel < 0:
        vel -= (vel - 7) >> 3
    return (yaw + (vel >> 6)) & 0xFFFF, vel


def check(out=sys.stdout):
    """What a snapshot's RAM can say: the switches, the pitch, the twin yaws."""
    import movement
    same = sum(1 for a in range(4096)
               if _sc(a) == (movement.game_sin(a), movement.game_cos(a)))
    ok = bad = snaps = 0
    for path in sorted(glob.glob(os.path.join(ROOT, "out", "snap", "*.ram"))):
        r = open(path, "rb").read()
        style = r[STYLE & 0x1FFFFF]
        if not style:
            continue
        snaps += 1
        live = parse(r[RECORDS & 0x1FFFFF:(RECORDS & 0x1FFFFF) + 8 * STRIDE])
        bare = not any(x["on"] for x in live)      # render_frame_bare's frame
        pitch = struct.unpack_from("<h", r, VIEW_PITCH & 0x1FFFFF)[0]
        yaws = {x["angles"][1] for x in live}
        tests = [len(yaws) == 1]
        for x in live:
            want_on = 0 if bare else (style >> x["index"]) & 1
            tests += [x["on"] == want_on,
                      bare or x["angles"][0] == pitch]
        for t in tests:
            ok += bool(t)
            bad += not t
            if not t:
                print(f"  {os.path.basename(path)}: a field differs", file=out)
    print(f"  {ok} of {ok + bad} switches, pitches and twin yaws over {snaps} "
          f"snapshots; RotMatrix's own table differs from the quarter wave "
          f"on {4096 - same} of 4096 angles, so the port carries it", file=out)
    return bad == 0


def export(out_dir):
    """compass.json -- records, model, light -- and the page it samples."""
    import lighting
    import modelbank
    import rtim
    import tim
    recs = records()
    _flags, objs = modelbank.load(recs[0]["model"])
    o = objs[0]
    look = lighting.table()
    base = recs[0]["cls"] * 108

    def mat(off):
        hw = struct.unpack_from("<10h", look, base + off)
        return [list(hw[0:3]), list(hw[3:6]), list(hw[6:9])]
    faces = []
    pages = set()
    for pr in o.prims:
        if len(pr.verts) < 3:
            continue
        faces.append({"v": list(pr.verts), "n": list(pr.norms), "uv": pr.uvs,
                      "quad": pr.quad, "page": [pr.tpage, pr.clut]})
        pages.add((pr.tpage, pr.clut))
    # Every face is semi-transparent (modes 0x36 and 0x3e), so a texel with STP
    # set mixes half and half with what is behind -- page rate 0 -- and the rest
    # is solid: the N is the solid part, which is why it reads so plainly.
    vram = rtim.level_vram(0)
    for f in faces:
        f["png"] = "compass_%04x_%04x.png" % tuple(f["page"])
    for tp, cl in pages:
        tim.write_png(os.path.join(out_dir, f"compass_{tp:04x}_{cl:04x}.png"),
                      256, 256, rtim.page4(vram, tp, cl, semi=True))
    doc = {"_note": "compass_models (0x80081c20) and model_table[0]; see "
                    "tools/compass.py",
           "records": recs, "verts": [list(v) for v in o.verts],
           "normals": [list(n) for n in o.normals], "faces": faces,
           "light": mat(0), "colour": mat(0x50),
           "trig": [c for pair in trig() for c in pair],
           "back": [look[base + 0x64 + k] * 16 for k in range(3)]}
    path = os.path.join(out_dir, "compass.json")
    with open(path, "w") as f:
        json.dump(doc, f, separators=(",", ":"))
    return path


def main():
    a = sys.argv[1] if len(sys.argv) > 1 else None
    if a == "--check":
        sys.exit(0 if check() else 1)
    if a == "--godot":
        print(export(os.path.join(ROOT, "out", "godot")))
        return
    print(__doc__)
    for r in records():
        print(f"  record {r['index']}: class {r['cls']:#x}, model {r['model']}, "
              f"scale {r['scale']}, place {r['place']}")
    check()


if __name__ == "__main__":
    main()
