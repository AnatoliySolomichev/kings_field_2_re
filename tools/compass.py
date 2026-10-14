#!/usr/bin/env python3
"""The compass: the ball with the N in the top-right corner.

    python3 tools/compass.py            the records, the model, the check
    python3 tools/compass.py --check    against every snapshot's RAM
    python3 tools/compass.py --godot    compass.json and its page for the port
    python3 tools/compass.py --quads    the quads' shapes on the whole-pixel
                                        screen, at every pitch and yaw

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

A quad goes to the GPU as the record's four corners in order (the arm for mode
0x3c, `0x80036384`, stores them as XY0 to XY3), and the GPU draws a quad as
the triangles 0 1 2 and 1 2 3 whichever way each turns. NCLIP has looked at
0 1 2 alone, so at the rim a quad seen edge on reaches the GPU bent or with
its corners crossed, and is drawn all the same. `--quads` counts those shapes
over every pitch the view takes and every yaw as RotMatrix reads one, and what
Godot's triangulation made of each as the polygon 0 1 3 2 -- which is how
godot/compass.gd drew them until it handed over the GPU's two triangles: a
crossed one it refused, "Invalid polygon data, triangulation failed".
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
PITCH_LIMIT = 0x2BC            # player_look (0x8002f5c0) stops the pitch here


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


def _shape(c):
    """A closed path of four corners: convex, concave, flat (three corners in
    a line) or crossed -- two turns each way, its edges crossing."""
    t = [(c[k][0] - c[k - 1][0]) * (c[(k + 1) % 4][1] - c[k - 1][1])
         - (c[k][1] - c[k - 1][1]) * (c[(k + 1) % 4][0] - c[k - 1][0])
         for k in range(4)]
    if 0 in t:
        return "flat"
    left = sum(1 for x in t if x > 0)
    return "convex" if left in (0, 4) else "crossed" if left == 2 else "concave"


def _ear_clip(c):
    """Godot's triangulation of a polygon, which `draw_polygon` runs first.

    `Triangulate::triangulate` (core/math/triangulate.cpp, Godot 4): ear
    clipping round a counter-clockwise copy, a second round that allows a flat
    triangle, and None where that runs out too -- "Invalid polygon data,
    triangulation failed", and nothing drawn. Its tests are floats against an
    epsilon of 1e-5; on whole-pixel corners every product is a whole number,
    so the epsilon only tells zero from not zero and integers say the same.
    Headless Godot 4.7.2 refused as many quads as this, 2368 of 2368 over 4495
    pairs.
    """
    n = len(c)
    area = sum(c[p][0] * c[q][1] - c[p][1] * c[q][0]
               for p, q in zip(range(-1, n - 1), range(n)))
    v_ = list(range(n)) if area > 0 else list(range(n - 1, -1, -1))
    tris, relaxed, nv = [], False, n
    count, v = 2 * nv, nv - 1
    while nv > 2:
        was = count
        count -= 1
        if was <= 0:
            if relaxed:
                return None
            count, relaxed = 2 * nv, True
        u = v if v < nv else 0
        v = u + 1 if u + 1 < nv else 0
        w = v + 1 if v + 1 < nv else 0
        (ax, ay), (bx, by), (cx, cy) = c[v_[u]], c[v_[v]], c[v_[w]]
        turn = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
        if turn < 0 or (turn == 0 and not relaxed):
            continue
        ear = True
        for p in range(nv):
            if p in (u, v, w):
                continue
            px, py = c[v_[p]]
            k = ((cx - bx) * (py - by) - (cy - by) * (px - bx),
                 (ax - cx) * (py - cy) - (ay - cy) * (px - cx),
                 (bx - ax) * (py - ay) - (by - ay) * (px - ax))
            if all(x > 0 for x in k) if relaxed else all(x >= 0 for x in k):
                ear = False
                break
        if ear:
            tris.append((v_[u], v_[v], v_[w]))
            del v_[v]
            nv -= 1
            count = 2 * nv
    return tris


def quads(out=sys.stdout):
    """The quads NCLIP lets through, at every pitch and every yaw: their
    shapes on the whole-pixel screen, and what Godot made of each as the
    polygon 0 1 3 2.

    The pitch is the port's, -0x2bc..0x2bc kept in 12 bits; the yaw every one
    of the 8192 ways RotMatrix reads one (0..0xfff, and 0xf000..0xffff, which
    it takes as negative). x of R v depends on the yaw alone and y on both, so
    each screen the pairs make is worked once and counted for each pair.
    """
    import modelbank
    rec = next(r for r in records() if r["index"] == 1)    # compass_style 2
    o = modelbank.load(rec["model"])[1][0]
    verts = [tuple(v) for v in o.verts]
    qs = [tuple(p.verts) for p in o.prims if p.quad and len(p.verts) == 4]
    s0, s1, s2 = rec["scale"]
    x0, y0 = rec["place"][0], rec["place"][1]
    sz, cz = _sc(0)
    pitches = []
    for p in range(-PITCH_LIMIT, PITCH_LIMIT + 1):
        sx, cx = _sc(p & 0xFFF)
        pitches.append((sx, (sz * cx) >> 12, (cz * cx) >> 12))
    seen = {}
    for yaw in list(range(0x1000)) + list(range(0xF000, 0x10000)):
        sy, cy = _sc(yaw)
        ny = -sy                                      # as rot_matrix rounds
        row0 = ((((cz * cy) >> 12) * s0) >> 12,
                (((-(sz * cy)) >> 12) * s1) >> 12, (sy * s2) >> 12)
        czny, szny = (cz * ny) >> 12, (sz * ny) >> 12
        for sx, szcx, czcx in pitches:
            key = row0 + ((((szcx - ((czny * sx) >> 12)) * s0) >> 12),
                          (((czcx + ((szny * sx) >> 12)) * s1) >> 12),
                          ((((-(cy * sx)) >> 12) * s2) >> 12))
            seen[key] = seen.get(key, 0) + 1
    gpu = {frozenset((0, 1, 2)), frozenset((1, 2, 3))}
    corner = (0, 1, 3, 2)                       # polygon slot -> quad corner
    shapes, made = {}, {}
    pairs = sum(seen.values())
    crossed_pairs = visible = 0
    for (a0, a1, a2, b0, b1, b2), n in seen.items():
        xs = [((a0 * x + a1 * y + a2 * z) >> 12) + x0 for x, y, z in verts]
        ys = [((b0 * x + b1 * y + b2 * z) >> 12) + y0 for x, y, z in verts]
        crossed = False
        for q in qs:
            (ax, bx, cx, dx), (ay, by, cy, dy) = ([xs[k] for k in q],
                                                  [ys[k] for k in q])
            if ax * by + bx * cy + cx * ay - ax * cy - bx * ay - cx * by <= 0:
                continue
            visible += n
            poly = ((ax, ay), (bx, by), (dx, dy), (cx, cy))
            sh = _shape(poly)
            shapes[sh] = shapes.get(sh, 0) + n
            crossed |= sh == "crossed"
            tris = _ear_clip(poly)
            how = ("refused" if tris is None else
                   "1-2" if {frozenset(corner[k] for k in t) for t in tris} == gpu
                   else "0-3")
            made[how, sh] = made.get((how, sh), 0) + n
        crossed_pairs += n if crossed else 0

    def by_shape(how):
        got = [(sh, made[how, sh]) for sh in ("convex", "concave", "flat",
                                               "crossed") if (how, sh) in made]
        return (f"{sum(c for _s, c in got)} ("
                + ", ".join(f"{c} {sh}" for sh, c in got) + ")")
    print(f"  {pairs} pairs of pitch and yaw make {len(seen)} screens; "
          f"{visible} quads pass NCLIP", file=out)
    print("  their shapes: " + ", ".join(
        f"{shapes.get(sh, 0)} {sh}" for sh in ("convex", "concave", "flat",
                                               "crossed"))
          + f" -- a crossed one in {crossed_pairs} pairs, "
          f"{100.0 * crossed_pairs / pairs:.2f} %", file=out)
    print(f"  as the polygon 0 1 3 2, Godot's triangulation splits "
          f"{by_shape('1-2')} along 1-2 as the GPU does, {by_shape('0-3')} "
          f"along 0-3, and refuses {by_shape('refused')}", file=out)


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
    if a == "--quads":
        quads()
        return
    print(__doc__)
    for r in records():
        print(f"  record {r['index']}: class {r['cls']:#x}, model {r['model']}, "
              f"scale {r['scale']}, place {r['place']}")
    check()


if __name__ == "__main__":
    main()
